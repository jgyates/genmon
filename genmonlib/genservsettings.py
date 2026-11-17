#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: genservsettings.py
# PURPOSE: the settings shown on the genserv.py web pages
#
#  AUTHOR: Jason G Yates
#    DATE: 17-Nov-2026
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import collections

from genmonlib.program_defaults import ProgramDefaults

# One setting on a settings page:
#   key      name of the setting, also the entry in the config file
#   type     string, password, int, float, boolean or list
#   title    label shown on the page
#   sort     the page shows settings in this order (settings with the same
#            number stay in table order)
#   default  value shown when the config file does not have the entry
#   bounds   checks done by the page ("digits", "number", "required UnixDir",
#            "range:0:1", ...), or for a list the comma separated choices;
#            0 for none
#   file     the config file: "genmon" (genmon.conf) or "mail" (mymail.conf)
#   when     only shown when this is true, see GenServ.SettingShown:
#            custom     custom controller
#            evo_nexus  Evolution / Nexus controller
#            not_h100   any controller except H-100 / G-Panel
#            h100       H-100 / G-Panel controller
#            nexus      not_h100 and the controller name has "nexus"
#            linux      genmon is running on Linux
#
# The browser gets each setting as a list:
#   [type, title, sort, value, tooltip, bounds, file name, section, key]
Setting = collections.namedtuple(
    "Setting", "key type title sort default bounds file when", defaults=(0, "genmon", None)
)


# A default or bounds value that genserv fills in when the page is built
class Dynamic(object):
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return "Dynamic(%r)" % self.name


GENMON_DIR = Dynamic("genmon_dir")  # the folder genserv.py is in
IMPORT_CONFIG_FILES = Dynamic("import_config_files")  # the files in data/controller

# ------------ Advanced settings page (get_advanced_settings) -------------------
ADVANCED_SETTINGS = (
    # not shown: changing it breaks the link between genmon and genserv
    Setting("server_port", "int", "Server Port", 5, ProgramDefaults.ServerPort, "digits"),
    # not shown: changing it breaks the modbus comms, only for debugging
    Setting("address", "string", "Modbus slave address", 6, "9d"),
    Setting("response_address", "string", "Modbus slave transmit address", 7, ""),
    Setting("additional_modbus_timeout", "float", "Additional Modbus Timeout (sec)",
            8, "0.0", "number"),
    Setting("modbus_between_frame_delay", "float", "Modbus Between Frame Delay (sec)",
            8, "0.0", "number"),
    # deprecated, no longer needed:
    # Setting("use_modbus_fc4", "boolean", "Use Modbus FC4 instead of FC3", 9, False),
    Setting("serial_rate", "int", "Serial Data Rate", 10, 9600, "digits"),
    Setting("serial_parity", "list", "Serial Parity", 11, "None", "None,Even,Odd"),
    Setting("forceserialuse", "boolean", "Force Use of Serial Port on Errors", 12, False),
    Setting("allow_local_access", "boolean", "Allow LAN access to genmon", 12, False, ""),
    Setting("wait_for_init_seconds", "int", "Initialization Wait Time (seconds)", 13, 15, "digits"),
    Setting("watchdog_addition", "float", "Additional Watchdog Timeout (sec)", 13, "0.0", "number"),
    Setting("controllertype", "list", "Controller Type",
            14, "generac_evo_nexus", "generac_evo_nexus,h_100,powerzone_pro,custom"),
    Setting("import_config_file", "list", "Custom Controller Config File",
            21, "Evolution_Liquid_Cooled.json", IMPORT_CONFIG_FILES),
    Setting("ignore_alarms", "string", "Ignore Alarms", 22, "", "", when="custom"),
    Setting("phase", "list", "Generator Phase", 22, "1", "1,3"),
    Setting("threephaseutilitycompensation", "boolean", "Three Phase Utility Volts Compensation",
            23, False, when="evo_nexus"),
    Setting("loglocation", "string", "Log Directory",
            23, ProgramDefaults.LogPath, "required UnixDir"),
    Setting("userdatalocation", "string", "User Defined Data Directory",
            24, GENMON_DIR, "required UnixDir"),
    Setting("ignore_unknown", "boolean", "Ignore Unknown Values", 25, False),
    Setting("alternate_date_format", "boolean", "Alternate Date Format", 26, False),
    Setting("use_aux_alarm_log", "boolean", "Use Auxiliary Alarm Log", 27, False),
    # not shown, the auto-detect sets these; only to override the auto-detect:
    # Setting("liquidcooled", "boolean", "Force Controller Type (cooling)", 30, False),
    # Setting("evolutioncontroller", "boolean", "Force Controller Type (Evo/Nexus)", 31, True),
    # removed, the outage log is always in the same location:
    # Setting("outagelog", "string", "Outage Log", 32, "/home/pi/genmon/outage.txt",
    #         "required UnixFile"),
    Setting("serialnumberifmissing", "string", "Serial Number if Missing", 36, ""),
    Setting("additionalrunhours", "float", "Additional Run Hours", 37, "", "number"),
    Setting("estimated_load", "float", "Estimated Load", 38, "0.0", "required range:0:1"),
    Setting("subtractfuel", "float", "Subtract Fuel", 39, "0.0", "number"),
    Setting("unbalanced_capacity", "float", "Unbalanced Load Capacity",
            46, "0", "range:0:0.50", when="evo_nexus"),
    Setting("show_hours_activation", "boolean", "Time Since Activation Format",
            47, True, when="evo_nexus"),
    # Setting("kwlog", "string", "Power Log Name / Disable", 36, ""),
    Setting("usenominallinevolts", "boolean", "Use Nominal Volts Override",
            45, False, when="not_h100"),
    Setting("nominallinevolts", "int", "Override nominal line voltage in UI",
            46, "240", "digits", when="not_h100"),
    Setting("outagelog_max_entries", "int", "Maximum Entries in Outage Log",
            46, "100", "digits", when="not_h100"),
    Setting("outage_notice_delay", "int", "Outage Notice Delay",
            47, "0", "digits", when="not_h100"),
    Setting("min_outage_duration", "int", "Minimum Outage Duration",
            48, "0", "digits", when="not_h100"),
    Setting("outage_notice_interval", "int", "Outage Recurring Notice Interval (minutes)",
            49, "0", "digits", when="not_h100"),
    Setting("nexus_legacy_freq", "boolean", "Use Nexus Legacy Frequency", 50, True, when="nexus"),
    # set up automatically for Nexus controllers:
    # Setting("uselegacysetexercise", "boolean", "Use Legacy Exercise Time", 49, False,
    #         when="nexus"),
    Setting("usecalculatedpower", "boolean", "Use Calculated Power", 45, False, when="h100"),
    Setting("half_rate", "float", "Fuel Rate Half Load", 55, "0.0", "number"),
    Setting("full_rate", "float", "Fuel Rate Full Load", 56, "0.0", "number"),
    Setting("fuel_units", "list", "Fuel Units", 57, "gal", "gal,cubic feet"),
    Setting("enable_fuel_log", "boolean", "Log Fuel Level to File", 60, False),
    Setting("fuel_log_freq", "float", "Fuel Log Frequency", 61, "15.0", "number"),
    # Setting("fuel_log", "string", "Fuel Log Path and File Name", 62, ""),
    Setting("kwlogmax", "string", "Maximum size Power Log (MB)", 70, ""),
    Setting("max_powerlog_entries", "int", "Maximum Entries in Power Log", 71, "8000", "digits"),
    Setting("currentdivider", "float", "Current Divider", 72, "", "number"),
    Setting("currentoffset", "float", "Current Offset", 73, "", "number"),
    Setting("legacy_power", "boolean", "Use Legacy Power Calculation", 74, False),
    Setting("disableplatformstats", "boolean", "Disable Platform Stats", 80, False),
    Setting("https_port", "int", "Override HTTPS port", 81, "", "digits"),
    Setting("user_url", "string", "User URL", 82, ""),
    Setting("extend_wait", "int", "Extend email retry", 83, "0", "digits", file="mail"),
    Setting("multi_instance", "boolean", "Allow Multiple Genmon Instances", 85, False),
    Setting("max_login_attempts", "int", "Maxmum login attempts before temporary lockout",
            96, 5, "digits"),
    Setting("login_lockout_seconds", "int", "Login lockout duration in seconds",
            97, 5 * 60, "digits"),
    Setting("uselinuxwifisignalgauge", "boolean", "Show Wifi Signal Strength Gauge",
            108, True, when="linux"),
    Setting("wifiispercent", "boolean", "Wifi Gauge is percentage", 108, False, when="linux"),
    Setting("preferred_network_adapter", "string", "Preferred Network Adapter",
            108, "", when="linux"),
    Setting("useraspberrypicputempgauge", "boolean", "Show CPU Temperature Gauge",
            109, True, when="linux"),
)
