#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: generac_H-100.py
# PURPOSE: Controller Specific Detils for Generac H-100
#
#  AUTHOR: Jason G Yates
#    DATE: 30-Apr-2018
#
# MODIFICATIONS:
#------------------------------------------------------------

import datetime, time, sys, os, threading, socket
import atexit, json, collections, random

import controller, mymodbus, mythread, modbus_file, mytile


#---------------------RegisterEnum::RegisterEnum--------------------------------
class RegisterEnum(object):
    UNK_2                   = "0002"            # UNKNOWN Bit 0100 change on power loss
    UNK_8                   = "0008"            # UNKNOWN
    CONTROLLER_NAME_START   = "0020"            # reg 0020 - 0035 "H-100 Controller, PM-DCP Release 4.1C , HW00"
    CONTROLLER_1            = "0021"            # Controller Name
    CONTROLLER_2            = "0022"            # Controller Name
    CONTROLLER_3            = "0023"            # Controller Name
    CONTROLLER_4            = "0024"            # Controller Name
    CONTROLLER_5            = "0025"            # Controller Name
    CONTROLLER_6            = "0026"            # Controller Name
    CONTROLLER_7            = "0027"            # Controller Name
    CONTROLLER_8            = "0028"            # Controller Name
    CONTROLLER_9            = "0029"            # Controller Name
    CONTROLLER_10           = "002a"            # Controller Name
    CONTROLLER_11           = "002b"            # Controller Name
    CONTROLLER_12           = "002c"            # Controller Name
    CONTROLLER_13           = "002d"            # Controller Name
    CONTROLLER_14           = "002e"            # Controller Name
    CONTROLLER_15           = "002f"            # Controller Name
    CONTROLLER_16           = "0030"            # Controller Name
    CONTROLLER_17           = "0031"            # Controller Name
    CONTROLLER_18           = "0031"            # Controller Name
    CONTROLLER_19           = "0033"            # Controller Name
    CONTROLLER_20           = "0034"            # Controller Name
    CONTROLLER_NAME_END     = "0035"            # Controller Name
    PMDCP_INFO_START        = "0040"            # reg 0040 - 005b "PM-DCP Release 4.1C , HW00, $Date: 2015/10/01 15:37:56 $"
    PMDCP_INFO_1            = "0041"            # PM-DCP Info
    PMDCP_INFO_2            = "0042"            # PM-DCP Info
    PMDCP_INFO_3            = "0043"            # PM-DCP Info
    PMDCP_INFO_4            = "0044"            # PM-DCP Info
    PMDCP_INFO_5            = "0045"            # PM-DCP Info
    PMDCP_INFO_6            = "0046"            # PM-DCP Info
    PMDCP_INFO_7            = "0047"            # PM-DCP Info
    PMDCP_INFO_8            = "0048"            # PM-DCP Info
    PMDCP_INFO_9            = "0049"            # PM-DCP Info
    PMDCP_INFO_10           = "004a"            # PM-DCP Info
    PMDCP_INFO_11           = "004b"            # PM-DCP Info
    PMDCP_INFO_12           = "004c"            # PM-DCP Info
    PMDCP_INFO_13           = "004d"            # PM-DCP Info
    PMDCP_INFO_14           = "004e"            # PM-DCP Info
    PMDCP_INFO_15           = "004f"            # PM-DCP Info
    PMDCP_INFO_16           = "0050"            # PM-DCP Info
    PMDCP_INFO_17           = "0051"            # PM-DCP Info
    PMDCP_INFO_18           = "0052"            # PM-DCP Info
    PMDCP_INFO_19           = "0053"            # PM-DCP Info
    PMDCP_INFO_20           = "0054"            # PM-DCP Info
    PMDCP_INFO_21           = "0055"            # PM-DCP Info
    PMDCP_INFO_22           = "0056"            # PM-DCP Info
    PMDCP_INFO_23           = "0057"            # PM-DCP Info
    PMDCP_INFO_24           = "0058"            # PM-DCP Info
    PMDCP_INFO_25           = "0059"            # PM-DCP Info
    PMDCP_INFO_26           = "005a"            # PM-DCP Info
    PMDCP_INFO_END          = "005b"            # PM-DCP Info

    VERSION_INFO_START      = "0060"            # reg 0060 - 0065 "4.0.1, 4.0.0"
    VERSION_INFO_1          = "0061"            # Version Info
    VERSION_INFO_2          = "0062"            # Version Info
    VERSION_INFO_3          = "0063"            # Version Info
    VERSION_INFO_4          = "0064"            # Version Info
    VERSION_INFO_5          = "0065"            # Version Info
    VERSION_INFO_END        = "0066"            # Version Info

    INPUT_1                 = "0080"            # Input 1
    INPUT_2                 = "0081"            # Input 2
    OUTPUT_1                = "0082"            # Output 1
    OUTPUT_2                = "0083"            # Output 2
    OUTPUT_3                = "0084"            # Output 3
    OUTPUT_4                = "0085"            # Output 4
    OUTPUT_5                = "0086"            # Output 5
    OUTPUT_6                = "0087"            # Output 6
    OUTPUT_7                = "0088"            # Output 7
    OUTPUT_8                = "0089"            # Output 8
    OIL_TEMP                = "008b"            # Oil Temp
    COOLANT_TEMP            = "008d"            # Coolant Temp
    OIL_PRESSURE            = "008f"            # Oil Pressure
    COOLANT_LEVEL           = "0091"            # Coolant Level
    FUEL_LEVEL              = "0093"            # USER CFG 05/Fuel Level =147
    USER_CFG_06             = "0095"            # USER CFG 06 = 149
    THROTTLE_POSITION       = "0097"            # Throttle Position
    O2_SENSOR               = "0099"            # O2 Sensor
    BATTERY_CHARGE_CURRNT   = "009b"            # Battery Charge Current NOTE: When the generator is running the battery charger current value may be wrong.
    BATTERY_VOLTS           = "009d"            # Battery Charge Volts
    CURRENT_PHASE_A         = "009f"            # Current Phase A
    CURRENT_PHASE_B         = "00a1"            # Current Phase B
    CURRENT_PHASE_C         = "00a3"            # Current Phase C
    AVG_CURRENT             = "00a5"            # Avg Current
    VOLTS_PHASE_A_B         = "00a7"            # Voltage Phase AB
    VOLTS_PHASE_B_C         = "00a9"            # Voltage Phase BC
    VOLTS_PHASE_C_A         = "00ab"            # Voltage Phase CA
    AVG_VOLTAGE             = "00ad"            # Average Voltage
    TOTAL_POWER_KW          = "00af"            # Total Power (kW)
    TOTAL_PF                = "00b1"            # Power Factor
    OUTPUT_FREQUENCY        = "00b3"            # Output Frequency
    OUTPUT_RPM              = "00b5"            # Output RPM
    A_F_DUTY_CYCLE          = "00b7"            # Air Fuel Duty Cycle
    UNK_B7                  = "00b9"            # Unknown (changes on power loss)
    UNK_DC                  = "00dc"            # UNKNOWN
    UNK_DD                  = "00dd"            # UNKNOWN
    GEN_TIME_HR_MIN         = "00e0"            # Time HR:MIN
    GEN_TIME_SEC_DYWK       = "00e1"            # Time SEC:DayOfWeek
    GEN_TIME_MONTH_DAY      = "00e2"            # Time Month:DayofMonth
    GEN_TIME_YR             = "00e3"            # Time YR:UNK
    GEN_TIME_5              = "00e4"            # Unknown (changes while running) High byte 100th of sec?, Low Byte?
    GEN_TIME_6              = "00e5"            # Unknown (changes while running) High byte incriments every min (0-59) Low Byte incriments every hour.
    GEN_TIME_7              = "00e6"            # Unknown
    GEN_TIME_8              = "00e7"            # Unknown
    UNK_EF                  = "00ef"            # Unknown (changes while running)
    UNK_F0                  = "00f0"            # Unknown (not used)
    UNK_F1                  = "00f1"            # Unknown (changes while running)
    UNK_F2                  = "00f2"            # Unknown (changes while running)
    UNK_F3                  = "00f3"            # Unknown (changes while running)
    UNK_104                 = "0104"            # UNKNOWN
    UNK_105                 = "0105"            # UNKNOWN
    UNK_106                 = "0106"            # UNKNOWN
    UNK_107                 = "0107"            # UNKNOWN
    UNK_108                 = "0108"            # UNKNOWN
    UNK_109                 = "0109"            # UNKNOWN
    UNK_10A                 = "010a"            # UNKNOWN
    UNK_10B                 = "010b"            # UNKNOWN
    UNK_110                 = "0110"            # UNKNOWN (change when running)
    ENGINE_HOURS_HI         = "0130"            # Engine Hours High
    ENGINE_HOURS_LO         = "0131"            # Engine Hours Low
    UNK_132                 = "0132"            # UNKNOWN
    STATUS_INFO_START       = "0133"            # reg 0133 - 013c "Running from Manual"
    STATUS_INFO_1           = "0134"            #
    STATUS_INFO_2           = "0135"            #
    STATUS_INFO_3           = "0136"            #
    STATUS_INFO_4           = "0137"            #
    STATUS_INFO_5           = "0138"            #
    STATUS_INFO_6           = "0139"            #
    STATUS_INFO_7           = "013a"            #
    STATUS_INFO_8           = "013b"            #
    STATUS_INFO_END         = "013c"            #

    STATUS_2_INFO_START     = "013f"            # reg 013f - 0148 "Running from 2-Wire"
    STATUS_2_INFO_1         = "0140"            #
    STATUS_2_INFO_2         = "0141"            #
    STATUS_2_INFO_3         = "0142"            #
    STATUS_2_INFO_4         = "0143"            #
    STATUS_2_INFO_5         = "0144"            #
    STATUS_2_INFO_6         = "0145"            #
    STATUS_2_INFO_7         = "0146"            #
    STATUS_2_INFO_8         = "0147"            #
    STATUS_2_INFO_END       = "0148"            #


    # reg 014b - 015c "Running from serWarmed Up, Alarms On"
    # reg 01e1 - 01e7 "OIL TEMP" or "No ECU Comms"

    # Register #665: DTC P0134 Fault Active Counter
    # This is a value between 0 and 5. If it is 5, then the DTC was active during
    # this Start/Stop cycle. If it is 1 through 4, then the DTC was not active
    # this Start/Stop cycle, but it was active in a previous cycle and has not
    # yet cleared. If it is 0, then the DTC is cleared.
    DTC_FAULT_COUNTER       = "0299"
    # Register #668: Oxygen Sensor Reading
    # This is a value between 0 and 1023. The lower the value the leaner the
    # combustion. The higher the value the richer the combustion. Roughly 450 is
    # the stoichiometric balance between lean and rich. It is desired that the
    # Oxygen Sensor tog- gle between rich and lean in order to optimize the
    # emissions.
    O2_SENSOR_EX            = "029c"
    # Register #670: Throttle Position
    # This is a value between 150 and 850 normally. The lower the number the
    # less flow there is. At rest, the throttle position is typically around
    # 150. Full open throttle is about 850.
    THROTTLE_POSITION_EX    = "029e"
    # Register #672: Generator Load / Engine Torque
    # This is the generator load in kW. It represents the engine output torque.
    GENERATOR_LOAD          = "02a0"
    # Register #673: Engine Speed
    # This is the engine speed in RPM * 8. A generator running at 1800 RPM will
    # show 14,400.
    ENGINE_SPEED            = "02a1"
    # Register #674: Engine Coolant Temperature
    # This is the coolant temperature in Celsius + 40. A generator with an
    # engine coolant temperature of 200 F will show 133.
    COOLANT_TEMP_EX         = "02a2"
    #---------------------RegisterEnum::GetRegList------------------------------
    @staticmethod
    def GetRegList():
        RetList = []
        for attr, value in RegisterEnum.__dict__.iteritems():
            if not callable(getattr(RegisterEnum(),attr)) and not attr.startswith("__"):
                RetList.append(value)

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

DEFAULT_THRESHOLD_VOLTAGE = 143
DEFAULT_PICKUP_VOLTAGE = 190

class HPanel(controller.GeneratorController):

    #---------------------HPanel::__init__--------------------------------------
    def __init__(self,
        log,
        newinstall = False,
        simulation = False,
        simulationfile = None,
        message = None,
        feedback = None,
        ConfigFilePath = None,
        config = None):

        # call parent constructor
        super(HPanel, self).__init__(log, newinstall = newinstall, simulation = simulation, simulationfile = simulationfile, message = message, feedback = feedback, ConfigFilePath = ConfigFilePath, config = config)

        self.LastEngineState = ""
        self.CurrentAlarmState = False
        self.VoltageConfig = None

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
                    self.Address, self.SerialPort, self.BaudRate, loglocation = self.LogLocation,
                    inputfile = self.SimulationFile)
            else:
                self.ModBus = mymodbus.ModbusProtocol(self.UpdateRegisterList,
                    self.Address, self.SerialPort, self.BaudRate, loglocation = self.LogLocation,
                    slowcpuoptimization = self.SlowCPUOptimization,
                    use_serial_tcp = self.UseSerialTCP,
                    tcp_address = self.SerialTCPAddress,
                    tcp_port = self.SerialTCPPort)

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
            if self.config.HasOption('address'):
                self.Address = int(self.config.ReadValue('address'),16)     # modbus address
            else:
                self.Address = 0x64

            if self.config.HasOption('voltageconfiguration'):
                self.VoltageConfig = self.config.ReadValue('voltageconfiguration')
            else:
                self.VoltageConfig = "277/480"

            if self.config.HasOption('nominalbattery'):
                self.NominalBatteryVolts = int(self.config.ReadValue('nominalbattery'))
            else:
                self.NominalBatteryVolts = 24

        except Exception as e1:
            self.FatalError("Missing config file or config file entries (HPanel): " + str(e1))
            return False

        return True

    #-------------HPanel:InitDevice---------------------------------------------
    # One time reads, and read all registers once
    def InitDevice(self):
        self.MasterEmulation()
        self.CheckModelSpecificInfo()
        self.SetupTiles()
        self.InitComplete = True
        self.InitCompleteEvent.set()

    #-------------HPanel:SetupTiles---------------------------------------------
    def SetupTiles(self):
        try:
            Tile = mytile.MyTile(self.log, title = "Battery Voltage", units = "V", type = "batteryvolts", nominal = self.NominalBatteryVolts,
                callback = self.GetParameter,
                callbackparameters = (RegisterEnum.BATTERY_VOLTS,  None, 100.0, False, False, True))
            self.TileList.append(Tile)

            # Nominal Voltage for gauge
            if self.VoltageConfig != None:
                #Valid settings are: 120/208, 120/240, 230/400, 240/415, 277/480, 347/600
                VoltageConfigList = self.VoltageConfig.split("/")
                NominalVoltage = int(VoltageConfigList[1])
            else:
                NominalVoltage = 600

            Tile = mytile.MyTile(self.log, title = "Average Voltage", units = "V", type = "linevolts", nominal = NominalVoltage,
            callback = self.GetParameter,
            callbackparameters = (RegisterEnum.AVG_VOLTAGE, None, None, False, True, False))
            self.TileList.append(Tile)

            NominalCurrent = int(self.NominalKW) * 1000 / NominalVoltage
            Tile = mytile.MyTile(self.log, title = "Average Current", units = "A", type = "current", nominal = NominalCurrent,
            callback = self.GetParameter,
            callbackparameters = (RegisterEnum.AVG_CURRENT, None, None, False, True, False))
            self.TileList.append(Tile)

            Tile = mytile.MyTile(self.log, title = "Frequency", units = "Hz", type = "frequency", nominal = int(self.NominalFreq),
            callback = self.GetParameter,
            callbackparameters = (RegisterEnum.OUTPUT_FREQUENCY, None, 10.0, False, False, True))
            self.TileList.append(Tile)

            Tile = mytile.MyTile(self.log, title = "RPM", type = "rpm", nominal = int(self.NominalRPM),
            callback = self.GetParameter,
            callbackparameters = (RegisterEnum.OUTPUT_RPM, None, None, False, True, False))
            self.TileList.append(Tile)

            # water temp between 170 and 200 is a normal range for a gen. most have a 180f thermostat
            Tile = mytile.MyTile(self.log, title = "Coolant Temp", units = "F", type = "temperature", subtype = "coolant", nominal = 180, maximum = 300,
            callback = self.GetParameter,
            callbackparameters = (RegisterEnum.COOLANT_TEMP, None, None, False, True, False))
            self.TileList.append(Tile)

            if self.PowerMeterIsSupported():
                Tile = mytile.MyTile(self.log, title = "Power Output", units = "kW", type = "power", nominal = int(self.NominalKW),
                callback = self.GetParameter,
                callbackparameters = (RegisterEnum.TOTAL_POWER_KW, None, None, False, True, False))
                self.TileList.append(Tile)

                Tile = mytile.MyTile(self.log, title = "kW Output", type = "powergraph", nominal = int(self.NominalKW),
                callback = self.GetParameter,
                callbackparameters = (RegisterEnum.TOTAL_POWER_KW, None, None, False, True, False))
                self.TileList.append(Tile)

        except Exception as e1:
            self.LogErrorLine("Error in SetupTiles: " + str(e1))

    #-------------HPanel:CheckModelSpecificInfo---------------------------------
    # check for model specific info in read from conf file, if not there then add some defaults
    def CheckModelSpecificInfo(self):

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
                RegValue = self.GetParameter( "%04x" % Register, ReturnInt = True)
                if RegValue == 0:
                    break
                ByteList.append(RegValue >> 8)
                ByteList.append(RegValue & 0xFF)
            return ReturnString.join(map(chr, ByteList))
        except Exception as e1:
            self.LogErrorLine("Error in GetStringParameter: " + str(e1))
            return ""

    #-------------HPanel:MasterEmulation----------------------------------------
    def MasterEmulation(self):

        for Register in RegisterEnum.GetRegList(): #RegisterEnum:
            try:
                if self.IsStopping:
                    return
                self.ModBus.ProcessMasterSlaveTransaction(Register, 1)
            except Exception as e1:
                self.LogErrorLine("Error in MasterEmulation: " + str(e1))
        self.CheckForAlarmEvent.set()

    #------------ HPanel:GetTransferStatus -------------------------------------
    def GetTransferStatus(self):

        LineState = "Unknown"
        #if self.GetParameterBit(RegisterEnum.INPUT_1, Input1.DI3_LINE_POWER):
        #if self.GetParameterBit(RegisterEnum.OUTPUT_6, Output6.DI3_LINE_PWR_ACT):
        if self.GetParameterBit(RegisterEnum.OUTPUT_6, Output6.LINE_POWER):
            LineState = "Utility"
        #if self.GetParameterBit(RegisterEnum.INPUT_1, Input1.DI4_GEN_POWER):
        #if self.GetParameterBit(RegisterEnum.OUTPUT_6, Output6.DI4_GEN_PWR_ACT):
        if self.GetParameterBit(RegisterEnum.OUTPUT_6, Output6.GEN_POWER):
            LineState = "Generator"
        return LineState

    #------------ HPanel:GetAlarmlist ------------------------------------------
    def GetAlarmList(self):

        AlarmList = []
        # Now check specific alarm conditions
        if self.GetParameterBit(RegisterEnum.OUTPUT_1, Output1.OVERCRANK_ALARM):
            AlarmList.append("Overcrank Alarm - Generator has unsuccessfully tried to start the designated number of times.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_1, Output1.OIL_INHIBIT_ALRM):
            AlarmList.append("Oil Inhibit Alarm - Oil pressure too high for a stopped engine.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_1, Output1.OIL_TEMP_HI_ALRM):
            AlarmList.append("Oil Temp High Alarm - Oil Temperature has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_1, Output1.OIL_TEMP_LO_ALRM):
            AlarmList.append("Oil Temp Low Alarm - Oil Temperature has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2, Output2.OIL_TEMP_HI_WARN):
            AlarmList.append("Oil Temp High Warning - Oil Temperature has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2, Output2.OIL_TEMP_LO_WARN):
            AlarmList.append("Oil Temp Low Warning - Oil Temperature has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2, Output2.OIL_TEMP_FAULT):
            AlarmList.append("Oil Temp Fault - Oil Temperature sensor exceeds nominal limits for valid sensor reading.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2, Output2.COOL_TMP_HI_ALRM):
            AlarmList.append("Coolant Temp High Alarm - Coolant Temperature has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2, Output2.COOL_TMP_LO_ALRM):
            AlarmList.append("Coolant Temp Low Alarm - Coolant Temperature has gone below mimimuim alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2, Output2.COOL_TMP_HI_WARN):
            AlarmList.append("Coolant Temp High Warning - Coolant Temperature has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2, Output2.COOL_TMP_LO_WARN):
            AlarmList.append("Coolant Temp Low Warning - Coolant Temperature has gone below mimimuim warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2, Output2.COOL_TMP_FAULT):
            AlarmList.append("Coolant Temp Fault - Coolant Temperature sensor exceeds nominal limits for valid sensor reading.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2, Output2.OIL_PRES_HI_ALRM):
            AlarmList.append("Oil Pressure High Alarm - Oil Pressure has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2, Output2.OIL_PRES_LO_ALRM):
            AlarmList.append("Oil Pressure Low Alarm - Oil Pressure has gone below mimimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2, Output2.OIL_PRES_HI_WARN):
            AlarmList.append("Oil Pressure High Warning - Oil Pressure has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2, Output2.OIL_PRES_LO_WARN):
            AlarmList.append("Oil Pressure Low Warning - Oil Pressure has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2, Output2.OIL_PRES_FAULT):
            AlarmList.append("Oil Pressure Fault - Oil Pressure sensor exceeds nominal limits for valid sensor reading.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2, Output2.COOL_LVL_HI_ALRM):
            AlarmList.append("Coolant Level High Alarm - Coolant Level has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2, Output2.COOL_LVL_LO_ALRM):
            AlarmList.append("Coolant Level Low Alarm - Coolant Level has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_2, Output2.COOL_LVL_HI_WARN):
            AlarmList.append("Coolant Level High Warning - Coolant Level has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3, Output3.COOL_LVL_LO_WARN):
            AlarmList.append("Coolant Level Low Warning - Coolant Level has gone below mimimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3, Output3.COOL_LVL_FAULT):
            AlarmList.append("Coolant Level Fault - Coolant Level sensor exceeds nominal limits for valid sensor reading.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3, Output3.FUEL_LVL_HI_ALRM):
            AlarmList.append("Fuel Level High Alarm - Fuel Level has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3, Output3.FUEL_LVL_LO_ALRM):
            AlarmList.append("Fuel Level Low Alarm - Fuel Level has gone below mimimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3, Output3.FUEL_LVL_HI_WARN):
            AlarmList.append("Fuel Level High Warning - Fuel Level has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3, Output3.FUEL_LVL_LO_WARN):
            AlarmList.append("Fuel Level Low Warning - Fuel Level has gone below mimimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3, Output3.FUEL_LVL_FAULT):
            AlarmList.append("Fuel Level Fault - Fuel Level sensor exceeds nominal limits for valid sensor reading.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3, Output3.ANALOG_6_HI_ALRM):
            AlarmList.append("Analog Input 6 High Alarm - Analog Input 6 has gone above maximum alarm limit (Fuel Pressure or Inlet Air Temperature).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3, Output3.ANALOG_6_LO_ALRM):
            AlarmList.append("Analog Input 6 Low Alarm - Analog Input 6 has gone below mimimum alarm limit (Fuel Pressure or Inlet Air Temperature).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3, Output3.ANALOG_6_HI_WARN):
            AlarmList.append("Analog Input 6 High Warning - Analog Input 6 has gone above maximum warning limit (Fuel Pressure or Inlet Air Temperature).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3, Output3.ANALOG_6_LO_WARN):
            AlarmList.append("Analog Input 6 Low Warning - Analog Input 6 has gone below mimimum warning limit (Fuel Pressure or Inlet Air Temperature).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3, Output3.ANALOG_6_FAULT):
            AlarmList.append("Analog Input 6 Fault - Analog Input 6 sensor exceeds nominal limits for valid sensor reading (Fuel Pressure or Inlet Air Temperature).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3, Output3.GOV_POS_HI_ALARM):
            AlarmList.append("Throttle Position High Alarm - Throttle Position has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3, Output3.GOV_POS_LO_ALARM):
            AlarmList.append("Throttle Position Low Alarm - Throttle Position has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3, Output3.GOV_POS_HI_WARN):
            AlarmList.append("Throttle Position High Warning - Throttle Position has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_3, Output3.GOV_POS_LO_WARN):
            AlarmList.append("Throttle Position Low Warning - Throttle Position has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4, Output4.GOV_POS_FAULT):
            AlarmList.append("Throttle Position Fault - Throttle Position sensor exceeds nominal limits for valid sensor reading.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4, Output4.OXYGEN_HI_ALARM):
            AlarmList.append("Analog Input 8 High Alarm - Analog Input 8 has gone above maximum alarm limit (Emissions Sensor or Fluid Basin).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4, Output4.OXYGEN_LO_ALARM):
            AlarmList.append("Analog Input 8 Low Alarm - Analog Input 8 has gone below minimum alarm limit (Emissions Sensor or Fluid Basin).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4, Output4.OXYGEN_HI_WARN):
            AlarmList.append("Analog Input 8 High Warning - Analog Input 8 has gone above maximum warning limit (Emissions Sensor or Fluid Basin).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4, Output4.OXYGEN_LO_WARN):
            AlarmList.append("Analog Input 8 Low Warning - Analog Input 8 has gone below minimum warning limit Emissions Sensor or Fluid Basin).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4, Output4.OXYGEN_SENSOR_FAULT):
            AlarmList.append("Analog Input 8 Fault - Analog Input 8 sensor exceeds nominal limits for valid sensor reading (Emissions Sensor or Fluid Basin).")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4, Output4.CHG_CURR_HI_ALRM):
            AlarmList.append("Battery Charge Current High Alarm - Battery Charge Current has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4, Output4.CHG_CURR_LO_ALRM):
            AlarmList.append("Battery Charge Current Low Alarm - Battery Charge Current has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4, Output4.CHG_CURR_HI_WARN):
            AlarmList.append("Battery Charge Current High Warning - Battery Charge Current has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4, Output4.CHG_CURR_LO_WARN):
            AlarmList.append("Battery Charge Current Low Warning - Battery Charge Current has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4, Output4.CHG_CURR_FAULT):
            AlarmList.append("Battery Charge Current Fault - Battery Charge Current sensor exceeds nominal limits for valid sensor reading.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4, Output4.CHG_CURR_HI_ALRM):
            AlarmList.append("Battery Charge Current High Alarm - Battery Charge Current has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4, Output4.CHG_CURR_LO_ALRM):
            AlarmList.append("Battery Charge Current Low Alarm - Battery Charge Current has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4, Output4.CHG_CURR_HI_WARN):
            AlarmList.append("Battery Charge Current High Warning - Battery Charge Current has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4, Output4.CHG_CURR_LO_WARN):
            AlarmList.append("Battery Charge Current Low Warning - Battery Charge Current has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_4, Output4.AVG_CURR_HI_ALRM):
            AlarmList.append("Average Current High Alarm - Average Current has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5, Output5.AVG_CURR_LO_ALRM):
            AlarmList.append("Average Current Low Alarm - Average Current has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5, Output5.AVG_CURR_HI_WARN):
            AlarmList.append("Average Current High Warning - Average Current has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5, Output5.AVG_CURR_LO_WARN):
            AlarmList.append("Average Current Low Warning - Average Current has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5, Output5.AVG_VOLT_HI_ALRM):
            AlarmList.append("Average Voltage High Alarm - Average Voltage has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5, Output5.AVG_VOLT_LO_ALRM):
            AlarmList.append("Average Voltage Low Alarm - Average Voltage has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5, Output5.AVG_VOLT_HI_WARN):
            AlarmList.append("Average Voltage High Warning - Average Voltage has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5, Output5.AVG_VOLT_LO_WARN):
            AlarmList.append("Average Voltage Low Warning - Average Voltage has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5, Output5.TOT_PWR_HI_ALARM):
            AlarmList.append("Total Real Power High Alarm - Total Real Power has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5, Output5.TOT_PWR_LO_ALARM):
            AlarmList.append("Total Real Power Low Alarm - Total Real Power has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5, Output5.AVG_VOLT_HI_WARN):
            AlarmList.append("Total Real Power High Warning - Total Real Power has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5, Output5.TOT_PWR_HI_WARN):
            AlarmList.append("Total Real Power Low Warning - Total Real Power has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5, Output5.GEN_FREQ_HI_ALRM):
            AlarmList.append("Generator Frequency High Alarm - Generator Frequency has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5, Output5.GEN_FREQ_LO_ALRM):
            AlarmList.append("Generator Frequency Low Alarm - Generator Frequency has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5, Output5.GEN_FREQ_HI_WARN):
            AlarmList.append("Generator Frequency High Warning - Generator Frequency has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5, Output5.GEN_FREQ_LO_WARN):
            AlarmList.append("Generator Frequency Low Warning - Generator Frequency has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_5, Output5.GEN_FREQ_FAULT):
            AlarmList.append("Generator Frequency Fault - Generator Frequency sensor exceeds nominal limits for valid sensor reading.")

        if self.GetParameterBit(RegisterEnum.OUTPUT_6, Output6.ENG_RPM_HI_ALARM):
            AlarmList.append("Engine RPM High Alarm - Engine RPM has gone above maximum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_6, Output6.ENG_RPM_LO_ALARM):
            AlarmList.append("Engine RPM Low Alarm - Engine RPM has gone below minimum alarm limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_6, Output6.ENG_RPM_HI_WARN):
            AlarmList.append("Engine RPM High Warning - Engine RPM has gone above maximum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_6, Output6.ENG_RPM_LO_WARN):
            AlarmList.append("Engine RPM Low Warning - Engine RPM has gone below minimum warning limit.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_6, Output6.ENG_RPM_FAULT):
            AlarmList.append("Engine RPM Fault - Engine RPM exceeds nominal limits for valid sensor reading.")

        if self.GetParameterBit(RegisterEnum.INPUT_1, Input1.DI1_BAT_CHRGR_FAIL):
            if self.GetParameterBit(RegisterEnum.OUTPUT_6, Output6.BATTERY_CHARGE_FAIL):
                AlarmList.append("Battery Charger Failure - Digital Input #5 active, Battery Charger Fail digital input active.")
        if self.GetParameterBit(RegisterEnum.INPUT_1, Input1.DI2_FUEL_PRESSURE):
            if self.GetParameterBit(RegisterEnum.OUTPUT_6, Output6.LOW_FUEL_PRS_ACT):
                AlarmList.append("Fuel Leak or Low Fuel Pressure - Ruptured Basin input active / Propane Gas Leak input active / Low Fuel Pressure digital input active.")

        if self.GetParameterBit(RegisterEnum.OUTPUT_6, Output6.ILC_ALR_WRN_1):
            AlarmList.append("Integrated Locic Controller Warning - Warning 1.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_7, Output7.ILC_ALR_WRN_2):
            AlarmList.append("Integrated Locic Controller Warning - Warning 2.")

        if self.GetParameterBit(RegisterEnum.OUTPUT_7, Output7.CHCK_V_PHS_ROT):
            AlarmList.append("Detected voltage phase rotation as not being A-B-C.")
        if self.GetParameterBit(RegisterEnum.OUTPUT_7, Output7.CHCK_C_PHS_ROT):
            AlarmList.append("Detected current phase rotation as not being A-B-C and not matching voltage.")

        return AlarmList

    #------------ HPanel:CheckForAlarms ----------------------------------------
    def CheckForAlarms(self):

        try:
            if not self.InitComplete:
                return
            # Check for changes in engine state
            EngineState = self.GetEngineState()
            if not EngineState == self.LastEngineState:
                self.LastEngineState = EngineState
                # This will trigger a call to CheckForalarms with LisOutput = True
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
    #------------ HPanel:RegisterIsKnown ---------------------------------------
    def RegisterIsKnown(self, Register):

        return Register in RegisterEnum.GetRegList()

    #------------ HPanel:UpdateRegisterList ------------------------------------
    def UpdateRegisterList(self, Register, Value):

        try:
            # TODO validate registers
            # Validate Register by length
            if len(Register) != 4 or len(Value) < 4:
                self.LogErrorLine("Validation Error: Invalid data in UpdateRegisterList: %s %s" % (Register, Value))

            if self.RegisterIsKnown(Register):
                self.Registers[Register] = Value
            else:
                self.LogErrorLine("Error in UpdateRegisterList: Unknown Register " + Register + ":" + Value)
        except Exception as e1:
            self.LogErrorLine("Error in UpdateRegisterList: " + str(e1))

    #---------------------HPanel::SystemInAlarm---------------------------------
    # return True if generator is in alarm, else False
    def SystemInAlarm(self):

        if self.GetParameterBit(RegisterEnum.OUTPUT_1, Output1.COMMON_ALARM):
            return True
        if self.GetParameterBit(RegisterEnum.OUTPUT_1, Output1.COMMON_WARNING):
            return True
        return False
    #------------ HPanel:GetSwitchState ----------------------------------------
    def GetSwitchState(self):

        if self.GetParameterBit(RegisterEnum.OUTPUT_6, Output6.SWITCH_IN_MANUAL):
            return "Manual"
        elif self.GetParameterBit(RegisterEnum.OUTPUT_6, Output6.SWITCH_IN_AUTO):
            return "Auto"
        else:
            return "Off"

    #------------ HPanel:GetEngineState ----------------------------------------
    def GetEngineState(self):

        EngineState = ""
        if self.GetParameterBit(RegisterEnum.OUTPUT_1, Output1.GEN_READY_TO_RUN):
            EngineState += "Ready. "
        if self.GetParameterBit(RegisterEnum.OUTPUT_1, Output1.GEN_RUNNING):
            EngineState += "Running. "
        if self.GetParameterBit(RegisterEnum.OUTPUT_1, Output1.READY_FOR_LOAD):
            EngineState += "Ready for Load. "
        if self.GetParameterBit(RegisterEnum.OUTPUT_1, Output1.GEN_STOPPED_ALARM):
            EngineState += "Stopped in Alarm. "
        if self.GetParameterBit(RegisterEnum.OUTPUT_1, Output1.GEN_STOPPED):
            EngineState += "Stopped. "
        if self.GetParameterBit(RegisterEnum.OUTPUT_6, Output6.E_STOP_ACTIVE):
            EngineState += "E-Stop Active. "
        if self.GetParameterBit(RegisterEnum.OUTPUT_6, Output6.REMOTE_START_ACT):
            EngineState += "Remote Start Active. "
        if self.GetParameterBit(RegisterEnum.OUTPUT_7, Output7.IN_WARM_UP):
            EngineState += "Warming Up. "
        if self.GetParameterBit(RegisterEnum.OUTPUT_7, Output7.IN_COOL_DOWN):
            EngineState += "Cooling Down. "
        if self.GetParameterBit(RegisterEnum.OUTPUT_7, Output7.CRANKING):
            EngineState += "Cranking. "
        if self.GetParameterBit(RegisterEnum.OUTPUT_7, Output7.NEED_SERVICE):
            EngineState += "Needs Service. "
        if self.GetParameterBit(RegisterEnum.OUTPUT_7, Output7.SHUTDOWN_GENSET):
            EngineState += "Shutdown alarm is active. "
        if self.GetParameterBit(RegisterEnum.OUTPUT_7, Output7.INT_EXERCISE_ACT):
            EngineState += "Exercising. "

        if not len(EngineState) and self.InitComplete and len(self.Registers):
            self.FeedbackPipe.SendFeedback("Engine State", FullLogs = True, Always = True, Message="Unknown Engine State")
            return "Unknown"
        return EngineState

    #------------ Evolution:HPanel -----------------------------------------
    def GetDateTime(self):

        ErrorReturn = "Unknown"
        try:
            Value = self.GetParameter(RegisterEnum.GEN_TIME_HR_MIN)
            if not len(Value):
                return ErrorReturn

            TempInt = int(Value)
            Hour = TempInt >> 8
            Minute = TempInt & 0x00ff
            if Hour > 23 or Minute >= 60:
                self.LogError("Error in GetDateTime: Invalid Hour or Minute: " + str(Hour) + ", " + str(Minute))
                return ErrorReturn

            Value = self.GetParameter(RegisterEnum.GEN_TIME_SEC_DYWK)
            if not len(Value):
                return ErrorReturn
            TempInt = int(Value)
            Second = TempInt >> 8
            DayOfWeek = TempInt & 0x00ff
            if Second >= 60 or DayOfWeek > 7:
                self.LogError("Error in GetDateTime: Invalid Seconds or Day of Week: " + str(Second) + ", " + str(DayOfWeek))
                return ErrorReturn

            Value = self.GetParameter(RegisterEnum.GEN_TIME_MONTH_DAY)
            if not len(Value):
                return ErrorReturn
            TempInt = int(Value)
            Month = TempInt >> 8
            DayOfMonth = TempInt & 0x00ff
            if Month > 12 or Month == 0 or DayOfMonth == 0 or DayOfMonth > 31:
                self.LogError("Error in GetDateTime: Invalid Month or Day of Month: " + str(Month) + ", " + str(DayOfMonth))
                return ErrorValue

            Value = self.GetParameter(RegisterEnum.GEN_TIME_YR)
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
    #------------ HPanel::GetStartInfo ----------------------------
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
            StartInfo["RemoteButtons"] = False
            StartInfo["PowerGraph"] = self.PowerMeterIsSupported()
            if not NoTile:
                StartInfo["pages"] = {
                                "status":True,
                                "maint":True,
                                "outage":False,
                                "logs":False,
                                "monitor": True,
                                "notifications": True,
                                "settings": True
                                }

                StartInfo["tiles"] = []
                for Tile in self.TileList:
                    StartInfo["tiles"].append(Tile.GetStartInfo())

            return StartInfo
        except Exception as e1:
            self.LogErrorLine("Error in GetStartInfo: " + str(e1))
            return ""
    #------------ HPanel::GetStatusForGUI -------------------------
    # return dict for GUI
    def GetStatusForGUI(self):

        try:
            Status = {}

            Status["basestatus"] = self.GetBaseStatus()
            Status["switchstate"] = self.GetSwitchState()
            Status["enginestate"] = self.GetEngineState()
            Status["kwOutput"] = self.GetPowerOutput()
            Status["OutputVoltage"] = self.GetParameter(RegisterEnum.AVG_VOLTAGE,"V")
            Status["BatteryVoltage"] = self.GetParameter(RegisterEnum.BATTERY_VOLTS, "V", 100.0)
            Status["UtilityVoltage"] = "0"
            Status["RPM"] = self.GetParameter(RegisterEnum.OUTPUT_RPM)
            Status["Frequency"] = self.GetParameter(RegisterEnum.OUTPUT_FREQUENCY, "Hz", 10.0)
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

            return Status
        except Exception as e1:
            self.LogErrorLine("Error in GetStatusForGUI: " + str(e1))
            return ""

    #---------------------HPanel::DisplayLogs----------------------
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
            #                      {"Start Stop Log" : [Log Entry3, Log Entry 4, ...]}...]

            ALARMLOG     = "Alarm Log:     "
            SERVICELOG   = "Service Log:   "
            STARTSTOPLOG = "Start Stop Log:"

            LogList = [ {"Alarm Log": ["Not Implemented"]},
                        {"Start Stop Log": ["Not Implemented"]}]

            RetValue["Logs"] = LogList
            if UnknownFound:
                msgbody = "\nThe output appears to have unknown values. Please see the following threads to resolve these issues:"
                msgbody += "\n        https://github.com/jgyates/genmon/issues/12"
                msgbody += "\n        https://github.com/jgyates/genmon/issues/13"
                RetValue["Note"] = msgbody
                self.FeedbackPipe.SendFeedback("Logs", FullLogs = True, Always = True, Message="Unknown Entries in Log")

            if not DictOut:
                return self.printToString(self.ProcessDispatch(RetValue,""))

            return RetValue

        except Exception as e1:
            self.LogErrorLine("Error in DisplayLogs: " + str(e1))
            return ""

    #------------ HPanel::DisplayMaintenance ----------------------
    def DisplayMaintenance (self, DictOut = False):

        try:
            # use ordered dict to maintain order of output
            # ordered dict to handle evo vs nexus functions
            Maintenance = collections.OrderedDict()
            Maint = collections.OrderedDict()
            Maintenance["Maintenance"] = Maint
            Maint["Model"] = self.Model
            # TODO
            #Maint["Generator Serial Number"] = self.GetSerialNumber()
            Maint["Controller"] = self.GetController()
            Maint["PM-DCP"] = self.GetParameterString(RegisterEnum.PMDCP_INFO_START, RegisterEnum.PMDCP_INFO_END)
            Maint["Version"] = self.GetParameterString(RegisterEnum.VERSION_INFO_START, RegisterEnum.VERSION_INFO_END)
            Maint["Nominal RPM"] = self.NominalRPM
            Maint["Rated kW"] = self.NominalKW
            Maint["Nominal Frequency"] = self.NominalFreq
            Maint["Fuel Type"] = self.FuelType
            Exercise = collections.OrderedDict()
            Maint["Exercise"] = Exercise
            #Exercise["Exercise Time"] = self.GetExerciseTime()
            #Exercise["Exercise Duration"] = self.GetExerciseDuration()

            Service = collections.OrderedDict()
            Maint["Service"] = Service
            #Service["Service A Due"] = self.GetServiceDue("A") + " or " + self.GetServiceDueDate("A")
            #Service["Service B Due"] = self.GetServiceDue("B") + " or " + self.GetServiceDueDate("B")

            Service["Total Run Hours"] = self.GetParameterLong(RegisterEnum.ENGINE_HOURS_LO, RegisterEnum.ENGINE_HOURS_HI,"H", 10.0)
            #Service["Hardware Version"] = self.GetHardwareVersion()
            #Service["Firmware Version"] = self.GetFirmwareVersion()


            if not DictOut:
                return self.printToString(self.ProcessDispatch(Maintenance,""))

            return Maintenance
        except Exception as e1:
            self.LogErrorLine("Error in DisplayMaintenance: " + str(e1))
            return ""

    #------------ HPanel::DisplayStatus ---------------------------
    def DisplayStatus(self, DictOut = False):

        try:
            Status = collections.OrderedDict()
            Stat = collections.OrderedDict()
            Status["Status"] = Stat
            Engine = collections.OrderedDict()
            Stat["Engine"] = Engine
            Battery = collections.OrderedDict()
            Stat["Battery"] = Battery
            Line = collections.OrderedDict()
            Stat["Line State"] = Line
            LastLog = collections.OrderedDict()
            Time = collections.OrderedDict()
            Stat["Time"] = Time


            Battery["Battery Voltage"] = self.GetParameter(RegisterEnum.BATTERY_VOLTS, "V", 100.0)
            Battery["Battery Charger Current"] = self.GetParameter(RegisterEnum.BATTERY_CHARGE_CURRNT, "A", 10.0)

            Engine["Current Status"] = self.GetParameterString(RegisterEnum.STATUS_INFO_START, RegisterEnum.STATUS_INFO_END)
            Engine["Previous Status"] = self.GetParameterString(RegisterEnum.STATUS_2_INFO_START, RegisterEnum.STATUS_2_INFO_END)
            Engine["Switch State"] = self.GetSwitchState()
            Engine["Engine State"] = self.GetEngineState()
            Engine["Output Power"] = self.GetPowerOutput()
            Engine["Output Power Factor"] = self.GetParameter(RegisterEnum.TOTAL_PF, Divider = 100.0)
            Engine["RPM"] = self.GetParameter(RegisterEnum.OUTPUT_RPM)
            Engine["Frequency"] = self.GetParameter(RegisterEnum.OUTPUT_FREQUENCY, "Hz", 10.0)
            Engine["Throttle Position"] = self.GetParameter(RegisterEnum.THROTTLE_POSITION, "Stp")
            Engine["Coolant Temp"] = self.GetParameter(RegisterEnum.COOLANT_TEMP, "F")
            Engine["Coolant Level"] = self.GetParameter(RegisterEnum.COOLANT_LEVEL, "Stp")
            Engine["Oil Pressure"] = self.GetParameter(RegisterEnum.OIL_PRESSURE, "psi")
            Engine["Oil Temp"] = self.GetParameter(RegisterEnum.OIL_TEMP, "F")
            Engine["Fuel Level"] = self.GetParameter(RegisterEnum.FUEL_LEVEL)
            Engine["Oxygen Sensor"] = self.GetParameter(RegisterEnum.O2_SENSOR)
            Engine["Current Phase A"] = self.GetParameter(RegisterEnum.CURRENT_PHASE_A,"A")
            Engine["Current Phase B"] = self.GetParameter(RegisterEnum.CURRENT_PHASE_B,"A")
            Engine["Current Phase C"] = self.GetParameter(RegisterEnum.CURRENT_PHASE_C,"A")
            Engine["Average Current"] = self.GetParameter(RegisterEnum.AVG_CURRENT,"A")
            Engine["Voltage A-B"] = self.GetParameter(RegisterEnum.VOLTS_PHASE_A_B,"V")
            Engine["Voltage B-C"] = self.GetParameter(RegisterEnum.VOLTS_PHASE_B_C,"V")
            Engine["Voltage C-A"] = self.GetParameter(RegisterEnum.VOLTS_PHASE_C_A,"V")
            Engine["Average Voltage"] = self.GetParameter(RegisterEnum.AVG_VOLTAGE,"V")
            Engine["Air Fuel Duty Cycle"] = self.GetParameter(RegisterEnum.A_F_DUTY_CYCLE, Divider = 10.0)

            if self.SystemInAlarm():
                Engine["System In Alarm"] = self.GetAlarmList()

            Line["Transfer Switch State"] = self.GetTransferStatus()

            # Generator time
            Time["Monitor Time"] = datetime.datetime.now().strftime("%A %B %-d, %Y %H:%M:%S")
            Time["Generator Time"] = self.GetDateTime()

            #Stat["Last Log Entries"] = self.DisplayLogs(AllLogs = False, DictOut = True)


            if not DictOut:
                return self.printToString(self.ProcessDispatch(Status,""))

            return Status
        except Exception as e1:
            self.LogErrorLine("Error in DisplayStatus: " + str(e1))
            return ""


    #------------------- HPanel::DisplayOutage --------------------
    def DisplayOutage(self, DictOut = False):

        try:
            Outage = collections.OrderedDict()
            OutageData = collections.OrderedDict()
            Outage["Outage"] = OutageData

            OutageData["Status"] = "Not Supported"

            if not DictOut:
                return self.printToString(self.ProcessDispatch(Outage,""))

            return Outage
        except Exception as e1:
            self.LogErrorLine("Error in DisplayOutage: " + str(e1))
            return ""


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

                # do not display log registers or model register
                # TODO
                #if self.RegisterIsLog(Register):
                #    continue
                ##
                RegList.append({Register:Value})


            if AllRegs:
                Regs["Log Registers"]= self.DisplayLogs(AllLogs = True, RawOutput = True, DictOut = True)

            if not DictOut:
                return self.printToString(self.ProcessDispatch(Registers,""))

            return Registers
        except Exception as e1:
            self.LogErrorLine("Error in DisplayRegisters: " + str(e1))
            return ""

    #----------  HPanel::SetGeneratorTimeDate----------------------
    # set generator time to system time
    def SetGeneratorTimeDate(self):

        try:
            # get system time
            d = datetime.datetime.now()

            # We will write four registers at once: GEN_TIME_HR_MIN - GEN_TIME_YR.
            Data= []
            Data.append(d.hour)             #GEN_TIME_HR_MIN
            Data.append(d.minute)
            Data.append(d.second)          #GEN_TIME_SEC_DYWK
            Data.append(0)                  #Day of Week is always zero
            Data.append(d.month)            #GEN_TIME_MONTH_DAY
            Data.append(d.day)              # low byte is day of month
            # Note: Day of week should always be zero when setting time
            Data.append(d.year - 2000)      # GEN_TIME_YR
            Data.append(0)                  #
            self.ModBus.ProcessMasterSlaveWriteTransaction(RegisterEnum.GEN_TIME_HR_MIN, len(Data) / 2, Data)
        except Exception as e1:
            self.LogErrorLine("Error in SetGeneratorTimeDate: " + str(e1))

    #----------  HPanel::SetGeneratorQuietMode---------------------
    # Format of CmdString is "setquiet=yes" or "setquiet=no"
    # return  "Set Quiet Mode Command sent" or some meaningful error string
    def SetGeneratorQuietMode(self, CmdString):
        return "Not Supported"

    #----------  HPanel::SetGeneratorExerciseTime------------------
    # CmdString is in the format:
    #   setexercise=Monday,13:30,Weekly
    #   setexercise=Monday,13:30,BiWeekly
    #   setexercise=15,13:30,Monthly
    # return  "Set Exercise Time Command sent" or some meaningful error string
    def SetGeneratorExerciseTime(self, CmdString):
        return "Not Supported"

    #----------  HPanel::SetGeneratorRemoteStartStop---------------
    # CmdString will be in the format: "setremote=start"
    # valid commands are start, stop, starttransfer, startexercise
    # return string "Remote command sent successfully" or some descriptive error
    # string if failure
    def SetGeneratorRemoteStartStop(self, CmdString):
        return "Not Supported"

    #----------  HPanel:GetController  ----------------------------
    # return the name of the controller, if Actual == False then return the
    # controller name that the software has been instructed to use if overridden
    # in the conf file
    def GetController(self, Actual = True):

        return self.GetParameterString(RegisterEnum.CONTROLLER_NAME_START, RegisterEnum.CONTROLLER_NAME_END)

    #----------  HPanel:ComminicationsIsActive  -------------------
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

        #if self.Simulation:
        #    return False
        return True

    #---------------------HPanel::GetPowerOutput-------------------
    # returns current kW
    # rerturn empty string ("") if not supported,
    # return kW with units i.e. "2.45kW"
    def GetPowerOutput(self, ReturnFloat = False):

        return self.GetParameter(RegisterEnum.TOTAL_POWER_KW, "kW", ReturnFloat = ReturnFloat)

    #----------  HPanel:GetCommStatus  ----------------------------
    # return Dict with communication stats
    def GetCommStatus(self):
        return self.ModBus.GetCommStats()

    #------------ HPanel:GetBaseStatus ----------------------------
    # return one of the following: "ALARM", "SERVICEDUE", "EXERCISING", "RUNNING",
    # "RUNNING-MANUAL", "OFF", "MANUAL", "READY"
    def GetBaseStatus(self):
        try:
            if self.SystemInAlarm():
                return "ALARM"
            elif self.GetParameterBit(RegisterEnum.OUTPUT_7, Output7.NEED_SERVICE):
                return "SERVICEDUE"
            elif self.GetParameterBit(RegisterEnum.OUTPUT_7, Output7.INT_EXERCISE_ACT):
                return "EXERCISING"
            elif self.GetParameterBit(RegisterEnum.OUTPUT_1, Output1.GEN_RUNNING) and self.GetSwitchState().lower() == "auto":
                return "RUNNING"
            elif self.GetParameterBit(RegisterEnum.OUTPUT_1, Output1.GEN_RUNNING) and self.GetSwitchState().lower() == "manual":
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

    #------------ HPanel:GetOneLineStatus -------------------------
    # returns a one line status for example : switch state and engine state
    def GetOneLineStatus(self):
        return self.GetSwitchState() + " : " + self.GetEngineState()
