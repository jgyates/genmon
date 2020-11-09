#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: gensms.py
# PURPOSE: genmon.py support program to allow SMS (txt messages)
# to be sent when the generator status changes
#
#  AUTHOR: Jason G Yates
#    DATE: 05-Apr-2016
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import datetime, time, sys, signal, os, threading, socket
import atexit, getopt

try:
    from genmonlib.program_defaults import ProgramDefaults
    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.mynotify import GenNotify
    from genmonlib.mysupport import MySupport
except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)

try:
    from twilio.rest import Client
except Exception as e1:
    print("\n\nThis program requires the twilio module to be installed.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)

#----------  Signal Handler ----------------------------------------------------
def signal_handler(signal, frame):

    GenNotify.Close()
    sys.exit(0)

#----------  OnRun -------------------------------------------------------------
def OnRun(Active):

    if Active:
        console.info("Generator Running")
        SendNotice("Generator Running")
    else:
        console.info("Generator Running End")

#----------  OnRunManual -------------------------------------------------------
def OnRunManual(Active):

    if Active:
        console.info("Generator Running in Manual Mode")
        SendNotice("Generator Running in Manual Mode")
    else:
        console.info("Generator Running in Manual Mode End")

#----------  OnExercise --------------------------------------------------------
def OnExercise(Active):

    if Active:
        console.info("Generator Exercising")
        SendNotice("Generator Exercising")
    else:
        console.info("Generator Exercising End")

#----------  OnReady -----------------------------------------------------------
def OnReady(Active):

    if Active:
        console.info("Generator Ready")
        SendNotice("Generator Ready")
    else:
        console.info("Generator Ready End")

#----------  OnOff -------------------------------------------------------------
def OnOff(Active):

    if Active:
        console.info("Generator Off")
        SendNotice("Generator Off")
    else:
        console.info("Generator Off End")

#----------  OnManual ----------------------------------------------------------
def OnManual(Active):

    if Active:
        console.info("Generator Manual")
        SendNotice("Generator Manual")
    else:
        console.info("Generator Manual End")

#----------  OnAlarm -----------------------------------------------------------
def OnAlarm(Active):

    if Active:
        console.info("Generator Alarm")
        SendNotice("Generator Alarm")
    else:
        console.info("Generator Alarm End")

#----------  OnService ---------------------------------------------------------
def OnService(Active):

    if Active:
        console.info("Generator Service Due")
        SendNotice("Generator Service Due")
    else:
        console.info("Generator Servcie Due End")

#----------  OnUtilityChange ---------------------------------------------------
def OnUtilityChange(Active):

    if Active:
        console.info("Utility Service is Down")
        SendNotice("Utility Service is Down")
    else:
        SendNotice("Utility Service is Up")
        console.info("Utility Service is Up")

#----------  SendNotice --------------------------------------------------------
def SendNotice(Message):

    try:

        client = Client(account_sid, auth_token)

        message = client.messages.create(
            to= to_number,
            from_ = from_number,
            body = Message)

        console.info(message.sid)

    except Exception as e1:
        log.error("Error: " + str(e1))
        console.error("Error: " + str(e1))

#------------------- Command-line interface for gengpio ------------------------
if __name__=='__main__':

    console, ConfigFilePath, address, port, loglocation, log = MySupport.SetupAddOnProgram("gensms")

    # Set the signal handler
    signal.signal(signal.SIGINT, signal_handler)

    try:

        config = MyConfig(filename = os.path.join(ConfigFilePath, 'gensms.conf'), section = 'gensms', log = log)

        account_sid = config.ReadValue('accountsid', default = "")
        auth_token = config.ReadValue('authtoken', default = "")
        to_number = config.ReadValue('to_number', default = "")
        from_number = config.ReadValue('from_number', default = "")

        if account_sid == "" or auth_token == "" or to_number == "" or from_number == "":
            log.error("Missing parameter in " +  os.path.join(ConfigFilePath, 'gensms.conf'))
            console.error("Missing parameter in " +  os.path.join(ConfigFilePath, 'gensms.conf'))
            sys.exit(1)

    except Exception as e1:
        log.error("Error reading " + os.path.join(ConfigFilePath, 'gensms.conf') + ": " + str(e1))
        console.error("Error reading " + os.path.join(ConfigFilePath, 'gensms.conf') + ": " + str(e1))
        sys.exit(1)
    try:
        GenNotify = GenNotify(
                                        host = address,
                                        port = port,
                                        onready = OnReady,
                                        onexercise = OnExercise,
                                        onrun = OnRun,
                                        onrunmanual = OnRunManual,
                                        onalarm = OnAlarm,
                                        onservice = OnService,
                                        onoff = OnOff,
                                        onmanual = OnManual,
                                        onutilitychange = OnUtilityChange,
                                        log = log,
                                        loglocation = loglocation,
                                        console = console)

        while True:
            time.sleep(1)

    except Exception as e1:
        log.error("Error: " + str(e1))
        console.error("Error: " + str(e1))
