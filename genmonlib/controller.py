#!/usr/bin/env python
#-------------------------------------------------------------------------------
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
#-------------------------------------------------------------------------------

import threading, datetime, collections, os, time
# NOTE: collections OrderedDict is used for dicts that are displayed to the UI

try:
    from ConfigParser import RawConfigParser
except ImportError as e:
    from configparser import RawConfigParser

import mysupport, mypipe, mythread

class GeneratorController(mysupport.MySupport):
    #---------------------GeneratorController::__init__-------------------------
    def __init__(self, log, newinstall = False, simulation = False, simulationfile = None, message = None, feedback = None, ConfigFilePath = None):
        super(GeneratorController, self).__init__(simulation = simulation)
        self.log = log
        self.NewInstall = newinstall
        self.Simulation = simulation
        self.SimulationFile = simulationfile
        self.FeedbackPipe = feedback
        self.MessagePipe = message
        if ConfigFilePath == None:
            self.ConfigFilePath = "/etc/"
        else:
            self.ConfigFilePath = ConfigFilePath
        self.Address = None
        self.SerialPort = "/dev/serial0"
        self.BaudRate = 9600
        self.ModBus = None
        self.InitComplete = False
        self.InitCompleteEvent = threading.Event() # Event to signal init complete
        self.CheckForAlarmEvent = threading.Event() # Event to signal checking for alarm
        self.Registers = {}         # dict for registers and values
        self.NotChanged = 0         # stats for registers
        self.Changed = 0            # stats for registers
        self.TotalChanged = 0.0     # ratio of changed ragisters
        self.EnableDebug = False    # Used for enabeling debugging
        self.OutageLog = os.path.dirname(os.path.dirname(os.path.realpath(__file__))) + "/outage.txt"
        self.PowerLogMaxSize = 15       # 15 MB max size
        self.PowerLog =  os.path.dirname(os.path.dirname(os.path.realpath(__file__))) + "/kwlog.txt"
        self.TileList = []        # Tile list for GUI

        if self.Simulation:
            self.LogLocation = "./"
        else:
            self.LogLocation = "/var/log/"
        self.DisableOutageCheck = False
        self.bDisplayUnknownSensors = False
        self.UtilityVoltsMin = 0    # Minimum reported utility voltage above threshold
        self.UtilityVoltsMax = 0    # Maximum reported utility voltage above pickup
        self.SystemInOutage = False         # Flag to signal utility power is out
        self.TransferActive = False         # Flag to signal transfer switch is allowing gen supply power
        self.SiteName = "Home"
        # The values "Unknown" are checked to validate conf file items are found
        self.FuelType = "Unknown"
        self.NominalFreq = "Unknown"
        self.NominalRPM = "Unknown"
        self.NominalKW = "Unknown"
        self.Model = "Unknown"

        self.ProgramStartTime = datetime.datetime.now()     # used for com metrics
        self.OutageStartTime = self.ProgramStartTime        # if these two are the same, no outage has occured
        self.LastOutageDuration = self.OutageStartTime - self.OutageStartTime

        # Read conf entries common to all controllers
        ConfigSection = "GenMon"
        try:
            # read config file
            config = RawConfigParser()
            # config parser reads from current directory, when running form a cron tab this is
            # not defined so we specify the full path
            config.read(self.ConfigFilePath + 'genmon.conf')

            # getfloat() raises an exception if the value is not a float
            # getint() and getboolean() also do this for their respective types
            if config.has_option(ConfigSection, 'sitename'):
                self.SiteName = config.get(ConfigSection, 'sitename')

            if config.has_option(ConfigSection, 'port'):
                self.SerialPort = config.get(ConfigSection, 'port')

            if config.has_option(ConfigSection, 'loglocation'):
                self.LogLocation = config.get(ConfigSection, 'loglocation')

            # optional config parameters, by default the software will attempt to auto-detect the controller
            # this setting will override the auto detect
            if config.has_option(ConfigSection, 'disableoutagecheck'):
                self.DisableOutageCheck = config.getboolean(ConfigSection, 'disableoutagecheck')

            if config.has_option(ConfigSection, 'enabledebug'):
                self.EnableDebug = config.getboolean(ConfigSection, 'enabledebug')

            if config.has_option(ConfigSection, 'displayunknown'):
                self.bDisplayUnknownSensors = config.getboolean(ConfigSection, 'displayunknown')
            if config.has_option(ConfigSection, 'outagelog'):
                self.OutageLog = config.get(ConfigSection, 'outagelog')

            if config.has_option(ConfigSection, 'kwlog'):
                self.PowerLog = config.get(ConfigSection, 'kwlog')
            if config.has_option(ConfigSection, 'kwlogmax'):
                self.PowerLogMaxSize = config.getint(ConfigSection, 'kwlogmax')

            if config.has_option(ConfigSection, 'nominalfrequency'):
                self.NominalFreq = config.get(ConfigSection, 'nominalfrequency')
            if config.has_option(ConfigSection, 'nominalRPM'):
                self.NominalRPM = config.get(ConfigSection, 'nominalRPM')
            if config.has_option(ConfigSection, 'nominalKW'):
                self.NominalKW = config.get(ConfigSection, 'nominalKW')
            if config.has_option(ConfigSection, 'model'):
                self.Model = config.get(ConfigSection, 'model')

            if config.has_option(ConfigSection, 'fueltype'):
                self.FuelType = config.get(ConfigSection, 'fueltype')

        except Exception as e1:
            if not reload:
                self.FatalError("Missing config file or config file entries: " + str(e1))
            else:
                self.LogErrorLine("Error reloading config file" + str(e1))


    #----------  GeneratorController:StartCommonThreads-------------------------
    # called after get config file, starts threads common to all controllers
    def StartCommonThreads(self):

        self.Threads["CheckAlarmThread"] = mythread.MyThread(self.CheckAlarmThread, Name = "CheckAlarmThread")
        # start read thread to process incoming data commands
        self.Threads["ProcessThread"] = mythread.MyThread(self.ProcessThread, Name = "ProcessThread")

        if self.EnableDebug:        # for debugging registers
            self.Threads["DebugThread"] = mythread.MyThread(self.DebugThread, Name = "DebugThread")

        # start thread for kw log
        self.Threads["PowerMeter"] = mythread.MyThread(self.PowerMeter, Name = "PowerMeter")

    # ---------- GeneratorController:ProcessThread------------------------------
    #  read registers, remove items from Buffer, form packets, store register data
    def ProcessThread(self):

        try:
            self.ModBus.Flush()
            self.InitDevice()

            while True:
                try:
                    self.MasterEmulation()
                    if self.IsStopSignaled("ProcessThread"):
                        break
                except Exception as e1:
                    self.LogErrorLine("Error in Controller ProcessThread (1), continue: " + str(e1))
        except Exception as e1:
            self.FatalError("Exiting Controller ProcessThread (2)" + str(e1))

    # ---------- GeneratorController:CheckAlarmThread---------------------------
    #  When signaled, this thread will check for alarms
    def CheckAlarmThread(self):

        while True:
            try:
                time.sleep(0.25)
                if self.IsStopSignaled("CheckAlarmThread"):
                    break
                if self.CheckForAlarmEvent.is_set():
                    self.CheckForAlarmEvent.clear()
                    self.CheckForAlarms()

            except Exception as e1:
                self.FatalError("Error in  CheckAlarmThread" + str(e1))

    #----------  GeneratorController:DebugThread--------------------------------
    def DebugThread(self):

        if not self.EnableDebug:
            return
        time.sleep(1)

        self.InitCompleteEvent.wait()

        self.LogError("Debug Enabled")
        self.FeedbackPipe.SendFeedback("Debug Thread Starting", FullLogs = True, Always = True, Message="Starting Debug Thread")
        TotalSent = 0

        RegistersUnderTest = collections.OrderedDict()
        RegistersUnderTestData = ""

        while True:

            if self.IsStopSignaled("DebugThread"):
                return
            if TotalSent >= 5:
                continue
            try:
                for Reg in range(0x0 , 0x2000):
                    time.sleep(0.25)
                    Register = "%04x" % Reg
                    NewValue = self.ModBus.ProcessMasterSlaveTransaction(Register, 1, ReturnValue = True)
                    OldValue = RegistersUnderTest.get(Register, "")
                    if OldValue == "":
                        RegistersUnderTest[Register] = NewValue        # first time seeing this register so add it to the list
                    elif NewValue != OldValue:
                        BitsChanged, Mask = self.GetNumBitsChanged(OldValue, NewValue)
                        RegistersUnderTestData += "Reg %s changed from %s to %s, Bits Changed: %d, Mask: %x, Engine State: %s\n" % \
                                (Register, OldValue, NewValue, BitsChanged, Mask, self.GetEngineState())
                        RegistersUnderTest[Register] = Value        # update the value

                msgbody = ""
                for Register, Value in RegistersUnderTest.items():
                    msgbody += self.printToString("%s:%s" % (Register, Value))

                self.FeedbackPipe.SendFeedback("Debug Thread (Registers)", FullLogs = True, Always = True, Message=msgbody, NoCheck = True)
                if len(RegistersUnderTestData):
                    self.FeedbackPipe.SendFeedback("Debug Thread (Changes)", FullLogs = True, Always = True, Message=RegistersUnderTestData, NoCheck = True)
                RegistersUnderTestData = ""
                TotalSent += 1

            except Exception as e1:
                self.LogErrorLine("Error in DebugThread: " + str(e1))

    #------------ GeneratorController:GetRegisterValueFromList -----------------
    def GetRegisterValueFromList(self,Register):

        return self.Registers.get(Register, "")

    #-------------GeneratorController:GetParameterBit---------------------------
    def GetParameterBit(self, Register, Mask, OnLabel = None, OffLabel = None):

        try:
            Value =  self.GetRegisterValueFromList(Register)
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

    #-------------GeneratorController:GetParameterLong--------------------------
    def GetParameterLong(self, RegisterLo, RegisterHi, Label = None, Divider = None, ReturnInt = False):

        try:
            if not Label == None:
                LabelStr = Label
            else:
                LabelStr = ""

            ValueLo = self.GetParameter(RegisterLo)
            ValueHi = self.GetParameter(RegisterHi)

            if not len(ValueLo) or not len(ValueHi):
                if ReturnInt:
                    return 0
                else:
                    return ""

            IntValueLo = int(ValueLo)
            IntValueHi = int(ValueHi)

            IntValue = IntValueHi << 16 | IntValueLo

            if ReturnInt:
                return IntValue

            if not Divider == None:
                FloatValue = IntValue / Divider
                return "%2.1f %s" % (FloatValue, LabelStr)
            return "%d %s" % (IntValue, LabelStr)
        except Exception as e1:
            self.LogErrorLine("Error in GetParameterBit: " + str(e1))
            return ""

    #-------------GeneratorController:GetParameter------------------------------
    # Hex assumes no Divider and Label - return Hex string
    # ReturnInt assumes no Divier and Label - Return int
    def GetParameter(self, Register, Label = None, Divider = None, Hex = False, ReturnInt = False, ReturnFloat = False):

        try:
            if ReturnInt:
                DefaultReturn = 0
            elif ReturnFloat:
                DefaultReturn = 0.0
            else:
                DefaultReturn = ""

            Value = self.GetRegisterValueFromList(Register)
            if not len(Value):
                return DefaultReturn

            if ReturnInt:
                return int(Value,16)

            if Divider == None and Label == None:
                if Hex:
                    return Value
                elif ReturnFloat:
                    return float(int(Value,16))
                else:
                    return str(int(Value,16))

            IntValue = int(Value,16)
            if not Divider == None:
                FloatValue = IntValue / Divider
                if ReturnFloat:
                    return FloatValue
                if not Label == None:
                    return "%.2f %s" % (FloatValue, Label)
                else:
                    return "%.2f" % (FloatValue)
            elif not Label == None:
                return "%d %s" % (IntValue, Label)
            else:
                return str(int(Value,16))

        except Exception as e1:
            self.LogErrorLine("Error in GetParameter:" + str(e1))
            return ""

    #---------------------GeneratorController::GetConfig------------------------
    # read conf file, used internally, not called by genmon
    # return True on success, else False
    def GetConfig(self):
        True

    #---------------------GeneratorController::SystemInAlarm--------------------
    # return True if generator is in alarm, else False
    def SystemInAlarm(self):
        return False

    #------------ GeneratorController::GetStartInfo ----------------------------
    # return a dictionary with startup info for the gui
    def GetStartInfo(self, NoTile = False):

        StartInfo = {}
        try:
            StartInfo["fueltype"] = self.FuelType
            StartInfo["model"] = self.Model
            StartInfo["nominalKW"] = self.NominalKW
            StartInfo["nominalRPM"] = self.NominalRPM
            StartInfo["nominalfrequency"] = self.NominalFreq
            StartInfo["Controller"] = "Generic Controller Name"
            StartInfo["PowerGraph"] = self.PowerMeterIsSupported()
            StartInfo["NominalBatteryVolts"] = "12"
            StartInfo["UtilityVoltageDisplayed"] = True
            StartInfo["RemoteCommands"] = True

            if not NoTile:
                StartInfo["tiles"] = []
                for Tile in self.TileList:
                    StartInfo["tiles"].append(Tile.GetStartInfo())

        except Exception as e1:
            self.LogErrorLine("Error in GetStartInfo: " + str(e1))
        return StartInfo

    #------------ GeneratorController::GetStatusForGUI -------------------------
    # return dict for GUI
    def GetStatusForGUI(self):

        Status = {}
        try:
            Status["basestatus"] = self.GetBaseStatus()
            Status["kwOutput"] = self.GetPowerOutput()
            Status["OutputVoltage"] = "0V"
            Status["BatteryVoltage"] = "0V"
            Status["UtilityVoltage"] = "0V"
            Status["Frequency"] = "0"
            Status["RPM"] = "0"

            # Exercise Info is a dict containing the following:
            ExerciseInfo = collections.OrderedDict()
            ExerciseInfo["Enabled"] = False
            ExerciseInfo["Frequency"] = "Weekly"    # Biweekly, Weekly or Monthly
            ExerciseInfo["Hour"] = "14"
            ExerciseInfo["Minute"] = "00"
            ExerciseInfo["QuietMode"] = "On"
            ExerciseInfo["EnhancedExerciseMode"] = False
            ExerciseInfo["Day"] = "Monday"
            Status["ExerciseInfo"] = ExerciseInfo
        except Exception as e1:
            self.LogErrorLine("Error in GetStatusForGUI: " + str(e1))
        return Status

    #---------------------GeneratorController::DisplayLogs----------------------
    def DisplayLogs(self, AllLogs = False, DictOut = False, RawOutput = False):
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in DisplayLogs: " + str(e1))

    #------------ GeneratorController::DisplayMaintenance ----------------------
    def DisplayMaintenance (self, DictOut = False):
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in DisplayMaintenance: " + str(e1))

    #------------ GeneratorController::DisplayStatus ---------------------------
    def DisplayStatus(self, DictOut = False):
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in DisplayStatus: " + str(e1))

    #------------------- GeneratorController::DisplayOutage --------------------
    def DisplayOutage(self, DictOut = False):
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in DisplayOutage: " + str(e1))

    #------------ GeneratorController::DisplayRegisters ------------------------
    def DisplayRegisters(self, AllRegs = False, DictOut = False):
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in DisplayRegisters: " + str(e1))

    #----------  GeneratorController::SetGeneratorTimeDate----------------------
    # set generator time to system time
    def SetGeneratorTimeDate(self):

        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in SetGeneratorTimeDate: " + str(e1))

        return "Not Supported"

    #----------  GeneratorController::SetGeneratorQuietMode---------------------
    # Format of CmdString is "setquiet=yes" or "setquiet=no"
    # return  "Set Quiet Mode Command sent" or some meaningful error string
    def SetGeneratorQuietMode(self, CmdString):
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in SetGeneratorQuietMode: " + str(e1))

        return "Not Supported"

    #----------  GeneratorController::SetGeneratorExerciseTime------------------
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

    #----------  GeneratorController::SetGeneratorRemoteStartStop---------------
    # CmdString will be in the format: "setremote=start"
    # valid commands are start, stop, starttransfer, startexercise
    # return string "Remote command sent successfully" or some descriptive error
    # string if failure
    def SetGeneratorRemoteStartStop(self, CmdString):
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in SetGeneratorRemoteStartStop: " + str(e1))

        return "Not Supported"

    #----------  GeneratorController:GetController  ----------------------------
    # return the name of the controller, if Actual == False then return the
    # controller name that the software has been instructed to use if overridden
    # in the conf file
    def GetController(self, Actual = True):
        return "Test Controller"

    #----------  GeneratorController:ComminicationsIsActive  -------------------
    # Called every 2 seconds, if communictions are failing, return False, otherwise
    # True
    def ComminicationsIsActive(self):
        return False

    #----------  GeneratorController:ResetCommStats  ---------------------------
    # reset communication stats, normally just a call to
    #   self.ModBus.ResetCommStats() if modbus is used
    def ResetCommStats(self):
        self.ModBus.ResetCommStats()

    #----------  GeneratorController:PowerMeterIsSupported  --------------------
    # return true if GetPowerOutput is supported
    def PowerMeterIsSupported(self):
        False

    #---------------------GeneratorController::GetPowerOutput-------------------
    # returns current kW
    # rerturn empty string ("") if not supported,
    # return kW with units i.e. "2.45kW"
    def GetPowerOutput(self, ReturnFloat = False):
        return ""

    #----------  GeneratorController:GetCommStatus  ----------------------------
    # return Dict with communication stats
    def GetCommStatus(self):
        return self.ModBus.GetCommStats()

    #------------ GeneratorController:GetBaseStatus ----------------------------
    # return one of the following: "ALARM", "SERVICEDUE", "EXERCISING", "RUNNING",
    # "RUNNING-MANUAL", "OFF", "MANUAL", "READY"
    def GetBaseStatus(self):
        return "OFF"

    #------------ GeneratorController:GetOneLineStatus -------------------------
    # returns a one line status for example : switch state and engine state
    def GetOneLineStatus(self):
        return "Unknown"
    #------------ GeneratorController:RegRegValue ------------------------------
    def GetRegValue(self, CmdString):

        # extract quiet mode setting from Command String
        # format is setquiet=yes or setquiet=no
        msgbody = "Invalid command syntax for command getregvalue"
        try:
            #Format we are looking for is "getregvalue=01f4"
            CmdList = CmdString.split("=")
            if len(CmdList) != 2:
                self.LogError("Validation Error: Error parsing command string in GetRegValue (parse): " + CmdString)
                return msgbody

            CmdList[0] = CmdList[0].strip()

            if not CmdList[0].lower() == "getregvalue":
                self.LogError("Validation Error: Error parsing command string in GetRegValue (parse2): " + CmdString)
                return msgbody

            Register = CmdList[1].strip()

            RegValue = self.GetRegisterValueFromList(Register)

            if RegValue == "":
                self.LogError("Validation Error: Register  not known:" + Register)
                msgbody = "Unsupported Register: " + Register
                return msgbody

            msgbody = RegValue

        except Exception as e1:
            self.LogErrorLine("Validation Error: Error parsing command string in GetRegValue: " + CmdString)
            self.LogError( str(e1))
            return msgbody

        return msgbody


    #------------ GeneratorController:ReadRegValue -----------------------------
    def ReadRegValue(self, CmdString):

        # extract quiet mode setting from Command String
        #Format we are looking for is "readregvalue=01f4"
        msgbody = "Invalid command syntax for command readregvalue"
        try:

            CmdList = CmdString.split("=")
            if len(CmdList) != 2:
                self.LogError("Validation Error: Error parsing command string in ReadRegValue (parse): " + CmdString)
                return msgbody

            CmdList[0] = CmdList[0].strip()

            if not CmdList[0].lower() == "readregvalue":
                self.LogError("Validation Error: Error parsing command string in ReadRegValue (parse2): " + CmdString)
                return msgbody

            Register = CmdList[1].strip()

            RegValue = self.ModBus.ProcessMasterSlaveTransaction( Register, 1, ReturnValue = True)

            if RegValue == "":
                self.LogError("Validation Error: Register  not known (ReadRegValue):" + Register)
                msgbody = "Unsupported Register: " + Register
                return msgbody

            msgbody = RegValue

        except Exception as e1:
            self.LogErrorLine("Validation Error: Error parsing command string in ReadRegValue: " + CmdString)
            self.LogError( str(e1))
            return msgbody

        return msgbody
    #------------ GeneratorController:DisplayOutageHistory----------------------
    def DisplayOutageHistory(self):

        LogHistory = []

        if not len(self.OutageLog):
            return ""
        try:
            # check to see if a log file exist yet
            if not os.path.isfile(self.OutageLog):
                return ""

            OutageLog = []

            with open(self.OutageLog,"r") as OutageFile:     #opens file

                for line in OutageFile:
                    line = line.strip()                   # remove whitespace at beginning and end

                    if not len(line):
                        continue
                    if line[0] == "#":              # comment?
                        continue
                    Items = line.split(",")
                    if len(Items) != 2 and len(Items) != 3:
                        continue
                    if len(Items) == 3:
                        strDuration = Items[1] + "," + Items[2]
                    else:
                        strDuration = Items[1]

                    OutageLog.insert(0, [Items[0], strDuration])
                    if len(OutageLog) > 50:     # limit log to 50 entries
                        OutageLog.pop()

            for Items in OutageLog:
                LogHistory.append("%s, Duration: %s" % (Items[0], Items[1]))

            return LogHistory

        except Exception as e1:
            self.LogErrorLine("Error in  DisplayOutageHistory: " + str(e1))
            return []
    #------------ GeneratorController::PrunePowerLog----------------------------
    def PrunePowerLog(self, Minutes):

        if not Minutes:
            return self.ClearPowerLog()

        try:
            CmdString = "power_log_json=%d" % Minutes
            PowerLog = self.GetPowerHistory(CmdString, NoReduce = True)

            LogSize = os.path.getsize(self.PowerLog)

            if float(LogSize) / (1024*1024) >= self.PowerLogMaxSize * 0.98:
                msgbody = "The kwlog file size is 98% of the maximum. Once the log reaches 100% of the maximum size the log will be reset."
                self.MessagePipe.SendMessage("Notice: Log file size warning" , msgbody, msgtype = "warn")

            # is the file size too big?
            if float(LogSize) / (1024*1024) >= self.PowerLogMaxSize:
                self.ClearPowerLog()
                self.LogError("Power Log entries deleted due to size reaching maximum.")
                return "OK"

            self.ClearPowerLog(NoCreate = True)
            # Write oldest log entries first
            for Items in reversed(PowerLog):
                self.LogToFile(self.PowerLog, Items[0], Items[1])

            if not os.path.isfile(self.PowerLog):
                TimeStamp = datetime.datetime.now().strftime('%x %X')
                self.LogToFile(self.PowerLog, TimeStamp, "0.0")

            LogSize = os.path.getsize(self.PowerLog)
            if LogSize == 0:
                TimeStamp = datetime.datetime.now().strftime('%x %X')
                self.LogToFile(self.PowerLog, TimeStamp, "0.0")

            return "OK"

        except Exception as e1:
            self.LogErrorLine("Error in  PrunePowerLog: " + str(e1))
            return "Error in  PrunePowerLog: " + str(e1)

    #------------ GeneratorController::ClearPowerLog----------------------------
    def ClearPowerLog(self, NoCreate = False):

        try:
            if not len(self.PowerLog):
                return "Power Log Disabled"

            if not os.path.isfile(self.PowerLog):
                return "Power Log is empty"
            try:
                os.remove(self.PowerLog)
            except:
                pass

            if not NoCreate:
                # add zero entry to note the start of the log
                TimeStamp = datetime.datetime.now().strftime('%x %X')
                self.LogToFile(self.PowerLog, TimeStamp, "0.0")

            return "Power Log cleared"
        except Exception as e1:
            self.LogErrorLine("Error in  ClearPowerLog: " + str(e1))
            return "Error in  ClearPowerLog: " + str(e1)

    #------------ GeneratorController::ReducePowerSamples-----------------------
    def ReducePowerSamplesOld(self, PowerList, MaxSize):

        if MaxSize == 0:
            self.LogError("RecducePowerSamples: Error: Max size is zero")
            return []

        if len(PowerList) < MaxSize:
            self.LogError("RecducePowerSamples: Error: Can't reduce ")
            return PowerList

        try:
            Sample = int(len(PowerList) / MaxSize)
            Remain = int(len(PowerList) % MaxSize)

            NewList = []
            Count = 0
            for Count in range(len(PowerList)):
                TimeStamp, KWValue = PowerList[Count]
                if float(KWValue) == 0:
                        NewList.append([TimeStamp,KWValue])
                elif ( Count % Sample == 0 ):
                    NewList.append([TimeStamp,KWValue])

            # if we have too many entries due to a remainder or not removing zero samples, then delete some
            if len(NewList) > MaxSize:
                return RemovePowerSamples(NewList, MaxSize)
        except Exception as e1:
            self.LogErrorLine("Error in RecducePowerSamples: %s" % str(e1))
            return PowerList

        return NewList

    #------------ GeneratorController::RemovePowerSamples-----------------------
    def RemovePowerSamples(List, MaxSize):

        try:
            if len(List) <= MaxSize:
                self.LogError("RemovePowerSamples: Error: Can't remove ")
                return List

            Extra = len(List) - MaxSize
            for Count in range(Extra):
                    # assume first and last sampels are zero samples so don't select thoes
                    self.MarkNonZeroKwEntry(List, random.randint(1, len(List) - 2))

            TempList = []
            for TimeStamp, KWValue in List:
                if not TimeStamp == "X":
                    TempList.append([TimeStamp, KWValue])
            return TempList
        except Exception as e1:
            self.LogErrorLine("Error in RemovePowerSamples: %s" % str(e1))
            return List

    #------------ GeneratorController::MarkNonZeroKwEntry-----------------------
    #       RECURSIVE
    def MarkNonZeroKwEntry(self, List, Index):

        try:
            TimeStamp, KwValue = List[Index]
            if not KwValue == "X" and not float(KwValue) == 0.0:
                List[Index] = ["X", "X"]
                return
            else:
                MarkNonZeroKwEntry(List, Index - 1)
                return
        except Exception as e1:
            self.LogErrorLine("Error in MarkNonZeroKwEntry: %s" % str(e1))
        return

    #------------ GeneratorController::ReducePowerSamples-----------------------
    def ReducePowerSamples(self, PowerList, MaxSize):

        if MaxSize == 0:
            self.LogError("RecducePowerSamples: Error: Max size is zero")
            return []

        periodMaxSamples = MaxSize
        NewList = []
        try:
            CurrentTime = datetime.datetime.now()
            secondPerSample = 0
            prevMax = 0
            currMax = 0
            currTime = CurrentTime
            prevTime = CurrentTime + datetime.timedelta(minutes=1)
            currSampleTime = CurrentTime
            prevBucketTime = CurrentTime # prevent a 0 to be written the first time
            nextBucketTime = CurrentTime - datetime.timedelta(seconds=1)

            for Count in range(len(PowerList)):
               TimeStamp, KWValue = PowerList[Count]
               struct_time = time.strptime(TimeStamp, "%x %X")
               delta_sec = (CurrentTime - datetime.datetime.fromtimestamp(time.mktime(struct_time))).total_seconds()
               if 0 <= delta_sec <= datetime.timedelta(minutes=60).total_seconds():
                   secondPerSample = int(datetime.timedelta(minutes=60).total_seconds() / periodMaxSamples)
               if datetime.timedelta(minutes=60).total_seconds() <= delta_sec <=  datetime.timedelta(hours=24).total_seconds():
                   secondPerSample = int(datetime.timedelta(hours=23).total_seconds() / periodMaxSamples)
               if datetime.timedelta(hours=24).total_seconds() <= delta_sec <= datetime.timedelta(days=7).total_seconds():
                   secondPerSample = int(datetime.timedelta(days=6).total_seconds() / periodMaxSamples)
               if datetime.timedelta(days=7).total_seconds() <= delta_sec <= datetime.timedelta(days=31).total_seconds():
                   secondPerSample = int(datetime.timedelta(days=25).total_seconds() / periodMaxSamples)

               currSampleTime = CurrentTime - datetime.timedelta(seconds=(int(delta_sec / secondPerSample)*secondPerSample))
               if (currSampleTime != currTime):
                   if ((currMax > 0) and (prevBucketTime != prevTime)):
                       NewList.append([prevBucketTime.strftime('%x %X'), 0.0])
                   if ((currMax > 0) or ((currMax == 0) and (prevMax > 0))):
                       NewList.append([currTime.strftime('%x %X'), currMax])
                   if ((currMax > 0) and (nextBucketTime != currSampleTime)):
                       NewList.append([nextBucketTime.strftime('%x %X'), 0.0])
                   prevMax = currMax
                   prevTime = currTime
                   currMax = KWValue
                   currTime = currSampleTime
                   prevBucketTime  = CurrentTime - datetime.timedelta(seconds=((int(delta_sec / secondPerSample)+1)*secondPerSample))
                   nextBucketTime  = CurrentTime - datetime.timedelta(seconds=((int(delta_sec / secondPerSample)-1)*secondPerSample))
               else:
                   currMax = max(currMax, KWValue)


            NewList.append([currTime.strftime('%x %X'), currMax])
        except Exception as e1:
            self.LogErrorLine("Error in RecducePowerSamples: %s" % str(e1))
            return PowerList

        return NewList

    #------------ GeneratorController::GetPowerHistory--------------------------
    def GetPowerHistory(self, CmdString, NoReduce = False):

        KWHours = False
        msgbody = "Invalid command syntax for command power_log_json"

        try:
            if not len(self.PowerLog):
                # power log disabled
                return []

            if not len(CmdString):
                self.LogError("Error in GetPowerHistory: Invalid input")
                return []

            #Format we are looking for is "power_log_json=5" or "power_log_json" or "power_log_json=1000,kw"
            CmdList = CmdString.split("=")

            if len(CmdList) > 2:
                self.LogError("Validation Error: Error parsing command string in GetPowerHistory (parse): " + CmdString)
                return msgbody

            CmdList[0] = CmdList[0].strip()

            if not CmdList[0].lower() == "power_log_json":
                self.LogError("Validation Error: Error parsing command string in GetPowerHistory (parse2): " + CmdString)
                return msgbody

            if len(CmdList) == 2:
                ParseList = CmdList[1].split(",")
                if len(ParseList) == 1:
                    Minutes = int(CmdList[1].strip())
                elif len(ParseList) == 2:
                    Minutes = int(ParseList[0].strip())
                    if ParseList[1].strip().lower() == "kw":
                        KWHours = True
                else:
                    self.LogError("Validation Error: Error parsing command string in GetPowerHistory (parse3): " + CmdString)
                    return msgbody

            else:
                Minutes = 0
        except Exception as e1:
            self.LogErrorLine("Error in  GetPowerHistory (Parse): %s : %s" % (CmdString,str(e1)))
            return msgbody

        try:
            # check to see if a log file exist yet
            if not os.path.isfile(self.PowerLog):
                return []

            PowerList = []

            with open(self.PowerLog,"r") as LogFile:     #opens file
                CurrentTime = datetime.datetime.now()
                try:
                    for line in LogFile:
                        line = line.strip()                  # remove whitespace at beginning and end

                        if not len(line):
                            continue
                        if line[0] == "#":                  # comment
                            continue
                        Items = line.split(",")
                        if len(Items) != 2:
                            continue

                        if Minutes:
                            struct_time = time.strptime(Items[0], "%x %X")
                            LogEntryTime = datetime.datetime.fromtimestamp(time.mktime(struct_time))
                            Delta = CurrentTime - LogEntryTime
                            if self.GetDeltaTimeMinutes(Delta) < Minutes :
                                PowerList.insert(0, [Items[0], Items[1]])
                        else:
                            PowerList.insert(0, [Items[0], Items[1]])
                    #Shorten list to 1000 if specific duration requested
                    if not KWHours and len(PowerList) > 500 and Minutes and not NoReduce:
                        PowerList = self.ReducePowerSamples(PowerList, 500)
                except Exception as e1:
                    self.LogErrorLine("Error in  GetPowerHistory (parse file): " + str(e1))
                    # continue to the next line

            if KWHours:
                TotalTime = datetime.timedelta(seconds=0)
                TotalPower = 0
                LastTime = None
                for Items in PowerList:
                    Power = float(Items[1])
                    struct_time = time.strptime(Items[0], "%x %X")
                    LogEntryTime = datetime.datetime.fromtimestamp(time.mktime(struct_time))
                    if LastTime == None or Power == 0:
                        TotalTime += LogEntryTime - LogEntryTime
                    else:
                        TotalTime += LastTime - LogEntryTime
                    LastTime = LogEntryTime

                    TotalPower += Power
                # return KW Hours
                return "%.2f" % ((TotalTime.total_seconds() / 3600) * TotalPower)

            return PowerList

        except Exception as e1:
            self.LogErrorLine("Error in  GetPowerHistory: " + str(e1))
            msgbody = "Error in  GetPowerHistory: " + str(e1)
            return msgbody

    #----------  GeneratorController::PowerMeter--------------------------------
    #----------  Monitors Power Output
    def PowerMeter(self):

        # make sure system is up and running otherwise we will not know which controller is present
        while True:
            time.sleep(1)
            if self.InitComplete:
                break
            if self.IsStopSignaled("PowerMeter"):
                return

        # if power meter is not supported do nothing.
        # Note: This is done since if we killed the thread here
        while not self.PowerMeterIsSupported() or not len(self.PowerLog):
            if self.IsStopSignaled("PowerMeter"):
                return
            time.sleep(1)

        # if log file is empty or does not exist, make a zero entry in log to denote start of collection
        if not os.path.isfile(self.PowerLog) or os.path.getsize(self.PowerLog) == 0:
            TimeStamp = datetime.datetime.now().strftime('%x %X')
            self.LogToFile(self.PowerLog, TimeStamp, "0.0")

        LastValue = 0.0
        LastPruneTime = datetime.datetime.now()
        while True:
            try:
                time.sleep(5)

                # Housekeeping on kw Log
                if self.GetDeltaTimeMinutes(datetime.datetime.now() - LastPruneTime) > 1440 :     # check every day
                    self.PrunePowerLog(43800)   # delete log entries greater than one month
                    LastPruneTime = datetime.datetime.now()

                # Time to exit?
                if self.IsStopSignaled("PowerMeter"):
                    return
                KWOut = self.removeAlpha(self.GetPowerOutput())
                KWFloat = float(KWOut)

                if LastValue == KWFloat:
                    continue

                if LastValue == 0:
                    StartTime = datetime.datetime.now() - datetime.timedelta(seconds=1)
                    TimeStamp = StartTime.strftime('%x %X')
                    self.LogToFile(self.PowerLog, TimeStamp, str(LastValue))

                LastValue = KWFloat
                # Log to file
                TimeStamp = datetime.datetime.now().strftime('%x %X')
                self.LogToFile(self.PowerLog, TimeStamp, str(KWFloat))

            except Exception as e1:
                self.LogErrorLine("Error in PowerMeter: " + str(e1))


    #----------  GeneratorController::Close-------------------------------------
    def Close(self):

        try:
            if self.ModBus != None:
                self.ModBus.Close()

            self.FeedbackPipe.Close()
            self.MessagePipe.Close()

        except Exception as e1:
            self.LogErrorLine("Error Closing Controller: " + str(e1))

        with self.CriticalLock:
            if self.log:
                self.LogError("Closing Controller")
