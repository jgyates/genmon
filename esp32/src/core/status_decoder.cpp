// =============================================================================
// status_decoder.cpp - Decoding of the 32-bit status word at register 0x0001
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "status_decoder.h"

#include <cstdio>

#include "alarm_codes.h"
#include "register_map.h"


namespace genmon {

namespace {

// =============================================================================
// Constants
// =============================================================================

constexpr uint32_t kEngineMask       = 0x001F0000;
constexpr int      kEngineShift      = 16;
constexpr uint32_t kSwitchMask       = 0x0000FFFF;
constexpr uint32_t kRemoteOffMask    = 0x000F0000;
constexpr uint32_t kServiceMask      = 0x0000003F;
constexpr uint32_t kServiceAAlarm    = 0x1F;
constexpr uint32_t kServiceBAlarm    = 0x20;
constexpr uint32_t kImpossibleBits   = 0xFFE0FFC0;   // never set in a genuine status word
constexpr int      kServiceSoonHours = 1;

// Values Evolution 2.0 returns when the register is momentarily garbage
// (they decode as ASCII fragments such as "  ", "?=", "go").
constexpr uint32_t kEvolution2Garbage[] = {
    0x2020, 0x20200000, 0x3F3D0000, 0x3F3D, 0x3430, 0x6F670000, 0x6F67, 0x6538,
};

struct NamedCode {
    uint16_t    code;
    const char* name;
};

// Low word of the status register while the switch reports an alarm.
constexpr NamedCode kStatusAlarms[] = {
    {0x01, "Low Battery"},
    {0x02, "High Temperature"},
    {0x03, "Controller Fault"},
    {0x05, "Low Fuel Pressure"},
    {0x08, "Low Coolant"},
    {0x0A, "Low Oil Pressure"},
    {0x0B, "Overcrank"},
    {0x0C, "Overspeed"},
    {0x0D, "RPM Sense Loss"},
    {0x0F, "Change Oil & Filter"},
    {0x10, "Inspect Air Filter"},
    {0x11, "Change Air Filter"},
    {0x12, "Check Spark Plugs"},
    {0x13, "Change Spark Plugs"},
    {0x14, "Check Battery"},
    {0x15, "Underspeed"},
    {0x16, "Change Coolant"},
    {0x18, "Wiring Error"},
    {0x19, "Check Engine"},
    {0x1A, "Missing Cam Pulse"},
    {0x1B, "Missing Crank Pulse"},
    {0x1C, "Throttle Failure"},
    {0x1D, "Over Voltage"},
    {0x1E, "Under Voltage"},
    {0x1F, "Service A Due"},
    {0x20, "Service B Due"},
    {0x22, "CANbus Error"},
    {0x23, "Ignition Fault"},
    {0x24, "Overload"},
    {0x27, "Firmware Error-25"},
    {0x28, "Fuse Problem"},
    {0x29, "Battery Problem"},
    {0x2A, "Charger Warning"},
    {0x2B, "Charger Missing AC"},
    {0x2D, "Overload Cooldown"},
    {0x30, "Ruptured Tank"},
    {0x31, "Low Fuel Level"},
    {0x32, "Low Fuel Pressure"},
    {0x34, "Emergency Stop"},
    {0x38, "Very Low Battery"},
    {0x46, "ECU Faulted"},
    {0x47, "Engine Throttle Valve 1 Position 1"},
    {0x48, "Engine Fuel Delivery Pressure"},
    {0x49, "Engine Oil Pressure"},
    {0x4A, "Engine Intake Manifold #1 Pressure"},
    {0x4B, "Engine Intake Manifold 1 Temperature"},
    {0x4C, "Engine Air Filter 1 Differential Pressure"},
    {0x4D, "Engine Coolant Temperature"},
    {0x4E, "Battery Potential / Power Input 1"},
    {0x4F, "Engine Oil Temperature 1"},
    {0x50, "Engine Fuel Shutoff 1 Control"},
    {0x51, "Engine Position Sensor"},
    {0x52, "Engine Timing Sensor"},
    {0x53, "O2 Sensor"},
    {0x54, "Engine Knock 1"},
    {0x55, "Engine Ignition Coil #1"},
    {0x56, "Engine Ignition Coil #2"},
    {0x57, "Engine Ignition Coil #3"},
    {0x58, "Engine Ignition Coil #4"},
    {0x59, "Engine Fuel Valve 1 Position"},
    {0x5A, "Engine Charge Air Cooler 1 Bypass"},
    {0x5B, "Engine Speed"},
    {0x5C, "Engine Fuel Shutoff 2 Control"},
    {0x72, "No Rotation Warning"},
};

// Bits 16-20 of the status register.
constexpr NamedCode kEngineStates[] = {
    {0x00, "Off - Ready"},
    {0x01, "Startup Delay Timer Activated"},
    {0x04, "Exercising"},
    {0x05, "Cooling Down"},
    {0x06, "Running in Warning"},
    {0x08, "Stopped in Alarm"},
    {0x09, "Stopped"},
    {0x0A, "Stopped in Warning"},
    {0x0B, "Cranking Paused"},
    {0x0C, "Running - Warm Up"},
    {0x0D, "Cranking in Warning"},
    {0x0E, "Cranking in Alarm"},
    {0x0F, "Off - Remote Switch Off"},
    {0x18, "Running - Transfer Switch Activated"},
    {0x1B, "Running Remote Transfer"},
    {0x1F, "Firmware Update in Progress"},
};

constexpr uint8_t kEngineCranking = 0x02;
constexpr uint8_t kEngineRunning  = 0x03;


// =============================================================================
// Helpers
// =============================================================================

const char* lookupName(const NamedCode* table, size_t count, uint16_t code) {
    for (size_t index = 0; index < count; ++index) {
        if (table[index].code == code) {
            return table[index].name;
        }
    }
    return nullptr;
}


template <size_t N>
const char* lookupName(const NamedCode (&table)[N], uint16_t code) {
    return lookupName(table, N, code);
}


bool contains(const std::string& text, const char* fragment) {
    return text.find(fragment) != std::string::npos;
}


std::string hex32(const char* prefix, uint32_t value) {
    char buffer[48];
    std::snprintf(buffer, sizeof(buffer), "%s%08X", prefix, static_cast<unsigned>(value));
    return buffer;
}


bool serviceCounterDueSoon(const RegisterCache& registers, uint16_t address) {
    const auto hours = registers.u16(address);
    return hours && *hours <= kServiceSoonHours;
}

}  // namespace


// =============================================================================
// StatusFilter
// =============================================================================

std::optional<uint32_t> StatusFilter::accept(uint32_t raw, const ControllerInfo& info, bool ignoreUnknown) {
    if (info.evolution2 && ignoreUnknown) {
        bool garbage = !isStatusWordPlausible(raw);
        for (uint32_t pattern : kEvolution2Garbage) {
            garbage = garbage || raw == pattern;
        }
        if (garbage) {
            return lastGood_;
        }
    }
    lastGood_ = raw;
    return raw;
}


void StatusFilter::reset() {
    lastGood_.reset();
}


// =============================================================================
// Status word decoding
// =============================================================================

bool isStatusWordPlausible(uint32_t status) {
    return (status & kImpossibleBits) == 0;
}


std::string switchState(uint32_t status) {
    switch (status & kSwitchMask) {
        case 0x00: return "Auto";
        case 0x07: return "Off";
        default:   break;
    }
    if ((status & kRemoteOffMask) == kRemoteOffMask) {
        return "Off via Remote Command";
    }
    switch (status & kSwitchMask) {
        case 0x06: return "Manual";
        case 0x17: return "Two Wire Stop";
        default:   return "System in Alarm";
    }
}


std::string alarmText(uint32_t status, const RegisterCache& registers, const ControllerInfo& info) {
    if (!contains(switchState(status), "Alarm")) {
        return "";
    }

    const char* name = lookupName(kStatusAlarms, static_cast<uint16_t>(status & kSwitchMask));
    if (name) {
        return name;
    }

    // Evolution keeps the last alarm code in 0x05F1, which covers alarms the
    // status word table does not know.
    if (info.evolution) {
        const auto lastCode = registers.u16(reg::kLastAlarmCode);
        const AlarmCode* entry = lastCode ? findAlarmCode(*lastCode) : nullptr;
        if (entry) {
            return entry->name;
        }
    }
    return hex32("UNKNOWN ALARM: ", status);
}


std::string engineState(uint32_t status, bool inAlarm) {
    const uint8_t code = static_cast<uint8_t>((status & kEngineMask) >> kEngineShift);

    if (code == kEngineCranking) {
        return inAlarm ? "Cranking in Alarm" : "Cranking";
    }
    if (code == kEngineRunning) {
        return inAlarm ? "Running in Alarm" : "Running";
    }
    const char* name = lookupName(kEngineStates, code);
    return name ? name : hex32("UNKNOWN: ", status);
}


bool engineIsRunning(const std::string& engine) {
    return !engine.empty() && !contains(engine, "Stopped") && !contains(engine, "Off");
}


bool serviceAlarmActive(uint32_t status) {
    const uint32_t serviceBits = status & kServiceMask;
    return serviceBits == kServiceAAlarm || serviceBits == kServiceBAlarm;
}


bool serviceDue(uint32_t status, const RegisterCache& registers, const ControllerInfo& info) {
    if (serviceAlarmActive(status)) {
        return true;
    }

    if (info.evolution) {
        return serviceCounterDueSoon(registers, reg::kServiceAHours) ||
               serviceCounterDueSoon(registers, reg::kServiceBHours);
    }

    // Nexus counters: spark/oil/air (and battery/other on air cooled units).
    const bool shared = serviceCounterDueSoon(registers, reg::kServiceAHours) ||
                        serviceCounterDueSoon(registers, reg::kServiceBHours) ||
                        serviceCounterDueSoon(registers, reg::kService1CHours);
    if (info.liquidCooled) {
        return shared;
    }
    return shared ||
           serviceCounterDueSoon(registers, reg::kServiceBDate) ||
           serviceCounterDueSoon(registers, reg::kService21Hours);
}


std::string baseStatus(bool               inAlarm,
                       bool               serviceAlarm,
                       bool               serviceDueSoon,
                       const std::string& engine,
                       const std::string& switchPosition) {
    if (inAlarm) {
        return serviceAlarm ? "SERVICEDUE" : "ALARM";
    }
    if (serviceDueSoon) {
        return "SERVICEDUE";
    }
    if (contains(engine, "Exercising")) {
        return "EXERCISING";
    }
    if (contains(engine, "Running")) {
        return contains(switchPosition, "Auto") ? "RUNNING" : "RUNNING-MANUAL";
    }
    if (contains(switchPosition, "Off")) {
        return "OFF";
    }
    if (contains(switchPosition, "Manual")) {
        return "MANUAL";
    }
    return "READY";
}


std::string ledState(const RegisterCache& registers, const ControllerInfo& info) {
    if (!info.evolution || info.liquidCooled || !(info.evolution2 || info.powerPact)) {
        return "";
    }
    const auto value = registers.u16(reg::kLedState);
    if (!value) {
        return "";
    }

    switch (static_cast<char>(*value & 0xFF)) {
        case 'G': return "Ready to Run";
        case 'Y': return "Not Running with Alarms or Warnings Active";
        case 'R': return "Switch Off or Alarms Active";
        case 'U': return "Running, no Alarms";
        case 'N': return "Running with Warnings";
        default:  return "Unknown";
    }
}

}  // namespace genmon
