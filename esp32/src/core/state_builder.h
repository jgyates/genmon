// =============================================================================
// state_builder.h - Builds GeneratorState and GeneratorLogs from registers
// =============================================================================
//
// All model-specific scaling and register selection lives here, so the rest
// of the firmware can treat every supported controller the same way.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <cstdint>

#include "controller_info.h"
#include "generator_state.h"
#include "monitor_options.h"
#include "register_cache.h"


namespace genmon {

// =============================================================================
// Functions
// =============================================================================

// `statusWord` is the already-filtered value of register 0x0001.
GeneratorState buildState(const RegisterCache&  registers,
                          const ControllerInfo& info,
                          const MonitorOptions& options,
                          uint32_t              statusWord);

GeneratorLogs buildLogs(const RegisterCache& registers, const ControllerInfo& info);

}  // namespace genmon
