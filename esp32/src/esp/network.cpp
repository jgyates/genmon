// =============================================================================
// network.cpp - Wi-Fi station with a setup access point fallback, mDNS, NTP
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "network.h"

#include <Arduino.h>
#include <ESPmDNS.h>
#include <WiFi.h>

#include <cstdio>


namespace genmon {

// =============================================================================
// Constants
// =============================================================================

const char* const kSetupApPassword = "genmon-setup";

namespace {

constexpr uint32_t kFallbackAfterMs = 30000;   // station must connect within this
constexpr uint16_t kHttpPort        = 80;

}  // namespace


// =============================================================================
// Public interface
// =============================================================================

void Network::begin(const Settings& settings) {
    settings_ = settings;

    char name[32];
    std::snprintf(name, sizeof(name), "genmon-setup-%04X", static_cast<unsigned>(ESP.getEfuseMac() & 0xFFFF));
    apName_ = name;

    WiFi.persistent(false);
    WiFi.setHostname(settings_.hostname.c_str());
    WiFi.setAutoReconnect(true);

    if (settings_.wifiSsid.empty()) {
        startSetupAp();
    } else {
        WiFi.mode(WIFI_STA);
        WiFi.begin(settings_.wifiSsid.c_str(), settings_.wifiPassword.c_str());
    }
    disconnectedSince_ = millis();

    configTzTime(settings_.timeZone.c_str(), settings_.ntpServer.c_str());
}


void Network::loop() {
    if (stationConnected()) {
        disconnectedSince_ = millis();
        if (!servicesStarted_) {
            MDNS.begin(settings_.hostname.c_str());
            MDNS.addService("http", "tcp", kHttpPort);
            servicesStarted_ = true;
            Serial.printf("[genmon] connected: http://%s/ (http://%s.local/)\n",
                          address().c_str(), settings_.hostname.c_str());
        }
        if (apActive_) {
            stopSetupAp();
        }
        return;
    }

    if (!apActive_ && millis() - disconnectedSince_ > kFallbackAfterMs) {
        startSetupAp();
    }
}


bool Network::stationConnected() const {
    return WiFi.status() == WL_CONNECTED;
}


std::string Network::address() const {
    if (stationConnected()) {
        return WiFi.localIP().toString().c_str();
    }
    return WiFi.softAPIP().toString().c_str();
}


// =============================================================================
// Setup access point
// =============================================================================

void Network::startSetupAp() {
    WiFi.mode(settings_.wifiSsid.empty() ? WIFI_AP : WIFI_AP_STA);
    WiFi.softAP(apName_.c_str(), kSetupApPassword);
    apActive_ = true;
    Serial.printf("[genmon] setup access point \"%s\" at http://%s/\n",
                  apName_.c_str(), WiFi.softAPIP().toString().c_str());
}


void Network::stopSetupAp() {
    WiFi.softAPdisconnect(true);
    WiFi.mode(WIFI_STA);
    apActive_ = false;
}

}  // namespace genmon
