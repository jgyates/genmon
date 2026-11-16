#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: genslack.py
# PURPOSE: genmon.py support program to allow Slack messages
# to be sent when the generator status changes
#
#  AUTHOR: Nate Renbarger - Mostly copied from gensms
#    DATE: 20-Sep-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import json
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
    import requests
except Exception as e1:
    print("\n\nThis program requires the requests module to be installed.\n")
    print(
        "Please see the project documentation at https://github.com/jgyates/genmon.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)


# ------------ GenSlack class ---------------------------------------------------
class GenSlack(MySupport):

    # ------------ GenSlack::init------------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):

        super(GenSlack, self).__init__()

        self.LogFileName = os.path.join(loglocation, "genslack.log")
        # log errors in this module to a file
        self.log = log
        self.console = console

        self.MonitorAddress = host
        self.debug = False
        self.SiteName = None
        self.RequestTimeout = 30  # seconds to wait for a response from slack
        self.Generator = None
        self.Queue = None
        self.Notify = None

        if self.MonitorAddress != None:
            self.MonitorAddress = self.MonitorAddress.strip()

        if self.MonitorAddress == None or not len(self.MonitorAddress):
            self.MonitorAddress = ProgramDefaults.LocalHost

        configfile = os.path.join(ConfigFilePath, "genslack.conf")
        try:
            self.config = MyConfig(filename=configfile, section="genslack", log=self.log)

            self.WebhookURL = self.config.ReadValue("webhook_url", default=None)
            # optional, if blank the channel configured for the webhook is used
            self.Channel = self.config.ReadValue("channel", default=None)
            self.Username = self.config.ReadValue("username", default=None)
            self.IconEmoji = self.config.ReadValue("icon_emoji", default=":red_circle:")
            # optional, makes the message title a link
            self.TitleLink = self.config.ReadValue("title_link", default=None)
            self.debug = self.config.ReadValue("debug", return_type=bool, default=False)

            # optional in the web UI, use the default if left blank
            if self.IconEmoji == None or not len(self.IconEmoji.strip()):
                self.IconEmoji = ":red_circle:"

            for name, value in [
                ("webhook_url", self.WebhookURL),
                ("username", self.Username),
            ]:
                if value == None or not len(value.strip()):
                    self.LogError("Error: invalid " + name + " setting in " + configfile)
                    self.LogConsole("Error: invalid " + name + " setting in " + configfile)
                    sys.exit(2)

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
            self.LogErrorLine("Error in GenSlack init: " + str(e1))
            self.LogConsole("Error in GenSlack init: " + str(e1))
            self.Close()
            sys.exit(1)

    # ----------  GenSlack::SendNotice ------------------------------------------
    # called by the message queue, return False to have the queue retry
    def SendNotice(self, Message):

        try:
            if self.SiteName != None and len(self.SiteName):
                Message = self.SiteName + ": " + Message

            attachment = {
                "title": "GenMon Alert",
                "fields": [{"title": "Status", "value": Message, "short": "false"}],
            }
            if self.TitleLink != None and len(self.TitleLink.strip()):
                attachment["title_link"] = self.TitleLink.strip()

            slack_data = {
                "username": self.Username,
                "icon_emoji": self.IconEmoji,
                "attachments": [attachment],
            }
            if self.Channel != None and len(self.Channel.strip()):
                slack_data["channel"] = self.Channel.strip()

            self.LogDebug("Sending to slack: " + Message)
            response = requests.post(
                self.WebhookURL,
                data=json.dumps(slack_data),
                headers={"Content-Type": "application/json"},
                timeout=self.RequestTimeout,
            )
            if response.status_code != 200:
                self.LogError(
                    "Request to slack returned an error %s, the response is: %s"
                    % (response.status_code, response.text)
                )
                self.LogConsole(
                    "Request to slack returned an error %s" % (response.status_code)
                )
                return False
            return True

        except Exception as e1:
            self.LogErrorLine("Error in SendNotice: " + str(e1))
            self.LogConsole("Error in SendNotice: " + str(e1))
            return False

    # ----------  GenSlack::QueueNotice -----------------------------------------
    def QueueNotice(self, Message):

        self.LogConsole(Message)
        self.Queue.SendMessage(Message)

    # ----------  GenSlack::NotifyState -----------------------------------------
    # common handler for simple on / off state callbacks
    def NotifyState(self, Active, Message):

        if Active:
            self.QueueNotice(Message)
        else:
            self.LogConsole(Message + " End")

    # ----------  GenSlack::OnRun -----------------------------------------------
    def OnRun(self, Active):
        self.NotifyState(Active, "Generator Running")

    # ----------  GenSlack::OnRunManual -----------------------------------------
    def OnRunManual(self, Active):
        self.NotifyState(Active, "Generator Running in Manual Mode")

    # ----------  GenSlack::OnExercise ------------------------------------------
    def OnExercise(self, Active):
        self.NotifyState(Active, "Generator Exercising")

    # ----------  GenSlack::OnReady ---------------------------------------------
    def OnReady(self, Active):
        self.NotifyState(Active, "Generator Ready")

    # ----------  GenSlack::OnOff -----------------------------------------------
    def OnOff(self, Active):
        self.NotifyState(Active, "Generator Off")

    # ----------  GenSlack::OnManual --------------------------------------------
    def OnManual(self, Active):
        self.NotifyState(Active, "Generator Manual")

    # ----------  GenSlack::OnAlarm ---------------------------------------------
    def OnAlarm(self, Active):
        self.NotifyState(Active, "Generator Alarm")

    # ----------  GenSlack::OnService -------------------------------------------
    def OnService(self, Active):
        self.NotifyState(Active, "Generator Service Due")

    # ----------  GenSlack::OnUtilityChange -------------------------------------
    def OnUtilityChange(self, Active):

        if Active:
            self.QueueNotice("Utility Service is Down")
        else:
            self.QueueNotice("Utility Service is Up")

    # ----------  GenSlack::OnSoftwareUpdate ------------------------------------
    def OnSoftwareUpdate(self, Active):

        if Active:
            self.QueueNotice("Software Update Available")
        else:
            self.QueueNotice("Software Is Up To Date")

    # ----------  GenSlack::OnSystemHealth --------------------------------------
    def OnSystemHealth(self, Notice):
        self.QueueNotice("System Health : " + Notice)

    # ----------  GenSlack::OnFuelState -----------------------------------------
    def OnFuelState(self, Active):

        if Active:  # True is OK
            self.QueueNotice("Fuel Level is OK")
        else:  # False = Low
            self.QueueNotice("Fuel Level is Low")

    # ----------  GenSlack::OnPiState -------------------------------------------
    def OnPiState(self, Notice):
        self.QueueNotice("Pi Health : " + Notice)

    # ----------GenSlack::SignalClose--------------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(0)

    # ----------GenSlack::Close--------------------------------------------------
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
    ) = MySupport.SetupAddOnProgram("genslack")

    GenSlackInstance = GenSlack(
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
