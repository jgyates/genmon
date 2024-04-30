#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: gentankutil.py
# PURPOSE: gentankutil.py add enhanced external tank data to genmon
#
#  AUTHOR: jgyates
#    DATE: 06-18-2019
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------


import datetime
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

    from genmonlib.myclient import ClientInterface
    from genmonlib.mycommon import MyCommon
    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.mysupport import MySupport
    from genmonlib.mytankutility import tankutility
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

        self.LogFileName = os.path.join(loglocation, "gentankutil.log")
        self.AccessLock = threading.Lock()

        self.log = log
        self.console = console

        self.MonitorAddress = host
        self.PollTime = 2
        self.TankID = ""
        self.TankID_2 = ""
        self.debug = False
        configfile = os.path.join(ConfigFilePath, "gentankutil.conf")
        try:
            if not os.path.isfile(configfile):
                self.LogConsole("Missing config file : " + configfile)
                self.LogError("Missing config file : " + configfile)
                sys.exit(1)

            self.config = MyConfig(
                filename=configfile, section="gentankutil", log=self.log
            )

            self.PollTime = self.config.ReadValue(
                "poll_frequency", return_type=float, default=60
            )
            self.debug = self.config.ReadValue("debug", return_type=bool, default=False)
            self.username = self.config.ReadValue("username", default="")
            self.password = self.config.ReadValue("password", default="")
            self.tank_name = self.config.ReadValue("tank_name", default="")
            self.tank_name_2 = self.config.ReadValue("tank_name_2", default="")
            self.check_battery = self.config.ReadValue("check_battery", return_type=bool, default=False)
            self.check_reading = self.config.ReadValue("check_reading", return_type=bool, default=False)
            self.reading_timeout = self.config.ReadValue("reading_timeout", return_type=int, default=50)

            if self.MonitorAddress != None:
                self.MonitorAddress = self.MonitorAddress.strip()
            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost

        except Exception as e1:
            self.LogErrorLine("Error reading " + configfile + ": " + str(e1))
            self.LogConsole("Error reading " + configfile + ": " + str(e1))
            sys.exit(1)

        if (
            self.username == ""
            or self.username == None
            or self.password == ""
            or self.password == None
        ):
            self.LogError("Invalid user name or password, exiting")
            sys.exit(1)

        try:
            self.LogDebug("Tank Name = " + str(self.tank_name))
            self.Generator = ClientInterface(
                host=self.MonitorAddress, port=port, log=self.log
            )

            # if not self.CheckGeneratorRequirement():
            #    self.LogError("Requirements not met. Exiting.")
            #    sys.exit(1)

            self.tank = tankutility(
                self.username, self.password, self.log, debug=self.debug
            )
            # start thread monitor time for exercise
            self.Threads["TankCheckThread"] = MyThread(
                self.TankCheckThread, Name="TankCheckThread", start=False
            )
            self.Threads["TankCheckThread"].Start()

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

        except Exception as e1:
            self.LogErrorLine("Error in GenTankData init: " + str(e1))
            self.console.error("Error in GenTankData init: " + str(e1))
            sys.exit(1)

    # ----------GenMopekaData::SendMessage----------------------------------------
    def SendMessage(self, title, body, type, onlyonce=False, oncedaily=False):

        try:
            if not self.check_battery and not self.check_reading:
                return "disabled"
            message = {"title": title, "body": body, "type": type, "onlyonce": onlyonce, "oncedaily": oncedaily}
            command = "generator: notify_message=" + json.dumps(message)

            data = self.SendCommand(command)
            return data
        except Exception as e1:
            self.LogErrorLine("Error in SendMessage: " + str(e1))
            return ""
        
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

    # ----------  GenTankData::CheckGeneratorRequirement ------------------------
    def CheckGeneratorRequirement(self):

        try:
            data = self.SendCommand("generator: start_info_json")
            StartInfo = {}
            StartInfo = json.loads(data)
            if (
                not "evolution" in StartInfo["Controller"].lower()
                and not "nexus" in StartInfo["Controller"].lower()
            ):
                self.LogError(
                    "Error: Only Evolution or Nexus controllers are supported for this feature: "
                    + StartInfo["Controller"]
                )
                return False
            return True
        except Exception as e1:
            self.LogErrorLine("Error in CheckGeneratorRequirement: " + str(e1))
            return False

    # ---------- GenTankData::Login---------------------------------------------
    def Login(self, force=False):

        if force:
            self.TankID = ""
            self.TankID_2 = ""

        if len(self.TankID):
            # already logged in
            return True
        if not self.tank.Login():
            return False
        self.TankID = self.tank.GetIDFromName(self.tank_name)

        if len(self.tank_name_2) > 0:
            self.LogDebug("Getting 2nd Tank ID for tank " + self.tank_name_2)
            self.TankID_2 = self.tank.GetIDFromName(self.tank_name_2)
            self.LogDebug("Tank 2 ID = " + self.TankID_2)

        if not len(self.TankID):
            return False
        return True

    # ---------- GenTankData::TankCheckThread-----------------------------------
    def TankCheckThread(self):

        time.sleep(1)
        LastLoginTime = datetime.datetime.now()
        while True:
            try:
                NUMBER_OF_SECONDS = 60 * 60 * 12  # 12 hours

                if (
                    (datetime.datetime.now() - LastLoginTime).total_seconds()
                    > NUMBER_OF_SECONDS
                ) or not len(self.TankID):
                    self.LogDebug("Login ")
                    if not self.Login(force=True):
                        self.LogError("Error logging in in TankCheckThread, retrying")

                dataforgenmon = {}

                tankdata = self.tank.GetData(self.TankID)
                if tankdata != None:
                    dataforgenmon["Tank Name"] = tankdata["name"]
                    dataforgenmon["Capacity"] = self.tank.GetCapacity()
                    dataforgenmon["Percentage"] = self.tank.GetPercentage()
                    dataforgenmon["Battery"] = self.tank.GetBattery()
                    dataforgenmon["Temperature"] = self.tank.GetReadingTemperature()
                    try:
                        epoch_time = self.tank.GetReadingEpochTime()
                        datetime_time = datetime.datetime.fromtimestamp(epoch_time / 1000)
                        dataforgenmon["Reading Time"] =  str(datetime_time)
                        self.CheckTankResponse(tankdata["name"], datetime_time, self.tank.GetBattery())
                    except Exception as e1:
                        self.LogErrorLine("Error reading tank 1 reading time: " + str(e1))

                    #self.LogDebug("Tank1 = " + json.dumps(tankdata))
                    if len(self.TankID_2) != 0:
                        tankdata = self.tank.GetData(self.TankID_2)
                        self.LogDebug("Tank2 = " + json.dumps(tankdata))
                        dataforgenmon["Percentage2"] = self.tank.GetPercentage()
                        try:
                            epoch_time = self.tank.GetReadingEpochTime()
                            datetime_time = datetime.datetime.fromtimestamp(epoch_time / 1000)
                            dataforgenmon["Battery2"] = self.tank.GetBattery()
                            dataforgenmon["Reading Time2"] =  str(datetime_time)
                            self.CheckTankResponse(tankdata["name"], datetime_time, self.tank.GetBattery())
                        except Exception as e1:
                            self.LogErrorLine("Error reading tank 2 reading time: " + str(e1))
                    
                    retVal = self.SendCommand("generator: set_tank_data=" + json.dumps(dataforgenmon))
                    #self.LogDebug(retVal)
                if self.WaitForExit("TankCheckThread", float(self.PollTime * 60)):
                    return
            except Exception as e1:
                self.LogErrorLine("Error in TankCheckThread: " + str(e1))
                if self.WaitForExit("TankCheckThread", float(self.PollTime * 60)):
                    return

    # ----------GenTankData::CheckTankResponse----------------------------------
    def CheckTankResponse(self, tank_name, datetime_time, battery_string):
        try:
            if self.check_reading and self.CheckTimeDiffExpired(datetime_time, (60 * int(self.reading_timeout))): # default is 50 hours
                msgbody = "Genmon Tankutil Warning: Tank Monitor Missed Update. Last update was " + str(datetime_time) + " for tank '" + tank_name + "'"
                msgsubject = "Genmon Tankutil Tank Monitor Message: Reporting: " + tank_name
                self.SendMessage(msgsubject, msgbody, "error", onlyonce=False, oncedaily=True)
                self.LogDebug(msgsubject)
                self.LogDebug(msgbody)

            if self.check_battery and battery_string.lower() == "critical":
                msgbody = "Warning: Tank Monitor Battery is : " + str(battery_string)
                msgsubject = "Genmon Tankutil Tank Monitor Message: Battery: " + tank_name
                self.SendMessage(msgsubject, msgbody, "error", onlyonce=False, oncedaily=True)
                self.LogDebug(msgsubject)
                self.LogDebug(msgbody)

        except Exception as e1:
            self.LogErrorLine("Error in CheckTanksReponse: " + str(e1))

    #---------------------CheckTimeDiffExpired----------------------------------
    # check that numner of minutes has expired since a given time
    def CheckTimeDiffExpired(self, time, min):

        try:
            time_reference_seconds = min * 60.0
            if (datetime.datetime.now() - time).total_seconds() > time_reference_seconds:
                return True
            else:
                return False
        except Exception as e1:
            self.LogErrorLine("Error in CheckTimeDiffExpired: " + str(e1))
            return True

    # ----------GenTankData::SignalClose----------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(1)

    # ----------GenTankData::Close----------------------------------------------
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
    ) = MySupport.SetupAddOnProgram("gentankutil")

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
