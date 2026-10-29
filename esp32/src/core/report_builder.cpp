// =============================================================================
// report_builder.cpp - genmon-compatible JSON reports
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "report_builder.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <ctime>


namespace genmon {

namespace {

// =============================================================================
// Constants
// =============================================================================

constexpr int64_t kSecondsPerDay  = 86400;
constexpr int     kTwoDecimals    = 100;


// =============================================================================
// Helpers
// =============================================================================

std::string formatNumber(double value, bool integer, const std::string& unit) {
    char buffer[48];
    if (integer) {
        std::snprintf(buffer, sizeof(buffer), "%lld %s", static_cast<long long>(std::llround(value)), unit.c_str());
    } else {
        std::snprintf(buffer, sizeof(buffer), "%.2f %s", value, unit.c_str());
    }
    return buffer;
}


// genmon's ValueOut(): a "<value> <unit>" string, or a {unit, type, value}
// object when numeric JSON was requested.
void addValue(JsonArray list, const char* key, double value, bool integer, const std::string& unit, bool numeric) {
    JsonObject item = list.add<JsonObject>();
    if (!numeric) {
        item[key] = formatNumber(value, integer, unit);
        return;
    }
    JsonObject entry = item[key].to<JsonObject>();
    entry["unit"] = unit;
    entry["type"] = integer ? "int" : "float";
    if (integer) {
        entry["value"] = static_cast<long long>(std::llround(value));
    } else {
        entry["value"] = std::round(value * kTwoDecimals) / kTwoDecimals;
    }
}


void addOptional(JsonArray list, const char* key, const std::optional<double>& value,
                 bool integer, const char* unit, bool numeric) {
    if (value) {
        addValue(list, key, *value, integer, unit, numeric);
    }
}


void addText(JsonArray list, const char* key, const std::string& text) {
    JsonObject item = list.add<JsonObject>();
    item[key] = text;
}


// "30 s" style strings become numeric objects in numeric mode (UnitsOut()).
void addUnitsText(JsonArray list, const char* key, const std::string& text, bool numeric) {
    if (text.empty()) {
        return;
    }
    const size_t space = text.find(' ');
    if (!numeric || space == std::string::npos) {
        addText(list, key, text);
        return;
    }
    addValue(list, key, std::atof(text.substr(0, space).c_str()), true, text.substr(space + 1), numeric);
}


JsonArray addSection(JsonArray list, const char* key) {
    JsonObject item = list.add<JsonObject>();
    return item[key].to<JsonArray>();
}


std::string formatLocalTime(int64_t epoch, const char* pattern) {
    const std::time_t seconds = static_cast<std::time_t>(epoch);
    const std::tm*    local   = std::localtime(&seconds);
    if (!local) {
        return "";
    }
    char buffer[40];
    std::strftime(buffer, sizeof(buffer), pattern, local);
    return buffer;
}


bool isEvolutionLiquid(const ControllerInfo& info) {
    return info.evolution && info.liquidCooled;
}


void addEngineSection(JsonArray engine, const GeneratorState& state, const ControllerInfo& info, bool numeric) {
    addText(engine, "Switch State", state.switchState);
    addText(engine, "Engine State", state.engineState);
    if (info.evolution2 || info.powerPact) {
        addText(engine, "Generator State", state.ledState);
    }
    if (isEvolutionLiquid(info)) {
        addText(engine, "Active Relays",  state.activeRelays);
        addText(engine, "Active Sensors", state.activeSensors);
    }
    if (state.inAlarm) {
        addText(engine, "System In Alarm", state.alarm);
    }

    addOptional(engine, "Battery Voltage",         state.batteryVolts,     false, "V",  numeric);
    addOptional(engine, "Battery Charger Current", state.chargerCurrentMa, true,  "mA", numeric);
    addOptional(engine, "RPM",                     state.rpm,              true,  "",   numeric);
    addOptional(engine, "Frequency",               state.frequencyHz,      false, "Hz", numeric);
    addOptional(engine, "Output Voltage",          state.outputVolts,      true,  "V",  numeric);

    if (state.powerMeter) {
        addOptional(engine, "Output Current", state.outputAmps,     false, "A", numeric);
        addOptional(engine, "Current L1",     state.outputAmpsLeg1, false, "A", numeric);
        addOptional(engine, "Current L2",     state.outputAmpsLeg2, false, "A", numeric);
        addOptional(engine, "Output Power (Single Phase)", state.outputKw, false, "kW", numeric);
    }
    addOptional(engine, "Active Rotor Poles (Calculated)", state.rotorPoles, true, "", numeric);
}


void addLineSection(JsonArray line, const GeneratorState& state, const OutageView& outage,
                    const ControllerInfo& info, bool numeric) {
    if (isEvolutionLiquid(info)) {
        addText(line, "Transfer Switch State", state.transferSwitch);
    }
    addOptional(line, "Utility Voltage",           state.utilityVolts,                       true, "V", numeric);
    addValue   (line, "Utility Max Voltage",       outage.maxUtilityVolts.value_or(0.0),     true, "V", numeric);
    addValue   (line, "Utility Min Voltage",       outage.minUtilityVolts.value_or(0.0),     true, "V", numeric);
    addOptional(line, "Utility Threshold Voltage", state.thresholdVolts,                     true, "V", numeric);
    if (isEvolutionLiquid(info)) {
        addOptional(line, "Utility Pickup Voltage", state.pickupVolts,    true, "V", numeric);
        addOptional(line, "Set Output Voltage",     state.setOutputVolts, true, "V", numeric);
    }
}


std::string firstOrEmpty(const std::vector<std::string>& entries) {
    return entries.empty() ? "" : entries.front();
}

}  // namespace


// =============================================================================
// Reports
// =============================================================================

void buildStatusReport(JsonObject            root,
                       const GeneratorState& state,
                       const GeneratorLogs&  logs,
                       const OutageView&     outage,
                       const ControllerInfo& info,
                       const MonitorInfo&    monitor,
                       bool                  numeric) {
    JsonArray status = root["Status"].to<JsonArray>();

    addEngineSection(addSection(status, "Engine"), state, info, numeric);
    addLineSection(addSection(status, "Line"), state, outage, info, numeric);

    JsonObject lastEntries = status.add<JsonObject>()["Last Log Entries"].to<JsonObject>();
    JsonObject lastLogs    = lastEntries["Logs"].to<JsonObject>();
    lastLogs["Alarm Log"] = firstOrEmpty(logs.alarm);
    if (info.evolution) {
        lastLogs["Service Log"] = firstOrEmpty(logs.service);
    }
    lastLogs["Run Log"] = firstOrEmpty(logs.run);

    JsonArray time = addSection(status, "Time");
    addText(time, "Monitor Time",   monitor.monitorTime);
    addText(time, "Generator Time", state.generatorTime);
}


void buildMaintenanceReport(JsonObject            root,
                            const GeneratorState& state,
                            const ControllerInfo& info,
                            const SiteInfo&       site,
                            bool                  numeric) {
    JsonArray maintenance = root["Maintenance"].to<JsonArray>();

    addText(maintenance, "Model",                   site.model);
    addText(maintenance, "Generator Serial Number", state.serialNumber);
    addText(maintenance, "Controller Detected",     state.productName);
    addText(maintenance, "Nominal RPM",             site.nominalRpm);
    addText(maintenance, "Rated kW",                site.ratedKw + " kW");
    addText(maintenance, "Nominal Frequency",       site.nominalFrequency + " Hz");
    addText(maintenance, "Fuel Type",               site.fuelType);
    addText(maintenance, "Generator Phase",         site.phase);

    if (info.evolution2) {
        addOptional(maintenance, "Ambient Temperature Sensor", state.ambientTemperatureF, true, "F", numeric);
    }

    JsonArray settings = addSection(maintenance, "Controller Settings");
    for (const Measurement& setting : state.controllerSettings) {
        if (setting.textOnly) {
            addText(settings, setting.label.c_str(), formatNumber(setting.value, setting.integer, setting.unit));
        } else {
            addValue(settings, setting.label.c_str(), setting.value, setting.integer, setting.unit, numeric);
        }
    }

    JsonArray exercise = addSection(maintenance, "Exercise");
    addText(exercise, "Exercise Time", state.exercise);
    if (isEvolutionLiquid(info)) {
        addText(exercise, "Exercise Duration", state.exerciseDuration);
    }

    JsonArray service = addSection(maintenance, "Service");
    for (const LabeledValue& item : state.service) {
        addText(service, item.label.c_str(), item.value);
    }
    addOptional(service, "Total Run Hours", state.runHours, false, "h", numeric);
    addText(service, "Hardware Version", state.hardwareVersion);
    addText(service, "Firmware Version", state.firmwareVersion);
}


void buildOutageReport(JsonObject            root,
                       const GeneratorState& state,
                       const OutageView&     outage,
                       const ControllerInfo& info,
                       bool                  numeric) {
    JsonArray list = root["Outage"].to<JsonArray>();

    addText(list, "Status",           outage.statusText);
    addText(list, "System In Outage", outage.inOutage ? "Yes" : "No");
    addOptional(list, "Utility Voltage",           state.utilityVolts,                   true, "V", numeric);
    addValue   (list, "Utility Voltage Minimum",   outage.minUtilityVolts.value_or(0.0), true, "V", numeric);
    addValue   (list, "Utility Voltage Maximum",   outage.maxUtilityVolts.value_or(0.0), true, "V", numeric);
    addOptional(list, "Utility Threshold Voltage", state.thresholdVolts,                 true, "V", numeric);

    if (state.showsPickupVolts) {
        addOptional(list, "Utility Pickup Voltage", state.pickupVolts, true, "V", numeric);
    }
    if (info.evolution) {
        addUnitsText(list, "Startup Delay", state.startupDelay, numeric);
        if (info.liquidCooled) {
            addUnitsText(list, "Warm-up Delay", state.warmupDelay, numeric);
        }
    }

    JsonObject logItem = list.add<JsonObject>();
    if (outage.history.empty()) {
        logItem["Outage Log"] = "";
        return;
    }
    JsonArray history = logItem["Outage Log"].to<JsonArray>();
    for (size_t index = 0; index < outage.history.size(); ++index) {
        const OutageLogEntry& entry = outage.history[index];
        if (!numeric) {
            history.add(entry.date + ", Duration: " + entry.duration);
            continue;
        }
        JsonArray fields = history.add<JsonObject>()[std::to_string(index)].to<JsonArray>();
        addText(fields, "Date",     entry.date);
        addText(fields, "Duration", entry.duration);
    }
}


void buildMonitorReport(JsonObject            root,
                        const GeneratorState& state,
                        const CommStats&      comm,
                        const SiteInfo&       site,
                        const MonitorInfo&    monitor,
                        bool                  numeric) {
    (void)numeric;   // genmon reports these as strings in both modes
    JsonArray list = root["Monitor"].to<JsonArray>();

    JsonArray stats = addSection(list, "Generator Monitor Stats");
    addText(stats, "Monitor Health",            monitor.health);
    addText(stats, "Controller",                state.controller);
    addText(stats, "Run time",                  monitor.runTime);
    addText(stats, "Generator Monitor Version", site.monitorVersion);
    addText(stats, "Update Available",          "No");
    addText(stats, "Update Version",            "");

    const double txShare      = comm.txPackets ? 100.0 / comm.txPackets : 0.0;
    const double packetsPerS  = comm.uptimeSeconds > 0.0 ? (comm.txPackets + comm.rxPackets) / comm.uptimeSeconds : 0.0;
    char         buffer[48];

    JsonArray link = addSection(list, "Communication Stats");
    std::snprintf(buffer, sizeof(buffer), "M: %u, S: %u", static_cast<unsigned>(comm.txPackets),
                  static_cast<unsigned>(comm.rxPackets));
    addText(link, "Packet Count", buffer);
    addText(link, "CRC Errors", std::to_string(comm.crcErrors) + " ");
    std::snprintf(buffer, sizeof(buffer), "%.2f%%", comm.crcErrors * txShare);
    addText(link, "CRC Percent Errors", buffer);
    addText(link, "Timeout Errors", std::to_string(comm.timeouts));
    std::snprintf(buffer, sizeof(buffer), "%.2f%%", comm.timeouts * txShare);
    addText(link, "Timeout Percent Errors", buffer);
    link.add<JsonObject>()["Modbus Exceptions"] = comm.exceptions;
    link.add<JsonObject>()["Validation Errors"] = comm.validationErrors;
    link.add<JsonObject>()["Sync Errors"]       = 0;
    link.add<JsonObject>()["Invalid Data"]      = comm.unexpectedData;
    addText(link, "Discarded Bytes", std::to_string(comm.discardedBytes));
    addText(link, "Comm Restarts",   std::to_string(comm.restarts));
    std::snprintf(buffer, sizeof(buffer), "%.2f", packetsPerS);
    addText(link, "Packets Per Second", buffer);
    if (comm.rxPackets) {
        std::snprintf(buffer, sizeof(buffer), "%.4f sec", comm.transactionSeconds / comm.rxPackets);
        addText(link, "Average Transaction Time", buffer);
    }
    addText(link, "Modbus Transport", "Serial");
    addText(link, "Serial Data Rate", std::to_string(comm.baudRate));

    JsonArray platform = addSection(list, "Platform Stats");
    addText(platform, "Platform",             "ESP32");
    addText(platform, "IP Address",           monitor.ipAddress);
    addText(platform, "WiFi Signal Strength", std::to_string(monitor.wifiRssi) + " dBm");
    addText(platform, "Free Memory",          std::to_string(monitor.freeHeapBytes / 1024) + " KB");
    addText(platform, "System Uptime",        formatDuration(monitor.uptimeSeconds));
}


void buildLogsReport(JsonObject root, const GeneratorLogs& logs, const ControllerInfo& info) {
    JsonObject list = root["Logs"].to<JsonObject>();

    JsonArray alarm = list["Alarm Log"].to<JsonArray>();
    for (const std::string& entry : logs.alarm) alarm.add(entry);

    if (info.evolution) {
        JsonArray service = list["Service Log"].to<JsonArray>();
        for (const std::string& entry : logs.service) service.add(entry);
    }

    JsonArray run = list["Run Log"].to<JsonArray>();
    for (const std::string& entry : logs.run) run.add(entry);
}


void buildStartInfo(JsonObject            root,
                    const GeneratorState& state,
                    const ControllerInfo& info,
                    const SiteInfo&       site) {
    root["version"]             = site.monitorVersion;
    root["sitename"]            = site.siteName;
    root["platform"]            = "esp32";
    root["fueltype"]            = site.fuelType;
    root["model"]               = site.model;
    root["nominalKW"]           = site.ratedKw;
    root["nominalRPM"]          = site.nominalRpm;
    root["nominalfrequency"]    = site.nominalFrequency;
    root["phase"]               = site.phase;
    root["Controller"]          = state.controller;
    root["Actual"]              = state.productName;
    root["NominalBatteryVolts"] = "12";
    root["PowerGraph"]          = state.powerMeter;
    root["UtilityVoltage"]      = true;
    root["RemoteCommands"]      = state.canRemoteStart;
    root["RemoteExercise"]      = true;
    root["ResetAlarms"]         = state.canResetAlarm;
    root["AckAlarms"]           = false;
    root["RemoteTransfer"]      = state.canRemoteStart;
    root["RemoteButtons"]       = state.canSetButtons;
    root["ExerciseControls"]    = true;
    root["WriteQuietMode"]      = state.reportsQuietToUi;
    root["EnhancedExercise"]    = info.enhancedExercise;
    root["Firmware"]            = state.firmwareVersion;
    root["Hardware"]            = state.hardwareVersion;
    root["SetGenTime"]          = true;
}


// =============================================================================
// Formatting
// =============================================================================

std::string formatDuration(int64_t seconds) {
    if (seconds < 0) {
        seconds = 0;
    }
    const int64_t days    = seconds / kSecondsPerDay;
    const int64_t rest    = seconds % kSecondsPerDay;
    char          clock[24];
    std::snprintf(clock, sizeof(clock), "%d:%02d:%02d", static_cast<int>(rest / 3600),
                  static_cast<int>((rest / 60) % 60), static_cast<int>(rest % 60));
    if (days == 0) {
        return clock;
    }
    return std::to_string(days) + (days == 1 ? " day, " : " days, ") + clock;
}


std::string outageStatusText(bool                   inOutage,
                             int64_t                outageStartEpoch,
                             std::optional<int64_t> lastStartEpoch,
                             std::optional<int64_t> lastDurationSeconds) {
    constexpr const char* kStamp = "%Y-%m-%d %H:%M:%S";
    if (inOutage) {
        return "System in outage since " + formatLocalTime(outageStartEpoch, kStamp);
    }
    if (lastStartEpoch && lastDurationSeconds) {
        return "Last outage occurred at " + formatLocalTime(*lastStartEpoch, kStamp) +
               " and lasted " + formatDuration(*lastDurationSeconds) + ".";
    }
    return "No outage has occurred since program launched.";
}

}  // namespace genmon
