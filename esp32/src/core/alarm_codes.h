// =============================================================================
// alarm_codes.h - Evolution alarm code descriptions
// =============================================================================
//
// Evolution controllers report a four-digit alarm code (register 0x05F1 and in
// each alarm log entry). This table, generated from ALARMS.txt, turns those
// codes into the names and troubleshooting hints shown in the UI.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <cstdint>


namespace genmon {

// =============================================================================
// Types
// =============================================================================

struct AlarmCode {
    uint16_t    code;
    const char* kind;        // "ALARM" or "WARNING"
    const char* name;
    const char* condition;
    const char* info;
};


// =============================================================================
// Functions
// =============================================================================

// Returns nullptr when the code is not in the table.
const AlarmCode* findAlarmCode(uint16_t code);

}  // namespace genmon
