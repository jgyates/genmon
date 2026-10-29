// =============================================================================
// outage_log.h - Outage history persisted on LittleFS
// =============================================================================
//
// Same line format as genmon's outage.txt ("YYYY-MM-DD HH:MM:SS,H:MM:SS") so a
// history file can be carried over from a Raspberry Pi install by uploading it.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <cstdint>
#include <mutex>
#include <vector>

#include "core/report_builder.h"


namespace genmon {

// =============================================================================
// Types
// =============================================================================

class OutageLog {
public:
    bool begin();

    void append(int64_t startEpoch, int64_t durationSeconds);

    // Newest first, formatted for the outage report.
    std::vector<OutageLogEntry> entries() const;

private:
    void trimFile();

    mutable std::mutex mutex_;
    bool               mounted_ = false;
};

}  // namespace genmon
