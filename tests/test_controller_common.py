#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_controller_common.py
# PURPOSE: Tests for genmonlib/controller.py, the code every controller type
#          shares (GeneratorController): command buttons and command
#          sequences, the maintenance log, data sent in by add-ons (tank, CT,
#          sensors, gauges), value modifiers, the power and outage logs, the
#          sensor logs.
#
#          The controllers are built in simulation mode from the controller
#          files in data/controller and the captures in tests/sim/captures (the
#          harnesses of test_custom_controller.py and
#          test_generac_controllers.py); the commands they would send are
#          recorded, not sent.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_controller_common
#
# -------------------------------------------------------------------------------

import datetime
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_custom_controller import ControllerTestCase  # noqa: E402
from test_generac_controllers import GeneracTestCase  # noqa: E402

import genmonlib.controller  # noqa: E402


def button_command(name, *values):
    """The set_button_command text the web page sends for button name, with
    a value for each command of its sequence ({} for a fixed value)."""
    sequence = [({"value": v} if v is not None else {}) for v in values] or [{}]
    return "set_button_command=" + json.dumps([{"onewordcommand": name, "command_sequence": sequence}])


# -------------------------------------------------------------------------------
class ButtonTests(ControllerTestCase):
    """Command buttons from the controller files (custom controllers)."""

    def setUp(self):
        self.writes = []

    def record(self, controller):
        def write(Register, Length, Data, IsCoil=False, IsSingle=False):
            self.writes.append((Register.lower(), Length, list(Data), IsCoil, IsSingle))
        controller.ModBus.ProcessWriteTransaction = write
        controller.DelayBetweenFrames = lambda *args, **kwargs: None
        return controller

    def test_buttons_from_the_controller_file(self):
        c = self.controller("Power_Zone_410.json", byte="01")
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "data", "controller", "Power_Zone_410.json")) as f:
            expected = [b["onewordcommand"] for b in json.load(f)["buttons"]]
        self.assertEqual([b["onewordcommand"] for b in c.GetButtons()], expected)
        self.assertEqual(c.GetButtons(singlebuttonname="auto")["title"], "Select Auto Mode")

    def test_fixed_value(self):
        # a button with a fixed value: written as is
        c = self.record(self.controller("Power_Zone_410.json", byte="01"))
        self.assertEqual(c.SetCommandButton(button_command("auto")), "The command was sent to the controller.")
        self.assertEqual(self.writes, [("0003", 1, [0x00, 0x0F], False, False)])

    def test_value_from_the_user(self):
        # input_title: the value typed on the page, checked with bounds_regex
        c = self.record(self.controller("Evolution_Liquid_Cooled.json", byte="00"))
        self.assertEqual(c.SetCommandButton(button_command("startupdelay", 30)),
                         "The command was sent to the controller.")
        self.assertEqual(self.writes, [("0239", 1, [0x00, 30], False, False)])
        self.writes = []
        self.assertEqual(c.SetCommandButton(button_command("startupdelay", 2)),
                         "Error in ExecuteRemoteCommand: Failed bounds check")
        self.assertEqual(self.writes, [])

    def test_single_coil(self):
        c = self.record(self.controller("SmartGen_HGM4000.json", byte="00"))
        c.SetCommandButton(button_command("start"))
        self.assertEqual(self.writes, [("0000", 1, [0x00, 0x01], True, True)])

    def test_invalid_input(self):
        c = self.record(self.controller("Power_Zone_410.json", byte="01"))
        for command in ["set_button_command=not json", "set_button_command=[]", "set_button_command={}",
                        "button=" + json.dumps([{"onewordcommand": "auto"}]), "", None,
                        button_command("no_such_button"),
                        "set_button_command=" + json.dumps([{"onewordcommand": "auto"}])]:
            with self.subTest(command=command):
                self.assertTrue(c.SetCommandButton(command).startswith("Error"))
        self.assertEqual(self.writes, [])

    def test_command_sequence_values(self):
        # the value forms a command sequence may hold
        c = self.record(self.controller("Power_Zone_410.json", byte="01"))
        c.ExecuteCommandSequence([
            {"reg": "0010", "value": "1234"},                    # hex text
            {"reg": "0011", "value": 0x0102},                     # number
            {"reg": "0012", "value": ["00", "0a", "00", "0b"]},   # list of hex bytes
            {"reg": "0013", "value": "0001", "shiftleft": 4},     # with a modifier
            {"reg": "0014", "value": "00ff", "reg_type": "coil"},
        ])
        self.assertEqual(self.writes, [
            ("0010", 1, [0x12, 0x34], False, False), ("0011", 1, [0x01, 0x02], False, False),
            ("0012", 2, [0x00, 0x0A, 0x00, 0x0B], False, False), ("0013", 1, [0x00, 0x10], False, False),
            ("0014", 1, [0x00, 0xFF], True, False)])

    def test_script(self):
        # reg_type script: the script in data/commands/script is started
        c = self.record(self.controller("Power_Zone_410.json", byte="01"))
        with mock.patch("subprocess.Popen") as popen:
            c.ExecuteCommandSequence([{"reg": "start_generator.py", "reg_type": "script"}])
        command = popen.call_args[0][0]
        self.assertEqual(command[0], sys.executable)
        self.assertTrue(command[1].endswith(os.path.join("data", "commands", "script", "start_generator.py")))
        self.assertEqual(self.writes, [])


# -------------------------------------------------------------------------------
class BitModifierTests(GeneracTestCase):
    """GeneratorController.ProcessBitModifiers (the base class version)."""

    def test_modifiers(self):
        c = self.controller("evo_ac")
        modify = genmonlib.controller.GeneratorController.ProcessBitModifiers
        self.assertEqual(modify(c, {"shiftright": 4}, 0x1230), 0x123)
        self.assertEqual(modify(c, {"shiftleft": 2}, 0x0003), 0x000C)
        self.assertEqual(modify(c, {"swapwords32": True}, 0x00010002), 0x00020001)
        self.assertEqual(modify(c, {"multiplier": 0.1}, 123), 12)
        self.assertAlmostEqual(modify(c, {"multiplier": 0.1}, 123, ReturnFloat=True), 12.3)

    def test_ieee754(self):
        # the register bits as a float (half and double did not work)
        c = self.controller("evo_ac")
        modify = genmonlib.controller.GeneratorController.ProcessBitModifiers
        self.assertEqual(modify(c, {"ieee754": "half"}, 0x4248, ReturnFloat=True), 3.140625)
        self.assertEqual(modify(c, {"ieee754": "single"}, 0x40490FDB, ReturnFloat=True), 3.1415927410125732)
        self.assertEqual(modify(c, {"ieee754": "double"}, 0x400921FB54442D18, ReturnFloat=True),
                         3.141592653589793)
        self.assertEqual(modify(c, {"ieee754": "single"}, 0x7FC00000, ReturnFloat=True), 0.0)  # NaN


# -------------------------------------------------------------------------------
class MaintenanceLogTests(GeneracTestCase):

    ENTRY = {"date": "11/02/2026 14:30", "type": "Repair", "hours": 120.5, "comment": "New battery"}

    def test_add_edit_delete(self):
        c = self.controller("evo_ac")
        self.assertEqual(c.GetMaintLogJSON(), "[]")
        self.assertEqual(c.AddEntryToMaintLog("add_maint_log=" + json.dumps(self.ENTRY)), "OK")
        second = dict(self.ENTRY, type="check", comment="Oil level")
        c.AddEntryToMaintLog("add_maint_log=" + json.dumps(second))
        entries = json.loads(c.GetMaintLogJSON())
        self.assertEqual([e["comment"] for e in entries], ["New battery", "Oil level"])
        self.assertEqual(entries[1]["type"], "Check")  # title case
        # saved to the file in the config folder
        with open(c.MaintLogFileName) as f:
            self.assertEqual(len(json.load(f)), 2)

        edited = dict(self.ENTRY, comment="New battery and cables")
        self.assertEqual(c.EditMaintLogRow("edit_row_maint_log=" + json.dumps({"0": edited})), "OK")
        self.assertEqual(json.loads(c.GetMaintLogJSON())[0]["comment"], "New battery and cables")
        self.assertEqual(c.DeleteMaintLogRow("delete_row_maint_log=0"), "OK")
        self.assertEqual([e["comment"] for e in json.loads(c.GetMaintLogJSON())], ["Oil level"])
        self.assertEqual(c.ClearMaintLog(), "Maintenance Log cleared")
        self.assertEqual(c.GetMaintLogJSON(), "[]")
        self.assertFalse(os.path.exists(c.MaintLogFileName))

    def test_invalid_entries(self):
        c = self.controller("evo_ac")
        # (a date not MM/DD/YYYY HH:MM, an unknown type and a comment that is
        # not text were only logged and saved)
        for entry in [dict(self.ENTRY, hours="120"), dict(self.ENTRY, date=20261102),
                      dict(self.ENTRY, type=5), "not a dict", {"date": "11/02/2026 14:30"},
                      dict(self.ENTRY, date="2026-11-02"), dict(self.ENTRY, date="NaN/NaN/NaN NaN:NaN"),
                      dict(self.ENTRY, type="Upgrade"), dict(self.ENTRY, comment=5)]:
            with self.subTest(entry=entry):
                self.assertNotEqual(c.AddEntryToMaintLog("add_maint_log=" + json.dumps(entry)), "OK")
        for command in ["add_maint_log=not json", "maint_log=" + json.dumps(self.ENTRY), ""]:
            with self.subTest(command=command):
                self.assertNotEqual(c.AddEntryToMaintLog(command), "OK")
        self.assertEqual(c.GetMaintLogJSON(), "[]")
        self.assertEqual(c.DeleteMaintLogRow("delete_row_maint_log=0"), "Error")  # empty log

    def test_types(self):
        # each type the web page offers, in any case
        c = self.controller("evo_ac")
        for kind in ["Maintenance", "check", "REPAIR", "Observation", "Note"]:
            with self.subTest(type=kind):
                self.assertEqual(c.AddEntryToMaintLog("add_maint_log=" + json.dumps(dict(self.ENTRY, type=kind))),
                                 "OK")

    def test_invalid_edit(self):
        # an edit is checked the same way; the entry is not changed
        c = self.controller("evo_ac")
        c.AddEntryToMaintLog("add_maint_log=" + json.dumps(self.ENTRY))
        bad = dict(self.ENTRY, date="yesterday")
        self.assertNotEqual(c.EditMaintLogRow("edit_row_maint_log=" + json.dumps({"0": bad})), "OK")
        self.assertEqual(json.loads(c.GetMaintLogJSON())[0]["date"], self.ENTRY["date"])


# -------------------------------------------------------------------------------
class ExternalDataTests(GeneracTestCase):
    """Data the add-ons send to genmon (gentankutil, gentankdiy, gencthat,
    genmqttin, gentemp, ...)."""

    def test_tank_data(self):
        c = self.controller("evo_ac")
        self.assertEqual(c.SetExternalTankData('set_tank_data={"Tank Name": "Main", "Percentage": 62.5}'), "OK")
        self.assertTrue(c.UseExternalFuelData)
        self.assertEqual(c.GetExternalFuelPercentage(ReturnFloat=True), 62.5)
        # up to four tanks: the average
        c.SetExternalTankData('set_tank_data={"Percentage": 40, "Percentage2": 60}')
        self.assertEqual(c.GetExternalFuelPercentage(ReturnFloat=True), 50.0)
        self.assertEqual(c.SetExternalTankData("set_tank_data=not json"), "Error")

    def test_ct_data(self):
        c = self.controller("evo_ac")
        data = {"current": 12.5, "power": 2.9, "ctdata": [7.5, 5.0], "ctpower": [1.7, 1.2], "voltage": 240}
        self.assertEqual(c.SetExternalCTData("set_power_data=" + json.dumps(data)), "OK")
        self.assertTrue(c.UseExternalCTData)
        self.assertEqual(c.ConvertExternalData("current", ReturnFloat=True), 12.5)
        self.assertEqual(c.ConvertExternalData("power", ReturnFloat=True), 2.9)
        self.assertEqual(c.ConvertExternalData("ct1", ReturnFloat=True), 7.5)
        self.assertEqual(c.ConvertExternalData("ct2", ReturnFloat=True), 5.0)
        self.assertEqual(c.ConvertExternalData("current"), "12.50 A")
        self.assertEqual(c.SetExternalCTData("set_power_data=not json"), "Error")

    def test_sensor_data(self):
        c = self.controller("evo_ac")
        sensors = [{"Shed Temperature": "21.5 C"}, {"Humidity": "40 %"}]
        self.assertEqual(c.SetExternalSensorData("set_sensor_data=" + json.dumps(sensors)), "OK")
        self.assertTrue(c.UseExternalSensorData)
        # an update of one sensor keeps the others
        c.SetExternalSensorData("set_sensor_data=" + json.dumps([{"Humidity": "45 %"}]))
        values = {k: v for item in c.ExternalSensorData for k, v in item.items()}
        self.assertEqual(values, {"Shed Temperature": "21.5 C", "Humidity": "45 %"})
        self.assertEqual(c.SetExternalSensorData(5), "Error")

    def test_gauge_data(self):
        c = self.controller("evo_ac")
        gauges = [{"title": "Shed Temperature", "type": "temperature", "units": "C", "value": 21.5,
                   "nominal": 50, "maximum": 100}]
        self.assertEqual(c.SetExternalGaugeData("set_sensor_gauge_data=" + json.dumps(gauges)), "OK")
        self.assertTrue(c.UseExternalSensorData)
        self.assertEqual(c.SetExternalGaugeData(5), "Error")


# -------------------------------------------------------------------------------
class PowerLogTests(GeneracTestCase):
    """The power log (kwlog.txt) and what is worked out from it: kWh, run
    hours, fuel used."""

    def controller_with_log(self):
        c = self.controller("evo_ac")  # 11 kW, natural gas
        c.Simulation = False  # (simulation mode writes no log files)
        now = datetime.datetime.now()
        # off, then 5.5 kW for an hour, then off again (30 minutes apart)
        for minutes, kw in [(120, "0.0"), (90, "5.5"), (60, "5.5"), (30, "0.0")]:
            c.LogToPowerLog((now - datetime.timedelta(minutes=minutes)).strftime("%x %X"), kw)
        return c

    def test_history(self):
        c = self.controller_with_log()
        history = c.GetPowerHistory("power_log_json")
        self.assertEqual([kw for _, kw in history], ["0.0", "5.5", "5.5", "0.0"])  # newest first
        self.assertEqual(len(c.GetPowerHistory("power_log_json=100")), 3)  # the last 100 minutes
        for command in ["power_log_json=x", "log=5", "power_log_json=1,2,3"]:
            with self.subTest(command=command):
                self.assertEqual(c.GetPowerHistory(command), "Invalid command syntax for command power_log_json")

    def test_totals(self):
        # straight lines between the samples: an hour at 5.5 kW, the last
        # half hour going down to 0 (4.125 kWh)
        c = self.controller_with_log()
        self.assertEqual(c.GetPowerHistory("power_log_json=0,time"), "1.00")
        self.assertEqual(c.GetPowerHistory("power_log_json=0,kw"), "4.12")
        # fuel: the line between the controller's points (50% load: 107,
        # 100%: 159 cubic feet an hour) at 4.125 / 11 kW = 37.5% -> 94
        self.assertEqual(c.GetFuelConsumptionDataPoints(), [0.5, 107.0, 1.0, 159.0, "cubic feet"])
        self.assertEqual(c.GetPowerHistory("power_log_json=0,fuel"), "94.00 cubic feet")

    def test_fuel_consumption(self):
        c = self.controller("evo_ac")
        self.assertEqual(c.GetFuelConsumption(11, 3600), (159.0, "cubic feet"))   # full load, an hour
        self.assertEqual(c.GetFuelConsumption(5.5, 1800), (53.5, "cubic feet"))   # half load, half an hour
        self.assertEqual(c.GetFuelConsumption(5.5, 0), (0.0, "cubic feet"))
        self.assertEqual(c.GetFuelConsumption(-1, 3600)[0], 55.0)                 # no load: the line at 0%
        c.UseMetric = True
        self.assertEqual(c.GetFuelConsumption(11, 3600), (round(159.0 * 0.0283168, 4), "cubic meters"))

    def test_clear(self):
        # a new log starts with a 0 kW entry (the start of the log)
        c = self.controller_with_log()
        with mock.patch.object(genmonlib.controller.time, "sleep"):
            self.assertEqual(c.ClearPowerLog(), "Power Log cleared")
        self.assertEqual([kw for _, kw in c.GetPowerHistory("power_log_json")], ["0.0"])
        with mock.patch.object(genmonlib.controller.time, "sleep"):
            self.assertEqual(c.ClearPowerLog(NoCreate=True), "Power Log cleared")
        self.assertEqual(c.ClearPowerLog(), "Power Log is empty")


# -------------------------------------------------------------------------------
class OutageHistoryTests(GeneracTestCase):

    def test_outage_history(self):
        # outage.txt: start, duration[, fuel]; shown newest first
        c = self.controller("evo_ac")
        with open(c.OutageLog, "w") as f:
            f.write("2026-11-02 14:00:00,1:30:00\n2026-11-05 08:15:00,0:05:10,0.25 gal\nbad line\n")
        self.assertEqual(c.DisplayOutageHistory(), [
            "11-05-2026 08:15:00, Duration: 0:05:10, Estimated Fuel: 0.25 gal",
            "11-02-2026 14:00:00, Duration: 1:30:00"])

    def test_no_outages(self):
        c = self.controller("evo_ac")
        self.assertEqual(c.DisplayOutageHistory(), "")


if __name__ == "__main__":
    unittest.main()


# -------------------------------------------------------------------------------
class SensorLogTests(unittest.TestCase):
    """The sensor logs (data/sensordata/sensor_<name>.txt): read at startup
    for the charts, kept within the entries and size settings."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="sensorlog_")
        self.addCleanup(shutil.rmtree, self.folder)
        c = genmonlib.controller.GeneratorController.__new__(genmonlib.controller.GeneratorController)
        c.log, c.console, c.Simulation = None, None, False
        c.SensorLogPath = self.folder
        c.SensorLogMaxSize = 5.0
        c.MaxSensorLogEntries = 100
        c.SensorLogLock = threading.RLock()
        c.SensorLogLists, c.SensorLogLineCount = {}, {}
        self.c = c
        self.start = datetime.datetime(2026, 1, 1)

    def stamp(self, n):
        return (self.start + datetime.timedelta(minutes=n)).strftime("%x %X")

    def write_file(self, name, count, extra=()):
        with open(self.c.GetSensorLogFile(name), "w") as f:
            for n in range(count):
                f.write("%s,%d.5 F\n" % (self.stamp(n), n))
            for line in extra:
                f.write(line + "\n")

    def file_lines(self, name):
        with open(self.c.GetSensorLogFile(name)) as f:
            return f.read().splitlines()

    def reference_parse(self, path, max_entries):
        # the parse before the speed up (every entry, newest first), decimated
        result = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line[0] == "#":
                    continue
                items = self.c.removeNonPrintable(line).split(",")
                if len(items) != 2:
                    continue
                items[1] = self.c.removeAlpha(items[1])
                result.insert(0, [items[0], items[1], self.c.ParseSensorTimestamp(items[0])])
        return self.c.DecimateList(result, max_entries)

    def test_parse_same_as_before(self):
        # newest first, at most the entries setting, spread over the whole log;
        # comments, blank and bad lines skipped, units removed
        self.write_file("Oil Temp", 1000, extra=["# comment", "", "bad line", "a,b,c",
                                                 self.stamp(2000) + ",\x0799.5 F"])
        path = self.c.GetSensorLogFile("Oil Temp")
        for max_entries in [100, 999, 5000]:
            with self.subTest(max_entries=max_entries):
                parsed = self.c._ParseSensorLogFile(path, MaxEntries=max_entries)
                self.assertEqual(parsed, self.reference_parse(path, max_entries))
        parsed = self.c._ParseSensorLogFile(path, MaxEntries=100)
        self.assertEqual(len(parsed), 100)
        self.assertEqual(parsed[0][:2], [self.stamp(2000), "99.5"])     # newest
        self.assertEqual(parsed[-1][:2], [self.stamp(0), "0.5"])        # oldest
        self.assertGreater(parsed[0][2], parsed[-1][2])

    def test_chart_data(self):
        self.write_file("Oil Temp", 1000)
        self.assertEqual(len(self.c.ReadSensorLogFromFile("Oil Temp")), 100)
        self.assertEqual(self.c.ReadSensorLogFromFile("Missing"), [])

    def test_trimmed_to_the_entries_setting(self):
        # at twice the setting the file is trimmed to it: the newest half as
        # they are, the older entries thinned out (the first one is kept)
        for n in range(200):
            self.c.LogToSensorLog("CPU Temp", self.stamp(n), "%d.5" % n)
        self.assertEqual(len(self.file_lines("CPU Temp")), 200)
        self.c.LogToSensorLog("CPU Temp", self.stamp(200), "200.5")
        lines = self.file_lines("CPU Temp")
        self.assertEqual(len(lines), 100)
        self.assertEqual(lines[-50:], ["%s,%d.5" % (self.stamp(n), n) for n in range(151, 201)])
        self.assertEqual(lines[0], "%s,0.5" % self.stamp(0))
        self.assertEqual(lines, sorted(lines, key=lambda l: self.c.ParseSensorTimestamp(l.split(",")[0])))
        # counted from the file after a trim: the next trim at 200 entries again
        for n in range(201, 301):
            self.c.LogToSensorLog("CPU Temp", self.stamp(n), "%d.5" % n)
        self.assertEqual(len(self.file_lines("CPU Temp")), 200)

    def test_large_file_from_before(self):
        # a file larger than the setting (e.g. from an older version) is
        # trimmed with the first new entry
        self.write_file("Oil Temp", 5000)
        self.c.LogToSensorLog("Oil Temp", self.stamp(5000), "1.5")
        lines = self.file_lines("Oil Temp")
        self.assertEqual(len(lines), 100)
        self.assertEqual(lines[-1], "%s,1.5" % self.stamp(5000))

    def test_size_setting(self):
        # a file at 85% of the size setting: the oldest entries are removed
        # (it was deleted when it was over the size)
        self.c.MaxSensorLogEntries = 100000
        self.c.SensorLogMaxSize = 0.01          # about 10 kB
        for n in range(500):
            self.c.LogToSensorLog("Oil Temp", self.stamp(n), "%d.5 F" % n)
        lines = self.file_lines("Oil Temp")
        self.assertTrue(lines)
        self.assertLess(os.path.getsize(self.c.GetSensorLogFile("Oil Temp")), 0.85 * 0.01 * 1024 * 1024)
        self.assertEqual(lines[-1], "%s,499.5 F" % self.stamp(499))
        first = int(lines[0].split(",")[1].split(".")[0])
        self.assertEqual(lines, ["%s,%d.5 F" % (self.stamp(n), n) for n in range(first, 500)])

    def test_cache_after_trim_and_clear(self):
        self.write_file("Oil Temp", 150)
        self.assertEqual(len(self.c.ReadSensorLogFromFile("Oil Temp")), 100)
        for n in range(150, 201):
            self.c.LogToSensorLog("Oil Temp", self.stamp(n), "%d.5" % n)
        cached = self.c.ReadSensorLogFromFile("Oil Temp")
        self.assertEqual(cached[0][:2], [self.stamp(200), "200.5"])
        self.assertLessEqual(len(cached), 100)
        with mock.patch.object(self.c, "GetSensorNames", return_value=["Oil Temp"]):
            self.assertEqual(self.c.ClearSensorLog(), "Sensor Log cleared")
        self.assertEqual(self.c.ReadSensorLogFromFile("Oil Temp"), [])
