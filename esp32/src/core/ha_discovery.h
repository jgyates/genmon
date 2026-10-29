// =============================================================================
// ha_discovery.h - Home Assistant MQTT discovery messages
// =============================================================================
//
// Topic and payload layout copied from upstream genhomeassistant so entities
// keep their unique_id ("genmon_<device_id>_<entity_id>") and topics:
//   <discovery_prefix>/<kind>/<device_id>/<entity_id>/config
//   <base_topic>/<kind>/<entity_id>/state | set | command
//   <base_topic>/status                    availability (online / offline)

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <string>

#include "ha_catalog.h"


namespace genmon {

// =============================================================================
// Types
// =============================================================================

struct HaDevice {
    std::string deviceId         = "generator";
    std::string deviceName       = "Generator";
    std::string discoveryPrefix  = "homeassistant";
    std::string baseTopic        = "genmon";
    std::string model            = "Generator";
    std::string softwareVersion;
    std::string configurationUrl;
    bool        useMetric        = false;
};

// Capability flags genhomeassistant reads from genmon's start_info_json.
struct HaCapabilities {
    bool remoteCommands   = true;
    bool exerciseControls = true;
    bool writeQuietMode   = false;
    bool enhancedExercise = false;
};

// An empty payload removes the entity from Home Assistant.
struct DiscoveryMessage {
    std::string topic;
    std::string payload;
};


// =============================================================================
// Functions
// =============================================================================

std::string availabilityTopic(const HaDevice& device);
std::string stateTopic(const HaDevice& device, const char* kind, const std::string& entityId);

DiscoveryMessage sensorDiscovery(const SensorDefinition& sensor, const HaDevice& device);
DiscoveryMessage binarySensorDiscovery(const BinarySensorDefinition& sensor, const HaDevice& device);
DiscoveryMessage buttonDiscovery(const ButtonDefinition& button, const HaDevice& device, const HaCapabilities& caps);
DiscoveryMessage switchDiscovery(const SwitchDefinition& entry, const HaDevice& device, const HaCapabilities& caps);
DiscoveryMessage selectDiscovery(const SelectDefinition& select, const HaDevice& device, const HaCapabilities& caps);
DiscoveryMessage numberDiscovery(const NumberDefinition& number, const HaDevice& device, const HaCapabilities& caps);
DiscoveryMessage updateDiscovery(const HaDevice& device);

// State payload for the "Software Update" entity (always up to date: the
// ESP32 is updated through its web page, not from Home Assistant).
std::string updateState(const HaDevice& device);

}  // namespace genmon
