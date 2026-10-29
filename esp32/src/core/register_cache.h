// =============================================================================
// register_cache.h - Thread-safe cache of the controller's register values
// =============================================================================
//
// The poller writes every successful read here keyed by the read's starting
// register; decoders read from it. Multi-word reads (the 32-bit status word at
// 0x0001, the 10-byte serial number, log entries) are stored whole under their
// start register, matching how the original genmon keyed its register dict.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <cstdint>
#include <map>
#include <mutex>
#include <optional>
#include <vector>


namespace genmon {

// =============================================================================
// Types
// =============================================================================

using RegisterBytes    = std::vector<uint8_t>;
using RegisterSnapshot = std::map<uint16_t, RegisterBytes>;

class RegisterCache {
public:
    void store(uint16_t startRegister, const RegisterBytes& bytes);
    void clear();

    std::optional<RegisterBytes> bytes(uint16_t startRegister) const;

    // Big-endian 16-bit value of a single-register read.
    std::optional<uint16_t> u16(uint16_t startRegister) const;

    // Big-endian 32-bit value of a two-register read.
    std::optional<uint32_t> u32(uint16_t startRegister) const;

    RegisterSnapshot snapshot() const;

private:
    mutable std::mutex mutex_;
    RegisterSnapshot   values_;
};

}  // namespace genmon
