// =============================================================================
// status_decoder.h - Decoding of the 32-bit status word at register 0x0001
// =============================================================================
//
// The high word of register 0x0001 encodes the engine state (bits 16-20) and
// the low word encodes the switch position or the active alarm. Everything
// the monitor reports about "what is the generator doing" derives from it.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <cstdint>
#include <optional>
#include <string>

#include "controller_info.h"
#include "register_cache.h"


namespace genmon {

// =============================================================================
// Types
// =============================================================================

// Evolution 2.0 controllers sometimes return text fragments or out-of-range
// values in the status register. This filter replaces them with the last
// good value so a single bad read does not raise a false alarm.
class StatusFilter {
public:
    std::optional<uint32_t> accept(uint32_t raw, const ControllerInfo& info, bool ignoreUnknown);
    void reset();

private:
    std::optional<uint32_t> lastGood_;
};


// =============================================================================
// Functions
// =============================================================================

// False when bits that are never set by a real status word are set.
bool isStatusWordPlausible(uint32_t status);

// "Auto", "Off", "Manual", "Two Wire Stop", "Off via Remote Command",
// or "System in Alarm".
std::string switchState(uint32_t status);

// Name of the active alarm, or an empty string when not in alarm.
std::string alarmText(uint32_t status, const RegisterCache& registers, const ControllerInfo& info);

std::string engineState(uint32_t status, bool inAlarm);

// True for engine states in which output values are meaningful.
bool engineIsRunning(const std::string& engine);

// True when the status word itself shows a Service A or B alarm.
bool serviceAlarmActive(uint32_t status);

// True on a service alarm or when a service counter is within one hour.
bool serviceDue(uint32_t status, const RegisterCache& registers, const ControllerInfo& info);

// One-word summary used by the UI and MQTT: ALARM, SERVICEDUE, EXERCISING,
// RUNNING, RUNNING-MANUAL, OFF, MANUAL, or READY.
std::string baseStatus(bool               inAlarm,
                       bool               serviceAlarm,
                       bool               serviceDueSoon,
                       const std::string& engine,
                       const std::string& switchPosition);

// Front-panel LED summary on Evolution 2.0 / Power Pact air cooled units.
std::string ledState(const RegisterCache& registers, const ControllerInfo& info);

}  // namespace genmon
