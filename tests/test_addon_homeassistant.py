#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_addon_homeassistant.py
# PURPOSE: Tests for addon/genhomeassistant.py, which publishes genmon's data to
#          Home Assistant with MQTT discovery: the discovery messages (only
#          for data the controller has, the blacklist, the software update
#          entity, removing old entities), the states published each poll
#          (sensors, binary sensors, sensors found in the data), the commands
#          from Home Assistant (buttons, quiet mode, exercise time), Home
#          Assistant restarts and TLS.
#          Buttons follow the controller's capabilities (start_info_json).
#
#          genmon, threads and the MQTT library (paho) are fakes, see
#          addon_fixture.py and test_addon_mqtt.py; no broker is needed.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_addon_homeassistant
#
# -------------------------------------------------------------------------------

import json
import os
import shutil
import ssl
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from addon_fixture import AddOnFixture  # noqa: E402
from test_addon_mqtt import fake_paho  # noqa: E402

EVOLUTION = "Evolution 2.0, Air Cooled"


def num(value, unit="", kind="float"):
    """A value as genmon's *_num_json commands send it."""
    return {"type": kind, "value": value, "unit": unit}


STATUS = {"Status": [
    {"Engine": [{"Switch State": "Auto"}, {"Engine State": "Off - Ready"},
                {"Battery Voltage": num(13.1, "V")}, {"Frequency": num(0.0, "Hz")},
                {"Unlisted Sensor": num(5.5, "V")}]},
    {"Line": [{"Utility Voltage": num(241, "V", "int")}]},
]}
MAINT = {"Maintenance": [
    {"Model": "Test 22kW"},
    {"Exercise": [{"Exercise Time": "Weekly Sunday 16:00 Quiet Mode On"},
                  {"Quiet Mode": "On"}]},
]}
OUTAGE = {"Outage": [{"Status": "OK"}, {"System In Outage": "No"}]}
MONITOR = {"Monitor": [{"Generator Monitor Stats": [
    {"Monitor Health": "OK"}, {"Update Available": "No"}]}]}


class HomeAssistantTestCase(unittest.TestCase):

    def start(self, controller=EVOLUTION, enhanced="False", start_info=None, **settings):
        self.modules = fake_paho()
        conf = {"mqtt_address": "broker.example", "mqtt_port": "1883", "username": "",
                "password": "", "blacklist": "Tiles", "cert_authority_path": "",
                "discovery_interval": "300", "numeric_json": "True"}
        conf.update(settings)
        fixture = AddOnFixture("genhomeassistant", "MyHomeAssistant", conf, modules=self.modules)
        info = {"Controller": controller, "Model": "Test 22kW", "RemoteCommands": True,
                "RemoteTransfer": True, "SetGenTime": True, "WriteQuietMode": True,
                "ExerciseControls": True}
        info.update(start_info or {})
        fixture.state["answers"] = {
            "start_info_json": json.dumps(info),
            "status_num_json": json.dumps(STATUS), "maint_num_json": json.dumps(MAINT),
            "outage_num_json": json.dumps(OUTAGE), "monitor_num_json": json.dumps(MONITOR),
            "gui_status_json": json.dumps({
                "ExerciseInfo": {"Frequency": "Weekly", "EnhancedExerciseMode": enhanced},
                "tiles": [{"title": "CPU Temp", "value": 41.2}]}),
        }
        self.addCleanup(fixture.stop)
        fixture.start()
        self.client = self.modules["paho.mqtt.client"].Client.instances[-1]
        return fixture

    def published(self, since=0):
        """{topic: payload} published (the last one of each topic)."""
        return {topic: payload for topic, payload, retain in self.client.published[since:]}

    def discovery(self, fixture, entity_type, entity_id):
        """The discovery message published for an entity: a dict, "" if the
        entity was removed, or None if nothing was published."""
        topic = "homeassistant/%s/generator/%s/config" % (entity_type, entity_id)
        payload = self.published().get(topic)
        return json.loads(payload) if payload else payload

    def connect(self, fixture, retained=None):
        """Connected to the broker. retained: the (topic, payload) messages the
        broker sends while the add-on waits after subscribing."""
        def wait(seconds):
            for topic, payload in retained or []:
                self.message(fixture, topic, payload)

        with mock.patch.object(fixture.module.time, "sleep", side_effect=wait):
            fixture.addon._on_connect(self.client, None, {}, 0)

    def poll(self, fixture):
        """One pass of the polling thread: the states published."""
        before = len(self.client.published)
        fixture.run_thread("PollingThread", waits=[False])
        return self.published(before)

    def message(self, fixture, topic, payload):
        before = len(fixture.genmon.commands)
        fixture.addon._on_message(self.client, None, types.SimpleNamespace(
            topic=topic, payload=payload.encode("utf-8")))
        return fixture.genmon.commands[before:]


# -------------------------------------------------------------------------------
class DiscoveryTests(HomeAssistantTestCase):

    def test_connect(self):
        fixture = self.start()
        self.assertEqual(self.client.calls["connect"][0], ("broker.example", 1883, 60))
        self.assertEqual(self.client.calls["will_set"][0], ("genmon/status",))
        self.connect(fixture)
        for topic in ["homeassistant/+/generator/+/config", "homeassistant/status",
                      "genmon/+/+/set", "genmon/+/+/command"]:
            self.assertIn(topic, self.client.subscribed)
        self.assertEqual(self.published()["genmon/status"], "online")

    def test_sensor(self):
        fixture = self.start()
        self.connect(fixture)
        config = self.discovery(fixture, "sensor", "battery_voltage")
        self.assertEqual(config["state_topic"], "genmon/sensor/battery_voltage/state")
        self.assertEqual(config["unit_of_measurement"], "V")
        self.assertEqual(config["device_class"], "voltage")
        self.assertEqual(config["unique_id"], "genmon_generator_battery_voltage")
        self.assertEqual(config["device"]["model"], "Test 22kW")

    def test_only_sensors_with_data(self):
        # Power Leg 1 is defined for Evolution, but this generator does not report it
        fixture = self.start()
        self.connect(fixture)
        self.assertIsNone(self.discovery(fixture, "sensor", "power_leg1"))
        self.assertIsNotNone(self.discovery(fixture, "sensor", "utility_voltage"))

    def test_binary_sensors_buttons_and_switches(self):
        fixture = self.start()
        self.connect(fixture)
        self.assertEqual(self.discovery(fixture, "binary_sensor", "generator_running")["payload_on"], "ON")
        self.assertEqual(self.discovery(fixture, "button", "start")["command_topic"],
                         "genmon/button/start/command")
        self.assertEqual(self.discovery(fixture, "switch", "quiet_mode")["command_topic"],
                         "genmon/switch/quiet_mode/set")

    def test_controller_specific(self):
        # Service A Due is for Evolution only, the oil service for Nexus only
        fixture = self.start(controller="Nexus, Air Cooled")
        self.assertFalse(fixture.addon._entity_allowed(
            fixture.addon.SensorDefinitions["service_a_due"], "service_a_due"))
        self.assertTrue(fixture.addon._entity_allowed(
            fixture.addon.SensorDefinitions["oil_service"], "oil_service"))

    def test_blacklist(self):
        fixture = self.start(blacklist="battery, Line")
        self.connect(fixture)
        self.assertIsNone(self.discovery(fixture, "sensor", "battery_voltage"))
        self.assertIsNone(self.discovery(fixture, "sensor", "utility_voltage"))
        self.assertIsNotNone(self.discovery(fixture, "sensor", "engine_state"))

    def test_software_update(self):
        fixture = self.start()
        fixture.state["answers"]["monitor_num_json"] = json.dumps({"Monitor": [
            {"Generator Monitor Stats": [{"Update Available": "Yes"},
                                         {"Update Version": "9.9.9"}]}]})
        self.connect(fixture)
        self.assertEqual(self.discovery(fixture, "update", "genmon_software")["payload_install"],
                         "INSTALL")
        state = json.loads(self.published()["genmon/update/genmon_software/state"])
        self.assertEqual(state["latest_version"], "9.9.9")
        self.assertFalse(state["in_progress"])

    def test_old_entities_removed(self):
        # entities from an earlier version (retained on the broker) are removed
        fixture = self.start()
        self.connect(fixture, retained=[
            ("homeassistant/sensor/generator/old_sensor/config", '{"name": "Old"}'),
            ("homeassistant/sensor/generator/battery_voltage/config", '{"name": "x"}')])
        self.assertEqual(self.published()["homeassistant/sensor/generator/old_sensor/config"], "")
        self.assertNotEqual(self.discovery(fixture, "sensor", "battery_voltage"), "")

    def test_home_assistant_restart(self):
        # Home Assistant's birth message: discovery is published again
        fixture = self.start()
        self.connect(fixture)
        before = len(self.client.published)
        self.message(fixture, "homeassistant/status", "online")
        self.assertIn("homeassistant/sensor/generator/battery_voltage/config", self.published(before))
        before = len(self.client.published)
        self.message(fixture, "homeassistant/status", "offline")
        self.assertEqual(self.published(before), {})


# -------------------------------------------------------------------------------
class StateTests(HomeAssistantTestCase):

    def test_sensor_states(self):
        fixture = self.start()
        states = self.poll(fixture)
        self.assertEqual(states["genmon/sensor/battery_voltage/state"], "13.1")
        self.assertEqual(states["genmon/sensor/utility_voltage/state"], "241")
        self.assertEqual(states["genmon/sensor/engine_state/state"], "Off - Ready")
        self.assertEqual(states["genmon/sensor/exercise_time/state"],
                         "Weekly Sunday 16:00 Quiet Mode On")

    def test_binary_sensor_states(self):
        fixture = self.start()
        states = self.poll(fixture)
        self.assertEqual(states["genmon/binary_sensor/generator_running/state"], "OFF")
        self.assertEqual(states["genmon/binary_sensor/system_in_outage/state"], "OFF")
        self.assertEqual(states["genmon/binary_sensor/utility_present/state"], "ON")
        self.assertEqual(states["genmon/binary_sensor/switch_in_auto/state"], "ON")
        self.assertEqual(states["genmon/binary_sensor/transfer_to_generator/state"], "OFF")
        # no alarm value from genmon: not in alarm (not "unknown")
        self.assertEqual(states["genmon/binary_sensor/alarm_active/state"], "OFF")
        self.assertEqual(states["genmon/switch/quiet_mode/state"], "ON")

    def test_only_changes_published(self):
        fixture = self.start()
        self.poll(fixture)
        status = json.loads(json.dumps(STATUS))
        status["Status"][0]["Engine"][1]["Engine State"] = "Running"
        fixture.state["answers"]["status_num_json"] = json.dumps(status)
        states = self.poll(fixture)
        self.assertEqual(states["genmon/sensor/engine_state/state"], "Running")
        self.assertEqual(states["genmon/binary_sensor/generator_running/state"], "ON")
        self.assertNotIn("genmon/sensor/battery_voltage/state", states)

    def test_sensor_found_in_the_data(self):
        # a value with no entity definition becomes a sensor of its own
        fixture = self.start()
        states = self.poll(fixture)
        entity_id = "status_engine_unlisted_sensor"
        self.assertEqual(states["genmon/sensor/%s/state" % entity_id], "5.5")
        config = self.discovery(fixture, "sensor", entity_id)
        self.assertEqual((config["unit_of_measurement"], config["device_class"]), ("V", "voltage"))

    def test_sensor_found_in_the_data_blacklisted(self):
        fixture = self.start(blacklist="unlisted")
        states = self.poll(fixture)
        self.assertNotIn("genmon/sensor/status_engine_unlisted_sensor/state", states)

    def test_exercise_settings(self):
        fixture = self.start()
        states = self.poll(fixture)
        self.assertEqual(states["genmon/select/exercise_day_of_week/state"], "Sunday")
        self.assertEqual(states["genmon/number/exercise_hour/state"], "16")
        self.assertEqual(states["genmon/number/exercise_minute/state"], "0")

    def test_exercise_time_from_genmon(self):
        # as generac_evolution.py GetExerciseTime writes them
        fixture = self.start(enhanced="True")
        for text, expected in [
                ("Weekly Saturday 13:30 Quiet Mode On", ("Weekly", "Saturday", 1, 13, 30)),
                ("Biweekly Monday 07:05 Quiet Mode Off", ("BiWeekly", "Monday", 1, 7, 5)),
                ("Monthly Day-15 09:00 Quiet Mode Off", ("Monthly", "Monday", 15, 9, 0)),
                ("Monthly Day 20 10:15 Quiet Mode Off", ("Monthly", "Monday", 20, 10, 15))]:
            with self.subTest(text=text):
                fixture.addon._parse_exercise_time(text)
                settings = fixture.addon.ExerciseSettings
                self.assertEqual((settings["frequency"], settings["day_of_week"],
                                  settings["day_of_month"], settings["hour"], settings["minute"]),
                                 expected)


# -------------------------------------------------------------------------------
class CommandTests(HomeAssistantTestCase):

    def test_buttons(self):
        fixture = self.start()
        self.assertEqual(self.message(fixture, "genmon/button/start/command", "PRESS"),
                         ["generator: setremote=START"])
        self.assertEqual(self.message(fixture, "genmon/button/set_generator_time/command", "PRESS"),
                         ["generator: settime"])
        self.assertEqual(self.message(fixture, "genmon/button/nothing/command", "PRESS"), [])

    def test_buttons_by_capability(self):
        # e.g. an Evolution with a SmartSwitch: no remote start, stop or
        # transfer; and a controller whose clock cannot be set
        fixture = self.start(start_info={"RemoteCommands": False, "RemoteTransfer": False,
                                         "SetGenTime": False})
        self.connect(fixture)
        for button in ["start", "stop", "start_transfer", "set_generator_time"]:
            with self.subTest(button=button):
                self.assertEqual(self.discovery(fixture, "button", button), "")
                self.assertEqual(self.message(fixture, "genmon/button/%s/command" % button, "PRESS"), [])
        self.assertIsInstance(self.discovery(fixture, "button", "start_exercise"), dict)

    def test_transfer_without_remote_transfer(self):
        # H-100 without an HTS transfer switch: start and stop, but no transfer
        fixture = self.start(controller="H-100 Controller", start_info={"RemoteTransfer": False})
        self.connect(fixture)
        self.assertIsInstance(self.discovery(fixture, "button", "start"), dict)
        self.assertEqual(self.discovery(fixture, "button", "start_transfer"), "")

    def test_quiet_mode(self):
        fixture = self.start()
        self.assertEqual(self.message(fixture, "genmon/switch/quiet_mode/set", "OFF"),
                         ["generator: setquiet=off"])
        self.assertEqual(self.published()["genmon/switch/quiet_mode/state"], "OFF")

    def test_exercise_day_and_time(self):
        fixture = self.start()
        self.message(fixture, "genmon/number/exercise_hour/set", "9")
        self.message(fixture, "genmon/number/exercise_minute/set", "5")
        self.assertEqual(self.message(fixture, "genmon/select/exercise_day_of_week/set", "Tuesday"),
                         ["generator: setexercise=Tuesday,09:05,Weekly"])

    def test_invalid_exercise_values(self):
        fixture = self.start()
        self.assertEqual(self.message(fixture, "genmon/number/exercise_hour/set", "24"), [])
        self.assertEqual(self.message(fixture, "genmon/number/exercise_hour/set", "noon"), [])
        self.assertEqual(self.message(fixture, "genmon/select/exercise_day_of_week/set", "Someday"), [])

    def test_without_enhanced_exercise(self):
        # weekly only: no frequency or day of month in Home Assistant
        fixture = self.start(enhanced="False")
        self.assertFalse(fixture.addon.EnhancedExerciseMode)
        self.connect(fixture)
        self.assertEqual(self.discovery(fixture, "select", "exercise_frequency"), "")
        self.assertEqual(self.discovery(fixture, "number", "exercise_day_of_month"), "")
        self.assertEqual(self.message(fixture, "genmon/select/exercise_frequency/set", "Monthly"),
                         ["generator: setexercise=Sunday,12:00,Weekly"])

    def test_enhanced_exercise(self):
        # Evolution with enhanced exercise on (genmon.conf enhancedexercise):
        # biweekly and monthly
        fixture = self.start(enhanced="True")
        self.assertTrue(fixture.addon.EnhancedExerciseMode)
        self.connect(fixture)
        self.assertEqual(self.discovery(fixture, "select", "exercise_frequency")["options"],
                         ["Weekly", "BiWeekly", "Monthly"])
        self.assertIsInstance(self.discovery(fixture, "number", "exercise_day_of_month"), dict)
        self.message(fixture, "genmon/number/exercise_day_of_month/set", "15")
        self.assertEqual(self.message(fixture, "genmon/select/exercise_frequency/set", "Monthly"),
                         ["generator: setexercise=15,12:00,Monthly"])
        self.assertEqual(self.message(fixture, "genmon/select/exercise_frequency/set", "BiWeekly"),
                         ["generator: setexercise=Sunday,12:00,BiWeekly"])

    def test_no_exercise_controls(self):
        fixture = self.start(start_info={"ExerciseControls": False})
        self.connect(fixture)
        self.assertEqual(self.discovery(fixture, "select", "exercise_day_of_week"), "")
        self.assertEqual(self.discovery(fixture, "number", "exercise_hour"), "")

    def test_custom_controller_buttons(self):
        # buttons from the controller's own definitions (custom_controller.py),
        # with the passcode from the settings where the button asks for one
        sequence = [{"reg": "0010", "input_title": "Passcode", "type": "int"},
                    {"reg": "0011", "value": "0001"}]
        fixture = self.start(
            controller="MEBAY DC Series", button_passcode="1234",
            start_info={"import_config_file": "MEBAY_DCxx.json", "buttons": [
                {"onewordcommand": "Start", "title": "Start Generator",
                 "command_sequence": sequence}]})
        self.assertEqual(list(fixture.addon.ButtonDefinitions), ["start"])
        commands = self.message(fixture, "genmon/button/start/command", "PRESS")
        prefix = "generator: set_button_command="
        self.assertTrue(commands[0].startswith(prefix))
        sent = json.loads(commands[0][len(prefix):])
        self.assertEqual(sent[0]["onewordcommand"], "Start")
        self.assertEqual([c.get("value") for c in sent[0]["command_sequence"]], ["1234", "0001"])
        # the definition itself does not keep the passcode
        self.assertNotIn("value", fixture.addon.ButtonDefinitions["start"]["command_sequence"][0])

    def test_update(self):
        fixture = self.start()
        with mock.patch.object(fixture.module.threading, "Thread") as thread:
            self.message(fixture, "genmon/update/genmon_software/command", "INSTALL")
        thread.return_value.start.assert_called_once_with()
        self.assertTrue(json.loads(self.published()["genmon/update/genmon_software/state"])["in_progress"])
        result = types.SimpleNamespace(returncode=1, stderr="no network")
        with mock.patch.object(fixture.module.subprocess, "run", return_value=result) as run, \
                mock.patch.object(fixture.module.subprocess, "Popen") as restart:
            fixture.addon._run_update()
        self.assertEqual(run.call_args[0][0][2:], ["-u", "-n"])
        restart.assert_not_called()
        self.assertFalse(fixture.addon.UpdateInProgress)


# -------------------------------------------------------------------------------
class TLSTests(HomeAssistantTestCase):

    def test_tls(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        ca_file = os.path.join(folder, "ca.crt")
        open(ca_file, "w").close()
        with mock.patch("ssl.SSLContext.load_verify_locations"):
            self.start(cert_authority_path=ca_file, tls_version="Auto", cert_reqs="Required")
        context = self.client.calls["tls_set_context"][0][0]
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(self.client.calls["connect"][0], ("broker.example", 8883, 60))


if __name__ == "__main__":
    unittest.main()
