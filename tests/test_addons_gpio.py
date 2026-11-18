#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_addons_gpio.py
# PURPOSE: Tests for the Raspberry Pi GPIO add-ons:
#          addon/gengpio.py sets outputs (LEDs) for the generator state, alarm
#          codes, monitor health, internet, CPU temperature and a time of day
#          output.
#          addon/gengpioin.py starts, stops or starts and transfers the
#          generator when an input changes.
#          addon/gengpioledblink.py blinks one LED for genmon's health.
#          addon/gencustomgpio.py shows inputs on the Monitor page (writes
#          userdefined.json).
#
#          genmon, threads and RPi.GPIO are fakes (see addon_fixture.py); the
#          fake GPIO records the pins set up, written and read.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_addons_gpio
#
# -------------------------------------------------------------------------------

import datetime
import json
import logging
import os
import runpy
import shutil
import signal
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from addon_fixture import ADDON_DIR, FakeGenmon, FakeThread, AddOnFixture  # noqa: E402


def fake_gpio():
    """RPi.GPIO: records the pins set up and written; the test sets inputs."""
    gpio = types.ModuleType("RPi.GPIO")
    gpio.BOARD, gpio.BCM, gpio.OUT, gpio.IN = "BOARD", "BCM", "OUT", "IN"
    gpio.HIGH, gpio.LOW = 1, 0
    gpio.PUD_UP, gpio.PUD_DOWN, gpio.PUD_OFF = "PUD_UP", "PUD_DOWN", "PUD_OFF"
    gpio.RISING, gpio.FALLING, gpio.BOTH = "RISING", "FALLING", "BOTH"
    gpio.RPI_INFO = {"TYPE": "Fake Pi"}
    gpio.setups, gpio.outputs, gpio.history, gpio.inputs = {}, {}, [], {}
    gpio.events, gpio.callbacks, gpio.detected = {}, {}, set()
    gpio.calls = []

    def setup(pin, direction, initial=None, pull_up_down=None):
        gpio.setups[pin] = (direction, initial, pull_up_down)
        if initial is not None:
            gpio.outputs[pin] = initial

    def output(pin, state):
        gpio.outputs[pin] = state
        gpio.history.append((pin, state))

    def add_event_detect(pin, edge, bouncetime=None):
        gpio.events[pin] = (edge, bouncetime)

    def add_event_callback(pin, callback):
        gpio.callbacks[pin] = callback

    def event_detected(pin):
        if pin in gpio.detected:
            gpio.detected.discard(pin)
            return True
        return False

    def record(name):
        return lambda *args, **kwargs: gpio.calls.append(name)

    gpio.setup, gpio.output, gpio.input = setup, output, lambda pin: gpio.inputs.get(pin, 0)
    gpio.add_event_detect, gpio.add_event_callback = add_event_detect, add_event_callback
    gpio.event_detected = event_detected
    for name in ["setmode", "setwarnings", "cleanup", "remove_event_detect"]:
        setattr(gpio, name, record(name))
    rpi = types.ModuleType("RPi")
    rpi.GPIO = gpio
    return gpio, {"RPi": rpi, "RPi.GPIO": gpio}


def monitor(health="OK", cpu_temp="45.0 C"):
    return json.dumps({"Monitor": [
        {"Generator Monitor Stats": [{"Monitor Health": health}]},
        {"Communication Stats": []},
        {"Platform Stats": [{"CPU Temperature": cpu_temp}]}]})


# -------------------------------------------------------------------------------
class GenGPIOTests(unittest.TestCase):

    # header pins (gengpio.conf defaults)
    READY, ALARM, SERVICE, RUNNING, EXERCISING, OFF = 16, 18, 22, 26, 24, 21
    GENMON, INTERNET, LOW_OIL, OVERCRANK = 3, 5, 31, 40

    def setUp(self):
        self.now = datetime.datetime(2026, 11, 2, 12, 0)
        test = self

        class FakeDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return test.now

        self.clock = types.SimpleNamespace(datetime=FakeDateTime)

    def start(self, controller="Evolution 2.0, Air Cooled", **settings):
        self.gpio, modules = fake_gpio()
        fixture = AddOnFixture("gengpio", "GenGPIO", settings, modules=modules,
                               patches=[("datetime", self.clock)])
        fixture.state["answers"] = {"monitor": "Controller Detected : " + controller,
                                    "monitor_json": monitor(), "network_status": "OK"}
        self.addCleanup(fixture.stop)
        fixture.start()
        self.fixture, self.addon = fixture, fixture.addon
        return fixture

    def high(self):
        return sorted(pin for pin, state in self.gpio.outputs.items() if state == self.gpio.HIGH)

    def test_setup(self):
        self.start()
        self.assertTrue(self.addon.Evolution)
        for pin in [self.READY, self.ALARM, self.GENMON, self.LOW_OIL]:
            self.assertEqual(self.gpio.setups[pin], ("OUT", 0, None))
        self.assertNotIn(0, self.gpio.setups)  # ER_PITEMP / PIN_EXTERNAL_SIGNAL off
        self.assertIn("setmode", self.gpio.calls)

    def test_generator_state(self):
        self.start()
        for base, pin in [("READY", self.READY), ("RUNNING", self.RUNNING),
                          ("RUNNING-MANUAL", self.RUNNING), ("EXERCISING", self.EXERCISING),
                          ("SERVICEDUE", self.SERVICE), ("OFF", self.OFF), ("MANUAL", self.OFF)]:
            with self.subTest(base=base):
                self.fixture.state["base"] = base
                self.addon.UpdateGeneratorState()
                self.assertEqual(self.high(), [pin])

    def test_alarm_code(self):
        # Evolution: the last alarm code (register 05f1) sets its own output
        self.start()
        self.fixture.state["base"] = "ALARM"
        self.fixture.state["answers"]["getregvalue=05f1"] = "%04x" % 1301  # Low Oil Pressure
        self.addon.UpdateGeneratorState()
        self.assertEqual(self.high(), [self.ALARM, self.LOW_OIL])
        # back to ready: the alarm outputs go off
        self.fixture.state["base"] = "READY"
        self.addon.UpdateGeneratorState()
        self.assertEqual(self.high(), [self.READY])

    def test_alarm_not_evolution(self):
        # Nexus has no last alarm code
        self.start(controller="Nexus, Air Cooled")
        self.fixture.state["base"] = "ALARM"
        self.addon.UpdateGeneratorState()
        self.assertEqual(self.high(), [self.ALARM])
        self.assertNotIn("generator: getregvalue=05f1", self.fixture.genmon.commands)

    def test_monitor_health_and_internet(self):
        self.start()
        self.addon.UpdateMonitorHealth(json.loads(monitor(health="System Initializing")))
        self.fixture.state["answers"]["network_status"] = "Network Down"
        self.addon.UpdateInternetStatus()
        self.assertEqual(self.high(), [self.GENMON, self.INTERNET])
        self.addon.UpdateMonitorHealth(json.loads(monitor(health="OK")))
        self.fixture.state["answers"]["network_status"] = "OK"
        self.now += datetime.timedelta(seconds=30)  # checked every 20 seconds
        self.addon.UpdateInternetStatus()
        self.assertEqual(self.high(), [])

    def test_cpu_temperature(self):
        self.start(ER_PITEMP="7", CPU_THRESHOLD_TEMP="158")
        self.addon.UpdateCPUTemp(json.loads(monitor(cpu_temp="160.5 F")))
        self.assertEqual(self.high(), [7])
        self.addon.UpdateCPUTemp(json.loads(monitor(cpu_temp="120.0 F")))
        self.assertEqual(self.high(), [])

    def test_time_of_day_output(self):
        for on, off, times in [
                ("08:00", "17:00", {7: 0, 8: 1, 12: 1, 17: 0, 23: 0}),
                ("22:00", "06:00", {3: 1, 6: 0, 12: 0, 22: 1, 23: 1})]:   # overnight
            with self.subTest(on=on, off=off):
                self.start(PIN_EXTERNAL_SIGNAL="8", PIN_EXTERNAL_SIGNAL_ON_TIME=on,
                           PIN_EXTERNAL_SIGNAL_OFF_TIME=off)
                for hour, state in times.items():
                    self.now = datetime.datetime(2026, 11, 2, hour, 0)
                    self.addon.UpdateExternalSignal()
                    self.assertEqual(self.gpio.outputs[8], state, "at %d:00" % hour)

    def test_time_of_day_output_invalid_time(self):
        self.start(PIN_EXTERNAL_SIGNAL="8", PIN_EXTERNAL_SIGNAL_ON_TIME="8am",
                   PIN_EXTERNAL_SIGNAL_OFF_TIME="17:00")
        self.assertEqual(self.addon.Pins["PIN_EXTERNAL_SIGNAL"], 0)

    def test_thread(self):
        fixture = self.start()
        fixture.state["base"] = "EXERCISING"
        fixture.run_thread("GPIOThread")
        self.assertEqual(self.high(), [self.EXERCISING])

    def test_close(self):
        self.start()
        self.addon.Close()
        self.assertIn("cleanup", self.gpio.calls)


# -------------------------------------------------------------------------------
class StopRunning(BaseException):
    pass


class GenGPIOInTests(unittest.TestCase):
    """gengpioin.py runs from its __main__ block: run as a program."""

    def run_program(self, conf_file=True, **settings):
        self.gpio, modules = fake_gpio()
        folder = tempfile.mkdtemp(prefix="addon_test_")
        self.addCleanup(shutil.rmtree, folder)
        conf = os.path.join(folder, "gengpioin.conf")
        shutil.copy(os.path.join(ADDON_DIR, os.pardir, "conf", "gengpioin.conf"), conf)
        from genmonlib.myconfig import MyConfig
        config = MyConfig(filename=conf, section="gengpioin")
        for key, value in settings.items():
            config.WriteValue(key, value)
        if not conf_file:
            os.remove(conf)
        log = logging.getLogger("addon_test_gengpioin")
        log.handlers, log.propagate = [logging.NullHandler()], False
        self.genmon = FakeGenmon({"base": "READY"})
        import genmonlib.myclient
        import genmonlib.mysupport
        import genmonlib.mythread
        with mock.patch.dict(sys.modules, modules), \
                mock.patch.object(genmonlib.mysupport.MySupport, "SetupAddOnProgram",
                                  return_value=(log, folder, "127.0.0.1", 9082, folder, log)), \
                mock.patch.object(genmonlib.myclient, "ClientInterface", self.genmon), \
                mock.patch.object(genmonlib.mythread, "MyThread", FakeThread), \
                mock.patch.object(signal, "signal"), \
                mock.patch("time.sleep", side_effect=StopRunning):
            try:
                runpy.run_path(os.path.join(ADDON_DIR, "gengpioin.py"), run_name="__main__")
            except StopRunning:
                pass

    def test_inputs(self):
        self.run_program()
        for pin in [11, 13, 15]:
            self.assertEqual(self.gpio.setups[pin], ("IN", None, "PUD_UP"))
            self.assertEqual(self.gpio.events[pin], ("FALLING", 200))
        for pin, command in [(11, "stop"), (13, "start"), (15, "starttransfer")]:
            with self.subTest(pin=pin):
                self.gpio.callbacks[pin](pin)
                self.assertEqual(self.genmon.commands[-1], "generator: setremote=" + command)

    def test_settings(self):
        self.run_program(trigger="rising", resistorpull="down", bounce="0",
                         INPUT_STOP="29", INPUT_START="31", INPUT_START_TRANSFER="33")
        self.assertEqual(sorted(self.gpio.setups), [29, 31, 33])
        self.assertEqual(self.gpio.setups[29], ("IN", None, "PUD_DOWN"))
        self.assertEqual(self.gpio.events[29], ("RISING", None))

    def test_without_conf_file(self):
        # the defaults (this used to stop with an error)
        self.run_program(conf_file=False)
        self.assertEqual(sorted(self.gpio.callbacks), [11, 13, 15])
        self.assertEqual(self.gpio.events[11], ("FALLING", None))

    def test_without_library_callbacks(self):
        # uselibcallbacks = False: gengpioin's own thread checks for changes
        with mock.patch("genmonlib.mysupport.MySupport.WaitForExit", return_value=True):
            self.run_program(uselibcallbacks="False")
        self.assertEqual(self.gpio.callbacks, {})


# -------------------------------------------------------------------------------
class GenGPIOLedBlinkTests(unittest.TestCase):

    def start(self, **settings):
        self.gpio, modules = fake_gpio()
        fixture = AddOnFixture("gengpioledblink", "GenGPIOLedBlink", settings, modules=modules)
        fixture.state["answers"] = {"monitor_json": monitor()}
        self.addCleanup(fixture.stop)
        fixture.start()
        self.fixture, self.addon = fixture, fixture.addon
        return fixture

    def blinks(self, health, passes=13):
        """The LED states written by the thread (1 = on)."""
        self.fixture.state["answers"]["monitor_json"] = monitor(health=health)
        self.fixture.run_thread("LedBlinkThread", waits=[False] * passes)
        return [state for pin, state in self.gpio.history]

    def test_pin(self):
        self.start(ledpin="40")
        self.assertEqual(self.gpio.setups[40], ("OUT", 0, None))

    def test_health_ok(self):
        # one long blink, then five short ones
        self.start()
        self.assertEqual(self.blinks("OK", passes=12)[:12], [1, 0] * 6)
        waits = []
        with mock.patch.object(self.addon, "WaitForExit",
                               side_effect=lambda name, t: waits.append(t) or len(waits) > 12):
            self.addon.LedBlinkThread()
        self.assertEqual(waits[:4], [1, 1, 0.15, 0.15])

    def test_health_not_ok(self):
        # one long blink, then two short ones
        self.start()
        self.assertEqual(self.blinks("System Initializing", passes=6), [1, 0, 1, 0, 1, 0, 1])

    def test_no_answer_from_genmon(self):
        self.start()
        self.fixture.state["answers"]["monitor_json"] = ""
        self.fixture.run_thread("LedBlinkThread")
        self.assertEqual(self.gpio.history, [])

    def test_close(self):
        self.start()
        self.addon.Close()
        self.assertEqual(self.gpio.outputs[12], 0)
        self.assertIn("cleanup", self.gpio.calls)


# -------------------------------------------------------------------------------
class GenCustomGPIOTests(unittest.TestCase):

    def start(self, pins):
        self.gpio, modules = fake_gpio()
        self.output = tempfile.mkdtemp(prefix="addon_test_")
        self.addCleanup(shutil.rmtree, self.output)
        fixture = AddOnFixture("gencustomgpio", "GenCustomGPIO",
                               {"output_path": self.output, "groupname": "Switches"},
                               modules=modules, extra_config={"gencustomgpio.conf": pins})
        self.addCleanup(fixture.stop)
        fixture.start()
        self.fixture, self.addon = fixture, fixture.addon
        return fixture

    def shown(self):
        with open(os.path.join(self.output, "userdefined.json")) as f:
            return json.load(f)

    def test_inputs(self):
        self.start({"29": {"title": "Door", "activename": "Open", "inactivename": "Closed",
                           "pullup": "True"}})
        # the conf file's own examples (pins 13 and 11) and the new one
        self.assertEqual(self.gpio.setups[29], ("IN", None, "PUD_UP"))
        self.assertEqual(self.gpio.setups[13], ("IN", None, "PUD_DOWN"))
        self.gpio.inputs[29] = 1
        self.fixture.run_thread("PollingThread", waits=[True])
        self.assertEqual(self.shown(), {"Switches": [
            {"GPIO Pin 13": "Inactive"}, {"GPIO Pin 11": "Off"}, {"Door": "Open"}]})

    def test_changes(self):
        self.start({})
        self.fixture.run_thread("PollingThread", waits=[True])
        self.gpio.inputs[11] = 1
        self.fixture.run_thread("PollingThread", waits=[False, True])
        self.assertEqual(self.shown()["Switches"][1], {"GPIO Pin 11": "On"})  # conf: On / Off

    def test_invalid_section(self):
        self.start({"door": {"title": "Door"}})
        self.assertEqual(sorted(p.pin for p in self.addon.GPIO_pins), [11, 13])


if __name__ == "__main__":
    unittest.main()
