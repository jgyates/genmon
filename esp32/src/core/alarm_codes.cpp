// =============================================================================
// alarm_codes.cpp - Evolution alarm code descriptions
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "alarm_codes.h"

#include <algorithm>
#include <iterator>


namespace genmon {

namespace {

// =============================================================================
// Constants
// =============================================================================

// Sorted by code; regenerate with esp32/tools/gen_upstream_data.py.
constexpr AlarmCode kAlarmCodes[] = {
#include "alarm_codes_table.inc"
};

}  // namespace


// =============================================================================
// Core logic
// =============================================================================

const AlarmCode* findAlarmCode(uint16_t code) {
    const AlarmCode* first = std::begin(kAlarmCodes);
    const AlarmCode* last  = std::end(kAlarmCodes);
    const AlarmCode* found = std::lower_bound(first, last, code,
        [](const AlarmCode& entry, uint16_t wanted) { return entry.code < wanted; });

    if (found == last || found->code != code) {
        return nullptr;
    }
    return found;
}

}  // namespace genmon
