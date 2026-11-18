#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_addon_alexa.py
# PURPOSE: Tests for addon/genalexa.py, which makes the generator look like a
#          WeMo switch to Amazon Echo devices: the answers to Alexa's network
#          search (UPnP), the device description, turning the generator on
#          (start and transfer, or start only without a transfer switch) and
#          off, its on / off state, and repeated commands from several Echos.
#
#          genmon is a fake; the network messages are given to the add-on's
#          functions directly (no network port is opened).
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_addon_alexa
#
# -------------------------------------------------------------------------------

import importlib
import logging
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from addon_fixture import FakeGenmon  # noqa: E402

genalexa = importlib.import_module("genalexa")

SENT = "Remote command sent successfully"
SET_ON = ('POST /upnp/control/basicevent1 HTTP/1.1\r\n'
          'SOAPACTION: "urn:Belkin:service:basicevent:1#SetBinaryState"\r\n\r\n'
          '<u:SetBinaryState><BinaryState>%d</BinaryState></u:SetBinaryState>')
GET_STATE = ('POST /upnp/control/basicevent1 HTTP/1.1\r\n'
             'SOAPACTION: "urn:Belkin:service:basicevent:1#GetBinaryState"\r\n\r\n'
             '<u:GetBinaryState></u:GetBinaryState>')


def quiet_log():
    log = logging.getLogger("addon_test_genalexa")
    log.handlers, log.propagate = [logging.NullHandler()], False
    return log


class FakeSocket(object):
    def __init__(self):
        self.sent = []

    def send(self, data):
        self.sent.append(data.decode("utf-8"))


class AlexaTestCase(unittest.TestCase):

    def setUp(self):
        self.genmon = FakeGenmon({"base": "READY", "answers": {
            "setremote=starttransfer": SENT, "setremote=start": SENT, "setremote=stop": SENT}})
        self.clock = 1000.0
        patch = mock.patch.object(genalexa.time, "time", side_effect=lambda: self.clock)
        patch.start()
        self.addCleanup(patch.stop)

    def callback(self, transfer=True):
        return genalexa.FauxmoCallback(self.genmon.ProcessMonitorCommand, log=quiet_log(),
                                       transfer=transfer)

    def device(self, handler):
        """A fauxmo switch without its network sockets."""
        device = genalexa.fauxmo.__new__(genalexa.fauxmo)
        device.log, device.debug = quiet_log(), False
        device.name, device.serial = "generator", genalexa.fauxmo.make_uuid("generator")
        device.ip_address, device.port, device.generatorStatus = "192.0.2.5", 52004, 0
        device.action_handler = handler
        return device

    def request(self, device, data):
        sock = FakeSocket()
        device.handle_request(data.encode("utf-8"), None, sock, None)
        return sock.sent


# -------------------------------------------------------------------------------
class CallbackTests(AlexaTestCase):

    def test_on_and_off(self):
        callback = self.callback()
        self.clock += 1
        self.assertTrue(callback.on())
        self.clock += 1
        self.assertTrue(callback.off())
        self.assertEqual(self.genmon.commands,
                         ["generator: setremote=starttransfer", "generator: setremote=stop"])

    def test_on_without_transfer_switch(self):
        # e.g. an H-100 without an HTS transfer switch: start only
        callback = self.callback(transfer=False)
        self.clock += 1
        self.assertTrue(callback.on())
        self.assertEqual(self.genmon.commands, ["generator: setremote=start"])

    def test_command_failed(self):
        callback = self.callback()
        self.genmon.state["answers"]["setremote=stop"] = "Error: not supported"
        self.clock += 1
        self.assertFalse(callback.off())

    def test_several_echos(self):
        # the same command heard by two Echos is sent once
        callback = self.callback()
        self.clock += 1
        callback.on()
        self.clock += 0.1
        self.assertTrue(callback.on())
        self.assertEqual(len(self.genmon.commands), 1)

    def test_status(self):
        callback = self.callback()
        self.clock += 11
        self.genmon.state["base"] = "RUNNING"
        self.assertEqual(callback.status(0), 1)
        # not asked again within 10 seconds
        self.genmon.state["base"] = "READY"
        self.assertEqual(callback.status(1), 1)
        self.clock += 11
        self.assertEqual(callback.status(1), 0)


# -------------------------------------------------------------------------------
class DeviceTests(AlexaTestCase):

    def test_setup_xml(self):
        sent = self.request(self.device(self.callback()), "GET /setup.xml HTTP/1.1\r\n\r\n")
        self.assertIn("<friendlyName>generator</friendlyName>", sent[0])
        self.assertIn("urn:Belkin:device:controllee:1", sent[0])

    def test_turn_on_and_off(self):
        device = self.device(self.callback())
        self.clock += 1
        sent = self.request(device, SET_ON % 1)
        self.assertTrue(sent[0].startswith("HTTP/1.1 200 OK"))
        self.assertEqual(device.generatorStatus, 1)
        self.clock += 1
        self.request(device, SET_ON % 0)
        self.assertEqual(device.generatorStatus, 0)
        self.assertEqual(self.genmon.commands[-1], "generator: setremote=stop")

    def test_failed_command_no_answer(self):
        device = self.device(self.callback())
        self.genmon.state["answers"]["setremote=starttransfer"] = "Error"
        self.clock += 1
        self.assertEqual(self.request(device, SET_ON % 1), [])
        self.assertEqual(device.generatorStatus, 0)

    def test_state(self):
        device = self.device(self.callback())
        self.genmon.state["base"] = "RUNNING"
        self.clock += 11
        sent = self.request(device, GET_STATE)
        self.assertIn("<BinaryState>1</BinaryState>", sent[0])


# -------------------------------------------------------------------------------
class SearchTests(AlexaTestCase):

    def responder(self, received):
        responder = genalexa.upnp_broadcast_responder(log=quiet_log())
        device = mock.Mock()
        responder.add_device(device)
        with mock.patch.object(responder, "recvfrom", return_value=received):
            responder.do_read(0)
        return device

    def test_echo_search(self):
        search = b'M-SEARCH * HTTP/1.1\r\nST: urn:Belkin:device:**\r\n\r\n'
        device = self.responder((search, ("192.0.2.9", 50000)))
        device.respond_to_search.assert_called_once_with(("192.0.2.9", 50000), "urn:Belkin:device:**")

    def test_root_device_search(self):
        search = b'M-SEARCH * HTTP/1.1\r\nST: upnp:rootdevice\r\n\r\n'
        device = self.responder((search, ("192.0.2.9", 50000)))
        self.assertEqual([c.args[1] for c in device.respond_to_search.call_args_list],
                         ["urn:Belkin:device:**", "upnp:rootdevice"])

    def test_other_search(self):
        search = b'M-SEARCH * HTTP/1.1\r\nST: urn:dial-multiscreen-org:service:dial:1\r\n\r\n'
        self.responder((search, ("192.0.2.9", 50000))).respond_to_search.assert_not_called()

    def test_receive_error(self):
        # recvfrom returns (False, False) after an error: nothing happens (this
        # used to raise an error, and the main loop then waited 60 seconds)
        self.responder((False, False)).respond_to_search.assert_not_called()

    def test_not_utf8(self):
        self.responder((b"\xff\xfeM-SEARCH", ("192.0.2.9", 50000))).respond_to_search.assert_not_called()

    def test_search_answer(self):
        device = self.device(self.callback())
        device.uuid, device.server_version = "1234", "Unspecified, UPnP/1.0, Unspecified"
        device.persistent_uuid = "Socket-1_0-" + device.serial
        device.root_url = "http://%(ip_address)s:%(port)s/setup.xml"
        device.other_headers = ["X-User-Agent: redsonic"]
        with mock.patch.object(genalexa.socket, "socket") as sock:
            device.respond_to_search(("192.0.2.9", 50000), "urn:Belkin:device:**")
        message, address = sock.return_value.sendto.call_args[0]
        self.assertEqual(address, ("192.0.2.9", 50000))
        self.assertIn(b"LOCATION: http://192.0.2.5:52004/setup.xml", message)
        self.assertIn(b"ST: urn:Belkin:device:**", message)


if __name__ == "__main__":
    unittest.main()
