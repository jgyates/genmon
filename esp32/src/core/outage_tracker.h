// =============================================================================
// outage_tracker.h - Utility outage detection and voltage statistics
// =============================================================================
//
// Evolution and Nexus controllers watch the utility line themselves and start
// the generator when it drops below the threshold voltage. This tracker
// applies the same thresholds to the reported utility voltage so the monitor
// can report outages, their duration, and the min/max voltage seen.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <cstdint>
#include <optional>


namespace genmon {

// =============================================================================
// Constants
// =============================================================================

constexpr double kDefaultThresholdVolts = 143.0;
constexpr double kDefaultPickupVolts    = 190.0;


// =============================================================================
// Types
// =============================================================================

enum class OutageEvent {
    None,
    Started,
    Ended,
};

struct OutageRecord {
    int64_t startEpoch      = 0;
    int64_t durationSeconds = 0;
};

struct OutageReading {
    double utilityVolts     = 0.0;
    double thresholdVolts   = 0.0;   // 0 selects kDefaultThresholdVolts
    double pickupVolts      = 0.0;   // 0 selects kDefaultPickupVolts
    double nominalLineVolts = 240.0;
    bool   rejectSuspectThresholds = false;   // Evolution 2.0 sometimes reports nonsense
};

class OutageTracker {
public:
    OutageEvent update(const OutageReading& reading, int64_t nowEpoch);

    bool                        inOutage() const       { return inOutage_; }
    int64_t                     outageStart() const    { return outageStart_; }
    std::optional<OutageRecord> lastOutage() const     { return lastOutage_; }
    std::optional<double>       minUtilityVolts() const { return minVolts_; }
    std::optional<double>       maxUtilityVolts() const { return maxVolts_; }

private:
    void updateStatistics(double volts, double threshold, double pickup);

    bool                        inOutage_    = false;
    int64_t                     outageStart_ = 0;
    std::optional<OutageRecord> lastOutage_;
    std::optional<double>       minVolts_;
    std::optional<double>       maxVolts_;
};

}  // namespace genmon
