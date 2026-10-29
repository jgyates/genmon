// =============================================================================
// network.h - Wi-Fi station with a setup access point fallback, mDNS, NTP
// =============================================================================
//
// With no saved network, or when the saved network cannot be reached, the
// ESP32 also opens its own access point so the web page stays reachable for
// configuration. The access point closes once the station link is up.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <cstdint>
#include <string>

#include "settings.h"


namespace genmon {

// =============================================================================
// Constants
// =============================================================================

extern const char* const kSetupApPassword;


// =============================================================================
// Types
// =============================================================================

class Network {
public:
    void begin(const Settings& settings);
    void loop();

    bool        stationConnected() const;
    bool        setupApActive() const { return apActive_; }
    std::string setupApName() const   { return apName_; }
    std::string address() const;

private:
    void startSetupAp();
    void stopSetupAp();

    Settings    settings_;
    std::string apName_;
    bool        apActive_          = false;
    bool        servicesStarted_   = false;
    uint32_t    disconnectedSince_ = 0;
};

}  // namespace genmon
