// =============================================================================
// main.cpp - genmon-esp32 entry point
// =============================================================================
//
// Wires the services together. The generator service runs in its own task;
// everything network-facing runs from loop() on the Arduino task.

// =============================================================================
// Includes
// =============================================================================

#include <Arduino.h>

#include "esp/generator_service.h"
#include "esp/mqtt_bridge.h"
#include "esp/network.h"
#include "esp/reports.h"
#include "esp/settings.h"
#include "esp/web_portal.h"


// =============================================================================
// Constants
// =============================================================================

namespace {

constexpr uint32_t kConsoleBaud = 115200;

// Pressing the DevKitC's BOOT button (GPIO 0) within the window after start-up
// and holding it erases all settings, for recovering from a lost admin
// password. (Held during reset itself, BOOT selects the ROM flash loader.)
constexpr int      kFactoryResetPin    = 0;
constexpr uint32_t kFactoryResetWindow = 3000;
constexpr uint32_t kFactoryResetHoldMs = 5000;


// =============================================================================
// Services
// =============================================================================

genmon::Settings         settings;
genmon::GeneratorService generator;
genmon::Network          network;
genmon::MqttBridge       mqtt;
genmon::WebPortal        web;


// =============================================================================
// Helpers
// =============================================================================

void factoryResetIfRequested() {
    pinMode(kFactoryResetPin, INPUT_PULLUP);
    Serial.println("[genmon] hold BOOT now for 5 s to erase all settings");

    const uint32_t windowStart = millis();
    while (millis() - windowStart < kFactoryResetWindow) {
        if (digitalRead(kFactoryResetPin) == HIGH) {
            delay(20);
            continue;
        }
        const uint32_t pressStart = millis();
        while (digitalRead(kFactoryResetPin) == LOW) {
            if (millis() - pressStart > kFactoryResetHoldMs) {
                Serial.println("[genmon] BOOT held: erasing settings");
                genmon::eraseSettings();
                ESP.restart();
            }
            delay(20);
        }
    }
}

}  // namespace


// =============================================================================
// Entry point
// =============================================================================

void setup() {
    Serial.begin(kConsoleBaud);
    Serial.printf("\n[genmon] genmon-esp32 %s starting\n", genmon::kFirmwareVersion);

    factoryResetIfRequested();
    settings = genmon::loadSettings();

    network.begin(settings);
    generator.begin(settings);
    mqtt.begin(settings, generator);
    web.begin(settings, generator, network, mqtt);
}


void loop() {
    network.loop();
    web.loop();
    mqtt.loop(network.stationConnected(), network.address());
    delay(2);
}
