// =============================================================================
// outage_log.cpp - Outage history persisted on LittleFS
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "outage_log.h"

#include <LittleFS.h>

#include <ctime>
#include <string>


namespace genmon {

namespace {

// =============================================================================
// Constants
// =============================================================================

constexpr const char* kPath           = "/outage.txt";
constexpr size_t      kMaxEntries     = 50;    // genmon's default outagelog_max_entries
constexpr size_t      kTrimThreshold  = 100;   // rewrite the file once it doubles


// =============================================================================
// Helpers
// =============================================================================

std::string formatEpoch(int64_t epoch, const char* pattern) {
    const std::time_t seconds = static_cast<std::time_t>(epoch);
    std::tm           local{};
    localtime_r(&seconds, &local);
    char buffer[32];
    std::strftime(buffer, sizeof(buffer), pattern, &local);
    return buffer;
}


// "2026-10-29 14:05:00" -> "10-29-2026 14:05:00", the report's display order.
std::string displayDate(const std::string& stored) {
    if (stored.size() < 19 || stored[4] != '-' || stored[7] != '-') {
        return stored;
    }
    return stored.substr(5, 2) + "-" + stored.substr(8, 2) + "-" + stored.substr(0, 4) + stored.substr(10);
}


std::vector<std::string> readLines() {
    std::vector<std::string> lines;
    File file = LittleFS.open(kPath, "r");
    if (!file) {
        return lines;
    }
    while (file.available()) {
        String line = file.readStringUntil('\n');
        line.trim();
        if (line.length() && line[0] != '#') {
            lines.push_back(line.c_str());
        }
    }
    file.close();
    return lines;
}

}  // namespace


// =============================================================================
// OutageLog
// =============================================================================

bool OutageLog::begin() {
    std::lock_guard<std::mutex> lock(mutex_);
    mounted_ = LittleFS.begin(true);   // formats an empty partition on first boot
    return mounted_;
}


void OutageLog::append(int64_t startEpoch, int64_t durationSeconds) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!mounted_) {
        return;
    }
    File file = LittleFS.open(kPath, "a");
    if (!file) {
        return;
    }
    const std::string line = formatEpoch(startEpoch, "%Y-%m-%d %H:%M:%S") + "," + formatDuration(durationSeconds);
    file.println(line.c_str());
    file.close();
    trimFile();
}


std::vector<OutageLogEntry> OutageLog::entries() const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<OutageLogEntry> entries;
    if (!mounted_) {
        return entries;
    }

    const std::vector<std::string> lines = readLines();
    for (auto line = lines.rbegin(); line != lines.rend() && entries.size() < kMaxEntries; ++line) {
        const size_t comma = line->find(',');
        if (comma == std::string::npos) {
            continue;
        }
        entries.push_back({displayDate(line->substr(0, comma)), line->substr(comma + 1)});
    }
    return entries;
}


void OutageLog::trimFile() {
    const std::vector<std::string> lines = readLines();
    if (lines.size() <= kTrimThreshold) {
        return;
    }
    File file = LittleFS.open(kPath, "w");
    if (!file) {
        return;
    }
    for (size_t index = lines.size() - kMaxEntries; index < lines.size(); ++index) {
        file.println(lines[index].c_str());
    }
    file.close();
}

}  // namespace genmon
