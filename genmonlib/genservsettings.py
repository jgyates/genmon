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
#   bounds   checks done by the page (see VALIDATION RULES below), or for a list
#            the comma separated choices; 0 for none
#   file     the config file: "genmon" (genmon.conf) or "mail" (mymail.conf),
#            or None for a value genserv works out that is not saved
#   when     only shown when this is true, see GenServ.SettingShown:
#            custom        custom controller
#            evo_nexus     Evolution / Nexus controller
#            not_h100      any controller except H-100 / G-Panel
#            h100          H-100 / G-Panel controller
#            h100_pzp      H-100 / G-Panel or PowerZone Pro controller
#            not_h100_pzp  any controller except H-100 / G-Panel or PowerZone Pro
#            nexus         not_h100 and the controller name has "nexus"
#            evo_lc_diesel Evolution liquid cooled diesel (by controller name)
#            linux         genmon is running on Linux
#            setgentime    the controller can set the generator time
#            A key can appear twice with different conditions; if both are
#            shown, the later row wins.
#
# The browser gets each setting as a list:
#   [type, title, sort, value, tooltip, bounds, file name, section, key]
# where sort is the setting's position in the table (genserv numbers them).
#
# VALIDATION RULES (bounds): a rule is rule or rule:param, for example
# minmax:10:50 uses the minmax rule with two arguments, 10 and 50. Several rules
# are separated by spaces.
#   required: The field is required. Only works with text inputs.
#   digits: Only digits.
#   number: Must be a number.
#   username: Must be between 4 and 32 characters long and start with a letter.
#       You may use letters, numbers, underscores, and one dot.
#   email: Must be a valid email.
#   pass: Must be at least 6 characters long, and contain at least one number,
#       one uppercase and one lowercase letter.
#   strongpass: Must be at least 8 characters long and contain at least one
#       uppercase and one lowercase letter and one number or special character.
#   phone: Must be a valid US phone number.
#   zip: Must be a valid US zip code
#   url: Must be a valid URL.
#   range:min:max: Must be a number between min and max. Usually combined with
#       number or digits.
#   min:min: Must be at least min characters long.
#   max:max: Must be no more that max characters long.
#   minmax:min:max: Must be between min and max characters long.
#   minoption:min: Must have at least min checkboxes or radios selected.
#   maxoption:max: Must have no more than max checkboxes or radios selected.
#   select:default: Make a select required, where default is the value of the
#       default option.
#   extension:ext: Validates file inputs. You can have as many ext as you want.
#   equalto:name: Must be equal to another field where name is the name of the field.
#   date:format: Must a valid date in any format. The default is mm/dd/yyyy but
#       you can pass any format with any separator, ie. date:yyyy-mm-dd.
#   InternetAddress: url without http in front.
#   UnixFile: Unix file file.
#   UnixDir: Unix file path.
#   UnixDevice: Unix file path starting with /dev/.
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
MFA_URL = Dynamic("mfa_url")  # MFA provisioning URL, only before MFA is enrolled
MFA_ENROLLED = Dynamic("mfa_enrolled")
EMAIL_CONFIGURED = Dynamic("email_configured")  # email can be sent
CERT_INFO = Dynamic("cert_info")  # certificate status for the certificate wizard

# ------------ Settings page (settings) ------------------------------------------
MAIN_SETTINGS = (
    Setting("sitename", "string", "Site Name", "SiteName", "required minmax:4:50"),
    Setting("use_serial_tcp", "boolean", "Enable Serial over TCP/IP", False, ""),
    Setting("port", "string", "Port for Serial Communication",
            "/dev/serial0", "required UnixDevice"),
    Setting("serial_tcp_address", "string", "Serial Server TCP/IP Address", "", "InternetAddress"),
    Setting("serial_tcp_port", "int", "Serial Server TCP/IP Port", "8899", "digits"),
    Setting("serial_tcp_keepalive", "boolean", "Enable TCP Keep Alive", False, ""),
    Setting("modbus_tcp", "boolean", "Use Modbus TCP protocol", False, ""),
    Setting("disableoutagecheck", "boolean", "Do Not Check for Outages", False, ""),
    Setting("syncdst", "boolean", "Sync Daylight Savings Time", False, "", when="setgentime"),
    Setting("synctime", "boolean", "Sync Time", False, "", when="setgentime"),
    Setting("metricweather", "boolean", "Use Metric Units", False, ""),
    Setting("optimizeforslowercpu", "boolean", "Optimize for slower CPUs", False, ""),
    Setting("disablepowerlog", "boolean", "Disable Power / Current Display", False, ""),
    Setting("disablesensorlog", "boolean", "Disable Sensor Log", False, ""),
    Setting("autofeedback", "boolean", "Automated Feedback", False, ""),
    Setting("update_check", "boolean", "Check for Software Update", True, ""),
    Setting("sensorlogmax", "string", "Maximum size Sensor Log (MB)", "5"),
    Setting("max_sensorlog_entries", "int", "Maximum Entries in Sensor Log", "2000", "digits"),
    Setting("nominalfrequency", "list", "Rated Frequency", "60", "50,60"),
    Setting("nominalrpm", "int", "Nominal RPM", "3600", "required digits range:1500:4000"),
    Setting("nominalkw", "int", "Maximum kW Output", "22", "required digits range:0:1000"),
    Setting("fueltype", "list", "Fuel Type", "Natural Gas", "Natural Gas,Propane,Diesel,Gasoline"),
    Setting("tanksize", "int", "Fuel Tank Size", "0", "required digits range:0:10000"),
    Setting("usesensorforfuelgauge", "boolean", "Use Sensor for Fuel Gauge",
            True, "", when="evo_lc_diesel"),
    Setting("usesensorforfuelgauge", "boolean", "Use Sensor for Fuel Gauge",
            False, "", when="h100_pzp"),
    Setting("voltageconfiguration", "list", "Line to Neutral / Line to Line",
            "277/480", "120/208,120/240,230/400,240/415,277/480,347/600", when="h100_pzp"),
    Setting("nominalbattery", "list", "Nominal Battery Voltage", "24", "12,24", when="custom"),
    Setting("hts_transfer_switch", "boolean", "HTS/MTS/STS Transfer Switch",
            False, "", when="h100_pzp"),
    Setting("enhancedexercise", "boolean", "Enhanced Exercise Time",
            False, "", when="not_h100_pzp"),
    Setting("smart_transfer_switch", "boolean", "Smart Transfer Switch", False, ""),
    Setting("displayunknown", "boolean", "Display Experimental Data", False, ""),
    Setting("industrialoutagecheck", "boolean", "Outage Notice on Transfer State Change",
            False, "", when="h100"),
    # These do not appear to work on reload, some issue with Flask
    Setting("usehttps", "boolean", "Use Secure Web Server", False, ""),
    Setting("cert_mode", "list", "Certificate Mode", "selfsigned", "selfsigned,localca,custom"),
    # Info-only cert status for the UI cert wizard
    Setting("cert_info", "string", "Certificate Info", CERT_INFO, "", file=None),
    Setting("keyfile", "string", "https Key File", "", "UnixFile"),
    Setting("certfile", "string", "https Certificate File", "", "UnixFile"),
    Setting("http_user", "string", "Web Username", "", "minmax:4:50"),
    Setting("http_pass", "password", "Web Password", "", "minmax:4:50"),
    Setting("http_user_ro", "string", "Limited Rights User Username", "", "minmax:4:50"),
    Setting("http_pass_ro", "password", "Limited Rights User Password", "", "minmax:4:50"),
    Setting("usemfa", "boolean", "Use Multi-Factor Authentication", False, ""),
    # Info-only MFA status, these can not be changed by the web app
    Setting("mfa_url", "qrcode", "MFA QRCode", MFA_URL, "", file=None),
    Setting("mfa_enrolled", "boolean", "MFA Enrolled", MFA_ENROLLED, "", file=None),
    # Info-only flag so the settings page can show whether email OTP is available
    Setting("email_configured", "boolean", "Email Configured", EMAIL_CONFIGURED, "", file=None),
    Setting("http_port", "int", "Port of WebServer", 8000, "required digits"),
    Setting("remember_me_days", "int", "Remember Me (days, 0 = browser session only)",
            0, "minmax:0:365"),
    Setting("allow_iframe", "boolean", "Allow Embedding in an iframe", False, ""),
    Setting("mfa_trust_extend", "boolean", "Remember this browser & don't ask for MFA again",
            False, ""),
    Setting("mfa_trust_days", "int", "Days to remember (never use on shared computers)",
            90, "minmax:1:365"),
    Setting("favicon", "string", "FavIcon", "", "minmax:8:255"),
    Setting("system_theme", "boolean",
            "Select light or dark theme based on the browser/system setting", False, ""),
    # Setting("disableemail", "boolean", "Disable Email Usage", True, "", file="mail"),
    Setting("disablesmtp", "boolean", "Disable Sending Email", False, "", file="mail"),
    Setting("email_account", "string", "Email Account",
            "myemail@gmail.com", "minmax:3:50", file="mail"),
    Setting("email_pw", "password", "Email Password", "password", "max:70", file="mail"),
    Setting("sender_account", "string", "Sender Address",
            "no-reply@gmail.com", "email", file="mail"),
    Setting("sender_name", "string", "Sender Name", "", "max:50", file="mail"),
    # email_recipient setting will be handled on the notification screen
    Setting("smtp_server", "string", "SMTP Server",
            "smtp.gmail.com", "InternetAddress", file="mail"),
    Setting("smtp_port", "int", "SMTP Server Port", 587, "digits", file="mail"),
    Setting("ssl_enabled", "boolean", "Use SSL Encryption", False, "", file="mail"),
    Setting("tls_disable", "boolean", "Disable TLS Encryption", False, "", file="mail"),
    Setting("smtpauth_disable", "boolean", "Disable SMTP Auth", False, "", file="mail"),
    Setting("use_html", "boolean", "Use HTML Email Format", False, "", file="mail"),
    Setting("disableimap", "boolean", "Disable Receiving Email", False, "", file="mail"),
    Setting("imap_server", "string", "IMAP Server",
            "imap.gmail.com", "InternetAddress", file="mail"),
    Setting("readonlyemailcommands", "boolean", "Disable Email Write Commands", False, ""),
    Setting("incoming_mail_folder", "string", "Incoming Mail Folder", "Generator", "minmax:1:1500"),
    Setting("processed_mail_folder", "string", "Mail Processed Folder",
            "Generator/Processed", "minmax:1:255"),
    Setting("disableweather", "boolean", "Disable Weather Functionality", False, ""),
    Setting("weatherkey", "string", "Openweathermap.org API key", "", "required minmax:4:50"),
    Setting("weatherlocation", "string", "Location to report weather", "", "required minmax:4:50"),
    Setting("minimumweatherinfo", "boolean", "Display Minimum Weather Info", True, ""),
)

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
