#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: generac_H-100.py
# PURPOSE: Controller Specific Detils for Generac H-100
#
#  AUTHOR: Jason G Yates
#    DATE: 30-Apr-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import datetime, time, sys, os, threading, socket, re
import atexit, json, collections, random

import controller, mymodbus, mythread, modbus_file, mytile

# Module defines ---------------------------------------------------------------
REGISTER = 0
LENGTH = 1
RET_STRING = 2

ALARM_LOG_START = 0x0c01
ALARM_LOG_ENTRIES = 20
ALARM_LOG_LENGTH = 64
EVENT_LOG_START = 0x0c15
EVENT_LOG_ENTRIES = 20
EVENT_LOG_LENGTH = 64
SERIAL_NUMBER_FILE_RECORD = "0040"      # 0x40
SERIAL_NUM_LENGTH   = 64
#---------------------RegisterEnum::RegisterEnum--------------------------------
class RegisterEnum(object):
    INPUT_1                 = ["0080", 2]            # Input 1
    INPUT_2                 = ["0081", 2]            # Input 2
    OUTPUT_1                = ["0082", 2]            # Output 1
    OUTPUT_2                = ["0083", 2]            # Output 2
    OUTPUT_3                = ["0084", 2]            # Output 3
    OUTPUT_4                = ["0085", 2]            # Output 4
    OUTPUT_5                = ["0086", 2]            # Output 5
    OUTPUT_6                = ["0087", 2]            # Output 6
    OUTPUT_7                = ["0088", 2]            # Output 7
    OUTPUT_8                = ["0089", 2]            # Output 8

    OIL_TEMP                = ["008b", 2]            # Oil Temp
    COOLANT_TEMP            = ["008d", 2]            # Coolant Temp
    OIL_PRESSURE            = ["008f", 2]            # Oil Pressure
    COOLANT_LEVEL           = ["0091", 2]            # Coolant Level
    FUEL_LEVEL              = ["0093", 2]            # USER CFG 05/Fuel Level =147
    USER_CFG_06             = ["0095", 2]            # USER CFG 06 = 149
    THROTTLE_POSITION       = ["0097", 2]            # Throttle Position
    O2_SENSOR               = ["0099", 2]            # O2 Sensor
    BATTERY_CHARGE_CURRNT   = ["009b", 2]            # Battery Charge Current NOTE: When the generator is running the battery charger current value may be wrong.
    BATTERY_VOLTS           = ["009d", 2]            # Battery Charge Volts
    CURRENT_PHASE_A         = ["009f", 2]            # Current Phase A
    CURRENT_PHASE_B         = ["00a1", 2]            # Current Phase B
    CURRENT_PHASE_C         = ["00a3", 2]            # Current Phase C
    AVG_CURRENT             = ["00a5", 2]            # Avg Current
    VOLTS_PHASE_A_B         = ["00a7", 2]            # Voltage Phase AB
    VOLTS_PHASE_B_C         = ["00a9", 2]            # Voltage Phase BC
    VOLTS_PHASE_C_A         = ["00ab", 2]            # Voltage Phase CA
    AVG_VOLTAGE             = ["00ad", 2]            # Average Voltage
    TOTAL_POWER_KW          = ["00af", 2]            # Total Power (kW)
    TOTAL_PF                = ["00b1", 2]            # Power Factor
    OUTPUT_FREQUENCY        = ["00b3", 2]            # Output Frequency
    OUTPUT_RPM              = ["00b5", 2]            # Output RPM
    A_F_DUTY_CYCLE          = ["00b7", 2]            # Air Fuel Duty Cycle

    GEN_TIME_HR_MIN         = ["00e0", 2]            # Time HR:MIN
    GEN_TIME_SEC_DYWK       = ["00e1", 2]            # Time SEC:DayOfWeek
    GEN_TIME_MONTH_DAY      = ["00e2", 2]            # Time Month:DayofMonth
    GEN_TIME_YR             = ["00e3", 2]            # Time YR:UNK

    ALARM_ACK               = ["012e", 2]            # Number of alarm acks
    ACTIVE_ALARM_COUNT      = ["012f", 2]            # Number of active alarms
    ENGINE_HOURS_HI         = ["0130", 2]            # Engine Hours High
    ENGINE_HOURS_LO         = ["0131", 2]            # Engine Hours Low
    ENGINE_STATUS_CODE      = ["0132", 2]            # Engine Status Code

    START_BITS              = ["019c", 2]            # Start Bits
    START_BITS_2            = ["019d", 2]            # Start Bits 2
    START_BITS_3            = ["019e", 2]            # Start Bits 2
    QUIETTEST_STATUS        = ["022b", 2]            # Quiet Test Status and reqest

    EXT_SW_TARGET_VOLTAGE   = ["0ea7", 2]            # External Switch Target Voltage
    EXT_SW_AVG_UTIL_VOLTS   = ["0eb5", 2]            # External Switch Avg Utility Volts

    #---------------------RegisterEnum::hexsort---------------------------------
    @staticmethod
    def hexsort(e):
        try:
            return int(e[REGISTER],16)
        except:
            return 0
    @staticmethod
    def GetRegList():
        RetList = []
        for attr, value in RegisterEnum.__dict__.iteritems():
            if not callable(getattr(RegisterEnum(),attr)) and not attr.startswith("__"):
                RetList.append(value)

        RetList.sort(key=RegisterEnum.hexsort)
        return RetList
#---------------------------RegisterStringEnum:RegisterStringEnum---------------
class RegisterStringEnum(object):

    # Note, the first value is the register (in hex string), the second is the numbert of bytes
    # third is if the result is stored as a string
    CONTROLLER_NAME             =   ["0020", 0x40, True]            #
    PMDCP_INFO                  =   ["0040", 0x40, True]
    LAST_POWER_FAIL             =   ["0104", 0x08, False]
    POWER_UP_TIME               =   ["0108", 0x08, False]
    ENGINE_STATUS               =   ["0133", 0x40, True]
    GENERATOR_STATUS            =   ["0153", 0x40, True]
    GENERATOR_DATA_TIME         =   ["0173", 0x40, True]
    MIN_GENLINK_VERSION         =   ["0060", 0x40, True]
    MAINT_LIFE                  =   ["0193", 0x12, False]

    #---------------------RegisterStringEnum::hexsort---------------------------
    @staticmethod
    def hexsort( e):
        try:
            return int(e[REGISTER],16)
        except:
            return 0
    #---------------------RegisterStringEnum::GetRegList------------------------
    @staticmethod
    def GetRegList():
        RetList = []
        for attr, value in RegisterStringEnum.__dict__.iteritems():
            if not callable(getattr(RegisterStringEnum(),attr)) and not attr.startswith("__"):
                RetList.append(value)
        RetList.sort(key=RegisterStringEnum.hexsort)
        return RetList


#---------------------Input1::Input1--------------------------------------------
# Enum for register Input1
class Input1(object):
    AUTO_SWITCH         = 0x8000
    MANUAL_SWITCH       = 0x4000
    EMERGENCY_STOP      = 0x2000
    REMOTE_START        = 0x1000
    DI1_BAT_CHRGR_FAIL  = 0x0800
    DI2_FUEL_PRESSURE   = 0x0400
    DI3_LINE_POWER      = 0x0200
    DI4_GEN_POWER       = 0x0100
    MODEM_DCD           = 0x0080
    MODEM_ENABLED       = 0x0040
    GEN_OVERSPEED       = 0x0020
    HUIO_1_CFG_12       = 0x0010
    HUIO_1_CFG_13       = 0x0008
    HUIO_1_CFG_14       = 0x0004
    HUIO_1_CFG_15       = 0x0002
    HUIO_2_CFG_16       = 0x0001

#---------------------Input2::Input2--------------------------------------------
# Enum for register Input2
class Input2(object):
    HUIO_2_CFG_17       = 0x8000
    HUIO_2_CFG_18       = 0x4000
    HUIO_2_CFG_19       = 0x2000
    HUIO_3_CFG_20       = 0x1000
    HUIO_3_CFG_21       = 0x0800
    HUIO_3_CFG_22       = 0x0400
    HUIO_3_CFG_23       = 0x0200
    HUIO_4_CFG_24       = 0x0100
    HUIO_4_CFG_25       = 0x0080
    HUIO_4_CFG_26       = 0x0040
    HUIO_4_CFG_27       = 0x0020

#---------------------Output1::Output1------------------------------------------
# Enum for register Output1
class Output1(object):
    COMMON_ALARM        = 0x8000
    COMMON_WARNING      = 0x4000
    GEN_RUNNING         = 0x2000
    ALARMS_ENABLED      = 0x1000
    READY_FOR_LOAD      = 0x0800
    GEN_READY_TO_RUN    = 0x0400
    GEN_STOPPED_ALARM   = 0x0200
    GEN_STOPPED         = 0x0100
    GEN_IN_MANUAL       = 0x0080
    GEN_IN_AUTO         = 0x0040
    GEN_IN_OFF          = 0x0020
    OVERCRANK_ALARM     = 0x0010
    OIL_INHIBIT_ALRM    = 0x0008
    ANNUNC_SPR_LIGHT    = 0x0004
    OIL_TEMP_HI_ALRM    = 0x0002
    OIL_TEMP_LO_ALRM    = 0x0001

#---------------------Output2::Output2------------------------------------------
# Enum for register Output2
class Output2(object):
    OIL_TEMP_HI_WARN    = 0x8000
    OIL_TEMP_LO_WARN    = 0x4000
    OIL_TEMP_FAULT      = 0x2000
    COOL_TMP_HI_ALRM    = 0x1000
    COOL_TMP_LO_ALRM    = 0x0800
    COOL_TMP_HI_WARN    = 0x0400
    COOL_TMP_LO_WARN    = 0x0200
    COOL_TMP_FAULT      = 0x0100
    OIL_PRES_HI_ALRM    = 0x0080
    OIL_PRES_LO_ALRM    = 0x0040
    OIL_PRES_HI_WARN    = 0x0020
    OIL_PRES_LO_WARN    = 0x0010
    OIL_PRES_FAULT      = 0x0008
    COOL_LVL_HI_ALRM    = 0x0004
    COOL_LVL_LO_ALRM    = 0x0002
    COOL_LVL_HI_WARN    = 0x0001

#---------------------Output3::Output3------------------------------------------
# Enum for register Output3
class Output3(object):
    COOL_LVL_LO_WARN    = 0x8000
    COOL_LVL_FAULT      = 0x4000
    FUEL_LVL_HI_ALRM    = 0x2000        # Analog Input 5
    FUEL_LVL_LO_ALRM    = 0x1000        # Analog Input 5
    FUEL_LVL_HI_WARN    = 0x0800        # Analog Input 5
    FUEL_LVL_LO_WARN    = 0x0400        # Analog Input 5
    FUEL_LVL_FAULT      = 0x0200        # Analog Input 5
    ANALOG_6_HI_ALRM    = 0x0100        # Fuel Pressure / Inlet Air Temperature
    ANALOG_6_LO_ALRM    = 0x0080        # Fuel Pressure / Inlet Air Temperature
    ANALOG_6_HI_WARN    = 0x0040        # Fuel Pressure / Inlet Air Temperature
    ANALOG_6_LO_WARN    = 0x0020        # Fuel Pressure / Inlet Air Temperature
    ANALOG_6_FAULT      = 0x0010        # Fuel Pressure / Inlet Air Temperature
    GOV_POS_HI_ALARM    = 0x0008
    GOV_POS_LO_ALARM    = 0x0004
    GOV_POS_HI_WARN     = 0x0002
    GOV_POS_LO_WARN     = 0x0001

#---------------------Output4::Output4------------------------------------------
# Enum for register Output4
class Output4(object):
    GOV_POS_FAULT       = 0x8000
    OXYGEN_HI_ALARM     = 0x4000        # Analog Input #8 (Emissions Sensor or Fluid Basin).
    OXYGEN_LO_ALARM     = 0x2000        # Analog Input #8 (Emissions Sensor or Fluid Basin).
    OXYGEN_HI_WARN      = 0x1000        # Analog Input #8 (Emissions Sensor or Fluid Basin).
    OXYGEN_LO_WARN      = 0x0800        # Analog Input #8 (Emissions Sensor or Fluid Basin).
    OXYGEN_SENSOR_FAULT = 0x0400        # Analog Input #8 (Emissions Sensor or Fluid Basin).
    CHG_CURR_HI_ALRM    = 0x0200
    CHG_CURR_LO_ALRM    = 0x0100
    CHG_CURR_HI_WARN    = 0x0080
    CHG_CURR_LO_WARN    = 0x0040
    CHG_CURR_FAULT      = 0x0020
    BAT_VOLT_HI_ALRM    = 0x0010
    BAT_VOLT_LO_ALRM    = 0x0008
    BAT_VOLT_HI_WARN    = 0x0004
    BAT_VOLT_LO_WARN    = 0x0002
    AVG_CURR_HI_ALRM    = 0x0001

#---------------------Output5::Output5------------------------------------------
# Enum for register Output5
class Output5(object):
    AVG_CURR_LO_ALRM    = 0x8000
    AVG_CURR_HI_WARN    = 0x4000
    AVG_CURR_LO_WARN    = 0x2000
    AVG_VOLT_HI_ALRM    = 0x1000
    AVG_VOLT_LO_ALRM    = 0x0800
    AVG_VOLT_HI_WARN    = 0x0400
    AVG_VOLT_LO_WARN    = 0x0200
    TOT_PWR_HI_ALARM    = 0x0100
    TOT_PWR_LO_ALARM    = 0x0080
    TOT_PWR_HI_WARN     = 0x0040
    TOT_PWR_LO_WARN     = 0x0020
    GEN_FREQ_HI_ALRM    = 0x0010
    GEN_FREQ_LO_ALRM    = 0x0008
    GEN_FREQ_HI_WARN    = 0x0004
    GEN_FREQ_LO_WARN    = 0x0002
    GEN_FREQ_FAULT      = 0x0001

#---------------------Output6::Output6------------------------------------------
# Enum for register Output6
class Output6(object):
    ENG_RPM_HI_ALARM    = 0x8000
    ENG_RPM_LO_ALARM    = 0x4000
    ENG_RPM_HI_WARN     = 0x2000
    ENG_RPM_LO_WARN     = 0x1000
    ENG_RPM_FAULT       = 0x0800
    SWITCH_IN_AUTO      = 0x0400        # Key Switch in AUTO digital input active
    SWITCH_IN_MANUAL    = 0x0200        # Key Switch in MANUAL digital input active
    E_STOP_ACTIVE       = 0x0100        # Emergency Stop Status digital input active
    REMOTE_START_ACT    = 0x0080        # Remote Start digital input active
    BATTERY_CHARGE_FAIL = 0x0040        # DI-1, Digital Input #5 active / Battery Charger Fail digital input active
    LOW_FUEL_PRS_ACT    = 0x0020        # DI-2, Digital Input #6 active Ruptured Basin digital input active, Propane Gas Leak digital input active, Low Fuel Pressure digital input active
    DI3_LINE_PWR_ACT    = 0x0010        # DI-3, Digital Input #7 active Line Power digital input active
    DI4_GEN_PWR_ACT     = 0x0008        # DI-4, Digital Input #8 active Generator Power digital input active
    LINE_POWER          = 0x0004        #
    GEN_POWER           = 0x0002        #
    ILC_ALR_WRN_1       = 0x0001        # Integrated Logic Controller Warning 1

#---------------------Output7::Output7------------------------------------------
# Enum for register Output7
class Output7(object):
    ILC_ALR_WRN_2       = 0x8000       # Integrated Logic Controller Warning 2
    IN_WARM_UP          = 0x4000
    IN_COOL_DOWN        = 0x2000
    CRANKING            = 0x1000
    NEED_SERVICE        = 0x0800
    SHUTDOWN_GENSET     = 0x0400
    CHCK_V_PHS_ROT      = 0x0200
    CHCK_C_PHS_ROT      = 0x0100
    FAULT_RLY_ACTIVE    = 0x0080
    USR_CONFIG_106      = 0x0040
    INT_EXERCISE_ACT    = 0x0020
    CHECK_FOR_ILC       = 0x0010
    USR_CONFIG_109      = 0x0008
    USR_CONFIG_110      = 0x0004
    USR_CONFIG_111      = 0x0002
    USR_CONFIG_112      = 0x0001

#---------------------Output8::Output8------------------------------------------
# Enum for register Output8
class Output8(object):
    USR_CONFIG_113      = 0x8000
    USR_CONFIG_114      = 0x4000
    USR_CONFIG_115      = 0x2000
    USR_CONFIG_116      = 0x1000
    USR_CONFIG_117      = 0x0800
    USR_CONFIG_118      = 0x0400
    RPM_MISSING         = 0x0200
    RESET_ALARMS        = 0x0100


class HPanel(controller.GeneratorController):

    #---------------------HPanel::__init__--------------------------------------
    def __init__(self,
        log,
        newinstall = False,
        simulation = False,
        simulationfile = None,
        message = None,
        feedback = None,
        config = None):

        # call parent constructor
        super(HPanel, self).__init__(log, newinstall = newinstall, simulation = simulation, simulationfile = simulationfile, message = message, feedback = feedback, config = config)

        self.LastEngineState = ""
        self.CurrentAlarmState = False
        self.VoltageConfig = None
        self.SerialNumber = "Unknown"
        self.AlarmAccessLock = threading.RLock()     # lock to synchronize access to the logs
        self.EventAccessLock = threading.RLock()     # lock to synchronize access to the logs
        self.AlarmLog = []
        self.EventLog = []

        self.DaysOfWeek = { 1: "Sunday",    # decode for register values with day of week
                            2: "Monday",
                            3: "Tuesday",
                            4: "Wednesday",
                            5: "Thursday",
                            6: "Friday",
                            7: "Saturday"}
        self.MonthsOfYear = { 1: "January",     # decode for register values with month
                              2: "February",
                              3: "March",
                              4: "April",
                              5: "May",
                              6: "June",
                              7: "July",
                              8: "August",
                              9: "September",
                              10: "October",
                              11: "November",
                              12: "December"}

        self.SetupClass()


    #-------------HPanel:SetupClass---------------------------------------------
    def SetupClass(self):

        # read config file
        if not self.GetConfig():
            self.FatalError("Failure in Controller GetConfig: " + str(e1))
            return None
        try:
            #Starting device connection
            if self.Simulation:
                self.ModBus = modbus_file.ModbusFile(self.UpdateRegisterList,
                    inputfile = self.SimulationFile,
                    config = self.config)
            else:
                self.ModBus = mymodbus.ModbusProtocol(self.UpdateRegisterList,
                    config = self.config)

            self.Threads = self.MergeDicts(self.Threads, self.ModBus.Threads)
            self.LastRxPacketCount = self.ModBus.RxPacketCount

            self.StartCommonThreads()

        except Exception as e1:
            self.FatalError("Error opening modbus device: " + str(e1))
            return None

    #---------------------HPanel::GetConfig-------------------------------------
    # read conf file, used internally, not called by genmon
    # return True on success, else False
    def GetConfig(self):

        try:
            self.VoltageConfig = self.config.ReadValue('voltageconfiguration', default = "277/480")
            self.NominalBatteryVolts = int(self.config.ReadValue('nominalbattery', return_type = int, default = 24))

        except Exception as e1:
            self.FatalError("Missing config file or config file entries (HPanel): " + str(e1))
            return False

        return True

    #-------------HPanel:InitDevice---------------------------------------------
    # One time reads, and read all registers once
    def InitDevice(self):

        try:
            self.MasterEmulation()
            self.CheckModelSpecificInfo()
            self.SetupTiles()
            self.InitComplete = True
            self.InitCompleteEvent.set()
        except Exception as e1:
            self.LogErrorLine("Error in InitDevice: " + str(e1))

    #-------------HPanel:SetupTiles---------------------------------------------
    def SetupTiles(self):
        try:
            Tile = mytile.MyTile(self.log, title = "Battery Voltage", units = "V", type = "batteryvolts", nominal = self.NominalBatteryVolts,
                callback = self.GetParameter,
                callbackparameters = (RegisterEnum.BATTERY_VOLTS[REGISTER],  None, 100.0, False, False, True))
            self.TileList.append(Tile)

            # Nominal Voltage for gauge
            if self.VoltageConfig != None:
                #Valid settings are: 120/208, 120/240, 230/400, 240/415, 277/480, 347/600
                VoltageConfigList = self.VoltageConfig.split("/")
                NominalVoltage = int(VoltageConfigList[1])
            else:
                NominalVoltage = 600

            if self.NominalKW == None or self.NominalKW == "" or self.NominalKW == "Unknown":
                self.NominalKW = "550"

            Tile = mytile.MyTile(self.log, title = "Average Voltage", units = "V", type = "linevolts", nominal = NominalVoltage,
            callback = self.GetParameter,
            callbackparameters = (RegisterEnum.AVG_VOLTAGE[REGISTER], None, None, False, True, False))
            self.TileList.append(Tile)

            NominalCurrent = int(self.NominalKW) * 1000 / NominalVoltage
            Tile = mytile.MyTile(self.log, title = "Average Current", units = "A", type = "current", nominal = NominalCurrent,
            callback = self.GetParameter,
            callbackparameters = (RegisterEnum.AVG_CURRENT[REGISTER], None, None, False, True, False))
            self.TileList.append(Tile)

            if self.NominalFreq == None or self.NominalFreq == "" or self.NominalFreq == "Unknown":
                self.NominalFreq = "60"
            Tile = mytile.MyTile(self.log, title = "Frequency", units = "Hz", type = "frequency", nominal = int(self.NominalFreq),
            callback = self.GetParameter,
            callbackparameters = (RegisterEnum.OUTPUT_FREQUENCY[REGISTER], None, 10.0, False, False, True))
            self.TileList.append(Tile)

            if self.NominalRPM == None or self.NominalRPM == "" or self.NominalRPM == "Unknown":
                self.NominalRPM = "3600"
            Tile = mytile.MyTile(self.log, title = "RPM", type = "rpm", nominal = int(self.NominalRPM),
            callback = self.GetParameter,
            callbackparameters = (RegisterEnum.OUTPUT_RPM[REGISTER], None, None, False, True, False))
            self.TileList.append(Tile)

            # water temp between 170 and 200 is a normal range for a gen. most have a 180f thermostat
            Tile = mytile.MyTile(self.log, title = "Coolant Temp", units = "F", type = "temperature", subtype = "coolant", nominal = 180, maximum = 300,
            callback = self.GetParameter,
            callbackparameters = (RegisterEnum.COOLANT_TEMP[REGISTER], None, None, False, True, False))
            self.TileList.append(Tile)

            if self.PowerMeterIsSupported():
                Tile = mytile.MyTile(self.log, title = "Power Output", units = "kW", type = "power", nominal = int(self.NominalKW),
                callback = self.GetParameter,
                callbackparameters = (RegisterEnum.TOTAL_POWER_KW[REGISTER], None, None, False, True, False))
                self.TileList.append(Tile)

                Tile = mytile.MyTile(self.log, title = "kW Output", type = "powergraph", nominal = int(self.NominalKW),
                callback = self.GetParameter,
                callbackparameters = (RegisterEnum.TOTAL_POWER_KW[REGISTER], None, None, False, True, False))
                self.TileList.append(Tile)

        except Exception as e1:
            self.LogErrorLine("Error in SetupTiles: " + str(e1))

    #-------------HPanel:CheckModelSpecificInfo---------------------------------
    # check for model specific info in read from conf file, if not there then add some defaults
    def CheckModelSpecificInfo(self):

        # Get Serial Number
        self.SerialNumber = self.ModBus.ProcessMasterSlaveFileReadTransaction(SERIAL_NUMBER_FILE_RECORD, SERIAL_NUM_LENGTH / 2 , ReturnString = True)

        # TODO this should be determined by reading the hardware if possible.
        if self.NominalFreq == "Unknown" or not len(self.NominalFreq):
            self.NominalFreq = "60"
            self.config.WriteValue("nominalfrequency", self.NominalFreq)

        # This is not correct for 50Hz models
        if self.NominalRPM == "Unknown" or not len(self.NominalRPM):
            if self.NominalFreq == "50":
                self.NominalRPM = "1500"
            else:
                self.NominalRPM = "1800"
            self.config.WriteValue("nominalrpm", self.NominalRPM)

        if self.NominalKW == "Unknown" or not len(self.NominalKW):
            self.NominalKW = "550"
            self.config.WriteValue("nominalkw", self.NominalKW)

        if self.Model == "Unknown" or not len(self.Model):
            self.Model = "Generac Generic H-100 Industrial Generator"
            self.config.WriteValue("model", self.Model)

        if self.FuelType == "Unknown" or not len(self.FuelType):
            self.FuelType = "Diesel"
            self.config.WriteValue("fueltype", self.FuelType)

        return
    #-------------HPanel:GetParameterString-------------------------------------
    def GetParameterString(self, Start, End):

        try:
            StartInt = int(Start, 16)
            EndInt = int(End, 16)

            ByteList = []
            ReturnString = ""
            for Register in range(StartInt, EndInt + 1):
                StrVal = self.GetParameter( "%04x" % Register)
                if not len(StrVal):
                    return ""
                RegValue = int(StrVal)
                if RegValue == 0:
                    break
                ByteList.append(RegValue >> 8)
                ByteList.append(RegValue & 0xFF)
            return ReturnString.join(map(chr, ByteList))
        except Exception as e1:
            self.LogErrorLine("Error in GetParameterString: " + str(e1))
            return ""

    #-------------HPanel:GetParameterStringValue------------------------------------
    def GetParameterStringValue(self, Register):

        return self.Strings.get(Register, "")

    #-------------HPanel:GetGeneratorStrings------------------------------------
    def GetGeneratorStrings(self):

        try:
            for RegisterList in RegisterStringEnum.GetRegList():
                try:
                    if self.IsStopping:
                        return
                    self.ModBus.ProcessMasterSlaveTransaction(RegisterList[REGISTER], RegisterList[LENGTH] / 2, ReturnString = RegisterList[RET_STRING])
                except Exception as e1:
                    self.LogErrorLine("Error in GetGeneratorStrings: " + str(e1))

        except Exception as e1:
            self.LogErrorLine("Error in GetGeneratorStrings: " + str(e1))

    #-------------HPanel:MasterEmulation----------------------------------------
    def MasterEmulation(self):

        try:
            for RegisterList in RegisterEnum.GetRegList():
                try:
                    if self.IsStopping:
                        return
                    self.ModBus.ProcessMasterSlaveTransaction(RegisterList[REGISTER], RegisterList[LENGTH] / 2)
                except Exception as e1:
                    self.LogErrorLine("Error in MasterEmulation: " + str(e1))

            self.GetGeneratorStrings()
            self.CheckForAlarmEvent.set()
        except Exception as e1:
            self.LogErrorLine("Error in MasterEmulation: " + str(e1))

    #------------ HPanel:GetTransferStatus -------------------------------------
    def GetTransferStatus(self):

        LineState = "Unknown"
        #if self.GetParameterBit(RegisterEnum.INPUT_1[REGISTER], Input1.DI3_LINE_POWER):
        #if self.GetParameterBit(RegisterEnum.OUTPUT_6[REGISTER], Output6.DI3_LINE_PWR_ACT):
        if self.GetParameterBit(RegisterEnum.OUTPUT_6[REGISTER], Output6.LINE_POWER):
            LineState = "Utility"
        #if self.GetParameterBit(RegisterEnum.INPUT_1[REGISTER], Input1.DI4_GEN_POWER):
        #if self.GetParameterBit(RegisterEnum.OUTPUT_6[REGISTER], Output6.DI4_GEN_PWR_ACT):
        if self.GetParameterBit(RegisterEnum.OUTPUT_6[REGISTER], Output6.GEN_POWER):
            LineState = "Generator"
        return LineState

    #------------ HPanel:GetAlarmlist ------------------------------------------
    def GetAlarmList(self):

        AlarmList = []
        # Now check specific alarm conditions
        if self.GetParameterBit(RegisterEnum.OUTPUT_1[REGISTER], Output1.OVERCRANK_ALARM):
            AlarmList.append("Overcrank Alarm - Generator has unsuccessfully tried to start the designated number of times.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_1[REGISTER], Output1.OIL_INHIBIT_ALRM):
            AlarmList.append("Oil Inhibit Alarm - Oil pressure too high for a stopped engine.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_1[REGISTER], Output1.OIL_TEMP_HI_ALRM):
            AlarmList.append("Oil Temp High Alarm - Oil Temperature has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_1[REGISTER], Output1.OIL_TEMP_LO_ALRM):
            AlarmList.append("Oil Temp Low Alarm - Oil Temperature has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2[REGISTER], Output2.OIL_TEMP_HI_WARN):
            AlarmList.append("Oil Temp High Warning - Oil Temperature has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2[REGISTER], Output2.OIL_TEMP_LO_WARN):
            AlarmList.append("Oil Temp Low Warning - Oil Temperature has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2[REGISTER], Output2.OIL_TEMP_FAULT):
            AlarmList.append("Oil Temp Fault - Oil Temperature sensor exceeds nominal limits for valid sensor reading.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2[REGISTER], Output2.COOL_TMP_HI_ALRM):
            AlarmList.append("Coolant Temp High Alarm - Coolant Temperature has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2[REGISTER], Output2.COOL_TMP_LO_ALRM):
            AlarmList.append("Coolant Temp Low Alarm - Coolant Temperature has gone below mimimuim alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2[REGISTER], Output2.COOL_TMP_HI_WARN):
            AlarmList.append("Coolant Temp High Warning - Coolant Temperature has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2[REGISTER], Output2.COOL_TMP_LO_WARN):
            AlarmList.append("Coolant Temp Low Warning - Coolant Temperature has gone below mimimuim warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2[REGISTER], Output2.COOL_TMP_FAULT):
            AlarmList.append("Coolant Temp Fault - Coolant Temperature sensor exceeds nominal limits for valid sensor reading.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2[REGISTER], Output2.OIL_PRES_HI_ALRM):
            AlarmList.append("Oil Pressure High Alarm - Oil Pressure has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2[REGISTER], Output2.OIL_PRES_LO_ALRM):
            AlarmList.append("Oil Pressure Low Alarm - Oil Pressure has gone below mimimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2[REGISTER], Output2.OIL_PRES_HI_WARN):
            AlarmList.append("Oil Pressure High Warning - Oil Pressure has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2[REGISTER], Output2.OIL_PRES_LO_WARN):
            AlarmList.append("Oil Pressure Low Warning - Oil Pressure has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2[REGISTER], Output2.OIL_PRES_FAULT):
            AlarmList.append("Oil Pressure Fault - Oil Pressure sensor exceeds nominal limits for valid sensor reading.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2[REGISTER], Output2.COOL_LVL_HI_ALRM):
            AlarmList.append("Coolant Level High Alarm - Coolant Level has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2[REGISTER], Output2.COOL_LVL_LO_ALRM):
            AlarmList.append("Coolant Level Low Alarm - Coolant Level has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2[REGISTER], Output2.COOL_LVL_HI_WARN):
            AlarmList.append("Coolant Level High Warning - Coolant Level has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3[REGISTER], Output3.COOL_LVL_LO_WARN):
            AlarmList.append("Coolant Level Low Warning - Coolant Level has gone below mimimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3[REGISTER], Output3.COOL_LVL_FAULT):
            AlarmList.append("Coolant Level Fault - Coolant Level sensor exceeds nominal limits for valid sensor reading.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3[REGISTER], Output3.FUEL_LVL_HI_ALRM):
            AlarmList.append("Fuel Level High Alarm - Fuel Level has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3[REGISTER], Output3.FUEL_LVL_LO_ALRM):
            AlarmList.append("Fuel Level Low Alarm - Fuel Level has gone below mimimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3[REGISTER], Output3.FUEL_LVL_HI_WARN):
            AlarmList.append("Fuel Level High Warning - Fuel Level has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3[REGISTER], Output3.FUEL_LVL_LO_WARN):
            AlarmList.append("Fuel Level Low Warning - Fuel Level has gone below mimimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3[REGISTER], Output3.FUEL_LVL_FAULT):
            AlarmList.append("Fuel Level Fault - Fuel Level sensor exceeds nominal limits for valid sensor reading.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3[REGISTER], Output3.ANALOG_6_HI_ALRM):
            AlarmList.append("Analog Input 6 High Alarm - Analog Input 6 has gone above maximum alarm limit (Fuel Pressure or Inlet Air Temperature).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3[REGISTER], Output3.ANALOG_6_LO_ALRM):
            AlarmList.append("Analog Input 6 Low Alarm - Analog Input 6 has gone below mimimum alarm limit (Fuel Pressure or Inlet Air Temperature).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3[REGISTER], Output3.ANALOG_6_HI_WARN):
            AlarmList.append("Analog Input 6 High Warning - Analog Input 6 has gone above maximum warning limit (Fuel Pressure or Inlet Air Temperature).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3[REGISTER], Output3.ANALOG_6_LO_WARN):
            AlarmList.append("Analog Input 6 Low Warning - Analog Input 6 has gone below mimimum warning limit (Fuel Pressure or Inlet Air Temperature).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3[REGISTER], Output3.ANALOG_6_FAULT):
            AlarmList.append("Analog Input 6 Fault - Analog Input 6 sensor exceeds nominal limits for valid sensor reading (Fuel Pressure or Inlet Air Temperature).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3[REGISTER], Output3.GOV_POS_HI_ALARM):
            AlarmList.append("Throttle Position High Alarm - Throttle Position has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3[REGISTER], Output3.GOV_POS_LO_ALARM):
            AlarmList.append("Throttle Position Low Alarm - Throttle Position has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3[REGISTER], Output3.GOV_POS_HI_WARN):
            AlarmList.append("Throttle Position High Warning - Throttle Position has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3[REGISTER], Output3.GOV_POS_LO_WARN):
            AlarmList.append("Throttle Position Low Warning - Throttle Position has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4[REGISTER], Output4.GOV_POS_FAULT):
            AlarmList.append("Throttle Position Fault - Throttle Position sensor exceeds nominal limits for valid sensor reading.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4[REGISTER], Output4.OXYGEN_HI_ALARM):
            AlarmList.append("Analog Input 8 High Alarm - Analog Input 8 has gone above maximum alarm limit (Emissions Sensor or Fluid Basin).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4[REGISTER], Output4.OXYGEN_LO_ALARM):
            AlarmList.append("Analog Input 8 Low Alarm - Analog Input 8 has gone below minimum alarm limit (Emissions Sensor or Fluid Basin).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4[REGISTER], Output4.OXYGEN_HI_WARN):
            AlarmList.append("Analog Input 8 High Warning - Analog Input 8 has gone above maximum warning limit (Emissions Sensor or Fluid Basin).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4[REGISTER], Output4.OXYGEN_LO_WARN):
            AlarmList.append("Analog Input 8 Low Warning - Analog Input 8 has gone below minimum warning limit Emissions Sensor or Fluid Basin).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4[REGISTER], Output4.OXYGEN_SENSOR_FAULT):
            AlarmList.append("Analog Input 8 Fault - Analog Input 8 sensor exceeds nominal limits for valid sensor reading (Emissions Sensor or Fluid Basin).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4[REGISTER], Output4.CHG_CURR_HI_ALRM):
            AlarmList.append("Battery Charge Current High Alarm - Battery Charge Current has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4[REGISTER], Output4.CHG_CURR_LO_ALRM):
            AlarmList.append("Battery Charge Current Low Alarm - Battery Charge Current has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4[REGISTER], Output4.CHG_CURR_HI_WARN):
            AlarmList.append("Battery Charge Current High Warning - Battery Charge Current has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4[REGISTER], Output4.CHG_CURR_LO_WARN):
            AlarmList.append("Battery Charge Current Low Warning - Battery Charge Current has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4[REGISTER], Output4.CHG_CURR_FAULT):
            AlarmList.append("Battery Charge Current Fault - Battery Charge Current sensor exceeds nominal limits for valid sensor reading.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4[REGISTER], Output4.CHG_CURR_HI_ALRM):
            AlarmList.append("Battery Charge Current High Alarm - Battery Charge Current has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4[REGISTER], Output4.CHG_CURR_LO_ALRM):
            AlarmList.append("Battery Charge Current Low Alarm - Battery Charge Current has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4[REGISTER], Output4.CHG_CURR_HI_WARN):
            AlarmList.append("Battery Charge Current High Warning - Battery Charge Current has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4[REGISTER], Output4.CHG_CURR_LO_WARN):
            AlarmList.append("Battery Charge Current Low Warning - Battery Charge Current has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4[REGISTER], Output4.AVG_CURR_HI_ALRM):
            AlarmList.append("Average Current High Alarm - Average Current has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5[REGISTER], Output5.AVG_CURR_LO_ALRM):
            AlarmList.append("Average Current Low Alarm - Average Current has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5[REGISTER], Output5.AVG_CURR_HI_WARN):
            AlarmList.append("Average Current High Warning - Average Current has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5[REGISTER], Output5.AVG_CURR_LO_WARN):
            AlarmList.append("Average Current Low Warning - Average Current has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5[REGISTER], Output5.AVG_VOLT_HI_ALRM):
            AlarmList.append("Average Voltage High Alarm - Average Voltage has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5[REGISTER], Output5.AVG_VOLT_LO_ALRM):
            AlarmList.append("Average Voltage Low Alarm - Average Voltage has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5[REGISTER], Output5.AVG_VOLT_HI_WARN):
            AlarmList.append("Average Voltage High Warning - Average Voltage has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5[REGISTER], Output5.AVG_VOLT_LO_WARN):
            AlarmList.append("Average Voltage Low Warning - Average Voltage has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5[REGISTER], Output5.TOT_PWR_HI_ALARM):
            AlarmList.append("Total Real Power High Alarm - Total Real Power has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5[REGISTER], Output5.TOT_PWR_LO_ALARM):
            AlarmList.append("Total Real Power Low Alarm - Total Real Power has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5[REGISTER], Output5.AVG_VOLT_HI_WARN):
            AlarmList.append("Total Real Power High Warning - Total Real Power has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5[REGISTER], Output5.TOT_PWR_HI_WARN):
            AlarmList.append("Total Real Power Low Warning - Total Real Power has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5[REGISTER], Output5.GEN_FREQ_HI_ALRM):
            AlarmList.append("Generator Frequency High Alarm - Generator Frequency has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5[REGISTER], Output5.GEN_FREQ_LO_ALRM):
            AlarmList.append("Generator Frequency Low Alarm - Generator Frequency has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5[REGISTER], Output5.GEN_FREQ_HI_WARN):
            AlarmList.append("Generator Frequency High Warning - Generator Frequency has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5[REGISTER], Output5.GEN_FREQ_LO_WARN):
            AlarmList.append("Generator Frequency Low Warning - Generator Frequency has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5[REGISTER], Output5.GEN_FREQ_FAULT):
            AlarmList.append("Generator Frequency Fault - Generator Frequency sensor exceeds nominal limits for valid sensor reading.")

        if self.GetParameterBit(RegisterEnum.OUTPUT_6[REGISTER], Output6.ENG_RPM_HI_ALARM):
            AlarmList.append("Engine RPM High Alarm - Engine RPM has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_6[REGISTER], Output6.ENG_RPM_LO_ALARM):
            AlarmList.append("Engine RPM Low Alarm - Engine RPM has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_6[REGISTER], Output6.ENG_RPM_HI_WARN):
            AlarmList.append("Engine RPM High Warning - Engine RPM has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_6[REGISTER], Output6.ENG_RPM_LO_WARN):
            AlarmList.append("Engine RPM Low Warning - Engine RPM has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_6[REGISTER], Output6.ENG_RPM_FAULT):
            AlarmList.append("Engine RPM Fault - Engine RPM exceeds nominal limits for valid sensor reading.")

        if self.GetParameterBit(RegisterEnum.INPUT_1[REGISTER], Input1.DI1_BAT_CHRGR_FAIL):
            if self.GetParameterBit(RegisterEnum.OUTPUT_6[REGISTER], Output6.BATTERY_CHARGE_FAIL):
                AlarmList.append("Battery Charger Failure - Digital Input #5 active, Battery Charger Fail digital input active.")
        if self.GetParameterBit(RegisterEnum.INPUT_1[REGISTER], Input1.DI2_FUEL_PRESSURE):
            if self.GetParameterBit(RegisterEnum.OUTPUT_6[REGISTER], Output6.LOW_FUEL_PRS_ACT):
                AlarmList.append("Fuel Leak or Low Fuel Pressure - Ruptured Basin input active / Propane Gas Leak input active / Low Fuel Pressure digital input active.")

        if self.GetParameterBit(RegisterEnum.OUTPUT_6[REGISTER], Output6.ILC_ALR_WRN_1):
            AlarmList.append("Integrated Logic Controller Warning - Warning 1.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_7[REGISTER], Output7.ILC_ALR_WRN_2):
            AlarmList.append("Integrated Logic Controller Warning - Warning 2.")

        # This appers to always be on
        if self.GetParameterBit(RegisterEnum.OUTPUT_7[REGISTER], Output7.CHCK_V_PHS_ROT):
            AlarmList.append("Detected voltage phase rotation as not being A-B-C.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_7[REGISTER], Output7.CHCK_C_PHS_ROT):
            AlarmList.append("Detected current phase rotation as not being A-B-C and not matching voltage.")

        return AlarmList

    #------------ HPanel:ParseLogEntry ---------------------------------------------
    def ParseLogEntry(self, Entry, Type = None):

        try:
            if Type == None:
                return ""

            if not len(Entry):
                return ""

            # get time
            RetList = re.findall(r'\d{1,2}:\d{1,2}:\d{1,2}', Entry)
            if RetList == None or not len(RetList):
                self.LogError("ParseLogEntry: No Time found in log entry")
                return Entry
            EntryTime = RetList[0]
            # get date
            RetList = re.findall(r'\d{1,2}/\d{1,2}/\d{1,2}', Entry)
            if RetList == None or not len(RetList):
                self.LogError("ParseLogEntry: No date found in log entry")
                return Entry
            EntryDate = RetList[0]

            Entry = Entry.replace(EntryDate, "")
            Entry = Entry.replace(EntryTime, "")

            Entry = Entry.strip()

            Entry = Entry.replace("  ", "")
            if Type.lower() == "alarm":
                Entry = Entry.replace("(?)","Shutdown")

            elif Type.lower() == "event":
                Entry = Entry.replace("()", "")

            Entry = EntryDate + " " + EntryTime + " " + Entry

            return Entry
        except Exception as e1:
            self.LogErrorLine("Error in ParseLogEntry: " + str(e1))
            return ""

    #------------ HPanel:UpdateLog ---------------------------------------------
    def UpdateLog(self):

        try:
            LocalEvent = []
            for RegValue in range(EVENT_LOG_START + EVENT_LOG_ENTRIES -1 , EVENT_LOG_START -1, -1):
                Register = "%04x" % RegValue
                LogEntry = self.ModBus.ProcessMasterSlaveFileReadTransaction(Register, EVENT_LOG_LENGTH /2 , ReturnString = True)
                LogEntry = self.ParseLogEntry(LogEntry, Type = "event")
                if not len(LogEntry):
                    continue
                if "undefined" in LogEntry:
                    continue

                LocalEvent.append(LogEntry)

            with self.EventAccessLock:
                self.EventLog = LocalEvent

            LocalAlarm = []
            for RegValue in range(ALARM_LOG_START + ALARM_LOG_ENTRIES -1, ALARM_LOG_START -1, -1):
                Register = "%04x" % RegValue
                LogEntry = self.ModBus.ProcessMasterSlaveFileReadTransaction(Register, ALARM_LOG_LENGTH /2, ReturnString = True)

                LogEntry = self.ParseLogEntry(LogEntry, Type = "alarm")
                if not len(LogEntry):
                    continue

                LocalAlarm.append(LogEntry)

            '''
            for i in range(0, 21):
                Data = []
                Data.append(0)
                Data.append(i)
                self.ModBus.ProcessMasterSlaveWriteTransaction("01e0", len(Data) / 2, Data)
                AlarmInfo = self.ModBus.ProcessMasterSlaveTransaction("01e1", 32 / 2, skipupdate = True, ReturnString = True)
                self.LogError("Alarm Info: <" + str(AlarmInfo) + ">")
            '''
            with self.AlarmAccessLock:
                self.AlarmLog = list(LocalAlarm)

        except Exception as e1:
            self.LogErrorLine("Error in UpdateLog: " + str(e1))
    #------------ HPanel:CheckForAlarms ----------------------------------------
    def CheckForAlarms(self):

        try:
            if not self.InitComplete:
                return
            # Check for changes in engine state
            EngineState = self.GetEngineState()
            if not EngineState == self.LastEngineState:
                self.LastEngineState = EngineState
                self.UpdateLog()
                # This will trigger a call to CheckForalarms with ListOutput = True
                msgsubject = "Generator Notice: " + self.SiteName
                msgbody = self.DisplayStatus()
                self.MessagePipe.SendMessage(msgsubject , msgbody, msgtype = "warn")

            # Check for Alarms

            if self.SystemInAlarm():
                if not self.CurrentAlarmState:
                    msgsubject = "Generator Notice: ALARM Active at " + self.SiteName
                    msgbody = self.DisplayStatus()
                    self.MessagePipe.SendMessage(msgsubject , msgbody, msgtype = "warn")
            else:
                if self.CurrentAlarmState:
                    msgsubject = "Generator Notice: ALARM Clear at " + self.SiteName
                    msgbody = self.DisplayStatus()
                    self.MessagePipe.SendMessage(msgsubject , msgbody, msgtype = "warn")

            self.CurrentAlarmState = self.SystemInAlarm()

        except Exception as e1:
            self.LogErrorLine("Error in CheckForAlarms: " + str(e1))

        return

    #------------ HPanel:RegisterIsFileRecord ------------------------------
    def RegisterIsFileRecord(self, Register):

        try:
            RegInt = int(Register,16)

            if RegInt == 0x0040:
                return True
            if RegInt < ALARM_LOG_START or  RegInt > EVENT_LOG_START + EVENT_LOG_ENTRIES:
                return False

        except Exception as e1:
            self.LogErrorLine("Error in RegisterIsFileRecord: " + str(e1))

        return True

    #------------ HPanel:RegisterIsStringRegister ------------------------------
    def RegisterIsStringRegister(self, Register):

        StringList = RegisterStringEnum.GetRegList()
        for StringReg in StringList:
            if Register.lower() == StringReg[REGISTER].lower():
                return True
        return False

    #------------ HPanel:RegisterIsBaseRegister --------------------------------
    def RegisterIsBaseRegister(self, Register):

        RegisterList = RegisterEnum.GetRegList()
        for ListReg in RegisterList:
            if Register.lower() == ListReg[REGISTER].lower():
                return True
        return False

    #------------ HPanel:UpdateRegisterList ------------------------------------
    def UpdateRegisterList(self, Register, Value, IsString = False, IsFile = False):

        try:
            if len(Register) != 4:
                self.LogError("Validation Error: Invalid register value in UpdateRegisterList: %s %s" % (Register, Value))

            if self.RegisterIsBaseRegister(Register) and not IsFile:
                self.Registers[Register] = Value
            elif self.RegisterIsStringRegister(Register) and not IsFile:
                self.Strings[Register] = Value
            elif self.RegisterIsFileRecord(Register) and IsFile:
                self.FileData[Register] = Value
            else:
                self.LogError("Error in UpdateRegisterList: Unknown Register " + Register + ":" + Value + ": IsFile: " + str(IsFile) + ": " + "IsString: " + str(IsString))
        except Exception as e1:
            self.LogErrorLine("Error in UpdateRegisterList: " + str(e1))

    #---------------------HPanel::SystemInAlarm---------------------------------
    # return True if generator is in alarm, else False
    def SystemInAlarm(self):

        if self.GetParameter(RegisterEnum.ACTIVE_ALARM_COUNT[REGISTER], ReturnInt = True) != 0:
            return True
        if self.GetParameterBit(RegisterEnum.OUTPUT_1[REGISTER], Output1.COMMON_ALARM):
            return True
        if self.GetParameterBit(RegisterEnum.OUTPUT_1[REGISTER], Output1.COMMON_WARNING):
            return True
        return False
    #------------ HPanel:GetSwitchState ----------------------------------------
    def GetSwitchState(self):

        if self.GetParameterBit(RegisterEnum.OUTPUT_6[REGISTER], Output6.SWITCH_IN_MANUAL):
            return "Manual"
        elif self.GetParameterBit(RegisterEnum.OUTPUT_6[REGISTER], Output6.SWITCH_IN_AUTO):
            return "Auto"
        else:
            return "Off"

    #------------ HPanel:GetEngineState ----------------------------------------
    def GetEngineState(self):

        State = self.GetParameterStringValue(RegisterStringEnum.ENGINE_STATUS[REGISTER])

        if len(State):
            return State

        try:
            EngineState = ""
            if self.GetParameterBit(RegisterEnum.OUTPUT_1[REGISTER], Output1.GEN_READY_TO_RUN):
                EngineState += "Ready. "
            if self.GetParameterBit(RegisterEnum.OUTPUT_1[REGISTER], Output1.GEN_RUNNING):
                EngineState += "Running. "
            if self.GetParameterBit(RegisterEnum.OUTPUT_1[REGISTER], Output1.READY_FOR_LOAD):
                EngineState += "Ready for Load. "
            if self.GetParameterBit(RegisterEnum.OUTPUT_1[REGISTER], Output1.GEN_STOPPED_ALARM):
                EngineState += "Stopped in Alarm. "
            if self.GetParameterBit(RegisterEnum.OUTPUT_1[REGISTER], Output1.GEN_STOPPED):
                EngineState += "Stopped. "
            if self.GetParameterBit(RegisterEnum.OUTPUT_6[REGISTER], Output6.E_STOP_ACTIVE):
                EngineState += "E-Stop Active. "
            if self.GetParameterBit(RegisterEnum.OUTPUT_6[REGISTER], Output6.REMOTE_START_ACT):
                EngineState += "Remote Start Active. "
            if self.GetParameterBit(RegisterEnum.OUTPUT_7[REGISTER], Output7.IN_WARM_UP):
                EngineState += "Warming Up. "
            if self.GetParameterBit(RegisterEnum.OUTPUT_7[REGISTER], Output7.IN_COOL_DOWN):
                EngineState += "Cooling Down. "
            if self.GetParameterBit(RegisterEnum.OUTPUT_7[REGISTER], Output7.CRANKING):
                EngineState += "Cranking. "
            if self.GetParameterBit(RegisterEnum.OUTPUT_7[REGISTER], Output7.NEED_SERVICE):
                EngineState += "Needs Service. "
            if self.GetParameterBit(RegisterEnum.OUTPUT_7[REGISTER], Output7.SHUTDOWN_GENSET):
                EngineState += "Shutdown alarm is active. "
            if self.GetParameterBit(RegisterEnum.OUTPUT_7[REGISTER], Output7.INT_EXERCISE_ACT):
                EngineState += "Exercising. "
            if self.GetParameterBit(RegisterEnum.OUTPUT_1[REGISTER], Output1.GEN_IN_MANUAL):
                EngineState += "Generator In Manual. "
            if self.GetParameterBit(RegisterEnum.INPUT_1[REGISTER], Input1.REMOTE_START):
                EngineState += "Two Wire Start. "

            if not len(EngineState) and self.InitComplete and len(self.Registers):
                self.FeedbackPipe.SendFeedback("Engine State", FullLogs = True, Always = True, Message="Unknown Engine State")
                return "Unknown"
        except Exception as e1:
            self.LogErrorLine("Error in GetEngineState: " + str(e1))
        return EngineState

    #------------ HPanel:GetDateTime -------------------------------------------
    def GetDateTime(self):

        ErrorReturn = "Unknown"
        try:
            Value = self.GetParameter(RegisterEnum.GEN_TIME_HR_MIN[REGISTER])
            if not len(Value):
                return ErrorReturn

            TempInt = int(Value)
            Hour = TempInt >> 8
            Minute = TempInt & 0x00ff
            if Hour > 23 or Minute >= 60:
                self.LogError("Error in GetDateTime: Invalid Hour or Minute: " + str(Hour) + ", " + str(Minute))
                return ErrorReturn

            Value = self.GetParameter(RegisterEnum.GEN_TIME_SEC_DYWK[REGISTER])
            if not len(Value):
                return ErrorReturn
            TempInt = int(Value)
            Second = TempInt >> 8
            DayOfWeek = TempInt & 0x00ff
            if Second >= 60 or DayOfWeek > 7:
                self.LogError("Error in GetDateTime: Invalid Seconds or Day of Week: " + str(Second) + ", " + str(DayOfWeek))
                return ErrorReturn

            Value = self.GetParameter(RegisterEnum.GEN_TIME_MONTH_DAY[REGISTER])
            if not len(Value):
                return ErrorReturn
            TempInt = int(Value)
            Month = TempInt >> 8
            DayOfMonth = TempInt & 0x00ff
            if Month > 12 or Month == 0 or DayOfMonth == 0 or DayOfMonth > 31:
                self.LogError("Error in GetDateTime: Invalid Month or Day of Month: " + str(Month) + ", " + str(DayOfMonth))
                return ErrorReturn

            Value = self.GetParameter(RegisterEnum.GEN_TIME_YR[REGISTER])
            if not len(Value):
                return ErrorReturn
            TempInt = int(Value)
            Year = TempInt >> 8

            FullDate = self.DaysOfWeek.get(DayOfWeek,"INVALID") + " " + self.MonthsOfYear.get(Month,"INVALID")
            FullDate += " " + str(DayOfMonth) + ", " + "20" + str(Year) + " "
            FullDate += "%02d:%02d:%02d" %  (Hour, Minute,Second)
            return FullDate

        except Exception as e1:
            self.LogErrorLine("Error in GetDateTime: " + str(e1))
            return ErrorReturn
    #------------ HPanel::GetStartInfo -----------------------------------------
    # return a dictionary with startup info for the gui
    def GetStartInfo(self, NoTile = False):

        try:
            StartInfo = {}

            StartInfo["fueltype"] = self.FuelType
            StartInfo["model"] = self.Model
            StartInfo["nominalKW"] = self.NominalKW
            StartInfo["nominalRPM"] = self.NominalRPM
            StartInfo["nominalfrequency"] = self.NominalFreq
            StartInfo["NominalBatteryVolts"] = self.NominalBatteryVolts
            StartInfo["Controller"] = self.GetController()
            StartInfo["UtilityVoltage"] = False
            StartInfo["RemoteCommands"] = False
            StartInfo["ResetAlarms"] = False
            StartInfo["AckAlarms"] = True
            StartInfo["RemoteButtons"] = False
            StartInfo["PowerGraph"] = self.PowerMeterIsSupported()
            StartInfo["ExerciseControls"] = False  # self.SmartSwitch

            if not NoTile:
                StartInfo["pages"] = {
                                "status":True,
                                "maint":True,
                                "outage":False,
                                "logs":True,
                                "monitor": True,
                                "notifications": True,
                                "settings": True,
                                "addons": True,
                                "about": True
                                }

                StartInfo["tiles"] = []
                for Tile in self.TileList:
                    StartInfo["tiles"].append(Tile.GetStartInfo())

        except Exception as e1:
            self.LogErrorLine("Error in GetStartInfo: " + str(e1))

        return StartInfo
    #------------ HPanel::GetStatusForGUI --------------------------------------
    # return dict for GUI
    def GetStatusForGUI(self):

        try:
            Status = {}

            Status["basestatus"] = self.GetBaseStatus()
            Status["switchstate"] = self.GetSwitchState()
            Status["enginestate"] = self.GetEngineState()
            Status["kwOutput"] = self.GetPowerOutput()
            Status["OutputVoltage"] = self.GetParameter(RegisterEnum.AVG_VOLTAGE[REGISTER],"V")
            Status["BatteryVoltage"] = self.GetParameter(RegisterEnum.BATTERY_VOLTS[REGISTER], "V", 100.0)
            Status["UtilityVoltage"] = "0"
            Status["RPM"] = self.GetParameter(RegisterEnum.OUTPUT_RPM[REGISTER])
            Status["Frequency"] = self.GetParameter(RegisterEnum.OUTPUT_FREQUENCY[REGISTER], "Hz", 10.0)
            # Exercise Info is a dict containing the following:
            # TODO
            ExerciseInfo = collections.OrderedDict()
            ExerciseInfo["Enabled"] = False
            ExerciseInfo["Frequency"] = "Weekly"    # Biweekly, Weekly or Monthly
            ExerciseInfo["Hour"] = "14"
            ExerciseInfo["Minute"] = "00"
            ExerciseInfo["QuietMode"] = "Off"
            ExerciseInfo["EnhancedExerciseMode"] = False
            ExerciseInfo["Day"] = "Monday"
            Status["ExerciseInfo"] = ExerciseInfo

            Status["tiles"] = []
            for Tile in self.TileList:
                Status["tiles"].append(Tile.GetGUIInfo())

        except Exception as e1:
            self.LogErrorLine("Error in GetStatusForGUI: " + str(e1))

        return Status

    #---------------------HPanel::DisplayLogs-----------------------------------
    def DisplayLogs(self, AllLogs = False, DictOut = False, RawOutput = False):

        RetValue = collections.OrderedDict()
        LogList = []
        RetValue["Logs"] = LogList
        UnknownFound = False
        try:
            # if DictOut is True, return a dictionary with a list of Dictionaries (one for each log)
            # Each dict in the list is a log (alarm, start/stop). For Example:
            #
            #       Dict[Logs] = [ {"Alarm Log" : [Log Entry1, LogEntry2, ...]},
            #                      {"Run Log" : [Log Entry3, Log Entry 4, ...]}...]

            with self.EventAccessLock:
                LocalEventLog = list(self.EventLog)

            with self.AlarmAccessLock:
                LocalAlarmLog = (self.AlarmLog)
            LogList = [ {"Alarm Log": LocalAlarmLog},
                        {"Run Log": LocalEventLog}]

            RetValue["Logs"] = LogList


        except Exception as e1:
            self.LogErrorLine("Error in DisplayLogs: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(RetValue,""))

        return RetValue

    #------------ HPanel::DisplayMaintenance -----------------------------------
    def DisplayMaintenance (self, DictOut = False):

        try:
            # use ordered dict to maintain order of output
            # ordered dict to handle evo vs nexus functions
            Maintenance = collections.OrderedDict()
            Maint = collections.OrderedDict()
            Maintenance["Maintenance"] = Maint
            Maint["Model"] = self.Model
            Maint["Generator Serial Number"] = self.SerialNumber
            Maint["Controller"] = self.GetController()
            Maint["PM-DCP"] = self.GetParameterStringValue(RegisterStringEnum.PMDCP_INFO[REGISTER])

            Maint["Minimum GenLink Version"] = self.GetParameterStringValue(RegisterStringEnum.MIN_GENLINK_VERSION[REGISTER])
            Maint["Nominal RPM"] = self.NominalRPM
            Maint["Rated kW"] = self.NominalKW
            Maint["Nominal Frequency"] = self.NominalFreq
            Maint["Fuel Type"] = self.FuelType

            if not self.SmartSwitch:
                pass
                Exercise = collections.OrderedDict()
                #Maint["Exercise"] = Exercise
                #Exercise["Exercise Time"] = self.GetExerciseTime()
                #Exercise["Exercise Duration"] = self.GetExerciseDuration()

            Service = collections.OrderedDict()
            Maint["Service"] = Service

            Service["Total Run Hours"] = self.GetParameterLong(RegisterEnum.ENGINE_HOURS_LO[REGISTER], RegisterEnum.ENGINE_HOURS_HI[REGISTER],"H", 10.0)

        except Exception as e1:
            self.LogErrorLine("Error in DisplayMaintenance: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(Maintenance,""))

        return Maintenance

    #------------ HPanel::DisplayStatus ----------------------------------------
    def DisplayStatus(self, DictOut = False, JSONNum = False):

        try:
            Status = collections.OrderedDict()
            Stat = collections.OrderedDict()
            Status["Status"] = Stat
            Engine = collections.OrderedDict()
            Stat["Engine"] = Engine
            Alarms = collections.OrderedDict()
            Stat["Alarms"] = Alarms
            Battery = collections.OrderedDict()
            Stat["Battery"] = Battery
            Line = collections.OrderedDict()
            Stat["Line State"] = Line
            LastLog = collections.OrderedDict()
            Time = collections.OrderedDict()
            Stat["Time"] = Time

            Battery["Battery Voltage"] = self.ValueOut(self.GetParameter(RegisterEnum.BATTERY_VOLTS[REGISTER], ReturnFloat = True, Divider = 100.0), "V", JSONNum)
            Battery["Battery Charger Current"] = self.ValueOut(self.GetParameter(RegisterEnum.BATTERY_CHARGE_CURRNT[REGISTER], ReturnFloat = True, Divider = 10.0), "A", JSONNum)

            Engine["Engine Status"] = self.GetEngineState()
            Engine["Generator Status"] = self.GetParameterStringValue(RegisterStringEnum.GENERATOR_STATUS[REGISTER])
            Engine["Switch State"] = self.GetSwitchState()
            Engine["Output Power"] = self.ValueOut(self.GetPowerOutput(ReturnFloat = True), "kW", JSONNum)
            Engine["Output Power Factor"] = self.ValueOut(self.GetParameter(RegisterEnum.TOTAL_PF[REGISTER], ReturnFloat = True, Divider = 100.0), "", JSONNum)
            Engine["RPM"] = self.ValueOut(self.GetParameter(RegisterEnum.OUTPUT_RPM[REGISTER], ReturnInt = True), "", JSONNum)
            Engine["Frequency"] = self.ValueOut(self.GetParameter(RegisterEnum.OUTPUT_FREQUENCY[REGISTER], ReturnFloat = True, Divider = 10.0), "Hz", JSONNum)
            Engine["Throttle Position"] = self.ValueOut(self.GetParameter(RegisterEnum.THROTTLE_POSITION[REGISTER], ReturnInt = True), "Stp", JSONNum)
            Engine["Coolant Temp"] = self.ValueOut(self.GetParameter(RegisterEnum.COOLANT_TEMP[REGISTER], ReturnInt = True), "F", JSONNum)
            Engine["Coolant Level"] = self.ValueOut(self.GetParameter(RegisterEnum.COOLANT_LEVEL[REGISTER], ReturnInt = True), "Stp", JSONNum)
            Engine["Oil Pressure"] = self.ValueOut(self.GetParameter(RegisterEnum.OIL_PRESSURE[REGISTER], ReturnInt = True), "psi", JSONNum)
            Engine["Oil Temp"] = self.ValueOut(self.GetParameter(RegisterEnum.OIL_TEMP[REGISTER], ReturnInt = True), "F", JSONNum)
            Engine["Fuel Level"] = self.ValueOut(self.GetParameter(RegisterEnum.FUEL_LEVEL[REGISTER], ReturnInt = True), "", JSONNum)
            Engine["Oxygen Sensor"] = self.ValueOut(self.GetParameter(RegisterEnum.O2_SENSOR[REGISTER], ReturnInt = True), "", JSONNum)
            Engine["Current Phase A"] = self.ValueOut(self.GetParameter(RegisterEnum.CURRENT_PHASE_A[REGISTER], ReturnInt = True), "A", JSONNum)
            Engine["Current Phase B"] = self.ValueOut(self.GetParameter(RegisterEnum.CURRENT_PHASE_B[REGISTER],ReturnInt = True), "A", JSONNum)
            Engine["Current Phase C"] = self.ValueOut(self.GetParameter(RegisterEnum.CURRENT_PHASE_C[REGISTER],ReturnInt = True), "A", JSONNum)
            Engine["Average Current"] = self.ValueOut(self.GetParameter(RegisterEnum.AVG_CURRENT[REGISTER],ReturnInt = True), "A", JSONNum)
            Engine["Voltage A-B"] = self.ValueOut(self.GetParameter(RegisterEnum.VOLTS_PHASE_A_B[REGISTER],ReturnInt = True), "V", JSONNum)
            Engine["Voltage B-C"] = self.ValueOut(self.GetParameter(RegisterEnum.VOLTS_PHASE_B_C[REGISTER],ReturnInt = True), "V", JSONNum)
            Engine["Voltage C-A"] = self.ValueOut(self.GetParameter(RegisterEnum.VOLTS_PHASE_C_A[REGISTER],ReturnInt = True), "V", JSONNum)
            Engine["Average Voltage"] = self.ValueOut(self.GetParameter(RegisterEnum.AVG_VOLTAGE[REGISTER],ReturnInt = True), "V", JSONNum)
            Engine["Air Fuel Duty Cycle"] = self.ValueOut(self.GetParameter(RegisterEnum.A_F_DUTY_CYCLE[REGISTER], ReturnFloat = True, Divider = 10.0), "", JSONNum)

            if self.SystemInAlarm():
                Alarms["Alarm List"] = self.GetAlarmList()
            Alarms["Number of Active Alarms"] = self.ValueOut(self.GetParameter(RegisterEnum.ACTIVE_ALARM_COUNT[REGISTER], ReturnInt = True), "", JSONNum)

            Line["Transfer Switch State"] = self.GetTransferStatus()

            # Generator time
            Time["Monitor Time"] = datetime.datetime.now().strftime("%A %B %-d, %Y %H:%M:%S")
            Time["Generator Time"] = self.GetDateTime()


        except Exception as e1:
            self.LogErrorLine("Error in DisplayStatus: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(Status,""))

        return Status

    #------------------- HPanel::DisplayOutage ---------------------------------
    def DisplayOutage(self, DictOut = False):

        try:
            Outage = collections.OrderedDict()
            OutageData = collections.OrderedDict()
            Outage["Outage"] = OutageData

            OutageData["Status"] = "Not Supported"

        except Exception as e1:
            self.LogErrorLine("Error in DisplayOutage: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(Outage,""))

        return Outage

    #------------ HPanel::DisplayRegisters -------------------------------------
    def DisplayRegisters(self, AllRegs = False, DictOut = False):

        try:
            Registers = collections.OrderedDict()
            Regs = collections.OrderedDict()
            Registers["Registers"] = Regs

            RegList = []

            Regs["Num Regs"] = "%d" % len(self.Registers)

            Regs["Base Registers"] = RegList
            # display all the registers
            for Register, Value in self.Registers.items():
                RegList.append({Register:Value})


            if AllRegs:
                Regs["Log Registers"]= self.DisplayLogs(AllLogs = True, RawOutput = True, DictOut = True)
                StringList = []
                Regs["Strings"] = StringList
                for Register, Value in self.Strings.items():
                     StringList.append({Register:Value})
                FileDataList = []
                Regs["FileData"] = FileDataList
                for Register, Value in self.FileData.items():
                     FileDataList.append({Register:Value})

        except Exception as e1:
            self.LogErrorLine("Error in DisplayRegisters: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(Registers,""))

        return Registers

    #----------  HPanel::SetGeneratorTimeDate-----------------------------------
    # set generator time to system time
    def SetGeneratorTimeDate(self):

        try:
            # get system time
            d = datetime.datetime.now()

            # We will write four registers at once: GEN_TIME_HR_MIN - GEN_TIME_YR.
            Data= []
            Data.append(d.hour)             #GEN_TIME_HR_MIN
            Data.append(d.minute)
            self.ModBus.ProcessMasterSlaveWriteTransaction(RegisterEnum.GEN_TIME_HR_MIN[REGISTER], len(Data) / 2, Data)

            DayOfWeek = d.weekday()     # returns Monday is 0 and Sunday is 6
            # expects Sunday = 1, Saturday = 7
            if DayOfWeek == 6:
                DayOfWeek = 1
            else:
                DayOfWeek += 2
            Data= []
            Data.append(d.second)           #GEN_TIME_SEC_DYWK
            Data.append(DayOfWeek)                  #Day of Week is always zero
            self.ModBus.ProcessMasterSlaveWriteTransaction(RegisterEnum.GEN_TIME_SEC_DYWK[REGISTER], len(Data) / 2, Data)

            Data= []
            Data.append(d.month)            #GEN_TIME_MONTH_DAY
            Data.append(d.day)              # low byte is day of month
            self.ModBus.ProcessMasterSlaveWriteTransaction(RegisterEnum.GEN_TIME_MONTH_DAY[REGISTER], len(Data) / 2, Data)

            Data= []
            # Note: Day of week should always be zero when setting time
            Data.append(d.year - 2000)      # GEN_TIME_YR
            Data.append(0)                  #
            self.ModBus.ProcessMasterSlaveWriteTransaction(RegisterEnum.GEN_TIME_YR[REGISTER], len(Data) / 2, Data)

        except Exception as e1:
            self.LogErrorLine("Error in SetGeneratorTimeDate: " + str(e1))

    #----------  HPanel::SetGeneratorQuietMode----------------------------------
    # Format of CmdString is "setquiet=yes" or "setquiet=no"
    # return  "Set Quiet Mode Command sent" or some meaningful error string
    def SetGeneratorQuietMode(self, CmdString):
        return "Not Supported"

    #----------  HPanel::SetGeneratorExerciseTime-------------------------------
    # CmdString is in the format:
    #   setexercise=Monday,13:30,Weekly
    #   setexercise=Monday,13:30,BiWeekly
    #   setexercise=15,13:30,Monthly
    # return  "Set Exercise Time Command sent" or some meaningful error string
    def SetGeneratorExerciseTime(self, CmdString):
        return "Not Supported"

    #----------  HPanel::SetGeneratorRemoteCommand----------------------------
    # CmdString will be in the format: "setremote=start"
    # valid commands are start, stop, starttransfer, startexercise
    # return string "Remote command sent successfully" or some descriptive error
    # string if failure
    def SetGeneratorRemoteCommand(self, CmdString):

        #return "Not Supported"
        msgbody = "Invalid command syntax for command setremote (1)"

        try:
            #Format we are looking for is "setremote=start"
            CmdList = CmdString.split("=")
            if len(CmdList) != 2:
                self.LogError("Validation Error: Error parsing command string in SetGeneratorRemoteCommand (parse): " + CmdString)
                return msgbody

            CmdList[0] = CmdList[0].strip()

            if not CmdList[0].lower() == "setremote":
                self.LogError("Validation Error: Error parsing command string in SetGeneratorRemoteCommand (parse2): " + CmdString)
                return msgbody

            Command = CmdList[1].strip()
            Command = Command.lower()

        except Exception as e1:
            self.LogErrorLine("Validation Error: Error parsing command string in SetGeneratorRemoteCommand: " + CmdString)
            self.LogError( str(e1))
            return msgbody

        try:
            Value = 0x0000               # writing any value to index register is valid for remote start / stop commands
            Data = []
            if Command == "start":
                Value = 0x0001       # remote start
                Value2 = 0x0000
                Value3 = 0x0000
            elif Command == "stop":
                Value = 0x0000       # remote stop
                Value2 = 0x0000
                Value3 = 0x0000
            elif Command == "startstandby":
                Value = 0x0001       # remote start (standby)
                Value2 = 0x0000
                Value3 = 0x0001
            elif Command == "startparallel":
                Value = 0x0001       # remote start (parallel)
                Value2 = 0x0001
                Value3 = 0x0000
            elif Command == "quiettest":
                Data = []
                Data.append(0)
                Data.append(1)
                self.ModBus.ProcessMasterSlaveWriteTransaction(RegisterEnum.QUIETTEST_STATUS[REGISTER], len(Data) / 2, Data)
                return "Remote command sent successfully (quiettest)"
            elif Command == "quietteststop":
                Data = []
                Data.append(0)
                Data.append(0)
                self.ModBus.ProcessMasterSlaveWriteTransaction(RegisterEnum.QUIETTEST_STATUS[REGISTER], len(Data) / 2, Data)
                return "Remote command sent successfully (quietteststop)"
            elif Command == "ackalarm":
                Data = []
                Data.append(0)
                Data.append(1)
                self.ModBus.ProcessMasterSlaveWriteTransaction(RegisterEnum.ALARM_ACK[REGISTER], len(Data) / 2, Data)
                return "Remote command sent successfully (ackalarm)"
                '''
                # This does not work
                elif Command == "off":
                    Data = []
                    Data.append(0)
                    Data.append(0)
                    self.ModBus.ProcessMasterSlaveWriteTransaction(RegisterEnum.SWITCH_STATE[REGISTER], len(Data) / 2, Data)
                    return "Remote command sent successfully (off)"
                elif Command == "auto":
                    Data = []
                    Data.append(1)
                    Data.append(0)
                    self.ModBus.ProcessMasterSlaveWriteTransaction(RegisterEnum.SWITCH_STATE[REGISTER], len(Data) / 2, Data)
                    return "Remote command sent successfully (auto)"
                elif Command == "manual":
                    Data = []
                    Data.append(0)
                    Data.append(1)
                    self.ModBus.ProcessMasterSlaveWriteTransaction(RegisterEnum.SWITCH_STATE[REGISTER], len(Data) / 2, Data)
                    return "Remote command sent successfully (manual)"
                '''
            else:
                return "Invalid command syntax for command setremote (2)"

            Data.append(Value >> 8)             # value to be written (High byte)
            Data.append(Value & 0x00FF)         # value written (Low byte)
            Data.append(Value2 >> 8)            # value to be written (High byte)
            Data.append(Value2 & 0x00FF)        # value written (Low byte)
            Data.append(Value3 >> 8)            # value to be written (High byte)
            Data.append(Value3 & 0x00FF)        # value written (Low byte)

            ## Write 3 regs at once
            self.ModBus.ProcessMasterSlaveWriteTransaction(RegisterEnum.START_BITS[REGISTER], len(Data) / 2, Data)

            return "Remote command sent successfully"
        except Exception as e1:
            self.LogErrorLine("Error in SetGeneratorRemoteCommand: " + str(e1))
            return "Error"


    #----------  HPanel:GetController  -----------------------------------------
    # return the name of the controller, if Actual == False then return the
    # controller name that the software has been instructed to use if overridden
    # in the conf file
    def GetController(self, Actual = True):

        return self.GetParameterStringValue(RegisterStringEnum.CONTROLLER_NAME[REGISTER])

    #----------  HPanel:ComminicationsIsActive  --------------------------------
    # Called every 2 seconds, if communictions are failing, return False, otherwise
    # True
    def ComminicationsIsActive(self):
        if self.LastRxPacketCount == self.ModBus.RxPacketCount:
            return False
        else:
            self.LastRxPacketCount = self.ModBus.RxPacketCount
            return True

    #----------  HPanel:RemoteButtonsSupported  --------------------------------
    # return true if Panel buttons are settable via the software
    def RemoteButtonsSupported(self):
        return False
    #----------  HPanel:PowerMeterIsSupported  ---------------------------------
    # return true if GetPowerOutput is supported
    def PowerMeterIsSupported(self):

        if self.bDisablePowerLog:
            return False
        return True

    #---------------------HPanel::GetPowerOutput--------------------------------
    # returns current kW
    # rerturn empty string ("") if not supported,
    # return kW with units i.e. "2.45kW"
    def GetPowerOutput(self, ReturnFloat = False):

        if ReturnFloat:
            return self.GetParameter(RegisterEnum.TOTAL_POWER_KW[REGISTER], ReturnFloat = True)
        else:
            return self.GetParameter(RegisterEnum.TOTAL_POWER_KW[REGISTER], "kW", ReturnFloat = False)

    #----------  HPanel:GetCommStatus  -----------------------------------------
    # return Dict with communication stats
    def GetCommStatus(self):
        return self.ModBus.GetCommStats()

    #------------ HPanel:GetBaseStatus -----------------------------------------
    # return one of the following: "ALARM", "SERVICEDUE", "EXERCISING", "RUNNING",
    # "RUNNING-MANUAL", "OFF", "MANUAL", "READY"
    def GetBaseStatus(self):
        try:
            Status = self.GetEngineState()
            if "running" in Status.lower():
                IsRunning = True
            else:
                IsRunning = False

            if self.SystemInAlarm():
                return "ALARM"
            elif self.GetParameterBit(RegisterEnum.OUTPUT_7[REGISTER], Output7.NEED_SERVICE):
                return "SERVICEDUE"
            elif self.GetParameterBit(RegisterEnum.OUTPUT_7[REGISTER], Output7.INT_EXERCISE_ACT):
                return "EXERCISING"
            elif (IsRunning or self.GetParameterBit(RegisterEnum.OUTPUT_1[REGISTER], Output1.GEN_RUNNING)) and self.GetSwitchState().lower() == "auto":
                return "RUNNING"
            elif (IsRunning or self.GetParameterBit(RegisterEnum.OUTPUT_1[REGISTER], Output1.GEN_RUNNING)) and self.GetSwitchState().lower() == "manual":
                return "RUNNING-MANUAL"
            elif self.GetSwitchState().lower() == "manual":
                return "MANUAL"
            elif self.GetSwitchState().lower() == "auto":
                return "READY"
            elif self.GetSwitchState().lower() == "off":
                return "OFF"
            else:
                self.FeedbackPipe.SendFeedback("Base State", FullLogs = True, Always = True, Message="Unknown Base State")
                return "UNKNOWN"
        except Exception as e1:
            self.LogErrorLine("Error in GetBaseStatus: " + str(e1))
            return "UNKNOWN"

    #------------ HPanel:GetOneLineStatus --------------------------------------
    # returns a one line status for example : switch state and engine state
    def GetOneLineStatus(self):
        return self.GetSwitchState() + " : " + self.GetEngineState()
