#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: gengpioledblink.py
# PURPOSE: genmon.py support program to allow GPIO pints to drive
# status LEDs
#
#  AUTHOR: Jason G Yates
#    DATE: 05-Apr-2016
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import datetime, time, sys, signal, os, threading, socket, json
import atexit, getopt
try:
    from genmonlib.mylog import SetupLogger
    from genmonlib.myconfig import MyConfig
    from genmonlib.myclient import ClientInterface
    from genmonlib.mysupport import MySupport
    from genmonlib.program_defaults import ProgramDefaults
except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)

import RPi.GPIO as GPIO

led_pin = 12     #GPIO board pin number that LED is connected to (default value)

#----------  Signal Handler ----------------------------------------------------
def signal_handler(signal, frame):

    #Turn off LED before exiting
    GPIO.output(led_pin,GPIO.LOW)

    GPIO.cleanup()
    MyClientInterface.Close()
    sys.exit(0)

#----------  blink_LED ---------------------------------------------------------
def blink_LED(pin, nfast):
    blinkdelay = .15

    GPIO.output(pin,GPIO.HIGH)
    time.sleep(1)
    GPIO.output(pin,GPIO.LOW)
    time.sleep(1)

    for i in range(nfast):
        GPIO.output(pin,GPIO.HIGH)
        time.sleep(blinkdelay)
        GPIO.output(pin,GPIO.LOW)
        time.sleep(blinkdelay)

#------------------- Command-line interface for gengpioledblink ----------------
if __name__=='__main__': # usage program.py [server_address]

    try:
        console, ConfigFilePath, address, port, loglocation, log = MySupport.SetupAddOnProgram("gengpioledblink")
        # Set the signal handler
        signal.signal(signal.SIGINT, signal_handler)

        conf_file = os.path.join(ConfigFilePath, 'gengpioledblink.conf')
        if os.path.isfile(conf_file):
            config = MyConfig(filename = conf_file, section = 'gengpioledblink', log = log)

            led_pin = config.ReadValue('ledpin', return_type = int, default = 12)

        MyClientInterface = ClientInterface(host = address, port = port, log = log)

        #setup GPIO using Board numbering
        GPIO.setmode(GPIO.BOARD)

        console.info(GPIO.RPI_INFO)

        GPIO.setwarnings(False)
        GPIO.setup(led_pin, GPIO.OUT, initial=GPIO.LOW)

        while True:

            # Get Genmon status
            try:
                TempDict = {}
                TempDict = json.loads(MyClientInterface.ProcessMonitorCommand("generator: monitor_json"))

                if TempDict["Monitor"][0]["Generator Monitor Stats"][0]["Monitor Health"].lower() == "ok":
                     blink_LED(led_pin, 5)
                else:
                     blink_LED(led_pin, 2)

            except Exception as e1:
                log.error("Error getting monitor health: " +str(e1))

    except Exception as e1:
        log.error("Error: " + str(e1))
        console.error ("Error: " + str(e1))
