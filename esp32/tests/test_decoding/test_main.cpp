// =============================================================================
// test_decoding - Status word, logs, maintenance, commands and outages
// =============================================================================
//
// Expected values follow genmonlib/generac_evolution.py so the ESP32 reports
// exactly what genmon reported for the same registers.

// =============================================================================
// Includes
// =============================================================================

#include <unity.h>

#include "command.h"
#include "controller_info.h"
#include "log_parser.h"
#include "maintenance_decoder.h"
#include "outage_tracker.h"
#include "register_map.h"
#include "state_builder.h"
#include "status_decoder.h"

using namespace genmon;


// =============================================================================
// Fixtures
// =============================================================================

void setUp() {}
void tearDown() {}


ControllerInfo evolutionAir() {
    return detectController(0x09, Detect::Auto, Detect::Auto, false, false);
}


ControllerInfo evolutionLiquid() {
    return detectController(0x0C, Detect::Auto, Detect::Auto, false, false);
}


ControllerInfo nexusAir() {
    return detectController(0x03, Detect::Auto, Detect::Auto, false, false);
}


void store16(RegisterCache& cache, uint16_t address, uint16_t value) {
    cache.store(address, {static_cast<uint8_t>(value >> 8), static_cast<uint8_t>(value & 0xFF)});
}


void store32(RegisterCache& cache, uint16_t address, uint32_t value) {
    cache.store(address, {static_cast<uint8_t>(value >> 24), static_cast<uint8_t>(value >> 16),
                          static_cast<uint8_t>(value >> 8),  static_cast<uint8_t>(value)});
}


// =============================================================================
// Controller detection
// =============================================================================

void test_detects_controller_families() {
    TEST_ASSERT_TRUE(evolutionAir().evolution);
    TEST_ASSERT_FALSE(evolutionAir().liquidCooled);
    TEST_ASSERT_TRUE(evolutionLiquid().liquidCooled);
    TEST_ASSERT_FALSE(nexusAir().evolution);
    TEST_ASSERT_TRUE(nexusAir().legacyExerciseWrite);

    const ControllerInfo evo2 = detectController(0x15, Detect::Auto, Detect::Auto, false, false);
    TEST_ASSERT_TRUE(evo2.evolution2);
    TEST_ASSERT_TRUE(evo2.enhancedExercise);
    TEST_ASSERT_EQUAL_STRING("Evolution 2.0, Air Cooled", controllerFamilyName(evo2).c_str());
}


void test_override_beats_detection() {
    const ControllerInfo info = detectController(0x09, Detect::No, Detect::Yes, false, false);
    TEST_ASSERT_FALSE(info.evolution);
    TEST_ASSERT_TRUE(info.liquidCooled);
}


// =============================================================================
// Status word
// =============================================================================

void test_ready_in_auto() {
    TEST_ASSERT_EQUAL_STRING("Auto", switchState(0x00000000).c_str());
    TEST_ASSERT_EQUAL_STRING("Off - Ready", engineState(0x00000000, false).c_str());
    TEST_ASSERT_EQUAL_STRING("READY", baseStatus(false, false, false, "Off - Ready", "Auto").c_str());
}


void test_running_states() {
    TEST_ASSERT_EQUAL_STRING("Running", engineState(0x00030000, false).c_str());
    TEST_ASSERT_EQUAL_STRING("RUNNING", baseStatus(false, false, false, "Running", "Auto").c_str());
    TEST_ASSERT_EQUAL_STRING("Manual", switchState(0x00030006).c_str());
    TEST_ASSERT_EQUAL_STRING("RUNNING-MANUAL", baseStatus(false, false, false, "Running", "Manual").c_str());
    TEST_ASSERT_EQUAL_STRING("Exercising", engineState(0x00040000, false).c_str());
}


void test_alarm_from_status_word() {
    RegisterCache cache;
    TEST_ASSERT_EQUAL_STRING("System in Alarm", switchState(0x00080014).c_str());
    TEST_ASSERT_EQUAL_STRING("Check Battery", alarmText(0x00080014, cache, evolutionAir()).c_str());
    TEST_ASSERT_EQUAL_STRING("Stopped in Alarm", engineState(0x00080014, true).c_str());
}


void test_unknown_alarm_falls_back_to_last_alarm_code() {
    RegisterCache cache;
    store16(cache, reg::kLastAlarmCode, 1600);
    TEST_ASSERT_EQUAL_STRING("Underspeed", alarmText(0x00000099, cache, evolutionAir()).c_str());
}


void test_service_alarm_reports_service_due() {
    RegisterCache cache;
    TEST_ASSERT_TRUE(serviceAlarmActive(0x0000001F));
    TEST_ASSERT_EQUAL_STRING("Service A Due", alarmText(0x0000001F, cache, evolutionAir()).c_str());
    TEST_ASSERT_EQUAL_STRING("SERVICEDUE", baseStatus(true, true, true, "Off - Ready", "System in Alarm").c_str());
}


void test_service_counter_within_an_hour_is_due() {
    RegisterCache cache;
    store16(cache, reg::kServiceAHours, 1);
    store16(cache, reg::kServiceBHours, 300);
    TEST_ASSERT_TRUE(serviceDue(0, cache, evolutionAir()));
}


void test_evolution2_filter_drops_garbage_status() {
    const ControllerInfo evo2 = detectController(0x15, Detect::Auto, Detect::Auto, false, false);
    StatusFilter         filter;
    TEST_ASSERT_FALSE(filter.accept(0x3F3D0000, evo2, true).has_value());
    TEST_ASSERT_EQUAL_HEX32(0x00030000, *filter.accept(0x00030000, evo2, true));
    TEST_ASSERT_EQUAL_HEX32(0x00030000, *filter.accept(0x6F670000, evo2, true));
}


// =============================================================================
// Logs
// =============================================================================

void test_run_log_entry() {
    const RegisterBytes entry = {0x2A, 0x05, 30, 14, 10, 15, 24, 29};
    TEST_ASSERT_EQUAL_STRING("10/29/24 14:30:15 Stopped - Auto",
                             parseLogEntry(entry, LogKind::Run, evolutionAir(), 0).c_str());
}


void test_alarm_log_entry_uses_alarm_code_when_event_unknown() {
    const RegisterBytes entry = {0x99, 0x01, 0, 8, 1, 0, 25, 2, 0x06, 0x40};
    TEST_ASSERT_EQUAL_STRING("01/02/25 08:00:00 Underspeed (Alarm Code 1600)",
                             parseLogEntry(entry, LogKind::EvolutionAlarm, evolutionAir(), 0).c_str());
}


void test_empty_log_slot_is_blank() {
    const RegisterBytes entry = {0, 0, 0, 0, 0, 0, 0, 0};
    TEST_ASSERT_EQUAL_STRING("", parseLogEntry(entry, LogKind::Run, evolutionAir(), 0).c_str());
}


// =============================================================================
// Maintenance
// =============================================================================

void test_exercise_schedule_text() {
    RegisterCache cache;
    store16(cache, reg::kExerciseTime, 0x0D1E);
    store16(cache, reg::kExerciseDay, 0x0601);
    TEST_ASSERT_EQUAL_STRING("Weekly Saturday 13:30 Quiet Mode On", exerciseSchedule(cache, evolutionAir()).c_str());
}


void test_serial_number_and_replacement() {
    RegisterCache cache;
    MonitorOptions options;
    cache.store(reg::kSerialNumber, {'0', '0', '0', '7', '7', '2', '2', '9', '8', '7'});
    TEST_ASSERT_EQUAL_STRING("0007722987", serialNumber(cache, options).c_str());

    cache.store(reg::kSerialNumber, RegisterBytes(10, 0xFF));
    TEST_ASSERT_EQUAL_STRING("None - Controller has been replaced", serialNumber(cache, options).c_str());
}


void test_run_hours_by_cooling_type() {
    RegisterCache  cache;
    MonitorOptions options;
    store32(cache, reg::kRunHours, 100);
    store32(cache, reg::kRunMinutes, 150);
    TEST_ASSERT_EQUAL_DOUBLE(100.0, *runHours(cache, evolutionAir(), options));
    TEST_ASSERT_EQUAL_DOUBLE(2.5, *runHours(cache, evolutionLiquid(), options));
}


void test_date_from_epoch_days() {
    TEST_ASSERT_EQUAL_STRING("01/01/1970", dateFromEpochDays(0).c_str());
    TEST_ASSERT_EQUAL_STRING("10/04/2024", dateFromEpochDays(20000).c_str());
}


void test_firmware_version_formatting() {
    TEST_ASSERT_EQUAL_STRING("V1.43", formatVersion(143).c_str());
    TEST_ASSERT_EQUAL_STRING("", formatVersion(std::nullopt).c_str());
}


// =============================================================================
// State builder
// =============================================================================

void test_state_scales_engine_values() {
    RegisterCache cache;
    store16(cache, reg::kBatteryVolts, 137);
    store16(cache, reg::kFrequency, 601);
    store16(cache, reg::kRpm, 3600);
    MonitorOptions options;

    const GeneratorState air    = buildState(cache, evolutionAir(), options, 0x00030000);
    const GeneratorState liquid = buildState(cache, evolutionLiquid(), options, 0x00030000);
    TEST_ASSERT_EQUAL_DOUBLE(13.7, *air.batteryVolts);
    TEST_ASSERT_EQUAL_DOUBLE(601.0, *air.frequencyHz);      // air cooled reports whole Hz
    TEST_ASSERT_EQUAL_DOUBLE(60.1, *liquid.frequencyHz);    // liquid cooled reports tenths
    TEST_ASSERT_TRUE(air.running);
}


void test_air_cooled_current_and_power() {
    RegisterCache cache;
    store16(cache, reg::kCurrentLeg1, 200);
    store16(cache, reg::kCurrentLeg2, 100);
    store16(cache, reg::kOutputVolts, 240);
    MonitorOptions options;
    options.ratedKw = 22.0f;

    const GeneratorState state = buildState(cache, evolutionAir(), options, 0x00030000);
    TEST_ASSERT_EQUAL_DOUBLE(15.0, *state.outputAmps);
    TEST_ASSERT_EQUAL_DOUBLE(20.0, *state.outputAmpsLeg1);
    TEST_ASSERT_EQUAL_DOUBLE(3.6, *state.outputKw);
}


// =============================================================================
// Commands
// =============================================================================

void test_remote_start_plan() {
    const ParsedCommand parsed = parseCommand("setremote=START");
    TEST_ASSERT_TRUE(parsed.command.has_value());
    const CommandPlan plan = planCommand(*parsed.command, evolutionAir(), std::nullopt, std::nullopt);
    TEST_ASSERT_EQUAL(1, plan.writes.size());
    TEST_ASSERT_EQUAL_HEX16(reg::kCommandIndex, plan.writes[0].startRegister);
    TEST_ASSERT_EQUAL_HEX8(0x01, plan.writes[0].data[1]);
}


void test_exercise_plan_direct_write() {
    const ParsedCommand parsed = parseCommand("setexercise=Monday,12:20,Weekly");
    const CommandPlan   plan   = planCommand(*parsed.command, evolutionAir(), std::nullopt, std::nullopt);
    TEST_ASSERT_EQUAL(2, plan.writes.size());
    TEST_ASSERT_EQUAL_HEX16(reg::kExerciseDayWrite, plan.writes[0].startRegister);
    TEST_ASSERT_EQUAL_HEX8(1, plan.writes[0].data[1]);
    TEST_ASSERT_EQUAL_HEX8(12, plan.writes[1].data[0]);
    TEST_ASSERT_EQUAL_HEX8(20, plan.writes[1].data[1]);
}


void test_exercise_plan_legacy_write_counts_128_second_steps() {
    const GeneratorClock clock{2026, 10, 25, 0, 10, 0};   // Sunday 10:00
    const ParsedCommand  parsed = parseCommand("setexercise=Monday,12:20");
    const CommandPlan    plan   = planCommand(*parsed.command, nexusAir(), clock, std::nullopt);
    TEST_ASSERT_EQUAL(2, plan.writes.size());
    TEST_ASSERT_EQUAL_HEX16(reg::kCommandValue, plan.writes[0].startRegister);
    TEST_ASSERT_EQUAL_HEX8(0x02, plan.writes[0].data[0]);   // 1580 min * 60 / 128 = 740 = 0x02E4
    TEST_ASSERT_EQUAL_HEX8(0xE4, plan.writes[0].data[1]);
}


void test_unsupported_commands_are_rejected() {
    TEST_ASSERT_FALSE(parseCommand("setremote=launch").command.has_value());
    const CommandPlan plan = planCommand(*parseCommand("setremote=resetalarm").command, evolutionAir(),
                                         std::nullopt, std::nullopt);
    TEST_ASSERT_FALSE(plan.error.empty());
}


void test_set_time_plan() {
    const GeneratorClock now{2026, 10, 29, 4, 14, 5};
    const CommandPlan    plan = planCommand(*parseCommand("settime").command, evolutionAir(), std::nullopt, now);
    const uint8_t        expected[] = {14, 5, 10, 29, 0, 26};
    TEST_ASSERT_EQUAL(1, plan.writes.size());
    TEST_ASSERT_EQUAL_HEX8_ARRAY(expected, plan.writes[0].data.data(), sizeof(expected));
}


// =============================================================================
// Outages
// =============================================================================

void test_outage_start_and_end() {
    OutageTracker tracker;
    OutageReading reading;
    reading.thresholdVolts = 143;
    reading.pickupVolts    = 190;

    reading.utilityVolts = 240;
    TEST_ASSERT_TRUE(tracker.update(reading, 1000) == OutageEvent::None);
    reading.utilityVolts = 50;
    TEST_ASSERT_TRUE(tracker.update(reading, 1010) == OutageEvent::Started);
    reading.utilityVolts = 238;
    TEST_ASSERT_TRUE(tracker.update(reading, 1310) == OutageEvent::Ended);
    TEST_ASSERT_EQUAL_INT64(300, tracker.lastOutage()->durationSeconds);
    TEST_ASSERT_EQUAL_DOUBLE(240.0, *tracker.maxUtilityVolts());
    TEST_ASSERT_EQUAL_DOUBLE(238.0, *tracker.minUtilityVolts());
}


// =============================================================================
// Runner
// =============================================================================

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_detects_controller_families);
    RUN_TEST(test_override_beats_detection);
    RUN_TEST(test_ready_in_auto);
    RUN_TEST(test_running_states);
    RUN_TEST(test_alarm_from_status_word);
    RUN_TEST(test_unknown_alarm_falls_back_to_last_alarm_code);
    RUN_TEST(test_service_alarm_reports_service_due);
    RUN_TEST(test_service_counter_within_an_hour_is_due);
    RUN_TEST(test_evolution2_filter_drops_garbage_status);
    RUN_TEST(test_run_log_entry);
    RUN_TEST(test_alarm_log_entry_uses_alarm_code_when_event_unknown);
    RUN_TEST(test_empty_log_slot_is_blank);
    RUN_TEST(test_exercise_schedule_text);
    RUN_TEST(test_serial_number_and_replacement);
    RUN_TEST(test_run_hours_by_cooling_type);
    RUN_TEST(test_date_from_epoch_days);
    RUN_TEST(test_firmware_version_formatting);
    RUN_TEST(test_state_scales_engine_values);
    RUN_TEST(test_air_cooled_current_and_power);
    RUN_TEST(test_remote_start_plan);
    RUN_TEST(test_exercise_plan_direct_write);
    RUN_TEST(test_exercise_plan_legacy_write_counts_128_second_steps);
    RUN_TEST(test_unsupported_commands_are_rejected);
    RUN_TEST(test_set_time_plan);
    RUN_TEST(test_outage_start_and_end);
    return UNITY_END();
}
