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


import time, sys, signal, os, threading, json, math

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
            self.send_notices = self.config.ReadValue('send_notices', return_type = bool, default = False)

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

            if self.tank_type.lower() == "20_lb":       # vertical
                self.max_mm = 254
            elif self.tank_type.lower() == "30_lb":     # vertical
                self.max_mm = 381
            elif self.tank_type.lower() == "40_lb":     # vertical
                self.max_mm = 508
            elif self.tank_type.lower() == "100_lb":    # vertical, 24 Gal
                self.max_mm = 915
            elif self.tank_type.lower() == "custom":
                # TODO
                if not isinstance(self.max_mm, int) or self.max_mm <= 1 or self.min_mm < 0:
                    self.LogError("Invalid min/max for custom tank type: min:" + str(self.min_mm) + ", max: " + str(self.max_mm))
                    self.LogConsole("Invalid min/max for custom tank type: min:" + str(self.min_mm) + ", max: " + str(self.max_mm))
                    sys.exit(1)

            self.TankDimensions = {
                # units are inches and gallons
                "20_lb" : { "length" : 18, "diameter" : 12, "volume" : 4.6, "orientation" : "vertical"},
                "30_lb" : { "length" : 24, "diameter" : 12.5, "volume" : 7.1,  "orientation" : "vertical"},
                "40_lb" : { "length" : 27, "diameter" : 14.5, "volume" : 9.4,  "orientation" : "vertical"},
                "100_lb" : { "length" : 48, "diameter" : 14.5, "volume" : 24,  "orientation" : "vertical"},
                "200_lb" : { "length" : 48, "diameter" : 19.5, "volume" : 46,  "orientation" : "vertical"},
                "120_gal" : { "length" : 52, "diameter" : 30, "volume" : 120,  "orientation" : "vertical"},
                "250_gal" : { "length" : 92, "diameter" : 30, "volume" : 250,  "orientation" : "horizontal"},
                "500_gal" : { "length" : 120, "diameter" : 37, "volume" : 500,  "orientation" : "horizontal"},
                "1000_gal" : { "length" : 190, "diameter" : 41,  "volume" : 1000, "orientation" : "horizontal"},
            }
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
            if not self.send_notices:
                return "disabled"
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
           
            if len(self.mopeka.SensorMonitoredList) == 0:
                self.LogDebug("No sensors monitoried.")
                return None
            if self.mopeka.SensorMonitoredList[bd_address]._last_packet == None:
                self.SendMessage("Genmon Warning for Mopeka Sensor Add On","Unable to communicate with Mopeka Pro sensor.", "error", True)
                self.LogDebug("No sensor comms detected.")
                return None 
            reading_depth = self.mopeka.SensorMonitoredList[bd_address]._last_packet.TankLevelInMM
            self.LogDebug("Tank Level in mm: " + str(reading_depth))
            battery = self.mopeka.SensorMonitoredList[bd_address]._last_packet.BatteryPercent
            if battery < 15:
                message = "Warning, battery is low. Battery percentage is " + str(battery)
                self.SendMessage("Genmon Warning for Mopeka Sensor Add On",message, "error", True)
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
                self.LogDebug("No tank dimensions found for tank type " + str(self.tank_type))
                if self.max_mm != None or self.min_mm != None:
                    self.LogDebug("Error: min: " + str(self.min_mm) + " , max: " + str(self.max_mm))
                    return None
                
                if reading_mm > self.max_mm:
                    reading_mm = self.max_mm
                tanksize = self.max_mm - self.min_mm
                return round(((reading_mm - self.min_mm) / tanksize ) * 100, 2)

            if dimensions["orientation"].lower() == "horizontal":
                volume = self.CalculateHorizontal(dimensions["diameter"], dimensions["length"],reading_inches)
            elif dimensions["orientation"].lower() == "vertical":
                volume = self.CalculateVertical(dimensions["diameter"], dimensions["length"],reading_inches)
            else:
                self.LogError("Error in ConvertTankReading: invalid value in dimenstions: " + str(dimensions["orientation"]))
                return 0
            self.LogDebug("Volume: " + str(volume))
            if volume >= dimensions["volume"]:
                return 100
            return round((volume / dimensions["volume"]) * 100, 2)

        except Exception as e1:
            self.LogErrorLine("Error in ConvertTankReading: " + str(e1))
            return None

    # ---------- GenMopekaData::SegmentArea-----------------------------------
    def SegmentArea(self, depth, diameter):

        try:
            if depth > 0 and diameter > 0:
                radius = diameter / 2
                temp = radius - depth
                chordl = 2 * math.sqrt(2* depth * radius - depth * depth)
                ang = math.acos(temp/radius) * 2
                arcl = ang * radius
                seg = ((arcl * radius - chordl * temp )/2)
                return seg 
            else:
                return 0
        except Exception as e1:
            self.LogErrorLine("Error in SegmentArea: " + str(e1))
            return 0
        
    # ---------- GenMopekaData::CalculateHorizontal------------------------
    def CalculateHorizontal(self, diameter, length, depth):

        try:
            if depth > diameter:
                depth = diameter 
            if diameter > 1 and length > 1 and depth > 0:
                area = self.SegmentArea(depth, diameter)
                volume = ((area * length) / 1728) * 7.48
                return round(volume , 2)
            else:
                return 0
        except Exception as e1:
            self.LogErrorLine("Error in CalcRoundHorizontal: " + str(e1))
            return 0

    # ---------- GenMopekaData::CalculateVertical------------------------
    def CalculateVertical(self, diameter, length, depth):

        # Everything is passed in inches and returned in gallons.
        # Remember that a Propane tank is considered full at 80% but the Tank Sensor mainly shows a percentage anyways.
        # When so when I fill my 250 gal tank, they only put 200 gal in it. 
        # The Tank App shows 80% full, BUT you can easily scale that to 
        # 0-100% by using tank size io gallons x .8

        self.LogDebug("diameter: " + str(diameter) + " length: " + str(length) + " depth: " + str(depth) )
        try:
            if depth > length:
                # If tank is over full then it equals full 
                depth = length 
            if diameter > 1 and length > 1 and depth > 0:
                radius = diameter / 2 
                area = ((radius * radius) *math.pi) * depth # cubic inches 
                volume = (area / 1728) * 7.48   # cubic inches to cubic feet, then to gallons
                return round(volume , 2)
            else:
                return 0
        except Exception as e1:
            self.LogErrorLine("Error in CalcRoundVertical: " + str(e1))
            return 0

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
