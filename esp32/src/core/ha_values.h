// =============================================================================
// ha_values.h - Home Assistant state extraction from genmon reports
// =============================================================================
//
// Ports the data-handling half of upstream's genhomeassistant add-on: path
// lookups into genmon's list-of-objects JSON, the sensor and binary sensor
// value rules, dynamic sensor discovery and the exercise-time controls.
// Following the same rules is what gives every entity the same entity_id
// and state it had when genmon ran on a Raspberry Pi.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <ArduinoJson.h>

#include <optional>
#include <string>
#include <vector>

#include "ha_catalog.h"


namespace genmon {

// =============================================================================
// Types
// =============================================================================

// Values behind the exercise select / number entities; genmon only accepts
// a whole schedule, so each change resends all of them.
struct ExerciseSettings {
    std::string frequency  = "Weekly";
    std::string dayOfWeek  = "Sunday";
    int         dayOfMonth = 1;
    int         hour       = 12;
    int         minute     = 0;
};


// =============================================================================
// Functions
// =============================================================================

// "Status/Engine/Battery Voltage" -> the matching node, or a null variant.
// Matching is case-insensitive; a numeric part may also index a list.
JsonVariantConst valueAtPath(JsonVariantConst data, const std::string& path);

// The state string to publish for a sensor, or nothing when the value is
// empty or unknown (in which case nothing is published).
std::optional<std::string> sensorState(JsonVariantConst value, const SensorDefinition& sensor);

// "ON" or "OFF".
std::string binarySensorState(JsonVariantConst value, const BinarySensorDefinition& sensor);

// "Status/Engine/Battery Voltage" -> "status_engine_battery_voltage".
std::string pathToEntityId(const std::string& path);

// Every leaf in `data` not covered by a predefined sensor or binary sensor,
// as a diagnostic sensor definition (genhomeassistant's dynamic sensors).
std::vector<SensorDefinition> discoverDynamicSensors(JsonVariantConst data, const EntityCatalog& catalog);

// Updates `settings` from genmon's "Exercise Time" text.
void parseExerciseTime(const std::string& text, ExerciseSettings& settings);

// The setexercise command for the current settings; frequencies other than
// weekly are forced to weekly when `enhanced` is false.
std::string exerciseCommand(ExerciseSettings& settings, bool enhanced);

// Formats a number the way Python's str() does for int and float values.
std::string pythonNumber(double value, bool isFloat);

}  // namespace genmon
