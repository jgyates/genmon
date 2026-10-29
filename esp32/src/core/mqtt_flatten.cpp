// =============================================================================
// mqtt_flatten.cpp - genmqtt-style flattening of genmon reports into topics
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "mqtt_flatten.h"

#include "ha_values.h"


namespace genmon {

namespace {

// =============================================================================
// Helpers
// =============================================================================

bool isStringList(JsonArrayConst list) {
    for (JsonVariantConst item : list) {
        if (!item.is<const char*>()) {
            return false;
        }
    }
    return true;
}


bool isTopicObject(JsonVariantConst node) {
    return node.is<JsonObjectConst>() && !node["type"].isNull() && !node["value"].isNull() && !node["unit"].isNull();
}


std::string scalarText(JsonVariantConst value) {
    if (value.is<const char*>()) {
        return value.as<const char*>();
    }
    if (value.is<bool>()) {
        return value.as<bool>() ? "True" : "False";
    }
    if (value.is<long long>()) {
        return std::to_string(value.as<long long>());
    }
    if (value.is<double>()) {
        return pythonNumber(value.as<double>(), true);
    }
    return "";
}


std::string jsonText(JsonVariantConst value) {
    std::string text;
    serializeJson(value, text);
    return text;
}


void flattenObject(JsonObjectConst object, const std::string& prefix, const FlattenOptions& options,
                   std::vector<TopicValue>& out) {
    for (JsonPairConst pair : object) {
        const std::string path  = prefix + "/" + pair.key().c_str();
        JsonVariantConst  value = pair.value();

        if (value.is<JsonObjectConst>()) {
            if (options.numericObjects && isTopicObject(value)) {
                out.push_back({path, jsonText(value)});
            } else {
                flattenObject(value.as<JsonObjectConst>(), path, options, out);
            }
            continue;
        }

        if (value.is<JsonArrayConst>()) {
            JsonArrayConst list = value.as<JsonArrayConst>();
            if (isStringList(list)) {
                if (options.stringListJson) {
                    out.push_back({path, jsonText(value)});
                } else {
                    std::string joined;
                    for (JsonVariantConst item : list) {
                        joined += joined.empty() ? "" : ", ";
                        joined += item.as<const char*>();
                    }
                    out.push_back({path, joined});
                }
                continue;
            }
            for (JsonVariantConst item : list) {
                if (item.is<JsonObjectConst>()) {
                    flattenObject(item.as<JsonObjectConst>(), path, options, out);
                }
            }
            continue;
        }

        out.push_back({path, scalarText(value)});
    }
}

}  // namespace


// =============================================================================
// Core logic
// =============================================================================

std::vector<TopicValue> flattenReports(JsonVariantConst node, const std::string& prefix, const FlattenOptions& options) {
    std::vector<TopicValue> topics;
    if (node.is<JsonObjectConst>()) {
        flattenObject(node.as<JsonObjectConst>(), prefix, options, topics);
    }
    return topics;
}

}  // namespace genmon
