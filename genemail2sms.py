#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: genemail2sms.py
# PURPOSE: genemail2sms.py support program to allow SMS (txt messages)
# to be sent when the generator status changes via email to sms carrier support
#
#  AUTHOR: Jason G Yates
#    DATE: 05-Apr-2016
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import datetime, time, sys, signal, os, threading, socket
import atexit

try:
    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.mynotify import GenNotify
    from genmonlib.mymail import MyMail
except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
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
        if SiteName != None and SiteName != "":
            Subject = "Generator Notice at " + SiteName
        else:
            Subject = "Generator Notice"
        MyMail.sendEmail(Subject, Message, recipient = DestinationEmail)

    except Exception as e1:
        log.error("Error in SendNotice: " + str(e1))
        console.error("Error in SendNotice: " + str(e1))
#----------  GetSiteName -------------------------------------------------------
def GetSiteName():

    try:
        localconfig = MyConfig(filename = '/etc/genmon.conf', section = "GenMon")
        return localconfig.ReadValue('sitename', default = None)
    except Exception as e1:
        log.error("Error in GetSiteName: " + str(e1))
        console.error("Error in GetSiteName: " + str(e1))
        return None
#------------------- Command-line interface for gengpio ------------------------
if __name__=='__main__': # usage program.py [server_address]
    address='127.0.0.1' if len(sys.argv)<2 else sys.argv[1]

    # Set the signal handler
    signal.signal(signal.SIGINT, signal_handler)

    if os.geteuid() != 0:
        print("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.")
        sys.exit(2)

    console = SetupLogger("emailsms_console", log_file = "", stream = True)
    log = SetupLogger("client", "/var/log/genemail2sms.log")

    ConfigFilePath = '/etc/'
    if not os.path.isfile(ConfigFilePath + 'genmon.conf'):
        console.error("Missing config file : " + ConfigFilePath + 'genmon.conf')
        sys.exit(1)
    if not os.path.isfile(ConfigFilePath + 'mymail.conf'):
        console.error("Missing config file : " + ConfigFilePath + 'mymail.conf')
        sys.exit(1)

    try:

        SiteName = GetSiteName()
        config = MyConfig(filename = '/etc/genemail2sms.conf', section = 'genemail2sms', log = log)

        DestinationEmail = config.ReadValue('destination', default = "")

        if DestinationEmail == "" or (not "@" in DestinationEmail):
            log.error("Missing parameter in /etc/genemail2sms.conf")
            console.error("Missing parameter in /etc/genemail2sms.conf")
            sys.exit(1)

        # init mail, start processing incoming email
        MyMail = MyMail()

    except Exception as e1:
        log.error("Error reading /etc/genemail2sms.conf: " + str(e1))
        console.error("Error reading /etc/genemail2sms.conf: " + str(e1))
        sys.exit(1)
    try:
        
        GenNotify = GenNotify(
                                        host = address,
                                        onready = OnReady,
                                        onexercise = OnExercise,
                                        onrun = OnRun,
                                        onrunmanual = OnRunManual,
                                        onalarm = OnAlarm,
                                        onservice = OnService,
                                        onoff = OnOff,
                                        onmanual = OnManual,
                                        onutilitychange = OnUtilityChange,
                                        log = log)

        while True:
            time.sleep(1)

    except Exception as e1:
        log.error("Error: " + str(e1))
        console.error("Error: " + str(e1))
