// =============================================================================
// genmqtt_publisher.cpp - Plain-topic MQTT publisher (upstream genmqtt add-on)
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "genmqtt_publisher.h"

#include <Arduino.h>

#include <algorithm>
#include <cctype>

#include "core/mqtt_flatten.h"
#include "reports.h"


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


std::vector<std::string> splitList(const std::string& text) {
    std::vector<std::string> items;
    size_t start = 0;
    while (start <= text.size()) {
        const size_t comma = text.find(',', start);
        std::string  item  = text.substr(start, comma - start);
        const size_t first = item.find_first_not_of(' ');
        if (first != std::string::npos) {
            items.push_back(lowercase(item.substr(first, item.find_last_not_of(' ') - first + 1)));
        }
        if (comma == std::string::npos) {
            break;
        }
        start = comma + 1;
    }
    return items;
}

}  // namespace


// =============================================================================
// Public interface
// =============================================================================

void GenmqttPublisher::begin(const Settings& settings, GeneratorService& service, PubSubClient& client) {
    settings_  = settings;
    service_   = &service;
    client_    = &client;
    blacklist_ = splitList(settings.genmqttBlacklist);
}


std::string GenmqttPublisher::statusTopic() const {
    return withRoot("generator/client_status");
}


void GenmqttPublisher::onConnected() {
    lastValues_.clear();
    client_->subscribe(withRoot("generator/#").c_str());
    client_->publish(statusTopic().c_str(), "Online", true);
}


void GenmqttPublisher::loop() {
    const uint32_t now = millis();
    if (now - lastPollMs_ < settings_.genmqttPollSeconds * 1000UL || !service_->snapshot().initialized) {
        return;
    }
    lastPollMs_ = now;

    JsonDocument reports;
    buildMergedReports(*service_, settings_, settings_.genmqttNumeric, reports);

    for (const TopicValue& item : flattenReports(reports.as<JsonVariantConst>(), "generator", FlattenOptions{})) {
        if (blacklisted(item.topic)) {
            continue;
        }
        const auto found = lastValues_.find(item.topic);
        if (found != lastValues_.end() && found->second == item.value) {
            continue;
        }
        lastValues_[item.topic] = item.value;

        std::string topic = withRoot(item.topic);
        if (settings_.genmqttRemoveSpaces) {
            std::replace(topic.begin(), topic.end(), ' ', '_');
        }
        client_->publish(topic.c_str(), item.value.c_str(), settings_.genmqttRetain);
    }
}


bool GenmqttPublisher::handleMessage(const std::string& topic, const std::string& payload) {
    if (lowercase(topic) != lowercase(withRoot("generator/command"))) {
        return false;
    }
    if (!settings_.genmqttAllowCommands || payload.empty()) {
        return true;
    }
    const std::string result = service_->submitCommand(payload);
    Serial.printf("[genmon] MQTT command \"%s\": %s\n", payload.c_str(), result.c_str());
    return true;
}


// =============================================================================
// Helpers
// =============================================================================

std::string GenmqttPublisher::withRoot(const std::string& path) const {
    if (settings_.genmqttRootTopic.empty()) {
        return path;
    }
    return settings_.genmqttRootTopic + "/" + path;
}


bool GenmqttPublisher::blacklisted(const std::string& path) const {
    const std::string lowerPath = lowercase(path);
    for (const std::string& item : blacklist_) {
        if (!item.empty() && lowerPath.find(item) != std::string::npos) {
            return true;
        }
    }
    return false;
}

}  // namespace genmon
