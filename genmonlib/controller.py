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

import threading, datetime, collections, os, time, json
# NOTE: collections OrderedDict is used for dicts that are displayed to the UI


from genmonlib.mysupport import MySupport
from genmonlib.mythread import MyThread
from genmonlib.mylog import SetupLogger
from genmonlib.program_defaults import ProgramDefaults

class GeneratorController(MySupport):
    #---------------------GeneratorController::__init__-------------------------
    def __init__(self,
        log,
        newinstall = False,
        simulation = False,
        simulationfile = None,
        message = None,
        feedback = None,
        config = None,
        ConfigFilePath = ProgramDefaults.ConfPath):

        super(GeneratorController, self).__init__(simulation = simulation)
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
        self.InitCompleteEvent = threading.Event() # Event to signal init complete
        self.CheckForAlarmEvent = threading.Event() # Event to signal checking for alarm
        self.Registers = collections.OrderedDict()         # dict for registers and values
        self.Strings = collections.OrderedDict()           # dict for registers read a string data
        self.FileData = collections.OrderedDict()          # dict for modbus file reads
        self.NotChanged = 0         # stats for registers
        self.Changed = 0            # stats for registers
        self.TotalChanged = 0.0     # ratio of changed ragisters
        self.MaintLog =  os.path.join(ConfigFilePath, "maintlog.json")
        self.MaintLogList = []
        self.MaintLock = threading.RLock()
        self.OutageLog = os.path.join(ConfigFilePath, "outage.txt")
        self.MinimumOutageDuration = 0
        self.PowerLogMaxSize = 15.0       # 15 MB max size
        self.PowerLog =  os.path.join(ConfigFilePath, "kwlog.txt")
        self.FuelLog =  os.path.join(ConfigFilePath, "fuellog.txt")
        self.FuelLock = threading.RLock()
        self.PowerLogList = []
        self.PowerLock = threading.RLock()
        self.KWHoursMonth = None
        self.FuelMonth = None
        self.RunHoursMonth = None
        self.FuelTotal  = None
        self.LastHouseKeepingTime = None
        self.TileList = []        # Tile list for GUI
        self.TankData = None
        self.ExternalDataLock = threading.RLock()
        self.ExternalTempData = None
        self.ExternalTempDataTime = None
        self.debug = False

        self.UtilityVoltsMin = 0    # Minimum reported utility voltage above threshold
        self.UtilityVoltsMax = 0    # Maximum reported utility voltage above pickup
        self.SystemInOutage = False         # Flag to signal utility power is out
        self.TransferActive = False         # Flag to signal transfer switch is allowing gen supply power
        self.ControllerSelected = None
        # The values "Unknown" are checked to validate conf file items are found
        self.FuelType = "Unknown"
        self.NominalFreq = "Unknown"
        self.NominalRPM = "Unknown"
        self.NominalKW = "Unknown"
        self.Model = "Unknown"
        self.EngineDisplacement = "Unknown"
        self.TankSize = 0
        self.UseExternalFuelData = False
        self.UseExternalCTData = False
        self.ExternalCTData = None

        self.ProgramStartTime = datetime.datetime.now()     # used for com metrics
        self.OutageStartTime = self.ProgramStartTime        # if these two are the same, no outage has occured
        self.LastOutageDuration = self.OutageStartTime - self.OutageStartTime

        try:
            self.console = SetupLogger("controller_console", log_file = "", stream = True)
            if self.config != None:
                self.SiteName = self.config.ReadValue('sitename', default = 'Home')
                self.LogLocation = self.config.ReadValue('loglocation', default = '/var/log/')
                self.UseMetric = self.config.ReadValue('metricweather', return_type = bool, default = False)
                self.EnableDebug = self.config.ReadValue('enabledebug', return_type = bool, default = False)
                self.bDisplayUnknownSensors = self.config.ReadValue('displayunknown', return_type = bool, default = False)
                self.bDisablePowerLog = self.config.ReadValue('disablepowerlog', return_type = bool, default = False)
                self.SubtractFuel = self.config.ReadValue('subtractfuel', return_type = float, default = 0.0)
                self.UserURL = self.config.ReadValue('user_url',  default = "").strip()
                self.UseExternalCTData = self.config.ReadValue('use_external_power_data', return_type = bool, default = False)
                # for gentankutil
                self.UseExternalFuelData = self.config.ReadValue('use_external_fuel_data', return_type = bool, default = False)
                if not self.UseExternalFuelData:
                    # for gentankdiy
                    self.UseExternalFuelData = self.config.ReadValue('use_external_fuel_data_diy', return_type = bool, default = False)

                self.EstimateLoad = self.config.ReadValue('estimated_load', return_type = float, default = 0.50)
                if self.EstimateLoad < 0:
                    self.EstimateLoad = 0
                if self.EstimateLoad > 1:
                    self.EstimateLoad = 1

                if self.config.HasOption('outagelog'):
                    self.OutageLog = self.config.ReadValue('outagelog')

                if self.config.HasOption('kwlog'):
                    self.PowerLog = self.config.ReadValue('kwlog')

                if self.config.HasOption('fuel_log'):
                    self.FuelLog = self.config.ReadValue('fuel_log')
                    self.FuelLog = self.FuelLog.strip()

                self.UseFuelLog = self.config.ReadValue('enable_fuel_log', return_type = bool, default = False)
                self.FuelLogFrequency = self.config.ReadValue('fuel_log_freq', return_type = float, default = 15.0)

                self.MinimumOutageDuration = self.config.ReadValue('min_outage_duration', return_type = int, default = 0)
                self.PowerLogMaxSize = self.config.ReadValue('kwlogmax', return_type = float, default = 15.0)

                if self.config.HasOption('nominalfrequency'):
                    self.NominalFreq = self.config.ReadValue('nominalfrequency')
                    if not self.StringIsInt(self.NominalFreq):
                        self.NominalFreq = "Unknown"
                if self.config.HasOption('nominalRPM'):
                    self.NominalRPM = self.config.ReadValue('nominalRPM')
                    if not self.StringIsInt(self.NominalRPM):
                        self.NominalRPM = "Unknown"
                if self.config.HasOption('nominalKW'):
                    self.NominalKW = self.config.ReadValue('nominalKW')
                    if not self.StringIsInt(self.NominalKW):
                        self.NominalKW = "Unknown"
                if self.config.HasOption('model'):
                    self.Model = self.config.ReadValue('model')

                if self.config.HasOption('controllertype'):
                    self.ControllerSelected = self.config.ReadValue('controllertype')

                if self.config.HasOption('fueltype'):
                    self.FuelType = self.config.ReadValue('fueltype')

                self.TankSize = self.config.ReadValue('tanksize', return_type = int, default  = 0)

                self.SmartSwitch = self.config.ReadValue('smart_transfer_switch', return_type = bool, default = False)

        except Exception as e1:
                self.FatalError("Missing config file or config file entries: " + str(e1))


    #----------  GeneratorController:StartCommonThreads-------------------------
    # called after get config file, starts threads common to all controllers
    def StartCommonThreads(self):

        self.Threads["CheckAlarmThread"] = MyThread(self.CheckAlarmThread, Name = "CheckAlarmThread")
        # start read thread to process incoming data commands
        self.Threads["ProcessThread"] = MyThread(self.ProcessThread, Name = "ProcessThread")

        if self.EnableDebug:        # for debugging registers
            self.Threads["DebugThread"] = MyThread(self.DebugThread, Name = "DebugThread")

        # start thread for kw log
        self.Threads["PowerMeter"] = MyThread(self.PowerMeter, Name = "PowerMeter")

        if self.UseFuelLog:
            self.Threads["FuelLogger"] = MyThread(self.FuelLogger, Name = "FuelLogger")

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
                    self.LogErrorLine("Error in Controller ProcessThread (1), continue: " + str(e1))
        except Exception as e1:
            self.LogErrorLine("Exiting Controller ProcessThread (2): " + str(e1))

    # ---------- GeneratorController:CheckAlarmThread---------------------------
    #  When signaled, this thread will check for alarms
    def CheckAlarmThread(self):

        time.sleep(.25)
        while True:
            try:
                if self.WaitForExit("CheckAlarmThread", 0.25):  #
                    return

                if self.CheckForAlarmEvent.is_set():
                    self.CheckForAlarmEvent.clear()
                    self.CheckForAlarms()

            except Exception as e1:
                self.LogErrorLine("Error in  CheckAlarmThread: " + str(e1))

    #----------  GeneratorController:TestCommand--------------------------------
    def TestCommand(self):
        return "Not Supported"

    #----------  GeneratorController:GeneratorIsRunning-------------------------
    def GeneratorIsRunning(self):

        return (self.GetBaseStatus() in ["EXERCISING", "RUNNING", "RUNNING-MANUAL"])

    #----------  GeneratorController:FuelLogger---------------------------------
    def FuelLogger(self):

        if not self.UseFuelLog:
            return

        while True:
            if self.InitComplete:
                break
            if self.WaitForExit("FuelLogger", 1):
                return

        LastFuelValue = None

        while True:
            try:
                if LastFuelValue != None and self.WaitForExit("FuelLogger", self.FuelLogFrequency * 60.0):
                    return

                if not self.ExternalFuelDataSupported() and not self.FuelTankCalculationSupported() and not self.FuelSensorSupported():
                    # this is an invalid setting so we do nothing, we do not exit to not flag a dead thread warning
                    continue

                FuelValue = self.GetFuelLevel(ReturnFloat = True)

                if FuelValue == LastFuelValue:
                    continue

                LastFuelValue = FuelValue
                TimeStamp = datetime.datetime.now().strftime('%x %X')
                with self.FuelLock:
                    self.LogToFile(self.FuelLog, TimeStamp, str(FuelValue))

            except Exception as e1:
                self.LogErrorLine("Error in  FuelLogger: " + str(e1))

    #------------ GeneratorController::ClearFuelLog-----------------------------
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

    #----------  GeneratorController:DebugThread--------------------------------
    def DebugThread(self):

        if not self.EnableDebug:
            return
        time.sleep(.25)

        if not self.ControllerSelected == None or not len(self.ControllerSelected) or self.ControllerSelected == "generac_evo_nexus":
            MaxReg = 0x400
        else:
            MaxReg == 0x2000
        self.InitCompleteEvent.wait()

        if self.IsStopping:
            return
        self.LogError("Debug Enabled")
        self.FeedbackPipe.SendFeedback("Debug Thread Starting", FullLogs = True, Always = True, Message="Starting Debug Thread")
        TotalSent = 0

        RegistersUnderTest = collections.OrderedDict()
        RegistersUnderTestData = ""

        while True:

            if self.IsStopSignaled("DebugThread"):
                return
            if TotalSent >= 5:
                self.FeedbackPipe.SendFeedback("Debug Thread Finished", Always = True, FullLogs = True, Message="Finished Debug Thread")
                if self.WaitForExit("DebugThread", 1):  #
                    return
                continue
            try:
                for Reg in range(0x0 , MaxReg):
                    if self.WaitForExit("DebugThread", 0.25):  #
                        return
                    Register = "%04x" % Reg
                    NewValue = self.ModBus.ProcessTransaction(Register, 1, skipupdate = True)
                    if not len(NewValue):
                        continue
                    OldValue = RegistersUnderTest.get(Register, "")
                    if OldValue == "":
                        RegistersUnderTest[Register] = NewValue        # first time seeing this register so add it to the list
                    elif NewValue != OldValue:
                        BitsChanged, Mask = self.GetNumBitsChanged(OldValue, NewValue)
                        RegistersUnderTestData += "Reg %s changed from %s to %s, Bits Changed: %d, Mask: %x, Engine State: %s\n" % \
                                (Register, OldValue, NewValue, BitsChanged, Mask, self.GetEngineState())
                        RegistersUnderTest[Register] = Value        # update the value

                msgbody = "\n"
                for Register, Value in RegistersUnderTest.items():
                    msgbody += self.printToString("%s:%s" % (Register, Value))

                self.FeedbackPipe.SendFeedback("Debug Thread (Registers)", FullLogs = True, Always = True, Message=msgbody, NoCheck = True)
                if len(RegistersUnderTestData):
                    self.FeedbackPipe.SendFeedback("Debug Thread (Changes)", FullLogs = True, Always = True, Message=RegistersUnderTestData, NoCheck = True)
                RegistersUnderTestData = "\n"
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
    def GetParameterLong(self, RegisterLo, RegisterHi, Label = None, Divider = None, ReturnInt = False, ReturnFloat = False):

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

            ValueLo = self.GetParameter(RegisterLo)
            ValueHi = self.GetParameter(RegisterHi)

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
                    return round(FloatValue,3)
                return "%2.1f %s" % (FloatValue, LabelStr)
            return "%d %s" % (IntValue, LabelStr)
        except Exception as e1:
            self.LogErrorLine("Error in GetParameterBit: " + str(e1))
            return DefaultReturn

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
                    return round(FloatValue,3)
                if not Label == None:
                    return "%.2f %s" % (FloatValue, Label)
                else:
                    return "%.2f" % (FloatValue)
            elif not Label == None:
                return "%d %s" % (IntValue, Label)
            else:
                return str(int(Value,16))

        except Exception as e1:
            self.LogErrorLine("Error in GetParameter: Reg: " + Register + ": " + str(e1))
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
            StartInfo["RemoteButtons"] = False

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
    def DisplayMaintenance (self, DictOut = False, JSONNum = False):
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in DisplayMaintenance: " + str(e1))

    #------------ GeneratorController::DisplayStatus ---------------------------
    def DisplayStatus(self, DictOut = False, JSONNum = False):
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in DisplayStatus: " + str(e1))

    #------------------- GeneratorController::DisplayOutage --------------------
    def DisplayOutage(self, DictOut = False, JSONNum = False):
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
    # Called every few seconds, if communictions are failing, return False, otherwise
    # True
    def ComminicationsIsActive(self):
        return False

    #----------  GeneratorController:ResetCommStats  ---------------------------
    # reset communication stats, normally just a call to
    #   self.ModBus.ResetCommStats() if modbus is used
    def ResetCommStats(self):
        self.ModBus.ResetCommStats()

    #----------  GeneratorController:RemoteButtonsSupported  --------------------
    # return true if Panel buttons are settable via the software
    def RemoteButtonsSupported(self):
        return False
    #----------  GeneratorController:PowerMeterIsSupported  --------------------
    # return true if GetPowerOutput is supported
    def PowerMeterIsSupported(self):
        return False

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

    #------------ GeneratorController:GetRunHours ------------------------------
    def GetRunHours(self):
        return "Unknown"
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

            RegValue = self.ModBus.ProcessTransaction( Register, 1, skipupdate = True)

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
                    # Three items is for duration greater than 24 hours, i.e 1 day, 08:12
                    if len(Items) < 2:
                        continue
                    strDuration = ""
                    strFuel = ""
                    if len(Items)  == 2:
                        # Only date and duration less than a day
                        strDuration = Items[1]
                    elif (len(Items) == 3) and ("day" in Items[1]):
                        #  date and outage greater than 24 hours
                        strDuration  = Items[1] + "," + Items[2]
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

                    if len(strDuration)  and len(strFuel):
                        OutageLog.insert(0, [Items[0], strDuration, strFuel])
                    elif len(strDuration):
                        OutageLog.insert(0, [Items[0], strDuration])

                    if len(OutageLog) > 100:     # limit log to 100 entries
                        OutageLog.pop()

            for Items in OutageLog:
                if len(Items) == 2:
                    LogHistory.append("%s, Duration: %s" % (Items[0], Items[1]))
                elif len(Items) == 3:
                    LogHistory.append("%s, Duration: %s, Estimated Fuel: %s" % (Items[0], Items[1], Items[2]))

            return LogHistory

        except Exception as e1:
            self.LogErrorLine("Error in  DisplayOutageHistory: " + str(e1))
            return []
    #------------ GeneratorController::LogToPowerLog----------------------------
    def LogToPowerLog(self, TimeStamp, Value):

        try:
            if len(self.PowerLogList):
                self.PowerLogList.insert(0, [TimeStamp, Value])
            self.LogToFile(self.PowerLog, TimeStamp, Value)
        except Exception as e1:
            self.LogErrorLine("Error in LogToPowerLog: " + str(e1))

    #------------ GeneratorController::GetPowerLogFileDetails-------------------
    def GetPowerLogFileDetails(self):

        if not self.PowerMeterIsSupported():
            return "Not Supported"
        try:
            LogSize = os.path.getsize(self.PowerLog)
            outstr = "%.2f MB of %.2f MB" %((float(LogSize) / (1024.0*1024.0)), self.PowerLogMaxSize )
            return outstr
        except Exception as e1:
            self.LogErrorLine("Error in GetPowerLogFileDetails : " + str(e1))
            return "Unknown"
    #------------ GeneratorController::PrunePowerLog----------------------------
    def PrunePowerLog(self, Minutes):

        if not Minutes:
            self.LogError("Clearing power log")
            return self.ClearPowerLog()

        try:

            LogSize = os.path.getsize(self.PowerLog)
            if float(LogSize) / (1024*1024) < self.PowerLogMaxSize * 0.85:
                return "OK"

            if float(LogSize) / (1024*1024) >= self.PowerLogMaxSize * 0.98:
                msgbody = "The genmon kwlog (power log) file size is 98 percent of the maximum. Once "
                msgbody += "the log reaches 100 percent of the log will be reset. This will result "
                msgbody += "inaccurate fuel estimation (if you are using this feature). You can  "
                msgbody += "either increase the size of the kwlog on the advanced settings page,"
                msgbody += "or reset your power log."
                self.MessagePipe.SendMessage("Notice: Power Log file size warning" , msgbody, msgtype = "warn", onlyonce = True)

            # is the file size too big?
            if float(LogSize) / (1024*1024) >= self.PowerLogMaxSize:
                self.ClearPowerLog()
                self.LogError("Power Log entries deleted due to size reaching maximum.")
                return "OK"

            # if we get here the power log is 85% full or greater so let's try to reduce the size by
            # deleting entires that are older than the input Minutes
            CmdString = "power_log_json=%d" % Minutes
            PowerLog = self.GetPowerHistory(CmdString, NoReduce = True)

            self.ClearPowerLog(NoCreate = True)
            # Write oldest log entries first
            for Items in reversed(PowerLog):
                self.LogToPowerLog(Items[0], Items[1])

            # Add null entry at the end
            if not os.path.isfile(self.PowerLog):
                TimeStamp = datetime.datetime.now().strftime('%x %X')
                self.LogToPowerLog(TimeStamp, "0.0")

            # if the power log is now empty add one entry
            LogSize = os.path.getsize(self.PowerLog)
            if LogSize == 0:
                TimeStamp = datetime.datetime.now().strftime('%x %X')
                self.LogToPowerLog( TimeStamp, "0.0")

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
                with self.PowerLock:
                    os.remove(self.PowerLog)
                    time.sleep(1)
            except:
                pass

            self.PowerLogList = []

            if not NoCreate:
                # add zero entry to note the start of the log
                TimeStamp = datetime.datetime.now().strftime('%x %X')
                self.LogToPowerLog( TimeStamp, "0.0")

            return "Power Log cleared"
        except Exception as e1:
            self.LogErrorLine("Error in  ClearPowerLog: " + str(e1))
            return "Error in  ClearPowerLog: " + str(e1)

    #------------ GeneratorController::ReducePowerSamples-----------------------
    def ReducePowerSamples(self, PowerList, MaxSize):

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
                return self.RemovePowerSamples(NewList, MaxSize)
        except Exception as e1:
            self.LogErrorLine("Error in RecducePowerSamples: %s" % str(e1))
            return PowerList

        return NewList

    #------------ GeneratorController::RemovePowerSamples-----------------------
    def RemovePowerSamples(self, List, MaxSize):

        import random
        try:
            NewList = List[:]
            if len(NewList) <= MaxSize:
                self.LogError("RemovePowerSamples: Error: Can't remove ")
                return NewList

            Extra = len(NewList) - MaxSize
            for Count in range(Extra):
                # assume first and last sampels are zero samples so don't select thoes
                repeat = True
                while (repeat):
                    position = random.randint(1, len(NewList) - 2)
                    if float(NewList[position][1]) != 0:
                        Entry = NewList.pop(position)
                        repeat = False

            return NewList
        except Exception as e1:
            self.LogErrorLine("Error in RemovePowerSamples: %s" % str(e1))
            return NewList

    #------------ GeneratorController::GetPowerLogForMinutes--------------------
    def GetPowerLogForMinutes(self, Minutes = 0):
        try:
            ReturnList = []
            PowerList = self.ReadPowerLogFromFile()
            if not Minutes:
                return PowerList
            CurrentTime = datetime.datetime.now()

            for Time, Power in reversed(PowerList):
                try:
                    struct_time = time.strptime(Time, "%x %X")
                    LogEntryTime = datetime.datetime.fromtimestamp(time.mktime(struct_time))
                except Exception as e1:
                    self.LogError("Error in GetPowerLogForMinutes: " + str(e1))
                    continue
                Delta = CurrentTime - LogEntryTime
                if self.GetDeltaTimeMinutes(Delta) < Minutes :
                    ReturnList.insert(0, [Time, Power])
            return ReturnList
        except Exception as e1:
            self.LogErrorLine("Error in GetPowerLogForMinutes: " + str(e1))
            return ReturnList

    #------------ GeneratorController::ReadPowerLogFromFile---------------------
    def ReadPowerLogFromFile(self, Minutes = 0, NoReduce = False):

        # check to see if a log file exist yet
        if not os.path.isfile(self.PowerLog):
            return []
        PowerList = []
        CurrentTime = datetime.datetime.now()

        # return cached list if we have read the file before
        if len(self.PowerLogList) and not Minutes:
            return self.PowerLogList
        with self.PowerLock:
            if Minutes:
                return self.GetPowerLogForMinutes(Minutes)

            try:
                with open(self.PowerLog,"r") as LogFile:     #opens file
                    for line in LogFile:
                        line = line.strip()                  # remove whitespace at beginning and end

                        if not len(line):
                            continue
                        if line[0] == "#":                  # comment
                            continue
                        Items = line.split(",")
                        if len(Items) != 2:
                            continue
                        # remove any kW labels that may be there
                        Items[1] = self.removeAlpha(Items[1])
                        PowerList.insert(0, [Items[0], Items[1]])

            except Exception as e1:
                self.LogErrorLine("Error in  ReadPowerLogFromFile (parse file): " + str(e1))

            if len(PowerList) > 500 and not NoReduce:
                PowerList = self.ReducePowerSamples(PowerList, 500)
            if not len(self.PowerLogList):
                self.PowerLogList = PowerList
        return PowerList
    #------------ GeneratorController::GetPowerHistory--------------------------
    def GetPowerHistory(self, CmdString, NoReduce = False):

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
                    elif ParseList[1].strip().lower() == "fuel":
                        FuelConsumption = True
                    elif ParseList[1].strip().lower() == "time":
                        RunHours = True
                else:
                    self.LogError("Validation Error: Error parsing command string in GetPowerHistory (parse3): " + CmdString)
                    return msgbody

            else:
                Minutes = 0
        except Exception as e1:
            self.LogErrorLine("Error in  GetPowerHistory (Parse): %s : %s" % (CmdString,str(e1)))
            return msgbody

        try:

            PowerList = self.ReadPowerLogFromFile( Minutes = Minutes)

            #Shorten list to 500 if specific duration requested
            #if not KWHours and len(PowerList) > 500 and Minutes and not NoReduce:
            if len(PowerList) > 500 and Minutes and not NoReduce:
                PowerList = self.ReducePowerSamples(PowerList, 500)

            if KWHours:
                AvgPower, TotalSeconds = self.GetAveragePower(PowerList)
                return "%.2f" % ((TotalSeconds / 3600) * AvgPower)
            if FuelConsumption:
                AvgPower, TotalSeconds = self.GetAveragePower(PowerList)
                Consumption, Label = self.GetFuelConsumption(AvgPower, TotalSeconds)
                if Consumption == None:
                    return "Unknown"
                return "%.2f %s" % (Consumption, Label)
            if RunHours:
                AvgPower, TotalSeconds = self.GetAveragePower(PowerList)
                return "%.2f" % (TotalSeconds / 60.0 / 60.0)

            return PowerList

        except Exception as e1:
            self.LogErrorLine("Error in  GetPowerHistory: " + str(e1))
            msgbody = "Error in  GetPowerHistory: " + str(e1)
            return msgbody

    #----------  GeneratorController::GetAveragePower---------------------------
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
                Power = float(Items[1])
                try:
                    # This should be date time
                    struct_time = time.strptime(Items[0], "%x %X")
                    LogEntryTime = datetime.datetime.fromtimestamp(time.mktime(struct_time))
                except Exception as e1:
                    self.LogError("Invalid time entry in power log: " + str(e1))
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
                return 0,0
            TotalPower = TotalPower / Entries
            return TotalPower, TotalTime.total_seconds()
        except Exception as e1:
            self.LogErrorLine("Error in  GetAveragePower: " + str(e1))
            return 0, 0

    #----------  GeneratorController::PowerMeter--------------------------------
    #----------  Monitors Power Output
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
            TimeStamp = datetime.datetime.now().strftime('%x %X')
            self.LogError("Creating Power Log: " + self.PowerLog)
            self.LogToPowerLog( TimeStamp, "0.0")

        LastValue = 0.0
        LastPruneTime = datetime.datetime.now()
        LastFuelCheckTime = datetime.datetime.now()
        while True:
            try:
                if self.WaitForExit("PowerMeter", 10):
                    return

                # Housekeeping on kw Log
                if LastValue == 0:
                    if self.GetDeltaTimeMinutes(datetime.datetime.now() - LastPruneTime) > 1440 :     # check every day
                        self.PrunePowerLog(60 * 24 * 30 * 36)   # delete log entries greater than three years
                        LastPruneTime = datetime.datetime.now()

                if self.GetDeltaTimeMinutes(datetime.datetime.now() - LastFuelCheckTime) > 10 :         # check 10 min
                    LastFuelCheckTime = datetime.datetime.now()
                    self.CheckFuelLevel()

                # Time to exit?
                if self.IsStopSignaled("PowerMeter"):
                    return
                KWFloat = self.GetPowerOutput(ReturnFloat = True)

                if LastValue == KWFloat:
                    continue

                if LastValue == 0:
                    StartTime = datetime.datetime.now() - datetime.timedelta(seconds=1)
                    TimeStamp = StartTime.strftime('%x %X')
                    self.LogToPowerLog( TimeStamp, str(LastValue))

                LastValue = KWFloat
                # Log to file
                TimeStamp = datetime.datetime.now().strftime('%x %X')
                self.LogToPowerLog( TimeStamp, str(KWFloat))

            except Exception as e1:
                self.LogErrorLine("Error in PowerMeter: " + str(e1))

    #----------  GeneratorController::GetFuelInTank------------------------------
    def GetFuelInTank(self, ReturnFloat = False):

        try:
            if self.TankSize == 0:
                return None

            if self.UseMetric:
                Units = "L"
            else:
                Units = "gal"

            FuelLevel = self.GetFuelLevel(ReturnFloat = True)
            FuelLevel = (FuelLevel * 0.01) * float(self.TankSize)

            if ReturnFloat:
                return float(FuelLevel)
            else:
                return "%.2f %s" % (FuelLevel, Units)
        except Exception as e1:
            self.LogErrorLine("Error in GetFuelInTank: " + str(e1))
            return None
    #----------  GeneratorController::GetFuelLevel------------------------------
    def GetFuelLevel(self, ReturnFloat = False):
        # return 0 - 100 or None

        if not self.ExternalFuelDataSupported() and not self.FuelTankCalculationSupported() and not self.FuelSensorSupported():
            return None

        if self.FuelSensorSupported():
            FuelLevel = float(self.GetFuelSensor(ReturnInt = True))
        elif self.ExternalFuelDataSupported():
            FuelLevel = self.GetExternalFuelPercentage(ReturnFloat = True)
        elif self.FuelTankCalculationSupported():
            if self.TankSize == 0:
                return None
            FuelInTank = self.GetEstimatedFuelInTank(ReturnFloat = True)

            if FuelInTank >= self.TankSize:
                FuelLevel = 100
            else:
                FuelLevel = float(FuelInTank) / float(self.TankSize) * 100
        else:
            FuelLevel = 0
        if ReturnFloat:
            return float(FuelLevel)
        else:
            return "%.2f %%" % FuelLevel
    #----------  GeneratorController::CheckFuelLevel----------------------------
    def CheckFuelLevel(self):
        try:
            if not self.ExternalFuelDataSupported() and not self.FuelTankCalculationSupported() and not self.FuelSensorSupported():
                return True

            FuelLevel = self.GetFuelLevel(ReturnFloat = True)

            if FuelLevel == None:
                return True

            if FuelLevel <= 10:    # Ten percent left
                msgbody = "Warning: The estimated fuel in the tank is at or below 10%"
                title = "Warning: Fuel Level Low (10%) at " + self.SiteName
                self.MessagePipe.SendMessage(title , msgbody, msgtype = "warn", onlyonce = True)
                return False
            elif FuelLevel <= 20:    # 20 percent left
                msgbody = "Warning: The estimated fuel in the tank is at or below 20%"
                title = "Warning: Fuel Level Low (20%) at " + self.SiteName
                self.MessagePipe.SendMessage(title , msgbody, msgtype = "warn", onlyonce = True)
                return False
            else:
                return True

        except Exception as e1:
            self.LogErrorLine("Error in CheckFuelLevel: " + str(e1))
            return True
    #----------  GeneratorController::GetEstimatedFuelInTank--------------------
    def GetEstimatedFuelInTank(self, ReturnFloat = False):

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

    #------------ Evolution:GetFuelSensor --------------------------------------
    def GetFuelSensor(self, ReturnInt = False):
        return None
    #----------  GeneratorController::FuelSensorSupported------------------------
    def FuelSensorSupported(self):
        return False
    #----------  GeneratorController::FuelTankCalculationSupported--------------
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
    #----------  GeneratorController::FuelConsumptionSupported------------------
    def FuelConsumptionSupported(self):

        if self.GetFuelConsumptionDataPoints() == None:
            return False
        else:
            return True
    #----------  GeneratorController::FuelConsumptionGaugeSupported-------------
    def FuelConsumptionGaugeSupported(self):

        if self.FuelTankCalculationSupported() and self.FuelType != "Natural Gas":
            return True
        return False

    #----------  GeneratorController::GetRemainingFuelTime------------------------
    def GetRemainingFuelTime(self, ReturnFloat = False, Actual = False):

        try:
            if not self.FuelConsumptionGaugeSupported():
                return None
            if not self.ExternalFuelDataSupported() and not self.FuelTankCalculationSupported() and not self.FuelSensorSupported():
                return None
            if self.TankSize == 0:
                return None

            FuelLevel = self.GetFuelLevel(ReturnFloat = True)
            FuelRemaining = self.TankSize * (FuelLevel / 100.0)

            if Actual:
                PowerValue = self.GetPowerOutput(ReturnFloat = True)
            else:
                PowerValue = self.EstimateLoad * int(self.NominalKW)

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
    #----------  GeneratorController::GetFuelConsumption------------------------
    def GetFuelConsumption(self, kw, seconds):
        try:
            ConsumptionData = self.GetFuelConsumptionDataPoints()

            if ConsumptionData == None or len(ConsumptionData) != 5:
                return None, ""

            Load = kw / int(self.NominalKW)
            X1 = ConsumptionData[0]
            Y1 = ConsumptionData[1]
            X2 = ConsumptionData[2]
            Y2 = ConsumptionData[3]
            Units = ConsumptionData[4]

            Slope = (Y2 - Y1) / (X2 - X1)   # Slope of fuel consumption plot (it is very close to if not linear in most cases)
            # now use point slope equation to find consumption for one hour
            # percent load is X2, Consumption is Y2, 100% (1.0) is X1 and Rate 100% is Y1
            # Y1-Y2= SLOPE(X1-X2)
            X2 = Load
            Y2 = (((Slope * X1)- (Slope * X2)) - Y1) * -1
            Consumption = Y2

            # now compensate for time
            Consumption = (seconds / 3600) * Consumption

            if self.UseMetric:
                if self.FuelType == "Natural Gas":
                    Consumption = Consumption * 0.0283168   # cubic feet to cubic meters
                    return round(Consumption, 4), "cubic meters"       # convert to Liters
                else:
                    Consumption = Consumption * 3.78541     # gal to liters
                    return round(Consumption, 4), "L"       # convert to Liters
            else:
                return round(Consumption, 4), Units
        except Exception as e1:
            self.LogErrorLine("Error in GetFuelConsumption: " + str(e1))
            return None, ""
    #----------  GeneratorController::GetFuelConsumptionDataPoints--------------
    def GetFuelConsumptionDataPoints(self):

        # Data points are expressed in a list [.50,50% fuel rate,1.0, 100% fuel rate, units]

        #The general rule of thumb for fuel consumption for diesel is 7% of the
        # rated generator output (Example: 200 kW x 7% = 1.4 gallon per hour at full load).
        # For Larger diesel generators KW * 7% = Fuel per hour
        # for 60 kw and below diesle generators KW * 8.5%  = Fuel per hour
        return None
    #----------  GeneratorController::ExternalFuelDataSupported-----------------
    def ExternalFuelDataSupported(self):
        return self.UseExternalFuelData
    #----------  GeneratorController::GetExternalFuelPercentage-----------------
    def GetExternalFuelPercentage(self, ReturnFloat = False):

        try:
            if ReturnFloat:
                DefaultReturn = 0.0
            else:
                DefaultReturn = "0"

            if not self.ExternalFuelDataSupported():
                return DefaultReturn

            if self.TankData != None:
                percentage =  self.TankData["Percentage"]
                if ReturnFloat:
                    return float(percentage)
                else:
                    return str(percentage)
            else:
                return DefaultReturn
        except Exception as e1:
            self.LogErrorLine("Error in GetExternalFuelPercentage: " + str(e1))
            return DefaultReturn
    #----------  GeneratorController::SetExternalTankData-----------------------
    def SetExternalTankData(self, command):

        try:
            CmdList = command.split("=")
            if len(CmdList) == 2:
                with self.ExternalDataLock:
                    self.TankData = json.loads(CmdList[1])
                if not self.UseExternalFuelData:
                    self.UseExternalFuelData = True
                    self.SetupTiles()
            else:
                self.LogError("Error in  SetExternalTankData: invalid input")
                return "Error"
        except Exception as e1:
            self.LogErrorLine("Error in SetExternalTankData: " + str(e1))
            return "Error"
        return "OK"

    #----------  GeneratorController::SetExternalCTData-------------------------
    def SetExternalCTData(self, command):
        try:
            CmdList = command.split("=")
            if len(CmdList) == 2:
                with self.ExternalDataLock:
                    self.ExternalCTData = json.loads(CmdList[1])
                if not self.UseExternalCTData:
                    self.UseExternalCTData = True
                    self.SetupTiles()
            else:
                self.LogError("Error in  SetExternalTankData: invalid input")
                return "Error"
        except Exception as e1:
            self.LogErrorLine("Error in SetExternalCTData: " + str(e1))
            return "Error"
        return "OK"

    #----------  GeneratorController::GetExternalCTData-------------------------
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
    #----------  GeneratorController::AddEntryToMaintLog------------------------
    def AddEntryToMaintLog(self, InputString):

        ValidInput = False
        EntryString = InputString
        if EntryString == None or not len(EntryString):
            return "Invalid input for Maintenance Log entry."

        EntryString = EntryString.strip()
        if EntryString.startswith("add_maint_log"):
            EntryString = EntryString[len('add_maint_log'):]
            EntryString = EntryString.strip()
            if EntryString.strip().startswith("="):
                EntryString = EntryString[len("="):]
                EntryString = EntryString.strip()
                ValidInput = True

        if ValidInput:
            try:
                Entry = json.loads(EntryString)
                # validate object
                if not self.ValidateMaintLogEntry(Entry):
                    return "Invalid maintenance log entry"
                self.MaintLogList.append(Entry)
                with open(self.MaintLog, 'w') as outfile:
                    json.dump(self.MaintLogList, outfile, sort_keys = True, indent = 4) #, ensure_ascii = False)
                    outfile.flush()
            except Exception as e1:
                self.LogErrorLine("Error in AddEntryToMaintLog: " + str(e1))
                return "Invalid input for Maintenance Log entry (2)."
        else:
            self.LogError("Error in AddEntryToMaintLog: invalid input: " + str(InputString))
            return "Invalid input for Maintenance Log entry (3)."
        return "OK"

    #----------  GeneratorController::ValidateMaintLogEntry---------------------
    def ValidateMaintLogEntry(self, Entry):

        try:
            # add_maint_log={"date":"01/02/2019 14:59", "type":"Repair", "comment":"Hello"}
            if not isinstance(Entry, dict):
                self.LogError("Error in ValidateMaintLogEntry: Entry is not a dict")
                return False

            if not isinstance(Entry["date"], str) and not isinstance(Entry["date"], unicode):
                self.LogError("Error in ValidateMaintLogEntry: Entry date is not a string: " + str(type(Entry["date"])))
                return False

            try:
                EntryDate = datetime.datetime.strptime(Entry["date"], "%m/%d/%Y %H:%M")
            except Exception as e1:
                self.LogErrorLine("Error in ValidateMaintLogEntry: expecting MM/DD/YYYY : " + str(e1))

            if not isinstance(Entry["type"], str) and not isinstance(Entry["type"], unicode):
                self.LogError("Error in ValidateMaintLogEntry: Entry type is not a string: " + str(type(Entry["hours"])))
                return False
            if not Entry["type"].lower() in ["maintenance", "check", "repair", "observation"]:
                self.LogError("Error in ValidateMaintLogEntry: Invalid type: " + str(Entry["type"]))

            Entry["type"] = Entry["type"].title()

            if not isinstance(Entry["hours"], int) and not isinstance(Entry["hours"], float) :
                self.LogError("Error in ValidateMaintLogEntry: Entry type is not a number: " + str(type(Entry["hours"])))
                return False
            if not isinstance(Entry["comment"], str) and not isinstance(Entry["comment"], unicode):
                self.LogError("Error in ValidateMaintLogEntry: Entry comment is not a string: " + str(type(Entry["comment"])))

        except Exception as e1:
            self.LogErrorLine("Error in ValidateMaintLogEntry: " + str(e1))
            return False

        return True
    #----------  GeneratorController::GetMaintLogJSON---------------------------
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

    #----------  GeneratorController::GetMaintLogDict---------------------------
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

    #----------  GeneratorController::UpdateMaintLog----------------------------
    def SaveMaintLog(self, NewLog):
        try:
            self.MaintLogList = NewLog
            with open(self.MaintLog, 'w') as outfile:
                json.dump(self.MaintLogList, outfile, sort_keys = True, indent = 4) #, ensure_ascii = False)
                outfile.flush()

        except Exception as e1:
            self.LogErrorLine("Error in SaveMaintLog: " + str(e1))
            return "Error in SaveMaintLog: " + str(e1)
    #----------  GeneratorController::ClearMaintLog-------------------------------
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

    #----------  GeneratorController::EditMaintLogRow---------------------------
    def EditMaintLogRow(self, InputString):

        # { index : {maint log entry}}
        ValidInput = False
        EntryString = InputString
        if EntryString == None or not len(EntryString):
            return "Invalid input for Edit Maintenance Log entry."

        EntryString = EntryString.strip()
        if EntryString.startswith("edit_row_maint_log"):
            EntryString = EntryString[len('edit_row_maint_log'):]
            EntryString = EntryString.strip()
            if EntryString.strip().startswith("="):
                EntryString = EntryString[len("="):]
                EntryString = EntryString.strip()
                ValidInput = True

        if ValidInput:
            try:
                EntryDict = json.loads(EntryString)
                MaintLog = self.GetMaintLogDict()
                for index, Entry in EntryDict.items():
                    # validate object
                    if not self.ValidateMaintLogEntry(Entry):
                        self.LogError("Error in EditMaintLogRow: failed validate entry in update")
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
            self.LogError("Error in EditMaintLogRow: invalid input: " + str(InputString))
            return "Invalid input for Edit Maintenance Log entry (3)."
        return "OK"

    #----------  GeneratorController::DeleteMaintLogRow-------------------------
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
                self.LogError("Error in  DeleteMaintLogRow: invalid input: " + str(CmdList))
                return "Error"
        except Exception as e1:
            self.LogErrorLine("Error in DeleteMaintLogRow: " + str(e1))
            return "Error in DeleteMaintLogRow: " + str(e1)
        return "OK"
    #----------  GeneratorController::SetExternalTemperatureData----------------
    def SetExternalTemperatureData(self, command):

        try:
            if not isinstance(command, str) and not isinstance(command, unicode) :
                self.LogErrorLine("Error in SetExternalTemperatureData, invalid data: " + str(type(command)))
                return "Error"

            with self.ExternalDataLock:
                CmdList = command.split("=")
                if len(CmdList) == 2:
                    self.ExternalTempData = json.loads(CmdList[1])
                    self.ExternalTempDataTime = datetime.datetime.now()
                else:
                    self.LogError("Error in  SetExternalTemperatureData: invalid input: " + str(len(CmdList)))
                    return "Error"

        except Exception as e1:
            self.LogErrorLine("Error in SetExternalTemperatureData: " + str(e1))
            return "Error"

        return "OK"

    #----------  GeneratorController::Close-------------------------------------
    def Close(self):

        try:
            # Controller
            self.IsStopping = True
            try:
                self.InitCompleteEvent.set()
            except:
                pass

            if self.ModBus != None:
                try:
                    self.ModBus.Close()
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
                self.KillThread("PowerMeter")
            except:
                pass

        except Exception as e1:
            self.LogErrorLine("Error Closing Controller: " + str(e1))

        with self.CriticalLock:
            self.InitComplete = False
