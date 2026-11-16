#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: gensms_modem.py
# PURPOSE: genmon.py support program to allow SMS (txt messages)
# to be sent when the generator status changes. This program uses
# an expansion card to send SMS messages via cellular.
#  AUTHOR: Jason G Yates
#    DATE: 05-Apr-2016
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import os
import signal
import sys
import time

try:
    # this will add the parent of the genmonlib folder to the path
    # if we are one level below the genmonlib parent (e.g. in the addon folder)
    file_root = os.path.dirname(os.path.realpath(__file__))
    parent_root = os.path.abspath(os.path.join(file_root, os.pardir))
    if os.path.isdir(os.path.join(parent_root, "genmonlib")):
        sys.path.insert(1, parent_root)

    from genmonlib.mycommon import MyCommon
    from genmonlib.mymodem import LTEPiHat
    from genmonlib.mynotify import GenNotify
    from genmonlib.mysupport import MySupport
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


# ------------ GenSMSModem class ------------------------------------------------
class GenSMSModem(MySupport):

    # ------------ GenSMSModem::init---------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):

        super(GenSMSModem, self).__init__()

        self.LogFileName = os.path.join(loglocation, "gensms_modem.log")
        # log errors in this module to a file
        self.log = log
        self.console = console

        self.MonitorAddress = host
        self.debug = False
        self.SMS = None
        self.Notify = None

        if self.MonitorAddress != None:
            self.MonitorAddress = self.MonitorAddress.strip()

        if self.MonitorAddress == None or not len(self.MonitorAddress):
            self.MonitorAddress = ProgramDefaults.LocalHost

        try:
            self.SMS = LTEPiHat(
                log=self.log, loglocation=loglocation, ConfigFilePath=ConfigFilePath
            )
            if not self.SMS.InitComplete:
                self.SMS.Close()
                self.LogError("Modem Init FAILED!")
                self.LogConsole("Modem Init FAILED!")
                sys.exit(2)

        except Exception as e1:
            self.LogErrorLine("Error on modem init: " + str(e1))
            self.LogConsole("Error on modem init: " + str(e1))
            sys.exit(1)

        try:
            self.Notify = GenNotify(
                host=self.MonitorAddress,
                port=port,
                onready=self.OnReady,
                onexercise=self.OnExercise,
                onrun=self.OnRun,
                onrunmanual=self.OnRunManual,
                onalarm=self.OnAlarm,
                onservice=self.OnService,
                onoff=self.OnOff,
                onmanual=self.OnManual,
                onutilitychange=self.OnUtilityChange,
                onsoftwareupdate=self.OnSoftwareUpdate,
                onsystemhealth=self.OnSystemHealth,
                onfuelstate=self.OnFuelState,
                onpistate=self.OnPiState,
                log=self.log,
                loglocation=loglocation,
                console=self.console,
                config=self.SMS.GetConfig(),
            )

            self.LogError(self.SMS.GetInfo(ReturnString=True))

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

        except Exception as e1:
            self.LogErrorLine("Error in GenSMSModem init: " + str(e1))
            self.LogConsole("Error in GenSMSModem init: " + str(e1))
            self.Close()
            sys.exit(1)

    # ----------  GenSMSModem::SendNotice ---------------------------------------
    def SendNotice(self, Message):

        try:
            self.SMS.SendMessage(Message)
        except Exception as e1:
            self.LogErrorLine("Error in SendNotice: " + str(e1))
            self.LogConsole("Error in SendNotice: " + str(e1))

    # ----------  GenSMSModem::NotifyState --------------------------------------
    # common handler for simple on / off state callbacks
    def NotifyState(self, Active, Message):

        if Active:
            self.LogConsole(Message)
            self.SendNotice(Message)
        else:
            self.LogConsole(Message + " End")

    # ----------  GenSMSModem::OnRun --------------------------------------------
    def OnRun(self, Active):
        self.NotifyState(Active, "Generator Running")

    # ----------  GenSMSModem::OnRunManual --------------------------------------
    def OnRunManual(self, Active):
        self.NotifyState(Active, "Generator Running in Manual Mode")

    # ----------  GenSMSModem::OnExercise ---------------------------------------
    def OnExercise(self, Active):
        self.NotifyState(Active, "Generator Exercising")

    # ----------  GenSMSModem::OnReady ------------------------------------------
    def OnReady(self, Active):
        self.NotifyState(Active, "Generator Ready")

    # ----------  GenSMSModem::OnOff --------------------------------------------
    def OnOff(self, Active):
        self.NotifyState(Active, "Generator Off")

    # ----------  GenSMSModem::OnManual -----------------------------------------
    def OnManual(self, Active):
        self.NotifyState(Active, "Generator Manual")

    # ----------  GenSMSModem::OnAlarm ------------------------------------------
    def OnAlarm(self, Active):
        self.NotifyState(Active, "Generator Alarm")

    # ----------  GenSMSModem::OnService ----------------------------------------
    def OnService(self, Active):
        self.NotifyState(Active, "Generator Service Due")

    # ----------  GenSMSModem::OnUtilityChange ----------------------------------
    def OnUtilityChange(self, Active):

        if Active:
            Message = "Utility Service is Down"
        else:
            Message = "Utility Service is Up"
        self.LogConsole(Message)
        self.SendNotice(Message)

    # ----------  GenSMSModem::OnSoftwareUpdate ---------------------------------
    def OnSoftwareUpdate(self, Active):

        if Active:
            Message = "Software Update Available"
        else:
            Message = "Software Is Up To Date"
        self.LogConsole(Message)
        self.SendNotice(Message)

    # ----------  GenSMSModem::OnSystemHealth -----------------------------------
    def OnSystemHealth(self, Notice):

        self.LogConsole("System Health : " + Notice)
        self.SendNotice("System Health : " + Notice)

    # ----------  GenSMSModem::OnFuelState --------------------------------------
    def OnFuelState(self, Active):

        if Active:  # True is OK
            Message = "Fuel Level is OK"
        else:  # False = Low
            Message = "Fuel Level is Low"
        self.LogConsole(Message)
        self.SendNotice(Message)

    # ----------  GenSMSModem::OnPiState ----------------------------------------
    def OnPiState(self, Notice):

        self.LogConsole("Pi Health : " + Notice)
        self.SendNotice("Pi Health : " + Notice)

    # ----------GenSMSModem::SignalClose-----------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(0)

    # ----------GenSMSModem::Close-----------------------------------------------
    def Close(self):

        try:
            if self.Notify != None:
                self.Notify.Close()
        except Exception as e1:
            self.LogErrorLine("Error closing GenNotify: " + str(e1))
        try:
            if self.SMS != None:
                self.SMS.Close()
        except Exception as e1:
            self.LogErrorLine("Error closing modem: " + str(e1))


# -------------------------------------------------------------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("gensms_modem")

    GenSMSModemInstance = GenSMSModem(
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
