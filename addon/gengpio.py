#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: gengpio.py
# PURPOSE: genmon.py support program to allow GPIO pins to drive
# status LEDs
#
#  AUTHOR: Jason G Yates
#    DATE: 05-Apr-2016
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


# ------------ GenGPIO class ----------------------------------------------------
class GenGPIO(MySupport):

    # These are the Raspberry Pi header pin numbers (not GPIO numbers), see
    # https://pinout.xyz/  A value of zero means the output is not used.
    # config file entry name : default header pin
    PIN_DEFAULTS = {
        # generator status
        "STATUS_READY": 16,
        "STATUS_ALARM": 18,
        "STATUS_SERVICE": 22,
        "STATUS_RUNNING": 26,
        "STATUS_EXERCISING": 24,
        "STATUS_OFF": 21,
        # genmon / internet errors
        "ER_GENMON": 3,
        "ER_INTERNET": 5,
        # alarm codes
        "ER_SPEED": 29,
        "ER_LOW_OIL": 31,
        "ER_HIGH_TEMP": 33,
        "ER_RPM_SENSE": 35,
        "ER_VOLTAGE": 37,
        "ER_OVERCRANK": 40,
        "ER_OVERLOAD": 38,
        "ER_GOVERNOR": 36,
        "ER_WARNING": 32,
        # Raspberry pi CPU temp
        "ER_PITEMP": 0,
        # time of day controlled output
        "PIN_EXTERNAL_SIGNAL": 0,
    }

    # generator state (from "generator: getbase") : status pin set HIGH for that state
    STATE_PINS = {
        "READY": "STATUS_READY",
        "EXERCISING": "STATUS_EXERCISING",
        "RUNNING": "STATUS_RUNNING",
        "RUNNING-MANUAL": "STATUS_RUNNING",
        "ALARM": "STATUS_ALARM",
        "SERVICEDUE": "STATUS_SERVICE",
        "OFF": "STATUS_OFF",
        "MANUAL": "STATUS_OFF",
    }

    # Evolution last alarm code ranges (inclusive) : pin set HIGH for that alarm
    # Last Error Code is not supported by Nexus controllers
    ALARM_CODE_PINS = [
        ("ER_SPEED", [(1200, 1299), (1600, 1699)]),  # Overspeed/Underspeed
        ("ER_LOW_OIL", [(1300, 1399)]),  # Low Oil
        ("ER_HIGH_TEMP", [(1400, 1499)]),  # High Temp
        ("ER_RPM_SENSE", [(1500, 1599)]),  # RPM Sensor
        ("ER_VOLTAGE", [(1800, 1899), (1900, 1999)]),  # Overvoltage/Undervoltage
        ("ER_OVERCRANK", [(1100, 1199)]),  # Overcrank
        ("ER_OVERLOAD", [(2100, 2199)]),  # Overload
        ("ER_GOVERNOR", [(2500, 2599)]),  # Governor
        ("ER_WARNING", [(0, 0)]),  # Warning (alarm 0000)
        # Other Faults, add the entry name to PIN_DEFAULTS and uncomment to use
        # ("ER_Controller", [(1000, 1099)]),  # Controller Internal
        # ("ER_Ignition", [(2600, 2669)]),  # Ignition
        # ("ER_Low_Fuel", [(2680, 2680), (2700, 2700)]),  # Fuel Level
        # ("ER_Low_Coolant", [(2720, 2720)]),  # Low Coolant
        # ("ER_Battery_Problem", [(2750, 2750), (2760, 2760)]),  # Battery
        # ("ER_Charger", [(2770, 2770), (2780, 2780)]),  # Charger
    ]

    # ------------ GenGPIO::init-------------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):

        super(GenGPIO, self).__init__()

        self.LogFileName = os.path.join(loglocation, "gengpio.log")
        self.AccessLock = threading.Lock()
        # log errors in this module to a file
        self.log = log
        self.console = console

        self.MonitorAddress = host
        self.debug = False
        self.PollTime = 3  # seconds between status checks
        self.NetworkPollTime = 20  # seconds between internet status checks
        self.Generator = None
        self.GPIOInitialized = False

        self.Pins = {}
        self.CPUThresholdTemp = 0
        self.OnTime = None
        self.OffTime = None
        self.Evolution = False

        # state used by the monitor thread
        self.LastEvent = ""
        self.LastNetStatus = ""
        self.LastMonitorHealth = ""
        self.LastCPUTemp = ""
        self.ExternalPinState = None
        self.NetStatusUpdated = datetime.datetime(2000, 1, 1, 1, 00)

        if self.MonitorAddress != None:
            self.MonitorAddress = self.MonitorAddress.strip()

        if self.MonitorAddress == None or not len(self.MonitorAddress):
            self.MonitorAddress = ProgramDefaults.LocalHost

        configfile = os.path.join(ConfigFilePath, "gengpio.conf")
        try:
            self.config = MyConfig(filename=configfile, section="gengpio", log=self.log)

            self.debug = self.config.ReadValue("debug", return_type=bool, default=False)

            for name, default in self.PIN_DEFAULTS.items():
                self.Pins[name] = self.config.ReadValue(
                    name, return_type=int, default=default
                )

            self.CPUThresholdTemp = self.config.ReadValue(
                "CPU_THRESHOLD_TEMP", return_type=float, default=70.0
            )
            if self.Pins["ER_PITEMP"] != 0 and self.CPUThresholdTemp != 0:
                self.LogError("Monitoring PI CPU Temp")

            self.ReadExternalSignalConfig()

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
            self.GPIOInitialized = True

            for name in self.Pins:
                self.InitGPIO(name, GPIO.OUT, initial=GPIO.LOW)

            data = self.SendCommand("generator: monitor")
            if "evolution" in data.lower():
                self.Evolution = True
                self.LogConsole("Evolution Controller Detected")
            else:
                self.Evolution = False
                self.LogConsole("Non Evolution Controller Detected")

            # start thread to monitor genmon and update the GPIO outputs
            self.Threads["GPIOThread"] = MyThread(
                self.GPIOThread, Name="GPIOThread", start=False
            )
            self.Threads["GPIOThread"].Start()

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

        except Exception as e1:
            self.LogErrorLine("Error in GenGPIO init: " + str(e1))
            self.LogConsole("Error in GenGPIO init: " + str(e1))
            self.Close()
            sys.exit(1)

    # ----------  GenGPIO::ReadExternalSignalConfig -----------------------------
    def ReadExternalSignalConfig(self):

        if self.Pins["PIN_EXTERNAL_SIGNAL"] == 0:
            return

        self.LogError("Using External Pin for Signaling")
        on_time_str = self.config.ReadValue("PIN_EXTERNAL_SIGNAL_ON_TIME", default=None)
        off_time_str = self.config.ReadValue("PIN_EXTERNAL_SIGNAL_OFF_TIME", default=None)

        if on_time_str == None:
            self.LogError("Error: Invalid setting for on time for external signal GPIO")
        else:
            on_time_str = on_time_str.strip()
            self.OnTime = self.ConvertToTimeObject(on_time_str)
            if self.OnTime == None:
                self.LogError(
                    "Error: invalid time format for signal enable time: " + on_time_str
                )

        if off_time_str == None:
            self.LogError("Error: Invalid setting for off time for external signal GPIO")
        else:
            off_time_str = off_time_str.strip()
            self.OffTime = self.ConvertToTimeObject(off_time_str)
            if self.OffTime == None:
                self.LogError(
                    "Error: invalid time format for signal disable time: " + off_time_str
                )

        if self.OnTime == None or self.OffTime == None:
            self.LogError("Disabling external signal pin.")
            self.Pins["PIN_EXTERNAL_SIGNAL"] = 0

        self.LogDebug("External Pin On Time: " + str(on_time_str))
        self.LogDebug("External Pin Off Time: " + str(off_time_str))

    # ----------  GenGPIO::InitGPIO ---------------------------------------------
    def InitGPIO(self, name, direction=GPIO.OUT, initial=GPIO.LOW):

        pin = self.Pins.get(name, 0)
        try:
            if pin != 0:
                GPIO.setup(pin, direction, initial=initial)
            else:
                self.LogDebug("Note: pin = 0 in InitGPIO for " + name)
        except Exception as e1:
            self.LogErrorLine(
                "Error in InitGPIO for %s on pin %d : %s" % (name, int(pin), str(e1))
            )

    # ----------  GenGPIO::SetGPIO ----------------------------------------------
    def SetGPIO(self, name, state):

        pin = self.Pins.get(name, 0)
        try:
            if pin != 0:
                GPIO.output(pin, state)
            else:
                self.LogDebug("Note: pin = 0 in SetGPIO for " + name)
        except Exception as e1:
            self.LogErrorLine(
                "Error in SetGPIO for %s on pin %d : %s" % (name, int(pin), str(e1))
            )

    # ----------  GenGPIO::SendCommand ------------------------------------------
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

    # ---------------- GenGPIO::RemoveAlpha -------------------------------------
    def RemoveAlpha(self, inputStr):

        answer = ""
        for char in inputStr:
            if not char.isalpha() and char != " " and char != "%":
                answer += char

        return answer.strip()

    # ---------------- GenGPIO::ConvertToTimeObject -----------------------------
    def ConvertToTimeObject(self, input_str):

        try:
            if input_str == None:
                return None
            if not self.IsTimeFormat(input_str):
                return None
            return datetime.datetime.strptime(input_str, "%H:%M")
        except Exception:
            self.LogErrorLine(
                "Error converting time to time object: " + str(input_str)
            )
            return None

    # ---------------- GenGPIO::IsTimeFormat ------------------------------------
    def IsTimeFormat(self, input_str):

        try:
            time.strptime(input_str, "%H:%M")
            return True
        except ValueError:
            self.LogDebug("Error in IsTimeFormat:" + str(input_str))
            return False

    # ---------------- GenGPIO::PastTimeOrEqual ---------------------------------
    def PastTimeOrEqual(self, target_time):

        try:
            current_time = datetime.datetime.now()
            if (
                current_time.hour == target_time.hour
                and current_time.minute >= target_time.minute
            ):
                return True
            if current_time.hour > target_time.hour:
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in PastTimeOrEqual: " + str(e1))
            return False

    # ---------------- GenGPIO::IsTimeTriggered ---------------------------------
    def IsTimeTriggered(self, on_state=False, off_state=False):

        try:
            on_time = self.OnTime
            off_time = self.OffTime
            if off_time > on_time:
                if off_state == True and self.PastTimeOrEqual(off_time):
                    return True
                if (
                    on_state == True
                    and self.PastTimeOrEqual(on_time)
                    and not self.PastTimeOrEqual(off_time)
                ):
                    return True
                if (
                    off_state == True
                    and not self.PastTimeOrEqual(on_time)
                    and not self.PastTimeOrEqual(off_time)
                ):
                    return True
            elif off_time < on_time:
                if on_state == True and self.PastTimeOrEqual(on_time):
                    return True
                if (
                    off_state == True
                    and self.PastTimeOrEqual(off_time)
                    and not self.PastTimeOrEqual(on_time)
                ):
                    return True
                if (
                    on_state == True
                    and not self.PastTimeOrEqual(on_time)
                    and not self.PastTimeOrEqual(off_time)
                ):
                    return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in IsTimeTriggered: " + str(e1))
            return False

    # ---------------- GenGPIO::UpdateGeneratorState ----------------------------
    def UpdateGeneratorState(self):

        data = self.SendCommand("generator: getbase")

        if self.LastEvent == data:
            return
        self.LastEvent = data
        self.LogConsole("State: " + data)

        # set the status pin for the current state HIGH, all others LOW
        active_pin = self.STATE_PINS.get(data, None)
        for name in set(self.STATE_PINS.values()):
            self.SetGPIO(name, GPIO.HIGH if name == active_pin else GPIO.LOW)

        if data == "ALARM" and self.Evolution:
            # Last Error Code not supported by Nexus
            LastErrorCode = int(self.SendCommand("generator: getregvalue=05f1"), 16)
            self.LogDebug("Last Error Code: " + str(LastErrorCode))
            for name, code_ranges in self.ALARM_CODE_PINS:
                for low, high in code_ranges:
                    if low <= LastErrorCode <= high:
                        self.SetGPIO(name, GPIO.HIGH)
        else:
            for name, code_ranges in self.ALARM_CODE_PINS:
                self.SetGPIO(name, GPIO.LOW)

    # ---------------- GenGPIO::UpdateMonitorHealth -----------------------------
    def UpdateMonitorHealth(self, MonitorData):

        try:
            HealthStr = MonitorData["Monitor"][0]["Generator Monitor Stats"][0][
                "Monitor Health"
            ]
            if HealthStr != self.LastMonitorHealth:
                self.LastMonitorHealth = HealthStr
                if HealthStr.lower() == "ok":
                    self.SetGPIO("ER_GENMON", GPIO.LOW)
                else:
                    self.SetGPIO("ER_GENMON", GPIO.HIGH)
        except Exception as e1:
            self.LogErrorLine("Error getting monitor health: " + str(e1))

    # ---------------- GenGPIO::UpdateInternetStatus ----------------------------
    def UpdateInternetStatus(self):

        try:
            # only check this every NetworkPollTime seconds
            TimeNow = datetime.datetime.now()
            if (TimeNow - self.NetStatusUpdated).total_seconds() > self.NetworkPollTime:
                self.NetStatusUpdated = TimeNow
                self.LogConsole("Updating internet status: " + str(self.NetStatusUpdated))
                data = self.SendCommand("generator: network_status")
                if data != self.LastNetStatus:
                    self.LastNetStatus = data
                    if data.lower() == "ok":
                        self.SetGPIO("ER_INTERNET", GPIO.LOW)
                    else:
                        self.SetGPIO("ER_INTERNET", GPIO.HIGH)
        except Exception as e1:
            self.LogErrorLine("Error getting internet status: " + str(e1))

    # ---------------- GenGPIO::UpdateCPUTemp -----------------------------------
    def UpdateCPUTemp(self, MonitorData):

        try:
            if self.Pins["ER_PITEMP"] != 0 and self.CPUThresholdTemp != 0:
                CPUTempStr = MonitorData["Monitor"][2]["Platform Stats"][0][
                    "CPU Temperature"
                ]
                CPUTempStr = self.RemoveAlpha(CPUTempStr)
                if CPUTempStr != self.LastCPUTemp:
                    self.LastCPUTemp = CPUTempStr
                    if float(CPUTempStr) < self.CPUThresholdTemp:
                        self.LogDebug("CPU Temp in Range: " + CPUTempStr)
                        self.SetGPIO("ER_PITEMP", GPIO.LOW)
                    else:
                        self.LogDebug("CPU Temp is HIGH: " + CPUTempStr)
                        self.SetGPIO("ER_PITEMP", GPIO.HIGH)
        except Exception as e1:
            self.LogErrorLine("Error checking pi CPU temp status: " + str(e1))

    # ---------------- GenGPIO::UpdateExternalSignal ----------------------------
    def UpdateExternalSignal(self):

        try:
            if self.Pins["PIN_EXTERNAL_SIGNAL"] != 0:
                if self.IsTimeTriggered(on_state=True):
                    if self.ExternalPinState == None or self.ExternalPinState == False:
                        self.LogDebug("External Pin State set to ON")
                        self.ExternalPinState = True
                    self.SetGPIO("PIN_EXTERNAL_SIGNAL", GPIO.HIGH)
                if self.IsTimeTriggered(off_state=True):
                    if self.ExternalPinState == None or self.ExternalPinState == True:
                        self.LogDebug("External Pin State set to OFF")
                        self.ExternalPinState = False
                    self.SetGPIO("PIN_EXTERNAL_SIGNAL", GPIO.LOW)
        except Exception as e1:
            self.LogErrorLine("Error in external pin signal: " + str(e1))

    # ---------------- GenGPIO::GetMonitorData ----------------------------------
    def GetMonitorData(self):

        try:
            return json.loads(self.SendCommand("generator: monitor_json"))
        except Exception as e1:
            self.LogErrorLine("Error getting monitor data: " + str(e1))
            return {}

    # ---------- GenGPIO::GPIOThread---------------------------------------------
    def GPIOThread(self):

        while True:
            try:
                self.UpdateGeneratorState()
            except Exception as e1:
                self.LogErrorLine("Error updating generator state: " + str(e1))

            # monitor health and CPU temp both come from the same monitor data
            MonitorData = self.GetMonitorData()
            self.UpdateMonitorHealth(MonitorData)
            self.UpdateInternetStatus()
            self.UpdateCPUTemp(MonitorData)
            self.UpdateExternalSignal()

            if self.WaitForExit("GPIOThread", float(self.PollTime)):
                return

    # ----------GenGPIO::SignalClose---------------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(0)

    # ----------GenGPIO::Close---------------------------------------------------
    def Close(self):

        try:
            if "GPIOThread" in self.Threads:
                self.KillThread("GPIOThread")
        except Exception as e1:
            self.LogErrorLine("Error stopping GPIO thread: " + str(e1))
        try:
            if self.GPIOInitialized:
                GPIO.cleanup()
        except Exception as e1:
            self.LogErrorLine("Error in GPIO cleanup: " + str(e1))
        try:
            if self.Generator != None:
                self.Generator.Close()
        except Exception as e1:
            self.LogErrorLine("Error closing generator client: " + str(e1))


# -------------------------------------------------------------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("gengpio")

    GenGPIOInstance = GenGPIO(
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
