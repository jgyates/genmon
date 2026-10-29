// =============================================================================
// mqtt_flatten.h - genmqtt-style flattening of genmon reports into topics
// =============================================================================
//
// Upstream's genmqtt add-on publishes every report value on its own topic,
//   [root_topic/]generator/Status/Engine/Battery Voltage = "13.70 V"
// and listens for commands on [root_topic/]generator/command. This module
// reproduces that topic layout so existing MQTT consumers keep working.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <ArduinoJson.h>

#include <string>
#include <vector>


namespace genmon {

// =============================================================================
// Types
// =============================================================================

struct TopicValue {
    std::string topic;   // relative to the root, e.g. "generator/Status/Engine/RPM"
    std::string value;
};

struct FlattenOptions {
    bool numericObjects = false;   // genmqtt numeric_json_object: publish {unit,type,value} as JSON
    bool stringListJson = false;   // genmqtt strlist_json: publish string lists as JSON arrays
};


// =============================================================================
// Functions
// =============================================================================

// Flattens `node` (a merged {Status, Maintenance, Outage, Monitor} object)
// under `prefix`, following genmqtt's CheckDictForChanges rules.
std::vector<TopicValue> flattenReports(JsonVariantConst node, const std::string& prefix, const FlattenOptions& options);

}  // namespace genmon
