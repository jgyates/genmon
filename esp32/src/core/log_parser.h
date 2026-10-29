// =============================================================================
// log_parser.h - Decoding of the controller's alarm, service and run logs
// =============================================================================
//
// Each log entry is 4 registers (5 for the Evolution alarm log) laid out as:
//   byte 0  event code        byte 4  month
//   byte 1  entry sequence    byte 5  seconds
//   byte 2  minute            byte 6  year (two digits)
//   byte 3  hour              byte 7  day of month
//   bytes 8-9  alarm code (Evolution alarm log only)
// An entry with month 0 is an unused slot.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <cstdint>
#include <string>

#include "controller_info.h"
#include "register_cache.h"


namespace genmon {

// =============================================================================
// Types
// =============================================================================

enum class LogKind {
    EvolutionAlarm,
    EvolutionService,
    Run,
    NexusAlarm,
};


// =============================================================================
// Functions
// =============================================================================

// Returns "MM/DD/YY HH:MM:SS Description" (plus the alarm code where the
// entry carries one), or an empty string for an unused or corrupt slot.
// `firmwareVersion` is the raw low byte of register 0x002A (e.g. 114 = V1.14).
std::string parseLogEntry(const RegisterBytes&  entry,
                          LogKind               kind,
                          const ControllerInfo& info,
                          uint8_t               firmwareVersion);

}  // namespace genmon
