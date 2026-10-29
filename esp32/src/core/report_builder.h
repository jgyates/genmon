// =============================================================================
// report_builder.h - genmon-compatible JSON reports
// =============================================================================
//
// Builds the same JSON trees genmon serves as status_json / status_num_json,
// maint_json, outage_json, monitor_json, logs_json and start_info_json. The
// Home Assistant and MQTT bridges walk these trees by path exactly as the
// upstream genhomeassistant and genmqtt add-ons do, which is what keeps
// existing Home Assistant entities and MQTT topics unchanged.
//
// genmon's layout is a list of single-key objects per section, e.g.
//   {"Status": [{"Engine": [{"Switch State": "Auto"}, ...]}, ...]}
// With `numeric` set, measurements become {"unit": "V", "type": "int", "value": 240}.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <ArduinoJson.h>

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "comm_stats.h"
#include "controller_info.h"
#include "generator_state.h"


namespace genmon {

// =============================================================================
// Types
// =============================================================================

// Values the controller cannot report; configured by the user.
struct SiteInfo {
    std::string siteName         = "SiteName";
    std::string model            = "Generic Evolution Air Cooled";
    std::string fuelType         = "Natural Gas";
    std::string ratedKw          = "0";
    std::string nominalRpm       = "3600";
    std::string nominalFrequency = "60";
    std::string phase            = "1";
    std::string monitorVersion;
};

// Run-time facts about the monitor itself.
struct MonitorInfo {
    std::string monitorTime;   // "Thursday October 29, 2026 14:05:00"
    std::string runTime;       // "genmon-esp32 running for 1 day, 2:03:04."
    std::string health;        // "OK" or a description of what is wrong
    std::string ipAddress;
    int32_t     wifiRssi       = 0;
    uint32_t    freeHeapBytes  = 0;
    int64_t     uptimeSeconds  = 0;
};

struct OutageLogEntry {
    std::string date;       // "MM-DD-YYYY HH:MM:SS"
    std::string duration;   // "H:MM:SS"
};

struct OutageView {
    bool                        inOutage = false;
    std::string                 statusText;
    std::optional<double>       minUtilityVolts;
    std::optional<double>       maxUtilityVolts;
    std::vector<OutageLogEntry> history;   // newest first
};


// =============================================================================
// Functions
// =============================================================================

void buildStatusReport(JsonObject            root,
                       const GeneratorState& state,
                       const GeneratorLogs&  logs,
                       const OutageView&     outage,
                       const ControllerInfo& info,
                       const MonitorInfo&    monitor,
                       bool                  numeric);

void buildMaintenanceReport(JsonObject            root,
                            const GeneratorState& state,
                            const ControllerInfo& info,
                            const SiteInfo&       site,
                            bool                  numeric);

void buildOutageReport(JsonObject            root,
                       const GeneratorState& state,
                       const OutageView&     outage,
                       const ControllerInfo& info,
                       bool                  numeric);

void buildMonitorReport(JsonObject            root,
                        const GeneratorState& state,
                        const CommStats&      comm,
                        const SiteInfo&       site,
                        const MonitorInfo&    monitor,
                        bool                  numeric);

void buildLogsReport(JsonObject root, const GeneratorLogs& logs, const ControllerInfo& info);

void buildStartInfo(JsonObject            root,
                    const GeneratorState& state,
                    const ControllerInfo& info,
                    const SiteInfo&       site);

// genmon's outage status sentence, e.g. "System in outage since 2026-...".
std::string outageStatusText(bool                   inOutage,
                             int64_t                outageStartEpoch,
                             std::optional<int64_t> lastStartEpoch,
                             std::optional<int64_t> lastDurationSeconds);

// "H:MM:SS", or "N days, H:MM:SS" past 24 hours, as Python prints timedelta.
std::string formatDuration(int64_t seconds);

}  // namespace genmon
