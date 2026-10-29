// =============================================================================
// controller_info.h - Controller family detection from the product code
// =============================================================================
//
// Register 0x0000 identifies the controller family. Many decoding rules differ
// between Evolution and Nexus, and between air and liquid cooled units, so the
// rest of the firmware branches on the flags computed here.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <cstdint>
#include <string>


namespace genmon {

// =============================================================================
// Types
// =============================================================================

// User override for an auto-detected property.
enum class Detect : uint8_t {
    Auto = 0,
    Yes  = 1,
    No   = 2,
};

struct ControllerInfo {
    bool     detected      = false;
    uint16_t productCode   = 0;
    bool     knownCode     = false;   // false: best-guess flags for an unvalidated code
    bool     evolution     = false;   // false means Nexus family
    bool     liquidCooled  = false;
    bool     evolution2    = false;
    bool     synergy       = false;
    bool     powerPact     = false;
    bool     preNexus      = false;
    bool     evolution45L  = false;
    bool     powerZone200  = false;   // detected but not supported (needs 115200 baud)

    bool     enhancedExercise    = false;   // biweekly / monthly exercise registers
    bool     legacyExerciseWrite = false;   // exercise set via indexed command
};


// =============================================================================
// Functions
// =============================================================================

ControllerInfo detectController(uint16_t productCode,
                                Detect   evolutionOverride,
                                Detect   liquidCooledOverride,
                                bool     enhancedExerciseSetting,
                                bool     legacyExerciseWriteSetting);

// Family description, e.g. "Evolution 2.0, Air Cooled".
std::string controllerFamilyName(const ControllerInfo& info);

// Name of the exact product code, e.g. "Nexus, Liquid Cooled (7)".
std::string productCodeName(uint16_t productCode);

}  // namespace genmon
