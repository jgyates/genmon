#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_myplatform.py
# PURPOSE: Tests for genmonlib/myplatform.py, the Raspberry Pi and Linux
#          information on the Monitor page: detecting a Raspberry Pi, the CPU
#          temperature (vcgencmd or the thermal zone file, Celsius or
#          Fahrenheit), throttling and undervoltage, CPU use, OS name and
#          version, the network adapter and WiFi signal.
#
#          The system files (/proc, /sys, /etc/os-release) and commands
#          (vcgencmd, iw, iwconfig) are fakes, so these tests run on any
#          computer.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_myplatform
#
# -------------------------------------------------------------------------------

import io
import logging
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genmonlib import myplatform  # noqa: E402
from genmonlib.myplatform import MyPlatform  # noqa: E402

OS_RELEASE = 'PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nNAME="Debian GNU/Linux"\nVERSION_ID="13"\nVERSION="13 (trixie)"\n'
PROC_STAT = "cpu  300 0 100 1600 0 0 0 0 0 0\ncpu0 1 2 3 4\n"
WIRELESS = ("Inter-| sta-|   Quality        |   Discarded packets\n"
            " face | tus | link level noise |  nwid  crypt\n"
            " wlan0: 0000   60.  -50.  -256        0      0\n")


class FakeProcess(object):
    def __init__(self, output):
        self.output = output

    def communicate(self):
        return self.output, None


class PlatformTestCase(unittest.TestCase):

    def setUp(self):
        log = logging.getLogger("myplatform_test")
        log.handlers, log.propagate = [logging.NullHandler()], False
        self.platform = MyPlatform(log=log, usemetric=True)
        self.files = {}
        self.commands = {}
        real_open, real_exists = open, os.path.exists

        def fake_open(path, *args, **kwargs):
            if path in self.files:
                return io.StringIO(self.files[path])
            if str(path).startswith(("/proc", "/sys", "/etc/os-release")):
                raise IOError(path)
            return real_open(path, *args, **kwargs)

        def fake_exists(path):
            if path in self.files:
                return True
            if str(path).startswith(("/proc", "/sys", "/usr/bin/vcgencmd", "/opt/vc")):
                return False
            return real_exists(path)

        def fake_popen(command, stdout=None):
            output = self.commands.get(tuple(command))
            if output is None:
                raise OSError("no " + command[0])
            return FakeProcess(output.encode())

        def fake_check_output(command):
            output = self.commands.get(tuple(command))
            if output is None:
                raise OSError("no " + command[0])
            return output.encode()

        for patch in [mock.patch("builtins.open", side_effect=fake_open),
                      mock.patch.object(myplatform.os.path, "exists", side_effect=fake_exists),
                      mock.patch.object(myplatform, "Popen", side_effect=fake_popen),
                      mock.patch.object(myplatform.subprocess, "check_output",
                                        side_effect=fake_check_output),
                      mock.patch.object(myplatform.sys, "platform", "linux")]:
            patch.start()
            self.addCleanup(patch.stop)

    def raspberry_pi(self):
        self.files["/proc/device-tree/model"] = "Raspberry Pi 4 Model B Rev 1.4\x00"


# -------------------------------------------------------------------------------
class RaspberryPiTests(PlatformTestCase):

    def test_detect_by_model(self):
        self.raspberry_pi()
        self.assertTrue(self.platform.IsPlatformRaspberryPi())
        self.assertEqual(self.platform.GetRaspberryPiModel(), "Raspberry Pi 4 Model B Rev 1.4")

    def test_detect_by_cpuinfo(self):
        self.files["/proc/cpuinfo"] = "processor : 0\nHardware : BCM2835\n"
        self.assertTrue(self.platform.IsPlatformRaspberryPi())
        self.files["/proc/cpuinfo"] = "processor : 0\nHardware : Allwinner sun8i\n"
        self.assertFalse(self.platform.IsPlatformRaspberryPi())
        with self.assertRaises(ValueError):
            self.platform.IsPlatformRaspberryPi(raise_on_errors=True)

    def test_not_a_pi(self):
        self.files["/proc/cpuinfo"] = "processor : 0\nmodel name : Intel\n"
        self.assertFalse(self.platform.IsPlatformRaspberryPi())
        self.assertIsNone(self.platform.GetRaspberryPiInfo())

    def test_temperature(self):
        self.commands[("/opt/vc/bin/vcgencmd", "measure_temp")] = "temp=48.3'C\n"
        self.assertEqual(self.platform.GetRaspberryPiTemp(), "48.30 C")
        self.assertEqual(self.platform.GetRaspberryPiTemp(ReturnFloat=True), 48.3)
        self.platform.UseMetric = False
        self.assertEqual(self.platform.GetRaspberryPiTemp(), "118.94 F")

    def test_temperature_without_vcgencmd(self):
        self.files["/sys/class/thermal/thermal_zone0/temp"] = "51234\n"
        self.commands[("cat", "/sys/class/thermal/thermal_zone0/temp")] = "51234\n"
        self.assertEqual(self.platform.GetRaspberryPiTemp(ReturnFloat=True), 51.23)

    def test_throttling(self):
        self.assertEqual(self.platform.ParseThrottleStatus(0), [
            {"Pi CPU Frequency Throttling": "OK"}, {"Pi ARM Frequency Cap": "OK"},
            {"Pi Undervoltage": "OK"}])
        status = self.platform.ParseThrottleStatus(0x50005)
        self.assertEqual(status[0], {"Pi CPU Frequency Throttling": "Has occurred. Throttling Active. "})
        self.assertEqual(status[2], {"Pi Undervoltage": "Has occurred. Undervoltage Detected. "})
        self.commands[("/opt/vc/bin/vcgencmd", "get_throttled")] = "throttled=0x50000\n"
        self.assertEqual(self.platform.GetThrottledStatus()[2], {"Pi Undervoltage": "Has occurred. "})

    def test_pi_info(self):
        self.raspberry_pi()
        self.commands[("/opt/vc/bin/vcgencmd", "measure_temp")] = "temp=40.0'C\n"
        self.commands[("/opt/vc/bin/vcgencmd", "get_throttled")] = "throttled=0x0\n"
        info = {k: v for item in self.platform.GetRaspberryPiInfo() for k, v in item.items()}
        self.assertEqual(info["CPU Temperature"], "40.00 C")
        self.assertEqual(info["Pi Model"], "Raspberry Pi 4 Model B Rev 1.4")
        self.assertEqual(info["Pi Undervoltage"], "OK")


# -------------------------------------------------------------------------------
class LinuxTests(PlatformTestCase):

    def test_cpu_utilization(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = os.path.join(folder, "stat")
        self.files[path] = PROC_STAT
        self.assertEqual(MyPlatform.ReadCPUUtilization(path), 20.0)

    def test_network_adapter(self):
        # the first broadcast adapter with a connection, in ifindex order
        base = "/sys/class/net"
        adapters = {"lo": (1, "0x9", "1"), "eth0": (2, "0x1003", "0"), "wlan0": (3, "0x1003", "1")}
        for name, (index, flags, carrier) in adapters.items():
            self.files[base + "/" + name + "/ifindex"] = str(index)
            self.files[base + "/" + name + "/flags"] = flags
            self.files[base + "/" + name + "/carrier"] = carrier
        with mock.patch.object(myplatform.os, "listdir", return_value=["wlan0", "lo", "eth0"]):
            self.assertEqual(MyPlatform.GetActiveNetworkAdapter(), "wlan0")
            self.files[base + "/eth0/carrier"] = "1"
            self.assertEqual(MyPlatform.GetActiveNetworkAdapter(), "eth0")
        self.assertEqual(MyPlatform.GetActiveNetworkAdapter("/no/such/folder"), "")

    def test_linux_info(self):
        self.files["/proc/stat"] = PROC_STAT
        self.files["/etc/os-release"] = OS_RELEASE
        self.files["/proc/uptime"] = "93784.52 12345.00\n"
        self.platform.PreferredNetworkAdapter = "eth0"
        info = {k: v for item in self.platform.GetLinuxInfo() for k, v in item.items()}
        self.assertEqual(info["CPU Utilization"], "20.0%")
        self.assertEqual(info["OS Name"], "Debian GNU/Linux")
        self.assertEqual(info["OS Version"], "13 (trixie)")
        self.assertEqual(info["System Uptime"], "1 day, 2:03:04")
        self.assertEqual(info["Network Interface Used"], "eth0")

    def test_wifi(self):
        self.files["/proc/net/wireless"] = WIRELESS
        self.platform.PreferredNetworkAdapter = "wlan0"
        self.commands[("iw", "wlan0", "link")] = "Connected to aa:bb\n\tsignal: -47 dBm\n"
        self.commands[("iwconfig", "wlan0")] = 'wlan0 ESSID:"HomeNet"\n Link Quality=63/70  Signal level=-47 dBm\n'
        self.assertEqual(self.platform.GetWiFiSignalStrength(), -47)
        info = {k: v for item in self.platform.GetWiFiInfo("wlan0") for k, v in item.items()}
        self.assertEqual(info, {"WLAN Signal Level": "-47 dBm", "WLAN Signal Quality": "63/70",
                                "WLAN Signal Noise": "-256 dBm", "WLAN ESSID": "HomeNet"})

    def test_wifi_without_iw(self):
        # the level from /proc/net/wireless: still a negative dBm value (it
        # was shown as +50 dBm)
        self.files["/proc/net/wireless"] = WIRELESS
        self.platform.PreferredNetworkAdapter = "wlan0"
        self.assertEqual(self.platform.GetWiFiSignalStrength(), -50)

    def test_wired(self):
        self.platform.PreferredNetworkAdapter = "eth0"
        self.assertEqual(self.platform.GetWiFiSignalStrength(), 0)

    def test_info(self):
        self.raspberry_pi()
        self.files["/etc/os-release"] = OS_RELEASE
        self.commands[("/opt/vc/bin/vcgencmd", "measure_temp")] = "temp=40.0'C\n"
        names = [k for item in self.platform.GetInfo() for k in item]
        for name in ["CPU Temperature", "Pi Model", "OS Name", "System Time"]:
            self.assertIn(name, names)

    def test_os(self):
        # macOS is not Windows ("darwin" has "win" in it)
        for platform, linux, windows, mac in [("linux", True, False, False),
                                              ("win32", False, True, False),
                                              ("cygwin", False, True, False),
                                              ("darwin", False, False, True)]:
            with self.subTest(platform=platform), mock.patch.object(myplatform.sys, "platform", platform):
                self.assertEqual((MyPlatform.IsOSLinux(), MyPlatform.IsOSWindows(), MyPlatform.IsOSMac()),
                                 (linux, windows, mac))

    def test_mac_info(self):
        with mock.patch.object(myplatform.sys, "platform", "darwin"), \
                mock.patch("platform.processor", return_value="arm"):
            self.assertIsNone(self.platform.GetPlatformInfo())
            names = [k for item in self.platform.GetOSInfo() for k in item]
        self.assertIn("OS Release", names)

    def test_bit_depth(self):
        with mock.patch("platform.architecture", return_value=("64bit", "ELF")):
            self.assertEqual(self.platform.PlatformBitDepth(), "64")
        with mock.patch("platform.architecture", side_effect=OSError("no")):
            self.assertEqual(self.platform.PlatformBitDepth(), "Unknown")


if __name__ == "__main__":
    unittest.main()
