#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_addon_mqtt.py
# PURPOSE: Tests for addon/genmqtt.py, which publishes genmon's data to an MQTT
#          broker and takes genmon commands from it: the topics and values
#          published (and the root topic, numeric, string list, blacklist and
#          remove spaces settings), only publishing changes, the online /
#          offline status, commands, and the TLS settings.
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
        self.assertEqual(self.client.subscribed, ["home/generator/#"])
        self.assertIn(("home/generator/client_status", "Online", True), self.client.published)

    def test_command(self):
        fixture = self.start(root_topic="home")
        message = types.SimpleNamespace(topic="home/generator/command", payload=b"setremote=start")
        fixture.addon.on_message(self.client, None, message)
        self.assertIn("generator: setremote=start", fixture.genmon.commands)

    def test_other_topics_are_not_commands(self):
        fixture = self.start()
        before = list(fixture.genmon.commands)
        for topic in ["generator/Status/Engine/Engine State", "other/command"]:
            fixture.addon.on_message(self.client, None,
                                     types.SimpleNamespace(topic=topic, payload=b"setremote=stop"))
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

if __name__ == "__main__":
    unittest.main()
