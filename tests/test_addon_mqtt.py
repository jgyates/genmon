#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_addon_mqtt.py
# PURPOSE: Tests for the MQTT add-ons:
#          addon/genmqtt.py publishes genmon's data to an MQTT broker and takes
#          genmon commands from it: the topics and values published (and the
#          root topic, numeric, string list, blacklist and remove spaces
#          settings), only publishing changes, the online / offline status,
#          commands, and the TLS settings.
#          addon/genmqttin.py reads sensor values from MQTT topics into genmon:
#          gauges, sensor data, fuel (tank) data and power data (current
#          transformers, power, voltage legs).
#
#          genmon, threads and the MQTT library (paho) are fakes, see
#          addon_fixture.py; no broker is needed.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_addon_mqtt
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


def fake_paho():
    """paho.mqtt.client: Client records what is published and subscribed."""
    client_module = types.ModuleType("paho.mqtt.client")
    client_module.MQTT_ERR_SUCCESS = 0
    client_module.CallbackAPIVersion = types.SimpleNamespace(VERSION1=1)

    class Client(object):
        instances = []

        def __init__(self, callback_api_version=None, client_id=None):
            self.client_id = client_id
            self.published, self.subscribed, self.calls = [], [], {}
            Client.instances.append(self)

        def __getattr__(self, name):
            # reconnect_delay_set, username_pw_set, tls_set, will_set, connect, ...
            if name.startswith("_"):
                raise AttributeError(name)

            def record(*args, **kwargs):
                self.calls[name] = (args, kwargs)
            return record

        def publish(self, topic, payload=None, qos=0, retain=False):
            self.published.append((topic, payload, retain))
            return types.SimpleNamespace(rc=0)

        def subscribe(self, topic):
            self.subscribed.append(topic)

    client_module.Client = Client
    mqtt = types.ModuleType("paho.mqtt")
    mqtt.client = client_module
    paho = types.ModuleType("paho")
    paho.mqtt = mqtt
    return {"paho": paho, "paho.mqtt": mqtt, "paho.mqtt.client": client_module}


STATUS = {"Status": [{"Engine": [{"Engine State": "Running"}, {"Battery Voltage": "13.1 V"}]},
                     {"Line": [{"Utility Voltage": "240 V"}]}]}
MAINT = {"Maintenance": [{"Model": "Test"}, {"Service": [{"Next Service": "Jan 1"}]}]}
OUTAGE = {"Outage": [{"System In Outage": "No"}]}
MONITOR = {"Monitor": [{"Generator Monitor Stats": [{"Monitor Health": "OK"}]}]}


class MQTTTestCase(unittest.TestCase):

    def start(self, **settings):
        modules = fake_paho()
        conf = {"mqtt_address": "broker.example", "mqtt_port": "1883", "root_topic": "",
                "username": "", "password": "", "blacklist": "", "numeric_json": "False",
                "numeric_json_object": "False", "strlist_json": "False", "remove_spaces": "False",
                "retain": "False", "cert_authority_path": ""}
        conf.update(settings)
        fixture = AddOnFixture("genmqtt", "MyMQTT", conf, modules=modules)
        fixture.state["answers"] = {
            "start_info_json": json.dumps({"Controller": "Evolution 2.0, Air Cooled"}),
            "status_json": json.dumps(STATUS), "maint_json": json.dumps(MAINT),
            "outage_json": json.dumps(OUTAGE), "monitor_json": json.dumps(MONITOR)}
        self.addCleanup(fixture.stop)
        fixture.start()
        self.client = modules["paho.mqtt.client"].Client.instances[-1]
        return fixture

    def poll(self, fixture):
        """One pass of the add-on's polling of genmon; the values published."""
        push = fixture.addon.Push
        before = len(self.client.published)
        with mock.patch.object(push, "WaitForExit", return_value=True):
            push.MainPollingThread()
        return {topic: value for topic, value, retain in self.client.published[before:]}


# -------------------------------------------------------------------------------
class PublishTests(MQTTTestCase):

    def test_topics_and_values(self):
        fixture = self.start()
        published = self.poll(fixture)
        self.assertEqual(published["generator/Status/Engine/Engine State"], "Running")
        self.assertEqual(published["generator/Status/Engine/Battery Voltage"], "13.1 V")
        self.assertEqual(published["generator/Status/Line/Utility Voltage"], "240 V")
        self.assertEqual(published["generator/Maintenance/Service/Next Service"], "Jan 1")
        self.assertEqual(published["generator/Outage/System In Outage"], "No")
        self.assertEqual(published["generator/Monitor/Generator Monitor Stats/Monitor Health"], "OK")

    def test_only_changes_published(self):
        fixture = self.start()
        self.poll(fixture)
        self.assertEqual(self.poll(fixture), {})
        STATUS_RUNNING = json.loads(json.dumps(STATUS))
        STATUS_RUNNING["Status"][0]["Engine"][0]["Engine State"] = "Stopped"
        fixture.state["answers"]["status_json"] = json.dumps(STATUS_RUNNING)
        self.assertEqual(self.poll(fixture), {"generator/Status/Engine/Engine State": "Stopped"})

    def test_root_topic_and_remove_spaces(self):
        fixture = self.start(root_topic="home/gen", remove_spaces="True")
        published = self.poll(fixture)
        self.assertIn("home/gen/generator/Status/Engine/Engine_State", published)

    def test_blacklist(self):
        fixture = self.start(blacklist="Maintenance, Line")
        topics = list(self.poll(fixture))
        self.assertFalse([t for t in topics if "Maintenance" in t or "/Line/" in t])
        self.assertIn("generator/Status/Engine/Engine State", topics)

    def test_list_of_strings(self):
        fixture = self.start()
        fixture.state["answers"]["outage_json"] = json.dumps(
            {"Outage": [{"Outage Log": ["11/01/26 Outage 1", "11/02/26 Outage 2"]}]})
        self.assertEqual(self.poll(fixture)["generator/Outage/Outage Log"],
                         "11/01/26 Outage 1, 11/02/26 Outage 2")

    def test_list_of_strings_as_json(self):
        fixture = self.start(strlist_json="True")
        fixture.state["answers"]["outage_json"] = json.dumps(
            {"Outage": [{"Outage Log": ["a", "b"]}]})
        self.assertEqual(self.poll(fixture)["generator/Outage/Outage Log"], '["a", "b"]')

    def test_numeric_object(self):
        # numeric_json_object: each value is published as {"type", "value", "unit"}
        fixture = self.start(numeric_json_object="True")
        value = {"type": "float", "value": 13.1, "unit": "V"}
        for name in ["status", "maint", "outage", "monitor"]:
            fixture.state["answers"][name + "_num_json"] = fixture.state["answers"][name + "_json"]
        fixture.state["answers"]["status_num_json"] = json.dumps(
            {"Status": [{"Engine": [{"Battery Voltage": value}]}]})
        published = self.poll(fixture)
        self.assertEqual(json.loads(published["generator/Status/Engine/Battery Voltage"]), value)

    def test_numeric_object_in_a_list(self):
        # a value directly in a list is published as one object (it used to
        # be split into type / value / unit topics)
        fixture = self.start(numeric_json_object="True")
        value = {"type": "int", "value": 5, "unit": ""}
        for name in ["status", "maint", "outage", "monitor"]:
            fixture.state["answers"][name + "_num_json"] = fixture.state["answers"][name + "_json"]
        fixture.state["answers"]["status_num_json"] = json.dumps({"Status": [{"Readings": [value]}]})
        published = self.poll(fixture)
        self.assertEqual(json.loads(published["generator/Status/Readings"]), value)
        self.assertNotIn("generator/Status/Readings/value", published)

    def test_retain(self):
        fixture = self.start(retain="True")
        self.poll(fixture)
        self.assertTrue(all(retain for topic, value, retain in self.client.published))


# -------------------------------------------------------------------------------
class ConnectionTests(MQTTTestCase):

    def test_connect(self):
        self.start(username="me", password="pw", mqtt_port="1884")
        self.assertEqual(self.client.calls["connect"][0], ("broker.example", 1884, 60))
        self.assertEqual(self.client.calls["username_pw_set"], (("me",), {"password": "pw"}))
        # broker shows the add-on offline if it stops
        self.assertEqual(self.client.calls["will_set"],
                         (("generator/client_status",), {"payload": "Offline", "qos": 0,
                                                         "retain": True}))
        self.assertIn("loop_start", self.client.calls)

    def test_on_connect(self):
        fixture = self.start(root_topic="home")
        fixture.addon.on_connect(self.client, None, {}, 0)
        # only commands (it subscribed to everything, receiving each value
        # it published)
        self.assertEqual(self.client.subscribed, ["home/generator/command"])
        self.assertIn(("home/generator/client_status", "Online", True), self.client.published)

    def test_on_connect_debug(self):
        # debug: everything under the root, to see what the broker received
        fixture = self.start(root_topic="home", debug="True")
        fixture.addon.on_connect(self.client, None, {}, 0)
        self.assertEqual(self.client.subscribed, ["home/generator/#"])

    def test_command(self):
        fixture = self.start(root_topic="home")
        message = types.SimpleNamespace(topic="home/generator/command", payload=b"setremote=start",
                                        retain=False)
        fixture.addon.on_message(self.client, None, message)
        self.assertIn("generator: setremote=start", fixture.genmon.commands)

    def test_retained_command(self):
        # the broker replays a retained command on every reconnect: ignore it
        # and clear it, so it does not repeat each time genmon restarts
        fixture = self.start(root_topic="home")
        before = list(fixture.genmon.commands)
        fixture.addon.on_message(self.client, None, types.SimpleNamespace(
            topic="home/generator/command", payload=b"setremote=start", retain=True))
        self.assertEqual(fixture.genmon.commands, before)
        self.assertIn(("home/generator/command", "", True), self.client.published)
        # the empty message that clears it comes back: not a command
        fixture.addon.on_message(self.client, None, types.SimpleNamespace(
            topic="home/generator/command", payload=b"", retain=False))
        self.assertEqual(fixture.genmon.commands, before)

    def test_other_topics_are_not_commands(self):
        fixture = self.start()
        before = list(fixture.genmon.commands)
        for topic in ["generator/Status/Engine/Engine State", "other/command"]:
            fixture.addon.on_message(self.client, None,
                                     types.SimpleNamespace(topic=topic, payload=b"setremote=stop",
                                                           retain=False))
        self.assertEqual(fixture.genmon.commands, before)


# -------------------------------------------------------------------------------
class TLSTests(MQTTTestCase):
    """The TLS settings; the TLS context itself is tested in test_tls.py."""

    def start_tls(self, **settings):
        folder = tempfile.mkdtemp(prefix="mqtt_tls_")
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        ca = os.path.join(folder, "ca.crt")
        open(ca, "w").close()
        # the CA file is only read by the ssl library
        with mock.patch.object(ssl.SSLContext, "load_verify_locations") as load:
            fixture = self.start(cert_authority_path=ca, **settings)
        load.assert_called_once_with(ca)
        return fixture

    def context(self):
        return self.client.calls["tls_set_context"][0][0]

    def test_tls_auto(self):
        self.start_tls(tls_version="Auto", cert_reqs="Required")
        context = self.context()
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        # the default port is changed to the MQTT TLS port
        self.assertEqual(self.client.calls["connect"][0][1], 8883)

    def test_tls_version_and_optional_certificate(self):
        self.start_tls(tls_version="1.2", cert_reqs="Optional")
        context = self.context()
        self.assertEqual((context.minimum_version, context.maximum_version),
                         (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_2))
        self.assertEqual(context.verify_mode, ssl.CERT_OPTIONAL)

    def test_tls_invalid_cert_reqs(self):
        # an unknown value: logged, and Required is used (it must not stop the add-on)
        self.start_tls(cert_reqs="Sometimes")
        self.assertEqual(self.context().verify_mode, ssl.CERT_REQUIRED)

    def test_tls_port_set_by_user(self):
        self.start_tls(mqtt_port="9883")
        self.assertEqual(self.client.calls["connect"][0][1], 9883)

    def test_no_ca_file_no_tls(self):
        self.start()
        self.assertNotIn("tls_set_context", self.client.calls)
        self.assertEqual(self.client.calls["connect"][0][1], 1883)


# -------------------------------------------------------------------------------
class MQTTInTests(unittest.TestCase):
    """genmqttin.py"""

    def start(self, sensors, **settings):
        """sensors: (topic, type, label, units, nominal, max) for each topic"""
        modules = fake_paho()
        columns = list(zip(*sensors))
        conf = {"mqtt_address": "broker.example", "mqtt_port": "1883", "root_topic": "",
                "username": "", "password": "", "cert_authority_path": "",
                "topics": ",".join(columns[0]), "types": ",".join(columns[1]),
                "labels": ",".join(columns[2]), "units": ",".join(columns[3]),
                "nominal_values": ",".join(columns[4]), "maximum_values": ",".join(columns[5]),
                "exclude_gauge": "", "strict": "False", "use_for_power_fuel": "False",
                "powerfactor": "1.0"}
        conf.update(settings)
        fixture = AddOnFixture("genmqttin", "MyMQTT", conf, modules=modules)
        fixture.state["answers"] = {
            "start_info_json": json.dumps({"Controller": "Evolution 2.0, Air Cooled"})}
        self.addCleanup(fixture.stop)
        fixture.start()
        self.client = modules["paho.mqtt.client"].Client.instances[-1]
        return fixture

    def receive(self, fixture, topic, payload):
        fixture.addon.on_message(self.client, None,
                                 types.SimpleNamespace(topic=topic, payload=payload.encode()))

    def test_gauges_and_subscriptions(self):
        fixture = self.start([("home/temp", "temperature", "Engine Temp", "F", "100", "250"),
                              ("home/fuel", "fuel", "Tank", "%", "50", "100")],
                             exclude_gauge="Tank")
        self.assertEqual(fixture.commands("generator: set_external_gauge_data="), [[
            {"title": "Engine Temp", "type": "temperature", "units": "F", "nominal": 100,
             "max": 250, "exclude_gauge": False, "from": "genmqttin", "strict": False},
            {"title": "Tank", "type": "fuel", "units": "%", "nominal": 50, "max": 100,
             "exclude_gauge": True, "from": "genmqttin", "strict": False}]])
        fixture.addon.on_connect(self.client, None, {}, 0)
        self.assertEqual(self.client.subscribed, ["home/temp", "home/fuel"])

    def test_sensor_value(self):
        fixture = self.start([("home/temp", "temperature", "Engine Temp", "F", "100", "250")])
        self.receive(fixture, "home/temp", "77.5")
        self.receive(fixture, "home/other", "1")  # not a configured topic
        self.assertEqual(fixture.commands("generator: set_sensor_data="),
                         [[{"Engine Temp": "77.5 F"}]])
        # power and fuel data only with use_for_power_fuel
        self.assertEqual(fixture.commands("generator: set_power_data="), [])

    def test_fuel(self):
        fixture = self.start([("home/fuel", "fuel", "Propane", "%", "50", "100")],
                             use_for_power_fuel="True")
        self.receive(fixture, "home/fuel", "55")
        self.receive(fixture, "home/fuel", "140")  # not a percentage
        self.assertEqual(fixture.commands("generator: set_tank_data="),
                         [{"Tank Name": "Propane", "Percentage": 55}])

    def test_power_in_watts(self):
        fixture = self.start([("home/power", "power", "Load", "W", "5000", "22000")],
                             use_for_power_fuel="True", strict="True")
        self.receive(fixture, "home/power", "4500")
        self.assertEqual(fixture.commands("generator: set_power_data="), [
            {"strict": True, "from": "genmqttin", "powerfactor": 1.0, "power": 4.5}])

    def test_current_transformers(self):
        fixture = self.start([("home/ct1", "ct1", "CT 1", "A", "20", "90"),
                              ("home/ct2", "ct2", "CT 2", "A", "20", "90")],
                             use_for_power_fuel="True")
        self.receive(fixture, "home/ct1", "12")
        self.receive(fixture, "home/ct2", "8")
        # the two are sent together, once both are known
        self.assertEqual(fixture.commands("generator: set_sensor_data=")[-1],
                         [{"CT 2": "8 A"}, {"CT 1": "12 A"}])
        power = fixture.commands("generator: set_power_data=")[-1]
        self.assertEqual((power["ctdata"], power["current"]), ([12, 8], 20))

    def test_power_transformers(self):
        fixture = self.start([("home/p1", "ctpower1", "Leg 1", "W", "5000", "22000"),
                              ("home/p2", "ctpower2", "Leg 2", "W", "5000", "22000")],
                             use_for_power_fuel="True")
        self.receive(fixture, "home/p2", "1500")  # leg 2 first: no total yet, no error
        self.receive(fixture, "home/p1", "2500")
        power = fixture.commands("generator: set_power_data=")[-1]
        self.assertEqual(power["ctpower"], [2.5, 1.5])
        self.assertEqual(power["power"], 4.0)

    def test_voltage_legs(self):
        fixture = self.start([("home/v1", "voltageleg1", "Leg 1 V", "V", "120", "140"),
                              ("home/v2", "voltageleg2", "Leg 2 V", "V", "120", "140")],
                             use_for_power_fuel="True")
        # gauges show both legs as voltage
        gauges = fixture.commands("generator: set_external_gauge_data=")[0]
        self.assertEqual([g["type"] for g in gauges], ["voltage", "voltage"])
        self.receive(fixture, "home/v1", "121")
        self.receive(fixture, "home/v2", "119")
        power = fixture.commands("generator: set_power_data=")[-1]
        self.assertEqual((power["voltagelegs"], power["voltage"]), ([121, 119], 240))

    def test_json_keys(self):
        # one Shelly Pro 3EM topic feeds four sensors
        topic = "shellypro3em400/status/em:0"
        fixture = self.start([(topic, "ct1", "Leg A Current", "A", "100", "125"),
                              (topic, "ct2", "Leg B Current", "A", "100", "125"),
                              (topic, "voltageleg1", "Leg A Voltage", "V", "120", "150"),
                              (topic, "voltageleg2", "Leg B Voltage", "V", "120", "150")],
                             json_keys="a_current,b_current,a_voltage,b_voltage",
                             use_for_power_fuel="True")
        self.assertEqual(len(fixture.commands("generator: set_external_gauge_data=")[0]), 4)
        fixture.addon.on_connect(self.client, None, {}, 0)
        self.assertEqual(self.client.subscribed, [topic])  # subscribed once
        self.receive(fixture, topic, json.dumps(
            {"id": 0, "a_current": 10.088, "a_voltage": 122.6, "b_current": 2.226,
             "b_voltage": 123.3, "n_current": None}))
        sensor = fixture.commands("generator: set_sensor_data=")
        self.assertIn([{"Leg B Current": "2.226 A"}, {"Leg A Current": "10.088 A"}], sensor)
        self.assertIn([{"Leg A Voltage": "122.6 V"}], sensor)
        self.assertIn([{"Leg B Voltage": "123.3 V"}], sensor)
        power = fixture.commands("generator: set_power_data=")[-1]
        self.assertEqual((power["ctdata"], power["voltagelegs"]), ([10, 2], [122, 123]))

    def test_json_keys_mixed_and_nested(self):
        fixture = self.start([("home/temp", "temperature", "Temp", "F", "100", "250"),
                              ("tasmota/SENSOR", "power", "Load", "W", "5000", "22000"),
                              ("z2m/plug", "current", "Plug", "A", "10", "15")],
                             json_keys=",ENERGY.Power,list.1")
        self.receive(fixture, "home/temp", "77")
        self.receive(fixture, "tasmota/SENSOR", '{"ENERGY": {"Power": "1500"}}')
        self.receive(fixture, "z2m/plug", '{"list": [1, 3.5]}')
        # missing key, null, bool and non-JSON payloads are skipped
        self.receive(fixture, "tasmota/SENSOR", '{"ENERGY": {"Voltage": 120}}')
        self.receive(fixture, "tasmota/SENSOR", '{"ENERGY": {"Power": null}}')
        self.receive(fixture, "tasmota/SENSOR", '{"ENERGY": {"Power": true}}')
        self.receive(fixture, "tasmota/SENSOR", "offline")
        self.assertEqual(fixture.commands("generator: set_sensor_data="),
                         [[{"Temp": "77 F"}], [{"Load": "1500 W"}], [{"Plug": "3.5 A"}]])

    def test_invalid_settings(self):
        for sensors, settings in [
                ([("t", "temperature", "T", "F", "1", "2")],
                 {"topics": "a,b", "types": "temperature,temperature", "labels": "A,B",
                  "units": "F,F", "nominal_values": "1,1", "maximum_values": "2,2",
                  "json_keys": "x,y,z"}),                                     # json key count
                ([("t", "humidity", "H", "%", "1", "2")], {}),            # unknown type
                ([("t", "temperature", "T", "F", "1", "2")], {"labels": "A,B"}),  # counts differ
                ([("t", "temperature", "T", "F", "1", "2")], {"topics": ""})]:   # no topics
            with self.subTest(sensors=sensors, settings=settings):
                with self.assertRaises(SystemExit):
                    self.start(sensors, **settings)


if __name__ == "__main__":
    unittest.main()
