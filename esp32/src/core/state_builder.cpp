// =============================================================================
// state_builder.cpp - Builds GeneratorState and GeneratorLogs from registers
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "state_builder.h"

#include <cmath>
#include <cstdio>
#include <iterator>

#include "alarm_codes.h"
#include "log_parser.h"
#include "maintenance_decoder.h"
#include "register_map.h"
#include "status_decoder.h"


namespace genmon {

namespace {

// =============================================================================
// Constants
// =============================================================================

constexpr double  kTenths                     = 10.0;
constexpr double  kDefaultPickupVolts         = 190.0;
constexpr double  kHallDividerNewFirmware     = 1000.0;   // mA on firmware >= V1.43
constexpr double  kHallDividerOldFirmware     = 100.0;
constexpr uint8_t kHallMilliampFirmware       = 143;
constexpr double  kAirCooledTotalDivider      = 20.0;     // (CT1 + CT2) / 2, CTs read x10
constexpr double  kAirCooledLegDivider        = 10.0;
constexpr double  kCurrentClampMinimumVolts   = 100.0;
constexpr double  kCurrentClampHeadroomAmps   = 2.0;
constexpr double  kWattsPerKilowatt           = 1000.0;
constexpr double  kMaxRotorPoles              = 4.0;

struct DigitalBit {
    uint16_t    mask;
    bool        activeHigh;
    const char* label;
};

constexpr DigitalBit kLiquidCooledOutputs[] = {
    {0x01, true, "Transfer Switch Activated"},
    {0x02, true, "Fuel Enrichment On"},
    {0x04, true, "Starter On"},
    {0x08, true, "Fuel Relay On"},
    {0x10, true, "Battery Charger On"},
    {0x20, true, "Alarm Active"},
    {0x40, true, "Bosch Governor On"},
    {0x80, true, "Air/Fuel Relay On"},
};


// =============================================================================
// Helpers
// =============================================================================

std::optional<double> scaled(const RegisterCache& registers, uint16_t address, double divider = 1.0) {
    const auto value = registers.u16(address);
    if (!value) {
        return std::nullopt;
    }
    return *value / divider;
}


std::string withUnit(const RegisterCache& registers, uint16_t address, const char* unit) {
    const auto value = registers.u16(address);
    if (!value) {
        return "";
    }
    return std::to_string(*value) + " " + unit;
}


std::string joinActiveBits(uint16_t value, const DigitalBit* bits, size_t count) {
    std::string text;
    for (size_t index = 0; index < count; ++index) {
        const bool set = (value & bits[index].mask) != 0;
        if (set == bits[index].activeHigh) {
            text += text.empty() ? "" : ", ";
            text += bits[index].label;
        }
    }
    return text;
}


std::string liquidCooledSensors(uint16_t inputs, const std::string& fuelType) {
    const bool diesel = fuelType.find("iesel") != std::string::npos;

    // The ruptured basin input only exists on diesel units, and the low
    // fuel input has inverted polarity on gaseous-fuel units.
    const DigitalBit bits[] = {
        {0x0001, true,    "Manual Button"},
        {0x0002, true,    "Auto Button"},
        {0x0004, true,    "Off Button"},
        {0x0008, true,    "2 Wire Start"},
        {0x0010, true,    "Wiring Error"},
        {0x0020, true,    diesel ? "Ruptured Basin" : ""},
        {0x0040, false,   "E-Stop Activated"},
        {0x0080, true,    "Oil below 8 psi"},
        {0x0100, true,    "Low Coolant"},
        {0x0200, diesel,  diesel ? "Fuel Pressure / Level Low" : "Fuel below 5 inch"},
    };

    std::string text;
    for (const DigitalBit& bit : bits) {
        const bool set = (inputs & bit.mask) != 0;
        if (bit.label[0] != '\0' && set == bit.activeHigh) {
            text += text.empty() ? "" : ", ";
            text += bit.label;
        }
    }
    return text;
}


std::string lastAlarmDescription(const RegisterCache& registers) {
    const auto code = registers.u16(reg::kLastAlarmCode);
    if (!code || *code == 0) {
        return "";
    }
    const AlarmCode* entry = findAlarmCode(*code);
    char buffer[96];
    std::snprintf(buffer, sizeof(buffer), "%04d: %s", *code, entry ? entry->name : "Unknown");
    return buffer;
}


double frequencyDivider(const ControllerInfo& info, const MonitorOptions& options) {
    if ((info.evolution && info.liquidCooled) || info.synergy) {
        return kTenths;
    }
    if (!info.evolution && info.liquidCooled && options.nexusDoubleFrequency) {
        return 0.5;
    }
    return 1.0;
}


bool powerMeterSupported(const ControllerInfo& info, const MonitorOptions& options) {
    return info.evolution && !info.powerPact && options.ratedKw > 0.0f;
}


// Keeps a mis-calibrated current transformer from reporting impossible values.
double clampCurrent(double amps, std::optional<double> outputVolts, const MonitorOptions& options) {
    if (!outputVolts || *outputVolts <= kCurrentClampMinimumVolts) {
        return amps;
    }
    const double ratedAmps = options.ratedKw * kWattsPerKilowatt / options.nominalLineVolts;
    if (amps < 0.0) {
        return 0.0;
    }
    if (amps > ratedAmps + kCurrentClampHeadroomAmps) {
        return ratedAmps;
    }
    return amps;
}


double roundTo(double value, int places) {
    const double factor = std::pow(10.0, places);
    return std::round(value * factor) / factor;
}


void fillCurrentAndPower(GeneratorState&       state,
                         const RegisterCache&  registers,
                         const ControllerInfo& info,
                         const MonitorOptions& options) {
    if (!powerMeterSupported(info, options)) {
        return;
    }
    if (!state.running) {
        state.outputAmps = 0.0;
        state.outputKw   = 0.0;
        return;
    }

    if (info.liquidCooled) {
        const auto hall = registers.u16(reg::kHallCurrent);
        if (!hall) {
            return;
        }
        double divider = options.currentDivider;
        if (divider <= 0.0f) {
            const auto firmware = firmwareVersionByte(registers);
            divider = (firmware && *firmware >= kHallMilliampFirmware) ? kHallDividerNewFirmware
                                                                       : kHallDividerOldFirmware;
        }
        state.outputAmps = std::fabs(*hall / divider + options.currentOffset);
    } else {
        const auto leg1 = registers.u16(reg::kCurrentLeg1);
        const auto leg2 = registers.u16(reg::kCurrentLeg2);
        if (!leg1 || !leg2) {
            return;
        }
        const bool   custom      = options.currentDivider > 0.0f;
        const double totalDiv    = custom ? options.currentDivider : kAirCooledTotalDivider;
        const double legDiv      = custom ? options.currentDivider : kAirCooledLegDivider;
        state.outputAmps     = (*leg1 + *leg2 + options.currentOffset) / totalDiv;
        state.outputAmpsLeg1 = roundTo(clampCurrent((*leg1 + options.currentOffset) / legDiv, state.outputVolts, options), 2);
        state.outputAmpsLeg2 = roundTo(clampCurrent((*leg2 + options.currentOffset) / legDiv, state.outputVolts, options), 2);
    }

    state.outputAmps = roundTo(clampCurrent(*state.outputAmps, state.outputVolts, options), 2);
    if (state.outputVolts) {
        state.outputKw = roundTo(*state.outputVolts * *state.outputAmps / kWattsPerKilowatt, 3);
    }
}


void fillEngine(GeneratorState&       state,
                const RegisterCache&  registers,
                const ControllerInfo& info,
                const MonitorOptions& options) {
    state.batteryVolts = scaled(registers, reg::kBatteryVolts, kTenths);
    state.rpm          = scaled(registers, reg::kRpm);
    state.frequencyHz  = scaled(registers, reg::kFrequency, frequencyDivider(info, options));

    if (info.evolution45L && !state.running) {
        state.rpm = 0.0;
    }
    if (info.evolution && !info.powerPact && !info.synergy) {
        state.chargerCurrentMa = scaled(registers, reg::kChargerCurrent);
    }
    if (!info.preNexus && !info.powerPact) {
        state.outputVolts = scaled(registers, reg::kOutputVolts);
    }

    if (info.evolution && info.liquidCooled) {
        const auto outputs = registers.u16(reg::kDigitalOutputs);
        const auto inputs  = registers.u16(reg::kDigitalInputs);
        if (outputs) {
            state.activeRelays   = joinActiveBits(*outputs, kLiquidCooledOutputs, std::size(kLiquidCooledOutputs));
            state.transferSwitch = (*outputs & 0x01) ? "Generator" : "Utility";
        }
        if (inputs) {
            state.activeSensors = liquidCooledSensors(*inputs, options.fuelType);
        }
    }

    fillCurrentAndPower(state, registers, info, options);

    // poles = (2 * 60 * Hz) / RPM; more than 4 means the inputs are noise.
    if (state.rpm && state.frequencyHz && *state.rpm > 0.0) {
        const double poles = std::round((2.0 * 60.0 * *state.frequencyHz) / *state.rpm);
        state.rotorPoles   = poles > kMaxRotorPoles ? 0.0 : poles;
    } else {
        state.rotorPoles = 0.0;
    }
}


void addSetting(GeneratorState&      state,
                const RegisterCache& registers,
                const char*          label,
                uint16_t             address,
                const char*          unit = "") {
    const auto value = registers.u16(address);
    if (value) {
        state.controllerSettings.push_back({label, static_cast<double>(*value), true, unit});
    }
}


void fillControllerSettings(GeneratorState&       state,
                            const RegisterCache&  registers,
                            const ControllerInfo& info,
                            const MonitorOptions& options) {
    if (info.evolution && !info.liquidCooled) {
        addSetting(state, registers, "Calibrate Current 1", 0x05F6);
        addSetting(state, registers, "Calibrate Current 2", 0x05F7);
    }
    if (!info.preNexus) {
        addSetting(state, registers, "Calibrate Volts", 0x0208);
    }
    state.controllerSettings.push_back({"Nominal Line Voltage", static_cast<double>(options.nominalLineVolts), true,  "V",  true});
    state.controllerSettings.push_back({"Rated Max Power",      options.ratedKw,                               false, "kW", true});

    if (info.liquidCooled) {
        addSetting(state, registers, "Param Group",  0x020A);
        addSetting(state, registers, "Voltage Code", 0x020B);
    }
    if (info.evolution && (info.liquidCooled || info.evolution2)) {
        addSetting(state, registers, "Time Since Activation", reg::kHoursSinceActivated, "h");
    }
    if (info.evolution && info.liquidCooled) {
        addSetting(state, registers, "Volts Per Hertz",  0x020E);
        addSetting(state, registers, "Gain",             0x0235);
        addSetting(state, registers, "Target Frequency", 0x005A, "Hz");
        addSetting(state, registers, "Target Voltage",   0x0059, "V");
    }
}


void fillLine(GeneratorState& state, const RegisterCache& registers, const ControllerInfo& info) {
    state.utilityVolts   = scaled(registers, reg::kUtilityVolts);
    state.thresholdVolts = scaled(registers, reg::kThresholdVolts);

    if (info.evolution && (info.liquidCooled || info.evolution2)) {
        state.pickupVolts = scaled(registers, reg::kPickupVolts);
    } else {
        state.pickupVolts = kDefaultPickupVolts;
    }
    if (info.evolution && info.liquidCooled) {
        state.setOutputVolts = scaled(registers, reg::kSetOutputVolts);
    }
}


void fillMaintenance(GeneratorState&       state,
                     const RegisterCache&  registers,
                     const ControllerInfo& info,
                     const MonitorOptions& options) {
    state.serialNumber    = serialNumber(registers, options);
    state.firmwareVersion = formatVersion(firmwareVersionByte(registers));
    state.hardwareVersion = formatVersion(hardwareVersionByte(registers));
    state.runHours        = runHours(registers, info, options);
    state.exercise        = exerciseSchedule(registers, info);
    state.service         = serviceSchedule(registers, info);

    const auto clock = generatorClock(registers);
    state.generatorTime = clock ? formatClock(*clock) : "";

    if (info.evolution) {
        state.lastAlarmCode = lastAlarmDescription(registers);
        state.startupDelay  = withUnit(registers, info.liquidCooled ? reg::kStartupDelayLiquid
                                                                    : reg::kStartupDelayAir, "s");
    }
    if (info.evolution && info.liquidCooled) {
        state.warmupDelay      = withUnit(registers, reg::kWarmupDelay, "s");
        state.exerciseDuration = withUnit(registers, reg::kExerciseDuration, "min");
    }
    if (info.evolution && (info.liquidCooled || info.evolution2)) {
        state.hoursSinceActivation = scaled(registers, reg::kHoursSinceActivated);
    }
    if (info.evolution2) {
        state.ambientTemperatureF = scaled(registers, reg::kAmbientTemperature);
    }
}


void fillCapabilities(GeneratorState& state, const ControllerInfo& info) {
    const bool evolutionLiquid = info.evolution && info.liquidCooled;

    state.canRemoteStart   = !info.powerZone200;
    state.canSetButtons    = evolutionLiquid && !info.evolution45L;
    state.canResetAlarm    = evolutionLiquid || info.evolution2;
    state.canSetQuietMode  = info.evolution && (info.liquidCooled || info.evolution2);
    state.enhancedExercise = info.enhancedExercise;
    state.showsPickupVolts = info.evolution && (info.liquidCooled || info.evolution2);
    state.reportsQuietToUi = evolutionLiquid;
}


void appendLog(std::vector<std::string>& out,
               const RegisterCache&      registers,
               const ControllerInfo&     info,
               uint8_t                   firmware,
               LogKind                   kind,
               uint16_t                  start,
               uint8_t                   stride) {
    for (uint16_t slot = 0; slot < kLogDepth; ++slot) {
        const auto entry = registers.bytes(static_cast<uint16_t>(start + slot * stride));
        if (!entry) {
            break;
        }
        const std::string line = parseLogEntry(*entry, kind, info, firmware);
        if (line.empty()) {
            break;
        }
        out.push_back(line);
    }
}

}  // namespace


// =============================================================================
// Core logic
// =============================================================================

GeneratorState buildState(const RegisterCache&  registers,
                          const ControllerInfo& info,
                          const MonitorOptions& options,
                          uint32_t              statusWord) {
    GeneratorState state;
    state.valid       = true;
    state.statusWord  = statusWord;
    state.controller  = controllerFamilyName(info);
    state.productName = productCodeName(info.productCode);

    state.alarm       = alarmText(statusWord, registers, info);
    state.inAlarm     = !state.alarm.empty();
    state.switchState = switchState(statusWord);
    state.engineState = engineState(statusWord, state.inAlarm);
    state.running     = engineIsRunning(state.engineState);
    state.serviceDue  = serviceDue(statusWord, registers, info);
    state.baseStatus  = baseStatus(state.inAlarm, serviceAlarmActive(statusWord), state.serviceDue,
                                   state.engineState, state.switchState);
    state.ledState    = ledState(registers, info);

    state.powerMeter  = powerMeterSupported(info, options);

    fillEngine(state, registers, info, options);
    fillLine(state, registers, info);
    fillMaintenance(state, registers, info, options);
    fillControllerSettings(state, registers, info, options);
    fillCapabilities(state, info);
    return state;
}


GeneratorLogs buildLogs(const RegisterCache& registers, const ControllerInfo& info) {
    GeneratorLogs logs;
    const uint8_t firmware = firmwareVersionByte(registers).value_or(0);

    if (info.evolution) {
        appendLog(logs.alarm,   registers, info, firmware, LogKind::EvolutionAlarm,
                  kEvolutionAlarmLogStart, kEvolutionAlarmLogStride);
        appendLog(logs.service, registers, info, firmware, LogKind::EvolutionService,
                  kServiceLogStart, kServiceLogStride);
    } else {
        appendLog(logs.alarm,   registers, info, firmware, LogKind::NexusAlarm,
                  kNexusAlarmLogStart, kNexusAlarmLogStride);
    }
    appendLog(logs.run, registers, info, firmware, LogKind::Run, kRunLogStart, kRunLogStride);
    return logs;
}

}  // namespace genmon
