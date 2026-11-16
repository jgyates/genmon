#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: gensms_voip.py
# PURPOSE: genmon.py support program to allow SMS (txt messages)
# to be sent when the generator status changes. SMS is set via voip.ms service
#
#  AUTHOR: Jason G Yates
#    DATE: 08-Dec-2022
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
    from genmonlib.myvoipms import MyVoipMs
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


# ------------ GenSMSVoip class -------------------------------------------------
class GenSMSVoip(MySupport):

    # ------------ GenSMSVoip::init----------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):

        super(GenSMSVoip, self).__init__()

        self.LogFileName = os.path.join(loglocation, "gensms_voip.log")
        # log errors in this module to a file
        self.log = log
        self.console = console

        self.MonitorAddress = host
        self.debug = False
        self.SiteName = None
        self.DestinationList = []
        self.Voip = None
        self.Generator = None
        self.Queue = None
        self.Notify = None

        if self.MonitorAddress != None:
            self.MonitorAddress = self.MonitorAddress.strip()

        if self.MonitorAddress == None or not len(self.MonitorAddress):
            self.MonitorAddress = ProgramDefaults.LocalHost

        configfile = os.path.join(ConfigFilePath, "gensms_voip.conf")
        try:
            self.config = MyConfig(
                filename=configfile, section="gensms_voip", log=self.log
            )

            self.Username = self.config.ReadValue("username", default="")
            self.Password = self.config.ReadValue("password", default="")
            destination = self.config.ReadValue("destination", default="")
            did = self.config.ReadValue("did", default="")
            self.debug = self.config.ReadValue("debug", return_type=bool, default=False)

            if (
                self.Username == ""
                or self.Password == ""
                or destination == ""
                or did == ""
            ):
                self.LogError("Missing parameter in " + configfile)
                self.LogConsole("Missing parameter in " + configfile)
                sys.exit(1)

            try:
                self.DID = self.ParsePhoneNumber(did)
                for dest in destination.split(","):
                    if len(dest.strip()):
                        self.DestinationList.append(self.ParsePhoneNumber(dest))
                if not len(self.DestinationList):
                    raise Exception("No destination numbers found")
            except Exception as e1:
                message = (
                    "Invalid DID or destination phone number. DID = "
                    + str(did)
                    + " Dest = "
                    + str(destination)
                    + ", "
                    + str(e1)
                )
                self.LogError(message)
                self.LogConsole(message)
                sys.exit(1)

        except Exception as e1:
            self.LogErrorLine("Error reading " + configfile + ": " + str(e1))
            self.LogConsole("Error reading " + configfile + ": " + str(e1))
            sys.exit(1)

        try:
            self.Voip = MyVoipMs(
                log=self.log,
                console=self.console,
                username=self.Username,
                password=self.Password,
                did=self.DID,
                debug=self.debug,
            )

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
            self.LogErrorLine("Error in GenSMSVoip init: " + str(e1))
            self.LogConsole("Error in GenSMSVoip init: " + str(e1))
            self.Close()
            sys.exit(1)

    # ----------  GenSMSVoip::ParsePhoneNumber ----------------------------------
    # remove formatting characters and convert to an integer. Raises an
    # exception if the number is not valid
    def ParsePhoneNumber(self, number):

        number = number.replace("-", "").replace("+", "").strip()
        return int(number)

    # ----------  GenSMSVoip::SendNotice ----------------------------------------
    # called by the message queue, return False to have the queue retry
    def SendNotice(self, Message):

        try:
            if self.SiteName != None and len(self.SiteName):
                Message = self.SiteName + ": " + Message

            # send to multiple recipient(s)
            for recipient in self.DestinationList:
                if not self.Voip.SendSMS(destination=recipient, message=Message):
                    return False
            return True
        except Exception as e1:
            self.LogErrorLine("Error in SendNotice: " + str(e1))
            self.LogConsole("Error in SendNotice: " + str(e1))
            return False

    # ----------  GenSMSVoip::QueueNotice ---------------------------------------
    def QueueNotice(self, Message):

        self.LogConsole(Message)
        self.Queue.SendMessage(Message)

    # ----------  GenSMSVoip::NotifyState ---------------------------------------
    # common handler for simple on / off state callbacks
    def NotifyState(self, Active, Message):

        if Active:
            self.QueueNotice(Message)
        else:
            self.LogConsole(Message + " End")

    # ----------  GenSMSVoip::OnRun ---------------------------------------------
    def OnRun(self, Active):
        self.NotifyState(Active, "Generator Running")

    # ----------  GenSMSVoip::OnRunManual ---------------------------------------
    def OnRunManual(self, Active):
        self.NotifyState(Active, "Generator Running in Manual Mode")

    # ----------  GenSMSVoip::OnExercise ----------------------------------------
    def OnExercise(self, Active):
        self.NotifyState(Active, "Generator Exercising")

    # ----------  GenSMSVoip::OnReady -------------------------------------------
    def OnReady(self, Active):
        self.NotifyState(Active, "Generator Ready")

    # ----------  GenSMSVoip::OnOff ---------------------------------------------
    def OnOff(self, Active):
        self.NotifyState(Active, "Generator Off")

    # ----------  GenSMSVoip::OnManual ------------------------------------------
    def OnManual(self, Active):
        self.NotifyState(Active, "Generator Manual")

    # ----------  GenSMSVoip::OnAlarm -------------------------------------------
    def OnAlarm(self, Active):
        self.NotifyState(Active, "Generator Alarm")

    # ----------  GenSMSVoip::OnService -----------------------------------------
    def OnService(self, Active):
        self.NotifyState(Active, "Generator Service Due")

    # ----------  GenSMSVoip::OnUtilityChange -----------------------------------
    def OnUtilityChange(self, Active):

        if Active:
            self.QueueNotice("Utility Service is Down")
        else:
            self.QueueNotice("Utility Service is Up")

    # ----------  GenSMSVoip::OnSoftwareUpdate ----------------------------------
    def OnSoftwareUpdate(self, Active):

        if Active:
            self.QueueNotice("Software Update Available")
        else:
            self.QueueNotice("Software Is Up To Date")

    # ----------  GenSMSVoip::OnSystemHealth ------------------------------------
    def OnSystemHealth(self, Notice):
        self.QueueNotice("System Health : " + Notice)

    # ----------  GenSMSVoip::OnFuelState ---------------------------------------
    def OnFuelState(self, Active):

        if Active:  # True is OK
            self.QueueNotice("Fuel Level is OK")
        else:  # False = Low
            self.QueueNotice("Fuel Level is Low")

    # ----------  GenSMSVoip::OnPiState -----------------------------------------
    def OnPiState(self, Notice):
        self.QueueNotice("Pi Health : " + Notice)

    # ----------GenSMSVoip::SignalClose------------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(0)

    # ----------GenSMSVoip::Close------------------------------------------------
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
    ) = MySupport.SetupAddOnProgram("gensms_voip")

    GenSMSVoipInstance = GenSMSVoip(
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
