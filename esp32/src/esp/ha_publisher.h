// =============================================================================
// ha_publisher.h - Home Assistant MQTT discovery publisher
// =============================================================================
//
// The ESP32 counterpart of upstream's addon/genhomeassistant.py. Same topics,
// unique_ids, entity definitions and value rules, so a Home Assistant install
// that used the Raspberry Pi add-on sees the same device and entities when
// the ESP32 is configured with the same device_id and base_topic.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <PubSubClient.h>

#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <vector>

#include "core/ha_catalog.h"
#include "core/ha_discovery.h"
#include "core/ha_values.h"
#include "generator_service.h"
#include "settings.h"


namespace genmon {

// =============================================================================
// Types
// =============================================================================

class HaPublisher {
public:
    void begin(const Settings& settings, GeneratorService& service, PubSubClient& client);

    std::string availabilityTopic() const;

    void onConnected(const std::string& configurationUrl);
    void loop();

    // Returns true when the message belonged to this publisher.
    bool handleMessage(const std::string& topic, const std::string& payload);

private:
    bool refreshDeviceInfo();
    void publishDiscovery();
    void removeStaleEntities();
    void publishStates();
    void publishState(const char* kind, const std::string& entityId, const std::string& value);
    void publishMessage(const DiscoveryMessage& message);
    void publishExerciseStates();

    void handleButton(const std::string& entityId);
    void handleSwitch(const std::string& entityId, const std::string& payload);
    void handleSelect(const std::string& entityId, const std::string& payload);
    void handleNumber(const std::string& entityId, const std::string& payload);
    void sendCommand(const std::string& command);

    Settings          settings_;
    GeneratorService* service_ = nullptr;
    PubSubClient*     client_  = nullptr;

    EntityCatalog                 catalog_;
    EntityPolicy                  policy_;
    HaDevice                      device_;
    HaCapabilities                caps_;
    std::vector<SensorDefinition> dynamicSensors_;
    ExerciseSettings              exercise_;

    std::map<std::string, std::string> lastValues_;
    std::set<std::string>              existingEntities_;   // "kind/entity_id" seen on the broker
    std::set<std::string>              publishedEntities_;

    bool     connected_       = false;
    bool     discovered_      = false;
    bool     cleanupDone_     = false;
    uint32_t connectedAtMs_   = 0;
    uint32_t lastPollMs_      = 0;
    uint32_t lastDiscoveryMs_ = 0;
};

}  // namespace genmon
