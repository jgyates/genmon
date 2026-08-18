#!/usr/bin/env python
# -------------------------------------------------------------------------------
# FILE: genneevo.py
# PURPOSE: Pull Otodata / Nee-Vo LTE propane tank data into Genmon
#
# Based on the structure of gentankutil.py
# -------------------------------------------------------------------------------

import datetime
import json
import os
import signal
import sys
import threading
import time
import requests
from requests.auth import HTTPBasicAuth

try:
    file_root = os.path.dirname(os.path.realpath(__file__))
    parent_root = os.path.abspath(os.path.join(file_root, os.pardir))
    if os.path.isdir(os.path.join(parent_root, "genmonlib")):
        sys.path.insert(1, parent_root)

    from genmonlib.myclient import ClientInterface
    from genmonlib.mycommon import MyCommon
    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.mysupport import MySupport
    from genmonlib.mythread import MyThread
    from genmonlib.program_defaults import ProgramDefaults

except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)


class GenNeeVo(MySupport):

    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):
        super(GenNeeVo, self).__init__()

        self.LogFileName = os.path.join(loglocation, "genneevo.log")
        self.AccessLock = threading.Lock()
        self.log = log
        self.console = console
        self.MonitorAddress = host
        self.PollTime = 60
        self.debug = False

        configfile = os.path.join(ConfigFilePath, "genneevo.conf")

        try:
            if not os.path.isfile(configfile):
                self.LogConsole("Missing config file : " + configfile)
                self.LogError("Missing config file : " + configfile)
                sys.exit(1)

            self.config = MyConfig(filename=configfile, section="genneevo", log=self.log)

            self.PollTime = self.config.ReadValue("poll_frequency", return_type=float, default=60)
            self.debug = self.config.ReadValue("debug", return_type=bool, default=False)
            self.username = self.config.ReadValue("username", default="")
            self.password = self.config.ReadValue("password", default="")
            self.tank_name = self.config.ReadValue("tank_name", default="Propane Tank")
            self.capacity = self.config.ReadValue("capacity", return_type=float, default=0)
            self.serial_number = self.config.ReadValue("serial_number", default="")

            if self.MonitorAddress is None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost

        except Exception as e1:
            self.LogErrorLine("Error reading " + configfile + ": " + str(e1))
            sys.exit(1)

        if not self.username or not self.password:
            self.LogError("Invalid username or password in genneevo.conf")
            sys.exit(1)

        try:
            self.Generator = ClientInterface(host=self.MonitorAddress, port=port, log=self.log)

            self.Threads["TankCheckThread"] = MyThread(
                self.TankCheckThread, Name="TankCheckThread", start=False
            )
            self.Threads["TankCheckThread"].Start()

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

        except Exception as e1:
            self.LogErrorLine("Error in GenNeeVo init: " + str(e1))
            sys.exit(1)

    # ---------- GenNeeVo::SendCommand -----------------------------------------
    def SendCommand(self, Command):
        if len(Command) == 0:
            return "Invalid Command"
        try:
            with self.AccessLock:
                data = self.Generator.ProcessMonitorCommand(Command)
        except Exception as e1:
            self.LogErrorLine("Error calling ProcessMonitorCommand: " + str(Command))
            data = ""
        return data

    # ---------- GenNeeVo::GetNeeVoData ----------------------------------------
    def GetNeeVoData(self):
        url = "https://ws.otodatanetwork.com/neevoapp/v1/DataService.svc/GetAllDisplayPropaneDevices"

        try:
            response = requests.get(
                url,
                auth=HTTPBasicAuth(self.username, self.password),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Genmon-NeeVo-Addon"
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e1:
            self.LogErrorLine("Error fetching Nee-Vo data: " + str(e1))
            return None

    # ---------- GenNeeVo::TankCheckThread -------------------------------------
    def TankCheckThread(self):
        time.sleep(2)

        while True:
            try:
                tanks = self.GetNeeVoData()

                if tanks is None or len(tanks) == 0:
                    self.LogError("No tank data returned from Nee-Vo API")
                else:
                    selected = None

                    # If a specific serial number is configured, find it
                    if self.serial_number:
                        for tank in tanks:
                            if str(tank.get("SerialNumber", "")) == str(self.serial_number):
                                selected = tank
                                break
                    else:
                        selected = tanks[0]   # default to first tank

                    if selected is None:
                        self.LogError("Configured serial number not found")
                    else:
                        level = selected.get("Level")
                        capacity_api = selected.get("TankCapacity")
                        name = selected.get("CustomName") or self.tank_name

                        # Prefer configured capacity, otherwise try to use API value
                        capacity = self.capacity
                        if capacity <= 0 and capacity_api:
                            # API often returns liters
                            capacity = round(float(capacity_api) * 0.264172, 1)

                        dataforgenmon = {
                            "Tank Name": name,
                            "Capacity": capacity,
                            "Percentage": level
                        }

                        # Optional extra fields
                        if selected.get("LastReadingDate"):
                            dataforgenmon["Reading Time"] = selected.get("LastReadingDate")

                        self.LogDebug("Sending to Genmon: " + json.dumps(dataforgenmon))
                        retVal = self.SendCommand(
                            "generator: set_tank_data=" + json.dumps(dataforgenmon)
                        )
                        self.LogDebug("Genmon response: " + str(retVal))

                if self.WaitForExit("TankCheckThread", float(self.PollTime * 60)):
                    return

            except Exception as e1:
                self.LogErrorLine("Error in TankCheckThread: " + str(e1))
                if self.WaitForExit("TankCheckThread", float(self.PollTime * 60)):
                    return

    # ---------- GenNeeVo::SignalClose ----------------------------------------
    def SignalClose(self, signum, frame):
        self.Close()
        sys.exit(1)

    # ---------- GenNeeVo::Close ----------------------------------------------
    def Close(self):
        self.KillThread("TankCheckThread")
        self.Generator.Close()


# -------------------------------------------------------------------------------
if __name__ == "__main__":
    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("genneevo")

    GenNeeVoInstance = GenNeeVo(
        log=log,
        loglocation=loglocation,
        ConfigFilePath=ConfigFilePath,
        host=address,
        port=port,
        console=console,
    )

    while True:
        time.sleep(0.5)

    sys.exit(1)