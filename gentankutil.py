#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: gentankutil.py
# PURPOSE: gentankutil.py add enhanced external tank data to genmon
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
    from genmonlib.mytankutility import tankutility
    from genmonlib.program_defaults import ProgramDefaults

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

        self.LogFileName = os.path.join(loglocation, "gentankutil.log")
        self.AccessLock = threading.Lock()

        self.log = log
        self.console = console

        self.MonitorAddress = host
        self.PollTime =  2
        self.TankID = ""
        self.debug = False
        configfile = os.path.join(ConfigFilePath, 'gentankutil.conf')
        try:
            if not os.path.isfile(configfile):
                self.LogConsole("Missing config file : " + configfile)
                self.LogError("Missing config file : " + configfile)
                sys.exit(1)

            self.config = MyConfig(filename = configfile, section = 'gentankutil', log = self.log)

            self.PollTime = self.config.ReadValue('poll_frequency', return_type = float, default = 60)
            self.debug = self.config.ReadValue('debug', return_type = bool, default = False)
            self.username = self.config.ReadValue('username', default = "")
            self.password = self.config.ReadValue('password', default = "")
            self.tank_name = self.config.ReadValue('tank_name', default = "")

            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost

        except Exception as e1:
            self.LogErrorLine("Error reading " + configfile + ": " + str(e1))
            self.LogConsole("Error reading " + configfile + ": " + str(e1))
            sys.exit(1)

        if self.username == "" or self.username == None or self.password == "" or self.password == None:
            self.LogError("Invalid user name or password, exiting")
            sys.exit(1)

        try:
            self.Generator = ClientInterface(host = self.MonitorAddress, port = port, log = self.log)

            #if not self.CheckGeneratorRequirement():
            #    self.LogError("Requirements not met. Exiting.")
            #    sys.exit(1)

            self.tank = tankutility(self.username, self.password, self.log, debug = self.debug)
            # start thread monitor time for exercise
            self.Threads["TankCheckThread"] = MyThread(self.TankCheckThread, Name = "TankCheckThread", start = False)
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
    #----------  GenTankData::CheckGeneratorRequirement ------------------------
    def CheckGeneratorRequirement(self):

        try:
            data = self.SendCommand("generator: start_info_json")
            StartInfo = {}
            StartInfo = json.loads(data)
            if not "evolution" in StartInfo["Controller"].lower() and not "nexus" in StartInfo["Controller"].lower():
                self.LogError("Error: Only Evolution or Nexus controllers are supported for this feature: " + StartInfo["Controller"])
                return False
            return True
        except Exception as e1:
            self.LogErrorLine("Error in CheckGeneratorRequirement: " + str(e1))
            return False


    # ---------- GenTankData::Login---------------------------------------------
    def Login(self, force = False):

        if force:
            self.TankID = ""
        if len(self.TankID):
            # already logged in
            return True
        if not self.tank.Login():
            return False
        self.TankID = self.tank.GetIDFromName(self.tank_name)
        if not len(self.TankID):
            return False
        return True

    # ---------- GenTankData::TankCheckThread-----------------------------------
    def TankCheckThread(self):

        time.sleep(1)
        LastLoginTime = datetime.datetime.now()
        while True:
            try:
                NUMBER_OF_SECONDS = 60 * 60 * 12    # 12 hours

                if ((datetime.datetime.now() - LastLoginTime).total_seconds() > NUMBER_OF_SECONDS) or not len(self.TankID):
                    self.LogDebug("Login ")
                    if not self.Login(force = True):
                        self.LogError("Error logging in in TankCheckThread, retrying")

                dataforgenmon = {}

                tankdata = self.tank.GetData(self.TankID)
                if tankdata != None:
                    dataforgenmon["Tank Name"] = tankdata["name"]
                    dataforgenmon["Capacity"] = self.tank.GetCapacity()
                    dataforgenmon["Percentage"] = self.tank.GetPercentage()

                    retVal = self.SendCommand("generator: set_tank_data=" + json.dumps(dataforgenmon))
                    self.LogDebug(retVal)
                if self.WaitForExit("TankCheckThread", float(self.PollTime * 60)):
                    return
            except Exception as e1:
                self.LogErrorLine("Error in TankCheckThread: " + str(e1))
                if self.WaitForExit("TankCheckThread", float(self.PollTime * 60)):
                    return

    # ----------GenTankData::SignalClose----------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(1)

    # ----------GenTankData::Close----------------------------------------------
    def Close(self):
        self.KillThread("TankCheckThread")
        self.Generator.Close()
#-------------------------------------------------------------------------------
if __name__ == "__main__":

    console, ConfigFilePath, address, port, loglocation, log = MySupport.SetupAddOnProgram("gentankutil")

    GenTankDataInstance = GenTankData(log = log, loglocation = loglocation, ConfigFilePath = ConfigFilePath, host = address, port = port, console = console)

    while True:
        time.sleep(0.5)

    sys.exit(1)
