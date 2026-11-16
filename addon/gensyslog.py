#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: gensyslog.py
# PURPOSE: genmon.py support program to allow messages to be written to the
# system log when the generator status changes
#
#  AUTHOR: Jason G Yates
#    DATE: 29-Nov-2017
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

try:
    import syslog
except Exception as e1:
    print("\n\nThis program requires the syslog module (Linux / Unix only).\n")
    print("Error: " + str(e1))
    sys.exit(2)


# ------------ GenSyslog class --------------------------------------------------
class GenSyslog(MySupport):

    # ------------ GenSyslog::init-----------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):

        super(GenSyslog, self).__init__()

        self.LogFileName = os.path.join(loglocation, "gensyslog.log")
        # log errors in this module to a file
        self.log = log
        self.console = console

        self.MonitorAddress = host
        self.debug = False
        self.SyslogIdent = "genmon"  # name messages are tagged with in the syslog
        self.Notify = None

        if self.MonitorAddress != None:
            self.MonitorAddress = self.MonitorAddress.strip()

        if self.MonitorAddress == None or not len(self.MonitorAddress):
            self.MonitorAddress = ProgramDefaults.LocalHost

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
            )

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

        except Exception as e1:
            self.LogErrorLine("Error in GenSyslog init: " + str(e1))
            self.LogConsole("Error in GenSyslog init: " + str(e1))
            self.Close()
            sys.exit(1)

    # ----------  GenSyslog::SendNotice -----------------------------------------
    def SendNotice(self, Message):

        try:
            syslog.openlog(self.SyslogIdent)
            syslog.syslog("%s" % Message)
            syslog.closelog()

        except Exception as e1:
            self.LogErrorLine("Error in SendNotice: " + str(e1))
            self.LogConsole("Error in SendNotice: " + str(e1))

    # ----------  GenSyslog::LogNotice ------------------------------------------
    def LogNotice(self, Message):

        self.LogConsole(Message)
        self.SendNotice(Message)

    # ----------  GenSyslog::NotifyState ----------------------------------------
    # common handler for simple on / off state callbacks
    def NotifyState(self, Active, Message):

        if Active:
            self.LogNotice(Message)
        else:
            self.LogConsole(Message + " End")

    # ----------  GenSyslog::OnRun ----------------------------------------------
    def OnRun(self, Active):
        self.NotifyState(Active, "Generator Running")

    # ----------  GenSyslog::OnRunManual ----------------------------------------
    def OnRunManual(self, Active):
        self.NotifyState(Active, "Generator Running in Manual Mode")

    # ----------  GenSyslog::OnExercise -----------------------------------------
    def OnExercise(self, Active):
        self.NotifyState(Active, "Generator Exercising")

    # ----------  GenSyslog::OnReady --------------------------------------------
    def OnReady(self, Active):
        self.NotifyState(Active, "Generator Ready")

    # ----------  GenSyslog::OnOff ----------------------------------------------
    def OnOff(self, Active):
        self.NotifyState(Active, "Generator Off")

    # ----------  GenSyslog::OnManual -------------------------------------------
    def OnManual(self, Active):
        self.NotifyState(Active, "Generator Manual")

    # ----------  GenSyslog::OnAlarm --------------------------------------------
    def OnAlarm(self, Active):
        self.NotifyState(Active, "Generator Alarm")

    # ----------  GenSyslog::OnService ------------------------------------------
    def OnService(self, Active):
        self.NotifyState(Active, "Generator Service Due")

    # ----------  GenSyslog::OnUtilityChange ------------------------------------
    def OnUtilityChange(self, Active):

        if Active:
            self.LogNotice("Utility Service is Down")
        else:
            self.LogNotice("Utility Service is Up")

    # ----------  GenSyslog::OnSoftwareUpdate -----------------------------------
    def OnSoftwareUpdate(self, Active):

        if Active:
            self.LogNotice("Software Update Available")
        else:
            self.LogNotice("Software Is Up To Date")

    # ----------  GenSyslog::OnSystemHealth -------------------------------------
    def OnSystemHealth(self, Notice):
        self.LogNotice("System Health : " + Notice)

    # ----------  GenSyslog::OnFuelState ----------------------------------------
    def OnFuelState(self, Active):

        if Active:  # True is OK
            self.LogNotice("Fuel Level is OK")
        else:  # False = Low
            self.LogNotice("Fuel Level is Low")

    # ----------  GenSyslog::OnPiState ------------------------------------------
    def OnPiState(self, Notice):
        self.LogNotice("Pi Health : " + Notice)

    # ----------GenSyslog::SignalClose-------------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(0)

    # ----------GenSyslog::Close-------------------------------------------------
    def Close(self):

        try:
            if self.Notify != None:
                self.Notify.Close()
        except Exception as e1:
            self.LogErrorLine("Error closing GenNotify: " + str(e1))


# -------------------------------------------------------------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("gensyslog")

    GenSyslogInstance = GenSyslog(
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
