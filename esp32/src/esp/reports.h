// =============================================================================
// reports.h - genmon JSON reports for the current generator snapshot
// =============================================================================
//
// Glue between GeneratorService snapshots and core/report_builder: fills in
// the monitor facts only the ESP32 knows (Wi-Fi, heap, clock) and exposes
// the reports by their genmon command names (status_json, maint_num_json...).

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <ArduinoJson.h>

#include <string>

#include "generator_service.h"
#include "settings.h"


namespace genmon {

// =============================================================================
// Constants
// =============================================================================

extern const char* const kFirmwareVersion;


// =============================================================================
// Functions
// =============================================================================

// Builds the report genmon serves for `name` (e.g. "status_num_json").
// Returns false for an unknown name.
bool buildNamedReport(const std::string&      name,
                      const GeneratorService& service,
                      const Settings&         settings,
                      JsonDocument&           out);

// {"Status": [...], "Maintenance": [...], "Outage": [...], "Monitor": [...]},
// the merged tree the Home Assistant and genmqtt add-ons walk.
void buildMergedReports(const GeneratorService& service,
                        const Settings&         settings,
                        bool                    numeric,
                        JsonDocument&           out);

void buildStartInfoReport(const GeneratorService& service, const Settings& settings, JsonDocument& out);

}  // namespace genmon
