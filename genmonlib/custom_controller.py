#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: custom_controller.py
# PURPOSE: Controller module for defining a custom generator controller
#
#  AUTHOR: Jason G Yates
#    DATE: 24-Jul-2021
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


class CustomController(GeneratorController):

    #---------------------CustomController::__init__----------------------------
    def __init__(self,
        log,
        newinstall = False,
        simulation = False,
        simulationfile = None,
        message = None,
        feedback = None,
        config = None):

        # call parent constructor
        super(CustomController, self).__init__(log, newinstall = newinstall, simulation = simulation, simulationfile = simulationfile, message = message, feedback = feedback, config = config)

        self.LastEngineState = ""
        self.CurrentAlarmState = False
        self.VoltageConfig = None
        self.AlarmAccessLock = threading.RLock()     # lock to synchronize access to the logs
        self.EventAccessLock = threading.RLock()     # lock to synchronize access to the logs
        self.ControllerDetected = False

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

        self.SetupClass()


    #-------------CustomController:SetupClass-----------------------------------
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
            #Starting device connection
            if self.Simulation:
                self.ModBus = ModbusFile(self.UpdateRegisterList,
                    inputfile = self.SimulationFile,
                    config = self.config)
            else:
                self.ModBus = ModbusProtocol(self.UpdateRegisterList,
                    config = self.config)


            self.ModBus.AlternateFileProtocol = self.AlternateFileProtocol
            self.Threads = self.MergeDicts(self.Threads, self.ModBus.Threads)
            self.LastRxPacketCount = self.ModBus.RxPacketCount

            self.StartCommonThreads()

        except Exception as e1:
            self.FatalError("Error opening modbus device: " + str(e1))
            return None

    #---------------------CustomController::GetConfig---------------------------
    # read conf file, used internally, not called by genmon
    # return True on success, else False
    def GetConfig(self):

        try:

            self.AlternateFileProtocol = self.config.ReadValue('alternatefileprotocol', return_type = bool, default = True)
            self.VoltageConfig = self.config.ReadValue('voltageconfiguration', default = "277/480")
            self.NominalBatteryVolts = int(self.config.ReadValue('nominalbattery', return_type = int, default = 24))
            self.FuelUnits = self.config.ReadValue('fuel_units', default = "gal")
            self.FuelHalfRate = self.config.ReadValue('half_rate', return_type = float, default = 0.0)
            self.FuelFullRate = self.config.ReadValue('full_rate', return_type = float, default = 0.0)
            self.UseFuelSensor = self.config.ReadValue('usesensorforfuelgauge', return_type = bool, default = True)
            self.UseCalculatedPower = self.config.ReadValue('usecalculatedpower', return_type = bool, default = False)

            self.ConfigImportFile = self.config.ReadValue('import_config_file', default = None)
            if self.ConfigImportFile == None:
                self.FatalError("Missing entry import_config_file. Unable to continue.")

            self.ConfigFileName = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "data",  "controller", self.ConfigImportFile)

            if not self.ReadImportConfig():
                self.FatalError("Unable to read import config: " + self.ConfigFileName)
                return False

        except Exception as e1:
            self.FatalError("Missing config file or config file entries (CustomController): " + str(e1))
            return False

        return True

    #-------------CustomController:ReadImportConfig-----------------------------
    def ReadImportConfig(self):

        if os.path.isfile(self.ConfigFileName):
            try:
                with open(self.ConfigFileName) as infile:
                    self.controllerimport = json.load(infile)
            except Exception as e1:
                self.LogErrorLine("Error in GetConfig reading config import file: " + str(e1))
                return False
        else:
            self.LogError("Error reading config import file: " + str(FullFileName))
            return False

        return True
    #-------------CustomController:IdentifyController---------------------------
    def IdentifyController(self):

        try:
            if self.ControllerDetected:
                return True

            #at this point we will parse the imported config from the JSON file
            # TODO
            if not "switch_state" in self.controllerimport:
                self.LogError("Error: Controller Import does not contain switch_state")
                return False
            if not "alarm_conditions" in self.controllerimport:
                self.LogError("Error: Controller Import does not contain alarm_conditions")
                return False
            if not "engine_state" in self.controllerimport:
                self.LogError("Error: Controller Import does not contain engine_state")
                return False
            if not "base_registers" in self.controllerimport:
                self.LogError("Error: Controller Import does not contain base_registers")
                return False
            if not "status" in self.controllerimport:
                self.LogError("Error: Controller Import does not contain status")
                return False
            if not "maintenance" in self.controllerimport:
                self.LogError("Error: Controller Import does not contain maintenance")
                return False
            if not "controller_name" in self.controllerimport:
                self.LogError("Error: Controller Import does not contain controller_name")
                return False

            if not "rated_max_output_power_kw" in self.controllerimport:
                self.LogError("Error: Controller Import does not contain rated_max_output_power_kw")
                return False
            if not "rated_nominal_voltage" in self.controllerimport:
                self.LogError("Error: Controller Import does not contain rated_nominal_voltage")
                return False
            if not "rated_nominal_freq" in self.controllerimport:
                self.LogError("Error: Controller Import does not contain rated_nominal_freq")
                return False
            if not "rated_nominal_rpm" in self.controllerimport:
                self.LogError("Error: Controller Import does not contain rated_nominal_rpm")
                return False
            if not "generator_phase" in self.controllerimport:
                self.LogError("Error: Controller Import does not contain generator_phase")
                return False
            if not "nominal_battery_voltage" in self.controllerimport:
                self.LogError("Error: Controller Import does not contain nominal_battery_voltage")
                return False

            self.NominalOutputVolts =  str(self.controllerimport["rated_nominal_voltage"])
            self.NominalBatteryVolts =  str(self.controllerimport["nominal_battery_voltage"])
            self.Model = str(self.controllerimport["controller_name"])
            self.NominalFreq = str(self.controllerimport["rated_nominal_freq"])
            self.NominalRPM = str(self.controllerimport["rated_nominal_rpm"])
            self.NominalKW = str(self.controllerimport["rated_max_output_power_kw"]) + " kW"
            self.Phase = str(self.controllerimport["generator_phase"])

            for Register, Length in self.controllerimport["base_registers"].items():
                if Length % 2 != 0:
                    self.LogError("Error: Controller Import: modbus register lenghts must be divisible by 2: " + str(Register) + ":" + str(Length))
                    return False

            self.ControllerDetected = True
            return True
        except Exception as e1:
            self.LogErrorLine("Error in IdentifyController: " + str(e1))
            return False
    #-------------CustomController:InitDevice-----------------------------------
    # One time reads, and read all registers once
    def InitDevice(self):

        try:
            self.IdentifyController()
            self.MasterEmulation()
            self.SetupTiles()
            self.InitComplete = True
            self.InitCompleteEvent.set()
        except Exception as e1:
            self.LogErrorLine("Error in InitDevice: " + str(e1))

    #-------------CustomController:SetupTiles-----------------------------------
    def SetupTiles(self):
        try:
            with self.ExternalDataLock:
                self.TileList = []

            sensor_list = self.controllerimport["gauges"]

            for sensor in sensor_list:

                title = sensor["title"]
                Tile = MyTile(self.log, title = sensor["title"],
                    type = sensor["sensor"], nominal = sensor["nominal"],
                    callback = self.GetGaugeValue, callbackparameters = (sensor["title"],))
                self.TileList.append(Tile)

            self.SetupCommonTiles()

        except Exception as e1:
            self.LogErrorLine("Error in SetupTiles: " + str(e1))

    #------------ CustomController:WaitAndPergeforTimeout ----------------------
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

    #-------------CustomController:MasterEmulation------------------------------
    def MasterEmulation(self):

        try:
            if not self.ControllerDetected:
                self.IdentifyController()
                if not self.ControllerDetected:
                    return
            for Register, Length in self.controllerimport["base_registers"].items():
                try:
                    if self.IsStopping:
                        return
                    localTimeoutCount = self.ModBus.ComTimoutError
                    localSyncError = self.ModBus.ComSyncError
                    self.ModBus.ProcessTransaction(Register, Length / 2)
                    if ((localSyncError != self.ModBus.ComSyncError or localTimeoutCount != self.ModBus.ComTimoutError)
                        and self.ModBus.RxPacketCount):
                        self.WaitAndPergeforTimeout()
                except Exception as e1:
                    self.LogErrorLine("Error in MasterEmulation: " + str(e1))

            self.CheckForAlarmEvent.set()
        except Exception as e1:
            self.LogErrorLine("Error in MasterEmulation: " + str(e1))

    #------------ CustomController:GetTransferStatus ---------------------------
    def GetTransferStatus(self):

        LineState = "Unknown"
        # TODO

        return LineState

    #------------ CustomController:CheckForAlarms ------------------------------
    def CheckForAlarms(self):

        try:
            status_included = False
            if not self.InitComplete:
                return
            # Check for changes in engine state
            EngineState = self.GetEngineState()
            EngineState += self.GetSwitchState()
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
                self.MessagePipe.SendMessage(msgsubject , msgbody, msgtype = MessageType)

            # Check for Alarms
            if self.SystemInAlarm():
                if not self.CurrentAlarmState:
                    msgsubject = "Generator Notice: ALARM Active at " + self.SiteName
                    if not status_included:
                        msgbody += self.DisplayStatus()
                    self.MessagePipe.SendMessage(msgsubject , msgbody, msgtype = "warn")
            else:
                if self.CurrentAlarmState:
                    msgsubject = "Generator Notice: ALARM Clear at " + self.SiteName
                    if not status_included:
                        msgbody += self.DisplayStatus()
                    self.MessagePipe.SendMessage(msgsubject , msgbody, msgtype = "warn")

            self.CurrentAlarmState = self.SystemInAlarm()

        except Exception as e1:
            self.LogErrorLine("Error in CheckForAlarms: " + str(e1))

        return


    #------------ CustomController:UpdateRegisterList --------------------------
    def UpdateRegisterList(self, Register, Value, IsString = False, IsFile = False):

        try:
            if len(Register) != 4:
                self.LogError("Validation Error: Invalid register value in UpdateRegisterList: %s %s" % (Register, Value))
                return False

            if not IsFile:
                #  validate data length
                length = len(Value) / 2
                reg_dict = self.controllerimport["base_registers"]
                if reg_dict[Register] != length:
                    self.LogError("Invalid length detected in received modbus regisger " + str(Register) + " : " + str(length ) + ": " + str(self.controllerimport["base_registers"]))
                    return False
                else:
                    self.Registers[Register] = Value
            else:
                # todo validate file data length
                self.FileData[Register] = Value
            return True
        except Exception as e1:
            self.LogErrorLine("Error in UpdateRegisterList: " + str(e1))
            return False

    #---------------------CustomController::SystemInAlarm-----------------------
    # return True if generator is in alarm, else False
    def SystemInAlarm(self):

        try:
            alarm_state = self.GetExtendedDisplayString(self.controllerimport, "alarm_active")
            if len(alarm_state) and not alarm_state == "Unknown" :
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in SystemInAlarm: " + str(e1))
            return False
    #------------ CustomController:GetSwitchState ------------------------------
    def GetSwitchState(self):

        try:
            return self.GetExtendedDisplayString(self.controllerimport, "switch_state")
        except Exception as e1:
            self.LogErrorLine("Error in GetSwitchState: " + str(e1))
            return "Unknown"

    #------------ CustomController:GetGeneratorStatus --------------------------
    def GetGeneratorStatus(self):

        try:
            generator_status = self.GetExtendedDisplayString(self.controllerimport, "generator_status")
            return generator_status
        except Exception as e1:
            self.LogErrorLine("Error in GetGeneratorStatus: " + str(e1))
            return "Unknown"

    #------------ CustomController:GetEngineState ------------------------------
    def GetEngineState(self):

        try:
            return self.GetExtendedDisplayString(self.controllerimport, "engine_state")

        except Exception as e1:
            self.LogErrorLine("Error in GetEngineState: " + str(e1))
            return "Unknown"

    #------------ CustomController:GetDateTime ----------------------------------------
    def GetDateTime(self):

        ErrorReturn = "Unknown"
        try:
            # TODO
            return ErrorReturn
        except Exception as e1:
            self.LogErrorLine("Error in GetDateTime: " + str(e1))
            return ErrorReturn

    #------------ CustomController::GetStartInfo --------------------------------------
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
            StartInfo["RemoteCommands"] = False      # Remote Start/ Stop/ StartTransfer
            StartInfo["ResetAlarms"] = False
            StartInfo["AckAlarms"] = False
            StartInfo["RemoteTransfer"] = False    # Remote start and transfer command
            StartInfo["RemoteButtons"] = False      # Remote controll of Off/Auto/Manual
            StartInfo["ExerciseControls"] = False  # self.SmartSwitch
            StartInfo["WriteQuietMode"] = False
            StartInfo["SetGenTime"] = False
            StartInfo["Linux"] = self.Platform.IsOSLinux()
            StartInfo["RaspbeerryPi"] = self.Platform.IsPlatformRaspberryPi()

            if not NoTile:
                StartInfo["pages"] = {
                                "status":True,
                                "maint":True,
                                "outage":False,
                                "logs":False,
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
    #------------ CustomController::GetStatusForGUI -----------------------------------
    # return dict for GUI
    def GetStatusForGUI(self):

        try:
            Status = {}

            Status["basestatus"] = self.GetBaseStatus()
            Status["switchstate"] = self.GetSwitchState()
            Status["enginestate"] = self.GetEngineState()
            Status["kwOutput"] = self.GetPowerOutput()
            # Exercise Info is a dict containing the following:
            # Not supported
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

    #---------------------CustomController::DisplayLogs-------------------------
    def DisplayLogs(self, AllLogs = False, DictOut = False, RawOutput = False):

        RetValue = collections.OrderedDict()
        LogList = []
        RetValue["Logs"] = LogList
        UnknownFound = False

        # Not supported

        return RetValue

    #------------ CustomController::DisplayMaintenance -------------------------
    def DisplayMaintenance (self, DictOut = False, JSONNum = False):

        try:
            # use ordered dict to maintain order of output
            # ordered dict to handle evo vs nexus functions
            Maintenance = collections.OrderedDict()
            Maintenance["Maintenance"] = []

            Maintenance["Maintenance"].append({"Model" : self.Model})
            Maintenance["Maintenance"].append({"Controller Detected" : self.GetController()})
            Maintenance["Maintenance"].append({"Nominal RPM" : self.NominalRPM})
            Maintenance["Maintenance"].append({"Rated kW" : self.NominalKW})
            Maintenance["Maintenance"].append({"Nominal Frequency" : self.NominalFreq})
            Maintenance["Maintenance"].append({"Fuel Type" : self.FuelType})

            Maintenance["Maintenance"].extend( self.GetDisplayList(self.controllerimport, "maintenance"))
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

            if self.FuelLevelOK != None:
                if self.FuelLevelOK:
                    level = "OK"
                else:
                    level = "Low"
                Maintenance["Maintenance"].append({"Fuel Level State" : level})


        except Exception as e1:
            self.LogErrorLine("Error in DisplayMaintenance: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(Maintenance,""))

        return Maintenance

    #------------ CustomController::DisplayStatus ------------------------------
    def DisplayStatus(self, DictOut = False, JSONNum = False):

        try:


            Status = collections.OrderedDict()
            Status["Status"] = []

            gen_status = self.GetSwitchState()
            if gen_status != "Unknown":
                Status["Status"].append({"Engine State" : gen_status})

            gen_status = self.GetEngineState()
            if gen_status != "Unknown":
                Status["Status"].append({"Engine State" : gen_status})

            gen_status = self.GetGeneratorStatus()
            if gen_status != "Unknown":
                Status["Status"].append({"Generator Status" : gen_status})

            Status["Status"].extend(self.GetDisplayList(self.controllerimport, "status"))

            with self.ExternalDataLock:
                try:
                    if self.ExternalTempData != None:
                        Status["Status"].append(self.ExternalTempData)
                except Exception as e1:
                    self.LogErrorLine("Error in DisplayStatus: " + str(e1))

            if self.SystemInAlarm():
                Status["Status"].append({"Alarm State" : "System In Alarm"})
                Status["Status"].append({"Active Alarms" : self.GetExtendedDisplayString(self.controllerimport, "alarm_conditions")})

            # Generator time
            Time = []
            Status["Status"].append({"Time":Time})
            Time.append({"Monitor Time" : datetime.datetime.now().strftime("%A %B %-d, %Y %H:%M:%S")})
            # TODO Time.append({"Generator Time" : self.GetDateTime()})

        except Exception as e1:
            self.LogErrorLine("Error in DisplayStatus: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(Status,""))

        return Status

    #------------ CustomController:GetSingleSensor -----------------------------
    def GetSingleSensor(self, dict_name, ReturnFloat = False, ReturnInt = False):

        try:
            if ReturnInt:
                ReturnValue = 0
            elif ReturnFloat:
                ReturnValue = 0.0
            else:
                ReturnValue = ""
            dict_results = self.controllerimport.get(dict_name, None)

            if dict_results == None:
                return ReturnValue

            out_string = self.GetExtendedDisplayString(self.controllerimport, dict_name)

            if not len(out_string):
                return ReturnValue
            if ReturnInt or ReturnFloat:
                out_string = self.removeAlpha(out_string)
            if ReturnInt:
                if self.StringIsFloat(out_string):
                    return int(float(out_string))
                return int(out_string)
            elif ReturnFloat:
                if self.StringIsInt(out_string):
                    return float(int(out_string))
                return float(out_string)
            else:
                return out_string

        except Exception as e1:
            self.LogErrorLine("Error in GetSingleSensor: " + str(dict_name) +  " : " + str(e1))
            return "Unknown"
    #------------ GeneratorController:GetExtendedDisplayString -----------------
    # returns one or multiple status strings
    def GetExtendedDisplayString(self, inputdict, key_name):

        try:
            StateList =  self.GetDisplayList(inputdict, key_name)
            ListValues = []
            for entry in StateList:
                ListValues.extend(entry.values())
            ReturnString = ",".join(ListValues)
            if not len(ReturnString):
                return "Unknown"
            return ReturnString
        except Exception as e1:
            self.LogErrorLine("Error in DisplayStatus: " + str(e1))
            return "Unknown"

    #------------ GeneratorController:GetGaugeValue ----------------------------
    def GetGaugeValue(self, sensor_title):

        try:
            sensor_list = self.GetDisplayList(self.controllerimport, "gauges")

            for sensor in sensor_list:
                if sensor_title in list(sensor.keys()):
                    items = list(sensor.values())
                    if len(items) == 1:
                        return items[0]
            return "Unknown"
        except Exception as e1:
            self.LogErrorLine("Error in GetGaugeValue: " + str(e1))
            return "Unknown"
    #------------ GeneratorController:GetDisplayList ---------------------------
    # parse a list of modbus values (expressed as dicts) and any sub lists of
    # values (also expressed as dicts, return a displayable dict with parsed values
    def GetDisplayList(self, inputdict, key_name, JSONNum = False):

        ReturnValue = []
        try:
            default = None
            ParseList = inputdict.get(key_name, None)
            if not isinstance(ParseList, list) or ParseList == None:
                self.LogError("Error in GetDisplayList: invalid input or data: " + str(key_name))
                return ReturnValue

            for Entry in ParseList:
                if not isinstance(Entry, dict):
                    self.LogError("Error in GetDisplayList: invalid list entry: " + str(Entry))
                    return ReturnValue

                title, value = self.GetDisplayEntry(Entry, JSONNum)

                if title == "default":
                    default = value
                    value = None
                if title != None:
                    if value != None:
                        ReturnValue.append({title:value})

            if not len(ReturnValue) and not default == None:
                ReturnValue.append({"default":default})
        except Exception as e1:
            self.LogErrorLine("Error in GetDisplayList: (" + key_name + ") : " + str(e1))
            return ReturnValue
        return ReturnValue

    #------------ GeneratorController:GetDisplayEntry --------------------------
    # return a title and value of an input dict describing the modbus register
    # and type of value it is
    def GetDisplayEntry(self, entry, JSONNum = False):

        ReturnTitle = ReturnValue = None
        try:
            if not isinstance(entry, dict):
                self.LogError("Error: non dict passed to GetDisplayEntry: " + str(type(entry)))
                return ReturnTitle, ReturnValue

            if 'reg' not in entry.keys():  # required
                self.LogError("Error: reg not found in input to GetDisplayEntry: " + str(entry))
                return ReturnTitle, ReturnValue
            elif not self.StringIsHex(entry['reg']):
                self.LogError("Error: reg does not contain valid hex value in input to GetDisplayEntry: " + str(entry))
                return ReturnTitle, ReturnValue
            if not "type" in entry:  # required
                self.LogError("Error: type not found in input to GetDisplayEntry: " + str(entry))
                return ReturnTitle, ReturnValue
            if not "title" in entry:  # required
                self.LogError("Error: title not found in input to GetDisplayEntry: " + str(entry))
                return ReturnTitle, ReturnValue
            if entry["type"] == "bits" and not "value" in entry:
                self.LogError("Error: value (requried for bits) not found in input to GetDisplayEntry: " + str(entry))
                return ReturnTitle, ReturnValue
            if entry["type"] == "bits" and not "text" in entry:
                self.LogError("Error: text not found in input to GetDisplayEntry: " + str(entry))
                return ReturnTitle, ReturnValue
            if entry["type"] == "float" and not "multiplier" in entry:
                self.LogError("Error: multiplier (requried for float) not found in input to GetDisplayEntry: " + str(entry))
                return ReturnTitle, ReturnValue
            if entry["type"] == "regex" and not "regex" in entry:
                self.LogError("Error: regex not found in input to GetDisplayEntry: " + str(entry))
                return ReturnTitle, ReturnValue
            if "multiplier" in entry and entry["multiplier"] == 0:
                self.LogError("Error: multiplier (requried for float) must not be zero in input to GetDisplayEntry: " + str(entry))
                return ReturnTitle, ReturnValue
            if entry["type"] in ["int", "bits", "regex"] and not "mask" in entry:  # required
                self.LogError("Error: mask not found in input to GetDisplayEntry: " + str(entry))
                return ReturnTitle, ReturnValue
            elif "mask" in entry and not self.StringIsHex(entry['mask']):
                self.LogError("Error: mask does not contain valid hex value in input to GetDisplayEntry: " + str(entry))
                return ReturnTitle, ReturnValue
            if entry["type"] == "default" and not "text" in entry:
                self.LogError("Error: text (default) not found in input to GetDisplayEntry: " + str(entry))
                return ReturnTitle, ReturnValue

            ReturnTitle = entry["title"]
            if entry["type"] == "bits":
                value = self.GetParameter(entry["reg"], ReturnInt = True)
                value = value & int(entry["mask"], 16)
                if value == int(entry["value"], 16):
                    ReturnValue = entry["text"]
                else:
                    ReturnValue = None
                    return ReturnTitle, ReturnValue
            elif entry["type"] == "float":
                Divider = 1 / float(entry["multiplier"])
                value = self.GetParameter(entry["reg"], Divider = Divider, ReturnFloat = True)
                ReturnValue = float(value)
            elif entry["type"] == "int":
                value = self.GetParameter(entry["reg"], ReturnInt = True)
                value = value & int(entry["mask"], 16)
                if "multiplier" in entry:
                    value = value * float(entry["multiplier"])
                ReturnValue = int(value)
            elif entry["type"] == "regex":
                regex_pattern = entry["regex"]
                value = self.GetParameter(entry["reg"], ReturnInt = True)
                value = value & int(entry["mask"], 16)
                value = "%x" % value
                result = re.match(regex_pattern, value)

                if result:
                    ReturnValue = entry["text"]
                else:
                    ReturnValue = None
            elif entry["type"] == "default":
                ReturnValue = entry["text"]
                ReturnTitle = "default"
            else:
                self.LogError("Unknown type found in GetDisplayEntry: " + str(entry))

            if "units" in entry and ReturnValue != None:
                units = entry["units"]
                if units == None:
                    units = ""
                ReturnValue = self.ValueOut(ReturnValue, str(units), JSONNum)

        except Exception as e1:
            self.LogErrorLine("Error in GetDisplayEntry : " + str(e1))

        return ReturnTitle, ReturnValue

    #------------ GeneratorController:GetRunHours ------------------------------
    # return a string with no units of run hours
    def GetRunHours(self):

        run_hours = self.GetSingleSensor("run_hours")
        run_hours = self.removeAlpha(run_hours)
        return run_hours

    #------------------- CustomController::DisplayOutage -----------------------
    def DisplayOutage(self, DictOut = False, JSONNum = False):

        try:
            Outage = collections.OrderedDict()
            Outage["Outage"] = []

            Outage["Outage"].append({"Status" : "Not Supported"})
            Outage["Outage"].append({"System In Outage" : "Yes" if self.SystemInOutage else "No"})

        except Exception as e1:
            self.LogErrorLine("Error in DisplayOutage: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(Outage,""))

        return Outage

    #------------ CustomController::DisplayRegisters ---------------------------
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


        except Exception as e1:
            self.LogErrorLine("Error in DisplayRegisters: " + str(e1))

        if not DictOut:
            return self.printToString(self.ProcessDispatch(Registers,""))

        return Registers

    #----------  CustomController:GetController  -------------------------------
    # return the name of the controller, if Actual == False then return the
    # controller name that the software has been instructed to use if overridden
    # in the conf file
    def GetController(self, Actual = True):

        return self.Model

    #----------  CustomController:ComminicationsIsActive  ----------------------
    # Called every few seconds, if communictions are failing, return False, otherwise
    # True
    def ComminicationsIsActive(self):
        if self.LastRxPacketCount == self.ModBus.RxPacketCount:
            return False
        else:
            self.LastRxPacketCount = self.ModBus.RxPacketCount
            return True

    #----------  CustomController:RemoteButtonsSupported  ----------------------
    # return true if Panel buttons are settable via the software
    def RemoteButtonsSupported(self):
        return False
    #----------  CustomController:PowerMeterIsSupported  -----------------------
    # return true if GetPowerOutput is supported
    def PowerMeterIsSupported(self):

        if self.bDisablePowerLog:
            return False
        if self.UseExternalCTData:
            return True

        if "power" in self.controllerimport.keys():
            return True
        return False

    #---------------------CustomController::GetPowerOutput----------------------
    # returns current kW
    # rerturn empty string ("") if not supported,
    # return kW with units i.e. "2.45kW"
    def GetPowerOutput(self, ReturnFloat = False):

        try:
            return self.GetSingleSensor("power", ReturnFloat = ReturnFloat)
        except Exception as e1:
            self.LogErrorLine("Error in GetPowerOutput: " + str(e1))
            return "Unknown"

    #------------ CustomController:GetBaseStatus -------------------------------
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
            if "exercising" in EngineStatus or "exercise" in EngineStatus or "quiettest" in EngineStatus:
                IsExercising = True
            else:
                IsExercising = False
            if "service" in EngineStatus or "service" in GeneratorStatus:
                ServiceDue = True
            else:
                ServiceDue = False

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

    #----------  CustomController::FuelSensorSupported--------------------------
    def FuelSensorSupported(self):

        if "fuel" in self.controllerimport.keys():
            return True

        return False

    #------------ CustomController:GetFuelSensor -------------------------------
    def GetFuelSensor(self, ReturnInt = False):

        if not self.FuelSensorSupported():
            return None

        try:
            return self.GetSingleSensor("fuel", ReturnInt = ReturnInt)
        except Exception as e1:
            self.LogErrorLine("Error in GetFuelSensor: " + str(e1))
            return "Unknown"

    #----------  CustomController::GetFuelConsumptionDataPoints-----------------
    def GetFuelConsumptionDataPoints(self):

        try:
            if self.FuelHalfRate == 0 or self.FuelFullRate == 0:
                return None

            return [.5, float(self.FuelHalfRate), 1.0, float(self.FuelFullRate), self.FuelUnits]

        except Exception as e1:
            self.LogErrorLine("Error in GetFuelConsumptionDataPoints: " + str(e1))
        return None
