#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: genpushover.py
# PURPOSE: genpushover.py sends Push notifications to Android, iOS and Desktop
#
#  AUTHOR: Stephen Bader - Stole a lot of code from gensms.py
#    DATE: 09-09-2017
#
# MODIFICATIONS:
#------------------------------------------------------------

import datetime, time, sys, signal, os, threading, socket
import atexit

try:
    from genmonlib import mynotify, mylog
except:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    sys.exit(2)


try:
    from ConfigParser import RawConfigParser
except ImportError as e:
    from configparser import RawConfigParser

from chump import Application


#----------  Signal Handler ------------------------------------------
def signal_handler(signal, frame):

    GenNotify.Close()
    sys.exit(0)

#----------  OnRun ------------------------------------------
def OnRun(Active):

    if Active:
        print ("Generator Running")
        SendNotice("Generator Running")
    else:
        print ("Generator Running End")

#----------  OnRunManual ------------------------------------------
def OnRunManual(Active):

    if Active:
        print ("Generator Running in Manual Mode")
        SendNotice("Generator Running in Manual Mode")
    else:
        print ("Generator Running in Manual Mode End")

#----------  OnExercise ------------------------------------------
def OnExercise(Active):

    if Active:
        print ("Generator Exercising")
        SendNotice("Generator Exercising")
    else:
        print ("Generator Exercising End")

#----------  OnReady ------------------------------------------
def OnReady(Active):

    if Active:
        print ("Generator Ready")
        SendNotice("Generator Ready")
    else:
        print ("Generator Ready End")

#----------  OnOff ------------------------------------------
def OnOff(Active):

    if Active:
        print ("Generator Off")
        SendNotice("Generator Off")
    else:
        print ("Generator Off End")

#----------  OnManual ------------------------------------------
def OnManual(Active):

    if Active:
        print ("Generator Manual")
        SendNotice("Generator Manual")
    else:
        print ("Generator Manual End")

#----------  OnAlarm ------------------------------------------
def OnAlarm(Active):

    if Active:
        print ("Generator Alarm")
        SendNotice("Generator Alarm")
    else:
        print ("Generator Alarm End")

#----------  OnService ------------------------------------------
def OnService(Active):

    if Active:
        print ("Generator Service Due")
        SendNotice("Generator Service Due")
    else:
        print ("Generator Servcie Due End")

#----------  OnUtilityChange -------------------------------------
def OnUtilityChange(Active):

    if Active:
        print "Utility Service is Down"
        SendNotice("Utility Service is Down")
    else:
        SendNotice("Utility Service is Up")
        print "Utility Service is Up"

#----------  SendNotice ------------------------------------------
def SendNotice(Message):

    try:
	app = Application(appid)
	user = app.get_user(userid)

        message = user.create_message(
		message = Message,
		sound = pushsound)

	message.send()

        print(message.id)

    except Exception as e1:
        log.error("Error: " + str(e1))
        print ("Error: " + str(e1))

#------------------- Command-line interface for gengpio -----------------#
if __name__=='__main__': # usage program.py [server_address]
    address='127.0.0.1' if len(sys.argv)<2 else sys.argv[1]

    # Set the signal handler
    signal.signal(signal.SIGINT, signal_handler)
    log = mylog.SetupLogger("client", "/var/log/genpushover.log")

    try:

        # read config file
        config = RawConfigParser()
        # config parser reads from current directory, when running form a cron tab this is
        # not defined so we specify the full path
        config.read('/etc/genpushover.conf')

        appid = config.get('genpushover', 'appid')
        userid = config.get('genpushover', 'userid')
        pushsound = config.get('genpushover', 'pushsound')

        GenNotify = mynotify.GenNotify(
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
        print ("Error: " + str(e1))
