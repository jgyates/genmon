// =============================================================================
// modbus_frame.h - Modbus RTU frame building and response parsing
// =============================================================================
//
// Pure byte-level helpers with no I/O, so they run on the ESP32 and in the
// host unit tests alike. Generac Evolution / Nexus controllers speak plain
// Modbus RTU: function 0x03 to read holding registers, 0x10 to write them.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <cstddef>
#include <cstdint>
#include <vector>


namespace genmon {

// =============================================================================
// Constants
// =============================================================================

constexpr uint8_t kFunctionReadHolding   = 0x03;
constexpr uint8_t kFunctionWriteMultiple = 0x10;
constexpr uint8_t kExceptionFlag         = 0x80;
constexpr uint8_t kExceptionAcknowledge  = 0x05;

constexpr size_t kCrcSize                = 2;
constexpr size_t kExceptionFrameSize     = 5;   // address, function, code, crc
constexpr size_t kWriteResponseFrameSize = 8;   // address, function, reg, count, crc
constexpr size_t kReadResponseHeaderSize = 3;   // address, function, byte count


// =============================================================================
// Types
// =============================================================================

enum class FrameStatus {
    Incomplete,   // more bytes are needed before the frame can be judged
    Complete,     // a valid response; see ParsedResponse
    Invalid,      // CRC, address, or function mismatch
};

struct ParsedResponse {
    uint8_t              function      = 0;
    bool                 isException   = false;
    uint8_t              exceptionCode = 0;
    std::vector<uint8_t> payload;   // register bytes, big-endian, for reads
};


// =============================================================================
// Functions
// =============================================================================

// Standard Modbus CRC-16 (poly 0xA001 reflected, init 0xFFFF).
uint16_t modbusCrc(const uint8_t* data, size_t length);

// Appends the CRC low byte first, as Modbus RTU requires.
void appendCrc(std::vector<uint8_t>& frame);

std::vector<uint8_t> buildReadRequest(uint8_t address, uint16_t startRegister, uint16_t registerCount);

// `data` holds big-endian register bytes and must have an even length.
std::vector<uint8_t> buildWriteRequest(uint8_t address, uint16_t startRegister, const std::vector<uint8_t>& data);

// Number of bytes the full response will occupy, or 0 if not yet knowable
// from the bytes received so far.
size_t expectedResponseLength(const std::vector<uint8_t>& buffer, uint8_t requestFunction);

FrameStatus parseResponse(const std::vector<uint8_t>& buffer,
                          uint8_t                     expectedAddress,
                          uint8_t                     requestFunction,
                          ParsedResponse&             out);

}  // namespace genmon
