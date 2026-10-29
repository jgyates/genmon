// =============================================================================
// test_protocol - Modbus framing and the Evolution 2.0 unlock sequence
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include <unity.h>

#include "evo2_unlock.h"
#include "modbus_frame.h"

using namespace genmon;


// =============================================================================
// Fixtures
// =============================================================================

void setUp() {}
void tearDown() {}


// Stand-in for AES so payload layout can be checked byte for byte.
void identityCipher(const uint8_t* input, uint8_t* output) {
    for (size_t index = 0; index < kAesBlockSize; ++index) {
        output[index] = input[index];
    }
}


std::vector<uint8_t> withCrc(std::vector<uint8_t> frame) {
    appendCrc(frame);
    return frame;
}


// =============================================================================
// Modbus framing
// =============================================================================

void test_crc_matches_reference_vector() {
    const uint8_t frame[] = {0x01, 0x03, 0x00, 0x00, 0x00, 0x01};
    TEST_ASSERT_EQUAL_HEX16(0x0A84, modbusCrc(frame, sizeof(frame)));
}


void test_read_request_layout() {
    const std::vector<uint8_t> request = buildReadRequest(0x9D, 0x0001, 2);
    TEST_ASSERT_EQUAL(8, request.size());
    TEST_ASSERT_EQUAL_HEX8(0x9D, request[0]);
    TEST_ASSERT_EQUAL_HEX8(0x03, request[1]);
    TEST_ASSERT_EQUAL_HEX8(0x01, request[3]);
    TEST_ASSERT_EQUAL_HEX8(0x02, request[5]);
    TEST_ASSERT_EQUAL_HEX16(modbusCrc(request.data(), 6), request[6] | (request[7] << 8));
}


void test_write_request_layout() {
    const std::vector<uint8_t> request = buildWriteRequest(0x9D, 0x0003, {0x00, 0x01});
    const uint8_t expected[] = {0x9D, 0x10, 0x00, 0x03, 0x00, 0x01, 0x02, 0x00, 0x01};
    TEST_ASSERT_EQUAL(11, request.size());
    TEST_ASSERT_EQUAL_HEX8_ARRAY(expected, request.data(), sizeof(expected));
}


void test_read_response_parses_payload() {
    const std::vector<uint8_t> frame = withCrc({0x9D, 0x03, 0x04, 0x00, 0x03, 0x00, 0x06});
    ParsedResponse response;
    TEST_ASSERT_TRUE(parseResponse(frame, 0x9D, kFunctionReadHolding, response) == FrameStatus::Complete);
    TEST_ASSERT_FALSE(response.isException);
    TEST_ASSERT_EQUAL(4, response.payload.size());
    TEST_ASSERT_EQUAL_HEX8(0x06, response.payload[3]);
}


void test_partial_response_is_incomplete() {
    const std::vector<uint8_t> frame = withCrc({0x9D, 0x03, 0x02, 0x12, 0x34});
    const std::vector<uint8_t> partial(frame.begin(), frame.end() - 1);
    ParsedResponse response;
    TEST_ASSERT_TRUE(parseResponse(partial, 0x9D, kFunctionReadHolding, response) == FrameStatus::Incomplete);
}


void test_corrupt_crc_is_invalid() {
    std::vector<uint8_t> frame = withCrc({0x9D, 0x03, 0x02, 0x12, 0x34});
    frame.back() ^= 0xFF;
    ParsedResponse response;
    TEST_ASSERT_TRUE(parseResponse(frame, 0x9D, kFunctionReadHolding, response) == FrameStatus::Invalid);
}


void test_exception_response_reports_code() {
    const std::vector<uint8_t> frame = withCrc({0x9D, 0x83, 0x05});
    ParsedResponse response;
    TEST_ASSERT_TRUE(parseResponse(frame, 0x9D, kFunctionReadHolding, response) == FrameStatus::Complete);
    TEST_ASSERT_TRUE(response.isException);
    TEST_ASSERT_EQUAL_HEX8(kExceptionAcknowledge, response.exceptionCode);
}


void test_wrong_address_is_invalid() {
    const std::vector<uint8_t> frame = withCrc({0x01, 0x03, 0x02, 0x12, 0x34});
    ParsedResponse response;
    TEST_ASSERT_TRUE(parseResponse(frame, 0x9D, kFunctionReadHolding, response) == FrameStatus::Invalid);
}


// =============================================================================
// Evolution 2.0 unlock
// =============================================================================

void test_nybble_swap_even_and_odd_positions() {
    std::vector<uint8_t> buffer(32, 0);
    buffer[0]  = 0x12;
    buffer[16] = 0x34;
    buffer[1]  = 0x56;
    buffer[17] = 0x78;

    const std::vector<uint8_t> swapped = nybbleSwap(buffer);
    TEST_ASSERT_EQUAL_HEX8(0x42, swapped[0]);
    TEST_ASSERT_EQUAL_HEX8(0x31, swapped[16]);
    TEST_ASSERT_EQUAL_HEX8(0x76, swapped[1]);
    TEST_ASSERT_EQUAL_HEX8(0x58, swapped[17]);
}


void test_unlock_payloads_have_expected_shape() {
    const std::vector<uint8_t> request  = buildReadRequest(0x9D, 0x0001, 2);
    const UnlockPayloads       payloads = buildUnlockPayloads(request, identityCipher);

    TEST_ASSERT_EQUAL(34, payloads.keyFrame.size());
    TEST_ASSERT_EQUAL(34, payloads.requestFrame.size());
    TEST_ASSERT_EQUAL(34, payloads.confirmFrame.size());
    TEST_ASSERT_EQUAL_HEX8(0xF1, payloads.keyFrame[0]);
    TEST_ASSERT_EQUAL_HEX8(0x01, payloads.keyFrame[1]);
    TEST_ASSERT_EQUAL_HEX8(0x51, payloads.requestFrame[1]);
    TEST_ASSERT_EQUAL_HEX8(0xA7, payloads.confirmFrame[1]);

    // The confirm frame carries the plaintext header, then the (here
    // unencrypted) request, without nybble scrambling.
    TEST_ASSERT_EQUAL_HEX8(0xE3, payloads.confirmFrame[2 + 9]);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(request.data(), &payloads.confirmFrame[2 + 16], request.size());
}


// =============================================================================
// Runner
// =============================================================================

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_crc_matches_reference_vector);
    RUN_TEST(test_read_request_layout);
    RUN_TEST(test_write_request_layout);
    RUN_TEST(test_read_response_parses_payload);
    RUN_TEST(test_partial_response_is_incomplete);
    RUN_TEST(test_corrupt_crc_is_invalid);
    RUN_TEST(test_exception_response_reports_code);
    RUN_TEST(test_wrong_address_is_invalid);
    RUN_TEST(test_nybble_swap_even_and_odd_positions);
    RUN_TEST(test_unlock_payloads_have_expected_shape);
    return UNITY_END();
}
