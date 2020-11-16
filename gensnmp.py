#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: gensnmp.py
# PURPOSE: gensnmp.py add SNMP support to genmon
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

    from pysnmp.carrier.asyncore.dispatch import AsyncoreDispatcher
    from pysnmp.carrier.asyncore.dgram import udp, udp6, unix
    from pyasn1.codec.ber import encoder, decoder
    from pysnmp.proto import api
    from pysnmp.proto.rfc1902 import *
    import time, bisect
except Exception as e1:
    print("Error loading pysnmp! :"  + str(e1))
    sys.exit(2)

# requires:
#    sudo pip install pysnmp
#
#------------ MyOID class ------------------------------------------------------
class MyOID(MySupport):
    def __init__(self, name, return_type  = None, description = None, default  = None, keywords = [], log = None):
        self.log = log
        self.name = name
        self.description = description
        self.return_type = return_type
        self.value = default
        self.keywords = keywords
        self.birthday = time.time()
        if return_type == str:
            pass
        elif return_type == int:
            pass
        else:
            pass
    def __eq__(self, other): return self.name == other

    def __ne__(self, other): return self.name != other

    def __lt__(self, other): return self.name < other

    def __le__(self, other): return self.name <= other

    def __gt__(self, other): return self.name > other

    def __ge__(self, other): return self.name >= other

    def __call__(self, protoVer):

        try:
            if self.return_type == str:
                return api.protoModules[protoVer].OctetString(self.value)
            elif self.return_type == int:
                return api.protoModules[protoVer].Integer(self.value)
            elif self.return_type == type(TimeTicks):
                return api.protoModules[protoVer].TimeTicks((time.time() - self.birthday) * 100)
            else:
                self.LogError("Invalid type in MyOID: " + str(self.return_type))
                return  api.protoModules[protoVer].Integer(self.value)
        except Exception as e1:
            self.LogErrorLine("Error in MyOid __call__: " + str(e1))
            return None

#------------ GenSNMP class ----------------------------------------------------
class GenSNMP(MySupport):

    #------------ GenSNMP::init-------------------------------------------------
    def __init__(self,
        log = None,
        loglocation = ProgramDefaults.LogPath,
        ConfigFilePath = MyCommon.DefaultConfPath,
        host = ProgramDefaults.LocalHost,
        port = ProgramDefaults.ServerPort,
        console = None):

        super(GenSNMP, self).__init__()

        self.AccessLock = threading.Lock()

        self.log = log
        self.console = console

        self.mibData = []
        self.LastValues = {}
        self.transportDispatcher = None

        self.UseNumeric = False
        self.MonitorAddress = host
        self.debug = False
        self.PollTime = 1
        self.BlackList = ["Outage"] #["Monitor"]
        configfile = os.path.join(ConfigFilePath , 'gensnmp.conf')
        try:
            if not os.path.isfile(configfile):
                self.LogConsole("Missing config file : " + configfile)
                self.LogError("Missing config file : " + configfile)
                sys.exit(1)

            self.genmon_config = MyConfig(filename = os.path.join(ConfigFilePath, 'genmon.conf'), section = 'GenMon', log = self.log)
            self.ControllerSelected = self.genmon_config.ReadValue('controllertype', default = "generac_evo_nexus")

            self.config = MyConfig(filename = configfile, section = 'gensnmp', log = self.log)

            self.UseNumeric = self.config.ReadValue('use_numeric', return_type = bool, default = False)
            self.PollTime = self.config.ReadValue('poll_frequency', return_type = float, default = 1)
            self.debug = self.config.ReadValue('debug', return_type = bool, default = False)
            self.community = self.config.ReadValue('community', default = "public")
            self.enterpriseID = self.config.ReadValue('enterpriseid', return_type = int, default = 9999)
            self.baseOID = (1, 3, 6, 1, 4, 1, self.enterpriseID)

            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost

        except Exception as e1:
            self.LogErrorLine("Error reading " + configfile + ": " + str(e1))
            self.LogConsole("Error reading " + configfile + ": " + str(e1))
            sys.exit(1)

        try:

            self.Generator = ClientInterface(host = self.MonitorAddress, port = port, log = self.log)

            self.GetGeneratorStartInfo()

            # start thread monitor time for exercise
            self.Threads["SNMPThread"] = MyThread(self.SNMPThread, Name = "SNMPThread", start = False)
            self.Threads["SNMPThread"].Start()

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

            self.SetupSNMP() # Must be last since we do not return from this call

        except Exception as e1:
            self.LogErrorLine("Error in GenSNMP init: " + str(e1))
            self.LogConsole("Error in GenSNMP init: " + str(e1))
            sys.exit(1)
    #----------  GenSNMP::ControllerIsEvolutionNexus --------------------------------
    def ControllerIsEvolutionNexus(self):
        try:
            if "evolution" in self.StartInfo["Controller"].lower() or "nexus" in self.StartInfo["Controller"].lower():
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in ControllerIsEvolutionNexus: " + str(e1))
            return False

    #----------  GenSNMP::ControllerIsGeneracH100 ------------------------------
    def ControllerIsGeneracH100(self):
        try:
            if "h-100" in self.StartInfo["Controller"].lower() or "g-panel" in self.StartInfo["Controller"].lower():
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in ControllerIsGeneracH100: " + str(e1))
            return False
    #----------  GenSNMP::GetGeneratorStartInfo --------------------------------
    def GetGeneratorStartInfo(self):

        try:
            data = self.SendCommand("generator: start_info_json")
            self.StartInfo = {}
            self.StartInfo = json.loads(data)

            return True
        except Exception as e1:
            self.LogErrorLine("Error in GetGeneratorStartInfo: " + str(e1))
            return False

    #----------  GenSNMP::UpdateSNMPData ----------------------------------------
    def UpdateSNMPData(self, Path, Value):

        try:
            if self.transportDispatcher == None:
                return
            oid = self.GetOID(Path)
            if oid == None:
                return
            self.LogDebug(Path + " : " + str(Value))
            if self.mibDataIdx[oid].return_type == str:
                self.mibDataIdx[oid].value = str(Value)
            elif self.mibDataIdx[oid].return_type == int:
                self.mibDataIdx[oid].value = int(self.removeAlpha(Value))
            else:
                self.LogError("Invalid type in UpdateSNMPData: " + str(self.mibDataIdx[oid].return_type))
                self.mibDataIdx[oid].value = Value
        except Exception as e1:
            self.LogErrorLine("Error in UpdateSNMPData: " + str(e1))

    #----------  GenSNMP::GetOID -----------------------------------------------
    def GetOID(self, path):
        try:
            if not len(path):
                return None

            for mib in self.mibData:
                if len(mib.keywords):
                    if all(x in path for x in mib.keywords):
                        self.LogDebug(str(mib.name))
                        return mib.name
            return None

        except Exception as e1:
            self.LogErrorLine("Error in GetOID: " + str(e1))

    #----------  GenSNMP::GetData ----------------------------------------------
    def GetData(self, namelist):

        try:
            if not len(namelist):
                return None

            for key in self.LastValues.keys():
                if all(x in key for x in namelist):
                    return self.LastValues[key]
            return None
        except Exception as e1:
            self.LogErrorLine("Error in GetData: " + str(e1))

    #----------  GenSNMP::AddOID -----------------------------------------------
    def AddOID(self, id, return_type, description, default, keywords):

        self.mibData.append(MyOID(self.baseOID+id, return_type, description, default,keywords, log = self.log))

    #----------  GenSNMP::SetupSNMP --------------------------------------------
    def SetupSNMP(self):

        try:
            if self.ControllerIsEvolutionNexus() or self.ControllerSelected == "generac_evo_nexus":
                CtlID = 0
            elif self.ControllerIsGeneracH100() or self.ControllerSelected == "h_100":
                CtlID = 1
            else:
                self.LogError("Error: Invalid controller type")
                self.LogError(str(self.ControllerSelected))
                return

            self.mibData.append(MyOID((1,3,6,1,2,1,1,1),return_type = str, description = "SysDescr", default = "Genmon Generator Monitor",log = self.log))
            self.mibData.append(MyOID((1,3,6,1,2,1,1,3,0),return_type = type(TimeTicks), description = "Uptime",log = self.log))

            if self.ControllerIsEvolutionNexus() or self.ControllerSelected == "generac_evo_nexus":
                self.LogDebug("Evo/Nexus")
                # Status Engine
                self.AddOID((CtlID,0,0,0),return_type = str, description = "SwitchState", default = "Unknown", keywords = ["Status/Engine","Switch State"])
                self.AddOID((CtlID,0,0,1),return_type = str, description = "EngineState", default = "Unknown", keywords = ["Status/Engine","Engine State"])
                self.AddOID((CtlID,0,0,2),return_type = str, description = "ActiveRelays", default = "", keywords = ["Status/Engine","Active Relays"])
                self.AddOID((CtlID,0,0,3),return_type = str, description = "ActiveSensors", default = "", keywords = ["Status/Engine","Active Sensors"])
                self.AddOID((CtlID,0,0,4),return_type = str, description = "BatteryVolts", default = "", keywords = ["Status/Engine","Battery Voltage"])
                self.AddOID((CtlID,0,0,5),return_type = str, description = "BatteryStatus", default = "", keywords = ["Status/Engine","Battery Status"])
                self.AddOID((CtlID,0,0,6),return_type = str, description = "RPM", default = "", keywords = ["Status/Engine","RPM"])
                self.AddOID((CtlID,0,0,7),return_type = str, description = "Frequency", default = "", keywords = ["Status/Engine","Frequency"])
                self.AddOID((CtlID,0,0,8),return_type = str, description = "OutputVoltage", default = "", keywords = ["Status/Engine","Output Voltage"])
                self.AddOID((CtlID,0,0,9),return_type = str, description = "OutputCurrent", default = "", keywords = ["Status/Engine","Output Current"])
                self.AddOID((CtlID,0,0,10),return_type = str, description = "OutputPower", default = "", keywords = ["Status/Engine","Output Power"])
                self.AddOID((CtlID,0,0,11),return_type = str, description = "RotorPoles", default = "", keywords = ["Status/Engine","Rotor Poles"])
                # Status Line
                self.AddOID((CtlID,0,1,0),return_type = str, description = "UtilityVoltage", default = "", keywords = ["Status/Line","Utility Voltage"])
                self.AddOID((CtlID,0,1,1),return_type = str, description = "UtilityVoltageMax", default = "", keywords = ["Status/Line","Utility Max Voltage"])
                self.AddOID((CtlID,0,1,2),return_type = str, description = "UtilityVoltageMin", default = "", keywords = ["Status/Line","Utility Min Voltage"])
                self.AddOID((CtlID,0,1,3),return_type = str, description = "UtilityThresholdVoltage", default = "", keywords = ["Status/Line","Utility Threshold Voltage"])
                self.AddOID((CtlID,0,1,4),return_type = str, description = "UtilityPickupVoltage", default = "", keywords = ["Status/Line","Utility Pickup Voltage"])
                self.AddOID((CtlID,0,1,4),return_type = str, description = "SetOutputVoltage", default = "", keywords = ["Status/Line","Set Output Voltage"])
                # Status Last Alarms
                self.AddOID((CtlID,0,2,0),return_type = str, description = "LastAlarmLog", default = " ", keywords = ["Status","Last Log","Alarm Log"])
                self.AddOID((CtlID,0,2,1),return_type = str, description = "LastServiceLog", default = " ", keywords = ["Status","Last Log","Service Log"])
                self.AddOID((CtlID,0,2,2),return_type = str, description = "LastRunLog", default = " ", keywords = ["Status","Last Log","Run Log"])
                # Status Time
                self.AddOID((CtlID,0,3,0),return_type = str, description = "MonitorTime", default = " ", keywords = ["Status/Time","Monitor Time"])
                self.AddOID((CtlID,0,3,1),return_type = str, description = "GeneratorTime", default = " ", keywords = ["Status/Time","Generator Time"])

                #Maintenance
                self.AddOID((CtlID,1,0,0),return_type = str, description = "GeneratorModel", default = " ", keywords = ["Maintenance","Model"])
                self.AddOID((CtlID,1,0,1),return_type = str, description = "SerialNumber", default = " ", keywords = ["Maintenance","Generator Serial Number"])
                self.AddOID((CtlID,1,0,2),return_type = str, description = "Controller", default = " ", keywords = ["Maintenance","Controller Detected"])
                self.AddOID((CtlID,1,0,3),return_type = str, description = "NominalRPM", default = " ", keywords = ["Maintenance","Nominal RPM"])
                self.AddOID((CtlID,1,0,4),return_type = str, description = "RatedkW", default = " ", keywords = ["Maintenance","Rated kW"])
                self.AddOID((CtlID,1,0,5),return_type = str, description = "RatedFreq", default = " ", keywords = ["Maintenance","Nominal Frequency"])
                self.AddOID((CtlID,1,0,6),return_type = str, description = "FuelType", default = " ", keywords = ["Maintenance","Fuel Type"])
                self.AddOID((CtlID,1,0,7),return_type = str, description = "FuelLevelSensor", default = " ", keywords = ["Maintenance","Fuel Level Sensor"])
                self.AddOID((CtlID,1,0,8),return_type = str, description = "EstFuelInTank", default = " ", keywords = ["Maintenance","Estimated Fuel In Tank"])
                self.AddOID((CtlID,1,0,9),return_type = str, description = "Displacement", default = " ", keywords = ["Maintenance","Engine Displacement"])
                self.AddOID((CtlID,1,0,10),return_type = str, description = "AmbientTemp", default = " ", keywords = ["Maintenance","Ambient Temperature Sensor"])
                self.AddOID((CtlID,1,0,11),return_type = str, description = "kwH30", default = " ", keywords = ["Maintenance","kW Hours in last 30 days"])
                self.AddOID((CtlID,1,0,12),return_type = str, description = "Fuel30", default = " ", keywords = ["Maintenance","Fuel Consumption in last 30 days"])
                self.AddOID((CtlID,1,0,13),return_type = str, description = "TotalFuelUsed", default = " ", keywords = ["Maintenance","Total Power Log Fuel Consumption"])
                self.AddOID((CtlID,1,0,14),return_type = str, description = "RunHours30", default = " ", keywords = ["Maintenance","Run Hours in last 30 days"])
                self.AddOID((CtlID,1,0,15),return_type = str, description = "EstHoursInTank", default = " ", keywords = ["Maintenance","Hours of Fuel Remaining","Estimated"])
                self.AddOID((CtlID,1,0,16),return_type = str, description = "LoadHoursInTank", default = " ", keywords = ["Maintenance","Hours of Fuel Remaining","Current"])
                self.AddOID((CtlID,1,0,17),return_type = str, description = "FuelInTank", default = " ", keywords = ["Maintenance","Fuel In Tank (Sensor)"])

                #Maintenance->Controller Settings
                self.AddOID((CtlID,1,1,0),return_type = str, description = "CalCurrent1", default = " ", keywords = ["Maintenance/Controller Settings","Calibrate Current 1"])
                self.AddOID((CtlID,1,1,1),return_type = str, description = "CalCurrent1", default = " ", keywords = ["Maintenance/Controller Settings","Calibrate Current 2"])
                self.AddOID((CtlID,1,1,2),return_type = str, description = "CalVolts", default = " ", keywords = ["Maintenance/Controller Settings","Calibrate Volts"])
                self.AddOID((CtlID,1,1,3),return_type = str, description = "NominalLineVolts", default = " ", keywords = ["Maintenance/Controller Settings","Nominal Line Voltage"])
                self.AddOID((CtlID,1,1,4),return_type = str, description = "RatedMaxPower", default = " ", keywords = ["Maintenance/Controller Settings","Rated Max Power"])
                self.AddOID((CtlID,1,1,5),return_type = str, description = "ParamGroup", default = " ", keywords = ["Maintenance/Controller Settings","Param Group"])
                self.AddOID((CtlID,1,1,6),return_type = str, description = "VoltageCode", default = " ", keywords = ["Maintenance/Controller Settings","Voltage Code"])
                self.AddOID((CtlID,1,1,7),return_type = str, description = "Phase", default = " ", keywords = ["Maintenance/Controller Settings","Phase"])
                self.AddOID((CtlID,1,1,8),return_type = str, description = "HoursProtection", default = " ", keywords = ["Maintenance/Controller Settings","Hours of Protection"])
                self.AddOID((CtlID,1,1,9),return_type = str, description = "VoltsPerHz", default = " ", keywords = ["Maintenance/Controller Settings","Volts Per Hertz"])
                self.AddOID((CtlID,1,1,10),return_type = str, description = "Gain", default = " ", keywords = ["Maintenance/Controller Settings","Gain"])
                self.AddOID((CtlID,1,1,11),return_type = str, description = "TargetFreq", default = " ", keywords = ["Maintenance/Controller Settings","Target Frequency"])
                self.AddOID((CtlID,1,1,12),return_type = str, description = "TargetVolts", default = " ", keywords = ["Maintenance/Controller Settings","Target Voltage"])
                # Maintenance->Exercise
                self.AddOID((CtlID,1,2,0),return_type = str, description = "ExerciseTime", default = " ", keywords = ["Maintenance/Exercise","Exercise Time"])
                self.AddOID((CtlID,1,2,1),return_type = str, description = "ExerciseDuration", default = " ", keywords = ["Maintenance/Exercise","Exercise Duration"])
                #Maintenance->Service
                self.AddOID((CtlID,1,3,0),return_type = str, description = "AFDue", default = " ", keywords = ["Maintenance/Service","Air Filter Service Due"])
                self.AddOID((CtlID,1,3,1),return_type = str, description = "OilDue", default = " ", keywords = ["Maintenance/Service","Oil and Oil Filter Service Due"])
                self.AddOID((CtlID,1,3,2),return_type = str, description = "SPDue", default = " ", keywords = ["Maintenance/Service","Spark Plug Service Due"])
                self.AddOID((CtlID,1,3,3),return_type = str, description = "BattServiceDue", default = " ", keywords = ["Maintenance/Service","Battery Service Due"])
                self.AddOID((CtlID,1,3,4),return_type = str, description = "ServiceADue", default = " ", keywords = ["Maintenance/Service","Service A Due"])
                self.AddOID((CtlID,1,3,5),return_type = str, description = "ServiceBDue", default = " ", keywords = ["Maintenance/Service","Service B Due"])
                self.AddOID((CtlID,1,3,6),return_type = str, description = "BatteryCheckDue", default = " ", keywords = ["Maintenance/Service","Battery Check Due"])
                self.AddOID((CtlID,1,3,7),return_type = str, description = "TotalRunHours", default = " ", keywords = ["Maintenance/Service","Total Run Hours"])
                self.AddOID((CtlID,1,3,8),return_type = str, description = "HardwareVersion", default = " ", keywords = ["Maintenance/Service","Hardware Version"])
                self.AddOID((CtlID,1,3,9),return_type = str, description = "FirmwareVersion", default = " ", keywords = ["Maintenance/Service","Firmware Version"])

            elif self.ControllerIsGeneracH100() or self.ControllerSelected == "h_100":
                self.LogDebug("H-100/GPanel")
                # Engine
                self.AddOID((CtlID,0,0,0),return_type = str, description = "SwitchState", default = " ", keywords = ["Status/Engine","Switch State"])
                self.AddOID((CtlID,0,0,1),return_type = str, description = "EngineStatus", default = " ", keywords = ["Status/Engine","Engine State"])
                self.AddOID((CtlID,0,0,2),return_type = str, description = "GeneratorStatus", default = " ", keywords = ["Status/Engine","Generator Status"])
                self.AddOID((CtlID,0,0,3),return_type = str, description = "OutputPower", default = " ", keywords = ["Status/Engine","Output Power"])
                self.AddOID((CtlID,0,0,4),return_type = str, description = "OutputPowerFactor", default = " ", keywords = ["Status/Engine","Power Factor"])
                self.AddOID((CtlID,0,0,5),return_type = str, description = "RPM", default = 0, keywords = ["Status/Engine/RPM"])
                self.AddOID((CtlID,0,0,6),return_type = str, description = "Frequency", default = " ", keywords = ["Status/Engine/Frequency"])
                self.AddOID((CtlID,0,0,7),return_type = str, description = "ThrottlePosition", default = " ", keywords = ["Status/Engine","Throttle Position"])
                self.AddOID((CtlID,0,0,8),return_type = str, description = "CoolantTemp", default = " ", keywords = ["Status/Engine","Coolant Temp"])
                self.AddOID((CtlID,0,0,9),return_type = str, description = "CoolantLevel", default = " ", keywords = ["Status/Engine","Coolant Level"])
                self.AddOID((CtlID,0,0,10),return_type = str, description = "OilPressure", default = " ", keywords = ["Status/Engine","Oil Pressure"])
                self.AddOID((CtlID,0,0,11),return_type = str, description = "OilTemp", default = " ", keywords = ["Status/Engine","Oil Temp"])
                self.AddOID((CtlID,0,0,12),return_type = str, description = "FuelLevel", default = " ", keywords = ["Status/Engine","Fuel Level"])
                self.AddOID((CtlID,0,0,13),return_type = str, description = "OxygeSensor", default = " ", keywords = ["Status/Engine","Oxygen Sensor"])
                self.AddOID((CtlID,0,0,14),return_type = str, description = "CurrentPhaseA", default = " ", keywords = ["Status/Engine","Current Phase A"])
                self.AddOID((CtlID,0,0,15),return_type = str, description = "CurrentPhaseB", default = " ", keywords = ["Status/Engine","Current Phase B"])
                self.AddOID((CtlID,0,0,16),return_type = str, description = "CurrentPhaseC", default = " ", keywords = ["Status/Engine","Current Phase C"])
                self.AddOID((CtlID,0,0,17),return_type = str, description = "AvgCurrent", default = " ", keywords = ["Status/Engine","Average Current"])
                self.AddOID((CtlID,0,0,18),return_type = str, description = "VoltageAB", default = " ", keywords = ["Status/Engine","Voltage A-B"])
                self.AddOID((CtlID,0,0,19),return_type = str, description = "VoltageBC", default = " ", keywords = ["Status/Engine","Voltage B-C"])
                self.AddOID((CtlID,0,0,20),return_type = str, description = "VoltageCA", default = " ", keywords = ["Status/Engine","Voltage C-A"])
                self.AddOID((CtlID,0,0,21),return_type = str, description = "AvgVoltage", default = " ", keywords = ["Status/Engine","Average Voltage"])
                self.AddOID((CtlID,0,0,22),return_type = str, description = "AirFuelDutyCycle", default = " ", keywords = ["Status/Engine","Air Fuel Duty Cycle" ])
                # Alarms
                self.AddOID((CtlID,0,1,0),return_type = str, description = "ActiveAlarms", default = " ", keywords = ["Status/Alarms","Number of Active Alarms"])
                self.AddOID((CtlID,0,1,1),return_type = str, description = "AckAlarms", default = " ", keywords = ["Status/Alarms","Number of Acknowledged Alarms"])
                self.AddOID((CtlID,0,1,2),return_type = str, description = "AlarmList", default = " ", keywords = ["Status/Alarms","Alarm List"])

                # Battery
                self.AddOID((CtlID,0,2,0),return_type = str, description = "BatteryVoltage", default = " ", keywords = ["Status/Battery","Battery Voltage"])
                self.AddOID((CtlID,0,2,1),return_type = str, description = "BatteryCurrent", default = " ", keywords = ["Status/Battery","Battery Charger Current"])
                # Line State
                self.AddOID((CtlID,0,4,0),return_type = str, description = "TransferSwitchState", default = " ", keywords = ["Status/Line State","Transfer Switch State"])
                # TODO add HTS switch info
                # Status Time
                self.AddOID((CtlID,0,3,0),return_type = str, description = "MonitorTime", default = " ", keywords = ["Status/Time","Monitor Time"])
                self.AddOID((CtlID,0,3,1),return_type = str, description = "GeneratorTime", default = " ", keywords = ["Status/Time","Generator Time"])
                # TODO selected H-100 Maint items?

            # Monitor->Generator Monitor Stats
            self.AddOID((CtlID,4,0,0),return_type = str, description = "MonitorHealth", default = "Unknown", keywords = ["Monitor","Monitor Health"])
            self.AddOID((CtlID,4,0,1),return_type = str, description = "RunTime", default = "Unknown", keywords = ["Monitor","Run time"])
            self.AddOID((CtlID,4,0,2),return_type = str, description = "PowerLogSize", default = "", keywords = ["Monitor","Power log file size"])
            self.AddOID((CtlID,4,0,3),return_type = str, description = "Version", default = "", keywords = ["Monitor","Generator Monitor Version"])
            # Communication Stats
            self.AddOID((CtlID,4,1,0),return_type = str, description = "PacketCount", default = "Unknown", keywords = ["Monitor/Communication Stats","Packet Count"])
            self.AddOID((CtlID,4,1,1),return_type = str, description = "CRCErrors", default = "Unknown", keywords = ["Monitor/Communication Stats","CRC Errors"])
            self.AddOID((CtlID,4,1,2),return_type = str, description = "CRCPercent", default = "Unknown", keywords = ["Monitor/Communication Stats","CRC Percent Errors"])
            self.AddOID((CtlID,4,1,3),return_type = str, description = "PacketTimeouts", default = "Unknown", keywords = ["Monitor/Communication Stats","Timeout Errors"])
            self.AddOID((CtlID,4,1,4),return_type = str, description = "TimeoutPercent", default = "Unknown", keywords = ["Monitor/Communication Stats","Timeout Percent Errors"])
            self.AddOID((CtlID,4,1,5),return_type = str, description = "ModbusErrors", default = "Unknown", keywords = ["Monitor/Communication Stats","Modbus Exceptions"])
            self.AddOID((CtlID,4,1,6),return_type = str, description = "ValidationErrors", default = "Unknown", keywords = ["Monitor/Communication Stats","Validation Errors"])
            self.AddOID((CtlID,4,1,7),return_type = str, description = "InvalidData", default = "Unknown", keywords = ["Monitor/Communication Stats","Invalid Data"])
            self.AddOID((CtlID,4,1,8),return_type = str, description = "DiscardedBytes", default = "Unknown", keywords = ["Monitor/Communication Stats","Discarded Bytes"])
            self.AddOID((CtlID,4,1,9),return_type = str, description = "CommRestarts", default = "Unknown", keywords = ["Monitor/Communication Stats","Comm Restarts"])
            self.AddOID((CtlID,4,1,10),return_type = str, description = "PPS", default = "Unknown", keywords = ["Monitor/Communication Stats","Packets Per Second"])
            self.AddOID((CtlID,4,1,11),return_type = str, description = "AvgTransTime", default = "Unknown", keywords = ["Monitor/Communication Stats","Average Transaction Time"])

            # Monitor -> Platform Stats
            self.AddOID((CtlID,4,2,0),return_type = str, description = "CPUTemp", default = "Unknown", keywords = ["Monitor","CPU Temperature"])
            self.AddOID((CtlID,4,2,1),return_type = str, description = "PiModel", default = "Unknown", keywords = ["Monitor","Pi Model"])
            self.AddOID((CtlID,4,2,2),return_type = str, description = "CPUFreqThrottling", default = "Unknown", keywords = ["Monitor","Pi CPU Frequency Throttling"])
            self.AddOID((CtlID,4,2,3),return_type = str, description = "ARMFreqCap", default = "Unknown", keywords = ["Monitor","Pi ARM Frequency Cap"])
            self.AddOID((CtlID,4,2,4),return_type = str, description = "ARMUnderVoltage", default = "Unknown", keywords = ["Monitor","Pi Undervoltage"])
            self.AddOID((CtlID,4,2,5),return_type = str, description = "CPUUtil", default = "Unknown", keywords = ["Monitor","CPU Utilization"])
            self.AddOID((CtlID,4,2,6),return_type = str, description = "OSName", default = "Unknown", keywords = ["Monitor","OS Name"])
            self.AddOID((CtlID,4,2,7),return_type = str, description = "OSVersion", default = "Unknown", keywords = ["Monitor","OS Version"])
            self.AddOID((CtlID,4,2,8),return_type = str, description = "SysUptime", default = "Unknown", keywords = ["Monitor","System Uptime"])
            self.AddOID((CtlID,4,2,9),return_type = str, description = "NetInferface", default = "Unknown", keywords = ["Monitor","Network Interface Used"])

            self.mibDataIdx = {}
            for mibVar in self.mibData:
                self.mibDataIdx[mibVar.name] = mibVar

            self.transportDispatcher = AsyncoreDispatcher()
            self.transportDispatcher.registerRecvCbFun(self.SnmpCallbackFunction)

            # UDP/IPv4
            self.transportDispatcher.registerTransport(
                udp.domainName, udp.UdpSocketTransport().openServerMode(('0.0.0.0', 161))
            )

            # UDP/IPv6
            self.transportDispatcher.registerTransport(
                udp6.domainName, udp6.Udp6SocketTransport().openServerMode(('::', 161))
            )

            ## Local domain socket
            # self.transportDispatcher.registerTransport(
            #    unix.domainName, unix.UnixSocketTransport().openServerMode('/tmp/snmp-agent')
            # )

            self.transportDispatcher.jobStarted(1)

            try:
                # Dispatcher will never finish as job#1 never reaches zero
                if self.transportDispatcher != None:
                    self.transportDispatcher.runDispatcher()
            except Exception as e1:
                self.SnmpClose()
                if self.transportDispatcher != None:
                    self.LogErrorLine("Fatal Error in SetupSNMP: " + str(e1))
                else:
                    # we are exiting
                    self.LogDebug("Exit Snmp Engine")

        except Exception as e1:
            self.LogErrorLine("Error in SetupSNMP: " + str(e1))
            self.SnmpClose()

    #----------  GenSNMP::SnmpClose --------------------------------------------
    def SnmpClose(self):

        try:
            if self.transportDispatcher != None:
                self.transportDispatcher.jobFinished(1)
                self.transportDispatcher.unregisterRecvCbFun(recvId=None)
                self.transportDispatcher.unregisterTransport(udp.domainName)
                self.transportDispatcher.unregisterTransport(udp6.domainName)
                self.transportDispatcher.closeDispatcher()
                self.LogDebug("Dispatcher Closed")
                self.transportDispatcher = None
        except Exception as e1:
            self.LogErrorLine("Error in SnmpClose: " + str(e1))

    #----------  GenSNMP::SnmpCallbackFunction ---------------------------------
    def SnmpCallbackFunction(self, transportDispatcher, transportDomain, transportAddress, wholeMsg):
        while wholeMsg:
            try:
                msgVer = api.decodeMessageVersion(wholeMsg)
                if msgVer in api.protoModules:
                    pMod = api.protoModules[msgVer]
                else:
                    self.LogError('Unsupported SNMP version %s' % msgVer)
                    return
                reqMsg, wholeMsg = decoder.decode(
                    wholeMsg, asn1Spec=pMod.Message(),
                )
                rspMsg = pMod.apiMessage.getResponse(reqMsg)
                rspPDU = pMod.apiMessage.getPDU(rspMsg)
                reqPDU = pMod.apiMessage.getPDU(reqMsg)
                Community = pMod.apiMessage.getCommunity(reqMsg)
                if Community != OctetString(self.community.strip()):
                    self.LogError("Invalid community string: <" + Community + ">, expected: <" + self.community+">")
                    return wholeMsg
                self.LogDebug("Community: " +  Community)
                varBinds = []
                pendingErrors = []
                errorIndex = 0
                # GETNEXT PDU
                if reqPDU.isSameTypeWith(pMod.GetNextRequestPDU()):
                    # Produce response var-binds
                    for oid, val in pMod.apiPDU.getVarBinds(reqPDU):
                        errorIndex = errorIndex + 1
                        # Search next OID to report
                        nextIdx = bisect.bisect(self.mibData, oid)
                        if nextIdx == len(self.mibData):
                            # Out of MIB
                            varBinds.append((oid, val))
                            pendingErrors.append(
                                (pMod.apiPDU.setEndOfMibError, errorIndex)
                            )
                        else:
                            # Report value if OID is found
                            varBinds.append(
                                (self.mibData[nextIdx].name, self.mibData[nextIdx](msgVer))
                            )
                elif reqPDU.isSameTypeWith(pMod.GetRequestPDU()):
                    for oid, val in pMod.apiPDU.getVarBinds(reqPDU):
                        #print("Oid: " + str(oid))
                        if oid in self.mibDataIdx:
                            varBinds.append((oid, self.mibDataIdx[oid](msgVer)))    # call the __call__  function
                        else:
                            # No such instance
                            varBinds.append((oid, val))
                            pendingErrors.append(
                                (pMod.apiPDU.setNoSuchInstanceError, errorIndex)
                            )
                            break
                else:
                    # Report unsupported request type
                    pMod.apiPDU.setErrorStatus(rspPDU, 'genErr')
                pMod.apiPDU.setVarBinds(rspPDU, varBinds)
                # Commit possible error indices to response PDU
                for f, i in pendingErrors:
                    f(rspPDU, i)
                transportDispatcher.sendMessage(
                    encoder.encode(rspMsg), transportDomain, transportAddress
                )
            except Exception as e1:
                self.LogErrorLine("Error in SnmpCallbackFunction: " + str(e1))
        return wholeMsg
    #----------  GenSNMP::SendCommand ------------------------------------------
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


    # ---------- GenSNMP::SNMPThread--------------------------------------------
    def SNMPThread(self):

        time.sleep(1)

        while True:
            try:
                if not self.UseNumeric:
                    statusdata = self.SendCommand("generator: status_json")
                    maintdata = self.SendCommand("generator: maint_json")
                    outagedata = self.SendCommand("generator: outage_json")
                    monitordata = self.SendCommand("generator: monitor_json")
                else:
                    statusdata = self.SendCommand("generator: status_num_json")
                    outagedata = self.SendCommand("generator: outage_num_json")
                    monitordata = self.SendCommand("generator: monitor_num_json")
                    maintdata = self.SendCommand("generator: maint_num_json")
                try:
                    GenmonDict = {}
                    TempDict = {}
                    TempDict = json.loads(statusdata)
                    GenmonDict["Status"] = TempDict["Status"]
                    TempDict = json.loads(maintdata)
                    GenmonDict["Maintenance"] = TempDict["Maintenance"]
                    TempDict = json.loads(outagedata)
                    GenmonDict["Outage"] = TempDict["Outage"]
                    TempDict = json.loads(monitordata)
                    GenmonDict["Monitor"] = TempDict["Monitor"]
                    self.CheckDictForChanges(GenmonDict, "home")

                    if self.WaitForExit("SNMPThread", float(self.PollTime)):
                        self.SnmpClose()
                        return
                except Exception as e1:
                    self.LogErrorLine("Error in SNMPThread: (parse) : " + str(e1))
            except Exception as e1:
                self.LogErrorLine("Error in SNMPThread: " + str(e1))
                if self.WaitForExit("SNMPThread", float(self.PollTime * 60)):
                    self.SnmpClose()
                    return

    #------------ GenSNMP::DictIsNumeric ---------------------------------------
    def DictIsNumeric(self, node):

        try:
            if not self.UseNumeric:
                return False
            if isinstance(node, dict) and "type" in node and "value" in node and "unit" in node:
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in DictIsNumeric: " + str(e1))
            return False
    #------------ GenSNMP::CheckDictForChanges ---------------------------------
    # This function is recursive, it will turn a nested dict into a flat dict keys
    # that have a directory structure with corrposonding values and determine if
    # anyting changed. If it has then call our callback function
    def CheckDictForChanges(self, node, PathPrefix):

        CurrentPath = PathPrefix
        if not isinstance(PathPrefix, str):
           return ""

        if isinstance(node, dict):
           for key, item in node.items():
               if isinstance(item, dict):
                   if not self.DictIsNumeric(item):
                       CurrentPath = PathPrefix + "/" + str(key)
                       self.CheckDictForChanges(item, CurrentPath)
                   else:
                       CurrentPath = PathPrefix + "/" + str(key)
                       self.CheckForChanges(CurrentPath, str(item["value"]))
               elif isinstance(item, list):
                   CurrentPath = PathPrefix + "/" + str(key)
                   if self.ListIsStrings(item):
                       # if this is a list of strings, the join the list to one comma separated string
                       self.CheckForChanges(CurrentPath, ', '.join(item))
                   else:
                       for listitem in item:
                           if isinstance(listitem, dict):
                               if not self.DictIsNumeric(item):
                                   self.CheckDictForChanges(listitem, CurrentPath)
                               else:
                                   CurrentPath = PathPrefix + "/" + str(key)
                                   self.CheckForChanges(CurrentPath, str(item["value"]))
                           else:
                               self.LogError("Invalid type in CheckDictForChanges: %s %s (2)" % (key, str(type(listitem))))
               else:
                   CurrentPath = PathPrefix + "/" + str(key)
                   self.CheckForChanges(CurrentPath, item)
        else:
           self.LogError("Invalid type in CheckDictForChanges %s " % str(type(node)))

    # ---------- GenSNMP::ListIsStrings-----------------------------------------
    # return true if every element of list is a string
    def ListIsStrings(self, listinput):

        try:
            if not isinstance(listinput, list):
                return False
            for item in listinput:
                if sys.version_info[0] < 3:
                    if not (isinstance(item, str) or isinstance(item, unicode)):
                        return False
                else:
                    if not (isinstance(item, str) or isinstance(item, bytes)):
                        return False
            return True
        except Exception as e1:
            self.LogErrorLine("Error in ListIsStrings: " + str(e1))
            return False

    # ---------- GenSNMP::CheckForChanges-------------------------------------
    def CheckForChanges(self, Path, Value):

        try:

            if self.BlackList != None:
                for BlackItem in self.BlackList:
                    if BlackItem.lower() in Path.lower():
                        return
            LastValue = self.LastValues.get(str(Path), None)

            if LastValue == None or LastValue != Value:
                self.LastValues[str(Path)] = Value
                self.UpdateSNMPData(Path, Value)

        except Exception as e1:
             self.LogErrorLine("Error in mygenpush:CheckForChanges: " + str(e1))

    # ----------GenSNMP::SignalClose--------------------------------------------
    def SignalClose(self, signum, frame):

        try:
            self.Close()
        except Exception as e1:
            self.LogErrorLine("Error in SignalClose: " + str(e1))
        sys.exit(1)

    # ----------GenSNMP::Close----------------------------------------------
    def Close(self):

        try:
            self.LogDebug("GenSNMP Exit")
            self.KillThread("SNMPThread")
            self.SnmpClose()
            self.Generator.Close()
        except Exception as e1:
            self.LogErrorLine("Error in Close: " + str(e1))
#-------------------------------------------------------------------------------
if __name__ == "__main__":

    console, ConfigFilePath, address, port, loglocation, log = MySupport.SetupAddOnProgram("gensnmp")

    GenSNMPInstance = GenSNMP(log = log, loglocation = loglocation, ConfigFilePath = ConfigFilePath, host = address, port = port, console = console)

    sys.exit(1)
