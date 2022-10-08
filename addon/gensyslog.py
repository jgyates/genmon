#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: gensyslog.py
# PURPOSE: genmon.py support program to allow SMS (txt messages)
# to be sent when the generator status changes
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

    from genmonlib.mylog import SetupLogger
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

import syslog


# ----------  Signal Handler ----------------------------------------------------
def signal_handler(signal, frame):

    GenNotify.Close()
    sys.exit(0)


# ----------  OnRun -------------------------------------------------------------
def OnRun(Active):

    if Active:
        console.info("Generator Running")
        SendNotice("Generator Running")
    else:
        console.info("Generator Running End")


# ----------  OnRunManual -------------------------------------------------------
def OnRunManual(Active):

    if Active:
        console.info("Generator Running in Manual Mode")
        SendNotice("Generator Running in Manual Mode")
    else:
        console.info("Generator Running in Manual Mode End")


# ----------  OnExercise --------------------------------------------------------
def OnExercise(Active):

    if Active:
        console.info("Generator Exercising")
        SendNotice("Generator Exercising")
    else:
        console.info("Generator Exercising End")


# ----------  OnReady -----------------------------------------------------------
def OnReady(Active):

    if Active:
        console.info("Generator Ready")
        SendNotice("Generator Ready")
    else:
        console.info("Generator Ready End")


# ----------  OnOff -------------------------------------------------------------
def OnOff(Active):

    if Active:
        console.info("Generator Off")
        SendNotice("Generator Off")
    else:
        console.info("Generator Off End")


# ----------  OnManual ----------------------------------------------------------
def OnManual(Active):

    if Active:
        console.info("Generator Manual")
        SendNotice("Generator Manual")
    else:
        console.info("Generator Manual End")


# ----------  OnAlarm -----------------------------------------------------------
def OnAlarm(Active):

    if Active:
        console.info("Generator Alarm")
        SendNotice("Generator Alarm")
    else:
        console.info("Generator Alarm End")


# ----------  OnService ---------------------------------------------------------
def OnService(Active):

    if Active:
        console.info("Generator Service Due")
        SendNotice("Generator Service Due")
    else:
        console.info("Generator Servcie Due End")


# ----------  OnUtilityChange ---------------------------------------------------
def OnUtilityChange(Active):

    if Active:
        console.info("Utility Service is Down")
        SendNotice("Utility Service is Down")
    else:
        SendNotice("Utility Service is Up")
        console.info("Utility Service is Up")


# ----------  OnSoftwareUpdate --------------------------------------------------
def OnSoftwareUpdate(Active):

    if Active:
        console.info("Software Update Available")
        SendNotice("Software Update Available")
    else:
        SendNotice("Software Is Up To Date")
        console.info("Software Is Up To Date")


# ----------  OnSystemHealth ----------------------------------------------------
def OnSystemHealth(Notice):
    SendNotice("System Health : " + Notice)
    console.info("System Health : " + Notice)


# ----------  OnFuelState -------------------------------------------------------
def OnFuelState(Active):
    if Active:  # True is OK
        console.info("Fuel Level is OK")
        SendNotice("Fuel Level is OK")
    else:  # False = Low
        SendNotice("Fuel Level is Low")
        console.info("Fuel Level is Low")


# ----------  OnPiState ---------------------------------------------------------
def OnPiState(Notice):
    SendNotice("Pi Health : " + Notice)
    console.info("Pi Health : " + Notice)


# ----------  SendNotice --------------------------------------------------------
def SendNotice(Message):

    try:

        syslog.openlog("genmon")
        syslog.syslog("%s" % Message)
        syslog.closelog()

    except Exception as e1:
        log.error("Error: " + str(e1))
        console.error("Error: " + str(e1))


# ------------------- Command-line interface for gengpio ------------------------
if __name__ == "__main__":  #

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("gensyslog")

    # Set the signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:

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
        )

        while True:
            time.sleep(1)

    except Exception as e1:
        log.error("Error: " + str(e1))
        console.error("Error: " + str(e1))
