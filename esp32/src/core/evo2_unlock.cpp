// =============================================================================
// evo2_unlock.cpp - Evolution 2.0 Modbus "encapsulation" unlock sequence
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "evo2_unlock.h"


namespace genmon {

// =============================================================================
// Constants
// =============================================================================

const std::array<uint8_t, kAesBlockSize> kEvo2AesKey = {
    0x4A, 0x2A, 0xA3, 0xE4, 0x7E, 0xE0, 0x42, 0x2C,
    0xA4, 0xBC, 0x8D, 0x1D, 0x52, 0xDE, 0xD9, 0x69,
};

const std::array<uint8_t, kAesBlockSize> kEvo2AesIv = {
    0xC0, 0x94, 0xFB, 0xEB, 0xF5, 0x96, 0x43, 0x7F,
    0xA2, 0x2E, 0xFA, 0x84, 0xFC, 0xC5, 0x21, 0x52,
};

namespace {

// Plaintext header of the key frame; byte 9 (0xE3) selects the key slot.
const std::array<uint8_t, kAesBlockSize> kKeyFrameHeader = {
    0x00, 0x00, 0x00, 0x05, 0x06, 0x02, 0x04, 0x04,
    0x01, 0xE3, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
};

constexpr uint8_t kPrefix         = 0xF1;
constexpr uint8_t kKeyCommand     = 0x01;
constexpr uint8_t kRequestCommand = 0x51;
constexpr uint8_t kConfirmCommand = 0xA7;


// =============================================================================
// Helpers
// =============================================================================

// Encrypts block by block, zero-padding the final partial block.
std::vector<uint8_t> encryptBuffer(std::vector<uint8_t> plaintext, const BlockEncryptor& encryptBlock) {
    const size_t remainder = plaintext.size() % kAesBlockSize;
    if (remainder != 0) {
        plaintext.resize(plaintext.size() + (kAesBlockSize - remainder), 0);
    }

    std::vector<uint8_t> ciphertext(plaintext.size());
    for (size_t offset = 0; offset < plaintext.size(); offset += kAesBlockSize) {
        encryptBlock(&plaintext[offset], &ciphertext[offset]);
    }
    return ciphertext;
}


std::vector<uint8_t> withPrefix(uint8_t command, const std::vector<uint8_t>& body) {
    std::vector<uint8_t> frame = {kPrefix, command};
    frame.insert(frame.end(), body.begin(), body.end());
    return frame;
}

}  // namespace


// =============================================================================
// Core logic
// =============================================================================

std::vector<uint8_t> nybbleSwap(std::vector<uint8_t> buffer) {
    const size_t half = buffer.size() / 2;
    for (size_t index = 0; index < half; ++index) {
        const uint8_t first  = buffer[index];
        const uint8_t second = buffer[index + half];

        if (index % 2 == 0) {
            buffer[index]        = static_cast<uint8_t>((second << 4) | (first & 0x0F));
            buffer[index + half] = static_cast<uint8_t>((first >> 4) | (second & 0xF0));
        } else {
            buffer[index]        = static_cast<uint8_t>((second & 0xF0) | (first & 0x0F));
            buffer[index + half] = static_cast<uint8_t>((first & 0xF0) | (second & 0x0F));
        }
    }
    return buffer;
}


UnlockPayloads buildUnlockPayloads(const std::vector<uint8_t>& readRequest, const BlockEncryptor& encryptBlock) {
    UnlockPayloads payloads;

    // Frame 1: plaintext header + encrypted request, scrambled.
    std::vector<uint8_t> headerAndRequest(kKeyFrameHeader.begin(), kKeyFrameHeader.end());
    const std::vector<uint8_t> encryptedRequest = encryptBuffer(readRequest, encryptBlock);
    headerAndRequest.insert(headerAndRequest.end(), encryptedRequest.begin(), encryptedRequest.end());
    payloads.keyFrame = withPrefix(kKeyCommand, nybbleSwap(headerAndRequest));

    // Frame 2: the request zero-padded to two blocks, encrypted, scrambled.
    std::vector<uint8_t> paddedRequest = readRequest;
    paddedRequest.resize(kAesBlockSize * 2, 0);
    payloads.requestFrame = withPrefix(kRequestCommand, nybbleSwap(encryptBuffer(paddedRequest, encryptBlock)));

    // Frame 3: frame 1's body without scrambling.
    payloads.confirmFrame = withPrefix(kConfirmCommand, headerAndRequest);

    return payloads;
}

}  // namespace genmon
