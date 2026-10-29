// =============================================================================
// command.cpp - genmon command parsing and register-write planning
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "command.h"

#include <algorithm>
#include <cctype>
#include <cstdlib>

#include "register_map.h"


namespace genmon {

namespace {

// =============================================================================
// Constants
// =============================================================================

struct NamedRemote {
    const char* name;
    CommandType type;
    uint16_t    index;   // value written to the indexed command register
};

constexpr NamedRemote kRemoteCommands[] = {
    {"stop",          CommandType::RemoteStop,    0x0000},
    {"start",         CommandType::RemoteStart,   0x0001},
    {"starttransfer", CommandType::StartTransfer, 0x0002},
    {"startexercise", CommandType::StartExercise, 0x0003},
    {"resetalarm",    CommandType::ResetAlarm,    0x000D},
    {"manual",        CommandType::ButtonManual,  0x000E},
    {"auto",          CommandType::ButtonAuto,    0x000F},
    {"off",           CommandType::ButtonOff,     0x0010},
};

constexpr uint16_t kLegacyExerciseIndex  = 0x0006;
constexpr int      kLegacySecondsPerStep = 128;   // the controller counts in 128 s steps
constexpr int      kMinutesPerDay        = 24 * 60;
constexpr int      kMinutesPerWeek       = 7 * kMinutesPerDay;
constexpr int      kMaxMonthlyDay        = 28;
constexpr int      kYearBase             = 2000;


// =============================================================================
// Helpers
// =============================================================================

std::string lowercase(std::string text) {
    std::transform(text.begin(), text.end(), text.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return text;
}


std::string trim(const std::string& text) {
    const size_t first = text.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) {
        return "";
    }
    const size_t last = text.find_last_not_of(" \t\r\n");
    return text.substr(first, last - first + 1);
}


std::vector<std::string> split(const std::string& text, char separator) {
    std::vector<std::string> parts;
    size_t start = 0;
    while (true) {
        const size_t found = text.find(separator, start);
        parts.push_back(trim(text.substr(start, found - start)));
        if (found == std::string::npos) {
            return parts;
        }
        start = found + 1;
    }
}


bool parseInteger(const std::string& text, int& out) {
    if (text.empty() || !std::all_of(text.begin(), text.end(), [](unsigned char c) { return std::isdigit(c); })) {
        return false;
    }
    out = std::atoi(text.c_str());
    return true;
}


int weekdayFromName(const std::string& name) {
    static const char* const kNames[] = {
        "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    };
    for (int index = 0; index < 7; ++index) {
        if (name == kNames[index]) {
            return index;
        }
    }
    return -1;
}


ParsedCommand failure(const std::string& message) {
    return ParsedCommand{std::nullopt, message};
}


ParsedCommand parseRemote(const std::string& value) {
    for (const NamedRemote& remote : kRemoteCommands) {
        if (value == remote.name) {
            GeneratorCommand command;
            command.type = remote.type;
            return ParsedCommand{command, ""};
        }
    }
    return failure("Unknown setremote value: " + value);
}


ParsedCommand parseExercise(const std::string& value) {
    const std::vector<std::string> items = split(value, ',');
    if (items.size() < 2 || items.size() > 3) {
        return failure("Expected setexercise=Day,HH:MM[,weekly|biweekly|monthly]");
    }

    GeneratorCommand command;
    command.type = CommandType::SetExercise;

    const std::string mode = items.size() == 3 ? items[2] : "weekly";
    if (mode == "weekly") {
        command.frequency = ExerciseFrequency::Weekly;
    } else if (mode == "biweekly") {
        command.frequency = ExerciseFrequency::Biweekly;
    } else if (mode == "monthly") {
        command.frequency = ExerciseFrequency::Monthly;
    } else {
        return failure("Exercise frequency must be weekly, biweekly or monthly");
    }

    const std::vector<std::string> clock = split(items[1], ':');
    int hour   = -1;
    int minute = -1;
    if (clock.size() != 2 || !parseInteger(clock[0], hour) || !parseInteger(clock[1], minute) ||
        hour > 23 || minute > 59) {
        return failure("Exercise time must be HH:MM (24 hour)");
    }

    int day = -1;
    if (command.frequency == ExerciseFrequency::Monthly) {
        if (!parseInteger(items[0], day) || day < 1 || day > kMaxMonthlyDay) {
            return failure("Monthly exercise day must be 1-28");
        }
    } else {
        day = weekdayFromName(items[0]);
        if (day < 0) {
            return failure("Unknown day of week: " + items[0]);
        }
    }

    command.day    = static_cast<uint8_t>(day);
    command.hour   = static_cast<uint8_t>(hour);
    command.minute = static_cast<uint8_t>(minute);
    return ParsedCommand{command, ""};
}


std::vector<uint8_t> word(uint16_t value) {
    return {static_cast<uint8_t>(value >> 8), static_cast<uint8_t>(value & 0xFF)};
}


// Indexed commands: an optional value goes to kCommandValue first, then the
// command number to kCommandIndex triggers the action.
void appendIndexed(CommandPlan& plan, uint16_t index, std::optional<uint16_t> value = std::nullopt) {
    if (value) {
        plan.writes.push_back({reg::kCommandValue, word(*value)});
    }
    plan.writes.push_back({reg::kCommandIndex, word(index)});
}


uint16_t remoteIndex(CommandType type) {
    for (const NamedRemote& remote : kRemoteCommands) {
        if (remote.type == type) {
            return remote.index;
        }
    }
    return 0;
}


// Older firmware only accepts "seconds from now until the next exercise",
// in 128-second steps, relative to the controller's own clock.
CommandPlan planLegacyExercise(const GeneratorCommand& command, const std::optional<GeneratorClock>& clock) {
    CommandPlan plan;
    if (command.frequency != ExerciseFrequency::Weekly) {
        plan.error = "This controller only supports a weekly exercise schedule";
        return plan;
    }
    if (!clock) {
        plan.error = "Generator clock has not been read yet; try again shortly";
        return plan;
    }

    const int daysAhead = (command.day - clock->weekday + 7) % 7;
    int minutes = daysAhead * kMinutesPerDay +
                  (command.hour * 60 + command.minute) - (clock->hour * 60 + clock->minute);
    if (minutes < 0) {
        minutes += kMinutesPerWeek;
    }

    appendIndexed(plan, kLegacyExerciseIndex, static_cast<uint16_t>(minutes * 60 / kLegacySecondsPerStep));
    return plan;
}


CommandPlan planExercise(const GeneratorCommand&              command,
                         const ControllerInfo&                info,
                         const std::optional<GeneratorClock>& clock) {
    if (info.legacyExerciseWrite) {
        return planLegacyExercise(command, clock);
    }

    CommandPlan plan;
    if (command.frequency != ExerciseFrequency::Weekly && !info.enhancedExercise) {
        plan.error = "Biweekly and monthly exercise are not supported by this controller";
        return plan;
    }
    if (info.enhancedExercise) {
        plan.writes.push_back({reg::kExerciseFrequency, {0x00, static_cast<uint8_t>(command.frequency)}});
    }
    plan.writes.push_back({reg::kExerciseDayWrite,  {0x00, command.day}});
    plan.writes.push_back({reg::kExerciseTimeWrite, {command.hour, command.minute}});
    return plan;
}

}  // namespace


// =============================================================================
// Core logic
// =============================================================================

ParsedCommand parseCommand(const std::string& text) {
    const std::string normalized = lowercase(trim(text));
    if (normalized == "settime") {
        GeneratorCommand command;
        command.type = CommandType::SetTime;
        return ParsedCommand{command, ""};
    }

    const size_t equals = normalized.find('=');
    if (equals == std::string::npos) {
        return failure("Unknown command: " + text);
    }
    const std::string name  = trim(normalized.substr(0, equals));
    const std::string value = trim(normalized.substr(equals + 1));

    if (name == "setremote") {
        return parseRemote(value);
    }
    if (name == "setexercise") {
        return parseExercise(value);
    }
    if (name == "setquiet") {
        if (value != "on" && value != "off") {
            return failure("Expected setquiet=on or setquiet=off");
        }
        GeneratorCommand command;
        command.type    = CommandType::SetQuietMode;
        command.quietOn = value == "on";
        return ParsedCommand{command, ""};
    }
    return failure("Unknown command: " + text);
}


CommandPlan planCommand(const GeneratorCommand&              command,
                        const ControllerInfo&                info,
                        const std::optional<GeneratorClock>& generatorClock,
                        const std::optional<GeneratorClock>& now) {
    CommandPlan plan;
    const bool evolutionLiquid = info.evolution && info.liquidCooled;

    switch (command.type) {
        case CommandType::RemoteStart:
        case CommandType::RemoteStop:
        case CommandType::StartTransfer:
        case CommandType::StartExercise:
            appendIndexed(plan, remoteIndex(command.type));
            return plan;

        case CommandType::ResetAlarm:
            if (!evolutionLiquid && !info.evolution2) {
                plan.error = "Alarm reset is only supported on Evolution liquid cooled and Evolution 2.0";
                return plan;
            }
            appendIndexed(plan, remoteIndex(command.type));
            return plan;

        case CommandType::ButtonAuto:
        case CommandType::ButtonManual:
        case CommandType::ButtonOff:
            if (!evolutionLiquid || info.evolution45L) {
                plan.error = "Remote panel buttons are only supported on Evolution liquid cooled";
                return plan;
            }
            appendIndexed(plan, remoteIndex(command.type));
            return plan;

        case CommandType::SetExercise:
            return planExercise(command, info, generatorClock);

        case CommandType::SetQuietMode:
            if (!info.evolution || !(info.liquidCooled || info.evolution2)) {
                plan.error = "Quiet mode cannot be set on this controller";
                return plan;
            }
            plan.writes.push_back({reg::kQuietMode, {0x00, static_cast<uint8_t>(command.quietOn ? 1 : 0)}});
            return plan;

        case CommandType::SetTime:
            if (!now) {
                plan.error = "Monitor clock is not set (no NTP time yet)";
                return plan;
            }
            // Day of week is written as zero; the controller derives it.
            plan.writes.push_back({reg::kTimeHourMinute, {
                static_cast<uint8_t>(now->hour),  static_cast<uint8_t>(now->minute),
                static_cast<uint8_t>(now->month), static_cast<uint8_t>(now->day),
                0x00,                             static_cast<uint8_t>(now->year - kYearBase),
            }});
            return plan;
    }
    plan.error = "Unsupported command";
    return plan;
}

}  // namespace genmon
