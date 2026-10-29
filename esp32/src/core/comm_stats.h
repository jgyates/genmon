// =============================================================================
// comm_stats.h - Modbus link counters
// =============================================================================
//
// Same counters genmon reports under "Monitor/Communication Stats", so
// existing dashboards that chart them keep working.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <cstdint>


namespace genmon {

// =============================================================================
// Types
// =============================================================================

struct CommStats {
    uint32_t txPackets          = 0;
    uint32_t rxPackets          = 0;
    uint32_t crcErrors          = 0;
    uint32_t timeouts           = 0;
    uint32_t exceptions         = 0;
    uint32_t ackExceptions      = 0;     // drives the Evolution 2.0 unlock
    uint32_t validationErrors   = 0;
    uint32_t unexpectedData     = 0;
    uint32_t discardedBytes     = 0;
    uint32_t restarts           = 0;
    double   transactionSeconds = 0.0;   // summed over successful transactions
    double   uptimeSeconds      = 0.0;   // since counters were reset
    uint32_t baudRate           = 0;
};

}  // namespace genmon
