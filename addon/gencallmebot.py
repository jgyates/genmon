#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: gencallmebot.py
# PURPOSE: genmon.py support program to allow CallMeBot messages
# to be sent when the generator status changes
#
#  AUTHOR: Michael Buschauer - Mostly copied from gensms
#    DATE: 19-May-2023
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import json
import os
import signal
import sys
import time

import requests
import urllib.parse

try:
    # this will add the parent of the genmonlib folder to the path
    # if we are one level below the genmonlib parent (e.g. in the addon folder)
    file_root = os.path.dirname(os.path.realpath(__file__))
    parent_root = os.path.abspath(os.path.join(file_root, os.pardir))
    if os.path.isdir(os.path.join(parent_root, "genmonlib")):
        sys.path.insert(1, parent_root)

    from genmonlib.mycommon import MyCommon
    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.myclient import ClientInterface
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

# ------------ GenCallMeBotemp class -------------------------------------------
class GenCallMeBot(MySupport):

    # ------------ GenTemp::init------------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):
        
        try:
            self.log = log 
            self.console = console
            self.loglocation = loglocation
            self.ConfigFilePath = ConfigFilePath
            
            self.config = MyConfig(
                filename=os.path.join(ConfigFilePath, "gencallmebot.conf"),
                section="gencallmebot",
                log=self.log,
            )

            self.notification_type = self.config.ReadValue("notification_type", default=None)
            self.api_key = self.config.ReadValue("api_key", default=None)
            self.recipient_number = self.config.ReadValue("recipient_number", default=None)
            self.username = self.config.ReadValue("username", default=None)
            self.debug = self.config.ReadValue("debug", return_type=bool, default=False)

            self.minimum_wait_between_messages = 0
            try:
                self.notification_type = self.notification_type.lower()
            except Exception as e1:
                self.LogErrorLine("Error reading gencallmebot.conf: notifcation type is not a valid string")
                sys.exit(1)
                
            if (self.notification_type.lower() == "whatsapp") or (self.notification_type.lower() == "signal"):
                if self.recipient_number == None or not len(self.recipient_number):
                    self.LogError("Error: invalid self.recipient_number setting")
                    sys.exit(2)
            if (self.notification_type.lower() == "whatsapp") or (self.notification_type.lower() == "signal") or (self.notification_type.lower() == "facebook"):
                if self.api_key == None or not len(self.api_key):
                    self.LogError("Error: invalid self.api_key setting")
                    sys.exit(2)
            if self.notification_type.lower() == "telegram":
                if self.username == None or not len(self.username):
                    self.LogError("Error: invalid username setting")
                    sys.exit(2)

            if (self.notification_type.lower() == "whatsapp"):
                self.webhook_url = "https://api.callmebot.com/whatsapp.php?phone=" + self.recipient_number + "&apikey=" + self.api_key + "&text="
            elif (self.notification_type.lower() == "facebook"):
                self.webhook_url = "https://api.callmebot.com/facebook/send.php?apikey=" + self.api_key + "&text="
            elif (self.notification_type.lower() == "telegram"):
                self.webhook_url = "http://api.callmebot.com/text.php?user=" + self.username + "&text="
            elif (self.notification_type.lower() == "signal"):
                self.minimum_wait_between_messages = 5
                self.LogDebug("SIGNAL Selected")
                # https://signal.callmebot.com/signal/send.php?phone=[phone_number]&apikey=[your_apikey]&text=[message]
                self.webhook_url = "https://signal.callmebot.com/signal/send.php?phone=" + self.recipient_number + "&apikey=" + self.api_key + "&text="
            else:  
                self.LogError("Error: invalid self.notification_type setting")
                sys.exit(2)
    
        except Exception as e1:
            self.LogErrorLine("Error reading gencallmebot.conf: " + str(e1))
            sys.exit(1)

        try:

            self.LogDebug("Type:" +  self.notification_type)
            self.Generator = ClientInterface(host=address, port=port, log=log)
            self.sitename = self.Generator.ProcessMonitorCommand("generator: getsitename")
            self.Queue = MyMsgQueue(config=self.config, log=log, callback=self.SendNotice, minimum_wait_between_messages = self.minimum_wait_between_messages)

            self.GenNotify = GenNotify(
                host=address,
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
                loglocation=self.loglocation,
                console=self.console,
                config=self.config,
            )

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

            while True:
                time.sleep(1)


        except Exception as e1:
            self.LogErrorLine("Error: " + str(e1))


    # ----------GenCallMeBotemp::SignalClose------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(1)

    # ----------GenCallMeBotemp::Close------------------------------------------
    def Close(self):

        try:
            self.GenNotify.Close()
            self.Queue.Close()
            self.Generator.Close()
        except Exception as e1:
            self.LogErrorLine("Error in Close: " + str(e1))
        sys.exit(0)


    # ----------  OnRun -------------------------------------------------------------
    def OnRun(self, Active):

        if Active:
            self.LogConsole("Generator Running")
            self.Queue.SendMessage("Generator Running")
        else:
            self.LogConsole("Generator Running End")


    # ----------  OnRunManual -------------------------------------------------------
    def OnRunManual(self,Active):

        if Active:
            self.LogConsole("Generator Running in Manual Mode")
            self.Queue.SendMessage("Generator Running in Manual Mode")
        else:
            self.LogConsole("Generator Running in Manual Mode End")


    # ----------  OnExercise --------------------------------------------------------
    def OnExercise(self, Active):

        if Active:
            self.LogConsole("Generator Exercising")
            self.Queue.SendMessage("Generator Exercising")
        else:
            self.LogConsole("Generator Exercising End")


    # ----------  OnReady -----------------------------------------------------------
    def OnReady(self, Active):

        if Active:
            self.LogConsole("Generator Ready")
            self.Queue.SendMessage("Generator Ready")
        else:
            self.LogConsole("Generator Ready End")


    # ----------  OnOff -------------------------------------------------------------
    def OnOff(self, Active):

        if Active:
            self.LogConsole("Generator Off")
            self.Queue.SendMessage("Generator Off")
        else:
            self.LogConsole("Generator Off End")


    # ----------  OnManual ----------------------------------------------------------
    def OnManual(self, Active):

        if Active:
            self.LogConsole("Generator Manual")
            self.Queue.SendMessage("Generator Manual")
        else:
            self.LogConsole("Generator Manual End")


    # ----------  OnAlarm -----------------------------------------------------------
    def OnAlarm(self, Active):

        if Active:
            self.LogConsole("Generator Alarm")
            self.Queue.SendMessage("Generator Alarm")
        else:
            self.LogConsole("Generator Alarm End")


    # ----------  OnService ---------------------------------------------------------
    def OnService(self, Active):

        if Active:
            self.LogConsole("Generator Service Due")
            self.Queue.SendMessage("Generator Service Due")
        else:
            self.LogConsole("Generator Servcie Due End")


    # ----------  OnUtilityChange ---------------------------------------------------
    def OnUtilityChange(self, Active):

        if Active:
            self.LogConsole("Utility Service is Down")
            self.Queue.SendMessage("Utility Service is Down")
        else:
            self.Queue.SendMessage("Utility Service is Up")
            self.LogConsole("Utility Service is Up")


    # ----------  OnSoftwareUpdate --------------------------------------------------
    def OnSoftwareUpdate(self, Active):

        if Active:
            self.LogConsole("Software Update Available")
            self.Queue.SendMessage("Software Update Available")
        else:
            self.Queue.SendMessage("Software Is Up To Date")
            self.LogConsole("Software Is Up To Date")


    # ----------  OnSystemHealth ----------------------------------------------------
    def OnSystemHealth(self, Notice):
        self.Queue.SendMessage("System Health : " + Notice)
        self.LogConsole("System Health : " + Notice)


    # ----------  OnFuelState -------------------------------------------------------
    def OnFuelState(self, Active):
        if Active:  # True is OK
            self.LogConsole("Fuel Level is OK")
            self.Queue.SendMessage("Fuel Level is OK")
        else:  # False = Low
            self.Queue.SendMessage("Fuel Level is Low")
            self.LogConsole("Fuel Level is Low")


    # ----------  OnPiState ---------------------------------------------------------
    def OnPiState(self, Notice):
        self.Queue.SendMessage("Pi Health : " + Notice)
        self.LogConsole("Pi Health : " + Notice)


    # ----------  SendNotice --------------------------------------------------------
    def SendNotice(self, Message):

        try:
            response = requests.post(
                self.webhook_url + urllib.parse.quote(Message)
            )
            if response.status_code != 200:
                raise ValueError(
                    "Request to callmebot returned an error %s, the response is: %s"
                    % (response.status_code, response.text)
                )
                return False
            return True

        except Exception as e1:
            self.LogErrorLine("Error in SendNotice: " + str(e1))
            return False


# ------------------- Command-line interface for gengpio ------------------------
# -------------------------------------------------------------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("gencallmebot")
    
    GenInstance = GenCallMeBot(
        log=log,
        loglocation=loglocation,
        ConfigFilePath=ConfigFilePath,
        host=address,
        port=port,
        console=console,
    )

    sys.exit(1)

