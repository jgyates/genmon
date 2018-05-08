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

import threading, datetime, collections, os
# NOTE: collections OrderedDict is used for dicts that are displayed to the UI

try:
    from ConfigParser import RawConfigParser
except ImportError as e:
    from configparser import RawConfigParser

import mysupport, mypipe

class GeneratorController(mysupport.MySupport):
    #---------------------GeneratorController::__init__-------------------------
    def __init__(self, log, newinstall = False, simulation = False):
        super(GeneratorController, self).__init__()
        self.log = log
        self.NewInstall = newinstall
        self.Simulation = simulation
        self.Address = None
        self.SerialPort = "/dev/serial0"
        self.BaudRate = 9600
        self.InitComplete = False
        self.Registers = {}         # dict for registers and values
        self.RegistersUnderTest = {}# dict for registers we are testing
        self.RegistersUnderTestData = ""
        self.NotChanged = 0         # stats for registers
        self.Changed = 0            # stats for registers
        self.TotalChanged = 0.0     # ratio of changed ragisters
        self.EnableDebug = False    # Used for enabeling debugging
        self.OutageLog = os.path.dirname(os.path.dirname(os.path.realpath(__file__))) + "/outage.txt"
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

        self.CommAccessLock = threading.RLock()  # lock to synchronize access to the protocol comms
        self.ProgramStartTime = datetime.datetime.now()     # used for com metrics
        self.OutageStartTime = self.ProgramStartTime        # if these two are the same, no outage has occured

        # Read conf entries common to all controllers
        ConfigSection = "GenMon"
        try:
            # read config file
            config = RawConfigParser()
            # config parser reads from current directory, when running form a cron tab this is
            # not defined so we specify the full path
            config.read('/etc/genmon.conf')

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

        self.FeedbackPipe = mypipe.MyPipe("Feedback", Reuse = True, log = log, simulation = self.Simulation)
        self.MessagePipe = mypipe.MyPipe("Message", Reuse = True, log = log, simulation = self.Simulation)
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
    def GetStartInfo(self):

        StartInfo = {}
        try:
            StartInfo["sitename"] = self.SiteName
            StartInfo["fueltype"] = self.FuelType
            StartInfo["model"] = self.Model
            StartInfo["nominalKW"] = self.NominalKW
            StartInfo["nominalRPM"] = self.NominalRPM
            StartInfo["nominalfrequency"] = self.NominalFreq
            StartInfo["Controller"] = "Generic Controller Name"
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
            # Exercise Info is a dict containing the following:
            ExerciseInfo = collections.OrderedDict()
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
    def GetPowerOutput(self):
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

    #----------  GeneratorController::Close-------------------------------------
    def Close(self):

        if self.ModBus.DeviceInit:
            self.ModBus.Close()

        self.FeedbackPipe.Close()
        self.MessagePipe.Close()
