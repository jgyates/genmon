#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: gentankdiy.py
# PURPOSE: gentankdiy.py add enhanced external tank data to genmon
#
#  AUTHOR: jgyates
#    DATE: 06-18-2019
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------


import datetime, time, sys, signal, os, threading, collections, json, ssl
import atexit, getopt, requests

try:
    from genmonlib.myclient import ClientInterface
    from genmonlib.mylog import SetupLogger
    from genmonlib.myconfig import MyConfig
    from genmonlib.mysupport import MySupport
    from genmonlib.mycommon import MyCommon
    from genmonlib.mythread import MyThread
    from genmonlib.program_defaults import ProgramDefaults
    from genmonlib.gaugediy import GaugeDIY1, GaugeDIY2
    import smbus

except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)


#------------ GenTankData class ------------------------------------------------
class GenTankData(MySupport):

    #------------ GenTankData::init---------------------------------------------
    def __init__(self,
        log = None,
        loglocation = ProgramDefaults.LogPath,
        ConfigFilePath = MyCommon.DefaultConfPath,
        host = ProgramDefaults.LocalHost,
        port = ProgramDefaults.ServerPort,
        console = None):

        super(GenTankData, self).__init__()

        self.LogFileName = os.path.join(loglocation, "gentankdiy.log")
        self.AccessLock = threading.Lock()

        self.log = log
        self.console = console
        self.MonitorAddress = host

        configfile = os.path.join(ConfigFilePath, 'gentankdiy.conf')
        try:
            if not os.path.isfile(configfile):
                self.LogConsole("Missing config file : " + configfile)
                self.LogError("Missing config file : " + configfile)
                sys.exit(1)

            self.config = MyConfig(filename = configfile, section = 'gentankdiy', log = self.log)

            self.gauge_type = self.config.ReadValue('gauge_type', return_type = int, default = 1)

            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost

        except Exception as e1:
            self.LogErrorLine("Error reading " + configfile + ": " + str(e1))
            self.LogConsole("Error reading " + configfile + ": " + str(e1))
            sys.exit(1)

        try:
            if self.gauge_type == 1:
                self.gauge = GaugeDIY1(self.config, log = self.log, console = self.console)
            elif self.gauge_type == 2:
                self.gauge = GaugeDIY2(self.config, log = self.log, console = self.console)
            else:
                self.LogError("Invalid guage type: " + str(self.gauge_type))
                sys.exit(1)

            self.debug = self.gauge.debug
            self.Generator = ClientInterface(host = self.MonitorAddress, port = port, log = self.log)

            # start thread monitor time for exercise
            self.Threads["TankCheckThread"] = MyThread(self.TankCheckThread, Name = "TankCheckThread", start = False)

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

    #----------  GenTankData::SendCommand --------------------------------------
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

                    retVal = self.SendCommand("generator: set_tank_data=" + json.dumps(dataforgenmon))
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
#-------------------------------------------------------------------------------
if __name__ == "__main__":

    console, ConfigFilePath, address, port, loglocation, log = MySupport.SetupAddOnProgram("gentankdiy")

    GenTankDataInstance = GenTankData(log = log, loglocation = loglocation, ConfigFilePath = ConfigFilePath, host = address, port = port, console = console)

    while True:
        time.sleep(0.5)

    sys.exit(1)
