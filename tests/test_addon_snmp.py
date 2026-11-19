#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_addon_snmp.py
# PURPOSE: Tests for addon/gensnmp.py, the SNMP agent: the OIDs it sets up from
#          data/mib (genmon, the controller's file, custom controllers), the
#          values it reads from genmon (text, integers), and its answers to
#          SNMP GET and GETNEXT (snmpwalk) requests, including the community.
#
#          genmon and threads are fakes, see addon_fixture.py. The requests are
#          real SNMP v2c messages (pysnmp), given to the agent's receive
#          function; no network port is opened.
#
#          The OID files themselves are also checked: every file in data/mib
#          has each OID once.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_addon_snmp
#
# -------------------------------------------------------------------------------

import glob
import json
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from addon_fixture import REPO_DIR, AddOnFixture  # noqa: E402

try:
    from pyasn1.codec.ber import decoder, encoder
    from pysnmp.proto import api
    if not hasattr(api, "PROTOCOL_MODULES"):
        api = None  # pysnmp before 7 (gensnmp.py needs 7)
except ImportError:  # see tests/requirements.txt
    api = None

BASE = (1, 3, 6, 1, 4, 1, 58399)
SYS_DESCR = (1, 3, 6, 1, 2, 1, 1, 1, 0)

STATUS = {"Status": [{"Engine": [{"Switch State": "Auto"}, {"Engine State": "Off - Ready"},
                                 {"Battery Voltage": "13.20 V"}, {"RPM": "0"}]},
                     {"Line": [{"Utility Voltage": "241 V"}]}]}
MAINT = {"Maintenance": [{"Model": "Test 22kW"}, {"Nominal Frequency": "60 Hz"}]}
OUTAGE = {"Outage": [{"System In Outage": "No"}]}
MONITOR = {"Monitor": [{"Generator Monitor Stats": [{"Monitor Health": "OK"}]},
                       {"Communication Stats": [{"Packet Count": "M:1234 S:5678"},
                                                {"CRC Errors": "12"}]}]}


class FakeDispatcher(object):
    """pysnmp's AsyncioDispatcher (pysnmp 7 method names only): records what
    the agent sends; run_dispatcher returns at once."""

    def __init__(self):
        self.sent, self.started, self.closed = [], False, False

    def register_recv_callback(self, callback):
        self.callback = callback

    def register_transport(self, domain, transport):
        pass

    def job_started(self, job):
        self.started = True

    def run_dispatcher(self):
        pass

    def job_finished(self, job):
        pass

    def unregister_recv_callback(self, recvId=None):
        pass

    def unregister_transport(self, domain):
        pass

    def close_dispatcher(self):
        self.closed = True

    def send_message(self, message, domain, address):
        self.sent.append(message)


def fake_udp(name):
    class Transport(object):
        def open_server_mode(self, address):
            return self

    module = types.SimpleNamespace(DOMAIN_NAME=(1, 3, 6, 1, 6, 1, 1))
    setattr(module, name, Transport)
    return module


@unittest.skipIf(api is None, "pysnmp 7 is not installed")
class SNMPTests(unittest.TestCase):

    def start(self, controller="Evolution 2.0, Air Cooled", genmon_conf=None, **settings):
        conf = {"community": "public", "use_numeric": "False", "use_integer": "False"}
        conf.update(settings)
        self.dispatcher = FakeDispatcher()
        fixture = AddOnFixture(
            "gensnmp", "GenSNMP", conf,
            extra_config={"genmon.conf": {"GenMon": genmon_conf or {}}},
            patches=[("AsyncioDispatcher", lambda: self.dispatcher),
                     ("udp", fake_udp("UdpAsyncioTransport")),
                     ("udp6", fake_udp("Udp6AsyncioTransport"))])
        fixture.state["answers"] = {
            "start_info_json": json.dumps({"Controller": controller}),
            "status_json": json.dumps(STATUS), "maint_json": json.dumps(MAINT),
            "outage_json": json.dumps(OUTAGE), "monitor_json": json.dumps(MONITOR)}
        self.addCleanup(fixture.stop)
        fixture.start()
        self.fixture, self.addon = fixture, fixture.addon
        return fixture

    def poll(self):
        """One pass of the thread that reads genmon (it then exits, which
        closes the dispatcher; requests are still answered by the callback)."""
        self.fixture.run_thread("SNMPThread", waits=[True])

    def request(self, oids, getnext=False, community="public"):
        """Send an SNMP v2c GET (or GETNEXT): [(oid, value)] and the error
        status, or None if the agent did not answer."""
        pMod = api.PROTOCOL_MODULES[api.SNMP_VERSION_2C]
        pdu = pMod.GetNextRequestPDU() if getnext else pMod.GetRequestPDU()
        pMod.apiPDU.set_defaults(pdu)
        pMod.apiPDU.set_varbinds(pdu, [(oid, pMod.Null("")) for oid in oids])
        message = pMod.Message()
        pMod.apiMessage.set_defaults(message)
        pMod.apiMessage.set_community(message, community)
        pMod.apiMessage.set_pdu(message, pdu)
        before = len(self.dispatcher.sent)
        self.addon.SnmpCallbackFunction(self.dispatcher, None, ("127.0.0.1", 50000),
                                        encoder.encode(message))
        if len(self.dispatcher.sent) == before:
            return None
        response, _ = decoder.decode(self.dispatcher.sent[-1], asn1Spec=pMod.Message())
        rsp_pdu = pMod.apiMessage.get_pdu(response)
        return ([(tuple(oid), value) for oid, value in pMod.apiPDU.get_varbinds(rsp_pdu)],
                int(pMod.apiPDU.get_error_status(rsp_pdu)))

    def get(self, oid):
        varbinds, status = self.request([oid])
        self.assertEqual(status, 0)
        value = varbinds[0][1]
        return value.prettyPrint()

    # ---------------------------------------------------------------------------
    def test_setup(self):
        self.start()
        self.assertTrue(self.dispatcher.started)
        self.assertEqual(self.addon.ControllerSelected, "generac_evo_nexus")
        self.assertEqual(self.get(SYS_DESCR), "Genmon Generator Monitor")

    def test_values(self):
        self.start()
        self.poll()
        self.assertEqual(self.get(BASE + (1, 0, 0, 1)), "Auto")           # Switch State
        self.assertEqual(self.get(BASE + (1, 0, 0, 2)), "Off - Ready")    # Engine State
        self.assertEqual(self.get(BASE + (0, 0, 1)), "OK")                # Monitor Health

    def test_values_as_integers(self):
        # use_integer: values marked "integer" in data/mib are sent as numbers
        # (genmon's *_num_json data)
        fixture = self.start(use_integer="True")
        monitor = {"Monitor": [{"Communication Stats": [
            {"CRC Errors": {"type": "int", "value": 12, "unit": ""}}]}]}
        fixture.state["answers"].update({
            "status_num_json": json.dumps(STATUS), "maint_num_json": json.dumps(MAINT),
            "outage_num_json": json.dumps(OUTAGE), "monitor_num_json": json.dumps(monitor)})
        self.poll()
        oid = self.addon.GetOID("home/Monitor/Communication Stats/CRC Errors")
        self.assertEqual(oid, BASE + (0, 1, 2))
        varbinds, status = self.request([oid])
        self.assertEqual(int(varbinds[0][1]), 12)

    def test_numeric_value_in_a_list(self):
        # use_numeric: a value of genmon's *_num_json data that is directly in
        # a list is one value (not its type / value / unit parts)
        self.start(use_numeric="True")
        self.addon.CheckDictForChanges(
            {"Status": [{"type": "float", "value": 13.2, "unit": "V"}]}, "home")
        self.assertEqual(self.addon.LastValues, {"home/Status": "13.2"})

    def test_keywords_match_in_file_order(self):
        # the OIDs are sorted for snmpwalk, but keywords still match in file
        # order: "Fuel Level Sensor Tank 2" is not taken by "Fuel Level Sensor"
        # (issue 1580: tanks 2-4 were empty, tank 1 showed the last tank)
        fixture = self.start()
        maint = {"Maintenance": [{"Fuel Level Sensor": "66.66"},
                                 {"Fuel Level Sensor Tank 2": "50.00"},
                                 {"Fuel Level Sensor Tank 3": "40.00"},
                                 {"Fuel Level Sensor Tank 4": "30.00"}]}
        fixture.state["answers"]["maint_json"] = json.dumps(maint)
        self.poll()
        self.assertEqual(self.get(BASE + (1, 1, 0, 8)), "66.66")
        self.assertEqual(self.get(BASE + (1, 1, 0, 8, 1)), "50.00")
        self.assertEqual(self.get(BASE + (1, 1, 0, 8, 2)), "40.00")
        self.assertEqual(self.get(BASE + (1, 1, 0, 8, 3)), "30.00")

    def test_unknown_oid(self):
        self.start()
        varbinds, status = self.request([BASE + (9, 9, 9)])
        self.assertEqual(varbinds[0][1].prettyPrint(), "No Such Instance currently exists at this OID")

    def test_wrong_community(self):
        self.start()
        self.assertIsNone(self.request([SYS_DESCR], community="private"))

    def test_walk(self):
        # snmpwalk: each GETNEXT answers the next OID; every OID once, in order
        self.start()
        self.poll()
        oid, walked = BASE, []
        for _ in range(1000):
            varbinds, status = self.request([oid], getnext=True)
            # after the last OID: the same OID back (value endOfMibView)
            if status or varbinds[0][0] <= oid or varbinds[0][0][:len(BASE)] != BASE:
                break
            oid = varbinds[0][0]
            walked.append(oid)
        expected = sorted(m.name for m in self.addon.mibData if m.name[:len(BASE)] == BASE)
        self.assertEqual(walked, expected)
        self.assertGreater(len(walked), 50)

    def test_custom_controller(self):
        # a custom controller with its own data/mib file (controller id 4)
        self.start(controller="Custom Controller",
                   genmon_conf={"controllertype": "custom",
                                "import_config_file": "Evolution_Liquid_Cooled.json"})
        self.poll()
        self.assertEqual(self.addon.ControllerSelected, "custom")
        self.assertEqual(self.get(BASE + (4, 0, 0, 1)), "Auto")      # Switch State
        self.assertEqual(self.get(BASE + (4, 0, 1, 5)), "60 Hz")     # Nominal Frequency

    def test_values_before_snmp_is_set_up(self):
        # values read before the agent is ready are stored once it is
        self.start()
        dispatcher, self.addon.transportDispatcher = self.addon.transportDispatcher, None
        self.fixture.run_thread("SNMPThread", waits=[True])
        self.addon.transportDispatcher = dispatcher
        self.poll()
        self.assertEqual(self.get(BASE + (1, 0, 0, 1)), "Auto")

    def test_no_data_from_genmon(self):
        # e.g. while genmon restarts: the thread still waits between polls
        # (it used to ask genmon again at once, without end)
        self.start()
        calls = []

        class Looping(BaseException):
            pass

        def no_data(command):
            calls.append(command)
            if len(calls) > 20:
                raise Looping()
            return ""

        with mock.patch.object(self.addon, "SendCommand", side_effect=no_data):
            try:
                self.fixture.run_thread("SNMPThread", waits=[False, True])
            except Looping:
                self.fail("the thread did not wait after an error")
        self.assertEqual(len(calls), 8)  # two polls of four commands

    def test_close(self):
        self.start()
        self.addon.SnmpClose()
        self.assertTrue(self.dispatcher.closed)
        self.assertIsNone(self.addon.transportDispatcher)


# -------------------------------------------------------------------------------
class MIBFileTests(unittest.TestCase):

    def test_each_oid_once(self):
        for path in glob.glob(os.path.join(REPO_DIR, "data", "mib", "*.json")):
            with self.subTest(file=os.path.basename(path)):
                with open(path) as f:
                    entries = json.load(f)["snmp"]
                oids = [tuple(int(x) for x in e["oid"].split(",")) for e in entries]
                duplicates = sorted(set(o for o in oids if oids.count(o) > 1))
                self.assertEqual(duplicates, [])


if __name__ == "__main__":
    unittest.main()
