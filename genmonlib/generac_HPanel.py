#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: generac_HPanel.py
# PURPOSE: Controller Specific Detils for Generac H-100 and G-Panel
#
#  AUTHOR: Jason G Yates
#    DATE: 30-Apr-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import datetime, time, sys, os, threading, socket, re
import atexit, json, collections, random

from genmonlib.controller import GeneratorController
from genmonlib.mytile import MyTile
from genmonlib.modbus_file import ModbusFile
from genmonlib.mymodbus import ModbusProtocol
from genmonlib.program_defaults import ProgramDefaults

# Module defines ---------------------------------------------------------------
REGISTER    = 0
LENGTH      = 1
RET_STRING  = 2

#These are the same or H-Panel and G-Panel
ALARM_LOG_START                 = 0x0c01
ALARM_LOG_ENTRIES               = 20
ALARM_LOG_LENGTH                = 64
EVENT_LOG_START                 = 0x0c15
EVENT_LOG_ENTRIES               = 20
EVENT_LOG_LENGTH                = 64
NAMEPLATE_DATA_FILE_RECORD      = "0040"      # 0x40
NAMEPLATE_DATA_LENGTH           = 64        # Note: This is 1024 but I only read 64 due to performance
MISC_GEN_FILE_RECORD            = "002a"
MISC_GEN_LENGTH                 = 18
ENGINE_DATA_FILE_RECORD         = "0050"
ENGINE_DATA_FILE_RECORD_LENGTH  = 48
GOV_DATA_FILE_RECORD            = "00d3"
GOV_DATA_FILE_RECORD_LENGTH     = 60        # Extra byte, actual data is 59
GOV_DATA_SEC_FILE_RECORD        = "00d4"
GOV_DATA_SEC_FILE_RECORD_LENGTH = 60        # Extra byte, actual data is 59
REGULATOR_FILE_RECORD           = "00d5"
REGULATOR_FILE_RECORD_LENGTH    = 46

#---------------------HPanelReg::HPanelReg--------------------------------------
class HPanelReg(object):
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
    OIL_TEMP                = ["008a", 4]            # Oil Temp
    COOLANT_TEMP            = ["008c", 4]            # Coolant Temp
    OIL_PRESSURE            = ["008e", 4]            # Oil Pressure
    COOLANT_LEVEL           = ["0090", 4]            # Coolant Level                * Different on G-Panel
    FUEL_LEVEL              = ["0092", 4]            # USER CFG 05/Fuel Level =147  * Different on G-Panel
    THROTTLE_POSITION       = ["0096", 4]            # Throttle Position            * Different on G-Panel
    O2_SENSOR               = ["0098", 4]            # O2 Sensor                    * Different on G-Panel
    # NOTE: When the generator is running the battery charger current value may be wrong.
    BATTERY_CHARGE_CURRNT   = ["009a", 4]            # Battery Charge Current       * Different on G-Panel
    BATTERY_VOLTS           = ["009c", 4]            # Battery Charge Volts         * Different on G-Panel
    CURRENT_PHASE_A         = ["009e", 4]            # Current Phase A              * Different on G-Panel
    CURRENT_PHASE_B         = ["00a0", 4]            # Current Phase B              * Different on G-Panel
    # NOTE: Single Phase Current
    CURRENT_PHASE_C         = ["00a2", 4]            # Current Phase C              * Different on G-Panel
    AVG_CURRENT             = ["00a4", 4]            # Avg Current                  * Different on G-Panel
    VOLTS_PHASE_A_B         = ["00a6", 4]            # Voltage Phase AB             * Different on G-Panel
    VOLTS_PHASE_B_C         = ["00a8", 4]            # Voltage Phase BC             * Different on G-Panel
    VOLTS_PHASE_C_A         = ["00aa", 4]            # Voltage Phase CA             * Different on G-Panel
    AVG_VOLTAGE             = ["00ac", 4]            # Average Voltage              * Different on G-Panel
    TOTAL_POWER_KW          = ["00ae", 4]            # Total Power (kW)             * Different on G-Panel
    TOTAL_PF                = ["00b0", 4]            # Power Factor                 * Different on G-Panel
    OUTPUT_FREQUENCY        = ["00b2", 4]            # Output Frequency             * Different on G-Panel
    OUTPUT_RPM              = ["00b4", 4]            # Output RPM                   * Different on G-Panel
    A_F_DUTY_CYCLE          = ["00b6", 4]            # Air Fuel Duty Cycle          * Different on G-Panel

    GEN_TIME_HR_MIN         = ["00e0", 2]            # Time HR:MIN
    GEN_TIME_SEC_DYWK       = ["00e1", 2]            # Time SEC:DayOfWeek
    GEN_TIME_MONTH_DAY      = ["00e2", 2]            # Time Month:DayofMonth
    GEN_TIME_YR             = ["00e3", 2]            # Time YR:UNK

    ALARM_ACK               = ["012e", 2]            # Number of alarm acks
    ACTIVE_ALARM_COUNT      = ["012f", 2]            # Number of active alarms
    ENGINE_HOURS            = ["0130", 4]            # Engine Hours High
    ENGINE_STATUS_CODE      = ["0132", 2]            # Engine Status Code

    START_BITS              = ["019c", 2]            # Start Bits
    START_BITS_2            = ["019d", 2]            # Start Bits 2
    START_BITS_3            = ["019e", 2]            # Start Bits 2
    KEY_SWITCH_STATE        = ["01a0", 2]            # High Byte is True if Auto, Low Byte True if Manual (False if Off)
    DI_STATE_1              = ["01a1", 2]            # * Different on G-Panel
    DI_STATE_2              = ["01a2", 2]            # * Different on G-Panel
    QUIETTEST_STATUS        = ["022b", 2]            # Quiet Test Status and reqest

    # EXT_SW_XX regististers are for HTS/MTS/STS Switches
    EXT_SW_GENERAL_STATUS   = ["0ea1", 2]            # External Switch General Status
    EXT_SW_MINIC_DIAGRAM    = ["0ea2", 2]            # Ext Switch Mimic Diagram
    EXT_SW_TARGET_VOLTAGE   = ["0ea7", 2]            # External Switch Target Voltage
    EXT_SW_TARGET_FREQ      = ["0eaa", 2]            # External Switch Target Freq
    EXT_SW_UTILITY_VOLTS_AB = ["0ead", 2]            # External Switch Utility AB Voltage
    EXT_SW_UTILITY_VOLTS_BC = ["0eae", 2]            # External Switch Utility BC Voltage
    EXT_SW_UTILITY_VOLTS_CA = ["0eaf", 2]            # External Switch Utility CA Voltage
    EXT_SW_UTILITY_AMPS_A   = ["0eb0", 2]            # External Switch Utility A Amps
    EXT_SW_UTILITY_AMPS_B   = ["0eb1", 2]            # External Switch Utility B Amps
    EXT_SW_UTILITY_AMPS_C   = ["0eb2", 2]            # External Switch Utility C Amps
    EXT_SW_UTILITY_AVG_VOLTS= ["0eb4", 2]            # External Switch Average Utility Volts
    EXT_SW_UTILITY_AVG_AMPS = ["0eb5", 2]            # External Switch Average Utility Amps
    EXT_SW_UTILITY_FREQ     = ["0eb6", 2]            # External Switch Utility Freq
    EXT_SW_UTILITY_PF       = ["0eb7", 2]            # External Switch Utility Power Factor
    EXT_SW_UTILITY_KW       = ["0eb8", 2]            # External Switch Utility Power
    EXT_SW_GEN_AVG_VOLT     = ["0eb9", 2]            # External Switch Generator Average Voltage
    EXT_SW_GEN_FREQ         = ["0eba", 2]            # External Switch Generator Freq
    EXT_SW_BACKUP_BATT_VOLTS= ["0ebc", 2]            # External Switch Backup Battery Voltage
    EXT_SW_VERSION          = ["0ebf", 2]            # External Switch SW Version
    EXT_SW_SELECTED         = ["0ec0", 2]            # External Switch Selected


    #---------------------HPanelReg::hexsort------------------------------------
    #@staticmethod
    def hexsort(self, e):
        try:
            return int(e[REGISTER],16)
        except:
            return 0
    #@staticmethod
    #---------------------HPanelReg::GetRegList---------------------------------
    def GetRegList(self):
        RetList = []
        for attr, value in HPanelReg.__dict__.items():
            if not callable(getattr(self,attr)) and not attr.startswith("__"):
                RetList.append(value)

        RetList.sort(key=self.hexsort)
        return RetList
#---------------------------HPanelIO:HPanelIO-----------------------------------
class HPanelIO(object):

    Inputs = {
        # Input 1
        ("0080", 0x8000) : "Switch In Auto",
        ("0080", 0x4000) : "Switch in Manual",
        ("0080", 0x2000) : "Emergency Stop",
        ("0080", 0x1000) : "Remote Start",
        ("0080", 0x0800) : "DI-1 Battery Charger Fail",
        ("0080", 0x0400) : "DI-2 Fuel Pressure",
        ("0080", 0x0200) : "DI-3 Line Power",
        ("0080", 0x0100) : "DI-4 Generator Power",
        ("0080", 0x0080) : "Modem DCD",
        ("0080", 0x0040) : "Modem Enabled",
        ("0080", 0x0020) : "Generator Overspeed",
        ("0080", 0x0010) : "HUIO-1 Config 12",
        ("0080", 0x0008) : "HUIO-1 Config 13",
        ("0080", 0x0004) : "HUIO-1 Config 14",
        ("0080", 0x0002) : "HUIO-1 Config 15",
        ("0080", 0x0001) : "HUIO-2 Config 16",
        # Input 2
        ("0081", 0x8000) : "HUIO-2 Config 17",
        ("0081", 0x4000) : "HUIO-2 Config 18",
        ("0081", 0x2000) : "HUIO-2 Config 19",
        ("0081", 0x1000) : "HUIO-3 Config 20",
        ("0081", 0x0800) : "HUIO-3 Config 21",
        ("0081", 0x0400) : "HUIO-3 Config 22",
        ("0081", 0x0200) : "HUIO-3 Config 23",
        ("0081", 0x0100) : "HUIO-4 Config 24",
        ("0081", 0x0080) : "HUIO-4 Config 25",
        ("0081", 0x0040) : "HUIO-4 Config 26",
        ("0081", 0x0020) : "HUIO-4 Config 27",
    }
    Outputs = {
        # Output1
        ("0082", 0x8000) : "Genertor in Alarm",
        ("0082", 0x4000) : "Genertor in Warning",
        ("0082", 0x2000) : "Running",
        ("0082", 0x1000) : "Alarms Enabled",
        ("0082", 0x0800) : "Read for Load",
        ("0082", 0x0400) : "Ready to Run",
        ("0082", 0x0200) : "Stopped in Alarm",
        ("0082", 0x0100) : "Stopped",
        ("0082", 0x0080) : "Key in Manual Position",
        ("0082", 0x0040) : "Key in Auto Position",
        ("0082", 0x0020) : "Key in Off Position",
        ("0082", 0x0004) : "Annunciator Light",

        # Output6
        ("0087", 0x0400) : "Digital Input Key in Auto Active",
        ("0087", 0x0200) : "Digital Input Key in Manual Active",
        ("0087", 0x0100) : "Emergency Stop Digitial Input Active",
        ("0087", 0x0080) : "Remote Start Digital Input Active",
        ("0087", 0x0040) : "DI-1, Digitial Input #5 Active / Battery Charger Fail",
        ("0087", 0x0020) : "DI-2, Digitial Input #6 Active / Ruptured Basin, Gas Leak, Low Fuel Pressure",
        ("0087", 0x0010) : "DI-3, Digitial Input #7 Active / Line Power",
        ("0087", 0x0008) : "DI-4, Digitial Input #8 Active / Generator Power",
        ("0087", 0x0004) : "Line Power",
        ("0087", 0x0002) : "Generator Power",
        # Output 7
        ("0088", 0x4000) : "In Warm Up",
        ("0088", 0x2000) : "In Cool Down",
        ("0088", 0x1000) : "Cranking",
        ("0088", 0x0800) : "Needs Service",
        ("0088", 0x0400) : "Shutdown",
        ("0088", 0x0080) : "Fault Relay Active",
        ("0088", 0x0040) : "User Config 106",
        ("0088", 0x0020) : "Internal Exercise Active",
        ("0088", 0x0010) : "Check for ILC",
        ("0088", 0x0008) : "User Config 109",
        ("0088", 0x0004) : "User Config 110",
        ("0088", 0x0002) : "User Config 111",
        ("0088", 0x0001) : "User Config 112",
        # Output 8
        ("0089", 0x8000) : "User Config 113",
        ("0089", 0x4000) : "User Config 114",
        ("0089", 0x2000) : "User Config 115",
        ("0089", 0x1000) : "User Config 116",
        ("0089", 0x0800) : "User Config 117",
        ("0089", 0x0400) : "User Config 118",
        ("0089", 0x0400) : "User Config 118",
        ("0089", 0x0200) : "RPM Missing",
        ("0089", 0x0200) : "Reset Alarms",
    }
    Alarms = {
        # Output 1
        ("0082", 0x0010) : "Overcrank Alarm - Generator has unsuccessfully tried to start the designated number of times.",
        ("0082", 0x0008) : "Oil Inhibit Alarm - Oil pressure too high for a stopped engine.",
        ("0082", 0x0002) : "Oil Temp High Alarm - Oil Temperature has gone above maximum alarm limit.",
        ("0082", 0x0002) : "Oil Temp Low Alarm - Oil Temperature has gone below minimum alarm limit.",
        # Output 2
        ("0083", 0x8000) : "Oil Temp High Warning - Oil Temperature has gone above maximum warning limit.",
        ("0083", 0x4000) : "Oil Temp Low Warning - Oil Temperature has gone below minimum warning limit.",
        ("0083", 0x2000) : "Oil Temp Fault - Oil Temperature sensor exceeds nominal limits for valid sensor reading.",
        ("0083", 0x1000) : "Coolant Temp High Alarm - Coolant Temperature has gone above maximum alarm limit.",
        ("0083", 0x0800) : "Coolant Temp Low Alarm - Coolant Temperature has gone below mimimuim alarm limit.",
        ("0083", 0x0400) : "Coolant Temp High Warning - Coolant Temperature has gone above maximum warning limit.",
        ("0083", 0x0200) : "Coolant Temp Low Warning - Coolant Temperature has gone below mimimuim warning limit.",
        ("0083", 0x0100) : "Coolant Temp Fault - Coolant Temperature sensor exceeds nominal limits for valid sensor reading.",
        ("0083", 0x0080) : "Oil Pressure High Alarm - Oil Pressure has gone above maximum alarm limit.",
        ("0083", 0x0040) : "Oil Pressure Low Alarm - Oil Pressure has gone below mimimum alarm limit.",
        ("0083", 0x0020) : "Oil Pressure High Warning - Oil Pressure has gone above maximum warning limit.",
        ("0083", 0x0010) : "Oil Pressure Low Warning - Oil Pressure has gone below minimum warning limit.",
        ("0083", 0x0008) : "Oil Pressure Fault - Oil Pressure sensor exceeds nominal limits for valid sensor reading.",
        ("0083", 0x0004) : "Coolant Level High Alarm - Coolant Level has gone above maximum alarm limit.",
        ("0083", 0x0002) : "Coolant Level Low Alarm - Coolant Level has gone below minimum alarm limit.",
        ("0083", 0x0001) : "Coolant Level High Warning - Coolant Level has gone above maximum warning limit.",
        # Output 3
        ("0084", 0x8000) : "Coolant Level Low Warning - Coolant Level has gone below mimimum warning limit.",
        ("0084", 0x4000) : "Coolant Level Fault - Coolant Level sensor exceeds nominal limits for valid sensor reading.",
        ("0084", 0x2000) : "Fuel Level High Alarm - Fuel Level has gone above maximum alarm limit.",
        ("0084", 0x1000) : "Fuel Level Low Alarm - Fuel Level has gone below mimimum alarm limit.",
        ("0084", 0x0800) : "Fuel Level High Warning - Fuel Level has gone above maximum warning limit.",
        ("0084", 0x0400) : "Fuel Level Low Warning - Fuel Level has gone below mimimum warning limit.",
        ("0084", 0x0200) : "Fuel Level Fault - Fuel Level sensor exceeds nominal limits for valid sensor reading.",
        ("0084", 0x0100) : "Analog Input 6 High Alarm - Analog Input 6 has gone above maximum alarm limit (Fuel Pressure or Inlet Air Temperature).",
        ("0084", 0x0080) : "Analog Input 6 Low Alarm - Analog Input 6 has gone below mimimum alarm limit (Fuel Pressure or Inlet Air Temperature).",
        ("0084", 0x0040) : "Analog Input 6 High Warning - Analog Input 6 has gone above maximum warning limit (Fuel Pressure or Inlet Air Temperature).",
        ("0084", 0x0020) : "Analog Input 6 Low Warning - Analog Input 6 has gone below mimimum warning limit (Fuel Pressure or Inlet Air Temperature).",
        ("0084", 0x0010) : "Analog Input 6 Fault - Analog Input 6 sensor exceeds nominal limits for valid sensor reading (Fuel Pressure or Inlet Air Temperature).",
        ("0084", 0x0008) : "Throttle Position High Alarm - Throttle Position has gone above maximum alarm limit.",
        ("0084", 0x0004) : "Throttle Position Low Alarm - Throttle Position has gone below minimum alarm limit.",
        ("0084", 0x0002) : "Throttle Position High Warning - Throttle Position has gone above maximum warning limit.",
        ("0084", 0x0001) : "Throttle Position Low Warning - Throttle Position has gone below minimum warning limit.",

        # Output 4
        ("0085", 0x8000) : "Throttle Position Fault - Throttle Position sensor exceeds nominal limits for valid sensor reading.",
        ("0085", 0x4000) : "Analog Input 8 High Alarm - Analog Input 8 has gone above maximum alarm limit (Emissions Sensor or Fluid Basin).",
        ("0085", 0x2000) : "Analog Input 8 Low Alarm - Analog Input 8 has gone below minimum alarm limit (Emissions Sensor or Fluid Basin).",
        ("0085", 0x1000) : "Analog Input 8 High Warning - Analog Input 8 has gone above maximum warning limit (Emissions Sensor or Fluid Basin).",
        ("0085", 0x0800) : "Analog Input 8 Low Warning - Analog Input 8 has gone below minimum warning limit Emissions Sensor or Fluid Basin).",
        ("0085", 0x0400) : "Analog Input 8 Fault - Analog Input 8 sensor exceeds nominal limits for valid sensor reading (Emissions Sensor or Fluid Basin).",
        ("0085", 0x0200) : "Battery Charge Current High Alarm - Battery Charge Current has gone above maximum alarm limit.",
        ("0085", 0x0100) : "Battery Charge Current Low Alarm - Battery Charge Current has gone below minimum alarm limit.",
        ("0085", 0x0080) : "Battery Charge Current High Warning - Battery Charge Current has gone above maximum warning limit.",
        ("0085", 0x0040) : "Battery Charge Current Low Warning - Battery Charge Current has gone below minimum warning limit.",
        ("0085", 0x0020) : "Battery Charge Current Fault - Battery Charge Current sensor exceeds nominal limits for valid sensor reading.",
        ("0085", 0x0010) : "Battery Charge Voltage High Alarm - Battery Charge Voltage has gone above maximum alarm limit.",
        ("0085", 0x0008) : "Battery Charge Voltage Low Alarm - Battery Charge Voltage has gone below minimum alarm limit.",
        ("0085", 0x0004) : "Battery Charge Voltage High Warning - Battery Charge Voltage has gone above maximum warning limit.",
        ("0085", 0x0002) : "Battery Charge Voltage Low Warning - Battery Charge Voltage has gone below minimum warning limit.",
        ("0085", 0x0001) : "Battery Charge Voltage Fault - Battery Charge Voltage sensor exceeds nominal limits for valid sensor reading.",

        # Output 5
        ("0086", 0x8000) : "Average Current Low Alarm - Average Current has gone below minimum alarm limit.",
        ("0086", 0x4000) : "Average Current High Warning - Average Current has gone above maximum warning limit.",
        ("0086", 0x2000) : "Average Current Low Warning - Average Current has gone below minimum warning limit.",
        ("0086", 0x1000) : "Average Voltage High Alarm - Average Voltage has gone above maximum alarm limit.",
        ("0086", 0x0800) : "Average Voltage Low Alarm - Average Voltage has gone below minimum alarm limit.",
        ("0086", 0x0400) : "Average Voltage High Warning - Average Voltage has gone above maximum warning limit.",
        ("0086", 0x0200) : "Average Voltage Low Warning - Average Voltage has gone below minimum warning limit.",
        ("0086", 0x0100) : "Total Real Power High Alarm - Total Real Power has gone above maximum alarm limit.",
        ("0086", 0x0080) : "Total Real Power Low Alarm - Total Real Power has gone below minimum alarm limit.",
        ("0086", 0x0040) : "Total Real Power High Warning - Total Real Power has gone above maximum warning limit.",
        ("0086", 0x0020) : "Total Real Power Low Warning - Total Real Power has gone below minimum warning limit.",
        ("0086", 0x0010) : "Generator Frequency High Alarm - Generator Frequency has gone above maximum alarm limit.",
        ("0086", 0x0008) : "Generator Frequency Low Alarm - Generator Frequency has gone below minimum alarm limit.",
        ("0086", 0x0004) : "Generator Frequency High Warning - Generator Frequency has gone above maximum warning limit.",
        ("0086", 0x0002) : "Generator Frequency Low Warning - Generator Frequency has gone below minimum warning limit.",
        ("0086", 0x0001) : "Generator Frequency Fault - Generator Frequency sensor exceeds nominal limits for valid sensor reading.",
        # Output 6
        ("0087", 0x8000) : "Engine RPM High Alarm - Engine RPM has gone above maximum alarm limit.",
        ("0087", 0x4000) : "Engine RPM Low Alarm - Engine RPM has gone below minimum alarm limit.",
        ("0087", 0x2000) : "Engine RPM High Warning - Engine RPM has gone above maximum warning limit.",
        ("0087", 0x1000) : "Engine RPM Low Warning - Engine RPM has gone below minimum warning limit.",
        ("0087", 0x0800) : "Engine RPM Fault - Engine RPM exceeds nominal limits for valid sensor reading.",
        ("0087", 0x0001) : "Integrated Logic Controller Warning - Warning 1.",
        # Output 7
        ("0088", 0x8000) : "Integrated Logic Controller Warning - Warning 2.",
        ("0088", 0x0200) : "Emergency Stop",
        ("0088", 0x0100) : "Detected current phase rotation as not being A-B-C and not matching voltage.",

    }

#---------------------GPanelReg::GPanelReg--------------------------------------
class GPanelReg(object):
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
    OIL_TEMP                = ["008a", 4]            # Oil Temp
    COOLANT_TEMP            = ["008c", 4]            # Coolant Temp
    OIL_PRESSURE            = ["008e", 4]            # Oil Pressure
    THROTTLE_POSITION       = ["0090", 4]            # Throttle Position            * Different on G-Panel
    COOLANT_LEVEL           = ["009c", 4]            # Coolant Level                * Different on G-Panel
    FUEL_LEVEL              = ["009e", 4]            # USER CFG 05/Fuel Level =147  * Different on G-Panel
    O2_SENSOR               = ["00a4", 4]            # O2 Sensor                    * Different on G-Panel
    # NOTE: When the generator is running the battery charger current value may be wrong.
    BATTERY_CHARGE_CURRNT   = ["00a6", 4]            # Battery Charge Current       * Different on G-Panel
    A_F_DUTY_CYCLE          = ["00aa", 4]            # Air Fuel Duty Cycle          * Different on G-Panel
    BATTERY_VOLTS           = ["00ac", 4]            # Battery Charge Volts         * Different on G-Panel
    CURRENT_PHASE_A         = ["00b6", 4]            # Current Phase A              * Different on G-Panel
    CURRENT_PHASE_B         = ["00b8", 4]            # Current Phase B              * Different on G-Panel
    # NOTE: Single Phase Current
    CURRENT_PHASE_C         = ["00ba", 4]            # Current Phase C              * Different on G-Panel
    AVG_CURRENT             = ["00bc", 4]            # Avg Current                  * Different on G-Panel
    VOLTS_PHASE_A_B         = ["00c6", 4]            # Voltage Phase AB             * Different on G-Panel
    VOLTS_PHASE_B_C         = ["00c8", 4]            # Voltage Phase BC             * Different on G-Panel
    VOLTS_PHASE_C_A         = ["00ca", 4]            # Voltage Phase CA             * Different on G-Panel
    AVG_VOLTAGE             = ["00cc", 4]            # Average Voltage              * Different on G-Panel
    TOTAL_POWER_KW          = ["00ce", 4]            # Total Power (kW)             * Different on G-Panel
    TOTAL_PF                = ["00d2", 4]            # Power Factor                 * Different on G-Panel
    OUTPUT_FREQUENCY        = ["00d6", 4]            # Output Frequency             * Different on G-Panel
    OUTPUT_RPM              = ["00da", 4]            # Output RPM                   * Different on G-Panel
    GEN_TIME_HR_MIN         = ["00e0", 2]            # Time HR:MIN
    GEN_TIME_SEC_DYWK       = ["00e1", 2]            # Time SEC:DayOfWeek
    GEN_TIME_MONTH_DAY      = ["00e2", 2]            # Time Month:DayofMonth
    GEN_TIME_YR             = ["00e3", 2]            # Time YR:UNK

    ALARM_ACK               = ["012e", 2]            # Number of alarm acks
    ACTIVE_ALARM_COUNT      = ["012f", 2]            # Number of active alarms
    ENGINE_HOURS            = ["0130", 4]            # Engine Hours High
    ENGINE_STATUS_CODE      = ["0132", 2]            # Engine Status Code

    START_BITS              = ["019c", 2]            # Start Bits
    START_BITS_2            = ["019d", 2]            # Start Bits 2
    START_BITS_3            = ["019e", 2]            # Start Bits 2
    KEY_SWITCH_STATE        = ["01a0", 2]            # High Byte is True if Auto, Low Byte True if Manual (False if Off)
    DI_STATE_1              = ["01a1", 2]            # * Different on G-Panel
    DI_STATE_2              = ["01a2", 2]            # * Different on G-Panel
    QUIETTEST_STATUS        = ["022b", 2]            # Quiet Test Status and reqest

    # EXT_SW_XX regististers are for HTS/MTS/STS Switches
    EXT_SW_GENERAL_STATUS   = ["0ea1", 2]            # External Switch General Status
    EXT_SW_MINIC_DIAGRAM    = ["0ea2", 2]            # Ext Switch Mimic Diagram
    EXT_SW_TARGET_VOLTAGE   = ["0ea7", 2]            # External Switch Target Voltage
    EXT_SW_TARGET_FREQ      = ["0eaa", 2]            # External Switch Target Freq
    EXT_SW_UTILITY_VOLTS_AB = ["0ead", 2]            # External Switch Utility AB Voltage
    EXT_SW_UTILITY_VOLTS_BC = ["0eae", 2]            # External Switch Utility BC Voltage
    EXT_SW_UTILITY_VOLTS_CA = ["0eaf", 2]            # External Switch Utility CA Voltage
    EXT_SW_UTILITY_AMPS_A   = ["0eb0", 2]            # External Switch Utility A Amps
    EXT_SW_UTILITY_AMPS_B   = ["0eb1", 2]            # External Switch Utility B Amps
    EXT_SW_UTILITY_AMPS_C   = ["0eb2", 2]            # External Switch Utility C Amps
    EXT_SW_UTILITY_AVG_VOLTS= ["0eb4", 2]            # External Switch Average Utility Volts
    EXT_SW_UTILITY_AVG_AMPS = ["0eb5", 2]            # External Switch Average Utility Amps
    EXT_SW_UTILITY_FREQ     = ["0eb6", 2]            # External Switch Utility Freq
    EXT_SW_UTILITY_PF       = ["0eb7", 2]            # External Switch Utility Power Factor
    EXT_SW_UTILITY_KW       = ["0eb8", 2]            # External Switch Utility Power
    EXT_SW_GEN_AVG_VOLT     = ["0eb9", 2]            # External Switch Generator Average Voltage
    EXT_SW_GEN_FREQ         = ["0eba", 2]            # External Switch Generator Freq
    EXT_SW_BACKUP_BATT_VOLTS= ["0ebc", 2]            # External Switch Backup Battery Voltage
    EXT_SW_VERSION          = ["0ebf", 2]            # External Switch SW Version
    EXT_SW_SELECTED         = ["0ec0", 2]            # External Switch Selected

    #---------------------GPanelReg::hexsort------------------------------------
    #@staticmethod
    def hexsort(self, e):
        try:
            return int(e[REGISTER],16)
        except:
            return 0
    #@staticmethod
    #---------------------GPanelReg::GetRegList---------------------------------
    def GetRegList(self):
        RetList = []
        for attr, value in GPanelReg.__dict__.items():
            if not callable(getattr(self,attr)) and not attr.startswith("__"):
                RetList.append(value)

        RetList.sort(key=self.hexsort)
        return RetList

#---------------------------GPanelIO:GPanelIO-----------------------------------
class GPanelIO(object):

    Inputs = {
        # Input 1
        ("0080", 0x8000) : "Switch In Auto",
        ("0080", 0x4000) : "Switch in Manual",
        ("0080", 0x2000) : "Alarm Acknowledg",
        ("0080", 0x1000) : "Emergency Stop",
        ("0080", 0x0800) : "Remote Start",
        ("0080", 0x0400) : "Battery Charger Fail",
        ("0080", 0x0200) : "Ruptured Basin",
        ("0080", 0x0100) : "User Configurable 08",
        ("0080", 0x0080) : "User Configurable 09",
        ("0080", 0x0040) : "User Configurable 10",
        ("0080", 0x0020) : "Stop Deadbus Connect",
        ("0080", 0x0010) : "Exercise Active",
        ("0080", 0x0008) : "Generator Switch Active",
        ("0080", 0x0004) : "Utility Switch Active",
        ("0080", 0x0002) : "Select Trip Status",
        ("0080", 0x0001) : "MCB Status",
        # Input 2
        ("0081", 0x8000) : "Phase Rotation Valid",
        ("0081", 0x4000) : "User Configurable 18",
        ("0081", 0x2000) : "User Configurable 19",
        ("0081", 0x1000) : "User Configurable 20",
        ("0081", 0x0800) : "User Configurable 21",
        ("0081", 0x0400) : "User Configurable 22",
        ("0081", 0x0200) : "User Configurable 23",
        ("0081", 0x0100) : "User Configurable 24",
        ("0081", 0x0080) : "Modem Selected",
        ("0081", 0x0040) : "Generator Overspeed",
        ("0081", 0x0020) : "DI-1",
        ("0081", 0x0010) : "DI-2",
        ("0081", 0x0008) : "DI-3 / Line Power",
        ("0081", 0x0004) : "DI-4 / Generator Power",
        ("0081", 0x0002) : "User Configurable 31",
        ("0081", 0x0001) : "User Configurable 32",
    }
    Outputs = {
        # Output1
        ("0082", 0x8000) : "Genertor in Alarm",
        ("0082", 0x4000) : "Genertor in Warning",
        # Output 2
        # Output 3
        ("0084", 0x0002) : "Switch in Auto",
        ("0084", 0x0001) : "Switch in Manual",
        # Output 4
        ("0085", 0x8000) : "Switch in Off",
        ("0085", 0x4000) : "Stopped",
        ("0085", 0x2000) : "Stopped in Alarm",
        ("0085", 0x1000) : "Stopped, Ready to Run",
        ("0085", 0x0800) : "Running",
        ("0085", 0x0400) : "Ready for Load",
        ("0085", 0x0200) : "Alarms Enabled",
        ("0085", 0x0100) : "In Warm Up",
        ("0085", 0x0080) : "In Cool Down",
        ("0085", 0x0040) : "Cranking",
        ("0085", 0x0020) : "Voltage Dropout",
        ("0085", 0x0010) : "Voltage Pickup",
        ("0085", 0x0008) : "In Line Interrupt Delay",
        ("0085", 0x0004) : "In Return to Utility Delay",
        ("0085", 0x0002) : "In TDN",
        ("0085", 0x0001) : "Load Shedding",
        # Output 5
        ("0086", 0x8000) : "Out of Service",
        ("0086", 0x4000) : "Needs Service",
        ("0086", 0x2000) : "Battery Charger Fail",
        ("0086", 0x1000) : "Line Power",
        ("0086", 0x0800) : "Generator Power",
        ("0086", 0x0400) : "Gas Reduced - Knock",
        ("0086", 0x0200) : "All Engines on Line",
        ("0086", 0x0100) : "Shutdown",
        # Output 6
        ("0087", 0x0010) : "User Configurable 92",
        ("0087", 0x0008) : "User Configurable 93",
        ("0087", 0x0004) : "User Configurable 94",
        ("0087", 0x0002) : "User Configurable 95",
        ("0087", 0x0001) : "User Configurable 96",
        # Output 7
        ("0088", 0x8000) : "User Configurable 97",
        ("0088", 0x4000) : "User Configurable 98",
        ("0088", 0x2000) : "User Configurable 99",
        ("0088", 0x1000) : "User Configurable 100",
        ("0088", 0x0800) : "User Configurable 101",
        ("0088", 0x0400) : "User Configurable 102",
        ("0088", 0x0200) : "User Configurable 103",
        ("0088", 0x0100) : "User Configurable 104",
        ("0088", 0x0080) : "User Configurable 105",
        ("0088", 0x0040) : "User Configurable 106",
        ("0088", 0x0020) : "User Configurable 107",
        ("0088", 0x0010) : "User Configurable 108",
        ("0088", 0x0008) : "User Configurable 109",
        ("0088", 0x0004) : "User Configurable 110",
        ("0088", 0x0002) : "User Configurable 111",
        ("0088", 0x0001) : "User Configurable 112",
        # Output 8
        ("0089", 0x8000) : "User Configurable 113",
        ("0089", 0x4000) : "User Configurable 114",
        ("0089", 0x2000) : "User Configurable 115",
        ("0089", 0x1000) : "User Configurable 116",
        ("0089", 0x0800) : "User Configurable 117",
        ("0089", 0x0400) : "User Configurable 118",
        ("0089", 0x0100) : "On Line in Backup Mode",
    }
    Alarms = {
        # Output 1
        ("0082", 0x2000) : "Low Oil Pressure Alarm",
        ("0082", 0x1000) : "Low Oil Pressure Warning",
        ("0082", 0x0800) : "High Coolant Temp Warning",
        ("0082", 0x0400) : "High Coolant Temp Alarm",
        ("0082", 0x0200) : "Low Coolant Temp Warning",
        ("0082", 0x0100) : "High Oil Temp Warning",
        ("0082", 0x0080) : "High Oil Temp Alarm",
        ("0082", 0x0040) : "Low Battery Voltage Warning",
        ("0082", 0x0020) : "High Batter Voltage Alarm",
        ("0082", 0x0010) : "Overspeed Alarm",
        ("0082", 0x0008) : "Underspeed Alarm",
        ("0082", 0x0004) : "Overvoltage Alarm",
        ("0082", 0x0002) : "Undervoltage Alarm",
        ("0082", 0x0001) : "Over Frequency Alarm",

        # Output 2
        ("0083", 0x8000) : "Under Frequency Alarm",
        ("0083", 0x4000) : "High Fuel Alarm",
        ("0083", 0x2000) : "Low Fuel Warning",
        ("0083", 0x1000) : "Low Fuel Alarm",
        ("0083", 0x0800) : "Fail to Start Alarm",
        ("0083", 0x0400) : "Coolant Level Alarm",
        ("0083", 0x0200) : "RPM Sensor Fail Alarm",
        ("0083", 0x0100) : "Stop Inhibit Alarm",
        ("0083", 0x0080) : "Emergency Stop Alarm",
        ("0083", 0x0040) : "Oil Pressure Sensor Fault",
        ("0083", 0x0020) : "Oil Temp Sensor Fault",
        ("0083", 0x0010) : "Coolant Temp Sensor Fault",
        ("0083", 0x0008) : "Knock Unit Fault",
        ("0083", 0x0004) : "Knock Not Calibrated",
        ("0083", 0x0002) : "Transfer Switch Error Alarm",
        ("0083", 0x0001) : "Reverse Power Alarm",

        # Output 3
        ("0084", 0x8000) : "MCB is Open",
        ("0084", 0x4000) : "Oil Filter Blocked Alarm",
        ("0084", 0x2000) : "Air Filter Blocked Alarm",
        ("0084", 0x1000) : "Oxygen Sensor Fault",
        ("0084", 0x0800) : "Alternator Problem",
        ("0084", 0x0400) : "Gas Pressure Warning",
        ("0084", 0x0200) : "Exhaust Temp Warning",
        ("0084", 0x0100) : "Exhaust Temp Alarm",
        ("0084", 0x0080) : "Flame Detection",
        ("0084", 0x0040) : "Carbon Monixide Alarm",
        ("0084", 0x0020) : "Vacume Sensor Fault Alarm",
        ("0084", 0x0010) : "Cam Mapped O P",
        ("0084", 0x0008) : "Crank Mapped O P",
        ("0084", 0x0004) : "Gas Flow Sensor Fault Alarm",
        # Output 4
        # Output 5
        ("0086", 0x0080) : "Check Voltage Phase Rotation",
        ("0086", 0x0040) : "Check Current Phase Rotation",
        ("0086", 0x0020) : "ILC Alarm / Warning 1",
        ("0086", 0x0010) : "ILC Alarm / Warning 2",
        ("0086", 0x0008) : "Gas Shutoff - Knock",
        ("0086", 0x0004) : "High Inlet Manifold Temp Alarm",
        ("0086", 0x0002) : "High Inlest Manifold Temp Warning",
        ("0086", 0x0001) : "Low Turbo Pressure - Gas",
        # Output 6
        ("0087", 0x8000) : "Low Turbo Pressure - Diesel",
        ("0087", 0x4000) : "Low Gass Pressure Shutoff",
        ("0087", 0x2000) : "Low Gas Pressure Disable",
        ("0087", 0x1000) : "High Gas Pressure Disable",
        ("0087", 0x0800) : "CAC Bypass Valve Fault",
        ("0087", 0x0400) : "Knock Sample Missing",
        ("0087", 0x0200) : "Disable Checksync Board",
        ("0087", 0x0100) : "Fault Relay Active",
        ("0087", 0x0080) : "Annunciator Light",
        ("0087", 0x0040) : "PC-SC Comms Failed",
        ("0087", 0x0020) : "Check if ILC is Running",
        # Output 7
        # Output 8
        ("0089", 0x0200) : "RPM Missing in Crank",

    }

#---------------------------RegisterStringEnum:RegisterStringEnum---------------
class RegisterStringEnum(object):

    # These Values are the same for H-Panel, and G-Panel
    # Note, the first value is the register (in hex string), the second is the numbert of bytes
    # third is if the result is stored as a string
    CONTROLLER_NAME             =   ["0020", 0x40, True]            #
    VERSION_DATE                =   ["0040", 0x40, True]
    LAST_POWER_FAIL             =   ["0104", 0x08, False]
    POWER_UP_TIME               =   ["0108", 0x08, False]
    ENGINE_STATUS               =   ["0133", 0x40, True]
    GENERATOR_STATUS            =   ["0153", 0x40, True]
    GENERATOR_DATA_TIME         =   ["0173", 0x40, False]
    MIN_GENLINK_VERSION         =   ["0060", 0x40, True]
    MAINT_LIFE                  =   ["0193", 0x12, False]
    ENGINE_KW_HOURS             =   ["0236", 0x08, False]

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
        for attr, value in RegisterStringEnum.__dict__.items():
            if not callable(getattr(RegisterStringEnum(),attr)) and not attr.startswith("__"):
                RetList.append(value)
        RetList.sort(key=RegisterStringEnum.hexsort)
        return RetList

#---------------------Input1::Input1--------------------------------------------
# Enum for register Input1
class Input1(object):                   # * Different on G-Panel
    AUTO_SWITCH         = 0x8000
    MANUAL_SWITCH       = 0x4000
    EMERGENCY_STOP      = 0x2000        # * Different on G-Panel
    REMOTE_START        = 0x1000        # * Different on G-Panel
    DI1_BAT_CHRGR_FAIL  = 0x0800        # * Different on G-Panel
    DI2_FUEL_PRESSURE   = 0x0400        # * Different on G-Panel
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
    COMMON_ALARM        = 0x8000        # Same on H and G Panel
    COMMON_WARNING      = 0x4000        # Same on H and G Panel
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


class HPanel(GeneratorController):

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
        self.AlarmAccessLock = threading.RLock()     # lock to synchronize access to the logs
        self.EventAccessLock = threading.RLock()     # lock to synchronize access to the logs
        self.ControllerDetected = False
        self.HPanelDetected = True          # False if G-Panel
        self.Reg = HPanelReg()
        self.IO = HPanelIO()

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
                self.ModBus = ModbusFile(self.UpdateRegisterList,
                    inputfile = self.SimulationFile,
                    config = self.config)
            else:
                self.ModBus = ModbusProtocol(self.UpdateRegisterList,
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
            self.HTSTransferSwitch = self.config.ReadValue('hts_transfer_switch', return_type = bool, default = False)
            self.FuelUnits = self.config.ReadValue('fuel_units', default = "gal")
            self.FuelHalfRate = self.config.ReadValue('half_rate', return_type = float, default = 0.0)
            self.FuelFullRate = self.config.ReadValue('full_rate', return_type = float, default = 0.0)
            self.UseFuelSensor = self.config.ReadValue('usesensorforfuelgauge', return_type = bool, default = True)

        except Exception as e1:
            self.FatalError("Missing config file or config file entries (HPanel): " + str(e1))
            return False

        return True

    #-------------HPanel:IdentifyController-------------------------------------
    def IdentifyController(self):

        try:
            if self.ControllerDetected:
                return True

            ControllerString = self.HexStringToString(self.ModBus.ProcessTransaction(RegisterStringEnum.CONTROLLER_NAME[REGISTER],
                RegisterStringEnum.CONTROLLER_NAME[LENGTH] / 2))

            ControllerString = str(ControllerString)
            if not len(ControllerString):
                self.LogError("Unable to ID controller, possiby not receiving data.")
                self.ControllerDetected = False
                return False
            self.ControllerDetected = True
            if "h-100" in ControllerString.lower():
                self.LogError("Detected H-100 Controller")
                self.HPanelDetected = True
                self.Reg = HPanelReg()
                self.IO = HPanelIO()
            else:
                self.LogError("Detected G-Panel Controller")
                self.HPanelDetected = False
                self.Reg = GPanelReg()
                self.IO = GPanelIO()
            return True
        except Exception as e1:
            self.LogErrorLine("Error in IdentifyController: " + str(e1))
            return False
    #-------------HPanel:InitDevice---------------------------------------------
    # One time reads, and read all registers once
    def InitDevice(self):

        try:
            self.IdentifyController()
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
            with self.ExternalDataLock:
                self.TileList = []
                Tile = MyTile(self.log, title = "Battery Voltage", units = "V", type = "batteryvolts", nominal = self.NominalBatteryVolts,
                    callback = self.GetParameter,
                    callbackparameters = (self.Reg.BATTERY_VOLTS[REGISTER],  None, 100.0, False, False, True))
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

                Tile = MyTile(self.log, title = "Voltage (Avg)", units = "V", type = "linevolts", nominal = NominalVoltage,
                callback = self.GetParameter,
                callbackparameters = (self.Reg.AVG_VOLTAGE[REGISTER], None, None, False, True, False))
                self.TileList.append(Tile)

                NominalCurrent = int(self.NominalKW) * 1000 / NominalVoltage
                Tile = MyTile(self.log, title = "Current (Avg)", units = "A", type = "current", nominal = NominalCurrent,
                callback = self.GetParameter,
                callbackparameters = (self.Reg.AVG_CURRENT[REGISTER], None, None, False, True, False))
                self.TileList.append(Tile)

                if self.NominalFreq == None or self.NominalFreq == "" or self.NominalFreq == "Unknown":
                    self.NominalFreq = "60"
                Tile = MyTile(self.log, title = "Frequency", units = "Hz", type = "frequency", nominal = int(self.NominalFreq),
                callback = self.GetParameter,
                callbackparameters = (self.Reg.OUTPUT_FREQUENCY[REGISTER], None, 10.0, False, False, True))
                self.TileList.append(Tile)

                if self.NominalRPM == None or self.NominalRPM == "" or self.NominalRPM == "Unknown":
                    self.NominalRPM = "3600"
                Tile = MyTile(self.log, title = "RPM", type = "rpm", nominal = int(self.NominalRPM),
                callback = self.GetParameter,
                callbackparameters = (self.Reg.OUTPUT_RPM[REGISTER], None, None, False, True, False))
                self.TileList.append(Tile)

                # water temp between 170 and 200 is a normal range for a gen. most have a 180f thermostat
                Tile = MyTile(self.log, title = "Coolant Temp", units = "F", type = "temperature", subtype = "coolant", nominal = 180, maximum = 300,
                callback = self.GetParameter,
                callbackparameters = (self.Reg.COOLANT_TEMP[REGISTER], None, None, False, True, False))
                self.TileList.append(Tile)

                if self.HTSTransferSwitch:
                    Tile = MyTile(self.log, title = "Utility Voltage (Avg)", units = "V", type = "linevolts", nominal = NominalVoltage,
                    callback = self.GetParameter,
                    callbackparameters = (self.Reg.EXT_SW_UTILITY_AVG_VOLTS[REGISTER], None, None, False, True, False))
                    self.TileList.append(Tile)
                    Tile = MyTile(self.log, title = "Utility Frequency", units = "Hz", type = "frequency", nominal = int(self.NominalFreq),
                    callback = self.GetParameter,
                    callbackparameters = (self.Reg.EXT_SW_UTILITY_FREQ[REGISTER], None, 100.0, False, False, True))
                    self.TileList.append(Tile)
                    Tile = MyTile(self.log, title = "Utility Power", units = "kW", type = "power", nominal = int(self.NominalKW),
                    callback = self.GetParameter,
                    callbackparameters = (self.Reg.EXT_SW_UTILITY_KW[REGISTER], None, None, False, True, False))
                    self.TileList.append(Tile)

                if self.FuelSensorSupported():
                    Tile = MyTile(self.log, title = "Fuel", units = "%", type = "fuel", nominal = 100, callback = self.GetFuelSensor, callbackparameters = (True,))
                    self.TileList.append(Tile)
                elif self.ExternalFuelDataSupported():
                    Tile = MyTile(self.log, title = "External Tank", units = "%", type = "fuel", nominal = 100, callback = self.GetExternalFuelPercentage, callbackparameters = (True,))
                    self.TileList.append(Tile)
                elif self.FuelConsumptionGaugeSupported():    # no gauge for NG
                    if self.UseMetric:
                        Units = "L"         # no gauge for NG
                    else:
                        Units = "gal"       # no gauge for NG
                    Tile = MyTile(self.log, title = "Estimated Fuel", units = Units, type = "fuel", nominal = int(self.TankSize), callback = self.GetEstimatedFuelInTank, callbackparameters = (True,))
                    self.TileList.append(Tile)

                if self.PowerMeterIsSupported():
                    Tile = MyTile(self.log, title = "Power Output", units = "kW", type = "power", nominal = int(self.NominalKW),
                    callback = self.GetParameter,
                    callbackparameters = (self.Reg.TOTAL_POWER_KW[REGISTER], None, None, False, True, False))
                    self.TileList.append(Tile)

                    Tile = MyTile(self.log, title = "kW Output", type = "powergraph", nominal = int(self.NominalKW),
                    callback = self.GetParameter,
                    callbackparameters = (self.Reg.TOTAL_POWER_KW[REGISTER], None, None, False, True, False))
                    self.TileList.append(Tile)

        except Exception as e1:
            self.LogErrorLine("Error in SetupTiles: " + str(e1))

    #-------------HPanel:CheckModelSpecificInfo---------------------------------
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

            if self.Model == "Unknown" or not len(self.Model) or "generic" in self.Model.lower():
                if self.HPanelDetected:
                    self.Model = "Generac H-100 Industrial Generator"
                else:
                    self.Model = "Generac G-Panel Industrial Generator"
                self.config.WriteValue("model", self.Model)

            if self.FuelType == "Unknown" or not len(self.FuelType):
                self.FuelType = "Diesel"
                self.config.WriteValue("fueltype", self.FuelType)
        except Exception as e1:
            self.LogErrorLine("Error in CheckModelSpecificInfo: " + str(e1))
        return
    #-------------HPanel:GetIntFromString---------------------------------------
    def GetIntFromString(self, input_string, byte_offset, length = 1, decimal = False):

        try:
            if len(input_string) < byte_offset + length:
                self.LogError("Invalid length in GetIntFromString: " + str(input_string))
                return 0
            StringOffset = byte_offset * 2
            StringOffsetEnd = StringOffset + (length *2)
            if StringOffset == StringOffsetEnd:
                if decimal:
                    return int(input_string[StringOffsetd])
                return int(input_string[StringOffset], 16)
            else:
                if decimal:
                    return int(input_string[StringOffset:StringOffsetEnd])
                return int(input_string[StringOffset:StringOffsetEnd], 16)
        except Exception as e1:
            self.LogErrorLine("Error in GetIntFromString: " + str(e1))
            return 0
    #-------------HPanel:GetParameterStringValue--------------------------------
    def GetParameterStringValue(self, Register, ReturnString = False):

        StringValue = self.Strings.get(Register, "")
        if ReturnString:
            return self.HexStringToString(StringValue)
        return self.Strings.get(Register, "")

    #-------------HPanel:GetParameterFileValue----------------------------------
    def GetParameterFileValue(self, Register, ReturnString = False):

        StringValue = self.FileData.get(Register, "")
        if ReturnString:
            return self.HexStringToString(StringValue)
        return self.FileData.get(Register, "")

    #-------------HPanel:GetGeneratorFileData-----------------------------------
    def GetGeneratorFileData(self):

        try:
            # Read the nameplate dataGet Serial Number
            self.ModBus.ProcessFileReadTransaction(NAMEPLATE_DATA_FILE_RECORD, NAMEPLATE_DATA_LENGTH / 2 )
            # Read Misc Engine data
            self.ModBus.ProcessFileReadTransaction(MISC_GEN_FILE_RECORD, MISC_GEN_LENGTH / 2 )
            # Read Engine Data
            self.ModBus.ProcessFileReadTransaction(ENGINE_DATA_FILE_RECORD, ENGINE_DATA_FILE_RECORD_LENGTH / 2 )
            # Read Govonor Data
            self.ModBus.ProcessFileReadTransaction(GOV_DATA_FILE_RECORD, GOV_DATA_FILE_RECORD_LENGTH / 2 )
            # Read Secondary Govonor Data
            self.ModBus.ProcessFileReadTransaction(GOV_DATA_SEC_FILE_RECORD, GOV_DATA_SEC_FILE_RECORD_LENGTH / 2 )
            # Read Regulator Data
            self.ModBus.ProcessFileReadTransaction(REGULATOR_FILE_RECORD, REGULATOR_FILE_RECORD_LENGTH / 2 )

            self.GetGeneratorLogFileData()
        except Exception as e1:
            self.LogErrorLine("Error in GetGeneratorFileData: " + str(e1))

    #------------ HPanel:WaitAndPergeforTimeout --------------------------------
    def WaitAndPergeforTimeout(self):
        # if we get here a timeout occured, and we have recieved at least one good packet
        # this logic is to keep from receiving a packet that we have already requested once we
        # timeout and start to request another
        # Wait for a bit to allow any missed response from the controller to arrive
        # otherwise this could get us out of sync
        # This assumes MasterEmulation is called from ProcessThread
        if self.WaitForExit("ProcessThread", float(self.ModBus.ModBusPacketTimoutMS / 1000.0)):  #
            return
        self.ModBus.Flush()
    #------------ HPanel:GetGeneratorLogFileData -------------------------------
    def GetGeneratorLogFileData(self):

        try:
            for RegValue in range(EVENT_LOG_START + EVENT_LOG_ENTRIES -1 , EVENT_LOG_START -1, -1):
                Register = "%04x" % RegValue
                localTimeoutCount = self.ModBus.ComTimoutError
                localSyncError = self.ModBus.ComSyncError
                self.ModBus.ProcessFileReadTransaction(Register, EVENT_LOG_LENGTH /2)
                if ((localSyncError != self.ModBus.ComSyncError or localTimeoutCount != self.ModBus.ComTimoutError)
                    and self.ModBus.RxPacketCount):
                    self.WaitAndPergeforTimeout()
            for RegValue in range(ALARM_LOG_START + ALARM_LOG_ENTRIES -1, ALARM_LOG_START -1, -1):
                Register = "%04x" % RegValue
                localTimeoutCount = self.ModBus.ComTimoutError
                localSyncError = self.ModBus.ComSyncError
                self.ModBus.ProcessFileReadTransaction(Register, ALARM_LOG_LENGTH /2)
                if ((localSyncError != self.ModBus.ComSyncError or localTimeoutCount != self.ModBus.ComTimoutError)
                    and self.ModBus.RxPacketCount):
                    self.WaitAndPergeforTimeout()
        except Exception as e1:
            self.LogErrorLine("Error in GetGeneratorLogFileData: " + str(e1))

    #-------------HPanel:GetGeneratorStrings------------------------------------
    def GetGeneratorStrings(self):

        try:
            for RegisterList in RegisterStringEnum.GetRegList():
                try:
                    if self.IsStopping:
                        return
                    localTimeoutCount = self.ModBus.ComTimoutError
                    localSyncError = self.ModBus.ComSyncError
                    self.ModBus.ProcessTransaction(RegisterList[REGISTER], RegisterList[LENGTH] / 2)
                    if ((localSyncError != self.ModBus.ComSyncError or localTimeoutCount != self.ModBus.ComTimoutError)
                        and self.ModBus.RxPacketCount):
                        self.WaitAndPergeforTimeout()

                except Exception as e1:
                    self.LogErrorLine("Error in GetGeneratorStrings: " + str(e1))

        except Exception as e1:
            self.LogErrorLine("Error in GetGeneratorStrings: " + str(e1))

    #-------------HPanel:MasterEmulation----------------------------------------
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
                    self.ModBus.ProcessTransaction(RegisterList[REGISTER], RegisterList[LENGTH] / 2)
                    if ((localSyncError != self.ModBus.ComSyncError or localTimeoutCount != self.ModBus.ComTimoutError)
                        and self.ModBus.RxPacketCount):
                        self.WaitAndPergeforTimeout()
                except Exception as e1:
                    self.LogErrorLine("Error in MasterEmulation: " + str(e1))

            self.GetGeneratorStrings()
            self.GetGeneratorFileData()
            self.CheckForAlarmEvent.set()
        except Exception as e1:
            self.LogErrorLine("Error in MasterEmulation: " + str(e1))

    #------------ HPanel:GetTransferStatus -------------------------------------
    def GetTransferStatus(self):

        LineState = "Unknown"
        if self.HPanelDetected:
            if self.GetParameterBit(self.Reg.OUTPUT_6[REGISTER], Output6.LINE_POWER):
                LineState = "Utility"
            if self.GetParameterBit(self.Reg.OUTPUT_6[REGISTER], Output6.GEN_POWER):
                LineState = "Generator"
        else:
            if self.GetParameterBit(self.Reg.OUTPUT_5[REGISTER], 0x1000):
                LineState = "Utility"
            if self.GetParameterBit(self.Reg.OUTPUT_5[REGISTER], 0x0800):
                LineState = "Generator"
        return LineState

    #------------ HPanel:GetCondition ------------------------------------------
    def GetCondition(self, RegList = None, type = None):

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
                self.LogError("Error in GetCondition: Invalid input for type: " + str(type))
                return []

            StringList = []
            for Register in RegList:
                Output = self.GetParameter(Register , ReturnInt = True)
                Mask = 1
                while (Output):
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

    #------------ HPanel:CheckForAlarms ----------------------------------------
    def CheckForAlarms(self):

        try:
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
                self.MessagePipe.SendMessage(msgsubject , msgbody, msgtype = MessageType)

            # Check for Alarms
            if self.SystemInAlarm():
                if not self.CurrentAlarmState:
                    msgsubject = "Generator Notice: ALARM Active at " + self.SiteName
                    msgbody += self.DisplayStatus()
                    self.MessagePipe.SendMessage(msgsubject , msgbody, msgtype = "warn")
            else:
                if self.CurrentAlarmState:
                    msgsubject = "Generator Notice: ALARM Clear at " + self.SiteName
                    msgbody += self.DisplayStatus()
                    self.MessagePipe.SendMessage(msgsubject , msgbody, msgtype = "warn")

            self.CurrentAlarmState = self.SystemInAlarm()

        except Exception as e1:
            self.LogErrorLine("Error in CheckForAlarms: " + str(e1))

        return

    #------------ HPanel:RegisterIsFileRecord ------------------------------
    def RegisterIsFileRecord(self, Register):

        try:
            RegInt = int(Register,16)

            if Register == NAMEPLATE_DATA_FILE_RECORD:
                return True
            if Register == MISC_GEN_FILE_RECORD:
                return True
            if Register == ENGINE_DATA_FILE_RECORD:
                return True
            if Register == GOV_DATA_FILE_RECORD:
                return True
            if Register == GOV_DATA_SEC_FILE_RECORD:
                return True
            if Register == REGULATOR_FILE_RECORD:
                return True
            if RegInt >= ALARM_LOG_START or RegInt <= ALARM_LOG_START + ALARM_LOG_ENTRIES:
                return True
            if RegInt >= EVENT_LOG_START or RegInt <= EVENT_LOG_START + EVENT_LOG_ENTRIES:
                return True

        except Exception as e1:
            self.LogErrorLine("Error in RegisterIsFileRecord: " + str(e1))

        return False

    #------------ HPanel:RegisterIsStringRegister ------------------------------
    def RegisterIsStringRegister(self, Register):

        try:
            StringList = RegisterStringEnum.GetRegList()
            for StringReg in StringList:
                if Register.lower() == StringReg[REGISTER].lower():
                    return True
        except Exception as e1:
            self.LogErrorLine("Error in RegisterIsBaseRegister: " + str(e1))
        return False

    #------------ HPanel:RegisterIsBaseRegister --------------------------------
    def RegisterIsBaseRegister(self, Register, Value):

        try:
            RegisterList = self.Reg.GetRegList()
            for ListReg in RegisterList:
                if Register.lower() == ListReg[REGISTER].lower():
                    # TODO check value length
                    return True
        except Exception as e1:
            self.LogErrorLine("Error in RegisterIsBaseRegister: " + str(e1))
        return False

    #------------ HPanel:UpdateRegisterList ------------------------------------
    def UpdateRegisterList(self, Register, Value, IsString = False, IsFile = False):

        try:
            if len(Register) != 4:
                self.LogError("Validation Error: Invalid register value in UpdateRegisterList: %s %s" % (Register, Value))
                return False

            if not IsFile and self.RegisterIsBaseRegister(Register, Value):
                # TODO validate register length
                self.Registers[Register] = Value
            elif not IsFile and self.RegisterIsStringRegister(Register):
                # TODO validate register string length
                self.Strings[Register] = Value
            elif IsFile and self.RegisterIsFileRecord(Register):
                # todo validate file data length
                self.FileData[Register] = Value
            else:
                self.LogError("Error in UpdateRegisterList: Unknown Register " + Register + ":" + Value + ": IsFile: " + str(IsFile) + ": " + "IsString: " + str(IsString))
                return False
            return True
        except Exception as e1:
            self.LogErrorLine("Error in UpdateRegisterList: " + str(e1))
            return False

    #---------------------HPanel::SystemInAlarm---------------------------------
    # return True if generator is in alarm, else False
    def SystemInAlarm(self):

        try:
            if self.GetParameter(self.Reg.ACTIVE_ALARM_COUNT[REGISTER], ReturnInt = True) != 0:
                return True
            if self.GetParameter(self.Reg.ALARM_ACK[REGISTER], ReturnInt = True) != 0:
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in SystemInAlarm: " + str(e1))
            return False
    #------------ HPanel:GetSwitchState ----------------------------------------
    def GetSwitchState(self):

        try:
            SwitchState = self.GetParameter(self.Reg.KEY_SWITCH_STATE[REGISTER], ReturnInt = True)
            if SwitchState & 0x00FF:
                return "Manual"
            elif SwitchState & 0xFF00:
                return "Auto"
            else:
                return "Off"
        except Exception as e1:
            self.LogErrorLine("Error in GetSwitchState: " + str(e1))
            return "Unknown"

    #------------ HPanel:GetEngineState ----------------------------------------
    def GetEngineState(self):

        try:
            # The Engine Status should return these values:
            #   "Stopped, Key SW Off"       The engine is stopped and the key switch is in the OFF position.
            #   "Running from Manual"       The engine is starting or running and the key switch is in the MANUAL position.
            #   "Running from 2-wire"       The engine is starting or running because the 2-wire start signal was activated and the key switch is in the AUTO position.
            #   "Running from serial"       The engine is starting or running because the GenLink commanded it to start and the key switch is in the AUTO position.
            #   "Running exercise"          The engine is starting or running because internal exercise was activated and the key switch is in the AUTO position.
            #   "Stopped, Key SW Auto"      The engine is stopped and the key switch is in the AUTO position.
            #   "Running, QuietTest"        The engine is starting or running because QuietTest was activated and the key switch is in the AUTO position.
            #   "Running, HTS Xfer SW"      The engine is starting or running because the HTS(s) indicated a need for the gen- erator power and the key switch is in the AUTO position.
            #   "Resetting"                 The generator control system is resetting.
            #   "Stopped"                   Generator is stopped and not preheating.
            #   "Stopped, Preheating"       Generator is stopped and preheating.
            #   "Cranking"                  Generator is starting and not preheating.
            #   "Cranking, Preheating"      Generator is starting and preheating.
            #   "Pause between starts"      Generator is pausing between consecutive start attempts.
            #   "Started, not to speed"     Generator is started, but has not attained normal running speed yet.
            #   "Warming, Alarms Off"       Generator is started and is up to speed, but is waiting for warmup timer to expire.
            #   "Warmed Up, Alarms Off"     Generator is started and warmed up, but the hold-off alarms are not yet enabled.
            #   "Warming, Alarms On"        Generator is started and the hold-off alarms are enabled, but is waiting for warm up timer to expire.
            #   "Warmed Up, Alarms On"      Generator is started, warmed up, and the hold-off alarms are enabled.
            #   "Running, cooling down"     Generator is still running, but waiting for cool down timer to expire.
            #   "Stopping"                  Generator is running down after being turned off normally.
            #   "Stopping due to Alrm"      Generator is running down after being turned off due to a shutdown alarm.
            #   "Stopped due to Alarm"      Generator is stopped due to a shutdown alarm.

            State = self.GetParameterStringValue(RegisterStringEnum.ENGINE_STATUS[REGISTER], RegisterStringEnum.ENGINE_STATUS[RET_STRING])

            if len(State):
                return str(State)
            else:
                return "Unknown"
        except Exception as e1:
            self.LogErrorLine("Error in GetEngineState (1): " + str(e1))
            return "Unknown"

    #------------ HPanel:GetDateTime -------------------------------------------
    def GetDateTime(self):

        ErrorReturn = "Unknown"
        try:
            Value = self.GetParameter(self.Reg.GEN_TIME_HR_MIN[REGISTER])
            if not len(Value):
                return ErrorReturn

            TempInt = int(Value)
            Hour = TempInt >> 8
            Minute = TempInt & 0x00ff
            if Hour > 23 or Minute >= 60:
                self.LogError("Error in GetDateTime: Invalid Hour or Minute: " + str(Hour) + ", " + str(Minute))
                return ErrorReturn

            Value = self.GetParameter(self.Reg.GEN_TIME_SEC_DYWK[REGISTER])
            if not len(Value):
                return ErrorReturn
            TempInt = int(Value)
            Second = TempInt >> 8
            DayOfWeek = TempInt & 0x00ff
            if Second >= 60 or DayOfWeek > 7:
                self.LogError("Error in GetDateTime: Invalid Seconds or Day of Week: " + str(Second) + ", " + str(DayOfWeek))
                return ErrorReturn

            Value = self.GetParameter(self.Reg.GEN_TIME_MONTH_DAY[REGISTER])
            if not len(Value):
                return ErrorReturn
            TempInt = int(Value)
            Month = TempInt >> 8
            DayOfMonth = TempInt & 0x00ff
            if Month > 12 or Month == 0 or DayOfMonth == 0 or DayOfMonth > 31:
                self.LogError("Error in GetDateTime: Invalid Month or Day of Month: " + str(Month) + ", " + str(DayOfMonth))
                return ErrorReturn

            Value = self.GetParameter(self.Reg.GEN_TIME_YR[REGISTER])
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

    #------------ HPanel::GetTimeFromString ------------------------------------
    def GetTimeFromString(self, input_string):

        try:
            # Format is: 00 31 52 d8 02 15 10 18
            if len(input_string) < 16:
                return "Unknown"

            OutString = ""
            Date = "%02d/%02d/%02d" % (self.GetIntFromString(input_string, 6, 1, decimal = True),
                self.GetIntFromString(input_string, 5, 1, decimal = True),
                self.GetIntFromString(input_string, 7, 1, decimal = True))

            AMorPM = self.GetIntFromString(input_string, 3, 1)

            if AMorPM == 0xd1:
                # PM
                Hour = self.GetIntFromString(input_string, 4, 1, decimal = True) + 12
            else:
                Hour = self.GetIntFromString(input_string, 4, 1, decimal = True)

            Time = "%02d:%02d:%02d" % (Hour, self.GetIntFromString(input_string, 2, 1, decimal = True),
                self.GetIntFromString(input_string, 1, 1, decimal = True))

            return Date + " " + Time
        except Exception as e1:
            self.LogErrorLine("Error in GetTimeFromString: " + str(e1))
            return "Unknown"
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
            StartInfo["PowerGraph"] = self.PowerMeterIsSupported()
            StartInfo["NominalBatteryVolts"] = self.NominalBatteryVolts
            StartInfo["FuelCalculation"] = self.FuelTankCalculationSupported()
            StartInfo["FuelSensor"] = self.FuelSensorSupported()
            StartInfo["FuelConsumption"] = self.FuelConsumptionSupported()
            StartInfo["Controller"] = self.GetController()
            StartInfo["UtilityVoltage"] = False
            StartInfo["RemoteCommands"] = True      # Remote Start/ Stop/ StartTransfer
            StartInfo["ResetAlarms"] = False
            StartInfo["AckAlarms"] = True
            StartInfo["RemoteTransfer"] = self.HTSTransferSwitch    # Remote start and transfer command
            StartInfo["RemoteButtons"] = False      # Remote controll of Off/Auto/Manual
            StartInfo["ExerciseControls"] = False  # self.SmartSwitch
            StartInfo["WriteQuietMode"] = False

            if not NoTile:
                StartInfo["pages"] = {
                                "status":True,
                                "maint":True,
                                "outage":False,
                                "logs":True,
                                "monitor": True,
                                "maintlog" : True,
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
            Status["OutputVoltage"] = self.GetParameter(self.Reg.AVG_VOLTAGE[REGISTER],"V")
            Status["BatteryVoltage"] = self.GetParameter(self.Reg.BATTERY_VOLTS[REGISTER], "V", 100.0)
            Status["UtilityVoltage"] = "0"
            Status["RPM"] = self.GetParameter(self.Reg.OUTPUT_RPM[REGISTER])
            Status["Frequency"] = self.GetParameter(self.Reg.OUTPUT_FREQUENCY[REGISTER], "Hz", 10.0)
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
            LocalEvent = []
            for RegValue in range(EVENT_LOG_START + EVENT_LOG_ENTRIES -1 , EVENT_LOG_START -1, -1):
                Register = "%04x" % RegValue
                LogEntry = self.GetParameterFileValue(Register, ReturnString = True)
                LogEntry = self.ParseLogEntry(LogEntry, Type = "event")
                if not len(LogEntry):
                    continue
                if "undefined" in LogEntry:
                    continue

                LocalEvent.append(LogEntry)

            LocalAlarm = []
            for RegValue in range(ALARM_LOG_START + ALARM_LOG_ENTRIES -1, ALARM_LOG_START -1, -1):
                Register = "%04x" % RegValue
                LogEntry = self.GetParameterFileValue(Register, ReturnString = True)
                LogEntry = self.ParseLogEntry(LogEntry, Type = "alarm")
                if not len(LogEntry):
                    continue

                LocalAlarm.append(LogEntry)

            LogList = [ {"Alarm Log": LocalAlarm},
                        {"Run Log": LocalEvent}]

            RetValue["Logs"] = LogList


        except Exception as e1:
            self.LogErrorLine("Error in DisplayLogs: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(RetValue,""))

        return RetValue

    #------------ HPanel::DisplayMaintenance -----------------------------------
    def DisplayMaintenance (self, DictOut = False, JSONNum = False):

        try:
            # use ordered dict to maintain order of output
            # ordered dict to handle evo vs nexus functions
            Maintenance = collections.OrderedDict()
            Maintenance["Maintenance"] = []

            Maintenance["Maintenance"].append({"Model" : self.Model})
            NamePlateData = self.GetParameterFileValue(NAMEPLATE_DATA_FILE_RECORD, ReturnString = True)
            if len(NamePlateData):
                Maintenance["Maintenance"].append({"Name Plate Info" : NamePlateData})
            Maintenance["Maintenance"].append({"Controller Detected" : self.GetController()})
            Maintenance["Maintenance"].append({"Controller Software Version" : self.GetParameterStringValue(RegisterStringEnum.VERSION_DATE[REGISTER], RegisterStringEnum.VERSION_DATE[RET_STRING])})

            Maintenance["Maintenance"].append({"Minimum GenLink Version" : self.GetParameterStringValue(RegisterStringEnum.MIN_GENLINK_VERSION[REGISTER], RegisterStringEnum.MIN_GENLINK_VERSION[RET_STRING])})
            Maintenance["Maintenance"].append({"Nominal RPM" : self.NominalRPM})
            Maintenance["Maintenance"].append({"Rated kW" : self.NominalKW})
            Maintenance["Maintenance"].append({"Nominal Frequency" : self.NominalFreq})
            Maintenance["Maintenance"].append({"Fuel Type" : self.FuelType})

            if self.UseMetric:
                Units = "L"
            else:
                Units = "gal"

            if self.FuelSensorSupported():
                FuelValue = self.GetFuelSensor(ReturnInt = True)
                Maintenance["Maintenance"].append({"Fuel Level Sensor" : self.ValueOut(FuelValue, "%", JSONNum)})
                FuelValue = self.GetFuelInTank(ReturnFloat = True)
                if FuelValue != None:
                    Maintenance["Maintenance"].append({"Fuel In Tank (Sensor)" : self.ValueOut(FuelValue, Units, JSONNum)})
            elif self.ExternalFuelDataSupported():
                FuelValue = self.GetExternalFuelPercentage(ReturnFloat = True)
                Maintenance["Maintenance"].append({"Fuel Level Sensor" : self.ValueOut(FuelValue, "%", JSONNum)})
                FuelValue = self.GetFuelInTank(ReturnFloat = True)
                if FuelValue != None:
                    Maintenance["Maintenance"].append({"Fuel In Tank (Sensor)" : self.ValueOut(FuelValue, Units, JSONNum)})

            if self.FuelTankCalculationSupported():
                Maintenance["Maintenance"].append({"Estimated Fuel In Tank " : self.ValueOut(self.GetEstimatedFuelInTank(ReturnFloat = True), Units, JSONNum)})

                DisplayText = "Hours of Fuel Remaining (Estimated %.02f Load )" % self.EstimateLoad
                RemainingFuelTimeFloat = self.GetRemainingFuelTime(ReturnFloat = True)
                if RemainingFuelTimeFloat != None:
                    Maintenance["Maintenance"].append({DisplayText : self.ValueOut(RemainingFuelTimeFloat, "h", JSONNum)})

                RemainingFuelTimeFloat = self.GetRemainingFuelTime(ReturnFloat = True, Actual = True)
                if RemainingFuelTimeFloat != None:
                    Maintenance["Maintenance"].append({"Hours of Fuel Remaining (Current Load)" : self.ValueOut(RemainingFuelTimeFloat, "h", JSONNum)})

            # Only update power log related info once a min for performance reasons
            if self.LastHouseKeepingTime == None or self.GetDeltaTimeMinutes(datetime.datetime.now() - self.LastHouseKeepingTime) >= 1 :
                UpdateNow = True
                self.LastHouseKeepingTime = datetime.datetime.now()
            else:
                UpdateNow = False
            if self.PowerMeterIsSupported() and self.FuelConsumptionSupported():
                if UpdateNow:
                    self.KWHoursMonth = self.GetPowerHistory("power_log_json=43200,kw")
                    self.FuelMonth = self.GetPowerHistory("power_log_json=43200,fuel")
                    self.FuelTotal = self.GetPowerHistory("power_log_json=0,fuel")
                    self.RunHoursMonth = self.GetPowerHistory("power_log_json=43200,time")

                if self.KWHoursMonth != None:
                    Maintenance["Maintenance"].append({"kW Hours in last 30 days" : self.UnitsOut(str(self.KWHoursMonth) + " kWh", type = float, NoString = JSONNum)})
                if self.FuelMonth != None:
                    Maintenance["Maintenance"].append({"Fuel Consumption in last 30 days" : self.UnitsOut(self.FuelMonth, type = float, NoString = JSONNum)})
                if self.FuelTotal != None:
                    Maintenance["Maintenance"].append({"Total Power Log Fuel Consumption" : self.UnitsOut(self.FuelTotal, type = float, NoString = JSONNum)})
                if self.RunHoursMonth != None:
                    Maintenance["Maintenance"].append({"Run Hours in last 30 days" : self.UnitsOut(str(self.RunHoursMonth) + " h", type = float, NoString = JSONNum)})

            if not self.SmartSwitch:
                pass
                Exercise = []
                #Maintenance["Maintenance"].append({"Exercise" : Exercise
                #Exercise["Exercise Time" : self.GetExerciseTime()
                #Exercise["Exercise Duration" : self.GetExerciseDuration()


            Maintenance["Maintenance"].append({"Controller Power Up Time" : self.GetTimeFromString(self.GetParameterStringValue(RegisterStringEnum.POWER_UP_TIME[REGISTER], RegisterStringEnum.POWER_UP_TIME[RET_STRING]))})
            Maintenance["Maintenance"].append({"Controller Last Power Fail" : self.GetTimeFromString(self.GetParameterStringValue(RegisterStringEnum.LAST_POWER_FAIL[REGISTER], RegisterStringEnum.LAST_POWER_FAIL[RET_STRING]))})

            Maintenance["Maintenance"].append({"Generator Settings" : self.GetGeneratorSettings()})
            Maintenance["Maintenance"].append({"Engine Settings" : self.GetEngineSettings()})
            Maintenance["Maintenance"].append({"Governor Settings" : self.GetGovernorSettings()})
            Maintenance["Maintenance"].append({"Regulator Settings" : self.GetRegulatorSettings()})

            Service = []
            Maintenance["Maintenance"].append({"Service" : Service})

            Service.append({"Total Run Hours" : self.GetRunHours()})

            IOStatus = []
            Maintenance["Maintenance"].append({"I/O Status" : IOStatus})

            OutputList = [self.Reg.OUTPUT_1[REGISTER],self.Reg.OUTPUT_2[REGISTER],
                            self.Reg.OUTPUT_3[REGISTER],self.Reg.OUTPUT_4[REGISTER],
                            self.Reg.OUTPUT_5[REGISTER],self.Reg.OUTPUT_6[REGISTER],
                            self.Reg.OUTPUT_7[REGISTER],self.Reg.OUTPUT_8[REGISTER]
                        ]
            IOStatus.append({"Inputs" : self.GetCondition(RegList = [self.Reg.INPUT_1[REGISTER],self.Reg.INPUT_2[REGISTER]], type = "inputs")})
            IOStatus.append({"Outputs" : self.GetCondition(RegList = OutputList, type = "outputs")})

        except Exception as e1:
            self.LogErrorLine("Error in DisplayMaintenance: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(Maintenance,""))

        return Maintenance

    #------------ HPanel::DisplayStatus ----------------------------------------
    def DisplayStatus(self, DictOut = False, JSONNum = False):

        try:
            Status = collections.OrderedDict()
            Status["Status"] = []

            Engine = []
            Alarms = []
            Battery = []
            Line = []
            Time = []

            Status["Status"].append({"Engine":Engine})
            Status["Status"].append({"Alarms":Alarms})
            Status["Status"].append({"Battery":Battery})
            if not self.SmartSwitch or self.HTSTransferSwitch:
                Status["Status"].append({"Line State":Line})

            with self.ExternalDataLock:
                try:
                    if self.ExternalTempData != None:
                        Status["Status"].append(self.ExternalTempData)
                except Exception as e1:
                    self.LogErrorLine("Error in DisplayStatus: " + str(e1))

            Status["Status"].append({"Time":Time})

            Battery.append({"Battery Voltage" : self.ValueOut(self.GetParameter(self.Reg.BATTERY_VOLTS[REGISTER], ReturnFloat = True, Divider = 100.0), "V", JSONNum)})
            Battery.append({"Battery Charger Current" : self.ValueOut(self.GetParameter(self.Reg.BATTERY_CHARGE_CURRNT[REGISTER], ReturnFloat = True, Divider = 10.0), "A", JSONNum)})

            Engine.append({"Engine State" : self.GetEngineState()})
            Engine.append({"Generator Status" : self.GetParameterStringValue(RegisterStringEnum.GENERATOR_STATUS[REGISTER], RegisterStringEnum.GENERATOR_STATUS[RET_STRING])})
            Engine.append({"Switch State" : self.GetSwitchState()})
            Engine.append({"Output Power" : self.ValueOut(self.GetPowerOutput(ReturnFloat = True), "kW", JSONNum)})
            Engine.append({"Power Factor" : self.ValueOut(self.GetParameter(self.Reg.TOTAL_PF[REGISTER], ReturnFloat = True, Divider = 100.0), "", JSONNum)})
            Engine.append({"RPM" : self.ValueOut(self.GetParameter(self.Reg.OUTPUT_RPM[REGISTER], ReturnInt = True), "", JSONNum)})
            Engine.append({"Frequency" : self.ValueOut(self.GetParameter(self.Reg.OUTPUT_FREQUENCY[REGISTER], ReturnFloat = True, Divider = 10.0), "Hz", JSONNum)})
            Engine.append({"Throttle Position" : self.ValueOut(self.GetParameter(self.Reg.THROTTLE_POSITION[REGISTER], ReturnInt = True), "Stp", JSONNum)})
            Engine.append({"Coolant Temp" : self.ValueOut(self.GetParameter(self.Reg.COOLANT_TEMP[REGISTER], ReturnInt = True), "F", JSONNum)})
            Engine.append({"Coolant Level" : self.ValueOut(self.GetParameter(self.Reg.COOLANT_LEVEL[REGISTER], ReturnInt = True), "Stp", JSONNum)})
            Engine.append({"Oil Pressure" : self.ValueOut(self.GetParameter(self.Reg.OIL_PRESSURE[REGISTER], ReturnInt = True), "psi", JSONNum)})
            Engine.append({"Oil Temp" : self.ValueOut(self.GetParameter(self.Reg.OIL_TEMP[REGISTER], ReturnInt = True), "F", JSONNum)})
            Engine.append({"Fuel Level" : self.ValueOut(self.GetParameter(self.Reg.FUEL_LEVEL[REGISTER], ReturnInt = True), "", JSONNum)})
            Engine.append({"Oxygen Sensor" : self.ValueOut(self.GetParameter(self.Reg.O2_SENSOR[REGISTER], ReturnInt = True), "", JSONNum)})
            Engine.append({"Current Phase A" : self.ValueOut(self.GetParameter(self.Reg.CURRENT_PHASE_A[REGISTER], ReturnInt = True), "A", JSONNum)})
            Engine.append({"Current Phase B" : self.ValueOut(self.GetParameter(self.Reg.CURRENT_PHASE_B[REGISTER],ReturnInt = True), "A", JSONNum)})
            Engine.append({"Current Phase C" : self.ValueOut(self.GetParameter(self.Reg.CURRENT_PHASE_C[REGISTER],ReturnInt = True), "A", JSONNum)})
            Engine.append({"Average Current" : self.ValueOut(self.GetParameter(self.Reg.AVG_CURRENT[REGISTER],ReturnInt = True), "A", JSONNum)})
            Engine.append({"Voltage A-B" : self.ValueOut(self.GetParameter(self.Reg.VOLTS_PHASE_A_B[REGISTER],ReturnInt = True), "V", JSONNum)})
            Engine.append({"Voltage B-C" : self.ValueOut(self.GetParameter(self.Reg.VOLTS_PHASE_B_C[REGISTER],ReturnInt = True), "V", JSONNum)})
            Engine.append({"Voltage C-A" : self.ValueOut(self.GetParameter(self.Reg.VOLTS_PHASE_C_A[REGISTER],ReturnInt = True), "V", JSONNum)})
            Engine.append({"Average Voltage" : self.ValueOut(self.GetParameter(self.Reg.AVG_VOLTAGE[REGISTER],ReturnInt = True), "V", JSONNum)})
            Engine.append({"Air Fuel Duty Cycle" : self.ValueOut(self.GetParameter(self.Reg.A_F_DUTY_CYCLE[REGISTER], ReturnFloat = True, Divider = 10.0), "", JSONNum)})

            Alarms.append({"Number of Active Alarms" : self.ValueOut(self.GetParameter(self.Reg.ACTIVE_ALARM_COUNT[REGISTER], ReturnInt = True), "", JSONNum)})
            Alarms.append({"Number of Acknowledged Alarms" : self.ValueOut(self.GetParameter(self.Reg.ALARM_ACK[REGISTER], ReturnInt = True), "", JSONNum)})

            OutputList = [self.Reg.OUTPUT_1[REGISTER],self.Reg.OUTPUT_2[REGISTER],
                            self.Reg.OUTPUT_3[REGISTER],self.Reg.OUTPUT_4[REGISTER],
                            self.Reg.OUTPUT_5[REGISTER],self.Reg.OUTPUT_6[REGISTER],
                            self.Reg.OUTPUT_7[REGISTER],self.Reg.OUTPUT_8[REGISTER]
                        ]
            if self.SystemInAlarm():
                AlarmList = self.GetCondition(RegList = OutputList, type = "alarms")
                if len(AlarmList):
                    Alarms.append({"Alarm List" : AlarmList})

            if not self.SmartSwitch  or self.HTSTransferSwitch:
                if not self.SmartSwitch:
                    Line.append({"Transfer Switch State" : self.GetTransferStatus()})
                if self.HTSTransferSwitch:
                    Line.append({"Target Utility Voltage" : self.ValueOut(self.GetParameter(self.Reg.EXT_SW_TARGET_VOLTAGE[REGISTER], ReturnInt = True), "V", JSONNum)})
                    Line.append({"Target Utility Frequency" : self.ValueOut(self.GetParameter(self.Reg.EXT_SW_TARGET_FREQ[REGISTER], ReturnInt = True), "Hz", JSONNum)})

                    Line.append({"Utility Frequency" : self.ValueOut(self.GetParameter(self.Reg.EXT_SW_UTILITY_FREQ[REGISTER], ReturnFloat = True, Divider = 100.0), "Hz", JSONNum)})

                    Line.append({"Utility Voltage A-B" : self.ValueOut(self.GetParameter(self.Reg.EXT_SW_UTILITY_VOLTS_AB[REGISTER], ReturnInt = True), "V", JSONNum)})
                    Line.append({"Utility Voltage B-C" : self.ValueOut(self.GetParameter(self.Reg.EXT_SW_UTILITY_VOLTS_BC[REGISTER], ReturnInt = True), "V", JSONNum)})
                    Line.append({"Utility Voltage C-A" : self.ValueOut(self.GetParameter(self.Reg.EXT_SW_UTILITY_VOLTS_CA[REGISTER], ReturnInt = True), "V", JSONNum)})
                    Line.append({"Average Utility Voltage" : self.ValueOut(self.GetParameter(self.Reg.EXT_SW_UTILITY_AVG_VOLTS[REGISTER], ReturnInt = True), "V", JSONNum)})

                    Line.append({"Utility Current Phase A" : self.ValueOut(self.GetParameter(self.Reg.EXT_SW_UTILITY_AMPS_A[REGISTER], ReturnInt = True), "A", JSONNum)})
                    Line.append({"Utility Current Phase B" : self.ValueOut(self.GetParameter(self.Reg.EXT_SW_UTILITY_AMPS_B[REGISTER], ReturnInt = True), "A", JSONNum)})
                    Line.append({"Utility Current Phase C" : self.ValueOut(self.GetParameter(self.Reg.EXT_SW_UTILITY_AMPS_C[REGISTER], ReturnInt = True), "A", JSONNum)})
                    Line.append({"Average Utility Current" : self.ValueOut(self.GetParameter(self.Reg.EXT_SW_UTILITY_AVG_AMPS[REGISTER], ReturnInt = True), "A", JSONNum)})

                    Line.append({"Utility Power Factor" : self.ValueOut(self.GetParameter(self.Reg.EXT_SW_UTILITY_PF[REGISTER], ReturnFloat = True, Divider = 100.0), "", JSONNum)})
                    Line.append({"Utility Power" : self.ValueOut(self.GetParameter(self.Reg.EXT_SW_UTILITY_KW[REGISTER], ReturnInt = True), "kW", JSONNum)})

                    Line.append({"Switch Reported Generator Average Voltage" : self.ValueOut(self.GetParameter(self.Reg.EXT_SW_GEN_AVG_VOLT[REGISTER], ReturnInt = True), "V", JSONNum)})
                    Line.append({"Switch Reported Generator Average Frequency" : self.ValueOut(self.GetParameter(self.Reg.EXT_SW_GEN_FREQ[REGISTER], ReturnFloat = True, Divider = 100.0), "Hz", JSONNum)})

                    Line.append({"Backup Battery Volts" : self.ValueOut(self.GetParameter(self.Reg.EXT_SW_BACKUP_BATT_VOLTS[REGISTER], ReturnFloat = True, Divider = 100.0), "V", JSONNum)})

                    Line.append({"Switch Software Version" : self.ValueOut(self.GetParameter(self.Reg.EXT_SW_VERSION[REGISTER], ReturnInt = True), "", JSONNum)})
                    Line.append({"Switch Selected" : self.ValueOut(self.GetParameter(self.Reg.EXT_SW_SELECTED[REGISTER], ReturnInt = True), "", JSONNum)})

                    '''
                    EXT_SW_GENERAL_STATUS           # External Switch General Status
                    EXT_SW_MINIC_DIAGRAM            # Ext Switch Mimic Diagram

                    '''

            # Generator time
            Time.append({"Monitor Time" : datetime.datetime.now().strftime("%A %B %-d, %Y %H:%M:%S")})
            Time.append({"Generator Time" : self.GetDateTime()})

        except Exception as e1:
            self.LogErrorLine("Error in DisplayStatus: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(Status,""))

        return Status

    #------------ GeneratorController:GetRegulatorSettings ---------------------
    def GetRegulatorSettings(self):

        RegSettings = []
        RegData = self.GetParameterFileValue(REGULATOR_FILE_RECORD)
        if len(RegData) >= (REGULATOR_FILE_RECORD_LENGTH * 2):
            try:
                RegSettings.append({"Voltage KP" : str(self.GetIntFromString(RegData, 0, 2)) + " V"})           # Byte 0 and 1
                RegSettings.append({"Voltage KI" : str(self.GetIntFromString(RegData, 2, 2)) + " V"})           # Byte 2 and 3
                RegSettings.append({"Voltage KD" : str(self.GetIntFromString(RegData, 4, 2)) + " V"})           # Byte 4 and 5
                RegSettings.append({"Volts Per Hz" : str(self.GetIntFromString(RegData, 14, 2))})               # Byte 14 and 15
                RegSettings.append({"High Voltage Limit" : str(self.GetIntFromString(RegData, 18, 2)) + " V"})  # Byte 18 and 19
                RegSettings.append({"Low Voltage Limit" : str(self.GetIntFromString(RegData, 20, 2)) + " V"})   # Byte 20 and 21
                RegSettings.append({"Target Volts" : str(self.GetIntFromString(RegData, 6, 2)) + " V"})         # Byte 6 and 7
                RegSettings.append({"VF Corner 1" : str(self.GetIntFromString(RegData, 10, 2)) + " Hz"})        # Byte 10 and 11
                RegSettings.append({"VF Corner 2" : str(self.GetIntFromString(RegData, 12, 2)) + " Hz"})        # Byte 12 and 13
                RegSettings.append({"Rated Power" : str(self.GetIntFromString(RegData, 26, 2))})                # Byte 26 and 27
                PowerFactor = self.GetIntFromString(RegData, 24, 2)         # Byte 24 and 25
                RegSettings.append({"Power Factor" : "%.2f" % (PowerFactor / 100)})
                RegSettings.append({"kW Demand" : str(self.GetIntFromString(RegData, 22, 2)) + " kW"})          # Byte 22 and 23
                RegSettings.append({"Panel Type" : str(self.GetIntFromString(RegData, 28, 2))})                 # Byte 28 and 29
                #RegSettings.append({"Exciter Frequency Ratio" : str(self.GetIntFromString(RegData, 44, 1))})   # Byte 44

            except Exception as e1:
                self.LogErrorLine("Error parsing regulator settings: " + str(e1))
        return RegSettings

    #------------ GeneratorController:GetGovernorSettings ----------------------
    def GetGovernorSettings(self):

        GovSettings = []
        GovData = self.GetParameterFileValue(GOV_DATA_FILE_RECORD)
        if len(GovData) >= (GOV_DATA_FILE_RECORD_LENGTH * 2):
            try:
                #GovSettings.append({"Standby KP" : str(self.GetIntFromString(GovData, 0, 2))})                        # Byte 0 and 1
                #GovSettings.append({"Standby KI" : str(self.GetIntFromString(GovData, 2, 2))})                        # Byte 2 and 3
                #GovSettings.append({"Standby KD" : str(self.GetIntFromString(GovData, 4, 2))})                        # Byte 4 and 5
                #GovSettings.append({"Actuator Start Position" : str(self.GetIntFromString(GovData, 20, 2))})          # Byte 20 and 21
                #GovSettings.append({"Offset" : str(self.GetIntFromString(GovData, 22, 2))})                           # Byte 22 and 23
                #GovSettings.append({"Full Scale" : str(self.GetIntFromString(GovData, 24, 2))})                       # Byte 24 and 25
                GovSettings.append({"Soft Start Frequency" : str(self.GetIntFromString(GovData, 26, 2)) + " Hz"})     # Byte 26 and 26
                #GovSettings.append({"Engine Linearization" : str(self.GetIntFromString(GovData, 28, 2))})             # Byte 28 and 29

                #GovSettings.append({"Use Diesel Algorithms" : "Yes" if self.GetIntFromString(GovData, 12, 2) else "No"})   # Byte 12 - 13
                GovFreq = self.GetIntFromString(GovData, 14, 2)         # Byte 14 and 15
                GovSettings.append({"Governor Target Frequency" : "%.2f Hz" % (GovFreq / 100)})

            except Exception as e1:
                self.LogErrorLine("Error parsing governor settings: " + str(e1))
        return GovSettings

    #------------ GeneratorController:GetEngineSettings ------------------------
    def GetEngineSettings(self):

        EngineSettings = []
        EngineData = self.GetParameterFileValue(ENGINE_DATA_FILE_RECORD)
        if len(EngineData) >= (ENGINE_DATA_FILE_RECORD_LENGTH * 2):
            try:
                EngineSettings.append({"Engine Transfer Enable" : "Enabled" if self.GetIntFromString(EngineData, 0, 2) else "Disabled"})   # Byte 1 and 2
                EngineSettings.append({"Preheat Enable" : "Enabled" if self.GetIntFromString(EngineData, 2, 2) else "Disabled"})           # Byte 2 and 3
                if self.GetIntFromString(EngineData, 2, 2):
                    EngineSettings.append({"Preheat Time" : str(self.GetIntFromString(EngineData, 4, 2)) + " s"})           # Byte 4 and 5
                    EngineSettings.append({"Preheat Temp Limit" : str(self.GetIntFromString(EngineData, 47, 1)) + " F"})    # Byte 47
                EngineSettings.append({"Start detection RPM" : str(self.GetIntFromString(EngineData, 6, 2))})               # Byte 6 and 7
                EngineSettings.append({"Crank Time" : str(self.GetIntFromString(EngineData, 8, 2)) + " s"})                 # Byte 8 and 9
                EngineSettings.append({"Alarm Hold Off Time" : str(self.GetIntFromString(EngineData, 10, 2)) + " s"})       # Byte 10 and 11
                EngineSettings.append({"Engine Warm Up Time" : str(self.GetIntFromString(EngineData, 12, 2)) + " s"})       # Byte 12 and 13
                EngineSettings.append({"Engine Cool Down Time" : str(self.GetIntFromString(EngineData, 14, 2)) + " s"})     # Byte 14 and 15
                EngineSettings.append({"Pause Between Cranks Attempts" : str(self.GetIntFromString(EngineData, 16, 2)) + " s"})         # Byte 16 and 17
                EngineSettings.append({"Start Attempts" : str(self.GetIntFromString(EngineData, 18, 2))})                   # Byte 18 and 19
                EngineSettings.append({"Load Accept Frequency" : str(self.GetIntFromString(EngineData, 20, 2)) + " Hz"})    # Byte 20 and 21
                EngineSettings.append({"Load Accept Voltage" : str(self.GetIntFromString(EngineData, 22, 2)) + " V"})       # Byte 22 and 23

            except Exception as e1:
                self.LogErrorLine("Error parsing engine settings: " + str(e1))
        return EngineSettings

    #------------ GeneratorController:GetGeneratorSettings ---------------------
    def GetGeneratorSettings(self):

        GeneratorSettings = []
        FlyWheelTeeth = []
        CTRatio = []
        Phase = None
        TargetRPM = []
        GenData = self.GetParameterFileValue(MISC_GEN_FILE_RECORD)
        if len(GenData) >= 34:
            try:
                FlyWheelTeeth.append(self.GetIntFromString(GenData, 0, 2))  # Byte 1 and 2
                FlyWheelTeeth.append(self.GetIntFromString(GenData, 2, 2))  # Byte 2 and 3
                FlyWheelTeeth.append(self.GetIntFromString(GenData, 4, 2))  # Byte 4 and 5
                CTRatio.append(self.GetIntFromString(GenData, 6, 2))        # Byte 6 and 7
                CTRatio.append(self.GetIntFromString(GenData, 8, 2))        # Byte 8 and 9
                # Skip byte 10 and 11
                Phase = self.GetIntFromString(GenData, 12, 1)               # Byte 12
                TargetRPM.append(self.GetIntFromString(GenData, 13, 2))     # Byte 13 and 14
                TargetRPM.append(self.GetIntFromString(GenData, 15, 2))     # Byte 15 and 16

                GeneratorSettings.append({"Target RPM" : str(TargetRPM[0]) if len(TargetRPM) else "Unknown"})
                GeneratorSettings.append({"Number of Flywheel Teeth" : str(FlyWheelTeeth[0]) if len(FlyWheelTeeth) else "Unknown"})
                GeneratorSettings.append({"Phase" : str(Phase) if Phase != None else "Unknown"})
                GeneratorSettings.append({"CT Ratio" : str(CTRatio[0]) if len(CTRatio) else "Unknown"})

            except Exception as e1:
                self.LogErrorLine("Error parsing generator settings: " + str(e1))

        return GeneratorSettings
    #------------ GeneratorController:GetRunHours ------------------------------
    def GetRunHours(self):
        return self.GetParameter(self.Reg.ENGINE_HOURS[REGISTER],"", 10.0 )

    #------------------- HPanel::DisplayOutage ---------------------------------
    def DisplayOutage(self, DictOut = False, JSONNum = False):

        try:
            Outage = collections.OrderedDict()
            OutageData = collections.OrderedDict()
            Outage["Outage"] = OutageData

            OutageData["Status"] = "Not Supported"
            OutageData["System In Outage"] = "No"       # mynotify.py checks this

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
            self.ModBus.ProcessWriteTransaction(self.Reg.GEN_TIME_HR_MIN[REGISTER], len(Data) / 2, Data)

            DayOfWeek = d.weekday()     # returns Monday is 0 and Sunday is 6
            # expects Sunday = 1, Saturday = 7
            if DayOfWeek == 6:
                DayOfWeek = 1
            else:
                DayOfWeek += 2
            Data= []
            Data.append(d.second)           #GEN_TIME_SEC_DYWK
            Data.append(DayOfWeek)                  #Day of Week is always zero
            self.ModBus.ProcessWriteTransaction(self.Reg.GEN_TIME_SEC_DYWK[REGISTER], len(Data) / 2, Data)

            Data= []
            Data.append(d.month)            #GEN_TIME_MONTH_DAY
            Data.append(d.day)              # low byte is day of month
            self.ModBus.ProcessWriteTransaction(self.Reg.GEN_TIME_MONTH_DAY[REGISTER], len(Data) / 2, Data)

            Data= []
            # Note: Day of week should always be zero when setting time
            Data.append(d.year - 2000)      # GEN_TIME_YR
            Data.append(0)                  #
            self.ModBus.ProcessWriteTransaction(self.Reg.GEN_TIME_YR[REGISTER], len(Data) / 2, Data)

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
                Value = 0x0080       # remote start
                Value2 = 0x0000
                Value3 = 0x0000
            elif Command == "stop":
                Value = 0x0000       # remote stop
                Value2 = 0x0000
                Value3 = 0x0000
            elif Command == "starttransfer":
                Value = 0x0080       # remote start (standby)
                Value2 = 0x0000
                Value3 = 0x0080
            elif Command == "startparallel":
                Value = 0x0080       # remote start (parallel)
                Value2 = 0x0080
                Value3 = 0x0000
            elif Command == "quiettest":
                Data = []
                Data.append(0)
                Data.append(1)
                self.ModBus.ProcessWriteTransaction(self.Reg.QUIETTEST_STATUS[REGISTER], len(Data) / 2, Data)
                return "Remote command sent successfully (quiettest)"
            elif Command == "quietteststop":
                Data = []
                Data.append(0)
                Data.append(0)
                self.ModBus.ProcessWriteTransaction(self.Reg.QUIETTEST_STATUS[REGISTER], len(Data) / 2, Data)
                return "Remote command sent successfully (quietteststop)"
            elif Command == "ackalarm":
                Data = []
                Data.append(0)
                Data.append(1)
                self.ModBus.ProcessWriteTransaction(self.Reg.ALARM_ACK[REGISTER], len(Data) / 2, Data)
                return "Remote command sent successfully (ackalarm)"

                '''
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
            self.ModBus.ProcessWriteTransaction(self.Reg.START_BITS[REGISTER], len(Data) / 2, Data)

            return "Remote command sent successfully"
        except Exception as e1:
            self.LogErrorLine("Error in SetGeneratorRemoteCommand: " + str(e1))
            return "Error"


    #----------  HPanel:GetController  -----------------------------------------
    # return the name of the controller, if Actual == False then return the
    # controller name that the software has been instructed to use if overridden
    # in the conf file
    def GetController(self, Actual = True):

        return self.GetParameterStringValue(RegisterStringEnum.CONTROLLER_NAME[REGISTER], RegisterStringEnum.CONTROLLER_NAME[RET_STRING])

    #----------  HPanel:ComminicationsIsActive  --------------------------------
    # Called every few seconds, if communictions are failing, return False, otherwise
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
        if self.UseExternalCTData:
            return True
        return True

    #---------------------HPanel::GetPowerOutput--------------------------------
    # returns current kW
    # rerturn empty string ("") if not supported,
    # return kW with units i.e. "2.45kW"
    def GetPowerOutput(self, ReturnFloat = False):

        #return self.GetPowerOutputAlt(ReturnFloat = ReturnFloat)
        if ReturnFloat:
            return self.GetParameter(self.Reg.TOTAL_POWER_KW[REGISTER], ReturnFloat = True)
        else:
            return self.GetParameter(self.Reg.TOTAL_POWER_KW[REGISTER], "kW", ReturnFloat = False)

    #------------ HPanel:GetPowerOutputAlt -------------------------------------
    def GetPowerOutputAlt(self, ReturnFloat = False):

        if ReturnFloat:
            DefaultReturn = 0.0
        else:
            DefaultReturn = "0 kW"

        if not self.PowerMeterIsSupported():
            return DefaultReturn

        EngineState = self.GetEngineState()
        # report null if engine is not running
        if not len(EngineState) or "stop" in EngineState.lower() or "off" in EngineState.lower():
            return DefaultReturn

        Current = float(self.GetParameter(self.Reg.AVG_CURRENT[REGISTER],ReturnInt = True))
        Voltage = float(self.GetParameter(self.Reg.AVG_VOLTAGE[REGISTER],ReturnInt = True))
        powerfactor = self.GetParameter(self.Reg.TOTAL_PF[REGISTER], ReturnFloat = True, Divider = 100.0)

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

    #----------  HPanel:GetCommStatus  -----------------------------------------
    # return Dict with communication stats
    def GetCommStatus(self):
        return self.ModBus.GetCommStats()

    #------------ HPanel:GetBaseStatus -----------------------------------------
    # return one of the following: "ALARM", "SERVICEDUE", "EXERCISING", "RUNNING",
    # "RUNNING-MANUAL", "OFF", "MANUAL", "READY"
    def GetBaseStatus(self):
        try:
            EngineStatus = self.GetEngineState().lower()
            GeneratorStatus = self.GetParameterStringValue(RegisterStringEnum.GENERATOR_STATUS[REGISTER],RegisterStringEnum.GENERATOR_STATUS[RET_STRING]).lower()
            SwitchState = self.GetSwitchState().lower()

            if "running" in EngineStatus:
                IsRunning = True
            else:
                IsRunning = False
            if "stopped" in GeneratorStatus:
                IsStopped = True
            else:
                IsStopped = False
            if "exercising" in EngineStatus or "exercise" in EngineStatus or "quiettest" in EngineStatus:
                IsExercising = True
            else:
                IsExercising = False
            if self.HPanelDetected:
                ServiceDue = self.GetParameterBit(self.Reg.OUTPUT_7[REGISTER], Output7.NEED_SERVICE)
            else:
                ServiceDue = self.GetParameterBit(self.Reg.OUTPUT_5[REGISTER], 0x4000)

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
                self.FeedbackPipe.SendFeedback("Base State", FullLogs = True, Always = True, Message="Unknown Base State")
                return "UNKNOWN"
        except Exception as e1:
            self.LogErrorLine("Error in GetBaseStatus: " + str(e1))
            return "UNKNOWN"

    #------------ HPanel:GetOneLineStatus --------------------------------------
    # returns a one line status for example : switch state and engine state
    def GetOneLineStatus(self):
        return self.GetSwitchState() + " : " + self.GetEngineState()

    #----------  GeneratorController::FuelSensorSupported------------------------
    def FuelSensorSupported(self):

        if self.UseFuelSensor:
            return True
        return False

    #------------ Evolution:GetFuelSensor --------------------------------------
    def GetFuelSensor(self, ReturnInt = False):

        if not self.FuelSensorSupported():
            return None

        return self.GetParameter(self.Reg.FUEL_LEVEL[REGISTER], ReturnInt = ReturnInt)

    #----------  GeneratorController::GetFuelConsumptionDataPoints--------------
    def GetFuelConsumptionDataPoints(self):

        try:
            if self.FuelHalfRate == 0 or self.FuelFullRate == 0:
                return None

            return [.5, float(self.FuelHalfRate), 1.0, float(self.FuelFullRate), self.FuelUnits]

        except Exception as e1:
            self.LogErrorLine("Error in GetFuelConsumptionDataPoints: " + str(e1))
        return None
