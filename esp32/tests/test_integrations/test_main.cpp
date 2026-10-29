// =============================================================================
// test_integrations - genmon JSON reports, Home Assistant and genmqtt rules
// =============================================================================
//
// These pin the behaviour existing integrations depend on: report paths,
// entity ids, state strings and discovery topics as upstream produces them.

// =============================================================================
// Includes
// =============================================================================

#include <unity.h>

#include <ArduinoJson.h>

#include <algorithm>
#include <string>

#include "controller_info.h"
#include "ha_catalog.h"
#include "ha_discovery.h"
#include "ha_values.h"
#include "mqtt_flatten.h"
#include "report_builder.h"

using namespace genmon;


// =============================================================================
// Fixtures
// =============================================================================

void setUp() {}
void tearDown() {}


EntityCatalog builtInCatalog() {
    std::vector<std::string> errors;
    EntityCatalog            catalog = loadBuiltInCatalog(errors);
    TEST_ASSERT_EQUAL(0, errors.size());
    return catalog;
}


template <typename Definition>
const Definition& findEntity(const std::vector<Definition>& list, const char* id) {
    const auto found = std::find_if(list.begin(), list.end(), [id](const Definition& d) { return d.id == id; });
    TEST_ASSERT_TRUE_MESSAGE(found != list.end(), id);
    return *found;
}


GeneratorState runningState() {
    GeneratorState state;
    state.valid        = true;
    state.switchState  = "Auto";
    state.engineState  = "Running";
    state.batteryVolts = 13.7;
    state.rpm          = 3600;
    state.frequencyHz  = 60.1;
    state.utilityVolts = 0;
    state.exercise     = "Weekly Saturday 13:30 Quiet Mode On";
    return state;
}


// =============================================================================
// Reports
// =============================================================================

void test_status_report_numeric_shape() {
    JsonDocument   document;
    ControllerInfo info = detectController(0x09, Detect::Auto, Detect::Auto, false, false);
    buildStatusReport(document.to<JsonObject>(), runningState(), GeneratorLogs{}, OutageView{}, info, MonitorInfo{}, true);

    JsonVariantConst battery = valueAtPath(document.as<JsonVariantConst>(), "Status/Engine/Battery Voltage");
    TEST_ASSERT_EQUAL_STRING("V", battery["unit"]);
    TEST_ASSERT_EQUAL_STRING("float", battery["type"]);
    TEST_ASSERT_EQUAL_DOUBLE(13.7, battery["value"].as<double>());

    JsonVariantConst rpm = valueAtPath(document.as<JsonVariantConst>(), "Status/Engine/RPM");
    TEST_ASSERT_EQUAL_STRING("int", rpm["type"]);
}


void test_status_report_text_values() {
    JsonDocument   document;
    ControllerInfo info = detectController(0x09, Detect::Auto, Detect::Auto, false, false);
    buildStatusReport(document.to<JsonObject>(), runningState(), GeneratorLogs{}, OutageView{}, info, MonitorInfo{}, false);
    TEST_ASSERT_EQUAL_STRING("13.70 V",
                             valueAtPath(document.as<JsonVariantConst>(), "Status/Engine/Battery Voltage").as<const char*>());
}


void test_duration_formatting_matches_python_timedelta() {
    TEST_ASSERT_EQUAL_STRING("0:05:00", formatDuration(300).c_str());
    TEST_ASSERT_EQUAL_STRING("1 day, 2:03:04", formatDuration(93784).c_str());
}


// =============================================================================
// Home Assistant
// =============================================================================

void test_built_in_definitions_load() {
    const EntityCatalog catalog = builtInCatalog();
    const SensorDefinition& battery = findEntity(catalog.sensors, "battery_voltage");
    TEST_ASSERT_EQUAL_STRING("Status/Engine/Battery Voltage", battery.path.c_str());
    findEntity(catalog.buttons, "start");
    findEntity(catalog.switches, "quiet_mode");
}


void test_sensor_states_match_python_str() {
    JsonDocument   document;
    SensorDefinition sensor;
    sensor.stateClass = "measurement";

    document["value"] = 13.7;   document["type"] = "float"; document["unit"] = "V";
    TEST_ASSERT_EQUAL_STRING("13.7", sensorState(document.as<JsonVariantConst>(), sensor)->c_str());

    document["value"] = 12.0;
    TEST_ASSERT_EQUAL_STRING("12.0", sensorState(document.as<JsonVariantConst>(), sensor)->c_str());

    document["value"] = 240;    document["type"] = "int";
    TEST_ASSERT_EQUAL_STRING("240", sensorState(document.as<JsonVariantConst>(), sensor)->c_str());
}


void test_sensor_text_rules() {
    JsonDocument     document;
    SensorDefinition numeric;
    numeric.deviceClass = "voltage";
    SensorDefinition text;

    document["v"] = "238 V";
    TEST_ASSERT_EQUAL_STRING("238", sensorState(document["v"], numeric)->c_str());
    document["v"] = "10/29/2026 14:05:00";
    TEST_ASSERT_EQUAL_STRING("10/29/2026 14:05:00", sensorState(document["v"], numeric)->c_str());
    document["v"] = "Running";
    TEST_ASSERT_EQUAL_STRING("Running", sensorState(document["v"], text)->c_str());
    document["v"] = "unknown";
    TEST_ASSERT_FALSE(sensorState(document["v"], text).has_value());
}


void test_binary_sensor_rules() {
    const EntityCatalog catalog = builtInCatalog();
    JsonDocument        document;

    const auto& running = findEntity(catalog.binarySensors, "generator_running");
    document["v"] = "Running";
    TEST_ASSERT_EQUAL_STRING("ON", binarySensorState(document["v"], running).c_str());
    document["v"] = "Off - Ready";
    TEST_ASSERT_EQUAL_STRING("OFF", binarySensorState(document["v"], running).c_str());

    const auto& autoSwitch = findEntity(catalog.binarySensors, "switch_in_auto");
    document["v"] = "Auto";
    TEST_ASSERT_EQUAL_STRING("ON", binarySensorState(document["v"], autoSwitch).c_str());
    document["v"] = "Manual";
    TEST_ASSERT_EQUAL_STRING("OFF", binarySensorState(document["v"], autoSwitch).c_str());

    const auto& transfer = findEntity(catalog.binarySensors, "transfer_to_generator");
    document["n"]["unit"] = "Hz"; document["n"]["type"] = "float"; document["n"]["value"] = 60.1;
    TEST_ASSERT_EQUAL_STRING("ON", binarySensorState(document["n"], transfer).c_str());

    const auto& outage = findEntity(catalog.binarySensors, "system_in_outage");
    document["v"] = "Yes";
    TEST_ASSERT_EQUAL_STRING("ON", binarySensorState(document["v"], outage).c_str());
}


void test_path_to_entity_id() {
    TEST_ASSERT_EQUAL_STRING("status_engine_battery_voltage", pathToEntityId("Status/Engine/Battery Voltage").c_str());
    TEST_ASSERT_EQUAL_STRING("status_engine_output_power_single_phase",
                             pathToEntityId("Status/Engine/Output Power (Single Phase)").c_str());
}


void test_dynamic_sensors() {
    JsonDocument document;
    deserializeJson(document,
        R"({"Maintenance":[{"Controller Settings":[{"Gain":{"unit":"","type":"int","value":3}}]},
                           {"Exercise":[{"Exercise Duration":"30 min"}]}],
            "Outage":[{"Outage Log":[{"0":[{"Date":"10-29-2026 14:05:00"}]},{"1":[{"Date":"10-01-2026 01:00:00"}]}]}]})");

    const std::vector<SensorDefinition> sensors = discoverDynamicSensors(document.as<JsonVariantConst>(), builtInCatalog());
    auto has = [&](const char* id) {
        return std::any_of(sensors.begin(), sensors.end(), [id](const SensorDefinition& s) { return s.id == id; });
    };
    TEST_ASSERT_TRUE(has("maintenance_exercise_exercise_duration"));
    TEST_ASSERT_TRUE(has("outage_outage_log_0_date"));
    TEST_ASSERT_FALSE(has("outage_outage_log_1_date"));
    TEST_ASSERT_FALSE(has("maintenance_controller_settings_gain"));

    const auto& date = findEntity(sensors, "outage_outage_log_0_date");
    TEST_ASSERT_EQUAL_STRING("Last Outage Date", date.name.c_str());
}


void test_blacklist_and_controller_filters() {
    EntityPolicy policy;
    policy.controllerType = "evolution";
    EntityFilter nexusOnly;
    nexusOnly.controllers = {"nexus"};

    TEST_ASSERT_FALSE(entityAllowed("cpu_temp", "CPU Temperature", "Tiles/CPU Temp/value", EntityFilter{}, policy));
    TEST_ASSERT_FALSE(entityAllowed("oil_service", "Oil", "Maintenance/Service/Oil", nexusOnly, policy));
    TEST_ASSERT_TRUE(entityAllowed("rpm", "RPM", "Status/Engine/RPM", EntityFilter{}, policy));
}


void test_sensor_discovery_topic_and_ids() {
    const EntityCatalog    catalog = builtInCatalog();
    HaDevice               device;
    const DiscoveryMessage message = sensorDiscovery(findEntity(catalog.sensors, "battery_voltage"), device);

    TEST_ASSERT_EQUAL_STRING("homeassistant/sensor/generator/battery_voltage/config", message.topic.c_str());
    JsonDocument payload;
    deserializeJson(payload, message.payload);
    TEST_ASSERT_EQUAL_STRING("genmon_generator_battery_voltage", payload["unique_id"]);
    TEST_ASSERT_EQUAL_STRING("genmon/sensor/battery_voltage/state", payload["state_topic"]);
    TEST_ASSERT_EQUAL_STRING("genmon/status", payload["availability_topic"]);
    TEST_ASSERT_EQUAL_STRING("genmon_generator", payload["device"]["identifiers"][0]);
}


void test_quiet_switch_removed_without_capability() {
    const EntityCatalog catalog = builtInCatalog();
    HaCapabilities      caps;
    caps.writeQuietMode = false;
    const DiscoveryMessage message = switchDiscovery(findEntity(catalog.switches, "quiet_mode"), HaDevice{}, caps);
    TEST_ASSERT_TRUE(message.payload.empty());
}


void test_exercise_controls_round_trip() {
    ExerciseSettings settings;
    parseExerciseTime("Weekly Saturday 13:30 Quiet Mode On", settings);
    TEST_ASSERT_EQUAL_STRING("Saturday", settings.dayOfWeek.c_str());
    TEST_ASSERT_EQUAL(13, settings.hour);
    TEST_ASSERT_EQUAL(30, settings.minute);

    settings.frequency = "Monthly";
    TEST_ASSERT_EQUAL_STRING("setexercise=Saturday,13:30,Weekly", exerciseCommand(settings, false).c_str());
}


// =============================================================================
// genmqtt
// =============================================================================

void test_flatten_matches_genmqtt_topics() {
    JsonDocument document;
    deserializeJson(document,
        R"({"Status":[{"Engine":[{"Battery Voltage":"13.70 V"},{"Switch State":"Auto"}]}],
            "Logs":{"Run Log":["a","b"]}})");

    const std::vector<TopicValue> topics = flattenReports(document.as<JsonVariantConst>(), "generator", FlattenOptions{});
    TEST_ASSERT_EQUAL(3, topics.size());
    TEST_ASSERT_EQUAL_STRING("generator/Status/Engine/Battery Voltage", topics[0].topic.c_str());
    TEST_ASSERT_EQUAL_STRING("13.70 V", topics[0].value.c_str());
    TEST_ASSERT_EQUAL_STRING("generator/Logs/Run Log", topics[2].topic.c_str());
    TEST_ASSERT_EQUAL_STRING("a, b", topics[2].value.c_str());
}


// =============================================================================
// Runner
// =============================================================================

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_status_report_numeric_shape);
    RUN_TEST(test_status_report_text_values);
    RUN_TEST(test_duration_formatting_matches_python_timedelta);
    RUN_TEST(test_built_in_definitions_load);
    RUN_TEST(test_sensor_states_match_python_str);
    RUN_TEST(test_sensor_text_rules);
    RUN_TEST(test_binary_sensor_rules);
    RUN_TEST(test_path_to_entity_id);
    RUN_TEST(test_dynamic_sensors);
    RUN_TEST(test_blacklist_and_controller_filters);
    RUN_TEST(test_sensor_discovery_topic_and_ids);
    RUN_TEST(test_quiet_switch_removed_without_capability);
    RUN_TEST(test_exercise_controls_round_trip);
    RUN_TEST(test_flatten_matches_genmqtt_topics);
    return UNITY_END();
}
