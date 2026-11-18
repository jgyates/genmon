#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: genpushover.py
# PURPOSE: genpushover.py sends Push notifications to Android, iOS and Desktop
#
#  AUTHOR: Stephen Bader - Stole a lot of code from gensms.py
#    DATE: 09-09-2017
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
    import chump
    from chump import Application
except Exception as e1:
    print("\n\nThis program requires the chump module to be installed.\n")
    print(
        "Please see the project documentation at https://github.com/jgyates/genmon.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)


# ------------ GenPushover class ------------------------------------------------
class GenPushover(MySupport):

    # ------------ GenPushover::init---------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):

        super(GenPushover, self).__init__()

        self.LogFileName = os.path.join(loglocation, "genpushover.log")
        # log errors in this module to a file
        self.log = log
        self.console = console

        self.MonitorAddress = host
        self.debug = False
        self.SiteName = None
        self.Generator = None
        self.Queue = None
        self.Notify = None

        if self.MonitorAddress != None:
            self.MonitorAddress = self.MonitorAddress.strip()

        if self.MonitorAddress == None or not len(self.MonitorAddress):
            self.MonitorAddress = ProgramDefaults.LocalHost

        configfile = os.path.join(ConfigFilePath, "genpushover.conf")
        try:
            self.config = MyConfig(
                filename=configfile, section="genpushover", log=self.log
            )

            self.AppID = self.config.ReadValue("appid", default=None)
            # userid supports one or more Pushover user/group keys, separated by
            # spaces and/or commas, so notifications can be sent to multiple people
            self.UserIDs = self.ParseUserIDs(
                self.config.ReadValue("userid", default=None)
            )

            # extra_userid is an optional second group of recipients (e.g. a
            # family member) who should only receive a subset of notification
            # categories, controlled by the extra_notify_* settings below
            self.ExtraUserIDs = self.ParseUserIDs(
                self.config.ReadValue("extra_userid", default=None)
            )
            self.ExtraNotifyCategories = {}
            for category in ["error", "warn", "info", "outage", "sw_update", "pi_state"]:
                self.ExtraNotifyCategories[category] = self.config.ReadValue(
                    "extra_notify_" + category, return_type=bool, default=True
                )

            self.PushSound = self.config.ReadValue("pushsound", default="updown").lower()
            self.debug = self.config.ReadValue("debug", return_type=bool, default=False)

            self.AlarmPriority = self.GetPriorityFromConf("alarm_priority")
            self.SWUpdatePriority = self.GetPriorityFromConf("sw_update_priority")
            self.SystemHealthPriority = self.GetPriorityFromConf("system_health_priority")
            self.FuelPriority = self.GetPriorityFromConf("fuel_priority")
            self.OutagePriority = self.GetPriorityFromConf("outage_priority")
            self.SwitchStatePriority = self.GetPriorityFromConf("switch_state_priority")
            self.RunStatePriority = self.GetPriorityFromConf("run_state_priority")
            self.ServiceStatePriority = self.GetPriorityFromConf("service_state_priority")
            self.PiStatePriority = self.GetPriorityFromConf("pi_state_priority")

            if self.AppID == None or not len(self.AppID):
                self.LogError("Error: invalid app ID")
                self.LogConsole("Error: invalid app ID")
                sys.exit(2)

            if not len(self.UserIDs):
                self.LogError("Error: invalid user ID")
                self.LogConsole("Error: invalid user ID")
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
            self.LogErrorLine("Error in GenPushover init: " + str(e1))
            self.LogConsole("Error in GenPushover init: " + str(e1))
            self.Close()
            sys.exit(1)

    # ----------  GenPushover::ParseUserIDs -------------------------------------
    def ParseUserIDs(self, value):
        # Pushover user/group keys may be separated by spaces and/or commas
        if value == None:
            return []
        return [
            SingleUserID
            for SingleUserID in value.replace(",", " ").split()
            if len(SingleUserID)
        ]

    # ----------  GenPushover::GetPriorityFromConf ------------------------------
    def GetPriorityFromConf(self, conf_entry):

        try:
            priority = self.config.ReadValue(conf_entry, default="NORMAL").lower()

            if priority == "lowest":
                return chump.LOWEST
            elif priority == "low":
                return chump.LOW
            elif priority == "high":
                return chump.HIGH
            elif priority == "emergency":
                return chump.EMERGENCY
            else:
                return chump.NORMAL
        except Exception as e1:
            self.LogErrorLine("Error in GetPriorityFromConf: " + str(e1))
            return chump.NORMAL

    # ----------  GenPushover::SendNotice ---------------------------------------
    # called by the message queue, return False to have the queue retry
    def SendNotice(self, Message, **kwargs):

        # Priority
        # LOWEST = -2 #: Message priority: No sound, no vibration, no banner.
        # LOW = -1 #: Message priority: No sound, no vibration, banner.
        # NORMAL = 0 #: Message priority: Sound, vibration, and banner if outside of user's quiet hours.
        # HIGH = 1 #: Message priority: Sound, vibration, and banner regardless of user's quiet hours.
        # EMERGENCY = 2 #: Message priority: Sound, vibration, and banner regardless of user's quiet hours, and re-alerts until acknowledged.

        try:
            if self.SiteName != None and len(self.SiteName):
                Message = self.SiteName + ": " + Message

            priority = kwargs.get("priority", chump.NORMAL)
            category = kwargs.get("category", None)

            app = Application(self.AppID)

            if app == None:
                self.LogError("Unable to get app context")
                return False

            if not app.is_authenticated:
                self.LogError("Unable to authenticate app ID")
                return False

            # the users this message has not been sent to yet. The queue passes
            # the same list to each retry, so a retry is only sent to the users
            # that did not get it.
            pending = kwargs.get("pending", None)
            if pending is None:
                pending = self.GetRecipients(category)

            for SingleUserID in list(pending):
                try:
                    user = app.get_user(SingleUserID)

                    if user == None:
                        self.LogError("Unable to get user context for " + SingleUserID)
                        continue

                    if not user.is_authenticated:
                        self.LogError("Unable to authenticate user ID " + SingleUserID)
                        continue

                    message = user.create_message(
                        message=Message, priority=priority, sound=self.PushSound
                    )

                    message.send()

                    self.LogConsole(message.id)
                    pending.remove(SingleUserID)
                except Exception as e1:
                    self.LogErrorLine(
                        "Send Notice Error for user " + SingleUserID + ": " + str(e1)
                    )
                    self.LogConsole(
                        "Send Notice Error for user " + SingleUserID + ": " + str(e1)
                    )

            return not len(pending)
        except Exception as e1:
            self.LogErrorLine("Send Notice Error: " + str(e1))
            self.LogConsole("Send Notice Error: " + str(e1))
            return False

    # ----------  GenPushover::QueueNotice --------------------------------------
    def QueueNotice(self, Message, **kwargs):

        self.LogConsole(Message)
        kwargs["pending"] = self.GetRecipients(kwargs.get("category", None))
        self.Queue.SendMessage(Message, **kwargs)

    # ----------  GenPushover::GetRecipients ------------------------------------
    # userids always receives every message. extra_userids is a second,
    # optional group of recipients (e.g. a family member) who only want a subset
    # of notification categories, controlled by the extra_notify_* settings
    def GetRecipients(self, category):

        Recipients = list(self.UserIDs)
        if category == None or self.ExtraNotifyCategories.get(category, True):
            Recipients += self.ExtraUserIDs
        return Recipients

    # ----------  GenPushover::NotifyState --------------------------------------
    # common handler for simple on / off state callbacks
    def NotifyState(self, Active, Message, priority, category):

        if Active:
            self.QueueNotice(Message, priority=priority, category=category)
        else:
            self.LogConsole(Message + " End")

    # ----------  GenPushover::OnRun --------------------------------------------
    def OnRun(self, Active):
        self.NotifyState(Active, "Generator Running", self.RunStatePriority, "info")

    # ----------  GenPushover::OnRunManual --------------------------------------
    def OnRunManual(self, Active):
        self.NotifyState(
            Active, "Generator Running in Manual Mode", self.RunStatePriority, "info"
        )

    # ----------  GenPushover::OnExercise ---------------------------------------
    def OnExercise(self, Active):
        self.NotifyState(Active, "Generator Exercising", self.RunStatePriority, "info")

    # ----------  GenPushover::OnReady ------------------------------------------
    def OnReady(self, Active):
        self.NotifyState(Active, "Generator Ready", self.RunStatePriority, "info")

    # ----------  GenPushover::OnOff --------------------------------------------
    def OnOff(self, Active):
        self.NotifyState(Active, "Generator Off", self.SwitchStatePriority, "info")

    # ----------  GenPushover::OnManual -----------------------------------------
    def OnManual(self, Active):
        self.NotifyState(Active, "Generator Manual", self.SwitchStatePriority, "info")

    # ----------  GenPushover::OnAlarm ------------------------------------------
    def OnAlarm(self, Active):
        self.NotifyState(Active, "Generator Alarm", self.AlarmPriority, "error")

    # ----------  GenPushover::OnService ----------------------------------------
    def OnService(self, Active):
        self.NotifyState(
            Active, "Generator Service Due", self.ServiceStatePriority, "warn"
        )

    # ----------  GenPushover::OnUtilityChange ----------------------------------
    def OnUtilityChange(self, Active):

        if Active:
            Message = "Utility Service is Down"
        else:
            Message = "Utility Service is Up"
        self.QueueNotice(Message, priority=self.OutagePriority, category="outage")

    # ----------  GenPushover::OnSoftwareUpdate ---------------------------------
    def OnSoftwareUpdate(self, Active):

        if Active:
            self.QueueNotice(
                "Software Update Available",
                priority=self.SWUpdatePriority,
                category="sw_update",
            )
        else:
            self.QueueNotice("Software Is Up To Date", category="sw_update")

    # ----------  GenPushover::OnSystemHealth -----------------------------------
    def OnSystemHealth(self, Notice):
        self.QueueNotice(
            "System Health : " + Notice,
            priority=self.SystemHealthPriority,
            category="info",
        )

    # ----------  GenPushover::OnFuelState --------------------------------------
    def OnFuelState(self, Active):

        if Active:  # True is OK
            Message = "Fuel Level is OK"
        else:  # False = Low
            Message = "Fuel Level is Low"
        self.QueueNotice(Message, priority=self.FuelPriority, category="warn")

    # ----------  GenPushover::OnPiState ----------------------------------------
    def OnPiState(self, Notice):
        self.QueueNotice(
            "Pi Health : " + Notice, priority=self.PiStatePriority, category="pi_state"
        )

    # ----------GenPushover::SignalClose-----------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(0)

    # ----------GenPushover::Close-----------------------------------------------
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
    ) = MySupport.SetupAddOnProgram("genpushover")

    GenPushoverInstance = GenPushover(
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
