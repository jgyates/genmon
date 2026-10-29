// =============================================================================
// monitor_options.h - User settings that influence how registers are decoded
// =============================================================================
//
// The controller does not report everything needed to present its data
// (rated kW, fuel type, current calibration), so these come from settings.
// Kept separate from the ESP32 settings store so the decoders stay portable.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <string>


namespace genmon {

// =============================================================================
// Types
// =============================================================================

struct MonitorOptions {
    float       ratedKw              = 0.0f;    // 0 disables current / power reporting
    int         nominalLineVolts     = 240;
    float       currentDivider       = 0.0f;    // 0 selects the per-controller default
    float       currentOffset        = 0.0f;
    float       additionalRunHours   = 0.0f;    // for replaced controllers
    std::string fuelType             = "Natural Gas";
    std::string serialNumberOverride;           // for replaced controllers (10 digits)
    bool        ignoreUnknownStatus  = true;    // drop Evolution 2.0 garbage status words
    bool        nexusDoubleFrequency = true;    // Nexus liquid cooled reports half the Hz
};

}  // namespace genmon
