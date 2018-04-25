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
    def __init__(self, log):
        super(GeneratorController, self).__init__()
        self.log = log
        self.InitComplete = False
        self.Registers = {}         # dict for registers and values
        self.RegistersUnderTest = {}# dict for registers we are testing
        self.RegistersUnderTestData = ""
        self.NotChanged = 0         # stats for registers
        self.Changed = 0            # stats for registers
        self.TotalChanged = 0.0     # ratio of changed ragisters
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
    # rerturn empty string if not supported,
    # return kW with units i.e. "2.45kW"
    def GetPowerOutput(self):
        return ""

    #---------------------GeneratorController::GetParsedExerciseTime------------
    # return exercise time in string format:
    #     "Wednesday!14!00!On!Weekly!False"
    #     "Wednesday!14!00!On!Biweekly!False"
    def GetParsedExerciseTime(self):
        pass

    #---------------------GeneratorController::GetSwitchState-------------------
    def GetSwitchState(self):
        pass

    #---------------------GeneratorController::GetSwitchState-------------------
    def GetEngineState(self, Override = None):
        pass

    #---------------------GeneratorController::GetAlarmState--------------------
    def GetAlarmState(self):
        pass

    #---------------------GeneratorController::SystemInAlarm--------------------
    def SystemInAlarm(self):
        pass

    #---------------------GeneratorController::DisplayLogs----------------------
    def DisplayLogs(self, AllLogs = False, ToString = False, DictOut = False, RawOutput = False):
        pass

    #------------ GeneratorController::GetStartInfo ----------------------------
    def GetStartInfo(self):
        pass

    #------------ GeneratorController::GetStatusForGUI -------------------------
    def GetStatusForGUI(self):
        pass
    #------------ GeneratorController::DisplayMaintenance ----------------------
    def DisplayMaintenance (self, ToString = False, DictOut = False):
        pass

    #------------ GeneratorController::DisplayStatus ---------------------------
    def DisplayStatus(self, ToString = False, DictOut = False):
        pass
    #------------ GeneratorController::DisplayMonitor --------------------------
    def DisplayMonitor(self, ToString = False, DictOut = False):
        pass
    #------------------- GeneratorController::DisplayOutage --------------------
    def DisplayOutage(self, ToString = False, DictOut = False):
        pass

    #------------ GeneratorController::DisplayRegisters ------------------------
    def DisplayRegisters(self, AllRegs = False, ToString = False, DictOut = False):
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

    #----------  Controller::Close----------------------------------------------
    def Close(self):
        pass
