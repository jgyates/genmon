#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: controller.py
# PURPOSE: Controller Specific Detils for Base Class
#
#  AUTHOR: Jason G Yates
#    DATE: 24-Apr-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import threading, datetime
import mysupport, mypipe

class GeneratorController(mysupport.MySupport):
    #---------------------GeneratorController::__init__-------------------------
    def __init__(self, log, newinstall = False):
        super(GeneratorController, self).__init__()
        self.log = log
        self.NewInstall = newinstall
        self.InitComplete = False
        self.Registers = {}         # dict for registers and values
        self.RegistersUnderTest = {}# dict for registers we are testing
        self.RegistersUnderTestData = ""
        self.NotChanged = 0         # stats for registers
        self.Changed = 0            # stats for registers
        self.TotalChanged = 0.0     # ratio of changed ragisters

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
        self.FeedbackPipe = mypipe.MyPipe("Feedback", Reuse = True, log = log)
        self.MessagePipe = mypipe.MyPipe("Message", Reuse = True, log = log)

    #---------------------GeneratorController::GetConfig------------------------
    # read conf file, used internally, not called by genmon
    # return True on success, else False
    def GetConfig(self):
        True

    #---------------------GeneratorController::GetPowerOutput-------------------
    # returns current kW
    # rerturn empty string ("") if not supported,
    # return kW with units i.e. "2.45kW"
    def GetPowerOutput(self):
        return ""

    #---------------------GeneratorController::SystemInAlarm--------------------
    # return True if generator is in alarm, else False
    def SystemInAlarm(self):
        return False

    #---------------------GeneratorController::DisplayLogs----------------------
    def DisplayLogs(self, AllLogs = False, ToString = False, DictOut = False, RawOutput = False):
        pass

    #------------ GeneratorController::GetStartInfo ----------------------------
    def GetStartInfo(self):

        StartInfo = {}

        StartInfo["sitename"] = self.SiteName
        StartInfo["fueltype"] = self.FuelType
        StartInfo["model"] = self.Model
        StartInfo["nominalKW"] = self.NominalKW
        StartInfo["nominalRPM"] = self.NominalRPM
        StartInfo["nominalfrequency"] = self.NominalFreq
        StartInfo["Controller"] = "Generic Controller Name"

        return StartInfo

    #------------ GeneratorController::GetStatusForGUI -------------------------
    # return dict for GUI
    def GetStatusForGUI(self):

        Status = {}

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
        return Status

    #------------ GeneratorController::DisplayMaintenance ----------------------
    def DisplayMaintenance (self, DictOut = False):
        pass

    #------------ GeneratorController::DisplayStatus ---------------------------
    def DisplayStatus(self, DictOut = False):
        pass
    #------------ GeneratorController::DisplayMonitor --------------------------
    def DisplayMonitor(self, DictOut = False):
        pass
    #------------------- GeneratorController::DisplayOutage --------------------
    def DisplayOutage(self, DictOut = False):
        pass

    #------------ GeneratorController::DisplayRegisters ------------------------
    def DisplayRegisters(self, AllRegs = False, DictOut = False):
        pass

    #----------  GeneratorController::SetGeneratorTimeDate----------------------
    def SetGeneratorTimeDate(self):
        pass

    #----------  GeneratorController::SetGeneratorQuietMode---------------------
    def SetGeneratorQuietMode(self, CmdString):
        pass

    #----------  GeneratorController::SetGeneratorExerciseTime------------------
    def SetGeneratorExerciseTime(self, CmdString):
        pass
    #----------  GeneratorController::SetGeneratorRemoteStartStop---------------
    def SetGeneratorRemoteStartStop(self, CmdString):
        pass

    #----------  GeneratorController:GetController  ----------------------------
    def GetController(self, Actual = True):
        pass

    #----------  GeneratorController:ComminicationsIsActive  -------------------
    def ComminicationsIsActive(self):
        pass

    #----------  GeneratorController:ResetCommStats  ---------------------------
    def ResetCommStats(self):
        pass

    #----------  GeneratorController:PowerMeterIsSupported  --------------------
    def PowerMeterIsSupported(self):
        pass

    #----------  GeneratorController:GetCommStatus  ----------------------------
    def GetCommStatus(self):
        pass
    #------------ GeneratorController:GetBaseStatus ----------------------------
    def GetBaseStatus(self):
        pass

    #------------ GeneratorController:GetOneLineStatus -------------------------
    def GetOneLineStatus(self):
        pass

    #----------  Controller::Close----------------------------------------------
    def Close(self):
        pass
