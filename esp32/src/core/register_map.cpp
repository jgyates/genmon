// =============================================================================
// register_map.cpp - Evolution / Nexus polling lists
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "register_map.h"


namespace genmon {

// =============================================================================
// Polling lists
// =============================================================================

const std::vector<RegisterSpan>& primeRegisters() {
    static const std::vector<RegisterSpan> kPrime = {
        {reg::kStatus,         2},
        {0x000D,               1},   // controller update flags
        {0x0018,               1},   // failed-to-exercise flag
        {reg::kDigitalOutputs, 1},
        {reg::kDigitalInputs,  1},
        {reg::kUtilityVolts,   1},
        {reg::kLastAlarmCode,  1},
    };
    return kPrime;
}


const std::vector<RegisterSpan>& baseRegisters() {
    static const std::vector<RegisterSpan> kBase = {
        {reg::kProductCode,         1},
        {reg::kExerciseTime,        1},
        {reg::kExerciseDay,         1},
        {reg::kRpm,                 1},
        {reg::kFrequency,           1},
        {reg::kBatteryVolts,        1},
        {reg::kRunHours,            2},
        {reg::kTimeHourMinute,      1},
        {reg::kTimeMonthDay,        1},
        {reg::kTimeWeekdayYear,     1},
        {reg::kThresholdVolts,      1},
        {reg::kOutputVolts,         1},
        {reg::kModelId,             1},
        {reg::kServiceAHours,       1},
        {reg::kServiceADate,        1},
        {reg::kService1CHours,      1},
        {reg::kService1DDate,       1},
        {reg::kServiceBHours,       1},
        {reg::kServiceBDate,        1},
        {reg::kService20Date,       1},
        {reg::kService21Hours,      1},
        {reg::kService22Date,       1},
        {reg::kVersions,            1},
        {reg::kStartupDelayAir,     1},
        {reg::kExerciseTimeWrite,   1},
        {reg::kExerciseFrequency,   1},
        {reg::kExerciseDayWrite,    1},
        {reg::kQuietMode,           1},
        {0x0051,                    1},   // boot code version
        {reg::kHoursSinceActivated, 1},
        {0x0055,                    1},
        {0x0056,                    1},
        {0x0057,                    1},
        {reg::kHallCurrent,         1},
        {0x0059,                    1},   // rated volts (liquid cooled)
        {0x005A,                    1},   // rated Hz (liquid cooled)
        {0x005C,                    1},
        {reg::kFuelLevelSensor,     1},
        {reg::kRunMinutes,          2},
        {reg::kLedState,            1},
        {0x003C,                    1},   // raw RPM sensor
        {0x0032,                    1},
        {0x0033,                    1},
        {0x0034,                    1},
        {0x0035,                    1},
        {0x0036,                    1},
        {0x0037,                    1},
        {0x0038,                    1},
        {0x0039,                    1},
        {0x003A,                    2},
        {0x004C,                    1},
        {0x0208,                    1},   // calibrate volts
        {0x0209,                    1},
        {0x020A,                    1},   // param group (liquid cooled)
        {0x020B,                    1},   // voltage code (liquid cooled)
        {0x020C,                    1},   // fuel type (liquid cooled)
        {0x020D,                    1},
        {0x020E,                    1},   // volts per hertz
        {0x020F,                    1},
        {0x0212,                    1},
        {0x0213,                    1},   // Wi-Fi RSSI (Evolution 2.0)
        {0x0235,                    1},   // gain
        {0x0236,                    1},   // two wire start
        {reg::kSetOutputVolts,      1},
        {reg::kWarmupDelay,         1},
        {reg::kStartupDelayLiquid,  1},
        {0x023A,                    1},
        {reg::kPickupVolts,         1},
        {0x023D,                    1},
        {reg::kExerciseDuration,    1},
        {0x023F,                    1},   // preheat time (diesel)
        {0x0241,                    1},
        {0x0242,                    1},
        {0x0243,                    1},
        {0x0244,                    1},
        {0x0245,                    1},
        {0x0246,                    1},
        {0x0247,                    1},
        {0x0248,                    1},
        {0x0249,                    1},
        {0x024A,                    1},
        {0x0258,                    1},
        {0x025A,                    1},
        {reg::kAmbientTemperature,  1},
        {reg::kChargerCurrent,      1},
        {0x05F2,                    1},
        {0x05F3,                    1},
        {reg::kCurrentLeg1,         1},
        {reg::kCurrentLeg2,         1},
        {0x05F6,                    1},   // current calibration 1
        {0x05F7,                    1},   // current calibration 2
        {0x05FA,                    1},
    };
    return kBase;
}

}  // namespace genmon
