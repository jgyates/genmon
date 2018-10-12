#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: gengpioin.py
# PURPOSE: genmon.py support program to allow GPIO inputs to control
# remote start, stop snd start/transfer functionality
# status LEDs
#
#  AUTHOR: Jason G Yates
#    DATE: 10-Apr-2016
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import datetime, time, sys, signal, os, threading, socket
import atexit
try:
    from genmonlib import myclient, mylog
except:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    sys.exit(2)
import RPi.GPIO as GPIO


# These are the GPIP pins numbers on the Raspberry PI GPIO header
# https://www.element14.com/community/servlet/JiveServlet/previewBody/73950-102-10-339300/pi3_gpio.png
INPUT_STOP = 11             # STOP GPIO 17
INPUT_START = 13            # START GPIO 27
INPUT_START_TRANSFER = 15   # START/TRANSFER GPIO 22

#----------  Signal Handler ----------------------------------------------------
def signal_handler(signal, frame):

    GPIO.remove_event_detect(INPUT_STOP)
    GPIO.remove_event_detect(INPUT_START)
    GPIO.remove_event_detect(INPUT_START_TRANSFER)
    GPIO.cleanup()
    MyClientInterface.Close()
    sys.exit(0)

#------------------- StopCallback ----------------------------------------------
def StopCallBack():

    try:
        MyClientInterface.ProcessMonitorCommand("generator: setremote=stop")
    except Exception as e1:
        log.error("Error: " + str(e1))


#------------------- StartCallBack ---------------------------------------------
def StartCallBack():

    try:
        MyClientInterface.ProcessMonitorCommand("generator: setremote=start")
    except Exception as e1:
        log.error("Error: " + str(e1))


#------------------- StartTransferCallBack -------------------------------------
def StartTransferCallBack():

    try:
        MyClientInterface.ProcessMonitorCommand("generator: setremote=starttransfer")
    except Exception as e1:
        log.error("Error: " + str(e1))

#------------------- Command-line interface for gengpioin ----------------------
if __name__=='__main__': # usage program.py [server_address]
    address='127.0.0.1' if len(sys.argv)<2 else sys.argv[1]

    try:
        console = mylog.SetupLogger("gengpioin_console", log_file = "", stream = True)
        log = mylog.SetupLogger("client", "/var/log/gengpioin.log")
        # Set the signal handler
        signal.signal(signal.SIGINT, signal_handler)

        MyClientInterface = myclient.ClientInterface(host = address, log = log)

        #setup GPIO using Board numbering
        GPIO.setmode(GPIO.BOARD)

        console.info( GPIO.RPI_INFO)

        GPIO.setwarnings(True)

        GPIO.setup(INPUT_STOP, GPIO.IN, pull_up_down=GPIO.PUD_UP)               # input, set internal pull up resistor#
        GPIO.add_event_detect(INPUT_STOP, GPIO.FALLING)                         # detect falling edge
        GPIO.add_event_callback(INPUT_STOP, callback = StopCallBack) #, bouncetime=1000)

        GPIO.setup(INPUT_START, GPIO.IN, pull_up_down=GPIO.PUD_UP)              # input, set internal pull up resistor#
        GPIO.add_event_detect(INPUT_START, GPIO.FALLING)                        # detect falling edge
        GPIO.add_event_callback(INPUT_START, callback = StartCallBack) #, bouncetime=1000)

        GPIO.setup(INPUT_START_TRANSFER, GPIO.IN, pull_up_down=GPIO.PUD_UP)     # input, set internal pull up resistor#
        GPIO.add_event_detect(INPUT_START_TRANSFER, GPIO.FALLING)               # detect falling edge
        GPIO.add_event_callback(INPUT_START_TRANSFER, callback = StartTransferCallBack) #, bouncetime=1000)


        while True:
            time.sleep(3)

    except Exception as e1:
        log.error("Error: " + str(e1))
        console.error("Error: " + str(e1))
