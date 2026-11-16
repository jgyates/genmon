#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: gensms.py
# PURPOSE: genmon.py support program to allow SMS (txt messages)
# to be sent when the generator status changes
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

    from genmonlib.myclient import ClientInterface
    from genmonlib.mycommon import MyCommon
    from genmonlib.myconfig import MyConfig
    from genmonlib.mymsgqueue import MyMsgQueue
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
    from twilio.rest import Client
except Exception as e1:
    print("\n\nThis program requires the twilio module to be installed.\n")
    print(
        "Please see the project documentation at https://github.com/jgyates/genmon.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)


# ------------ GenSMS class -----------------------------------------------------
class GenSMS(MySupport):

    # ------------ GenSMS::init--------------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):

        super(GenSMS, self).__init__()

        self.LogFileName = os.path.join(loglocation, "gensms.log")
        # log errors in this module to a file
        self.log = log
        self.console = console

        self.MonitorAddress = host
        self.debug = False
        self.SiteName = None
        self.ToNumberList = []
        self.Generator = None
        self.Queue = None
        self.Notify = None

        if self.MonitorAddress != None:
            self.MonitorAddress = self.MonitorAddress.strip()

        if self.MonitorAddress == None or not len(self.MonitorAddress):
            self.MonitorAddress = ProgramDefaults.LocalHost

        configfile = os.path.join(ConfigFilePath, "gensms.conf")
        try:
            self.config = MyConfig(filename=configfile, section="gensms", log=self.log)

            self.AccountSID = self.config.ReadValue("accountsid", default="")
            self.AuthToken = self.config.ReadValue("authtoken", default="")
            to_number = self.config.ReadValue("to_number", default="")
            self.FromNumber = self.config.ReadValue("from_number", default="")
            self.debug = self.config.ReadValue("debug", return_type=bool, default=False)

            # to_number may contain multiple recipients separated by commas
            self.ToNumberList = [
                number.strip() for number in to_number.split(",") if len(number.strip())
            ]

            if (
                self.AccountSID == ""
                or self.AuthToken == ""
                or not len(self.ToNumberList)
                or self.FromNumber == ""
            ):
                self.LogError("Missing parameter in " + configfile)
                self.LogConsole("Missing parameter in " + configfile)
                sys.exit(1)

        except Exception as e1:
            self.LogErrorLine("Error reading " + configfile + ": " + str(e1))
            self.LogConsole("Error reading " + configfile + ": " + str(e1))
            sys.exit(1)

        try:
            self.Generator = ClientInterface(
                host=self.MonitorAddress, port=port, log=self.log
            )
            self.SiteName = self.Generator.ProcessMonitorCommand(
                "generator: getsitename"
            )

            self.Queue = MyMsgQueue(
                config=self.config, log=self.log, callback=self.SendNotice
            )

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
            self.LogErrorLine("Error in GenSMS init: " + str(e1))
            self.LogConsole("Error in GenSMS init: " + str(e1))
            self.Close()
            sys.exit(1)

    # ----------  GenSMS::SendNotice --------------------------------------------
    # called by the message queue, return False to have the queue retry
    def SendNotice(self, Message):

        try:
            if self.SiteName != None and len(self.SiteName):
                Message = self.SiteName + ": " + Message

            client = Client(self.AccountSID, self.AuthToken)

            # send to multiple recipient(s)
            for recipient in self.ToNumberList:
                message = client.messages.create(
                    to=recipient, from_=self.FromNumber, body=Message
                )
                self.LogConsole(message.sid)
                self.LogDebug("Sent to " + recipient + ": " + Message)
            return True
        except Exception as e1:
            self.LogErrorLine("Error in SendNotice: " + str(e1))
            self.LogConsole("Error in SendNotice: " + str(e1))
            return False

    # ----------  GenSMS::QueueNotice -------------------------------------------
    def QueueNotice(self, Message):

        self.LogConsole(Message)
        self.Queue.SendMessage(Message)

    # ----------  GenSMS::NotifyState -------------------------------------------
    # common handler for simple on / off state callbacks
    def NotifyState(self, Active, Message):

        if Active:
            self.QueueNotice(Message)
        else:
            self.LogConsole(Message + " End")

    # ----------  GenSMS::OnRun -------------------------------------------------
    def OnRun(self, Active):
        self.NotifyState(Active, "Generator Running")

    # ----------  GenSMS::OnRunManual -------------------------------------------
    def OnRunManual(self, Active):
        self.NotifyState(Active, "Generator Running in Manual Mode")

    # ----------  GenSMS::OnExercise --------------------------------------------
    def OnExercise(self, Active):
        self.NotifyState(Active, "Generator Exercising")

    # ----------  GenSMS::OnReady -----------------------------------------------
    def OnReady(self, Active):
        self.NotifyState(Active, "Generator Ready")

    # ----------  GenSMS::OnOff -------------------------------------------------
    def OnOff(self, Active):
        self.NotifyState(Active, "Generator Off")

    # ----------  GenSMS::OnManual ----------------------------------------------
    def OnManual(self, Active):
        self.NotifyState(Active, "Generator Manual")

    # ----------  GenSMS::OnAlarm -----------------------------------------------
    def OnAlarm(self, Active):
        self.NotifyState(Active, "Generator Alarm")

    # ----------  GenSMS::OnService ---------------------------------------------
    def OnService(self, Active):
        self.NotifyState(Active, "Generator Service Due")

    # ----------  GenSMS::OnUtilityChange ---------------------------------------
    def OnUtilityChange(self, Active):

        if Active:
            self.QueueNotice("Utility Service is Down")
        else:
            self.QueueNotice("Utility Service is Up")

    # ----------  GenSMS::OnSoftwareUpdate --------------------------------------
    def OnSoftwareUpdate(self, Active):

        if Active:
            self.QueueNotice("Software Update Available")
        else:
            self.QueueNotice("Software Is Up To Date")

    # ----------  GenSMS::OnSystemHealth ----------------------------------------
    def OnSystemHealth(self, Notice):
        self.QueueNotice("System Health : " + Notice)

    # ----------  GenSMS::OnFuelState -------------------------------------------
    def OnFuelState(self, Active):

        if Active:  # True is OK
            self.QueueNotice("Fuel Level is OK")
        else:  # False = Low
            self.QueueNotice("Fuel Level is Low")

    # ----------  GenSMS::OnPiState ---------------------------------------------
    def OnPiState(self, Notice):
        self.QueueNotice("Pi Health : " + Notice)

    # ----------GenSMS::SignalClose----------------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(0)

    # ----------GenSMS::Close----------------------------------------------------
    def Close(self):

        for name, item in [
            ("GenNotify", self.Notify),
            ("message queue", self.Queue),
            ("generator client", self.Generator),
        ]:
            try:
                if item != None:
                    item.Close()
            except Exception as e1:
                self.LogErrorLine("Error closing " + name + ": " + str(e1))


# -------------------------------------------------------------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("gensms")

    GenSMSInstance = GenSMS(
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
