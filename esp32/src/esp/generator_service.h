// =============================================================================
// generator_service.h - Polls the controller and owns the decoded state
// =============================================================================
//
// Runs one FreeRTOS task that is the only user of the serial link: it polls
// registers the way genmon's MasterEmulation() does, rebuilds the decoded
// state, tracks outages, records events, and executes queued commands
// between polls. Everything else reads thread-safe snapshots.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <cstdint>
#include <deque>
#include <mutex>
#include <string>
#include <vector>

#include "core/command.h"
#include "core/comm_stats.h"
#include "core/controller_info.h"
#include "core/generator_state.h"
#include "core/monitor_options.h"
#include "core/outage_tracker.h"
#include "core/register_cache.h"
#include "core/report_builder.h"
#include "core/status_decoder.h"
#include "modbus_port.h"
#include "outage_log.h"
#include "settings.h"


namespace genmon {

// =============================================================================
// Types
// =============================================================================

struct GeneratorSnapshot {
    bool           initialized  = false;
    bool           commsActive  = false;
    ControllerInfo info;
    GeneratorState state;
    GeneratorLogs  logs;
    OutageView     outage;
    CommStats      comm;
    uint32_t       revision     = 0;   // increments whenever state is rebuilt
};

struct EventRecord {
    int64_t     epoch;
    std::string text;
};


class GeneratorService {
public:
    void begin(const Settings& settings);

    GeneratorSnapshot        snapshot() const;
    RegisterSnapshot         registers() const;
    std::vector<EventRecord> recentEvents() const;

    // Validates and queues a genmon command string; returns the message to
    // show the caller ("Command sent" or why it was rejected).
    std::string submitCommand(const std::string& text);

    // genmon's "Monitor Health" text.
    std::string health() const;

private:
    static void taskEntry(void* self);
    void        run();

    void initialize();
    void pollCycle();
    void readSpan(uint16_t start, uint8_t words);
    void readLogs();
    void rebuildState();
    void detectChanges(const GeneratorState& previous, const GeneratorState& current);
    void updateOutage(const GeneratorState& state);
    void executePendingCommands();
    void syncGeneratorTimeIfDue();
    void recordEvent(const std::string& text);

    Settings       settings_;
    MonitorOptions options_;
    ModbusPort     port_;
    RegisterCache  registers_;
    StatusFilter   statusFilter_;
    OutageTracker  outageTracker_;
    OutageLog      outageLog_;

    mutable std::mutex         mutex_;   // guards everything below
    GeneratorSnapshot          snapshot_;
    std::deque<RegisterWrite>  pendingWrites_;
    std::deque<EventRecord>    events_;

    uint32_t lastLogReadMs_     = 0;
    uint32_t lastTimeSyncMs_    = 0;
    bool     logsDirty_         = true;
    bool     wasCommsActive_    = false;
};

}  // namespace genmon
