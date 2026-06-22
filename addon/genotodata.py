#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: genotodata.py
# PURPOSE: Genmon addon for the Otodata TM6030 Bluetooth Low Energy propane
#          tank sensor.  The TM6030 broadcasts its tank fill level as a
#          percentage in the BLE advertisement local name, e.g.:
#              "Otodata level: 72%"
#          This addon scans for that advertisement and forwards the reading to
#          genmon via the set_tank_data command.
#
#  AUTHOR: Brian Wilson
#    DATE: 2024
#
#   USAGE: Copy to /home/pi/genmon/addon/
#          Copy genotodata.conf to /etc/genmon/
#          Add [genotodata] section to /etc/genmon/genloader.conf (see below)
#          Run the genmon installation script to install dependencies (bleak)
#
#          [genotodata]
#          module = genotodata.py
#          enable = True
#          hardstop = False
#          conffile = genotodata.conf
#          args =
#          priority = 2
#          postloaddelay = 0
# -------------------------------------------------------------------------------

import asyncio
import json
import os
import re
import sys
import threading
import time

# ---------------------------------------------------------------------------
# Ensure genmonlib is importable when invoked by genloader without PYTHONPATH.
# The addon lives in <genmon_root>/addon/; genmonlib is one level up.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Optional BLE dependency — log a clear message if missing rather than crash.
# Install with: sudo pip3 install bleak
# ---------------------------------------------------------------------------
try:
    from bleak import BleakScanner

    bleak_installed = True
except ImportError:
    bleak_installed = False

from genmonlib.myclient import ClientInterface
from genmonlib.myconfig import MyConfig
from genmonlib.mysupport import MySupport
from genmonlib.mythread import MyThread

# ---------------------------------------------------------------------------
LEVEL_REGEX = re.compile(r"level:\s*([0-9]+(?:\.[0-9]+)?)\s*%", re.IGNORECASE)


class GenOtodataData(MySupport):

    def __init__(
        self,
        log=None,
        loglocation=None,
        ConfigFilePath=None,
        host="localhost",
        port=9082,
        console=None,
    ):
        super(GenOtodataData, self).__init__()

        self.log = log
        self.loglocation = loglocation
        self.console = console
        self.host = host
        self.port = port
        self.running = True
        self.current_level = None
        self.CommAccessLock = threading.Lock()
        self.debug = False

        if not bleak_installed:
            self.LogError(
                "GenOtodataData: Required library 'bleak' is not installed. "
                "Run the genmon installation script or: sudo pip3 install bleak"
            )
            self.running = False
            return

        conf_path = os.path.join(
            ConfigFilePath if ConfigFilePath else "/etc/genmon/",
            "genotodata.conf",
        )
        self.config = MyConfig(filename=conf_path, section="genotodata", log=self.log)

        self.tank_name = self.config.ReadValue(
            "tank_name", return_type=str, default="Propane Tank"
        )
        self.capacity = self.config.ReadValue("capacity", return_type=int, default=0)
        self.poll_frequency = self.config.ReadValue(
            "poll_frequency", return_type=int, default=5
        )
        self.scan_time = self.config.ReadValue(
            "scan_time", return_type=float, default=30.0
        )
        self.mac_address = (
            self.config.ReadValue("mac_address", return_type=str, default="")
            .strip()
            .lower()
        )
        self.debug = self.config.ReadValue("debug", return_type=bool, default=False)

        try:
            self.Generator = ClientInterface(host=host, port=port, log=self.log)
        except Exception as e1:
            self.LogErrorLine(
                "GenOtodataData: Cannot connect to genmon at %s:%d: %s"
                % (host, port, str(e1))
            )
            self.Generator = None

        self.Threads["TankCheckThread"] = MyThread(
                self.TankCheckThread, Name="TankCheckThread", start=False
            )
        self.Threads["TankCheckThread"].Start()
        self.LogDebug("GenOtodataData: Started.")

    # ------------------------------------------------------------------
    def SendCommand(self, Command):
        if not Command:
            return "Invalid command"
        if self.Generator is None:
            return ""
        try:
            with self.CommAccessLock:
                return self.Generator.ProcessMonitorCommand(Command)
        except Exception as e1:
            self.LogErrorLine("Error in SendCommand: " + str(e1))
            return ""

    # ------------------------------------------------------------------
    async def _ble_scan_async(self):
        """Scan for scan_time seconds; return (address, level_pct) or (None, None)."""
        result = {}

        def _callback(device, adv_data):
            name = device.name or (adv_data.local_name if adv_data else "") or ""
            m = LEVEL_REGEX.search(name)
            if not m:
                return
            addr = device.address.lower()
            if self.mac_address and addr != self.mac_address:
                return
            result["addr"] = device.address
            result["level"] = float(m.group(1))

        scanner = BleakScanner(detection_callback=_callback)
        await scanner.start()
        await asyncio.sleep(self.scan_time)
        await scanner.stop()
        return result.get("addr"), result.get("level")

    def GetTankReading(self):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._ble_scan_async())
        except Exception as e1:
            self.LogErrorLine("GenOtodataData: BLE scan error: " + str(e1))
            return None, None
        finally:
            loop.close()

    # ------------------------------------------------------------------
    def TankCheckThread(self):
        # Brief startup delay so genmon can fully initialise before we connect.
        if self.WaitForExit("TankCheckThread", 5):
            return

        while True:
            self.LogDebug(
                "GenOtodataData: Scanning %.0f s for Otodata TM6030 sensor..."
                % self.scan_time
            )
            addr, level = self.GetTankReading()

            if level is not None:
                self.LogDebug(
                    "GenOtodataData: Sensor [%s] level %.1f%%" % (addr, level)
                )
                if level != self.current_level:
                    self.current_level = level
                    data = {"Tank Name": self.tank_name, "Percentage": level}
                    if self.capacity > 0:
                        data["Capacity"] = self.capacity
                    self.SendCommand(
                        "generator: set_tank_data=" + json.dumps(data)
                    )
            else:
                self.LogDebug(
                    "GenOtodataData: Sensor not found during scan window. "
                    "Check Bluetooth adapter and sensor proximity."
                )

            if self.WaitForExit("TankCheckThread", self.poll_frequency * 60):
                return

    # ------------------------------------------------------------------
    def Close(self):
        self.running = False
        if getattr(self, "Generator", None):
            try:
                self.Generator.Close()
            except Exception:
                pass
        super(GenOtodataData, self).Close()


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    (console, ConfigFilePath, address, port, loglocation, log) = (
        MySupport.SetupAddOnProgram("genotodata")
    )

    instance = GenOtodataData(
        log=log,
        loglocation=loglocation,
        ConfigFilePath=ConfigFilePath,
        host=address,
        port=port,
        console=console,
    )

    while instance.running:
        time.sleep(0.5)

    instance.Close()
    sys.exit(0)
