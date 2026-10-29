// =============================================================================
// web_portal.cpp - HTTP interface: UI page, genmon JSON endpoints, settings, OTA
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "web_portal.h"

#include <Arduino.h>
#include <Update.h>
#include <WiFi.h>

#include <cstdio>

#include "reports.h"
#include "web_page.h"


namespace genmon {

namespace {

// =============================================================================
// Constants
// =============================================================================

constexpr const char* kAdminUser      = "admin";
constexpr const char* kRealm          = "genmon";
constexpr const char* kReportPrefix   = "/cmd/";
constexpr uint32_t    kRebootDelayMs  = 1500;   // let the HTTP response go out first

}  // namespace


// =============================================================================
// Lifecycle
// =============================================================================

void WebPortal::begin(Settings& settings, GeneratorService& service, Network& network, MqttBridge& mqtt) {
    settings_ = &settings;
    service_  = &service;
    network_  = &network;
    mqtt_     = &mqtt;

    server_.on("/",              HTTP_GET,  [this]() { handleRoot(); });
    server_.on("/api/registers", HTTP_GET,  [this]() { handleRegisters(); });
    server_.on("/api/events",    HTTP_GET,  [this]() { handleEvents(); });
    server_.on("/api/info",      HTTP_GET,  [this]() { handleInfo(); });
    server_.on("/api/settings",  HTTP_GET,  [this]() { handleGetSettings(); });
    server_.on("/api/settings",  HTTP_POST, [this]() { handlePostSettings(); });
    server_.on("/api/command",   HTTP_POST, [this]() { handleCommand(); });
    server_.on("/api/reboot",    HTTP_POST, [this]() { handleReboot(); });
    server_.on("/api/update",    HTTP_POST,
               [this]() { handleUpdateFinished(); },
               [this]() { handleUpdateUpload(); });
    server_.onNotFound([this]() { handleNotFound(); });
    server_.begin();
}


void WebPortal::loop() {
    server_.handleClient();
    if (rebootPending_ && millis() - rebootAtMs_ > kRebootDelayMs) {
        ESP.restart();
    }
}


// =============================================================================
// Helpers
// =============================================================================

// With no admin password, changes are accepted only from clients of the
// setup access point (someone physically near the generator).
bool WebPortal::authorized() {
    if (settings_->adminPassword.empty()) {
        if (network_->setupApActive() && server_.client().localIP() == WiFi.softAPIP()) {
            return true;
        }
        sendError(403, "Set an admin password from the setup access point first");
        return false;
    }
    if (server_.authenticate(kAdminUser, settings_->adminPassword.c_str())) {
        return true;
    }
    server_.requestAuthentication(BASIC_AUTH, kRealm);
    return false;
}


void WebPortal::sendJson(int status, const JsonDocument& document) {
    String body;
    serializeJson(document, body);
    server_.send(status, "application/json", body);
}


void WebPortal::sendError(int status, const std::string& message) {
    JsonDocument document;
    document["error"] = message;
    sendJson(status, document);
}


// =============================================================================
// Read-only handlers
// =============================================================================

void WebPortal::handleRoot() {
    server_.send_P(200, "text/html", kWebPage);
}


void WebPortal::handleNotFound() {
    const std::string uri = server_.uri().c_str();
    if (uri.rfind(kReportPrefix, 0) == 0) {
        JsonDocument document;
        if (buildNamedReport(uri.substr(std::char_traits<char>::length(kReportPrefix)), *service_, *settings_, document)) {
            sendJson(200, document);
            return;
        }
    }
    sendError(404, "Not found: " + uri);
}


void WebPortal::handleRegisters() {
    JsonDocument document;
    JsonObject   list = document["Registers"].to<JsonObject>();
    for (const auto& entry : service_->registers()) {
        char key[8];
        std::snprintf(key, sizeof(key), "%04x", entry.first);
        std::string hex;
        for (uint8_t byte : entry.second) {
            char pair[3];
            std::snprintf(pair, sizeof(pair), "%02x", byte);
            hex += pair;
        }
        list[key] = hex;
    }
    sendJson(200, document);
}


void WebPortal::handleEvents() {
    JsonDocument document;
    JsonArray    list = document["Events"].to<JsonArray>();
    for (const EventRecord& event : service_->recentEvents()) {
        JsonObject item = list.add<JsonObject>();
        item["epoch"] = event.epoch;
        item["text"]  = event.text;
    }
    sendJson(200, document);
}


void WebPortal::handleInfo() {
    JsonDocument document;
    document["firmware"]       = kFirmwareVersion;
    document["sitename"]       = settings_->siteName;
    document["address"]        = network_->address();
    document["setup_ap"]       = network_->setupApActive();
    document["setup_ap_name"]  = network_->setupApName();
    document["wifi_ssid"]      = settings_->wifiSsid;
    document["admin_set"]      = !settings_->adminPassword.empty();
    document["mqtt_enabled"]   = mqtt_->enabled();
    document["mqtt_connected"] = mqtt_->enabled() && mqtt_->connected();
    document["mqtt_error"]     = mqtt_->lastError();
    document["health"]         = service_->health();
    sendJson(200, document);
}


// =============================================================================
// Authenticated handlers
// =============================================================================

void WebPortal::handleGetSettings() {
    if (!authorized()) {
        return;
    }
    JsonDocument document;
    toJson(*settings_, document.to<JsonObject>());
    sendJson(200, document);
}


void WebPortal::handlePostSettings() {
    if (!authorized()) {
        return;
    }
    JsonDocument               body;
    const DeserializationError error = deserializeJson(body, server_.arg("plain"));
    if (error || !body.is<JsonObject>()) {
        sendError(400, "Body must be a JSON object");
        return;
    }

    std::string message;
    if (!applyJson(*settings_, body.as<JsonObjectConst>(), message)) {
        sendError(400, message);
        return;
    }
    saveSettings(*settings_);

    JsonDocument reply;
    reply["result"] = "Saved; restarting";
    sendJson(200, reply);
    rebootPending_ = true;
    rebootAtMs_    = millis();
}


void WebPortal::handleCommand() {
    if (!authorized()) {
        return;
    }
    const std::string command = server_.hasArg("command") ? server_.arg("command").c_str()
                                                          : server_.arg("plain").c_str();
    JsonDocument reply;
    reply["result"] = service_->submitCommand(command);
    sendJson(200, reply);
}


void WebPortal::handleReboot() {
    if (!authorized()) {
        return;
    }
    JsonDocument reply;
    reply["result"] = "Restarting";
    sendJson(200, reply);
    rebootPending_ = true;
    rebootAtMs_    = millis();
}


void WebPortal::handleUpdateUpload() {
    HTTPUpload& upload = server_.upload();
    switch (upload.status) {
        case UPLOAD_FILE_START:
            uploadAuthorized_ = settings_->adminPassword.empty()
                ? (network_->setupApActive() && server_.client().localIP() == WiFi.softAPIP())
                : server_.authenticate(kAdminUser, settings_->adminPassword.c_str());
            if (uploadAuthorized_ && !Update.begin(UPDATE_SIZE_UNKNOWN)) {
                Update.printError(Serial);
            }
            break;
        case UPLOAD_FILE_WRITE:
            if (uploadAuthorized_ && Update.write(upload.buf, upload.currentSize) != upload.currentSize) {
                Update.printError(Serial);
            }
            break;
        case UPLOAD_FILE_END:
            if (uploadAuthorized_ && !Update.end(true)) {
                Update.printError(Serial);
            }
            break;
        default:
            if (uploadAuthorized_) {
                Update.abort();
            }
            break;
    }
}


void WebPortal::handleUpdateFinished() {
    if (!uploadAuthorized_) {
        if (!authorized()) {
            return;
        }
        sendError(400, "No firmware received");
        return;
    }
    if (Update.hasError() || !Update.isFinished()) {
        sendError(500, std::string("Update failed: ") + Update.errorString());
        return;
    }
    JsonDocument reply;
    reply["result"] = "Update installed; restarting";
    sendJson(200, reply);
    rebootPending_ = true;
    rebootAtMs_    = millis();
}

}  // namespace genmon
