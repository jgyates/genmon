#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: gentemp.py
# PURPOSE: gentemp.py add support for type K thermocouples and DS18B20 temp sesnsors
#
#  AUTHOR: jgyates
#    DATE: 09-12-2019
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------


import json
import os
import signal
import sys
import threading
import time
import itertools

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

try:
    import glob
    import os
    import time
except Exception as e1:
    print("Error importing modules! :" + str(e1))
    sys.exit(2)

# Typical reading
# 73 01 4b 46 7f ff 0d 10 41 : crc=41 YES
# 73 01 4b 46 7f ff 0d 10 41 t=23187

# ------------ GenTemp class ----------------------------------------------------
class GenTemp(MySupport):

    # ------------ GenTemp::init-------------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):

        super(GenTemp, self).__init__()

        self.LogFileName = os.path.join(loglocation, "gentemp.log")
        self.AccessLock = threading.Lock()
        # log errors in this module to a file
        self.log = log

        self.console = console

        self.LastValues = {}

        self.MonitorAddress = host
        self.debug = False
        self.PollTime = 1
        self.BlackList = None

        configfile = os.path.join(ConfigFilePath, "gentemp.conf")
        try:
            if not os.path.isfile(configfile):
                self.LogConsole("Missing config file : " + configfile)
                self.LogError("Missing config file : " + configfile)
                sys.exit(1)

            self.config = MyConfig(filename=configfile, section="gentemp", log=self.log)

            self.UseMetric = self.config.ReadValue("use_metric", return_type=bool, default=False)
            self.PollTime = self.config.ReadValue("poll_frequency", return_type=float, default=1)
            self.debug = self.config.ReadValue("debug", return_type=bool, default=False)
            self.DeviceLabels = self.GetParamList(self.config.ReadValue("device_labels", default=None))
            self.DeviceNominalValues = self.GetParamList(self.config.ReadValue("device_nominal_values", default=None), bInteger=True)
            self.DeviceMaxValues = self.GetParamList(self.config.ReadValue("device_max_values", default=None), bInteger=True)
            self.DeviceMinValues = self.GetParamList(self.config.ReadValue("device_min_values", default=None), bInteger=True)
            self.BlackList = self.GetParamList(self.config.ReadValue("blacklist", default=None))

            if self.MonitorAddress != None:
                self.MonitorAddress = self.MonitorAddress.strip()

            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost


        except Exception as e1:
            self.LogErrorLine("Error reading " + configfile + ": " + str(e1))
            self.LogConsole("Error reading " + configfile + ": " + str(e1))
            sys.exit(1)

        try:
                    
            self.Generator = ClientInterface(host=self.MonitorAddress, port=port, log=self.log)

            self.GaugeData = [] 
            
            if self.UseMetric:
                self.Units = "C"
            else:
                self.Units = "F"
            if self.DeviceNominalValues != None and self.DeviceMaxValues != None and self.DeviceLabels != None:
                # DeviceMinValues is optional
                if self.DeviceMinValues == None:
                    self.DeviceMinValues = []
                    for i in range(len(self.DeviceNominalValues)):
                        self.DeviceMinValues.append(0)

                if len(self.DeviceNominalValues) == len(self.DeviceMaxValues) == len(self.DeviceLabels) == len(self.DeviceMinValues):
                    for (NominalValue,MaxValue, DeviceName, MinValue) in itertools.zip_longest(self.DeviceNominalValues, self.DeviceMaxValues, self.DeviceLabels, self.DeviceMinValues):
                        self.GaugeData.append({"max": MaxValue, 
                                               "min": MinValue,
                                               "nominal": NominalValue, 
                                               "title": DeviceName, 
                                               "units": self.Units, 
                                               "type": "temperature",
                                               "exclude_gauge": False,
                                               "from": "gentemp"})
                    return_string = json.dumps(self.GaugeData)
                    self.LogDebug("Bounds Data: " + str(self.GaugeData))
                    self.SendCommand("generator: set_external_gauge_data=" + return_string)
                else:
                    self.LogError("Error in configuration: sensor name, nominal and max values do not have he same number of entries (possibly min values also)")

            self.DeviceList = self.EnumDevices()

            if not len(self.DeviceList):
                self.LogConsole("No sensors found.")
                self.LogError("No sensors found.")
                sys.exit(1)

            # start thread monitor time for exercise
            self.Threads["GenTempThread"] = MyThread(self.GenTempThread, Name="GenTempThread", start=False)
            self.Threads["GenTempThread"].Start()

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

        except Exception as e1:
            self.LogErrorLine("Error in GenTemp init: " + str(e1))
            self.LogConsole("Error in GenTemp init: " + str(e1))
            sys.exit(1)

    # ----------  GenTemp::GetParamList -----------------------------------------
    def GetParamList(self, input_string, bInteger = False):

        ReturnValue = []
        try:
            if input_string != None:
                if len(input_string):
                    ReturnList = input_string.strip().split(",")
                    if len(ReturnList):
                        for Items in ReturnList:
                            Items = Items.strip()
                            if len(Items):
                                if bInteger:
                                    ReturnValue.append(int(Items))
                                else:
                                    ReturnValue.append(Items)
                        if len(ReturnValue):
                            return ReturnValue
            return None
        except Exception as e1:
            self.LogErrorLine("Error in GetParamList: " + str(e1))
            return None

    # ----------  GenTemp::EnumDevices ------------------------------------------
    def EnumDevices(self):

        DeviceList = []
        try:
            # enum DS18B20 temp sensors
            for sensor in glob.glob("/sys/bus/w1/devices/28-*/w1_slave"):
                if not self.CheckBlackList(sensor) and self.DeviceValid(sensor):
                    self.LogDebug("Found DS18B20 : " + sensor)
                    DeviceList.append(sensor)

            # enum type K thermocouples
            # for sensor in glob.glob("/sys/bus/w1/devices/w1_bus_master*/3b-*/w1_slave"):
            for sensor in glob.glob("/sys/bus/w1/devices/3b-*/w1_slave"):
                if not self.CheckBlackList(sensor) and self.DeviceValid(sensor):
                    self.LogDebug("Found type K thermocouple : " + sensor)
                    DeviceList.append(sensor)
            return DeviceList
        except Exception as e1:
            self.LogErrorLine("Error in EnumDevices: " + str(e1))
            return DeviceList

    # ------------ GenTemp::ReadData --------------------------------------------
    def ReadData(self, device):
        try:
            f = open(device, "r")
            data = f.read()
            f.close()
            return data
        except Exception as e1:
            self.LogErrorLine("Error in ReadData for " + device + " : " + str(e1))
            return None

    # ------------ GenTemp::DeviceValid -----------------------------------------
    def DeviceValid(self, device):

        try:
            data = self.ReadData(device)

            if (
                isinstance(data, str)
                and "YES" in data
                and " crc=" in data
                and " t=" in data
            ):
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in DeviceValid for " + device + " : " + str(e1))
            return False

    # ------------ GenTemp::ParseData -------------------------------------------
    def ParseData(self, data):

        try:
            if self.UseMetric:
                units = "C"
            else:
                units = "F"
            if not isinstance(data, str):
                return None, units
            if not len(data):
                return None, units
            (discard, sep, reading) = data.partition(" t=")
            t = float(reading) / 1000.0
            if not self.UseMetric:
                return self.ConvertCelsiusToFahrenheit(t), units
            else:
                return t, units
        except Exception as e1:
            self.LogErrorLine("Error in ParseData: " + str(e1))
            return None, units

    # ------------ GenTemp::GetIDFromDeviceName ---------------------------------
    def GetIDFromDeviceName(self, device):

        try:
            if "28-" in device or "3b-" in device:
                id = device.split("/")[5]
                return id
        except Exception as e1:
            self.LogErrorLine(
                "Error in GetIDFromDeviceName for " + device + " : " + str(e1)
            )
        return "UNKNOWN_ID"

    # ----------  GenTemp::SendCommand ------------------------------------------
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

    # ---------- GenTemp::CheckBlackList-----------------------------------------
    def CheckBlackList(self, device):

        if not isinstance(self.BlackList, list):
            return False
        return any(blacklistitem in device for blacklistitem in self.BlackList)

    # ---------- GenTemp::GenTempThread-----------------------------------------
    def GenTempThread(self):

        time.sleep(1)

        while True:
            try:
                labelIndex = 0
                ReturnDeviceData = []
                for sensor in self.DeviceList:
                    temp, units = self.ParseData(self.ReadData(sensor))
                    if temp != None:
                        self.LogDebug(
                            "Device: %s Reading: %.2f %s"
                            % (self.GetIDFromDeviceName(sensor), temp, units)
                        )
                        if (isinstance(self.DeviceLabels, list) and len(self.DeviceLabels) and (labelIndex < len(self.DeviceLabels))):
                            device_label = self.DeviceLabels[labelIndex]
                        else:
                            device_label = self.GetIDFromDeviceName(sensor)
                        # dict to hold last value, don't update if unchanged
                        LastValue = self.LastValues.get(device_label, None)
                        do_not_send = False
                        if LastValue != None:
                            if LastValue["temp"] == temp:
                                do_not_send = True
                        
                        self.LastValues[device_label] = {"temp": temp, "units": units}
                        if not do_not_send:
                            ReturnDeviceData.append({device_label: "%.2f %s" % (temp, units)})
                    labelIndex += 1
                
                if len(ReturnDeviceData):
                    return_string = json.dumps(ReturnDeviceData)
                    self.SendCommand("generator: set_sensor_data=" + return_string)
                    self.LogDebug(return_string)

                if self.WaitForExit("GenTempThread", float(self.PollTime)):
                    return

            except Exception as e1:
                self.LogErrorLine("Error in GenTempThread: " + str(e1))
                if self.WaitForExit("GenTempThread", float(self.PollTime * 60)):
                    return

    # ----------GenTemp::SignalClose--------------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(1)

    # ----------GenTemp::Close----------------------------------------------
    def Close(self):

        self.KillThread("GenTempThread")
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
    ) = MySupport.SetupAddOnProgram("gentemp")
    GenTempInstance = GenTemp(
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
