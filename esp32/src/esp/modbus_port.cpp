// =============================================================================
// modbus_port.cpp - Modbus RTU master on an ESP32 UART
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "modbus_port.h"

#include <mbedtls/aes.h>

#include <cstring>

#include "core/evo2_unlock.h"


namespace genmon {

namespace {

// =============================================================================
// Constants
// =============================================================================

constexpr uint32_t kBaudRate           = 9600;
// A reply normally takes ~30 ms; the controller occasionally needs close to
// a second, so this leaves headroom without stalling the poll loop for long.
constexpr uint32_t kResponseTimeoutMs  = 1500;
constexpr uint32_t kUnlockTimeoutMs    = 500;
// Modbus RTU needs 3.5 character times of silence between frames (~4 ms at
// 9600 baud); a little more keeps slow controllers happy.
constexpr uint32_t kInterFrameGapMs    = 6;
constexpr uint32_t kSettleAfterErrorMs = 50;


// =============================================================================
// Helpers
// =============================================================================

// AES-128-CBC over a single block, restarting the chain from the fixed IV
// for every block as the controller expects.
void encryptEvolution2Block(const uint8_t* input, uint8_t* output) {
    uint8_t iv[kAesBlockSize];
    std::memcpy(iv, kEvo2AesIv.data(), sizeof(iv));

    mbedtls_aes_context context;
    mbedtls_aes_init(&context);
    mbedtls_aes_setkey_enc(&context, kEvo2AesKey.data(), 128);
    mbedtls_aes_crypt_cbc(&context, MBEDTLS_AES_ENCRYPT, kAesBlockSize, iv, input, output);
    mbedtls_aes_free(&context);
}

}  // namespace


// =============================================================================
// Public interface
// =============================================================================

void ModbusPort::begin(HardwareSerial& serial, int rxPin, int txPin, uint8_t address) {
    serial_  = &serial;
    address_ = address;
    serial_->begin(kBaudRate, SERIAL_8N1, rxPin, txPin);
    statsStartMs_ = millis();

    std::lock_guard<std::mutex> lock(statsMutex_);
    stats_          = CommStats{};
    stats_.baudRate = kBaudRate;
}


bool ModbusPort::readRegisters(uint16_t startRegister, uint16_t registerCount, RegisterBytes& out) {
    unlockIfNeeded(startRegister, registerCount);

    ParsedResponse response;
    const Outcome  outcome = transact(buildReadRequest(address_, startRegister, registerCount),
                                      kFunctionReadHolding, kResponseTimeoutMs, response);
    if (outcome != Outcome::Ok || response.payload.size() != registerCount * 2u) {
        return false;
    }
    out = response.payload;
    return true;
}


bool ModbusPort::writeRegisters(uint16_t startRegister, const std::vector<uint8_t>& data) {
    unlockIfNeeded(startRegister, static_cast<uint16_t>(data.size() / 2));

    ParsedResponse response;
    return transact(buildWriteRequest(address_, startRegister, data),
                    kFunctionWriteMultiple, kResponseTimeoutMs, response) == Outcome::Ok;
}


CommStats ModbusPort::stats() const {
    std::lock_guard<std::mutex> lock(statsMutex_);
    CommStats copy     = stats_;
    copy.uptimeSeconds = (millis() - statsStartMs_) / 1000.0;
    return copy;
}


bool ModbusPort::recentlyActive(uint32_t windowMs) const {
    return lastGoodResponseMs_ != 0 && (millis() - lastGoodResponseMs_) < windowMs;
}


// =============================================================================
// Transactions
// =============================================================================

ModbusPort::Outcome ModbusPort::transact(const std::vector<uint8_t>& request,
                                         uint8_t                     function,
                                         uint32_t                    timeoutMs,
                                         ParsedResponse&             response) {
    if (serial_->available()) {
        std::lock_guard<std::mutex> lock(statsMutex_);
        ++stats_.unexpectedData;
    }
    discardInput();
    delay(kInterFrameGapMs);

    serial_->write(request.data(), request.size());
    serial_->flush();
    const uint32_t sentMs = millis();
    {
        std::lock_guard<std::mutex> lock(statsMutex_);
        ++stats_.txPackets;
    }

    std::vector<uint8_t> buffer;
    while (millis() - sentMs < timeoutMs) {
        while (serial_->available()) {
            buffer.push_back(static_cast<uint8_t>(serial_->read()));
        }
        const FrameStatus status = parseResponse(buffer, address_, function, response);
        if (status == FrameStatus::Incomplete) {
            delay(1);
            continue;
        }

        std::lock_guard<std::mutex> lock(statsMutex_);
        if (status == FrameStatus::Invalid) {
            ++stats_.crcErrors;
            stats_.discardedBytes += buffer.size();
            delay(kSettleAfterErrorMs);
            discardInput();
            return Outcome::Invalid;
        }

        ++stats_.rxPackets;
        stats_.transactionSeconds += (millis() - sentMs) / 1000.0;
        lastGoodResponseMs_ = millis();
        if (response.isException) {
            ++stats_.exceptions;
            if (response.exceptionCode == kExceptionAcknowledge) {
                ++stats_.ackExceptions;
            }
            return Outcome::Exception;
        }
        return Outcome::Ok;
    }

    std::lock_guard<std::mutex> lock(statsMutex_);
    ++stats_.timeouts;
    stats_.discardedBytes += buffer.size();
    return Outcome::Timeout;
}


// Evolution 2.0 starts answering with Acknowledge exceptions once it wants
// the encapsulation unlock; resend it when new exceptions arrive and at
// least every few minutes after that.
void ModbusPort::unlockIfNeeded(uint16_t startRegister, uint16_t registerCount) {
    uint32_t ackCount = 0;
    {
        std::lock_guard<std::mutex> lock(statsMutex_);
        ackCount = stats_.ackExceptions;
    }
    if (ackCount <= kUnlockExceptionThreshold) {
        return;
    }
    const bool newExceptions = ackCount != ackCountAtUnlock_;
    const bool intervalDue   = millis() - lastUnlockMs_ > kUnlockIntervalMs;
    if (unlockedOnce_ && !newExceptions && !intervalDue) {
        return;
    }

    unlockedOnce_     = true;
    lastUnlockMs_     = millis();
    ackCountAtUnlock_ = ackCount;

    const UnlockPayloads payloads = buildUnlockPayloads(buildReadRequest(address_, startRegister, registerCount),
                                                        encryptEvolution2Block);
    ParsedResponse ignored;
    transact(buildWriteRequest(address_, kEncapsulationRegister, payloads.keyFrame),
             kFunctionWriteMultiple, kUnlockTimeoutMs, ignored);
    transact(buildWriteRequest(address_, kEncapsulationRegister, payloads.requestFrame),
             kFunctionWriteMultiple, kUnlockTimeoutMs, ignored);
    transact(buildWriteRequest(address_, kEncapsulationRegister, payloads.confirmFrame),
             kFunctionWriteMultiple, kUnlockTimeoutMs, ignored);
    discardInput();
}


void ModbusPort::discardInput() {
    while (serial_->available()) {
        serial_->read();
    }
}

}  // namespace genmon
