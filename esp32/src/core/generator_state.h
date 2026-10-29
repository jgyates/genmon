// =============================================================================
// generator_state.h - Decoded, presentation-ready snapshot of the generator
// =============================================================================
//
// Built once per polling cycle from the register cache and handed by value to
// the web server and MQTT bridge, so they never touch raw registers or the
// serial link. Optional numbers are absent when the controller does not
// support them or they have not been read yet; they serialize as JSON null.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <cstdint>
#include <optional>
#include <string>
#include <vector>


namespace genmon {

// =============================================================================
// Types
// =============================================================================

struct LabeledValue {
    std::string label;
    std::string value;
};

// A number shown with a unit; `integer` selects "%d" vs "%.2f" formatting
// and the "int" / "float" type tag in genmon's numeric JSON. `textOnly`
// entries are always reported as "<value> <unit>" strings, matching the
// handful of settings genmon reports that way even in numeric JSON.
struct Measurement {
    std::string label;
    double      value    = 0.0;
    bool        integer  = true;
    std::string unit;
    bool        textOnly = false;
};

struct GeneratorState {
    bool        valid = false;   // false until the status register has been read
    uint32_t    statusWord = 0;

    // Identity
    std::string controller;
    std::string productName;
    std::string serialNumber;
    std::string firmwareVersion;
    std::string hardwareVersion;

    // Engine
    std::string switchState;
    std::string engineState;
    std::string baseStatus;
    std::string alarm;           // empty when not in alarm
    std::string lastAlarmCode;   // Evolution only, e.g. "1600: Underspeed"
    std::string ledState;
    std::string activeRelays;    // Evolution liquid cooled only
    std::string activeSensors;   // Evolution liquid cooled only
    bool        inAlarm    = false;
    bool        serviceDue = false;
    bool        running    = false;

    std::optional<double> batteryVolts;
    std::optional<double> chargerCurrentMa;
    std::optional<double> rpm;
    std::optional<double> frequencyHz;
    std::optional<double> outputVolts;
    std::optional<double> outputAmps;
    std::optional<double> outputAmpsLeg1;
    std::optional<double> outputAmpsLeg2;
    std::optional<double> outputKw;
    std::optional<double> rotorPoles;   // calculated from RPM and frequency

    // Line
    std::string           transferSwitch;   // Evolution liquid cooled only
    std::optional<double> utilityVolts;
    std::optional<double> thresholdVolts;
    std::optional<double> pickupVolts;
    std::optional<double> setOutputVolts;

    // Maintenance
    std::optional<double>     runHours;
    std::optional<double>     hoursSinceActivation;
    std::optional<double>     ambientTemperatureF;
    std::string               exercise;
    std::string               exerciseDuration;
    std::string               startupDelay;
    std::string               warmupDelay;
    std::string               generatorTime;
    std::vector<LabeledValue> service;
    std::vector<Measurement>  controllerSettings;

    // Capabilities, used by the UI to show only valid commands
    bool canRemoteStart     = false;
    bool canSetButtons      = false;
    bool canResetAlarm      = false;
    bool canSetQuietMode    = false;
    bool enhancedExercise   = false;
    bool powerMeter         = false;
    bool showsPickupVolts   = false;   // pickup voltage is a real controller setting
    bool reportsQuietToUi   = false;   // genmon's "WriteQuietMode" start-info flag
};

struct GeneratorLogs {
    std::vector<std::string> alarm;
    std::vector<std::string> service;
    std::vector<std::string> run;
};

}  // namespace genmon
