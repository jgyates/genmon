// =============================================================================
// generator_service.cpp - Polls the controller and owns the decoded state
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "generator_service.h"

#include <Arduino.h>

#include <ctime>

#include "core/maintenance_decoder.h"
#include "core/register_map.h"
#include "core/state_builder.h"


namespace genmon {

namespace {

// =============================================================================
// Constants
// =============================================================================

constexpr uint32_t    kTaskStackBytes     = 12 * 1024;
constexpr UBaseType_t kTaskPriority       = 2;
constexpr BaseType_t  kTaskCore           = 1;
constexpr uint32_t    kDetectRetryMs      = 2000;
constexpr size_t      kBaseReadsPerPrime  = 6;            // as genmon's MasterEmulation()
constexpr uint32_t    kCommsWindowMs      = 15000;
constexpr uint32_t    kLogRefreshMs       = 30UL * 60UL * 1000UL;
constexpr uint32_t    kTimeSyncIntervalMs = 60UL * 60UL * 1000UL;
constexpr size_t      kMaxEvents          = 40;
constexpr int64_t     kEarliestValidEpoch = 1700000000;   // NTP has not synced before this

struct LogLayout {
    uint16_t start;
    uint8_t  stride;
    bool     evolutionOnly;
    bool     nexusOnly;
};

constexpr LogLayout kLogs[] = {
    {kEvolutionAlarmLogStart, kEvolutionAlarmLogStride, true,  false},
    {kServiceLogStart,        kServiceLogStride,        true,  false},
    {kNexusAlarmLogStart,     kNexusAlarmLogStride,     false, true},
    {kRunLogStart,            kRunLogStride,            false, false},
};

constexpr size_t kLogMonthByte = 4;   // a zero month marks an unused log slot


// =============================================================================
// Helpers
// =============================================================================

int64_t nowEpoch() {
    return static_cast<int64_t>(std::time(nullptr));
}


std::optional<GeneratorClock> localClock() {
    const std::time_t now = std::time(nullptr);
    if (now < kEarliestValidEpoch) {
        return std::nullopt;
    }
    std::tm local{};
    localtime_r(&now, &local);
    return GeneratorClock{local.tm_year + 1900, local.tm_mon + 1, local.tm_mday,
                          local.tm_wday,        local.tm_hour,    local.tm_min};
}

}  // namespace


// =============================================================================
// Public interface
// =============================================================================

void GeneratorService::begin(const Settings& settings) {
    settings_ = settings;
    options_  = monitorOptionsFrom(settings);

    outageLog_.begin();
    port_.begin(Serial2, settings.uartRxPin, settings.uartTxPin, settings.modbusAddress);

    xTaskCreatePinnedToCore(&GeneratorService::taskEntry, "generator", kTaskStackBytes, this,
                            kTaskPriority, nullptr, kTaskCore);
}


GeneratorSnapshot GeneratorService::snapshot() const {
    std::lock_guard<std::mutex> lock(mutex_);
    GeneratorSnapshot copy = snapshot_;
    copy.comm        = port_.stats();
    copy.commsActive = port_.recentlyActive(kCommsWindowMs);
    return copy;
}


RegisterSnapshot GeneratorService::registers() const {
    return registers_.snapshot();
}


std::vector<EventRecord> GeneratorService::recentEvents() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return std::vector<EventRecord>(events_.rbegin(), events_.rend());
}


std::string GeneratorService::submitCommand(const std::string& text) {
    const ParsedCommand parsed = parseCommand(text);
    if (!parsed.command) {
        return parsed.error;
    }

    ControllerInfo info;
    bool           initialized = false;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        info        = snapshot_.info;
        initialized = snapshot_.initialized;
    }
    if (!initialized) {
        return "Controller not detected yet; try again shortly";
    }

    const CommandPlan plan = planCommand(*parsed.command, info, generatorClock(registers_), localClock());
    if (!plan.error.empty()) {
        return plan.error;
    }

    std::lock_guard<std::mutex> lock(mutex_);
    pendingWrites_.insert(pendingWrites_.end(), plan.writes.begin(), plan.writes.end());
    return "Command sent";
}


std::string GeneratorService::health() const {
    const GeneratorSnapshot current = snapshot();
    std::string             text;
    if (!current.initialized) {
        text += "System Initializing. ";
    }
    if (!current.commsActive) {
        text += " Not receiving data. ";
    }
    return text.empty() ? "OK" : text;
}


// =============================================================================
// Task
// =============================================================================

void GeneratorService::taskEntry(void* self) {
    static_cast<GeneratorService*>(self)->run();
}


void GeneratorService::run() {
    initialize();
    while (true) {
        pollCycle();
    }
}


void GeneratorService::initialize() {
    std::optional<uint16_t> productCode;
    while (!productCode) {
        readSpan(reg::kProductCode, 1);
        productCode = registers_.u16(reg::kProductCode);
        if (!productCode) {
            delay(kDetectRetryMs);
        }
    }

    const ControllerInfo info = detectController(*productCode,
                                                 settings_.evolutionOverride,
                                                 settings_.liquidCooledOverride,
                                                 settings_.enhancedExercise,
                                                 settings_.legacyExerciseWrite);
    {
        std::lock_guard<std::mutex> lock(mutex_);
        snapshot_.info = info;
    }
    recordEvent("Detected " + productCodeName(*productCode) + " (" + controllerFamilyName(info) + ")");
    if (info.powerZone200) {
        recordEvent("Power Zone 200 controllers use 115200 baud and are not supported");
    }
    if (!info.knownCode) {
        recordEvent("Unvalidated product code; controller type is a best guess");
    }

    readSpan(reg::kSerialNumber, kSerialNumberWords);
    for (const RegisterSpan& span : primeRegisters()) readSpan(span.start, span.words);
    for (const RegisterSpan& span : baseRegisters())  readSpan(span.start, span.words);
    readLogs();

    {
        std::lock_guard<std::mutex> lock(mutex_);
        snapshot_.initialized       = true;
        snapshot_.outage.history    = outageLog_.entries();
        snapshot_.outage.statusText = outageStatusText(false, 0, std::nullopt, std::nullopt);
    }
    rebuildState();
}


void GeneratorService::pollCycle() {
    const std::vector<RegisterSpan>& base = baseRegisters();

    for (size_t index = 0; index < base.size(); ++index) {
        if (index % kBaseReadsPerPrime == 0) {
            for (const RegisterSpan& span : primeRegisters()) {
                readSpan(span.start, span.words);
            }
            executePendingCommands();
            rebuildState();
            if (logsDirty_ || millis() - lastLogReadMs_ > kLogRefreshMs) {
                readLogs();
            }
            syncGeneratorTimeIfDue();
        }
        readSpan(base[index].start, base[index].words);
    }

    if (!registers_.bytes(reg::kSerialNumber)) {
        readSpan(reg::kSerialNumber, kSerialNumberWords);
    }
}


void GeneratorService::readSpan(uint16_t start, uint8_t words) {
    RegisterBytes bytes;
    if (port_.readRegisters(start, words, bytes)) {
        registers_.store(start, bytes);
    }
}


void GeneratorService::readLogs() {
    ControllerInfo info;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        info = snapshot_.info;
    }

    for (const LogLayout& log : kLogs) {
        if ((log.evolutionOnly && !info.evolution) || (log.nexusOnly && info.evolution)) {
            continue;
        }
        for (uint8_t slot = 0; slot < kLogDepth; ++slot) {
            const uint16_t start = static_cast<uint16_t>(log.start + slot * log.stride);
            readSpan(start, log.stride);
            const auto entry = registers_.bytes(start);
            // Logs fill from the first slot, so an empty slot ends the log.
            if (!entry || entry->size() <= kLogMonthByte || (*entry)[kLogMonthByte] == 0) {
                break;
            }
        }
    }

    const GeneratorLogs logs = buildLogs(registers_, info);
    std::lock_guard<std::mutex> lock(mutex_);
    snapshot_.logs = logs;
    logsDirty_     = false;
    lastLogReadMs_ = millis();
}


// =============================================================================
// State
// =============================================================================

void GeneratorService::rebuildState() {
    const auto raw = registers_.u32(reg::kStatus);
    if (!raw) {
        return;
    }

    ControllerInfo info;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        info = snapshot_.info;
    }
    const auto status = statusFilter_.accept(*raw, info, options_.ignoreUnknownStatus);
    if (!status) {
        return;
    }

    const GeneratorState current = buildState(registers_, info, options_, *status);
    GeneratorState       previous;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        previous = snapshot_.state;
    }

    detectChanges(previous, current);
    if (!settings_.disableOutageCheck) {
        updateOutage(current);
    }

    const bool commsActive = port_.recentlyActive(kCommsWindowMs);
    if (commsActive != wasCommsActive_) {
        recordEvent(commsActive ? "Communication with controller established" : "Not receiving data from controller");
        wasCommsActive_ = commsActive;
    }

    std::lock_guard<std::mutex> lock(mutex_);
    snapshot_.state = current;
    ++snapshot_.revision;
}


void GeneratorService::detectChanges(const GeneratorState& previous, const GeneratorState& current) {
    if (!previous.valid) {
        return;
    }
    if (previous.statusWord != current.statusWord) {
        logsDirty_ = true;   // genmon re-reads the logs whenever the status word changes
    }
    if (previous.switchState != current.switchState) {
        recordEvent("Switch: " + previous.switchState + " -> " + current.switchState);
    }
    if (previous.engineState != current.engineState) {
        recordEvent("Engine: " + previous.engineState + " -> " + current.engineState);
    }
    if (previous.alarm != current.alarm) {
        recordEvent(current.alarm.empty() ? "Alarm cleared" : "ALARM: " + current.alarm);
    }
}


void GeneratorService::updateOutage(const GeneratorState& state) {
    if (!state.utilityVolts) {
        return;
    }

    ControllerInfo info;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        info = snapshot_.info;
    }

    OutageReading reading;
    reading.utilityVolts            = *state.utilityVolts;
    reading.thresholdVolts          = state.thresholdVolts.value_or(0.0);
    reading.pickupVolts             = state.pickupVolts.value_or(0.0);
    reading.nominalLineVolts        = options_.nominalLineVolts;
    reading.rejectSuspectThresholds = info.evolution2 && options_.ignoreUnknownStatus;

    const int64_t     now   = nowEpoch();
    const OutageEvent event = outageTracker_.update(reading, now);
    if (event == OutageEvent::Started) {
        recordEvent("Utility power out");
    } else if (event == OutageEvent::Ended) {
        const OutageRecord record = *outageTracker_.lastOutage();
        outageLog_.append(record.startEpoch, record.durationSeconds);
        recordEvent("Utility power restored after " + formatDuration(record.durationSeconds));
    }

    const auto last = outageTracker_.lastOutage();
    std::lock_guard<std::mutex> lock(mutex_);
    snapshot_.outage.inOutage        = outageTracker_.inOutage();
    snapshot_.outage.minUtilityVolts = outageTracker_.minUtilityVolts();
    snapshot_.outage.maxUtilityVolts = outageTracker_.maxUtilityVolts();
    snapshot_.outage.statusText      = outageStatusText(
        outageTracker_.inOutage(), outageTracker_.outageStart(),
        last ? std::optional<int64_t>(last->startEpoch) : std::nullopt,
        last ? std::optional<int64_t>(last->durationSeconds) : std::nullopt);
    if (event == OutageEvent::Ended) {
        snapshot_.outage.history = outageLog_.entries();
    }
}


// =============================================================================
// Commands
// =============================================================================

void GeneratorService::executePendingCommands() {
    while (true) {
        RegisterWrite write;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (pendingWrites_.empty()) {
                return;
            }
            write = pendingWrites_.front();
            pendingWrites_.pop_front();
        }
        if (!port_.writeRegisters(write.startRegister, write.data)) {
            char text[48];
            snprintf(text, sizeof(text), "Write to register %04X failed", write.startRegister);
            recordEvent(text);
        }
    }
}


void GeneratorService::syncGeneratorTimeIfDue() {
    if (!settings_.syncGeneratorTime || !localClock()) {
        return;
    }
    if (lastTimeSyncMs_ != 0 && millis() - lastTimeSyncMs_ < kTimeSyncIntervalMs) {
        return;
    }
    lastTimeSyncMs_ = millis();
    recordEvent("Generator time sync: " + submitCommand("settime"));
}


void GeneratorService::recordEvent(const std::string& text) {
    Serial.printf("[genmon] %s\n", text.c_str());
    std::lock_guard<std::mutex> lock(mutex_);
    events_.push_back({nowEpoch(), text});
    while (events_.size() > kMaxEvents) {
        events_.pop_front();
    }
}

}  // namespace genmon
