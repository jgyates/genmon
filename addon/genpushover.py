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

    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.myclient import ClientInterface
    from genmonlib.mymsgqueue import MyMsgQueue
    from genmonlib.mynotify import GenNotify
    from genmonlib.mysupport import MySupport
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


# ---------------------GetErrorLine----------------------------------------------
def GetErrorLine():

    try:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        lineno = exc_tb.tb_lineno
        return fname + ":" + str(lineno)
    except Exception as e1:
        return "Unknown Line " + str(e1)


# ----------  Signal Handler ----------------------------------------------------
def signal_handler(signal, frame):

    try:
        GenNotify.Close()
        Queue.Close()
    except Exception as e1:
        log.error("signal_handler: " + str(e1) + ": " + GetErrorLine())
    sys.exit(0)


# ----------  OnRun -------------------------------------------------------------
def OnRun(Active):

    if Active:
        console.info("Generator Running")
        Queue.SendMessage("Generator Running", priority=run_state_priority)
    else:
        console.info("Generator Running End")


# ----------  OnRunManual -------------------------------------------------------
def OnRunManual(Active):

    if Active:
        console.info("Generator Running in Manual Mode")
        Queue.SendMessage(
            "Generator Running in Manual Mode", priority=run_state_priority
        )
    else:
        console.info("Generator Running in Manual Mode End")


# ----------  OnExercise --------------------------------------------------------
def OnExercise(Active):

    if Active:
        console.info("Generator Exercising")
        Queue.SendMessage("Generator Exercising", priority=run_state_priority)
    else:
        console.info("Generator Exercising End")


# ----------  OnReady -----------------------------------------------------------
def OnReady(Active):

    if Active:
        console.info("Generator Ready")
        Queue.SendMessage("Generator Ready", priority=run_state_priority)
    else:
        console.info("Generator Ready End")


# ----------  OnOff -------------------------------------------------------------
def OnOff(Active):

    if Active:
        console.info("Generator Off")
        Queue.SendMessage("Generator Off", priority=switch_state_priority)
    else:
        console.info("Generator Off End")


# ----------  OnManual ----------------------------------------------------------
def OnManual(Active):

    if Active:
        console.info("Generator Manual")
        Queue.SendMessage("Generator Manual", priority=switch_state_priority)
    else:
        console.info("Generator Manual End")


# ----------  OnAlarm -----------------------------------------------------------
def OnAlarm(Active):

    if Active:
        console.info("Generator Alarm")
        Queue.SendMessage("Generator Alarm", priority=alarm_priority)
    else:
        console.info("Generator Alarm End")


# ----------  OnService ---------------------------------------------------------
def OnService(Active):

    if Active:
        console.info("Generator Service Due")
        Queue.SendMessage("Generator Service Due", priority=service_state_priority)
    else:
        console.info("Generator Servcie Due End")


# ----------  OnUtilityChange ---------------------------------------------------
def OnUtilityChange(Active):

    if Active:
        console.info("Utility Service is Down")
        Queue.SendMessage("Utility Service is Down")
    else:
        Queue.SendMessage("Utility Service is Up")
        console.info("Utility Service is Up")


# ----------  OnSoftwareUpdate --------------------------------------------------
def OnSoftwareUpdate(Active):

    if Active:
        console.info("Software Update Available")
        Queue.SendMessage("Software Update Available", priority=sw_update_priority)
    else:
        Queue.SendMessage("Software Is Up To Date")
        console.info("Software Is Up To Date")


# ----------  OnSystemHealth ----------------------------------------------------
def OnSystemHealth(Notice):
    Queue.SendMessage("System Health : " + Notice, priority=system_health_priority)
    console.info("System Health : " + Notice)


# ----------  OnFuelState -------------------------------------------------------
def OnFuelState(Active):
    if Active:  # True is OK
        console.info("Fuel Level is OK")
        Queue.SendMessage("Fuel Level is OK", priority=fuel_priority)
    else:  # False = Low
        Queue.SendMessage("Fuel Level is Low", priority=fuel_priority)
        console.info("Fuel Level is Low")


# ----------  OnPiState ---------------------------------------------------------
def OnPiState(Notice):
    Queue.SendMessage("Pi Health : " + Notice, priority=pi_state_priority)
    console.info("Pi Health : " + Notice)


# ----------  SendNotice --------------------------------------------------------
def SendNotice(Message, **kwargs):

    # Priority
    # LOWEST = -2 #: Message priority: No sound, no vibration, no banner.
    # LOW = -1 #: Message priority: No sound, no vibration, banner.
    # NORMAL = 0 #: Message priority: Sound, vibration, and banner if outside of user's quiet hours.
    # HIGH = 1 #: Message priority: Sound, vibration, and banner regardless of user's quiet hours.
    # EMERGENCY = 2 #: Message priority: Sound, vibration, and banner regardless of user's quiet hours, and re-alerts until acknowledged.

    try:

        if sitename != None and len(sitename):
            Message = sitename + ": " + Message

        priority = chump.NORMAL
        if len(kwargs) and isinstance(kwargs, dict):
            try:
                priority = kwargs["priority"]
            except:
                priority = chump.NORMAL

        app = Application(appid)

        if app == None:
            log.error("Unable to get app context")
            return False

        if not app.is_authenticated:
            log.error("Unable to authenticate app ID")
            return False

        user = app.get_user(userid)

        if user == None:
            log.error("Unable to get user context")
            return False
        
        if not user.is_authenticated:
            log.error("Unable to authenticate user ID")
            return False

        message = user.create_message(
            message=Message, priority=priority, sound=pushsound
        )

        message.send()

        console.info(message.id)
        return True
    except Exception as e1:
        log.error("Send Notice Error: " + GetErrorLine() + ": " + str(e1))
        console.error("Send Notice Error: " + str(e1))
        return False


# ----------  GetPriorityFromConf -----------------------------------------------
def GetPriorityFromConf(conf_entry):
    try:
        priority = config.ReadValue(conf_entry, default="NORMAL")

        if priority.lower() == "lowest":
            return chump.LOWEST
        elif priority.lower() == "low":
            return chump.LOW
        elif priority.lower() == "high":
            return chump.HIGH
        elif priority.lower() == "emergency":
            return chump.EMERGENCY
        else:
            return chump.NORMAL
    except Exception as e1:
        log.error("Error in GetPriorityFromConf: " + GetErrorLine() + ": " + str(e1))
        return chump.NORMAL


# ------------------- Command-line interface for gengpio ------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("genpushover")

    # Set the signal handler
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:

        config = MyConfig(
            filename=os.path.join(ConfigFilePath, "genpushover.conf"),
            section="genpushover",
            log=log,
        )

        appid = config.ReadValue("appid", default=None)
        userid = config.ReadValue("userid", default=None)
        pushsound = config.ReadValue("pushsound", default="updown")
        pushsound = pushsound.lower()

        alarm_priority = GetPriorityFromConf("alarm_priority")
        sw_update_priority = GetPriorityFromConf("sw_update_priority")
        system_health_priority = GetPriorityFromConf("system_health_priority")
        fuel_priority = GetPriorityFromConf("fuel_priority")
        outage_priority = GetPriorityFromConf("outage_priority")
        switch_state_priority = GetPriorityFromConf("switch_state_priority")
        run_state_priority = GetPriorityFromConf("run_state_priority")
        service_state_priority = GetPriorityFromConf("service_state_priority")
        pi_state_priority = GetPriorityFromConf("pi_state_priority")

        if appid == None or not len(appid):
            log.error("Error:  invalid app ID")
            console.error("Error:  invalid app ID")
            sys.exit(2)

        if userid == None or not len(userid):
            log.error("Error:  invalid user ID")
            console.error("Error:  invalid user ID")
            sys.exit(2)

    except Exception as e1:
        log.error(
            "Error reading "
            + os.path.join(ConfigFilePath, "genpushover.conf")
            + ": "
            + str(e1)
        )
        console.error(
            "Error reading "
            + os.path.join(ConfigFilePath, "genpushover.conf")
            + ": "
            + str(e1)
        )
        sys.exit(1)
    try:
        Generator = ClientInterface(host=address, port=port, log=log)
        sitename = Generator.ProcessMonitorCommand("generator: getsitename")
        Queue = MyMsgQueue(config=config, log=log, callback=SendNotice)

        GenNotify = GenNotify(
            host=address,
            port=port,
            onready=OnReady,
            onexercise=OnExercise,
            onrun=OnRun,
            onrunmanual=OnRunManual,
            onalarm=OnAlarm,
            onservice=OnService,
            onoff=OnOff,
            onmanual=OnManual,
            onutilitychange=OnUtilityChange,
            onsoftwareupdate=OnSoftwareUpdate,
            onsystemhealth=OnSystemHealth,
            onfuelstate=OnFuelState,
            onpistate=OnPiState,
            log=log,
            loglocation=loglocation,
            console=console,
            config=config,
        )

        while True:
            time.sleep(1)

    except Exception as e1:
        log.error("Error: " + GetErrorLine() + ": " + str(e1))
        console.error("Error: " + str(e1))
