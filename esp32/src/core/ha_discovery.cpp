// =============================================================================
// ha_discovery.cpp - Home Assistant MQTT discovery messages
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "ha_discovery.h"

#include <ArduinoJson.h>


namespace genmon {

namespace {

// =============================================================================
// Constants
// =============================================================================

constexpr const char* kOnline           = "online";
constexpr const char* kOffline          = "offline";
constexpr const char* kUpdateEntityId   = "genmon_software";
constexpr const char* kExercisePrefix   = "exercise_";
constexpr const char* kUpdatePicture    = "https://raw.githubusercontent.com/jgyates/genmon/master/static/favicon.ico";
constexpr const char* kUpdateReleaseUrl = "https://raw.githubusercontent.com/jgyates/genmon/master/changelog.md";


// =============================================================================
// Helpers
// =============================================================================

std::string configTopic(const HaDevice& device, const char* kind, const std::string& entityId) {
    return device.discoveryPrefix + "/" + kind + "/" + device.deviceId + "/" + entityId + "/config";
}


std::string uniqueId(const HaDevice& device, const std::string& entityId) {
    return "genmon_" + device.deviceId + "_" + entityId;
}


// Fields every entity shares.
JsonObject commonPayload(JsonDocument& document, const HaDevice& device, const std::string& name,
                         const std::string& entityId) {
    JsonObject payload = document.to<JsonObject>();
    payload["name"]                  = name;
    payload["unique_id"]             = uniqueId(device, entityId);
    payload["availability_topic"]    = availabilityTopic(device);
    payload["payload_available"]     = kOnline;
    payload["payload_not_available"] = kOffline;

    JsonObject info = payload["device"].to<JsonObject>();
    info["identifiers"].to<JsonArray>().add("genmon_" + device.deviceId);
    info["name"]         = device.deviceName;
    info["manufacturer"] = "Generac";
    info["model"]        = device.model;
    info["sw_version"]   = device.softwareVersion;
    if (!device.configurationUrl.empty()) {
        info["configuration_url"] = device.configurationUrl;
    }
    return payload;
}


void setIfPresent(JsonObject payload, const char* key, const std::string& value) {
    if (!value.empty()) {
        payload[key] = value;
    }
}


DiscoveryMessage finish(const std::string& topic, const JsonDocument& document) {
    DiscoveryMessage message{topic, ""};
    serializeJson(document, message.payload);
    return message;
}


DiscoveryMessage removal(const HaDevice& device, const char* kind, const std::string& entityId) {
    return DiscoveryMessage{configTopic(device, kind, entityId), ""};
}


bool isExerciseEntity(const std::string& entityId) {
    return entityId.rfind(kExercisePrefix, 0) == 0;
}

}  // namespace


// =============================================================================
// Topics
// =============================================================================

std::string availabilityTopic(const HaDevice& device) {
    return device.baseTopic + "/status";
}


std::string stateTopic(const HaDevice& device, const char* kind, const std::string& entityId) {
    return device.baseTopic + "/" + kind + "/" + entityId + "/state";
}


// =============================================================================
// Discovery payloads
// =============================================================================

DiscoveryMessage sensorDiscovery(const SensorDefinition& sensor, const HaDevice& device) {
    JsonDocument document;
    JsonObject   payload = commonPayload(document, device, sensor.name, sensor.id);
    payload["state_topic"] = stateTopic(device, "sensor", sensor.id);

    setIfPresent(payload, "device_class", sensor.deviceClass);
    if (!sensor.unit.empty()) {
        payload["unit_of_measurement"] = sensor.unit;
    } else if (sensor.deviceClass == "temperature") {
        payload["unit_of_measurement"] = device.useMetric ? "\xC2\xB0" "C" : "\xC2\xB0" "F";
    } else if (sensor.deviceClass == "consumption") {
        payload["unit_of_measurement"] = device.useMetric ? "l" : "gal";
    }
    setIfPresent(payload, "icon",            sensor.icon);
    setIfPresent(payload, "state_class",     sensor.stateClass);
    setIfPresent(payload, "entity_category", sensor.category);
    if (!sensor.enabledByDefault) {
        payload["enabled_by_default"] = false;
    }
    return finish(configTopic(device, "sensor", sensor.id), document);
}


DiscoveryMessage binarySensorDiscovery(const BinarySensorDefinition& sensor, const HaDevice& device) {
    JsonDocument document;
    JsonObject   payload = commonPayload(document, device, sensor.name, sensor.id);
    payload["state_topic"] = stateTopic(device, "binary_sensor", sensor.id);
    payload["payload_on"]  = "ON";
    payload["payload_off"] = "OFF";
    setIfPresent(payload, "device_class",    sensor.deviceClass);
    setIfPresent(payload, "icon",            sensor.icon);
    setIfPresent(payload, "entity_category", sensor.category);
    return finish(configTopic(device, "binary_sensor", sensor.id), document);
}


DiscoveryMessage buttonDiscovery(const ButtonDefinition& button, const HaDevice& device, const HaCapabilities& caps) {
    const bool remoteButton = button.id == "start" || button.id == "stop";
    if ((remoteButton && !caps.remoteCommands) || (button.id == "start_exercise" && !caps.exerciseControls)) {
        return removal(device, "button", button.id);
    }

    JsonDocument document;
    JsonObject   payload = commonPayload(document, device, button.name, button.id);
    payload["command_topic"] = device.baseTopic + "/button/" + button.id + "/command";
    payload["payload_press"] = "PRESS";
    setIfPresent(payload, "icon", button.icon);
    return finish(configTopic(device, "button", button.id), document);
}


DiscoveryMessage switchDiscovery(const SwitchDefinition& entry, const HaDevice& device, const HaCapabilities& caps) {
    if (entry.id == "quiet_mode" && !caps.writeQuietMode) {
        return removal(device, "switch", entry.id);
    }

    JsonDocument document;
    JsonObject   payload = commonPayload(document, device, entry.name, entry.id);
    payload["state_topic"]   = stateTopic(device, "switch", entry.id);
    payload["command_topic"] = device.baseTopic + "/switch/" + entry.id + "/set";
    payload["payload_on"]    = "ON";
    payload["payload_off"]   = "OFF";
    setIfPresent(payload, "icon", entry.icon);
    return finish(configTopic(device, "switch", entry.id), document);
}


DiscoveryMessage selectDiscovery(const SelectDefinition& select, const HaDevice& device, const HaCapabilities& caps) {
    if ((isExerciseEntity(select.id) && !caps.exerciseControls) ||
        (select.id == "exercise_frequency" && !caps.enhancedExercise)) {
        return removal(device, "select", select.id);
    }

    JsonDocument document;
    JsonObject   payload = commonPayload(document, device, select.name, select.id);
    payload["state_topic"]   = stateTopic(device, "select", select.id);
    payload["command_topic"] = device.baseTopic + "/select/" + select.id + "/set";
    JsonArray options = payload["options"].to<JsonArray>();
    for (const std::string& option : select.options) {
        options.add(option);
    }
    setIfPresent(payload, "icon", select.icon);
    return finish(configTopic(device, "select", select.id), document);
}


DiscoveryMessage numberDiscovery(const NumberDefinition& number, const HaDevice& device, const HaCapabilities& caps) {
    if ((isExerciseEntity(number.id) && !caps.exerciseControls) ||
        (number.id == "exercise_day_of_month" && !caps.enhancedExercise)) {
        return removal(device, "number", number.id);
    }

    JsonDocument document;
    JsonObject   payload = commonPayload(document, device, number.name, number.id);
    payload["state_topic"]   = stateTopic(device, "number", number.id);
    payload["command_topic"] = device.baseTopic + "/number/" + number.id + "/set";
    payload["min"]           = number.min;
    payload["max"]           = number.max;
    payload["step"]          = number.step;
    payload["mode"]          = "box";
    setIfPresent(payload, "icon",                number.icon);
    setIfPresent(payload, "unit_of_measurement", number.unit);
    return finish(configTopic(device, "number", number.id), document);
}


DiscoveryMessage updateDiscovery(const HaDevice& device) {
    JsonDocument document;
    JsonObject   payload = commonPayload(document, device, "Software Update", kUpdateEntityId);
    payload["state_topic"]     = stateTopic(device, "update", kUpdateEntityId);
    payload["command_topic"]   = device.baseTopic + "/update/" + kUpdateEntityId + "/command";
    payload["payload_install"] = "INSTALL";
    payload["device_class"]    = "firmware";
    payload["entity_category"] = "config";
    payload["entity_picture"]  = kUpdatePicture;
    payload["release_url"]     = kUpdateReleaseUrl;
    return finish(configTopic(device, "update", kUpdateEntityId), document);
}


std::string updateState(const HaDevice& device) {
    JsonDocument document;
    document["installed_version"] = device.softwareVersion;
    document["latest_version"]    = device.softwareVersion;
    document["title"]             = "Genmon";
    document["in_progress"]       = false;
    std::string payload;
    serializeJson(document, payload);
    return payload;
}

}  // namespace genmon
