// =============================================================================
// modbus_port.h - Modbus RTU master on an ESP32 UART
// =============================================================================
//
// Talks to the generator controller at 9600 8N1 through an RS-232 level
// shifter. Owns transaction timing, link statistics and the Evolution 2.0
// unlock handshake; framing and payload rules live in core/.
//
// Not thread-safe: only the generator service task may call it.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <Arduino.h>

#include <cstdint>
#include <mutex>
#include <vector>

#include "core/comm_stats.h"
#include "core/modbus_frame.h"
#include "core/register_cache.h"


namespace genmon {

// =============================================================================
// Types
// =============================================================================

class ModbusPort {
public:
    void begin(HardwareSerial& serial, int rxPin, int txPin, uint8_t address);

    bool readRegisters(uint16_t startRegister, uint16_t registerCount, RegisterBytes& out);
    bool writeRegisters(uint16_t startRegister, const std::vector<uint8_t>& data);

    CommStats stats() const;

    // True once a valid response has arrived within the last `windowMs`.
    bool recentlyActive(uint32_t windowMs) const;

private:
    enum class Outcome {
        Ok,
        Exception,
        Timeout,
        Invalid,
    };

    Outcome transact(const std::vector<uint8_t>& request,
                     uint8_t                     function,
                     uint32_t                    timeoutMs,
                     ParsedResponse&             response);

    void unlockIfNeeded(uint16_t startRegister, uint16_t registerCount);
    void discardInput();

    HardwareSerial* serial_  = nullptr;
    uint8_t         address_ = 0x9D;

    uint32_t lastUnlockMs_        = 0;
    uint32_t ackCountAtUnlock_    = 0;
    bool     unlockedOnce_        = false;
    uint32_t lastGoodResponseMs_  = 0;
    uint32_t statsStartMs_        = 0;

    mutable std::mutex statsMutex_;
    CommStats          stats_;
};

}  // namespace genmon
