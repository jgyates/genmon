#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: genmopeka.py
# PURPOSE: genmopeka.py add mopeka tank sensor data to genmon
#
#  AUTHOR: jgyates
#    DATE: 07-28-2022
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

# Tank size info: https://learnmetrics.com/propane-tank-sizes/
# https://github.com/spbrogan/sensor.mopeka_pro_check/blob/main/custom_components/mopeka_pro_check/const.py
# https://github.com/spbrogan/mopeka_pro_check


import time, sys, signal, os, threading, json

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


#------------ GenMopekaData class ------------------------------------------------
class GenMopekaData(MySupport):

    #------------ GenMopekaData::init---------------------------------------------
    def __init__(self,
        log = None,
        loglocation = ProgramDefaults.LogPath,
        ConfigFilePath = MyCommon.DefaultConfPath,
        host = ProgramDefaults.LocalHost,
        port = ProgramDefaults.ServerPort,
        console = None):

        super(GenMopekaData, self).__init__()

        self.LogFileName = os.path.join(loglocation, "genmopeka.log")
        self.AccessLock = threading.Lock()

        self.log = log
        self.console = console

        self.MonitorAddress = host
        self.PollTime =  2
        self.tank_address = None
        self.debug = False

        try: 
            from bleson import BDAddress
        except Exception as e1:
            self.LogConsole("The requires library bleson is not installed.")
            self.LogErrorLine("The requires library bleson is not installed." + str(e1))
            sys.exit(2)
        try:
            from mopeka_pro_check.service import MopekaService, MopekaSensor, GetServiceInstance
        except Exception as e1:
            self.LogConsole("The requires library mopeka_pro_check is not installed.")
            self.LogErrorLine("The requires library mopeka_pro_check is not installed: " + str(e1))
            sys.exit(2)

        configfile = os.path.join(ConfigFilePath, 'genmopeka.conf')
        try:
            if not os.path.isfile(configfile):
                self.LogConsole("Missing config file : " + configfile)
                self.LogError("Missing config file : " + configfile)
                sys.exit(1)

            self.config = MyConfig(filename = configfile, section = 'genmopeka', log = self.log)

            self.PollTime = self.config.ReadValue('poll_frequency', return_type = float, default = 60)
            self.debug = self.config.ReadValue('debug', return_type = bool, default = False)
            self.tank_address = self.config.ReadValue('tank_address', default = None)
            self.tank_type = self.config.ReadValue('tank_type', default = None)
            self.min_mm = self.config.ReadValue('min_mm', return_type = int, default = None, NoLog = True)
            self.max_mm = self.config.ReadValue('max_mm', return_type = int, default = None, NoLog = True)
            self.scan_time = self.config.ReadValue('scan_time', return_type = int, default = 15)    # num of seconds to scan

            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost

        except Exception as e1:
            self.LogErrorLine("Error reading " + configfile + ": " + str(e1))
            self.LogConsole("Error reading " + configfile + ": " + str(e1))
            sys.exit(1)

        try:
            self.LogDebug("Tank Address = " + str(self.tank_address))

            self.Generator = ClientInterface(host = self.MonitorAddress, port = port, log = self.log)

            
            if self.tank_address == None or self.tank_address == "":
                self.LogError("No valid tank address found: " + str(self.tank_address))
                self.LogConsole("No valid tank address found: " + str(self.tank_address))
                sys.exit(1)

            if "," in self.tank_address:
                self.tank_address = self.tank_address.split(",")
            else:
                temp = []
                temp.append(self.tank_address)
                self.tank_address = temp

            if len(self.tank_address) > 4:
                self.LogError("Only four tanks sensors are supportd. Found " + str(len(self.tank_address)))
                self.LogConsole("Only four tanks sensors are supportd. Found " + str(len(self.tank_address)))
                sys.exit(1)

            index = 0
            self.tank_address = list(map(str.strip, self.tank_address))
            for tank in self.tank_address:
                # must be in format xx:xx:xx:xx:xx:xx
                import re
                if not re.match("[0-9a-f]{2}([-:]?)[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", tank.lower()):
                    self.LogError("Invalid tank sensor address format: " + str(len(tank)))
                    self.LogConsole("Invalid tank sensor address format: " + str(len(tank)))
                    sys.exit(1)
                if len(tank) != 17:
                    self.LogError("Invalid tank sensor address length: " + str(len(tank)))
                    self.LogConsole("Invalid tank sensor address length: " + str(len(tank)))
                    sys.exit(1)
                
            self.bd_tank_address = list(map(BDAddress, self.tank_address))

            if (self.tank_type == None or self.tank_type.lower() == "custom") and (self.min_mm == None or self.max_mm == None):
                self.LogError("Invalid tank type: " + str(self.tank_type) + ": " + str(self.min_mm) + ": " + str(self.max_mm))
                self.LogConsole("Invalid tank type: " + str(self.tank_type) + ": " + str(self.min_mm) + ": " + str(self.max_mm))
                sys.exit(1)
            
            if self.tank_type == None:
                self.tank_type == "Custom"

            if self.tank_type.lower() != "custom":
                # default tank mim
                self.min_mm = 38.1

            if self.tank_type.lower() == "20_lb":
                self.max_mm = 254
            elif self.tank_type.lower() == "30_lb":
                self.max_mm = 381
            elif self.tank_type.lower() == "40_lb":
                self.max_mm = 508
            elif self.tank_type.lower() == "100_lb":
                self.max_mm = 915
            elif self.tank_type.lower() == "100_gal":
                # TODO
                self.max_mm = 915
            elif self.tank_type.lower() == "250_gal":
                # TODO
                self.max_mm = 915
            elif self.tank_type.lower() == "500_gal":
                # TODO
                self.max_mm = 915
            elif self.tank_type.lower() == "custom":
                # TODO
                if not isinstance(self.max_mm, int) or self.max_mm <= 1 or self.min_mm < 0:
                    self.LogError("Invalid min/max for custom tank type: min:" + str(self.min_mm) + ", max: " + str(self.max_mm))
                    self.LogConsole("Invalid min/max for custom tank type: min:" + str(self.min_mm) + ", max: " + str(self.max_mm))
                    sys.exit(1)

            self.LogDebug("min: " + str(self.min_mm) + " , max: " + str(self.max_mm))
            self.LogDebug("Tank Type: " + str(self.tank_type))

            self.mopeka = GetServiceInstance()
            self.mopeka.SetHostControllerIndex(0)
            for tank in self.tank_address:
                self.mopeka.AddSensorToMonitor(MopekaSensor(tank))
            

            # start thread monitor time for exercise
            self.Threads["TankCheckThread"] = MyThread(self.TankCheckThread, Name = "TankCheckThread", start = False)
            self.Threads["TankCheckThread"].Start()

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

        except Exception as e1:
            self.LogErrorLine("Error in GenMopekaData init: " + str(e1))
            self.console.error("Error in GenMopekaData init: " + str(e1))
            sys.exit(1)

    #----------  GenMopekaData::SendCommand --------------------------------------
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
    def SendMessage(self, title, body, type, onlyonce = False):

        try:
            message = {
                    "title": title,
                    "body": body,
                    "type": type,
                    "onlyonce" : onlyonce
                    }
            command = "generator: notify_message=" + json.dumps(message)

            data = self.SendCommand(command)
            return data
        except Exception as e1:
            self.LogErrorLine("Error in SendMessage: " + str(e1))
            return ""
    # ---------- GenMopekaData::GetTankReading------------------------------------
    def GetTankReading(self, bd_address):
        try:
           
            if self.min_mm == None or self.max_mm == None:
                self.LogError("min or max not set: max: " + str(self.max_mm) + "; min: " + (str(self.min_mm)))
                return None
            if len(self.mopeka.SensorMonitoredList) == 0:
                self.LogDebug("No sensors monitoried.")
                return None
            if self.mopeka.SensorMonitoredList[bd_address]._last_packet == None:
                self.LogDebug("No sensor comms detected.")
                return None 
            reading_depth = self.mopeka.SensorMonitoredList[bd_address]._last_packet.TankLevelInMM
            self.LogDebug("Tank Level in mm: " + str(reading_depth))
            if reading_depth:
                if reading_depth > self.max_mm:
                    reading_depth = self.max_mm
                tanksize = self.max_mm - self.min_mm
                return round(((reading_depth - self.min_mm) / tanksize ) * 100, 2)
            else:
                return 0
        except Exception as e1:
            self.LogErrorLine("Error in GetTankReading: " + str(e1))
            return None
    # ---------- GenMopekaData::TankCheckThread-----------------------------------
    def TankCheckThread(self):

        time.sleep(1)

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

                
                reading = self.GetTankReading(self.bd_tank_address[0])
                if reading != None:
                    self.LogDebug("Tank1 = " + str(reading))
                    dataforgenmon["Percentage"] = reading 

                if len(self.bd_tank_address) >= 2:
                    reading = self.GetTankReading(self.bd_tank_address[1])
                    if reading != None:
                        self.LogDebug("Tank2 = " + str(reading))
                        dataforgenmon["Percentage2"] = reading 

                if len(self.bd_tank_address) >= 3:
                    reading = self.GetTankReading(self.bd_tank_address[2])
                    if reading != None:
                        self.LogDebug("Tank3 = " + str(reading))
                        dataforgenmon["Percentage3"] = reading 

                if len(self.bd_tank_address) >= 4:
                    reading = self.GetTankReading(self.bd_tank_address[3])
                    if reading != None:
                        self.LogDebug("Tank4 = " + str(reading))
                        dataforgenmon["Percentage4"] = reading 

                if len(dataforgenmon) != 0:
                    dataforgenmon["Tank Name"] = "Mopeka Sensor Tank"     
                    
                    self.LogDebug("Tank Data = " + json.dumps(dataforgenmon))

                    retVal = self.SendCommand("generator: set_tank_data=" + json.dumps(dataforgenmon))
                    self.LogDebug(retVal)
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
        self.Generator.Close()
#-------------------------------------------------------------------------------
if __name__ == "__main__":

    console, ConfigFilePath, address, port, loglocation, log = MySupport.SetupAddOnProgram("genmopeka")

    GenMopekaDataInstance = GenMopekaData(log = log, loglocation = loglocation, ConfigFilePath = ConfigFilePath, host = address, port = port, console = console)

    while True:
        time.sleep(0.5)

    sys.exit(1)
