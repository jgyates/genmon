// =============================================================================
// register_map.h - Evolution / Nexus register addresses and polling lists
// =============================================================================
//
// Register meanings come from the original genmon reverse engineering
// (genmonlib/generac_evolution.py). Addresses that matter to the
// decoders get named constants; the polling lists also include registers whose
// meaning is unknown so the raw register view stays useful for diagnosis.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <cstdint>
#include <vector>


namespace genmon {

// =============================================================================
// Types
// =============================================================================

struct RegisterSpan {
    uint16_t start;
    uint8_t  words;
};


// =============================================================================
// Register addresses
// =============================================================================

namespace reg {

constexpr uint16_t kProductCode         = 0x0000;   // controller family code
constexpr uint16_t kStatus              = 0x0001;   // 32-bit: hi word engine state, lo word alarm/switch
constexpr uint16_t kExerciseTime        = 0x0005;   // hi = hour, lo = minute
constexpr uint16_t kExerciseDay         = 0x0006;   // hi = day of week (Sun = 0), lo = quiet mode
constexpr uint16_t kRpm                 = 0x0007;
constexpr uint16_t kFrequency           = 0x0008;
constexpr uint16_t kUtilityVolts        = 0x0009;
constexpr uint16_t kBatteryVolts        = 0x000A;   // tenths of a volt
constexpr uint16_t kRunHours            = 0x000B;   // 32-bit hours (air cooled, Nexus)
constexpr uint16_t kTimeHourMinute      = 0x000E;
constexpr uint16_t kTimeMonthDay        = 0x000F;
constexpr uint16_t kTimeWeekdayYear     = 0x0010;
constexpr uint16_t kThresholdVolts      = 0x0011;
constexpr uint16_t kOutputVolts         = 0x0012;
constexpr uint16_t kModelId             = 0x0019;
constexpr uint16_t kServiceAHours       = 0x001A;
constexpr uint16_t kServiceADate        = 0x001B;
constexpr uint16_t kService1CHours      = 0x001C;
constexpr uint16_t kService1DDate       = 0x001D;
constexpr uint16_t kServiceBHours       = 0x001E;
constexpr uint16_t kServiceBDate        = 0x001F;
constexpr uint16_t kService20Date       = 0x0020;
constexpr uint16_t kService21Hours      = 0x0021;
constexpr uint16_t kService22Date       = 0x0022;
constexpr uint16_t kVersions            = 0x002A;   // hi = hardware, lo = firmware (x100)
constexpr uint16_t kStartupDelayAir     = 0x002B;
constexpr uint16_t kExerciseTimeWrite   = 0x002C;
constexpr uint16_t kExerciseFrequency   = 0x002D;   // 0 weekly, 1 biweekly, 2 monthly
constexpr uint16_t kExerciseDayWrite    = 0x002E;   // also day of month for monthly
constexpr uint16_t kQuietMode           = 0x002F;
constexpr uint16_t kDigitalInputs       = 0x0052;   // Evolution liquid cooled
constexpr uint16_t kDigitalOutputs      = 0x0053;   // Evolution liquid cooled
constexpr uint16_t kHoursSinceActivated = 0x0054;
constexpr uint16_t kHallCurrent         = 0x0058;   // Evolution liquid cooled
constexpr uint16_t kFuelLevelSensor     = 0x005D;
constexpr uint16_t kRunMinutes          = 0x005E;   // 32-bit minutes (liquid cooled)
constexpr uint16_t kLedState            = 0x0062;   // Evolution 2.0 / Power Pact
constexpr uint16_t kSerialNumber        = 0x01F4;   // 5 words of ASCII
constexpr uint16_t kSetOutputVolts      = 0x0237;
constexpr uint16_t kWarmupDelay         = 0x0238;
constexpr uint16_t kStartupDelayLiquid  = 0x0239;
constexpr uint16_t kPickupVolts         = 0x023B;
constexpr uint16_t kExerciseDuration    = 0x023E;
constexpr uint16_t kAmbientTemperature  = 0x05ED;   // Evolution 2.0, deg F
constexpr uint16_t kChargerCurrent      = 0x05EE;   // mA
constexpr uint16_t kLastAlarmCode       = 0x05F1;
constexpr uint16_t kCurrentLeg1         = 0x05F4;   // Evolution air cooled
constexpr uint16_t kCurrentLeg2         = 0x05F5;

// Writing a command index to kCommandIndex (optionally after a value to
// kCommandValue) triggers the controller's "indexed" remote actions.
constexpr uint16_t kCommandIndex        = 0x0003;
constexpr uint16_t kCommandValue        = 0x0004;

}  // namespace reg


// =============================================================================
// Log layout
// =============================================================================

constexpr uint8_t  kLogDepth                = 50;
constexpr uint16_t kRunLogStart             = 0x012C;
constexpr uint8_t  kRunLogStride            = 4;
constexpr uint16_t kEvolutionAlarmLogStart  = 0x03E8;
constexpr uint8_t  kEvolutionAlarmLogStride = 5;
constexpr uint16_t kServiceLogStart         = 0x04E2;
constexpr uint8_t  kServiceLogStride        = 4;
constexpr uint16_t kNexusAlarmLogStart      = 0x0064;
constexpr uint8_t  kNexusAlarmLogStride     = 4;
constexpr uint8_t  kSerialNumberWords       = 5;


// =============================================================================
// Polling lists
// =============================================================================

// Read every few base registers so state changes show up within seconds.
const std::vector<RegisterSpan>& primeRegisters();

// Read round-robin; together they describe everything else the UI shows.
const std::vector<RegisterSpan>& baseRegisters();

}  // namespace genmon
