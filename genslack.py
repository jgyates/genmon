#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: genslack.py
# PURPOSE: genmon.py support program to allow Slack messages
# to be sent when the generator status changes
#
#  AUTHOR: Nate Renbarger - Mostly copied from gensms
#    DATE: 20-Sep-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import datetime, time, sys, signal, os, threading, socket, json, requests, getopt

try:
    from genmonlib.mylog import SetupLogger
    from genmonlib.mynotify import GenNotify
    from genmonlib.myconfig import MyConfig
    from genmonlib.mysupport import MySupport
    from genmonlib.program_defaults import ProgramDefaults
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
        slack_data = {'channel':channel, 'username':username, 'icon_emoji':icon_emoji, 'attachments': [{'title':'GenMon Alert', 'title_link':title_link, 'fields': [{ 'title':'Status', 'value':Message, 'short':'false' }]}]}

        response = requests.post(
                webhook_url, data=json.dumps(slack_data),
                headers={'Content-Type': 'application/json'}
            )
        if response.status_code != 200:
            raise ValueError(
                'Request to slack returned an error %s, the response is:\n%s'
                % (response.status_code, response.text)
            )

    except Exception as e1:
        log.error("Error in SendNotice: " + str(e1))
        console.error("Error in SendNotice: " + str(e1))

#------------------- Command-line interface for gengpio ------------------------
if __name__=='__main__':

    console, ConfigFilePath, address, port, loglocation, log = MySupport.SetupAddOnProgram("genslack")

    # Set the signal handler
    signal.signal(signal.SIGINT, signal_handler)
    try:
        config = MyConfig(filename = os.path.join(ConfigFilePath, 'genslack.conf'), section = 'genslack', log = log)

        webhook_url = config.ReadValue('webhook_url', default = None)
        channel = config.ReadValue('channel', default = None)
        username = config.ReadValue('username', default = None)
        icon_emoji = config.ReadValue('icon_emoji', default = ":red_circle:")
        title_link = config.ReadValue('title_link', default = None)

        if webhook_url == None or not len(webhook_url):
            log.error("Error: invalid webhoot_url setting")
            console.error("Error: invalid webhoot_url setting")
            sys.exit(2)

        if channel == None or not len(channel):
            log.error("Error: invalid channel setting")
            console.error("Error: invalid channel setting")
            sys.exit(2)

        if username == None or not len(username):
            log.error("Error: invalid username setting")
            console.error("Error: invalid username setting")
            sys.exit(2)

        if icon_emoji == None or not len(icon_emoji):
            log.error("Error: invalid username setting")
            console.error("Error: invalid username setting")
            sys.exit(2)

        if title_link == None or not len(title_link):
            log.error("Error: invalid title_link setting")
            console.error("Error: invalid title_link setting")
            sys.exit(2)

    except Exception as e1:
        log.error("Error reading genslack.conf: " + str(e1))
        console.error("Error reading genslack.conf: " + str(e1))
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
