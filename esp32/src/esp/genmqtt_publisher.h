// =============================================================================
// genmqtt_publisher.h - Plain-topic MQTT publisher (upstream genmqtt add-on)
// =============================================================================
//
// Publishes every report value to [root_topic/]generator/<path> when it
// changes and accepts genmon commands on [root_topic/]generator/command,
// matching addon/genmqtt.py for setups that consume those topics directly.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <PubSubClient.h>

#include <cstdint>
#include <map>
#include <string>
#include <vector>

#include "generator_service.h"
#include "settings.h"


namespace genmon {

// =============================================================================
// Types
// =============================================================================

class GenmqttPublisher {
public:
    void begin(const Settings& settings, GeneratorService& service, PubSubClient& client);

    std::string statusTopic() const;   // "Online" / "Offline" last-will topic

    void onConnected();
    void loop();
    bool handleMessage(const std::string& topic, const std::string& payload);

private:
    std::string withRoot(const std::string& path) const;
    bool        blacklisted(const std::string& path) const;

    Settings                           settings_;
    GeneratorService*                  service_ = nullptr;
    PubSubClient*                      client_  = nullptr;
    std::vector<std::string>           blacklist_;
    std::map<std::string, std::string> lastValues_;
    uint32_t                           lastPollMs_ = 0;
};

}  // namespace genmon
