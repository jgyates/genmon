// =============================================================================
// ha_publisher.cpp - Home Assistant MQTT discovery publisher
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "ha_publisher.h"

#include <Arduino.h>

#include <algorithm>
#include <cctype>
#include <cstdlib>

#include "reports.h"


namespace genmon {

namespace {

// =============================================================================
// Constants
// =============================================================================

// Upstream waits this long after connecting so retained discovery configs
// arrive before it decides which entities are stale.
constexpr uint32_t    kCollectExistingMs  = 2000;
constexpr const char* kExerciseTimePath   = "Maintenance/Exercise/Exercise Time";
constexpr const char* kUpdateEntity       = "update/genmon_software";


// =============================================================================
// Helpers
// =============================================================================

std::vector<std::string> splitTopic(const std::string& topic) {
    std::vector<std::string> parts;
    size_t start = 0;
    while (true) {
        const size_t slash = topic.find('/', start);
        parts.push_back(topic.substr(start, slash - start));
        if (slash == std::string::npos) {
            return parts;
        }
        start = slash + 1;
    }
}


std::vector<std::string> parseBlacklist(const std::string& text) {
    std::vector<std::string> items;
    std::string              item;
    auto flush = [&]() {
        const size_t first = item.find_first_not_of(' ');
        if (first != std::string::npos) {
            items.push_back(item.substr(first, item.find_last_not_of(' ') - first + 1));
        }
        item.clear();
    };
    for (char c : text) {
        if (c == ',') {
            flush();
        } else {
            item.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
        }
    }
    flush();
    return items;
}


bool endsWith(const std::string& text, const std::string& suffix) {
    return text.size() >= suffix.size() && text.compare(text.size() - suffix.size(), suffix.size(), suffix) == 0;
}


std::string lowercase(std::string text) {
    std::transform(text.begin(), text.end(), text.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return text;
}

}  // namespace


// =============================================================================
// Lifecycle
// =============================================================================

void HaPublisher::begin(const Settings& settings, GeneratorService& service, PubSubClient& client) {
    settings_ = settings;
    service_  = &service;
    client_   = &client;

    std::vector<std::string> errors;
    catalog_ = loadBuiltInCatalog(errors);
    for (const std::string& error : errors) {
        Serial.printf("[genmon] Home Assistant definitions: %s\n", error.c_str());
    }

    policy_.blacklist           = parseBlacklist(settings.haBlacklist);
    policy_.includeMonitorStats = settings.haIncludeMonitorStats;
    policy_.includeWeather      = true;

    device_.deviceId        = settings.haDeviceId;
    device_.deviceName      = settings.haDeviceName;
    device_.discoveryPrefix = settings.haDiscoveryPrefix;
    device_.baseTopic       = settings.haBaseTopic;
    device_.softwareVersion = kFirmwareVersion;
}


std::string HaPublisher::availabilityTopic() const {
    return genmon::availabilityTopic(device_);
}


void HaPublisher::onConnected(const std::string& configurationUrl) {
    device_.configurationUrl = configurationUrl;

    connected_     = true;
    discovered_    = false;
    cleanupDone_   = false;
    connectedAtMs_ = millis();
    lastValues_.clear();
    existingEntities_.clear();
    publishedEntities_.clear();

    const std::string prefix = device_.discoveryPrefix;
    const std::string base   = device_.baseTopic;
    client_->subscribe((prefix + "/+/" + device_.deviceId + "/+/config").c_str());
    client_->subscribe((prefix + "/status").c_str());
    client_->subscribe((base + "/+/+/set").c_str());
    client_->subscribe((base + "/+/+/command").c_str());
    client_->publish(availabilityTopic().c_str(), "online", true);
}


void HaPublisher::loop() {
    if (!connected_) {
        return;
    }
    const uint32_t now = millis();

    if (!discovered_) {
        if (now - connectedAtMs_ < kCollectExistingMs || !refreshDeviceInfo()) {
            return;
        }
        publishDiscovery();
        removeStaleEntities();
        discovered_ = true;
    }

    if (settings_.haDiscoverySeconds > 0 && now - lastDiscoveryMs_ > settings_.haDiscoverySeconds * 1000UL) {
        publishDiscovery();
    }
    if (now - lastPollMs_ >= settings_.haPollSeconds * 1000UL) {
        lastPollMs_ = now;
        publishStates();
    }
}


// =============================================================================
// Discovery
// =============================================================================

// Mirrors _get_generator_info(): controller type and capabilities come from
// start_info_json. Returns false until the controller has been detected.
bool HaPublisher::refreshDeviceInfo() {
    if (!service_->snapshot().initialized) {
        return false;
    }
    JsonDocument startInfo;
    buildStartInfoReport(*service_, settings_, startInfo);

    const std::string controller = lowercase(startInfo["Controller"] | "");
    policy_.controllerType = controller.find("evolution") != std::string::npos ? "evolution" : "nexus";

    device_.model          = startInfo["model"] | "Generator";
    caps_.writeQuietMode   = startInfo["WriteQuietMode"] | false;
    caps_.remoteCommands   = startInfo["RemoteCommands"] | false;
    caps_.exerciseControls = startInfo["ExerciseControls"] | true;
    // Upstream looks for an "Enhanced Exercise Mode" entry that Evolution and
    // Nexus reports never contain, so these controllers never get the
    // frequency / day-of-month controls; kept identical for compatibility.
    caps_.enhancedExercise = false;
    return true;
}


void HaPublisher::publishDiscovery() {
    lastDiscoveryMs_ = millis();

    JsonDocument data;
    buildMergedReports(*service_, settings_, true, data);

    for (const SensorDefinition& sensor : catalog_.sensors) {
        if (!entityAllowed(sensor.id, sensor.name, sensor.path, sensor.filter, policy_)) {
            continue;
        }
        if (valueAtPath(data.as<JsonVariantConst>(), sensor.path).isNull()) {
            continue;   // no data on this controller
        }
        publishMessage(sensorDiscovery(sensor, device_));
    }

    dynamicSensors_ = discoverDynamicSensors(data.as<JsonVariantConst>(), catalog_);
    for (const SensorDefinition& sensor : dynamicSensors_) {
        if (entityAllowed(sensor.id, sensor.name, sensor.path, sensor.filter, policy_)) {
            publishMessage(sensorDiscovery(sensor, device_));
        }
    }

    for (const BinarySensorDefinition& sensor : catalog_.binarySensors) {
        if (!entityAllowed(sensor.id, sensor.name, sensor.path, sensor.filter, policy_)) {
            continue;
        }
        if (!sensor.onWhenNotEmpty && valueAtPath(data.as<JsonVariantConst>(), sensor.path).isNull()) {
            continue;
        }
        publishMessage(binarySensorDiscovery(sensor, device_));
    }

    for (const ButtonDefinition& button : catalog_.buttons) {
        if (entityAllowed(button.id, button.name, "", button.filter, policy_)) {
            publishMessage(buttonDiscovery(button, device_, caps_));
        }
    }
    for (const SwitchDefinition& entry : catalog_.switches) {
        if (entityAllowed(entry.id, entry.name, "", entry.filter, policy_)) {
            publishMessage(switchDiscovery(entry, device_, caps_));
        }
    }
    for (const SelectDefinition& select : catalog_.selects) {
        if (entityAllowed(select.id, select.name, "", select.filter, policy_)) {
            publishMessage(selectDiscovery(select, device_, caps_));
        }
    }
    for (const NumberDefinition& number : catalog_.numbers) {
        if (entityAllowed(number.id, number.name, "", number.filter, policy_)) {
            publishMessage(numberDiscovery(number, device_, caps_));
        }
    }

    publishMessage(updateDiscovery(device_));
    client_->publish(stateTopic(device_, "update", "genmon_software").c_str(), updateState(device_).c_str(), true);
}


// Removes entities a previous install published that this one does not
// define (for example Raspberry Pi platform statistics).
void HaPublisher::removeStaleEntities() {
    if (cleanupDone_) {
        return;
    }
    cleanupDone_ = true;

    std::set<std::string> defined = {kUpdateEntity};
    for (const auto& sensor : catalog_.sensors) {
        if (entityAllowed(sensor.id, sensor.name, sensor.path, sensor.filter, policy_)) defined.insert("sensor/" + sensor.id);
    }
    for (const auto& sensor : dynamicSensors_) {
        if (entityAllowed(sensor.id, sensor.name, sensor.path, sensor.filter, policy_)) defined.insert("sensor/" + sensor.id);
    }
    for (const auto& sensor : catalog_.binarySensors) {
        if (entityAllowed(sensor.id, sensor.name, sensor.path, sensor.filter, policy_)) defined.insert("binary_sensor/" + sensor.id);
    }
    for (const auto& button : catalog_.buttons) {
        if (entityAllowed(button.id, button.name, "", button.filter, policy_)) defined.insert("button/" + button.id);
    }
    for (const auto& entry : catalog_.switches) {
        if (entityAllowed(entry.id, entry.name, "", entry.filter, policy_)) defined.insert("switch/" + entry.id);
    }
    for (const auto& select : catalog_.selects) {
        if (entityAllowed(select.id, select.name, "", select.filter, policy_)) defined.insert("select/" + select.id);
    }
    for (const auto& number : catalog_.numbers) {
        if (entityAllowed(number.id, number.name, "", number.filter, policy_)) defined.insert("number/" + number.id);
    }

    for (const std::string& key : existingEntities_) {
        if (defined.count(key)) {
            continue;
        }
        const size_t      slash = key.find('/');
        const std::string topic = device_.discoveryPrefix + "/" + key.substr(0, slash) + "/" +
                                  device_.deviceId + "/" + key.substr(slash + 1) + "/config";
        client_->publish(topic.c_str(), "", true);
        Serial.printf("[genmon] removed stale Home Assistant entity %s\n", key.c_str());
    }
}


void HaPublisher::publishMessage(const DiscoveryMessage& message) {
    if (!client_->publish(message.topic.c_str(), message.payload.c_str(), true)) {
        Serial.printf("[genmon] MQTT publish failed (%u bytes): %s\n",
                      static_cast<unsigned>(message.payload.size()), message.topic.c_str());
    }
}


// =============================================================================
// States
// =============================================================================

void HaPublisher::publishStates() {
    JsonDocument data;
    buildMergedReports(*service_, settings_, true, data);
    JsonVariantConst root = data.as<JsonVariantConst>();

    for (const SensorDefinition& sensor : discoverDynamicSensors(root, catalog_)) {
        const bool known = std::any_of(dynamicSensors_.begin(), dynamicSensors_.end(),
                                       [&](const SensorDefinition& existing) { return existing.id == sensor.id; });
        if (known || !entityAllowed(sensor.id, sensor.name, sensor.path, sensor.filter, policy_)) {
            continue;
        }
        dynamicSensors_.push_back(sensor);
        publishMessage(sensorDiscovery(sensor, device_));
    }

    auto publishSensor = [&](const SensorDefinition& sensor) {
        JsonVariantConst value = valueAtPath(root, sensor.path);
        if (value.isNull()) {
            return;
        }
        const auto state = sensorState(value, sensor);
        if (state) {
            publishState("sensor", sensor.id, *state);
        }
    };
    for (const SensorDefinition& sensor : catalog_.sensors) {
        if (entityAllowed(sensor.id, sensor.name, sensor.path, sensor.filter, policy_)) {
            publishSensor(sensor);
        }
    }
    for (const SensorDefinition& sensor : dynamicSensors_) {
        publishSensor(sensor);
    }

    for (const BinarySensorDefinition& sensor : catalog_.binarySensors) {
        if (!entityAllowed(sensor.id, sensor.name, sensor.path, sensor.filter, policy_)) {
            continue;
        }
        JsonVariantConst value = valueAtPath(root, sensor.path);
        if (!value.isNull()) {
            publishState("binary_sensor", sensor.id, binarySensorState(value, sensor));
        } else if (sensor.onWhenNotEmpty) {
            publishState("binary_sensor", sensor.id, "OFF");
        }
    }

    for (const SwitchDefinition& entry : catalog_.switches) {
        if (entry.statePath.empty() || !entityAllowed(entry.id, entry.name, "", entry.filter, policy_)) {
            continue;
        }
        JsonVariantConst value = valueAtPath(root, entry.statePath);
        if (!value.isNull()) {
            const bool on = lowercase(value.as<std::string>()) == lowercase(entry.payloadOn);
            publishState("switch", entry.id, on ? "ON" : "OFF");
        }
    }

    JsonVariantConst exercise = valueAtPath(root, kExerciseTimePath);
    if (exercise.is<const char*>()) {
        parseExerciseTime(exercise.as<const char*>(), exercise_);
        publishExerciseStates();
    }
}


void HaPublisher::publishState(const char* kind, const std::string& entityId, const std::string& value) {
    const std::string key   = std::string(kind) + "/" + entityId;
    const auto        found = lastValues_.find(key);
    if (found != lastValues_.end() && found->second == value) {
        return;
    }
    lastValues_[key] = value;
    client_->publish(stateTopic(device_, kind, entityId).c_str(), value.c_str(), true);
}


void HaPublisher::publishExerciseStates() {
    if (caps_.enhancedExercise) {
        client_->publish(stateTopic(device_, "select", "exercise_frequency").c_str(), exercise_.frequency.c_str(), true);
        client_->publish(stateTopic(device_, "number", "exercise_day_of_month").c_str(),
                         std::to_string(exercise_.dayOfMonth).c_str(), true);
    }
    client_->publish(stateTopic(device_, "select", "exercise_day_of_week").c_str(), exercise_.dayOfWeek.c_str(), true);
    client_->publish(stateTopic(device_, "number", "exercise_hour").c_str(), std::to_string(exercise_.hour).c_str(), true);
    client_->publish(stateTopic(device_, "number", "exercise_minute").c_str(), std::to_string(exercise_.minute).c_str(), true);
}


// =============================================================================
// Commands
// =============================================================================

bool HaPublisher::handleMessage(const std::string& topic, const std::string& payload) {
    const std::string configMarker = "/" + device_.deviceId + "/";
    if (topic.rfind(device_.discoveryPrefix + "/", 0) == 0 && endsWith(topic, "/config") &&
        topic.find(configMarker) != std::string::npos) {
        const std::vector<std::string> parts = splitTopic(topic);
        if (parts.size() >= 5 && !payload.empty()) {
            existingEntities_.insert(parts[parts.size() - 4] + "/" + parts[parts.size() - 2]);
        }
        return true;
    }

    if (topic == device_.discoveryPrefix + "/status") {
        if (payload == "online" && discovered_) {
            publishDiscovery();   // Home Assistant restarted
        }
        return true;
    }

    if (topic.rfind(device_.baseTopic + "/", 0) != 0) {
        return false;
    }
    const std::vector<std::string> parts = splitTopic(topic);
    if (parts.size() < 4) {
        return false;
    }
    const std::string& kind     = parts[parts.size() - 3];
    const std::string& entityId = parts[parts.size() - 2];
    const std::string& action   = parts[parts.size() - 1];

    if (action == "command" && kind == "button") {
        handleButton(entityId);
    } else if (action == "set" && kind == "switch") {
        handleSwitch(entityId, payload);
    } else if (action == "set" && kind == "select") {
        handleSelect(entityId, payload);
    } else if (action == "set" && kind == "number") {
        handleNumber(entityId, payload);
    } else if (action == "command" && kind == "update") {
        Serial.println("[genmon] firmware updates are installed from the web page, not Home Assistant");
    } else {
        return false;
    }
    return true;
}


void HaPublisher::handleButton(const std::string& entityId) {
    for (const ButtonDefinition& button : catalog_.buttons) {
        if (button.id == entityId) {
            sendCommand(button.command);
            return;
        }
    }
}


void HaPublisher::handleSwitch(const std::string& entityId, const std::string& payload) {
    for (const SwitchDefinition& entry : catalog_.switches) {
        if (entry.id != entityId) {
            continue;
        }
        const bool on = lowercase(payload) == "on";
        sendCommand(on ? entry.commandOn : entry.commandOff);
        client_->publish(stateTopic(device_, "switch", entityId).c_str(), on ? "ON" : "OFF", true);
        return;
    }
}


void HaPublisher::handleSelect(const std::string& entityId, const std::string& payload) {
    for (const SelectDefinition& select : catalog_.selects) {
        if (select.id != entityId) {
            continue;
        }
        if (std::find(select.options.begin(), select.options.end(), payload) == select.options.end()) {
            return;
        }
        if (select.commandTemplate == "exercise") {
            if (entityId == "exercise_frequency") exercise_.frequency = payload;
            if (entityId == "exercise_day_of_week") exercise_.dayOfWeek = payload;
            sendCommand(exerciseCommand(exercise_, caps_.enhancedExercise));
        }
        client_->publish(stateTopic(device_, "select", entityId).c_str(), payload.c_str(), true);
        return;
    }
}


void HaPublisher::handleNumber(const std::string& entityId, const std::string& payload) {
    for (const NumberDefinition& number : catalog_.numbers) {
        if (number.id != entityId) {
            continue;
        }
        char*        end   = nullptr;
        const double value = std::strtod(payload.c_str(), &end);
        if (end == payload.c_str() || value < number.min || value > number.max) {
            return;
        }
        const int whole = static_cast<int>(value);
        if (number.commandTemplate == "exercise") {
            if (entityId == "exercise_day_of_month") exercise_.dayOfMonth = whole;
            if (entityId == "exercise_hour")         exercise_.hour       = whole;
            if (entityId == "exercise_minute")       exercise_.minute     = whole;
            sendCommand(exerciseCommand(exercise_, caps_.enhancedExercise));
        }
        client_->publish(stateTopic(device_, "number", entityId).c_str(), std::to_string(whole).c_str(), true);
        return;
    }
}


void HaPublisher::sendCommand(const std::string& command) {
    const std::string result = service_->submitCommand(command);
    Serial.printf("[genmon] Home Assistant command \"%s\": %s\n", command.c_str(), result.c_str());
}

}  // namespace genmon
