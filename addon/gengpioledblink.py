#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: gengpioledblink.py
# PURPOSE: genmon.py support program to allow GPIO pins to drive
# status LEDs
#
#  AUTHOR: Jason G Yates
#    DATE: 05-Apr-2016
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import json
import os
import signal
import sys
import threading
import time

try:
    # this will add the parent of the genmonlib folder to the path
    # if we are one level below the genmonlib parent (e.g. in the addon folder)
    file_root = os.path.dirname(os.path.realpath(__file__))
    parent_root = os.path.abspath(os.path.join(file_root, os.pardir))
    if os.path.isdir(os.path.join(parent_root, "genmonlib")):
        sys.path.insert(1, parent_root)

    from genmonlib.myclient import ClientInterface
    from genmonlib.mycommon import MyCommon
    from genmonlib.myconfig import MyConfig
    from genmonlib.mysupport import MySupport
    from genmonlib.mythread import MyThread
    from genmonlib.program_defaults import ProgramDefaults
except Exception as e1:
    print(
        "\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n"
    )
    print(
        "Please see the project documentation at https://github.com/jgyates/genmon.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)

try:
    import RPi.GPIO as GPIO
except Exception as e1:
    print("\n\nThis program requires the RPi.GPIO module to be installed.\n")
    print(
        "Please see the project documentation at https://github.com/jgyates/genmon.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)


# ------------ GenGPIOLedBlink class --------------------------------------------
class GenGPIOLedBlink(MySupport):

    # ------------ GenGPIOLedBlink::init-----------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):

        super(GenGPIOLedBlink, self).__init__()

        self.LogFileName = os.path.join(loglocation, "gengpioledblink.log")
        self.AccessLock = threading.Lock()
        # log errors in this module to a file
        self.log = log
        self.console = console

        self.MonitorAddress = host
        self.debug = False
        self.LedPin = 12  # GPIO board pin number that LED is connected to (default)
        self.BlinkDelay = 0.15  # seconds between fast blinks
        self.ErrorRetryTime = 5  # seconds to wait after an error
        self.Generator = None
        self.GPIOInitialized = False

        if self.MonitorAddress != None:
            self.MonitorAddress = self.MonitorAddress.strip()

        if self.MonitorAddress == None or not len(self.MonitorAddress):
            self.MonitorAddress = ProgramDefaults.LocalHost

        configfile = os.path.join(ConfigFilePath, "gengpioledblink.conf")
        try:
            if os.path.isfile(configfile):
                self.config = MyConfig(
                    filename=configfile, section="gengpioledblink", log=self.log
                )
                self.LedPin = self.config.ReadValue(
                    "ledpin", return_type=int, default=12
                )
                self.debug = self.config.ReadValue(
                    "debug", return_type=bool, default=False
                )
        except Exception as e1:
            self.LogErrorLine("Error reading " + configfile + ": " + str(e1))
            self.LogConsole("Error reading " + configfile + ": " + str(e1))
            sys.exit(1)

        try:
            self.Generator = ClientInterface(
                host=self.MonitorAddress, port=port, log=self.log
            )

            # setup GPIO using Board numbering
            GPIO.setmode(GPIO.BOARD)
            self.LogConsole(str(GPIO.RPI_INFO))
            GPIO.setwarnings(False)
            GPIO.setup(self.LedPin, GPIO.OUT, initial=GPIO.LOW)
            self.GPIOInitialized = True

            # start thread to monitor genmon health and blink the LED
            self.Threads["LedBlinkThread"] = MyThread(
                self.LedBlinkThread, Name="LedBlinkThread", start=False
            )
            self.Threads["LedBlinkThread"].Start()

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

        except Exception as e1:
            self.LogErrorLine("Error in GenGPIOLedBlink init: " + str(e1))
            self.LogConsole("Error in GenGPIOLedBlink init: " + str(e1))
            sys.exit(1)

    # ----------  GenGPIOLedBlink::SendCommand ----------------------------------
    def SendCommand(self, Command):

        if len(Command) == 0:
            return "Invalid Command"

        try:
            with self.AccessLock:
                data = self.Generator.ProcessMonitorCommand(Command)
        except Exception:
            self.LogErrorLine("Error calling ProcessMonitorCommand: " + str(Command))
            data = ""

        return data

    # ----------  GenGPIOLedBlink::SetLed ---------------------------------------
    # turn LED on / off, then wait. Returns True if the thread should exit
    def SetLed(self, on, delay):

        GPIO.output(self.LedPin, GPIO.HIGH if on else GPIO.LOW)
        return self.WaitForExit("LedBlinkThread", delay)

    # ----------  GenGPIOLedBlink::BlinkLED -------------------------------------
    # one long blink followed by nfast short blinks. Returns True if the thread
    # should exit
    def BlinkLED(self, nfast):

        if self.SetLed(True, 1) or self.SetLed(False, 1):
            return True

        for i in range(nfast):
            if self.SetLed(True, self.BlinkDelay) or self.SetLed(
                False, self.BlinkDelay
            ):
                return True
        return False

    # ----------  GenGPIOLedBlink::GetMonitorHealthOK ---------------------------
    def GetMonitorHealthOK(self):

        TempDict = json.loads(self.SendCommand("generator: monitor_json"))
        Health = TempDict["Monitor"][0]["Generator Monitor Stats"][0]["Monitor Health"]
        self.LogDebug("Monitor Health: " + str(Health))
        return Health.lower() == "ok"

    # ---------- GenGPIOLedBlink::LedBlinkThread---------------------------------
    def LedBlinkThread(self):

        while True:
            try:
                if self.GetMonitorHealthOK():
                    nfast = 5
                else:
                    nfast = 2

                if self.BlinkLED(nfast):
                    return

            except Exception as e1:
                self.LogErrorLine("Error getting monitor health: " + str(e1))
                if self.WaitForExit("LedBlinkThread", float(self.ErrorRetryTime)):
                    return

    # ----------GenGPIOLedBlink::SignalClose-------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(0)

    # ----------GenGPIOLedBlink::Close-------------------------------------------
    def Close(self):

        try:
            self.KillThread("LedBlinkThread")

            if self.GPIOInitialized:
                # Turn off LED before exiting
                GPIO.output(self.LedPin, GPIO.LOW)
                GPIO.cleanup()

            if self.Generator != None:
                self.Generator.Close()
        except Exception as e1:
            self.LogErrorLine("Error in Close: " + str(e1))


# -------------------------------------------------------------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("gengpioledblink")

    GenGPIOLedBlinkInstance = GenGPIOLedBlink(
        log=log,
        loglocation=loglocation,
        ConfigFilePath=ConfigFilePath,
        host=address,
        port=port,
        console=console,
    )

    while True:
        time.sleep(0.5)

    sys.exit(1)
