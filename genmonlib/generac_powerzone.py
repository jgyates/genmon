#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: generac_powerzone.py
# PURPOSE: Controller Specific Detils for Generac Power Zone controller
#
#  AUTHOR: Jason G Yates
#    DATE: 13-Feb-2021
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import collections
import datetime
import threading

from genmonlib.controller import GeneratorController
from genmonlib.modbus_file import ModbusFile
from genmonlib.mymodbus import ModbusProtocol
from genmonlib.mytile import MyTile

# Module defines ---------------------------------------------------------------
REGISTER = 0
LENGTH = 1
RET_STRING = 2

"""
EVENT_LOG                       = "0c01"
EVENT_LOG_2                     = "0c02"
EVENT_LOG_3                     = "0c03"
EVENT_LOG_4                     = "0c04"
EVENT_LOG_5                     = "0c05"
EVENT_LOG_LENGTH                = 64 #342
ALARM_LOG                       = "0123"
ALARM_LOG_2                     = "0124"
ALARM_LOG_3                     = "0125"
ALARM_LOG_4                     = "0127"
ALARM_LOG_5                     = "0127"
ALARM_LOG_LENGTH                = 64 # 340
"""

# These are the same or H-Panel and G-Panel
EVENT_LOG_START = 0x0C01
EVENT_LOG_ENTRIES = 5
EVENT_LOG_LENGTH = 64
# These are the same or H-Panel and G-Panel
ALARM_LOG_START = 0x0123
ALARM_LOG_ENTRIES = 5
ALARM_LOG_LENGTH = 64

# ---------------------PowerZoneReg::PowerZoneReg--------------------------------
class PowerZoneReg(object):
    # Remote Annunciator Status
    RA_STATUS_0 = ["0000", 2]
    RA_STATUS_1 = ["0001", 2]
    RA_STATUS_2 = ["0002", 2]
    RA_STATUS_3 = ["0003", 2]
    RA_STATUS_4 = ["0004", 2]
    RA_STATUS_5 = ["0005", 2]
    RA_STATUS_6 = ["0006", 2]
    RA_STATUS_7 = ["0007", 2]
    RA_STATUS_8 = ["0008", 2]
    RA_STATUS_9 = ["0009", 2]

    # Digital Input Results Bitmap
    DI_RESULTS_0 = ["006a", 2]
    DI_RESULTS_0 = ["006B", 2]

    # Digital Output Function Bitmap
    DOF_RESULTS_0 = ["0070", 2]
    DOF_RESULTS_1 = ["0071", 2]
    DOF_RESULTS_2 = ["0072", 2]

    # RTC
    GEN_TIME_HR_MIN = ["015d", 2]  # RTC Hours Hi (0-23)/ Minutes Low (0-59)
    GEN_TIME_SEC_DYWK = [
        "015e",
        2,
    ]  # RTC Seconds Hi (0-59)/ Day of Week (Sunday = 0, 0 - 6) Low
    GEN_TIME_MONTH_DAY = ["015f", 2]  # RTC Month (1-12) / Day of Month (1-31)
    GEN_TIME_YR = ["0160", 2]  # RTC Year (xxxx)

    # Alarm Command / Alarm Globals
    # ALARM_GLOBAL_CMD        = ["0161", 2]           # Alarm Globals Command
    ALARM_GLOBALS = ["0162", 2]  # Alarm Globals
    # Alarm Globals Values
    # 1 : Acknowledge All
    # 4 : Clear Alarm
    # 6 : Reset All Alarms
    # 8 : Silence Horn
    # Engine
    ENGINE_HOUR_NOW = ["0163", 4]  # Engine Hours Now, Divide by 10
    ENGINE_STATUS = ["0165", 2]  # Engine Status
    # 0 : ENGINE_STOPPED_OFF
    # 1 : ENGINE_RUNNING_MANUAL
    # 2 : ENGINE_RUNNING_REMOTE_START
    # 3 : ENGINE_RUNNING_COMMS_START
    # 4 : ENGINE_RUNNING_EXERCISE_WO_XFER
    # 5 : ENGINE_RUNNING_UTILITY_START
    # 6 : ENGINE_RUNNING_EXERCISE_W_XFER
    # 7 : ENGINE_RUNNING_UTILITY_LOSS
    # 8 : ENGINE_STOPPED_AUTO
    # 9 : ENGINE_RUNNING_MPS_START
    # 10 : ENGINE_RUNNING_EXERCISE_LO_SPD
    # 11 : ENGINE_RUNNING_EXT_SW_START
    GENERATOR_STATUS = ["0166", 2]
    # 0 : RESET_ENGINE
    # 1 : STOPPED
    # 2 : WAIT_TO_CRANK
    # 3 : STARTING_ENGINE
    # 4 : STARTING_WAIT_TO_START
    # 5 : STARTING_PAUSE
    # 6 : RUNNING_UP
    # 7 : WARMING_ENGINE
    # 8 : WARMED_NOT_ACTIVE
    # 9 : WARMING_ACTIVE
    # 10 : ALARMS_ARE_ACTIVE
    # 11 : COOL_DOWN
    # 12 : STOPPING_ENGINE
    # 13 : ALARM_STOPPING_ENGINE
    # 14 : ALARM_STOPPED_ENGINE
    # 15 : NOT_RESPONDING
    GEN_CURRENT_PHASE_ROTATION = ["0171", 4]  # Generator Current Phase Rotation
    GEN_VOLTAGE_PHASE_ROTATION = ["0173", 4]  # Generator Voltage Phase Rotation
    QUIET_TEST_REQUEST = ["019a", 2]  # Quiet Test Request and Status
    ENGINE_KW_HOURS = ["019b", 8]  # Engine Kw Hours, Divide by 10
    O2_SENSOR = ["01a2", 2]  # O2 Sensor , Divide by 10
    GOVERNOR_POSITION = ["01a4", 2]  # Govonor Position, Divide by 10
    ALARM_GLOBAL_FLAGS = ["01b5", 2]  # Alarm Globals Flag
    # Low Byte Bit Field
    # Flag 1 Bit Mask= 0x0001..Flag 5 Bit Mask= 0x0010
    # Flag 1: Shutdown Alarm
    # Flag 2: Alarm
    # Flag 3: Warning
    # Flag 4: DTC
    # Flag 5: Horn is on
    KEY_SWITCH_STATE = ["01b6", 2]  # Key Switch Postion
    # 1 = Off
    # 2 = Manual
    # 4 = Auto

    KEYSWITCH_OVERRIDE = ["0170", 2]

    BATTERY_CHARGER_CURRENT = ["01b7", 2]  # Divide by 100
    BATTERY_VOLTAGE = ["01b8", 2]  # Divide by 100
    BUS_AVERAGE_CURRENT = ["01b9", 2]  # Divide by 10
    BUS_AVERAGE_VOLTAGE_LL = ["01bb", 2]  # Divide by 10
    BUS_N_CURRENT = ["01c3", 2]  # Divide by 10
    BUS_FREQUENCY = ["01c5", 2]  # Divide by 10
    BUS_VOLT_PHASE_A_B = ["01cd", 2]  # Divide by 10
    BUS_VOLT_PHASE_A_N = ["01ce", 2]  # Divide by 10
    BUS_VOLT_PHASE_B_C = ["01cf", 2]  # Divide by 10
    BUS_VOLT_PHASE_B_N = ["01d0", 2]  # Divide by 10
    BUS_VOLT_PHASE_C_A = ["01d1", 2]  # Divide by 10
    BUS_VOLT_PHASE_C_N = ["01d2", 2]  # Divide by 10
    COOLANT_LEVEL = ["01d3", 2]  # Divide by 10 (Percent)
    COOLANT_TEMP = ["01d4", 2]  # Degrees F
    GEN_PHASE_A_CURRENT = ["01d5", 4]  # Divide by 10
    GEN_PHASE_B_CURRENT = ["01d7", 4]  # Divide by 10
    GEN_PHASE_C_CURRENT = ["01d9", 4]  # Divide by 10
    DEF_LEVEL = ["01dd", 2]  # Divide by 10
    FUEL_LEVEL = ["01e0", 2]  # Divide by 10
    FUEL_PRESSURE = ["01e1", 2]  # Divide by 10
    GEN_AVERAGE_CURRENT = ["01e2", 2]  # Divide by 10
    GEN_AVERAGE_VOLTAGE_LL = ["01e4", 2]  # Divide by 10
    GEN_AVERAGE_VOLTAGE_LN = ["01e5", 2]  # Divide by 10
    OUTPUT_FREQUENCY = ["01e6", 2]  # Divide by 10
    TURBO_BOOST_PRESSURE = ["01e7", 2]  # psi
    INTAKE_AIR_TEMPERATURE = ["01e8", 2]  # Degrees F
    GEN_TOTAL_KVA = ["01e9", 4]  # Divide by 1000
    GEN_TOTAL_KVAR = ["01eb", 4]  # Divide by 1000
    KW_HOURS = ["01ed", 4]  # Divide by 10
    GEN_LAST_KWHR = ["01ef", 4]  # Divide by 10
    LAST_RUN_HOURS = ["01f1", 2]  # Divide by 10
    OIL_LEVEL = ["01f2", 2]  # Percentage
    OIL_PRESSURE = ["01f3", 2]  # psi
    OIL_TEMP = ["01f4", 2]  # Degrees F
    MIN_MAINT_REMAIN = ["01f5", 2]  # Minimum percentage Maintenance Remaining
    MIN_MAINT_LIFE = ["01f6", 4]  # Life left for minimum maintenance percent
    MIN_MAINT_TYPE = ["01f8", 2]  # maintenance type for minimum maintenance percent
    INTAKE_MANIFOLD_AIR_TEMPERATURE = [
        "01fe",
        2,
    ]  # Life left for minimum maintenance percent

    TOTAL_POWER_KW = ["0203", 4]
    GEN_TOTAL_POWER_FACTOR = ["0205", 4]
    OUTPUT_RPM = ["0206", 4]
    ENGINE_HOURS_NOW = ["020a", 4]  # Divide by 10
    SYSTEM_STATUS = ["020c", 2]
    GEN_VOLT_PHASE_A_B = ["020d", 2]  # Divide by 10
    GEN_VOLT_PHASE_A_N = ["020e", 2]  # Divide by 10
    GEN_VOLT_PHASE_B_C = ["020f", 2]  # Divide by 10
    GEN_VOLT_PHASE_B_N = ["0210", 2]  # Divide by 10
    GEN_VOLT_PHASE_C_A = ["0211", 2]  # Divide by 10
    GEN_VOLT_PHASE_C_N = ["0212", 2]  # Divide by 10
    BATTERY_TEMPERATURE = ["0214", 2]  # Divide by 10
    SYNC_ANGLE = ["0215", 2]
    MPS_CAPACITY = ["0216", 2]  # Divide by 100
    ALARM_LOG_IDX = ["0218", 2]
    EVENT_LOG_IDX = ["0219", 2]
    SWITCH_CLOSED = ["02c1", 2]  # High Byte = Gen Switch, Low Byte Bus Switch
    REMOTE_START = ["02c4", 2]  # 0 : Stop, 1 : Start

    # Analog Inputs
    GEN_VOLTAGE_AN = ["007d", 2]  # Divide by 10
    GEN_VOLTAGE_BN = ["007f", 2]  # Divide by 10
    GEN_VOLTAGE_CN = ["0081", 2]  # Divide by 10
    GEN_VOLTAGE_LN_AVG = ["0083", 2]  # Divide by 10
    BUS_VOLTAGE_AN = ["0085", 2]  # Divide by 10
    BUS_VOLTAGE_BN = ["0087", 2]  # Divide by 10
    BUS_VOLTAGE_CN = ["0089", 2]  # Divide by 10
    BUS_VOLTAGE_LN_AVG = ["008B", 2]  # Divide by 10
    GEN_VOLTAGE_AB = ["008d", 2]  # Divide by 10
    GEN_VOLTAGE_BC = ["008f", 2]  # Divide by 10
    GEN_VOLTAGE_CA = ["0091", 2]  # Divide by 10
    GEN_VOLTAGE_LL_AVG = ["0093", 2]  # Divide by 10
    BUS_VOLTAGE_AB = ["0095", 2]  # Divide by 10
    BUS_VOLTAGE_BC = ["0097", 2]  # Divide by 10
    BUS_VOLTAGE_CA = ["0099", 2]  # Divide by 10
    BUS_VOLTAGE_LL_AVG = ["009b", 2]  # Divide by 10
    GEN_CURRENT_A = ["009d", 2]  # Divide by 10
    GEN_CURRENT_B = ["009f", 2]  # Divide by 10
    GEN_CURRENT_C = ["00a1", 2]  # Divide by 10
    GEN_CURRENT_AVG = ["00a3", 2]  # Divide by 10
    GEN_CURRENT_N = ["00a5", 2]  # Divide by 10
    BUS_CURRENT_A = ["00a7", 2]  # Divide by 10
    BUS_CURRENT_B = ["00a9", 2]  # Divide by 10
    BUS_CURRENT_C = ["00ab", 2]  # Divide by 10
    BUS_CURRENT_AVG = ["00ad", 2]  # Divide by 10
    BUS_CURRENT_N = ["00af", 2]  # Divide by 10
    GEN_APPARENT_PWR_LL_TOTAL = ["00b1", 2]
    GEN_REAL_PWR_KW_LL_TOTAL = ["00b3", 2]
    GEN_REAL_PWR_WATTS_LL_TOTAL = ["00b5", 2]
    GEN_REACTIVE_PWR_LL_TOTAL = ["00b7", 2]
    GEN_PF_LL_AVG = ["00b9", 2]
    BUS_APPARENT_PWR_LL_TOTAL = ["00bb", 2]
    BUS_REAL_PWR_KW_LL_TOTAL = ["00bd", 2]
    BUS_REAL_PWR_WATTS_LL_TOTAL = ["00bf", 2]
    BUS_REACTIVE_PWR_LL_TOTAL = ["00c1", 2]
    BUS_PF_LL_AVG = ["00c3", 2]
    AVR_FIELD_CURRENT_AVR_SCR_DELAY_ANGLE = ["00c5", 2]  # Divide by 100
    AVR_EXCITATION_VOLTAGE_FREQUENCY = ["00c7", 2]
    GEN_FREQ_LL = ["00c9", 2]  # Divide by 10
    BUS_FREQ_LL = ["00cb", 2]  # Divide by 10
    RPM_1 = ["00cd", 2]
    BATT_VOLTAGE = ["00cf", 2]  # Divide by 100
    BATT_CHARGER_CURRENT_1 = ["00d1", 2]  # Divide by 100
    OIL_TEMP_1 = ["00d3", 2]
    OIL_PRESS_1 = ["00d5", 2]
    OIL_PRESS_2 = ["00d7", 2]
    COOLANT_TEMP_1 = ["00d9", 2]
    COOLANT_TEMP_2 = ["00db", 2]
    COOLANT_LEVEL_ENGINE_1 = ["00dd", 2]  # Divide by 10
    GOVERNOR_THROTTLE_POSITION_1 = ["00df", 2]  # Divide by 10
    AIR_FUEL_RATIO_DUTY_CYCLE_1 = ["00e1", 2]
    PRE_CAT_O2_SENSOR_1 = ["00e3", 2]  # Divide by 10
    INTAKE_MANIFOLD_AIR_TEMP_1 = ["00e5", 2]
    AVR_VOLTAGE_BIAS = ["00e7", 2]
    GOV_SPEED_BIAS = ["00e9", 2]
    ENGINE_PERCENT_LOAD_AT_SPEED = ["00eb", 2]
    ENGINE_DESIRED_SPEED = ["00ed", 2]
    BOOST_PRESS_POST_TURBO_1 = ["00ef", 2]
    ENGINE_FUEL_DELIVERY_PRESSURE = ["00f1", 2]
    DIESEL_FUEL_TEMP = ["00f3", 2]
    DIESEL_FUEL_FLOW_RATE = ["00f5", 2]
    DIESEL_FUEL_LEVEL_1 = ["00f7", 2]
    MIXER_POSITION = ["00f9", 2]
    INTAKE_AIR_PRESSURE_DELTA_FILTER_1 = ["00fb", 2]
    INTAKE_AIR_PRESSURE = ["00fd", 2]

    # EXT_SW_XX regististers are for HTS/MTS/STS Switches
    EXT_SW_GENERAL_STATUS = ["0241", 2]  # External Switch General Status
    EXT_SW_MINIC_DIAGRAM = ["0242", 2]  # Ext Switch Mimic Diagram
    EXT_SW_TARGET_VOLTAGE = ["0247", 2]  # External Switch Target Voltage
    EXT_SW_TARGET_FREQ = ["024a", 2]  # External Switch Target Freq
    EXT_SW_UTILITY_VOLTS_AB = ["024d", 2]  # External Switch Utility AB Voltage
    EXT_SW_UTILITY_VOLTS_BC = ["024e", 2]  # External Switch Utility BC Voltage
    EXT_SW_UTILITY_VOLTS_CA = ["024f", 2]  # External Switch Utility CA Voltage
    EXT_SW_UTILITY_AMPS_A = ["0250", 2]  # External Switch Utility A Amps
    EXT_SW_UTILITY_AMPS_B = ["0251", 2]  # External Switch Utility B Amps
    EXT_SW_UTILITY_AMPS_C = ["0252", 2]  # External Switch Utility C Amps
    EXT_SW_UTILITY_AVG_VOLTS = ["0254", 2]  # External Switch Average Utility Volts
    EXT_SW_UTILITY_AVG_AMPS = ["0255", 2]  # External Switch Average Utility Amps
    EXT_SW_UTILITY_FREQ = ["0256", 2]  # External Switch Utility Freq
    EXT_SW_UTILITY_PF = ["0257", 2]  # External Switch Utility Power Factor
    EXT_SW_UTILITY_KW = ["0258", 2]  # External Switch Utility Power
    EXT_SW_GEN_AVG_VOLT = ["0259", 2]  # External Switch Generator Average Voltage
    EXT_SW_GEN_FREQ = ["025a", 2]  # External Switch Generator Freq
    EXT_SW_BACKUP_BATT_VOLTS = ["025c", 2]  # External Switch Backup Battery Voltage
    EXT_SW_VERSION = ["025f", 2]  # External Switch SW Version
    EXT_SW_SELECTED = ["0260", 2]  # External Switch Selected

    # ---------------------PowerZoneReg::hexsort---------------------------------
    # @staticmethod
    def hexsort(self, e):
        try:
            return int(e[REGISTER], 16)
        except:
            return 0

    # @staticmethod
    # ---------------------PowerZoneReg::GetRegList------------------------------
    def GetRegList(self):
        RetList = []
        for attr, value in PowerZoneReg.__dict__.items():
            if not callable(getattr(self, attr)) and not attr.startswith("__"):
                RetList.append(value)

        RetList.sort(key=self.hexsort)
        return RetList


# ---------------------------PowerZoneIO:PowerZoneIO-----------------------------
class PowerZoneIO(object):

    Inputs = {
        # DI Results
        ("006a", 0x8000): "Switch In Auto",
        ("006a", 0x4000): "Switch In Manual",
        ("006a", 0x2000): "NG Low Gas Pressure Switch / Ruptured Basin",
        ("006a", 0x1000): "Emergency Stop 1",
        ("006a", 0x0800): "Remote Stop 1",
        ("006a", 0x0400): "Battery Charger Fault 1",
        ("006a", 0x0200): "Transfer Line Power",
        ("006a", 0x0100): "Transfer Generator Power",
        ("006a", 0x0200): "Bias Sync Active",
        ("006a", 0x0100): "Bias Share Active",
        ("006a", 0x0080): "User Config 01",
        ("006a", 0x0080): "NULL Function",
        ("006a", 0x0040): "User Config 02",
        ("006a", 0x0040): "NULL Function/LS AVR Alarm",
        ("006a", 0x0020): "User Config 05",
        ("006a", 0x0020): "Inhibit Deadbus Connect",
        ("006a", 0x0010): "User Config 06",
        ("006a", 0x0010): "Exercise",
        ("006a", 0x0008): "User Config 07",
        ("006a", 0x0008): "Generator Switch Status",
        ("006a", 0x0004): "User Config 08",
        ("006a", 0x0004): "Utility Switch Status",
        ("006a", 0x0002): "SEL Trip",
        ("006a", 0x0001): "MCB Status 1",
        ("006b", 0x8000): "Phase Rotation Fault",
        ("006b", 0x4000): "Transfer Line Power",
        ("006b", 0x2000): "Transfer Gen Power",
        ("006b", 0x1000): "User Config 01",
        ("006b", 0x0800): "User Config 02",
    }
    Outputs = {
        # RA Outputs
        # ("0008", 0x0100) : "Line Power",
        ("0005", 0x0001): "Not In Auto",
        ("0002", 0x0100): "Generator Running",
        # ("0007", 0x0001) : "Generator Power",
        # DOF Resutls
        ("0070", 0x8000): "COMMON DTC",
        ("0070", 0x4000): "COMMON WARNING",
        ("0070", 0x2000): "COMMON ALARM",
        ("0070", 0x1000): "COMMON SHUTDOWN",
        ("0070", 0x0800): "FAULT RELAY ACTIVE",
        ("0070", 0x0400): "GEN STOPPING DUE TO ALARM",
        ("0070", 0x0200): "GEN STOPPED DUE TO ALARM",
        ("0070", 0x0100): "GEN IN AUTO",
        ("0070", 0x0080): "GEN IN MAN",
        ("0070", 0x0040): "GEN IN OFF",
        ("0070", 0x0020): "GEN STOPPED READY TO RUN",
        ("0070", 0x0010): "GEN STOPPED",
        ("0070", 0x0008): "GEN PREHEAT ACTIVE",
        ("0070", 0x0004): "GEN CRANKING",
        ("0070", 0x0002): "GEN RUNNING",
        ("0070", 0x0001): "GEN RUNNING IN EXERCISE",
        ("0071", 0x8000): "GEN RUNNING IN QUIETTEST",
        ("0071", 0x4000): "GEN IN WARMUP",
        ("0071", 0x2000): "GEN READY TO ACCEPT LOAD",
        ("0071", 0x1000): "GEN SYNCHING TO BUS/UTILITY",
        ("0071", 0x0800): "GEN HOLDOFF ALARMS ENABLED",
        ("0071", 0x0400): "GEN IN COOLDOWN",
        ("0071", 0x0200): "LINE POWER",
        ("0071", 0x0100): "GENERATOR POWER",
        ("0071", 0x0080): "RAP LOW OIL PRESSURE WARNING",
        ("0071", 0x0040): "RAP LOW OIL PRESSURE ALARM",
        ("0071", 0x0020): "RAP HIGH COOLANT TEMPERATURE WARNING",
        ("0071", 0x0010): "RAP HIGH COOLANT TEMPERATURE ALARM",
        ("0071", 0x0008): "RAP LOW COOLANT TEMPERATURE WARNING",
        ("0071", 0x0004): "RAP LOW BATTERY VOLTAGE WARNING",
        ("0071", 0x0002): "RAP HIGH BATTERY VOLTAGE WARNING",
        ("0071", 0x0001): "RAP LOW FUEL WARNING",
        ("0072", 0x8000): "RAP FAIL TO START ALARM",
        ("0072", 0x4000): "RAP COOLANT LEVEL ALARM",
        ("0072", 0x2000): "RAP BATTERY CHARGE FAIL ALARM",
        ("0072", 0x1000): "ANNUNCIATOR SPARE LIGHT",
        ("0072", 0x0800): "GFI FAULT",
    }
    Alarms = {
        # Remote Annunciator
        ("0000", 0x0001): "Coolant Temp High Alarm",
        ("0000", 0x0100): "Oil Pressure Low Alarm",
        ("0001", 0x0001): "Fuel Level Low Alarm",
        ("0001", 0x0100): "Coolant Temp Low Alarm",
        ("0002", 0x0001): "Battery Charge Fail Alarm",
        ("0003", 0x0001): "Battery Volts High Alarm",
        ("0003", 0x0100): "Battery Volts Low Alarm",
        ("0004", 0x0001): "Coolant Temp Shutdown Alarm",
        ("0004", 0x0100): "Oil Pressure Shutdown Alarm",
        ("0005", 0x0100): "Emergency Stop Shutdown Alarm",
        ("0006", 0x0001): "Fail Start Shutdown Alarm",
        ("0006", 0x0100): "RPM Sense Shutdown Alarm",
        ("0007", 0x0100): "RPM Shutdown Alarm",
    }


# ---------------------------RegisterStringEnum:RegisterStringEnum---------------
class RegisterStringEnum(object):

    # Note, the first value is the register (in hex string), the second is the numbert of bytes
    # third is if the result is stored as a string
    PRODUCT_VERSION_DATE = ["000a", 192, False]
    MAINT_LIFE_REMAINING = ["0167", 18, False]
    CURRENT_ALARM_LOG = ["058f", 202, False]

    # ---------------------RegisterStringEnum::hexsort---------------------------
    @staticmethod
    def hexsort(e):
        try:
            return int(e[REGISTER], 16)
        except:
            return 0

    # ---------------------RegisterStringEnum::GetRegList------------------------
    @staticmethod
    def GetRegList():
        RetList = []
        for attr, value in RegisterStringEnum.__dict__.items():
            if not callable(
                getattr(RegisterStringEnum(), attr)
            ) and not attr.startswith("__"):
                RetList.append(value)
        RetList.sort(key=RegisterStringEnum.hexsort)
        return RetList


# ---------------------------RegisterFileEnum:RegisterFileEnum-------------------
class RegisterFileEnum(object):

    # Note, the first value is the register (in hex string), the second is the numbert of bytes
    # third is if the result is stored as a string

    # Nameplate, Serial Number, etc
    SN_DATA_FILE_RECORD = ["0112", 64]
    ALT_SN_DATA_FILE_RECORD = ["0113", 64]
    MODEL_FILE_RECORD = ["0114", 64]
    PRODUCTION_DATE_COUNTRY_FILE_RECORD = ["0115", 64]
    NP_SPECS_1_FILE_RECORD = ["0116", 64]
    NP_SPECS_2_FILE_RECORD = ["0117", 64]
    NP_SPECS_3_FILE_RECORD = ["0118", 64]

    GOV_DATA_FILE_RECORD = ["01a4", 56]
    REGULATOR_FILE_RECORD = ["01a6", 44]
    ENGINE_DATA_FILE_RECORD = ["0122", 64]
    MISC_GEN_FILE_RECORD = ["0109", 14]

    # ---------------------RegisterFileEnum::hexsort---------------------------
    @staticmethod
    def hexsort(e):
        try:
            return int(e[REGISTER], 16)
        except:
            return 0

    # ---------------------RegisterFileEnum::GetRegList------------------------
    @staticmethod
    def GetRegList():
        RetList = []
        for attr, value in RegisterFileEnum.__dict__.items():
            if not callable(getattr(RegisterFileEnum(), attr)) and not attr.startswith(
                "__"
            ):
                RetList.append(value)
        RetList.sort(key=RegisterFileEnum.hexsort)
        return RetList


class PowerZone(GeneratorController):

    # ---------------------PowerZone::__init__--------------------------------------
    def __init__(
        self,
        log,
        newinstall=False,
        simulation=False,
        simulationfile=None,
        message=None,
        feedback=None,
        config=None,
    ):

        # call parent constructor
        super(PowerZone, self).__init__(
            log,
            newinstall=newinstall,
            simulation=simulation,
            simulationfile=simulationfile,
            message=message,
            feedback=feedback,
            config=config,
        )

        self.LastEngineState = ""
        self.CurrentAlarmState = False
        self.VoltageConfig = None
        self.AlarmAccessLock = (
            threading.RLock()
        )  # lock to synchronize access to the logs
        self.EventAccessLock = (
            threading.RLock()
        )  # lock to synchronize access to the logs
        self.ControllerDetected = False
        self.Reg = PowerZoneReg()
        self.IO = PowerZoneIO()

        self.DaysOfWeek = {
            0: "Sunday",  # decode for register values with day of week
            1: "Monday",
            2: "Tuesday",
            3: "Wednesday",
            4: "Thursday",
            5: "Friday",
            6: "Saturday",
        }
        self.MonthsOfYear = {
            1: "January",  # decode for register values with month
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
            12: "December",
        }

        self.SetupClass()

    # -------------PowerZone:SetupClass------------------------------------------
    def SetupClass(self):

        # read config file
        try:
            if not self.GetConfig():
                self.FatalError("Failure in Controller GetConfig")
                return None
        except Exception as e1:
            self.FatalError("Error reading config file: " + str(e1))
            return None
        try:
            # Starting device connection
            if self.Simulation:
                self.ModBus = ModbusFile(
                    self.UpdateRegisterList,
                    inputfile=self.SimulationFile,
                    config=self.config,
                )
            else:
                self.ModBus = ModbusProtocol(
                    self.UpdateRegisterList, config=self.config
                )

            self.ModBus.AlternateFileProtocol = True
            self.Threads = self.MergeDicts(self.Threads, self.ModBus.Threads)
            self.LastRxPacketCount = self.ModBus.RxPacketCount

            self.StartCommonThreads()

        except Exception as e1:
            self.FatalError("Error opening modbus device: " + str(e1))
            return None

    # ---------------------PowerZone::GetConfig----------------------------------
    # read conf file, used internally, not called by genmon
    # return True on success, else False
    def GetConfig(self):

        try:
            self.VoltageConfig = self.config.ReadValue(
                "voltageconfiguration", default="277/480"
            )
            self.NominalBatteryVolts = int(
                self.config.ReadValue("nominalbattery", return_type=int, default=24)
            )
            self.HTSTransferSwitch = self.config.ReadValue(
                "hts_transfer_switch", return_type=bool, default=False
            )
            self.FuelUnits = self.config.ReadValue("fuel_units", default="gal")
            self.FuelHalfRate = self.config.ReadValue(
                "half_rate", return_type=float, default=0.0
            )
            self.FuelFullRate = self.config.ReadValue(
                "full_rate", return_type=float, default=0.0
            )
            self.UseFuelSensor = self.config.ReadValue(
                "usesensorforfuelgauge", return_type=bool, default=True
            )
            self.UseCalculatedPower = self.config.ReadValue(
                "usecalculatedpower", return_type=bool, default=False
            )

        except Exception as e1:
            self.FatalError(
                "Missing config file or config file entries (PowerZone): " + str(e1)
            )
            return False

        return True

    # -------------PowerZone:IdentifyController----------------------------------
    def IdentifyController(self):

        try:

            if self.ControllerDetected:
                return True
            # TODO Validate a way to detect controller and powerzone standard vs pro model
            self.ControllerDetected = True
            return True
        except Exception as e1:
            self.LogErrorLine("Error in IdentifyController: " + str(e1))
            return False

    # -------------PowerZone:InitDevice------------------------------------------
    # One time reads, and read all registers once
    def InitDevice(self):

        try:
            self.IdentifyController()
            self.MasterEmulation()
            """
            Register = "%04x" % EVENT_LOG_START
            Data = []
            Data.append(0x00)
            Data.append(0x13)
            self.ModBus.ProcessFileWriteTransaction(Register, len(Data) / 2, Data)
            """
            self.CheckModelSpecificInfo()
            self.SetupTiles()
            self.InitComplete = True
            self.InitCompleteEvent.set()
        except Exception as e1:
            self.LogErrorLine("Error in InitDevice: " + str(e1))

    # -------------PowerZone:SetupTiles------------------------------------------
    def SetupTiles(self):
        try:
            with self.ExternalDataLock:
                self.TileList = []
                Tile = MyTile(
                    self.log,
                    title="Battery Voltage",
                    units="V",
                    type="batteryvolts",
                    nominal=self.NominalBatteryVolts,
                    callback=self.GetParameter,
                    callbackparameters=(
                        self.Reg.BATTERY_VOLTAGE[REGISTER],
                        None,
                        100.0,
                        False,
                        False,
                        True,
                    ),
                )
                self.TileList.append(Tile)

                # Nominal Voltage for gauge
                if self.VoltageConfig != None:
                    # Valid settings are: 120/208, 120/240, 230/400, 240/415, 277/480, 347/600
                    VoltageConfigList = self.VoltageConfig.split("/")
                    NominalVoltage = int(VoltageConfigList[1])
                else:
                    NominalVoltage = 600

                if (
                    self.NominalKW == None
                    or self.NominalKW == ""
                    or self.NominalKW == "Unknown"
                ):
                    self.NominalKW = "550"

                Tile = MyTile(
                    self.log,
                    title="Voltage (Avg)",
                    units="V",
                    type="linevolts",
                    nominal=NominalVoltage,
                    callback=self.GetParameter,
                    callbackparameters=(
                        self.Reg.GEN_AVERAGE_VOLTAGE_LL[REGISTER],
                        None,
                        10.0,
                        False,
                        True,
                        False,
                    ),
                )
                self.TileList.append(Tile)

                NominalCurrent = float(self.NominalKW) * 1000 / NominalVoltage
                Tile = MyTile(
                    self.log,
                    title="Current (Avg)",
                    units="A",
                    type="current",
                    nominal=NominalCurrent,
                    callback=self.GetParameter,
                    callbackparameters=(
                        self.Reg.GEN_AVERAGE_CURRENT[REGISTER],
                        None,
                        10.0,
                        False,
                        True,
                        False,
                    ),
                )
                self.TileList.append(Tile)

                if (
                    self.NominalFreq == None
                    or self.NominalFreq == ""
                    or self.NominalFreq == "Unknown"
                ):
                    self.NominalFreq = "60"
                Tile = MyTile(
                    self.log,
                    title="Frequency",
                    units="Hz",
                    type="frequency",
                    nominal=int(self.NominalFreq),
                    callback=self.GetParameter,
                    callbackparameters=(
                        self.Reg.OUTPUT_FREQUENCY[REGISTER],
                        None,
                        10.0,
                        False,
                        False,
                        True,
                    ),
                )
                self.TileList.append(Tile)

                if (
                    self.NominalRPM == None
                    or self.NominalRPM == ""
                    or self.NominalRPM == "Unknown"
                ):
                    self.NominalRPM = "3600"
                Tile = MyTile(
                    self.log,
                    title="RPM",
                    type="rpm",
                    nominal=int(self.NominalRPM),
                    callback=self.GetParameter,
                    callbackparameters=(
                        self.Reg.OUTPUT_RPM[REGISTER],
                        None,
                        None,
                        False,
                        True,
                        False,
                    ),
                )
                self.TileList.append(Tile)

                # water temp between 170 and 200 is a normal range for a gen. most have a 180f thermostat
                Tile = MyTile(
                    self.log,
                    title="Coolant Temp",
                    units="F",
                    type="temperature",
                    subtype="coolant",
                    nominal=180,
                    maximum=300,
                    callback=self.GetParameter,
                    callbackparameters=(
                        self.Reg.COOLANT_TEMP[REGISTER],
                        None,
                        None,
                        False,
                        True,
                        False,
                    ),
                )
                self.TileList.append(Tile)

                if self.PowerMeterIsSupported():
                    Tile = MyTile(
                        self.log,
                        title="Power Output",
                        units="kW",
                        type="power",
                        nominal=float(self.NominalKW),
                        callback=self.GetParameter,
                        callbackparameters=(
                            self.Reg.TOTAL_POWER_KW[REGISTER],
                            None,
                            1000,       # Divider 1000?
                            False,
                            True,
                            False,
                        ),
                    )
                    self.TileList.append(Tile)

                    Tile = MyTile(
                        self.log,
                        title="kW Output",
                        type="powergraph",
                        nominal=float(self.NominalKW),
                        callback=self.GetParameter,
                        callbackparameters=(
                            self.Reg.TOTAL_POWER_KW[REGISTER],
                            None,
                            1000,       # Divider 1000?
                            False,
                            True,
                            False,
                        ),
                    )
                    self.TileList.append(Tile)

                self.SetupCommonTiles()
        except Exception as e1:
            self.LogErrorLine("Error in SetupTiles: " + str(e1))

    # -------------PowerZone:CheckModelSpecificInfo------------------------------
    # check for model specific info in read from conf file, if not there then add some defaults
    def CheckModelSpecificInfo(self):

        try:
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

            if (
                self.Model == "Unknown"
                or not len(self.Model)
                or "generic" in self.Model.lower()
            ):
                # TODO
                self.Model = "Generac Power Zone Industrial Generator"
                self.config.WriteValue("model", self.Model)

            if self.FuelType == "Unknown" or not len(self.FuelType):
                self.FuelType = "Diesel"
                self.config.WriteValue("fueltype", self.FuelType)
        except Exception as e1:
            self.LogErrorLine("Error in CheckModelSpecificInfo: " + str(e1))
        return

    # -------------PowerZone:GetGeneratorFileData--------------------------------
    def GetGeneratorFileData(self):

        try:
            for RegisterList in RegisterFileEnum.GetRegList():
                try:
                    if self.IsStopping:
                        return
                    localTimeoutCount = self.ModBus.ComTimoutError
                    localSyncError = self.ModBus.ComSyncError
                    self.ModBus.ProcessFileReadTransaction(
                        RegisterList[REGISTER], RegisterList[LENGTH] / 2
                    )
                    if (
                        localSyncError != self.ModBus.ComSyncError
                        or localTimeoutCount != self.ModBus.ComTimoutError
                    ) and self.ModBus.RxPacketCount:
                        self.WaitAndPergeforTimeout()

                except Exception as e1:
                    self.LogErrorLine("Error in GetGeneratorFileData (1): " + str(e1))

            self.GetGeneratorLogFileData()
        except Exception as e1:
            self.LogErrorLine("Error in GetGeneratorFileData: (2)" + str(e1))

    # ------------ PowerZone:WaitAndPergeforTimeout -----------------------------
    def WaitAndPergeforTimeout(self):
        # if we get here a timeout occured, and we have recieved at least one good packet
        # this logic is to keep from receiving a packet that we have already requested once we
        # timeout and start to request another
        # Wait for a bit to allow any missed response from the controller to arrive
        # otherwise this could get us out of sync
        # This assumes MasterEmulation is called from ProcessThread
        if self.WaitForExit(
            "ProcessThread", float(self.ModBus.ModBusPacketTimoutMS / 1000.0)
        ):  #
            return
        self.ModBus.Flush()

    # ------------ PowerZone:GetGeneratorLogFileData ----------------------------
    def GetGeneratorLogFileData(self):

        try:

            for RegValue in range(
                EVENT_LOG_START + EVENT_LOG_ENTRIES - 1, EVENT_LOG_START - 1, -1
            ):
                Register = "%04x" % RegValue
                localTimeoutCount = self.ModBus.ComTimoutError
                localSyncError = self.ModBus.ComSyncError
                self.ModBus.ProcessFileReadTransaction(Register, EVENT_LOG_LENGTH / 2)
                if (
                    localSyncError != self.ModBus.ComSyncError
                    or localTimeoutCount != self.ModBus.ComTimoutError
                ) and self.ModBus.RxPacketCount:
                    self.WaitAndPergeforTimeout()

            for RegValue in range(
                ALARM_LOG_START + ALARM_LOG_ENTRIES - 1, ALARM_LOG_START - 1, -1
            ):
                Register = "%04x" % RegValue
                localTimeoutCount = self.ModBus.ComTimoutError
                localSyncError = self.ModBus.ComSyncError
                self.ModBus.ProcessFileReadTransaction(Register, ALARM_LOG_LENGTH / 2)
                if (
                    localSyncError != self.ModBus.ComSyncError
                    or localTimeoutCount != self.ModBus.ComTimoutError
                ) and self.ModBus.RxPacketCount:
                    self.WaitAndPergeforTimeout()

        except Exception as e1:
            self.LogErrorLine("Error in GetGeneratorLogFileData: " + str(e1))

    # -------------HPanel:GetGeneratorStrings------------------------------------
    def GetGeneratorStrings(self):

        try:
            for RegisterList in RegisterStringEnum.GetRegList():
                try:
                    if self.IsStopping:
                        return
                    localTimeoutCount = self.ModBus.ComTimoutError
                    localSyncError = self.ModBus.ComSyncError
                    self.ModBus.ProcessTransaction(
                        RegisterList[REGISTER], RegisterList[LENGTH] / 2
                    )
                    if (
                        localSyncError != self.ModBus.ComSyncError
                        or localTimeoutCount != self.ModBus.ComTimoutError
                    ) and self.ModBus.RxPacketCount:
                        self.WaitAndPergeforTimeout()

                except Exception as e1:
                    self.LogErrorLine("Error in GetGeneratorStrings: " + str(e1))

        except Exception as e1:
            self.LogErrorLine("Error in GetGeneratorStrings: " + str(e1))

    # -------------PowerZone:MasterEmulation-------------------------------------
    def MasterEmulation(self):

        try:
            if not self.ControllerDetected:
                self.IdentifyController()
                if not self.ControllerDetected:
                    return
            for RegisterList in self.Reg.GetRegList():
                try:
                    if self.IsStopping:
                        return
                    localTimeoutCount = self.ModBus.ComTimoutError
                    localSyncError = self.ModBus.ComSyncError
                    self.ModBus.ProcessTransaction(
                        RegisterList[REGISTER], RegisterList[LENGTH] / 2
                    )
                    if (
                        localSyncError != self.ModBus.ComSyncError
                        or localTimeoutCount != self.ModBus.ComTimoutError
                    ) and self.ModBus.RxPacketCount:
                        self.WaitAndPergeforTimeout()
                except Exception as e1:
                    self.LogErrorLine("Error in MasterEmulation: " + str(e1))

            self.GetGeneratorStrings()
            self.GetGeneratorFileData()
            self.CheckForAlarmEvent.set()
        except Exception as e1:
            self.LogErrorLine("Error in MasterEmulation: " + str(e1))

    # ------------ PowerZone:GetTransferStatus ----------------------------------
    def GetTransferStatus(self):

        LineState = "Unknown"
        # TODO

        return LineState

    # ------------ PowerZone:GetCondition ---------------------------------------
    def GetCondition(self, RegList=None, type=None):

        try:
            if type == None or RegList == None:
                return []
            if type.lower() == "alarms":
                Lookup = self.IO.Alarms
            elif type.lower() == "inputs":
                Lookup = self.IO.Inputs
            elif type.lower() == "outputs":
                Lookup = self.IO.Outputs
            else:
                self.LogError(
                    "Error in GetCondition: Invalid input for type: " + str(type)
                )
                return []

            StringList = []
            for Register in RegList:
                Output = self.GetParameter(Register, ReturnInt=True)
                Mask = 1
                while Output:
                    if Output & 0x01:
                        Value = Lookup.get((Register, Mask), None)
                        if not Value == None:
                            StringList.append(Value)
                    Mask <<= 1
                    Output >>= 1

            return StringList
        except Exception as e1:
            self.LogErrorLine("Error in GetCondition: " + str(e1))
            return []

    # ------------ PowerZone:ParseLogEntry --------------------------------------
    def ParseLogEntry(self, Entry, Type=None):

        try:
            if Type == None:
                return ""

            if not len(Entry):
                return ""

            if Type == "event":
                """
                description_1: bytes: 1, offset: 4
                comparison: bytes: 1, offset: 4, bitmask: 224
                message_type: bytes: 1, offset: 5, bitmask: 192
                description_2: bytes: 1, offset: 5

                """
                channel = self.GetIntFromString(Entry, 0, 2)
                if channel == 0xFFFF:
                    # no entry
                    return ""
                functionCode = self.GetIntFromString(Entry, 2, 2)
                description_1 = self.GetIntFromString(Entry, 4, 1)
                description_2 = self.GetIntFromString(Entry, 5, 1)
                hour = self.GetIntFromString(Entry, 6, 1)
                min = self.GetIntFromString(Entry, 7, 1)
                milli = self.GetIntFromString(Entry, 8, 2)
                month = self.GetIntFromString(Entry, 10, 1)
                date = self.GetIntFromString(Entry, 11, 1)
                year = self.GetIntFromString(Entry, 12, 1)
                triggerValue = self.GetIntFromString(Entry, 14, 4)
                Entry = "Channel: " + str(channel)
                Entry += " Function Code: " + str(functionCode)
                Entry += " description 1: " + str(description_1)
                Entry += " description 2: " + str(description_2)
                Entry += " " + str(month) + "/" + str(date) + "/" + str(year)
                Entry += " " + str(hour) + ":" + str(min) + ":" + str(milli)
                Entry += " " + str(triggerValue)
            if Type == "alarm":
                """
                description_1: bytes: 1, offset: 4
                setPointType: bytes: 1, offset: 4, bitmask: 128
                fault_type: bytes: 1, offset: 4, bitmask: 96
                dtc:  bytes: 1, offset: 4, bitmask: 16
                fault_number:  bytes: 1, offset: 4, bitmask: 14
                message_type:  bytes: 1, offset: 5, bitmask: 192
                description_2:  bytes: 1, offset: 5

                """
                channel = self.GetIntFromString(Entry, 0, 2)
                if channel == 0xFFFF:
                    # no entry
                    return ""
                functionCode = self.GetIntFromString(Entry, 2, 2)
                description_1 = self.GetIntFromString(Entry, 4, 1)
                description_2 = self.GetIntFromString(Entry, 5, 1)
                hour = self.GetIntFromString(Entry, 6, 1)
                min = self.GetIntFromString(Entry, 7, 1)
                milli = self.GetIntFromString(Entry, 8, 2)
                month = self.GetIntFromString(Entry, 10, 1)
                date = self.GetIntFromString(Entry, 11, 1)
                year = self.GetIntFromString(Entry, 12, 1)
            return Entry
        except Exception as e1:
            self.LogErrorLine("Error in ParseLogEntry: " + str(e1))
            return ""

    # ------------ PowerZone:CheckForAlarms -------------------------------------
    def CheckForAlarms(self):

        try:
            status_included = False
            if not self.InitComplete:
                return
            # Check for changes in engine state
            EngineState = self.GetEngineState()
            msgbody = ""

            if len(self.UserURL):
                msgbody += "For additional information : " + self.UserURL + "\n"
            if not EngineState == self.LastEngineState:
                self.LastEngineState = EngineState
                msgsubject = "Generator Notice: " + self.SiteName
                if not self.SystemInAlarm():
                    msgbody += "NOTE: This message is a notice that the state of the generator has changed. The system is not in alarm.\n"
                    MessageType = "info"
                else:
                    MessageType = "warn"
                msgbody += self.DisplayStatus()
                status_included = True
                self.MessagePipe.SendMessage(msgsubject, msgbody, msgtype=MessageType)

            # Check for Alarms
            if self.SystemInAlarm():
                if not self.CurrentAlarmState:
                    msgsubject = "Generator Notice: ALARM Active at " + self.SiteName
                    if not status_included:
                        msgbody += self.DisplayStatus()
                    self.MessagePipe.SendMessage(msgsubject, msgbody, msgtype="warn")
            else:
                if self.CurrentAlarmState:
                    msgsubject = "Generator Notice: ALARM Clear at " + self.SiteName
                    if not status_included:
                        msgbody += self.DisplayStatus()
                    self.MessagePipe.SendMessage(msgsubject, msgbody, msgtype="warn")

            self.CurrentAlarmState = self.SystemInAlarm()

        except Exception as e1:
            self.LogErrorLine("Error in CheckForAlarms: " + str(e1))

        return

    # ------------ PowerZone:RegisterIsFileRecord -------------------------------
    def RegisterIsFileRecord(self, Register, Value):

        try:

            FileList = RegisterFileEnum.GetRegList()
            for FileReg in FileList:
                if Register.lower() == FileReg[REGISTER].lower():
                    return True

            RegInt = int(Register, 16)

            if RegInt >= ALARM_LOG_START and RegInt <= (
                ALARM_LOG_START + ALARM_LOG_ENTRIES
            ):
                return True
            if RegInt >= EVENT_LOG_START and RegInt <= (
                EVENT_LOG_START + EVENT_LOG_ENTRIES
            ):
                return True

        except Exception as e1:
            self.LogErrorLine("Error in RegisterIsFileRecord: " + str(e1))

        return False

    # ------------ HPanel:RegisterIsStringRegister ------------------------------
    def RegisterIsStringRegister(self, Register):

        try:
            StringList = RegisterStringEnum.GetRegList()
            for StringReg in StringList:
                if Register.lower() == StringReg[REGISTER].lower():
                    return True
        except Exception as e1:
            self.LogErrorLine("Error in RegisterIsBaseRegister: " + str(e1))
        return False

    # ------------ PowerZone:RegisterIsBaseRegister -----------------------------
    def RegisterIsBaseRegister(self, Register, Value, validate_length=False):

        try:
            found = False
            RegisterList = self.Reg.GetRegList()
            for ListReg in RegisterList:
                if Register.lower() == ListReg[REGISTER].lower():
                    if validate_length:
                        if len(Value) != (ListReg[LENGTH] * 2):
                            return False
                    return True

        except Exception as e1:
            self.LogErrorLine("Error in RegisterIsBaseRegister: " + str(e1))
        return False

    # ------------ PowerZone:UpdateRegisterList ---------------------------------
    def UpdateRegisterList(self, Register, Value, IsString=False, IsFile=False, IsCoil = False, IsInput = False):

        try:
            if len(Register) != 4:
                self.LogError(
                    "Validation Error: Invalid register value in UpdateRegisterList: %s %s"
                    % (Register, Value)
                )
                return False

            if not IsFile and self.RegisterIsBaseRegister(
                Register, Value, validate_length=True
            ):
                self.Holding[Register] = Value
            elif not IsFile and self.RegisterIsStringRegister(Register):
                # TODO validate register string length
                self.Strings[Register] = Value
            elif IsFile and self.RegisterIsFileRecord(Register, Value):
                # todo validate file data length
                self.FileData[Register] = Value
            else:
                self.LogError(
                    "Error in UpdateRegisterList: Unknown Register "
                    + Register
                    + ":"
                    + Value
                    + ": IsFile: "
                    + str(IsFile)
                    + ": "
                    + "IsString: "
                    + str(IsString)
                )
                return False
            return True
        except Exception as e1:
            self.LogErrorLine("Error in UpdateRegisterList: " + str(e1))
            return False

    # ---------------------PowerZone::SystemInAlarm------------------------------
    # return True if generator is in alarm, else False
    def SystemInAlarm(self):

        try:
            status = self.GetGeneratorStatus()
            if "alarm" in status.lower():
                return True

            AlarmFlags = self.GetParameter(
                self.Reg.ALARM_GLOBAL_FLAGS[REGISTER], ReturnInt=True
            )
            if AlarmFlags & 0x07:
                # Flag 1: Shutdown Alarm
                # Flag 2: Alarm
                # Flag 3: Warning
                # Flag 4: DTC
                # Flag 5: Horn is on
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in SystemInAlarm: " + str(e1))
            return False

    # ------------ PowerZone:GetSwitchState -------------------------------------
    def GetSwitchState(self):

        try:
            SwitchState = self.GetParameter(
                self.Reg.KEY_SWITCH_STATE[REGISTER], ReturnInt=True
            )
            # 1 = Off
            # 2 = Manual
            # 4 = Auto
            # 8 = Remote Start
            if SwitchState == 2:
                return "Manual"
            elif SwitchState == 4:
                return "Auto"
            elif SwitchState == 1:
                return "Off"
            elif SwitchState == 8:
                return "Remote Start"
            else:
                return "Unknown"
        except Exception as e1:
            self.LogErrorLine("Error in GetSwitchState: " + str(e1))
            return "Unknown"

    # ------------ PowerZone:GetGeneratorStatus ---------------------------------
    def GetGeneratorStatus(self):

        try:
            State = self.GetParameter(
                self.Reg.GENERATOR_STATUS[REGISTER], ReturnInt=True
            )

            # 0 : RESET_ENGINE
            # 1 : STOPPED
            # 2 : WAIT_TO_CRANK
            # 3 : STARTING_ENGINE
            # 4 : STARTING_WAIT_TO_START
            # 5 : STARTING_PAUSE
            # 6 : RUNNING_UP
            # 7 : WARMING_ENGINE
            # 8 : WARMED_NOT_ACTIVE
            # 9 : WARMING_ACTIVE
            # 10 : ALARMS_ARE_ACTIVE
            # 11 : COOL_DOWN
            # 12 : STOPPING_ENGINE
            # 13 : ALARM_STOPPING_ENGINE
            # 14 : ALARM_STOPPED_ENGINE
            # 15 : NOT_RESPONDING
            if State == 0:
                return "Reset Engine"
            elif State == 1:
                return "Stopped"
            elif State == 2:
                return "Waiting to Crank"
            elif State == 3:
                return "Starting Engine"
            elif State == 4:
                return "Starting Wait to Start"
            elif State == 5:
                return "Starting Pause"
            elif State == 6:
                return "Running Up"
            elif State == 7:
                return "Warming Engine"
            elif State == 8:
                return "Warmed Not Active"
            elif State == 9:
                return "Warming Active"
            elif State == 10:
                return "Alarms are Active"
            elif State == 11:
                return "Cooling Down"
            elif State == 12:
                return "Stopping Engine"
            elif State == 13:
                return "Alarm Stopping Engine"
            elif State == 14:
                return "Alarm Stopped Engine"
            elif State == 15:
                return "Not Responding"
            else:
                return "Unknown"
        except Exception as e1:
            self.LogErrorLine("Error in GetGeneratorStatus: " + str(e1))
            return "Unknown"

    # ------------ PowerZone:GetEngineState -------------------------------------
    def GetEngineState(self):

        try:
            State = self.GetParameter(self.Reg.ENGINE_STATUS[REGISTER], ReturnInt=True)

            # 0 : ENGINE_STOPPED_OFF
            # 1 : ENGINE_RUNNING_MANUAL
            # 2 : ENGINE_RUNNING_REMOTE_START
            # 3 : ENGINE_RUNNING_COMMS_START
            # 4 : ENGINE_RUNNING_EXERCISE_WO_XFER
            # 5 : ENGINE_RUNNING_UTILITY_START
            # 6 : ENGINE_RUNNING_EXERCISE_W_XFER
            # 7 : ENGINE_RUNNING_UTILITY_LOSS
            # 8 : ENGINE_STOPPED_AUTO
            # 9 : ENGINE_RUNNING_MPS_START
            # 10 : ENGINE_RUNNING_EXERCISE_LO_SPD
            # 11 : ENGINE_RUNNING_EXT_SW_START

            if State == 0:
                return "Engine Stopped, Off"
            elif State == 1:
                return "Engine Running Manual"
            elif State == 2:
                return "Engine Running Remote Start"
            elif State == 3:
                return "Engine Running Comms Start"
            elif State == 4:
                return "Engine Running Exercise Without Transfer"
            elif State == 5:
                return "Engine Running Utility Start"
            elif State == 6:
                return "Engine Running Exercise With Transfer"
            elif State == 7:
                return "Engine Running Utlity Loss"
            elif State == 8:
                return "Engine Stopped Auto"
            elif State == 9:
                return "Engine Running MPS Start"
            elif State == 10:
                return "Engine Running Exercise LO SPD"
            elif State == 11:
                return "Engine Running External Switch Start"
            else:
                return "Unknown"
        except Exception as e1:
            self.LogErrorLine("Error in GetEngineState: " + str(e1))
            return "Unknown"

    # ------------ PowerZone:GetDateTime ----------------------------------------
    def GetDateTime(self):

        ErrorReturn = "Unknown"
        try:
            Value = self.GetParameter(self.Reg.GEN_TIME_HR_MIN[REGISTER])
            if not len(Value):
                return ErrorReturn

            TempInt = int(Value)
            Hour = TempInt >> 8
            Minute = TempInt & 0x00FF
            if Hour > 23 or Minute >= 60:
                self.LogError(
                    "Error in GetDateTime: Invalid Hour or Minute: "
                    + str(Hour)
                    + ", "
                    + str(Minute)
                )
                return ErrorReturn

            Value = self.GetParameter(self.Reg.GEN_TIME_SEC_DYWK[REGISTER])
            if not len(Value):
                return ErrorReturn
            TempInt = int(Value)
            Second = TempInt >> 8
            DayOfWeek = TempInt & 0x00FF
            if Second >= 60 or DayOfWeek > 7:
                self.LogError(
                    "Error in GetDateTime: Invalid Seconds or Day of Week: "
                    + str(Second)
                    + ", "
                    + str(DayOfWeek)
                )
                return ErrorReturn

            Value = self.GetParameter(self.Reg.GEN_TIME_MONTH_DAY[REGISTER])
            if not len(Value):
                return ErrorReturn
            TempInt = int(Value)
            Month = TempInt >> 8
            DayOfMonth = TempInt & 0x00FF
            if Month > 12 or Month == 0 or DayOfMonth == 0 or DayOfMonth > 31:
                self.LogError(
                    "Error in GetDateTime: Invalid Month or Day of Month: "
                    + str(Month)
                    + ", "
                    + str(DayOfMonth)
                )
                return ErrorReturn

            Value = self.GetParameter(self.Reg.GEN_TIME_YR[REGISTER])
            if not len(Value):
                return ErrorReturn
            TempInt = int(Value)
            Year = TempInt >> 8

            FullDate = (
                self.DaysOfWeek.get(DayOfWeek, "INVALID")
                + " "
                + self.MonthsOfYear.get(Month, "INVALID")
            )
            FullDate += " " + str(DayOfMonth) + ", " + "20" + str(Year) + " "
            FullDate += "%02d:%02d:%02d" % (Hour, Minute, Second)
            return FullDate

        except Exception as e1:
            self.LogErrorLine("Error in GetDateTime: " + str(e1))
            return ErrorReturn

    # ------------ PowerZone::GetTimeFromString ---------------------------------
    def GetTimeFromString(self, input_string):

        try:
            # Format is: 00 31 52 d8 02 15 10 18
            if len(input_string) < 16:
                return "Unknown"

            OutString = ""
            Date = "%02d/%02d/%02d" % (
                self.GetIntFromString(input_string, 6, 1, decimal=True),
                self.GetIntFromString(input_string, 5, 1, decimal=True),
                self.GetIntFromString(input_string, 7, 1, decimal=True),
            )

            AMorPM = self.GetIntFromString(input_string, 3, 1)

            if AMorPM == 0xD1:
                # PM
                Hour = self.GetIntFromString(input_string, 4, 1, decimal=True) + 12
            else:
                Hour = self.GetIntFromString(input_string, 4, 1, decimal=True)

            Time = "%02d:%02d:%02d" % (
                Hour,
                self.GetIntFromString(input_string, 2, 1, decimal=True),
                self.GetIntFromString(input_string, 1, 1, decimal=True),
            )

            return Date + " " + Time
        except Exception as e1:
            self.LogErrorLine("Error in GetTimeFromString: " + str(e1))
            return "Unknown"

    # ------------ PowerZone::GetStartInfo --------------------------------------
    # return a dictionary with startup info for the gui
    def GetStartInfo(self, NoTile=False):

        try:
            StartInfo = {}

            self.GetGeneratorSettings()
            StartInfo["fueltype"] = self.FuelType
            StartInfo["model"] = self.Model
            StartInfo["nominalKW"] = self.NominalKW
            StartInfo["nominalRPM"] = self.NominalRPM
            StartInfo["nominalfrequency"] = self.NominalFreq
            StartInfo["phase"] = self.Phase
            StartInfo["PowerGraph"] = self.PowerMeterIsSupported()
            StartInfo["NominalBatteryVolts"] = self.NominalBatteryVolts
            StartInfo["FuelCalculation"] = self.FuelTankCalculationSupported()
            StartInfo["FuelSensor"] = self.FuelSensorSupported()
            StartInfo["FuelConsumption"] = self.FuelConsumptionSupported()
            StartInfo["Controller"] = self.GetController()
            StartInfo["UtilityVoltage"] = False
            StartInfo["RemoteCommands"] = True  # Remote Start/ Stop/ StartTransfer
            StartInfo["ResetAlarms"] = False
            StartInfo["AckAlarms"] = True
            StartInfo["RemoteTransfer"] = self.HTSTransferSwitch  # Remote start and transfer command
            StartInfo["RemoteButtons"] = False  # Remote controll of Off/Auto/Manual
            StartInfo["ExerciseControls"] = False  # self.SmartSwitch
            StartInfo["WriteQuietMode"] = True
            StartInfo["SetGenTime"] = True
            if self.Platform != None:
                StartInfo["Linux"] = self.Platform.IsOSLinux()
                StartInfo["RaspberryPi"] = self.Platform.IsPlatformRaspberryPi()

            if not NoTile:

                StartInfo["buttons"] = []

                StartInfo["pages"] = {
                    "status": True,
                    "maint": True,
                    "outage": False,
                    "logs": False,
                    "monitor": True,
                    "maintlog": True,
                    "notifications": True,
                    "settings": True,
                    "addons": True,
                    "about": True,
                }

                StartInfo["tiles"] = []
                for Tile in self.TileList:
                    StartInfo["tiles"].append(Tile.GetStartInfo())

        except Exception as e1:
            self.LogErrorLine("Error in GetStartInfo: " + str(e1))

        return StartInfo

    # ------------ PowerZone::GetStatusForGUI -----------------------------------
    # return dict for GUI
    def GetStatusForGUI(self):

        try:
            Status = {}

            Status["basestatus"] = self.GetBaseStatus()
            Status["switchstate"] = self.GetSwitchState()
            Status["enginestate"] = self.GetEngineState()
            Status["kwOutput"] = self.GetPowerOutput()
            Status["OutputVoltage"] = self.GetParameter(
                self.Reg.GEN_AVERAGE_VOLTAGE_LL[REGISTER], "V"
            )
            Status["BatteryVoltage"] = self.GetParameter(
                self.Reg.BATTERY_VOLTAGE[REGISTER], "V", 100.0
            )
            Status["UtilityVoltage"] = "0"
            Status["RPM"] = self.GetParameter(self.Reg.OUTPUT_RPM[REGISTER])
            Status["Frequency"] = self.GetParameter(
                self.Reg.OUTPUT_FREQUENCY[REGISTER], "Hz", 10.0
            )
            # Exercise Info is a dict containing the following:
            # TODO
            ExerciseInfo = collections.OrderedDict()
            ExerciseInfo["Enabled"] = False
            ExerciseInfo["Frequency"] = "Weekly"  # Biweekly, Weekly or Monthly
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

    # ---------------------PowerZone::DisplayLogs--------------------------------
    def DisplayLogs(self, AllLogs=False, DictOut=False, RawOutput=False):

        RetValue = collections.OrderedDict()
        LogList = []
        RetValue["Logs"] = LogList
        UnknownFound = False

        # # TODO:

        try:
            # if DictOut is True, return a dictionary with a list of Dictionaries (one for each log)
            # Each dict in the list is a log (alarm, start/stop). For Example:
            #
            #       Dict[Logs] = [ {"Alarm Log" : [Log Entry1, LogEntry2, ...]},
            #                      {"Run Log" : [Log Entry3, Log Entry 4, ...]}...]
            LocalEvent = []
            LogRawData = ""
            for RegValue in range(
                EVENT_LOG_START, EVENT_LOG_START + EVENT_LOG_ENTRIES - 1, +1
            ):
                Register = "%04x" % RegValue
                LogRawData += self.GetParameterFileValue(Register, ReturnString=False)

            if len(LogRawData) != 0:
                CurrentIndex = self.GetIntFromString(LogRawData, 0, 2)
                LogRawData = LogRawData[4:]
                EntrySize = 17 * 2
                RawEntry = ""
                for index in range(0, len(LogRawData), EntrySize):
                    if (index + EntrySize) <= len(LogRawData):
                        LogEntry = self.ParseLogEntry(
                            LogRawData[index : index + EntrySize], Type="event"
                        )
                        if not len(LogEntry):
                            continue
                        if "undefined" in LogEntry:
                            continue
                        LocalEvent.append(LogEntry)

            LocalAlarm = []

            LogRawData = ""
            for RegValue in range(
                ALARM_LOG_START, ALARM_LOG_START + ALARM_LOG_ENTRIES - 1, +1
            ):
                Register = "%04x" % RegValue
                LogRawData += self.GetParameterFileValue(Register, ReturnString=False)

            if len(LogRawData) != 0:
                CurrentIndex = self.GetIntFromString(LogRawData, 0, 2)
                LogRawData = LogRawData[4:]
                EntrySize = 17 * 2
                RawEntry = ""
                for index in range(0, len(LogRawData), EntrySize):
                    if (index + EntrySize) <= len(LogRawData):
                        LogEntry = self.ParseLogEntry(
                            LogRawData[index : index + EntrySize], Type="event"
                        )
                        if not len(LogEntry):
                            continue
                        if "undefined" in LogEntry:
                            continue
                        LocalEvent.append(LogEntry)

            LogList = [{"Alarm Log": LocalAlarm}, {"Run Log": LocalEvent}]

            RetValue["Logs"] = LogList

        except Exception as e1:
            self.LogErrorLine("Error in DisplayLogs: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(RetValue, ""))

        return RetValue

    # ------------ PowerZone::DisplayMaintenance --------------------------------
    def DisplayMaintenance(self, DictOut=False, JSONNum=False):

        try:
            # use ordered dict to maintain order of output
            # ordered dict to handle evo vs nexus functions
            Maintenance = collections.OrderedDict()
            Maintenance["Maintenance"] = []
            Nameplate = []
            Maintenance["Maintenance"].append({"Nameplate Data": Nameplate})
            # these offsets are doubled since we are dealing with Hex ASCII string
            MARK_32 = 32 * 2
            MARK_10 = 10 * 2
            MARK_20 = 20 * 2
            MARK_30 = 30 * 2
            MARK_40 = 40 * 2
            MARK_50 = 50 * 2
            NamePlateData = self.GetParameterFileValue(
                RegisterFileEnum.SN_DATA_FILE_RECORD[REGISTER], ReturnString=True
            )
            if len(NamePlateData):
                Nameplate.append({"Serial Number": NamePlateData})
            NamePlateData = self.GetParameterFileValue(
                RegisterFileEnum.ALT_SN_DATA_FILE_RECORD[REGISTER], ReturnString=True
            )
            if len(NamePlateData):
                Nameplate.append({"Alternate Number": NamePlateData})
            # the following nameplate entries return hex strings and will be converted to ASCII after parsing
            NamePlateData = self.GetParameterFileValue(
                RegisterFileEnum.MODEL_FILE_RECORD[REGISTER], ReturnString=False
            )
            if len(NamePlateData) >= MARK_32:
                Nameplate.append(
                    {"Generator Model": self.HexStringToString(NamePlateData[:MARK_32])}
                )
            if len(NamePlateData) >= RegisterFileEnum.MODEL_FILE_RECORD[LENGTH]:
                Nameplate.append(
                    {"Model": self.HexStringToString(NamePlateData[MARK_32:])}
                )
            NamePlateData = self.GetParameterFileValue(
                RegisterFileEnum.PRODUCTION_DATE_COUNTRY_FILE_RECORD[REGISTER],
                ReturnString=False,
            )
            if len(NamePlateData) >= MARK_32:
                Nameplate.append(
                    {"Production Date": self.HexStringToString(NamePlateData[:MARK_32])}
                )
            if (
                len(NamePlateData)
                >= RegisterFileEnum.PRODUCTION_DATE_COUNTRY_FILE_RECORD[LENGTH]
            ):
                Nameplate.append(
                    {
                        "Country of Origin": self.HexStringToString(
                            NamePlateData[MARK_32:]
                        )
                    }
                )
            NamePlateData = self.GetParameterFileValue(
                RegisterFileEnum.NP_SPECS_1_FILE_RECORD[REGISTER], ReturnString=False
            )
            if len(NamePlateData) >= MARK_10:
                Nameplate.append(
                    {"kW": self.HexStringToString(NamePlateData[:MARK_10])}
                )
            if len(NamePlateData) >= MARK_20:
                Nameplate.append(
                    {"kVA": self.HexStringToString(NamePlateData[MARK_10:MARK_20])}
                )
            if len(NamePlateData) >= MARK_30:
                Nameplate.append(
                    {"Hz": self.HexStringToString(NamePlateData[MARK_20:MARK_30])}
                )
            if len(NamePlateData) >= MARK_40:
                Nameplate.append(
                    {
                        "Power Factor": self.HexStringToString(
                            NamePlateData[MARK_30:MARK_40]
                        )
                    }
                )
            if len(NamePlateData) >= MARK_50:
                Nameplate.append(
                    {
                        "Upsize Alternate kW": self.HexStringToString(
                            NamePlateData[MARK_40:MARK_50]
                        )
                    }
                )
            NamePlateData = self.GetParameterFileValue(
                RegisterFileEnum.NP_SPECS_2_FILE_RECORD[REGISTER], ReturnString=False
            )
            if len(NamePlateData) >= MARK_10:
                Nameplate.append(
                    {
                        "Upsize Alternate kVA": self.HexStringToString(
                            NamePlateData[:MARK_10]
                        )
                    }
                )
            if len(NamePlateData) >= MARK_20:
                Nameplate.append(
                    {"Volts": self.HexStringToString(NamePlateData[MARK_10:MARK_20])}
                )
            if len(NamePlateData) >= MARK_30:
                Nameplate.append(
                    {"Amps": self.HexStringToString(NamePlateData[MARK_20:MARK_30])}
                )
            if len(NamePlateData) >= MARK_40:
                Nameplate.append(
                    {
                        "Engine RPM": self.HexStringToString(
                            NamePlateData[MARK_30:MARK_40]
                        )
                    }
                )
            if len(NamePlateData) >= MARK_50:
                Nameplate.append(
                    {
                        "Alternate RPM": self.HexStringToString(
                            NamePlateData[MARK_40:MARK_50]
                        )
                    }
                )
            NamePlateData = self.GetParameterFileValue(
                RegisterFileEnum.NP_SPECS_3_FILE_RECORD[REGISTER], ReturnString=False
            )
            if len(NamePlateData) >= MARK_10:
                Nameplate.append(
                    {"Breaker kW": self.HexStringToString(NamePlateData[:MARK_10])}
                )
            if len(NamePlateData) >= MARK_20:
                Nameplate.append(
                    {
                        "Breaker Amps": self.HexStringToString(
                            NamePlateData[MARK_10:MARK_20]
                        )
                    }
                )

            ProductVersion = self.GetParameterStringValue(
                RegisterStringEnum.PRODUCT_VERSION_DATE[REGISTER], ReturnString=True
            )
            if len(ProductVersion):
                Maintenance["Maintenance"].append({"Firmware": str(ProductVersion)})
            Maintenance["Maintenance"].append({"Model": self.Model})
            Maintenance["Maintenance"].append(
                {"Controller Detected": self.GetController()}
            )
            Maintenance["Maintenance"].append({"Nominal RPM": self.NominalRPM})
            Maintenance["Maintenance"].append({"Rated kW": self.NominalKW})
            Maintenance["Maintenance"].append({"Nominal Frequency": self.NominalFreq})
            Maintenance["Maintenance"].append({"Fuel Type": self.FuelType})

            Maintenance = self.DisplayMaintenanceCommon(Maintenance, JSONNum=JSONNum)

            if not self.SmartSwitch:
                pass
                Exercise = []
                # Maintenance["Maintenance"].append({"Exercise" : Exercise
                # Exercise["Exercise Time" : self.GetExerciseTime()
                # Exercise["Exercise Duration" : self.GetExerciseDuration()

            Maintenance["Maintenance"].append(
                {
                    "Maintenance Life Remaining": self.ValueOut(
                        self.GetParameter(
                            self.Reg.MIN_MAINT_REMAIN[REGISTER], ReturnInt=True
                        ),
                        "%",
                        JSONNum,
                    )
                }
            )
            Maintenance["Maintenance"].append(
                {"Maintenance Times": self.GetMaintTimes()}
            )
            Maintenance["Maintenance"].append(
                {"Generator Settings": self.GetGeneratorSettings()}
            )
            Maintenance["Maintenance"].append(
                {"Engine Settings": self.GetEngineSettings()}
            )
            Maintenance["Maintenance"].append(
                {"Governor Settings": self.GetGovernorSettings()}
            )
            Maintenance["Maintenance"].append(
                {"Regulator Settings": self.GetRegulatorSettings()}
            )

            Service = []
            Maintenance["Maintenance"].append({"Service": Service})

            Service.append({"Total Run Hours": self.GetRunHours()})

            IOStatus = []
            Maintenance["Maintenance"].append({"I/O Status": IOStatus})
            # TODO

            OutputList = [
                self.Reg.RA_STATUS_0[REGISTER],
                self.Reg.RA_STATUS_1[REGISTER],
                self.Reg.RA_STATUS_2[REGISTER],
                self.Reg.RA_STATUS_3[REGISTER],
                self.Reg.RA_STATUS_4[REGISTER],
                self.Reg.RA_STATUS_5[REGISTER],
                self.Reg.RA_STATUS_6[REGISTER],
                self.Reg.RA_STATUS_7[REGISTER],
                self.Reg.RA_STATUS_8[REGISTER],
                self.Reg.RA_STATUS_9[REGISTER],
            ]
            IOStatus.append(
                {"Inputs": self.GetCondition(RegList=OutputList, type="inputs")}
            )
            IOStatus.append(
                {"Outputs": self.GetCondition(RegList=OutputList, type="outputs")}
            )

        except Exception as e1:
            self.LogErrorLine("Error in DisplayMaintenance: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(Maintenance, ""))

        return Maintenance

    # ------------ PowerZone::DisplayStatus -------------------------------------
    def DisplayStatus(self, DictOut=False, JSONNum=False):

        try:
            Status = collections.OrderedDict()
            Status["Status"] = []

            Engine = []
            Alarms = []
            Battery = []
            Line = []
            Time = []

            Status["Status"].append({"Engine": Engine})
            Status["Status"].append({"Alarms": Alarms})
            Status["Status"].append({"Battery": Battery})
            if not self.SmartSwitch or self.HTSTransferSwitch:
                Status["Status"].append({"Line State": Line})

            Status = self.DisplayStatusCommon(Status, JSONNum=JSONNum)

            Status["Status"].append({"Time": Time})

            Battery.append(
                {
                    "Battery Voltage": self.ValueOut(
                        self.GetParameter(
                            self.Reg.BATTERY_VOLTAGE[REGISTER],
                            ReturnFloat=True,
                            Divider=100.0,
                        ),
                        "V",
                        JSONNum,
                    )
                }
            )
            Battery.append(
                {
                    "Battery Charger Current": self.ValueOut(
                        self.GetParameter(
                            self.Reg.BATTERY_CHARGER_CURRENT[REGISTER],
                            ReturnFloat=True,
                            Divider=100.0,
                        ),
                        "A",
                        JSONNum,
                    )
                }
            )

            Engine.append({"Engine State": self.GetEngineState()})
            Engine.append({"Generator Status": self.GetGeneratorStatus()})
            Engine.append({"Switch State": self.GetSwitchState()})
            Engine.append(
                {
                    "Output Power": self.ValueOut(
                        self.GetPowerOutput(ReturnFloat=True), "kW", JSONNum
                    )
                }
            )
            Engine.append(
                {
                    "Power Factor": self.ValueOut(
                        self.GetParameter(
                            self.Reg.GEN_PF_LL_AVG[REGISTER],
                            ReturnFloat=True,
                            Divider=100.0,
                        ),
                        "",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "RPM": self.ValueOut(
                        self.GetParameter(
                            self.Reg.OUTPUT_RPM[REGISTER], ReturnInt=True
                        ),
                        "",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "Frequency": self.ValueOut(
                        self.GetParameter(
                            self.Reg.OUTPUT_FREQUENCY[REGISTER],
                            ReturnFloat=True,
                            Divider=10.0,
                        ),
                        "Hz",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "Throttle Position": self.ValueOut(
                        self.GetParameter(
                            self.Reg.GOVERNOR_THROTTLE_POSITION_1[REGISTER],
                            ReturnFloat=True,
                            Divider=10.0,
                        ),
                        "Stp",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "Coolant Temp": self.ValueOut(
                        self.GetParameter(
                            self.Reg.COOLANT_TEMP[REGISTER], ReturnInt=True
                        ),
                        "F",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "Coolant Level": self.ValueOut(
                        self.GetParameter(
                            self.Reg.COOLANT_LEVEL[REGISTER],
                            ReturnFloat=True,
                            Divider=10.0,
                        ),
                        "Stp",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "Oil Pressure": self.ValueOut(
                        self.GetParameter(
                            self.Reg.OIL_PRESSURE[REGISTER], ReturnInt=True
                        ),
                        "psi",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "Oil Temp": self.ValueOut(
                        self.GetParameter(self.Reg.OIL_TEMP[REGISTER], ReturnInt=True),
                        "F",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "Fuel Level": self.ValueOut(
                        self.GetParameter(
                            self.Reg.FUEL_LEVEL[REGISTER],
                            ReturnFloat=True,
                            Divider=10.0,
                        ),
                        "",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "Fuel Pressure": self.ValueOut(
                        self.GetParameter(
                            self.Reg.FUEL_PRESSURE[REGISTER],
                            ReturnFloat=True,
                            Divider=10.0,
                        ),
                        "psi",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "Oxygen Sensor": self.ValueOut(
                        self.GetParameter(self.Reg.O2_SENSOR[REGISTER], ReturnInt=True),
                        "",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "Current Phase A": self.ValueOut(
                        self.GetParameter(
                            self.Reg.GEN_PHASE_A_CURRENT[REGISTER], ReturnFloat=True,
                                Divider=10.0,
                        ),
                        "A",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "Current Phase B": self.ValueOut(
                        self.GetParameter(
                            self.Reg.GEN_PHASE_B_CURRENT[REGISTER], ReturnFloat=True,
                                Divider=10.0,
                        ),
                        "A",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "Current Phase C": self.ValueOut(
                        self.GetParameter(
                            self.Reg.GEN_PHASE_C_CURRENT[REGISTER], ReturnFloat=True,
                                Divider=10.0,
                        ),
                        "A",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "Average Current": self.ValueOut(
                        self.GetParameter(
                            self.Reg.GEN_AVERAGE_CURRENT[REGISTER], ReturnFloat=True,
                                Divider=10.0,
                        ),
                        "A",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "Voltage A-B": self.ValueOut(
                        self.GetParameter(
                            self.Reg.GEN_VOLT_PHASE_A_B[REGISTER], ReturnFloat=True,
                                Divider=10.0,
                        ),
                        "V",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "Voltage B-C": self.ValueOut(
                        self.GetParameter(
                            self.Reg.GEN_VOLT_PHASE_B_C[REGISTER], ReturnFloat=True,
                                Divider=10.0,
                        ),
                        "V",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "Voltage C-A": self.ValueOut(
                        self.GetParameter(
                            self.Reg.GEN_VOLT_PHASE_C_A[REGISTER], ReturnFloat=True,
                                Divider=10.0,
                        ),
                        "V",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "Average Voltage": self.ValueOut(
                        self.GetParameter(
                            self.Reg.GEN_AVERAGE_VOLTAGE_LL[REGISTER], ReturnFloat=True,
                                Divider=10.0,
                        ),
                        "V",
                        JSONNum,
                    )
                }
            )
            Engine.append(
                {
                    "Air Fuel Duty Cycle": self.ValueOut(
                        self.GetParameter(
                            self.Reg.AIR_FUEL_RATIO_DUTY_CYCLE_1[REGISTER],
                            ReturnInt=True,
                        ),
                        "",
                        JSONNum,
                    )
                }
            )

            OutputList = [
                self.Reg.RA_STATUS_0[REGISTER],
                self.Reg.RA_STATUS_1[REGISTER],
                self.Reg.RA_STATUS_2[REGISTER],
                self.Reg.RA_STATUS_3[REGISTER],
                self.Reg.RA_STATUS_4[REGISTER],
                self.Reg.RA_STATUS_5[REGISTER],
                self.Reg.RA_STATUS_6[REGISTER],
                self.Reg.RA_STATUS_7[REGISTER],
                self.Reg.RA_STATUS_8[REGISTER],
                self.Reg.RA_STATUS_9[REGISTER],
            ]
            if self.SystemInAlarm():
                AlarmList = self.GetCondition(RegList=OutputList, type="alarms")
                if len(AlarmList):
                    Alarms.append({"Alarm List": AlarmList})

            if self.HTSTransferSwitch:
                Line.append(
                    {
                        "Target Utility Voltage": self.ValueOut(
                            self.GetParameter(
                                self.Reg.EXT_SW_TARGET_VOLTAGE[REGISTER], ReturnInt=True
                            ),
                            "V",
                            JSONNum,
                        )
                    }
                )
                Line.append(
                    {
                        "Target Utility Frequency": self.ValueOut(
                            self.GetParameter(
                                self.Reg.EXT_SW_TARGET_FREQ[REGISTER], ReturnInt=True
                            ),
                            "Hz",
                            JSONNum,
                        )
                    }
                )

                Line.append(
                    {
                        "Utility Frequency": self.ValueOut(
                            self.GetParameter(
                                self.Reg.EXT_SW_UTILITY_FREQ[REGISTER],
                                ReturnFloat=True,
                                Divider=100.0,
                            ),
                            "Hz",
                            JSONNum,
                        )
                    }
                )

                Line.append(
                    {
                        "Utility Voltage A-B": self.ValueOut(
                            self.GetParameter(
                                self.Reg.EXT_SW_UTILITY_VOLTS_AB[REGISTER],
                                ReturnInt=True,
                            ),
                            "V",
                            JSONNum,
                        )
                    }
                )
                Line.append(
                    {
                        "Utility Voltage B-C": self.ValueOut(
                            self.GetParameter(
                                self.Reg.EXT_SW_UTILITY_VOLTS_BC[REGISTER],
                                ReturnInt=True,
                            ),
                            "V",
                            JSONNum,
                        )
                    }
                )
                Line.append(
                    {
                        "Utility Voltage C-A": self.ValueOut(
                            self.GetParameter(
                                self.Reg.EXT_SW_UTILITY_VOLTS_CA[REGISTER],
                                ReturnInt=True,
                            ),
                            "V",
                            JSONNum,
                        )
                    }
                )
                Line.append(
                    {
                        "Average Utility Voltage": self.ValueOut(
                            self.GetParameter(
                                self.Reg.EXT_SW_UTILITY_AVG_VOLTS[REGISTER],
                                ReturnInt=True,
                            ),
                            "V",
                            JSONNum,
                        )
                    }
                )

                Line.append(
                    {
                        "Utility Current Phase A": self.ValueOut(
                            self.GetParameter(
                                self.Reg.EXT_SW_UTILITY_AMPS_A[REGISTER], ReturnInt=True
                            ),
                            "A",
                            JSONNum,
                        )
                    }
                )
                Line.append(
                    {
                        "Utility Current Phase B": self.ValueOut(
                            self.GetParameter(
                                self.Reg.EXT_SW_UTILITY_AMPS_B[REGISTER], ReturnInt=True
                            ),
                            "A",
                            JSONNum,
                        )
                    }
                )
                Line.append(
                    {
                        "Utility Current Phase C": self.ValueOut(
                            self.GetParameter(
                                self.Reg.EXT_SW_UTILITY_AMPS_C[REGISTER], ReturnInt=True
                            ),
                            "A",
                            JSONNum,
                        )
                    }
                )
                Line.append(
                    {
                        "Average Utility Current": self.ValueOut(
                            self.GetParameter(
                                self.Reg.EXT_SW_UTILITY_AVG_AMPS[REGISTER],
                                ReturnInt=True,
                            ),
                            "A",
                            JSONNum,
                        )
                    }
                )

                Line.append(
                    {
                        "Utility Power Factor": self.ValueOut(
                            self.GetParameter(
                                self.Reg.EXT_SW_UTILITY_PF[REGISTER],
                                ReturnFloat=True,
                                Divider=100.0,
                            ),
                            "",
                            JSONNum,
                        )
                    }
                )
                Line.append(
                    {
                        "Utility Power": self.ValueOut(
                            self.GetParameter(
                                self.Reg.EXT_SW_UTILITY_KW[REGISTER], ReturnInt=True
                            ),
                            "kW",
                            JSONNum,
                        )
                    }
                )

                Line.append(
                    {
                        "Switch Reported Generator Average Voltage": self.ValueOut(
                            self.GetParameter(
                                self.Reg.EXT_SW_GEN_AVG_VOLT[REGISTER], ReturnInt=True
                            ),
                            "V",
                            JSONNum,
                        )
                    }
                )
                Line.append(
                    {
                        "Switch Reported Generator Average Frequency": self.ValueOut(
                            self.GetParameter(
                                self.Reg.EXT_SW_GEN_FREQ[REGISTER],
                                ReturnFloat=True,
                                Divider=100.0,
                            ),
                            "Hz",
                            JSONNum,
                        )
                    }
                )

                Line.append(
                    {
                        "Backup Battery Volts": self.ValueOut(
                            self.GetParameter(
                                self.Reg.EXT_SW_BACKUP_BATT_VOLTS[REGISTER],
                                ReturnFloat=True,
                                Divider=100.0,
                            ),
                            "V",
                            JSONNum,
                        )
                    }
                )

                Line.append(
                    {
                        "Switch Software Version": self.ValueOut(
                            self.GetParameter(
                                self.Reg.EXT_SW_VERSION[REGISTER], ReturnInt=True
                            ),
                            "",
                            JSONNum,
                        )
                    }
                )
                Line.append(
                    {
                        "Switch Selected": self.ValueOut(
                            self.GetParameter(
                                self.Reg.EXT_SW_SELECTED[REGISTER], ReturnInt=True
                            ),
                            "",
                            JSONNum,
                        )
                    }
                )

            # Generator time
            Time.append(
                {
                    "Monitor Time": datetime.datetime.now().strftime(
                        "%A %B %-d, %Y %H:%M:%S"
                    )
                }
            )
            Time.append({"Generator Time": self.GetDateTime()})

        except Exception as e1:
            self.LogErrorLine("Error in DisplayStatus: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(Status, ""))

        return Status

    # ------------ GeneratorController:GetRegulatorSettings ---------------------
    def GetRegulatorSettings(self):

        RegSettings = []
        RegData = self.GetParameterFileValue(
            RegisterFileEnum.REGULATOR_FILE_RECORD[REGISTER]
        )

        if len(RegData) >= ((RegisterFileEnum.REGULATOR_FILE_RECORD[LENGTH] * 2)):
            try:
                RegSettings.append(
                    {"Voltage KP": str(self.GetIntFromString(RegData, 0, 2)) + " V"}
                )  # Byte 0 and 1
                RegSettings.append(
                    {"Voltage KI": str(self.GetIntFromString(RegData, 2, 2)) + " V"}
                )  # Byte 2 and 3
                RegSettings.append(
                    {"Voltage KD": str(self.GetIntFromString(RegData, 4, 2)) + " V"}
                )  # Byte 4 and 5
                RegSettings.append(
                    {"Volts Per Hz": str(self.GetIntFromString(RegData, 14, 2))}
                )  # Byte 14 and 15
                RegSettings.append(
                    {
                        "High Voltage Limit": str(self.GetIntFromString(RegData, 18, 2))
                        + " V"
                    }
                )  # Byte 18 and 19
                RegSettings.append(
                    {
                        "Low Voltage Limit": str(self.GetIntFromString(RegData, 20, 2))
                        + " V"
                    }
                )  # Byte 20 and 21
                RegSettings.append(
                    {
                        "Target Volts": str(
                            (self.GetIntFromString(RegData, 6, 2) / 10.0)
                        )
                        + " V"
                    }
                )  # Byte 6 and 7
                RegSettings.append(
                    {"VF Corner 1": str(self.GetIntFromString(RegData, 10, 2)) + " Hz"}
                )  # Byte 10 and 11
                RegSettings.append(
                    {"VF Corner 2": str(self.GetIntFromString(RegData, 12, 2)) + " Hz"}
                )  # Byte 12 and 13
                RegSettings.append(
                    {"Rated Power": str(self.GetIntFromString(RegData, 26, 2)) + "kW"}
                )  # Byte 26 and 27
                PowerFactor = self.GetIntFromString(RegData, 24, 2)  # Byte 24 and 25
                RegSettings.append({"Power Factor": "%.2f" % (PowerFactor / 100)})
                RegSettings.append(
                    {"kW Demand": str(self.GetIntFromString(RegData, 22, 2)) + " kW"}
                )  # Byte 22 and 23
                RegSettings.append(
                    {"Panel Type": str(self.GetIntFromString(RegData, 28, 2))}
                )  # Byte 28 and 29
                # RegSettings.append({"Exciter Frequency Ratio" : str(self.GetIntFromString(RegData, 44, 1))})   # Byte 44

            except Exception as e1:
                self.LogErrorLine("Error parsing regulator settings: " + str(e1))
        return RegSettings

    # ------------ GeneratorController:GetGovernorSettings ----------------------
    def GetGovernorSettings(self):

        GovSettings = []

        GovData = self.GetParameterFileValue(
            RegisterFileEnum.GOV_DATA_FILE_RECORD[REGISTER]
        )
        if len(GovData) >= ((RegisterFileEnum.GOV_DATA_FILE_RECORD[LENGTH] * 2)):
            try:
                # GovSettings.append({"Standby KP" : str(self.GetIntFromString(GovData, 0, 2))})                        # Byte 0 and 1
                # GovSettings.append({"Standby KI" : str(self.GetIntFromString(GovData, 2, 2))})                        # Byte 2 and 3
                # GovSettings.append({"Standby KD" : str(self.GetIntFromString(GovData, 4, 2))})                        # Byte 4 and 5
                # GovSettings.append({"Actuator Start Position" : str(self.GetIntFromString(GovData, 20, 2))})          # Byte 20 and 21
                # GovSettings.append({"Offset" : str(self.GetIntFromString(GovData, 22, 2))})                           # Byte 22 and 23
                # GovSettings.append({"Full Scale" : str(self.GetIntFromString(GovData, 24, 2))})                       # Byte 24 and 25
                GovSettings.append(
                    {
                        "Soft Start Frequency": str(
                            self.GetIntFromString(GovData, 26, 2)
                        )
                        + " Hz"
                    }
                )  # Byte 26 and 26
                # GovSettings.append({"Engine Linearization" : str(self.GetIntFromString(GovData, 28, 2))})             # Byte 28 and 29

                # GovSettings.append({"Use Diesel Algorithms" : "Yes" if self.GetIntFromString(GovData, 12, 2) else "No"})   # Byte 12 - 13
                GovFreq = self.GetIntFromString(GovData, 14, 2)  # Byte 14 and 15
                GovSettings.append(
                    {"Governor Target Frequency": "%.2f Hz" % (GovFreq / 100)}
                )

            except Exception as e1:
                self.LogErrorLine("Error parsing governor settings: " + str(e1))
        return GovSettings

    # ------------ GeneratorController:GetEngineSettings ------------------------
    def GetEngineSettings(self):

        EngineSettings = []
        EngineData = self.GetParameterFileValue(
            RegisterFileEnum.ENGINE_DATA_FILE_RECORD[REGISTER]
        )
        if len(EngineData) >= ((RegisterFileEnum.ENGINE_DATA_FILE_RECORD[LENGTH] * 2)):
            try:
                EngineSettings.append(
                    {
                        "Engine Transfer Enable": "Enabled"
                        if self.GetIntFromString(EngineData, 0, 2)
                        else "Disabled"
                    }
                )  # Byte 1 and 2
                EngineSettings.append(
                    {
                        "Preheat Enable": "Enabled"
                        if self.GetIntFromString(EngineData, 2, 2)
                        else "Disabled"
                    }
                )  # Byte 2 and 3
                if self.GetIntFromString(EngineData, 2, 2):
                    EngineSettings.append(
                        {
                            "Preheat Time": str(self.GetIntFromString(EngineData, 4, 2))
                            + " s"
                        }
                    )  # Byte 4 and 5
                    EngineSettings.append(
                        {
                            "Preheat Temp Limit": str(
                                self.GetIntFromString(EngineData, 47, 1)
                            )
                            + " F"
                        }
                    )  # Byte 47
                EngineSettings.append(
                    {
                        "Start detection RPM": str(
                            self.GetIntFromString(EngineData, 6, 2)
                        )
                    }
                )  # Byte 6 and 7
                EngineSettings.append(
                    {"Crank Time": str(self.GetIntFromString(EngineData, 8, 2)) + " s"}
                )  # Byte 8 and 9
                EngineSettings.append(
                    {
                        "Engine Hold Off Time": str(
                            self.GetIntFromString(EngineData, 10, 2)
                        )
                        + " s"
                    }
                )  # Byte 10 and 11
                EngineSettings.append(
                    {
                        "Engine Warm Up Time": str(
                            self.GetIntFromString(EngineData, 12, 2)
                        )
                        + " s"
                    }
                )  # Byte 12 and 13
                EngineSettings.append(
                    {
                        "Engine Cool Down Time": str(
                            self.GetIntFromString(EngineData, 14, 2)
                        )
                        + " s"
                    }
                )  # Byte 14 and 15
                EngineSettings.append(
                    {
                        "Pause Between Cranks Attempts": str(
                            self.GetIntFromString(EngineData, 16, 2)
                        )
                        + " s"
                    }
                )  # Byte 16 and 17
                EngineSettings.append(
                    {"Start Attempts": str(self.GetIntFromString(EngineData, 18, 2))}
                )  # Byte 18 and 19
                EngineSettings.append(
                    {
                        "Load Accept Frequency": str(
                            (self.GetIntFromString(EngineData, 20, 2)) / 100.0
                        )
                        + " Hz"
                    }
                )  # Byte 20 and 21
                EngineSettings.append(
                    {
                        "Load Accept Voltage": str(
                            (self.GetIntFromString(EngineData, 22, 2) / 10.0)
                        )
                        + " V"
                    }
                )  # Byte 22 and 23

            except Exception as e1:
                self.LogErrorLine("Error parsing engine settings: " + str(e1))
        return EngineSettings

    # ------------ GeneratorController:GetMaintTimes ----------------------------
    def GetMaintTimes(self):
        MaintTimes = []

        MaintData = self.GetParameterStringValue(
            RegisterStringEnum.MAINT_LIFE_REMAINING[REGISTER],
            RegisterStringEnum.MAINT_LIFE_REMAINING[RET_STRING],
        )

        if len(MaintData) >= (RegisterStringEnum.MAINT_LIFE_REMAINING[LENGTH]):
            try:

                OilLife = self.GetIntFromString(MaintData, 0, 2)  # Byte 1 and 2
                OilFilterLife = self.GetIntFromString(MaintData, 2, 2)  # Byte 2 and 3
                SparkPlugLife = self.GetIntFromString(MaintData, 4, 2)
                AirFilterLife = self.GetIntFromString(MaintData, 6, 2)
                BatteryLife = self.GetIntFromString(MaintData, 8, 2)
                GeneralMaintLife = self.GetIntFromString(MaintData, 10, 2)
                UtilityTransferLife = self.GetIntFromString(MaintData, 12, 2)
                GeneratorTransferLife = self.GetIntFromString(MaintData, 14, 2)
                BioFuelLife = self.GetIntFromString(MaintData, 16, 2)

                MaintTimes.append({"Oil Life": str(OilLife / 100.0) + " %"})
                MaintTimes.append({"Oil Filter Life": str(OilLife / 100.0) + " %"})
                MaintTimes.append(
                    {"Spark Plug Life": str(SparkPlugLife / 100.0) + " %"}
                )
                MaintTimes.append({"Battery Life": str(BatteryLife / 100.0) + " %"})
                MaintTimes.append(
                    {"General Maintenance Life": str(GeneralMaintLife / 100.0) + " %"}
                )
                MaintTimes.append(
                    {"Utility Transfer Life": str(UtilityTransferLife / 100.0) + " %"}
                )
                MaintTimes.append(
                    {
                        "Generator Transfer Life": str(GeneratorTransferLife / 100.0)
                        + " %"
                    }
                )
                MaintTimes.append({"Bio Fuel Life": str(BioFuelLife / 100.0) + " %"})

            except Exception as e1:
                self.LogErrorLine("Error parsing maint times: " + str(e1))

        return MaintTimes

    # ------------ GeneratorController:GetGeneratorSettings ---------------------
    def GetGeneratorSettings(self):

        GeneratorSettings = []
        FlyWheelTeeth = []
        Phase = None
        GenData = self.GetParameterFileValue(
            RegisterFileEnum.MISC_GEN_FILE_RECORD[REGISTER]
        )
        if len(GenData) >= ((RegisterFileEnum.MISC_GEN_FILE_RECORD[LENGTH] * 2)):
            try:
                FlyWheelTeeth.append(
                    self.GetIntFromString(GenData, 0, 2)
                )  # Byte 1 and 2
                FlyWheelTeeth.append(
                    self.GetIntFromString(GenData, 2, 2)
                )  # Byte 2 and 3
                UtilityCTRatio = self.GetIntFromString(GenData, 4, 2)
                GenCTRatio = self.GetIntFromString(GenData, 6, 2)
                Phase = self.GetIntFromString(GenData, 8, 1)  # Byte 8
                TargetRPMNormal = self.GetIntFromString(GenData, 9, 2)
                TargetRPMLowSpeed = self.GetIntFromString(GenData, 11, 2)

                GeneratorSettings.append({"Target RPM (Normal)": str(TargetRPMNormal)})
                GeneratorSettings.append(
                    {"Target RPM (Low Speed)": str(TargetRPMNormal)}
                )
                GeneratorSettings.append(
                    {
                        "Number of Flywheel Teeth": str(FlyWheelTeeth[0])
                        + ", "
                        + str(FlyWheelTeeth[1])
                    }
                )
                GeneratorSettings.append({"Phase": str(Phase)})
                self.Phase = str(Phase) if Phase != None else "Unknown"
                GeneratorSettings.append({"Utility CT Ratio": str(GenCTRatio)})
                GeneratorSettings.append({"Gen CT Ratio": str(UtilityCTRatio)})

            except Exception as e1:
                self.LogErrorLine("Error parsing generator settings: " + str(e1))

        return GeneratorSettings

    # ------------ GeneratorController:GetRunHours ------------------------------
    def GetRunHours(self):
        return self.GetParameter(self.Reg.ENGINE_HOURS_NOW[REGISTER], "", 10.0)

    # ------------------- PowerZone::DisplayOutage ------------------------------
    def DisplayOutage(self, DictOut=False, JSONNum=False):

        try:
            Outage = collections.OrderedDict()
            Outage["Outage"] = []

            Outage["Outage"].append({"Status": "Not Supported"})
            Outage["Outage"].append(
                {"System In Outage": "Yes" if self.SystemInOutage else "No"}
            )

        except Exception as e1:
            self.LogErrorLine("Error in DisplayOutage: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(Outage, ""))

        return Outage

    # ------------ PowerZone::DisplayRegisters ----------------------------------
    def DisplayRegisters(self, AllRegs=False, DictOut=False):

        try:
            Registers = collections.OrderedDict()
            Regs = collections.OrderedDict()
            Registers["Registers"] = Regs

            RegList = []

            Regs["Num Regs"] = "%d" % len(self.Holding)

            Regs["Holding"] = RegList
            # display all the registers
            temp_regsiters = self.Holding
            for Register, Value in temp_regsiters.items():
                RegList.append({Register: Value})

            if AllRegs:
                Regs["Log Registers"] = self.DisplayLogs(
                    AllLogs=True, RawOutput=True, DictOut=True
                )
                StringList = []
                Regs["Strings"] = StringList
                temp_regsiters = self.Strings
                for Register, Value in temp_regsiters.items():
                    StringList.append({Register: Value})
                FileDataList = []
                Regs["FileData"] = FileDataList
                temp_regsiters = self.FileData
                for Register, Value in temp_regsiters.items():
                    FileDataList.append({Register: Value})

        except Exception as e1:
            self.LogErrorLine("Error in DisplayRegisters: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(Registers, ""))

        return Registers

    # ----------  PowerZone::SetGeneratorTimeDate--------------------------------
    # set generator time to system time
    def SetGeneratorTimeDate(self):

        try:
            # get system time
            d = datetime.datetime.now()

            # We will write four registers at once: GEN_TIME_HR_MIN - GEN_TIME_YR.
            Data = []
            Data.append(d.hour)  # GEN_TIME_HR_MIN
            Data.append(d.minute)
            self.ModBus.ProcessWriteTransaction(
                self.Reg.GEN_TIME_HR_MIN[REGISTER], len(Data) / 2, Data
            )

            DayOfWeek = d.weekday()  # returns Monday is 0 and Sunday is 6
            # expects Sunday = 1, Saturday = 7
            if DayOfWeek == 6:
                DayOfWeek = 1
            else:
                DayOfWeek += 2
            Data = []
            Data.append(d.second)  # GEN_TIME_SEC_DYWK
            Data.append(DayOfWeek)  # Day of Week is always zero
            self.ModBus.ProcessWriteTransaction(
                self.Reg.GEN_TIME_SEC_DYWK[REGISTER], len(Data) / 2, Data
            )

            Data = []
            Data.append(d.month)  # GEN_TIME_MONTH_DAY
            Data.append(d.day)  # low byte is day of month
            self.ModBus.ProcessWriteTransaction(
                self.Reg.GEN_TIME_MONTH_DAY[REGISTER], len(Data) / 2, Data
            )

            Data = []
            # Note: Day of week should always be zero when setting time
            Data.append(d.year - 2000)  # GEN_TIME_YR
            Data.append(0)  #
            self.ModBus.ProcessWriteTransaction(
                self.Reg.GEN_TIME_YR[REGISTER], len(Data) / 2, Data
            )

        except Exception as e1:
            self.LogErrorLine("Error in SetGeneratorTimeDate: " + str(e1))

    # ----------  PowerZone::SetGeneratorQuietMode-------------------------------
    # Format of CmdString is "setquiet=yes" or "setquiet=no"
    # return  "Set Quiet Mode Command sent" or some meaningful error string
    def SetGeneratorQuietMode(self, CmdString):

        # TODO QUIET_TEST_REQUEST
        return "Not Supported"

    # ----------  PowerZone::SetGeneratorExerciseTime----------------------------
    # CmdString is in the format:
    #   setexercise=Monday,13:30,Weekly
    #   setexercise=Monday,13:30,BiWeekly
    #   setexercise=15,13:30,Monthly
    # return  "Set Exercise Time Command sent" or some meaningful error string
    def SetGeneratorExerciseTime(self, CmdString):
        return "Not Supported"

    # ----------  PowerZone::SetGeneratorRemoteCommand---------------------------
    # CmdString will be in the format: "setremote=start"
    # valid commands are start, stop, starttransfer, startexercise
    # return string "Remote command sent successfully" or some descriptive error
    # string if failure
    def SetGeneratorRemoteCommand(self, CmdString):

        # return "Not Supported"
        msgbody = "Invalid command syntax for command setremote (1)"

        try:
            # Format we are looking for is "setremote=start"
            CmdList = CmdString.split("=")
            if len(CmdList) != 2:
                self.LogError(
                    "Validation Error: Error parsing command string in SetGeneratorRemoteCommand (parse): "
                    + CmdString
                )
                return msgbody

            CmdList[0] = CmdList[0].strip()

            if not CmdList[0].lower() == "setremote":
                self.LogError(
                    "Validation Error: Error parsing command string in SetGeneratorRemoteCommand (parse2): "
                    + CmdString
                )
                return msgbody

            Command = CmdList[1].strip()
            Command = Command.lower()

        except Exception as e1:
            self.LogErrorLine(
                "Validation Error: Error parsing command string in SetGeneratorRemoteCommand: "
                + CmdString
            )
            self.LogError(str(e1))
            return msgbody

        try:
            Value = 0x0000  # writing any value to index register is valid for remote start / stop commands
            Data = []
            if Command == "start":
                # 0 : Stop, 1 : Start
                Value = 0x0001  # remote start
            elif Command == "stop":
                Value = 0x0000  # remote stop
            elif Command == "starttransfer":
                return "Remote start transfer not supported"
            elif Command == "startparallel":
                return "Remote start parallel not supported"
            elif Command == "quiettest":
                Data = []
                Data.append(0)
                Data.append(1)
                self.ModBus.ProcessWriteTransaction(
                    self.Reg.QUIET_TEST_REQUEST[REGISTER], len(Data) / 2, Data
                )
                return "Remote command sent successfully (quiettest)"
            elif Command == "quietteststop":
                Data = []
                Data.append(0)
                Data.append(0)
                self.ModBus.ProcessWriteTransaction(
                    self.Reg.QUIET_TEST_REQUEST[REGISTER], len(Data) / 2, Data
                )
                return "Remote command sent successfully (quietteststop)"
            elif Command == "ackalarm":
                Data = []
                Data.append(0)
                Data.append(1)
                # Alarm Globals Values
                # 1 : Acknowledge All
                # 4 : Clear Alarm
                # 6 : Reset All Alarms
                # 8 : Silence Horn
                self.ModBus.ProcessWriteTransaction(
                    self.Reg.ALARM_GLOBALS[REGISTER], len(Data) / 2, Data
                )

                return "Remote command sent successfully (ackalarm)"
            elif Command == "cleartalarm":
                Data = []
                Data.append(0)
                Data.append(4)
                self.ModBus.ProcessWriteTransaction(
                    self.Reg.ALARM_GLOBALS[REGISTER], len(Data) / 2, Data
                )
                return "Remote command sent successfully (ackalarm)"
            elif Command == "resetallalarm":
                Data = []
                Data.append(0)
                Data.append(6)
                self.ModBus.ProcessWriteTransaction(
                    self.Reg.ALARM_GLOBALS[REGISTER], len(Data) / 2, Data
                )
                return "Remote command sent successfully (ackalarm)"
            elif Command == "silencetalarm":
                Data = []
                Data.append(0)
                Data.append(8)
                self.ModBus.ProcessWriteTransaction(
                    self.Reg.ALARM_GLOBALS[REGISTER], len(Data) / 2, Data
                )
                return "Remote command sent successfully (ackalarm)"
                """
                # This does not work
                elif Command == "off":
                    Data = []
                    Data.append(0)
                    Data.append(0)
                    self.ModBus.ProcessWriteTransaction(self.Reg.SWITCH_STATE[REGISTER], len(Data) / 2, Data)
                    return "Remote command sent successfully (off)"
                elif Command == "auto":
                    Data = []
                    Data.append(1)
                    Data.append(0)
                    self.ModBus.ProcessWriteTransaction(self.Reg.SWITCH_STATE[REGISTER], len(Data) / 2, Data)
                    return "Remote command sent successfully (auto)"
                elif Command == "manual":
                    Data = []
                    Data.append(0)
                    Data.append(1)
                    self.ModBus.ProcessWriteTransaction(self.Reg.SWITCH_STATE[REGISTER], len(Data) / 2, Data)
                    return "Remote command sent successfully (manual)"
                """
            else:
                return "Invalid command syntax for command setremote (2)"

            Data.append(Value >> 8)  # value to be written (High byte)
            Data.append(Value & 0x00FF)  # value written (Low byte)

            self.ModBus.ProcessWriteTransaction(
                self.Reg.REMOTE_START[REGISTER], len(Data) / 2, Data
            )

            return "Remote command sent successfully"
        except Exception as e1:
            self.LogErrorLine("Error in SetGeneratorRemoteCommand: " + str(e1))
            return "Error"

    # ----------  PowerZone:GetController  --------------------------------------
    # return the name of the controller, if Actual == False then return the
    # controller name that the software has been instructed to use if overridden
    # in the conf file
    def GetController(self, Actual=True):

        # TODO Power Zone vs Power Zone Pro
        return "Power Zone"

    # ----------  PowerZone:ComminicationsIsActive  -----------------------------
    # Called every few seconds, if communictions are failing, return False, otherwise
    # True
    def ComminicationsIsActive(self):
        if self.LastRxPacketCount == self.ModBus.RxPacketCount:
            return False
        else:
            self.LastRxPacketCount = self.ModBus.RxPacketCount
            return True

    # ----------  PowerZone:RemoteButtonsSupported  -----------------------------
    # return true if Panel buttons are settable via the software
    def RemoteButtonsSupported(self):
        return False

    # ----------  PowerZone:PowerMeterIsSupported  ------------------------------
    # return true if GetPowerOutput is supported
    def PowerMeterIsSupported(self):

        if self.bDisablePowerLog:
            return False
        if self.UseExternalCTData:
            return True
        return True

    # ---------------------PowerZone::GetPowerOutput-----------------------------
    # returns current kW
    # rerturn empty string ("") if not supported,
    # return kW with units i.e. "2.45kW"
    def GetPowerOutput(self, ReturnFloat=False):

        if self.UseCalculatedPower:
            return self.GetPowerOutputAlt(ReturnFloat=ReturnFloat)
        if ReturnFloat:
            return self.GetParameter(
                self.Reg.TOTAL_POWER_KW[REGISTER], ReturnFloat=True, Divider = 1000
            )
        else:
            return self.GetParameter(
                self.Reg.TOTAL_POWER_KW[REGISTER], "kW", ReturnFloat=False,  Divider = 1000
            )

    # ------------ PowerZone:GetPowerOutputAlt ----------------------------------
    def GetPowerOutputAlt(self, ReturnFloat=False):

        if ReturnFloat:
            DefaultReturn = 0.0
        else:
            DefaultReturn = "0 kW"

        if not self.PowerMeterIsSupported():
            return DefaultReturn

        EngineState = self.GetEngineState()
        # report null if engine is not running
        if (
            not len(EngineState)
            or "stop" in EngineState.lower()
            or "off" in EngineState.lower()
        ):
            return DefaultReturn

        Current = float(
            self.GetParameter(self.Reg.GEN_AVERAGE_CURRENT[REGISTER], ReturnInt=True)
        )
        Voltage = float(
            self.GetParameter(self.Reg.GEN_AVERAGE_VOLTAGE_LL[REGISTER], ReturnInt=True)
        )
        powerfactor = self.GetParameter(
            self.Reg.GEN_PF_LL_AVG[REGISTER], ReturnFloat=True, Divider=100.0
        )

        PowerOut = 0.0
        try:
            if not Current == 0:
                # P(W) = PF x I(A) x V(V)
                # this calculation is for single phase but we are using average voltage and current
                # watts is the unit
                PowerOut = powerfactor * Voltage * Current
        except:
            PowerOut = 0.0

        # return kW
        if ReturnFloat:
            return round((PowerOut / 1000.0), 3)
        return "%.2f kW" % (PowerOut / 1000.0)

    # ------------ PowerZone:CheckExternalCTData ----------------------------
    def CheckExternalCTData(self, request="current", ReturnFloat=False, gauge=False):
        try:

            if ReturnFloat:
                DefaultReturn = 0.0
            else:
                DefaultReturn = 0

            if not self.UseExternalCTData:
                return None
            ExternalData = self.GetExternalCTData()

            if ExternalData == None:
                return None

            # This assumes the following format:
            # NOTE: all fields are *optional*
            # { "strict" : True or False (true requires an outage to use the data)
            #   "current" : optional, float value in amps
            #   "power"   : optional, float value in kW
            #   "powerfactor" : float value (default is 1.0) used if converting from current to power or power to current
            #   ctdata[] : list of amps for each leg
            #   ctpower[] :  list of power in kW for each leg
            #   voltagelegs[] : list of voltage legs
            #   voltage : optional, float value of total RMS voltage (all legs combined)
            #   phase : optional, int (1 or 3)
            # }
            strict = False
            if "strict" in ExternalData:
                strict = ExternalData["strict"]

            if strict:
                # TODO? Need to know utility voltage or outage state
                pass

            # if we get here we must convert the data.
            Voltage = self.GetParameter(
                self.Reg.GEN_AVERAGE_VOLTAGE_LL[REGISTER], ReturnInt=True
            )

            return self.ConvertExternalData(
                request=request, voltage=Voltage, ReturnFloat=ReturnFloat
            )

        except Exception as e1:
            self.LogErrorLine("Error in CheckExternalCTData: " + str(e1))
            return DefaultReturn

    # ----------  PowerZone:GetCommStatus  --------------------------------------
    # return Dict with communication stats
    def GetCommStatus(self):
        return self.ModBus.GetCommStats()

    # ------------ PowerZone:GetBaseStatus --------------------------------------
    # return one of the following: "ALARM", "SERVICEDUE", "EXERCISING", "RUNNING",
    # "RUNNING-MANUAL", "OFF", "MANUAL", "READY"
    def GetBaseStatus(self):
        try:
            EngineStatus = self.GetEngineState().lower()
            GeneratorStatus = self.GetGeneratorStatus().lower()
            SwitchState = self.GetSwitchState().lower()

            if "running" in EngineStatus:
                IsRunning = True
            else:
                IsRunning = False
            if "stopped" in GeneratorStatus:
                IsStopped = True
            else:
                IsStopped = False
            if (
                "exercising" in EngineStatus
                or "exercise" in EngineStatus
                or "quiettest" in EngineStatus
            ):
                IsExercising = True
            else:
                IsExercising = False
            # TODO
            ServiceDue = False
            """
            if self.HPanelDetected:
                ServiceDue = self.GetParameterBit(self.Reg.OUTPUT_7[REGISTER], Output7.NEED_SERVICE)
            else:
                ServiceDue = self.GetParameterBit(self.Reg.OUTPUT_5[REGISTER], 0x4000)
            """
            if self.SystemInAlarm():
                return "ALARM"
            elif ServiceDue:
                return "SERVICEDUE"
            elif IsExercising:
                return "EXERCISING"
            elif IsRunning and SwitchState == "auto":
                return "RUNNING"
            elif IsRunning and SwitchState == "manual":
                return "RUNNING-MANUAL"
            elif SwitchState == "manual":
                return "MANUAL"
            elif SwitchState == "auto":
                return "READY"
            elif SwitchState == "off":
                return "OFF"
            else:
                self.FeedbackPipe.SendFeedback(
                    "Base State",
                    FullLogs=True,
                    Always=True,
                    Message="Unknown Base State",
                )
                return "UNKNOWN"
        except Exception as e1:
            self.LogErrorLine("Error in GetBaseStatus: " + str(e1))
            return "UNKNOWN"

    # ------------ PowerZone:GetOneLineStatus -----------------------------------
    # returns a one line status for example : switch state and engine state
    def GetOneLineStatus(self):
        return self.GetSwitchState() + " : " + self.GetEngineState()

    # ----------  PowerZone::FuelSensorSupported---------------------------------
    def FuelSensorSupported(self):

        if self.UseFuelSensor:
            return True
        return False

    # ------------ PowerZone:GetFuelSensor --------------------------------------
    def GetFuelSensor(self, ReturnInt=False):

        if not self.FuelSensorSupported():
            return None

        return self.GetParameter(self.Reg.FUEL_LEVEL[REGISTER], ReturnInt=ReturnInt)

    # ----------  PowerZone::GetFuelConsumptionDataPoints------------------------
    def GetFuelConsumptionDataPoints(self):

        try:
            if self.FuelHalfRate == 0 or self.FuelFullRate == 0:
                return None

            return [
                0.5,
                float(self.FuelHalfRate),
                1.0,
                float(self.FuelFullRate),
                self.FuelUnits,
            ]

        except Exception as e1:
            self.LogErrorLine("Error in GetFuelConsumptionDataPoints: " + str(e1))
        return None
