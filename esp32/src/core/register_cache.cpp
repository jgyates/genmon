// =============================================================================
// register_cache.cpp - Thread-safe cache of the controller's register values
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "register_cache.h"


namespace genmon {

// =============================================================================
// RegisterCache
// =============================================================================

void RegisterCache::store(uint16_t startRegister, const RegisterBytes& bytes) {
    std::lock_guard<std::mutex> lock(mutex_);
    values_[startRegister] = bytes;
}


void RegisterCache::clear() {
    std::lock_guard<std::mutex> lock(mutex_);
    values_.clear();
}


std::optional<RegisterBytes> RegisterCache::bytes(uint16_t startRegister) const {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto found = values_.find(startRegister);
    if (found == values_.end()) {
        return std::nullopt;
    }
    return found->second;
}


std::optional<uint16_t> RegisterCache::u16(uint16_t startRegister) const {
    const auto value = bytes(startRegister);
    if (!value || value->size() != 2) {
        return std::nullopt;
    }
    return static_cast<uint16_t>(((*value)[0] << 8) | (*value)[1]);
}


std::optional<uint32_t> RegisterCache::u32(uint16_t startRegister) const {
    const auto value = bytes(startRegister);
    if (!value || value->size() != 4) {
        return std::nullopt;
    }
    return (static_cast<uint32_t>((*value)[0]) << 24) |
           (static_cast<uint32_t>((*value)[1]) << 16) |
           (static_cast<uint32_t>((*value)[2]) << 8)  |
            static_cast<uint32_t>((*value)[3]);
}


RegisterSnapshot RegisterCache::snapshot() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return values_;
}

}  // namespace genmon
