// =============================================================================
// log_parser.cpp - Decoding of the controller's alarm, service and run logs
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "log_parser.h"

#include <cstdio>

#include "alarm_codes.h"


namespace genmon {

namespace {

// =============================================================================
// Constants
// =============================================================================

constexpr size_t  kShortEntrySize            = 8;
constexpr size_t  kAlarmEntrySize            = 10;
constexpr uint8_t kNoRotationCode            = 0x33;
constexpr uint8_t kNoRotationMinimumFirmware = 114;   // V1.14

struct LogCode {
    uint8_t     code;
    const char* text;
};

constexpr LogCode kRunLog[] = {
    {0x28, "Switched Off"},
    {0x29, "Running - Manual"},
    {0x2A, "Stopped - Auto"},
    {0x2B, "Running - Utility Loss"},
    {0x2C, "Running - 2 Wire Start"},
    {0x2D, "Running - Remote Start"},
    {0x2E, "Running - Exercise"},
    {0x2F, "Stopped - Alarm"},
};

constexpr LogCode kEvolutionServiceLog[] = {
    {0x16, "Service Schedule B"},
    {0x17, "Service Schedule A"},
    {0x18, "Inspect Battery"},
    {0x3C, "Schedule B Serviced"},
    {0x3D, "Schedule A Serviced"},
    {0x3E, "Battery Maintained"},
    {0x3F, "Maintenance Reset"},
};

constexpr LogCode kEvolutionLiquidAlarmLog[] = {
    {0x00, "High Temperature"},           {0x01, "Low Oil Pressure"},
    {0x02, "Overcrank"},                  {0x03, "Overspeed"},
    {0x04, "RPM Sense Loss"},             {0x05, "Underspeed"},
    {0x06, "Low Coolant Level"},          {0x08, "Wiring Error"},
    {0x09, "Over Voltage"},               {0x0A, "Under Voltage"},
    {0x0B, "Overload"},                   {0x0C, "Undervoltage Overload"},
    {0x0D, "Stepper Overcurrent"},        {0x0E, "Fuse Problem"},
    {0x0F, "VSCF_COMM_GONE"},             {0x10, "VSCF_ENABLE_MISMATCH"},
    {0x11, "VSCF_PWM_SPEED_GONE"},        {0x12, "Very Low Battery"},
    {0x13, "VSCF_SPECIAL_NO_TRANSLATION"},{0x14, "Low Battery"},
    {0x15, "Exercise Set Error"},         {0x16, "Service Schedule B"},
    {0x17, "Service Schedule A"},         {0x18, "Inspect Battery"},
    {0x19, "Service Schedule C"},         {0x1C, "Stopping"},
    {0x1D, "Software Error 9"},           {0x1E, "Fuel Pressure"},
    {0x1F, "Battery Problem"},            {0x20, "Charger Warning"},
    {0x21, "Charger missing AC"},         {0x22, "Overload warning"},
    {0x23, "Check Engine"},               {0x24, "DTC Warning"},
    {0x25, "VSCF Warning"},               {0x26, "USB Warning"},
    {0x27, "Modbus Comms Failure Warning"},{0x28, "Switched Off"},
    {0x29, "Running-Manual"},             {0x2A, "Stopped-Auto"},
    {0x2B, "Running-Utility Lost"},       {0x2C, "Running-2 Wire Start"},
    {0x2D, "Running-Radio Start"},        {0x2E, "Running-Exercise"},
    {0x2F, "Stopped-Alarm"},              {0x30, "WIRING ERROR"},
    {0x31, "Over Voltage"},               {0x32, "Under Voltage"},
    {0x33, "Overload Remove Load"},       {0x34, "Low Volts Remove Load"},
    {0x35, "Stepper Over Current"},       {0x36, "Fuse Problem"},
    {0x39, "Loss of Speed Signal"},       {0x3A, "Loss of Serial Link"},
    {0x3B, "VSCF Alarm"},                 {0x3C, "Service B performed"},
    {0x3D, "Service A performed"},        {0x3E, "Battery Inspected"},
    {0x3F, "Reset Maintenance"},          {0x40, "Internal Fault"},
    {0x41, "Ignition Fault"},             {0x42, "CANbus Error"},
    {0x43, "Missing Cam Pulse"},          {0x44, "Missing Crank Pulse"},
    {0x45, "Governor Fault"},             {0x46, "Ruptured Tank"},
    {0x47, "Low Fuel"},                   {0x48, "E-Stop"},
    {0x49, "Hall Calibration Error"},     {0x4A, "SEEProm Abuse"},
    {0x4B, "Download Failure"},           {0x4C, "Service C Performed"},
    {0xAA, "ECU Fault"},                  {0xAB, "Engine Throttle Valve 1 Position 1"},
    {0xAC, "Engine Fuel Delivery Pressure"}, {0xAD, "Engine Oil Pressure"},
    {0xAE, "Engine Intake Manifold #1 Pressure"},
    {0xAF, "Engine Intake Manifold 1 Temperature"},
    {0xB0, "Engine Air Filter 1 Differential Pressure"},
    {0xB1, "Engine Coolant Temperature"}, {0xB2, "Battery Potential / Power Input 1"},
    {0xB3, "Engine Oil Temperature 1"},   {0xB4, "Engine Fuel Shutoff 1 Control"},
    {0xB5, "Engine Position Sensor"},     {0xB6, "Engine Timing Sensor"},
    {0xB7, "O2 Sensor"},                  {0xB8, "Engine Knock 1"},
    {0xB9, "Engine Ignition Coil #1"},    {0xBA, "Engine Ignition Coil #2"},
    {0xBB, "Engine Ignition Coil #3"},    {0xBC, "Engine Ignition Coil #4"},
    {0xBD, "Engine Fuel Valve 1 Position"},
    {0xBE, "Engine Charge Air Cooler 1 Bypass"},
    {0xBF, "Engine Speed"},
};

// Evolution air cooled warnings are logged with an alarm code of zero.
constexpr LogCode kEvolutionAirAlarmLog[] = {
    {0x08, "WIRING ERROR"},           {0x13, "FIRMWARE ERROR-25"},
    {0x14, "Low Battery"},            {0x15, "Exercise Set Error"},
    {0x16, "Service Schedule B"},     {0x17, "Service Schedule A"},
    {0x18, "Inspect Battery"},        {0x19, "SEEPROM ABUSE"},
    {0x1C, "Stopping"},               {0x1D, "FIRMWARE ERROR-9"},
    {0x1E, "Fuel Pressure"},          {0x1F, "Battery Problem"},
    {0x20, "Charger Warning"},        {0x21, "Charger Missing AC"},
    {0x22, "Overload Warning"},       {0x23, "Overload Cooldown"},
    {0x25, "VSCF Warning"},           {0x26, "USB Warning"},
    {0x27, "Download Failure"},       {0x28, "High Engine Temp"},
    {0x29, "Low Oil Pressure"},       {0x2A, "Overcrank"},
    {0x2B, "Overspeed"},              {0x2C, "RPM Sense Loss"},
    {0x2D, "Underspeed"},             {0x2E, "Controller Fault"},
    {0x2F, "FIRMWARE ERROR-7"},       {0x30, "WIRING ERROR"},
    {0x31, "Over Voltage"},           {0x32, "Under Voltage"},
    {0x33, "Overload Remove Load"},   {0x34, "Low Volts Remove Load"},
    {0x35, "Stepper Over Current"},   {0x36, "Fuse Problem"},
    {0x39, "Loss of Speed Signal"},   {0x3A, "Loss of Serial Link"},
    {0x3B, "VSCF Alarm"},             {0x3C, "Schedule B Serviced"},
    {0x3D, "Schedule A Serviced"},    {0x3E, "Battery Maintained"},
    {0x3F, "Maintenance Reset"},      {0x78, "No Wi-Fi Module"},
};

constexpr LogCode kNexusLiquidAlarmLog[] = {
    {0x00, "High Engine Temperature"}, {0x01, "Low Oil Pressure"},
    {0x02, "Overcrank"},               {0x03, "Overspeed"},
    {0x04, "RPM Sense Loss"},          {0x05, "Underspeed"},
    {0x08, "WIRING ERROR"},            {0x09, "Over Voltage"},
    {0x0A, "Under Voltage"},           {0x0B, "Low Cooling Fluid"},
    {0x0C, "Canbus Error"},            {0x0D, "Missing Cam Pulse"},
    {0x0E, "Missing Crank Pulse"},     {0x0F, "Governor Fault"},
    {0x10, "Ignition Fault"},          {0x14, "Low Battery"},
    {0x16, "Change Oil & Filter"},     {0x17, "Inspect Air Filter"},
    {0x18, "Change Air Filter"},       {0x19, "Inspect Spark Plugs"},
    {0x1B, "Inspect Battery"},         {0x1E, "Low Fuel Pressure"},
    {0x21, "Service Schedule A"},      {0x22, "Service Schedule B"},
    {0x23, "Check Engine"},
};

constexpr LogCode kNexusAirAlarmLog[] = {
    {0x00, "High Temperature"},        {0x01, "Low Oil Pressure"},
    {0x02, "Overcrank"},               {0x03, "Overspeed"},
    {0x04, "RPM Sense Loss"},          {0x05, "Underspeed"},
    {0x06, "Internal Fault"},          {0x07, "Software Error 7"},
    {0x08, "Wiring Error"},            {0x09, "Over Voltage"},
    {0x0A, "Under Voltage"},           {0x14, "Low Battery"},
    {0x15, "Exercise Set Error"},      {0x16, "Change Oil & Filter"},
    {0x17, "Inspect Air Filter"},      {0x18, "Change Air Filter"},
    {0x19, "Inspect Spark Plugs"},     {0x1A, "Change Spark Plugs"},
    {0x1B, "Inspect Battery"},         {0x1C, "Stopping"},
    {0x1D, "Software Error 9"},        {0x27, "Modbus Comms Failure Warning"},
    {0x28, "Switched Off"},            {0x29, "Running-manual"},
    {0x2A, "Stopped-auto"},            {0x2B, "Running-Utility Lost"},
    {0x2C, "Running-2 wire start"},    {0x2D, "Running-radio start"},
    {0x2E, "Running-exercise"},
};


// =============================================================================
// Types
// =============================================================================

struct LogTable {
    const LogCode* codes;
    size_t         count;
};

struct EntryTime {
    int month;
    int day;
    int year;
    int hour;
    int minute;
    int second;
};


// =============================================================================
// Helpers
// =============================================================================

template <size_t N>
LogTable table(const LogCode (&codes)[N]) {
    return LogTable{codes, N};
}


LogTable selectTable(LogKind kind, const ControllerInfo& info) {
    const bool evolutionAir = info.evolution && !info.liquidCooled;
    switch (kind) {
        case LogKind::EvolutionAlarm:
            return evolutionAir ? table(kEvolutionAirAlarmLog) : table(kEvolutionLiquidAlarmLog);
        case LogKind::EvolutionService:
            return evolutionAir ? table(kEvolutionAirAlarmLog) : table(kEvolutionServiceLog);
        case LogKind::NexusAlarm:
            return (!info.evolution && !info.liquidCooled) ? table(kNexusAirAlarmLog) : table(kNexusLiquidAlarmLog);
        case LogKind::Run:
        default:
            return table(kRunLog);
    }
}


const char* lookupText(const LogTable& codes, uint8_t code) {
    for (size_t index = 0; index < codes.count; ++index) {
        if (codes.codes[index].code == code) {
            return codes.codes[index].text;
        }
    }
    return nullptr;
}


bool decodeTime(const RegisterBytes& entry, EntryTime& time) {
    time.minute = entry[2];
    time.hour   = entry[3];
    time.month  = entry[4];
    time.second = entry[5];
    time.year   = entry[6];
    time.day    = entry[7];

    return time.month >= 1 && time.month <= 12 &&
           time.day   >= 1 && time.day   <= 31 &&
           time.hour   <= 23 &&
           time.minute <= 59 &&
           time.second <= 59;
}


std::string describe(const RegisterBytes& entry, LogKind kind, const ControllerInfo& info, uint8_t firmwareVersion) {
    const uint8_t code = entry[0];

    const bool noRotation = kind == LogKind::EvolutionAlarm && info.evolution2 &&
                            code == kNoRotationCode && firmwareVersion >= kNoRotationMinimumFirmware;
    if (noRotation) {
        return "No Rotation Warning";
    }

    const char* text = lookupText(selectTable(kind, info), code);
    if (text) {
        return text;
    }

    if (kind == LogKind::EvolutionAlarm && entry.size() == kAlarmEntrySize) {
        const AlarmCode* alarm = findAlarmCode(static_cast<uint16_t>((entry[8] << 8) | entry[9]));
        if (alarm) {
            return alarm->name;
        }
    }

    char buffer[16];
    std::snprintf(buffer, sizeof(buffer), "Unknown 0x%02X", code);
    return buffer;
}

}  // namespace


// =============================================================================
// Core logic
// =============================================================================

std::string parseLogEntry(const RegisterBytes&  entry,
                          LogKind               kind,
                          const ControllerInfo& info,
                          uint8_t               firmwareVersion) {
    if (entry.size() != kShortEntrySize && entry.size() != kAlarmEntrySize) {
        return "";
    }

    EntryTime time{};
    if (!decodeTime(entry, time)) {
        return "";
    }

    char stamp[24];
    std::snprintf(stamp, sizeof(stamp), "%02d/%02d/%02d %02d:%02d:%02d ",
                  time.month, time.day, time.year, time.hour, time.minute, time.second);

    std::string line = stamp + describe(entry, kind, info, firmwareVersion);

    if (entry.size() == kAlarmEntrySize) {
        char code[24];
        std::snprintf(code, sizeof(code), " (Alarm Code %04d)", (entry[8] << 8) | entry[9]);
        line += code;
    }
    return line;
}

}  // namespace genmon
