#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: gengpio.py
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

        STATUS_READY = 16       # READY GPIO 23 (pin 16)
        STATUS_ALARM = 18       # ALARM GPIO 24 (pin 18)
        STATUS_SERVICE = 22     # SERVICE DUE GPIO 25 (pin 22)
        STATUS_RUNNING = 26     # RUNNING GPIO 7 (pin 26)
        STATUS_EXERCISING = 24  # EXERCISING GPIO 8 (pin 24)
        STATUS_OFF = 21         # OFF GPIO 9   (pin 21)

        # Set additional GPIO based on these error codes
        ER_GENMON = 3           # Genmon is reporting errors due to modbus or internal problems GPIO 2(pin3)
        ER_INTERNET = 5         # No internet connection GPIO3 (pin 5)
        # Overspeed/Underspeed (alarms 1200-1206, 1600-1603) GPIO 5 (pin 29)
        ER_SPEED = 29
        # Low Oil (alarm 1300) GPIO 6 (pin 31)
        ER_LOW_OIL = 31
        # High Temp (alarm 1400) GPIO 13 (pin 33
        ER_HIGH_TEMP = 33
        # RPM Sensor (alarm 1500-1521) GPIO 19 (pin 35)
        ER_RPM_SENSE = 35
        # Overvoltage/Undervoltage (alarm1800-1803, 1900-1906) GPIO 26 (pin 37)
        ER_VOLTAGE = 37
        # Overcrank (alarm 1100-1101) GPIO 21 (pin 40)
        ER_OVERCRANK = 40
        # Overload (alarm 2100-2103) GPIO 20 (pin 38)
        ER_OVERLOAD = 38
        # Governor (alarm 2500-2502) GPIO 16 (pin 36)
        ER_GOVERNOR = 36
        # Evolution Air Cooled Warning GPIO 12 (pin 32)
        ER_WARNING = 32

        GPIO.setup(STATUS_READY, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(STATUS_ALARM, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(STATUS_SERVICE, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(STATUS_RUNNING, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(STATUS_EXERCISING, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(STATUS_OFF, GPIO.OUT, initial=GPIO.LOW)

        GPIO.setup(ER_GENMON, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(ER_INTERNET, GPIO.OUT, initial=GPIO.LOW)

        GPIO.setup(ER_SPEED, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(ER_LOW_OIL, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(ER_HIGH_TEMP, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(ER_RPM_SENSE, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(ER_VOLTAGE, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(ER_OVERCRANK, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(ER_OVERLOAD, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(ER_GOVERNOR, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(ER_WARNING, GPIO.OUT, initial=GPIO.LOW)

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

                if data == "READY":
                    GPIO.output(STATUS_READY,GPIO.HIGH)
                else:
                    GPIO.output(STATUS_READY,GPIO.LOW)

                if data == "EXERCISING":
                    GPIO.output(STATUS_EXERCISING,GPIO.HIGH)
                else:
                    GPIO.output(STATUS_EXERCISING,GPIO.LOW)

                if data == "RUNNING" or data == "RUNNING-MANUAL":
                    GPIO.output(STATUS_RUNNING,GPIO.HIGH)
                else:
                    GPIO.output(STATUS_RUNNING,GPIO.LOW)

                if data == "ALARM":
                    GPIO.output(STATUS_ALARM,GPIO.HIGH)
                else:
                    GPIO.output(STATUS_ALARM,GPIO.LOW)

                if data == "SERVICEDUE":
                    GPIO.output(STATUS_SERVICE,GPIO.HIGH)
                else:
                    GPIO.output(STATUS_SERVICE, GPIO.LOW)

                if data == "OFF" or data == "MANUAL":
                    GPIO.output(STATUS_OFF,GPIO.HIGH)
                else:
                    GPIO.output(STATUS_OFF, GPIO.LOW)


                if data == "ALARM" and Evolution:     # Last Error Code not supported by Nexus

                    # get last error code
                    data = MyClientInterface.ProcessMonitorCommand("generator: getregvalue=05f1")
                    LastErrorCode = int(data,16)

                    # Overspeed/Underspeed (alarms 1200-1206, 1600-1603)
                    if 1200 <= LastErrorCode <= 1206 or 1600 <= LastErrorCode <= 1603:
                        GPIO.output(ER_SPEED,GPIO.HIGH)

                    # Low Oil (alarm 1300)
                    if LastErrorCode == 1300:
                        GPIO.output(ER_LOW_OIL,GPIO.HIGH)

                    # High Temp (alarm 1400)
                    if LastErrorCode == 1400:
                        GPIO.output(ER_HIGH_TEMP,GPIO.HIGH)

                    # RPM Sensor (alarm 1500-1521)
                    if 1500 <= LastErrorCode <= 1521:
                        GPIO.output(ER_RPM_SENSE,GPIO.HIGH)

                    # Overvoltage/Undervoltage (alarm 1800-1803, 1900-1906)
                    if 1800 <= LastErrorCode <= 1803 or 1900 <= LastErrorCode <= 1906:
                        GPIO.output(ER_VOLTAGE,GPIO.HIGH)

                    # Overcrank (alarm 1100-1101)
                    if 1100 <= LastErrorCode <= 1101:
                        GPIO.output(ER_OVERCRANK,GPIO.HIGH)

                    # Overload (alarm 2100-2103)
                    if 2100 <= LastErrorCode <= 2103:
                        GPIO.output(ER_OVERLOAD,GPIO.HIGH)

                    # Governor (alarm 2500-2502)
                    if 2500 <= LastErrorCode <= 2502:
                        GPIO.output(ER_GOVERNOR,GPIO.HIGH)

                    # Warning (alarm 0000)
                    if 0000 == LastErrorCode:
                        GPIO.output(ER_WARNING,GPIO.HIGH)

                else:
                    GPIO.output(ER_SPEED,GPIO.LOW)
                    GPIO.output(ER_LOW_OIL,GPIO.LOW)
                    GPIO.output(ER_HIGH_TEMP,GPIO.LOW)
                    GPIO.output(ER_RPM_SENSE,GPIO.LOW)
                    GPIO.output(ER_VOLTAGE,GPIO.LOW)
                    GPIO.output(ER_OVERCRANK,GPIO.LOW)
                    GPIO.output(ER_OVERLOAD,GPIO.LOW)
                    GPIO.output(ER_GOVERNOR,GPIO.LOW)
                    GPIO.output(ER_WARNING,GPIO.LOW)

            # Get Genmon status
            try:
                data = MyClientInterface.ProcessMonitorCommand("generator: monitor_json")
                TempDict = {}
                TempDict = json.loads(data)
                HealthStr = TempDict["Monitor"][0]["Generator Monitor Stats"][0]["Monitor Health"]
                if HealthStr.lower() == "ok":
                    GPIO.output(ER_GENMON,GPIO.LOW)
                else:
                    GPIO.output(ER_GENMON,GPIO.HIGH)
            except Exception as e1:
                log.error("Error getting monitor health: " +str(e1))
            # get Internet Status
            try:
                data = MyClientInterface.ProcessMonitorCommand("generator: network_status")
                if data.lower() == "ok":
                    GPIO.output(ER_INTERNET,GPIO.LOW)
                else:
                    GPIO.output(ER_INTERNET,GPIO.HIGH)
                time.sleep(3)
            except Exception as e1:
                log.error("Error getting internet status: " +str(e1))

    except Exception as e1:
        log.error("Error: " + str(e1))
        console.error ("Error: " + str(e1))
