#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: gencustomgpio.py
# PURPOSE: gencustomgpio.py add custom GPIO status to genmon
#
#  AUTHOR: jgyates
#    DATE: 12-01-2022
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------


import datetime
import json
import os
import signal
import sys
import threading
import time
import RPi.GPIO as GPIO
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
    from genmonlib.mylog import SetupLogger
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

#------------ MyGPIO class -----------------------------------------------------
class MyGPIO(MyCommon):
    def __init__(self, title = None, activename = "Active", inactivename = "Inactive", pin = None, pullup = True, log = None, debug = False):

        super(MyGPIO, self).__init__()

        self.title = title
        self.activename = activename 
        self.inactivename = inactivename
        self.log = log
        self.debug = debug
        self.pin = pin

        try:
            if pullup == True:
                self.resistor = GPIO.PUD_UP
            else:
                self.resistor = GPIO.PUD_DOWN
            GPIO.setup(self.pin, GPIO.IN, pull_up_down=self.resistor)
        except Exception as e1:
            self.LogErrorLine("Error in MyGPIOInit : " + str(pin) + ": " + str(title) + ": " + str(e1))

    # ------------ MyGPIO::state -----------------------------------------------
    def state(self):
        try:
            pin_state = GPIO.input(self.pin)
            if pin_state:
                return self.activename
            else:
                return self.inactivename
        except Exception as e1:
            self.LogErrorLine("Error in MyGPIOInit : state" + str(e1))

# ------------ GenCustomGPIO class ---------------------------------------------
class GenCustomGPIO(MySupport):

    # ------------ GenCustomGPIO::init------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):

        super(GenCustomGPIO, self).__init__()

        self.AccessLock = threading.Lock()

        self.log = log
        self.console = console

        self.MonitorAddress = host
        self.PollTime = 5
        self.debug = False

        try:
            configfile = os.path.join(ConfigFilePath, "gencustomgpio.conf")
            self.config = MyConfig(
                filename=configfile,
                section="gencustomgpio",log=self.log,
            )

            self.PollTime = self.config.ReadValue("poll_interval", return_type=float, default=5.0)
            self.debug = self.config.ReadValue("debug", return_type=bool, default=False)
            self.OutputPath = self.config.ReadValue("output_path", default="/home/pi/genmon")
            self.groupname = self.config.ReadValue("groupname", default="Custom GPIO Inputs")

            try:   
                # setup GPIO using Board numbering
                GPIO.setmode(GPIO.BOARD)
                GPIO.setwarnings(True)
                self.LogDebug("Debug Enabled")
                self.LogDebug("Group Name: " + self.groupname)
                self.LogDebug("Output path: " + self.OutputPath)
                self.LogDebug("Poll Time : " + str(self.PollTime))
            except Exception as e1:
                self.LogErrorLine(str(e1))

            self.GPIO_pins = []
            Sections = self.config.GetSections()
            for entry in Sections:
                if entry == "gencustomgpio":
                    continue
                try:
                    pin = int(entry)
                except:
                    self.LogError("Invalid section in " + configfile + ": " + str(entry))
                    continue
                self.LogDebug("Reading Section " + entry)
                self.config.SetSection(entry)
                title = self.config.ReadValue("title", default="GPIO Input " + str(pin))
                activename = self.config.ReadValue("activename", default="Active")
                inactivename = self.config.ReadValue("inactivename", default="Inactive")
                pullup = self.config.ReadValue("pullup", return_type = bool, default = False)

                self.LogDebug(str(pin) + ": " + title + ", " + activename + ", " + inactivename + ", " + str(pullup))
                self.GPIO_pins.append(
                    MyGPIO(title = title, activename = activename, 
                        inactivename = inactivename, pin = pin, 
                        pullup = pullup, log = self.log, debug = self.debug)
                )
                
            # Validate settings  
            if self.MonitorAddress != None:
                self.MonitorAddress = self.MonitorAddress.strip()

            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost

        except Exception as e1:
            self.LogErrorLine(
                "Error reading "
                + os.path.join(ConfigFilePath, "gencustomgpio.conf")
                + ": "
                + str(e1)
            )
            self.console.error(
                "Error reading "
                + os.path.join(ConfigFilePath, "gencustomgpio.conf")
                + ": "
                + str(e1)
            )
            sys.exit(1)

        try:

            self.Generator = ClientInterface(host=self.MonitorAddress, port=port, log=self.log)
            # start thread monitor time for exercise
            self.Threads["PollingThread"] = MyThread(self.PollingThread, Name="PollingThread", start=False)
            self.Threads["PollingThread"].Start()

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

        except Exception as e1:
            self.LogErrorLine("Error in GenCustomGPIO init: " + str(e1))
            self.console.error("Error in GenCustomGPIO init: " + str(e1))
            sys.exit(1)

    # ---------- GenCustomGPIO::PollingThread------------------------------------
    def PollingThread(self):

        time.sleep(1)

        LastPinState = self.GetPinStates()
        # write file
        self.UpdateFile(LastPinState)

        while True:
            try:
                pin_states = self.GetPinStates()
                if pin_states != LastPinState:
                    LastPinState = pin_states
                    self.UpdateFile(LastPinState)
                
                if self.WaitForExit("PollingThread", float(self.PollTime)):
                    return
            except Exception as e1:
                self.LogErrorLine("Error in PollingThread: " + str(e1))
                if self.WaitForExit("PollingThread", float(self.PollTime)):
                    return
    # ----------GenCustomGPIO::GetPinStates-------------------------------------
    def GetPinStates(self):

        pin_values = []
        PinStates = {self.groupname : pin_values}

        for pin in self.GPIO_pins:
            pin_values.append({pin.title: pin.state()})

        return PinStates

    # ----------GenCustomGPIO::UpdateFile---------------------------------------
    def UpdateFile(self, state):

        try:
            if len(state):
                with open(os.path.join(self.OutputPath, "userdefined.json"), 'w') as outfile:
                    self.LogDebug(str(state))
                    json.dump(state, outfile, ensure_ascii = False, indent = 4)
        except Exception as e1:
            self.LogErrorLine("Error in UpdateFile: " + str(e1))

    # ----------GenCustomGPIO::SignalClose--------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(1)

    # ----------GenCustomGPIO::Close--------------------------------------------
    def Close(self):
        self.KillThread("PollingThread")
        self.Generator.Close()


# -------------------------------------------------------------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("gencustomgpio")

    GenGPIOInstance = GenCustomGPIO(
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
