// =============================================================================
// maintenance_decoder.cpp - Identity, clock, exercise and service decoding
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "maintenance_decoder.h"

#include <cstdio>

#include "register_map.h"


namespace genmon {

namespace {

// =============================================================================
// Constants
// =============================================================================

constexpr const char* kWeekdays[] = {
    "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
};

constexpr const char* kMonths[] = {
    "January", "February", "March",     "April",   "May",      "June",
    "July",    "August",   "September", "October", "November", "December",
};

constexpr uint8_t kReplacedControllerMarker = 0xFF;
constexpr int     kMinimumClockYear         = 16;   // years before 2016 mean "not set"
constexpr int     kMaxMonthlyExerciseDay    = 28;
constexpr double  kMinutesPerHour           = 60.0;

enum FrequencyCode : uint8_t {
    kWeekly   = 0,
    kBiweekly = 1,
    kMonthly  = 2,
};

// One service item: a label, its hours-remaining register and the register
// holding its due date as days since 1970. A zero register means "absent".
struct ServiceItem {
    const char* label;
    uint16_t    hoursRegister;
    uint16_t    dateRegister;
};

constexpr ServiceItem kEvolutionService[] = {
    {"Service A Due", reg::kServiceAHours, reg::kServiceADate},
    {"Service B Due", reg::kServiceBHours, reg::kServiceBDate},
};

constexpr ServiceItem kEvolutionAirBattery = {"Battery Check Due", 0, reg::kService22Date};

// Nexus reuses the same service registers with different meanings, so the
// Evolution-oriented register names below do not describe Nexus contents.
constexpr ServiceItem kNexusAirService[] = {
    {"Air Filter Service Due",         reg::kService1CHours, reg::kService22Date},
    {"Oil and Oil Filter Service Due", reg::kServiceBHours,  reg::kService20Date},
    {"Spark Plug Service Due",         reg::kServiceAHours,  reg::kServiceADate},
    {"Battery Service Due",            reg::kServiceBDate,   reg::kService1DDate},
};

constexpr ServiceItem kNexusLiquidService[] = {
    {"Air Filter Service Due",    reg::kService1CHours, reg::kService1DDate},
    {"Oil Change and Filter Due", reg::kServiceAHours,  reg::kServiceADate},
    {"Spark Plug Change Due",     reg::kServiceBHours,  reg::kServiceBDate},
};


// =============================================================================
// Helpers
// =============================================================================

uint8_t highByte(uint16_t value) { return static_cast<uint8_t>(value >> 8); }
uint8_t lowByte(uint16_t value)  { return static_cast<uint8_t>(value & 0xFF); }


std::string formatServiceItem(const RegisterCache& registers, const ServiceItem& item, bool addOneDay) {
    std::string text;

    if (item.hoursRegister != 0) {
        const auto hours = registers.u16(item.hoursRegister);
        if (hours) {
            text = std::to_string(*hours) + " hrs";
        }
    }

    if (item.dateRegister != 0) {
        const auto days = registers.u16(item.dateRegister);
        if (days) {
            // Most controllers store the day before the due date.
            const std::string date = dateFromEpochDays(static_cast<int64_t>(*days) + (addOneDay ? 1 : 0));
            text += text.empty() ? date : " or " + date;
        }
    }
    return text;
}


template <size_t N>
void appendItems(std::vector<LabeledValue>& out, const RegisterCache& registers,
                 const ServiceItem (&items)[N], bool includeDates, bool addOneDay) {
    for (const ServiceItem& item : items) {
        ServiceItem effective = item;
        if (!includeDates) {
            effective.dateRegister = 0;
        }
        out.push_back({item.label, formatServiceItem(registers, effective, addOneDay)});
    }
}

}  // namespace


// =============================================================================
// Identity
// =============================================================================

std::optional<uint8_t> firmwareVersionByte(const RegisterCache& registers) {
    const auto value = registers.u16(reg::kVersions);
    if (!value) {
        return std::nullopt;
    }
    return lowByte(*value);
}


std::optional<uint8_t> hardwareVersionByte(const RegisterCache& registers) {
    const auto value = registers.u16(reg::kVersions);
    if (!value) {
        return std::nullopt;
    }
    return highByte(*value);
}


std::string formatVersion(std::optional<uint8_t> versionByte) {
    if (!versionByte) {
        return "";
    }
    char buffer[12];
    std::snprintf(buffer, sizeof(buffer), "V%d.%02d", *versionByte / 100, *versionByte % 100);
    return buffer;
}


std::string serialNumber(const RegisterCache& registers, const MonitorOptions& options) {
    const auto bytes = registers.bytes(reg::kSerialNumber);
    if (!bytes || bytes->empty()) {
        return "";
    }
    if ((*bytes)[0] == kReplacedControllerMarker) {
        if (!options.serialNumberOverride.empty()) {
            return options.serialNumberOverride;
        }
        return "None - Controller has been replaced";
    }

    std::string text;
    for (uint8_t byte : *bytes) {
        if (byte == 0) {
            break;
        }
        text.push_back(static_cast<char>(byte));
    }
    return text;
}


// =============================================================================
// Clock
// =============================================================================

std::optional<GeneratorClock> generatorClock(const RegisterCache& registers) {
    const auto hourMinute  = registers.u16(reg::kTimeHourMinute);
    const auto monthDay    = registers.u16(reg::kTimeMonthDay);
    const auto weekdayYear = registers.u16(reg::kTimeWeekdayYear);
    if (!hourMinute || !monthDay || !weekdayYear) {
        return std::nullopt;
    }

    GeneratorClock clock{};
    clock.hour    = highByte(*hourMinute);
    clock.minute  = lowByte(*hourMinute);
    clock.month   = highByte(*monthDay);
    clock.day     = lowByte(*monthDay);
    clock.weekday = highByte(*weekdayYear);
    clock.year    = lowByte(*weekdayYear);

    const bool valid = clock.hour <= 23 && clock.minute <= 59 &&
                       clock.month >= 1 && clock.month <= 12 &&
                       clock.day >= 1 && clock.day <= 31 &&
                       clock.weekday <= 6 && clock.year >= kMinimumClockYear;
    if (!valid) {
        return std::nullopt;
    }
    clock.year += 2000;
    return clock;
}


std::string formatClock(const GeneratorClock& clock) {
    char buffer[64];
    std::snprintf(buffer, sizeof(buffer), "%s %s %d, %d %02d:%02d",
                  weekdayName(clock.weekday), kMonths[clock.month - 1],
                  clock.day, clock.year, clock.hour, clock.minute);
    return buffer;
}


const char* weekdayName(int weekday) {
    if (weekday < 0 || weekday > 6) {
        return "";
    }
    return kWeekdays[weekday];
}


std::string dateFromEpochDays(int64_t days) {
    // Howard Hinnant's civil-from-days algorithm; avoids depending on the
    // platform's time zone database for a date-only value.
    const int64_t shifted    = days + 719468;
    const int64_t era        = (shifted >= 0 ? shifted : shifted - 146096) / 146097;
    const int64_t dayOfEra   = shifted - era * 146097;
    const int64_t yearOfEra  = (dayOfEra - dayOfEra / 1460 + dayOfEra / 36524 - dayOfEra / 146096) / 365;
    const int64_t dayOfYear  = dayOfEra - (365 * yearOfEra + yearOfEra / 4 - yearOfEra / 100);
    const int64_t monthIndex = (5 * dayOfYear + 2) / 153;
    const int64_t day        = dayOfYear - (153 * monthIndex + 2) / 5 + 1;
    const int64_t month      = monthIndex < 10 ? monthIndex + 3 : monthIndex - 9;
    const int64_t year       = yearOfEra + era * 400 + (month <= 2 ? 1 : 0);

    char buffer[16];
    std::snprintf(buffer, sizeof(buffer), "%02d/%02d/%04d",
                  static_cast<int>(month), static_cast<int>(day), static_cast<int>(year));
    return buffer;
}


// =============================================================================
// Exercise
// =============================================================================

std::string exerciseSchedule(const RegisterCache& registers, const ControllerInfo& info) {
    uint8_t frequency = kWeekly;
    if (info.enhancedExercise) {
        const auto value = registers.u16(reg::kExerciseFrequency);
        if (!value || lowByte(*value) > kMonthly) {
            return "";
        }
        frequency = lowByte(*value);
    }

    const auto time = registers.u16(reg::kExerciseTime);
    const auto day  = registers.u16(reg::kExerciseDay);
    if (!time || !day || highByte(*time) > 23 || lowByte(*time) > 59) {
        return "";
    }

    std::string schedule;
    if (frequency == kMonthly) {
        const auto dayOfMonth = registers.u16(reg::kExerciseDayWrite);
        if (!dayOfMonth || lowByte(*dayOfMonth) > kMaxMonthlyExerciseDay) {
            return "";
        }
        schedule = "Monthly Day-" + std::to_string(lowByte(*dayOfMonth));
    } else {
        if (highByte(*day) > 6) {
            return "";
        }
        schedule  = frequency == kBiweekly ? "Biweekly " : "Weekly ";
        schedule += weekdayName(highByte(*day));
    }

    char clock[8];
    std::snprintf(clock, sizeof(clock), " %02d:%02d", highByte(*time), lowByte(*time));
    schedule += clock;

    switch (lowByte(*day)) {
        case 0:  schedule += " Quiet Mode Off";     break;
        case 1:  schedule += " Quiet Mode On";      break;
        default: schedule += " Quiet Mode Unknown"; break;
    }
    return schedule;
}


// =============================================================================
// Service
// =============================================================================

std::vector<LabeledValue> serviceSchedule(const RegisterCache& registers, const ControllerInfo& info) {
    std::vector<LabeledValue> items;
    const bool addOneDay = !info.evolution2;

    if (info.evolution) {
        appendItems(items, registers, kEvolutionService, !info.powerPact, addOneDay);
        if (!info.liquidCooled && !info.powerPact) {
            items.push_back({kEvolutionAirBattery.label, formatServiceItem(registers, kEvolutionAirBattery, addOneDay)});
        }
    } else if (info.liquidCooled) {
        appendItems(items, registers, kNexusLiquidService, true, addOneDay);
    } else {
        appendItems(items, registers, kNexusAirService, true, addOneDay);
    }
    return items;
}


std::optional<double> runHours(const RegisterCache&  registers,
                               const ControllerInfo& info,
                               const MonitorOptions& options) {
    // Evolution liquid cooled keeps total minutes; everything else whole hours.
    if (info.evolution && info.liquidCooled) {
        const auto minutes = registers.u32(reg::kRunMinutes);
        if (!minutes) {
            return std::nullopt;
        }
        return *minutes / kMinutesPerHour + options.additionalRunHours;
    }

    const auto hours = registers.u32(reg::kRunHours);
    if (!hours) {
        return std::nullopt;
    }
    return static_cast<double>(*hours) + options.additionalRunHours;
}

}  // namespace genmon
