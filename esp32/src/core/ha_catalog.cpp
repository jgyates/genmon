// =============================================================================
// ha_catalog.cpp - Home Assistant entity definitions from upstream genmon
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "ha_catalog.h"

#include <ArduinoJson.h>

#include <algorithm>
#include <cctype>

#include "ha_definitions.inc"


namespace genmon {

namespace {

// =============================================================================
// Helpers
// =============================================================================

std::string lowercase(std::string text) {
    std::transform(text.begin(), text.end(), text.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return text;
}


std::string text(JsonObjectConst object, const char* key, const char* fallback = "") {
    JsonVariantConst value = object[key];
    if (value.is<const char*>()) {
        return value.as<const char*>();
    }
    return fallback;
}


// Reads a field that may be a single string or a list of strings.
std::vector<std::string> stringOrList(JsonVariantConst value, bool& isList) {
    std::vector<std::string> items;
    isList = value.is<JsonArrayConst>();
    if (isList) {
        for (JsonVariantConst item : value.as<JsonArrayConst>()) {
            items.push_back(item.as<std::string>());
        }
    } else if (!value.isNull()) {
        items.push_back(value.as<std::string>());
    }
    return items;
}


EntityFilter readFilter(JsonObjectConst object) {
    EntityFilter filter;
    bool         ignored = false;
    filter.controllers  = stringOrList(object["controllers"], ignored);
    filter.monitorStats = object["monitor_stats"] | false;
    filter.weather      = object["weather"] | false;
    return filter;
}


SensorDefinition readSensor(JsonObjectConst object) {
    SensorDefinition sensor;
    sensor.id               = text(object, "entity_id");
    sensor.name             = text(object, "name", sensor.id.c_str());
    sensor.path             = text(object, "path");
    sensor.deviceClass      = text(object, "device_class");
    sensor.unit             = text(object, "unit");
    sensor.icon             = text(object, "icon");
    sensor.stateClass       = text(object, "state_class");
    sensor.category         = text(object, "category");
    sensor.enabledByDefault = object["enabled_default"] | true;
    sensor.filter           = readFilter(object);
    return sensor;
}


BinarySensorDefinition readBinarySensor(JsonObjectConst object) {
    BinarySensorDefinition sensor;
    sensor.id               = text(object, "entity_id");
    sensor.name             = text(object, "name", sensor.id.c_str());
    sensor.path             = text(object, "path");
    sensor.deviceClass      = text(object, "device_class");
    sensor.icon             = text(object, "icon");
    sensor.category         = text(object, "category");
    sensor.payloadOn        = stringOrList(object["payload_on"],  sensor.payloadOnIsList);
    sensor.payloadOff       = stringOrList(object["payload_off"], sensor.payloadOffIsList);
    sensor.payloadOffInvert = object["payload_off_invert"] | false;
    sensor.onWhenNotEmpty   = object["payload_on_not_empty"] | false;
    if (!object["payload_on_gt"].isNull()) {
        sensor.onWhenGreaterThan = object["payload_on_gt"].as<double>();
    }
    sensor.filter = readFilter(object);
    return sensor;
}


ButtonDefinition readButton(JsonObjectConst object) {
    ButtonDefinition button;
    button.id      = text(object, "entity_id");
    button.name    = text(object, "name", button.id.c_str());
    button.command = text(object, "command");
    button.icon    = text(object, "icon");
    button.filter  = readFilter(object);
    return button;
}


SwitchDefinition readSwitch(JsonObjectConst object) {
    SwitchDefinition entry;
    entry.id         = text(object, "entity_id");
    entry.name       = text(object, "name", entry.id.c_str());
    entry.commandOn  = text(object, "command_on");
    entry.commandOff = text(object, "command_off");
    entry.icon       = text(object, "icon");
    entry.statePath  = text(object, "state_path");
    entry.payloadOn  = text(object, "payload_on", "on");
    entry.filter     = readFilter(object);
    return entry;
}


SelectDefinition readSelect(JsonObjectConst object) {
    SelectDefinition select;
    bool             ignored = false;
    select.id              = text(object, "entity_id");
    select.name            = text(object, "name", select.id.c_str());
    select.icon            = text(object, "icon");
    select.commandTemplate = text(object, "command_template");
    select.options         = stringOrList(object["options"], ignored);
    select.filter          = readFilter(object);
    return select;
}


NumberDefinition readNumber(JsonObjectConst object) {
    NumberDefinition number;
    number.id              = text(object, "entity_id");
    number.name            = text(object, "name", number.id.c_str());
    number.icon            = text(object, "icon");
    number.unit            = text(object, "unit");
    number.commandTemplate = text(object, "command_template");
    number.min             = object["min"]  | 0.0;
    number.max             = object["max"]  | 100.0;
    number.step            = object["step"] | 1.0;
    number.filter          = readFilter(object);
    return number;
}


// Replace an entry with the same id in place, otherwise append; this keeps
// the base file's ordering as Python dict assignment does.
template <typename Definition>
void mergeInto(std::vector<Definition>& target, const Definition& entry) {
    if (entry.id.empty()) {
        return;
    }
    for (Definition& existing : target) {
        if (existing.id == entry.id) {
            existing = entry;
            return;
        }
    }
    target.push_back(entry);
}


template <typename Definition, typename Reader>
void mergeList(std::vector<Definition>& target, JsonArrayConst list, Reader read) {
    for (JsonVariantConst item : list) {
        if (item.is<JsonObjectConst>()) {
            mergeInto(target, read(item.as<JsonObjectConst>()));
        }
    }
}

}  // namespace


// =============================================================================
// Core logic
// =============================================================================

EntityCatalog loadCatalog(const std::vector<const char*>& documents, std::vector<std::string>& errors) {
    EntityCatalog catalog;
    for (const char* source : documents) {
        JsonDocument               document;
        const DeserializationError result = deserializeJson(document, source);
        if (result) {
            errors.push_back(std::string("entity definitions: ") + result.c_str());
            continue;
        }
        JsonObjectConst root = document.as<JsonObjectConst>();
        mergeList(catalog.sensors,       root["sensors"],        readSensor);
        mergeList(catalog.binarySensors, root["binary_sensors"], readBinarySensor);
        mergeList(catalog.buttons,       root["buttons"],        readButton);
        mergeList(catalog.switches,      root["switches"],       readSwitch);
        mergeList(catalog.selects,       root["selects"],        readSelect);
        mergeList(catalog.numbers,       root["numbers"],        readNumber);
    }
    return catalog;
}


EntityCatalog loadBuiltInCatalog(std::vector<std::string>& errors) {
    return loadCatalog({kHaBaseDefinitions, kHaControllerDefinitions, kHaUserDefinitions}, errors);
}


bool entityAllowed(const std::string&  id,
                   const std::string&  name,
                   const std::string&  path,
                   const EntityFilter& filter,
                   const EntityPolicy& policy) {
    const std::string lowerId   = lowercase(id);
    const std::string lowerName = lowercase(name.empty() ? id : name);
    const std::string lowerPath = lowercase(path);

    for (const std::string& blocked : policy.blacklist) {
        if (blocked.empty()) {
            continue;
        }
        if (lowerName.find(blocked) != std::string::npos ||
            lowerId.find(blocked)   != std::string::npos ||
            lowerPath.find(blocked) != std::string::npos) {
            return false;
        }
    }

    if (!filter.controllers.empty() &&
        std::find(filter.controllers.begin(), filter.controllers.end(), policy.controllerType) == filter.controllers.end()) {
        return false;
    }
    if (filter.monitorStats && !policy.includeMonitorStats) {
        return false;
    }
    if (filter.weather && !policy.includeWeather) {
        return false;
    }
    return true;
}

}  // namespace genmon
