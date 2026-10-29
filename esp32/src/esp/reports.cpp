// =============================================================================
// reports.cpp - genmon JSON reports for the current generator snapshot
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "reports.h"

#include <Arduino.h>
#include <WiFi.h>

#include <ctime>

#include "core/report_builder.h"


namespace genmon {

// =============================================================================
// Constants
// =============================================================================

const char* const kFirmwareVersion = "esp32-1.0.0";

namespace {

constexpr const char* kProgramName = "genmon-esp32";


// =============================================================================
// Helpers
// =============================================================================

MonitorInfo monitorInfo(const GeneratorService& service) {
    MonitorInfo info;

    const std::time_t now = std::time(nullptr);
    std::tm           local{};
    localtime_r(&now, &local);
    char clock[48];
    std::strftime(clock, sizeof(clock), "%A %B %d, %Y %H:%M:%S", &local);

    const int64_t uptime = static_cast<int64_t>(millis() / 1000);
    info.monitorTime     = clock;
    info.runTime         = std::string(kProgramName) + " running for " + formatDuration(uptime) + ".";
    info.health          = service.health();
    info.ipAddress       = WiFi.localIP().toString().c_str();
    info.wifiRssi        = WiFi.RSSI();
    info.freeHeapBytes   = ESP.getFreeHeap();
    info.uptimeSeconds   = uptime;
    return info;
}


SiteInfo siteInfo(const Settings& settings) {
    SiteInfo site       = siteInfoFrom(settings);
    site.monitorVersion = kFirmwareVersion;
    return site;
}


void addReport(JsonObject root, const std::string& kind, const GeneratorSnapshot& snapshot,
               const MonitorInfo& monitor, const SiteInfo& site, bool numeric) {
    if (kind == "status") {
        buildStatusReport(root, snapshot.state, snapshot.logs, snapshot.outage, snapshot.info, monitor, numeric);
    } else if (kind == "maint") {
        buildMaintenanceReport(root, snapshot.state, snapshot.info, site, numeric);
    } else if (kind == "outage") {
        buildOutageReport(root, snapshot.state, snapshot.outage, snapshot.info, numeric);
    } else if (kind == "monitor") {
        buildMonitorReport(root, snapshot.state, snapshot.comm, site, monitor, numeric);
    } else if (kind == "logs") {
        buildLogsReport(root, snapshot.logs, snapshot.info);
    }
}

}  // namespace


// =============================================================================
// Public interface
// =============================================================================

bool buildNamedReport(const std::string&      name,
                      const GeneratorService& service,
                      const Settings&         settings,
                      JsonDocument&           out) {
    if (name == "start_info_json") {
        buildStartInfoReport(service, settings, out);
        return true;
    }

    static const char* const kKinds[] = {"status", "maint", "outage", "monitor", "logs"};
    for (const char* kind : kKinds) {
        const std::string plain   = std::string(kind) + "_json";
        const std::string numeric = std::string(kind) + "_num_json";
        if (name != plain && name != numeric) {
            continue;
        }
        const GeneratorSnapshot snapshot = service.snapshot();
        addReport(out.to<JsonObject>(), kind, snapshot, monitorInfo(service), siteInfo(settings), name == numeric);
        return true;
    }
    return false;
}


void buildMergedReports(const GeneratorService& service,
                        const Settings&         settings,
                        bool                    numeric,
                        JsonDocument&           out) {
    const GeneratorSnapshot snapshot = service.snapshot();
    const MonitorInfo       monitor  = monitorInfo(service);
    const SiteInfo          site     = siteInfo(settings);

    JsonObject root = out.to<JsonObject>();
    for (const char* kind : {"status", "maint", "outage", "monitor"}) {
        addReport(root, kind, snapshot, monitor, site, numeric);
    }
}


void buildStartInfoReport(const GeneratorService& service, const Settings& settings, JsonDocument& out) {
    const GeneratorSnapshot snapshot = service.snapshot();
    buildStartInfo(out.to<JsonObject>(), snapshot.state, snapshot.info, siteInfo(settings));
}

}  // namespace genmon
