#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: gengpio.py
# PURPOSE: genmon.py support program to allow GPIO pints to drive
# status LEDs
#
#  AUTHOR: Jason G Yates
#    DATE: 05-Apr-2016
#
# MODIFICATIONS:
#------------------------------------------------------------

import datetime, time, sys, signal, os, threading, socket
import atexit
import mynotify, mylog
import ConfigParser
from twilio.rest import Client


#----------  Signal Handler ------------------------------------------
def signal_handler(signal, frame):

    GenNotify.Close()
    sys.exit(0)

#----------  OnRun ------------------------------------------
def OnRun(Active):

    if Active:
        print "Generator Running"
        SendNotice("Generator Running")
    else:
        print "Generator Running End"

#----------  OnRun ------------------------------------------
def OnExercise(Active):

    if Active:
        print "Generator Exercising"
        SendNotice("Generator Exercising")
    else:
        print "Generator Exercising End"

#----------  OnRun ------------------------------------------
def OnReady(Active):

    if Active:
        print "Generator Ready"
        SendNotice("Generator Ready")
    else:
        print "Generator Ready End"

#----------  OnRun ------------------------------------------
def OnAlarm(Active):

    if Active:
        print "Generator Alarm"
        SendNotice("Generator Alarm")
    else:
        print "Generator Alarm End"

#----------  OnRun ------------------------------------------
def OnService(Active):

    if Active:
        print "Generator Service Due"
        SendNotice("Generator Service Due")
    else:
        print "Generator Servcie Due End"

#----------  SendNotice ------------------------------------------
def SendNotice(Message):

    try:

        client = Client(account_sid, auth_token)

        message = client.messages.create(
            to= to_number,
            from_ = from_number,
            body = Message)

        print(message.sid)

    except Exception, e1:
        log.error("Error: " + str(e1))
        print "Error: " + str(e1)

#------------------- Command-line interface for gengpio -----------------#
if __name__=='__main__': # usage program.py [server_address]
    address='127.0.0.1' if len(sys.argv)<2 else sys.argv[1]

    # Set the signal handler
    signal.signal(signal.SIGINT, signal_handler)
    try:
        log = mylog.SetupLogger("client", "/var/log/gensms.log")

        # read config file
        config = ConfigParser.RawConfigParser()
        # config parser reads from current directory, when running form a cron tab this is
        # not defined so we specify the full path
        config.read('/etc/gensms.conf')

        account_sid = config.get('gensms', 'accountsid')
        auth_token = config.get('gensms', 'authtoken')
        to_number = config.get('gensms', 'to_number')
        from_number = config.get('gensms', 'from_number')

        GenNotify = mynotify.GenNotify(host=address, onready = OnReady, onexercise = OnExercise, onrun = OnRun, onalarm = OnAlarm, onservice = OnService, log = log)

        while True:
            time.sleep(1)

    except Exception, e1:
        log.error("Error: " + str(e1))
        print "Error: " + str(e1)

