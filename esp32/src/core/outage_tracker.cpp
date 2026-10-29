// =============================================================================
// outage_tracker.cpp - Utility outage detection and voltage statistics
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "outage_tracker.h"


namespace genmon {

namespace {

// =============================================================================
// Constants
// =============================================================================

// Readings above this multiple of nominal are corrupt, not real voltages.
constexpr double kImplausibleVoltageFactor = 2.5;

}  // namespace


// =============================================================================
// OutageTracker
// =============================================================================

OutageEvent OutageTracker::update(const OutageReading& reading, int64_t nowEpoch) {
    const double volts = reading.utilityVolts;
    if (volts < 0.0 || reading.thresholdVolts < 0.0 || reading.pickupVolts < 0.0) {
        return OutageEvent::None;
    }
    if (volts >= reading.nominalLineVolts * kImplausibleVoltageFactor) {
        return OutageEvent::None;
    }
    if (reading.rejectSuspectThresholds &&
        (reading.thresholdVolts >= reading.nominalLineVolts || reading.pickupVolts >= reading.nominalLineVolts)) {
        return OutageEvent::None;
    }

    const double threshold = reading.thresholdVolts > 0.0 ? reading.thresholdVolts : kDefaultThresholdVolts;
    const double pickup    = reading.pickupVolts    > 0.0 ? reading.pickupVolts    : kDefaultPickupVolts;

    updateStatistics(volts, threshold, pickup);

    // The controller's own start delay is not modelled: brief dips below the
    // threshold are reported even if the generator never started.
    if (inOutage_ && volts > pickup) {
        inOutage_   = false;
        lastOutage_ = OutageRecord{outageStart_, nowEpoch - outageStart_};
        return OutageEvent::Ended;
    }
    if (!inOutage_ && volts < threshold) {
        inOutage_    = true;
        outageStart_ = nowEpoch;
        return OutageEvent::Started;
    }
    return OutageEvent::None;
}


void OutageTracker::updateStatistics(double volts, double threshold, double pickup) {
    if (!minVolts_ || !maxVolts_) {
        minVolts_ = volts;
        maxVolts_ = volts;
        return;
    }
    // Readings taken during an outage would swamp the statistics, so only
    // voltages on the "utility is healthy" side of each limit count.
    if (volts > *maxVolts_ && volts > pickup) {
        maxVolts_ = volts;
    }
    if (volts < *minVolts_ && volts > threshold) {
        minVolts_ = volts;
    }
}

}  // namespace genmon
