// =============================================================================
// modbus_frame.cpp - Modbus RTU frame building and response parsing
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "modbus_frame.h"


namespace genmon {

// =============================================================================
// CRC
// =============================================================================

uint16_t modbusCrc(const uint8_t* data, size_t length) {
    constexpr uint16_t kPolynomial = 0xA001;

    uint16_t crc = 0xFFFF;
    for (size_t index = 0; index < length; ++index) {
        crc ^= data[index];
        for (int bit = 0; bit < 8; ++bit) {
            const bool lowBitSet = (crc & 0x0001) != 0;
            crc >>= 1;
            if (lowBitSet) {
                crc ^= kPolynomial;
            }
        }
    }
    return crc;
}


void appendCrc(std::vector<uint8_t>& frame) {
    const uint16_t crc = modbusCrc(frame.data(), frame.size());
    frame.push_back(static_cast<uint8_t>(crc & 0xFF));
    frame.push_back(static_cast<uint8_t>(crc >> 8));
}


// =============================================================================
// Requests
// =============================================================================

std::vector<uint8_t> buildReadRequest(uint8_t address, uint16_t startRegister, uint16_t registerCount) {
    std::vector<uint8_t> frame = {
        address,
        kFunctionReadHolding,
        static_cast<uint8_t>(startRegister >> 8),
        static_cast<uint8_t>(startRegister & 0xFF),
        static_cast<uint8_t>(registerCount >> 8),
        static_cast<uint8_t>(registerCount & 0xFF),
    };
    appendCrc(frame);
    return frame;
}


std::vector<uint8_t> buildWriteRequest(uint8_t address, uint16_t startRegister, const std::vector<uint8_t>& data) {
    const uint16_t registerCount = static_cast<uint16_t>(data.size() / 2);

    std::vector<uint8_t> frame = {
        address,
        kFunctionWriteMultiple,
        static_cast<uint8_t>(startRegister >> 8),
        static_cast<uint8_t>(startRegister & 0xFF),
        static_cast<uint8_t>(registerCount >> 8),
        static_cast<uint8_t>(registerCount & 0xFF),
        static_cast<uint8_t>(data.size()),
    };
    frame.insert(frame.end(), data.begin(), data.end());
    appendCrc(frame);
    return frame;
}


// =============================================================================
// Responses
// =============================================================================

size_t expectedResponseLength(const std::vector<uint8_t>& buffer, uint8_t requestFunction) {
    if (buffer.size() < 2) {
        return 0;
    }
    if (buffer[1] & kExceptionFlag) {
        return kExceptionFrameSize;
    }
    if (requestFunction == kFunctionWriteMultiple) {
        return kWriteResponseFrameSize;
    }
    if (buffer.size() < kReadResponseHeaderSize) {
        return 0;
    }
    return kReadResponseHeaderSize + buffer[2] + kCrcSize;
}


FrameStatus parseResponse(const std::vector<uint8_t>& buffer,
                          uint8_t                     expectedAddress,
                          uint8_t                     requestFunction,
                          ParsedResponse&             out) {
    const size_t expected = expectedResponseLength(buffer, requestFunction);
    if (expected == 0 || buffer.size() < expected) {
        return FrameStatus::Incomplete;
    }

    const uint16_t computed = modbusCrc(buffer.data(), expected - kCrcSize);
    const uint16_t received = static_cast<uint16_t>(buffer[expected - 2] | (buffer[expected - 1] << 8));
    if (computed != received || buffer[0] != expectedAddress) {
        return FrameStatus::Invalid;
    }

    const uint8_t function = buffer[1] & static_cast<uint8_t>(~kExceptionFlag);
    if (function != requestFunction) {
        return FrameStatus::Invalid;
    }

    out             = ParsedResponse{};
    out.function    = function;
    out.isException = (buffer[1] & kExceptionFlag) != 0;
    if (out.isException) {
        out.exceptionCode = buffer[2];
        return FrameStatus::Complete;
    }
    if (requestFunction == kFunctionReadHolding) {
        out.payload.assign(buffer.begin() + kReadResponseHeaderSize, buffer.begin() + expected - kCrcSize);
    }
    return FrameStatus::Complete;
}

}  // namespace genmon
