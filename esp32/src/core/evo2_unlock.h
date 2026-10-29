// =============================================================================
// evo2_unlock.h - Evolution 2.0 Modbus "encapsulation" unlock sequence
// =============================================================================
//
// Evolution 2.0 controllers start answering plain Modbus reads with exception
// 0x05 (Acknowledge) unless the master periodically sends a three-frame unlock
// sequence to register 0xEA60. Each frame carries an AES-128 encrypted copy of
// the next read request, nybble-scrambled across two 16-byte blocks. This
// mirrors the sequence Generac's Mobile Link module sends.
//
// The AES primitive is injected so this file stays free of platform crypto
// and can be unit tested on the host.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <array>
#include <cstdint>
#include <functional>
#include <vector>


namespace genmon {

// =============================================================================
// Constants
// =============================================================================

constexpr uint16_t kEncapsulationRegister = 0xEA60;
constexpr size_t   kAesBlockSize          = 16;

// Number of Acknowledge exceptions tolerated before unlocking is attempted.
constexpr uint32_t kUnlockExceptionThreshold = 2;

// The unlock is repeated at least this often once encapsulation is active.
constexpr uint32_t kUnlockIntervalMs = 3UL * 60UL * 1000UL;

extern const std::array<uint8_t, kAesBlockSize> kEvo2AesKey;
extern const std::array<uint8_t, kAesBlockSize> kEvo2AesIv;


// =============================================================================
// Types
// =============================================================================

// Encrypts exactly one 16-byte block with AES-128-CBC starting from
// kEvo2AesIv every time (the controller restarts the chain per block).
using BlockEncryptor = std::function<void(const uint8_t* input, uint8_t* output)>;

// Register data for the three writes to kEncapsulationRegister, in order.
struct UnlockPayloads {
    std::vector<uint8_t> keyFrame;       // prefix F1 01
    std::vector<uint8_t> requestFrame;   // prefix F1 51
    std::vector<uint8_t> confirmFrame;   // prefix F1 A7
};


// =============================================================================
// Functions
// =============================================================================

// Swaps nybbles between the first and second 16-byte halves of a 32-byte
// buffer using the controller's alternating even/odd pattern.
std::vector<uint8_t> nybbleSwap(std::vector<uint8_t> buffer);

// Builds the three unlock payloads that wrap `readRequest`, the complete RTU
// read frame (including CRC) that will be sent right after the unlock.
UnlockPayloads buildUnlockPayloads(const std::vector<uint8_t>& readRequest, const BlockEncryptor& encryptBlock);

}  // namespace genmon
