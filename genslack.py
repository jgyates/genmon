#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: genslack.py
# PURPOSE: genmon.py support program to allow Slack messages
# to be sent when the generator status changes
#
#  AUTHOR: Nate Renbarger - Mostly copied from gensms
#    DATE: 20-Sep-2018
#
# MODIFICATIONS:
#------------------------------------------------------------

import datetime, time, sys, signal, os, threading, socket, json, requests

try:
    from genmonlib import mynotify, mylog, myconfig
except:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    sys.exit(2)

#----------  Signal Handler ------------------------------------------
def signal_handler(signal, frame):

    GenNotify.Close()
    sys.exit(0)

#----------  OnRun ------------------------------------------
def OnRun(Active):

    if Active:
        console.info("Generator Running")
        SendNotice("Generator Running")
    else:
        console.info("Generator Running End")

#----------  OnRunManual ------------------------------------------
def OnRunManual(Active):

    if Active:
        console.info("Generator Running in Manual Mode")
        SendNotice("Generator Running in Manual Mode")
    else:
        console.info("Generator Running in Manual Mode End")

#----------  OnExercise ------------------------------------------
def OnExercise(Active):

    if Active:
        console.info("Generator Exercising")
        SendNotice("Generator Exercising")
    else:
        console.info("Generator Exercising End")

#----------  OnReady ------------------------------------------
def OnReady(Active):

    if Active:
        console.info("Generator Ready")
        SendNotice("Generator Ready")
    else:
        console.info("Generator Ready End")

#----------  OnOff ------------------------------------------
def OnOff(Active):

    if Active:
        console.info("Generator Off")
        SendNotice("Generator Off")
    else:
        console.info("Generator Off End")

#----------  OnManual ------------------------------------------
def OnManual(Active):

    if Active:
        console.info("Generator Manual")
        SendNotice("Generator Manual")
    else:
        console.info("Generator Manual End")

#----------  OnAlarm ------------------------------------------
def OnAlarm(Active):

    if Active:
        console.info("Generator Alarm")
        SendNotice("Generator Alarm")
    else:
        console.info("Generator Alarm End")

#----------  OnService ------------------------------------------
def OnService(Active):

    if Active:
        console.info("Generator Service Due")
        SendNotice("Generator Service Due")
    else:
        console.info("Generator Servcie Due End")

#----------  OnUtilityChange -------------------------------------
def OnUtilityChange(Active):

    if Active:
        console.info("Utility Service is Down")
        SendNotice("Utility Service is Down")
    else:
        SendNotice("Utility Service is Up")
        console.info("Utility Service is Up")

#----------  SendNotice ------------------------------------------
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
        log.error("Error: " + str(e1))
        console.error("Error: " + str(e1))

#------------------- Command-line interface for gengpio -----------------#
if __name__=='__main__': # usage program.py [server_address]
    address='127.0.0.1' if len(sys.argv)<2 else sys.argv[1]

    # Set the signal handler
    signal.signal(signal.SIGINT, signal_handler)

    if os.geteuid() != 0:
        print("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.")
        sys.exit(2)

    console = mylog.SetupLogger("slack_console", log_file = "", stream = True)
    log = mylog.SetupLogger("client", "/var/log/genslack.log")

    try:
        config = myconfig.MyConfig(filename = '/etc/genslack.conf', section = 'genslack', log = log)

        webhook_url = config.ReadValue('webhook_url')
        channel = config.ReadValue('channel')
        username = config.ReadValue('username')
        icon_emoji = config.ReadValue('icon_emoji')
        title_link = config.ReadValue('title_link')

    except Exception as e1:
        log.error("Error reading /etc/genslack.conf: " + str(e1))
        console.error("Error reading /etc/genslack.conf: " + str(e1))
        sys.exit(1)

    try:
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
        console.error("Error: " + str(e1))