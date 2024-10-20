#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: controller.py
# PURPOSE: Controller Specific Detils for Base Class
#
#  AUTHOR: Jason G Yates
#    DATE: 24-Apr-2018
#
# MODIFICATIONS:
#
# USAGE: This is the base class of generator controllers. LogError or FatalError
#   should be used to log errors or fatal errors.
#
# -------------------------------------------------------------------------------

import collections
import datetime
import json
import os
import sys
import threading
import time
import itertools
import copy
import re

from genmonlib.mylog import SetupLogger
from genmonlib.myplatform import MyPlatform
from genmonlib.mysupport import MySupport
from genmonlib.mythread import MyThread
from genmonlib.mytile import MyTile
from genmonlib.program_defaults import ProgramDefaults

# NOTE: collections OrderedDict is used for dicts that are displayed to the UI


# Fix Python 2.x. unicode type
if sys.version_info[0] >= 3:  # PYTHON 3
    unicode = str


class GeneratorController(MySupport):
    # ---------------------GeneratorController::__init__-------------------------
    def __init__(
        self,
        log,
        newinstall=False,
        simulation=False,
        simulationfile=None,
        message=None,
        feedback=None,
        config=None,
        ConfigFilePath=ProgramDefaults.ConfPath,
    ):

        super(GeneratorController, self).__init__(simulation=simulation)
        self.log = log
        self.NewInstall = newinstall
        self.Simulation = simulation
        self.SimulationFile = simulationfile
        self.FeedbackPipe = feedback
        self.MessagePipe = message
        self.config = config

        self.ModBus = None
        self.InitComplete = False
        self.IsStopping = False
        self.InitCompleteEvent = threading.Event()  # Event to signal init complete
        self.CheckForAlarmEvent = (
            threading.Event()
        )  # Event to signal checking for alarm
        self.Holding = collections.OrderedDict()  # dict for registers and values (modbus fuction 03)
        self.Strings = collections.OrderedDict()    # dict for registers read a string data
        self.FileData = collections.OrderedDict()   # dict for modbus file reads (modbus function 0x14)
        self.Coils = collections.OrderedDict()      # dict for modbus coil reads (modbus fuction 01)
        self.Inputs = collections.OrderedDict()     # dict for modbus input registers (modbus function 4)
        self.NotChanged = 0  # stats for registers
        self.Changed = 0  # stats for registers
        self.TotalChanged = 0.0  # ratio of changed ragisters
        self.MaintLog = os.path.join(ConfigFilePath, "maintlog.json")
        self.MaintLogList = []
        self.MaintLock = threading.RLock()
        self.OutageLog = os.path.join(ConfigFilePath, "outage.txt")
        self.MinimumOutageDuration = 0
        self.PowerLogMaxSize = 15.0  # 15 MB max size
        self.PowerLog = os.path.join(ConfigFilePath, "kwlog.txt")
        self.MaxPowerLogEntries = 4000
        self.FuelLog = os.path.join(ConfigFilePath, "fuellog.txt")
        self.FuelLock = threading.RLock()
        self.PowerLogList = []
        self.PowerLock = threading.RLock()
        self.bAlternateDateFormat = False
        self.KWHoursMonth = None
        self.FuelMonth = None
        self.RunHoursMonth = None
        self.RunHoursYear = None
        self.FuelTotal = None
        self.TileList = []  # Tile list for GUI
        self.TankData = None
        self.FuelLevelOK = None  # used in mynotify.py
        self.debug = False

        self.UtilityVoltsMin = 0  # Minimum reported utility voltage above threshold
        self.UtilityVoltsMax = 0  # Maximum reported utility voltage above pickup
        self.SystemInOutage = False  # Flag to signal utility power is out
        self.TransferActive = (
            False  # Flag to signal transfer switch is allowing gen supply power
        )
        self.ControllerSelected = None
        # The values "Unknown" are checked to validate conf file items are found
        self.FuelType = "Unknown"
        self.NominalFreq = "Unknown"
        self.NominalRPM = "Unknown"
        self.NominalKW = "Unknown"
        self.Model = "Unknown"
        self.Phase = "Unknown"
        self.NominalLineVolts = 240
        self.EngineDisplacement = "Unknown"
        self.TankSize = 0
        self.UseExternalFuelData = False
        self.UseExternalCTData = False
        self.ExternalCTData = None
        self.UseExternalSensorData = False
        self.ExternalSensorData = None
        self.ExternalSensorDataTime = None
        self.ExternalSensorGagueData = None
        self.ExternalDataLock = threading.RLock()

        self.ProgramStartTime = datetime.datetime.now() # used for com metrics
        self.OutageStartTime = (self.ProgramStartTime)  # if these two are the same, no outage has occured
        self.OutageReoccuringNoticeTime = (self.ProgramStartTime)
        self.OutageNoticeDelayTime = None
        self.LastOutageDuration = self.OutageStartTime - self.OutageStartTime
        self.OutageNoticeDelay = 0
        self.Buttons = []   # UI command buttons (loaded after controller ID, if any)

        try:

            self.console = SetupLogger("controller_console", log_file="", stream=True)
            if self.config != None:
                self.SiteName = self.config.ReadValue("sitename", default="Home")
                self.LogLocation = self.config.ReadValue(
                    "loglocation", default="/var/log/"
                )
                self.UseMetric = self.config.ReadValue(
                    "metricweather", return_type=bool, default=False
                )
                self.debug = self.config.ReadValue(
                    "debug", return_type=bool, default=False
                )
                self.EnableDebug = self.config.ReadValue(
                    "enabledebug", return_type=bool, default=False
                )
                self.bDisplayUnknownSensors = self.config.ReadValue(
                    "displayunknown", return_type=bool, default=False
                )
                self.bDisablePowerLog = self.config.ReadValue(
                    "disablepowerlog", return_type=bool, default=False
                )
                self.SubtractFuel = self.config.ReadValue(
                    "subtractfuel", return_type=float, default=0.0
                )
                self.UserURL = self.config.ReadValue("user_url", default="").strip()
                self.FuelUnits = self.config.ReadValue("fuel_units", default="gal")
                self.FuelHalfRate = self.config.ReadValue(
                    "half_rate", return_type=float, default=0.0
                )
                self.FuelFullRate = self.config.ReadValue(
                    "full_rate", return_type=float, default=0.0
                )
                self.UseExternalCTData = self.config.ReadValue(
                    "use_external_power_data", return_type=bool, default=False
                )
                # for gentankutil
                self.UseExternalFuelData = self.config.ReadValue(
                    "use_external_fuel_data", return_type=bool, default=False
                )
                if not self.UseExternalFuelData:
                    # for gentankdiy
                    self.UseExternalFuelData = self.config.ReadValue(
                        "use_external_fuel_data_diy", return_type=bool, default=False
                    )

                self.EstimateLoad = self.config.ReadValue(
                    "estimated_load", return_type=float, default=0.50
                )
                if self.EstimateLoad < 0:
                    self.EstimateLoad = 0
                if self.EstimateLoad > 1:
                    self.EstimateLoad = 1

                if self.config.HasOption("outagelog"):
                    self.OutageLog = self.config.ReadValue("outagelog")
                    self.LogError(
                        "Using alternate outage logfile: " + str(self.OutageLog)
                    )

                if self.config.HasOption("kwlog"):
                    self.PowerLog = self.config.ReadValue("kwlog")

                if self.config.HasOption("fuel_log"):
                    self.FuelLog = self.config.ReadValue("fuel_log")
                    self.FuelLog = self.FuelLog.strip()

                self.UseFuelLog = self.config.ReadValue(
                    "enable_fuel_log", return_type=bool, default=False
                )
                self.FuelLogFrequency = self.config.ReadValue(
                    "fuel_log_freq", return_type=float, default=15.0
                )

                self.MinimumOutageDuration = self.config.ReadValue(
                    "min_outage_duration", return_type=int, default=0
                )
                self.PowerLogMaxSize = self.config.ReadValue(
                    "kwlogmax", return_type=float, default=15.0
                )
                self.MaxPowerLogEntries = self.config.ReadValue(
                    "max_powerlog_entries", return_type=int, default=4000
                )

                if self.config.HasOption("nominalfrequency"):
                    self.NominalFreq = self.config.ReadValue("nominalfrequency")
                    if not self.StringIsInt(self.NominalFreq):
                        self.NominalFreq = "Unknown"
                if self.config.HasOption("nominalRPM"):
                    self.NominalRPM = self.config.ReadValue("nominalRPM")
                    if not self.StringIsInt(self.NominalRPM):
                        self.NominalRPM = "Unknown"
                if self.config.HasOption("nominalKW"):
                    self.NominalKW = self.config.ReadValue("nominalKW")
                    if not self.StringIsFloat(self.NominalKW):
                        self.NominalKW = "Unknown"
                if self.config.HasOption("model"):
                    self.Model = self.config.ReadValue("model")
                
                self.NominalLineVolts = self.config.ReadValue("nominallinevolts", return_type=int, default=240)

                if self.config.HasOption("controllertype"):
                    self.ControllerSelected = self.config.ReadValue("controllertype")

                if self.config.HasOption("fueltype"):
                    self.FuelType = self.config.ReadValue("fueltype")

                self.TankSize = self.config.ReadValue(
                    "tanksize", return_type=int, default=0
                )

                self.SmartSwitch = self.config.ReadValue(
                    "smart_transfer_switch", return_type=bool, default=False
                )

                self.OutageNoticeDelay = self.config.ReadValue(
                    "outage_notice_delay", return_type=int, default=0
                )

                self.bDisablePlatformStats = self.config.ReadValue(
                    "disableplatformstats", return_type=bool, default=False
                )
                self.bAlternateDateFormat = self.config.ReadValue(
                    "alternate_date_format", return_type=bool, default=False
                )

                # num minutes to send a warning email about an outage
                self.OutageNoticeInterval = self.config.ReadValue("outage_notice_interval", return_type=int, default=0)

                # the percentage of the total load of the allowable difference in current between legs
                self.UnbalancedCapacity = self.config.ReadValue(
                    "unbalanced_capacity", return_type=float, default=0
                )
                if self.bDisablePlatformStats:
                    self.bUseRaspberryPiCpuTempGauge = False
                    self.bUseLinuxWifiSignalGauge = False
                else:
                    self.bUseRaspberryPiCpuTempGauge = self.config.ReadValue(
                        "useraspberrypicputempgauge", return_type=bool, default=True
                    )
                    self.bUseLinuxWifiSignalGauge = self.config.ReadValue(
                        "uselinuxwifisignalgauge", return_type=bool, default=True
                    )
        except Exception as e1:
            self.FatalError("Missing config file or config file entries: " + str(e1))

        try:
            if not self.bDisablePlatformStats:
                self.Platform = MyPlatform(log=self.log, usemetric=self.UseMetric, debug = self.debug)
                if self.Platform.GetRaspberryPiTemp(ReturnFloat=True) == 0.0:
                    self.LogError("CPU Temp not supported.")
                    self.bUseRaspberryPiCpuTempGauge = False
                    # CPU temp is not supported on this platform
            else:
                self.Platform = None
        except Exception as e1:
            self.FatalError("Failure loading platform module: " + str(e1))

    # ----------  GeneratorController:StartCommonThreads-------------------------
    # called after get config file, starts threads common to all controllers
    def StartCommonThreads(self):

        self.Threads["CheckAlarmThread"] = MyThread(
            self.CheckAlarmThread, Name="CheckAlarmThread"
        )
        # start read thread to process incoming data commands
        self.Threads["ProcessThread"] = MyThread(
            self.ProcessThread, Name="ProcessThread"
        )

        if self.EnableDebug:  # for debugging registers
            self.Threads["DebugThread"] = MyThread(self.DebugThread, Name="DebugThread")

        # start thread for kw log
        self.Threads["PowerMeter"] = MyThread(self.PowerMeter, Name="PowerMeter")

        self.Threads["MaintenanceHouseKeepingThread"] = MyThread(
            self.MaintenanceHouseKeepingThread, Name="MaintenanceHouseKeepingThread")

        if self.UseFuelLog:
            self.Threads["FuelLogger"] = MyThread(self.FuelLogger, Name="FuelLogger")

    # ---------- GeneratorController:CheckForOutageCommon--------------------------
    def CheckForOutageCommon(self, UtilityVolts, ThresholdVoltage, PickupVoltage):

        try:
            if (
                UtilityVolts == None
                or ThresholdVoltage == None
                or PickupVoltage == None
            ):
                return

            if UtilityVolts < 0 or ThresholdVoltage < 0 or PickupVoltage < 0:
                # invalid value
                return
            if UtilityVolts >= (self.NominalLineVolts * 2.5):
                # ivalid value
                return

            # first time thru set the values to the same voltage level
            if self.UtilityVoltsMin == 0 and self.UtilityVoltsMax == 0:
                self.UtilityVoltsMin = UtilityVolts
                self.UtilityVoltsMax = UtilityVolts

            if UtilityVolts > self.UtilityVoltsMax:
                if UtilityVolts > PickupVoltage:
                    self.UtilityVoltsMax = UtilityVolts

            if UtilityVolts < self.UtilityVoltsMin:
                if UtilityVolts > ThresholdVoltage:
                    self.UtilityVoltsMin = UtilityVolts

            # Check for outage
            # are we in an outage now
            # NOTE: for now we are just comparing these numbers, the generator has a programmable delay
            # that must be met once the voltage passes the threshold. This may cause some "switch bounce"
            # testing needed
            if self.SystemInOutage:
                if UtilityVolts > PickupVoltage:
                    self.SystemInOutage = False
                    self.LastOutageDuration = (datetime.datetime.now() - self.OutageStartTime)
                    OutageStr = str(self.LastOutageDuration).split(".")[0]      # remove microseconds from string
                    msgbody = ("\nUtility Power Restored at " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ". Duration of outage " + OutageStr)
                    self.MessagePipe.SendMessage("Outage Recovery Notice at " + self.SiteName,msgbody,msgtype="outage")

                    try:
                        if self.PowerMeterIsSupported() and self.FuelConsumptionSupported():
                            if (int(self.LastOutageDuration.total_seconds()) > 0):
                                # calling getpowerhistory with a duration of zero returns total fuel used so don't do that
                                FuelUsed = self.GetPowerHistory("power_log_json=%d,fuel" % int(self.LastOutageDuration.total_seconds()))
                            else:
                                # Outage of zero seconds...
                                if self.UseMetric:
                                    FuelUsed = "0 L"
                                else:
                                    FuelUsed = "0 gal"
                            if len(FuelUsed) and not "unknown" in FuelUsed.lower():
                                OutageStr += "," + FuelUsed
                    except Exception as e1:
                        self.LogErrorLine("Error recording fuel usage for outage: " + str(e1))
                    # log outage to file
                    if (int(self.LastOutageDuration.total_seconds())> self.MinimumOutageDuration):
                        self.LogToFile(self.OutageLog, self.OutageStartTime.strftime("%Y-%m-%d %H:%M:%S"),OutageStr,)
                else:
                    self.SendRecuringOutageNotice()
            else:
                if UtilityVolts < ThresholdVoltage:
                    if self.CheckOutageNoticeDelay():
                        self.SystemInOutage = True
                        self.OutageStartTime = datetime.datetime.now()
                        self.OutageReoccuringNoticeTime = datetime.datetime.now()
                        msgbody = ("\nUtility Power Out at "+ self.OutageStartTime.strftime("%Y-%m-%d %H:%M:%S"))
                        self.MessagePipe.SendMessage("Outage Notice at " + self.SiteName,msgbody,msgtype="outage",)
                else:
                    self.OutageNoticeDelayTime = None
        except Exception as e1:
            self.LogErrorLine("Error in CheckForOutageCommon: " + str(e1))
            return

    # ------------ GeneratorController:SendRecuringOutageNotice ----------------
    def SendRecuringOutageNotice(self):
        try:
            if not self.SystemInOutage:
                return 
            if self.OutageNoticeInterval < 1:
                return 
            
            LastOutageDuration = (datetime.datetime.now() - self.OutageStartTime)
            if LastOutageDuration.total_seconds() <= self.MinimumOutageDuration:
                return

            if (datetime.datetime.now() - self.OutageReoccuringNoticeTime).total_seconds() / 60 < self.OutageNoticeInterval:
                return
            self.OutageReoccuringNoticeTime = datetime.datetime.now()
            OutageStr = str(LastOutageDuration).split(".")[0]      # remove microseconds from string
            msgbody = ("\nUtility Outage Status: Untility power still out at " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ". Duration of outage " + OutageStr)
            self.MessagePipe.SendMessage("Recurring Outage Notice at " + self.SiteName,msgbody,msgtype="outage")
        except Exception as e1:
            self.LogErrorLine("Error in SendRecuringOutageNotice: " + str(e1))
            return
    # ------------ GeneratorController:CheckOutageNoticeDelay ------------------
    def CheckOutageNoticeDelay(self):

        try:
            if self.OutageNoticeDelay == 0:
                return True

            if self.OutageNoticeDelayTime == None:
                self.OutageNoticeDelayTime = datetime.datetime.now()
                return False

            OutageNoticeDelta = datetime.datetime.now() - self.OutageNoticeDelayTime
            if self.OutageNoticeDelay > OutageNoticeDelta.total_seconds():
                return False

            self.OutageNoticeDelayTime = None
        except Exception as e1:
            self.LogErrorLine("Error in CheckOutageNoticeDelay: " + str(e1))
        return True

    # ---------- GeneratorController:ProcessThread------------------------------
    #  read registers, remove items from Buffer, form packets, store register data
    def ProcessThread(self):

        try:
            self.ModBus.Flush()
            self.InitDevice()
            if self.IsStopping:
                return
            while True:
                try:
                    if not self.InitComplete:
                        self.InitDevice()
                    else:
                        self.MasterEmulation()
                    if self.IsStopSignaled("ProcessThread"):
                        break
                    if self.IsStopping:
                        break
                except Exception as e1:
                    self.LogErrorLine(
                        "Error in Controller ProcessThread (1), continue: " + str(e1)
                    )
        except Exception as e1:
            self.LogErrorLine("Exiting Controller ProcessThread (2): " + str(e1))

    # ---------- GeneratorController:CheckAlarmThread---------------------------
    #  When signaled, this thread will check for alarms
    def CheckAlarmThread(self):

        time.sleep(0.25)
        while True:
            try:
                if self.WaitForExit("CheckAlarmThread", 0.25):  #
                    return

                if self.CheckForAlarmEvent.is_set():
                    self.CheckForAlarmEvent.clear()
                    self.CheckForAlarms()

            except Exception as e1:
                self.LogErrorLine("Error in  CheckAlarmThread: " + str(e1))

    # ----------  GeneratorController:TestCommand--------------------------------
    def TestCommand(self):
        return "Not Supported"

    # ----------  GeneratorController:GeneratorIsRunning-------------------------
    def GeneratorIsRunning(self):

        return self.GetBaseStatus() in ["EXERCISING", "RUNNING", "RUNNING-MANUAL"]

    # ----------  GeneratorController:FuelLogger---------------------------------
    def FuelLogger(self):

        if not self.UseFuelLog:
            return

        time.sleep(0.25)
        while True:
            if self.InitComplete:
                break
            if self.WaitForExit("FuelLogger", 1):
                return

        LastFuelValue = None

        while True:
            try:
                if LastFuelValue != None and self.WaitForExit(
                    "FuelLogger", self.FuelLogFrequency * 60.0
                ):
                    return

                if (
                    not self.ExternalFuelDataSupported()
                    and not self.FuelTankCalculationSupported()
                    and not self.FuelSensorSupported()
                ):
                    # this is an invalid setting so we do nothing, we do not exit to not flag a dead thread warning
                    LastFuelValue = 0.0
                    continue

                FuelValue = self.GetFuelLevel(ReturnFloat=True)

                if FuelValue == None:
                    if self.WaitForExit("FuelLogger", self.FuelLogFrequency * 60.0):
                        return
                    continue
                if FuelValue == LastFuelValue:
                    continue

                LastFuelValue = FuelValue
                TimeStamp = datetime.datetime.now().strftime("%x %X")
                with self.FuelLock:
                    self.LogToFile(self.FuelLog, TimeStamp, str(FuelValue))

            except Exception as e1:
                self.LogErrorLine("Error in  FuelLogger: " + str(e1))

    # ------------ GeneratorController::ClearFuelLog-----------------------------
    def ClearFuelLog(self):

        try:
            if not len(self.FuelLog):
                return "Fuel Not Present"

            if not os.path.isfile(self.FuelLog):
                return "Power Log is empty"

            with self.FuelLock:
                os.remove(self.FuelLog)
                time.sleep(1)

            return "Fuel Log cleared"
        except Exception as e1:
            self.LogErrorLine("Error in  ClearFuelLog: " + str(e1))
            return "Error in  ClearFuelLog: " + str(e1)

    # ----------  GeneratorController:DebugThread--------------------------------
    def DebugThread(self):

        if not self.EnableDebug:
            return
        time.sleep(0.25)

        if (
            not self.ControllerSelected == None
            or not len(self.ControllerSelected)
            or self.ControllerSelected == "generac_evo_nexus"
        ):
            MaxReg = 0x400
        else:
            MaxReg = 0x2000
        self.InitCompleteEvent.wait()

        if self.IsStopping:
            return
        self.LogError("Debug Enabled")
        self.FeedbackPipe.SendFeedback(
            "Debug Thread Starting",
            FullLogs=True,
            Always=True,
            Message="Starting Debug Thread",
        )
        TotalSent = 0

        RegistersUnderTest = collections.OrderedDict()
        RegistersUnderTestData = ""

        while True:

            if self.IsStopSignaled("DebugThread"):
                return
            if TotalSent >= 5:
                self.FeedbackPipe.SendFeedback(
                    "Debug Thread Finished",
                    Always=True,
                    FullLogs=True,
                    Message="Finished Debug Thread",
                )
                if self.WaitForExit("DebugThread", 1):  #
                    return
                continue
            try:
                for Reg in range(0x0, MaxReg):
                    if self.WaitForExit("DebugThread", 0.25):  #
                        return
                    Register = "%04x" % Reg
                    NewValue = self.ModBus.ProcessTransaction(
                        Register, 1, skipupdate=True
                    )
                    if not len(NewValue):
                        continue
                    OldValue = RegistersUnderTest.get(Register, "")
                    if OldValue == "":
                        RegistersUnderTest[
                            Register
                        ] = NewValue  # first time seeing this register so add it to the list
                    elif NewValue != OldValue:
                        BitsChanged, Mask = self.GetNumBitsChanged(OldValue, NewValue)
                        RegistersUnderTestData += (
                            "Reg %s changed from %s to %s, Bits Changed: %d, Mask: %x, Engine State: %s\n"
                            % (
                                Register,
                                OldValue,
                                NewValue,
                                BitsChanged,
                                Mask,
                                self.GetEngineState(),
                            )
                        )
                        RegistersUnderTest[Register] = Value  # update the value

                msgbody = "\n"
                try:
                    msgbody += json.dumps(RegistersUnderTest, indent=4, sort_keys=False)
                except:
                    for Register, Value in RegistersUnderTest.items():
                        msgbody += self.printToString("%s:%s" % (Register, Value))

                self.FeedbackPipe.SendFeedback(
                    "Debug Thread (Registers)",
                    FullLogs=True,
                    Always=True,
                    Message=msgbody,
                    NoCheck=True,
                )
                if len(RegistersUnderTestData):
                    self.FeedbackPipe.SendFeedback(
                        "Debug Thread (Changes)",
                        FullLogs=True,
                        Always=True,
                        Message=RegistersUnderTestData,
                        NoCheck=True,
                    )
                RegistersUnderTestData = "\n"
                TotalSent += 1

            except Exception as e1:
                self.LogErrorLine("Error in DebugThread: " + str(e1))

    # -------------GeneratorController:GetParameterStringValue-------------------
    def GetParameterStringValue(
        self, Register, ReturnString=False, offset=None, max=None
    ):

        StringValue = self.Strings.get(Register, "")
        if ReturnString:
            if offset == None:
                return self.HexStringToString(StringValue)
            elif offset != None and max != None:
                return self.HexStringToString(StringValue[offset:max])
            elif offset != None and max == None:
                return self.HexStringToString(StringValue[offset:])
            elif offset == None and max != None:
                return self.HexStringToString(StringValue[:max])
        return StringValue

    # -------------GeneratorController:GetParameterFileValue---------------------
    def GetParameterFileValue(
        self, Register, ReturnString=False, offset=None, max=None
    ):

        StringValue = self.FileData.get(Register, "")
        if ReturnString:
            if offset == None:
                return self.HexStringToString(StringValue)
            elif offset != None and max != None:
                return self.HexStringToString(StringValue[offset:max])
            elif offset != None and max == None:
                return self.HexStringToString(StringValue[offset:])
            elif offset == None and max != None:
                return self.HexStringToString(StringValue[:max])
        return StringValue

    # ------------ GeneratorController:GetRegisterValueFromList -----------------
    def GetRegisterValueFromList(self, Register, IsCoil = False, IsInput = False):

        try:
            if IsCoil:
                return self.Coils.get(Register, "")
            if IsInput:
                return self.Inputs.get(Register, "")
            return self.Holding.get(Register, "")
        except Exception as e1:
            self.LogErrorLine("Error in GetRegisterValueFromList: " + str(e1))
            return ""

    # -------------GeneratorController:GetCoil-----------------------------------
    def GetCoil(self, Register,OnLabel=None, OffLabel=None):

        try:
            if OnLabel != None and OffLabel != None:
                DefaultReturn = False
            else:
                DefaultReturn =  OffLabel
            value = self.GetParameterBit(Register, 0x01, OnLabel = OnLabel, OffLabel = OffLabel, IsCoil = True)
            if OnLabel != None and OffLabel != None:
                return value 
            if value == 1:
                return True 
            return False
        except Exception as e1:
            self.LogErrorLine("Error in GetCoil: " + str(e1))
            return DefaultReturn

    # -------------GeneratorController:GetParameterBit---------------------------
    def GetParameterBit(self, Register, Mask, OnLabel=None, OffLabel=None, IsCoil = False, IsInput = False):

        try:
            Value = self.GetRegisterValueFromList(Register, IsCoil = IsCoil, IsInput = IsInput)
            if not len(Value):
                return ""

            IntValue = int(Value, 16)

            if OnLabel == None or OffLabel == None:
                return self.BitIsEqual(IntValue, Mask, Mask)
            elif self.BitIsEqual(IntValue, Mask, Mask):
                return OnLabel
            else:
                return OffLabel
        except Exception as e1:
            self.LogErrorLine("Error in GetParameterBit: " + str(e1))
            return ""

    # -------------GeneratorController:GetParameterLong--------------------------
    def GetParameterLong(
        self,
        RegisterLo,
        RegisterHi,
        Label=None,
        Divider=None,
        ReturnInt=False,
        ReturnFloat=False,
        IsCoil = False, 
        IsInput = False
    ):

        try:
            if ReturnInt:
                DefaultReturn = 0
            elif ReturnFloat:
                DefaultReturn = 0.0
            else:
                DefaultReturn = ""

            if not Label == None:
                LabelStr = Label
            else:
                LabelStr = ""

            ValueLo = self.GetParameter(RegisterLo, IsCoil = IsCoil, IsInput = IsInput)
            ValueHi = self.GetParameter(RegisterHi, IsCoil = IsCoil, IsInput = IsInput)

            if not len(ValueLo) or not len(ValueHi):
                return DefaultReturn

            IntValueLo = int(ValueLo)
            IntValueHi = int(ValueHi)

            IntValue = IntValueHi << 16 | IntValueLo

            if ReturnInt:
                return IntValue

            if not Divider == None:
                FloatValue = IntValue / Divider
                if ReturnFloat:
                    return round(FloatValue, 3)
                return "%2.1f %s" % (FloatValue, LabelStr)
            return "%d %s" % (IntValue, LabelStr)
        except Exception as e1:
            self.LogErrorLine("Error in GetParameterLong: " + str(e1))
            return DefaultReturn

    # -------------GeneratorController:GetParameter------------------------------
    # Hex assumes no Divider and Label - return Hex string
    # ReturnInt assumes no Divier and Label - Return int
    def GetParameter(
        self,
        Register,
        Label=None,
        Divider=None,
        Hex=False,
        ReturnInt=False,
        ReturnFloat=False,
        ReturnString=False,
        IsCoil = False,
        IsInput = False
    ):

        try:
            if ReturnInt:
                DefaultReturn = 0
            elif ReturnFloat:
                DefaultReturn = 0.0
            else:
                DefaultReturn = ""

            Value = self.GetRegisterValueFromList(Register, IsCoil = IsCoil, IsInput = IsInput)
            if not len(Value):
                return DefaultReturn

            if ReturnString == True:
                return self.HexStringToString(Value)

            if Divider == None and Label == None:
                if Hex:
                    return Value
                elif ReturnFloat:
                    return float(int(Value, 16))
                elif ReturnInt:
                    return int(Value, 16)
                else:
                    return str(int(Value, 16))

            IntValue = int(Value, 16)
            if not Divider == None:
                FloatValue = IntValue / Divider
                if ReturnInt:
                    return int(FloatValue)
                if ReturnFloat:
                    return round(FloatValue, 3)
                if not Label == None:
                    return "%.2f %s" % (FloatValue, Label)
                else:
                    return "%.2f" % (FloatValue)
            elif ReturnInt:
                return IntValue
            elif not Label == None:
                return "%d %s" % (IntValue, Label)
            else:
                return str(int(Value, 16))

        except Exception as e1:
            self.LogErrorLine(
                "Error in GetParameter: Reg: " + Register + ": " + str(e1)
            )
            return ""

    # ---------------------GeneratorController::GetConfig------------------------
    # read conf file, used internally, not called by genmon
    # return True on success, else False
    def GetConfig(self):
        True

    # ---------------------GeneratorController::SystemInAlarm--------------------
    # return True if generator is in alarm, else False
    def SystemInAlarm(self):
        return False

    # -------------CustomController:SetCommandButton-----------------------------
    def SetCommandButton(self, CommandString):
        try:
            ValidInput = False
            EntryString = CommandString
            if EntryString == None or not len(EntryString):
                return "Error: Invalid input for Set Button Command entry."

            EntryString = EntryString.strip()
            if EntryString.startswith("set_button_command"):
                EntryString = EntryString[len("set_button_command") :]
                EntryString = EntryString.strip()
                if EntryString.strip().startswith("="):
                    EntryString = EntryString[len("=") :]
                    EntryString = EntryString.strip()
                    ValidInput = True

            if ValidInput:
                try:
                    CommandSetList = json.loads(EntryString)
                    # validate object
                    if not isinstance(CommandSetList, list) and not (len(CommandSetList) == 0):
                        self.LogError("Invalid button object in SetCommandButton")
                        return "Error: Invalid button object"
                    # Execute Command
                    return self.ExecuteRemoteCommand(CommandSetList)
                except Exception as e1:
                    self.LogErrorLine("Error in SetCommandButton: " + str(e1))
                    return "Error: Invalid input for SetCommandButton (2), see error log."
            else:
                self.LogError("Error in SetCommandButton: invalid input: " + str(CommandString))
                return "Error: Invalid input for SetCommandButton (3)."
            return "OK"
        except Exception as e1:
            self.LogErrorLine("Error in SetCommandButton: " + str(e1))
            return "Error in SetCommandButton, see error log."
        return "OK"

     # -------------Controller:GetButtons---------------------------------------
    def GetButtons(self, singlebuttonname = None):
        try:

            if len(self.Buttons) < 1:
                return []
            button_list = self.Buttons
            button_list = self.GetButtonsCommon(button_list, singlebuttonname=singlebuttonname)
            return button_list
        except Exception as e1:
            self.LogErrorLine("Error in GetButtons: " + str(e1))
            return []
        
    # ----------  Controller::GetButtonsCommon----------------------------------
    def GetButtonsCommon(self, button_list, singlebuttonname = None):
        try:
            if button_list == None:
                return []
            if not isinstance(button_list, list):
                self.LogError("Error in GetButtonsCommon: invalid input or data: "+ str(type(button_list)))
                return []

            # Validate buttons before sending to the web app
            return_buttons = []
            for button in button_list:
                
                if not "onewordcommand" in button.keys():
                    self.LogError("Error in GetButtonsCommon: button must have onewordcommand element: "+ str(button))
                    continue
                elif not isinstance(button["onewordcommand"], str):
                    self.LogError("Error in GetButtonsCommon: invalid button defined validateing onewordcommand (non string): "+ str(button))
                    continue
                if not "title" in button.keys():
                    self.LogError("Error in GetButtonsCommon: button must have title element: "+ str(button))
                    continue
                elif not isinstance(button["title"], str):
                    self.LogError("Error in GetButtonsCommon: invalid button defined validateing title (not string): "+ str(button))
                    continue
                if not "command_sequence" in button.keys():
                    self.LogError("Error in GetButtonsCommon: button must have command_sequence element: "+ str(button))
                    continue
                elif not isinstance(button["command_sequence"], list):
                    self.LogError("Error in GetButtonsCommon: invalid button defined validateing command_sequence:(not list) "+ str(button))
                    continue
                
                # valiate command sequeuence
                CommandError = False
                for command in button["command_sequence"]:
                    if not "reg" in command.keys() or not isinstance(command["reg"], str):
                        self.LogError("Error in GetButtonsCommon: invalid command string defined validateing reg: "+ str(button))
                        CommandError = True
                        break
                    if not "value" in command.keys():
                        # this command requires input from the web app, let's validate the params
                        # "input_title", "type" is required. "length" is default 2 but must be a multiple of 2
                        if not "input_title" in command.keys() or not "type" in command.keys():
                            self.LogError("Error in GetButtonsCommon: Error validateing input_title and type: "+ str(button))
                            CommandError = True
                            break
                        if "length" in command.keys():
                            if(int(command["length"]) % 2 != 0):
                                self.LogError("Error in GetButtonsCommon: length of command_sequence input must be a multiple of 2: " + str(button))
                                CommandError = True
                                break
                        if "bounds_regex" in command.keys():
                            if not self.RegExIsValid(command["bounds_regex"]):
                                self.LogError("Error in GetButtonsCommon: invalid regular expression for bounds_regex in command_sequence: " + str(button))
                                CommandError = True
                                break
                if CommandError:
                    continue

                if singlebuttonname != None and singlebuttonname == button["onewordcommand"]:
                    return button

                return_buttons.append(button)

            return return_buttons
        except Exception as e1:
            self.LogErrorLine("Error in GetButtonsCommon: " + str(e1))
            return []

    # -------------CustomController:ExecuteRemoteCommand-------------------------
    def ExecuteRemoteCommand(self, CommandSetList):
        # CommandSetList is a list of dicts, each dict is a command to execute 
        # Each dict in the list is in the format of the objects in the 'buttons' 
        # list in the custom controller JSON format
        try:
            if sys.version_info[0] < 3:  #
                self.LogError("Error in ExecuteRemoteCommand, requires python3: " + str(sys.version_info.major) + "." + str(sys.version_info.minor))
                return "Error in ExecuteRemoteCommand, requires python3"
            if not isinstance(CommandSetList, list):
                return "Error: invalid input in ExecuteRemoteCommand"
            
            with self.ModBus.CommAccessLock:
                # put the lock here so if there are multiple commands they will be executed back to back
                for button_command in CommandSetList:
                    if not isinstance(button_command, dict) and not len(button_command) == 1:
                        self.LogError("Error on ExecuteRemoteCommand, expecting single dict: " + str(button_command))
                        return "Error: invalid input in ExecuteRemoteCommand"
                    if not "onewordcommand" in button_command.keys():
                        self.LogError("Error on ExecuteRemoteCommand, invalid dict: " + str(button_command))
                        return "Error: invalid input in ExecuteRemoteCommand (2)"
                    # make a copy of the dict so we can add the input without modifying the original
                    returndict = self.GetButtons(singlebuttonname = button_command["onewordcommand"])
                    if returndict == None:
                        self.LogError("Error on ExecuteRemoteCommand, command not found: " + str(button_command))
                        return "Error: invalid input in ExecuteRemoteCommand command not found"
                    selected_command = copy.deepcopy(returndict)
                    if not len(selected_command):
                        self.LogError("Error on ExecuteRemoteCommand, invalid command: " + str(button_command))
                        return "Error: invalid command in ExecuteRemoteCommand (2)"
                    
                    # selected_command from genmon, button_command from UI
                    if not "command_sequence" in selected_command.keys() or not "command_sequence" in button_command.keys():
                        self.LogError("Error on ExecuteRemoteCommand, command sequence mismatch: " + str(button_command))
                        return "Error on ExecuteRemoteCommand, command sequence mismatch"
                    if not (len(selected_command["command_sequence"]) == len(button_command["command_sequence"])):
                        self.LogError("Error on ExecuteRemoteCommand, command sequence mismatch (2): " + str(button_command))
                        return "Error on ExecuteRemoteCommand, command sequence mismatch (2)"
                    # iterate thru both lists of commands
                    for gm_cmd, ui_cmd in zip(selected_command["command_sequence"], button_command["command_sequence"]):
                        if "input_title" in gm_cmd.keys() and "value" in ui_cmd.keys():
                            if "bounds_regex" in gm_cmd.keys():
                                if not re.match(gm_cmd["bounds_regex"], str(ui_cmd["value"])):
                                    self.LogError("Error in ExecuteRemoteCommand: Failed bounds check: " + str(ui_cmd))
                                    return "Error in ExecuteRemoteCommand: Failed bounds check"
                            if "type" in gm_cmd.keys() and gm_cmd["type"] == "int":
                                if not "length" in gm_cmd.keys() or ("length" in gm_cmd.keys() and gm_cmd["length"] == 2):
                                    gm_cmd["value"] = "%04x" % int(ui_cmd["value"])
                                elif "length" in gm_cmd and gm_cmd["length"] == 4:
                                    gm_cmd["value"] = "%08x" % int(ui_cmd["value"])
                                else:
                                    self.LogError("Error in ExecuteRemoteCommand: only 2 or 4 supported for int lenght: " + str(gm_cmd))
                                    return "Error in ExecuteRemoteCommand, invalid length of input"
                            else:
                                self.LogError("Error in ExecuteRemoteCommand, unsupported type: " + str(ui_cmd))
                                return "Error in ExecuteRemoteCommand, unsupported type"
                        elif not "reg" in gm_cmd.keys() or not "value" in gm_cmd.keys():
                            self.LogError("Error in ExecuteRemoteCommand, invalid command in sequence: " + str(selected_command))
                            self.LogDebug(str(button_command))
                            return "Error in ExecuteRemoteCommand, invalid command in sequence"
                    # execute the command selected_command
                    return self.ExecuteCommandSequence(selected_command["command_sequence"])

        except Exception as e1:
            self.LogErrorLine("Error in ExecuteRemoteCommand: " + str(e1))
            self.LogDebug(str(CommandSetList))
            return "Error in ExecuteRemoteCommand"
        return "OK"
    # -------------CustomController:ExecuteCommandSequence-----------------------
    def ExecuteCommandSequence(self, command_sequence):
        try:
            with self.ModBus.CommAccessLock:
                for command in command_sequence:
                    if not "reg" in command.keys():
                        self.LogDebug("Error in ExecuteCommandSequence: invalid value array, no 'reg' in command_sequence command: " + str(command))
                        continue
                    if not isinstance(command["value"],int) and not len(command["value"]):
                        self.LogDebug("Error in ExecuteCommandSequence: invalid value array")
                        continue
                    if isinstance(command["value"], list):
                        if not (len(command["value"]) % 2) == 0:
                            self.LogDebug("Error in ExecuteCommandSequence: invalid value length")
                            return "Command not found."
                        Data = []
                        for item in command["value"]:
                            if isinstance(item, str):
                                Data.append(int(item, 16))
                            elif isinstance(item, int):
                                Data.append(item)
                            else:
                                self.LogDebug("Error in ExecuteCommandSequence: invalid type if value list")
                                return "Command not found."
                        self.LogDebug("Write List: len: " + str(int(len(Data)  / 2)) + " : "  + self.LogHexList(Data, prefix=command["reg"], nolog = True))
                        self.ModBus.ProcessWriteTransaction(command["reg"], len(Data) / 2, Data)

                    elif isinstance(command["value"], str):
                        # only supports single word writes
                        value = int(command["value"], 16)
                        LowByte = value & 0x00FF
                        HighByte = (value >> 8) & 0x00ff
                        Data = []
                        Data.append(HighByte)  
                        Data.append(LowByte)  
                        self.LogDebug("Write Str: len: "+ str(int(len(Data)  / 2)) + " : " + command["reg"] + ": "+ ("%04x %04x" % (HighByte, LowByte)))
                        self.ModBus.ProcessWriteTransaction(command["reg"], len(Data) / 2, Data)
                    elif isinstance(command["value"], int):
                        # only supports single word writes
                        value = command["value"]
                        LowByte = value & 0x00FF
                        HighByte = (value >> 8) & 0x00ff
                        Data = []
                        Data.append(HighByte)  
                        Data.append(LowByte)  
                        self.LogDebug("Write Int: len: "+ str(int(len(Data)  / 2)) + " : " + command["reg"]+ ": "+ ("%04x %04x" % (HighByte, LowByte)))
                        self.ModBus.ProcessWriteTransaction(command["reg"], len(Data) / 2, Data)
                    else:
                        self.LogDebug("Error in ExecuteCommandSequence: invalid value type")
                        return "Command not found."

                return "OK"
        except Exception as e1:
            self.LogErrorLine("Error in ExecuteCommandSequence: " + str(e1))
            self.LogDebug(str(command_sequence))
            return "Error in ExecuteCommandSequence"
        return "OK"
    # ------------ GeneratorController::GetStartInfo ----------------------------
    # return a dictionary with startup info for the gui
    def GetStartInfo(self, NoTile=False):

        StartInfo = {}
        try:
            StartInfo["fueltype"] = self.FuelType
            StartInfo["model"] = self.Model
            StartInfo["nominalKW"] = self.NominalKW
            StartInfo["nominalRPM"] = self.NominalRPM
            StartInfo["nominalfrequency"] = self.NominalFreq
            StartInfo["phase"] = self.Phase
            StartInfo["Controller"] = "Generic Controller Name"
            StartInfo["PowerGraph"] = self.PowerMeterIsSupported()
            StartInfo["NominalBatteryVolts"] = "12"
            StartInfo["UtilityVoltageDisplayed"] = True
            StartInfo["RemoteCommands"] = True
            StartInfo["RemoteButtons"] = False
            StartInfo["Linux"] = self.Platform.IsOSLinux()
            StartInfo["RaspberryPi"] = self.Platform.IsPlatformRaspberryPi()

            if not NoTile:

                StartInfo["buttons"] = self.GetButtons()

                StartInfo["tiles"] = []
                for Tile in self.TileList:
                    StartInfo["tiles"].append(Tile.GetStartInfo())

        except Exception as e1:
            self.LogErrorLine("Error in GetStartInfo: " + str(e1))
        return StartInfo

    # ------------ GeneratorController::GetStatusForGUI -------------------------
    # return dict for GUI
    def GetStatusForGUI(self):

        Status = {}
        try:
            Status["basestatus"] = self.GetBaseStatus()
            Status["switchstate"] = self.GetSwitchState()
            Status["enginestate"] = self.GetEngineState()
            Status["kwOutput"] = self.GetPowerOutput()
            Status["OutputVoltage"] = "0V"
            Status["BatteryVoltage"] = "0V"
            Status["UtilityVoltage"] = "0V"
            Status["Frequency"] = "0"
            Status["RPM"] = "0"

            # Exercise Info is a dict containing the following:
            ExerciseInfo = collections.OrderedDict()
            ExerciseInfo["Enabled"] = False
            ExerciseInfo["Frequency"] = "Weekly"  # Biweekly, Weekly or Monthly
            ExerciseInfo["Hour"] = "14"
            ExerciseInfo["Minute"] = "00"
            ExerciseInfo["QuietMode"] = "On"
            ExerciseInfo["EnhancedExerciseMode"] = False
            ExerciseInfo["Day"] = "Monday"
            Status["ExerciseInfo"] = ExerciseInfo
        except Exception as e1:
            self.LogErrorLine("Error in GetStatusForGUI: " + str(e1))
        return Status

    # ---------------------GeneratorController::DisplayLogs----------------------
    def DisplayLogs(self, AllLogs=False, DictOut=False, RawOutput=False):
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in DisplayLogs: " + str(e1))

    # ------------ GeneratorController::DisplayMaintenance ----------------------
    def DisplayMaintenance(self, DictOut=False, JSONNum=False):
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in DisplayMaintenance: " + str(e1))

    # ------------ GeneratorController::DisplayStatus ---------------------------
    def DisplayStatus(self, DictOut=False, JSONNum=False):
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in DisplayStatus: " + str(e1))

    # ------------------- GeneratorController::DisplayOutage --------------------
    def DisplayOutage(self, DictOut=False, JSONNum=False):
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in DisplayOutage: " + str(e1))

    # ------------ GeneratorController::DisplayRegisters ------------------------
    def DisplayRegisters(self, AllRegs=False, DictOut=False):
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in DisplayRegisters: " + str(e1))

    # ----------  GeneratorController::SetGeneratorTimeDate----------------------
    # set generator time to system time
    def SetGeneratorTimeDate(self):

        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in SetGeneratorTimeDate: " + str(e1))

        return "Not Supported"

    # ----------  GeneratorController::SetGeneratorQuietMode---------------------
    # Format of CmdString is "setquiet=yes" or "setquiet=no"
    # return  "Set Quiet Mode Command sent" or some meaningful error string
    def SetGeneratorQuietMode(self, CmdString):
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in SetGeneratorQuietMode: " + str(e1))

        return "Not Supported"

    # ----------  GeneratorController::SetGeneratorExerciseTime------------------
    # CmdString is in the format:
    #   setexercise=Monday,13:30,Weekly
    #   setexercise=Monday,13:30,BiWeekly
    #   setexercise=15,13:30,Monthly
    # return  "Set Exercise Time Command sent" or some meaningful error string
    def SetGeneratorExerciseTime(self, CmdString):
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in SetGeneratorExerciseTime: " + str(e1))

        return "Not Supported"

    # ----------  GeneratorController::SetGeneratorRemoteCommand---------------
    # CmdString will be in the format: "setremote=start"
    # valid commands are start, stop, starttransfer, startexercise
    # return string "Remote command sent successfully" or some descriptive error
    # string if failure
    def SetGeneratorRemoteCommand(self, CmdString):
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in SetGeneratorRemoteStartStop: " + str(e1))

        return "Not Supported"

    # ----------  GeneratorController:GetController  ----------------------------
    # return the name of the controller, if Actual == False then return the
    # controller name that the software has been instructed to use if overridden
    # in the conf file
    def GetController(self, Actual=True):
        return "Test Controller"

    # ----------  GeneratorController:ComminicationsIsActive  -------------------
    # Called every few seconds, if communictions are failing, return False, otherwise
    # True
    def ComminicationsIsActive(self):
        return False

    # ----------  GeneratorController:ResetCommStats  ---------------------------
    # reset communication stats, normally just a call to
    #   self.ModBus.ResetCommStats() if modbus is used
    def ResetCommStats(self):
        self.ModBus.ResetCommStats()

    # ----------  GeneratorController:RemoteButtonsSupported  --------------------
    # return true if Panel buttons are settable via the software
    def RemoteButtonsSupported(self):
        return False

    # ----------  GeneratorController:PowerMeterIsSupported  --------------------
    # return true if GetPowerOutput is supported
    def PowerMeterIsSupported(self):
        return False

    # ---------------------GeneratorController::GetPowerOutput-------------------
    # returns current kW
    # rerturn empty string ("") if not supported,
    # return kW with units i.e. "2.45kW"
    def GetPowerOutput(self, ReturnFloat=False):
        return ""

    # ----------  GeneratorController:GetCommStatus  ----------------------------
    # return Dict with communication stats
    def GetCommStatus(self):
        return self.ModBus.GetCommStats()

    # ------------ GeneratorController:GetRunHours ------------------------------
    def GetRunHours(self):
        return "Unknown"

    # ------------ GeneratorController:GetBaseStatus ----------------------------
    # return one of the following: "ALARM", "SERVICEDUE", "EXERCISING", "RUNNING",
    # "RUNNING-MANUAL", "OFF", "MANUAL", "READY"
    def GetBaseStatus(self):
        return "OFF"

    # ------------ GeneratorController:GetOneLineStatus -------------------------
    # returns a one line status for example : switch state and engine state
    def GetOneLineStatus(self):
        return self.GetSwitchState() + " : " + self.GetEngineState()

    # ------------ GeneratorController:RegRegValue ------------------------------
    def GetRegValue(self, CmdString):

        # extract quiet mode setting from Command String
        # format is setquiet=yes or setquiet=no
        msgbody = "Invalid command syntax for command getregvalue"
        try:
            # Format we are looking for is "getregvalue=01f4"
            CmdList = CmdString.split("=")
            if len(CmdList) != 2:
                self.LogError(
                    "Validation Error: Error parsing command string in GetRegValue (parse): "
                    + CmdString
                )
                return msgbody

            CmdList[0] = CmdList[0].strip()

            if not CmdList[0].lower() == "getregvalue":
                self.LogError(
                    "Validation Error: Error parsing command string in GetRegValue (parse2): "
                    + CmdString
                )
                return msgbody

            Register = CmdList[1].strip()

            RegValue = self.GetRegisterValueFromList(Register)

            if RegValue == "":
                self.LogError("Validation Error: Register  not known:" + Register)
                msgbody = "Unsupported Register: " + Register
                return msgbody

            msgbody = RegValue

        except Exception as e1:
            self.LogErrorLine(
                "Validation Error: Error parsing command string in GetRegValue: "
                + CmdString
            )
            self.LogError(str(e1))
            return msgbody

        return msgbody

    # ------------ GeneratorController:ReadRegValue -----------------------------
    def ReadRegValue(self, CmdString):

        # extract quiet mode setting from Command String
        # Format we are looking for is "readregvalue=01f4"
        msgbody = "Invalid command syntax for command readregvalue"
        try:

            CmdList = CmdString.split("=")
            if len(CmdList) != 2:
                self.LogError(
                    "Validation Error: Error parsing command string in ReadRegValue (parse): "
                    + CmdString
                )
                return msgbody

            CmdList[0] = CmdList[0].strip()

            if not CmdList[0].lower() == "readregvalue":
                self.LogError(
                    "Validation Error: Error parsing command string in ReadRegValue (parse2): "
                    + CmdString
                )
                return msgbody

            Register = CmdList[1].strip()

            RegValue = self.ModBus.ProcessTransaction(Register, 1, skipupdate=True)

            if RegValue == "":
                self.LogError(
                    "Validation Error: Register not known (ReadRegValue):" + Register
                )
                msgbody = "Unsupported Register: " + Register
                return msgbody

            msgbody = RegValue

        except Exception as e1:
            self.LogErrorLine(
                "Validation Error: Error parsing command string in ReadRegValue: "
                + CmdString
            )
            self.LogError(str(e1))
            return msgbody

        return msgbody

    # ------------ GeneratorController:WriteRegValue ---------------------------
    def WriteRegValue(self, CmdString):

        # extract quiet mode setting from Command String
        # Format we are looking for is "writeregvalue=01f4,aa"
        msgbody = "Invalid command syntax for command writeregvalue"
        try:

            CmdList = CmdString.split("=")
            if len(CmdList) != 2:
                self.LogError("Validation Error: Error parsing command string in WriteRegValue (parse): " + CmdString)
                return msgbody

            CmdList[0] = CmdList[0].strip()

            if not CmdList[0].lower() == "writeregvalue":
                self.LogError("Validation Error: Error parsing command string in WriteRegValue (parse2): " + CmdString)
                return msgbody

            ParsedList = CmdList[1].split(",")

            if len(ParsedList) != 2:
                self.LogError("Validation Error: Error parsing command string in WriteRegValue (parse3): " + CmdString)
                return msgbody
            Register = ParsedList[0].strip()
            Value = ParsedList[1].strip()
            Value = int(Value,16)
            LowByte = Value & 0x00FF
            HighByte = Value >> 8
            Data = []
            Data.append(HighByte)
            Data.append(LowByte)
            RegValue = self.ModBus.ProcessWriteTransaction(Register, len(Data) / 2, Data)

            if RegValue == "":
                msgbody = "OK"

        except Exception as e1:
            self.LogErrorLine("Validation Error: Error parsing command string in WriteRegValue: " + CmdString)
            self.LogError(str(e1))
            return msgbody

        return msgbody

    # ------------ GeneratorController:DisplayOutageHistory----------------------
    def DisplayOutageHistory(self, JSONNum=False):

        LogHistory = []

        if not len(self.OutageLog):
            return ""
        try:
            # check to see if a log file exist yet
            if not os.path.isfile(self.OutageLog):
                return ""

            OutageLog = []

            with open(self.OutageLog, "r") as OutageFile:  # opens file

                for line in OutageFile:
                    line = line.strip()  # remove whitespace at beginning and end

                    if not len(line):
                        continue
                    if line[0] == "#":  # comment?
                        continue
                    line = self.removeNonPrintable(line)
                    Items = line.split(",")
                    # Three items is for duration greater than 24 hours, i.e 1 day, 08:12
                    if len(Items) < 2:
                        continue
                    strDuration = ""
                    strFuel = ""
                    if len(Items) == 2:
                        # Only date and duration less than a day
                        strDuration = Items[1]
                    elif (len(Items) == 3) and ("day" in Items[1]):
                        #  date and outage greater than 24 hours
                        strDuration = Items[1] + "," + Items[2]
                    elif len(Items) == 3:
                        # date, outage less than 1 day, and fuel
                        strDuration = Items[1]
                        strFuel = Items[2]
                    elif len(Items) == 4 and ("day" in Items[1]):
                        # date, outage less greater than 1 day, and fuel
                        strDuration = Items[1] + "," + Items[2]
                        strFuel = Items[3]
                    else:
                        continue

                    if len(strDuration) and len(strFuel):
                         OutageLog.insert(0, [Items[0], strDuration, strFuel])
                    elif len(strDuration):
                        OutageLog.insert(0, [Items[0], strDuration])

                    if len(OutageLog) > 100:  # limit log to 100 entries
                        OutageLog.pop()

            index = 0
            for Items in OutageLog:
                if len(Items) > 1:
                    try:
                        # should be format yyyy-mm-dd hh:mm:ss
                        EntryDate = datetime.datetime.strptime(Items[0], "%Y-%m-%d %H:%M:%S")
                        if self.bAlternateDateFormat:
                            FormattedDate = EntryDate.strftime("%d-%m-%Y %H:%M:%S")
                        else:
                            FormattedDate = EntryDate.strftime("%m-%d-%Y %H:%M:%S")
                    except Exception as e1:
                        self.LogErrorLine("Error parsing date/time in outage log: " + str(e1))
                        continue
                if len(Items) == 2:
                    if JSONNum:
                        LogHistory.append({index: [{"Date": FormattedDate}, {"Duration": Items[1]}]})
                    else:   
                        LogHistory.append("%s, Duration: %s" % (FormattedDate, Items[1]))
                elif len(Items) == 3:
                    if JSONNum:
                        LogHistory.append({index:[{"Date": FormattedDate}, {"Duration": Items[1]},{"Estimated Fuel": Items[2]}]})
                    else:
                        LogHistory.append("%s, Duration: %s, Estimated Fuel: %s"% (FormattedDate, Items[1], Items[2]))
                index += 1

            return LogHistory

        except Exception as e1:
            self.LogErrorLine("Error in  DisplayOutageHistory: " + str(e1))
            return []

    # ------------ GeneratorController::LogToPowerLog----------------------------
    def LogToPowerLog(self, TimeStamp, Value):

        try:
            TimeStamp = self.removeNonPrintable(TimeStamp)
            Value = self.removeNonPrintable(Value)
            if not len(TimeStamp) or not len(Value):
                self.LogError(
                    "Invalid entry in LogToPowerLog: "
                    + str(TimeStamp)
                    + ","
                    + str(Value)
                )
                return
            if len(self.PowerLogList):
                self.PowerLogList.insert(0, [TimeStamp, Value])
            self.LogToFile(self.PowerLog, TimeStamp, Value)
        except Exception as e1:
            self.LogErrorLine("Error in LogToPowerLog: " + str(e1))

    # ------------ GeneratorController::GetPowerLogFileDetails-------------------
    def GetPowerLogFileDetails(self):

        if not self.PowerMeterIsSupported():
            return "Not Supported"
        try:
            LogSize = os.path.getsize(self.PowerLog)
            outstr = "%.2f MB of %.2f MB" % (
                (float(LogSize) / (1024.0 * 1024.0)),
                self.PowerLogMaxSize,
            )
            return outstr
        except Exception as e1:
            self.LogErrorLine("Error in GetPowerLogFileDetails : " + str(e1))
            return "Unknown"

    # ------------ GeneratorController::PrunePowerLog----------------------------
    def PrunePowerLog(self, Minutes):

        if not Minutes:
            self.LogError("Clearing power log")
            return self.ClearPowerLog()

        try:

            LogSize = os.path.getsize(self.PowerLog)
            if float(LogSize) / (1024 * 1024) < self.PowerLogMaxSize * 0.85:
                return "OK"

            if float(LogSize) / (1024 * 1024) >= self.PowerLogMaxSize * 0.98:
                msgbody = "The genmon kwlog (power log) file size is 98 percent of the maximum. Once "
                msgbody += "the log reaches 100 percent of the log will be reset. This will result "
                msgbody += "inaccurate fuel estimation (if you are using this feature). You can  "
                msgbody += "either increase the size of the kwlog on the advanced settings page,"
                msgbody += "or reset your power log."
                self.MessagePipe.SendMessage(
                    "Notice: Power Log file size warning",
                    msgbody,
                    msgtype="warn",
                    onlyonce=True,
                )

            # is the file size too big?
            if float(LogSize) / (1024 * 1024) >= self.PowerLogMaxSize:
                self.ClearPowerLog()
                self.LogError("Power Log entries deleted due to size reaching maximum.")
                return "OK"

            # if we get here the power log is 85% full or greater so let's try to reduce the size by
            # deleting entires that are older than the input Minutes
            CmdString = "power_log_json=%d" % Minutes
            PowerLog = self.GetPowerHistory(CmdString, NoReduce=True)

            self.ClearPowerLog(NoCreate=True)
            # Write oldest log entries first
            for Items in reversed(PowerLog):
                self.LogToPowerLog(Items[0], Items[1])

            # Add null entry at the end
            if not os.path.isfile(self.PowerLog):
                TimeStamp = datetime.datetime.now().strftime("%x %X")
                self.LogToPowerLog(TimeStamp, "0.0")

            # if the power log is now empty add one entry
            LogSize = os.path.getsize(self.PowerLog)
            if LogSize == 0:
                TimeStamp = datetime.datetime.now().strftime("%x %X")
                self.LogToPowerLog(TimeStamp, "0.0")

            return "OK"

        except Exception as e1:
            self.LogErrorLine("Error in  PrunePowerLog: " + str(e1))
            return "Error in  PrunePowerLog: " + str(e1)

    # ------------ GeneratorController::ClearPowerLog----------------------------
    def ClearPowerLog(self, NoCreate=False):

        try:
            if not len(self.PowerLog):
                return "Power Log Disabled"

            if not os.path.isfile(self.PowerLog):
                return "Power Log is empty"
            try:
                with self.PowerLock:
                    os.remove(self.PowerLog)
                    time.sleep(1)
            except:
                pass

            self.PowerLogList = []

            if not NoCreate:
                # add zero entry to note the start of the log
                TimeStamp = datetime.datetime.now().strftime("%x %X")
                self.LogToPowerLog(TimeStamp, "0.0")

            return "Power Log cleared"
        except Exception as e1:
            self.LogErrorLine("Error in  ClearPowerLog: " + str(e1))
            return "Error in  ClearPowerLog: " + str(e1)

    # ------------ GeneratorController::ReducePowerSamples-----------------------
    def ReducePowerSamples(self, PowerList, MaxSize):


        if MaxSize == 0:
            self.LogError("RecducePowerSamples: Error: Max size is zero")
            return []

        if len(PowerList) < MaxSize:
            self.LogError("RecducePowerSamples: Error: Can't reduce ")
            return PowerList

        try:
            # reduce to only the last 31 days
            NewList = self.GetPowerLogForMinutes(60 * 24 * 31, InputList=PowerList)
            
            # if we have too many entries due to a remainder or not removing zero samples, then delete some
            if len(NewList) > MaxSize:
                return self.RemovePowerSamples(NewList, MaxSize)
        except Exception as e1:
            self.LogErrorLine("Error in RecducePowerSamples: %s" % str(e1))
            return PowerList

        return NewList

    # ------------ GeneratorController::RemovePowerSamples-----------------------
    def RemovePowerSamples(self, List, MaxSize):

        try:
            NewList = List[:]
            if len(NewList) <= MaxSize:
                self.LogError("RemovePowerSamples: Error: Can't remove ")
                return NewList

            # This will just remove all samples but the first MaxSize. This will only do anything if the above
            # code failes to find valid samples to remove (i.e. all samples are zero)
            if len(NewList) > MaxSize:
                NewList = NewList[:MaxSize]
            return NewList
        except Exception as e1:
            self.LogErrorLine("Error in RemovePowerSamples: %s" % str(e1))
            return NewList

    # ------------ GeneratorController::GetPowerLogForMinutes--------------------
    def GetPowerLogForMinutes(self, Minutes=0, InputList = None):
        try:
            ReturnList = []
            if InputList == None:
                PowerList = self.ReadPowerLogFromFile()
            else:
                PowerList = InputList
            if not Minutes:
                return PowerList
            CurrentTime = datetime.datetime.now()

            for Time, Power in reversed(PowerList):
                try:
                    struct_time = time.strptime(Time, "%x %X")
                    LogEntryTime = datetime.datetime.fromtimestamp(time.mktime(struct_time))
                except Exception as e1:
                    self.LogErrorLine("Error in GetPowerLogForMinutes: " + str(e1))
                    continue
                Delta = CurrentTime - LogEntryTime
                if self.GetDeltaTimeMinutes(Delta) < Minutes:
                    ReturnList.insert(0, [Time, Power])
            return ReturnList
        except Exception as e1:
            self.LogErrorLine("Error in GetPowerLogForMinutes: " + str(e1))
            return ReturnList

    # ------------ GeneratorController::ReadPowerLogFromFile---------------------
    def ReadPowerLogFromFile(self, Minutes=0, NoReduce=False):

        # check to see if a log file exist yet
        if not os.path.isfile(self.PowerLog):
            return []
        PowerList = []

        # return cached list if we have read the file before
        if len(self.PowerLogList) and not Minutes:
            return self.PowerLogList
        with self.PowerLock:
            if Minutes:
                return self.GetPowerLogForMinutes(Minutes)

            try:
                with open(self.PowerLog, "r") as LogFile:  # opens file
                    for line in LogFile:
                        line = line.strip()  # remove whitespace at beginning and end

                        if not len(line):
                            continue
                        if line[0] == "#":  # comment
                            continue
                        line = self.removeNonPrintable(line)
                        Items = line.split(",")
                        if len(Items) != 2:
                            continue
                        # remove any kW labels that may be there
                        Items[1] = self.removeAlpha(Items[1])
                        PowerList.insert(0, [Items[0], Items[1]])

            except Exception as e1:
                self.LogErrorLine(
                    "Error in  ReadPowerLogFromFile (parse file): " + str(e1)
                )

            if len(PowerList) > self.MaxPowerLogEntries and not NoReduce:
                PowerList = self.ReducePowerSamples(PowerList, self.MaxPowerLogEntries)
            if not len(self.PowerLogList):
                self.PowerLogList = PowerList
        return PowerList

    # ------------ GeneratorController::GetPowerHistory--------------------------
    def GetPowerHistory(self, CmdString, NoReduce=False):

        KWHours = False
        FuelConsumption = False
        RunHours = False
        msgbody = "Invalid command syntax for command power_log_json"

        try:
            if not len(self.PowerLog):
                # power log disabled
                return []

            if not len(CmdString):
                self.LogError("Error in GetPowerHistory: Invalid input")
                return []

            # Format we are looking for is "power_log_json=5" or "power_log_json" or "power_log_json=1000,kw"
            CmdList = CmdString.split("=")

            if len(CmdList) > 2:
                self.LogError(
                    "Validation Error: Error parsing command string in GetPowerHistory (parse): "
                    + CmdString
                )
                return msgbody

            CmdList[0] = CmdList[0].strip()

            if not CmdList[0].lower() == "power_log_json":
                self.LogError(
                    "Validation Error: Error parsing command string in GetPowerHistory (parse2): "
                    + CmdString
                )
                return msgbody

            if len(CmdList) == 2:
                ParseList = CmdList[1].split(",")
                if len(ParseList) == 1:
                    Minutes = int(CmdList[1].strip())
                elif len(ParseList) == 2:
                    Minutes = int(ParseList[0].strip())
                    if ParseList[1].strip().lower() == "kw":
                        KWHours = True
                    elif ParseList[1].strip().lower() == "fuel":
                        FuelConsumption = True
                    elif ParseList[1].strip().lower() == "time":
                        RunHours = True
                else:
                    self.LogError(
                        "Validation Error: Error parsing command string in GetPowerHistory (parse3): "
                        + CmdString
                    )
                    return msgbody

            else:
                Minutes = 0
        except Exception as e1:
            self.LogErrorLine(
                "Error in  GetPowerHistory (Parse): %s : %s" % (CmdString, str(e1))
            )
            return msgbody

        try:

            PowerList = self.ReadPowerLogFromFile(Minutes=Minutes)

            # Shorten list to self.MaxPowerLogEntries if specific duration requested
            # if not KWHours and len(PowerList) > self.MaxPowerLogEntries and Minutes and not NoReduce:
            if len(PowerList) > self.MaxPowerLogEntries and Minutes and not NoReduce:
                PowerList = self.ReducePowerSamples(PowerList, self.MaxPowerLogEntries)
            if KWHours:
                AvgPower, TotalSeconds = self.GetAveragePower(PowerList)
                return "%.2f" % ((TotalSeconds / 3600) * AvgPower)
            if FuelConsumption:
                AvgPower, TotalSeconds = self.GetAveragePower(PowerList)
                Consumption, Label = self.GetFuelConsumption(AvgPower, TotalSeconds)
                if Consumption == None:
                    return "Unknown"
                if Consumption < 0:
                    self.LogDebug("WARNING: Fuel Consumption is less than zero in GetPowerHistory: %d" % Consumption)
                return "%.2f %s" % (Consumption, Label)
            if RunHours:
                AvgPower, TotalSeconds = self.GetAveragePower(PowerList)
                return "%.2f" % (TotalSeconds / 60.0 / 60.0)

            return PowerList

        except Exception as e1:
            self.LogErrorLine("Error in  GetPowerHistory: " + str(e1))
            msgbody = "Error in  GetPowerHistory: " + str(e1)
            return msgbody

    # ----------  GeneratorController::GetAveragePower---------------------------
    # a list of the power log is passed in (already parsed for a time period)
    # returns a time period and average power used for that time period
    def GetAveragePower(self, PowerList):

        try:
            TotalTime = datetime.timedelta(seconds=0)
            Entries = 0
            TotalPower = 0.0
            LastPower = 0.0
            LastTime = None
            for Items in PowerList:
                try:
                    # is the power value a float?
                    Power = float(Items[1])
                except Exception as e1:
                    Power = 0.0
                    continue
                try:
                    # This should be date time
                    struct_time = time.strptime(Items[0], "%x %X")
                    LogEntryTime = datetime.datetime.fromtimestamp(
                        time.mktime(struct_time)
                    )
                except Exception as e1:
                    self.LogErrorLine("Invalid time entry in power log: " + str(e1))
                    continue

                # Changes in Daylight savings time will effect this
                if LastTime == None or Power == 0:
                    TotalTime += LogEntryTime - LogEntryTime
                else:
                    TotalTime += LastTime - LogEntryTime
                    TotalPower += (Power + LastPower) / 2
                    Entries += 1
                LastTime = LogEntryTime
                LastPower = Power

            if Entries == 0:
                return 0, 0
            TotalPower = TotalPower / Entries
            return TotalPower, TotalTime.total_seconds()
        except Exception as e1:
            self.LogErrorLine("Error in  GetAveragePower: " + str(e1))
            return 0, 0

    # ----------  GeneratorController::PowerMeter--------------------------------
    # ----------  Monitors Power Output
    def PowerMeter(self):

        # make sure system is up and running otherwise we will not know which controller is present
        time.sleep(1)
        while True:

            if self.InitComplete:
                break
            if self.WaitForExit("PowerMeter", 1):
                return

        # if power meter is not supported do nothing.
        # Note: This is done since if we killed the thread here
        while not self.PowerMeterIsSupported() or not len(self.PowerLog):
            if self.WaitForExit("PowerMeter", 60):
                return

        # if log file is empty or does not exist, make a zero entry in log to denote start of collection
        if not os.path.isfile(self.PowerLog) or os.path.getsize(self.PowerLog) == 0:
            TimeStamp = datetime.datetime.now().strftime("%x %X")
            self.LogError("Creating Power Log: " + self.PowerLog)
            self.LogToPowerLog(TimeStamp, "0.0")

        LastValue = 0.0
        LastPruneTime = datetime.datetime.now()
        LastFuelCheckTime = datetime.datetime.now()
        while True:
            try:
                if self.WaitForExit("PowerMeter", 10):
                    return

                # Housekeeping on kw Log
                if LastValue == 0:
                    if (
                        self.GetDeltaTimeMinutes(
                            datetime.datetime.now() - LastPruneTime
                        )
                        > 1440
                    ):  # check every day
                        self.PrunePowerLog(
                            60 * 24 * 30 * 36
                        )  # delete log entries greater than three years
                        LastPruneTime = datetime.datetime.now()

                if (
                    self.GetDeltaTimeMinutes(
                        datetime.datetime.now() - LastFuelCheckTime
                    )
                    > 10
                ):  # check 10 min
                    LastFuelCheckTime = datetime.datetime.now()
                    self.CheckFuelLevel()

                # Time to exit?
                if self.IsStopSignaled("PowerMeter"):
                    return
                KWFloat = self.GetPowerOutput(ReturnFloat=True)

                if LastValue == KWFloat:
                    continue

                if LastValue == 0:
                    StartTime = datetime.datetime.now() - datetime.timedelta(seconds=1)
                    TimeStamp = StartTime.strftime("%x %X")
                    self.LogToPowerLog(TimeStamp, str(LastValue))

                LastValue = KWFloat
                # Log to file
                TimeStamp = datetime.datetime.now().strftime("%x %X")
                self.LogToPowerLog(TimeStamp, str(KWFloat))

            except Exception as e1:
                self.LogErrorLine("Error in PowerMeter: " + str(e1))

    # ----------  GeneratorController::SetupCommonTiles--------------------------
    def SetupCommonTiles(self):

        try:

            if self.FuelSensorSupported():
                Tile = MyTile(
                    self.log,
                    title="Fuel",
                    units="%",
                    type="fuel",
                    nominal=100,
                    callback=self.GetFuelSensor,
                    callbackparameters=(True,),
                )
                self.TileList.append(Tile)
            elif self.ExternalFuelDataSupported():
                NumTanks = self.GetNumberExternalTanks()
                if NumTanks >= 2:
                    ExternalTankTitle = "External Tank 1"
                else:  # only one tank
                    ExternalTankTitle = "External Tank"
                Tile = MyTile(
                    self.log,
                    title=ExternalTankTitle,
                    units="%",
                    type="fuel",
                    nominal=100,
                    callback=self.GetExternalFuelPercentage,
                    callbackparameters=(True, 1),
                )
                self.TileList.append(Tile)
                if NumTanks >= 2:
                    ExternalTankTitle = "External Tank 2"
                    Tile = MyTile(
                        self.log,
                        title=ExternalTankTitle,
                        units="%",
                        type="fuel",
                        nominal=100,
                        callback=self.GetExternalFuelPercentage,
                        callbackparameters=(True, 2),
                    )
                    self.TileList.append(Tile)
                if NumTanks >= 3:
                    ExternalTankTitle = "External Tank 3"
                    Tile = MyTile(
                        self.log,
                        title=ExternalTankTitle,
                        units="%",
                        type="fuel",
                        nominal=100,
                        callback=self.GetExternalFuelPercentage,
                        callbackparameters=(True, 3),
                    )
                    self.TileList.append(Tile)
                if NumTanks >= 4:
                    ExternalTankTitle = "External Tank 4"
                    Tile = MyTile(
                        self.log,
                        title=ExternalTankTitle,
                        units="%",
                        type="fuel",
                        nominal=100,
                        callback=self.GetExternalFuelPercentage,
                        callbackparameters=(True, 4),
                    )
                    self.TileList.append(Tile)
            elif self.FuelConsumptionGaugeSupported():  # no gauge for NG
                if self.UseMetric:
                    Units = "L"  # no gauge for NG
                else:
                    Units = "gal"  # no gauge for NG
                Tile = MyTile(
                    self.log,
                    title="Estimated Fuel",
                    units=Units,
                    type="fuel",
                    nominal=int(self.TankSize),
                    callback=self.GetEstimatedFuelInTank,
                    callbackparameters=(True,),
                )
                self.TileList.append(Tile)

            if self.UseExternalCTData:
                NominalCurrent = float(self.NominalKW) * 1000 / self.NominalLineVolts
                if int(self.Phase) == 1:
                    NominalLegCurrent = ((float(self.NominalKW) * 1000) / 2 ) / (self.NominalLineVolts / 2)
                else:
                    # TODO: validate with 3 phase, also show three gauges?
                    NominalLegCurrent = float(self.NominalKW) * 1000 / self.NominalLineVolts

                ReturnCurrent1 = self.CheckExternalCTData(request="ct1", ReturnFloat=True, gauge=True)
                ReturnCurrent2 = self.CheckExternalCTData(request="ct2", ReturnFloat=True, gauge=True)
                if ReturnCurrent1 != None and ReturnCurrent2 != None:
                    Tile = MyTile(
                        self.log,
                        title="Current L1",
                        units="A",
                        type="current",
                        nominal=int(NominalLegCurrent),
                        callback=self.CheckExternalCTData,
                        callbackparameters=("ct1", True, True),
                    )
                    self.TileList.append(Tile)

                    Tile = MyTile(
                        self.log,
                        title="Current L2",
                        units="A",
                        type="current",
                        nominal=int(NominalLegCurrent),
                        callback=self.CheckExternalCTData,
                        callbackparameters=("ct2", True, True),
                    )
                    self.TileList.append(Tile)
                else:
                    Tile = MyTile(
                        self.log,
                        title="External Current",
                        units="A",
                        type="current",
                        nominal=int(NominalCurrent),
                        callback=self.CheckExternalCTData,
                        callbackparameters=("current", True, True),
                    )
                    self.TileList.append(Tile)
                NominalPower = float(self.NominalKW)
                Tile = MyTile(
                    self.log,
                    title="External Power",
                    units="kW",
                    type="power",
                    nominal=int(NominalPower),
                    callback=self.CheckExternalCTData,
                    callbackparameters=("power", True, True),
                )
                self.TileList.append(Tile)

            # Raspberry pi CPU temp
            if self.bUseRaspberryPiCpuTempGauge and self.Platform != None:
                nominal = 80
                maximum = 90
                if self.UseMetric:
                    units = "C"
                else:
                    units = "F"
                    nominal = self.ConvertCelsiusToFahrenheit(nominal)
                    maximum = self.ConvertCelsiusToFahrenheit(maximum)
                Tile = MyTile(
                    self.log,
                    title="CPU Temp",
                    units=units,
                    type="temperature",
                    subtype="cpu",
                    nominal=nominal,
                    maximum=maximum,
                    callback=self.Platform.GetRaspberryPiTemp,
                    callbackparameters=(True,),
                )
                self.TileList.append(Tile)

            # external Temp data from gentemp add on
            if self.UseExternalSensorData and self.ExternalSensorGagueData != None:
                # setup each temp gauge
                try:
                    self.LogDebug("Setting up gauges for external sensors")
                    index = 0
                    for SensorBounds in self.ExternalSensorGagueData:
                        sensor_max = SensorBounds['max']
                        sensor_min = SensorBounds['min']
                        sensor_nominal = SensorBounds['nominal']
                        sensor_name = SensorBounds['title'].strip()
                        sensor_units = SensorBounds['units']
                        sensor_type = SensorBounds['type']
                        if sensor_name != None and sensor_max != None and sensor_nominal != None:
                            if not SensorBounds['exclude_gauge']:
                                Tile = MyTile(self.log,title=sensor_name, units=sensor_units,type=sensor_type, subtype = "external",
                                    nominal=sensor_nominal, minimum = sensor_min, maximum=sensor_max, callback=self.GetExternalSensorData, callbackparameters=(sensor_name,),)
                                self.TileList.append(Tile)
                        index += 1

                except Exception as e1:
                    self.LogErrorLine("Error in SetupCommonTiles: sensor_bounds: " + str(e1))
                
            # wifi signal strength
            if self.bUseLinuxWifiSignalGauge and self.Platform != None:
                signal = self.Platform.GetWiFiSignalStrength()
                if signal != 0:
                    Tile = MyTile(
                        self.log,
                        title="WiFi Signal",
                        units="dBm",
                        type="wifi",
                        callback=self.Platform.GetWiFiSignalStrength,
                        callbackparameters=(True,),
                    )
                    self.TileList.append(Tile)

            powergraphdefined = False
            for tile in self.TileList:
                if tile.Type == "powergraph":
                    powergraphdefined = True

            if not powergraphdefined and self.UseExternalCTData:
                # setup power graph
                self.LogDebug("Setting up power graph for external CT data")
                NominalPower = float(self.NominalKW)
                Tile = MyTile(
                    self.log,
                    title="kW Output",
                    type="powergraph",
                    nominal=int(NominalPower),
                    callback=self.CheckExternalCTData,
                    callbackparameters=("power", True, True),
                )
                self.TileList.append(Tile)

        except Exception as e1:
            self.LogErrorLine("Error in SetupCommonTiles: " + str(e1))

    # ----------  GeneratorController::MaintenanceHouseKeepingThread------------
    def MaintenanceHouseKeepingThread(self):

        try:
            time.sleep(0.5)
            if self.WaitForExit("MaintenanceHouseKeepingThread", 10):  #
                return
            
            while True:
                try:

                    self.KWHoursMonth = self.GetPowerHistory(
                        "power_log_json=43200,kw"
                    )  # 43200 minutes in a month
                    self.FuelMonth = self.GetPowerHistory("power_log_json=43200,fuel")
                    self.FuelTotal = self.GetPowerHistory("power_log_json=0,fuel")
                    self.RunHoursMonth = self.GetPowerHistory(
                        "power_log_json=43200,time"
                    )
                    self.RunHoursYear = self.GetPowerHistory(
                        "power_log_json=525600,time"
                    )
                    # 525600 minutes in a year
                    if self.WaitForExit("MaintenanceHouseKeepingThread", 60):  #
                        return
                except Exception as e1:
                     self.LogErrorLine("Error in MaintenanceHouseKeepingThread: " + str(e1))
    
        except Exception as e1:
            self.LogErrorLine("Error in MaintenanceHouseKeepingThread (2): " + str(e1))

    # ----------  GeneratorController::DisplayMaintenanceCommon------------------
    def DisplayMaintenanceCommon(self, Maintenance, JSONNum=False):

        try:
            if self.UseMetric:
                Units = "L"
            else:
                Units = "gal"

            if self.FuelSensorSupported():
                FuelValue = self.GetFuelSensor(ReturnInt=True)
                Maintenance["Maintenance"].append(
                    {"Fuel Level Sensor": self.ValueOut(FuelValue, "%", JSONNum)}
                )
                FuelValue = self.GetFuelInTank(ReturnFloat=True)
                if FuelValue != None:
                    Maintenance["Maintenance"].append(
                        {
                            "Fuel In Tank (Sensor)": self.ValueOut(
                                FuelValue, Units, JSONNum
                            )
                        }
                    )
            elif self.ExternalFuelDataSupported():
                NumTanks = self.GetNumberExternalTanks()
                if NumTanks >= 1:
                    FuelValue = self.GetExternalFuelPercentage(
                        ReturnFloat=True, TankNumber=1
                    )
                    Maintenance["Maintenance"].append(
                        {"Fuel Level Sensor": self.ValueOut(FuelValue, "%", JSONNum)}
                    )
                if NumTanks >= 2:
                    FuelValue = self.GetExternalFuelPercentage(
                        ReturnFloat=True, TankNumber=2
                    )
                    Maintenance["Maintenance"].append(
                        {
                            "Fuel Level Sensor Tank 2": self.ValueOut(
                                FuelValue, "%", JSONNum
                            )
                        }
                    )
                if NumTanks >= 3:
                    FuelValue = self.GetExternalFuelPercentage(
                        ReturnFloat=True, TankNumber=3
                    )
                    Maintenance["Maintenance"].append(
                        {
                            "Fuel Level Sensor Tank 3": self.ValueOut(
                                FuelValue, "%", JSONNum
                            )
                        }
                    )
                if NumTanks >= 4:
                    FuelValue = self.GetExternalFuelPercentage(
                        ReturnFloat=True, TankNumber=4
                    )
                    Maintenance["Maintenance"].append(
                        {
                            "Fuel Level Sensor Tank 4": self.ValueOut(
                                FuelValue, "%", JSONNum
                            )
                        }
                    )
                FuelValue = self.GetFuelInTank(ReturnFloat=True)
                if FuelValue != None:
                    Maintenance["Maintenance"].append(
                        {
                            "Fuel In Tank (Sensor)": self.ValueOut(
                                FuelValue, Units, JSONNum
                            )
                        }
                    )

            # Don't Show estimated fuel for propane tanks with a sensor on Evo controllers
            if self.FuelTankCalculationSupported() and not (
                self.FuelType == "Propane"
                and (self.ExternalFuelDataSupported() or self.FuelSensorSupported())
            ):
                Maintenance["Maintenance"].append(
                    {
                        "Estimated Fuel In Tank ": self.ValueOut(
                            self.GetEstimatedFuelInTank(ReturnFloat=True),
                            Units,
                            JSONNum,
                        )
                    }
                )

            # Show hours of fuel remaining if any calculation is supported
            if (
                self.FuelTankCalculationSupported()
                or self.ExternalFuelDataSupported()
                or self.FuelSensorSupported()
            ):
                DisplayText = (
                    "Hours of Fuel Remaining (Estimated %.02f Load )"
                    % self.EstimateLoad
                )
                RemainingFuelTimeFloat = self.GetRemainingFuelTime(ReturnFloat=True)
                if RemainingFuelTimeFloat != None:
                    Maintenance["Maintenance"].append(
                        {
                            DisplayText: self.ValueOut(
                                RemainingFuelTimeFloat, "h", JSONNum
                            )
                        }
                    )

                RemainingFuelTimeFloat = self.GetRemainingFuelTime(
                    ReturnFloat=True, Actual=True
                )
                if RemainingFuelTimeFloat != None:
                    Maintenance["Maintenance"].append(
                        {
                            "Hours of Fuel Remaining (Current Load)": self.ValueOut(
                                RemainingFuelTimeFloat, "h", JSONNum
                            )
                        }
                    )

            if self.PowerMeterIsSupported() and self.FuelConsumptionSupported():
                if self.KWHoursMonth != None:
                    Maintenance["Maintenance"].append(
                        {
                            "kW Hours in last 30 days": self.UnitsOut(
                                str(self.KWHoursMonth) + " kWh",
                                type=float,
                                NoString=JSONNum,
                            )
                        }
                    )
                if self.FuelMonth != None:
                    Maintenance["Maintenance"].append(
                        {
                            "Fuel Consumption in last 30 days": self.UnitsOut(
                                self.FuelMonth, type=float, NoString=JSONNum
                            )
                        }
                    )
                if self.FuelTotal != None:
                    Maintenance["Maintenance"].append(
                        {
                            "Total Power Log Fuel Consumption": self.UnitsOut(
                                self.FuelTotal, type=float, NoString=JSONNum
                            )
                        }
                    )
                if self.RunHoursMonth != None:
                    Maintenance["Maintenance"].append(
                        {
                            "Run Hours in last 30 days": self.UnitsOut(
                                str(self.RunHoursMonth) + " h",
                                type=float,
                                NoString=JSONNum,
                            )
                        }
                    )
                if self.RunHoursYear != None:
                    Maintenance["Maintenance"].append(
                        {
                            "Run Hours in the last year": self.UnitsOut(
                                str(self.RunHoursYear) + " h",
                                type=float,
                                NoString=JSONNum,
                            )
                        }
                    )

            if self.FuelLevelOK != None:
                if self.FuelLevelOK:
                    level = "OK"
                else:
                    level = "Low"
                Maintenance["Maintenance"].append({"Fuel Level State": level})

            return Maintenance

        except Exception as e1:
            self.LogErrorLine("Error in DisplayMaintenanceCommon: " + str(e1))
            return Maintenance

    # ----------  GeneratorController::DisplayStatusCommon-----------------------
    def DisplayStatusCommon(self, Status, JSONNum=False):

        try:
            
            with self.ExternalDataLock:
                try:
                    if self.ExternalSensorData != None:
                        if not JSONNum:
                            Status["Status"].append({"External Sensors":self.ExternalSensorData})
                        else:
                            # This will unpack the list of dicts and put them in the JSONNum format 
                            TempList = []
                            ExternalTempList = self.ExternalSensorData
                            if len(ExternalTempList):
                                Status["Status"].append({"External Sensors" : TempList})
                                for ExTempDict in ExternalTempList:
                                    try:
                                        TempDict = ExTempDict.copy()    # make a copy since we use popitmes below
                                        if len(TempDict):
                                            TempKey, TempData = TempDict.popitem()
                                            TempDataList = TempData.strip().split( " ")
                                            TempList.append({TempKey: self.ValueOut(float(TempDataList[0]), TempDataList[1], JSONNum)}) 
                                    except Exception as e1:
                                        self.LogErrorLine("Error in DisplayStatus (3): " + str(e1))
                except Exception as e1:
                    self.LogErrorLine("Error in DisplayStatusCommon(2): " + str(e1))
            
            ReturnCurrent = self.CheckExternalCTData(request="current", ReturnFloat=True, gauge=True)
            ReturnCurrent1 = self.CheckExternalCTData(request="ct1", ReturnFloat=True, gauge=True)
            ReturnCurrent2 = self.CheckExternalCTData(request="ct2", ReturnFloat=True, gauge=True)
            ReturnPower = self.CheckExternalCTData(request="power", ReturnFloat=True, gauge=True)
            ReturnPower1 = self.CheckExternalCTData(request="ctpower1", ReturnFloat=True, gauge=True)
            ReturnPower2 = self.CheckExternalCTData(request="ctpower2", ReturnFloat=True, gauge=True)
            
            if ReturnCurrent != None and ReturnPower != None:
                ExternalSensors = []
                Status["Status"].append({"External Line Sensors": ExternalSensors})

                if ReturnCurrent != None:
                    ExternalSensors.append(
                        {"Total Current": self.ValueOut(ReturnCurrent, "A", JSONNum)}
                    )
                if ReturnCurrent1 != None:
                    ExternalSensors.append(
                        {"Current Leg 1": self.ValueOut(ReturnCurrent1, "A", JSONNum)}
                    )
                if ReturnCurrent2 != None:
                    ExternalSensors.append(
                        {"Current Leg 2": self.ValueOut(ReturnCurrent2, "A", JSONNum)}
                    )
                if ReturnPower != None:
                    ExternalSensors.append(
                        {"Power": self.ValueOut(ReturnPower, "kW", JSONNum)}
                    )
                if ReturnPower1 != None:
                    ExternalSensors.append(
                        {"Power Leg 1": self.ValueOut(ReturnPower1, "kW", JSONNum)}
                    )
                if ReturnPower2 != None:
                    ExternalSensors.append(
                        {"Power Leg 2": self.ValueOut(ReturnPower2, "kW", JSONNum)}
                    )
            return Status
        except Exception as e1:
            self.LogErrorLine("Error in DisplayStatusCommon: " + str(e1))
            return Status

    # ----------  GeneratorController::GetFuelInTank-----------------------------
    def GetFuelInTank(self, ReturnFloat=False):

        try:
            if self.TankSize == 0:
                return None

            if self.UseMetric:
                Units = "L"
            else:
                Units = "gal"

            FuelLevel = self.GetFuelLevel(ReturnFloat=True)
            if FuelLevel == None:
                return None
            FuelLevel = (FuelLevel * 0.01) * float(self.TankSize)

            if ReturnFloat:
                return float(FuelLevel)
            else:
                return "%.2f %s" % (FuelLevel, Units)
        except Exception as e1:
            self.LogErrorLine("Error in GetFuelInTank: " + str(e1))
            return None

    # ----------  GeneratorController::GetFuelLevel------------------------------
    def GetFuelLevel(self, ReturnFloat=False):
        # return 0 - 100 or None

        if (
            not self.ExternalFuelDataSupported()
            and not self.FuelTankCalculationSupported()
            and not self.FuelSensorSupported()
        ):
            return None

        if self.FuelSensorSupported():
            FuelLevel = self.GetFuelSensor(ReturnInt=True)
            if FuelLevel == None:
                return None
            FuelLevel = float(FuelLevel)
        elif self.ExternalFuelDataSupported():
            FuelLevel = self.GetExternalFuelPercentage(ReturnFloat=True)
        elif self.FuelTankCalculationSupported():
            if self.TankSize == 0:
                return None
            FuelInTank = self.GetEstimatedFuelInTank(ReturnFloat=True)

            if FuelInTank >= self.TankSize:
                FuelLevel = 100
            else:
                FuelLevel = float(FuelInTank) / float(self.TankSize) * 100
        else:
            FuelLevel = 0
        if FuelLevel == None:
            return FuelLevel
        if ReturnFloat:
            return float(FuelLevel)
        else:
            return "%.2f %%" % FuelLevel

    # ----------  GeneratorController::CheckFuelLevel----------------------------
    def CheckFuelLevel(self):
        try:
            if (
                not self.ExternalFuelDataSupported()
                and not self.FuelTankCalculationSupported()
                and not self.FuelSensorSupported()
            ):
                return True

            FuelLevel = self.GetFuelLevel(ReturnFloat=True)

            if FuelLevel == None:
                return True

            if FuelLevel <= 10:  # Ten percent left
                msgbody = (
                    "Warning: The estimated fuel in the tank is at or below 10%. Fuel Level is "
                    + str(FuelLevel)
                    + "%"
                )
                title = "Warning: Fuel Level Low (10%) at " + self.SiteName
                self.MessagePipe.SendMessage(
                    title, msgbody, msgtype="warn", onlyonce=True
                )
                self.FuelLevelOK = False
                return False
            elif FuelLevel <= 20:  # 20 percent left
                msgbody = (
                    "Warning: The estimated fuel in the tank is at or below 20%. Fuel Level is "
                    + str(FuelLevel)
                    + "%"
                )
                title = "Warning: Fuel Level Low (20%) at " + self.SiteName
                self.MessagePipe.SendMessage(
                    title, msgbody, msgtype="warn", onlyonce=True
                )
                self.FuelLevelOK = False
                return False
            else:
                self.FuelLevelOK = True
                return True

        except Exception as e1:
            self.LogErrorLine("Error in CheckFuelLevel: " + str(e1))
            return True

    # ----------  GeneratorController::GetEstimatedFuelInTank--------------------
    def GetEstimatedFuelInTank(self, ReturnFloat=False):

        if ReturnFloat:
            DefaultReturn = 0.0
        else:
            DefaultReturn = "0"

        if not self.FuelConsumptionGaugeSupported():
            return DefaultReturn
        if not self.FuelTankCalculationSupported():
            return DefaultReturn

        if self.TankSize == 0:
            return DefaultReturn
        try:
            FuelUsed = self.GetPowerHistory("power_log_json=0,fuel")
            if FuelUsed == "Unknown" or not len(FuelUsed):
                return DefaultReturn
            FuelUsed = self.removeAlpha(FuelUsed)
            FuelLeft = float(self.TankSize) - float(FuelUsed)
            FuelLeft = float(FuelLeft) - float(self.SubtractFuel)

            if FuelLeft < 0:
                FuelLeft = 0.0
            if self.UseMetric:
                Units = "L"
            else:
                Units = "gal"
            if ReturnFloat:
                return FuelLeft
            return "%.2f %s" % (FuelLeft, Units)
        except Exception as e1:
            self.LogErrorLine("Error in GetEstimatedFuelInTank: " + str(e1))
            return DefaultReturn

    # ------------ Evolution:GetFuelSensor --------------------------------------
    def GetFuelSensor(self, ReturnInt=False):
        return None

    # ----------  GeneratorController::FuelSensorSupported------------------------
    def FuelSensorSupported(self):
        return False

    # ----------  GeneratorController::FuelTankCalculationSupported--------------
    def FuelTankCalculationSupported(self):

        if not self.PowerMeterIsSupported():
            return False
        if not self.FuelConsumptionSupported():
            return False

        if self.TankSize == 0:
            return False

        if self.FuelType == "Natural Gas":
            return False
        return True

    # ----------  GeneratorController::FuelConsumptionSupported------------------
    def FuelConsumptionSupported(self):

        if self.GetFuelConsumptionDataPoints() == None:
            return False
        else:
            return True

    # ----------  GeneratorController::FuelConsumptionGaugeSupported-------------
    def FuelConsumptionGaugeSupported(self):

        if self.FuelTankCalculationSupported() and self.FuelType != "Natural Gas":
            return True
        return False

    # ----------  GeneratorController::GetRemainingFuelTime------------------------
    def GetRemainingFuelTime(self, ReturnFloat=False, Actual=False):

        try:
            if not self.FuelConsumptionGaugeSupported():
                return None
            if (
                not self.ExternalFuelDataSupported()
                and not self.FuelTankCalculationSupported()
                and not self.FuelSensorSupported()
            ):
                return None
            if self.TankSize == 0:
                return None

            FuelLevel = self.GetFuelLevel(ReturnFloat=True)
            FuelRemaining = self.TankSize * (FuelLevel / 100.0)

            if Actual:
                PowerValue = self.GetPowerOutput(ReturnFloat=True)
            else:
                PowerValue = self.EstimateLoad * float(self.NominalKW)

            if PowerValue == 0:
                return None

            FuelPerHour, Units = self.GetFuelConsumption(PowerValue, 60 * 60)
            if FuelPerHour == None or not len(Units):
                return None
            if FuelPerHour == 0:
                return None

            try:
                # make sure our units are correct
                # 1 cubic foot propane = 0.0278 gallons propane
                # 1 gallon propane = 35.97 cubic feet propane
                # 1 cubic foot natural gas = 0.012 gallons natural gas
                # 1 gallon natural gas = 82.62 cubic feet natural gas
                if Units.lower() == "cubic feet" and self.UseMetric == False:
                    # this means that fuel left is gallons and fuel per hour is cubic feet
                    # so convert remaining fuel from gallons to cu ft
                    if self.FuelType == "Natural Gas":
                        # 1 gallon natural gas = 82.62 cubic feet natural gas
                        FuelRemaining = FuelRemaining * 82.62
                    else:
                        # 1 gallon propane = 35.97 cubic feet propane
                        FuelRemaining = FuelRemaining * 35.97
                elif Units.lower() == "gal" and self.UseMetric == True:
                    # this mean that fuel left is Liters, and fuel per hour is gallons
                    # so convert remaining fuel to gallons
                    # 1 L =  0.264172 gal
                    FuelRemaining = FuelRemaining * 0.264172
                elif Units.lower() == "cubic feet" and self.UseMetric == True:
                    # this means that fuel left is Liters and fuel per hour is cu feet
                    # so convert remaing fuel to cubic feet
                    # 1 L = 0.0353147 cu ft
                    FuelRemaining = FuelRemaining * 0.0353147
            except Exception as e1:
                self.LogErrorLine("Error in GetRemainingFuelTime (2): " + str(e1))

            HoursRemaining = FuelRemaining / FuelPerHour

            if ReturnFloat:
                return float(HoursRemaining)
            else:
                return "%.2f h" % HoursRemaining
        except Exception as e1:
            self.LogErrorLine("Error in GetRemainingFuelTime: " + str(e1))
            return None

    # ----------  GeneratorController::GetFuelConsumption------------------------
    def GetFuelConsumption(self, kw, seconds):
        try:
            ConsumptionData = self.GetFuelConsumptionDataPoints()

            if ConsumptionData == None or len(ConsumptionData) != 5:
                return None, ""

            if self.NominalKW == None or float(self.NominalKW) == 0.0:
                return None, ""

            if kw < 0:
                self.LogDebug("WARNING: Load is %d in GetFuelConsumption" % kw)
                kw = 0
            if seconds < 0:
                self.LogDebug("WARNING: seconds is %d in GetFuelConsumption" % seconds)
                seconds = 0

            Load = kw / float(self.NominalKW)
            # X axis is percent utilization, y axis is fuel consumption
            X1 = ConsumptionData[0]
            Y1 = ConsumptionData[1]
            X2 = ConsumptionData[2]
            Y2 = ConsumptionData[3]
            Units = ConsumptionData[4]

            if seconds == 0:
                # for zero duration return zero fuel used
                if self.UseMetric and self.FuelType == "Natural Gas":
                    return 0.0, "cubic meters"
                elif self.UseMetric:
                    return 0.0, "L"
                else:
                    0.0, Units
            # Slope of fuel consumption plot (it is very close to if not linear in most cases)
            Slope = (Y2 - Y1) / (X2 - X1)  
            # now use point slope equation to find consumption for one hour
            # percent load is X2, Consumption is Y2, 100% (1.0) is X1 and Rate 100% is Y1
            # Y1-Y2= SLOPE(X1-X2)
            X2 = Load
            Y2 = (((Slope * X1) - (Slope * X2)) - Y1) * -1
            Consumption = Y2

            # now compensate for time
            Consumption = (seconds / 3600) * Consumption

            if Consumption < 0:
                self.LogDebug("WARNING: Fuel Consumption is " + str(Consumption)  + " " + Units)
                Consumption = 0

            if self.UseMetric:
                if self.FuelType == "Natural Gas":
                    Consumption = Consumption * 0.0283168  # cubic feet to cubic meters
                    return round(Consumption, 4), "cubic meters"  # convert to Liters
                else:
                    Consumption = Consumption * 3.78541  # gal to liters
                    return round(Consumption, 4), "L"  # convert to Liters
            else:
                return round(Consumption, 4), Units
        except Exception as e1:
            self.LogErrorLine("Error in GetFuelConsumption: " + str(e1))
            return None, ""

    # ----------  GeneratorController::GetFuelConsumptionDataPoints--------------
    def GetFuelConsumptionDataPoints(self):

        # Data points are expressed in a list [.50,50% fuel rate,1.0, 100% fuel rate, units]

        # The general rule of thumb for fuel consumption for diesel is 7% of the
        # rated generator output (Example: 200 kW x 7% = 1.4 gallon per hour at full load).
        # For Larger diesel generators KW * 7% = Fuel per hour
        # for 60 kw and below diesle generators KW * 8.5%  = Fuel per hour
        try:
            if self.FuelHalfRate == 0 or self.FuelFullRate == 0:
                return None

            return [
                0.5,
                float(self.FuelHalfRate),
                1.0,
                float(self.FuelFullRate),
                self.FuelUnits,
            ]

        except Exception as e1:
            self.LogErrorLine("Error in GetFuelConsumptionDataPoints: " + str(e1))
        return None

    # ----------  GeneratorController::ExternalFuelDataSupported-----------------
    def ExternalFuelDataSupported(self):
        return self.UseExternalFuelData

    # ----------  GeneratorController::GetNumberExternalTanks--------------------
    def GetNumberExternalTanks(self):

        try:
            if not self.ExternalFuelDataSupported():
                return 0
            if self.TankData == None:
                return 0
            if "Percentage4" in self.TankData:
                return 4
            elif "Percentage3" in self.TankData:
                return 3
            elif "Percentage2" in self.TankData:
                return 2
            elif "Percentage" in self.TankData:
                return 1
            else:
                return 0
        except Exception as e1:
            self.LogErrorLine("Error in GetNumberExternalTanks: " + str(e1))
            return 0

    # ----------  GeneratorController::GetExternalFuelPercentage-----------------
    def GetExternalFuelPercentage(self, ReturnFloat=False, TankNumber=0):

        try:
            if ReturnFloat:
                DefaultReturn = 0.0
            else:
                DefaultReturn = "0"

            if not self.ExternalFuelDataSupported():
                return DefaultReturn

            if self.TankData == None:
                return DefaultReturn

            NumTanks = self.GetNumberExternalTanks()
            if TankNumber > NumTanks:
                return DefaultReturn

            if TankNumber == 1:
                percentage = self.TankData["Percentage"]
            if TankNumber == 2:
                percentage = self.TankData["Percentage2"]
            if TankNumber == 3:
                percentage = self.TankData["Percentage3"]
            if TankNumber == 4:
                percentage = self.TankData["Percentage4"]
            # TankNumber == 0 denotes an average of all tanks
            if TankNumber == 0:
                if "Percentage4" in self.TankData:
                    percentage = (
                        float(self.TankData["Percentage"])
                        + float(self.TankData["Percentage2"])
                        + float(self.TankData["Percentage3"])
                        + float(self.TankData["Percentage4"])
                    ) / 4
                elif "Percentage3" in self.TankData:
                    percentage = (
                        float(self.TankData["Percentage"])
                        + float(self.TankData["Percentage2"])
                        + float(self.TankData["Percentage3"])
                    ) / 3
                elif "Percentage2" in self.TankData:
                    percentage = (
                        float(self.TankData["Percentage"])
                        + float(self.TankData["Percentage2"])
                    ) / 2
                else:
                    percentage = self.TankData["Percentage"]
            if ReturnFloat:
                return float(percentage)
            else:
                return str(percentage)
        except Exception as e1:
            self.LogErrorLine("Error in GetExternalFuelPercentage: " + str(e1))
            return DefaultReturn

    # ----------  GeneratorController::SetExternalTankData-----------------------
    def SetExternalTankData(self, command):

        try:
            bInitTiles = False
            CmdList = command.split("=")
            if len(CmdList) == 2:
                with self.ExternalDataLock:
                    if self.TankData == None:
                        bInitTiles = True
                    self.TankData = json.loads(CmdList[1])
                if bInitTiles:
                    self.UseExternalFuelData = True
                    self.SetupTiles()
            else:
                self.LogError("Error in  SetExternalTankData: invalid input")
                return "Error"
        except Exception as e1:
            self.LogErrorLine("Error in SetExternalTankData: " + str(e1))
            return "Error"
        return "OK"

    # ----------  GeneratorController::CheckLegBalance--------------------------
    def CheckLegBalance(self, current_leg1, current_leg2, current_leg3 = None):
        try:
            ReturnValue = True

            if self.bDisablePowerLog:
                return True
            if self.UnbalancedCapacity == None or not isinstance(self.UnbalancedCapacity, float) or self.UnbalancedCapacity <= 0:
                return True
        
            if self.UnbalancedCapacity > 0.50:
                self.UnbalancedCapacity == 0.5
            elif self.UnbalancedCapacity > 0:
                self.UnbalancedCapacity == 0

            if current_leg3 != None and current_leg3 == 0 and current_leg1 == 0 and current_leg2 == 0:
                return True
            if current_leg1 == 0 and current_leg2 == 0:
                return True

            try:
                NominalKw = float(self.NominalKW)
                NominalLineVolts = float(self.NominalLineVolts)
            except:
                return True 
            
            leg_notice = ""
            MaxCurrent = float(((NominalKw) * 1000.0) / NominalLineVolts)
            diffvalue = abs(current_leg1 - current_leg2) / MaxCurrent
            if ((abs(current_leg1 - current_leg2) / MaxCurrent) > self.UnbalancedCapacity):
                msgbody = ("Unbalanced load on L1-L2:  %.2fA,  %.2fA, difference  is %d%% of %dA" % 
                    (current_leg1, current_leg2,((abs(current_leg1 - current_leg2) / MaxCurrent) * 100), MaxCurrent))
                leg_notice = "L1 - L2"
                self.LogDebug(msgbody)
                ReturnValue = False
            if current_leg3 != None:
                # now check leg 3
                if ((abs(current_leg3 - current_leg2) / MaxCurrent) > self.UnbalancedCapacity):
                    msgbody = ("Unbalanced load on L2-L3:  %.2fA,  %.2fA, difference  is %d%% of %dA" % 
                    (current_leg1, current_leg2,((abs(current_leg1 - current_leg2) / MaxCurrent) * 100), MaxCurrent))
                    leg_notice = "L2 - L3"
                    self.LogDebug(msgbody)
                    ReturnValue = False
                if ((abs(current_leg3 - current_leg1) / MaxCurrent) > self.UnbalancedCapacity):
                    msgbody = ("Unbalanced load on L1-L3:  %.2fA,  %.2fA, difference  is %d%% of %dA" % 
                    (current_leg1, current_leg2,((abs(current_leg1 - current_leg2) / MaxCurrent) * 100), MaxCurrent))
                    leg_notice = "L1 - L3"
                    self.LogDebug(msgbody)
                    ReturnValue = False
            if not ReturnValue:
                self.MessagePipe.SendMessage(
                    "Generator Warning at %s: Load Imbalance on %s" % (self.SiteName, leg_notice),
                    msgbody,
                    msgtype="warn",
                    oncedaily=True,
                )
            return ReturnValue
        except Exception as e1:
            self.LogErrorLine("Error in CheckLegBalance: " + str(e1))
            return False
    # ----------  GeneratorController::SetExternalSensorData----------------
    def SetExternalSensorData(self, command):

        try:
            if not isinstance(command, str) and not isinstance(command, unicode):
                self.LogErrorLine("Error in SetExternalSensorData, invalid data: " + str(type(command)))
                return "Error"

            with self.ExternalDataLock:
                CmdList = command.split("=")
                if len(CmdList) == 2:
                    if self.ExternalSensorData == None:
                        self.ExternalSensorData = json.loads(CmdList[1])
                    else:
                        new_list = json.loads(CmdList[1])   # list of dicts {'label': 'value with units'}
                        for new_sensor in new_list:
                            found = False
                            for i in range(len(self.ExternalSensorData)):
                                existing_sensor = self.ExternalSensorData[i]
                                if list(new_sensor.keys())[0] == list(existing_sensor.keys())[0]:
                                    self.ExternalSensorData[i] = new_sensor
                                    found = True
                            if not found:   # first time seeing this sensor
                                self.ExternalSensorData.append(new_sensor)

                    self.UseExternalSensorData = True
                    self.ExternalSensorDataTime = datetime.datetime.now()
                    
                else:
                    self.LogError("Error in  SetExternalSensorData: invalid input: " + str(len(CmdList)))
                    return "Error"

        except Exception as e1:
            self.LogErrorLine("Error in SetExternalSensorData: " + str(e1))
            return "Error"

        return "OK"

    # ----------  GeneratorController::GetExternalSensorData--------------------------
    # used to get external temp data for gauge / tile
    def GetExternalSensorData(self, sensor_name):
        try:
            if not self.UseExternalSensorData or self.ExternalSensorData == None or self.ExternalSensorGagueData == None:
                return 0.0

            with self.ExternalDataLock:
                if len(self.ExternalSensorData) > 0:
                    for SensorDict in self.ExternalSensorData:
                        if sensor_name == list(SensorDict.keys())[0]:
                            sensor_value = SensorDict[sensor_name]
                            return self.ConvertToNumber(sensor_value)
                else:
                    self.LogDebug("Error in GetExternalSensorData: " + str(self.ExternalSensorData))
                        
            self.LogDebug("Sensor data not found in GetExternalSensorData: " + str(sensor_name))

            return 0.0
        except Exception as e1:
            self.LogErrorLine("Error in GetExternalSensorData: " + str(e1) + ": " + str(sensor_name) + ": " + str(self.ExternalSensorData))
            return 0.0

    # ----------  GeneratorController::SetExternalGaugeData-------------
    # NOTE: This command must be called first before SetExternalSensorData
    # otherwise the bounds data will be ignored
    def SetExternalGaugeData(self, command):

        try:
            if not isinstance(command, str) and not isinstance(command, unicode):
                self.LogErrorLine("Error in SetExternalGaugeData, invalid data: " + str(type(command)))
                return "Error"

            with self.ExternalDataLock:
                CmdList = command.split("=")
                if len(CmdList) == 2:
                    TempSensorGaugeList = json.loads(CmdList[1])
                    if self.ExternalSensorGagueData == None:
                        self.ExternalSensorGagueData = TempSensorGaugeList
                        self.UseExternalSensorData = True
                    else:
                        
                        for Gauge in TempSensorGaugeList:
                            found = False
                            for ExistingGauge in  self.ExternalSensorGagueData:
                                if ExistingGauge['title'] == Gauge['title']:
                                    found = True    # already exist
                                    self.LogDebug("Gauge already exist: " + Gauge['title'])
                                    break
                            if not found:
                                self.ExternalSensorGagueData.append(Gauge)
                    self.SetupTiles()
                else:
                    self.LogError("Error in  SetExternalGaugeData: invalid input: " + str(len(CmdList)))
                    return "Error"

        except Exception as e1:
            self.LogErrorLine("Error in SetExternalGaugeData: " + str(e1))
            return "Error"

        return "OK"
    # ----------  GeneratorController::SetExternalCTData-------------------------
    def SetExternalCTData(self, command):
        try:
            bInitTiles = False
            CmdList = command.split("=")
            if len(CmdList) == 2:
                with self.ExternalDataLock:
                    if self.ExternalCTData == None:
                        bInitTiles = True
                    self.ExternalCTData = json.loads(CmdList[1])
                if bInitTiles:
                    self.UseExternalCTData = True
                    self.SetupTiles()
            else:
                self.LogError("Error in  SetExternalTankData: invalid input")
                return "Error"
        except Exception as e1:
            self.LogErrorLine("Error in SetExternalCTData: " + str(e1))
            return "Error"
        return "OK"

    # ----------  GeneratorController::GetExternalCTData-------------------------
    def GetExternalCTData(self):
        try:
            if not self.UseExternalCTData:
                return None
            if self.ExternalCTData != None:
                with self.ExternalDataLock:
                    return self.ExternalCTData.copy()
            else:
                return None
        except Exception as e1:
            self.LogErrorLine("Error in GetExternalCTData: " + str(e1))
            return None
        return None

    # ------------ Evolution:ConvertExternalData --------------------------------
    def ConvertExternalData(self, request="current", voltage=None, ReturnFloat=False):

        try:
            # ExternalData can contain any of the following: current, power, ctdata[], ctpower[], voltage
            # ctpower[] and ctdata[] is a list of 2 ints, voltage is both legs combined
            if not self.UseExternalCTData:
                return None
            ExternalData = self.GetExternalCTData()

            if ExternalData == None:
                return None

            if request.lower() == "current" and "current" in ExternalData.keys():
                return self.ReturnFormat(ExternalData["current"], "A", ReturnFloat)

            if request.lower() == "power" and "power" in ExternalData.keys():
                return self.ReturnFormat(ExternalData["power"], "kW", ReturnFloat)

            if (
                request.lower() == "ct1"
                and "ctdata" in ExternalData.keys()
                and len(ExternalData["ctdata"]) >= 2
            ):
                return self.ReturnFormat(ExternalData["ctdata"][0], "A", ReturnFloat)
            if (
                request.lower() == "ct2"
                and "ctdata" in ExternalData.keys()
                and len(ExternalData["ctdata"]) >= 2
            ):
                return self.ReturnFormat(ExternalData["ctdata"][1], "A", ReturnFloat)
            if (
                request.lower() == "ctpower1"
                and "ctpower" in ExternalData.keys()
                and len(ExternalData["ctpower"]) >= 2
            ):
                return self.ReturnFormat(ExternalData["ctpower"][0], "kW", ReturnFloat)
            if (
                request.lower() == "ctpower2"
                and "ctpower" in ExternalData.keys()
                and len(ExternalData["ctpower"]) >= 2
            ):
                return self.ReturnFormat(ExternalData["ctpower"][1], "kW", ReturnFloat)

            if "powerfactor" in ExternalData.keys():
                powerfactor = float(ExternalData["powerfactor"])
            else:
                powerfactor = 1.0

            if voltage == None:
                if "voltage" in ExternalData.keys():
                    voltage = int(ExternalData["voltage"])
                else:
                    return None

            if "phase" in ExternalData.keys():
                phase = ExternalData["phase"]
            else:
                phase = 1
            if phase == 1:
                singlelegvoltage = voltage / 2
            else:
                # TODO check this
                singlelegvoltage = voltage / 3

            if request.lower() == "current" and "power" in ExternalData.keys():
                if voltage == 0:
                    return self.ReturnFormat(0.0, "A", ReturnFloat)

                if "ctpower" in ExternalData.keys() and len(ExternalData["ctpower"]) >= 2:
                    power1 = float(ExternalData["ctpower"][0]) * 1000
                    power2 = float(ExternalData["ctpower"][1]) * 1000
                    CurrentFloat = round(
                        (power1 / (powerfactor * (singlelegvoltage)))
                        + (power2 / (powerfactor * (singlelegvoltage))),
                        2,
                    )
                else:
                    PowerFloat = float(ExternalData["power"]) * 1000.0
                    # I(A) = P(W) / (PF x V(V))
                    CurrentFloat = round(PowerFloat / (powerfactor * voltage), 2)
                return self.ReturnFormat(CurrentFloat, "A", ReturnFloat)
            elif request.lower() == "power"and "current" in ExternalData.keys() and "ctdata" in ExternalData.keys():
                CurrentFloat = float(ExternalData["current"])
                if len(ExternalData["ctdata"]) < 2:
                    # P(W) = PF x I(A) x V(V)
                    PowerFloat = (powerfactor * CurrentFloat * voltage) / 1000
                else:
                    # P(W) = (PF x I(A) x V(V)) + (PF x I(A) x V(V))
                    current1 = float(ExternalData["ctdata"][0])
                    current2 = float(ExternalData["ctdata"][1])
                    PowerFloat = (
                        (powerfactor * current1 * (singlelegvoltage))
                        + (powerfactor * current2 * (singlelegvoltage))
                    ) / 1000
                    #
                return self.ReturnFormat(PowerFloat, "kW", ReturnFloat)
            elif (request.lower() in ["ct1", "ct2"] and "ctpower" in ExternalData.keys() 
                and "voltagelegs" in ExternalData.keys() and len(ExternalData["voltagelegs"]) != 0):
                # convert leg power to leg current
                if request.lower() == "ct1":
                    ctpower = ExternalData["ctpower"][0]
                    extvolts = ExternalData["voltagelegs"][0]
                elif request.lower() == "ct2":
                    ctpower = ExternalData["ctpower"][1]
                    extvolts = ExternalData["voltagelegs"][1]
                else:
                    self.LogDebug("Error in ConvertExternalData: invalid CT requested")
                    return None
                CurrentFloat = round(((ctpower*1000.0) / extvolts),2)
                return self.ReturnFormat(CurrentFloat, "A", ReturnFloat)
            elif (request.lower() in ["ctpower1", "ctpower2"] and "ctdata" in ExternalData.keys() 
                  and "voltagelegs" in ExternalData.keys() and len(ExternalData["voltagelegs"]) != 0):
                # convert leg current to leg power
                if request.lower() == "ctpower1":
                    extcurrent = ExternalData["ctdata"][0]
                    extvolts = ExternalData["voltagelegs"][0]
                elif request.lower() == "ctpower2":
                    extcurrent = ExternalData["ctdata"][1]
                    extvolts = ExternalData["voltagelegs"][1]
                else:
                    self.LogDebug("Error in ConvertExternalData: invalid Power requested")
                    return None
                PowerFloat = round(((extcurrent * extvolts)/1000.0),2)
                return self.ReturnFormat(PowerFloat, "kW", ReturnFloat)
            return None

        except Exception as e1:
            self.LogErrorLine("Error in ConvertExternalData: " + str(e1))
            return None

    # ------------ Evolution:ReturnFormat ---------------------------------------
    def ReturnFormat(sefl, value, units, ReturnFloat):

        if ReturnFloat:
            return round(float(value), 2)
        else:
            return ("%.2f " + units) % float(value)

    # ----------  GeneratorController::AddEntryToMaintLog------------------------
    def AddEntryToMaintLog(self, InputString):

        ValidInput = False
        EntryString = InputString
        if EntryString == None or not len(EntryString):
            return "Invalid input for Maintenance Log entry."

        EntryString = EntryString.strip()
        if EntryString.startswith("add_maint_log"):
            EntryString = EntryString[len("add_maint_log") :]
            EntryString = EntryString.strip()
            if EntryString.strip().startswith("="):
                EntryString = EntryString[len("=") :]
                EntryString = EntryString.strip()
                ValidInput = True

        if ValidInput:
            try:
                Entry = json.loads(EntryString)
                # validate object
                if not self.ValidateMaintLogEntry(Entry):
                    return "Invalid maintenance log entry"
                self.MaintLogList.append(Entry)
                with open(self.MaintLog, "w") as outfile:
                    json.dump(self.MaintLogList, outfile, sort_keys=True, indent=4)  
                    outfile.flush()
            except Exception as e1:
                self.LogErrorLine("Error in AddEntryToMaintLog: " + str(e1))
                return "Invalid input for Maintenance Log entry (2)."
        else:
            self.LogError("Error in AddEntryToMaintLog: invalid input: " + str(InputString))
            return "Invalid input for Maintenance Log entry (3)."
        return "OK"

    # ----------  GeneratorController::ValidateMaintLogEntry---------------------
    def ValidateMaintLogEntry(self, Entry):

        try:
            # add_maint_log={"date":"01/02/2019 14:59", "type":"Repair", "comment":"Hello"}
            if not isinstance(Entry, dict):
                self.LogError("Error in ValidateMaintLogEntry: Entry is not a dict")
                return False

            if not isinstance(Entry["date"], str) and not isinstance(
                Entry["date"], unicode
            ):
                self.LogError(
                    "Error in ValidateMaintLogEntry: Entry date is not a string: "
                    + str(type(Entry["date"]))
                )
                return False

            try:
                EntryDate = datetime.datetime.strptime(Entry["date"], "%m/%d/%Y %H:%M")
            except Exception as e1:
                self.LogErrorLine(
                    "Error in ValidateMaintLogEntry: expecting MM/DD/YYYY : " + str(e1)
                )

            if not isinstance(Entry["type"], str) and not isinstance(
                Entry["type"], unicode
            ):
                self.LogError(
                    "Error in ValidateMaintLogEntry: Entry type is not a string: "
                    + str(type(Entry["hours"]))
                )
                return False
            if not Entry["type"].lower() in [
                "maintenance",
                "check",
                "repair",
                "observation",
            ]:
                self.LogError(
                    "Error in ValidateMaintLogEntry: Invalid type: "
                    + str(Entry["type"])
                )

            Entry["type"] = Entry["type"].title()

            if not isinstance(Entry["hours"], int) and not isinstance(
                Entry["hours"], float
            ):
                self.LogError(
                    "Error in ValidateMaintLogEntry: Entry type is not a number: "
                    + str(type(Entry["hours"]))
                )
                return False
            if not isinstance(Entry["comment"], str) and not isinstance(
                Entry["comment"], unicode
            ):
                self.LogError(
                    "Error in ValidateMaintLogEntry: Entry comment is not a string: "
                    + str(type(Entry["comment"]))
                )

        except Exception as e1:
            self.LogErrorLine("Error in ValidateMaintLogEntry: " + str(e1))
            return False

        return True
    # ----------  GeneratorController::GetRegisterLabels------------------------
    def GetRegisterLabels(self):
        # return JSON of dict with registers and text descriptions
        try:
            return "{}"     # this is the default, no labels
        except Exception as e1:
            self.LogErrorLine("Error in GetRegisterLabels: " + str(e1))
        return "{}"

    # ----------  GeneratorController::GetMaintLogJSON--------------------------
    def GetMaintLogJSON(self):

        try:
            if len(self.MaintLogList):
                return json.dumps(self.MaintLogList)
            if os.path.isfile(self.MaintLog):
                try:
                    with open(self.MaintLog) as infile:
                        self.MaintLogList = json.load(infile)
                        return json.dumps(self.MaintLogList)
                except Exception as e1:
                    self.LogErrorLine("Error in GetMaintLogJSON: " + str(e1))
        except Exception as e1:
            self.LogErrorLine("Error in GetMaintLogJSON (2): " + str(e1))

        return "[]"

    # ----------  GeneratorController::GetMaintLogDict--------------------------
    def GetMaintLogDict(self):
        try:
            if len(self.MaintLogList):
                return self.MaintLogList
            if os.path.isfile(self.MaintLog):
                try:
                    with open(self.MaintLog) as infile:
                        self.MaintLogList = json.load(infile)
                        return self.MaintLogList
                except Exception as e1:
                    self.LogErrorLine("Error in GetMaintLogDict: " + str(e1))
                    return []
        except Exception as e1:
            self.LogErrorLine("Error in GetMaintLogDict (2): " + str(e1))

        return []

    # ----------  GeneratorController::UpdateMaintLog----------------------------
    def SaveMaintLog(self, NewLog):
        try:
            self.MaintLogList = NewLog
            with open(self.MaintLog, "w") as outfile:
                json.dump(
                    self.MaintLogList, outfile, sort_keys=True, indent=4
                )  # , ensure_ascii = False)
                outfile.flush()

        except Exception as e1:
            self.LogErrorLine("Error in SaveMaintLog: " + str(e1))
            return "Error in SaveMaintLog: " + str(e1)

    # ----------  GeneratorController::ClearMaintLog-------------------------------
    def ClearMaintLog(self):
        try:
            if len(self.MaintLog) and os.path.isfile(self.MaintLog):
                try:
                    with self.MaintLock:
                        os.remove(self.MaintLog)
                except:
                    pass

            self.MaintLogList = []

            return "Maintenance Log cleared"
        except Exception as e1:
            self.LogErrorLine("Error in  ClearMaintLog: " + str(e1))
            return "Error in  ClearMaintLog: " + str(e1)
        return "OK"

    # ----------  GeneratorController::EditMaintLogRow---------------------------
    def EditMaintLogRow(self, InputString):

        # { index : {maint log entry}}
        ValidInput = False
        EntryString = InputString
        if EntryString == None or not len(EntryString):
            return "Invalid input for Edit Maintenance Log entry."

        EntryString = EntryString.strip()
        if EntryString.startswith("edit_row_maint_log"):
            EntryString = EntryString[len("edit_row_maint_log") :]
            EntryString = EntryString.strip()
            if EntryString.strip().startswith("="):
                EntryString = EntryString[len("=") :]
                EntryString = EntryString.strip()
                ValidInput = True

        if ValidInput:
            try:
                EntryDict = json.loads(EntryString)
                MaintLog = self.GetMaintLogDict()
                for index, Entry in EntryDict.items():
                    # validate object
                    if not self.ValidateMaintLogEntry(Entry):
                        self.LogError(
                            "Error in EditMaintLogRow: failed validate entry in update"
                        )
                        return "Invalid edit maintenance log entry"

                    if not len(MaintLog):
                        self.LogError("Error in  EditMaintLogRow: maint log is empty")
                        return "Error"
                    del MaintLog[int(index)]
                    # save log
                    MaintLog.insert(int(index), Entry)
                self.SaveMaintLog(MaintLog)

            except Exception as e1:
                self.LogErrorLine("Error in EditMaintLogRow: " + str(e1))
                return "Invalid input for Edit Maintenance Log entry (2)."
        else:
            self.LogError(
                "Error in EditMaintLogRow: invalid input: " + str(InputString)
            )
            return "Invalid input for Edit Maintenance Log entry (3)."
        return "OK"

    # ----------  GeneratorController::DeleteMaintLogRow-------------------------
    def DeleteMaintLogRow(self, command):

        try:
            CmdList = command.split("=")
            if len(CmdList) == 2:
                index = int(CmdList[1])
                MaintLog = self.GetMaintLogDict()
                if not len(MaintLog):
                    self.LogError("Error in  DeleteMaintLogRow: maint log is empty")
                    return "Error"

                del MaintLog[int(index)]
                # save log
                self.SaveMaintLog(MaintLog)
            else:
                self.LogError(
                    "Error in  DeleteMaintLogRow: invalid input: " + str(CmdList)
                )
                return "Error"
        except Exception as e1:
            self.LogErrorLine("Error in DeleteMaintLogRow: " + str(e1))
            return "Error in DeleteMaintLogRow: " + str(e1)
        return "OK"


    # ----------  GeneratorController::Close-------------------------------------
    def Close(self):

        try:
            # Controller
            self.IsStopping = True
            try:
                self.InitCompleteEvent.set()
            except:
                pass

            try:
                if self.EnableDebug:
                    self.KillThread("DebugThread")
            except:
                pass

            try:
                self.KillThread("ProcessThread")
            except:
                pass

            try:
                self.KillThread("CheckAlarmThread")
            except:
                pass

            try:
                self.KillThread("MaintenanceHouseKeepingThread")
            except:
                pass
            try:
                self.KillThread("PowerMeter")
            except:
                pass

            if self.ModBus != None:
                # close modbus last 
                try:
                    if self.ControllerSelected.lower() == "h_100":
                        # H100 has problems with locking up if partial modbus packets are sent so delay here
                        time.sleep(0.5)
                    self.ModBus.Close()
                except:
                    pass
        except Exception as e1:
            self.LogErrorLine("Error Closing Controller: " + str(e1))

        with self.CriticalLock:
            self.InitComplete = False
