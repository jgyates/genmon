// =============================================================================
// settings.h - Persistent configuration stored in ESP32 NVS
// =============================================================================
//
// The ESP32 equivalent of genmon.conf, genhomeassistant.conf and genmqtt.conf.
// Option names and defaults follow those files so a user moving from the
// Raspberry Pi can copy values across one for one (see esp32/README.md).

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <ArduinoJson.h>

#include <cstdint>
#include <string>

#include "core/controller_info.h"
#include "core/monitor_options.h"
#include "core/report_builder.h"


namespace genmon {

// =============================================================================
// Types
// =============================================================================

struct Settings {
    // Network
    std::string wifiSsid;
    std::string wifiPassword;
    std::string hostname   = "genmon";
    std::string timeZone   = "EST5EDT,M3.2.0,M11.1.0";   // POSIX TZ string
    std::string ntpServer  = "pool.ntp.org";
    std::string adminPassword;                          // empty: changes only from the setup portal

    // Site (genmon.conf)
    std::string siteName         = "SiteName";
    std::string model            = "Generic Evolution Air Cooled";
    std::string fuelType         = "Natural Gas";
    float       ratedKw          = 0.0f;
    std::string nominalRpm       = "3600";
    std::string nominalFrequency = "60";
    std::string phase            = "1";
    int         nominalLineVolts = 240;

    // Controller (genmon.conf)
    uint8_t     modbusAddress        = 0x9D;
    int         uartRxPin            = 16;
    int         uartTxPin            = 17;
    Detect      evolutionOverride    = Detect::Auto;
    Detect      liquidCooledOverride = Detect::Auto;
    bool        enhancedExercise     = false;
    bool        legacyExerciseWrite  = false;
    float       currentDivider       = 0.0f;
    float       currentOffset        = 0.0f;
    float       additionalRunHours   = 0.0f;
    std::string serialNumberOverride;
    bool        ignoreUnknownStatus  = true;
    bool        nexusDoubleFrequency = true;
    bool        disableOutageCheck   = false;
    bool        syncGeneratorTime    = false;

    // MQTT broker (shared by both publishers)
    std::string mqttHost;
    uint16_t    mqttPort     = 1883;
    std::string mqttUser;
    std::string mqttPassword;
    std::string mqttClientId = "genmon_ha";

    // Home Assistant discovery (genhomeassistant.conf)
    bool        haEnabled             = true;
    std::string haDiscoveryPrefix     = "homeassistant";
    std::string haBaseTopic           = "genmon";
    std::string haDeviceId            = "generator";
    std::string haDeviceName          = "Generator";
    std::string haBlacklist           = "Tiles";
    bool        haIncludeMonitorStats = true;
    uint32_t    haPollSeconds         = 3;
    uint32_t    haDiscoverySeconds    = 300;

    // Plain topic publishing (genmqtt.conf)
    bool        genmqttEnabled        = false;
    std::string genmqttRootTopic;
    bool        genmqttNumeric        = false;
    bool        genmqttRetain         = false;
    bool        genmqttRemoveSpaces   = false;
    std::string genmqttBlacklist      = "Monitor,Run Time,Monitor Time,Generator Time,External Data";
    bool        genmqttAllowCommands  = true;
    uint32_t    genmqttPollSeconds    = 2;
};


// =============================================================================
// Functions
// =============================================================================

Settings loadSettings();
void     saveSettings(const Settings& settings);
void     eraseSettings();

// Passwords are never written out; their presence is reported as a flag.
void toJson(const Settings& settings, JsonObject out);

// Applies the fields present in `in`. Empty password fields keep the stored
// password. Returns false and sets `error` when a value is out of range.
bool applyJson(Settings& settings, JsonObjectConst in, std::string& error);

MonitorOptions monitorOptionsFrom(const Settings& settings);
SiteInfo       siteInfoFrom(const Settings& settings);

}  // namespace genmon
