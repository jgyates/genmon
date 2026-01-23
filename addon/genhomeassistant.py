#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: genhomeassistant.py
# PURPOSE: Home Assistant MQTT Discovery integration for genmon
#
#  AUTHOR: Claude AI (Anthropic) with jgyates genmon framework
#    DATE: 2024
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import json
import os
import re
import signal
import ssl
import sys
import threading
import time

try:
    import paho.mqtt.client as mqtt
except Exception as e1:
    print(
        "\n\nThis program requires the paho-mqtt module. Please use 'sudo pip3 install paho-mqtt' to install.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)

try:
    # Add parent directory to path for genmonlib imports
    file_root = os.path.dirname(os.path.realpath(__file__))
    parent_root = os.path.abspath(os.path.join(file_root, os.pardir))
    if os.path.isdir(os.path.join(parent_root, "genmonlib")):
        sys.path.insert(1, parent_root)

    from genmonlib.myclient import ClientInterface
    from genmonlib.mycommon import MyCommon
    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.mysupport import MySupport
    from genmonlib.mythread import MyThread
    from genmonlib.program_defaults import ProgramDefaults

except Exception as e1:
    print(
        "\n\nThis program requires the modules located in the genmonlib directory.\n"
    )
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)


# -------------------------------------------------------------------------------
# Entity Definitions
# -------------------------------------------------------------------------------

# Sensor definitions: key is entity_id suffix
# path: JSON path in genmon data (using / separator)
# name: Human readable name
# device_class: HA device class (or None)
# unit: Unit of measurement (or None)
# icon: MDI icon
# state_class: measurement, total, total_increasing (or None)
# category: diagnostic, config, or None (default)
# enabled: True if enabled by default
SENSOR_DEFINITIONS = {
    # Engine sensors
    "battery_voltage": {
        "name": "Battery Voltage",
        "path": "Status/Engine/Battery Voltage",
        "device_class": "voltage",
        "unit": "V",
        "icon": "mdi:car-battery",
        "state_class": "measurement",
    },
    "rpm": {
        "name": "RPM",
        "path": "Status/Engine/RPM",
        "device_class": None,
        "unit": "RPM",
        "icon": "mdi:engine",
        "state_class": "measurement",
    },
    "frequency": {
        "name": "Output Frequency",
        "path": "Status/Engine/Frequency",
        "device_class": "frequency",
        "unit": "Hz",
        "icon": "mdi:sine-wave",
        "state_class": "measurement",
    },
    "output_voltage": {
        "name": "Output Voltage",
        "path": "Status/Engine/Output Voltage",
        "device_class": "voltage",
        "unit": "V",
        "icon": "mdi:flash",
        "state_class": "measurement",
    },
    "output_current": {
        "name": "Output Current",
        "path": "Status/Engine/Output Current",
        "device_class": "current",
        "unit": "A",
        "icon": "mdi:current-ac",
        "state_class": "measurement",
    },
    "output_power": {
        "name": "Output Power",
        "path": "Status/Engine/Output Power (Single Phase)",
        "device_class": "power",
        "unit": "kW",
        "icon": "mdi:lightning-bolt",
        "state_class": "measurement",
    },
    "power_leg1": {
        "name": "Power Leg 1",
        "path": "Status/Engine/Power Leg 1",
        "device_class": "power",
        "unit": "kW",
        "icon": "mdi:lightning-bolt",
        "state_class": "measurement",
        "controllers": ["evolution", "nexus", "h-100", "powerzone"],
    },
    "power_leg2": {
        "name": "Power Leg 2",
        "path": "Status/Engine/Power Leg 2",
        "device_class": "power",
        "unit": "kW",
        "icon": "mdi:lightning-bolt",
        "state_class": "measurement",
        "controllers": ["evolution", "nexus", "h-100", "powerzone"],
    },
    "current_leg1": {
        "name": "Current Leg 1",
        "path": "Status/Engine/Current Leg 1",
        "device_class": "current",
        "unit": "A",
        "icon": "mdi:current-ac",
        "state_class": "measurement",
        "controllers": ["evolution", "nexus", "h-100", "powerzone"],
    },
    "current_leg2": {
        "name": "Current Leg 2",
        "path": "Status/Engine/Current Leg 2",
        "device_class": "current",
        "unit": "A",
        "icon": "mdi:current-ac",
        "state_class": "measurement",
        "controllers": ["evolution", "nexus", "h-100", "powerzone"],
    },
    "engine_state": {
        "name": "Engine State",
        "path": "Status/Engine/Engine State",
        "device_class": None,
        "unit": None,
        "icon": "mdi:engine",
        "state_class": None,
    },
    "switch_state": {
        "name": "Switch State",
        "path": "Status/Engine/Switch State",
        "device_class": None,
        "unit": None,
        "icon": "mdi:electric-switch",
        "state_class": None,
    },
    "active_alarms": {
        "name": "Active Alarms",
        "path": "Status/Engine/System In Alarm",
        "device_class": None,
        "unit": None,
        "icon": "mdi:alert",
        "state_class": None,
    },
    # Line sensors
    "utility_voltage": {
        "name": "Utility Voltage",
        "path": "Status/Line/Utility Voltage",
        "device_class": "voltage",
        "unit": "V",
        "icon": "mdi:transmission-tower",
        "state_class": "measurement",
    },
    "utility_voltage_max": {
        "name": "Utility Voltage Max",
        "path": "Status/Line/Utility Max Voltage",
        "device_class": "voltage",
        "unit": "V",
        "icon": "mdi:arrow-up-bold",
        "state_class": "measurement",
        "enabled_default": False,
    },
    "utility_voltage_min": {
        "name": "Utility Voltage Min",
        "path": "Status/Line/Utility Min Voltage",
        "device_class": "voltage",
        "unit": "V",
        "icon": "mdi:arrow-down-bold",
        "state_class": "measurement",
        "enabled_default": False,
    },
    "utility_threshold": {
        "name": "Utility Threshold Voltage",
        "path": "Status/Line/Utility Threshold Voltage",
        "device_class": "voltage",
        "unit": "V",
        "icon": "mdi:tune-vertical",
        "state_class": None,
        "category": "diagnostic",
    },
    "transfer_switch_state": {
        "name": "Transfer Switch State",
        "path": "Status/Line/Transfer Switch State",
        "device_class": None,
        "unit": None,
        "icon": "mdi:electric-switch",
        "state_class": None,
        "controllers": ["evolution", "nexus", "h-100", "powerzone"],
    },
    # Maintenance sensors
    "fuel_level": {
        "name": "Fuel Level",
        "path": "Maintenance/Fuel Level Sensor",
        "device_class": None,
        "unit": "%",
        "icon": "mdi:fuel",
        "state_class": "measurement",
    },
    "estimated_fuel": {
        "name": "Estimated Fuel in Tank",
        "path": "Maintenance/Estimated Fuel In Tank",
        "device_class": None,
        "unit": "gal",
        "icon": "mdi:gas-station",
        "state_class": "measurement",
    },
    "hours_fuel_remaining": {
        "name": "Hours of Fuel Remaining",
        "path": "Maintenance/Hours of Fuel Remaining",
        "device_class": "duration",
        "unit": "h",
        "icon": "mdi:timer-sand",
        "state_class": "measurement",
    },
    "ambient_temp": {
        "name": "Ambient Temperature",
        "path": "Maintenance/Ambient Temperature Sensor",
        "device_class": "temperature",
        "unit": None,  # Will be set based on metric setting
        "icon": "mdi:thermometer",
        "state_class": "measurement",
        "controllers": ["evolution", "h-100"],
    },
    "cpu_temp": {
        "name": "CPU Temperature",
        "path": "Tiles/CPU Temp/value",
        "device_class": "temperature",
        "unit": None,  # Will be set based on metric setting
        "icon": "mdi:cpu-64-bit",
        "state_class": "measurement",
        "category": "diagnostic",
    },
    "kwh_30days": {
        "name": "Energy (30 Days)",
        "path": "Maintenance/kW Hours in last 30 days",
        "device_class": "energy",
        "unit": "kWh",
        "icon": "mdi:meter-electric",
        "state_class": "total",
    },
    "run_hours_30days": {
        "name": "Run Hours (30 Days)",
        "path": "Maintenance/Run Hours in last 30 days",
        "device_class": "duration",
        "unit": "h",
        "icon": "mdi:timer",
        "state_class": "total",
    },
    "fuel_30days": {
        "name": "Fuel Consumption (30 Days)",
        "path": "Maintenance/Fuel Consumption in last 30 days",
        "device_class": None,
        "unit": "gal",
        "icon": "mdi:gas-station",
        "state_class": "total",
    },
    # Service due sensors (Evolution controllers only - Nexus uses different service naming)
    "service_a_due": {
        "name": "Service A Due",
        "path": "Maintenance/Service/Service A Due",
        "device_class": None,
        "unit": None,
        "icon": "mdi:wrench-clock",
        "state_class": None,
        "category": "diagnostic",
        "controllers": ["evolution"],
    },
    "service_b_due": {
        "name": "Service B Due",
        "path": "Maintenance/Service/Service B Due",
        "device_class": None,
        "unit": None,
        "icon": "mdi:wrench-clock",
        "state_class": None,
        "category": "diagnostic",
        "controllers": ["evolution"],
    },
    "battery_check_due": {
        "name": "Battery Check Due",
        "path": "Maintenance/Service/Battery Check Due",
        "device_class": None,
        "unit": None,
        "icon": "mdi:battery-clock",
        "state_class": None,
        "category": "diagnostic",
        "controllers": ["evolution"],
    },
    "oil_service": {
        "name": "Oil and Filter Service Due",
        "path": "Maintenance/Service/Oil and Oil Filter Service Due",
        "device_class": None,
        "unit": None,
        "icon": "mdi:oil",
        "state_class": None,
        "category": "diagnostic",
    },
    "air_filter_service": {
        "name": "Air Filter Service Due",
        "path": "Maintenance/Service/Air Filter Service Due",
        "device_class": None,
        "unit": None,
        "icon": "mdi:air-filter",
        "state_class": None,
        "category": "diagnostic",
    },
    "spark_plug_service": {
        "name": "Spark Plug Service Due",
        "path": "Maintenance/Service/Spark Plug Service Due",
        "device_class": None,
        "unit": None,
        "icon": "mdi:flash",
        "state_class": None,
        "category": "diagnostic",
    },
    "battery_service": {
        "name": "Battery Service Due",
        "path": "Maintenance/Service/Battery Service Due",
        "device_class": None,
        "unit": None,
        "icon": "mdi:car-battery",
        "state_class": None,
        "category": "diagnostic",
    },
    # Outage sensors
    "outage_status": {
        "name": "Outage Status",
        "path": "Outage/Status",
        "device_class": None,
        "unit": None,
        "icon": "mdi:power-plug-off",
        "state_class": None,
    },
    "startup_delay": {
        "name": "Startup Delay",
        "path": "Outage/Startup Delay",
        "device_class": "duration",
        "unit": "s",
        "icon": "mdi:timer",
        "state_class": None,
        "category": "diagnostic",
    },
    # Diagnostic sensors
    "model": {
        "name": "Model",
        "path": "Maintenance/Model",
        "device_class": None,
        "unit": None,
        "icon": "mdi:information",
        "state_class": None,
        "category": "diagnostic",
    },
    "serial_number": {
        "name": "Serial Number",
        "path": "Maintenance/Generator Serial Number",
        "device_class": None,
        "unit": None,
        "icon": "mdi:identifier",
        "state_class": None,
        "category": "diagnostic",
    },
    "controller": {
        "name": "Controller",
        "path": "Maintenance/Controller Detected",
        "device_class": None,
        "unit": None,
        "icon": "mdi:chip",
        "state_class": None,
        "category": "diagnostic",
    },
    "nominal_rpm": {
        "name": "Nominal RPM",
        "path": "Maintenance/Nominal RPM",
        "device_class": None,
        "unit": "RPM",
        "icon": "mdi:speedometer",
        "state_class": None,
        "category": "diagnostic",
    },
    "rated_kw": {
        "name": "Rated Power",
        "path": "Maintenance/Rated kW",
        "device_class": "power",
        "unit": "kW",
        "icon": "mdi:flash",
        "state_class": None,
        "category": "diagnostic",
    },
    "fuel_type": {
        "name": "Fuel Type",
        "path": "Maintenance/Fuel Type",
        "device_class": None,
        "unit": None,
        "icon": "mdi:fuel",
        "state_class": None,
        "category": "diagnostic",
    },
    "exercise_time": {
        "name": "Exercise Time",
        "path": "Maintenance/Exercise/Exercise Time",
        "device_class": None,
        "unit": None,
        "icon": "mdi:calendar-clock",
        "state_class": None,
    },
    # Monitor sensors
    "monitor_health": {
        "name": "Monitor Health",
        "path": "Monitor/Generator Monitor Stats/Monitor Health",
        "device_class": None,
        "unit": None,
        "icon": "mdi:heart-pulse",
        "state_class": None,
    },
    "genmon_version": {
        "name": "Genmon Version",
        "path": "Monitor/Generator Monitor Stats/Generator Monitor Version",
        "device_class": None,
        "unit": None,
        "icon": "mdi:tag",
        "state_class": None,
        "category": "diagnostic",
    },
    "run_time": {
        "name": "Monitor Run Time",
        "path": "Monitor/Generator Monitor Stats/Run time",
        "device_class": None,
        "unit": None,
        "icon": "mdi:clock-outline",
        "state_class": None,
        "category": "diagnostic",
        "monitor_stats": True,
    },
    "cpu_usage": {
        "name": "CPU Usage",
        "path": "Monitor/Platform Stats/CPU Utilization",
        "device_class": None,
        "unit": "%",
        "icon": "mdi:cpu-64-bit",
        "state_class": "measurement",
        "category": "diagnostic",
        "monitor_stats": True,
    },
    # NOTE: memory_usage removed - only CPU Utilization exists in genmon, not Memory Utilization
    "crc_errors": {
        "name": "CRC Errors",
        "path": "Monitor/Communication Stats/CRC Errors",
        "device_class": None,
        "unit": None,
        "icon": "mdi:alert-circle",
        "state_class": "total_increasing",
        "category": "diagnostic",
        "monitor_stats": True,
    },
    "timeout_errors": {
        "name": "Timeout Errors",
        "path": "Monitor/Communication Stats/Timeouts",
        "device_class": None,
        "unit": None,
        "icon": "mdi:timer-off",
        "state_class": "total_increasing",
        "category": "diagnostic",
        "monitor_stats": True,
    },
    "comm_success": {
        "name": "Communication Success",
        "path": "Monitor/Communication Stats/Packet Count",
        "device_class": None,
        "unit": None,
        "icon": "mdi:check-network",
        "state_class": None,
        "category": "diagnostic",
        "monitor_stats": True,
    },
    # Log entry sensors
    "last_alarm_log": {
        "name": "Last Alarm",
        "path": "Status/Last Log Entries/Logs/Alarm Log",
        "device_class": None,
        "unit": None,
        "icon": "mdi:alert",
        "state_class": None,
        "category": "diagnostic",
    },
    "last_run_log": {
        "name": "Last Run",
        "path": "Status/Last Log Entries/Logs/Run Log",
        "device_class": None,
        "unit": None,
        "icon": "mdi:engine",
        "state_class": None,
        "category": "diagnostic",
    },
    "last_outage": {
        "name": "Last Outage",
        "path": "Outage/Outage Log/0",
        "device_class": None,
        "unit": None,
        "icon": "mdi:power-plug-off",
        "state_class": None,
        "category": "diagnostic",
    },
    # Weather sensors
    "weather_temp": {
        "name": "Weather Temperature",
        "path": "Monitor/Weather/Temperature",
        "device_class": "temperature",
        "unit": None,
        "icon": "mdi:thermometer",
        "state_class": "measurement",
        "weather": True,
    },
    "weather_humidity": {
        "name": "Weather Humidity",
        "path": "Monitor/Weather/Humidity",
        "device_class": "humidity",
        "unit": "%",
        "icon": "mdi:water-percent",
        "state_class": "measurement",
        "weather": True,
    },
    "weather_pressure": {
        "name": "Weather Pressure",
        "path": "Monitor/Weather/Pressure",
        "device_class": "pressure",
        "unit": None,
        "icon": "mdi:gauge",
        "state_class": "measurement",
        "weather": True,
    },
    "weather_conditions": {
        "name": "Weather Conditions",
        "path": "Monitor/Weather/Conditions",
        "device_class": None,
        "unit": None,
        "icon": "mdi:weather-partly-cloudy",
        "state_class": None,
        "weather": True,
    },
}

# Binary sensor definitions
BINARY_SENSOR_DEFINITIONS = {
    "system_in_outage": {
        "name": "System In Outage",
        "path": "Outage/System In Outage",
        "device_class": "power",
        "payload_on": "Yes",
        "payload_off": "No",
        "icon": "mdi:transmission-tower-off",
    },
    "generator_running": {
        "name": "Generator Running",
        "path": "Status/Engine/Engine State",
        "device_class": "running",
        "payload_on": ["Running", "Exercising", "Running Manual"],
        "payload_off": ["Off", "Stopped", "Off - Loss of Speed or Flame", "Ready"],
        "icon": "mdi:engine",
    },
    "exercising": {
        "name": "Exercising",
        "path": "Status/Engine/Engine State",
        "device_class": None,
        "payload_on": ["Exercising"],
        "payload_off_invert": True,
        "icon": "mdi:dumbbell",
    },
    "alarm_active": {
        "name": "Alarm Active",
        "path": "Status/Engine/System In Alarm",
        "device_class": "problem",
        "payload_on_not_empty": True,
        "icon": "mdi:alert",
    },
    "transfer_to_generator": {
        "name": "Transfer to Generator",
        "path": "Status/Line/Transfer Switch State",
        "device_class": None,
        "payload_on": ["Generator"],
        "payload_off": ["Utility"],
        "icon": "mdi:electric-switch-closed",
        "controllers": ["evolution", "nexus", "h-100", "powerzone"],
    },
    "utility_present": {
        "name": "Utility Power Present",
        "path": "Outage/System In Outage",
        "device_class": "power",
        "payload_on": "No",
        "payload_off": "Yes",
        "icon": "mdi:transmission-tower",
    },
    "switch_in_auto": {
        "name": "Switch in Auto",
        "path": "Status/Engine/Switch State",
        "device_class": None,
        "payload_on": ["Auto", "System in Auto"],
        "payload_off_invert": True,
        "icon": "mdi:auto-mode",
    },
    "update_available": {
        "name": "Update Available",
        "path": "Monitor/Generator Monitor Stats/Update Available",
        "device_class": "update",
        "payload_on": "Yes",
        "payload_off": "No",
        "icon": "mdi:update",
        "category": "diagnostic",
    },
}

# Button definitions for remote commands
BUTTON_DEFINITIONS = {
    "start": {
        "name": "Start Generator",
        "command": "setremote=START",
        "icon": "mdi:play",
    },
    "stop": {
        "name": "Stop Generator",
        "command": "setremote=STOP",
        "icon": "mdi:stop",
    },
    "start_transfer": {
        "name": "Start and Transfer",
        "command": "setremote=STARTTRANSFER",
        "icon": "mdi:play-circle",
        "controllers": ["evolution", "nexus", "h-100", "powerzone"],
    },
    "start_exercise": {
        "name": "Start Exercise",
        "command": "setremote=STARTEXERCISE",
        "icon": "mdi:dumbbell",
    },
    "set_time": {
        "name": "Set Generator Time",
        "command": "settime",
        "icon": "mdi:clock-edit",
    },
}

# Switch definitions
SWITCH_DEFINITIONS = {
    "quiet_mode": {
        "name": "Quiet Mode",
        "command_on": "setquiet=on",
        "command_off": "setquiet=off",
        "icon": "mdi:volume-off",
        "state_path": "Maintenance/Exercise/Quiet Mode",
        "payload_on": "On",
        "payload_off": "Off",
        "controllers": ["evolution", "nexus"],
    },
}

# Select definitions for dropdown controls
SELECT_DEFINITIONS = {
    "exercise_frequency": {
        "name": "Exercise Frequency",
        "icon": "mdi:calendar-refresh",
        "options": ["Weekly", "BiWeekly", "Monthly"],
        "command_template": "exercise",  # Special handling for exercise
    },
    "exercise_day_of_week": {
        "name": "Exercise Day of Week",
        "icon": "mdi:calendar-week",
        "options": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "command_template": "exercise",  # Special handling for exercise
    },
}

# Number definitions for numeric inputs
NUMBER_DEFINITIONS = {
    "exercise_day_of_month": {
        "name": "Exercise Day of Month",
        "icon": "mdi:calendar-month",
        "min": 1,
        "max": 28,
        "step": 1,
        "unit": None,
        "command_template": "exercise",  # Special handling for exercise
    },
    "exercise_hour": {
        "name": "Exercise Hour",
        "icon": "mdi:clock-outline",
        "min": 0,
        "max": 23,
        "step": 1,
        "unit": None,
        "command_template": "exercise",  # Special handling for exercise
    },
    "exercise_minute": {
        "name": "Exercise Minute",
        "icon": "mdi:clock-outline",
        "min": 0,
        "max": 59,
        "step": 1,
        "unit": None,
        "command_template": "exercise",  # Special handling for exercise
    },
}


# -------------------------------------------------------------------------------
# MyHomeAssistant class
# -------------------------------------------------------------------------------
class MyHomeAssistant(MySupport):

    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        configfilepath=ProgramDefaults.ConfPath,
        console=None,
    ):

        super(MyHomeAssistant, self).__init__()

        self.log = log
        self.console = console
        self.Exiting = False

        # Configuration defaults
        self.MQTTAddress = None
        self.MQTTPort = 1883
        self.Username = None
        self.Password = None
        self.MonitorAddress = host
        self.DiscoveryPrefix = "homeassistant"
        self.BaseTopic = "genmon"
        self.DeviceId = "generator"
        self.DeviceName = "Generator"
        self.PollTime = 3
        self.DiscoveryInterval = 300
        self.BlackList = []
        self.IncludeMonitorStats = True
        self.IncludeWeather = True
        self.IncludeLogs = False
        self.UseNumeric = True
        self.UseMetric = False  # Read from genmon.conf metricweather setting
        self.debug = False

        # Runtime state
        self.AccessLock = threading.Lock()
        self.LastValues = {}
        self.StartInfo = {}
        self.ControllerType = "unknown"
        self.EnhancedExerciseMode = False  # True if BiWeekly/Monthly supported
        self.WriteQuietMode = False  # True if setquiet command supported
        self.RemoteButtons = False  # True if remote start/stop supported
        self.ExerciseControls = True  # True if exercise controls supported
        self.RemoteCommands = False  # True if remote commands supported
        self.DeviceInfo = {}
        self.EntitiesPublished = False
        self.LastDiscoveryTime = 0
        self.DynamicSensors = {}  # Storage for dynamically discovered sensors

        # Entity cleanup tracking
        self.ExistingEntities = set()  # Entities found via MQTT subscription
        self.PublishedEntities = set()  # Entities we've published this session
        self.CleanupComplete = False  # True after stale entities removed
        self.DiscoverySubscribed = False  # True when subscribed to discovery topics

        # Entity definitions - will be loaded from JSON or fall back to hardcoded
        self.SensorDefinitions = {}
        self.BinarySensorDefinitions = {}
        self.ButtonDefinitions = {}
        self.SwitchDefinitions = {}
        self.SelectDefinitions = {}
        self.NumberDefinitions = {}

        # Exercise time settings (parsed from genmon)
        self.ExerciseSettings = {
            "frequency": "Weekly",
            "day_of_week": "Sunday",
            "day_of_month": 1,
            "hour": 12,
            "minute": 0,
        }

        try:
            self._load_config(configfilepath)
        except Exception as e1:
            self.LogErrorLine("Error loading configuration: " + str(e1))
            sys.exit(1)

        try:
            self.Generator = ClientInterface(host=self.MonitorAddress, port=port, log=log)
            self._get_generator_info()
        except Exception as e1:
            self.LogErrorLine("Error connecting to genmon: " + str(e1))
            sys.exit(1)

        # Load entity definitions from JSON files (with hardcoded fallback)
        try:
            self._load_entity_definitions()
        except Exception as e1:
            self.LogErrorLine("Error loading entity definitions: " + str(e1))
            self._use_hardcoded_fallback()

        try:
            self._setup_mqtt()
        except Exception as e1:
            self.LogErrorLine("Error setting up MQTT: " + str(e1))
            sys.exit(1)

        # Start polling thread
        self.Threads = {}
        self.Threads["PollingThread"] = MyThread(
            self._polling_thread, Name="PollingThread", start=False
        )
        self.Threads["PollingThread"].Start()

        # Start discovery republish thread if interval > 0
        if self.DiscoveryInterval > 0:
            self.Threads["DiscoveryThread"] = MyThread(
                self._discovery_thread, Name="DiscoveryThread", start=False
            )
            self.Threads["DiscoveryThread"].Start()

        signal.signal(signal.SIGTERM, self._signal_close)
        signal.signal(signal.SIGINT, self._signal_close)

        self.MQTTclient.loop_start()

    # --------------------------------------------------------------------------
    def _load_config(self, configfilepath):
        """Load configuration from config file"""

        config = MyConfig(
            filename=os.path.join(configfilepath, "genhomeassistant.conf"),
            section="genhomeassistant",
            log=self.log,
        )

        self.MQTTAddress = config.ReadValue("mqtt_address")
        if not self.MQTTAddress or not len(self.MQTTAddress):
            self.LogError("Error: mqtt_address is required")
            sys.exit(1)

        self.Username = config.ReadValue("username")
        self.Password = config.ReadValue("password")
        self.MQTTPort = config.ReadValue("mqtt_port", return_type=int, default=1883)

        self.MonitorAddress = config.ReadValue("monitor_address", default=self.MonitorAddress)
        if self.MonitorAddress:
            self.MonitorAddress = self.MonitorAddress.strip()
        if not self.MonitorAddress:
            self.MonitorAddress = ProgramDefaults.LocalHost

        self.DiscoveryPrefix = config.ReadValue("discovery_prefix", default="homeassistant")
        self.BaseTopic = config.ReadValue("base_topic", default="genmon")
        self.DeviceId = config.ReadValue("device_id", default="generator")
        self.DeviceName = config.ReadValue("device_name", default="Generator")
        self.PollTime = config.ReadValue("poll_interval", return_type=float, default=3.0)
        self.DiscoveryInterval = config.ReadValue("discovery_interval", return_type=int, default=300)

        # TLS configuration
        self.CertificateAuthorityPath = config.ReadValue("cert_authority_path", default="")
        self.TLSVersion = config.ReadValue("tls_version", default="1.2")
        self.CertReqs = config.ReadValue("cert_reqs", default="Required")
        self.ClientCertificatePath = config.ReadValue("client_cert_path", default="")
        self.ClientKeyPath = config.ReadValue("client_key_path", default="")

        # Entity filtering
        # Default blacklist excludes web UI tile data which duplicates existing sensors
        default_blacklist = "Tiles"
        blacklist_str = config.ReadValue("blacklist", default=default_blacklist)
        if blacklist_str:
            self.BlackList = [x.strip().lower() for x in blacklist_str.split(",") if x.strip()]

        self.IncludeMonitorStats = config.ReadValue("include_monitor_stats", return_type=bool, default=True)
        self.IncludeWeather = config.ReadValue("include_weather", return_type=bool, default=True)
        self.IncludeLogs = config.ReadValue("include_logs", return_type=bool, default=False)
        self.UseNumeric = config.ReadValue("numeric_json", return_type=bool, default=True)
        self.debug = config.ReadValue("debug", return_type=bool, default=False)
        self.ClientID = config.ReadValue("client_id", default="genmon_ha")

        # Read metric setting from genmon.conf for temperature unit selection
        try:
            genmon_config = MyConfig(
                filename=os.path.join(configfilepath, "genmon.conf"),
                section="GenMon",
                log=self.log,
            )
            self.UseMetric = genmon_config.ReadValue("metricweather", return_type=bool, default=False)
            self.LogDebug(f"Using metric units: {self.UseMetric}")
        except Exception as e:
            self.LogDebug(f"Could not read metricweather from genmon.conf, defaulting to imperial: {e}")

    # --------------------------------------------------------------------------
    def _get_generator_info(self):
        """Get generator information from genmon"""

        try:
            data = self._send_command("generator: start_info_json")
            self.StartInfo = json.loads(data)

            # Determine controller type
            controller = self.StartInfo.get("Controller", "").lower()
            if "evolution" in controller:
                self.ControllerType = "evolution"
            elif "nexus" in controller:
                self.ControllerType = "nexus"
            elif "h-100" in controller or "g-panel" in controller:
                self.ControllerType = "h-100"
            elif "powerzone" in controller:
                self.ControllerType = "powerzone"
            else:
                self.ControllerType = "custom"

            self.LogDebug("Controller type detected: " + self.ControllerType)

            # Check enhanced exercise support from maintenance data
            self.EnhancedExerciseMode = False
            try:
                if self.NumericJSON:
                    maint_data = self._send_command("generator: maint_num_json")
                else:
                    maint_data = self._send_command("generator: maint_json")
                maint = json.loads(maint_data)
                exercise_info = self._get_value_from_path(maint, "Maintenance/Exercise")
                if exercise_info:
                    # Look for EnhancedExerciseMode in exercise info
                    if isinstance(exercise_info, list):
                        for item in exercise_info:
                            if isinstance(item, dict):
                                if "Enhanced Exercise Mode" in item:
                                    mode_val = item["Enhanced Exercise Mode"]
                                    if isinstance(mode_val, dict):
                                        mode_val = mode_val.get("value", "False")
                                    self.EnhancedExerciseMode = str(mode_val).lower() not in ["false", "disabled", "off"]
                                    break
                self.LogDebug(f"Enhanced exercise mode: {self.EnhancedExerciseMode}")
            except Exception as e_ex:
                self.LogDebug(f"Could not determine enhanced exercise mode: {e_ex}")

            # Extract capability flags from start_info
            self.WriteQuietMode = self.StartInfo.get("WriteQuietMode", False)
            self.RemoteButtons = self.StartInfo.get("RemoteButtons", False)
            self.ExerciseControls = self.StartInfo.get("ExerciseControls", True)
            self.RemoteCommands = self.StartInfo.get("RemoteCommands", False)
            self.LogDebug(f"Capabilities - WriteQuietMode: {self.WriteQuietMode}, "
                         f"RemoteButtons: {self.RemoteButtons}, "
                         f"ExerciseControls: {self.ExerciseControls}, "
                         f"RemoteCommands: {self.RemoteCommands}")

            # Build device info
            self.DeviceInfo = {
                "identifiers": [f"genmon_{self.DeviceId}"],
                "name": self.DeviceName,
                "manufacturer": "Generac",
                "model": self.StartInfo.get("Model", "Generator"),
                "sw_version": self.StartInfo.get("Version", ProgramDefaults.GENMON_VERSION),
            }

            # Add configuration URL if we have the address
            if self.MonitorAddress and self.MonitorAddress != "127.0.0.1":
                self.DeviceInfo["configuration_url"] = f"http://{self.MonitorAddress}:8000"

        except Exception as e1:
            self.LogErrorLine("Error in _get_generator_info: " + str(e1))

    # --------------------------------------------------------------------------
    def ReadJSONConfig(self, FileName):
        """Read and parse a JSON configuration file.

        Following the pattern from gensnmp.py for consistency.
        """
        if os.path.isfile(FileName):
            try:
                with open(FileName) as infile:
                    return json.load(infile)
            except Exception as e1:
                self.LogErrorLine(
                    "Error in ReadJSONConfig reading file: " + str(e1) + ": " + str(FileName)
                )
                return None
        else:
            self.LogDebug("JSON config file not found: " + str(FileName))
            return None

    # --------------------------------------------------------------------------
    def _get_controller_config_filename(self):
        """Map controller type to JSON filename.

        For custom controllers, uses the import_config_file from start_info_json
        to allow each custom controller type to have its own JSON definition file.
        """
        # For custom controllers, use import_config_file from StartInfo
        if self.ControllerType == "custom":
            import_config = self.StartInfo.get("import_config_file", "")
            if import_config:
                # Remove .json extension if present (we'll add it)
                if import_config.lower().endswith(".json"):
                    import_config = import_config[:-5]
                return f"{import_config}.json"
            # Fallback if import_config_file not set
            return "custom.json"

        controller_map = {
            "evolution": "generac_evo_nexus.json",
            "nexus": "generac_evo_nexus.json",
            "h-100": "h_100.json",
            "powerzone": "powerzone.json",
        }
        return controller_map.get(self.ControllerType, "custom.json")

    # --------------------------------------------------------------------------
    def _convert_json_entities_to_dict(self, entity_list):
        """Convert a list of entity definitions from JSON format to dict format.

        JSON format uses a list with entity_id as a field.
        Dict format uses entity_id as the key (for backward compatibility).
        """
        result = {}
        if not entity_list:
            return result
        for entity in entity_list:
            if isinstance(entity, dict) and "entity_id" in entity:
                entity_id = entity["entity_id"]
                # Create a copy without entity_id in the value
                entity_copy = {k: v for k, v in entity.items() if k != "entity_id"}
                result[entity_id] = entity_copy
        return result

    # --------------------------------------------------------------------------
    def _merge_entity_definitions(self, new_definitions, target_dict, override=False):
        """Merge entity definitions into target dictionary.

        Args:
            new_definitions: Dict of new entity definitions
            target_dict: Target dict to merge into
            override: If True, replace existing entries; if False, only add new ones
        """
        for entity_id, entity_def in new_definitions.items():
            if override or entity_id not in target_dict:
                target_dict[entity_id] = entity_def.copy()

    # --------------------------------------------------------------------------
    def _load_entity_definitions(self):
        """Load entity definitions from JSON files.

        Loads base.json first, then controller-specific file, then optionally
        userdefined.json. Falls back to hardcoded definitions if base.json
        is missing.
        """
        # Determine the data directory path
        file_root = os.path.dirname(os.path.realpath(__file__))
        parent_root = os.path.abspath(os.path.join(file_root, os.pardir))
        data_dir = os.path.join(parent_root, "data", "homeassistant")

        # Load base.json (required for JSON-based loading)
        base_file = os.path.join(data_dir, "base.json")
        base_config = self.ReadJSONConfig(base_file)

        if base_config is None:
            self.LogDebug("base.json not found, using hardcoded fallback")
            self._use_hardcoded_fallback()
            return

        self.LogDebug(f"Loading entity definitions from JSON files in {data_dir}")

        # Convert and load base definitions
        self.SensorDefinitions = self._convert_json_entities_to_dict(
            base_config.get("sensors", [])
        )
        self.BinarySensorDefinitions = self._convert_json_entities_to_dict(
            base_config.get("binary_sensors", [])
        )
        self.ButtonDefinitions = self._convert_json_entities_to_dict(
            base_config.get("buttons", [])
        )
        self.SwitchDefinitions = self._convert_json_entities_to_dict(
            base_config.get("switches", [])
        )
        self.SelectDefinitions = self._convert_json_entities_to_dict(
            base_config.get("selects", [])
        )
        self.NumberDefinitions = self._convert_json_entities_to_dict(
            base_config.get("numbers", [])
        )

        self.LogDebug(
            f"Loaded base definitions: {len(self.SensorDefinitions)} sensors, "
            f"{len(self.BinarySensorDefinitions)} binary_sensors, "
            f"{len(self.ButtonDefinitions)} buttons, "
            f"{len(self.SwitchDefinitions)} switches, "
            f"{len(self.SelectDefinitions)} selects, "
            f"{len(self.NumberDefinitions)} numbers"
        )

        # Load controller-specific file (extends/overrides base)
        controller_filename = self._get_controller_config_filename()
        controller_file = os.path.join(data_dir, controller_filename)
        controller_config = self.ReadJSONConfig(controller_file)

        # For custom controllers, the JSON file is required
        if controller_config is None and self.ControllerType == "custom":
            import_config = self.StartInfo.get("import_config_file", "unknown")
            self.LogError(
                f"Custom controller JSON file not found: {controller_file}. "
                f"Custom controllers require a Home Assistant entity definition file. "
                f"Please create {controller_filename} in data/homeassistant/ "
                f"for your '{import_config}' controller and submit it to the repo."
            )
            # Exit the addon - custom controllers must have a definition file
            sys.exit(1)

        if controller_config:
            self.LogDebug(f"Loading controller-specific definitions from {controller_filename}")
            # Merge controller-specific definitions (override mode for customization)
            self._merge_entity_definitions(
                self._convert_json_entities_to_dict(controller_config.get("sensors", [])),
                self.SensorDefinitions,
                override=True,
            )
            self._merge_entity_definitions(
                self._convert_json_entities_to_dict(controller_config.get("binary_sensors", [])),
                self.BinarySensorDefinitions,
                override=True,
            )
            self._merge_entity_definitions(
                self._convert_json_entities_to_dict(controller_config.get("buttons", [])),
                self.ButtonDefinitions,
                override=True,
            )
            self._merge_entity_definitions(
                self._convert_json_entities_to_dict(controller_config.get("switches", [])),
                self.SwitchDefinitions,
                override=True,
            )
            self._merge_entity_definitions(
                self._convert_json_entities_to_dict(controller_config.get("selects", [])),
                self.SelectDefinitions,
                override=True,
            )
            self._merge_entity_definitions(
                self._convert_json_entities_to_dict(controller_config.get("numbers", [])),
                self.NumberDefinitions,
                override=True,
            )

        # Optionally load userdefined.json (user customizations, always override)
        user_file = os.path.join(data_dir, "userdefined.json")
        user_config = self.ReadJSONConfig(user_file)

        if user_config:
            self.LogDebug("Loading user-defined entity definitions from userdefined.json")
            self._merge_entity_definitions(
                self._convert_json_entities_to_dict(user_config.get("sensors", [])),
                self.SensorDefinitions,
                override=True,
            )
            self._merge_entity_definitions(
                self._convert_json_entities_to_dict(user_config.get("binary_sensors", [])),
                self.BinarySensorDefinitions,
                override=True,
            )
            self._merge_entity_definitions(
                self._convert_json_entities_to_dict(user_config.get("buttons", [])),
                self.ButtonDefinitions,
                override=True,
            )
            self._merge_entity_definitions(
                self._convert_json_entities_to_dict(user_config.get("switches", [])),
                self.SwitchDefinitions,
                override=True,
            )
            self._merge_entity_definitions(
                self._convert_json_entities_to_dict(user_config.get("selects", [])),
                self.SelectDefinitions,
                override=True,
            )
            self._merge_entity_definitions(
                self._convert_json_entities_to_dict(user_config.get("numbers", [])),
                self.NumberDefinitions,
                override=True,
            )

    # --------------------------------------------------------------------------
    def _use_hardcoded_fallback(self):
        """Fall back to hardcoded definitions if JSON files are missing or invalid."""
        self.LogDebug("Using hardcoded entity definitions as fallback")
        self.SensorDefinitions = SENSOR_DEFINITIONS.copy()
        self.BinarySensorDefinitions = BINARY_SENSOR_DEFINITIONS.copy()
        self.ButtonDefinitions = BUTTON_DEFINITIONS.copy()
        self.SwitchDefinitions = SWITCH_DEFINITIONS.copy()
        self.SelectDefinitions = SELECT_DEFINITIONS.copy()
        self.NumberDefinitions = NUMBER_DEFINITIONS.copy()

    # --------------------------------------------------------------------------
    def _setup_mqtt(self):
        """Initialize MQTT client and connection"""

        self.MQTTclient = mqtt.Client(client_id=self.ClientID)

        if self.Username and self.Password:
            self.MQTTclient.username_pw_set(self.Username, password=self.Password)

        self.MQTTclient.on_connect = self._on_connect
        self.MQTTclient.on_message = self._on_message
        self.MQTTclient.on_disconnect = self._on_disconnect

        # TLS setup
        if self.CertificateAuthorityPath and os.path.isfile(self.CertificateAuthorityPath):
            cert_reqs = ssl.CERT_REQUIRED
            if self.CertReqs.lower() == "none":
                cert_reqs = ssl.CERT_NONE
            elif self.CertReqs.lower() == "optional":
                cert_reqs = ssl.CERT_OPTIONAL

            tls_version = ssl.PROTOCOL_TLSv1_2
            if self.TLSVersion == "1.0":
                tls_version = ssl.PROTOCOL_TLSv1
            elif self.TLSVersion == "1.1":
                tls_version = ssl.PROTOCOL_TLSv1_1

            certfile = self.ClientCertificatePath.strip() or None
            keyfile = self.ClientKeyPath.strip() or None

            self.MQTTclient.tls_set(
                ca_certs=self.CertificateAuthorityPath,
                certfile=certfile,
                keyfile=keyfile,
                cert_reqs=cert_reqs,
                tls_version=tls_version,
            )
            self.MQTTPort = 8883

        # Set Last Will and Testament
        availability_topic = f"{self.BaseTopic}/status"
        self.MQTTclient.will_set(availability_topic, payload="offline", qos=1, retain=True)

        self.LogDebug(f"Connecting to MQTT broker: {self.MQTTAddress}:{self.MQTTPort}")
        self.MQTTclient.connect(self.MQTTAddress, self.MQTTPort, 60)

    # --------------------------------------------------------------------------
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""

        if rc != 0:
            self.LogError(f"Error connecting to MQTT broker, return code: {rc}")
            return

        self.LogInfo(f"Connected to MQTT broker: {self.MQTTAddress}")

        # Reset cleanup state on new connection
        self.ExistingEntities.clear()
        self.PublishedEntities.clear()
        self.CleanupComplete = False

        # Subscribe to discovery topics to find existing entities for cleanup
        # Pattern: {discovery_prefix}/{entity_type}/{device_id}/{entity_id}/config
        discovery_topic = f"{self.DiscoveryPrefix}/+/{self.DeviceId}/+/config"
        self.MQTTclient.subscribe(discovery_topic)
        self.DiscoverySubscribed = True
        self.LogDebug(f"Subscribed to discovery topic for cleanup: {discovery_topic}")

        # Subscribe to HA birth topic to detect HA restarts
        ha_status_topic = f"{self.DiscoveryPrefix}/status"
        self.MQTTclient.subscribe(ha_status_topic)

        # Subscribe to command topics
        command_topic = f"{self.BaseTopic}/+/+/set"
        self.MQTTclient.subscribe(command_topic)
        button_topic = f"{self.BaseTopic}/+/+/command"
        self.MQTTclient.subscribe(button_topic)

        # Publish availability online
        availability_topic = f"{self.BaseTopic}/status"
        self.MQTTclient.publish(availability_topic, payload="online", qos=1, retain=True)

        # Brief delay to allow retained discovery messages to arrive before publishing
        # This allows us to collect existing entities for cleanup comparison
        time.sleep(2)

        # Publish discovery messages (cleanup happens after publishing)
        self._publish_discovery()

    # --------------------------------------------------------------------------
    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""

        self.LogInfo(f"Disconnected from MQTT broker, return code: {rc}")
        self.EntitiesPublished = False
        self.DiscoverySubscribed = False

    # --------------------------------------------------------------------------
    def _on_message(self, client, userdata, message):
        """MQTT message callback for commands"""

        try:
            topic = message.topic
            payload = message.payload.decode("utf-8")

            self.LogDebug(f"Received message: {topic} = {payload}")

            # Handle discovery config messages for cleanup tracking
            # Format: {discovery_prefix}/{entity_type}/{device_id}/{entity_id}/config
            if topic.endswith("/config") and f"/{self.DeviceId}/" in topic:
                parts = topic.split("/")
                if len(parts) >= 5 and parts[-1] == "config":
                    entity_type = parts[-4]
                    entity_id = parts[-2]
                    # Only track if it has a non-empty payload (entity exists)
                    if payload and payload.strip():
                        entity_key = f"{entity_type}/{entity_id}"
                        self.ExistingEntities.add(entity_key)
                        self.LogDebug(f"Found existing entity: {entity_key}")
                return

            # Parse topic to determine entity type and id
            # Format: {base_topic}/{entity_type}/{entity_id}/set or /command
            parts = topic.split("/")
            if len(parts) < 4:
                return

            entity_type = parts[-3]
            entity_id = parts[-2]
            action = parts[-1]

            # Handle Home Assistant status (birth message)
            if topic == f"{self.DiscoveryPrefix}/status" and payload == "online":
                self.LogDebug("Home Assistant restarted, republishing discovery")
                self._publish_discovery()
                return

            # Handle button press
            if action == "command" and entity_type == "button":
                self._handle_button_press(entity_id, payload)
                return

            # Handle switch command
            if action == "set" and entity_type == "switch":
                self._handle_switch_command(entity_id, payload)
                return

            # Handle select command
            if action == "set" and entity_type == "select":
                self._handle_select_command(entity_id, payload)
                return

            # Handle number command
            if action == "set" and entity_type == "number":
                self._handle_number_command(entity_id, payload)
                return

        except Exception as e1:
            self.LogErrorLine(f"Error in _on_message: {str(e1)}")

    # --------------------------------------------------------------------------
    def _handle_button_press(self, entity_id, payload):
        """Handle button press commands"""

        try:
            if entity_id not in self.ButtonDefinitions:
                self.LogError(f"Unknown button entity: {entity_id}")
                return

            button_def = self.ButtonDefinitions[entity_id]
            command = button_def["command"]

            self.LogDebug(f"Executing button command: {command}")
            response = self._send_command(f"generator: {command}")
            self.LogDebug(f"Command response: {response}")

        except Exception as e1:
            self.LogErrorLine(f"Error handling button press: {str(e1)}")

    # --------------------------------------------------------------------------
    def _handle_switch_command(self, entity_id, payload):
        """Handle switch on/off commands"""

        try:
            if entity_id not in self.SwitchDefinitions:
                self.LogError(f"Unknown switch entity: {entity_id}")
                return

            switch_def = self.SwitchDefinitions[entity_id]

            if payload.upper() == "ON":
                command = switch_def["command_on"]
            else:
                command = switch_def["command_off"]

            self.LogDebug(f"Executing switch command: {command}")
            response = self._send_command(f"generator: {command}")
            self.LogDebug(f"Command response: {response}")

            # Publish state update
            state_topic = f"{self.BaseTopic}/switch/{entity_id}/state"
            self.MQTTclient.publish(state_topic, payload.upper(), retain=True)

        except Exception as e1:
            self.LogErrorLine(f"Error handling switch command: {str(e1)}")

    # --------------------------------------------------------------------------
    def _handle_select_command(self, entity_id, payload):
        """Handle select dropdown commands"""

        try:
            if entity_id not in self.SelectDefinitions:
                self.LogError(f"Unknown select entity: {entity_id}")
                return

            select_def = self.SelectDefinitions[entity_id]

            # Validate the selection
            if payload not in select_def["options"]:
                self.LogError(f"Invalid option '{payload}' for {entity_id}")
                return

            # Handle exercise-related selects
            if select_def.get("command_template") == "exercise":
                if entity_id == "exercise_frequency":
                    self.ExerciseSettings["frequency"] = payload
                elif entity_id == "exercise_day_of_week":
                    self.ExerciseSettings["day_of_week"] = payload

                # Send the combined exercise command
                self._send_exercise_command()

            # Publish state update
            state_topic = f"{self.BaseTopic}/select/{entity_id}/state"
            self.MQTTclient.publish(state_topic, payload, retain=True)

        except Exception as e1:
            self.LogErrorLine(f"Error handling select command: {str(e1)}")

    # --------------------------------------------------------------------------
    def _handle_number_command(self, entity_id, payload):
        """Handle number input commands"""

        try:
            if entity_id not in self.NumberDefinitions:
                self.LogError(f"Unknown number entity: {entity_id}")
                return

            number_def = self.NumberDefinitions[entity_id]

            # Parse and validate the number
            try:
                value = int(float(payload))
            except ValueError:
                self.LogError(f"Invalid number '{payload}' for {entity_id}")
                return

            min_val = number_def.get("min", 0)
            max_val = number_def.get("max", 100)
            if value < min_val or value > max_val:
                self.LogError(f"Value {value} out of range [{min_val}, {max_val}] for {entity_id}")
                return

            # Handle exercise-related numbers
            if number_def.get("command_template") == "exercise":
                if entity_id == "exercise_day_of_month":
                    self.ExerciseSettings["day_of_month"] = value
                elif entity_id == "exercise_hour":
                    self.ExerciseSettings["hour"] = value
                elif entity_id == "exercise_minute":
                    self.ExerciseSettings["minute"] = value

                # Send the combined exercise command
                self._send_exercise_command()

            # Publish state update
            state_topic = f"{self.BaseTopic}/number/{entity_id}/state"
            self.MQTTclient.publish(state_topic, str(value), retain=True)

        except Exception as e1:
            self.LogErrorLine(f"Error handling number command: {str(e1)}")

    # --------------------------------------------------------------------------
    def _send_exercise_command(self):
        """Send the combined exercise time command to genmon"""

        try:
            freq = self.ExerciseSettings["frequency"]
            hour = self.ExerciseSettings["hour"]
            minute = self.ExerciseSettings["minute"]
            time_str = f"{hour:02d}:{minute:02d}"

            # Force weekly if enhanced exercise mode not supported
            if not self.EnhancedExerciseMode:
                if freq != "Weekly":
                    self.LogDebug(f"Forcing Weekly mode (enhanced exercise not supported)")
                    freq = "Weekly"
                    self.ExerciseSettings["frequency"] = "Weekly"

            if freq == "Monthly":
                day = self.ExerciseSettings["day_of_month"]
                command = f"setexercise={day},{time_str},{freq}"
            else:
                # Weekly or BiWeekly
                day = self.ExerciseSettings["day_of_week"]
                command = f"setexercise={day},{time_str},{freq}"

            self.LogDebug(f"Sending exercise command: {command}")
            response = self._send_command(f"generator: {command}")
            self.LogDebug(f"Exercise command response: {response}")

        except Exception as e1:
            self.LogErrorLine(f"Error sending exercise command: {str(e1)}")

    # --------------------------------------------------------------------------
    def _parse_exercise_time(self, exercise_str):
        """Parse exercise time string from genmon and update settings.

        Examples:
        - "Weekly Sunday 16:00 Quiet Mode Off"
        - "BiWeekly Monday 13:30 Quiet Mode On"
        - "Monthly Day 15 09:00 Quiet Mode Off"
        """
        try:
            if not exercise_str:
                return

            parts = exercise_str.split()
            if len(parts) < 3:
                return

            # Parse frequency (first word)
            freq = parts[0]
            if freq in ["Weekly", "BiWeekly", "Monthly"]:
                self.ExerciseSettings["frequency"] = freq

            if freq == "Monthly":
                # Format: "Monthly Day 15 09:00 ..."
                if len(parts) >= 4 and parts[1] == "Day":
                    try:
                        self.ExerciseSettings["day_of_month"] = int(parts[2])
                    except ValueError:
                        pass
                    time_part = parts[3]
                else:
                    # Try alternate format
                    time_part = parts[2] if len(parts) > 2 else "12:00"
            else:
                # Format: "Weekly Sunday 16:00 ..."
                day_of_week = parts[1]
                if day_of_week in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
                    self.ExerciseSettings["day_of_week"] = day_of_week
                time_part = parts[2] if len(parts) > 2 else "12:00"

            # Parse time (HH:MM)
            if ":" in time_part:
                time_parts = time_part.split(":")
                try:
                    self.ExerciseSettings["hour"] = int(time_parts[0])
                    self.ExerciseSettings["minute"] = int(time_parts[1])
                except (ValueError, IndexError):
                    pass

            # Only log if values changed (reduce verbosity)
            # The state publish will handle actual updates

        except Exception as e1:
            self.LogDebug(f"Error parsing exercise time '{exercise_str}': {str(e1)}")

    # --------------------------------------------------------------------------
    def _publish_exercise_states(self):
        """Publish current exercise settings to MQTT"""
        try:
            # Publish select states (only if enhanced mode is supported)
            if self.EnhancedExerciseMode:
                self.MQTTclient.publish(
                    f"{self.BaseTopic}/select/exercise_frequency/state",
                    self.ExerciseSettings["frequency"], retain=True
                )

            # Day of week is always published
            self.MQTTclient.publish(
                f"{self.BaseTopic}/select/exercise_day_of_week/state",
                self.ExerciseSettings["day_of_week"], retain=True
            )

            # Publish number states (day_of_month only if enhanced mode is supported)
            if self.EnhancedExerciseMode:
                self.MQTTclient.publish(
                    f"{self.BaseTopic}/number/exercise_day_of_month/state",
                    str(self.ExerciseSettings["day_of_month"]), retain=True
                )

            # Hour and minute are always published
            self.MQTTclient.publish(
                f"{self.BaseTopic}/number/exercise_hour/state",
                str(self.ExerciseSettings["hour"]), retain=True
            )
            self.MQTTclient.publish(
                f"{self.BaseTopic}/number/exercise_minute/state",
                str(self.ExerciseSettings["minute"]), retain=True
            )
        except Exception as e1:
            self.LogDebug(f"Error publishing exercise states: {str(e1)}")

    # --------------------------------------------------------------------------
    def _send_command(self, command):
        """Send command to genmon"""

        try:
            with self.AccessLock:
                return self.Generator.ProcessMonitorCommand(command)
        except Exception as e1:
            self.LogErrorLine(f"Error sending command: {str(e1)}")
            return ""

    # --------------------------------------------------------------------------
    def _entity_allowed(self, entity_def, entity_id):
        """Check if entity should be created based on filters"""

        # Check blacklist
        name = entity_def.get("name", entity_id).lower()
        for bl_item in self.BlackList:
            if bl_item in name or bl_item in entity_id:
                return False

        # Check controller-specific entities
        if "controllers" in entity_def:
            if self.ControllerType not in entity_def["controllers"]:
                return False

        # Check monitor stats filter
        if entity_def.get("monitor_stats") and not self.IncludeMonitorStats:
            return False

        # Check weather filter
        if entity_def.get("weather") and not self.IncludeWeather:
            return False

        return True

    # --------------------------------------------------------------------------
    def _publish_discovery(self):
        """Publish all discovery messages to Home Assistant"""

        try:
            self.LogDebug("Publishing Home Assistant discovery messages")

            # Get current genmon data to check which sensors have actual values
            try:
                status_data = json.loads(self._send_command("generator: status_num_json"))
                maint_data = json.loads(self._send_command("generator: maint_num_json"))
                outage_data = json.loads(self._send_command("generator: outage_num_json"))
                monitor_data = json.loads(self._send_command("generator: monitor_num_json"))
                gui_data = json.loads(self._send_command("generator: gui_status_json"))
                genmon_data = {**status_data, **maint_data, **outage_data, **monitor_data}
                # Add tiles from gui_status_json
                tiles = gui_data.get("tiles", [])
                tiles_dict = {}
                for tile in tiles:
                    title = tile.get("title", "")
                    if title:
                        tiles_dict[title] = tile
                genmon_data["Tiles"] = tiles_dict
            except Exception as e:
                self.LogError(f"Could not get genmon data for discovery check: {e}")
                genmon_data = {}

            # Publish sensor discoveries (predefined) - only if data exists
            sensors_published = 0
            sensors_skipped = 0
            for entity_id, entity_def in self.SensorDefinitions.items():
                if self._entity_allowed(entity_def, entity_id):
                    # Check if this sensor has actual data from genmon
                    if "path" in entity_def and genmon_data:
                        value = self._get_value_from_path(genmon_data, entity_def["path"])
                        if value is None:
                            sensors_skipped += 1
                            continue  # Skip sensors with no data
                    self._publish_sensor_discovery(entity_id, entity_def)
                    sensors_published += 1

            if sensors_skipped > 0:
                self.LogDebug(f"Skipped {sensors_skipped} sensors with no data")

            # Publish dynamic sensor discoveries
            for entity_id, entity_def in self.DynamicSensors.items():
                self._publish_sensor_discovery(entity_id, entity_def)

            # Publish binary sensor discoveries - only if data exists (except payload_on_not_empty)
            binary_sensors_skipped = 0
            for entity_id, entity_def in self.BinarySensorDefinitions.items():
                if self._entity_allowed(entity_def, entity_id):
                    # Check if this binary sensor has actual data from genmon
                    # Skip sensors that reference data that doesn't exist on this controller
                    # Exception: payload_on_not_empty sensors are valid even with no data (they'll show OFF)
                    if "path" in entity_def and genmon_data and not entity_def.get("payload_on_not_empty"):
                        value = self._get_value_from_path(genmon_data, entity_def["path"])
                        if value is None:
                            binary_sensors_skipped += 1
                            continue  # Skip binary sensors with no data
                    self._publish_binary_sensor_discovery(entity_id, entity_def)
            if binary_sensors_skipped > 0:
                self.LogDebug(f"Skipped {binary_sensors_skipped} binary sensors with no data")

            # Publish button discoveries
            for entity_id, entity_def in self.ButtonDefinitions.items():
                if self._entity_allowed(entity_def, entity_id):
                    self._publish_button_discovery(entity_id, entity_def)

            # Publish switch discoveries
            for entity_id, entity_def in self.SwitchDefinitions.items():
                if self._entity_allowed(entity_def, entity_id):
                    self._publish_switch_discovery(entity_id, entity_def)

            # Publish select discoveries
            for entity_id, entity_def in self.SelectDefinitions.items():
                if self._entity_allowed(entity_def, entity_id):
                    self._publish_select_discovery(entity_id, entity_def)

            # Publish number discoveries
            for entity_id, entity_def in self.NumberDefinitions.items():
                if self._entity_allowed(entity_def, entity_id):
                    self._publish_number_discovery(entity_id, entity_def)

            self.EntitiesPublished = True
            self.LastDiscoveryTime = time.time()
            self.LogDebug(f"Discovery messages published ({sensors_published} predefined + {len(self.DynamicSensors)} dynamic sensors, {sensors_skipped} skipped)")

            # Clean up stale entities (only on first publish after connect)
            if not self.CleanupComplete:
                self._cleanup_stale_entities()

        except Exception as e1:
            self.LogErrorLine(f"Error publishing discovery: {str(e1)}")

    # --------------------------------------------------------------------------
    def _cleanup_stale_entities(self):
        """Remove entities that exist in MQTT but are no longer defined.

        This handles cleanup when entity IDs change between versions.
        Compares existing entities (found via MQTT subscription) against
        entities we just published, and removes any stale ones.
        """
        try:
            if not self.ExistingEntities:
                self.LogDebug("No existing entities found, skipping cleanup")
                self.CleanupComplete = True
                return

            # Build set of entities we just published
            # Track by "entity_type/entity_id" format
            for entity_id in self.SensorDefinitions:
                self.PublishedEntities.add(f"sensor/{entity_id}")
            for entity_id in self.DynamicSensors:
                self.PublishedEntities.add(f"sensor/{entity_id}")
            for entity_id in self.BinarySensorDefinitions:
                self.PublishedEntities.add(f"binary_sensor/{entity_id}")
            for entity_id in self.ButtonDefinitions:
                self.PublishedEntities.add(f"button/{entity_id}")
            for entity_id in self.SwitchDefinitions:
                self.PublishedEntities.add(f"switch/{entity_id}")
            for entity_id in self.SelectDefinitions:
                self.PublishedEntities.add(f"select/{entity_id}")
            for entity_id in self.NumberDefinitions:
                self.PublishedEntities.add(f"number/{entity_id}")

            # Find stale entities (exist in MQTT but not in current definitions)
            stale_entities = self.ExistingEntities - self.PublishedEntities

            if not stale_entities:
                self.LogDebug("No stale entities to clean up")
                self.CleanupComplete = True
                return

            self.LogInfo(f"Cleaning up {len(stale_entities)} stale entities")

            for entity_key in stale_entities:
                try:
                    # entity_key format: "entity_type/entity_id"
                    entity_type, entity_id = entity_key.split("/", 1)
                    discovery_topic = f"{self.DiscoveryPrefix}/{entity_type}/{self.DeviceId}/{entity_id}/config"

                    # Publish empty payload to remove entity from Home Assistant
                    self.MQTTclient.publish(discovery_topic, "", retain=True)
                    self.LogInfo(f"Removed stale entity: {entity_key}")
                except Exception as e:
                    self.LogError(f"Error removing stale entity {entity_key}: {e}")

            self.CleanupComplete = True
            self.LogDebug("Stale entity cleanup complete")

        except Exception as e1:
            self.LogErrorLine(f"Error in stale entity cleanup: {str(e1)}")
            self.CleanupComplete = True  # Mark complete to avoid repeated attempts

    # --------------------------------------------------------------------------
    def _publish_sensor_discovery(self, entity_id, entity_def):
        """Publish discovery message for a sensor entity"""

        try:
            unique_id = f"genmon_{self.DeviceId}_{entity_id}"
            discovery_topic = f"{self.DiscoveryPrefix}/sensor/{self.DeviceId}/{entity_id}/config"
            state_topic = f"{self.BaseTopic}/sensor/{entity_id}/state"

            payload = {
                "name": entity_def["name"],
                "unique_id": unique_id,
                "state_topic": state_topic,
                "availability_topic": f"{self.BaseTopic}/status",
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": self.DeviceInfo,
            }

            if entity_def.get("device_class"):
                payload["device_class"] = entity_def["device_class"]

            # Handle unit of measurement, with special handling for temperature sensors
            unit = entity_def.get("unit")
            if unit:
                payload["unit_of_measurement"] = unit
            elif entity_def.get("device_class") == "temperature":
                # Temperature sensors require a unit - set based on metric setting
                payload["unit_of_measurement"] = "°C" if self.UseMetric else "°F"
            if entity_def.get("icon"):
                payload["icon"] = entity_def["icon"]
            if entity_def.get("state_class"):
                payload["state_class"] = entity_def["state_class"]
            if entity_def.get("category"):
                payload["entity_category"] = entity_def["category"]
            if entity_def.get("enabled_default") is False:
                payload["enabled_by_default"] = False

            self.MQTTclient.publish(discovery_topic, json.dumps(payload), retain=True)
            self.LogDebug(f"Published sensor discovery: {entity_id}")

        except Exception as e1:
            self.LogErrorLine(f"Error publishing sensor discovery {entity_id}: {str(e1)}")

    # --------------------------------------------------------------------------
    def _publish_binary_sensor_discovery(self, entity_id, entity_def):
        """Publish discovery message for a binary sensor entity"""

        try:
            unique_id = f"genmon_{self.DeviceId}_{entity_id}"
            discovery_topic = f"{self.DiscoveryPrefix}/binary_sensor/{self.DeviceId}/{entity_id}/config"
            state_topic = f"{self.BaseTopic}/binary_sensor/{entity_id}/state"

            payload = {
                "name": entity_def["name"],
                "unique_id": unique_id,
                "state_topic": state_topic,
                "availability_topic": f"{self.BaseTopic}/status",
                "payload_available": "online",
                "payload_not_available": "offline",
                "payload_on": "ON",
                "payload_off": "OFF",
                "device": self.DeviceInfo,
            }

            if entity_def.get("device_class"):
                payload["device_class"] = entity_def["device_class"]
            if entity_def.get("icon"):
                payload["icon"] = entity_def["icon"]
            if entity_def.get("category"):
                payload["entity_category"] = entity_def["category"]

            self.MQTTclient.publish(discovery_topic, json.dumps(payload), retain=True)
            self.LogDebug(f"Published binary sensor discovery: {entity_id}")

        except Exception as e1:
            self.LogErrorLine(f"Error publishing binary sensor discovery {entity_id}: {str(e1)}")

    # --------------------------------------------------------------------------
    def _publish_button_discovery(self, entity_id, entity_def):
        """Publish discovery message for a button entity"""

        try:
            # Check if button is supported by this controller
            if entity_id in ["start", "stop"] and not self.RemoteCommands:
                # Publish empty payload to remove entity from Home Assistant
                discovery_topic = f"{self.DiscoveryPrefix}/button/{self.DeviceId}/{entity_id}/config"
                self.MQTTclient.publish(discovery_topic, "", retain=True)
                self.LogDebug(f"Removed {entity_id}: RemoteCommands not supported on this controller")
                return
            if entity_id == "start_exercise" and not self.ExerciseControls:
                # Publish empty payload to remove entity from Home Assistant
                discovery_topic = f"{self.DiscoveryPrefix}/button/{self.DeviceId}/{entity_id}/config"
                self.MQTTclient.publish(discovery_topic, "", retain=True)
                self.LogDebug(f"Removed {entity_id}: ExerciseControls not supported on this controller")
                return

            unique_id = f"genmon_{self.DeviceId}_{entity_id}"
            discovery_topic = f"{self.DiscoveryPrefix}/button/{self.DeviceId}/{entity_id}/config"
            command_topic = f"{self.BaseTopic}/button/{entity_id}/command"

            payload = {
                "name": entity_def["name"],
                "unique_id": unique_id,
                "command_topic": command_topic,
                "availability_topic": f"{self.BaseTopic}/status",
                "payload_available": "online",
                "payload_not_available": "offline",
                "payload_press": "PRESS",
                "device": self.DeviceInfo,
            }

            if entity_def.get("icon"):
                payload["icon"] = entity_def["icon"]

            self.MQTTclient.publish(discovery_topic, json.dumps(payload), retain=True)
            self.LogDebug(f"Published button discovery: {entity_id}")

        except Exception as e1:
            self.LogErrorLine(f"Error publishing button discovery {entity_id}: {str(e1)}")

    # --------------------------------------------------------------------------
    def _publish_switch_discovery(self, entity_id, entity_def):
        """Publish discovery message for a switch entity"""

        try:
            # Check if switch is supported by this controller
            if entity_id == "quiet_mode" and not self.WriteQuietMode:
                # Publish empty payload to remove entity from Home Assistant
                discovery_topic = f"{self.DiscoveryPrefix}/switch/{self.DeviceId}/{entity_id}/config"
                self.MQTTclient.publish(discovery_topic, "", retain=True)
                self.LogDebug(f"Removed {entity_id}: WriteQuietMode not supported on this controller")
                return

            unique_id = f"genmon_{self.DeviceId}_{entity_id}"
            discovery_topic = f"{self.DiscoveryPrefix}/switch/{self.DeviceId}/{entity_id}/config"
            state_topic = f"{self.BaseTopic}/switch/{entity_id}/state"
            command_topic = f"{self.BaseTopic}/switch/{entity_id}/set"

            payload = {
                "name": entity_def["name"],
                "unique_id": unique_id,
                "state_topic": state_topic,
                "command_topic": command_topic,
                "availability_topic": f"{self.BaseTopic}/status",
                "payload_available": "online",
                "payload_not_available": "offline",
                "payload_on": "ON",
                "payload_off": "OFF",
                "device": self.DeviceInfo,
            }

            if entity_def.get("icon"):
                payload["icon"] = entity_def["icon"]

            self.MQTTclient.publish(discovery_topic, json.dumps(payload), retain=True)
            self.LogDebug(f"Published switch discovery: {entity_id}")

        except Exception as e1:
            self.LogErrorLine(f"Error publishing switch discovery {entity_id}: {str(e1)}")

    # --------------------------------------------------------------------------
    def _publish_select_discovery(self, entity_id, entity_def):
        """Publish discovery message for a select entity"""

        try:
            discovery_topic = f"{self.DiscoveryPrefix}/select/{self.DeviceId}/{entity_id}/config"

            # Remove exercise-related entities if exercise controls not supported
            if entity_id.startswith("exercise_") and not self.ExerciseControls:
                self.MQTTclient.publish(discovery_topic, "", retain=True)
                self.LogDebug(f"Removed {entity_id}: ExerciseControls not supported")
                return
            # Remove exercise_frequency if enhanced mode not supported (only weekly available)
            if entity_id == "exercise_frequency" and not self.EnhancedExerciseMode:
                self.MQTTclient.publish(discovery_topic, "", retain=True)
                self.LogDebug(f"Removed {entity_id}: Enhanced exercise mode not supported")
                return

            unique_id = f"genmon_{self.DeviceId}_{entity_id}"
            state_topic = f"{self.BaseTopic}/select/{entity_id}/state"
            command_topic = f"{self.BaseTopic}/select/{entity_id}/set"

            # Get options - may be modified based on capabilities
            options = entity_def["options"]

            payload = {
                "name": entity_def["name"],
                "unique_id": unique_id,
                "state_topic": state_topic,
                "command_topic": command_topic,
                "availability_topic": f"{self.BaseTopic}/status",
                "payload_available": "online",
                "payload_not_available": "offline",
                "options": options,
                "device": self.DeviceInfo,
            }

            if entity_def.get("icon"):
                payload["icon"] = entity_def["icon"]

            self.MQTTclient.publish(discovery_topic, json.dumps(payload), retain=True)
            self.LogDebug(f"Published select discovery: {entity_id}")

        except Exception as e1:
            self.LogErrorLine(f"Error publishing select discovery {entity_id}: {str(e1)}")

    # --------------------------------------------------------------------------
    def _publish_number_discovery(self, entity_id, entity_def):
        """Publish discovery message for a number entity"""

        try:
            discovery_topic = f"{self.DiscoveryPrefix}/number/{self.DeviceId}/{entity_id}/config"

            # Remove exercise-related entities if exercise controls not supported
            if entity_id.startswith("exercise_") and not self.ExerciseControls:
                self.MQTTclient.publish(discovery_topic, "", retain=True)
                self.LogDebug(f"Removed {entity_id}: ExerciseControls not supported")
                return
            # Remove day_of_month if enhanced mode not supported (monthly not available)
            if entity_id == "exercise_day_of_month" and not self.EnhancedExerciseMode:
                self.MQTTclient.publish(discovery_topic, "", retain=True)
                self.LogDebug(f"Removed {entity_id}: Enhanced exercise mode not supported")
                return

            unique_id = f"genmon_{self.DeviceId}_{entity_id}"
            state_topic = f"{self.BaseTopic}/number/{entity_id}/state"
            command_topic = f"{self.BaseTopic}/number/{entity_id}/set"

            payload = {
                "name": entity_def["name"],
                "unique_id": unique_id,
                "state_topic": state_topic,
                "command_topic": command_topic,
                "availability_topic": f"{self.BaseTopic}/status",
                "payload_available": "online",
                "payload_not_available": "offline",
                "min": entity_def.get("min", 0),
                "max": entity_def.get("max", 100),
                "step": entity_def.get("step", 1),
                "mode": "box",  # Use input box instead of slider
                "device": self.DeviceInfo,
            }

            if entity_def.get("icon"):
                payload["icon"] = entity_def["icon"]
            if entity_def.get("unit"):
                payload["unit_of_measurement"] = entity_def["unit"]

            self.MQTTclient.publish(discovery_topic, json.dumps(payload), retain=True)
            self.LogDebug(f"Published number discovery: {entity_id}")

        except Exception as e1:
            self.LogErrorLine(f"Error publishing number discovery {entity_id}: {str(e1)}")

    # --------------------------------------------------------------------------
    def _polling_thread(self):
        """Main polling thread to get data from genmon and publish states"""

        self.LogDebug("Polling thread started")

        while True:
            try:
                if self.WaitForExit("PollingThread", float(self.PollTime)):
                    self.LogDebug("Polling thread exiting (WaitForExit returned True)")
                    return

                # Get all data from genmon
                if self.UseNumeric:
                    status_data = self._send_command("generator: status_num_json")
                    maint_data = self._send_command("generator: maint_num_json")
                    outage_data = self._send_command("generator: outage_num_json")
                    monitor_data = self._send_command("generator: monitor_num_json")
                    gui_data = self._send_command("generator: gui_status_json")
                else:
                    status_data = self._send_command("generator: status_json")
                    maint_data = self._send_command("generator: maint_json")
                    outage_data = self._send_command("generator: outage_json")
                    monitor_data = self._send_command("generator: monitor_json")
                    gui_data = self._send_command("generator: gui_status_json")

                # Parse JSON responses
                try:
                    genmon_data = {}
                    if status_data:
                        temp = json.loads(status_data)
                        genmon_data["Status"] = temp.get("Status", {})
                    if maint_data:
                        temp = json.loads(maint_data)
                        genmon_data["Maintenance"] = temp.get("Maintenance", {})
                    if outage_data:
                        temp = json.loads(outage_data)
                        genmon_data["Outage"] = temp.get("Outage", {})
                    if monitor_data:
                        temp = json.loads(monitor_data)
                        genmon_data["Monitor"] = temp.get("Monitor", {})
                    if gui_data:
                        temp = json.loads(gui_data)
                        # Extract tiles as a dict keyed by title for easy lookup
                        tiles = temp.get("tiles", [])
                        tiles_dict = {}
                        for tile in tiles:
                            title = tile.get("title", "")
                            if title:
                                tiles_dict[title] = tile
                        genmon_data["Tiles"] = tiles_dict

                    # Process and publish states
                    self._process_data(genmon_data)

                except json.JSONDecodeError as e1:
                    self.LogErrorLine(f"Error parsing JSON: {str(e1)}")

            except Exception as e1:
                self.LogErrorLine(f"Error in polling thread: {str(e1)}")

    # --------------------------------------------------------------------------
    def _discovery_thread(self):
        """Thread to periodically republish discovery messages"""

        while True:
            try:
                if self.WaitForExit("DiscoveryThread", float(self.DiscoveryInterval)):
                    return

                if self.EntitiesPublished:
                    self.LogDebug("Republishing discovery messages (periodic)")
                    self._publish_discovery()

            except Exception as e1:
                self.LogErrorLine(f"Error in discovery thread: {str(e1)}")

    # --------------------------------------------------------------------------
    def _process_data(self, genmon_data):
        """Process genmon data and publish state updates"""

        # Track counts for consolidated logging
        stats = {
            "predefined_changed": 0,
            "predefined_total": 0,
            "dynamic_changed": 0,
            "dynamic_total": 0,
            "binary_changed": 0,
            "switch_changed": 0,
            "new_discoveries": 0,
        }

        # Discover dynamic sensors on each poll (to catch new data)
        new_dynamic = self._discover_dynamic_sensors(genmon_data)
        if new_dynamic:
            for entity_id, entity_def in new_dynamic.items():
                if entity_id not in self.DynamicSensors:
                    self.DynamicSensors[entity_id] = entity_def
                    stats["new_discoveries"] += 1
                    self._publish_sensor_discovery(entity_id, entity_def)

        # Process predefined sensors
        for entity_id, entity_def in self.SensorDefinitions.items():
            if not self._entity_allowed(entity_def, entity_id):
                continue
            try:
                value = self._get_value_from_path(genmon_data, entity_def["path"])
                if value is not None:
                    processed_value = self._process_sensor_value(value, entity_def)
                    if processed_value is not None:
                        stats["predefined_total"] += 1
                        if self._publish_state("sensor", entity_id, str(processed_value)):
                            stats["predefined_changed"] += 1
            except Exception as e1:
                if self.debug:
                    self.LogDebug(f"Error processing sensor {entity_id}: {str(e1)}")

        # Process dynamic sensors
        for entity_id, entity_def in self.DynamicSensors.items():
            try:
                value = self._get_value_from_path(genmon_data, entity_def["path"])
                if value is not None:
                    processed_value = self._process_sensor_value(value, entity_def)
                    if processed_value is not None:
                        stats["dynamic_total"] += 1
                        if self._publish_state("sensor", entity_id, str(processed_value)):
                            stats["dynamic_changed"] += 1
            except Exception as e1:
                if self.debug:
                    self.LogDebug(f"Error processing dynamic sensor {entity_id}: {str(e1)}")

        # Process binary sensors
        for entity_id, entity_def in self.BinarySensorDefinitions.items():
            if not self._entity_allowed(entity_def, entity_id):
                continue
            try:
                value = self._get_value_from_path(genmon_data, entity_def["path"])
                # For binary sensors with payload_on_not_empty, treat None/missing as OFF
                # This prevents "Unknown" state in Home Assistant when no alarm is present
                if value is not None:
                    binary_value = self._process_binary_value(value, entity_def)
                    if self._publish_state("binary_sensor", entity_id, binary_value):
                        stats["binary_changed"] += 1
                elif entity_def.get("payload_on_not_empty"):
                    # Value is None/missing - for "not empty" sensors, this means OFF
                    if self._publish_state("binary_sensor", entity_id, "OFF"):
                        stats["binary_changed"] += 1
            except Exception as e1:
                if self.debug:
                    self.LogDebug(f"Error processing binary sensor {entity_id}: {str(e1)}")

        # Process switches (state only)
        for entity_id, entity_def in self.SwitchDefinitions.items():
            if not self._entity_allowed(entity_def, entity_id):
                continue
            try:
                if "state_path" in entity_def:
                    value = self._get_value_from_path(genmon_data, entity_def["state_path"])
                    if value is not None:
                        switch_value = "ON" if str(value).lower() == entity_def.get("payload_on", "on").lower() else "OFF"
                        if self._publish_state("switch", entity_id, switch_value):
                            stats["switch_changed"] += 1
            except Exception as e1:
                if self.debug:
                    self.LogDebug(f"Error processing switch {entity_id}: {str(e1)}")

        # Update exercise settings from genmon data
        try:
            exercise_value = self._get_value_from_path(genmon_data, "Maintenance/Exercise/Exercise Time")
            if exercise_value is not None:
                if isinstance(exercise_value, dict):
                    exercise_value = exercise_value.get("value", "")
                exercise_str = str(exercise_value).strip()
                if exercise_str and exercise_str.lower() not in ["unknown", "n/a", "none", "--"]:
                    self._parse_exercise_time(exercise_str)
                    self._publish_exercise_states()
                else:
                    self.LogDebug(f"Exercise time value invalid or empty: '{exercise_str}'")
            else:
                self.LogDebug("Exercise time value not found in genmon data")
        except Exception as e1:
            self.LogErrorLine(f"Error processing exercise settings: {str(e1)}")

        # Consolidated logging - only log if something changed or new discoveries
        total_changed = stats["predefined_changed"] + stats["dynamic_changed"] + stats["binary_changed"] + stats["switch_changed"]
        if total_changed > 0 or stats["new_discoveries"] > 0:
            parts = []
            if stats["predefined_changed"] > 0:
                parts.append(f"{stats['predefined_changed']} sensors")
            if stats["dynamic_changed"] > 0:
                parts.append(f"{stats['dynamic_changed']} dynamic")
            if stats["binary_changed"] > 0:
                parts.append(f"{stats['binary_changed']} binary")
            if stats["switch_changed"] > 0:
                parts.append(f"{stats['switch_changed']} switches")
            if stats["new_discoveries"] > 0:
                parts.append(f"{stats['new_discoveries']} new discoveries")
            self.LogDebug(f"Updated: {', '.join(parts)}")

    # --------------------------------------------------------------------------
    def _get_value_from_path(self, data, path):
        """Extract value from genmon's list-of-dicts JSON structure.

        Genmon returns data like:
        {"Status": [{"Engine": [{"Battery Voltage": {"value": 12.5}}, ...]}, ...]}

        Path format: 'Status/Engine/Battery Voltage'
        """

        try:
            parts = path.split("/")
            current = data

            for part in parts:
                if current is None:
                    return None

                if isinstance(current, dict):
                    # Direct dict lookup (for top level like Status, Maintenance)
                    if part in current:
                        current = current[part]
                    else:
                        # Case-insensitive match
                        found = False
                        for key in current.keys():
                            if key.lower() == part.lower():
                                current = current[key]
                                found = True
                                break
                        if not found:
                            return None

                elif isinstance(current, list):
                    # Search list of single-key dicts for matching key first
                    # This handles structures like [{"0": [...]}, {"1": [...]}]
                    found = False
                    for item in current:
                        if isinstance(item, dict):
                            # Each item is like {"Engine": [...]} or {"0": [...]}
                            if part in item:
                                current = item[part]
                                found = True
                                break
                            # Case-insensitive match
                            for key in item.keys():
                                if key.lower() == part.lower():
                                    current = item[key]
                                    found = True
                                    break
                            if found:
                                break
                    # If not found as dict key and part is numeric, try as list index
                    if not found and part.isdigit():
                        idx = int(part)
                        if idx < len(current):
                            current = current[idx]
                            found = True
                    if not found:
                        return None
                else:
                    return None

            return current
        except Exception as e:
            self.LogDebug(f"Error in path lookup '{path}': {str(e)}")
            return None

    # --------------------------------------------------------------------------
    def _process_sensor_value(self, value, entity_def):
        """Process sensor value - extract numeric if needed"""

        try:
            # If it's already a number, return it
            if isinstance(value, (int, float)):
                return value

            # Handle dict from numeric_json_object format
            if isinstance(value, dict):
                if "value" in value:
                    value = value["value"]
                    # If inner value is already a number, return it
                    if isinstance(value, (int, float)):
                        return value
                else:
                    return None

            # Convert string value
            value_str = str(value).strip()

            # Handle empty or unknown
            if not value_str or value_str.lower() in ["unknown", "n/a", "none", "--"]:
                return None

            # Detect date/time patterns and preserve them as-is
            # Matches: MM-DD-YYYY, YYYY-MM-DD, MM/DD/YYYY, dates with times, etc.
            date_patterns = [
                r'^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}',  # MM-DD-YYYY or MM/DD/YYYY
                r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}',     # YYYY-MM-DD
                r'^\w+day\s+\w+\s+\d',               # "Thursday December 4..."
                r'^\d{1,2}:\d{2}',                   # HH:MM time
                r'\d{1,2}:\d{2}:\d{2}',              # Contains HH:MM:SS
            ]
            for pattern in date_patterns:
                if re.search(pattern, value_str, re.IGNORECASE):
                    return value_str  # Return date/time strings as-is

            # For non-numeric sensors (states), return as-is
            if entity_def.get("state_class") is None and entity_def.get("device_class") is None:
                return value_str

            # Try to extract numeric value
            match = re.search(r'([+-]?[0-9]*\.?[0-9]+)', value_str)
            if match:
                num_value = float(match.group(1))
                # Convert to int if whole number
                if num_value == int(num_value):
                    return int(num_value)
                return round(num_value, 2)

            # Return original for text values
            return value_str

        except Exception as e1:
            self.LogDebug(f"Error processing sensor value: {str(e1)}")
            return None

    # --------------------------------------------------------------------------
    def _is_genmon_entity(self, data):
        """Check if a dict represents a genmon entity with type/value/unit structure.

        Genmon numeric JSON returns entities like:
        {"type": "float", "value": 13.5, "unit": "V"}
        or just {"value": "some text"}
        """
        if not isinstance(data, dict):
            return False
        # Must have 'value' key to be considered an entity
        if "value" not in data:
            return False
        # Check if keys are only the expected entity characteristics
        valid_keys = {"type", "value", "unit"}
        return all(k in valid_keys for k in data.keys())

    # --------------------------------------------------------------------------
    def _walk_genmon_data(self, data, path=""):
        """Recursively walk genmon data and yield all (path, entity_data) pairs.

        Handles genmon's list-of-dicts JSON structure.
        When an entity with type/value/unit is found, yields the whole dict.
        """
        if isinstance(data, dict):
            # Check if this dict IS an entity (has type/value/unit structure)
            if self._is_genmon_entity(data):
                if path:
                    yield (path, data)
                return

            # Otherwise, walk into the dict
            for key, value in data.items():
                new_path = f"{path}/{key}" if path else key
                if isinstance(value, (dict, list)):
                    yield from self._walk_genmon_data(value, new_path)
                else:
                    # Plain value (not in type/value/unit structure)
                    yield (new_path, value)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield from self._walk_genmon_data(item, path)

    # --------------------------------------------------------------------------
    def _path_to_entity_id(self, path):
        """Convert a path like 'Status/Engine/Battery Voltage' to 'status_engine_battery_voltage'"""
        # Remove leading slash if present
        path = path.lstrip("/")
        # Replace slashes and spaces with underscores, lowercase
        entity_id = re.sub(r'[/\s]+', '_', path).lower()
        # Remove special characters except underscores
        entity_id = re.sub(r'[^a-z0-9_]', '', entity_id)
        # Remove duplicate underscores
        entity_id = re.sub(r'_+', '_', entity_id)
        # Remove leading/trailing underscores
        entity_id = entity_id.strip('_')
        return entity_id

    # --------------------------------------------------------------------------
    def _extract_unit_from_value(self, value_str):
        """Try to extract unit from a value string like '245 V' or '60 Hz'"""
        if not isinstance(value_str, str):
            return None

        # Common unit patterns
        unit_patterns = [
            (r'[\d.]+\s*(V|Volts?)$', 'V'),
            (r'[\d.]+\s*(A|Amps?)$', 'A'),
            (r'[\d.]+\s*(W|Watts?)$', 'W'),
            (r'[\d.]+\s*(kW|Kilowatts?)$', 'kW'),
            (r'[\d.]+\s*(kWh)$', 'kWh'),
            (r'[\d.]+\s*(Hz|Hertz)$', 'Hz'),
            (r'[\d.]+\s*(RPM)$', 'RPM'),
            (r'[\d.]+\s*(%|percent)$', '%'),
            (r'[\d.]+\s*(°?[CF])$', None),  # Temperature - let HA figure it out
            (r'[\d.]+\s*(h|hrs?|hours?)$', 'h'),
            (r'[\d.]+\s*(s|sec|seconds?)$', 's'),
            (r'[\d.]+\s*(gal|gallons?)$', 'gal'),
            (r'[\d.]+\s*(L|liters?)$', 'L'),
            (r'[\d.]+\s*(psi|PSI)$', 'psi'),
            (r'[\d.]+\s*(cc)$', 'cc'),
        ]

        for pattern, unit in unit_patterns:
            if re.search(pattern, value_str, re.IGNORECASE):
                return unit
        return None

    # --------------------------------------------------------------------------
    def _is_numeric_value(self, value):
        """Check if a value is or contains a numeric value (not date/time)"""
        if isinstance(value, (int, float)):
            return True
        if isinstance(value, dict) and "value" in value:
            return isinstance(value["value"], (int, float))
        if isinstance(value, str):
            value_str = str(value).strip()
            # Exclude date/time patterns from being considered numeric
            date_patterns = [
                r'^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}',  # MM-DD-YYYY or MM/DD/YYYY
                r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}',     # YYYY-MM-DD
                r'^\w+day\s+\w+\s+\d',               # "Thursday December 4..."
                r'^\d{1,2}:\d{2}',                   # HH:MM time
                r'\d{1,2}:\d{2}:\d{2}',              # Contains HH:MM:SS
            ]
            for pattern in date_patterns:
                if re.search(pattern, value_str, re.IGNORECASE):
                    return False  # Date/time strings are not numeric
            # Check if we can extract a number
            match = re.search(r'([+-]?[0-9]*\.?[0-9]+)', value_str)
            return match is not None
        return False

    # --------------------------------------------------------------------------
    def _generate_dynamic_sensor_config(self, path, entity_data):
        """Generate a sensor configuration for dynamically discovered data.

        entity_data can be:
        - A dict with type/value/unit structure from genmon numeric JSON
        - A plain value (string, number) from non-numeric JSON
        """

        # Build a descriptive name from the path
        name_parts = path.split("/")

        # Special handling for log entries (Outage Log, Alarm Log, Run Log)
        # Paths like "Outage/Outage Log/0/Date" should become "Last Outage Date"
        # Only process entry "0" (the latest, 0-indexed) and skip others
        if any(log_type in path for log_type in ["Outage Log", "Alarm Log", "Run Log"]):
            # Check if this is a numbered log entry
            for i, part in enumerate(name_parts):
                if part.isdigit():
                    entry_num = int(part)
                    if entry_num != 0:
                        # Skip non-latest entries - return None to signal skip
                        return None
                    # Build name as "Last [Log Type] [Field]"
                    # Find the log type (part before the number)
                    if i > 0:
                        log_type = name_parts[i - 1].replace(" Log", "")
                        field = name_parts[-1] if i < len(name_parts) - 1 else ""
                        name = f"Last {log_type} {field}".strip()
                    else:
                        name = " ".join(name_parts[-2:])
                    break
            else:
                # No number found, use default naming
                if len(name_parts) >= 2:
                    name = " ".join(name_parts[-2:])
                else:
                    name = name_parts[-1] if name_parts else path
        elif len(name_parts) >= 2:
            # Use last 2 components for reasonable context
            # e.g., "Monitor/Last Log Entries/Logs/Alarm Log" -> "Logs Alarm Log"
            name = " ".join(name_parts[-2:])
        else:
            name = name_parts[-1] if name_parts else path

        # Extract unit and value from entity data
        if isinstance(entity_data, dict) and "value" in entity_data:
            # Genmon numeric JSON format: {"type": "float", "value": 13.5, "unit": "V"}
            unit = entity_data.get("unit") or None  # Normalize empty string to None
            value = entity_data.get("value")
            genmon_type = entity_data.get("type", "")
            is_numeric = genmon_type in ("int", "float") or isinstance(value, (int, float))
        else:
            # Plain value - try to extract unit from string
            value = entity_data
            value_str = str(value) if value is not None else ""
            unit = self._extract_unit_from_value(value_str)
            is_numeric = self._is_numeric_value(value)

        # Guess device class based on unit or name
        device_class = None
        if unit == 'V':
            device_class = 'voltage'
        elif unit == 'A':
            device_class = 'current'
        elif unit in ('W', 'kW'):
            device_class = 'power'
        elif unit == 'kWh':
            device_class = 'energy'
        elif unit == 'Hz':
            device_class = 'frequency'
        elif unit in ('h', 's'):
            device_class = 'duration'
        elif unit == '%':
            device_class = None  # percentage doesn't have a specific device class
        elif 'temperature' in name.lower() or 'temp' in name.lower():
            device_class = 'temperature'
        elif 'humidity' in name.lower():
            device_class = 'humidity'
        elif 'pressure' in name.lower():
            device_class = 'pressure'

        # Select icon based on content
        icon = "mdi:information-outline"
        if "outage" in name.lower():
            icon = "mdi:power-plug-off" if "date" in name.lower() else "mdi:timer-outline"
        elif "alarm" in name.lower():
            icon = "mdi:alert"
        elif "run" in name.lower():
            icon = "mdi:engine"

        # Build config
        config = {
            "name": name,
            "path": path,
            "device_class": device_class,
            "unit": unit,
            "icon": icon,
            "state_class": "measurement" if is_numeric else None,
            "category": "diagnostic",
            "dynamic": True,  # Mark as dynamically discovered
        }

        return config

    # --------------------------------------------------------------------------
    def _discover_dynamic_sensors(self, genmon_data):
        """Walk through genmon data and discover sensors not in self.SensorDefinitions"""

        # Get all known paths from entity definitions
        known_paths = set()
        for entity_def in self.SensorDefinitions.values():
            known_paths.add(entity_def["path"].lower())
        for entity_def in self.BinarySensorDefinitions.values():
            known_paths.add(entity_def["path"].lower())

        # Walk all data and find new sensors
        new_sensors = {}
        for path, entity_data in self._walk_genmon_data(genmon_data):
            # Skip if this path is already defined
            if path.lower() in known_paths:
                continue

            # Skip certain paths that don't make sense as sensors
            skip_patterns = [
                'controller settings',  # Configuration, not sensor data
            ]
            # Skip Tiles - handled by static sensor definitions (cpu_temp)
            if path.startswith("Tiles/"):
                continue
            if any(skip in path.lower() for skip in skip_patterns):
                continue

            # Only include the most recent outage log entry (entry 0, which is the latest)
            # Skip entries like "Outage/Outage Log/1/Date", keep "Outage/Outage Log/0/Date"
            if 'outage log' in path.lower():
                outage_match = re.search(r'outage log/(\d+)/', path, re.IGNORECASE)
                if outage_match and outage_match.group(1) != '0':
                    continue  # Skip all but the most recent (0th) outage log entry

            # Extract the actual value for empty check
            if isinstance(entity_data, dict) and "value" in entity_data:
                actual_value = entity_data.get("value")
            else:
                actual_value = entity_data

            # Skip empty or useless values
            if actual_value is None or actual_value == "" or actual_value == "--":
                continue

            # Generate entity_id and config
            entity_id = self._path_to_entity_id(path)
            if entity_id and entity_id not in self.SensorDefinitions:
                config = self._generate_dynamic_sensor_config(path, entity_data)
                # config is None if we should skip this entry (e.g., non-latest log entries)
                if config is not None:
                    new_sensors[entity_id] = config

        return new_sensors

    # --------------------------------------------------------------------------
    def _process_binary_value(self, value, entity_def):
        """Process value to determine ON/OFF state for binary sensor"""

        try:
            value_str = str(value).strip()

            # Handle payload_on_not_empty (true if value exists and not empty)
            if entity_def.get("payload_on_not_empty"):
                if value_str and value_str.lower() not in ["", "none", "n/a", "unknown"]:
                    return "ON"
                return "OFF"

            # Handle numeric comparison: payload_on_gt (greater than threshold)
            if "payload_on_gt" in entity_def:
                try:
                    # Extract numeric value from string (e.g., "60.12 Hz" -> 60.12)
                    numeric_str = ''.join(c for c in value_str.split()[0] if c.isdigit() or c == '.' or c == '-')
                    if numeric_str:
                        numeric_val = float(numeric_str)
                        threshold = float(entity_def["payload_on_gt"])
                        return "ON" if numeric_val > threshold else "OFF"
                except (ValueError, IndexError):
                    pass
                return "OFF"

            # Handle list of ON values
            if isinstance(entity_def.get("payload_on"), list):
                for on_value in entity_def["payload_on"]:
                    if on_value.lower() in value_str.lower():
                        return "ON"
                # Check for invert logic
                if entity_def.get("payload_off_invert"):
                    return "OFF"

            # Handle list of OFF values
            if isinstance(entity_def.get("payload_off"), list):
                for off_value in entity_def["payload_off"]:
                    if off_value.lower() in value_str.lower():
                        return "OFF"

            # Handle simple string match
            if entity_def.get("payload_on") and not isinstance(entity_def["payload_on"], list):
                if value_str.lower() == str(entity_def["payload_on"]).lower():
                    return "ON"

            if entity_def.get("payload_off") and not isinstance(entity_def["payload_off"], list):
                if value_str.lower() == str(entity_def["payload_off"]).lower():
                    return "OFF"

            # Default based on invert flag
            if entity_def.get("payload_off_invert"):
                return "OFF"

            return "OFF"

        except Exception as e1:
            self.LogDebug(f"Error processing binary value: {str(e1)}")
            return "OFF"

    # --------------------------------------------------------------------------
    def _publish_state(self, entity_type, entity_id, value, track_change=True):
        """Publish state update to MQTT.

        Returns True if value was published (changed), False if skipped (unchanged).
        """

        try:
            # Check if value changed
            state_key = f"{entity_type}/{entity_id}"
            if state_key in self.LastValues and self.LastValues[state_key] == value:
                return False  # No change

            self.LastValues[state_key] = value
            state_topic = f"{self.BaseTopic}/{entity_type}/{entity_id}/state"
            self.MQTTclient.publish(state_topic, value, retain=True)
            return True

        except Exception as e1:
            self.LogErrorLine(f"Error publishing state: {str(e1)}")
            return False

    # --------------------------------------------------------------------------
    def _signal_close(self, signum, frame):
        """Handle shutdown signal"""

        self.Close()
        sys.exit(0)

    # --------------------------------------------------------------------------
    def Close(self):
        """Clean shutdown"""

        self.LogDebug("Shutting down MyHomeAssistant")
        self.Exiting = True

        # Publish offline status
        try:
            availability_topic = f"{self.BaseTopic}/status"
            self.MQTTclient.publish(availability_topic, payload="offline", qos=1, retain=True)
        except Exception:
            pass

        # Stop threads
        for thread_name in list(self.Threads.keys()):
            try:
                self.KillThread(thread_name)
            except Exception:
                pass

        # Close connections
        try:
            self.MQTTclient.loop_stop()
            self.MQTTclient.disconnect()
        except Exception:
            pass

        try:
            self.Generator.Close()
        except Exception:
            pass


# -------------------------------------------------------------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("genhomeassistant")

    Instance = MyHomeAssistant(
        host=address,
        port=port,
        log=log,
        loglocation=loglocation,
        configfilepath=ConfigFilePath,
        console=console,
    )

    while not Instance.Exiting:
        time.sleep(0.5)

    sys.exit(0)
