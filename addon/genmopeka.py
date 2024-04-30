#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: genmopeka.py
# PURPOSE: genmopeka.py add mopeka tank sensor data to genmon
#
#  AUTHOR: jgyates
#    DATE: 07-28-2022
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------


# https://www.engineersedge.com/calculators/fluids/propane-tank-dimensional-calculator.htm

# Possible alternative
# https://github.com/Bluetooth-Devices/mopeka-iot-ble


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
    from genmonlib.mylog import SetupLogger
    from genmonlib.mysupport import MySupport
    from genmonlib.mythread import MyThread
    from genmonlib.program_defaults import ProgramDefaults
    from genmonlib.mymopeka import MopekaBT, MopekaBTSensor

except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)

try:
    from enum import Enum
    from typing import Optional
    from bleson import get_provider, BDAddress
    from bleson.core.hci.type_converters import rssi_from_byte
    from bleson.core.hci.constants import GAP_MFG_DATA, GAP_NAME_COMPLETE

except Exception as e1:
    print("The required library bleson is not installed.")
    sys.exit(2)


class GenMopekaData(MySupport):

    # ------------ GenMopekaData::init---------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):

        super(GenMopekaData, self).__init__()

        self.LogFileName = os.path.join(loglocation, "genmopeka.log")
        self.AccessLock = threading.Lock()

        self.log = log
        self.console = console

        self.MonitorAddress = host
        self.PollTime = 2
        self.tank_address = None
        self.debug = False
        self.UseMopekaLib = False

        try:

            configfile = os.path.join(ConfigFilePath, "genmopeka.conf")

            if not os.path.isfile(configfile):
                self.LogConsole("Missing config file : " + configfile)
                self.LogError("Missing config file : " + configfile)
                sys.exit(1)

            self.config = MyConfig(filename=configfile, section="genmopeka", log=self.log)

            self.PollTime = self.config.ReadValue("poll_frequency", return_type=float, default=60)
            self.debug = self.config.ReadValue("debug", return_type=bool, default=False)
            self.tank_address = self.config.ReadValue("tank_address", default=None)
            self.tank_type = self.config.ReadValue("tank_type", default=None)
            self.min_mm = self.config.ReadValue("min_mm", return_type=int, default=None, NoLog=True)
            self.max_mm = self.config.ReadValue("max_mm", return_type=int, default=None, NoLog=True)
            self.scan_time = self.config.ReadValue("scan_time", return_type=int, default=15)  # num of seconds to scan
            self.send_notices = self.config.ReadValue("send_notices", return_type=bool, default=False)
            self.min_reading_quality = self.config.ReadValue("min_reading_quality", return_type=int, default=0, NoLog=True)
            self.UseMopekaLib = self.config.ReadValue("use_old_lib", return_type=bool, default=False)

            if self.MonitorAddress != None:
                self.MonitorAddress = self.MonitorAddress.strip()

            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost


        except Exception as e1:
            self.LogErrorLine("Error reading " + configfile + ": " + str(e1))
            self.LogConsole("Error reading " + configfile + ": " + str(e1))
            sys.exit(1)

        try:

            try:
                from bleson import BDAddress
            except Exception as e1:
                self.LogConsole("The required library bleson is not installed.")
                self.LogErrorLine(
                    "The required library bleson is not installed." + str(e1)
                )
                sys.exit(2)
            if self.UseMopekaLib:
                try:
                    from mopeka_pro_check.service import (GetServiceInstance,MopekaSensor,MopekaService,)
                except Exception as e1:
                    self.LogConsole("The required library mopeka_pro_check is not installed.")
                    self.LogErrorLine("The required library mopeka_pro_check is not installed: " + str(e1))
                    sys.exit(2)
            try:
                from fluids.geometry import TANK
            except Exception as e1:
                self.LogConsole("The required library fluids is not installed.")
                self.LogErrorLine(
                    "The required library fluids is not installed: " + str(e1)
                )
                sys.exit(2)

            # we do this again to override the console output that is set in bleson module
            self.console = SetupLogger(
                "genmopeka" + "_console", log_file="", stream=True
            )

            self.LogDebug("Tank Address = " + str(self.tank_address))
            self.LogDebug("Min Reading Quality: " + str(self.min_reading_quality))

            self.Generator = ClientInterface(
                host=self.MonitorAddress, port=port, log=self.log
            )

            if self.tank_address == None or self.tank_address == "":
                self.LogError("No valid tank address found: " + str(self.tank_address))
                self.LogConsole(
                    "No valid tank address found: " + str(self.tank_address)
                )
                sys.exit(1)

            if "," in self.tank_address:
                self.tank_address = self.tank_address.split(",")
            else:
                temp = []
                temp.append(self.tank_address)
                self.tank_address = temp

            if len(self.tank_address) > 4:
                self.LogError(
                    "Only four tanks sensors are supportd. Found "
                    + str(len(self.tank_address))
                )
                self.LogConsole(
                    "Only four tanks sensors are supportd. Found "
                    + str(len(self.tank_address))
                )
                sys.exit(1)

            self.tank_address = list(map(str.strip, self.tank_address))
            for tank in self.tank_address:
                # must be in format xx:xx:xx:xx:xx:xx
                import re

                if not re.match(
                    "[0-9a-f]{2}([-:]?)[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", tank.lower()
                ):
                    self.LogError(
                        "Invalid tank sensor address format: " + str(len(tank))
                    )
                    self.LogConsole(
                        "Invalid tank sensor address format: " + str(len(tank))
                    )
                    sys.exit(1)
                if len(tank) != 17:
                    self.LogError(
                        "Invalid tank sensor address length: " + str(len(tank))
                    )
                    self.LogConsole(
                        "Invalid tank sensor address length: " + str(len(tank))
                    )
                    sys.exit(1)

            self.bd_tank_address = list(map(BDAddress, self.tank_address))

            if (self.tank_type == None or self.tank_type.lower() == "custom") and (
                self.min_mm == None or self.max_mm == None
            ):
                self.LogError(
                    "Invalid tank type: "
                    + str(self.tank_type)
                    + ": "
                    + str(self.min_mm)
                    + ": "
                    + str(self.max_mm)
                )
                self.LogConsole(
                    "Invalid tank type: "
                    + str(self.tank_type)
                    + ": "
                    + str(self.min_mm)
                    + ": "
                    + str(self.max_mm)
                )
                sys.exit(1)

            if self.tank_type == None:
                self.tank_type == "Custom"

            if self.tank_type.lower() != "custom":
                # default tank mim
                self.min_mm = 38.1

            if self.tank_type.lower() == "20_lb":  # vertical
                self.max_mm = 254
            elif self.tank_type.lower() == "30_lb":  # vertical
                self.max_mm = 381
            elif self.tank_type.lower() == "40_lb":  # vertical
                self.max_mm = 508
            elif self.tank_type.lower() == "100_lb":  # vertical, 24 Gal
                self.max_mm = 915
            elif self.tank_type.lower() == "custom":
                # TODO
                if (
                    not isinstance(self.max_mm, int)
                    or self.max_mm <= 1
                    or self.min_mm < 0
                ):
                    self.LogError(
                        "Invalid min/max for custom tank type: min:"
                        + str(self.min_mm)
                        + ", max: "
                        + str(self.max_mm)
                    )
                    self.LogConsole(
                        "Invalid min/max for custom tank type: min:"
                        + str(self.min_mm)
                        + ", max: "
                        + str(self.max_mm)
                    )
                    sys.exit(1)

            self.TankDimensions = {
                # Tank size info: https://learnmetrics.com/propane-tank-sizes/
                # units are inches and gallons
                # note: for all of these measurements, diameter is the same value for width and height e.g. diameter=width=height
                # total length of tank is length + (cap_lenth * 2)
                "20_lb": {
                    "length": (17.8 - 10),
                    "diameter": 12.5,
                    "orientation": "vertical",
                    "cap": "torispherical",
                    "cap_length": 3,
                },
                "30_lb": {
                    "length": (24 - 10),
                    "diameter": 12.5,
                    "orientation": "vertical",
                    "cap": "torispherical",
                    "cap_length": 3,
                },
                "40_lb": {
                    "length": (27 - 10),
                    "diameter": 13,
                    "orientation": "vertical",
                    "cap": "torispherical",
                    "cap_length": 3,
                },
                "100_lb": {
                    "length": (48 - 10),
                    "diameter": 14.5,
                    "orientation": "vertical",
                    "cap": "torispherical",
                    "cap_length": 3,
                },
                "200_lb": {
                    "length": (48 - 10),
                    "diameter": 19.5,
                    "orientation": "vertical",
                    "cap": "torispherical",
                    "cap_length": 3,
                },
                "120_gal": {
                    "length": (52 - 10),
                    "diameter": 30,
                    "orientation": "vertical",
                    "cap": "torispherical",
                    "cap_length": 3,
                },
                # for horizontal tanks the cap length is estimated to be half the diameter
                "120_gal_horiz": {
                    "length": (66 - 12),
                    "diameter": 24,
                    "orientation": "horizontal",
                    "cap": "spherical",
                    "cap_length": 12,
                },
                "250_gal": {
                    "length": (92 - 30),
                    "diameter": 30,
                    "orientation": "horizontal",
                    "cap": "spherical",
                    "cap_length": 15,
                },
                "500_gal": {
                    "length": (120 - 37),
                    "diameter": 37,
                    "orientation": "horizontal",
                    "cap": "spherical",
                    "cap_length": 18.5,
                },
                "1000_gal": {
                    "length": (190 - 41),
                    "diameter": 41,
                    "orientation": "horizontal",
                    "cap": "spherical",
                    "cap_length": 20.5,
                },
            }
            self.LogDebug("min: " + str(self.min_mm) + " , max: " + str(self.max_mm))
            self.LogDebug("Tank Type: " + str(self.tank_type))

            if self.UseMopekaLib:
                self.mopeka = GetServiceInstance()
                self.mopeka.SetHostControllerIndex(0)
            else:
                self.mopeka = MopekaBT(log = self.log, console = self.console, debug = self.debug, min_reading_quality=self.min_reading_quality)

            for tank in self.tank_address:
                if self.UseMopekaLib:
                    self.mopeka.AddSensorToMonitor(MopekaSensor(tank))
                else:
                    self.mopeka.AddSensor(MopekaBTSensor(tank, log = self.log, debug = self.debug, console = self.console))

            # https://fluids.readthedocs.io/tutorial.html#tank-geometry
            if self.tank_type.lower() != "custom":
                dimensions = self.TankDimensions.get(self.tank_type.lower(), None)
                if dimensions == None:
                    self.LogError("Invalid Tank Type: " + str(self.tank_type))
                    sys.exit(1)

                if dimensions["cap"] == "torispherical":
                    # the fluids lib assumes the cap lenght is 25% of the diameter for vertical tanks
                    self.Tank = TANK(
                        D=dimensions["diameter"],
                        L=dimensions["length"],
                        horizontal=dimensions["orientation"] == "horizontal",
                        sideA=dimensions["cap"],
                        sideB=dimensions["cap"],
                    )
                else:
                    # we use a cap of 1/2 the diameter for horizontal tanks
                    self.Tank = TANK(
                        D=dimensions["diameter"],
                        L=dimensions["length"],
                        horizontal=dimensions["orientation"] == "horizontal",
                        sideA=dimensions["cap"],
                        sideB=dimensions["cap"],
                        sideA_a=dimensions["cap_length"],
                        sideB_a=dimensions["cap_length"],
                    )

                self.TankVolume = self.CubicInToGallons(self.Tank.V_total)
                self.LogDebug("Tank Volume Calculated: " + str(self.TankVolume))
                self.LogDebug(self.Tank)

            # start thread monitor time for exercise
            self.Threads["TankCheckThread"] = MyThread(
                self.TankCheckThread, Name="TankCheckThread", start=False
            )
            self.Threads["TankCheckThread"].Start()

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

        except Exception as e1:
            self.LogErrorLine("Error in GenMopekaData init: " + str(e1))
            self.console.error("Error in GenMopekaData init: " + str(e1))
            sys.exit(1)

    # ----------  GenMopekaData::CubicInToGallons -------------------------------
    def CubicInToGallons(self, cubic_inches):
        return round(cubic_inches / 231, 2)

    # ----------  GenMopekaData::SendCommand --------------------------------------
    def SendCommand(self, Command):

        if len(Command) == 0:
            return "Invalid Command"

        try:
            with self.AccessLock:
                data = self.Generator.ProcessMonitorCommand(Command)
        except Exception as e1:
            self.LogErrorLine("Error calling  ProcessMonitorCommand: " + str(Command))
            data = ""

        return data

    # ----------GenMopekaData::SendMessage----------------------------------------
    def SendMessage(self, title, body, type, onlyonce=False, oncedaily=False):

        try:
            if not self.send_notices:
                return "disabled"
            message = {"title": title, "body": body, "type": type, "onlyonce": onlyonce, "oncedaily": oncedaily}
            command = "generator: notify_message=" + json.dumps(message)

            data = self.SendCommand(command)
            return data
        except Exception as e1:
            self.LogErrorLine("Error in SendMessage: " + str(e1))
            return ""

    # ---------- GenMopekaData::GetTankReading------------------------------------
    def GetTankReading(self, bd_address):
        try:

            if self.UseMopekaLib:
                if len(self.mopeka.SensorMonitoredList) == 0:
                    self.LogDebug("No sensors monitoried.")
                    return None
            else:
                if len(self.mopeka.sensors) == 0:
                    self.LogDebug("No sensors monitoried.")
                    return None
                
                if not bd_address in self.mopeka.sensors.keys():
                    self.LogError("Error in GetTankReading: " + str(bd_address) + ": " + str(self.mopeka.sensors.keys()))
                    return None
        
            if self.UseMopekaLib:
                if self.mopeka.SensorMonitoredList[bd_address]._last_packet == None:
                    self.SendMessage(
                        "Genmon Warning for Mopeka Sensor Add On",
                        "Unable to communicate with Mopeka Pro sensor.",
                        "error",
                        True,
                    )
                    self.LogDebug("No sensor comms detected for " + str(bd_address))
                    return None
            else:
                if self.mopeka.sensors[bd_address].last_reading == None:
                    self.SendMessage(
                        "Genmon Warning for Mopeka Sensor Add On",
                        "Unable to communicate with Mopeka Pro sensor.",
                        "error",
                        True,
                    )
                    self.LogDebug("No sensor comms detected for " + str(bd_address))
                    return None
            
            if self.UseMopekaLib:
                sensor_list =  self.mopeka.SensorMonitoredList
            else:
                sensor_list =  self.mopeka.sensors 

            if self.UseMopekaLib:
                reading_depth = sensor_list[bd_address]._last_packet.TankLevelInMM
                sensor_temperature = sensor_list[bd_address]._last_packet.TemperatureInCelsius
                self.LogDebug("Tank Level in mm: " + str(reading_depth))
                battery = sensor_list[bd_address]._last_packet.BatteryPercent
            else:
                reading_depth = sensor_list[bd_address].last_reading.TankLevelInMM
                sensor_temperature = sensor_list[bd_address].last_reading.TemperatureInCelsius
                self.LogDebug("Tank Level in mm: " + str(reading_depth))
                battery = sensor_list[bd_address].last_reading.BatteryPercent

            if battery < 15:
                message = "Warning, battery is low. Battery percentage is " + str(
                    battery
                )
                self.SendMessage(
                    "Genmon Warning for Mopeka Sensor Add On", message, "error", True
                )
            return self.ConvertTankReading(reading_depth)

        except Exception as e1:
            self.LogErrorLine("Error in GetTankReading: " + str(e1))
            return None

    # ---------- GenMopekaData::MmToInches--------------------------------------------
    def MmToInches(self, mm):

        try:
            if mm <= 0:
                return 0
            else:
                return round(mm / 25.4, 2)

        except Exception as e1:
            self.LogErrorLine("Error in MmToInches: " + str(e1))
            return 0

    # ---------- GenMopekaData::ConvertTankReading-----------------------------------
    def ConvertTankReading(self, reading_mm):

        try:
            if reading_mm == None:
                return 0

            reading_inches = self.MmToInches(reading_mm)
            dimensions = self.TankDimensions.get(self.tank_type.lower(), None)
            self.LogDebug("Tank Level in inches: " + str(reading_inches))

            if dimensions == None:
                # Custom tank type
                self.LogDebug(
                    "No tank dimensions found for tank type " + str(self.tank_type)
                )
                if self.max_mm != None or self.min_mm != None:
                    self.LogDebug(
                        "Error: min: "
                        + str(self.min_mm)
                        + " , max: "
                        + str(self.max_mm)
                    )
                    return None

                if reading_mm > self.max_mm:
                    reading_mm = self.max_mm
                    reading_inches = self.MmToInches(reading_mm)
                tanksize = self.max_mm - self.min_mm
                return round(((reading_mm - self.min_mm) / tanksize) * 100, 2)
            try:
                cubic_inches = self.Tank.V_from_h(reading_inches)
            except Exception as e1:
                self.LogError("Error in fluids geometry: " + str(e1))
                self.LogDebug("max mm:" + str(self.max_mm) + " reading mm: " + reading_mm)
                return None
            gallons_left = self.CubicInToGallons(cubic_inches)
            self.LogDebug("Gallons Left: " + str(gallons_left))
            if gallons_left >= self.TankVolume:
                percent = 100
                return 100
            else:
                percent = round((gallons_left / self.TankVolume) * 100, 2)
            self.LogDebug("Tank Percentage: " + str(percent))
            return percent

        except Exception as e1:
            self.LogErrorLine("Error in ConvertTankReading: " + str(e1))
            return None

    # ---------- GenMopekaData::TankCheckThread-----------------------------------
    def TankCheckThread(self):

        time.sleep(1)
        
        LastTankReading = [None,None,None,None]

        while True:
            try:
                if len(self.bd_tank_address) == 0:
                    self.LogError("ERROR in TankCheckThread: No tanks available")
                    return

                dataforgenmon = {}

                self.LogDebug("starting scan")
                self.mopeka.Start()
                if self.WaitForExit("TankCheckThread", self.scan_time):
                    self.mopeka.Stop()
                    return
                self.mopeka.Stop()
                self.LogDebug("stopped scan")
                self.mopeka.LogStats()

                reading = self.GetTankReading(self.bd_tank_address[0])
                if reading != None:
                    self.LogDebug("Tank1 = " + str(reading))
                    dataforgenmon["Percentage"] = reading
                    LastTankReading[0] = reading
                else:
                    # if we get an error, but have a last valid reading, use hte last valid reading, 
                    # otherwise it is zero as there is no sensor because we never got a good reading
                    if LastTankReading[0] == None:
                        dataforgenmon["Percentage"] = 0
                    else:
                        dataforgenmon["Percentage"] = LastTankReading[0]

                if len(self.bd_tank_address) >= 2:
                    reading = self.GetTankReading(self.bd_tank_address[1])
                    if reading != None:
                        self.LogDebug("Tank2 = " + str(reading))
                        dataforgenmon["Percentage2"] = reading
                        LastTankReading[1] = reading
                    else:
                        if LastTankReading[1] == None:
                            dataforgenmon["Percentage2"] = 0
                        else:
                            dataforgenmon["Percentage2"] = LastTankReading[1]
                        

                if len(self.bd_tank_address) >= 3:
                    reading = self.GetTankReading(self.bd_tank_address[2])
                    if reading != None:
                        self.LogDebug("Tank3 = " + str(reading))
                        dataforgenmon["Percentage3"] = reading
                        LastTankReading[2] = reading
                    else:
                        if LastTankReading[2] == None:
                            dataforgenmon["Percentage3"] = 0
                        else:
                            dataforgenmon["Percentage3"] = LastTankReading[2]

                if len(self.bd_tank_address) >= 4:
                    reading = self.GetTankReading(self.bd_tank_address[3])
                    if reading != None:
                        self.LogDebug("Tank4 = " + str(reading))
                        dataforgenmon["Percentage4"] = reading
                        LastTankReading[3] = reading
                    else:
                        if LastTankReading[3] == None:
                            dataforgenmon["Percentage4"] = 0
                        else:
                            dataforgenmon["Percentage4"] = LastTankReading[3]

                if len(dataforgenmon) != 0:
                    dataforgenmon["Tank Name"] = "Mopeka Sensor Tank"

                    self.LogDebug("Tank Data = " + json.dumps(dataforgenmon))

                    retVal = self.SendCommand(
                        "generator: set_tank_data=" + json.dumps(dataforgenmon)
                    )
                    self.LogDebug("SendCommand Result: " +  retVal)
                else:
                    self.LogDebug("No reading from tank sensor!")
                if self.WaitForExit("TankCheckThread", float(self.PollTime * 60)):
                    return
            except Exception as e1:
                self.LogErrorLine("Error in TankCheckThread: " + str(e1))
                if self.WaitForExit("TankCheckThread", float(self.PollTime * 60)):
                    return

    # ----------GenMopekaData::SignalClose----------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(1)

    # ----------GenMopekaData::Close----------------------------------------------
    def Close(self):
        self.KillThread("TankCheckThread")
        try:
            self.mopeka.Close()
        except:
            pass
        try:
            self.Generator.Close()
        except:
            pass


# -------------------------------------------------------------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("genmopeka")

    GenMopekaDataInstance = GenMopekaData(
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
