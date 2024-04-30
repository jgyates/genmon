#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: gentankdiy.py
# PURPOSE: gentankdiy.py add enhanced external tank data to genmon
#
#  AUTHOR: jgyates
#    DATE: 06-18-2019
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------


import json
import os
import signal
import sys
import threading
import time

try:
    # this will add the parent of the genmonlib folder to the path
    # if we are one level below the genmonlib parent (e.g. in the addon folder)
    file_root = os.path.dirname(os.path.realpath(__file__))
    parent_root = os.path.abspath(os.path.join(file_root, os.pardir))
    if os.path.isdir(os.path.join(parent_root, "genmonlib")):
        sys.path.insert(1, parent_root)

    import smbus

    from genmonlib.gaugediy import GaugeDIY1, GaugeDIY2
    from genmonlib.myclient import ClientInterface
    from genmonlib.mycommon import MyCommon
    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.mysupport import MySupport
    from genmonlib.mythread import MyThread
    from genmonlib.program_defaults import ProgramDefaults

except Exception as e1:
    print(
        "\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n"
    )
    print(
        "Please see the project documentation at https://github.com/jgyates/genmon.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)


# ------------ GenTankData class ------------------------------------------------
class GenTankData(MySupport):

    # ------------ GenTankData::init---------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):

        super(GenTankData, self).__init__()

        self.LogFileName = os.path.join(loglocation, "gentankdiy.log")
        self.AccessLock = threading.Lock()

        self.log = log
        self.console = console
        self.MonitorAddress = host

        configfile = os.path.join(ConfigFilePath, "gentankdiy.conf")
        try:
            if not os.path.isfile(configfile):
                self.LogConsole("Missing config file : " + configfile)
                self.LogError("Missing config file : " + configfile)
                sys.exit(1)

            self.config = MyConfig(
                filename=configfile, section="gentankdiy", log=self.log
            )

            self.gauge_type = self.config.ReadValue(
                "gauge_type", return_type=int, default=1
            )

            self.nb_tanks = self.config.ReadValue(
                "nb_tanks", return_type=int, default=1
            )

            if self.MonitorAddress != None:
                self.MonitorAddress = self.MonitorAddress.strip()

            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost

        except Exception as e1:
            self.LogErrorLine("Error reading " + configfile + ": " + str(e1))
            self.LogConsole("Error reading " + configfile + ": " + str(e1))
            sys.exit(1)

        try:
            if self.gauge_type == 1:
                self.gauge = GaugeDIY1(self.config, log=self.log, console=self.console)
            elif self.gauge_type == 2:
                self.gauge = GaugeDIY2(self.config, log=self.log, console=self.console)
            else:
                self.LogError("Invalid gauge type: " + str(self.gauge_type))
                sys.exit(1)

            if not self.nb_tanks in [1, 2, 3, 4]:
                self.LogError(
                    "Invalid Number of tanks (nb_tanks), 1, 2, 3 or 4 accepted: "
                    + str(self.nb_tanks)
                )
                sys.exit(1)

            self.debug = self.gauge.debug
            self.simulate = self.gauge.simulate

            self.LogDebug("Num Tanks: " + str(self.nb_tanks))
            self.LogDebug("Gauge Type: " + str(self.gauge_type))

            self.Generator = ClientInterface(
                host=self.MonitorAddress, port=port, log=self.log
            )

            # start thread monitor time for exercise
            self.Threads["TankCheckThread"] = MyThread(
                self.TankCheckThread, Name="TankCheckThread", start=False
            )

            if not self.gauge.InitADC():
                self.LogError("InitADC failed, exiting")
                sys.exit(1)

            self.Threads["TankCheckThread"].Start()

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

        except Exception as e1:
            self.LogErrorLine("Error in GenTankData init: " + str(e1))
            self.console.error("Error in GenTankData init: " + str(e1))
            sys.exit(1)

    # ----------  GenTankData::SendCommand --------------------------------------
    def SendCommand(self, Command):

        if len(Command) == 0:
            return "Invalid Command"

        try:
            with self.AccessLock:
                data = self.Generator.ProcessMonitorCommand(Command)
        except Exception as e1:
            self.LogErrorLine("Error calling  ProcessMonitorCommand: " + str(Command))
            data = ""

        return data

    # ---------- GenTankData::TankCheckThread-----------------------------------
    def TankCheckThread(self):

        time.sleep(1)

        while True:
            try:

                dataforgenmon = {}

                tankdata = self.gauge.GetGaugeData()
                if tankdata != None:
                    dataforgenmon["Tank Name"] = "External Tank"
                    dataforgenmon["Capacity"] = 0
                    dataforgenmon["Percentage"] = tankdata
                    if self.nb_tanks >= 2:
                        tankdata2 = self.gauge.GetGaugeData(tanknum=1)
                        if tankdata2 != None:
                            dataforgenmon["Percentage2"] = tankdata2
                    if self.nb_tanks >= 3:
                        tankdata2 = self.gauge.GetGaugeData(tanknum=2)
                        if tankdata2 != None:
                            dataforgenmon["Percentage3"] = tankdata2
                    if self.nb_tanks >= 4:
                        tankdata2 = self.gauge.GetGaugeData(tanknum=3)
                        if tankdata2 != None:
                            dataforgenmon["Percentage4"] = tankdata2

                    retVal = self.SendCommand(
                        "generator: set_tank_data=" + json.dumps(dataforgenmon)
                    )
                    self.LogDebug(json.dumps(dataforgenmon))
                    self.LogDebug(retVal)
                if self.WaitForExit("TankCheckThread", float(self.gauge.PollTime * 60)):
                    return
            except Exception as e1:
                self.LogErrorLine("Error in TankCheckThread: " + str(e1))
                if self.WaitForExit("TankCheckThread", float(self.gauge.PollTime * 60)):
                    return

    # ----------GenTankData::SignalClose----------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(1)

    # ----------GenTankData::Close----------------------------------------------
    def Close(self):

        self.KillThread("TankCheckThread")
        self.gauge.Close()
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
    ) = MySupport.SetupAddOnProgram("gentankdiy")

    GenTankDataInstance = GenTankData(
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
