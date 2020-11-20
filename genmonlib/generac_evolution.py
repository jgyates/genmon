#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: generac_evolution.py
# PURPOSE: Controller Specific Detils for Generac Evolution Controller
#
#  AUTHOR: Jason G Yates
#    DATE: 24-Apr-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import datetime, time, sys, os, threading, socket
import json, collections, math
import re

try:
    from httplib import HTTPSConnection
except ImportError:
     from http.client import HTTPSConnection

from genmonlib.controller import GeneratorController
from genmonlib.mytile import MyTile
from genmonlib.modbus_file import ModbusFile
from genmonlib.mymodbus import ModbusProtocol
from genmonlib.modbus_evo2 import ModbusEvo2
from genmonlib.program_defaults import ProgramDefaults

#-------------------Generator specific const defines for Generator class--------
LOG_DEPTH               = 50
START_LOG_STARTING_REG  = 0x012c    # the most current start log entry should be at this register
START_LOG_STRIDE        = 4
START_LOG_END_REG       = ((START_LOG_STARTING_REG + (START_LOG_STRIDE * LOG_DEPTH)) - START_LOG_STRIDE)
ALARM_LOG_STARTING_REG  = 0x03e8    # the most current alarm log entry should be at this register
ALARM_LOG_STRIDE        = 5
ALARM_LOG_END_REG       = ((ALARM_LOG_STARTING_REG + (ALARM_LOG_STRIDE * LOG_DEPTH)) - ALARM_LOG_STRIDE)
SERVICE_LOG_STARTING_REG= 0x04e2    # the most current service log entry should be at this register
SERVICE_LOG_STRIDE      = 4
SERVICE_LOG_END_REG     = ((SERVICE_LOG_STARTING_REG + (SERVICE_LOG_STRIDE * LOG_DEPTH)) - SERVICE_LOG_STRIDE)
# Register for Model number
SERIAL_NUM_REG          = 0x01f4
SERIAL_NUM_REG_LENGTH   = 5

NEXUS_ALARM_LOG_STARTING_REG    = 0x064
NEXUS_ALARM_LOG_STRIDE          = 4
NEXUS_ALARM_LOG_END_REG         = ((NEXUS_ALARM_LOG_STARTING_REG + (NEXUS_ALARM_LOG_STRIDE * LOG_DEPTH)) - NEXUS_ALARM_LOG_STRIDE)

DEFAULT_THRESHOLD_VOLTAGE = 143
DEFAULT_PICKUP_VOLTAGE = 190

class Evolution(GeneratorController):

    #---------------------Evolution::__init__-----------------------------------
    def __init__(self,
        log,
        newinstall = False,
        simulation = False,
        simulationfile = None,
        message = None,
        feedback = None,
        config = None):

        # call parent constructor
        super(Evolution, self).__init__(log, newinstall = newinstall, simulation = simulation, simulationfile = simulationfile, message = message, feedback = feedback, config = config)

        # Controller Type
        self.EvolutionController = None
        self.SynergyController = False
        self.Evolution2 = False
        self.PowerPact = False
        self.PreNexus  = False
        self.LiquidCooled = None
        self.LiquidCooledParams = None
        self.SavedFirmwareVersion = None
        # State Info
        self.GeneratorInAlarm = False       # Flag to let the heartbeat thread know there is a problem
        self.LastAlarmValue = 0xFF  # Last Value of the Alarm / Status Register
        self.bUseLegacyWrite = False        # Nexus will set this to True
        self.bEnhancedExerciseFrequency = False     # True if controller supports biweekly and monthly exercise times
        self.CurrentDivider = None
        self.CurrentOffset = None
        self.DisableOutageCheck = False
        self.SerialNumberReplacement = None
        self.AdditionalRunHours = None
        self.NominalLineVolts = 240

        self.DaysOfWeek = { 0: "Sunday",    # decode for register values with day of week
                            1: "Monday",
                            2: "Tuesday",
                            3: "Wednesday",
                            4: "Thursday",
                            5: "Friday",
                            6: "Saturday"}
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

        # base registers and their length in bytes
        # note: the lengths are in bytes. The request packet should be in words
        # and due to the magic of python, we often deal with the response in string values
        #   dict format  Register: [ Length in bytes: monitor change 0 - no, 1 = yes]
        self.BaseRegisters = {                  # base registers read by master
                    "0000" : [2, 0],     # possibly product line code (Nexus, EvoAC, EvoLC)
                    "0005" : [2, 0],     # Exercise Time Hi Byte = Hour, Lo Byte = Min (Read Only) (Nexus, EvoAC, EvoLC)
                    "0006" : [2, 0],     # Exercise Time Hi Byte = Day of Week 00=Sunday 01=Monday, Low Byte = 00=quiet=no, 01=yes (Nexus, EvoAC, EvoLC)
                    "0007" : [2, 0],     # Engine RPM  (Nexus, EvoAC, EvoLC)
                    "0008" : [2, 0],     # Freq - value includes Hz to the tenths place i.e. 59.9 Hz (Nexus, EvoAC, EvoLC)
                    "000a" : [2, 0],     # battery voltage Volts to  tenths place i.e. 13.9V (Nexus, EvoAC, EvoLC)
                    "000b" : [4, 0],     # engine run time hours (000b=high,000c=low)
                    "000e" : [2, 0],     # Read / Write: Generator Time Hi byte = hours, Lo byte = min (Nexus, EvoAC, EvoLC)
                    "000f" : [2, 0],     # Read / Write: Generator Time Hi byte = month, Lo byte = day of the month (Nexus, EvoAC, EvoLC)
                    "0010" : [2, 0],     # Read / Write: Generator Time = Hi byte Day of Week 00=Sunday 01=Monday, Lo byte = last 2 digits of year (Nexus, EvoAC, EvoLC)
                    "0011" : [2, 0],     # Utility Threshold, ML Does not read this  (Nexus, EvoAC, EvoLC) (possibly read / write)
                    "0012" : [2, 0],     # Gen output voltage (Nexus, EvoAC, EvoLC)
                    "0019" : [2, 0],     # Model ID register, (EvoAC, NexusAC)
                    "001a" : [2, 0],     # Hours Until Service A
                    "001b" : [2, 0],     # Date Service A Due
                    "001c" : [2, 0],     # Service Info Hours (Nexus)
                    "001d" : [2, 0],     # Service Info Date (Nexus)
                    "001e" : [2, 0],     # Hours Until Service B
                    "001f" : [2, 0],     # Hours util Service (NexusAC), Date Service Due (Evo)
                    "0020" : [2, 0],     # Service Info Date (NexusAC)
                    "0021" : [2, 0],     # Service Info Hours (NexusAC)
                    "0022" : [2, 0],     # Service Info Date (NexusAC, EvoAC)
                    "002a" : [2, 0],     # hardware (high byte) (Hardware V1.04 = 0x68) and firmware version (low byte) (Firmware V1.33 = 0x85) (Nexus, EvoAC, EvoLC)
                    "002b" : [2, 0],     # Startup Delay (Evo AC)
                    "002c" : [2, 0],     # Evo      (Exercise Time) Exercise Time HH:MM
                    "002d" : [2, 0],     # Evo AC   (Weekly, Biweekly, Monthly)
                    "002e" : [2, 0],     # Evo      (Exercise Time) Exercise Day Sunday =0, Monday=1
                    "002f" : [2, 0],     # Evo      (Quiet Mode)
                    "0051" : [2, 0],     # Bootcode Version
                    "0054" : [2, 0],     # Hours since generator activation (hours of protection) (Evo LC only)
                    "0055" : [2, 0],     # Unknown
                    "0056" : [2, 0],     # Unknown Looks like some status bits (0000 to 0003, back to 0000 on stop)
                    "0057" : [2, 0],     # Unknown Looks like some status bits (0002 to 0005 when engine starts, back to 0002 on stop)
                    "0058" : [2, 0],     # Hall Effect Sensor (EvoLC)
                    "0059" : [2, 0],     # Rated Volts (EvoLC)
                    "005a" : [2, 0],     # Rated Hz (EvoLC)
                    "005d" : [2, 0],     # Fuel Pressure Sensor, Moves between 0x55 - 0x58 continuously even when engine off
                    "005e" : [4, 0],     # Total engine time in minutes  (EvoLC) 005e= high, 005f=low
                    "000d" : [2, 0],     # Bit changes when the controller is updating registers.
                    "003c" : [2, 0],     # Raw RPM Sensor Data (Hall Sensor)
                    "05fa" : [2, 0],     # Evo AC   (Status?)
                    "0033" : [2, 0],     # Evo AC   (Status?)
                    "0034" : [2, 0],     # Evo AC   (Status?) Goes from FFFF 0000 00001 (Nexus and Evo AC)
                    "0032" : [2, 0],     # Evo AC   (Sensor?) starts  0x4000 ramps up to ~0x02f0
                    "0035" : [2, 0],     # Evo AC    Unknown
                    "0036" : [2, 0],     # Evo AC   (Sensor?) Unknown
                    "0037" : [2, 0],     # CT Sensor (EvoAC)
                    "0038" : [2, 0],     # Evo AC   (Sensor?)       FFFE, FFFF, 0001, 0002 random - not linear
                    "0039" : [2, 0],     # Evo AC   (Sensor?)
                    "003a" : [4, 0],     # CT Sensor (EvoAC)
                    "0208" : [2, 0],     # Calibrate Volts (Evo all)
                    "020a" : [2, 0],     # Param Group (EvoLC, NexuLC)
                    "020b" : [2, 0],     # Voltage Code (EvoLC, NexusLC)
                    "020c" : [2, 0],     #  Fuel Type (EvoLC, NexusLC)
                    "020e" : [2, 0],     # Volts Per Hertz (EvoLC)
                    "0212" : [2, 0],     # Unknown status data
                    "0213" : [2, 0],     # Wifi Signal Strength RSSI (Evo2)
                    "004c" : [2, 0],     # Unknown register data
                    "0235" : [2, 0],     # Gain (EvoLC)
                    "0236" : [2, 0],     # Two Wire Start (EvoAC)
                    "0237" : [2, 0],     # Set Voltage (Evo LC)
                    "0239" : [2, 0],     # Startup Delay (Evo LC)
                    "023b" : [2, 0],     # Pick Up Voltage (Evo LC only)
                    "023e" : [2, 0],     # Exercise time duration (Evo LC only)
                    "0209" : [2, 0],     #  Unknown (EvoLC)
                    "020d" : [2, 0],     #  Unknown (EvoLC)
                    "020f" : [2, 0],     #  Unknown (EvoLC)  Something in EvoLC
                    "0238" : [2, 0],     #  Unknown (EvoLC)
                    "023a" : [2, 0],     #  Unknown (EvoLC)
                    "023d" : [2, 0],     #  Unknown (EvoLC)
                    "0241" : [2, 0],     #  Unknown (EvoLC)
                    "0242" : [2, 0],     #  Unknown (EvoLC)
                    "0243" : [2, 0],     #  Unknown (EvoLC)
                    "0244" : [2, 0],     #  Unknown (EvoLC)
                    "0245" : [2, 0],     #  Unknown (EvoLC)
                    "0246" : [2, 0],     #  Unknown (EvoLC)
                    "0247" : [2, 0],     #  Unknown (EvoLC)
                    "0248" : [2, 0],     #  Unknown (EvoLC)
                    "0249" : [2, 0],     #  Unknown (EvoLC)
                    "024a" : [2, 0],     #  Unknown (EvoLC)
                    "0258" : [2, 0],     #  Unknown (EvoLC, NexusLC) Some type of setting
                    "025a" : [2, 0],     #  Unknown (EvoLC)
                    "005c" : [2, 0],     # Unknown , possible model reg on EvoLC
                    "05ed" : [2, 0],     # Ambient Temp Sensor (EvoLC, Evo2)
                    "05ee" : [2, 0],     # (CT on Battery Charger)
                    "05f2" : [2, 0],     # Unknown (EvoLC)
                    "05f3" : [2, 0],     # EvoAC, EvoLC, counter of some type
                    "05f4" : [2, 0],     # Evo AC   Current 1
                    "05f5" : [2, 0],     # Evo AC   Current 2
                    "05f6" : [2, 0],     # Evo AC   Current Cal 1
                    "05f7" : [2, 0],     # Evo AC   Current Cal 1
                    }

        # registers that need updating more frequently than others to make things more responsive
        self.PrimeRegisters = {
                    "0001" : [4, 0],     # Alarm and status register
                    "0053" : [2, 0],     # Evo LC Output relay status register (battery charging, transfer switch, Change at startup and stop
                    "0052" : [2, 0],     # Evo LC Input status register (sensors) only tested on liquid cooled Evo
                    "0009" : [2, 0],     # Utility voltage
                    "05f1" : [2, 0]}     # Last Alarm Code

        self.REGLEN = 0
        self.REGMONITOR = 1

        self.SetupClass()


    #-------------Evolution:SetupClass------------------------------------------
    def SetupClass(self):

        # read config file
        if not self.GetConfig():
            self.LogError("Failure in Controller GetConfig: " + str(e1))
            sys.exit(1)
        try:
            self.AlarmFile = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "data", "ALARMS.txt")
            with open(self.AlarmFile,"r") as AlarmFile:     #
                pass
        except Exception as e1:
            self.LogErrorLine("Unable to open alarm file: " + str(e1))
            sys.exit(1)

        try:
            #Starting device connection
            if self.Simulation:
                self.ModBus = ModbusFile(self.UpdateRegisterList,
                    inputfile = self.SimulationFile,
                    config = self.config)
            else:
                # ModbusEvo2 is a filter to ModbusProtocol class, this will handle Nexus and Evo traffic as well
                # and Evo2 specific as needed
                self.ModBus = ModbusEvo2(self.UpdateRegisterList,
                    config = self.config)

            self.Threads = self.MergeDicts(self.Threads, self.ModBus.Threads)
            self.LastRxPacketCount = self.ModBus.RxPacketCount

            self.StartCommonThreads()

        except Exception as e1:
            self.LogErrorLine("Error opening modbus device: " + str(e1))
            self.LogError("Possible cause is invalid serial port specified.")
            sys.exit(1)
    #-------------Evolution:InitDevice------------------------------------------
    # One time reads, and read all registers once
    def InitDevice(self):

        try:
            self.ModBus.ProcessTransaction("%04x" % SERIAL_NUM_REG, SERIAL_NUM_REG_LENGTH)

            self.DetectController()

            if self.EvolutionController:
                self.ModBus.ProcessTransaction("%04x" % ALARM_LOG_STARTING_REG, ALARM_LOG_STRIDE)
            else:
                self.ModBus.ProcessTransaction("%04x" % NEXUS_ALARM_LOG_STARTING_REG, NEXUS_ALARM_LOG_STRIDE)

            self.ModBus.ProcessTransaction("%04x" % START_LOG_STARTING_REG, START_LOG_STRIDE)

            if self.EvolutionController:
                self.ModBus.ProcessTransaction("%04x" % SERVICE_LOG_STARTING_REG, SERVICE_LOG_STRIDE)

            for PrimeReg, PrimeInfo in self.PrimeRegisters.items():
                if self.IsStopping:
                    break
                self.ModBus.ProcessTransaction(PrimeReg, int(PrimeInfo[self.REGLEN] / 2))

            for Reg, Info in self.BaseRegisters.items():
                if self.IsStopping:
                    break
                #The divide by 2 is due to the diference in the values in our dict are bytes
                # but modbus makes register request in word increments so the request needs to
                # in word multiples, not bytes
                self.ModBus.ProcessTransaction(Reg, int(Info[self.REGLEN] / 2))

            # check for model specific info in read from conf file, if not there then add some defaults
            if not self.IsStopping:
                self.CheckModelSpecificInfo(NoLookUp = self.Simulation)
            # check for unknown events (i.e. events we are not decoded) and send an email if they occur
            self.CheckForAlarmEvent.set()
            self.SetupTiles()
            if not self.EvolutionController == None and not self.LiquidCooled == None:
                self.InitComplete = True
                self.InitCompleteEvent.set()
        except Exception as e1:
            self.LogErrorLine("Error in InitDevice: " + str(e1))

    #---------------------------------------------------------------------------
    def SetupTiles(self):

        try:
            with self.ExternalDataLock:
                self.TileList = []
                Tile = MyTile(self.log, title = "Battery Voltage", units = "V", type = "batteryvolts", nominal = 12, callback = self.GetBatteryVoltage, callbackparameters = (True,))
                self.TileList.append(Tile)
                Tile = MyTile(self.log, title = "Utility Voltage", units = "V", type = "linevolts", nominal = self.NominalLineVolts, callback = self.GetUtilityVoltage, callbackparameters = (True,))
                self.TileList.append(Tile)
                Tile = MyTile(self.log, title = "Output Voltage", units = "V", type = "linevolts", nominal = self.NominalLineVolts, callback = self.GetVoltageOutput, callbackparameters = (True,))
                self.TileList.append(Tile)

                if self.NominalFreq == None or self.NominalFreq == "" or self.NominalFreq == "Unknown":
                    self.NominalFreq = "60"
                Tile = MyTile(self.log, title = "Frequency", units = "Hz", type = "frequency", nominal = int(self.NominalFreq), callback = self.GetFrequency, callbackparameters = (False, True))
                self.TileList.append(Tile)

                if self.NominalRPM == None or self.NominalRPM == "" or self.NominalRPM == "Unknown":
                    self.NominalRPM = "3600"
                Tile = MyTile(self.log, title = "RPM", type = "rpm", nominal = int(self.NominalRPM), callback = self.GetRPM, callbackparameters = (True,))
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
                    Tile = MyTile(self.log, title = "Power Output", units = "kW", type = "power", nominal = float(self.NominalKW), callback = self.GetPowerOutput, callbackparameters = (True,))
                    self.TileList.append(Tile)
                    Tile = MyTile(self.log, title = "kW Output", type = "powergraph", nominal = float(self.NominalKW), callback = self.GetPowerOutput, callbackparameters = (True,))
                    self.TileList.append(Tile)

        except Exception as e1:
            self.LogErrorLine("Error in SetupTiles: " + str(e1))
    #---------------------------------------------------------------------------
    def ModelIsValid(self):

        if self.Model == "Unknown" or not len(self.Model) or not self.Model.isalnum() or "generic" in self.Model.lower():
            return False
        return True
    #---------------------------------------------------------------------------
    def GetGenericModel(self):

        if self.LiquidCooled:
            return "Generic Liquid Cooled"
        else:
            return "Generic Air Cooled"

    #---------------------------------------------------------------------------
    def GetGenericKW(self):

        if self.LiquidCooled:
            if self.EvolutionController:
                return "60"
            else:
                return "36"
        else:
            if self.EvolutionController:
                return "22"
            else:
                return "20"
    #---------------------------------------------------------------------------
    def CheckModelSpecificInfo(self, NoLookUp = False):

        try:
            if self.NominalFreq == "Unknown" or not len(self.NominalFreq):
                self.NominalFreq = self.GetModelInfo("Frequency")
                if self.NominalFreq == "Unknown":
                    self.NominalFreq = "60"
                self.config.WriteValue("nominalfrequency", self.NominalFreq)

            # This is not correct for 50Hz models
            if self.NominalRPM == "Unknown" or not len(self.NominalRPM):
                if self.LiquidCooled:
                    if self.NominalFreq == "50":
                        self.NominalRPM = "1500"
                    else:
                        self.NominalRPM = "1800"
                else:
                    if self.NominalFreq == "50":
                        self.NominalRPM = "3000"
                    else:
                        self.NominalRPM = "3600"
                self.config.WriteValue("nominalrpm", self.NominalRPM)

            if self.NominalKW == "Unknown" or not len(self.NominalKW):
                self.NominalKW = self.GetModelInfo("KW")
                if self.NominalKW != "Unknown":
                    self.config.WriteValue("nominalkw", self.NominalKW)

            if self.NewInstall:
                if not self.ModelIsValid() or self.NominalKW == "Unknown":
                    ReturnStatus, ReturnModel, ReturnKW = self.LookUpSNInfo(SkipKW = (not self.NominalKW == "Unknown"), NoLookUp = NoLookUp)
                    if not ReturnStatus:
                        if not self.ModelIsValid():
                            self.Model = self.GetGenericModel()
                            self.config.WriteValue("model", self.Model)
                        if self.NominalKW == "Unknown":
                            self.NominalKW = self.GetGenericKW()
                            self.config.WriteValue("nominalkw", self.NominalKW)
                    else:
                        if ReturnModel == "Unknown":
                            self.Model = self.GetGenericModel()
                        else:
                            self.Model = ReturnModel
                        self.config.WriteValue("model", self.Model)

                        if ReturnKW != "Unknown" and self.NominalKW == "Unknown":   # we found a valid Kw on the lookup
                            self.NominalKW = ReturnKW
                            self.config.WriteValue("nominalkw", self.NominalKW)
                        elif ReturnKW == "Unknown" and self.NominalKW == "Unknown":
                            self.NominalKW = self.GetGenericKW()
                            self.config.WriteValue("nominalkw", self.NominalKW)

            if self.FuelType == "Unknown" or not len(self.FuelType):
                if self.LiquidCooled:
                    self.FuelType = self.GetModelInfo("Fuel")
                    if self.FuelType == "Unknown":
                        if self.Model.startswith("RD"):
                            self.FuelType = "Diesel"
                        elif self.Model.startswith("RG"):
                            if len(self.Model) >= 11:   # e.g. RD04834ADSE
                                if self.Model[8] == "N":
                                    self.FuelType = "Natural Gas"
                                elif self.Model[8] == "V":
                                    self.FuelType = "Propane"
                                else:
                                    self.FuelType = "Propane"
                        elif self.Model.startswith("QT"):
                            self.FuelType = "Propane"
                        elif self.LiquidCooled and self.EvolutionController:          # EvoLC
                            if self.GetModelInfo("Fuel") == "Diesel":
                                self.FuelType = "Diesel"
                            else:
                                self.FuelType = "Natural Gas"
                else:
                    self.FuelType = "Propane"                           # NexusLC, NexusAC, EvoAC
                self.config.WriteValue("fueltype", self.FuelType)

            # This should fix issues with prefious installs of liquid cooled models that had the wrong fuel type
            if self.LiquidCooled:
                FuelType = self.GetModelInfo("Fuel")
                if FuelType != "Unknown" and self.FuelType != FuelType:
                    self.FuelType = FuelType
                    self.config.WriteValue("fueltype", self.FuelType)
            # Set Nominal Line Volts if three phase
            try:
                if not self.UseNominalLineVoltsFromConfig:
                    nomVolts = self.GetModelInfo( "nominalvolts")
                    if nomVolts == "Unknown":
                        self.NominalLineVolts = 240
                    else:
                        self.NominalLineVolts = int(self.GetModelInfo( "nominalvolts"))
            except Exception as e1:
                self.NominalLineVolts = 240
                self.LogErrorLine("Error getting nominal line volts: " + str(e1))
                pass

            self.EngineDisplacement = self.GetModelInfo("EngineDisplacement")
        except Exception as e1:
            self.LogErrorLine("Error in CheckModelSpecificInfo: " + str(e1))

    #----------  GeneratorController::FuelSensorSupported------------------------
    def FuelSensorSupported(self):

        if self.EvolutionController and self.LiquidCooled and self.UseFuelSensor and self.FuelType.lower() == "diesel":
            return True
        return False

    #----------  GeneratorController::GetFuelConsumptionDataPoints--------------
    def GetFuelConsumptionDataPoints(self):

        try:
            if self.FuelType == "Gasoline":
                return None
            if self.EvolutionController:
                return self.GetFuelParamsFromFile()

        except Exception as e1:
            self.LogErrorLine("Error in GetFuelConsumptionDataPoints: " + str(e1))
        return None

    #------------ Evolution:GetFuelParamsFromFile-------------------------------
    def GetFuelParamsFromFile(self):

        try:
            ReturnPoints = []
            if not self.EvolutionController:
                return []
            if self.LiquidCooled:
                FileName = "EvoLC_Fuel.txt"
            else:
                FileName = "EvoAC_Fuel.txt"

            FullFileName = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "data",  FileName)
            ReturnList = self.ReadCSVFile(FullFileName)

            for Item in ReturnList:
                if len(Item) < 9:
                    continue
                if self.LiquidCooled:
                    try:
                        if int(Item[0]) != int(self.NominalKW):
                            continue
                        if Item[1] != self.FuelType:
                            continue
                        ReturnPoints.append(float(Item[4])) # 50%
                        ReturnPoints.append(float(Item[5])) # 50% Rate
                        ReturnPoints.append(float(Item[8])) # 100%
                        ReturnPoints.append(float(Item[9])) # 100% Rate
                        ReturnPoints.append(Item[10])       # Units
                        return ReturnPoints
                    except Exception as e1:
                        self.LogErrorLine("Error in GetFuelParamsFromFile (LC): " + str(e1))
                        continue

                else:   # Air Cooled
                    try:
                        Value = self.GetRegisterValueFromList("0019")
                        if not len(Value):
                            return []

                        if int(Item[0]) != int(Value,16):   #model ID match
                            continue

                        if str(Item[2].strip()) != str(self.FuelType.strip()):
                            continue

                        ReturnPoints.append(float(Item[4]))     # 50%
                        ReturnPoints.append(float(Item[5]))     # 50% Rate
                        ReturnPoints.append(float(Item[6]))     # 100%
                        ReturnPoints.append(float(Item[7]))     # 100% Rate
                        ReturnPoints.append(Item[8])           # Units
                        return ReturnPoints
                    except Exception as e1:
                        self.LogErrorLine("Error in GetFuelParamsFromFile (AC): " + str(e1))
                        continue


        except Exception as e1:
            self.LogErrorLine("Error in GetFuelParamsFromFile: " + str(e1))

        return []

    #------------ Evolution:GetLiquidCooledParams-------------------------------
    def GetLiquidCooledParams(self, ParamGroup, VoltageCode):

        # Nexus LC is the QT line
        # 50Hz : QT02724MNAX
        # QT022, QT027, QT036, QT048, QT080, QT070,QT100,QT130,QT150

        # Evolution LC is the Protector series
        # 50Hz Models: RG01724MNAX, RG02224MNAX, RG02724RNAX
        # RG022, RG025,RG030,RG027,RG036,RG032,RG045,RG038,RG048,RG060
        # RD01523,RD02023,RD03024,RD04834,RD05034

        # Liquid Cooled Units must be matched by the Param Group and Voltage Code settings
        # in the dealer menu

        try:
            if not self.LiquidCooled:
                return None

            if self.EvolutionController:
                FileName = "EvoLCParam.txt"
            else:
                FileName = "NexusLCParam.txt"

            FullFileName = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "data", FileName)
            ReturnList = self.ReadCSVFile(FullFileName)

            for Item in ReturnList:
                if len(Item) < 9:
                    continue
                # Lookup Param Group and # Voltage Code to find kw, phase, etc
                if ParamGroup == int(Item[4]) and VoltageCode == int(Item[5] ):
                    return Item

            self.LogDebug("Unable to find match for Param Group and Voltage Code: " + str(ParamGroup) + ", " + str(VoltageCode))
        except Exception as e1:
            self.LogErrorLine("Error in GetLiquidCooledParams: " + str(e1))

        return None

    #------------ Evolution:GetLiquidCooledModelInfo----------------------------
    def GetLiquidCooledModelInfo(self, Request):

        if self.LiquidCooledParams == None:
            self.LiquidCooledParams = self.GetLiquidCooledParams(self.GetParameter("020a", ReturnInt = True), self.GetParameter("020b", ReturnInt = True))

        if self.LiquidCooledParams == None:
            return "Unknown"

        if len(self.LiquidCooledParams) < 9:
            return "Unknown"

        if Request.lower() == "frequency":
            if self.LiquidCooledParams[2] == "60" or self.LiquidCooledParams[2] == "50":
                return self.LiquidCooledParams[2]
            else:
                return "Unknown"

        elif Request.lower() == "kw":
            return self.LiquidCooledParams[0]
        elif Request.lower() == "phase":
            return self.LiquidCooledParams[3]
        elif Request.lower() == "enginedisplacement":
            return self.LiquidCooledParams[8]
        elif Request.lower() == "nominalvolts":
            return self.LiquidCooledParams[1]
        elif Request.lower() == "fuel":

            Value = self.GetParameter("020c", ReturnInt = True)

            if Value == 0:
                return "Propane"
            if Value == 1:
                return "Natural Gas"
            if Value == 2:
                return "Diesel"
            if len(self.LiquidCooledParams) >= 9:
                if self.LiquidCooledParams[9] == "NG/LPV":
                    return "Propane"
                if self.LiquidCooledParams[9] == "Diesel":
                    return "Diesel"
        return "Unknown"

    #------------ Evolution:GetModelInfo----------------------------------------
    def GetModelInfo(self, Request):

        if self.LiquidCooled == None or self.EvolutionController == None:
            return "Unknown"

        if self.LiquidCooled:
            return self.GetLiquidCooledModelInfo(Request)

        if self.LiquidCooled:
            return "Unknown"

        # List format: [Rated kW, Freq, Voltage, Phase, Engine Displacement, Line Voltage]
        UnknownList = ["Unknown", "Unknown", "Unknown", "Unknown", "Unknown", "Unknown"]

        # Nexus AC
        ModelLookUp_NexusAC = {
                                0 : ["8KW", "60", "120/240", "1", "410 cc", "240"],
                                1 : ["11KW", "60", "120/240", "1", "530 cc", "240"],
                                2 : ["14KW", "60", "120/240", "1", "992 cc", "240"],
                                3 : ["15KW", "60", "120/240", "1", "992 cc", "240"],
                                4 : ["20KW", "60", "120/240", "1", "999 cc", "240"]
                                }
        # This should cover the guardian line
        ModelLookUp_EvoAC = { #ID : [KW or KVA Rating, Hz Rating, Voltage Rating, Phase, Engine Displacement Nominal Line Voltage ]
                                1 : ["9KW", "60", "120/240", "1", "426 cc", "240"],
                                2 : ["14KW", "60", "120/240", "1", "992 cc", "240"],
                                3 : ["17KW", "60", "120/240", "1", "992 cc", "240"],
                                4 : ["20KW", "60", "120/240", "1", "999 cc", "240"],
                                5 : ["8KW", "60", "120/240", "1", "410 cc", "240"],
                                7 : ["13KW", "60", "120/240", "1", "992 cc", "240"],
                                8 : ["15KW", "60", "120/240", "1", "999 cc", "240"],
                                9 : ["16KW", "60", "120/240", "1", "999 cc", "240"],
                                10 : ["20KW", "VSCF", "120/240", "1", "999 cc", "240"],          # Variable Speed Constant Frequency
                                11 : ["15KW", "ECOVSCF", "120/240", "1", "999 cc", "240"],       # Eco Variable Speed Constant Frequency
                                12 : ["8KVA", "50", "220,230,240", "1", "530 cc", "240"],        # 3 distinct models 220, 230, 240
                                13 : ["10KVA", "50", "220,230,240", "1", "992 cc", "240"],       # 3 distinct models 220, 230, 240
                                14 : ["13KVA", "50", "220,230,240", "1", "992 cc", "240"],       # 3 distinct models 220, 230, 240
                                15 : ["11KW", "60" ,"240", "1", "530 cc", "240"],
                                17 : ["22KW", "60", "120/240", "1", "999 cc", "240"],
                                21 : ["11KW", "60", "240 LS", "1", "530 cc", "240"],
                                22 : ["7.5KW", "60", "240", "1", "420 cc", "240"],              # Power Pact
                                32 : ["20KW", "60", "208 3 Phase", "3", "999 cc", "208"],       # Trinity G007077
                                33 : ["Trinity", "50", "380,400,416", "3", None, "380"]         # Discontinued
                                }

        LookUp = None
        if self.EvolutionController:
            LookUp = ModelLookUp_EvoAC
        else:
            LookUp = ModelLookUp_NexusAC

        Value = self.GetRegisterValueFromList("0019")
        if not len(Value):
            return "Unknown"

        ModelInfo = LookUp.get(int(Value,16), UnknownList)

        if ModelInfo == UnknownList:
            self.FeedbackPipe.SendFeedback("ModelID", Message="Model ID register is unknown", FullLogs = True )

        if Request.lower() == "frequency":
            if ModelInfo[1] == "60" or ModelInfo[1] == "50":
                return ModelInfo[1]
            else:
                return "Unknown"

        elif Request.lower() == "kw":
            if "kw" in ModelInfo[0].lower():
                return self.removeAlpha(ModelInfo[0])
            elif "kva" in ModelInfo[0].lower():
                # TODO: This is not right, I think if we take KVA * 0.8 it should equal KW for single phase
                return self.removeAlpha(ModelInfo[0])
            else:
                return "Unknown"

        elif Request.lower() == "phase":
            return ModelInfo[3]

        elif Request.lower() == "enginedisplacement":
            if ModelInfo[4] == None:
                return "Unknown"
            else:
                return ModelInfo[4]
        elif Request.lower() == "nominalvolts":
            return ModelInfo[5]
        return "Unknown"

    #---------------------------------------------------------------------------
    def LookUpSNInfo(self, SkipKW = False, NoLookUp = False):

        if NoLookUp:
            return False

        productId = None
        ModelNumber = None
        ReturnKW = "Unknown"
        ReturnModel = "Unknown"

        SerialNumber = self.GetSerialNumber(retry = True)
        Controller = self.GetController()

        if not len(SerialNumber) or not len(Controller):
            self.LogError("Error in LookUpSNInfo: bad input, no serial number or controller info not present. Possible issue with serial comms.")
            return False, ReturnModel, ReturnKW

        if "none" in SerialNumber.lower() or "unknown" in SerialNumber.lower():      # serial number is not present due to controller being replaced
            self.LogError("Error in LookUpSNInfo: No valid serial number, controller likely replaced.")
            return False, ReturnModel, ReturnKW

        try:
            # for diagnostic reasons we will log the internet search
            self.LogError("Looking up model info on internet using SN: " + str(SerialNumber))
            myregex = re.compile('<.*?>')

            try:
                conn = HTTPSConnection("www.generac.com", 443, timeout=10)
                conn.request("GET", "/GeneracCorporate/WebServices/GeneracSelfHelpWebService.asmx/GetSearchResults?query=" + SerialNumber, "",
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.140 Safari/537.36 Edge/17.17134"})
                r1 = conn.getresponse()
            except Exception as e1:
                conn.close()
                self.LogErrorLine("Error in LookUpSNInfo (request 1): " + str(e1))
                return False, ReturnModel, ReturnKW

            try:
                if sys.version_info[0] < 3:
                    data1 = r1.read()                                   # Python 2.x
                else:
                    encoding = r1.info().get_param('charset', 'utf8')   # Python 3.x
                    data1 = r1.read().decode(encoding)
                data2 = re.sub(myregex, '', data1)
                myresponse1 = json.loads(data2)
                ModelNumber = myresponse1["SerialNumber"]["ModelNumber"]

                if not len(ModelNumber):
                    self.LogError("Error in LookUpSNInfo: Model (response1)")
                    conn.close()
                    return False, ReturnModel, ReturnKW

                self.LogError("Found: Model: %s" % str(ModelNumber))
                ReturnModel = ModelNumber

            except Exception as e1:
                self.LogErrorLine("Error in LookUpSNInfo (parse request 1): " + str(e1))
                conn.close()
                return False, ReturnModel, ReturnKW

            try:
                productId = myresponse1["Results"][0]["Id"]
            except Exception as e1:
                self.LogErrorLine("Notice: product ID not found online. Using serial number to complete lookup." )
                productId = SerialNumber

            if SkipKW:
                return True, ReturnModel, ReturnKW

            try:
                if productId == SerialNumber:
                    conn.request("GET", "/service-support/product-support-lookup/product-manuals?modelNo="+productId, "",
                    headers={"User-Agent": "Mozilla/4.0 (compatible; MSIE 5.01; Windows NT 5.0)"})
                else:
                    conn.request("GET", "/GeneracCorporate/WebServices/GeneracSelfHelpWebService.asmx/GetProductById?productId="+productId, "",
                        headers={"User-Agent": "Mozilla/4.0 (compatible; MSIE 5.01; Windows NT 5.0)"})
                r1 = conn.getresponse()

                if sys.version_info[0] < 3:
                    data1 = r1.read()                                   # Python 2.x
                else:
                    encoding = r1.info().get_param('charset', 'utf8')   # Python 3.x
                    data1 = r1.read().decode(encoding)

                conn.close()
                data2 = re.sub(myregex, '', data1)
            except Exception as e1:
                self.LogErrorLine("Error in LookUpSNInfo (parse request 2, product ID): " + str(e1))

            try:
                if productId == SerialNumber:
                    #within the formatted HTML we are looking for something like this :   "Manuals: 17KW/990 HNYWL+200A SE"
                    ListData = re.split("<div", data1) #
                    for Count in range(len(ListData)):
                        if "Manuals:" in ListData[Count]:
                            KWStr = re.findall(r"(\d+)KW", ListData[Count])[0]
                            if len(KWStr) and KWStr.isdigit():
                                ReturnKW = KWStr

                else:
                    myresponse2 = json.loads(data2)

                    kWRating = myresponse2["Attributes"][0]["Value"]

                    if "kw" in kWRating.lower():
                        kWRating = self.removeAlpha(kWRating)
                    elif "watts" in kWRating.lower():
                        kWRating = self.removeAlpha(kWRating)
                        kWRating = str(int(kWRating) / 1000)
                    else:
                        if int(kWRating) < 1000:
                            kWRating = str(int(kWRating))
                        else:
                            kWRating = str(int(kWRating) / 1000)

                    ReturnKW = kWRating

                    if not len(kWRating):
                        self.LogError("Error in LookUpSNInfo: KW")
                        return False, ReturnModel, ReturnKW

                    self.LogError("Found: KW: %skW" % str(kWRating))

            except Exception as e1:
                self.LogErrorLine("Error in LookUpSNInfo: (parse KW)" + str(e1))
                return False, ReturnModel, ReturnKW

            return True, ReturnModel, ReturnKW
        except Exception as e1:
            self.LogErrorLine("Error in LookUpSNInfo: " + str(e1))
            return False, ReturnModel, ReturnKW


    #-------------Evolution:DetectController------------------------------------
    def DetectController(self, Simulation = False):

        UnknownController = False
        # issue modbus read
        self.ModBus.ProcessTransaction("0000", 1)

        # read register from cached list.
        Value = self.GetRegisterValueFromList("0000")
        if len(Value) != 4:
            return ""
        ProductModel = int(Value,16)

        # 0x03  Nexus, Air Cooled
        # 0x06  Nexus, Liquid Cooled
        # 0x09  Evolution, Air Cooled
        # 0x0c  Evolution, Liquid Cooled

        msgbody = "\nThis email is a notification informing you that the software has detected a generator "
        msgbody += "model variant that has not been validated by the authors of this sofrware. "
        msgbody += "The software has made it's best effort to identify your generator controller type however since "
        msgbody += "your generator is one that we have not validated, your generator controller may be incorrectly identified. "
        msgbody += "To validate this variant, please submit the output of the following command (generator: registers)"
        msgbody += "and your model numbert to the following project thread: https://github.com/jgyates/genmon/issues/10. "
        msgbody += "Once your feedback is receivd we an add your model product code and controller type to the list in the software."

        if self.EvolutionController == None:

            if ProductModel == 0x0a:
                self.SynergyController = True

            if ProductModel == 0x15:
                self.Evolution2 = True

            if ProductModel == 0x12:
                self.PowerPact = True

            if ProductModel == 0x02:
                self.PreNexus = True
            # if reg 000 is 3 or less then assume we have a Nexus Controller
            if ProductModel == 0x03 or ProductModel == 0x06 or ProductModel == 0x02:
                self.EvolutionController = False    #"Nexus"
            elif ProductModel == 0x09 or ProductModel == 0x0c or ProductModel == 0x0a  or ProductModel == 0x15 or ProductModel == 0x12:
                self.EvolutionController = True     #"Evolution"
            else:
                # set a reasonable default
                if ProductModel <= 0x06:
                    self.EvolutionController = False
                else:
                    self.EvolutionController = True

                self.LogError("Warning in DetectController (Nexus / Evolution):  Unverified value detected in model register (%04x)" %  ProductModel)
                self.MessagePipe.SendMessage("Generator Monitor (Nexus / Evolution): Warning at " + self.SiteName, msgbody, msgtype = "error" )
        else:
            self.LogError("DetectController auto-detect override (controller). EvolutionController now is %s" % str(self.EvolutionController))

        if self.LiquidCooled == None:
            if ProductModel == 0x03 or ProductModel == 0x09 or ProductModel == 0x0a  or ProductModel == 0x15  or ProductModel == 0x12 or ProductModel == 0x02:
                self.LiquidCooled = False    # Air Cooled
            elif ProductModel == 0x06 or ProductModel == 0x0c:
                self.LiquidCooled = True     # Liquid Cooled
            else:
                # set a reasonable default
                self.LiquidCooled = False
                self.LogError("Warning in DetectController (liquid / air cooled):  Unverified value detected in model register (%04x)" %  ProductModel)
                self.MessagePipe.SendMessage("Generator Monitor (liquid / air cooled: Warning at " + self.SiteName, msgbody, msgtype = "error" )
        else:
            self.LogError("DetectController auto-detect override (Liquid Cooled). Liquid Cooled now is %s" % str(self.LiquidCooled))

        if not self.EvolutionController:        # if we are using a Nexus Controller, force legacy writes
            self.bUseLegacyWrite = True

        if UnknownController:
            msg = "Unknown Controller Found: %x" % ProductModel
            self.FeedbackPipe.SendFeedback("UnknownController", Message=msg, FullLogs = True)
        return "OK"

    #----------  ControllerGetController  --------------------------------------
    def GetController(self, Actual = True):

        outstr = ""

        if Actual:

            ControllerDecoder = {
                0x02 :  "Pre-Nexus, Air Cooled",
                0x03 :  "Nexus, Air Cooled",
                0x06 :  "Nexus, Liquid Cooled",
                0x09 :  "Evolution, Air Cooled",
                0x0a :  "Synergy Evolution, Air Cooled",
                0x0c :  "Evolution, Liquid Cooled",
                0x12 :  "Power Pact Evolution, Air Cooled",
                0x15 :  "Evolution 2.0, Air Cooled"
            }

            Value = self.GetRegisterValueFromList("0000")
            if len(Value) != 4:
                return ""
            ProductModel = int(Value,16)

            return ControllerDecoder.get(ProductModel, "Unknown 0x%02X" % ProductModel)
        else:

            if self.EvolutionController:
                if self.SynergyController:
                    outstr = "Synergy Evolution, "
                elif self.PowerPact:
                    outstr = "Power Pact Evolution, "
                elif self.Evolution2:
                    outstr = "Evolution 2.0, "
                else:
                    outstr = "Evolution, "
            else:
                if self.PreNexus:
                    outstr = "Pre-Nexus, "
                else:
                    outstr = "Nexus, "
            if self.LiquidCooled:
                outstr += "Liquid Cooled"
            else:
                outstr += "Air Cooled"

        return outstr

    #-------------Evolution:MasterEmulation-------------------------------------
    def MasterEmulation(self):

        counter = 0
        for Reg, Info in self.BaseRegisters.items():

            if counter % 6 == 0:
                for PrimeReg, PrimeInfo in self.PrimeRegisters.items():
                    localTimeoutCount = self.ModBus.ComTimoutError
                    localSyncError = self.ModBus.ComSyncError
                    self.ModBus.ProcessTransaction(PrimeReg, int(PrimeInfo[self.REGLEN] / 2))
                    if self.IsStopping:
                        return
                    if ((localSyncError != self.ModBus.ComSyncError or localTimeoutCount != self.ModBus.ComTimoutError)
                    and self.ModBus.RxPacketCount):
                        # if we get here a timeout occured, and we have recieved at least one good packet
                        # this logic is to keep from receiving a packet that we have already requested once we
                        # timeout and start to request another
                        # Wait for a bit to allow any missed response from the controller to arrive
                        # otherwise this could get us out of sync
                        # This assumes MasterEmulation is called from ProcessThread
                        if self.WaitForExit("ProcessThread", float(self.ModBus.ModBusPacketTimoutMS / 1000.0)):  #
                            return
                        self.ModBus.Flush()
                # check for unknown events (i.e. events we are not decoded) and send an email if they occur
                self.CheckForAlarmEvent.set()

            if self.IsStopping:
                return
            # The divide by 2 is due to the diference in the values in our dict are bytes
            # but modbus makes register request in word increments so the request needs to
            # in word multiples, not bytes
            self.ModBus.ProcessTransaction(Reg, int(Info[self.REGLEN] / 2))
            counter += 1

        # check that we have the serial number, if we do not then retry
        RegStr = "%04x" % SERIAL_NUM_REG
        Value = self.GetRegisterValueFromList(RegStr)       # Serial Number Register
        if len(Value) != 20:
            self.ModBus.ProcessTransaction("%04x" % SERIAL_NUM_REG, SERIAL_NUM_REG_LENGTH)


    #-------------Evolution:UpdateLogRegistersAsMaster--------------------------
    def UpdateLogRegistersAsMaster(self):

        # Start / Stop Log
        for Register in self.LogRange(START_LOG_STARTING_REG , LOG_DEPTH,START_LOG_STRIDE):
            RegStr = "%04x" % Register
            self.ModBus.ProcessTransaction(RegStr, START_LOG_STRIDE)
            if self.IsStopping:
                return

        if self.EvolutionController:
            # Service Log
            for Register in self.LogRange(SERVICE_LOG_STARTING_REG , LOG_DEPTH, SERVICE_LOG_STRIDE):
                RegStr = "%04x" % Register
                self.ModBus.ProcessTransaction(RegStr, SERVICE_LOG_STRIDE)
                if self.IsStopping:
                    return
            # Alarm Log
            for Register in self.LogRange(ALARM_LOG_STARTING_REG , LOG_DEPTH, ALARM_LOG_STRIDE):
                RegStr = "%04x" % Register
                self.ModBus.ProcessTransaction(RegStr, ALARM_LOG_STRIDE)
                if self.IsStopping:
                    return
        else:
            # Alarm Log
            for Register in self.LogRange(NEXUS_ALARM_LOG_STARTING_REG , LOG_DEPTH, NEXUS_ALARM_LOG_STRIDE):
                RegStr = "%04x" % Register
                self.ModBus.ProcessTransaction(RegStr, NEXUS_ALARM_LOG_STRIDE)
                if self.IsStopping:
                    return

    #----------  GeneratorController:TestCommand--------------------------------
    def TestCommand(self, CmdString):

        msgbody = "Invalid command syntax for command testcommand (1)"

        try:
            #Format we are looking for is "testcommand=xx, where xx is a number"
            CmdList = CmdString.split("=")
            if len(CmdList) != 2:
                self.LogError("Validation Error: Error parsing command string in TestCommand (parse): " + CmdString)
                return msgbody

            CmdList[0] = CmdList[0].strip()

            if not CmdList[0].lower() == "testcommand":
                self.LogError("Validation Error: Error parsing command string in TestCommand (parse2): " + CmdString)
                return msgbody

            Command = CmdList[1].strip()
            Command = Command.lower()

        except Exception as e1:
            self.LogErrorLine("Validation Error: Error parsing command string in TestCommand: " + CmdString)
            self.LogError( str(e1))
            return msgbody

        Register = 0
        Value = 0x000               # writing any value to index register is valid for remote start / stop commands

        try:
            Register = int(Command)
        except  Exception as e1:
            self.LogErrorLine("Error parsing testcommand: " + str(e1))
            return msgbody

        if Register < 0 or Register > 16:
            self.LogError("Testcommand supports commands 0 - 16")
            return "Testcommand supports commands 0 - 16"

        self.WriteIndexedRegister(Register, Value)

        return "Test command sent successfully"

    #----------  Evolution:SetGeneratorRemoteCommand--------------------------
    def SetGeneratorRemoteCommand(self, CmdString):

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

        # Index register 0001 controls remote start (data written 0001 to start,I believe ).
        # Index register 0002 controls remote transfer switch (Not sure of the data here )
        Register = 0
        Value = 0x000               # writing any value to index register is valid for remote start / stop commands

        if Command == "start":
            Register = 0x0001       # remote start (radio start)
        elif Command == "stop":
            Register = 0x0000       # remote stop (radio stop)
        elif Command == "starttransfer":
            Register = 0x0002       # start the generator, then engage the transfer transfer switch
        elif Command == "startexercise":
            Register = 0x0003       # remote run in quiet mode (exercise)
        elif Command == "resetalarm":
            Register = 0x000d
        else:
            if self.RemoteButtonsSupported():
                if Command == "auto":
                    Register = 0x000f   # set button to auto
                elif Command == "manual":
                    Register = 0x000e
                elif Command == "off":
                    Register = 0x0010
                else:
                    "Invalid command syntax for command setremote (3)"
            else:
                return "Invalid command syntax for command setremote (2)"

        self.WriteIndexedRegister(Register,Value)

        return "Remote command sent successfully"

    #-------------WriteIndexedRegister------------------------------------------
    def WriteIndexedRegister(self, register, value):

        try:
            with self.ModBus.CommAccessLock:
                #
                LowByte = value & 0x00FF
                HighByte = value >> 8
                Data= []
                Data.append(HighByte)           # Value for indexed register (High byte)
                Data.append(LowByte)            # Value for indexed register (Low byte)

                self.ModBus.ProcessWriteTransaction("0004", len(Data) / 2, Data)

                LowByte = register & 0x00FF
                HighByte = register >> 8
                Data= []
                Data.append(HighByte)           # indexed register to be written (High byte)
                Data.append(LowByte)            # indexed register to be written (Low byte)

                self.ModBus.ProcessWriteTransaction("0003", len(Data) / 2, Data)
        except Exception as e1:
            self.LogErrorLine("Error in WriteIndexedRegister: " + str(e1))

    #-------------MonitorUnknownRegisters---------------------------------------
    def MonitorUnknownRegisters(self,Register, FromValue, ToValue):


        msgbody = ""
        if self.RegisterIsKnown(Register):
            if not self.MonitorRegister(Register):
                return

            msgbody = "%s changed from %s to %s" % (Register, FromValue, ToValue)
            msgbody += "\n"
            msgbody += self.DisplayRegisters()
            msgbody += "\n"
            msgbody += self.DisplayStatus()

            self.MessagePipe.SendMessage("Monitor Register Alert: " + Register, msgbody, msgtype = "warn")

    #----------  Evolution:CalculateExerciseTime--------------------------------
    # helper routine for AltSetGeneratorExerciseTime
    def CalculateExerciseTime(self,MinutesFromNow):

        ReturnedValue = 0x00
        Remainder = MinutesFromNow
        # convert minutes from now to weighted bit value
        if Remainder >= 8738:
            ReturnedValue |= 0x1000
            Remainder -=  8738
        if Remainder >= 4369:
            ReturnedValue |= 0x0800
            Remainder -=  4369
        if Remainder >= 2184:
            ReturnedValue |= 0x0400
            Remainder -=  2185
        if Remainder >= 1092:
            ReturnedValue |= 0x0200
            Remainder -=  1092
        if Remainder >= 546:
            ReturnedValue |= 0x0100
            Remainder -=  546
        if Remainder >= 273:
            ReturnedValue |= 0x0080
            Remainder -=  273
        if Remainder >= 136:
            ReturnedValue |= 0x0040
            Remainder -=  137
        if Remainder >= 68:
            ReturnedValue |= 0x0020
            Remainder -=  68
        if Remainder >= 34:
            ReturnedValue |= 0x0010
            Remainder -=  34
        if Remainder >= 17:
            ReturnedValue |= 0x0008
            Remainder -=  17
        if Remainder >= 8:
            ReturnedValue |= 0x0004
            Remainder -=  8
        if Remainder >= 4:
            ReturnedValue |= 0x0002
            Remainder -=  4
        if Remainder >= 2:
            ReturnedValue |= 0x0001
            Remainder -=  2

        return ReturnedValue

    #----------  Evolution:AltSetGeneratorExerciseTime--------------------------
    # Note: This method is a bit odd but it is how ML does it. It can result in being off by
    # a min or two
    def AltSetGeneratorExerciseTime(self, CmdString):

        # extract time of day and day of week from command string
        # format is day:hour:min  Monday:15:00
        msgsubject = "Generator Command Notice at " + self.SiteName
        msgbody = "Invalid command syntax for command setexercise"
        try:

            DayOfWeek =  {  "monday": 0,        # decode for register values with day of week
                            "tuesday": 1,       # NOTE: This decodes for datetime i.e. Monday=0
                            "wednesday": 2,     # the generator firmware programs Sunday = 0, but
                            "thursday": 3,      # this is OK since we are calculating delta minutes
                            "friday": 4,        # since time of day to set exercise time
                            "saturday": 5,
                            "sunday": 6}

            Day, Hour, Minute, ModeStr = self.ParseExerciseStringEx(CmdString, DayOfWeek)

        except Exception as e1:
            self.LogErrorLine("Validation Error: Error parsing command string in AltSetGeneratorExerciseTime: " + CmdString)
            self.LogError( str(e1))
            return msgbody

        if Minute < 0 or Hour < 0 or Day < 0:     # validate settings
            self.LogError("Validation Error: Error parsing command string in AltSetGeneratorExerciseTime (v1): " + CmdString)
            return msgbody

        if not ModeStr.lower() in ["weekly"]:
            self.LogError("Validation Error: Error parsing command string in AltSetGeneratorExerciseTime (v2): " + CmdString)
            return msgbody

        # Get System time and create a new datatime item with the target exercise time
        GeneratorTime = datetime.datetime.strptime(self.GetDateTime(), "%A %B %d, %Y %H:%M")
        # fix hours and min in gen time to the requested exercise time
        TargetExerciseTime = GeneratorTime.replace(hour = Hour, minute = Minute, day = GeneratorTime.day)
        # now change day of week
        while TargetExerciseTime.weekday() != Day:
            TargetExerciseTime += datetime.timedelta(1)

        # convert total minutes between two datetime objects
        DeltaTime =  TargetExerciseTime - GeneratorTime
        total_delta_min = self.GetDeltaTimeMinutes(DeltaTime)

         # Hour 0 - 23,  Min 0 - 59
        WriteValue = self.CalculateExerciseTime(total_delta_min)

        self.WriteIndexedRegister(0x0006,WriteValue)

        return  "Set Exercise Time Command sent (using legacy write)"

    #----------  Evolution:SetGeneratorExerciseTime-----------------------------
    def SetGeneratorExerciseTime(self, CmdString):

        # use older style write to set exercise time if this flag is set
        if self.bUseLegacyWrite:
            return self.AltSetGeneratorExerciseTime(CmdString)


        # extract time of day and day of week from command string
        # format is day:hour:min  Monday:15:00
        msgbody = "Invalid command syntax for command setexercise"
        try:

            DayOfWeek =  {  "sunday": 0,
                            "monday": 1,        # decode for register values with day of week
                            "tuesday": 2,       # NOTE: This decodes for datetime i.e. Sunday = 0, Monday=1
                            "wednesday": 3,     #
                            "thursday": 4,      #
                            "friday": 5,        #
                            "saturday": 6,
                            }

            Day, Hour, Minute, ModeStr = self.ParseExerciseStringEx(CmdString, DayOfWeek)

        except Exception as e1:
            self.LogErrorLine("Validation Error: Error parsing command string in SetGeneratorExerciseTime: " + CmdString)
            self.LogError( str(e1))
            return msgbody

        if Minute < 0 or Hour < 0 or Day < 0:     # validate Settings
            self.LogError("Validation Error: Error parsing command string in SetGeneratorExerciseTime (v1): " + CmdString)
            return msgbody


        # validate conf file option
        if not self.bEnhancedExerciseFrequency:
            if ModeStr.lower() in ["biweekly", "monthly"]:
                self.LogError("Validation Error: Biweekly and Monthly Exercises are not supported. " + CmdString)
                return msgbody

        with self.ModBus.CommAccessLock:

            if self.bEnhancedExerciseFrequency:
                Data = []
                Data.append(0x00)
                if ModeStr.lower() == "weekly":
                    Data.append(0x00)
                elif ModeStr.lower() == "biweekly":
                    Data.append(0x01)
                elif ModeStr.lower() == "monthly":
                    Data.append(0x02)
                else:
                    self.LogError("Validation Error: Invalid exercise frequency. " + CmdString)
                    return msgbody
                self.ModBus.ProcessWriteTransaction("002d", len(Data) / 2, Data)

            Data = []
            Data.append(0x00)               #
            Data.append(Day)                # Day

            self.ModBus.ProcessWriteTransaction("002e", len(Data) / 2, Data)

            #
            Data = []
            Data.append(Hour)                  #
            Data.append(Minute)                #

            self.ModBus.ProcessWriteTransaction("002c", len(Data) / 2, Data)

        return  "Set Exercise Time Command sent"

    #----------  Evolution:ParseExerciseStringEx--------------------------------
    def ParseExerciseStringEx(self, CmdString, DayDict):

        Day = -1
        Hour = -1
        Minute = -1
        ModeStr = ""
        try:

            #Format we are looking for is :
            # "setexercise=Monday,12:20"  (weekly default)
            # "setexercise=Monday,12:20,weekly"
            # "setexercise=Monday,12:20,biweekly"
            # "setexercise=15,12:20,monthly"

            if "setexercise" not in  CmdString.lower():
                self.LogError("Validation Error: Error parsing command string in ParseExerciseStringEx (setexercise): " + CmdString)
                return Day, Hour, Minute, ModeStr

            Items = CmdString.split(b"=")

            if len(Items) != 2:
                self.LogError("Validation Error: Error parsing command string in ParseExerciseStringEx (command): " + CmdString)
                return Day, Hour, Minute, ModeStr

            ParsedItems = Items[1].split(b",")

            if len(ParsedItems) < 2 or len(ParsedItems) > 3:
                self.LogError("Validation Error: Error parsing command string in ParseExerciseStringEx (items): " + CmdString)
                return Day, Hour, Minute, ModeStr

            DayStr = ParsedItems[0].strip()

            if len(ParsedItems) == 3:
                ModeStr = ParsedItems[2].strip()
            else:
                ModeStr = "weekly"

            if ModeStr.lower() not in ["weekly", "biweekly", "monthly"]:
                self.LogError("Validation Error: Error parsing command string in ParseExerciseStringEx (Mode): " + CmdString)
                return Day, Hour, Minute, ModeStr

            TimeItems = ParsedItems[1].split(b":")

            if len(TimeItems) != 2:
                return Day, Hour, Minute, ModeStr

            HourStr = TimeItems[0].strip()

            MinuteStr = TimeItems[1].strip()

            Minute = int(MinuteStr)
            Hour = int(HourStr)

            if ModeStr.lower() != "monthly":
                Day = DayDict.get(DayStr.lower(), -1)
                if Day == -1:
                    self.LogError("Validation Error: Error parsing command string in ParseExerciseStringEx (day of week): " + CmdString)
                    return -1, -1, -1, ""
            else:
                Day = int(DayStr.lower())

        except Exception as e1:
            self.LogErrorLine("Validation Error: Error parsing command string in ParseExerciseStringEx: " + CmdString)
            self.LogError( str(e1))
            return -1, -1, -1, ""

        if not ModeStr.lower() in ["weekly", "biweekly", "monthly"]:
            self.LogError("Validation Error: Error parsing command string in ParseExerciseStringEx (v2): " + CmdString)
            return -1, -1, -1, ""

        if Minute < 0 or Hour < 0 or Day < 0:     # validate Settings
            self.LogError("Validation Error: Error parsing command string in ParseExerciseStringEx (v3): " + CmdString)
            return -1, -1, -1, ""

        if ModeStr.lower() in ["weekly", "biweekly"]:
            if Minute >59 or Hour > 23 or Day > 6:     # validate Settings
                self.LogError("Validation Error: Error parsing command string in ParseExerciseStringEx (v4): " + CmdString)
                return -1, -1, -1, ""
        else:
            if Minute >59 or Hour > 23 or Day > 28:    # validate Settings
                self.LogError("Validation Error: Error parsing command string in ParseExerciseStringEx (v5): " + CmdString)
                return -1, -1, -1, ""

        return Day, Hour, Minute, ModeStr

    #----------  Evolution:SetGeneratorQuietMode--------------------------------
    def SetGeneratorQuietMode(self, CmdString):

        if not self.EvolutionController or not self.LiquidCooled:
            return "Not supported on this controller."

        # extract quiet mode setting from Command String
        # format is setquiet=yes or setquiet=no
        msgbody = "Invalid command syntax for command setquiet"
        try:
            # format is setquiet=yes or setquiet=no
            CmdList = CmdString.split("=")
            if len(CmdList) != 2:
                self.LogError("Validation Error: Error parsing command string in SetGeneratorQuietMode (parse): " + CmdString)
                return msgbody

            CmdList[0] = CmdList[0].strip()

            if not CmdList[0].lower() == "setquiet":
                self.LogError("Validation Error: Error parsing command string in SetGeneratorQuietMode (parse2): " + CmdString)
                return msgbody

            Mode = CmdList[1].strip()

            if "on" in Mode.lower():
                ModeValue = 0x01
            elif "off" in Mode.lower():
                ModeValue = 0x00
            else:
                self.LogError("Validation Error: Error parsing command string in SetGeneratorQuietMode (value): " + CmdString)
                return msgbody

        except Exception as e1:
            self.LogErrorLine("Validation Error: Error parsing command string in SetGeneratorQuietMode: " + CmdString)
            self.LogError( str(e1))
            return msgbody

        Data= []
        Data.append(0x00)
        Data.append(ModeValue)
        self.ModBus.ProcessWriteTransaction("002f", len(Data) / 2, Data)

        return "Set Quiet Mode Command sent"

    #----------  Evolution:SetGeneratorTimeDate---------------------------------
    def SetGeneratorTimeDate(self):

        # get system time
        d = datetime.datetime.now()

        # attempt to make the seconds zero when we set the generator time so it will
        # be very close to the system time
        # Testing has show that this is not really achieving the seconds synced up, but
        # it does make the time offset consistant
        while d.second != 0:
            time.sleep(60 - d.second)       # sleep until seconds are zero
            d = datetime.datetime.now()

        # We will write three registers at once: 000e - 0010.
        Data= []
        Data.append(d.hour)             #000e
        Data.append(d.minute)
        Data.append(d.month)            #000f
        Data.append(d.day)
        # Note: Day of week should always be zero when setting time
        Data.append(0)                  #0010
        Data.append(d.year - 2000)
        self.ModBus.ProcessWriteTransaction("000e", len(Data) / 2, Data)

    #------------ Evolution:GetRegisterLength ----------------------------------
    def GetRegisterLength(self, Register):

        RegInfoReg = self.BaseRegisters.get(Register, [0,0])

        RegLength = RegInfoReg[self.REGLEN]

        if RegLength == 0:
            RegInfoReg = self.PrimeRegisters.get(Register, [0,0])
            RegLength = RegInfoReg[self.REGLEN]

        return RegLength

    #------------ Evolution:MonitorRegister ------------------------------------
    # return true if we are monitoring this register
    def MonitorRegister(self, Register):

        RegInfoReg = self.BaseRegisters.get(Register, [0,-1])

        MonitorReg = RegInfoReg[self.REGMONITOR]

        if MonitorReg == -1:
            RegInfoReg = self.PrimeRegisters.get(Register, [0,-1])
            MonitorReg = RegInfoReg[self.REGMONITOR]

        if MonitorReg == 1:
            return True
        return False

    #------------ Evolution:ValidateRegister -----------------------------------
    def ValidateRegister(self, Register, Value):

        ValidationOK = True
        # validate the length of the data against the size of the register
        RegLength = self.GetRegisterLength(Register)
        if(RegLength):      # if this is a base register
            if RegLength != (len(Value) / 2):  # note: the divide here compensates between the len of hex values vs string data
                self.LogError("Validation Error: Invalid register length (base) %s:%s %d %d" % (Register, Value, RegLength, len(Value) /2 ))
                ValidationOK = False
        # appears to be Start/Stop Log or service log
        elif int(Register,16) >=  SERVICE_LOG_STARTING_REG and int(Register,16) <= SERVICE_LOG_END_REG:
            if len(Value) != 16:
                self.LogError("Validation Error: Invalid register length (Service) %s %s" % (Register, Value))
                ValidationOK = False
        elif int(Register,16) >=  START_LOG_STARTING_REG and int(Register,16) <= START_LOG_END_REG:
            if len(Value) != 16:
                self.LogError("Validation Error: Invalid register length (Start) %s %s" % (Register, Value))
                ValidationOK = False
        elif int(Register,16) >=  ALARM_LOG_STARTING_REG and int(Register,16) <= ALARM_LOG_END_REG:
            if len(Value) != 20:      #
                self.LogError("Validation Error: Invalid register length (Alarm) %s %s" % (Register, Value))
                ValidationOK = False
        elif int(Register,16) >=  NEXUS_ALARM_LOG_STARTING_REG and int(Register,16) <= NEXUS_ALARM_LOG_END_REG:
            if len(Value) != 16:      # Nexus alarm reg is 16 chars, no alarm codes
                self.LogError("Validation Error: Invalid register length (Nexus Alarm) %s %s" % (Register, Value))
                ValidationOK = False
        elif int(Register,16) == SERIAL_NUM_REG:
            if len(Value) != 20:
                self.LogError("Validation Error: Invalid register length (Model) %s %s" % (Register, Value))
                ValidationOK = False
        else:
            self.LogError("Validation Error: Invalid register or length (Unkown) %s %s" % (Register, Value))
            ValidationOK = False

        return ValidationOK


    #------------ Evolution:RegisterIsLog --------------------------------------
    def RegisterIsLog(self, Register):

        ## Is this a log register
        if int(Register,16) >=  SERVICE_LOG_STARTING_REG and int(Register,16) <= SERVICE_LOG_END_REG and self.EvolutionController:
            return True
        elif int(Register,16) >=  START_LOG_STARTING_REG and int(Register,16) <= START_LOG_END_REG:
            return True
        elif int(Register,16) >=  ALARM_LOG_STARTING_REG and int(Register,16) <= ALARM_LOG_END_REG and self.EvolutionController:
            return True
        elif int(Register,16) >=  NEXUS_ALARM_LOG_STARTING_REG and int(Register,16) <= NEXUS_ALARM_LOG_END_REG and (not self.EvolutionController):
            return True
        elif int(Register,16) == SERIAL_NUM_REG:
            return True
        return False

    #------------ Evolution:UpdateRegisterList ---------------------------------
    def UpdateRegisterList(self, Register, Value, IsString = False, IsFile = False):

        if IsString:
            self.LogError("Validation Error: IsString is True")
        # Validate Register by length
        if len(Register) != 4 or len(Value) < 4:
            self.LogError("Validation Error: Invalid data in UpdateRegisterList: %s %s" % (Register, Value))
            return False

        if not self.RegisterIsKnown(Register):
            self.LogError("Unexpected Register received: " + Register)
            return False
        if not self.ValidateRegister(Register, Value):
            return False
        RegValue = self.Registers.get(Register, "")

        if RegValue == "":
            self.Registers[Register] = Value        # first time seeing this register so add it to the list
        elif RegValue != Value:
            # don't print values of registers we have validated the purpose
            if not self.RegisterIsLog(Register):
                self.MonitorUnknownRegisters(Register,RegValue, Value)
            self.Registers[Register] = Value
            self.Changed += 1
        else:
            self.NotChanged += 1
        return True

    #------------ Evolution:RegisterIsKnown ------------------------------------
    def RegisterIsKnown(self, Register):

        RegLength = self.GetRegisterLength(Register)

        if RegLength != 0:
            return True

        return self.RegisterIsLog(Register)
    #------------ Evolution:DisplayRegisters -----------------------------------
    def DisplayRegisters(self, AllRegs = False, DictOut = False):

        try:
            Registers = collections.OrderedDict()
            Regs = collections.OrderedDict()
            Registers["Registers"] = Regs

            RegList = []

            Regs["Num Regs"] = "%d" % len(self.Registers)
            if self.NotChanged == 0:
                self.TotalChanged = 0.0
            else:
                self.TotalChanged =  float(self.Changed)/float(self.NotChanged)
            Regs["Not Changed"] = "%d" % self.NotChanged
            Regs["Changed"] = "%d" % self.Changed
            Regs["Total Changed"] = "%.2f" % self.TotalChanged

            Regs["Base Registers"] = RegList
            # print all the registers
            for Register, Value in self.Registers.items():

                # do not display log registers or model register
                if self.RegisterIsLog(Register):
                    continue
                ##
                RegList.append({Register:Value})

            Register = "%04x" % SERIAL_NUM_REG
            Value = self.GetRegisterValueFromList(Register)
            if len(Value) != 0:
                RegList.append({Register:Value})

            if AllRegs:
                Regs["Log Registers"]= self.DisplayLogs(AllLogs = True, RawOutput = True, DictOut = True)

            if not DictOut:
                return self.printToString(self.ProcessDispatch(Registers,""))
        except Exception as e1:
            self.LogErrorLine("Error in DisplayRegisters: " + str(e1))

        return Registers
    #------------ Evolution:CheckForOutage -------------------------------------
    # also update min and max utility voltage
    def CheckForOutage(self):

        try:
            if self.DisableOutageCheck:
                # do not check for outage
                return

            if not self.InitComplete:
                return

            UtilityVoltsStr = self.GetUtilityVoltage()
            if not len(UtilityVoltsStr):
                return

            UtilityVolts = self.GetUtilityVoltage(ReturnInt = True)

            # Get threshold voltage
            ThresholdVoltage = self.GetThresholdVoltage(ReturnInt = True)
            # get pickup voltage
            PickupVoltage = self.GetPickUpVoltage(ReturnInt = True)

            # if something is wrong then we use some sensible values here
            if PickupVoltage == 0:
                PickupVoltage = DEFAULT_PICKUP_VOLTAGE
            if ThresholdVoltage == 0:
                ThresholdVoltage = DEFAULT_THRESHOLD_VOLTAGE

            # first time thru set the values to the same voltage level
            if self.UtilityVoltsMin == 0 and self.UtilityVoltsMax == 0:
                self.UtilityVoltsMin = UtilityVolts
                self.UtilityVoltsMax = UtilityVolts

            if UtilityVolts > self.UtilityVoltsMax:
                if UtilityVolts > PickupVoltage:
                    self.UtilityVoltsMax = UtilityVolts

            if UtilityVolts < self.UtilityVoltsMin:
                if UtilityVolts > ThresholdVoltage:
                    self.UtilityVoltsMin = UtilityVolts

            TransferStatus = self.GetTransferStatus()

            if len(TransferStatus):
                if self.TransferActive:
                    if TransferStatus == "Utility":
                        self.TransferActive = False
                        msgbody = "\nPower is being supplied by the utility line. "
                        self.MessagePipe.SendMessage("Transfer Switch Changed State Notice at " + self.SiteName, msgbody, msgtype = "outage")
                else:
                    if TransferStatus == "Generator":
                        self.TransferActive = True
                        msgbody = "\nPower is being supplied by the generator. "
                        self.MessagePipe.SendMessage("Transfer Switch Changed State Notice at " + self.SiteName, msgbody, msgtype = "outage")

            # Check for outage
            # are we in an outage now
            # NOTE: for now we are just comparing these numbers, the generator has a programmable delay
            # that must be met once the voltage passes the threshold. This may cause some "switch bounce"
            # testing needed
            if self.SystemInOutage:
                if UtilityVolts > PickupVoltage:
                    self.SystemInOutage = False
                    self.LastOutageDuration = datetime.datetime.now() - self.OutageStartTime
                    OutageStr = str(self.LastOutageDuration).split(".")[0]  # remove microseconds from string
                    msgbody = "\nUtility Power Restored. Duration of outage " + OutageStr
                    self.MessagePipe.SendMessage("Outage Recovery Notice at " + self.SiteName, msgbody, msgtype = "outage")
                    try:
                        if self.FuelConsumptionSupported():
                            if self.LastOutageDuration.total_seconds():
                                FuelUsed = self.GetPowerHistory("power_log_json=%d,fuel" % self.LastOutageDuration.total_seconds())
                            else:
                                # Outage of zero seconds...
                                if self.UseMetric:
                                    FuelUsed = "0 L"
                                else:
                                    FuelUsed = "0 gal"
                            if len(FuelUsed) and not "unknown" in FuelUsed.lower():
                                OutageStr += "," + FuelUsed
                    except Exception as e1:
                        self.LogErrorLine("Error recording fuel usage for outage: " + str(e1))
                    # log outage to file
                    if self.LastOutageDuration.total_seconds() > self.MinimumOutageDuration:
                        self.LogToFile(self.OutageLog, self.OutageStartTime.strftime("%Y-%m-%d %H:%M:%S"), OutageStr)
            else:
                if UtilityVolts < ThresholdVoltage:
                    self.SystemInOutage = True
                    self.OutageStartTime = datetime.datetime.now()
                    msgbody = "\nUtility Power Out at " + self.OutageStartTime.strftime("%Y-%m-%d %H:%M:%S")
                    self.MessagePipe.SendMessage("Outage Notice at " + self.SiteName, msgbody, msgtype = "outage")
        except Exception as e1:
            self.LogErrorLine("Error in CheckForOutage: " + str(e1))

    #------------ Evolution:CheckForAlarms -------------------------------------
    # Note this must be called from the Process thread since it queries the log registers
    # when in master emulation mode
    def CheckForAlarms(self):

        try:
            # update outage time, update utility low voltage and high voltage
            self.CheckForOutage()

            self.CheckForFirmwareUpdate()
            # now check to see if there is an alarm
            Value = self.GetRegisterValueFromList("0001")
            if len(Value) != 8:
                return              # we don't have a value for this register yet
            RegVal = int(Value, 16)

            if RegVal == self.LastAlarmValue:
                return      # nothing new to report, return

            if self.Evolution2 and self.IgnoreUnknown and not self.Reg0001IsValid(RegVal):
                return
            # if we get past this point there is something to report, either first time through
            # or there is an alarm that has been set or reset
            self.LastAlarmValue = RegVal    # update the stored alarm

            self.UpdateLogRegistersAsMaster()       # Update all log registers

            if self.IsStopping:
                return

            msgsubject = ""
            msgbody = "\n"

            if len(self.UserURL):
                msgbody += "For additional information : " + self.UserURL + "\n"

            if self.SystemInAlarm():        # Update Alarm Status global flag, returns True if system in alarm

                msgsubject += "Generator Alert at " + self.SiteName + ": "
                AlarmState = self.GetAlarmState()

                msgsubject += "CRITICAL "
                if len(AlarmState):
                    msgbody += self.printToString("\nCurrent Alarm: " + AlarmState)
                else:
                    msgbody += self.printToString("\nSystem In Alarm! Please check alarm log")

                msgbody += self.printToString("System In Alarm: 0001:%08x" % RegVal)
                MessageType = "warn"
            else:
                MessageType = "info"
                msgsubject = "Generator Notice: " + self.SiteName
                msgbody += "NOTE: This message is a notice that the state of the generator has changed. The system is not in alarm.\n"

            msgbody += self.DisplayStatus(Reg0001Value = RegVal)

            if self.SystemInAlarm():
                msgbody += self.printToString("\nTo clear the Alarm/Warning message, press OFF on the control panel keypad followed by the ENTER key.")
            else:
                msgbody += self.printToString("\nNo Alarms: 0001:%08x" % RegVal)

            # if option enabled and evo 2.0 detected and result invalid, do not end email.
            sendMessage = True
            if self.Evolution2 and self.IgnoreUnknown and not self.Reg0001IsValid(RegVal):
                sendMessage = False

            if sendMessage:
                self.MessagePipe.SendMessage(msgsubject , msgbody, msgtype = MessageType)

        except Exception as e1:
            self.LogErrorLine("Error in CheckForAlarms: " + str(e1))

    #------------ Evolution:DisplayMaintenance ---------------------------------
    def DisplayMaintenance (self, DictOut = False, JSONNum = False):

        try:
            # use ordered dict to maintain order of output
            # ordered dict to handle evo vs nexus functions
            Maintenance = collections.OrderedDict()
            Maintenance["Maintenance"] = []
            Maintenance["Maintenance"].append({"Model" : self.Model})
            Maintenance["Maintenance"].append({"Generator Serial Number" : self.GetSerialNumber()})
            Maintenance["Maintenance"].append({"Controller Detected" : self.GetController()})
            Maintenance["Maintenance"].append({"Nominal RPM" : self.NominalRPM})
            Maintenance["Maintenance"].append({"Rated kW" : str(self.NominalKW) + " kW"})
            Maintenance["Maintenance"].append({"Nominal Frequency" : str(self.NominalFreq) + " Hz"})
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

            if self.EngineDisplacement != "Unknown":
                Maintenance["Maintenance"].append({"Engine Displacement" : self.UnitsOut( self.EngineDisplacement, type = float, NoString = JSONNum)})


            if self.EvolutionController and self.Evolution2:
                if self.UseMetric:
                    Value = self.ConvertFahrenheitToCelsius(self.GetParameter("05ed", ReturnInt = True))
                    Maintenance["Maintenance"].append({"Ambient Temperature Sensor" : self.ValueOut(Value, "C", JSONNum)})
                else:
                    Maintenance["Maintenance"].append({"Ambient Temperature Sensor" : self.ValueOut(self.GetParameter("05ed", ReturnInt = True), "F", JSONNum)})

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


            ControllerSettings = []
            Maintenance["Maintenance"].append({"Controller Settings" : ControllerSettings})

            if self.EvolutionController and not self.LiquidCooled:
                ControllerSettings.append({"Calibrate Current 1" : self.ValueOut(self.GetParameter("05f6", ReturnInt = True), "", JSONNum)})
                ControllerSettings.append({"Calibrate Current 2" : self.ValueOut(self.GetParameter("05f7", ReturnInt = True), "", JSONNum)})

            if not self.PreNexus:
                ControllerSettings.append({"Calibrate Volts" : self.ValueOut(self.GetParameter("0208", ReturnInt = True), "", JSONNum)})

            ControllerSettings.append({"Nominal Line Voltage" : str(self.GetModelInfo( "nominalvolts")) +  " V"})
            ControllerSettings.append({"Rated Max Power" : str(self.GetModelInfo( "kw")) +  " kW"})
            if self.LiquidCooled:

                ControllerSettings.append({"Param Group" : self.ValueOut(self.GetParameter("020a", ReturnInt = True), "", JSONNum)})
                ControllerSettings.append({"Voltage Code" : self.ValueOut(self.GetParameter("020b", ReturnInt = True), "", JSONNum)})
                ControllerSettings.append({"Phase" : self.GetLiquidCooledModelInfo( "phase")})

                if self.EvolutionController and self.LiquidCooled:
                    # get total hours since activation
                    ControllerSettings.append({"Hours of Protection" : self.ValueOut(self.GetParameter("0054", ReturnInt = True), "h", JSONNum)})
                    ControllerSettings.append({"Volts Per Hertz" : self.ValueOut(self.GetParameter("020e", ReturnInt = True), "", JSONNum)})
                    ControllerSettings.append({"Gain" : self.ValueOut(self.GetParameter("0235", ReturnInt = True), "", JSONNum)})
                    ControllerSettings.append({"Target Frequency" : self.ValueOut(self.GetParameter("005a", ReturnInt = True), "Hz", JSONNum)})
                    ControllerSettings.append({"Target Voltage" : self.ValueOut(self.GetParameter("0059", ReturnInt = True), "V", JSONNum)})

            if not self.SmartSwitch:
                Exercise = []
                Exercise.append({"Exercise Time" : self.GetExerciseTime()})
                if self.EvolutionController and self.LiquidCooled:
                    Exercise.append({"Exercise Duration" : self.GetExerciseDuration()})
                Maintenance["Maintenance"].append({"Exercise" : Exercise})

            Service = []
            Maintenance["Maintenance"].append({"Service" : Service})
            if not self.EvolutionController and self.LiquidCooled:
                # NexusLC
                Service.append({"Air Filter Service Due" : self.GetServiceDue("AIR") + " or " + self.GetServiceDueDate("AIR")})
                Service.append({"Oil Change and Filter Due" : self.GetServiceDue("OIL") + " or " + self.GetServiceDueDate("OIL")})
                Service.append({"Spark Plug Change Due" : self.GetServiceDue("SPARK") + " or " + self.GetServiceDueDate("SPARK")})
            elif not self.EvolutionController and not self.LiquidCooled:
                # Note: On Nexus AC These represent Air Filter, Oil Filter, and Spark Plugs, possibly 5 all together
                # The labels are generic for now until I get clarification from someone with a Nexus AC
                Service.append({"Air Filter Service Due" : self.GetServiceDue("AIR")  + " or " + self.GetServiceDueDate("AIR")})
                Service.append({"Oil and Oil Filter Service Due" : self.GetServiceDue("OIL") + " or " + self.GetServiceDueDate("OIL")})
                Service.append({"Spark Plug Service Due" : self.GetServiceDue("SPARK") + " or " + self.GetServiceDueDate("SPARK")})
                Service.append({"Battery Service Due" : self.GetServiceDue("BATTERY") + " or " + self.GetServiceDueDate("BATTERY")})
            else:
                # Evolution
                if self.PowerPact:
                    Service.append({"Service A Due" : self.GetServiceDue("A")})
                    Service.append({"Service B Due" : self.GetServiceDue("B")})
                else:
                    Service.append({"Service A Due" : self.GetServiceDue("A") + " or " + self.GetServiceDueDate("A")})
                    Service.append({"Service B Due" : self.GetServiceDue("B") + " or " + self.GetServiceDueDate("B")})
                    if not self.LiquidCooled:
                        Service.append({"Battery Check Due" : self.GetServiceDueDate("BATTERY")})

            Service.append({"Total Run Hours" : self.ValueOut(self.GetRunHours(ReturnFloat = True), "h", JSONNum)})
            Service.append({"Hardware Version" : self.GetHardwareVersion()})
            Service.append({"Firmware Version" : self.GetFirmwareVersion()})

        except Exception as e1:
            self.LogErrorLine("Error in DisplayMaintenance: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(Maintenance,""))

        return Maintenance
    #------------ Evolution:signed16--------------------------------------------
    def signed16(self, value):
        return -(value & 0x8000) | (value & 0x7fff)
    #------------ Evolution:signed32--------------------------------------------
    def signed32(self, value):
        return -(value & 0x80000000) | (value & 0x7fffffff)
    #------------ Evolution:DisplayUnknownSensors-------------------------------
    def DisplayUnknownSensors(self):

        Sensors = []

        if not self.bDisplayUnknownSensors:
            return ""

        # Evo Liquid Cooled: ramps up to 300 decimal (1800 RPM)
        # Nexus and Evo Air Cooled: ramps up to 600 decimal on LP/NG   (3600 RPM)
        # this is possibly raw data from RPM sensor
        Sensors.append({"Raw RPM Sensor" : self.GetParameter("003c")})
        Sensors.append({"Hz (Calculated)" : self.GetFrequency(Calculate = True)})

        if self.EvolutionController and self.LiquidCooled:
            # get total hours since activation
            Sensors.append({"Battery Charger Sensor" : self.GetParameter("05ee", Divider = 100.0)})
            Sensors.append({"Battery Status (Sensor)" : self.GetBatteryStatusAlternate()})

             # get UKS
            Value = self.GetUnknownSensor("05ed")
            if len(Value):
                # Shift by one then  apply this formula
                # The shift by one appears
                # Sensor values odd below 60 decimal, even above 60 decimal (60 shift right 1 is 30 which is 11.5C or 52.7F)
                SensorValue = int(Value) >> 1
                Celsius = float((-0.2081* SensorValue**2)+(10.928*SensorValue)-129.02)
                Fahrenheit = 9.0/5.0 * Celsius + 32
                CStr = "%.1f" % Celsius
                FStr = "%.1f" % Fahrenheit
                Sensors.append({"Ambient Temp Thermistor" : "Sensor: " + Value + ", " + CStr + "C, " + FStr + "F"})

        if self.EvolutionController and self.Evolution2:
            Sensors.append({"Battery Charger Sensor" : self.GetParameter("05ee", Divider = 100.0)})
            Sensors.append({"Battery Status (Sensor)" : self.GetBatteryStatusAlternate()})


        if not self.LiquidCooled:       # Nexus AC and Evo AC

            # starts  0x4000 when idle, ramps up to ~0x2e6a while running
            Value = self.GetUnknownSensor("0032", RequiresRunning = True)
            if len(Value):
                FloatTemp = int(Value) / 100.0
                FloatStr = "%.2f" % FloatTemp
                Sensors.append({"Unsupported Sensor 1 (0x0032)" : FloatStr})

            Value = self.GetUnknownSensor("0033")
            if len(Value):
                Sensors.append({"Unsupported Sensor 2 (0x0033)" : Value})

            # return -2 thru 2
            Value = self.GetUnknownSensor("0034")
            if len(Value):
                SignedStr = str(self.signed16( int(Value)))
                Sensors.append({"Unsupported Sensor 3 (0x0034)" : SignedStr})


        return Sensors

    #------------ Evolution:LogRange -------------------------------------------
    # used for iterating log registers
    def LogRange(self, start, count, step):
        Counter = 0
        while Counter < count:
            yield start
            start += step
            Counter += 1

    #------------ Evolution:GetOneLogEntry -------------------------------------
    def GetOneLogEntry(self, Register, LogBase, RawOutput = False):

        outstring = ""
        RegStr = "%04x" % Register
        Value = self.GetRegisterValueFromList(RegStr)
        if len(Value) == 0:
            return False, ""
        if not RawOutput:
            LogStr = self.ParseLogEntry(Value, LogBase = LogBase)
            if len(LogStr):             # if the register is there but no log entry exist
                outstring += self.printToString(LogStr, nonewline = True)
        else:
            outstring += self.printToString("%s:%s" % (RegStr, Value), nonewline = True)

        return True, outstring

    #------------ Evolution:GetLogs --------------------------------------------
    def GetLogs(self, Title, StartReg, Stride, AllLogs = False, RawOutput = False):

        # The output will be a Python Dictionary with a key (Title) and
        # the entry will be a list of strings (or one string if not AllLogs,

        RetValue = collections.OrderedDict()
        LogList = []
        Title = Title.strip()
        Title = Title.replace(":","")

        if AllLogs:
            for Register in self.LogRange(StartReg , LOG_DEPTH, Stride):
                bSuccess, LogEntry = self.GetOneLogEntry(Register, StartReg, RawOutput)
                if not bSuccess or len(LogEntry) == 0:
                    break
                LogList.append(LogEntry)

            RetValue[Title] = LogList
            return RetValue
        else:
            bSuccess, LogEntry = self.GetOneLogEntry(StartReg, StartReg, RawOutput)
            if bSuccess:
                RetValue[Title] = LogEntry
            return RetValue

    #------------ Evolution:DisplayLogs ----------------------------------------
    def DisplayLogs(self, AllLogs = False, DictOut = False, RawOutput = False):

        try:
            # if DictOut is True, return a dictionary containing a Dictionaries (dict entry for each log)
            # Each dict item a log (alarm, start/stop). For Example:
            #
            #       Dict[Logs] =  {"Alarm Log" : [Log Entry1, LogEntry2, ...]},
            #                     {"Start Stop Log" : [Log Entry3, Log Entry 4, ...]}...

            ALARMLOG     = "Alarm Log:     "
            SERVICELOG   = "Service Log:   "
            STARTSTOPLOG = "Run Log:"

            EvolutionLog = [[ALARMLOG, ALARM_LOG_STARTING_REG, ALARM_LOG_STRIDE],
                            [SERVICELOG, SERVICE_LOG_STARTING_REG, SERVICE_LOG_STRIDE],
                            [STARTSTOPLOG, START_LOG_STARTING_REG, START_LOG_STRIDE]]
            NexusLog     = [[ALARMLOG, NEXUS_ALARM_LOG_STARTING_REG, NEXUS_ALARM_LOG_STRIDE],
                            [STARTSTOPLOG, START_LOG_STARTING_REG, START_LOG_STRIDE]]

            LogParams = EvolutionLog if self.EvolutionController else NexusLog

            RetValue = collections.OrderedDict()
            LogDict = collections.OrderedDict()

            for Params in LogParams:
                LogOutput = self.GetLogs(Params[0], Params[1], Params[2], AllLogs, RawOutput)
                LogDict = self.MergeDicts(LogDict,LogOutput)

            RetValue["Logs"] = LogDict

            UnknownFound = False
            for Key, Entries in RetValue["Logs"].items():
                if not AllLogs:
                    if "unknown" in Entries.lower():
                        UnknownFound = True
                        break
                else:
                    for LogItems in Entries:
                        if "unknown" in LogItems.lower():
                            UnknownFound = True
                            break
            if UnknownFound:
                msgbody = "\nThe output appears to have unknown values. Please see the following threads to resolve these issues:"
                msgbody += "\n        https://github.com/jgyates/genmon/issues/12"
                msgbody += "\n        https://github.com/jgyates/genmon/issues/13"
                RetValue["Note"] = msgbody
                self.FeedbackPipe.SendFeedback("Logs", FullLogs = True, Always = True, Message="Unknown Entries in Log")
        except Exception as e1:
            self.LogErrorLine("Error in DisplayLogs: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(RetValue,""))

        return RetValue

    #----------  Evolution:ParsePreNexusLog-------------------------------------
    # This function will parse log entries for Pre-Nexus models
    # #     AABBCCDDEEFFGGHH
    #       AA = log entry number
    #       BB = Log Code - Unique Value for displayable string
    #       CC = Hour
    #       DD = minutes
    #       EE = seconds
    #       FF = Month
    #       GG = Date
    #       HH = year
    #---------------------------------------------------------------------------
    def ParsePreNexusLog(self, Value, LogBase = None):

        # Nexus    14071b12090e1212
        # PreNexus be040f2d0b031d13 = "03/29/19 15:45:11 RPM Sense Loss"

        if len(Value) < 16:
            self.LogError("Error in  ParsePreNexusLog length check (16)")
            return None,None,None,None,None,None,None

        TempVal = Value[10:12]
        Month = int(TempVal, 16)
        if Month == 0 or Month > 12:    # validate month
            # This is the normal return path for an empty log entry
            return None,None,None,None,None,None,None

        TempVal = Value[6:8]
        Min = int(TempVal, 16)
        if Min >59:                     # validate minute
            self.LogError("Error in  ParsePreNexusLog minutes check")
            return None,None,None,None,None,None,None

        TempVal = Value[4:6]
        Hour = int(TempVal, 16)
        if Hour > 23:                   # validate hour
            self.LogError("Error in  ParsePreNexusLog hours check")
            return None,None,None,None,None,None,None

        # Seconds
        TempVal = Value[8:10]
        Seconds = int(TempVal, 16)
        if Seconds > 59:
            self.LogError("Error in  ParsePreNexusLog seconds check")
            return None,None,None,None,None,None,None

        TempVal = Value[12:14]
        Day = int(TempVal, 16)
        if Day == 0 or Day > 31:        # validate day
            self.LogError("Error in  ParsePreNexusLog day check")
            return None,None,None,None,None,None,None

        TempVal = Value[14:16]
        Year = int(TempVal, 16)         # year

        TempVal = Value[2:4]            # this value represents a unique display string
        LogCode = int(TempVal, 16)

        return Month,Day,Year,Hour,Min, Seconds, LogCode
    #----------  Evolution:ParseLogEntry----------------------------------------
    #  Log Entries are in one of two formats, 16 (On off Log, Service Log) or
    #   20 chars (Alarm Log)
    #     AABBCCDDEEFFGGHHIIJJ
    #       AA = Log Code - Unique Value for displayable string
    #       BB = log entry number
    #       CC = minutes
    #       DD = hours
    #       EE = Month
    #       FF = Date
    #       GG = year
    #       HH = seconds
    #       IIJJ = Alarm Code for Alarm Log only
    #---------------------------------------------------------------------------
    def ParseLogEntry(self, Value, LogBase = None):
        # This should be the same for all models
        StartLogDecoder = {
        0x28: "Switched Off",               # Start / Stop Log
        0x29: "Running - Manual",           # Start / Stop Log
        0x2A: "Stopped - Auto",             # Start / Stop Log
        0x2B: "Running - Utility Loss",     # Start / Stop Log
        0x2C: "Running - 2 Wire Start",     # Start / Stop Log
        0x2D: "Running - Remote Start",     # Start / Stop Log
        0x2E: "Running - Exercise",         # Start / Stop Log
        0x2F: "Stopped - Alarm"             # Start / Stop Log
        # Stopped Alarm
        }

        # This should be the same for all Evo models , Not sure about service C, this may be a Nexus thing
        ServiceLogDecoder = {
        0x16: "Service Schedule B",         # Maint
        0x17: "Service Schedule A",         # Maint
        0x18: "Inspect Battery",
        0x3C: "Schedule B Serviced",        # Maint
        0x3D: "Schedule A Serviced",        # Maint
        0x3E: "Battery Maintained",
        0x3F: "Maintenance Reset"
        # This is from the diagnostic manual.
        # *Schedule Service A
        # Schedule Service B
        # Schedule Service C
        # *Schedule A Serviced
        # Schedule B Serviced
        # Schedule C Serviced
        # Inspect Battery
        # Maintenance Reset
        # Battery Maintained
        }

        AlarmLogDecoder_EvoLC = {
        0x04: "RPM Sense Loss",             # 1500 Alarm
        0x06: "Low Coolant Level",          # 2720  Alarm
        0x47: "Low Fuel Level",             # 2700A Alarm
        0x1B: "Low Fuel Level",             # 2680W Alarm
        0x46: "Ruptured Tank",              # 2710 Alarm
        0x49: "Hall Calibration Error"      # 2810  Alarm
        # Low Oil Pressure
        # High Engine Temperature
        # Overcrank
        # Overspeed
        # RPM Sensor Loss
        # Underspeed
        # Underfrequency
        # Wiring Error
        # Undervoltage
        # Overvoltage
        # Internal Fault
        # Firmware Error
        # Stepper Overcurrent
        # Fuse Problem
        # Ruptured Basin
        # Canbus Error
        ####Warning Displays
        # Low Battery
        # Maintenance Periods
        # Exercise Error
        # Battery Problem
        # Charger Warning
        # Charger Missing AC
        # Overload Cooldown
        # USB Warning
        # Download Failure
        # FIRMWARE ERROR-9
        }

        # Evolution Air Cooled Decoder
        # NOTE: Warnings on Evolution Air Cooled have an error code of zero
        AlarmLogDecoder_EvoAC = {
        0x13 : "FIRMWARE ERROR-25",
        0x14 : "Low Battery",
        0x15 : "Exercise Set Error",
        0x16 : "Service Schedule B",
        0x17 : "Service Schedule A ",
        0x18 : "Inspect Battery",
        0x19 : "SEEPROM ABUSE",
        0x1c : "Stopping.....",
        0x1d : "FIRMWARE ERROR-9",
        0x1e : "Fuel Pressure",
        0x1f : "Battery Problem",
        0x20 : "Charger Warning",
        0x21 : "Charger Missing AC",
        0x22 : "Overload Warning",
        0x23 : "Overload Cooldown",
        0x25 : "VSCF Warning",
        0x26 : "USB Warning",
        0x27 : "Download Failure",
        0x28 : "High Engine Temp",
        0x29 : "Low Oil Pressure",
        0x2a : "Overcrank",
        0x2b : "Overspeed",
        0x2c : "RPM Sense Loss",
        0x2d : "Underspeed",
        0x2e : "Controller Fault",
        0x2f : "FIRMWARE ERROR-7",
        0x30 : "WIRING ERROR",
        0x31 : "Over Voltage",
        0x32 : "Under Voltage",
        0x33 : "Overload Remove Load",
        0x34 : "Low Volts Remove Load",
        0x35 : "Stepper Over Current",
        0x36 : "Fuse Problem",
        0x39 : "Loss of Speed Signal",
        0x3a : "Loss of Serial Link ",
        0x3b : "VSCF Alarm",
        0x3c : "Schedule B Serviced",
        0x3d : "Schedule A Serviced",
        0x3e : "Battery Maintained",
        0x3f : "Maintenance Reset",
        0x78 : "No Wi-Fi Module"             # Validated on Evolution 2 Air Cooled
        }

        NexusAlarmLogDecoder = {
        0x00 : "High Engine Temperature",    # Validated on Nexus Air Cooled
        0x01 : "Low Oil Pressure",           # Validated on Nexus Liquid Cooled
        0x02 : "Overcrank",                  # Validated on Nexus Air Cooled
        0x03 : "Overspeed",                  # Validated on Nexus Air Cooled
        0x04 : "RPM Sense Loss",             # Validated on Nexus Liquid Cooled and Air Cooled
        0x05 : "Underspeed",
        0x08 : "WIRING ERROR",               # Validasted on Nexus Air Cooled
        #0x09 : "UNKNOWN",
        0x0a : "Under Voltage",              #  Validated on Nexus AC
        0x0B : "Low Cooling Fluid",          # Validated on Nexus Liquid Cooled
        0x0C : "Canbus Error",               # Validated on Nexus Liquid Cooled
        0x0D : "Missing Cam Pulse",          # Validate on Nexus Liquid Cooled
        0x0E : "Missing Crank Pulse",        # Validate on Nexus Liquid Cooled
        0x0F : "Govenor Fault",              # Validated on Nexus Liquid Cooled
        0x10 : "Ignition Fault",             # Validate on Nexus Liquid Cooled
        0x14 : "Low Battery",                # Validated on Nexus Air Cooled
        0x16 : "Change Oil & Filter",        # Validated on Nexus Air Cooled
        0x17 : "Inspect Air Filter",         # Validated on Nexus Air Cooled
        0x19 : "Inspect Spark Plugs",        # Validated on Nexus Air Cooled
        0x1b : "Inspect Battery",            # Validated on Nexus Air Cooled
        0x1E : "Low Fuel Pressure",          # Validated on Nexus Liquid Cooled
        0x21 : "Service Schedule A",         # Validated on Nexus Liquid Cooled
        0x22 : "Service Schedule B"          # Validated on Nexus Liquid Cooled
        }

        # Service Schedule log and Start/Stop Log are 16 chars long
        # error log is 20 chars log
        if len(Value) < 16:
            self.LogError("Error in  ParseLogEntry length check (16)")
            return ""

        if self.PreNexus:
            Month,Day,Year,Hour,Min, Seconds, LogCode = self.ParsePreNexusLog( Value, LogBase = LogBase)
            if Month == None:
                return ""
        else:
            if len(Value) > 20:
                self.LogError("Error in  ParseLogEntry length check (20)")
                return ""

            TempVal = Value[8:10]
            Month = int(TempVal, 16)
            if Month == 0 or Month > 12:    # validate month
                # This is the normal return path for an empty log entry
                return ""

            TempVal = Value[4:6]
            Min = int(TempVal, 16)
            if Min >59:                     # validate minute
                self.LogError("Error in  ParseLogEntry minutes check")
                return ""

            TempVal = Value[6:8]
            Hour = int(TempVal, 16)
            if Hour > 23:                   # validate hour
                self.LogError("Error in  ParseLogEntry hours check")
                return ""

            # Seconds
            TempVal = Value[10:12]
            Seconds = int(TempVal, 16)
            if Seconds > 59:
                self.LogError("Error in  ParseLogEntry seconds check")
                return ""

            TempVal = Value[14:16]
            Day = int(TempVal, 16)
            if Day == 0 or Day > 31:        # validate day
                self.LogError("Error in  ParseLogEntry day check")
                return ""

            TempVal = Value[12:14]
            Year = int(TempVal, 16)         # year

            TempVal = Value[0:2]            # this value represents a unique display string
            LogCode = int(TempVal, 16)

        DecoderLookup = {}

        if self.EvolutionController and not self.LiquidCooled:
            DecoderLookup[ALARM_LOG_STARTING_REG] = AlarmLogDecoder_EvoAC
            DecoderLookup[SERVICE_LOG_STARTING_REG] = AlarmLogDecoder_EvoAC
        else:
            DecoderLookup[ALARM_LOG_STARTING_REG] = AlarmLogDecoder_EvoLC
            DecoderLookup[SERVICE_LOG_STARTING_REG] = ServiceLogDecoder

        DecoderLookup[START_LOG_STARTING_REG] = StartLogDecoder
        DecoderLookup[NEXUS_ALARM_LOG_STARTING_REG] = NexusAlarmLogDecoder

        if LogBase == NEXUS_ALARM_LOG_STARTING_REG and self.EvolutionController:
            self.LogError("Error in ParseLog: Invalid Base Register %X", LogBase)
            return "Error Parsing Log Entry"

        Decoder = DecoderLookup.get(LogBase, "Error Parsing Log Entry")

        if isinstance(Decoder, str):
            self.LogError("Error in ParseLog: Invalid Base Register %X", ALARM_LOG_STARTING_REG)
            return Decoder

        # Get the readable string, if we have one
        LogStr = Decoder.get(LogCode, "Unknown 0x%02X" % LogCode)

        # This is a numeric value that increments for each new log entry
        TempVal = Value[2:4]
        EntryNumber = int(TempVal, 16)

        # this will attempt to find a description for the log entry based on the info in ALARMS.txt
        if LogBase == ALARM_LOG_STARTING_REG and "unknown" in LogStr.lower() and  self.EvolutionController and len(Value) > 16:
            TempVal = Value[16:20]      # get alarm code
            AlarmStr = self.GetAlarmInfo(TempVal, ReturnNameOnly = True, FromLog = True)
            if not "unknown" in AlarmStr.lower():
                LogStr = AlarmStr

        RetStr = "%02d/%02d/%02d %02d:%02d:%02d %s " % (Month,Day,Year,Hour,Min, Seconds, LogStr)
        if len(Value) > 16:
            TempVal = Value[16:20]
            AlarmCode = int(TempVal,16)
            RetStr += ": Alarm Code: %04d" % AlarmCode

        return RetStr

    #------------------- Evolution:GetAlarmInfo --------------------------------
    # Read file alarm file and get more info on alarm if we have it
    # passes ErrorCode as string of hex values
    def GetAlarmInfo(self, ErrorCode, ReturnNameOnly = False, FromLog = False):

        if not self.EvolutionController:
            return ""
        try:
            # Evolution Air Cooled will give a code of 0000 for warnings
            # Note: last error code can be zero if controller was power cycled
            if ErrorCode == "0000":
                if ReturnNameOnly:
                    # We should not see a zero in the alarm log, this would indicate a true UNKNOWN
                    # returning unknown here is OK since ParseLogEntry will look up a code also
                    return "Warning Code Unknown: %d" % int(ErrorCode,16)
                else:
                    # This can occur if the controller was power cycled and not alarms have occurred since power applied
                    return "Error Code 0000: No alarms occured since controller has been power cycled.\n"

            with open(self.AlarmFile,"r") as AlarmFile:     #opens file

                for line in AlarmFile:
                    line = line.strip()                   # remove newline at beginning / end and trailing whitespace
                    if not len(line):
                        continue
                    if line[0] == "#":              # comment?
                        continue
                    Items = line.split("!")
                    if len(Items) != 5:
                        continue
                    if Items[0] == str(int(ErrorCode,16)):
                        if ReturnNameOnly:
                            outstr = Items[2]
                        else:
                            outstr =  Items[2] + ", Error Code: " + Items[0] + "\n" + "    Description: " + Items[3] + "\n" + "    Additional Info: " + Items[4] + "\n"
                        return outstr

        except Exception as e1:
            self.LogErrorLine("Error in  GetAlarmInfo " + str(e1))

        AlarmCode = int(ErrorCode,16)
        return "Error Code Unknown: %04d\n" % AlarmCode

    #------------ Evolution:GetSerialNumber ------------------------------------
    def GetSerialNumber(self, retry = False):

        # serial number format:
        # Hex Register Values:  30 30 30 37 37 32 32 39 38 37 -> High part of each byte = 3, low part is SN
        #                       decode as s/n 0007722987
        # at present I am guessing that the 3 that is interleaved in this data is the line of gensets (air cooled may be 03?)

        if self.PreNexus:
            # Pre-Nexus does not have a serial number
            if self.SerialNumberReplacement != None:
                return self.SerialNumberReplacement
            return "Unknown"
        RegStr = "%04x" % SERIAL_NUM_REG
        Value = self.GetRegisterValueFromList(RegStr)       # Serial Number Register
        if len(Value) != 20:
            # retry reading serial number
            if retry:
                self.ModBus.ProcessTransaction("%04x" % SERIAL_NUM_REG, SERIAL_NUM_REG_LENGTH)
            return ""

        # all nexus and evolution models should have all "f" for values.
        if (Value[0] == 'f' and Value[1] == 'f'):
            if self.SerialNumberReplacement != None:
                return self.SerialNumberReplacement
            # this occurs if the controller has been replaced
            return "None - Controller has been replaced"

        SerialNumberHex = 0x00
        BitPosition = 0
        for Index in range(len(Value) -1 , 0, -1):
            TempVal = Value[Index]
            if (Index & 0x01 == 0):     # only odd positions
                continue

            HexVal = int(TempVal, 16)
            SerialNumberHex = SerialNumberHex | ((HexVal) << (BitPosition))
            BitPosition += 4

        return "%010x" % SerialNumberHex

    #------------ Evolution:GetTransferStatus ----------------------------------
    def GetTransferStatus(self):

        if not self.EvolutionController:
            return ""                           # Nexus

        if not self.LiquidCooled:               # Evolution AC
            return ""

        return self.GetParameterBit("0053", 0x01, OnLabel = "Generator", OffLabel = "Utility")

    ##------------ Evolution:SystemInAlarm -------------------------------------
    def SystemInAlarm(self):

        AlarmState = self.GetAlarmState()

        if len(AlarmState):
            self.GeneratorInAlarm = True
            return True

        self.GeneratorInAlarm = False
        return False

    ##------------ Evolution:GetAlarmState -------------------------------------
    def GetAlarmState(self):

        strSwitch = self.GetSwitchState()

        if len(strSwitch) == 0 or not "alarm" in strSwitch.lower():
            return ""

        outString = ""

        Value = self.GetRegisterValueFromList("0001")
        if len(Value) != 8:
            return ""
        RegVal = int(Value, 16)


        # These codes indicate an alarm needs to be reset before the generator will run again
        AlarmValues = {
         0x01 : "Low Battery",          #  Validate on Nexus, occurred when Low Battery Alarm
         0x02 : "High Temperature",     #  Validaed on EvoAC
         0x05 : "Low Fuel Pressure",    #  Validate on Nexus LC
         0x08 : "Low Coolant",          #  Validate on Evolution, occurred when forced low coolant
         0x0a : "Low Oil Pressure",     #  Validate on Nexus Air Cooled.
         0x0b : "Overcrank",            #  Validate on NexusAC
         0x0c : "Overspeed",            #  Validated on Nexus AC
         0x0d : "RPM Sense Loss",       #  Validate on Evolution, occurred when forcing RPM sense loss from manual start
         0x0f : "Change Oil & Filter",  #  Validate on Nexus AC
         0x10 : "Inspect Air Filter",   #  Validate on Nexus LC
         0x12 : "Check for Service",    #  Validate on Nexus AC (Spark Plugs service due?)
         0x14 : "Check Battery",        #  Validate on Nexus, occurred when Check Battery Alarm
         0x15 : "Underspeed",           #  Validate on Evo AC 2
         0x1a : "Missing Cam Pulse",    #  Validate on Nexus Liquid Cooled
         0x1c : "Throttle Failure",     #  Validate on Nexus LC,
         0x1e : "Under Voltage",        #  Validate on EvoAC
         0x1f : "Service Due",          #  Validate on Evolution, occurred when forced service due
         0x20 : "Service Complete",     #  Validate on Evolution, occurred when service reset
         0x24 : "Overload",             #  Validate on Evolution Air Cooled
         0x28 : "Fuse Problem",         #  Validate on Evolution Air Cooled
         0x29 : "Battery Problem",      #  Validate on EvoLC
         0x2a : "Charger Warning",      #  Validate on EvoAC 2
         0x2b : "Charger Missing AC",   #  Validate on EvoAC, occurred when Charger Missing AC Warning
         0x30 : "Ruptured Tank",        #  Validate on Evolution, occurred when forced ruptured tank
         0x31 : "Low Fuel Level",       #  Validate on Evolution, occurred when Low Fuel Level
         0x32 : "Low Fuel Pressure",    #  Validate on EvoLC
         0x34 : "Emergency Stop"        #  Validate on Evolution, occurred when E-Stop
        }

        outString += AlarmValues.get(RegVal & 0x0FFFF,"UNKNOWN ALARM: %08x" % RegVal)
        if "unknown" in outString.lower():
            self.FeedbackPipe.SendFeedback("Alarm", Always = True, Message = "Reg 0001 = %08x" % RegVal, FullLogs = True )

        if self.EvolutionController and "unknown" in outString.lower():
            # This method works in most cases for Evolution. Service due is an exception to
            # this. Reg 051f is not updated with service due alarms.
            Value = self.GetRegisterValueFromList("05f1")   # get last error code
            if len(Value) == 4:
                AlarmStr = self.GetAlarmInfo(Value, ReturnNameOnly = True)
                if not "unknown" in AlarmStr.lower():
                    outString = AlarmStr

        return outString
    #------------ Evolution:Reg0001IsValid -------------------------------------
    def Reg0001IsValid(self, regvalue):

        if regvalue & 0xFFF0FFC0:
            return False
        return True
    #------------ Evolution:GetDigitalValues -----------------------------------
    def GetDigitalValues(self, RegVal, LookUp):

        outvalue = ""
        counter = 0x01

        for BitMask, Items in LookUp.items():
            if len(Items[1]):
                if self.BitIsEqual(RegVal, BitMask, BitMask):
                    if Items[0]:
                        outvalue += "%s, " % Items[1]
                else:
                    if not Items[0]:
                        outvalue += "%s, " % Items[1]
        # take of the last comma
        ret = outvalue.rsplit(",", 1)
        return ret[0]

    ##------------ Evolution:GetSensorInputs -----------------------------------
    def GetSensorInputs(self):

        # at the moment this has only been validated on an Evolution Liquid cooled generator
        # so we will disallow any others from this status
        if not self.EvolutionController:
            return ""        # Nexus

        if not self.LiquidCooled:
            return ""

        # Dict format { bit position : [ Polarity, Label]}
        # Air cooled
        DealerInputs_Evo_AC = { 0x0001: [True, "Manual"],         # Bits 0 and 1 are only momentary (i.e. only set if the button is being pushed)
                                0x0002: [True, "Auto"],           # Bits 0 and 1 are only set in the controller Dealer Test Menu
                                0x0008: [True, "Wiring Error"],
                                0x0020: [True, "High Temperature"],
                                0x0040: [True, "Low Oil Pressure"]}

        DealerInputs_Evo_LC = {
                                0x0001: [True, "Manual Button"],    # Bits 0, 1 and 2 are momentary and only set in the controller
                                0x0002: [True, "Auto Button"],      #  Dealer Test Menu, not in this register
                                0x0004: [True, "Off Button"],
                                0x0008: [True, "2 Wire Start"],
                                0x0010: [True, "Wiring Error"],
                                0x0020: [True, "Ruptured Basin"],
                                0x0040: [False, "E-Stop Activated"],
                                0x0080: [True, "Oil below 8 psi"],
                                0x0100: [True, "Low Coolant"],
                                #0x0200: [False, "Fuel below 5 inch"]}          # Propane/NG
                                0x0200: [True, "Fuel Pressure / Level Low"]}     # Gasoline / Diesel

        if not "diesel" in self.FuelType.lower():
            DealerInputs_Evo_LC[0x0200] = [False, "Fuel below 5 inch"]
            DealerInputs_Evo_LC[0x0020] = [False, ""]    # Ruptured Basin is not valid for non diesel systems

        # Nexus Liquid Cooled
        #   Position    Digital inputs      Digital Outputs
        #   1           Low Oil Pressure    air/Fuel Relay
        #   2           Not used            Bosch Enable
        #   3           Low Coolant Level   alarm Relay
        #   4           Low Fuel Pressure   Battery Charge Relay
        #   5           Wiring Error        Fuel Relay
        #   6           two Wire Start      Starter Relay
        #   7           auto Position       Cold Start Relay
        #   8           Manual Position     transfer Relay

        # Nexus Air Cooled
        #   Position    Digital Inputs      Digital Outputs
        #   1           Not Used            Not Used
        #   2           Low Oil Pressure    Not Used
        #   3           High Temperature    Not Used
        #   4           Not Used            Battery Charger Relay
        #   5           Wiring Error Detect Fuel
        #   6           Not Used            Starter
        #   7           Auto                Ignition
        #   8           Manual              Transfer

        # get the inputs registes
        Value = self.GetRegisterValueFromList("0052")
        if len(Value) != 4:
            return ""

        RegVal = int(Value, 16)

        if self.LiquidCooled:
            return self.GetDigitalValues(RegVal, DealerInputs_Evo_LC)
        else:
            return self.GetDigitalValues(RegVal, DealerInputs_Evo_AC)

    #------------ Evolution:GetDigitalOutputs ----------------------------------
    def GetDigitalOutputs(self):

        if not self.EvolutionController:
            return ""        # Nexus

        if not self.LiquidCooled:
            return ""

        # Dict format { bit position : [ Polarity, Label]}
        # Liquid cooled
        DigitalOutputs_LC = {   0x01: [True, "Transfer Switch Activated"],
                                0x02: [True, "Fuel Enrichment On"],
                                0x04: [True, "Starter On"],
                                0x08: [True, "Fuel Relay On"],
                                0x10: [True, "Battery Charger On"],
                                0x20: [True, "Alarm Active"],
                                0x40: [True, "Bosch Governor On"],
                                0x80: [True, "Air/Fuel Relay On"]}
        # Air cooled
        DigitalOutputs_AC = {   #0x10: [True, "Transfer Switch Activated"],  # Bit Position in Display 0x01
                                0x01: [True, "Ignition On"],                # Bit Position in Display 0x02
                                0x02: [True, "Starter On"],                 # Bit Position in Display 0x04
                                0x04: [True, "Fuel Relay On"],              # Bit Position in Display 0x08
                                #0x08: [True, "Battery Charger On"]         # Bit Position in Display 0x10
                                }

        Register = "0053"

        Value = self.GetRegisterValueFromList(Register)
        if len(Value) != 4:
            return ""
        RegVal = int(Value, 16)

        return self.GetDigitalValues(RegVal, DigitalOutputs_LC)

    #------------ Evolution:GetEngineState -------------------------------------
    def GetEngineState(self, Reg0001Value = None):

        if Reg0001Value is None:
            Value = self.GetRegisterValueFromList("0001")
            if len(Value) != 8:
                return ""
            RegVal = int(Value, 16)
        else:
            RegVal = Reg0001Value


        # other values that are possible:
        # Running in Warning
        # Running in Alarm
        # Running Remote Start
        # Running Two Wire Start
        # Stopped Alarm
        # Stopped Warning
        # Cranking
        # Cranking Warning
        # Cranking Alarm
        if self.BitIsEqual(RegVal,   0x000F0000, 0x00040000):
            return "Exercising"
        elif self.BitIsEqual(RegVal, 0x000F0000, 0x00090000):
            return "Stopped"
        # Note: this appears to define the state where the generator should start, it defines
        # the initiation of the start delay timer, This only appears in Nexus and Air Cooled Evo
        elif self.BitIsEqual(RegVal, 0x000F0000, 0x00010000):
                return "Startup Delay Timer Activated"
        elif self.BitIsEqual(RegVal, 0x000F0000, 0x00020000):
            if self.SystemInAlarm():
                return "Cranking in Alarm"
            else:
                return "Cranking"
        elif self.BitIsEqual(RegVal, 0x000F0000, 0x00050000):
            return "Cooling Down"
        elif self.BitIsEqual(RegVal, 0x000F0000, 0x00030000):
            if self.SystemInAlarm():
                return "Running in Alarm"
            else:
                return "Running"
        elif self.BitIsEqual(RegVal, 0x000F0000, 0x00080000):
            return "Stopped in Alarm"
        elif self.BitIsEqual(RegVal, 0x000F0000, 0x00060000):
            return "Running in Warning"
        elif self.BitIsEqual(RegVal, 0x000F0000, 0x00080000):
            return "Stopped in Alarm"
        elif self.BitIsEqual(RegVal, 0x000F0000, 0x00000000):
            return "Off - Ready"
        else:
            self.FeedbackPipe.SendFeedback("Unknown EngineState", Always = True, Message = "Reg 0001 = %08x" % RegVal, FullLogs = True)
            return "UNKNOWN: %08x" % RegVal

    #------------ Evolution:GetSwitchState -------------------------------------
    def GetSwitchState(self, Reg0001Value = None):

        if Reg0001Value is None:
            Value = self.GetRegisterValueFromList("0001")
            if len(Value) != 8:
                return ""
            RegVal = int(Value, 16)
        else:
            RegVal = Reg0001Value

        if self.BitIsEqual(RegVal, 0x0FFFF, 0x00):
            return "Auto"
        elif self.BitIsEqual(RegVal, 0x0FFFF, 0x07):
            return "Off"
        elif self.BitIsEqual(RegVal, 0x0FFFF, 0x06):
            return "Manual"
        elif self.BitIsEqual(RegVal, 0x0FFFF, 0x17):
            # This occurs momentarily when stopping via two wire method
            return "Two Wire Stop"
        else:
            return "System in Alarm"

    #------------ Evolution:GetDateTime ----------------------------------------
    def GetDateTime(self):

        #Generator Time Hi byte = hours, Lo byte = min
        Value = self.GetRegisterValueFromList("000e")
        if len(Value) != 4:
            return ""
        Hour = Value[:2]
        if int(Hour,16) > 23:
            return ""
        Minute = Value[2:]
        if int(Minute,16) >= 60:
            return ""
        # Hi byte = month, Lo byte = day of the month
        Value = self.GetRegisterValueFromList("000f")
        if len(Value) != 4:
            return ""
        Month = Value[:2]
        if int(Month,16) == 0 or int(Month,16) > 12:            # 1 - 12
            return ""
        DayOfMonth = Value[2:]
        if int(DayOfMonth,16) > 31 or int(DayOfMonth,16) == 0:  # 1 - 31
            return ""
        # Hi byte Day of Week 00=Sunday 01=Monday, Lo byte = last 2 digits of year
        Value = self.GetRegisterValueFromList("0010")
        if len(Value) != 4:
            return ""
        DayOfWeek = Value[:2]
        if int(DayOfWeek,16) > 7:
            return ""
        Year = Value[2:]
        if int(Year,16) < 16:
            return ""

        FullDate =self.DaysOfWeek.get(int(DayOfWeek,16),"INVALID") + " " + self.MonthsOfYear.get(int(Month,16),"INVALID")
        FullDate += " " + str(int(DayOfMonth,16)) + ", " + "20" + str(int(Year,16)) + " "
        FullDate += "%02d:%02d" %  (int(Hour,16), int(Minute,16))

        return FullDate

    #------------ Evolution:GetExerciseDuration --------------------------------
    def GetExerciseDuration(self):

        if not self.EvolutionController:
            return ""                       # Not supported on Nexus
        if not self.LiquidCooled:
            return ""                       # Not supported on Air Cooled
        # get exercise duration
        return self.GetParameter("023e", Label = "min")

    #------------ Evolution:GetParsedExerciseTime --------------------------------------------
    # Expcected output is # Wednesday!14!00!On!Weekly!False
    def GetParsedExerciseTime(self, DictOut = False):

        retstr = self.GetExerciseTime()
        if not len(retstr):
            return ""
        # GetExerciseTime should return this format:
        # "Weekly Saturday 13:30 Quiet Mode On"
        # "Biweekly Saturday 13:30 Quiet Mode On"
        # "Monthly Day-1 13:30 Quiet Mode On"
        Items = retstr.split(" ")
        HoursMin = Items[2].split(":")

        if self.bEnhancedExerciseFrequency:
            ModeStr = "True"
        else:
            ModeStr = "False"

        if "monthly" in retstr.lower():
            Items[1] = ''.join(x for x in Items[1] if x.isdigit())
            Day = int(Items[1])
            Items[1] = "%02d" % Day

        if DictOut:
            ExerciseInfo = collections.OrderedDict()
            ExerciseInfo["Enabled"] = True
            ExerciseInfo["Frequency"] = Items[0]
            ExerciseInfo["Hour"] = HoursMin[0]
            ExerciseInfo["Minute"] = HoursMin[1]
            ExerciseInfo["QuietMode"] = Items[5]
            ExerciseInfo["EnhancedExerciseMode"] = ModeStr
            ExerciseInfo["Day"] = Items[1]
            return ExerciseInfo
        else:
            retstr = Items[1] + "!" + HoursMin[0] + "!" + HoursMin[1] + "!" + Items[5] + "!" + Items[0] + "!" + ModeStr
            return retstr

    #------------ Evolution:GetExerciseTime ------------------------------------
    def GetExerciseTime(self):

        ExerciseFreq = ""   # Weekly
        FreqVal = 0
        DayOfMonth = 0

        if self.bEnhancedExerciseFrequency:
            # get frequency:  00 = weekly, 01= biweekly, 02=monthly
            Value = self.GetRegisterValueFromList("002d")
            if len(Value) != 4:
                return ""

            FreqValStr = Value[2:]
            FreqVal = int(FreqValStr,16)
            if FreqVal > 2:
                return ""

        # get exercise time of day
        Value = self.GetRegisterValueFromList("0005")
        if len(Value) != 4:
            return ""
        Hour = Value[:2]
        if int(Hour,16) > 23:
            return ""
        Minute = Value[2:]
        if int(Minute,16) >= 60:
            return ""

        # Get exercise day of week
        Value = self.GetRegisterValueFromList("0006")
        if len(Value) != 4:
            return ""

        if FreqVal == 0 or FreqVal == 1:        # weekly or biweekly

            DayOfWeek = Value[:2]       # Mon = 1
            if int(DayOfWeek,16) > 7:
                return ""
        elif FreqVal == 2:                      # Monthly
            # Get exercise day of month
            AltValue = self.GetRegisterValueFromList("002e")
            if len(AltValue) != 4:
                return ""
            DayOfMonth = AltValue[2:]
            if int(DayOfMonth,16) > 28:
                return ""

        Type = Value[2:]    # Quiet Mode 00=no 01=yes

        ExerciseTime = ""
        if FreqVal == 0:
            ExerciseTime += "Weekly "
        elif FreqVal == 1:
            ExerciseTime += "Biweekly "
        elif FreqVal == 2:
            ExerciseTime += "Monthly "

        if FreqVal == 0 or FreqVal == 1:
            ExerciseTime +=  self.DaysOfWeek.get(int(DayOfWeek,16),"") + " "
        elif FreqVal == 2:
            ExerciseTime +=  ("Day-%d" % (int(DayOfMonth,16))) + " "

        ExerciseTime += "%02d:%02d" %  (int(Hour,16), int(Minute,16))

        if Type == "00":
            ExerciseTime += " Quiet Mode Off"
        elif Type == "01":
            ExerciseTime += " Quiet Mode On"
        else:
            ExerciseTime += " Quiet Mode Unknown"

        return ExerciseTime

    #------------ Evolution:GetUnknownSensor1-----------------------------------
    def GetUnknownSensor(self, Register, RequiresRunning = False, Hex = False):

        if not len(Register):
            return ""

        if RequiresRunning:
            EngineState = self.GetEngineState()
            # report null if engine is not running
            if "Stopped" in EngineState or "Off" in EngineState or not len(EngineState):
                return "0"

        # get value
        return self.GetParameter(Register, Hex = Hex)

    #------------ Evolution:GetRPM ---------------------------------------------
    def GetRPM(self, ReturnInt = True):

        # get RPM
        return self.GetParameter("0007", ReturnInt = ReturnInt)

    #------------ Evolution:ReturnFormat ---------------------------------------
    def ReturnFormat(sefl, value, units, ReturnFloat):

        if ReturnFloat:
            return round(float(value), 2)
        else:
            return ("%.2f " + units) % float(value)

    #------------ Evolution:CheckExternalCTData --------------------------------
    def CheckExternalCTData(self, request = 'current', ReturnFloat = False):
        try:
            if not self.UseExternalCTData:
                return None
            ExternalData = self.GetExternalCTData()

            if ExternalData == None:
                return None

            # This assumes the following format:
            # NOTE: all fields are optional
            # { "strict" : True or False (true requires and outage to use the data)
            #   "current" : float value in amps
            #   "power"   : float value in kW
            #   "powerfactor" : float value (default is 1.0) used if converting from current to power or power to current
            # }
            if 'strict' in ExternalData:
                strict = ExternalData['strict']
            else:
                strict = False

            if strict:
                if self.EvolutionController and self.LiquidCooled:
                    if(self.GetTransferStatus().lower() != 'generator'):
                        return None
                if not self.SystemInOutage:
                    return None

            if request.lower() == 'current' and 'current' in ExternalData:
                return self.ReturnFormat(ExternalData['current'],"A", ReturnFloat)

            if request.lower() == 'power' and 'power' in ExternalData:
                return self.ReturnFormat(ExternalData['power'],"kW", ReturnFloat)

            # if we get here we must convert the data.
            VoltageFloat = float(self.GetVoltageOutput(ReturnInt = True))
            if 'powerfactor' in ExternalData:
                powerfactor = ExternalData['powerfactor']
            else:
                powerfactor = 1.0

            if request.lower() == 'current' and 'power' in ExternalData:
                if VoltageFloat == 0:
                    return self.ReturnFormat(0.0,"A", ReturnFloat)
                PowerFloat = float(ExternalData['power']) * 1000.0
                # I(A) = P(W) / (PF x V(V))
                CurrentFloat = round(PowerFloat / (powerfactor * VoltageFloat), 2)
                return self.ReturnFormat(CurrentFloat,"A", ReturnFloat)
            if request.lower() == 'power' and 'current' in ExternalData:
                CurrentFloat = float(ExternalData['current'])
                # P(W) = PF x I(A) x V(V)
                PowerFloat = (powerfactor * CurrentFloat * VoltageFloat) / 1000
                return self.ReturnFormat(PowerFloat,"kW", ReturnFloat)
            return None
        except Exception as e1:
            self.LogErrorLine("Error in CheckExternalCTData: " + str(e1))
            return None
    #------------ Evolution:GetCurrentOutput -----------------------------------
    def GetCurrentOutput(self, ReturnFloat = False):

        CurrentOutput = 0.0
        Divisor = 1.0
        CurrentOffset = 0.0
        CurrentFloat = 0.0
        DebugInfo = ""

        if ReturnFloat:
            DefaultReturn = 0.0
        else:
            DefaultReturn = "0.00 A"
        try:
            if not self.PowerMeterIsSupported():
                return DefaultReturn

            EngineState = self.GetEngineState()
            # report null if engine is not running
            if "Stopped" in EngineState or "Off" in EngineState or not len(EngineState):
                return DefaultReturn

            ReturnValue = self.CheckExternalCTData(request = 'current', ReturnFloat = ReturnFloat)
            if ReturnValue !=  None:
                return ReturnValue

            if self.EvolutionController and self.LiquidCooled:
                Value = self.GetRegisterValueFromList("0058")   # Hall Effect Sensor
                DebugInfo += Value
                if len(Value):
                    CurrentFloat = int(Value,16)
                else:
                    CurrentFloat = 0.0

                if self.CurrentDivider == None or self.CurrentDivider <= 0:
                    Divisor = .72       #0.425    #30.0/67.0  #http://www.webmath.com/equline1.html
                else:
                    Divisor = self.CurrentDivider

                if self.CurrentOffset == None:
                    CurrentOffset = -211.42     #-323.31     #-1939.0/6.0
                else:
                    CurrentOffset = self.CurrentOffset

                CurrentOutput = round(((CurrentFloat  / Divisor) +  CurrentOffset), 2)
                CurrentOutput = abs(CurrentOutput)

            elif self.EvolutionController and not self.LiquidCooled:
                if not self.LegacyPower:
                    Value = self.GetRegisterValueFromList("05f4")
                    Value2 = self.GetRegisterValueFromList("05f5")
                    DebugInfo += Value
                    if len(Value) and len(Value2):
                        CurrentFloat = int(Value,16) + int(Value2,16)
                    else:
                        CurrentFloat = 0.0
                else:
                    Value = self.GetRegisterValueFromList("003a")
                    DebugInfo += Value
                    if len(Value):
                        CurrentFloat = int(Value,16)
                    else:
                        CurrentFloat = 0.0

                CurrentFloat = self.signed32(CurrentFloat)
                CurrentFloat = abs(CurrentFloat)

                # Dict is formated this way:  ModelID: [ divisor, offset to register]
                ModelLookUp_EvoAC = { #ID : [KW or KVA Rating, Hz Rating, Voltage Rating, Phase]
                                        1 : None,      #["9KW", "60", "120/240", "1"],
                                        2 : None,      #["14KW", "60", "120/240", "1"],
                                        3 : None,      #["17KW", "60", "120/240", "1"],
                                        4 : None,      #["20KW", "60", "120/240", "1"],
                                        5 : None,      #["8KW", "60", "120/240", "1"],
                                        7 : None,      #["13KW", "60", "120/240", "1"],
                                        8 : None,      #["15KW", "60", "120/240", "1"],
                                        9 : None,      #["16KW", "60", "120/240", "1"],
                                        10 : None,      #["20KW", "VSCF", "120/240", "1"],      #Variable Speed Constant Frequency
                                        11 : None,      #["15KW", "ECOVSCF", "120/240", "1"],   # Eco Variable Speed Constant Frequency
                                        12 : None,      #["8KVA", "50", "220,230,240", "1"],    # 3 distinct models 220, 230, 240
                                        13 : None,      #["10KVA", "50", "220,230,240", "1"],   # 3 distinct models 220, 230, 240
                                        14 : None,      #["13KVA", "50", "220,230,240", "1"],   # 3 distinct models 220, 230, 240
                                        15 : 56.24,     #["11KW", "60" ,"240", "1"],
                                        17 : 21.48,     #["22KW", "60", "120/240", "1"],
                                        21 : None,      #["11KW", "60", "240 LS", "1"],
                                        22 : None,      # Power Pact
                                        32 : None,      #["Trinity", "60", "208 3Phase", "3"],  # G007077
                                        33 : None       #["Trinity", "50", "380,400,416", "3"]  # 3 distinct models 380, 400 or 416
                                        }


                # Get Model ID
                Value = self.GetRegisterValueFromList("0019")
                if not len(Value):
                    Value = "0"

                LookUpReturn = ModelLookUp_EvoAC.get(int(Value,16), None)


                if self.CurrentDivider == None or self.CurrentDivider <= 0:
                    if LookUpReturn == None:
                        if not self.LegacyPower:
                            Divisor = 20.0       # Default Divisor This is 20 because CT1 + CT2 / 2 is average / 10 again because the CT is divide by 10
                        else:
                            Divisor = (22.0 / float(self.NominalKW)) * 22       # Default Divisor
                    else:
                        Divisor = LookUpReturn
                else:
                    Divisor = self.CurrentDivider

                if not self.CurrentOffset == None:
                    CurrentOffset = self.CurrentOffset

                CurrentOutput = round((CurrentFloat + CurrentOffset) / Divisor, 2)

            else:
                CurrentOutput = 0.0
            # is the current out of bounds?
            # NOTE: This occurs if the EvoAC current transformers are not properly calibrated, or so we think.
            BaseStatus = self.GetBaseStatus()
            Voltage = self.GetVoltageOutput(ReturnInt = True)
            if Voltage > 100:     # only bounds check if the voltage is over 100V to give things a chance to stabalize
                if CurrentOutput > ((float(self.NominalKW) * 1000) / self.NominalLineVolts) + 2 or CurrentOutput < 0:
                    # if we are here, then the current is out of range.
                    if not self.EvolutionController  and not self.LiquidCooled and not BaseStatus == "EXERCISING":
                        msg = "Current Calculation: %f, CurrentFloat: %f, Divisor: %f, Offset %f, Debug: %s" % (CurrentOutput, CurrentFloat, Divisor, CurrentOffset, DebugInfo)
                        self.FeedbackPipe.SendFeedback("Current Calculation out of range", Message=msg, FullLogs = True )
                    if CurrentOutput < 0:
                        CurrentOutput = 0
                    else:
                        CurrentOutput = round((float(self.NominalKW) * 1000) / self.NominalLineVolts, 2)
            if ReturnFloat:
                return round(CurrentOutput, 2)

            return "%.2f A" % CurrentOutput
        except Exception as e1:
            self.LogErrorLine("Error in GetCurrentOutput: " + str(e1))
            return DefaultReturn

     ##------------ Evolution:GetActiveRotorPoles ------------------------------
    def GetActiveRotorPoles(self, ReturnInt = True):
        # (2 * 60 * Freq) / RPM = Num Rotor Poles

        if ReturnInt:
            DefaultReturn = 0
        else:
            DefaultReturn = "0"

        try:
            FreqFloat = self.GetFrequency(ReturnFloat = True)
            RPMInt = self.GetRPM(ReturnInt = True)
            RotorPoles = DefaultReturn

            if RPMInt:
                NumRotorPoles = int(round((2 * 60 * FreqFloat) / RPMInt))
                if NumRotorPoles > 4:
                    NumRotorPoles = 0
                if ReturnInt:
                    RotorPoles = NumRotorPoles
                else:
                    RotorPoles = str(NumRotorPoles)

            return RotorPoles
        except Exception as e1:
            self.LogErrorLine("Error in GetActiveRotorPoles: " + str(e1))
            return DefaultReturn

    #------------ Evolution:GetFuelSensor --------------------------------------
    def GetFuelSensor(self, ReturnInt = False):

        if not self.FuelSensorSupported():
            return None
        return self.GetParameter("005d", Label = "%", ReturnInt = ReturnInt)

    #------------ Evolution:GetPowerOutput -------------------------------------
    def GetPowerOutput(self, ReturnFloat = False):

        if ReturnFloat:
            DefaultReturn = 0.0
        else:
            DefaultReturn = "0 kW"

        if not self.PowerMeterIsSupported():
            return DefaultReturn

        EngineState = self.GetEngineState()
        # report null if engine is not running
        if  not len(EngineState) or "stopped" in EngineState.lower() or "off" in EngineState.lower():
            return DefaultReturn

        Current = self.GetCurrentOutput(ReturnFloat = True)
        Voltage = self.GetVoltageOutput(ReturnInt = True)

        PowerOut = 0.0

        if not Current == 0:
            PowerOut = Voltage * Current

        if ReturnFloat:
            return round((PowerOut / 1000.0), 3)
        return "%.2f kW" % (PowerOut / 1000.0)


    #------------ Evolution:GetFrequency ---------------------------------------
    def GetFrequency(self, Calculate = False, ReturnFloat = False):

        # get Frequency
        FloatTemp = 0.0
        try:

            if not Calculate:
                if self.EvolutionController and self.LiquidCooled:
                    return self.GetParameter("0008", ReturnFloat = ReturnFloat, Divider = 10.0, Label = "Hz")

                elif not self.EvolutionController and self.LiquidCooled:
                    # Nexus Liquid Cooled
                    FloatTemp = self.GetParameter("0008", ReturnFloat = True, Divider = 1.0, Label = "Hz")
                    # TODO this should be optiona
                    if self.NexusLegacyFreq:
                        FloatTemp = FloatTemp * 2.0
                    if ReturnFloat:
                        return FloatTemp

                    return "%2.1f Hz" % FloatTemp
                else:
                    # Nexus and Evolution Air Cooled
                    return self.GetParameter("0008", ReturnFloat = ReturnFloat, Divider = 1.0, Label = "Hz")

            else:
                # (RPM * Poles) / 2 * 60
                RPM = self.GetRPM(ReturnInt = True)
                Poles = self.GetActiveRotorPoles(ReturnInt = True)
                FloatTemp = (RPM * Poles) / (2*60)
        except Exception as e1:
            self.LogErrorLine("Error in GetFrequency: " + str(e1))
        if ReturnFloat:
            return FloatTemp

        FreqValue = "%2.1f Hz" % FloatTemp
        return FreqValue

    #------------ Evolution:GetVoltageOutput -----------------------------------
    def GetVoltageOutput(self, ReturnInt = False):

        # get Output Voltage
        return self.GetParameter("0012", ReturnInt = ReturnInt, Label = "V")

    #------------ Evolution:GetPickUpVoltage -----------------------------------
    def GetPickUpVoltage(self, ReturnInt = False):

         # get Utility Voltage Pickup Voltage
        if (self.EvolutionController and self.LiquidCooled) or (self.EvolutionController and self.Evolution2):
            return self.GetParameter("023b", ReturnInt = ReturnInt, Label = "V")

        PickupVoltage = DEFAULT_PICKUP_VOLTAGE

        if ReturnInt:
            return PickupVoltage
        return "%dV" % PickupVoltage

    #------------ Evolution:GetThresholdVoltage --------------------------------
    def GetThresholdVoltage(self, ReturnInt = False):

        # get Utility Voltage Threshold
        return self.GetParameter("0011", ReturnInt = ReturnInt, Label = "V")

    #------------ Evolution:GetSetOutputVoltage --------------------------------
    def GetSetOutputVoltage(self, ReturnInt = False):

        # get set output voltage
        if not self.EvolutionController or not self.LiquidCooled:
            if ReturnInt:
                return 0
            else:
                return ""

        return self.GetParameter("0237", Label = "V", ReturnInt = ReturnInt)

    #------------ Evolution:GetStartupDelay ------------------------------------
    def GetStartupDelay(self):

        # get Startup Delay
        if self.EvolutionController and not self.LiquidCooled:
            return self.GetParameter("002b", Label = "s")
        elif self.EvolutionController and self.LiquidCooled:
            return self.GetParameter("0239", Label = "s")
        else:
            return ""

    #------------ Evolution:GetUtilityVoltage ----------------------------------
    def GetUtilityVoltage(self, ReturnInt = False):

        return self.GetParameter("0009", ReturnInt = ReturnInt, Label = "V")

    #------------ Evolution:GetBatteryVoltage -------------------------
    def GetBatteryVoltage(self, ReturnFloat = False):

        # get Battery Charging Voltage
        return self.GetParameter("000a", Label = "V", ReturnFloat = ReturnFloat, Divider = 10.0)

    #------------ Evolution:GetBatteryStatusAlternate --------------------------
    def GetBatteryStatusAlternate(self):

        if not self.EvolutionController:
            return "Not Available"     # Nexus

        EngineState = self.GetEngineState()
        if  not len(EngineState):
            return "Not Charging"
        if not "Stopped" in EngineState and not "Off" in EngineState:
            return "Not Charging"

        Value = self.GetParameter("05ee", Divider = 100.0, ReturnFloat = True)
        if self.LiquidCooled:
            CompValue = 0.9
        else:
            CompValue = 0
        if Value > CompValue:
            return "Charging"
        else:
            return "Not Charging"


    #------------ Evolution:GetBatteryStatus -----------------------------------
    # The charger operates at one of three battery charging voltage
    # levels depending on ambient temperature.
    #  - 13.5VDC at High Temperature
    #  - 14.1VDC at Normal Temperature
    #  - 14.6VDC at Low Temperature
    # The battery charger is powered from a 120 VAC Load connection
    # through a fuse (F3) in the transfer switch. This 120 VAC source
    # must be connected to the Generator in order to operate the
    # charger.
    # During a Utility failure, the charger will momentarily be turned
    # off until the Generator is connected to the Load. During normal
    # operation, the battery charger supplies all the power to the
    # controller; the Generator battery is not used to supply power.
    # The battery charger will begin its charge cycle when battery
    # voltage drops below approximately 12.6V. The charger provides
    # current directly to the battery dependant on temperature, and the
    # battery is charged at the appropriate voltage level for 18 hours.
    # At the end of the 18 hour charge period battery charge current
    # is measured when the Generator is off. If battery charge current
    # at the end of the 18 hour charge time is greater than a pre-set
    # level, or the battery open-circuit voltage is less than approximately
    # 12.5V, an Inspect Battery warning is raised. If the engine cranks
    # during the 18 hour charge period, then the 18 hour charge timer
    # is restarted.
    # At the end of the 18 hour charge period the charger does one of
    # two things. If the temperature is less than approximately 40F
    # the battery is continuously charged at a voltage of 14.1V (i.e. the
    # charge voltage is changed from 14.6V to 14.1V after 18 hours). If
    # the temperature is above approximately 40F then the charger will
    # stop charging the battery after 18 hours.
    # The battery has a similar role as that found in an automobile
    # application. It sits doing nothing until it either self-discharges below
    # 12.6V or an engine crank occurs (i.e. such as occurs during the
    # weekly exercise cycle). If either condition occurs the battery charge
    # will begin its 18 hour charge cycle.
    def GetBatteryStatus(self):

        if not self.EvolutionController or not self.LiquidCooled:
            return "Not Available"     # Nexus or EvoAC not supported

        # get Battery Charging Voltage
        return self.GetParameterBit("0053", 0x10, OnLabel = "Charging", OffLabel = "Not Charging")

    #------------ Evolution:GetOneLineStatus -----------------------------------
    def GetOneLineStatus(self):

        return  self.GetSwitchState() + ", " + self.GetEngineState()

    #------------ Evolution:GetBaseStatus --------------------------------------
    def GetBaseStatus(self):

        if self.SystemInAlarm():
            return "ALARM"

        if self.ServiceIsDue():
            return "SERVICEDUE"

        EngineValue = self.GetEngineState()
        SwitchValue = self.GetSwitchState()
        if "exercising" in EngineValue.lower():
            return "EXERCISING"
        elif "running" in EngineValue.lower():
            if "auto" in SwitchValue.lower():
                return "RUNNING"
            else:
                return "RUNNING-MANUAL"
        else:
            if "off" in SwitchValue.lower():
                return "OFF"
            elif "manual" in SwitchValue.lower():
                return "MANUAL"
            else:
                return "READY"

    #------------ Evolution:ServiceIsDue ---------------------------------------
    def ServiceIsDue(self):

        # get Hours until next service
        Value = self.GetRegisterValueFromList("0001")
        if len(Value) != 8:
            return False

        HexValue = int(Value,16)

        # service due alarm?
        if self.BitIsEqual(HexValue,   0xFFF0FFFF, 0x0000001F):
            return True

        # get Hours until next service
        if self.EvolutionController:
            ServiceList = ["A","B"]
            for Service in ServiceList:
                Value = self.GetServiceDue(Service, NoUnits = True)
                if not len(Value):
                    continue

                if (int(Value) <= 1):
                    return True

        if not self.EvolutionController:

            ServiceList = ["OIL","AIR","SPARK","BATTERY","OTHER"]

            for Service in ServiceList:
                Value = self.GetServiceDue(Service, NoUnits = True)
                if not len(Value):
                    continue

                if (int(Value) <= 1):
                    return True

        return False

    #------------ Evolution:GetServiceDue --------------------------------------
    def GetServiceDue(self, serviceType = "A", NoUnits = False):

        ServiceTypeLookup_Evo = {
                                "A" : "001a",
                                "B" : "001e"
                                }
        ServiceTypeLookup_Nexus_AC = {
                                "SPARK" : "001a",
                                "OIL" : "001e",
                                "AIR" : "001c",
                                "BATTERY" : "001f",
                                "OTHER" : "0021"        # Do not know the corrposonding Due Date Register for this one
                                }
        ServiceTypeLookup_Nexus_LC = {
                                "OIL" : "001a",
                                "SPARK" : "001e",
                                "AIR" : "001c"
                                }
        if self.EvolutionController:
            LookUp = ServiceTypeLookup_Evo
        elif not self.LiquidCooled:
            LookUp = ServiceTypeLookup_Nexus_AC
        else:
            LookUp = ServiceTypeLookup_Nexus_LC

        Register = LookUp.get(serviceType.upper(), "")

        if not len(Register):
            return ""

        # get Hours until next service
        Value = self.GetRegisterValueFromList(Register)
        if len(Value) != 4:
            return ""

        if NoUnits:
            ServiceValue = "%d" % int(Value,16)
        else:
            ServiceValue = "%d hrs" % int(Value,16)

        return ServiceValue

    #------------ Evolution:GetServiceDueDate ----------------------------------
    def GetServiceDueDate(self, serviceType = "A"):

        if self.EvolutionController == None or self.LiquidCooled == None:
            return ""
        if self.PowerPact:
            return ""
        # Evolution Air Cooled Maintenance Message Intervals
        #Inspect Battery"  1 Year
        #Schedule A       200 Hours or 2 years
        #Schedule B       400 Hours
        # Evolution Liquid Cooled Maintenance Message Intervals
        #Inspect Battery"  1000 Hours
        #Schedule A       125 Hours or 1 years
        #Schedule B       250 Hours or 2 years
        #Schedule C       1000 Hours
        ServiceTypeLookup_Evo = {
                                "A" : "001b",
                                "B" : "001f",
                                }

        ServiceTypeLookup_EvoAC = {
                                "A" : "001b",
                                "B" : "001f",
                                "BATTERY" : "0022"
                                }
        # Nexus Air Cooled Maintenance Message Intervals
        # Inspect Battery     1 Year
        #Change Oil & Filter  200 Hours or 2 years
        #Inspect Air Filter   200 Hours or 2 years
        #Change Air Filter    200 Hours or 2 years
        #Inspect Spark Plugs  200 Hours or 2 years
        #Change spark Plugs   400 Hours or 10 years
        ServiceTypeLookup_Nexus_AC = {
                                "SPARK" : "001b",
                                "OIL" : "0020",
                                "BATTERY" : "001d",
                                "AIR": "0022"
                                }
        # Nexus Liquid Cooled Maintenance Message Intervals
        #Change oil & filter alert                  3mo/30hrs break-in 1yr/100hrs
        #inspect/clean air inlet & exhaust alert    3mo/30hrs break-in 6mo/50hrs
        #Change / inspect air filter alert          1yr/100hr
        #inspect spark plugs alert                  1yr/100hrs
        #Change / inspect spark plugs alert         2yr/250hr
        #inspect accessory drive alert              3mo/30hrs break-in 1yr/100hrs
        #Coolant change & flush                     1yr/100hrs
        #inspect battery alert                      1yr/100hrs
        ServiceTypeLookup_Nexus_LC = {
                                "OIL" : "001b",
                                "SPARK" : "001f",
                                "AIR" : "001d",
                                }
        if self.EvolutionController:
            if self.LiquidCooled:
                LookUp = ServiceTypeLookup_Evo
            else:
                LookUp = ServiceTypeLookup_EvoAC
        elif not self.LiquidCooled:
            LookUp = ServiceTypeLookup_Nexus_AC
        else:
            LookUp = ServiceTypeLookup_Nexus_LC

        Register = LookUp.get(serviceType.upper(), "")

        if not len(Register):
            return ""

        # get Hours until next service
        Value = self.GetRegisterValueFromList(Register)
        if len(Value) != 4:
            return ""

        try:
            time = int(Value,16) * 86400
            if not self.Evolution2:     # add one day
                time += 86400
            Date = datetime.datetime.fromtimestamp(time)
            return Date.strftime('%m/%d/%Y ')
        except Exception as e1:
            self.LogErrorLine("Error in GetServiceDueDate: " + str(e1))
            return ""

    #----------  Controller:GetHardwareVersion  ---------------------------------
    def GetHardwareVersion(self):

        try:
            Value = self.GetRegisterValueFromList("002a")
            if len(Value) != 4:
                return ""
            RegVal = int(Value, 16)

            IntTemp = RegVal >> 8           # high byte is firmware version
            FloatTemp = IntTemp / 100.0
            return "V%2.2f" % FloatTemp     #
        except Exception as e1:
            self.LogErrorLine("Error in GetHardwareVersion: " + str(e1))
            return ""

    #----------  Controller:GetFirmwareVersion  ---------------------------------
    def GetFirmwareVersion(self):

        try:
            Value = self.GetRegisterValueFromList("002a")
            if len(Value) != 4:
                return ""
            RegVal = int(Value, 16)

            IntTemp = RegVal & 0xff         # low byte is firmware version
            FloatTemp = IntTemp / 100.0
            return "V%2.2f" % FloatTemp     #
        except Exception as e1:
            self.LogErrorLine("Error in GetFirmwareVersion: " + str(e1))
            return ""
    #----------  ControllerCheckForFirmwareUpdate  -----------------------------
    def CheckForFirmwareUpdate(self):

        try:
            if not self.Evolution2:
                return

            FWVersionString = self.GetFirmwareVersion()
            if not len(FWVersionString):
                return
            if self.SavedFirmwareVersion == None:
               self.SavedFirmwareVersion = FWVersionString
            else:
                if FWVersionString != self.SavedFirmwareVersion:
                    # FIRMWARE VERSION CHANGED
                    MessageType = "info"
                    msgsubject = "Generator Notice: Firmware update at " + self.SiteName
                    msgbody = "NOTE: This message is a notice that the version of the generator controller firmware has changed from %s to %s. \n" % (self.SavedFirmwareVersion,FWVersionString)
                    self.LogError("Frimware Changed from %s to %s" % (self.SavedFirmwareVersion,FWVersionString))
                    msgbody += self.DisplayStatus()
                    self.MessagePipe.SendMessage(msgsubject , msgbody, msgtype = MessageType)
                    self.SavedFirmwareVersion = FWVersionString
        except Exception as e1:
            self.LogErrorLine("Error in CheckForFirmwareUpdate : " + str(e1))

        return


    #------------ Evolution:GetRunHours ----------------------------------------
    def GetRunHours(self, ReturnFloat = False):

        try:
            RunHours = None
            if not self.EvolutionController or not self.LiquidCooled:
                # get total hours running
                RunHours =  self.GetParameter("000b", ReturnInt = True)
                if self.AdditionalRunHours != None:
                    RunHours = int(RunHours) + int(self.AdditionalRunHours)
            else:
                # Run minutes / 60
                RunHours = self.GetParameter("005e", Divider = 60.0)
                if not len(RunHours):
                    RunHours = "0.0"
                if self.AdditionalRunHours != None:
                    RunHours = float(RunHours) + float(self.AdditionalRunHours)
            if ReturnFloat:
                return float(RunHours)
            else:
                return str(RunHours)
        except Exception as e1:
            self.LogErrorLine("Error getting run hours: " + str(RunHours) + ":" + str(self.AdditionalRunHours) + ": "+ str(e1))
            if ReturnFloat:
                return 0.0
            else:
                return "0.0"
    #------------------- Evolution:DisplayOutage -------------------------------
    def DisplayOutage(self, DictOut = False, JSONNum = False):

        try:

            Outage = collections.OrderedDict()
            Outage["Outage"] = []

            if self.SystemInOutage:
                outstr = "System in outage since %s" % self.OutageStartTime.strftime("%Y-%m-%d %H:%M:%S")
            else:
                if self.ProgramStartTime != self.OutageStartTime:
                    OutageStr = str(self.LastOutageDuration).split(".")[0]  # remove microseconds from string
                    outstr = "Last outage occurred at %s and lasted %s." % (self.OutageStartTime.strftime("%Y-%m-%d %H:%M:%S"), OutageStr)
                else:
                    outstr = "No outage has occurred since program launched."

            Outage["Outage"].append({"Status" : outstr})
            Outage["Outage"].append({"System In Outage" : "Yes" if self.SystemInOutage else "No"})

             # get utility voltage
            Outage["Outage"].append({"Utility Voltage" : self.ValueOut(self.GetUtilityVoltage(ReturnInt = True), "V", JSONNum)})
            Outage["Outage"].append({"Utility Voltage Minimum" : self.ValueOut(self.UtilityVoltsMin, "V", JSONNum)})
            Outage["Outage"].append({"Utility Voltage Maximum" : self.ValueOut(self.UtilityVoltsMax, "V", JSONNum)})

            Outage["Outage"].append({"Utility Threshold Voltage" : self.ValueOut(self.GetThresholdVoltage(ReturnInt = True), "V", JSONNum)})

            if (self.EvolutionController and self.LiquidCooled) or (self.EvolutionController and self.Evolution2):
                Outage["Outage"].append({"Utility Pickup Voltage" : self.ValueOut(self.GetPickUpVoltage(ReturnInt = True), "V", JSONNum)})

            if self.EvolutionController:
                Outage["Outage"].append({"Startup Delay" : self.UnitsOut( self.GetStartupDelay(), type = int, NoString = JSONNum)})

            Outage["Outage"].append({"Outage Log" : self.DisplayOutageHistory()})

        except Exception as e1:
            self.LogErrorLine("Error in DisplayOutage: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(Outage,""))

        return Outage

    #------------ Evolution:DisplayStatus --------------------------------------
    def DisplayStatus(self, DictOut = False, JSONNum = False, Reg0001Value = None):
        # Store dicts in list to ensure that JSON will order them properly. The
        # JSON spec does not define order except for lists
        try:
            Status = collections.OrderedDict()
            Status["Status"] = []
            Engine = []
            Line = []
            Time = []

            Status["Status"].append({"Engine":Engine})
            Status["Status"].append({"Line":Line})
            with self.ExternalDataLock:
                try:
                    if self.ExternalTempData != None:
                        Status["Status"].append(self.ExternalTempData)
                except Exception as e1:
                    self.LogErrorLine("Error in DisplayStatus: " + str(e1))

            Status["Status"].append({"Last Log Entries":self.DisplayLogs(AllLogs = False, DictOut = True)})
            Status["Status"].append({"Time":Time})

            Engine.append({"Switch State" : self.GetSwitchState(Reg0001Value = Reg0001Value)})
            Engine.append({"Engine State" : self.GetEngineState(Reg0001Value = Reg0001Value)})
            if self.EvolutionController and self.LiquidCooled:
                Engine.append({"Active Relays" : self.GetDigitalOutputs()})
                Engine.append({"Active Sensors" : self.GetSensorInputs()})

            if self.SystemInAlarm():
                Engine.append({"System In Alarm" : self.GetAlarmState()})

            Engine.append({"Battery Voltage" : self.ValueOut(self.GetBatteryVoltage(ReturnFloat = True), "V", JSONNum)})
            if self.EvolutionController and self.LiquidCooled:
                Engine.append({"Battery Status" : self.GetBatteryStatus()})

            Engine.append({"RPM" : self.ValueOut(self.GetRPM(ReturnInt = True), "", JSONNum)})

            Engine.append({"Frequency" : self.ValueOut(self.GetFrequency(ReturnFloat = True), "Hz", JSONNum)})
            Engine.append({"Output Voltage" : self.ValueOut(self.GetVoltageOutput(ReturnInt = True), "V", JSONNum)})

            if self.PowerMeterIsSupported():
                Engine.append({"Output Current" : self.ValueOut(self.GetCurrentOutput(ReturnFloat = True), "A", JSONNum)})
                Engine.append({"Output Power (Single Phase)" : self.ValueOut(self.GetPowerOutput(ReturnFloat = True), "kW", JSONNum)})

            Engine.append({"Active Rotor Poles (Calculated)" : self.ValueOut(self.GetActiveRotorPoles(ReturnInt = True), "", JSONNum)})

            if self.bDisplayUnknownSensors:
                Engine.append({"Unsupported Sensors" : self.DisplayUnknownSensors()})

            if self.EvolutionController and self.LiquidCooled:
                Line.append({"Transfer Switch State" : self.GetTransferStatus()})

            Line.append({"Utility Voltage" : self.ValueOut(self.GetUtilityVoltage(ReturnInt = True), "V", JSONNum)})
            #
            Line.append({"Utility Max Voltage" : self.ValueOut(self.UtilityVoltsMax, "V", JSONNum)})
            Line.append({"Utility Min Voltage" : self.ValueOut(self.UtilityVoltsMin, "V", JSONNum)})
            Line.append({"Utility Threshold Voltage" : self.ValueOut(self.GetThresholdVoltage(ReturnInt = True), "V", JSONNum)})

            if self.EvolutionController and self.LiquidCooled:
                Line.append({"Utility Pickup Voltage" : self.ValueOut(self.GetPickUpVoltage(ReturnInt = True), "V", JSONNum)})
                Line.append({"Set Output Voltage" : self.ValueOut(self.GetSetOutputVoltage(ReturnInt = True), "V", JSONNum)})


            # Generator time
            Time.append({"Monitor Time" : datetime.datetime.now().strftime("%A %B %-d, %Y %H:%M:%S")})
            Time.append({"Generator Time" : self.GetDateTime()})



        except Exception as e1:
            self.LogErrorLine("Error in DisplayStatus: " + str(e1))
        if not DictOut:
            return self.printToString(self.ProcessDispatch(Status,""))

        return Status

    #------------ Monitor::GetStatusForGUI -------------------------------------
    def GetStatusForGUI(self):

        Status = {}

        try:
            Status["basestatus"] = self.GetBaseStatus()
            Status["switchstate"] = self.GetSwitchState()
            Status["enginestate"] = self.GetEngineState()
            Status["kwOutput"] = self.GetPowerOutput()
            Status["OutputVoltage"] = self.GetVoltageOutput()
            Status["BatteryVoltage"] = self.GetBatteryVoltage()
            Status["UtilityVoltage"] = self.GetUtilityVoltage()
            Status["Frequency"] = self.GetFrequency()
            Status["RPM"] = self.GetRPM()
            Status["ExerciseInfo"] = self.GetParsedExerciseTime(True)
            Status["tiles"] = []
            for Tile in self.TileList:
                Status["tiles"].append(Tile.GetGUIInfo())
        except Exception as e1:
            self.LogErrorLine("Error in GetStatusForGUI: " + str(e1))
        return Status

    #------------ Evolution:GetStartInfo ---------------------------------------
    def GetStartInfo(self, NoTile = False):

        StartInfo = {}
        try:
            EvoLC = self.EvolutionController and self.LiquidCooled
            if EvoLC is None:
                EvoLC = False
            StartInfo["fueltype"] = self.FuelType
            StartInfo["model"] = self.Model
            StartInfo["nominalKW"] = self.NominalKW
            StartInfo["nominalRPM"] = self.NominalRPM
            StartInfo["nominalfrequency"] = self.NominalFreq
            StartInfo["Controller"] = self.GetController(Actual = False)
            StartInfo["Actual"] = self.GetController(Actual = True)
            StartInfo["NominalBatteryVolts"] = "12"
            StartInfo["PowerGraph"] = self.PowerMeterIsSupported()
            StartInfo["FuelCalculation"] = self.FuelTankCalculationSupported()
            StartInfo["FuelSensor"] = self.FuelSensorSupported()
            StartInfo["FuelConsumption"] = self.FuelConsumptionSupported()
            StartInfo["UtilityVoltage"] = True
            StartInfo["RemoteCommands"] = not self.SmartSwitch  # Start and Stop
            StartInfo["ResetAlarms"] = EvoLC
            StartInfo["AckAlarms"] = False
            StartInfo["RemoteTransfer"] = not self.SmartSwitch      # Start / Transfer
            StartInfo["RemoteButtons"] = self.RemoteButtonsSupported()  # On, Off , Auto
            StartInfo["ExerciseControls"] = not self.SmartSwitch
            StartInfo["WriteQuietMode"] = EvoLC
            StartInfo["Firmware"] = self.GetFirmwareVersion()
            StartInfo["Hardware"] = self.GetHardwareVersion()

            if not NoTile:
                StartInfo["pages"] = {
                                "status":True,
                                "maint":True,
                                "outage":True,
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

    # ---------- Evolution:GetConfig--------------------------------------------
    def GetConfig(self):

        try:

            if self.config != None:
                # optional config parameters, by default the software will attempt to auto-detect the controller
                # this setting will override the auto detect
                if self.config.HasOption('evolutioncontroller'):
                    self.EvolutionController = self.config.ReadValue('evolutioncontroller', return_type = bool, default = False)
                if self.config.HasOption('liquidcooled'):
                    self.LiquidCooled = self.config.ReadValue('liquidcooled', return_type = bool, default = False)

                self.DisableOutageCheck = self.config.ReadValue('disableoutagecheck', return_type = bool, default = False)
                self.bUseLegacyWrite = self.config.ReadValue('uselegacysetexercise', return_type = bool, default = False)
                self.bEnhancedExerciseFrequency = self.config.ReadValue('enhancedexercise', return_type = bool, default = False)
                self.CurrentDivider = self.config.ReadValue('currentdivider', return_type = float, default = None, NoLog = True)
                self.CurrentOffset = self.config.ReadValue('currentoffset', return_type = float, default = None, NoLog = True)
                self.UseFuelSensor = self.config.ReadValue('usesensorforfuelgauge', return_type = bool, default = True)
                self.IgnoreUnknown = self.config.ReadValue('ignore_unknown', return_type = bool, default = False)
                self.LegacyPower = self.config.ReadValue('legacy_power', return_type = bool, default = False)
                self.NexusLegacyFreq = self.config.ReadValue('nexus_legacy_freq', return_type = bool, default = True)

                self.SerialNumberReplacement = self.config.ReadValue('serialnumberifmissing', default = None)
                if self.SerialNumberReplacement != None and len(self.SerialNumberReplacement):
                    if self.SerialNumberReplacement.isdigit() and len(self.SerialNumberReplacement) == 10:
                        self.LogError("Override Serial Number: " + "<" + self.SerialNumberReplacement + ">")
                    else:
                        self.LogError("Override Serial Number: bad format: " + "<" + self.SerialNumberReplacement + ">")
                        self.SerialNumberReplacement = None
                else:
                    self.SerialNumberReplacement = None

                self.AdditionalRunHours = self.config.ReadValue('additionalrunhours', return_type = float, default = 0.0, NoLog = True)
                self.UseNominalLineVoltsFromConfig = self.config.ReadValue('usenominallinevolts', return_type = bool, default = False)
                self.NominalLineVolts = self.config.ReadValue('nominallinevolts', return_type = int, default = 240)

        except Exception as e1:
            self.LogErrorLine("Missing config file or config file entries (evo/nexus): " + str(e1))
            return False

        return True
    #----------  Evolution::ComminicationsIsActive  ----------------------------
    # Called every few seconds
    def ComminicationsIsActive(self):

        if self.LastRxPacketCount == self.ModBus.RxPacketCount:
            return False
        else:
            self.LastRxPacketCount = self.ModBus.RxPacketCount
            return True

    #----------  Generator:RemoteButtonsSupported  -----------------------------
    # return true if Panel buttons are settable via the software
    def RemoteButtonsSupported(self):

        if self.EvolutionController and self.LiquidCooled:
            return True
        return False
    #----------  Generator:PowerMeterIsSupported  ------------------------------
    def PowerMeterIsSupported(self):

        if self.bDisablePowerLog:
            return False
        if self.UseExternalCTData:
            return True
        if not self.EvolutionController:    # Not supported by Nexus at this time
            return False

        if not len(self.NominalKW) or self.NominalKW.lower() == "unknown" or self.NominalKW == "0":
            return False
        return True
