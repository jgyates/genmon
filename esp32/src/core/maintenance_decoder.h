// =============================================================================
// maintenance_decoder.h - Identity, clock, exercise and service decoding
// =============================================================================
//
// Slow-changing information: versions, serial number, the controller's clock,
// the exercise schedule, service counters and run hours.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "controller_info.h"
#include "generator_state.h"
#include "monitor_options.h"
#include "register_cache.h"


namespace genmon {

// =============================================================================
// Types
// =============================================================================

struct GeneratorClock {
    int year;      // four digits
    int month;     // 1-12
    int day;       // 1-31
    int weekday;   // 0 = Sunday
    int hour;
    int minute;
};


// =============================================================================
// Functions
// =============================================================================

// Raw version bytes from register 0x002A, e.g. 143 for V1.43.
std::optional<uint8_t> firmwareVersionByte(const RegisterCache& registers);
std::optional<uint8_t> hardwareVersionByte(const RegisterCache& registers);
std::string            formatVersion(std::optional<uint8_t> versionByte);

std::string serialNumber(const RegisterCache& registers, const MonitorOptions& options);

std::optional<GeneratorClock> generatorClock(const RegisterCache& registers);
std::string                   formatClock(const GeneratorClock& clock);

// e.g. "Weekly Saturday 13:30 Quiet Mode On", empty if not yet readable.
std::string exerciseSchedule(const RegisterCache& registers, const ControllerInfo& info);

std::vector<LabeledValue> serviceSchedule(const RegisterCache& registers, const ControllerInfo& info);

std::optional<double> runHours(const RegisterCache&  registers,
                               const ControllerInfo& info,
                               const MonitorOptions& options);

// Calendar date for a count of days since 1970-01-01, as MM/DD/YYYY.
std::string dateFromEpochDays(int64_t days);

const char* weekdayName(int weekday);

}  // namespace genmon
