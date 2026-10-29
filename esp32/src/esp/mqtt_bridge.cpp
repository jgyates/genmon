// =============================================================================
// mqtt_bridge.cpp - MQTT broker connection shared by both publishers
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "mqtt_bridge.h"

#include <Arduino.h>


namespace genmon {

namespace {

// =============================================================================
// Constants
// =============================================================================

// Discovery payloads with device info run to ~700 bytes; 2 KB leaves room for
// retained configs echoed back from the broker during stale-entity cleanup.
constexpr uint16_t kBufferBytes      = 2048;
constexpr uint32_t kRetryIntervalMs  = 10000;
constexpr uint16_t kKeepAliveSeconds = 30;

}  // namespace


// =============================================================================
// Public interface
// =============================================================================

void MqttBridge::begin(const Settings& settings, GeneratorService& service) {
    settings_ = settings;
    enabled_  = !settings.mqttHost.empty() && (settings.haEnabled || settings.genmqttEnabled);
    if (!enabled_) {
        return;
    }

    client_.setServer(settings_.mqttHost.c_str(), settings_.mqttPort);
    client_.setBufferSize(kBufferBytes);
    client_.setKeepAlive(kKeepAliveSeconds);
    client_.setCallback([this](char* topic, uint8_t* payload, unsigned int length) {
        onMessage(topic, payload, length);
    });

    ha_.begin(settings_, service, client_);
    genmqtt_.begin(settings_, service, client_);
}


void MqttBridge::loop(bool networkUp, const std::string& monitorAddress) {
    if (!enabled_ || !networkUp) {
        return;
    }
    if (!client_.connected()) {
        if (lastAttemptMs_ == 0 || millis() - lastAttemptMs_ > kRetryIntervalMs) {
            lastAttemptMs_ = millis();
            connect(monitorAddress);
        }
        return;
    }

    client_.loop();
    if (settings_.haEnabled) {
        ha_.loop();
    }
    if (settings_.genmqttEnabled) {
        genmqtt_.loop();
    }
}


// =============================================================================
// Connection
// =============================================================================

void MqttBridge::connect(const std::string& monitorAddress) {
    const std::string willTopic   = settings_.haEnabled ? ha_.availabilityTopic() : genmqtt_.statusTopic();
    const char*       willPayload = settings_.haEnabled ? "offline" : "Offline";
    const char*       user        = settings_.mqttUser.empty() ? nullptr : settings_.mqttUser.c_str();
    const char*       password    = settings_.mqttPassword.empty() ? nullptr : settings_.mqttPassword.c_str();

    const bool ok = client_.connect(settings_.mqttClientId.c_str(), user, password,
                                    willTopic.c_str(), 1, true, willPayload);
    if (!ok) {
        lastError_ = "MQTT connect failed, state " + std::to_string(client_.state());
        Serial.printf("[genmon] %s\n", lastError_.c_str());
        return;
    }

    lastError_.clear();
    Serial.printf("[genmon] MQTT connected to %s:%u\n", settings_.mqttHost.c_str(), settings_.mqttPort);
    if (settings_.haEnabled) {
        ha_.onConnected("http://" + monitorAddress + "/");
    }
    if (settings_.genmqttEnabled) {
        genmqtt_.onConnected();
    }
}


void MqttBridge::onMessage(char* topic, uint8_t* payload, unsigned int length) {
    const std::string topicText(topic);
    const std::string body(reinterpret_cast<const char*>(payload), length);

    if (settings_.haEnabled && ha_.handleMessage(topicText, body)) {
        return;
    }
    if (settings_.genmqttEnabled) {
        genmqtt_.handleMessage(topicText, body);
    }
}

}  // namespace genmon
