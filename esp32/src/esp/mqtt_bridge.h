// =============================================================================
// mqtt_bridge.h - MQTT broker connection shared by both publishers
// =============================================================================
//
// One broker connection carries the Home Assistant publisher and the
// genmqtt-style publisher. MQTT allows a single last-will message, so it is
// set to the Home Assistant availability topic when that publisher is
// enabled, and to genmqtt's client_status topic otherwise.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <PubSubClient.h>
#include <WiFiClient.h>

#include <cstdint>
#include <string>

#include "generator_service.h"
#include "genmqtt_publisher.h"
#include "ha_publisher.h"
#include "settings.h"


namespace genmon {

// =============================================================================
// Types
// =============================================================================

class MqttBridge {
public:
    void begin(const Settings& settings, GeneratorService& service);
    void loop(bool networkUp, const std::string& monitorAddress);

    bool        enabled() const   { return enabled_; }
    bool        connected()       { return client_.connected(); }
    std::string lastError() const { return lastError_; }

private:
    void connect(const std::string& monitorAddress);
    void onMessage(char* topic, uint8_t* payload, unsigned int length);

    Settings         settings_;
    WiFiClient       network_;
    PubSubClient     client_{network_};
    HaPublisher      ha_;
    GenmqttPublisher genmqtt_;
    bool             enabled_         = false;
    uint32_t         lastAttemptMs_   = 0;
    std::string      lastError_;
};

}  // namespace genmon
