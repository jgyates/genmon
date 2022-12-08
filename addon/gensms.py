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
    from twilio.rest import Client
except Exception as e1:
    print("\n\nThis program requires the twilio module to be installed.\n")
    print(
        "Please see the project documentation at https://github.com/jgyates/genmon.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)

# ----------  Signal Handler ----------------------------------------------------
def signal_handler(signal, frame):

    try:
        GenNotify.Close()
        Queue.Close()
    except Exception as e1:
        log.error("signal_handler: " + str(e1))

    sys.exit(0)


# ----------  OnRun -------------------------------------------------------------
def OnRun(Active):

    if Active:
        console.info("Generator Running")
        Queue.SendMessage("Generator Running")
    else:
        console.info("Generator Running End")


# ----------  OnRunManual -------------------------------------------------------
def OnRunManual(Active):

    if Active:
        console.info("Generator Running in Manual Mode")
        Queue.SendMessage("Generator Running in Manual Mode")
    else:
        console.info("Generator Running in Manual Mode End")


# ----------  OnExercise --------------------------------------------------------
def OnExercise(Active):

    if Active:
        console.info("Generator Exercising")
        Queue.SendMessage("Generator Exercising")
    else:
        console.info("Generator Exercising End")


# ----------  OnReady -----------------------------------------------------------
def OnReady(Active):

    if Active:
        console.info("Generator Ready")
        Queue.SendMessage("Generator Ready")
    else:
        console.info("Generator Ready End")


# ----------  OnOff -------------------------------------------------------------
def OnOff(Active):

    if Active:
        console.info("Generator Off")
        Queue.SendMessage("Generator Off")
    else:
        console.info("Generator Off End")


# ----------  OnManual ----------------------------------------------------------
def OnManual(Active):

    if Active:
        console.info("Generator Manual")
        Queue.SendMessage("Generator Manual")
    else:
        console.info("Generator Manual End")


# ----------  OnAlarm -----------------------------------------------------------
def OnAlarm(Active):

    if Active:
        console.info("Generator Alarm")
        Queue.SendMessage("Generator Alarm")
    else:
        console.info("Generator Alarm End")


# ----------  OnService ---------------------------------------------------------
def OnService(Active):

    if Active:
        console.info("Generator Service Due")
        Queue.SendMessage("Generator Service Due")
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
        Queue.SendMessage("Software Update Available")
    else:
        Queue.SendMessage("Software Is Up To Date")
        console.info("Software Is Up To Date")


# ----------  OnSystemHealth ----------------------------------------------------
def OnSystemHealth(Notice):
    Queue.SendMessage("System Health : " + Notice)
    console.info("System Health : " + Notice)


# ----------  OnFuelState -------------------------------------------------------
def OnFuelState(Active):
    if Active:  # True is OK
        console.info("Fuel Level is OK")
        Queue.SendMessage("Fuel Level is OK")
    else:  # False = Low
        Queue.SendMessage("Fuel Level is Low")
        console.info("Fuel Level is Low")


# ----------  OnPiState ---------------------------------------------------------
def OnPiState(Notice):
    Queue.SendMessage("Pi Health : " + Notice)
    console.info("Pi Health : " + Notice)


# ----------  SendNotice --------------------------------------------------------
def SendNotice(Message):

    try:

        if sitename != None and len(sitename):
            Message = sitename + ": " + Message

        client = Client(account_sid, auth_token)

        # send to multiple recipient(s)
        for recipient in to_number_list:
            recipient = recipient.strip()
            message = client.messages.create(
                to=recipient, from_=from_number, body=Message
            )
            console.info(message.sid)
        return True
    except Exception as e1:
        log.error("Error: " + str(e1))
        console.error("Error: " + str(e1))
        return False


# ------------------- Command-line interface for gengpio ------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("gensms")

    # Set the signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:

        config = MyConfig(
            filename=os.path.join(ConfigFilePath, "gensms.conf"),
            section="gensms",
            log=log,
        )

        account_sid = config.ReadValue("accountsid", default="")
        auth_token = config.ReadValue("authtoken", default="")
        to_number = config.ReadValue("to_number", default="")
        from_number = config.ReadValue("from_number", default="")

        to_number_list = to_number.split(",")

        if (
            account_sid == ""
            or auth_token == ""
            or to_number == ""
            or from_number == ""
        ):
            log.error(
                "Missing parameter in " + os.path.join(ConfigFilePath, "gensms.conf")
            )
            console.error(
                "Missing parameter in " + os.path.join(ConfigFilePath, "gensms.conf")
            )
            sys.exit(1)

    except Exception as e1:
        log.error(
            "Error reading "
            + os.path.join(ConfigFilePath, "gensms.conf")
            + ": "
            + str(e1)
        )
        console.error(
            "Error reading "
            + os.path.join(ConfigFilePath, "gensms.conf")
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
        log.error("Error: " + str(e1))
        console.error("Error: " + str(e1))
