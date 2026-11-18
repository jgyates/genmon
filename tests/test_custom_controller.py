#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_custom_controller.py
# PURPOSE: Tests for genmonlib/custom_controller.py, the controller for the
#          generators described by a JSON file in data/controller (ComAp,
#          Deep Sea, Kohler, SmartGen, ...):
#
#          - every file in data/controller: the controller starts, is
#            detected and shows its status, maintenance, outage, log, register,
#            start and web page data without errors (register values made up
#            by the test, so no captures are needed)
#          - the value types and modifiers of the JSON entries (int, float,
#            bits, bool, IEEE 754 floats, signed values, masks, word swap,
#            multipliers, rounding, temperature, exec, lists, lookups, ASCII,
#            values from genmon.conf)
#          - setting up the gauges
#
#          The registers come from a register file through
#          genmonlib/modbus_file.py (genmon's simulation mode); threads are
#          not started.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_custom_controller
#
# -------------------------------------------------------------------------------

import glob
import json
import logging
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from addon_fixture import REPO_DIR, FakeThread  # noqa: E402

import genmonlib.controller  # noqa: E402
import genmonlib.modbus_file  # noqa: E402
from genmonlib.custom_controller import CustomController  # noqa: E402
from genmonlib.myconfig import MyConfig  # noqa: E402

CONTROLLER_DIR = os.path.join(REPO_DIR, "data", "controller")
CONTROLLER_FILES = sorted(os.path.basename(p) for p in glob.glob(os.path.join(CONTROLLER_DIR, "*.json")))

# errors that come from the made up register values, not from the code: dates
# like 0/0/2000, a rated voltage of 0
DATA_ERRORS = ["does not match format", "year must be in", "is out of range", "day is out of range",
               "month must be in", "MyGauge:init: invalid value", "division by zero"]


class Collect(logging.Handler):
    def __init__(self):
        super(Collect, self).__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


class FakeFeedback(object):
    """genmon's feedback pipe (unknown states are reported to the developer)."""

    def __init__(self):
        self.sent = []

    def SendFeedback(self, *args, **kwargs):
        self.sent.append(args)


def register_file(imported, byte="00"):
    """A register file (modbus_file.py JSON format) with a value for every
    register the import file reads, each byte set to byte."""
    data = {"Registers": {}, "Strings": {}, "FileData": {}, "Coils": {}, "Inputs": {}}
    for section, target in [("holding_registers", "Registers"), ("input_registers", "Inputs"),
                            ("coil_registers", "Coils")]:
        for register, info in imported.get(section, {}).items():
            if register.lower().startswith("comment"):
                continue
            length = info["length"] if isinstance(info, dict) else info
            data[target][register] = byte * (length if section != "coil_registers" else 2)
    return data


class ControllerTestCase(unittest.TestCase):

    def controller(self, import_file, byte="00", registers=None, **settings):
        """A CustomController for data/controller/import_file, its registers
        read once (as genmon does when it starts)."""
        folder = tempfile.mkdtemp(prefix="custom_controller_")
        self.addCleanup(shutil.rmtree, folder)
        shutil.copy(os.path.join(REPO_DIR, "conf", "genmon.conf"), folder)
        config = MyConfig(filename=os.path.join(folder, "genmon.conf"), section="GenMon")
        values = {"controllertype": "custom", "import_config_file": import_file,
                  "loglocation": folder, "nominalKW": "30"}
        values.update(settings)
        for key, value in values.items():
            config.WriteValue(key, str(value))
        with open(os.path.join(CONTROLLER_DIR, import_file)) as f:
            imported = json.load(f)
        regs = registers if registers is not None else register_file(imported, byte)
        path = os.path.join(folder, "registers.json")
        with open(path, "w") as f:
            json.dump(regs, f)

        self.log = logging.getLogger("custom_controller_test")
        self.log.handlers, self.log.propagate = [], False
        self.errors = Collect()
        self.log.addHandler(self.errors)
        self.feedback = FakeFeedback()
        patches = [mock.patch.object(genmonlib.controller, "MyThread", FakeThread),
                   mock.patch.object(genmonlib.modbus_file, "MyThread", FakeThread),
                   mock.patch.object(genmonlib.modbus_file.time, "sleep")]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        controller = CustomController(self.log, simulation=True, simulationfile=path,
                                      config=config, feedback=self.feedback,
                                      ConfigFilePath=folder)
        controller.ModBus.SimulateTime = False
        self.addCleanup(self.close_logs)
        controller.InitDevice()
        return controller

    @staticmethod
    def close_logs():
        # the log files the controller opened (mymodbus.log in the test folder)
        for name in ["mymodbus"]:
            logger = logging.getLogger(name)
            for handler in list(logger.handlers):
                handler.close()
                logger.removeHandler(handler)

    def code_errors(self):
        return [m for m in self.errors.messages
                if ("error" in m.lower() or "unable" in m.lower())
                and not any(d in m for d in DATA_ERRORS)]


# -------------------------------------------------------------------------------
class ControllerFileTests(ControllerTestCase):
    """Every controller file in data/controller."""

    def check(self, import_file, byte, detected=True):
        controller = self.controller(import_file, byte=byte)
        status = controller.DisplayStatus(DictOut=True)
        self.assertIn("Status", status)
        if detected:
            self.assertTrue(controller.ControllerDetected)
            self.assertNotIn({"Genmon State": "Waiting for comms"}, status["Status"])
        self.assertIn("Maintenance", controller.DisplayMaintenance(DictOut=True))
        self.assertIn("Outage", controller.DisplayOutage(DictOut=True))
        self.assertIsInstance(controller.DisplayLogs(DictOut=True), dict)
        self.assertIsInstance(controller.DisplayRegisters(DictOut=True), dict)
        info = controller.GetStartInfo()
        self.assertTrue(info["Controller"])
        gui = controller.GetStatusForGUI()
        self.assertIn("basestatus", gui)
        self.assertIn(controller.GetBaseStatus(),
                      ["READY", "EXERCISING", "RUNNING", "RUNNING-MANUAL", "ALARM",
                       "SERVICEDUE", "OFF", "MANUAL", "UNKNOWN"])
        # text output too (as the web page and email show it)
        self.assertTrue(controller.DisplayStatus())
        return controller

    def test_all_files_zero_registers(self):
        for import_file in CONTROLLER_FILES:
            with self.subTest(file=import_file):
                self.check(import_file, "00")
                self.assertEqual(self.code_errors(), [])

    def test_all_files_other_values(self):
        # every byte 0x11: odd values in every register (unknown states,
        # alarms, nonsense dates). A controller may then not be detected (e.g.
        # a rated value that is not one of its known codes)
        for import_file in CONTROLLER_FILES:
            with self.subTest(file=import_file):
                self.check(import_file, "11", detected=False)
                self.assertEqual(self.code_errors(), [])

    def test_gauges(self):
        # every file sets up gauges (some are left out on purpose, e.g. the
        # third phase on a single phase generator)
        for import_file in CONTROLLER_FILES:
            with self.subTest(file=import_file):
                controller = self.controller(import_file, byte="01")
                self.assertGreater(len(controller.TileList), 0)
                self.assertEqual(self.code_errors(), [])

    def test_simulation_coils_and_inputs(self):
        # coils and input registers from a register file are stored as coils
        # and input registers (they were stored as holding registers)
        def has_inputs(name):
            with open(os.path.join(CONTROLLER_DIR, name)) as f:
                return "input_registers" in json.load(f)

        import_file = next(f for f in CONTROLLER_FILES if has_inputs(f))
        controller = self.controller(import_file, byte="00")
        imported = controller.controllerimport
        register = next(r for r in imported["input_registers"] if not r.lower().startswith("comment"))
        self.assertIn(register, controller.Inputs)


# -------------------------------------------------------------------------------
class EntryTests(ControllerTestCase):
    """GetDisplayEntry: the types and modifiers of the JSON entries."""

    def setUp(self):
        self.c = self.controller("Kohler_APM402.json")

    def value(self, entry, hex_value, reg="0f00", **kwargs):
        """The value of entry with register reg set to hex_value."""
        entry = dict({"reg": reg, "title": "Test"}, **entry)
        self.c.controllerimport.setdefault("holding_registers", {})[reg] = len(hex_value) // 2
        self.c.Holding[reg] = hex_value
        title, value = self.c.GetDisplayEntry(entry, **kwargs)
        return value

    def test_int(self):
        self.assertEqual(self.value({"type": "int", "mask": "ffff"}, "0123"), 291)
        self.assertEqual(self.value({"type": "int", "mask": "00ff"}, "0123"), 0x23)
        self.assertEqual(self.value({"type": "int", "mask": "ffff", "multiplier": 0.1}, "0123"), 29)
        self.assertEqual(self.value({"type": "int", "mask": "ffff", "shiftright": 8}, "0123"), 1)
        self.assertEqual(self.value({"type": "int", "mask": "ffff", "units": "V"}, "00f0"), "240 V")

    def test_signed(self):
        self.assertEqual(self.value({"type": "int", "mask": "ffff", "signed16": True}, "fffe"), -2)
        self.assertEqual(self.value({"type": "int", "mask": "ffffffff", "signed32": True},
                                    "fffffffd"), -3)

    def test_word_swap(self):
        self.assertEqual(self.value({"type": "int", "mask": "ffffffff", "swapwords32": True},
                                    "00010002"), 0x00020001)

    def test_float(self):
        self.assertEqual(self.value({"type": "float", "multiplier": 0.1, "round": 1}, "0123"), 29.1)
        self.assertEqual(self.value({"type": "float", "multiplier": 0.1, "round": 1,
                                     "units": "Hz"}, "0258"), "60.00 Hz")
        self.assertEqual(self.value({"type": "float", "multiplier": 0.1, "round": 1},
                                    "0123", JSONNum=False), 29.1)

    def test_ieee754(self):
        self.assertEqual(self.value({"type": "float", "ieee754": "single"}, "3fc00000"), 1.5)
        # half and double did not work (wrong struct format)
        self.assertEqual(self.value({"type": "float", "ieee754": "half"}, "3c00"), 1.0)
        self.assertEqual(self.value({"type": "float", "ieee754": "double"},
                                    "3ff8000000000000"), 1.5)
        # not a number: 0
        self.assertEqual(self.value({"type": "float", "ieee754": "single"}, "7fc00000"), 0.0)

    def test_bits_and_bool(self):
        entry = {"type": "bits", "mask": "0004", "value": "0004", "text": "Running"}
        self.assertEqual(self.value(entry, "0006"), "Running")
        self.assertIsNone(self.value(entry, "0002"))
        entry = {"type": "bool", "mask": "0001", "text": "In Alarm"}
        self.assertEqual(self.value(entry, "0001"), "In Alarm")
        self.assertIsNone(self.value(entry, "0000"))
        entry = {"type": "bool", "mask": "0001", "value": "false", "text": "Not Ready"}
        self.assertEqual(self.value(entry, "0000"), "Not Ready")

    def test_regex(self):
        entry = {"type": "regex", "mask": "ffff", "regex": "^1[0-9]$", "text": "Teen"}
        self.assertEqual(self.value(entry, "0013"), "Teen")
        self.assertIsNone(self.value(entry, "0020"))

    def test_lookups(self):
        entry = {"type": "object_int_index", "mask": "ffff",
                 "object": {"0": "Off", "1": "Auto", "2": "Manual"}, "default": "Unknown"}
        self.assertEqual(self.value(entry, "0001"), "Auto")
        self.assertEqual(self.value(entry, "0009"), "Unknown")
        entry = {"type": "object_bit_index", "mask": "ffff",
                 "object": {"0": "Low Oil", "1": "High Temp", "2": "Overspeed"}, "default": "None"}
        self.assertEqual(self.value(entry, "0005"), "Low Oil, Overspeed")
        self.assertEqual(self.value(entry, "0000"), "None")

    def test_ascii(self):
        self.assertEqual(self.value({"type": "ascii"}, "48656c6c6f21"), "Hello!")

    def test_temperature(self):
        entry = {"type": "int", "mask": "ffff", "temperature": "celsius", "units": "C"}
        self.c.UseMetric = False
        self.assertEqual(self.value(entry, "0064"), "212 F")
        self.c.UseMetric = True
        self.assertEqual(self.value(entry, "0064"), "100 C")

    def test_exec_and_bounds(self):
        self.assertEqual(self.value({"type": "int", "mask": "ffff", "exec": "exec_out = {0} * 2"},
                                    "0005"), 10)
        entry = {"type": "int", "mask": "ffff", "bounds_regex": "^[0-9]$"}
        self.assertEqual(self.value(entry, "0005"), 5)
        self.assertIsNone(self.value(entry, "0010"))

    def test_list(self):
        self.c.controllerimport["holding_registers"].update({"0f01": 2, "0f02": 2})
        self.c.Holding.update({"0f01": "000c", "0f02": "001e"})
        items = [{"reg": "0f01", "type": "int", "mask": "ffff", "title": "h"},
                 {"reg": "0f02", "type": "int", "mask": "ffff", "title": "m"}]
        title, value = self.c.GetDisplayEntry({"type": "list", "title": "Time", "value": items,
                                               "separator": ":"})
        self.assertEqual(value, "12:30")
        title, value = self.c.GetDisplayEntry({"type": "list", "title": "Time", "value": items,
                                               "format": "%s h %s min"})
        self.assertEqual(value, "12 h 30 min")
        title, value = self.c.GetDisplayEntry({"type": "list", "title": "Time", "value": items,
                                               "exec": "exec_out = int({0}) * 60 + int({1})"})
        self.assertEqual(value, 750)

    def test_list_exec_with_a_missing_item(self):
        # a missing item would shift the others: no value (it used to raise an
        # error, or could use the wrong values)
        self.c.controllerimport["holding_registers"].update({"0f01": 2})
        self.c.Holding.update({"0f01": "000c"})
        items = [{"reg": "0f01", "type": "int", "mask": "ffff", "title": "a"},
                 {"reg": "0f09", "type": "int", "mask": "ffff", "title": "missing"},
                 {"reg": "0f01", "type": "int", "mask": "ffff", "title": "c"}]
        title, value = self.c.GetDisplayEntry({"type": "list", "title": "T", "value": items,
                                               "exec": "exec_out = '{0} {1} {2}'"})
        self.assertIsNone(value)
        self.assertEqual(self.code_errors(), [])

    def test_config_values(self):
        # values from genmon.conf (reg_type config)
        self.c.config.WriteValue("testfloat", "12.5")
        self.c.config.WriteValue("testint", "7")
        title, value = self.c.GetDisplayEntry({"reg_type": "config", "reg": "testint", "type": "int",
                                               "title": "I", "mask": "ffff"})
        self.assertEqual(value, 7)
        # float did not work (it used a variable that was not set)
        title, value = self.c.GetDisplayEntry({"reg_type": "config", "reg": "testfloat",
                                               "type": "float", "title": "F", "multiplier": 1,
                                               "round": 1})
        self.assertEqual(value, 12.5)
        title, value = self.c.GetDisplayEntry({"reg_type": "config", "reg": "notset",
                                               "type": "float", "title": "F", "multiplier": 1})
        self.assertIsNone(value)
        self.assertEqual(self.code_errors(), [])

    def test_invalid_entries(self):
        for entry in [{"type": "int"},                                  # no mask
                      {"type": "float"},                                # no multiplier
                      {"type": "int", "mask": "xyz"},                   # mask not hex
                      {"type": "float", "multiplier": 0}]:
            with self.subTest(entry=entry):
                self.assertIsNone(self.value(entry, "0001"))

    def test_register_not_read(self):
        title, value = self.c.GetDisplayEntry({"reg": "0eee", "type": "int", "mask": "ffff",
                                               "title": "Not read"})
        self.assertIsNone(value)


# -------------------------------------------------------------------------------
class GaugeTests(ControllerTestCase):

    def test_one_bad_gauge(self):
        # a gauge that can not be set up does not stop the gauges after it
        # (it stopped every gauge after it)
        controller = self.controller("Power_Zone_410.json", byte="01")
        gauges = controller.controllerimport["gauges"]
        bad = gauges[0]["title"]
        real_setup = controller.SetupTile

        def setup(sensor):
            if sensor["title"] == bad:
                raise ValueError("bad gauge")
            return real_setup(sensor)

        controller.TileList = []
        with mock.patch.object(controller, "SetupTile", side_effect=setup):
            controller.SetupTiles()
        titles = [tile.Title for tile in controller.TileList]
        self.assertNotIn(bad, titles)
        for gauge in gauges[1:]:
            self.assertIn(gauge["title"], titles)

    def test_rated_volts_zero_float(self):
        # Basler reads the rated volts as an IEEE 754 float: 0.0 is the 480 V
        # default, as an int 0 (it was 0 V, the current gauge divided by zero)
        controller = self.controller("Basler_DGC_2020HD.json", byte="00")
        self.assertEqual(controller.NominalLineVolts, 480)
        titles = [tile.Title for tile in controller.TileList]
        for gauge in controller.controllerimport["gauges"]:
            self.assertIn(gauge["title"], titles)

    def test_rated_kw_not_set(self):
        # not in the controller file or genmon.conf: 100 kW, so the power and
        # current gauges are shown (they were left out)
        controller = self.controller("Power_Zone_410.json", byte="01", nominalKW="")
        self.assertEqual(controller.NominalKW, "100")
        titles = [tile.Title for tile in controller.TileList]
        for gauge in controller.controllerimport["gauges"]:
            self.assertIn(gauge["title"], titles)
        # the genmon.conf value when set
        controller = self.controller("Power_Zone_410.json", byte="01", nominalKW="45")
        self.assertEqual(controller.NominalKW, "45")


if __name__ == "__main__":
    unittest.main()
