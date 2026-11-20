#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_generac_controllers.py
# PURPOSE: Tests for the Generac controllers: genmonlib/generac_evolution.py
#          (Evolution, Nexus, Evolution 2, liquid cooled), generac_HPanel.py
#          (H-100) and generac_powerzone_pro.py (Power Zone).
#
#          Each test builds the controller as genmon does, in simulation mode
#          (genmonlib/modbus_file.py) from an anonymized register capture in
#          tests/sim/captures, then changes registers to put the generator in
#          other states (running, exercising, alarms, outage, ...) the captures
#          do not show, and checks what genmon reports and the commands it
#          sends.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_generac_controllers
#
# -------------------------------------------------------------------------------

import json
import logging
import os
import shutil
import sys
import datetime
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from addon_fixture import REPO_DIR, FakeThread  # noqa: E402

import genmonlib.controller  # noqa: E402
import genmonlib.generac_HPanel  # noqa: E402
import genmonlib.generac_powerzone_pro  # noqa: E402
import genmonlib.modbus_file  # noqa: E402
from genmonlib.generac_evolution import Evolution  # noqa: E402
from genmonlib.generac_HPanel import HPanel  # noqa: E402
from genmonlib.generac_powerzone_pro import PowerZonePro  # noqa: E402
from genmonlib.myconfig import MyConfig  # noqa: E402

CAPTURES = os.path.join(REPO_DIR, "tests", "sim", "captures")
CLASSES = {"generac_evo_nexus": Evolution, "h_100": HPanel, "powerzone_pro": PowerZonePro}

# logged in simulation mode, not errors in the code: a register the capture
# does not have reads as empty (Evolution), a captured register the controller
# does not list (Power Zone)
SIMULATION_ERRORS = ["Invalid data in UpdateRegisterList", "UpdateRegisterList: Unknown Register"]

# read commands genmon sends to a controller (genmon.py), with arguments
READ_CALLS = [
    ("DisplayStatus", {}), ("DisplayStatus", {"DictOut": True}),
    ("DisplayStatus", {"DictOut": True, "JSONNum": True}),
    ("DisplayMaintenance", {}), ("DisplayMaintenance", {"DictOut": True}),
    ("DisplayMaintenance", {"DictOut": True, "JSONNum": True}),
    ("DisplayOutage", {}), ("DisplayOutage", {"DictOut": True}),
    ("DisplayLogs", {}), ("DisplayLogs", {"DictOut": True}),
    ("DisplayLogs", {"AllLogs": True, "DictOut": True}),
    ("DisplayRegisters", {}), ("DisplayRegisters", {"DictOut": True}),
    ("DisplayRegisters", {"AllRegs": True, "DictOut": True}),
    ("GetStartInfo", {}), ("GetStartInfo", {"NoTile": True}), ("GetStatusForGUI", {}),
    ("GetBaseStatus", {}), ("GetOneLineStatus", {}), ("GetController", {}),
    ("GetRunHours", {}), ("GetCommStatus", {}), ("GetRegisterLabels", {}),
    ("SystemInAlarm", {}), ("PowerMeterIsSupported", {}), ("GetSensorNames", {}),
]


def load_capture(name):
    with open(os.path.join(CAPTURES, "captures.json")) as f:
        capture = next(c for c in json.load(f)["captures"] if c["name"] == name)
    with open(os.path.join(CAPTURES, capture["file"])) as f:
        registers = json.load(f)
    return capture, registers


class Collect(logging.Handler):
    def __init__(self):
        super(Collect, self).__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


class FakeFeedback(object):
    def __init__(self):
        self.sent = []

    def SendFeedback(self, *args, **kwargs):
        self.sent.append(args)


class FakeMessage(object):
    """genmon's notification queue (mymail)."""

    def __init__(self):
        self.sent, self.types = [], []

    def SendMessage(self, *args, **kwargs):
        self.sent.append(args)
        self.types.append(kwargs.get("msgtype"))
        return True


# -------------------------------------------------------------------------------
class GeneracTestCase(unittest.TestCase):

    def controller(self, name, registers=None, settings=None):
        """The controller for capture name (tests/sim/captures), its registers
        read once as genmon does when it starts. registers: changes to the
        captured holding registers {register: value}."""
        capture, data = load_capture(name)
        data["Registers"].update(registers or {})
        folder = tempfile.mkdtemp(prefix="generac_")
        self.addCleanup(shutil.rmtree, folder)
        self.folder = folder
        shutil.copy(os.path.join(REPO_DIR, "conf", "genmon.conf"), folder)
        config = MyConfig(filename=os.path.join(folder, "genmon.conf"), section="GenMon")
        values = {"controllertype": capture["controllertype"], "address": capture["address"],
                  "model": capture["model"], "nominalkw": capture["nominalkw"],
                  "fueltype": capture.get("fueltype", "Natural Gas"), "loglocation": folder,
                  "userdatalocation": folder, "sitename": "Test"}
        values.update(settings or {})
        for key, value in values.items():
            config.WriteValue(key, str(value))
        path = os.path.join(folder, "registers.json")
        with open(path, "w") as f:
            json.dump(data, f)

        self.log = logging.getLogger("generac_test")
        self.log.handlers, self.log.propagate = [], False
        self.errors = Collect()
        self.log.addHandler(self.errors)
        self.message = FakeMessage()
        self.feedback = FakeFeedback()
        for patch in [mock.patch.object(genmonlib.controller, "MyThread", FakeThread),
                      mock.patch.object(genmonlib.modbus_file, "MyThread", FakeThread),
                      mock.patch.object(genmonlib.modbus_file.time, "sleep")]:
            patch.start()
            self.addCleanup(patch.stop)
        cls = CLASSES[capture["controllertype"]]
        controller = cls(self.log, simulation=True, simulationfile=path, message=self.message,
                         feedback=self.feedback, config=config, ConfigFilePath=folder)
        controller.ModBus.SimulateTime = False
        self.addCleanup(self.close_logs)
        controller.InitDevice()
        self.writes = []
        controller.ModBus.ProcessWriteTransaction = self.record_write
        # no pause between Modbus frames, no network look up for the IP address
        controller.DelayBetweenFrames = lambda *args, **kwargs: None
        controller.GetNetworkIp = lambda: "192.0.2.1"
        return controller

    def record_write(self, Register, Length, Data, IsCoil=False):
        self.writes.append((Register.lower(), Length, list(Data)))
        return True

    @staticmethod
    def close_logs():
        for name in ["mymodbus"]:
            logger = logging.getLogger(name)
            for handler in list(logger.handlers):
                handler.close()
                logger.removeHandler(handler)

    def set_registers(self, controller, registers):
        """Change holding registers after start up (as a new read would)."""
        for register, value in registers.items():
            controller.Holding[register] = value
            controller.ModBus.Registers[register] = value

    def code_errors(self):
        return [m for m in self.errors.messages if ("Error" in m or "error" in m)
                and not any(e in m for e in SIMULATION_ERRORS)]

    def read_all(self, controller):
        """Every read command genmon sends; returns the answers by name."""
        answers = {}
        for method, kwargs in READ_CALLS:
            function = getattr(controller, method, None)
            if function is None:
                continue
            answers[(method, tuple(sorted(kwargs.items())))] = function(**kwargs)
        return answers


# -------------------------------------------------------------------------------
class ReadTests(GeneracTestCase):

    def test_every_read_command(self):
        for name in ["evo_ac", "nexus_ac", "evo_lc", "h100", "powerzone"]:
            with self.subTest(capture=name):
                controller = self.controller(name)
                answers = self.read_all(controller)
                status = answers[("DisplayStatus", (("DictOut", True),))]
                self.assertIn("Status", status)
                for call, answer in answers.items():
                    json.dumps(answer)  # every answer can be sent as JSON
                self.assertEqual(self.code_errors(), [])


# -------------------------------------------------------------------------------
class EvolutionCommandTests(GeneracTestCase):

    def test_remote_commands(self):
        # setremote: the command number is written to register 0003
        c = self.controller("evo_ac")
        for command, number in [("start", 0x01), ("stop", 0x00), ("starttransfer", 0x02),
                                ("startexercise", 0x03), ("resetmainttimer", 0x09),
                                ("resetmaintalarm", 0x08), ("resetalarm", 0x0D), ("auto", 0x0F),
                                ("manual", 0x0E), ("off", 0x10)]:
            with self.subTest(command=command):
                self.writes = []
                self.assertEqual(c.SetGeneratorRemoteCommand("setremote=" + command),
                                 "Remote command sent successfully")
                self.assertEqual(self.writes, [("0003", 1, [0x00, number])])

    def test_remote_commands_power_zone_200(self):
        # Power Zone 200: other registers, start and start / transfer run for
        # 300 seconds (0x012c, written to 0004 first)
        c = self.controller("evo_ac")
        c.PowerZone200 = True
        for command, writes in [
                ("start", [("0004", 1, [0x01, 0x2C]), ("0003", 1, [0x00, 0x19])]),
                ("stop", [("0003", 1, [0x00, 0x1A])]),
                ("starttransfer", [("0004", 1, [0x01, 0x2C]), ("0003", 1, [0x00, 0x28])]),
                ("startexercise", [("0003", 1, [0x00, 0x1B])])]:
            with self.subTest(command=command):
                self.writes = []
                c.SetGeneratorRemoteCommand("setremote=" + command)
                self.assertEqual(self.writes, writes)

    def test_invalid_remote_commands(self):
        c = self.controller("evo_ac")
        for command in ["setremote=fly", "setremote", "setremote=start=now", "remote=start"]:
            with self.subTest(command=command):
                self.assertIn("Invalid command syntax", c.SetGeneratorRemoteCommand(command))
        self.assertEqual(self.writes, [])

    def test_exercise_time(self):
        # day of the week to 002e (Sunday = 0), hour and minute to 002c
        c = self.controller("evo_lc")
        self.assertEqual(c.SetGeneratorExerciseTime("setexercise=Monday,13:30"),
                         "Set Exercise Time Command sent")
        self.assertEqual(self.writes, [("002e", 1, [0, 1]), ("002c", 1, [13, 30])])

    def test_exercise_frequency(self):
        # enhanced exercise frequency: weekly / biweekly / monthly to 002d
        c = self.controller("evo_lc")
        c.bEnhancedExerciseFrequency = True
        for command, writes in [
                ("setexercise=Saturday,09:05,weekly",
                 [("002d", 1, [0, 0]), ("002e", 1, [0, 6]), ("002c", 1, [9, 5])]),
                ("setexercise=Sunday,23:59,biweekly",
                 [("002d", 1, [0, 1]), ("002e", 1, [0, 0]), ("002c", 1, [23, 59])]),
                ("setexercise=15,12:00,monthly",
                 [("002d", 1, [0, 2]), ("002e", 1, [0, 15]), ("002c", 1, [12, 0])])]:
            with self.subTest(command=command):
                self.writes = []
                self.assertEqual(c.SetGeneratorExerciseTime(command), "Set Exercise Time Command sent")
                self.assertEqual(self.writes, writes)

    def test_invalid_exercise_time(self):
        c = self.controller("evo_lc")
        for command in ["setexercise=Funday,13:30", "setexercise=Monday,24:00",
                        "setexercise=Monday,13:60", "setexercise=Monday", "setexercise=29,10:00,monthly",
                        "setexercise=Monday,13:30,daily", "setexercise=Monday,13:30,biweekly",
                        "exercise=Monday,13:30"]:
            with self.subTest(command=command):
                self.assertEqual(c.SetGeneratorExerciseTime(command),
                                 "Invalid command syntax for command setexercise")
        self.assertEqual(self.writes, [])

    def test_exercise_time_older_firmware(self):
        # Evolution firmware before V1.10: the older way of setting the time
        c = self.controller("evo_lc")
        c.GetFirmwareVersion = lambda: "V1.05"
        result = c.SetGeneratorExerciseTime("setexercise=Monday,13:30")
        self.assertTrue(c.bUseLegacyWrite)
        self.assertNotIn("Invalid", result)
        self.assertTrue(self.writes)

    def test_quiet_mode(self):
        c = self.controller("evo_lc")
        for command, value in [("setquiet=on", 1), ("setquiet=off", 0), ("setquiet=On", 1),
                               ("setquiet= OFF ", 0)]:
            with self.subTest(command=command):
                self.writes = []
                self.assertEqual(c.SetGeneratorQuietMode(command), "Set Quiet Mode Command sent")
                self.assertEqual(self.writes, [("002f", 1, [0, value])])
        # exactly on or off ("none" turned quiet mode on)
        self.writes = []
        for command in ["setquiet=maybe", "setquiet=none", "setquiet=yes", "setquiet=1", "setquiet="]:
            with self.subTest(command=command):
                self.assertEqual(c.SetGeneratorQuietMode(command),
                                 "Invalid command syntax for command setquiet")
        self.assertEqual(self.writes, [])
        # air cooled Evolution 1: no quiet mode setting
        self.assertEqual(self.controller("evo_ac").SetGeneratorQuietMode("setquiet=on"),
                         "Not supported on this controller.")


# -------------------------------------------------------------------------------
class EvolutionStateTests(GeneracTestCase):

    def test_engine_state(self):
        # register 0001, high word
        c = self.controller("evo_lc")
        c.SystemInAlarm = lambda: False
        for value, state in [(0x00000000, "Off - Ready"), (0x00010000, "Startup Delay Timer Activated"),
                             (0x00020000, "Cranking"), (0x00030000, "Running"),
                             (0x00040000, "Exercising"), (0x00050000, "Cooling Down"),
                             (0x00060000, "Running in Warning"), (0x00080000, "Stopped in Alarm"),
                             (0x00090000, "Stopped"), (0x000A0000, "Stopped in Warning"),
                             (0x000B0000, "Cranking Paused"), (0x000C0000, "Running - Warm Up"),
                             (0x000D0000, "Cranking in Warning"), (0x000E0000, "Cranking in Alarm"),
                             (0x000F0000, "Off - Remote Switch Off"),
                             (0x00180000, "Running - Transfer Switch Activated"),
                             (0x001B0000, "Running Remote Transfer"),
                             (0x001F0000, "Firmware Update in Progress")]:
            with self.subTest(value="%08x" % value):
                self.assertEqual(c.GetEngineState(Reg0001Value=value), state)
        c.SystemInAlarm = lambda: True
        self.assertEqual(c.GetEngineState(Reg0001Value=0x00030000), "Running in Alarm")
        self.assertEqual(c.GetEngineState(Reg0001Value=0x00020000), "Cranking in Alarm")

    def test_unknown_engine_state(self):
        # reported to the developer
        c = self.controller("evo_lc")
        self.assertEqual(c.GetEngineState(Reg0001Value=0x00070000), "UNKNOWN: 00070000")
        self.assertEqual(self.feedback.sent[-1][0], "Unknown EngineState")

    def test_switch_state(self):
        # register 0001, low word
        c = self.controller("evo_lc")
        for value, state in [(0x00, "Auto"), (0x06, "Manual"), (0x07, "Off"), (0x17, "Two Wire Stop"),
                             (0x000F0000, "Auto"), (0x0B, "System in Alarm"),
                             (0x000F000B, "System in Alarm")]:
            with self.subTest(value="%08x" % value):
                self.assertEqual(c.GetSwitchState(Reg0001Value=value), state)

    def test_alarm_codes(self):
        # in alarm: the alarm code is the low word of register 0001
        c = self.controller("evo_lc")
        for code, alarm in [(0x01, "Low Battery"), (0x0B, "Overcrank"), (0x14, "Check Battery"),
                            (0x1F, "Service A Due")]:
            with self.subTest(code=code):
                self.set_registers(c, {"0001": "%08x" % (0x00080000 | code)})
                self.assertTrue(c.SystemInAlarm())
                self.assertIn(alarm, c.GetAlarmState())
        self.set_registers(c, {"0001": "00000000"})
        self.assertFalse(c.SystemInAlarm())
        self.assertEqual(c.GetAlarmState(), "")


# -------------------------------------------------------------------------------
class EvolutionNotificationTests(GeneracTestCase):

    def test_alarm_message(self):
        # a change of register 0001: an alert in alarm, a notice when it clears
        c = self.controller("evo_lc")
        self.set_registers(c, {"0001": "0008000b"})
        c.CheckForAlarms()
        subject, body = self.message.sent[-1][:2]
        self.assertIn("Generator Alert at Test", subject)
        self.assertIn("CRITICAL", subject)
        self.assertIn("Overcrank", body)
        self.set_registers(c, {"0001": "00000000"})
        c.CheckForAlarms()
        subject, body = self.message.sent[-1][:2]
        self.assertEqual(subject, "Generator Notice: Test")
        self.assertIn("No Alarms: 0001:00000000", body)
        # no change: no message
        count = len(self.message.sent)
        c.CheckForAlarms()
        self.assertEqual(len(self.message.sent), count)

    def test_outage(self):
        # utility voltage (0009) below the threshold: outage; above the
        # pickup voltage: restored (the outage log is not written in
        # simulation mode)
        c = self.controller("evo_lc")
        c.CheckForOutage()
        self.assertFalse(c.SystemInOutage)
        self.set_registers(c, {"0009": "0000"})
        c.CheckForOutage()
        self.assertTrue(c.SystemInOutage)
        self.assertEqual(self.message.sent[-1][0], "Outage Notice at Test")
        self.set_registers(c, {"0009": "00f0"})
        c.CheckForOutage()
        self.assertFalse(c.SystemInOutage)
        self.assertEqual(self.message.sent[-1][0], "Outage Recovery Notice at Test")
        self.assertIn("Duration of outage", self.message.sent[-1][1])

    def test_transfer_switch(self):
        # liquid cooled: register 0053 bit 0, a message when it changes
        c = self.controller("evo_lc")
        self.set_registers(c, {"0053": "0031"})
        c.CheckForOutage()
        self.assertEqual(self.message.sent[-1][0], "Transfer Switch Changed State Notice at Test")
        self.assertIn("supplied by the generator", self.message.sent[-1][1])
        self.set_registers(c, {"0053": "0030"})
        c.CheckForOutage()
        self.assertIn("supplied by the utility", self.message.sent[-1][1])

    def test_outage_check_disabled(self):
        c = self.controller("evo_lc", settings={"disableoutagecheck": "True"})
        self.set_registers(c, {"0009": "0000"})
        c.CheckForOutage()
        self.assertFalse(c.SystemInOutage)


# -------------------------------------------------------------------------------
class EvolutionModelTests(GeneracTestCase):

    def test_model_variants(self):
        # the code for the other Evolution family models (Evolution 2, Power
        # Zone 200, Evolution 4.5L, pre Nexus, Synergy, PowerPact) answers
        # every read command and checks alarms and outages without an error
        for name, flag in [("evo_ac", "Evolution2"), ("evo_lc", "Evolution2"), ("evo_ac", "PowerZone200"),
                           ("evo_lc", "Evo45L"), ("nexus_ac", "PreNexus"), ("evo_ac", "SynergyController"),
                           ("evo_ac", "PowerPact")]:
            with self.subTest(capture=name, model=flag):
                c = self.controller(name)
                setattr(c, flag, True)
                answers = self.read_all(c)
                for answer in answers.values():
                    json.dumps(answer)
                c.CheckForAlarms()
                c.CheckForOutage()
                self.assertEqual(self.code_errors(), [])

    def test_evolution_2_model_11(self):
        # model ID 11 (register 0019) is the 60 Hz single phase EcoGen or the
        # 20 kW 50 Hz 3 phase export model, picked by the phase or frequency
        # setting; Phase is a number from genmon.conf, then text (issue 1581)
        for phase, freq, expected in [(1, "60", "1"), (3, "60", "3"), ("3", "60", "3"),
                                      (1, "50", "3"), ("1", "50", "3")]:
            with self.subTest(phase=phase, frequency=freq):
                c = self.controller("evo_ac", registers={"0019": "000b"})
                c.Evolution2 = True
                c.Phase, c.NominalFreq = phase, freq
                self.assertEqual(c.GetModelInfo("phase"), expected)
                c.Phase = c.GetModelInfo("phase")   # as InitDevice does
                self.assertEqual(c.GetModelInfo("phase"), expected)
                self.assertEqual(c.GetModelInfo("kw"), "20" if expected == "3" else "15")

    def test_power_zone_200_alarms(self):
        # alarm flags 0637 / 0638, then a register for each alarm / warning
        c = self.controller("evo_ac")
        c.PowerZone200 = True
        self.set_registers(c, {"0637": "0000", "0638": "0000", "0001": "00000000"})
        self.assertFalse(c.SystemInAlarm())
        self.assertEqual(c.GetAlarmState(), "")
        self.set_registers(c, {"0637": "0001", "2198": "0001", "21d1": "0001"})
        self.assertTrue(c.SystemInAlarm())
        alarms = c.GetAlarmState()
        self.assertIn("Warning - BATTERY VOLT LOW", alarms)
        self.assertIn("Alarm - OVERCRANK", alarms)


class FixedTime(datetime.datetime):
    """datetime.datetime with now() Wednesday 11/18/2026 14:05:09."""

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 18, 14, 5, 9)


# -------------------------------------------------------------------------------
class HPanelTests(GeneracTestCase):

    def test_remote_commands(self):
        # start bits (019c, 3 registers): start, parallel, transfer
        c = self.controller("h100")
        for command, data in [("start", [0, 0x80, 0, 0, 0, 0]), ("stop", [0, 0, 0, 0, 0, 0]),
                              ("starttransfer", [0, 0x80, 0, 0, 0, 0x80]),
                              ("startparallel", [0, 0x80, 0, 0x80, 0, 0])]:
            with self.subTest(command=command):
                self.writes = []
                self.assertEqual(c.SetGeneratorRemoteCommand("setremote=" + command),
                                 "Remote command sent successfully")
                self.assertEqual(self.writes, [("019c", 3, data)])
        for command, register, data in [("quiettest", "022b", [0, 1]), ("quietteststop", "022b", [0, 0]),
                                        ("ackalarm", "012e", [0, 1])]:
            with self.subTest(command=command):
                self.writes = []
                self.assertIn("sent successfully", c.SetGeneratorRemoteCommand("setremote=" + command))
                self.assertEqual(self.writes, [(register, 1, data)])
        self.writes = []
        self.assertIn("Invalid command", c.SetGeneratorRemoteCommand("setremote=fly"))
        self.assertIn("Invalid command", c.SetGeneratorRemoteCommand("setremote"))
        self.assertEqual(self.writes, [])

    def test_set_time(self):
        # one write of the four time registers (00e0 - 00e3): hour, minute,
        # second, day of the week (Sunday = 1), month, day, year - 2000
        c = self.controller("h100")
        with mock.patch.object(genmonlib.generac_HPanel.datetime, "datetime", FixedTime):
            c.SetGeneratorTimeDate()
        self.assertEqual(self.writes, [("00e0", 4, [14, 5, 9, 4, 11, 18, 26, 0])])

    def test_alarm(self):
        # active alarm count (012f) or unacknowledged alarms (012e)
        c = self.controller("h100")
        self.assertFalse(c.SystemInAlarm())
        self.set_registers(c, {"012f": "0001"})
        self.assertTrue(c.SystemInAlarm())
        self.set_registers(c, {"012f": "0000", "012e": "0002"})
        self.assertTrue(c.SystemInAlarm())

    def test_state_change_message(self):
        # a message when the engine state changes
        c = self.controller("h100")
        c.CheckForAlarms()
        count = len(self.message.sent)
        c.CheckForAlarms()
        self.assertEqual(len(self.message.sent), count)  # no change, no message
        # in alarm: the state change notice and an alarm notice
        self.set_registers(c, {"012f": "0001"})
        c.GetOneLineStatus = lambda: "Running"
        c.CheckForAlarms()
        subjects = [m[0] for m in self.message.sent[count:]]
        self.assertEqual(subjects, ["Generator Notice: Test", "Generator Notice: ALARM Active at Test"])
        self.assertEqual(self.message.types[count:], ["warn", "warn"])

    def test_outage(self):
        # industrialoutagecheck: the transfer switch (output 6) on the
        # generator is an outage
        c = self.controller("h100", settings={"industrialoutagecheck": "True"})
        self.set_registers(c, {"0087": "0002"})
        c.CheckForOutage()
        self.assertTrue(c.SystemInOutage)
        self.assertEqual(self.message.types[-1], "outage")
        self.set_registers(c, {"0087": "0004"})
        c.CheckForOutage()
        self.assertFalse(c.SystemInOutage)
        self.assertEqual(self.message.types[-1], "outage")
        # off (the default): no outage check
        c = self.controller("h100")
        self.set_registers(c, {"0087": "0002"})
        c.CheckForOutage()
        self.assertFalse(c.SystemInOutage)


# -------------------------------------------------------------------------------
class PowerZoneTests(GeneracTestCase):

    def test_remote_commands(self):
        c = self.controller("powerzone")
        for command, register, data in [("start", "02c4", [0, 1]), ("stop", "02c4", [0, 0]),
                                        ("quiettest", "019a", [0, 1]), ("quietteststop", "019a", [0, 0]),
                                        ("ackalarm", "0162", [0, 1]), ("clearalarm", "0162", [0, 4]),
                                        ("resetallalarm", "0162", [0, 6]),
                                        ("silencealarm", "0162", [0, 8])]:
            with self.subTest(command=command):
                self.writes = []
                reply = c.SetGeneratorRemoteCommand("setremote=" + command)
                self.assertIn("sent successfully", reply)
                if command not in ["start", "stop"]:
                    self.assertIn("(%s)" % command, reply)
                self.assertEqual(self.writes, [(register, 1, data)])
        # the old misspelled names are not commands
        for command in ["cleartalarm", "silencetalarm"]:
            self.assertIn("Invalid command", c.SetGeneratorRemoteCommand("setremote=" + command))
        self.writes = []
        self.assertEqual(c.SetGeneratorRemoteCommand("setremote=starttransfer"),
                         "Remote start transfer not supported")
        self.assertIn("Invalid command", c.SetGeneratorRemoteCommand("setremote=fly"))
        self.assertEqual(self.writes, [])

    def test_set_time(self):
        # hour / minute, second / day of the week (Sunday = 1), month / day,
        # year - 2000
        c = self.controller("powerzone")
        with mock.patch.object(genmonlib.generac_powerzone_pro.datetime, "datetime", FixedTime):
            c.SetGeneratorTimeDate()
        self.assertEqual(self.writes, [("015d", 1, [14, 5]), ("015e", 1, [9, 4]),
                                       ("015f", 1, [11, 18]), ("0160", 1, [26, 0])])

    def test_engine_state(self):
        c = self.controller("powerzone")
        for value, state in [(0, "Engine Stopped, Off"), (1, "Engine Running Manual"),
                             (4, "Engine Running Exercise Without Transfer"),
                             (7, "Engine Running Utility Loss"),
                             (6, "Engine Running Exercise With Transfer"), (8, "Engine Stopped Auto"),
                             (11, "Engine Running External Switch Start"), (99, "Unknown")]:
            with self.subTest(value=value):
                self.set_registers(c, {"0165": "%04x" % value})
                self.assertEqual(c.GetEngineState(), state)

    def test_generator_status_and_alarm(self):
        c = self.controller("powerzone")
        for value, status, alarm in [(1, "Stopped", False), (7, "Warming Engine", False),
                                     (10, "Alarms are Active", True), (11, "Cooling Down", False),
                                     (14, "Alarm Stopped Engine", True), (99, "Unknown", False)]:
            with self.subTest(value=value):
                self.set_registers(c, {"0166": "%04x" % value})
                self.assertEqual(c.GetGeneratorStatus(), status)
                self.assertEqual(c.SystemInAlarm(), alarm)
        # or an alarm flag (01b5)
        self.set_registers(c, {"0166": "0001", "01b5": "0001"})
        self.assertTrue(c.SystemInAlarm())

    def test_state_change_message(self):
        c = self.controller("powerzone")
        c.CheckForAlarms()
        count = len(self.message.sent)
        # in alarm: the state change notice and an alarm notice
        self.set_registers(c, {"0165": "0001", "0166": "000a"})
        c.CheckForAlarms()
        subjects = [m[0] for m in self.message.sent[count:]]
        self.assertEqual(subjects, ["Generator Notice: Test", "Generator Notice: ALARM Active at Test"])
        self.assertEqual(self.message.types[count:], ["warn", "warn"])
        # back to normal: the state change notice and an alarm clear notice
        count = len(self.message.sent)
        self.set_registers(c, {"0165": "0008", "0166": "0001"})
        c.CheckForAlarms()
        subjects = [m[0] for m in self.message.sent[count:]]
        self.assertEqual(subjects, ["Generator Notice: Test", "Generator Notice: ALARM Clear at Test"])
        self.assertEqual(self.message.types[count:], ["info", "warn"])


if __name__ == "__main__":
    unittest.main()
