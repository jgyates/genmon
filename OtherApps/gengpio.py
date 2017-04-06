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
import atexit, ConfigParser
import myclient, mylog
import RPi.GPIO as GPIO



#----------  Signal Handler ------------------------------------------
def signal_handler(signal, frame):

    GPIO.cleanup()
    MyClientInterface.Close()
    sys.exit(0)

#------------------- Command-line interface for gengpio -----------------#
if __name__=='__main__': # usage program.py [server_address]
    address='127.0.0.1' if len(sys.argv)<2 else sys.argv[1]


    log = mylog.SetupLogger("client", "gengpio.log")
    # Set the signal handler
    signal.signal(signal.SIGINT, signal_handler)


    try:

        MyClientInterface = myclient.ClientInterface(host = address, log = log)

        #setup GPIO using Board numbering
        GPIO.setmode(GPIO.BOARD)

        print GPIO.RPI_INFO

        GPIO.setwarnings(True)

        # These are the GPIP pins numbers on the Raspberry PI GPIO header
        # https://www.element14.com/community/servlet/JiveServlet/previewBody/73950-102-10-339300/pi3_gpio.png
        LED_GREEN = 16      # READY GPIO 23
        LED_RED = 18        # ALARM GPIO 24
        LED_YELLOW = 22     # SERVICE DUE GPIO 25

        GPIO.setup(LED_GREEN, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(LED_RED, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(LED_YELLOW, GPIO.OUT, initial=GPIO.LOW)

        while True:


            data = MyClientInterface.ProcessMonitorCommand("generator: getbase")


            if data == "READY" or data == "EXERCISING" or data == "RUNNING":
                GPIO.output(LED_GREEN,GPIO.HIGH)
            else:
                GPIO.output(LED_GREEN,GPIO.LOW)

            if data == "ALARM":
                GPIO.output(LED_RED,GPIO.HIGH)
            else:
                GPIO.output(LED_RED,GPIO.LOW)

            if data == "SERVICEDUE":
                GPIO.output(LED_YELLOW,GPIO.HIGH)
            else:
                GPIO.output(LED_YELLOW, GPIO.LOW)


            time.sleep(3)

    except Exception, e1:
        print "Error: " + str(e1)




