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

# One setting on a settings page. The page shows the settings in table order.
#   key      name of the setting, also the entry in the config file
#   type     string, password, int, float, boolean or list
#   title    label shown on the page
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
# where sort is the setting's position in the table (genserv numbers them).
Setting = collections.namedtuple(
    "Setting", "key type title default bounds file when", defaults=(0, "genmon", None)
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
    Setting("server_port", "int", "Server Port", ProgramDefaults.ServerPort, "digits"),
    # not shown: changing it breaks the modbus comms, only for debugging
    Setting("address", "string", "Modbus slave address", "9d"),
    Setting("response_address", "string", "Modbus slave transmit address", ""),
    Setting("additional_modbus_timeout", "float", "Additional Modbus Timeout (sec)",
            "0.0", "number"),
    Setting("modbus_between_frame_delay", "float", "Modbus Between Frame Delay (sec)",
            "0.0", "number"),
    # deprecated, no longer needed:
    # Setting("use_modbus_fc4", "boolean", "Use Modbus FC4 instead of FC3", False),
    Setting("serial_rate", "int", "Serial Data Rate", 9600, "digits"),
    Setting("serial_parity", "list", "Serial Parity", "None", "None,Even,Odd"),
    Setting("forceserialuse", "boolean", "Force Use of Serial Port on Errors", False),
    Setting("allow_local_access", "boolean", "Allow LAN access to genmon", False, ""),
    Setting("wait_for_init_seconds", "int", "Initialization Wait Time (seconds)", 15, "digits"),
    Setting("watchdog_addition", "float", "Additional Watchdog Timeout (sec)", "0.0", "number"),
    Setting("controllertype", "list", "Controller Type",
            "generac_evo_nexus", "generac_evo_nexus,h_100,powerzone_pro,custom"),
    Setting("import_config_file", "list", "Custom Controller Config File",
            "Evolution_Liquid_Cooled.json", IMPORT_CONFIG_FILES),
    Setting("ignore_alarms", "string", "Ignore Alarms", "", "", when="custom"),
    Setting("phase", "list", "Generator Phase", "1", "1,3"),
    Setting("threephaseutilitycompensation", "boolean", "Three Phase Utility Volts Compensation",
            False, when="evo_nexus"),
    Setting("loglocation", "string", "Log Directory", ProgramDefaults.LogPath, "required UnixDir"),
    Setting("userdatalocation", "string", "User Defined Data Directory",
            GENMON_DIR, "required UnixDir"),
    Setting("ignore_unknown", "boolean", "Ignore Unknown Values", False),
    Setting("alternate_date_format", "boolean", "Alternate Date Format", False),
    Setting("use_aux_alarm_log", "boolean", "Use Auxiliary Alarm Log", False),
    # not shown, the auto-detect sets these; only to override the auto-detect:
    # Setting("liquidcooled", "boolean", "Force Controller Type (cooling)", False),
    # Setting("evolutioncontroller", "boolean", "Force Controller Type (Evo/Nexus)", True),
    # removed, the outage log is always in the same location:
    # Setting("outagelog", "string", "Outage Log", "/home/pi/genmon/outage.txt",
    #         "required UnixFile"),
    Setting("serialnumberifmissing", "string", "Serial Number if Missing", ""),
    Setting("additionalrunhours", "float", "Additional Run Hours", "", "number"),
    Setting("estimated_load", "float", "Estimated Load", "0.0", "required range:0:1"),
    Setting("subtractfuel", "float", "Subtract Fuel", "0.0", "number"),
    # Setting("kwlog", "string", "Power Log Name / Disable", ""),
    Setting("usenominallinevolts", "boolean", "Use Nominal Volts Override", False, when="not_h100"),
    # set up automatically for Nexus controllers:
    # Setting("uselegacysetexercise", "boolean", "Use Legacy Exercise Time", False,
    #         when="nexus"),
    Setting("usecalculatedpower", "boolean", "Use Calculated Power", False, when="h100"),
    Setting("unbalanced_capacity", "float", "Unbalanced Load Capacity",
            "0", "range:0:0.50", when="evo_nexus"),
    Setting("nominallinevolts", "int", "Override nominal line voltage in UI",
            "240", "digits", when="not_h100"),
    Setting("outagelog_max_entries", "int", "Maximum Entries in Outage Log",
            "100", "digits", when="not_h100"),
    Setting("show_hours_activation", "boolean", "Time Since Activation Format",
            True, when="evo_nexus"),
    Setting("outage_notice_delay", "int", "Outage Notice Delay", "0", "digits", when="not_h100"),
    Setting("min_outage_duration", "int", "Minimum Outage Duration",
            "0", "digits", when="not_h100"),
    Setting("outage_notice_interval", "int", "Outage Recurring Notice Interval (minutes)",
            "0", "digits", when="not_h100"),
    Setting("nexus_legacy_freq", "boolean", "Use Nexus Legacy Frequency", True, when="nexus"),
    Setting("half_rate", "float", "Fuel Rate Half Load", "0.0", "number"),
    Setting("full_rate", "float", "Fuel Rate Full Load", "0.0", "number"),
    Setting("fuel_units", "list", "Fuel Units", "gal", "gal,cubic feet"),
    Setting("enable_fuel_log", "boolean", "Log Fuel Level to File", False),
    Setting("fuel_log_freq", "float", "Fuel Log Frequency", "15.0", "number"),
    # Setting("fuel_log", "string", "Fuel Log Path and File Name", ""),
    Setting("kwlogmax", "string", "Maximum size Power Log (MB)", ""),
    Setting("max_powerlog_entries", "int", "Maximum Entries in Power Log", "8000", "digits"),
    Setting("currentdivider", "float", "Current Divider", "", "number"),
    Setting("currentoffset", "float", "Current Offset", "", "number"),
    Setting("legacy_power", "boolean", "Use Legacy Power Calculation", False),
    Setting("disableplatformstats", "boolean", "Disable Platform Stats", False),
    Setting("https_port", "int", "Override HTTPS port", "", "digits"),
    Setting("user_url", "string", "User URL", ""),
    Setting("extend_wait", "int", "Extend email retry", "0", "digits", file="mail"),
    Setting("multi_instance", "boolean", "Allow Multiple Genmon Instances", False),
    Setting("max_login_attempts", "int", "Maxmum login attempts before temporary lockout",
            5, "digits"),
    Setting("login_lockout_seconds", "int", "Login lockout duration in seconds", 5 * 60, "digits"),
    Setting("uselinuxwifisignalgauge", "boolean", "Show Wifi Signal Strength Gauge",
            True, when="linux"),
    Setting("wifiispercent", "boolean", "Wifi Gauge is percentage", False, when="linux"),
    Setting("preferred_network_adapter", "string", "Preferred Network Adapter", "", when="linux"),
    Setting("useraspberrypicputempgauge", "boolean", "Show CPU Temperature Gauge",
            True, when="linux"),
)
