#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_addons_data.py
# PURPOSE: Tests for the add-ons that read a tank or sensor and send the data to
#          genmon (set_tank_data and similar commands): what they read, what
#          they send, and what happens when a reading fails.
#
#          Nothing is read or sent: genmon, threads, the web services and the
#          hardware are fakes, see addon_fixture.py. The add-ons' own API
#          clients (genmonlib/mytankutility.py, mycentriconnect.py) are real;
#          the web requests under them are fakes.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_addons_data
#
# -------------------------------------------------------------------------------

import datetime
import io
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests  # noqa: E402

from addon_fixture import AddOnFixture  # noqa: E402

TANK_DATA = "generator: set_tank_data="


class FakeResponse(object):
    def __init__(self, status_code, data):
        self.status_code, self.data = status_code, data
        self.text = str(data)

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code != 200:
            raise requests.exceptions.HTTPError("HTTP %d" % self.status_code)


class FakeWeb(object):
    """requests.get: answers by the end of the URL; a value of an int is an
    HTTP error with that status."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        for end, answer in self.answers.items():
            if url.endswith(end):
                if isinstance(answer, int):
                    return FakeResponse(answer, {})
                return FakeResponse(200, answer)
        return FakeResponse(404, {})


def epoch_ms(when):
    return int(when.timestamp() * 1000)


# -------------------------------------------------------------------------------
class TankUtilityTests(unittest.TestCase):
    """gentankutil.py with genmonlib/mytankutility.py"""

    READING = datetime.datetime(2026, 11, 1, 8, 30, 0)

    def tank(self, name, percent, **extra):
        device = {"name": name, "capacity": 500, "battery_crit": False, "battery_warn": False,
                  "lastReading": {"tank": percent, "temperature": 41.5,
                                  "time": epoch_ms(self.READING)}}
        device.update(extra)
        return {"device": device}

    def start(self, answers, **settings):
        self.web = FakeWeb(answers)
        conf = {"username": "me", "password": "pw", "tank_name": "Main Tank", "tank_name_2": ""}
        conf.update(settings)
        fixture = AddOnFixture("gentankutil", "GenTankData", conf,
                               patches=[((requests, "get"), self.web)])
        self.addCleanup(fixture.stop)
        return fixture.start()

    def answers(self, tank2=None):
        return {"getToken": {"token": "TOKEN"}, "devices": {"devices": ["d1", "d2"]},
                "devices/d1": self.tank("Main Tank", 55.256),
                "devices/d2": tank2 if tank2 is not None else self.tank("Shed Tank", 80)}

    def test_one_tank(self):
        fixture = self.start(self.answers())
        fixture.run_thread("TankCheckThread")
        self.assertEqual(fixture.commands(TANK_DATA), [{
            "Tank Name": "Main Tank", "Capacity": 500, "Percentage": 55.26, "Battery": "OK",
            "Temperature": 41.5, "Reading Time": str(self.READING)}])
        # the token is sent with each request
        self.assertEqual(self.web.calls[-1][1]["params"], (("token", "TOKEN"),))

    def test_two_tanks(self):
        fixture = self.start(self.answers(), tank_name_2="Shed Tank")
        fixture.run_thread("TankCheckThread")
        data = fixture.commands(TANK_DATA)[0]
        self.assertEqual(data["Percentage"], 55.26)
        self.assertEqual(data["Percentage2"], 80.0)
        self.assertEqual(data["Reading Time2"], str(self.READING))

    def test_second_tank_reading_fails(self):
        # tank 2's reading fails after it was found at login: tank 1's values
        # must not be sent as tank 2's
        fixture = self.start(self.answers(), tank_name_2="Shed Tank")
        fixture.run_thread("TankCheckThread")  # logs in and finds both tanks
        self.web.answers["devices/d2"] = 500
        fixture.run_thread("TankCheckThread")
        data = fixture.commands(TANK_DATA)[-1]
        self.assertEqual(data["Percentage"], 55.26)
        self.assertNotIn("Percentage2", data)

    def test_battery(self):
        fixture = self.start(self.answers())
        self.web.answers["devices/d1"] = self.tank("Main Tank", 50, battery_warn=True)
        fixture.run_thread("TankCheckThread")
        self.assertEqual(fixture.commands(TANK_DATA)[0]["Battery"], "Warning")

    def test_login_fails(self):
        fixture = self.start({"getToken": 401})
        fixture.run_thread("TankCheckThread")
        self.assertEqual(fixture.commands(TANK_DATA), [])


# -------------------------------------------------------------------------------
class CentriConnectTests(unittest.TestCase):
    """gencentriconnect.py with genmonlib/mycentriconnect.py"""

    def start(self, data):
        self.web = FakeWeb({"/centriconnect/U1/device/D1/all-data": data})
        fixture = AddOnFixture("gencentriconnect", "GenTankData",
                               {"user_id": "U1", "device_id": "D1", "device_auth": "123456"},
                               patches=[((requests, "get"), self.web)])
        self.addCleanup(fixture.stop)
        return fixture.start()

    def test_tank_data(self):
        fixture = self.start({"D1": {"DeviceName": "White Cloud", "TankLevel": 42.0, "TankSize": 500,
                                     "BatteryVolts": 4.0, "LastPostTimeIso": "2024-10-25 18:00:35.378000"}})
        fixture.run_thread("TankCheckThread")
        data = fixture.commands(TANK_DATA)[0]
        self.assertEqual(data["Tank Name"], "White Cloud")
        self.assertEqual(data["Capacity"], 500)
        self.assertEqual(data["Percentage"], 42.0)
        self.assertEqual(data["Reading Time"], "2024-10-25 18:00:35.378000")
        self.assertEqual(self.web.calls[0][1]["params"], {"device_auth": "123456"})

    def test_unknown_device(self):
        fixture = self.start({"Result": "Device does not exist."})
        fixture.run_thread("TankCheckThread")
        self.assertEqual(fixture.commands(TANK_DATA), [])


# -------------------------------------------------------------------------------
class NeeVoTests(unittest.TestCase):
    """genneevo.py"""

    TANKS = [{"SerialNumber": "111", "Level": 30, "TankCapacity": 1000, "CustomName": "Front",
              "LastReadingDate": "2026-11-01T08:00:00"},
             {"SerialNumber": "222", "Level": 70, "TankCapacity": 400, "CustomName": ""}]

    def start(self, data, **settings):
        self.web = FakeWeb({"GetAllDisplayPropaneDevices": data})
        conf = {"username": "me", "password": "pw", "capacity": "0", "serial_number": ""}
        conf.update(settings)
        fixture = AddOnFixture("genneevo", "GenNeeVo", conf,
                               patches=[((requests, "get"), self.web)])
        self.addCleanup(fixture.stop)
        return fixture.start()

    def test_first_tank(self):
        fixture = self.start(self.TANKS)
        fixture.run_thread("TankCheckThread")
        # the API's capacity is in liters
        self.assertEqual(fixture.commands(TANK_DATA), [{
            "Tank Name": "Front", "Capacity": 264.2, "Percentage": 30,
            "Reading Time": "2026-11-01T08:00:00"}])

    def test_tank_by_serial_number(self):
        fixture = self.start(self.TANKS, serial_number="222", capacity="100", tank_name="Back")
        fixture.run_thread("TankCheckThread")
        # the configured capacity and name are used when given
        self.assertEqual(fixture.commands(TANK_DATA), [{
            "Tank Name": "Back", "Capacity": 100.0, "Percentage": 70}])

    def test_unknown_serial_number(self):
        fixture = self.start(self.TANKS, serial_number="999")
        fixture.run_thread("TankCheckThread")
        self.assertEqual(fixture.commands(TANK_DATA), [])



# -------------------------------------------------------------------------------
class TempTests(unittest.TestCase):
    """gentemp.py: 1-wire temperature sensors"""

    SENSORS = {
        "/sys/bus/w1/devices/28-000001/w1_slave":
            "72 01 4b 46 7f ff 0e 10 57 : crc=57 YES\n72 01 4b 46 7f ff 0e 10 57 t=25000\n",
        "/sys/bus/w1/devices/3b-000002/w1_slave":
            "10 0d 00 : crc=a1 YES\n10 0d 00 t=210500\n",
        "/sys/bus/w1/devices/28-000003/w1_slave":
            "00 00 : crc=00 NO\n00 00 t=0\n",   # a CRC error: not used
    }

    def start(self, **settings):
        self.files = dict(self.SENSORS)

        def fake_glob(pattern):
            prefix = pattern.split("devices/")[1].split("*")[0]
            return [p for p in self.files if p.split("devices/")[1].startswith(prefix)]

        def fake_open(path, mode="r"):
            return io.StringIO(self.files[path])

        import glob as glob_module
        fixture = AddOnFixture("gentemp", "GenTemp", settings,
                               patches=[((glob_module, "glob"), fake_glob),
                                        ("open", fake_open)])
        self.addCleanup(fixture.stop)
        return fixture.start()

    def test_readings_sent(self):
        fixture = self.start(use_metric="False", device_labels="", blacklist="")
        fixture.run_thread("GenTempThread")
        self.assertEqual(fixture.commands("generator: set_sensor_data="), [[
            {"28-000001": "77.00 F"}, {"3b-000002": "410.90 F"}]])

    def test_labels_metric_and_gauges(self):
        fixture = self.start(use_metric="True", device_labels="Engine, Exhaust",
                             device_nominal_values="40, 300", device_max_values="120, 600",
                             blacklist="")
        # the gauges are sent once, when the add-on starts
        self.assertEqual(fixture.commands("generator: set_external_gauge_data="), [[
            {"max": 120, "min": 0, "nominal": 40, "title": "Engine", "units": "C",
             "type": "temperature", "exclude_gauge": False, "from": "gentemp"},
            {"max": 600, "min": 0, "nominal": 300, "title": "Exhaust", "units": "C",
             "type": "temperature", "exclude_gauge": False, "from": "gentemp"}]])
        fixture.run_thread("GenTempThread")
        self.assertEqual(fixture.commands("generator: set_sensor_data="),
                         [[{"Engine": "25.00 C"}, {"Exhaust": "210.50 C"}]])

    def test_only_changed_readings_sent(self):
        fixture = self.start(use_metric="True", device_labels="", blacklist="")
        fixture.run_thread("GenTempThread")
        self.files["/sys/bus/w1/devices/3b-000002/w1_slave"] = "10 : crc=a1 YES\n10 t=211000\n"
        fixture.run_thread("GenTempThread")
        self.assertEqual(fixture.commands("generator: set_sensor_data=")[-1],
                         [{"3b-000002": "211.00 C"}])

    def test_blacklist(self):
        fixture = self.start(use_metric="True", device_labels="", blacklist="3b-000002")
        fixture.run_thread("GenTempThread")
        self.assertEqual(fixture.commands("generator: set_sensor_data="),
                         [[{"28-000001": "25.00 C"}]])



# -------------------------------------------------------------------------------
class TankDIYTests(unittest.TestCase):
    """gentankdiy.py with genmonlib/gaugediy.py, gauge type 1: an ADS1115 ADC on I2C"""

    # the ADC input of each tank, from the config byte genmon writes
    CHANNEL = {0xC1: 0, 0xD1: 1, 0xE1: 2, 0xF1: 3}

    def start(self, readings, **settings):
        """readings: ADC steps (0.1875 mV each) for each tank, or an exception"""
        test = self

        class SMBus(object):
            def __init__(self, channel):
                self.tank = 0

            def write_byte(self, address, value):
                pass

            def write_i2c_block_data(self, address, register, data):
                self.tank = test.CHANNEL[data[0]]

            def read_i2c_block_data(self, address, register, length):
                reading = readings[self.tank]
                if isinstance(reading, Exception):
                    raise reading
                reading &= 0xFFFF  # the ADC sends a signed 16 bit value
                return [reading >> 8, reading & 0xFF]

        smbus = types.ModuleType("smbus")
        smbus.SMBus = SMBus
        conf = {"gauge_type": "1", "nb_tanks": "1", "mv_per_step": "187.5",
                "volts_to_percent_multiplier": "20.0"}
        conf.update(settings)
        # gaugediy looks for /dev/i2c-<n> to check i2c is enabled
        import glob as glob_module
        real_glob = glob_module.glob

        def fake_glob(pattern, *args, **kwargs):
            if pattern.startswith("/dev/i2c-"):
                return ["/dev/i2c-1"]
            return real_glob(pattern, *args, **kwargs)

        fixture = AddOnFixture("gentankdiy", "GenTankData", conf, modules={"smbus": smbus},
                               patches=[((glob_module, "glob"), fake_glob)],
                               reimport=["genmonlib.gaugediy"])
        self.addCleanup(fixture.stop)
        return fixture.start()

    def test_one_tank(self):
        # 13333 steps = 2.50 V = 50%
        fixture = self.start({0: 13333})
        fixture.run_thread("TankCheckThread")
        self.assertEqual(fixture.commands(TANK_DATA),
                         [{"Tank Name": "External Tank", "Capacity": 0, "Percentage": 50.0}])

    def test_two_tanks(self):
        fixture = self.start({0: 13333, 1: 21333}, nb_tanks="2")
        fixture.run_thread("TankCheckThread")
        data = fixture.commands(TANK_DATA)[0]
        self.assertEqual((data["Percentage"], data["Percentage2"]), (50.0, 80.0))

    def test_read_error_is_not_an_empty_tank(self):
        # a failed I2C read must not be sent as 0% (a false low fuel warning)
        fixture = self.start({0: OSError("I2C error")})
        fixture.run_thread("TankCheckThread")
        self.assertEqual(fixture.commands(TANK_DATA), [])

    def test_second_tank_read_error(self):
        fixture = self.start({0: 13333, 1: OSError("I2C error")}, nb_tanks="2")
        fixture.run_thread("TankCheckThread")
        data = fixture.commands(TANK_DATA)[0]
        self.assertEqual(data["Percentage"], 50.0)
        self.assertNotIn("Percentage2", data)

    def test_negative_reading(self):
        # just below 0 V (noise) is a small negative number, not 245%
        fixture = self.start({0: -16})
        fixture.run_thread("TankCheckThread")
        self.assertEqual(fixture.commands(TANK_DATA)[0]["Percentage"], 0.0)


# -------------------------------------------------------------------------------
class CTHatTests(unittest.TestCase):
    """gencthat.py: two current clamps read with an MCP3008 ADC on SPI"""

    def start(self, waveforms, **settings):
        """waveforms: the ADC values (0-1023, 512 = no current) each clamp cycles through"""

        class SpiDev(object):
            max_speed_hz = 0

            def __init__(self):
                self.positions = {0: 0, 1: 0}

            def open(self, bus, device):
                pass

            def close(self):
                pass

            def xfer2(self, data):
                channel = (data[1] >> 4) - 8
                values = waveforms[channel]
                value = values[self.positions[channel] % len(values)]
                self.positions[channel] += 1
                return [0, value >> 8, value & 0xFF]

        spidev = types.ModuleType("spidev")
        spidev.SpiDev = SpiDev
        conf = {"sample_time_ms": "2", "multiplier": "0.2", "powerfactor": "1.0",
                "singlelegthreshold": "0.6", "strict": "False"}
        conf.update(settings)
        fixture = AddOnFixture("gencthat", "GenCTHat", conf, modules={"spidev": spidev})
        self.addCleanup(fixture.stop)
        return fixture.start()

    def test_current(self):
        # peak 100 and 10 from the middle (512), times the multiplier
        fixture = self.start({0: [512, 612, 412], 1: [512, 522, 502]})
        fixture.run_thread("SensorCheckThread")
        data = fixture.commands("generator: set_power_data=")[0]
        self.assertEqual(data["ctdata"], [20.0, 2.0])
        self.assertEqual(data["current"], 22.0)
        self.assertEqual((data["powerfactor"], data["strict"], data["from"]), (1.0, False, "gencthat"))

    def test_below_threshold_is_zero(self):
        # 2 steps is noise; 5 steps * 0.1 = 0.5 is below the single leg threshold
        fixture = self.start({0: [512, 514], 1: [512, 517]}, multiplier="0.1")
        fixture.run_thread("SensorCheckThread")
        self.assertEqual(fixture.commands("generator: set_power_data=")[0]["ctdata"], [0, 0])


if __name__ == "__main__":
    unittest.main()
