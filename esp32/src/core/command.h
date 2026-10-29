// =============================================================================
// command.h - genmon command parsing and register-write planning
// =============================================================================
//
// Commands use genmon's text syntax so the same strings work from the web UI,
// from Home Assistant buttons (data/homeassistant/*.json) and from the
// genmqtt-style "generator/command" topic:
//   setremote=start | stop | starttransfer | startexercise | resetalarm |
//             auto | manual | off
//   setexercise=Monday,12:20[,weekly|biweekly]   setexercise=15,12:20,monthly
//   setquiet=on | off
//   settime
// Parsing and planning are separate so the planner can be unit tested
// against the exact register writes genmon would make.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "controller_info.h"
#include "maintenance_decoder.h"


namespace genmon {

// =============================================================================
// Types
// =============================================================================

enum class CommandType : uint8_t {
    RemoteStart,
    RemoteStop,
    StartTransfer,
    StartExercise,
    ResetAlarm,
    ButtonAuto,
    ButtonManual,
    ButtonOff,
    SetExercise,
    SetQuietMode,
    SetTime,
};

enum class ExerciseFrequency : uint8_t {
    Weekly   = 0,
    Biweekly = 1,
    Monthly  = 2,
};

struct GeneratorCommand {
    CommandType       type      = CommandType::RemoteStop;
    ExerciseFrequency frequency = ExerciseFrequency::Weekly;
    uint8_t           day       = 0;   // weekday (Sunday = 0) or day of month
    uint8_t           hour      = 0;
    uint8_t           minute    = 0;
    bool              quietOn   = false;
};

struct ParsedCommand {
    std::optional<GeneratorCommand> command;
    std::string                     error;
};

struct RegisterWrite {
    uint16_t             startRegister;
    std::vector<uint8_t> data;
};

struct CommandPlan {
    std::vector<RegisterWrite> writes;
    std::string                error;   // non-empty when the command cannot run
};


// =============================================================================
// Functions
// =============================================================================

ParsedCommand parseCommand(const std::string& text);

// `generatorClock` is needed only for the legacy (Nexus) exercise write and
// `now` only for settime; both may be empty otherwise.
CommandPlan planCommand(const GeneratorCommand&              command,
                        const ControllerInfo&                info,
                        const std::optional<GeneratorClock>& generatorClock,
                        const std::optional<GeneratorClock>& now);

}  // namespace genmon
