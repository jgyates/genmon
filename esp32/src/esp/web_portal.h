// =============================================================================
// web_portal.h - HTTP interface: UI page, genmon JSON endpoints, settings, OTA
// =============================================================================
//
// Read-only endpoints are open, as on genmon. Anything that changes state
// (commands, settings, firmware, reboot) needs HTTP basic auth as "admin"
// with the configured admin password; until one is set, those endpoints are
// only reachable through the setup access point.
//
//   GET  /                      web UI
//   GET  /cmd/<report>          genmon reports: status_json, status_num_json,
//                               maint_json, outage_json, monitor_json,
//                               logs_json (and _num_ variants), start_info_json
//   GET  /api/registers         raw register cache
//   GET  /api/events            recent monitor events
//   GET  /api/info              network / MQTT / firmware summary
//   GET  /api/settings          configuration (passwords omitted)      [auth]
//   POST /api/settings          JSON body; saves and reboots           [auth]
//   POST /api/command           body "setremote=start" etc.            [auth]
//   POST /api/update            multipart firmware.bin upload          [auth]
//   POST /api/reboot                                                   [auth]

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <WebServer.h>

#include <string>

#include "generator_service.h"
#include "mqtt_bridge.h"
#include "network.h"
#include "settings.h"


namespace genmon {

// =============================================================================
// Types
// =============================================================================

class WebPortal {
public:
    void begin(Settings& settings, GeneratorService& service, Network& network, MqttBridge& mqtt);
    void loop();

private:
    bool authorized();
    void sendJson(int status, const JsonDocument& document);
    void sendError(int status, const std::string& message);

    void handleRoot();
    void handleNotFound();
    void handleRegisters();
    void handleEvents();
    void handleInfo();
    void handleGetSettings();
    void handlePostSettings();
    void handleCommand();
    void handleUpdateUpload();
    void handleUpdateFinished();
    void handleReboot();

    WebServer         server_{80};
    Settings*         settings_ = nullptr;
    GeneratorService* service_  = nullptr;
    Network*          network_  = nullptr;
    MqttBridge*       mqtt_     = nullptr;
    bool              uploadAuthorized_ = false;
    bool              rebootPending_    = false;
    uint32_t          rebootAtMs_       = 0;
};

}  // namespace genmon
