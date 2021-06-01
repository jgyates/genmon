#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: gengpio_relayboard.py
# PURPOSE: genmon.py support program to allow GPIO pins to drive
# status of WaveShare RPi Relay Board
#
#  AUTHOR: Liltux (using jgyates gengpio.py modified)
#    DATE: 01-Jun-2021
#
# MODIFICATIONS: limit too only 3 outputs.  Alarm, Running, Off
#-------------------------------------------------------------------------------

import datetime, time, sys, signal, os, threading, socket, json
import atexit, getopt
try:
    from genmonlib.mylog import SetupLogger
    from genmonlib.myclient import ClientInterface
    from genmonlib.mysupport import MySupport
    from genmonlib.program_defaults import ProgramDefaults
except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)

import RPi.GPIO as GPIO


#----------  Signal Handler ----------------------------------------------------
def signal_handler(signal, frame):

    GPIO.cleanup()
    MyClientInterface.Close()
    sys.exit(0)

#------------------- Command-line interface for gengpio ------------------------
if __name__=='__main__': # usage program.py [server_address]

    try:
        console, ConfigFilePath, address, port, loglocation, log = MySupport.SetupAddOnProgram("gengpio")

        # Set the signal handler
        signal.signal(signal.SIGINT, signal_handler)

        MyClientInterface = ClientInterface(host = address, port = port, log = log)

        #setup GPIO using Board numbering
        GPIO.setmode(GPIO.BOARD)

        console.info( GPIO.RPI_INFO)

        GPIO.setwarnings(False)

        # These are the GPIP pins numbers on the Raspberry PI GPIO header
        # https://www.element14.com/community/servlet/JiveServlet/previewBody/73950-102-10-339300/pi3_gpio.png

        STATUS_ALARM = 37       # ALARM GPIO 26 (pin 37)
        STATUS_RUNNING = 38     # RUNNING GPIO 20 (pin 38)
        STATUS_OFF = 40         # OFF GPIO 21   (pin 40)

        GPIO.setup(STATUS_ALARM, GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(STATUS_RUNNING, GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(STATUS_OFF, GPIO.OUT, initial=GPIO.HIGH)

        LastEvent = ""

        data = MyClientInterface.ProcessMonitorCommand("generator: monitor")

        if "evolution" in data.lower():
            Evolution = True
            console.info ("Evolution Controller Detected\n")
        else:
            Evolution = False
            console.info ("Non Evolution Controller Detected\n")

        while True:


            data = MyClientInterface.ProcessMonitorCommand("generator: getbase")

            if LastEvent != data:
                LastEvent = data
                console.info ("State: " + data)

                if data == "RUNNING" or data == "RUNNING-MANUAL":
                    GPIO.output(STATUS_RUNNING,GPIO.LOW)
                else:
                    GPIO.output(STATUS_RUNNING,GPIO.HIGH)

                if data == "ALARM":
                    GPIO.output(STATUS_ALARM,GPIO.LOW)
                else:
                    GPIO.output(STATUS_ALARM,GPIO.HIGH)

                if data == "OFF" or data == "MANUAL":
                    GPIO.output(STATUS_OFF,GPIO.LOW)
                else:
                    GPIO.output(STATUS_OFF, GPIO.HIGH)

    except Exception as e1:
        log.error("Error: " + str(e1))
        console.error ("Error: " + str(e1))
