#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: genemail2sms.py
# PURPOSE: genemail2sms.py support program to allow SMS (txt messages)
# to be sent when the generator status changes via email to sms carrier support
#
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
    from genmonlib.myconfig import MyConfig
    from genmonlib.mymail import MyMail
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


# ------------ GenEmail2SMS class -----------------------------------------------
class GenEmail2SMS(MySupport):

    # ------------ GenEmail2SMS::init--------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):

        super(GenEmail2SMS, self).__init__()

        self.LogFileName = os.path.join(loglocation, "genemail2sms.log")
        # log errors in this module to a file
        self.log = log
        self.console = console

        self.ConfigFilePath = ConfigFilePath
        self.MonitorAddress = host
        self.debug = False
        self.SiteName = None
        self.DestinationEmail = ""
        self.Mail = None
        self.Notify = None

        if self.MonitorAddress != None:
            self.MonitorAddress = self.MonitorAddress.strip()

        if self.MonitorAddress == None or not len(self.MonitorAddress):
            self.MonitorAddress = ProgramDefaults.LocalHost

        for required_file in ["genmon.conf", "mymail.conf"]:
            required_path = os.path.join(ConfigFilePath, required_file)
            if not os.path.isfile(required_path):
                self.LogConsole("Missing config file : " + required_path)
                self.LogError("Missing config file : " + required_path)
                sys.exit(1)

        configfile = os.path.join(ConfigFilePath, "genemail2sms.conf")
        try:
            self.SiteName = self.GetSiteName()

            self.config = MyConfig(
                filename=configfile, section="genemail2sms", log=self.log
            )

            self.DestinationEmail = self.config.ReadValue("destination", default="")

            if self.DestinationEmail == "" or (not "@" in self.DestinationEmail):
                self.LogError("Missing parameter in " + configfile)
                self.LogConsole("Missing parameter in " + configfile)
                sys.exit(1)

            # init mail, start processing incoming email
            self.Mail = MyMail(
                loglocation=loglocation, log=self.log, ConfigFilePath=ConfigFilePath
            )
        except Exception as e1:
            self.LogErrorLine("Error reading " + configfile + ": " + str(e1))
            self.LogConsole("Error reading " + configfile + ": " + str(e1))
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
                config=self.config,
            )

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

        except Exception as e1:
            self.LogErrorLine("Error in GenEmail2SMS init: " + str(e1))
            self.LogConsole("Error in GenEmail2SMS init: " + str(e1))
            sys.exit(1)

    # ----------  GenEmail2SMS::GetSiteName -------------------------------------
    def GetSiteName(self):

        try:
            localconfig = MyConfig(
                filename=os.path.join(self.ConfigFilePath, "genmon.conf"),
                section="GenMon",
                log=self.log,
            )
            return localconfig.ReadValue("sitename", default=None)
        except Exception as e1:
            self.LogErrorLine("Error in GetSiteName: " + str(e1))
            self.LogConsole("Error in GetSiteName: " + str(e1))
            return None

    # ----------  GenEmail2SMS::SendNotice --------------------------------------
    def SendNotice(self, Message):

        try:
            if self.SiteName != None and self.SiteName != "":
                Subject = "Generator Notice at " + self.SiteName
            else:
                Subject = "Generator Notice"
            self.Mail.sendEmail(Subject, Message, recipient=self.DestinationEmail)

        except Exception as e1:
            self.LogErrorLine("Error in SendNotice: " + str(e1))
            self.LogConsole("Error in SendNotice: " + str(e1))

    # ----------  GenEmail2SMS::NotifyState -------------------------------------
    # common handler for simple on / off state callbacks
    def NotifyState(self, Active, Message):

        if Active:
            self.LogConsole(Message)
            self.SendNotice(Message)
        else:
            self.LogConsole(Message + " End")

    # ----------  GenEmail2SMS::OnRun -------------------------------------------
    def OnRun(self, Active):
        self.NotifyState(Active, "Generator Running")

    # ----------  GenEmail2SMS::OnRunManual -------------------------------------
    def OnRunManual(self, Active):
        self.NotifyState(Active, "Generator Running in Manual Mode")

    # ----------  GenEmail2SMS::OnExercise --------------------------------------
    def OnExercise(self, Active):
        self.NotifyState(Active, "Generator Exercising")

    # ----------  GenEmail2SMS::OnReady -----------------------------------------
    def OnReady(self, Active):
        self.NotifyState(Active, "Generator Ready")

    # ----------  GenEmail2SMS::OnOff -------------------------------------------
    def OnOff(self, Active):
        self.NotifyState(Active, "Generator Off")

    # ----------  GenEmail2SMS::OnManual ----------------------------------------
    def OnManual(self, Active):
        self.NotifyState(Active, "Generator Manual")

    # ----------  GenEmail2SMS::OnAlarm -----------------------------------------
    def OnAlarm(self, Active):
        self.NotifyState(Active, "Generator Alarm")

    # ----------  GenEmail2SMS::OnService ---------------------------------------
    def OnService(self, Active):
        self.NotifyState(Active, "Generator Service Due")

    # ----------  GenEmail2SMS::OnUtilityChange ---------------------------------
    def OnUtilityChange(self, Active):

        if Active:
            Message = "Utility Service is Down"
        else:
            Message = "Utility Service is Up"
        self.LogConsole(Message)
        self.SendNotice(Message)

    # ----------  GenEmail2SMS::OnSoftwareUpdate --------------------------------
    def OnSoftwareUpdate(self, Active):

        if Active:
            Message = "Software Update Available"
        else:
            Message = "Software Is Up To Date"
        self.LogConsole(Message)
        self.SendNotice(Message)

    # ----------  GenEmail2SMS::OnSystemHealth ----------------------------------
    def OnSystemHealth(self, Notice):

        self.LogConsole("System Health : " + Notice)
        self.SendNotice("System Health : " + Notice)

    # ----------  GenEmail2SMS::OnFuelState -------------------------------------
    def OnFuelState(self, Active):

        if Active:  # True is OK
            Message = "Fuel Level is OK"
        else:  # False = Low
            Message = "Fuel Level is Low"
        self.LogConsole(Message)
        self.SendNotice(Message)

    # ----------  GenEmail2SMS::OnPiState ---------------------------------------
    def OnPiState(self, Notice):

        self.LogConsole("Pi Health : " + Notice)
        self.SendNotice("Pi Health : " + Notice)

    # ----------GenEmail2SMS::SignalClose----------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(0)

    # ----------GenEmail2SMS::Close----------------------------------------------
    def Close(self):

        try:
            if self.Notify != None:
                self.Notify.Close()
            if self.Mail != None:
                self.Mail.Close()
        except Exception as e1:
            self.LogErrorLine("Error in Close: " + str(e1))


# -------------------------------------------------------------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("genemail2sms")

    GenEmail2SMSInstance = GenEmail2SMS(
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
