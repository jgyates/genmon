// =============================================================================
// settings.cpp - Persistent configuration stored in ESP32 NVS
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "settings.h"

#include <Preferences.h>

#include <algorithm>
#include <cctype>


namespace genmon {

namespace {

// =============================================================================
// Constants
// =============================================================================

constexpr const char* kNamespace = "genmon";


// =============================================================================
// Field table
// =============================================================================

// One list of every setting drives load, save and both JSON directions, so a
// new option needs exactly one line here. JSON names follow the upstream
// .conf option names; NVS keys are limited to 15 characters.
template <typename Visitor>
void visitFields(Settings& s, Visitor&& visit) {
    //    JSON name                       NVS key          member                    secret
    visit("wifi_ssid",                    "wifi_ssid",     s.wifiSsid,               false);
    visit("wifi_password",                "wifi_pass",     s.wifiPassword,           true);
    visit("hostname",                     "hostname",      s.hostname,               false);
    visit("timezone",                     "tz",            s.timeZone,               false);
    visit("ntp_server",                   "ntp",           s.ntpServer,              false);
    visit("admin_password",               "admin_pass",    s.adminPassword,          true);

    visit("sitename",                     "site",          s.siteName,               false);
    visit("model",                        "model",         s.model,                  false);
    visit("fueltype",                     "fuel",          s.fuelType,               false);
    visit("nominalkw",                    "rated_kw",      s.ratedKw,                false);
    visit("nominalrpm",                   "rpm",           s.nominalRpm,             false);
    visit("nominalfrequency",             "freq",          s.nominalFrequency,       false);
    visit("phase",                        "phase",         s.phase,                  false);
    visit("nominallinevolts",             "line_volts",    s.nominalLineVolts,       false);

    visit("address",                      "modbus_addr",   s.modbusAddress,          false);
    visit("uart_rx_pin",                  "uart_rx",       s.uartRxPin,              false);
    visit("uart_tx_pin",                  "uart_tx",       s.uartTxPin,              false);
    visit("evolutioncontroller",          "evo_override",  s.evolutionOverride,      false);
    visit("liquidcooled",                 "lc_override",   s.liquidCooledOverride,   false);
    visit("enhancedexercise",             "enh_exercise",  s.enhancedExercise,       false);
    visit("uselegacysetexercise",         "legacy_ex",     s.legacyExerciseWrite,    false);
    visit("currentdivider",               "cur_div",       s.currentDivider,         false);
    visit("currentoffset",                "cur_off",       s.currentOffset,          false);
    visit("additionalrunhours",           "add_hours",     s.additionalRunHours,     false);
    visit("serialnumberifmissing",        "serial_ovr",    s.serialNumberOverride,   false);
    visit("ignore_unknown",               "ignore_unk",    s.ignoreUnknownStatus,    false);
    visit("nexus_legacy_freq",            "nexus_freq",    s.nexusDoubleFrequency,   false);
    visit("disableoutagecheck",           "no_outage",     s.disableOutageCheck,     false);
    visit("synctime",                     "sync_time",     s.syncGeneratorTime,      false);

    visit("mqtt_address",                 "mqtt_host",     s.mqttHost,               false);
    visit("mqtt_port",                    "mqtt_port",     s.mqttPort,               false);
    visit("username",                     "mqtt_user",     s.mqttUser,               false);
    visit("password",                     "mqtt_pass",     s.mqttPassword,           true);
    visit("client_id",                    "mqtt_client",   s.mqttClientId,           false);

    visit("ha_enabled",                   "ha_on",         s.haEnabled,              false);
    visit("discovery_prefix",             "ha_prefix",     s.haDiscoveryPrefix,      false);
    visit("base_topic",                   "ha_base",       s.haBaseTopic,            false);
    visit("device_id",                    "ha_dev_id",     s.haDeviceId,             false);
    visit("device_name",                  "ha_dev_name",   s.haDeviceName,           false);
    visit("blacklist",                    "ha_blacklist",  s.haBlacklist,            false);
    visit("include_monitor_stats",        "ha_mon_stats",  s.haIncludeMonitorStats,  false);
    visit("poll_interval",                "ha_poll",       s.haPollSeconds,          false);
    visit("discovery_interval",           "ha_disc_int",   s.haDiscoverySeconds,     false);

    visit("genmqtt_enabled",              "gm_on",         s.genmqttEnabled,         false);
    visit("root_topic",                   "gm_root",       s.genmqttRootTopic,       false);
    visit("numeric_json",                 "gm_numeric",    s.genmqttNumeric,         false);
    visit("retain",                       "gm_retain",     s.genmqttRetain,          false);
    visit("remove_spaces",                "gm_no_spaces",  s.genmqttRemoveSpaces,    false);
    visit("genmqtt_blacklist",            "gm_blacklist",  s.genmqttBlacklist,       false);
    visit("genmqtt_allow_commands",       "gm_commands",   s.genmqttAllowCommands,   false);
    visit("genmqtt_poll_interval",        "gm_poll",       s.genmqttPollSeconds,     false);
}


// =============================================================================
// Visitors
// =============================================================================

struct Loader {
    Preferences& prefs;

    void operator()(const char*, const char* key, std::string& v, bool) { v = prefs.getString(key, v.c_str()).c_str(); }
    void operator()(const char*, const char* key, bool& v, bool)        { v = prefs.getBool(key, v); }
    void operator()(const char*, const char* key, int& v, bool)         { v = prefs.getInt(key, v); }
    void operator()(const char*, const char* key, float& v, bool)       { v = prefs.getFloat(key, v); }
    void operator()(const char*, const char* key, uint8_t& v, bool)     { v = prefs.getUChar(key, v); }
    void operator()(const char*, const char* key, uint16_t& v, bool)    { v = prefs.getUShort(key, v); }
    void operator()(const char*, const char* key, uint32_t& v, bool)    { v = prefs.getUInt(key, v); }
    void operator()(const char*, const char* key, Detect& v, bool) {
        v = static_cast<Detect>(prefs.getUChar(key, static_cast<uint8_t>(v)));
    }
};

struct Saver {
    Preferences& prefs;

    void operator()(const char*, const char* key, const std::string& v, bool) { prefs.putString(key, v.c_str()); }
    void operator()(const char*, const char* key, bool v, bool)               { prefs.putBool(key, v); }
    void operator()(const char*, const char* key, int v, bool)                { prefs.putInt(key, v); }
    void operator()(const char*, const char* key, float v, bool)              { prefs.putFloat(key, v); }
    void operator()(const char*, const char* key, uint8_t v, bool)            { prefs.putUChar(key, v); }
    void operator()(const char*, const char* key, uint16_t v, bool)           { prefs.putUShort(key, v); }
    void operator()(const char*, const char* key, uint32_t v, bool)           { prefs.putUInt(key, v); }
    void operator()(const char*, const char* key, Detect v, bool)             { prefs.putUChar(key, static_cast<uint8_t>(v)); }
};

struct JsonWriter {
    JsonObject out;

    void operator()(const char* name, const char*, const std::string& v, bool secret) {
        if (secret) {
            out[std::string(name) + "_set"] = !v.empty();
        } else {
            out[name] = v;
        }
    }
    void operator()(const char* name, const char*, bool v, bool)     { out[name] = v; }
    void operator()(const char* name, const char*, int v, bool)      { out[name] = v; }
    void operator()(const char* name, const char*, float v, bool)    { out[name] = v; }
    // The only byte setting is the Modbus address, which genmon.conf writes in hex.
    void operator()(const char* name, const char*, uint8_t v, bool) {
        char hex[4];
        snprintf(hex, sizeof(hex), "%02x", v);
        out[name] = hex;
    }
    void operator()(const char* name, const char*, uint16_t v, bool) { out[name] = v; }
    void operator()(const char* name, const char*, uint32_t v, bool) { out[name] = v; }
    void operator()(const char* name, const char*, Detect v, bool) {
        out[name] = v == Detect::Auto ? "auto" : (v == Detect::Yes ? "true" : "false");
    }
};

struct JsonReader {
    JsonObjectConst in;

    void operator()(const char* name, const char*, std::string& v, bool secret) {
        JsonVariantConst value = in[name];
        if (!value.is<const char*>()) {
            return;
        }
        const std::string text = value.as<const char*>();
        if (secret && text.empty()) {
            return;   // blank password field means "unchanged"
        }
        v = text;
    }
    void operator()(const char* name, const char*, uint8_t& v, bool) {
        JsonVariantConst value = in[name];
        if (value.is<const char*>()) {
            v = static_cast<uint8_t>(strtoul(value.as<const char*>(), nullptr, 16));
        } else if (!value.isNull()) {
            v = value.as<uint8_t>();
        }
    }
    template <typename Number>
    void operator()(const char* name, const char*, Number& v, bool) {
        JsonVariantConst value = in[name];
        if (!value.isNull()) {
            v = value.as<Number>();
        }
    }
    void operator()(const char* name, const char*, Detect& v, bool) {
        JsonVariantConst value = in[name];
        if (!value.is<const char*>()) {
            return;
        }
        std::string text = value.as<const char*>();
        std::transform(text.begin(), text.end(), text.begin(), [](unsigned char c) { return std::tolower(c); });
        v = text == "true" ? Detect::Yes : (text == "false" ? Detect::No : Detect::Auto);
    }
};


// =============================================================================
// Validation
// =============================================================================

bool validGpio(int pin) {
    // GPIO 6-11 drive the module's flash; 34-39 are input only (fine for RX).
    return pin >= 0 && pin <= 39 && !(pin >= 6 && pin <= 11);
}


bool validate(const Settings& settings, std::string& error) {
    if (!validGpio(settings.uartRxPin) || !validGpio(settings.uartTxPin) || settings.uartTxPin >= 34) {
        error = "UART pins must be usable GPIOs (TX cannot be 34-39)";
        return false;
    }
    if (settings.uartRxPin == settings.uartTxPin) {
        error = "UART RX and TX must be different pins";
        return false;
    }
    if (settings.nominalLineVolts < 100 || settings.nominalLineVolts > 600) {
        error = "nominallinevolts must be between 100 and 600";
        return false;
    }
    if (settings.ratedKw < 0.0f || settings.currentDivider < 0.0f) {
        error = "nominalkw and currentdivider cannot be negative";
        return false;
    }
    if (settings.haPollSeconds < 1 || settings.genmqttPollSeconds < 1) {
        error = "poll intervals must be at least 1 second";
        return false;
    }
    if (!settings.serialNumberOverride.empty() &&
        (settings.serialNumberOverride.size() != 10 ||
         !std::all_of(settings.serialNumberOverride.begin(), settings.serialNumberOverride.end(),
                      [](unsigned char c) { return std::isdigit(c); }))) {
        error = "serialnumberifmissing must be exactly ten digits";
        return false;
    }
    return true;
}

}  // namespace


// =============================================================================
// Persistence
// =============================================================================

Settings loadSettings() {
    Settings    settings;
    Preferences prefs;
    if (prefs.begin(kNamespace, true)) {
        visitFields(settings, Loader{prefs});
        prefs.end();
    }
    return settings;
}


void saveSettings(const Settings& settings) {
    Settings    copy = settings;
    Preferences prefs;
    if (prefs.begin(kNamespace, false)) {
        visitFields(copy, Saver{prefs});
        prefs.end();
    }
}


void eraseSettings() {
    Preferences prefs;
    if (prefs.begin(kNamespace, false)) {
        prefs.clear();
        prefs.end();
    }
}


// =============================================================================
// JSON
// =============================================================================

void toJson(const Settings& settings, JsonObject out) {
    Settings copy = settings;
    visitFields(copy, JsonWriter{out});
}


bool applyJson(Settings& settings, JsonObjectConst in, std::string& error) {
    Settings candidate = settings;
    visitFields(candidate, JsonReader{in});
    if (!validate(candidate, error)) {
        return false;
    }
    settings = candidate;
    return true;
}


// =============================================================================
// Conversions
// =============================================================================

MonitorOptions monitorOptionsFrom(const Settings& settings) {
    MonitorOptions options;
    options.ratedKw              = settings.ratedKw;
    options.nominalLineVolts     = settings.nominalLineVolts;
    options.currentDivider       = settings.currentDivider;
    options.currentOffset        = settings.currentOffset;
    options.additionalRunHours   = settings.additionalRunHours;
    options.fuelType             = settings.fuelType;
    options.serialNumberOverride = settings.serialNumberOverride;
    options.ignoreUnknownStatus  = settings.ignoreUnknownStatus;
    options.nexusDoubleFrequency = settings.nexusDoubleFrequency;
    return options;
}


SiteInfo siteInfoFrom(const Settings& settings) {
    char ratedKw[16];
    snprintf(ratedKw, sizeof(ratedKw), "%g", static_cast<double>(settings.ratedKw));

    SiteInfo site;
    site.siteName         = settings.siteName;
    site.model            = settings.model;
    site.fuelType         = settings.fuelType;
    site.ratedKw          = ratedKw;
    site.nominalRpm       = settings.nominalRpm;
    site.nominalFrequency = settings.nominalFrequency;
    site.phase            = settings.phase;
    return site;
}

}  // namespace genmon
