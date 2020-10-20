#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: gentemp.py
# PURPOSE: gentemp.py add support for type K thermocouples and DS18B20 temp sesnsors
#
#  AUTHOR: jgyates
#    DATE: 09-12-2019
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------


import datetime, time, sys, signal, os, threading, collections, json, ssl
import atexit, getopt

try:
    from genmonlib.myclient import ClientInterface
    from genmonlib.mylog import SetupLogger
    from genmonlib.myconfig import MyConfig
    from genmonlib.mysupport import MySupport
    from genmonlib.mycommon import MyCommon
    from genmonlib.mythread import MyThread
    from genmonlib.program_defaults import ProgramDefaults

except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)

try:
    import os, time, glob
except Exception as e1:
    print("Error importing modules! :"  + str(e1))
    sys.exit(2)

# Typical reading
# 73 01 4b 46 7f ff 0d 10 41 : crc=41 YES
# 73 01 4b 46 7f ff 0d 10 41 t=23187

#------------ GenTemp class ----------------------------------------------------
class GenTemp(MySupport):

    #------------ GenTemp::init-------------------------------------------------
    def __init__(self,
        log = None,
        loglocation = ProgramDefaults.LogPath,
        ConfigFilePath = MyCommon.DefaultConfPath,
        host = ProgramDefaults.LocalHost,
        port = ProgramDefaults.ServerPort):

        super(GenTemp, self).__init__()

        self.LogFileName = os.path.join(loglocation, "gentemp.log")
        self.AccessLock = threading.Lock()
        # log errors in this module to a file
        self.log = SetupLogger("gentemp", self.LogFileName)

        self.console = SetupLogger("gentemp_console", log_file = "", stream = True)

        self.LastValues = {}

        self.MonitorAddress = host
        self.debug = False
        self.PollTime = 1
        self.BlackList = None

        configfile = os.path.join(ConfigFilePath, 'gentemp.conf')
        try:
            if not os.path.isfile(configfile):
                self.LogConsole("Missing config file : " + configfile)
                self.LogError("Missing config file : " + configfile)
                sys.exit(1)

            self.config = MyConfig(filename = configfile, section = 'gentemp', log = self.log)


            self.UseMetric = self.config.ReadValue('use_metric', return_type = bool, default = False)
            self.PollTime = self.config.ReadValue('poll_frequency', return_type = float, default = 1)
            self.debug = self.config.ReadValue('debug', return_type = bool, default = False)
            self.DeviceLabels = self.GetParamList(self.config.ReadValue('device_labels', default = None))
            self.BlackList = self.GetParamList(self.config.ReadValue('blacklist', default = None))


            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost

        except Exception as e1:
            self.LogErrorLine("Error reading " + configfile + ": " + str(e1))
            self.LogConsole("Error reading " + configfile + ": " + str(e1))
            sys.exit(1)

        try:

            try:
                startcount = 0
                while startcount <= 10:
                    try:
                        self.Generator = ClientInterface(host = self.MonitorAddress, port = port, log = self.log)
                        break
                    except Exception as e1:
                        startcount += 1
                        if startcount >= 10:
                            self.LogConsole("genmon not loaded.")
                            self.LogError("Unable to connect to genmon.")
                            sys.exit(1)
                        time.sleep(1)
                        continue

            except Exception as e1:
                self.LogErrorLine("Error in GenTempThread init: "  + str(e1))

            self.DeviceList = self.EnumDevices()

            if not len(self.DeviceList):
                self.LogConsole("No sensors found.")
                self.LogError("No sensors found.")
                sys.exit(1)

            # start thread monitor time for exercise
            self.Threads["GenTempThread"] = MyThread(self.GenTempThread, Name = "GenTempThread", start = False)
            self.Threads["GenTempThread"].Start()

            atexit.register(self.Close)

        except Exception as e1:
            self.LogErrorLine("Error in GenTemp init: " + str(e1))
            self.LogConsole("Error in GenTemp init: " + str(e1))
            sys.exit(1)

    #----------  GenTemp::GetParamList -----------------------------------------
    def GetParamList(self, input_string):

        ReturnValue = []
        try:
            if input_string != None:
                if len(input_string):
                    ReturnList = input_string.strip().split(",")
                    if len(ReturnList):
                        for Items in ReturnList:
                            Items = Items.strip()
                            if len(Items):
                                ReturnValue.append(Items)
                        if len(ReturnValue):
                            return ReturnValue
            return None
        except Exception as e1:
            self.LogErrorLine("Error in GetParamList: " + str(e1))
            return None
    #----------  GenTemp::EnumDevices ------------------------------------------
    def EnumDevices(self):

        DeviceList = []
        try:
            # enum DS18B20 temp sensors
            for sensor in glob.glob("/sys/bus/w1/devices/28-*/w1_slave"):
                if not self.CheckBlackList(sensor) and self.DeviceValid(sensor):
                    self.LogDebug("Found DS18B20 : " + sensor)
                    DeviceList.append(sensor)

            # enum type K thermocouples
            #for sensor in glob.glob("/sys/bus/w1/devices/w1_bus_master*/3b-*/w1_slave"):
            for sensor in glob.glob("/sys/bus/w1/devices/3b-*/w1_slave"):
                if not self.CheckBlackList(sensor) and self.DeviceValid(sensor):
                    self.LogDebug("Found type K thermocouple : " + sensor)
                    DeviceList.append(sensor)
            return DeviceList
        except Exception as e1:
            self.LogErrorLine("Error in EnumDevices: " + str(e1))
            return DeviceList

    #------------ GenTemp::ReadData --------------------------------------------
    def ReadData(self, device):
        try:
            f = open(device, "r")
            data = f.read()
            f.close()
            return data
        except Exception as e1:
            self.LogErrorLine("Error in ReadData for " + device + " : " + str(e1))
            return None

    #------------ GenTemp::DeviceValid -----------------------------------------
    def DeviceValid(self, device):

        try:
            data = self.ReadData(device)

            if isinstance(data, str) and "YES" in data and " crc=" in data and " t=" in data:
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in DeviceValid for " + device + " : " + str(e1))
            return False
    #------------ GenTemp::ParseData -------------------------------------------
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
            (discard, sep, reading) = data.partition(' t=')
            t = float(reading) / 1000.0
            if not self.UseMetric:
                return self.ConvertCelsiusToFahrenheit(t), units
            else:
                return t, units
        except Exception as e1:
            self.LogErrorLine("Error in ParseData: " + str(e1))
            return None, units

    #------------ GenTemp::GetIDFromDeviceName ---------------------------------
    def GetIDFromDeviceName(self, device):

        try:
            if "28-" in device or "3b-" in device:
                id = device.split("/")[5]
                return id
        except Exception as e1:
            self.LogErrorLine("Error in GetIDFromDeviceName for " + device + " : " + str(e1))
        return "UNKNOWN_ID"


    #----------  GenTemp::SendCommand ------------------------------------------
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
                        self.LogDebug("Device: %s Reading: %.2f %s" % (self.GetIDFromDeviceName(sensor), temp, units))
                        if isinstance(self.DeviceLabels, list) and len(self.DeviceLabels) and (labelIndex < len(self.DeviceLabels)):
                            device_label = self.DeviceLabels[labelIndex]
                        else:
                            device_label = self.GetIDFromDeviceName(sensor)
                        ReturnDeviceData.append({device_label : "%.2f %s" % (temp, units)})
                    labelIndex += 1
                return_string = json.dumps({"External Temperature Sensors": ReturnDeviceData})
                self.SendCommand("generator: set_temp_data=" + return_string )

                self.LogDebug(return_string)
                if self.WaitForExit("GenTempThread", float(self.PollTime)):
                    return

            except Exception as e1:
                self.LogErrorLine("Error in GenTempThread: " + str(e1))
                if self.WaitForExit("GenTempThread", float(self.PollTime * 60)):
                    return


    # ----------GenTemp::Close----------------------------------------------
    def Close(self):
        self.LogError("GenTemp Exit")
        self.KillThread("GenTempThread")
        self.Generator.Close()
#-------------------------------------------------------------------------------
if __name__ == "__main__":

    console = SetupLogger("GenTemp_console", log_file = "", stream = True)
    HelpStr = '\nsudo python gentemp.py -a <IP Address or localhost> -c <path to genmon config file>\n'
    if os.geteuid() != 0:
        console.error("\nYou need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.\n")
        sys.exit(2)

    try:
        ConfigFilePath = ProgramDefaults.ConfPath
        address = ProgramDefaults.LocalHost
        opts, args = getopt.getopt(sys.argv[1:],"hc:a:",["help","configpath=","address="])
    except getopt.GetoptError:
        console.error("Invalid command line argument.")
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            console.error(HelpStr)
            sys.exit()
        elif opt in ("-a", "--address"):
            address = arg
        elif opt in ("-c", "--configpath"):
            ConfigFilePath = arg
            ConfigFilePath = ConfigFilePath.strip()

    port, loglocation = MySupport.GetGenmonInitInfo(ConfigFilePath, log = console)
    log = SetupLogger("client", loglocation + "gentemp.log")

    GenTempInstance = GenTemp(log = log, loglocation = loglocation, ConfigFilePath = ConfigFilePath, host = address, port = port)

    while True:
        time.sleep(0.5)

    sys.exit(1)
