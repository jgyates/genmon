#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_addon_halink.py
# PURPOSE: Tests for addon/genhalink.py (Home Assistant integration) and
#          addon/genhubitat.py (Hubitat), which serve genmon's data over a
#          REST and WebSocket API: polling genmon (state, blacklist, CPU
#          temperature, sensors found in the data), the API key, the entity
#          list (by controller and capabilities, only entities with data),
#          commands, the WebSocket (authentication, full state, updates,
#          commands), waiting for genmon to finish starting and
#          the self-signed TLS certificate.
#
#          genmon and threads are fakes, see addon_fixture.py. The API runs
#          in the test with aiohttp's test server (no port is opened to the
#          network).
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_addon_halink
#
# -------------------------------------------------------------------------------

import asyncio
import json
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from addon_fixture import AddOnFixture  # noqa: E402

try:
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
except ImportError:  # see tests/requirements.txt
    web = None

EVOLUTION = "Evolution 2.0, Air Cooled"
API_KEY = "test-api-key"


def num(value, unit="", kind="float"):
    """A value as genmon's *_num_json commands send it."""
    return {"type": kind, "value": value, "unit": unit}


STATUS = {"Status": [
    {"Engine": [{"Switch State": "Auto"}, {"Engine State": "Off - Ready"},
                {"Battery Voltage": num(13.1, "V")}, {"Unlisted Sensor": num(5.5, "V")}]},
    {"Line": [{"Utility Voltage": num(241, "V", "int")}]},
]}
MAINT = {"Maintenance": [{"Model": "Test 22kW"}]}
OUTAGE = {"Outage": [{"System In Outage": "No"}, {"Utility Voltage": num(241, "V", "int")}]}


def monitor(health="OK"):
    return {"Monitor": [{"Generator Monitor Stats": [{"Monitor Health": health}]}]}


# -------------------------------------------------------------------------------
class LinkTests(object):
    """Tests for both add-ons (genhubitat.py is a copy of genhalink.py)."""

    MODULE = CLASS = POLL_THREAD = None

    def start(self, start_info=None, health="OK", **settings):
        conf = {"api_key": API_KEY, "blacklist": "", "use_https": "False",
                "zeroconf_enabled": "False"}
        conf.update(settings)
        fixture = AddOnFixture(self.MODULE, self.CLASS, conf)
        info = {"Controller": EVOLUTION, "RemoteCommands": True, "ExerciseControls": True,
                "SetGenTime": True, "RemoteTransfer": True, "WriteQuietMode": True}
        info.update(start_info or {})
        fixture.state["answers"] = {
            "start_info_json": json.dumps(info),
            "status_num_json": json.dumps(STATUS), "maint_num_json": json.dumps(MAINT),
            "outage_num_json": json.dumps(OUTAGE), "monitor_num_json": json.dumps(monitor(health)),
            "gui_status_json": json.dumps({"PlatformStats": {"CPU Temperature": "28.70 C"}}),
        }
        self.addCleanup(fixture.stop)
        fixture.start()
        self.fixture, self.addon = fixture, fixture.addon
        return fixture

    async def client(self):
        """The add-on's API (the routes of its _server_thread)."""
        self.addon._loop = asyncio.get_running_loop()
        app = web.Application()
        app.router.add_get("/api/health", self.addon._handle_health)
        app.router.add_get("/api/info", self.addon._handle_info)
        app.router.add_get("/api/status", self.addon._handle_status)
        app.router.add_get("/api/entities", self.addon._handle_entities)
        app.router.add_post("/api/command", self.addon._handle_command)
        app.router.add_get("/ws", self.addon._handle_ws)
        client = TestClient(TestServer(app))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        return client

    def auth(self, key=API_KEY):
        return {"Authorization": "Bearer " + key}

    async def entities(self, client):
        response = await client.get("/api/entities", headers=self.auth())
        self.assertEqual(response.status, 200)
        result = await response.json()
        return {category: {e["entity_id"]: e for e in result[category]}
                for category in ["sensors", "binary_sensors", "buttons", "switches"]}, result

    # ---------- polling --------------------------------------------------------
    def test_poll(self):
        self.start()
        self.addon._poll_genmon()
        values = self.addon.LastValues
        self.assertEqual(values["Status/Engine/Battery Voltage"], "13.1 V")
        self.assertEqual(values["Status/Engine/Engine State"], "Off - Ready")
        self.assertEqual(values["Maintenance/Model"], "Test 22kW")
        self.assertEqual(self.addon.CurrentState["Status"]["Line"]["Utility Voltage"]["value"], 241)

    def test_poll_thread(self):
        fixture = self.start()
        fixture.run_thread(self.POLL_THREAD, waits=[False])
        self.assertIn("Status/Engine/Battery Voltage", self.addon.LastValues)

    def test_blacklist(self):
        self.start(blacklist="Line, model")
        self.addon._poll_genmon()
        self.assertNotIn("Line", self.addon.CurrentState["Status"])
        self.assertNotIn("Maintenance/Model", self.addon.LastValues)
        self.assertIn("Status/Engine/Battery Voltage", self.addon.LastValues)

    def test_monitor_stats_off(self):
        self.start(include_monitor_stats="False")
        self.addon._poll_genmon()
        self.assertNotIn("Monitor", self.addon.CurrentState)

    def test_cpu_temperature(self):
        # kept under Tiles/ even with "Tiles" in the blacklist, with a degree sign
        self.start(blacklist="Tiles")
        self.addon._poll_genmon()
        self.assertEqual(self.addon.LastValues["Tiles/CPU Temp/value"], "28.70 °C")

    def test_cpu_temperature_blacklisted(self):
        self.start(blacklist="CPU Temp")
        self.addon._poll_genmon()
        self.assertNotIn("Tiles/CPU Temp/value", self.addon.LastValues)

    def test_api_key_made(self):
        from genmonlib.myconfig import MyConfig

        fixture = self.start(api_key="")
        self.assertEqual(len(self.addon.ApiKey), 36)
        config = MyConfig(filename=os.path.join(fixture.folder, self.MODULE + ".conf"),
                          section=self.MODULE)
        self.assertEqual(config.ReadValue("api_key"), self.addon.ApiKey)

    def test_controller_types(self):
        self.start()
        cls = type(self.addon)
        for controller, expected_type, expected_file in [
                ("Evolution 2.0, Liquid Cooled", "evolution", "generac_evo_nexus.json"),
                ("Nexus, Air Cooled", "nexus", "generac_evo_nexus.json"),
                ("H-100 Controller", "h-100", "h_100.json"),
                ("Briggs & Stratton GC-1032", "Briggs_Stratton_GC-1032", "Briggs_Stratton_GC-1032.json"),
                ("Something Else", "custom", "custom.json")]:
            with self.subTest(controller=controller):
                self.assertEqual(cls._normalize_controller_type(controller), expected_type)
                self.assertEqual(self.addon._get_controller_filename(controller), expected_file)
        self.assertTrue(cls._matches_controller({"controllers": ["custom"]}, "ComAp"))
        self.assertFalse(cls._matches_controller({"controllers": ["custom"]}, "nexus"))

    def test_cpu_temperature_from_the_tile(self):
        # not a Raspberry Pi: no PlatformStats, the CPU Temp tile has the value
        fixture = self.start()
        fixture.state["answers"]["gui_status_json"] = json.dumps(
            {"tiles": [{"title": "CPU Temp", "text": "82.04 F"}]})
        self.addon._poll_genmon()
        self.assertEqual(self.addon.LastValues["Tiles/CPU Temp/value"], "82.04 °F")

    async def test_entities_wait_for_genmon(self):
        # while genmon is starting: 503, so Home Assistant keeps its entities
        fixture = self.start(health="System Initializing")
        self.addon._poll_genmon()
        client = await self.client()
        with mock.patch.object(type(self.addon), "ENTITIES_WAIT_SECONDS", 0):
            response = await client.get("/api/entities", headers=self.auth())
            self.assertEqual(response.status, 503)
            fixture.state["answers"]["monitor_num_json"] = json.dumps(monitor("OK"))
            self.addon._poll_genmon()
            response = await client.get("/api/entities", headers=self.auth())
            self.assertEqual(response.status, 200)

    async def test_entities_after_the_timeout(self):
        # genmon still initializing a minute after the first data (e.g. no
        # communication with the controller): the entities are sent anyway
        self.start(health="System Initializing")
        self.addon._poll_genmon()
        self.assertFalse(self.addon._data_ready.is_set())
        self.addon._first_data_time = time.time() - self.addon.DATA_READY_TIMEOUT
        self.addon._poll_genmon()
        self.assertTrue(self.addon._data_ready.is_set())

    async def test_entity_with_data_later(self):
        # a value genmon does not report at first (e.g. while starting) is
        # still sent as its own entity once it is there
        fixture = self.start()
        self.addon._poll_genmon()
        client = await self.client()
        entities, result = await self.entities(client)
        self.assertNotIn("power_leg1", entities["sensors"])
        status = json.loads(json.dumps(STATUS))
        status["Status"][0]["Engine"].append({"Power Leg 1": num(1.5, "kW")})
        fixture.state["answers"]["status_num_json"] = json.dumps(status)
        self.addon._poll_genmon()
        entities, result = await self.entities(client)
        self.assertEqual(entities["sensors"]["power_leg1"]["path"], "Status/Engine/Power Leg 1")
        self.assertNotIn("status_engine_power_leg_1", entities["sensors"])

    def test_userdefined_entities(self):
        # data/homeassistant/userdefined.json (as genhomeassistant.py), not
        # genmon's userdefined.json for the web page
        self.start()
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        user_file = os.path.join(repo, "data", "homeassistant", "userdefined.json")
        user_data = json.dumps({"sensors": [{"entity_id": "my_sensor", "name": "My Sensor",
                                             "path": "Status/Engine/My Sensor"}]})
        real_isfile, real_open = os.path.isfile, open
        checked = []

        def isfile(path):
            checked.append(os.path.abspath(path))
            return path == user_file or real_isfile(path)

        def fake_open(path, *args, **kwargs):
            if path == user_file:
                return mock.mock_open(read_data=user_data)()
            return real_open(path, *args, **kwargs)

        with mock.patch.object(self.fixture.module.os.path, "isfile", side_effect=isfile), \
                mock.patch("builtins.open", side_effect=fake_open):
            self.addon._load_entity_definitions()
        self.assertIn(user_file, checked)
        self.assertNotIn(os.path.join(repo, "userdefined.json"), checked)
        self.assertIn("my_sensor", [e["entity_id"] for e in self.addon.EntityDefinitions["sensors"]])

    # ---------- REST API -------------------------------------------------------
    async def test_authorization(self):
        self.start()
        client = await self.client()
        self.assertEqual((await client.get("/api/health")).status, 200)
        self.assertEqual((await client.get("/api/info")).status, 401)
        self.assertEqual((await client.get("/api/info", headers=self.auth("wrong"))).status, 401)
        response = await client.get("/api/info", headers=self.auth())
        self.assertEqual((await response.json())["Controller"], EVOLUTION)
        self.assertEqual((await client.get("/api/entities")).status, 401)
        self.assertEqual((await client.post("/api/command", json={"command": "x"})).status, 401)
        self.assertEqual(self.fixture.genmon.commands.count("generator: x"), 0)

    async def test_status(self):
        self.start()
        self.addon._poll_genmon()
        client = await self.client()
        result = await (await client.get("/api/status", headers=self.auth())).json()
        self.assertEqual(result["values"]["Status/Engine/Battery Voltage"], "13.1 V")
        self.assertIn("Engine", result["state"]["Status"])

    async def test_entities(self):
        self.start()
        self.addon._poll_genmon()
        client = await self.client()
        entities, result = await self.entities(client)
        self.assertEqual(result["controller_type"], "evolution")
        self.assertIn("battery_voltage", entities["sensors"])
        self.assertIn("generator_running", entities["binary_sensors"])
        self.assertEqual(set(entities["buttons"]),
                         {"start", "stop", "start_transfer", "start_exercise", "set_generator_time"})
        # defined for Evolution, but this generator does not report it
        self.assertNotIn("power_leg1", entities["sensors"])

    async def test_entities_by_capability(self):
        self.start(start_info={"RemoteCommands": False, "RemoteTransfer": False,
                               "SetGenTime": False, "WriteQuietMode": False})
        self.addon._poll_genmon()
        client = await self.client()
        entities, result = await self.entities(client)
        self.assertEqual(set(entities["buttons"]), {"start_exercise"})
        self.assertNotIn("quiet_mode", entities["switches"])
        self.assertFalse(result["capabilities"]["SetGenTime"])

    async def test_sensors_found_in_the_data(self):
        self.start()
        self.addon._poll_genmon()
        client = await self.client()
        entities, result = await self.entities(client)
        sensor = entities["sensors"]["status_engine_unlisted_sensor"]
        self.assertEqual((sensor["unit"], sensor["device_class"]), ("V", "voltage"))
        # Utility Voltage is in Status/Line and in Outage: one sensor, and the
        # second value is not sent
        names = [s["name"] for s in entities["sensors"].values()]
        self.assertEqual(names.count("Utility Voltage"), 1)
        self.assertNotIn("Outage/Utility Voltage", self.addon.LastValues)

    async def test_command(self):
        self.start()
        client = await self.client()
        response = await client.post("/api/command", json={"command": "setremote=start"},
                                     headers=self.auth())
        self.assertEqual(response.status, 200)
        self.assertIn("generator: setremote=start", self.fixture.genmon.commands)
        response = await client.post("/api/command", json={}, headers=self.auth())
        self.assertEqual(response.status, 400)
        response = await client.post("/api/command", data="not json", headers=self.auth())
        self.assertEqual(response.status, 400)

    # ---------- WebSocket ------------------------------------------------------
    async def test_websocket(self):
        self.start()
        self.addon._poll_genmon()
        client = await self.client()
        ws = await client.ws_connect("/ws")
        await ws.send_json({"type": "auth", "token": API_KEY})
        self.assertEqual((await ws.receive_json(timeout=5))["type"], "auth_ok")
        full = await ws.receive_json(timeout=5)
        self.assertEqual(full["type"], "full_state")
        self.assertEqual(full["values"]["Status/Engine/Battery Voltage"], "13.1 V")
        # a command
        await ws.send_json({"type": "command", "command": "setquiet=on"})
        self.assertEqual((await ws.receive_json(timeout=5))["type"], "command_response")
        self.assertIn("generator: setquiet=on", self.fixture.genmon.commands)
        # a change in genmon's data
        status = json.loads(json.dumps(STATUS))
        status["Status"][0]["Engine"][1]["Engine State"] = "Running"
        self.fixture.state["answers"]["status_num_json"] = json.dumps(status)
        self.addon._poll_genmon()
        update = await ws.receive_json(timeout=5)
        self.assertEqual(update["type"], "state_update")
        self.assertEqual(update["state"]["Status"]["Engine"]["Engine State"], "Running")
        await ws.close()

    async def test_websocket_wrong_key(self):
        self.start()
        client = await self.client()
        ws = await client.ws_connect("/ws")
        await ws.send_json({"type": "auth", "token": "wrong"})
        self.assertEqual((await ws.receive_json(timeout=5))["type"], "auth_error")
        await ws.receive(timeout=5)
        self.assertTrue(ws.closed)
        self.assertEqual(ws.close_code, 4001)
        self.assertEqual(self.addon.WSClients, set())

    # ---------- TLS ------------------------------------------------------------
    def test_certificate(self):
        from cryptography import x509

        fixture = self.start()
        with mock.patch.object(type(self.addon), "_get_local_ips", return_value={"192.0.2.10"}):
            crt, key = self.addon._ensure_tls_cert()
            self.assertEqual(os.path.dirname(crt) + os.sep, fixture.folder)
            with open(crt, "rb") as f:
                cert = x509.load_pem_x509_certificate(f.read())
            names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            self.assertIn("192.0.2.10", [str(ip) for ip in names.get_values_for_type(x509.IPAddress)])
            self.assertIn("localhost", names.get_values_for_type(x509.DNSName))
            self.assertEqual(os.stat(key).st_mode & 0o777, 0o600)
            # used again while the addresses are the same
            mtime = os.stat(crt).st_mtime_ns
            self.assertEqual(self.addon._ensure_tls_cert(), (crt, key))
            self.assertEqual(os.stat(crt).st_mtime_ns, mtime)
        # a new address: a new certificate
        with mock.patch.object(type(self.addon), "_get_local_ips", return_value={"192.0.2.99"}):
            self.addon._ensure_tls_cert()
            with open(crt, "rb") as f:
                cert = x509.load_pem_x509_certificate(f.read())
            names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            self.assertIn("192.0.2.99", [str(ip) for ip in names.get_values_for_type(x509.IPAddress)])


# -------------------------------------------------------------------------------
@unittest.skipIf(web is None, "aiohttp is not installed")
class HALinkTests(LinkTests, unittest.IsolatedAsyncioTestCase):
    MODULE, CLASS, POLL_THREAD = "genhalink", "GenHALink", "PollingThread"

@unittest.skipIf(web is None, "aiohttp is not installed")
class HubitatTests(LinkTests, unittest.IsolatedAsyncioTestCase):
    MODULE, CLASS, POLL_THREAD = "genhubitat", "GenHubitat", "HubitatPollingThread"


if __name__ == "__main__":
    unittest.main()
