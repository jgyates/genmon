#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: genservsettings.py
# PURPOSE: the settings shown on the genserv.py web pages: Settings, Advanced
#          Settings and Add-Ons
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
#            evo_nexus_name  the controller name has "evolution" or "nexus"
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
    Setting("ssl_verify_cert", "boolean", "Verify Server Certificate", True, "", file="mail"),
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


# ------------ Add-ons page (get_add_on_settings) --------------------------------
# One add-on:
#   name        the add-on module name, also its section in genloader.conf (where
#               "enable" is stored)
#   title       title shown on the page
#   description description shown on the page
#   icon        icon name ("genmon" gives a generic icon)
#   url         documentation link
#   conf        the add-on's config file, where its parameters are stored, or None
#               if it has no config file of its own
#   params      the parameters shown, or None for an add-on with no settings
#   when        only shown when this is true (see GenServ.SettingShown)
#   libraries   Python modules the add-on needs; if one is missing, the description
#               says so (genloader installs them on restart)
#   checks      hardware the add-on needs, see ADDON_CHECKS
#
# One parameter of an add-on:
#   key         the entry in the add-on's config file
#   type        string, password, int, float, boolean, list or readonly
#   title       label shown on the page
#   description description shown on the page
#   default     value shown when the config file does not have the entry
#   bounds      checks done by the page (see VALIDATION RULES above), or for a list
#               the comma separated choices
#   read        how the value is read from the config file (str, int, float, bool)
#               when it is not the usual one for the type
#   special     handled in a special way, see GenServ.ReadAddOnParam:
#               api_key      a key is made (and saved) if the config file has none
#
# A new parameter is shown, and can be saved, as soon as it is in this table, even
# if the config file on the system does not have the entry yet (saving adds it).
#
# The browser gets each add-on as {"enable", "title", "description", "icon", "url",
# "parameters"}, each parameter as {"value", "type", "description", "bounds",
# "display_name"}.
AddOn = collections.namedtuple(
    "AddOn", "name title description icon url conf params when libraries checks",
    defaults=(None, None, None, (), ()),
)
Param = collections.namedtuple(
    "Param", "key type title description default bounds read special",
    defaults=("", None, None),
)

WIKI = "https://github.com/jgyates/genmon/wiki/1----Software-Overview"

# added to the description when a library in AddOn.libraries is not installed
MISSING_LIBRARY_NOTE = (
    "<br/><font color='red'>The required libraries for this add on are not installed. "
    "They will be installed when the program is restarted.</font>"
)
# AddOn.checks: added to the description when the hardware is not found
ADDON_CHECKS = {
    "i2c": "<br/><font color='red'>The I2C bus not enabled but required for this add-on "
           "to function.</font>",
    "1wire": "<br/><font color='red'>1-wire is not enabled but is required</font>",
    "spi1": "<br/><font color='red'>The SPI bus number one is not enabled but required "
            "for this add-on to function.</font>",
}

NOTIFY_PARAMS = (
    Param("notify_error", "boolean", "Notify for Errors",
          "Send messages for errors (Generator Alarms).",
          True),
    # notify_warning is read by genmonlib/mynotify.py (before 2.0.3 the page saved
    # it as notify_warn, which nothing read)
    Param("notify_warning", "boolean", "Notify for Warnings",
          "Send messages for warnings (service due, fuel low).",
          True),
    Param("notify_info", "boolean", "Notify for Information",
          "Send messages for information (switch state change, engine state change, "
          "exercising).",
          True),
    Param("notify_outage", "boolean", "Notify for Outages",
          "Send messages for outages.",
          True),
    Param("notify_sw_update", "boolean", "Notify for Software Updates",
          "Send messages for software updates.",
          True),
    Param("notify_pi_state", "boolean", "Notify for Pi Hardware Issues",
          "Send messages for Pi hardware sensor status (CPU throttling, undervoltage, etc).",
          True),
)

RETRY_PARAMS = (
    Param("max_retry_time", "int", "Max Retry Duration (seconds)",
          "Maximum number of seconds to retry a failed message before dropping the message.",
          600),
    Param("default_wait", "int", "Retry Interval (seconds)",
          "The number of seconds to wait before retrying a failed message.",
          120),
    # not shown, but a valid conf file setting:
    # Param("minimum_wait_between_messages", "int", "Min Time Between Messages (seconds)",
    #       "The minimum of seconds to wait between sending a message. This is typically "
    #       "zero, except for Callmebot Signal Messaging (should be at least 2 seconds) or "
    #       "other messaging apps that have minimum delays.", 0),
)

ADDONS = (
    AddOn("gengpio", "Genmon GPIO Outputs",
          "Genmon will set Raspberry Pi GPIO outputs (see documentation for details)",
          icon="rpi", url=WIKI + "#gengpiopy-optional"),
    AddOn("gengpioin", "Genmon GPIO Inputs",
          "Genmon will set Raspberry Pi GPIO inputs (see documentation for details)",
          icon="rpi", url=WIKI + "#gengpioinpy-optional", conf="gengpioin.conf",
          params=(
              Param("trigger", "list", "GPIO Edge Trigger",
                    "Set GPIO input to trigger on rising or falling edge.",
                    "falling", "falling,rising,both"),
              Param("resistorpull", "list", "Internal resistor pull",
                    "Set GPIO input internal pull up or pull down resistor.",
                    "up", "up,down,off"),
              Param("bounce", "int", "Software Debounce",
                    "Minimum interval in milliseconds between valid input changes. Zero to "
                    "disable, or positive whole number.",
                    0, "number"),
          )),
    AddOn("gengpioledblink", "Genmon GPIO Output to blink LED",
          "Genmon will blink LED connected to GPIO pin to indicate genmon status",
          icon="rpi", url=WIKI + "#gengpioledblinkpy-optional", conf="gengpioledblink.conf",
          params=(
              Param("ledpin", "int", "GPIO LED pin",
                    "Raspberry Pi header pin number (1 - 40) that the LED is connected to. "
                    "This is the board pin number, not the GPIO number (the default, 12, "
                    "is GPIO 18).",
                    12, "required digits range:1:40"),
          )),
    AddOn("genlog", "Notifications to CSV Log",
          "Log Genmon and utility state changes to a file. Log file is in text CSV format.",
          icon="csv", url=WIKI + "#genlogpy-optional", conf="genlog.conf",
          params=(
              # before 2.0.3 this was "args = -f <file>" in genloader.conf, see
              # Loader.MoveGenLogArgs in genloader.py
              Param("filename", "string", "Log File Name",
                    "Filename for log. Full path of the file must be included (i.e. "
                    "/home/pi/genmon/LogFile.csv)",
                    "", "required UnixFile"),
          )),
    AddOn("gensms", "Notifications via SMS - Twilio",
          "Send Genmon and utility state changes via Twilio SMS",
          icon="twilio", url=WIKI + "#gensmspy-optional", conf="gensms.conf",
          params=(
              Param("accountsid", "string", "Twilio Account SID",
                    "Twilio account SID. This can be obtained from a valid Twilio account",
                    "", "required minmax:10:50"),
              Param("authtoken", "string", "Twilio Authentication Token",
                    "Twilio authentication token. This can be obtained from a valid Twilio "
                    "account",
                    "", "required minmax:10:50"),
              Param("to_number", "string", "Recipient Phone Number",
                    "Mobile number to send SMS message to. This can be any mobile number. "
                    "Separate multiple recipients with commas.",
                    "", "required InternationalPhone"),
              Param("from_number", "string", "Twilio Phone Number",
                    "Number to send SMS message from. This should be a twilio phone number.",
                    "", "required InternationalPhone"),
          )
          + NOTIFY_PARAMS
          + RETRY_PARAMS),
    AddOn("gensms_voip", "SMS via VoIP using voip.ms",
          "SMS Support vis VoIP using voip.ms",
          icon="voipms", url=WIKI + "#gensms_voippy-optional", conf="gensms_voip.conf",
          libraries=("voipms",),
          params=(
              Param("username", "string", "VoIP.ms User Name",
                    "Voip.ms account username",
                    "", "required minmax:5:50"),
              Param("password", "password", "VoIP.ms API password",
                    "VoIP.ms API password. This is NOT the account login, but rather then API "
                    "password",
                    "", "required minmax:8:50"),
              Param("did", "string", "Sender DID Number",
                    "DID number for your voip.ms account to send the SMS.",
                    "", "required InternationalPhone"),
              Param("destination", "string", "Recipient Phone Number",
                    "Mobile number to send SMS message to. This can be any mobile number. "
                    "Separate multiple recipients with commas.",
                    "", "required InternationalPhone"),
          )),
    # not shown: modem_type, the type of modem used. For future use. Presently
    # "LTEPiHat" is the only option.
    AddOn("gensms_modem", "Notifications via SMS - LTE Hat",
          "Send Genmon and utility state changes via cellular SMS (additional hardware "
          "required)",
          icon="sms", url=WIKI + "#gensms_modempy-optional", conf="mymodem.conf",
          params=(
              Param("recipient", "string", "Recipient Phone Number",
                    "Mobile number to send SMS message. This can be any mobile number. No "
                    "dashes or spaces.",
                    "", "required InternationalPhone"),
              Param("port", "string", "Modem Serial Port",
                    "This is the serial device to send AT modem commands. This *must* be "
                    "different from the serial port used by the generator monitor software.",
                    "/dev/ttyAMA0", "required UnixDevice"),
              Param("rate", "int", "Modem Serial Rate",
                    "The baud rate for the port. Use 115200 for the LTEPiHat.",
                    115200, "required digits"),
              Param("log_at_commands", "boolean", "Log AT Commands",
                    "Enable to log at commands to the log file.",
                    False),
          )
          + NOTIFY_PARAMS),
    AddOn("genpushover", "Notifications via Pushover",
          "Send Genmon and utility state changes via Pushover service",
          icon="pushover", url=WIKI + "#genpushoverpy-optional", conf="genpushover.conf",
          params=(
              Param("appid", "string", "Application ID",
                    "Pushover app ID. This is generated by pushover.net when an application is "
                    "created for your account.",
                    "", "required minmax:30:30"),
              Param("userid", "string", "Pushover User Key",
                    "Pushover User Key. Note: this is not your login user name but a key "
                    "generated by pushover.net for your account. To send notifications to more "
                    "than one person, enter multiple user (or group) keys separated by spaces "
                    "and/or commas, e.g. 'key1 key2 key3'. These keys all receive the same "
                    "notifications. If you wish to send different notification types to other "
                    "users, please use the Additional Recipient(s) key and adjust the settings "
                    "for that user.",
                    "", "required minmax:30:500"),
              Param("pushsound", "string", "Push Sound",
                    "Notification sound identifier. See https://pushover.net/api#sounds for a "
                    "full list of sound IDs. All sounds must be lower case.",
                    "updown", "minmax:3:20"),
              Param("alarm_priority", "list", "Alarm Priority",
                    "Alarm Notification priority identifier. See "
                    "https://pushover.net/api#priority",
                    "NORMAL", "LOWEST,LOW,NORMAL,HIGH,EMERGENCY"),
              Param("sw_update_priority", "list", "Software Update Priority",
                    "Software Update Notification priority identifier. See "
                    "https://pushover.net/api#priority",
                    "NORMAL", "LOWEST,LOW,NORMAL,HIGH,EMERGENCY"),
              Param("system_health_priority", "list", "System Health Priority",
                    "System Health Notification priority identifier. See "
                    "https://pushover.net/api#priority",
                    "NORMAL", "LOWEST,LOW,NORMAL,HIGH,EMERGENCY"),
              Param("fuel_priority", "list", "Fuel Level Priority",
                    "Fuel Level Notification priority identifier. See "
                    "https://pushover.net/api#priority",
                    "NORMAL", "LOWEST,LOW,NORMAL,HIGH,EMERGENCY"),
              Param("outage_priority", "list", "Outage Priority",
                    "Outage Notification priority identifier. See "
                    "https://pushover.net/api#priority",
                    "NORMAL", "LOWEST,LOW,NORMAL,HIGH,EMERGENCY"),
              Param("switch_state_priority", "list", "Switch State Priority",
                    "Switch State Notification priority identifier. See "
                    "https://pushover.net/api#priority",
                    "NORMAL", "LOWEST,LOW,NORMAL,HIGH,EMERGENCY"),
              Param("run_state_priority", "list", "Run State Priority",
                    "Run State Notification priority identifier. See "
                    "https://pushover.net/api#priority",
                    "NORMAL", "LOWEST,LOW,NORMAL,HIGH,EMERGENCY"),
              Param("service_state_priority", "list", "Service State Priority",
                    "Service State Notification priority identifier. See "
                    "https://pushover.net/api#priority",
                    "NORMAL", "LOWEST,LOW,NORMAL,HIGH,EMERGENCY"),
              Param("pi_state_priority", "list", "Pi Hardware Sensor State Priority",
                    "Pi Hardware Sensor State Notification priority identifier. See "
                    "https://pushover.net/api#priority",
                    "NORMAL", "LOWEST,LOW,NORMAL,HIGH,EMERGENCY"),
          )
          + NOTIFY_PARAMS
          + (
              Param("extra_userid", "string", "Additional Recipient(s) User Key",
                    "Optional additional Pushover user (or group) key(s), separated by spaces "
                    "and/or commas, for recipients who should only receive some notification "
                    "categories (e.g. a family member who only wants outage alerts). Use the "
                    "'Additional Recipient(s)' Notify settings below to choose which "
                    "categories they receive. A category must also be enabled above for it to "
                    "be sent to these recipients.",
                    "", "minmax:0:500"),
              Param("extra_notify_error", "boolean", "Additional Recipient(s) Notify for Errors",
                    "Send messages for errors (Generator Alarms) to the Additional "
                    "Recipient(s) above.",
                    True),
              Param("extra_notify_warn", "boolean", "Additional Recipient(s) Notify for Warnings",
                    "Send messages for warnings (service due, fuel low) to the Additional "
                    "Recipient(s) above.",
                    True),
              Param("extra_notify_info", "boolean",
                    "Additional Recipient(s) Notify for Information",
                    "Send messages for information (switch state change, engine state change, "
                    "exercising) to the Additional Recipient(s) above.",
                    True),
              Param("extra_notify_outage", "boolean", "Additional Recipient(s) Notify for Outages",
                    "Send messages for outages to the Additional Recipient(s) above.",
                    True),
              Param("extra_notify_sw_update", "boolean",
                    "Additional Recipient(s) Notify for Software Updates",
                    "Send messages for software updates to the Additional Recipient(s) above.",
                    True),
              Param("extra_notify_pi_state", "boolean",
                    "Additional Recipient(s) Notify for Pi Hardware Issues",
                    "Send messages for Pi hardware sensor status to the Additional "
                    "Recipient(s) above.",
                    True),
          )
          + RETRY_PARAMS),
    AddOn("gensyslog", "Linux System Logging",
          "Write generator and utility state changes to system log (/var/log/syslog)",
          icon="linux", url=WIKI + "#gensyslogpy-optional"),
    AddOn("genmqtt", "MQTT integration",
          "Export Genmon data and status to MQTT server for automation integration",
          icon="mqtt", url=WIKI + "#genmqttpy-optional", conf="genmqtt.conf",
          params=(
              Param("mqtt_address", "string", "MQTT Server Address",
                    "Address of your MQTT server.",
                    "", "required InternetAddress"),
              Param("mqtt_port", "int", "MQTT Server Port Number",
                    "The port of the MQTT server in a decimal number.",
                    1883, "required digits"),
              Param("username", "string", "MQTT Authentication Username",
                    "This value is used for the username if your MQTT server requires "
                    "authentication. Leave blank for no authentication.",
                    "", "minmax:4:50"),
              Param("password", "password", "MQTT Authentication Password",
                    "This value is used for the password if your MQTT server requires "
                    "authentication. Leave blank for no authentication or no password.",
                    "", "minmax:4:50"),
              Param("poll_interval", "float", "Poll Interval",
                    "The time in seconds between requesting status from genmon. The default "
                    "value is 2 seconds.",
                    2.0, "number"),
              Param("root_topic", "string", "Root Topic",
                    "(Optional) Prepend this value to the MQTT data path i.e. 'Home' would "
                    "result in 'Home/generator/...''",
                    "", "minmax:1:50"),
              Param("blacklist", "string", "Blacklist Filter",
                    "(Optional) Names of data not exported to the MQTT server, separated by "
                    "commas.",
                    ""),
              Param("flush_interval", "float", "Flush Interval",
                    "(Optional) Time in seconds where even unchanged values will be published "
                    "to their MQTT topic. Set to zero to disable flushing.",
                    0, "number"),
              Param("numeric_json", "boolean", "Numeric Topics",
                    "If enabled will return numeric values in the Status, Maintenance and "
                    "Outage topics as separate topics for unit, type and value.",
                    False),
              Param("numeric_json_object", "boolean", "JSON for Numerics",
                    "If enabled will return a JSON object for numeric values in the Status, "
                    "Maintenance and Outage topics as an object with unit, type and value "
                    "members.",
                    False),
              Param("strlist_json", "boolean", "JSON for String Lists",
                    "If enabled will return a JSON list for any list of strings like the "
                    "Outage log. Does not apply if JSON for Numerics is enabled.",
                    False),
              Param("remove_spaces", "boolean", "Remove Spaces in Topic Path",
                    "If enabled any spaces in the topic path will be converted to underscores",
                    False),
              Param("retain", "boolean", "Retain Data",
                    "If enabled, published messages will be retained by the MQTT broker server "
                    "after a the Add On disconnects from the server.",
                    False),
              Param("cert_authority_path", "string", "SSL/TLS CA certificate file",
                    "(Optional) Full path to Certificate Authority file. Leave empty to not "
                    "use SSL/TLS. If used and the port is 1883, port 8883 is used.",
                    ""),
              Param("client_cert_path", "string", "Client Certificate File",
                    "Optional. Full path the client certificate file. Leave empty to not use "
                    "MTLS.",
                    ""),
              Param("client_key_path", "string", "Client Key File",
                    "Optional. Full path the client key file. Leave empty to not use MTLS.",
                    ""),
              Param("tls_version", "list", "TLS Version",
                    "(Optional) TLS version used. Auto (the default) uses TLS 1.2 or newer, "
                    "whatever the broker supports. Most brokers no longer allow 1.0 or 1.1. "
                    "This is ignored if a CA cert file is not used.",
                    "Auto", "Auto,1.3,1.2,1.1,1.0"),
              Param("cert_reqs", "list", "Certificate Requirements",
                    "(Optional) Defines the certificate requirements that the client imposes "
                    "on the broker. Used if Certificate Authority file is used.",
                    "Required", "None,Optional,Required"),
              Param("client_id", "string", "Client ID",
                    "Unique identifier. Must be unique for each instance of genmon and add on "
                    "running on a given system. ",
                    "genmon"),
          )),
    AddOn("genmqttin", "MQTT Sensor Input",
          "Import data from MQTT broker for genmon use",
          icon="mqtt", url=WIKI + "#genmqttinpy-optional", conf="genmqttin.conf",
          params=(
              Param("topics", "string", "Topics",
                    "Comma separated list of MQTT topics to subscribe and import into genmon. "
                    "All topics must return a numeric value or a string representation of a "
                    "numeric value.",
                    ""),
              Param("labels", "string", "Displayed Name",
                    "Comma separated list of display names for each topic listed above. These "
                    "will be the displayed label for each topic value.",
                    ""),
              Param("units", "string", "Units",
                    "Comma separated list of units for each topic listed above. If no labeled "
                    "is used for a given topic, use a space. If using the imported MQTT data "
                    "for genmon calculations, for power use W or kW, for current use A, for "
                    "voltage use V. ",
                    ""),
              Param("types", "string", "Sensor Type",
                    "Comma separated list of value types for each topic listed above. Valid "
                    "types are: ct1,ct2,ctpower1,ctpower2,fuel,temperature,power,current,"
                    "voltage or pressure. See the wiki entry for this add on for more details.",
                    ""),
              Param("exclude_gauge", "string", "Exclude Gauge",
                    "Comma separated list of Displayed Names that will not be displayed as a "
                    "gauge. If you enable 'Use Data for Calculations' then you can remove "
                    "duplicate gauges with this setting if they show up in the user interface.",
                    ""),
              Param("nominal_values", "string", "Nominal Values",
                    "Comma separated list of nominal values for each topic listed above.",
                    ""),
              Param("maximum_values", "string", "Maximum Values",
                    "Comma separated list of maximum values for each topic listed above.",
                    ""),
              Param("use_for_power_fuel", "boolean", "Use Data for Calculations",
                    "If enabled, the data from sensor types fuel,power,current,ct1,ct2,"
                    "voltageleg1, voltageleg2, ctpower1 and ctpower2 will be imported and used "
                    "for power and fuel calculations (instead of just displaying) within "
                    "genmon.",
                    False),
              Param("strict", "boolean", "Strict Import Rules",
                    "If enabled, genmon will only use Data for Calculations if the generator "
                    "utility line is in an outage. If your sensors are connected after the "
                    "transfer switch (i.e. utility and generator are monitored) the you will "
                    "want to enable this setting to keep genmon from using the sensor readings "
                    "when there is not an outage.",
                    False),
              Param("mqtt_address", "string", "MQTT Server Address",
                    "Address of your MQTT server.",
                    "", "required InternetAddress"),
              Param("mqtt_port", "int", "MQTT Server Port Number",
                    "The port of the MQTT server in a decimal number.",
                    1883, "required digits"),
              Param("username", "string", "MQTT Authentication Username",
                    "This value is used for the username if your MQTT server requires "
                    "authentication. Leave blank for no authentication.",
                    "", "minmax:4:50"),
              Param("password", "password", "MQTT Authentication Password",
                    "This value is used for the password if your MQTT server requires "
                    "authentication. Leave blank for no authentication or no password.",
                    "", "minmax:4:50"),
              Param("cert_authority_path", "string", "SSL/TLS CA certificate file",
                    "(Optional) Full path to Certificate Authority file. Leave empty to not "
                    "use SSL/TLS. If used and the port is 1883, port 8883 is used.",
                    ""),
              Param("client_cert_path", "string", "Client Certificate File",
                    "Optional. Full path the client certificate file. Leave empty to not use "
                    "MTLS.",
                    ""),
              Param("client_key_path", "string", "Client Key File",
                    "Optional. Full path the client key file. Leave empty to not use MTLS.",
                    ""),
              Param("tls_version", "list", "TLS Version",
                    "(Optional) TLS version used. Auto (the default) uses TLS 1.2 or newer, "
                    "whatever the broker supports. Most brokers no longer allow 1.0 or 1.1. "
                    "This is ignored if a CA cert file is not used.",
                    "Auto", "Auto,1.3,1.2,1.1,1.0"),
              Param("cert_reqs", "list", "Certificate Requirements",
                    "(Optional) Defines the certificate requirements that the client imposes "
                    "on the broker. Used if Certificate Authority file is used.",
                    "Required", "None,Optional,Required"),
              Param("client_id", "string", "Client ID",
                    "Unique identifier. Must be unique for each instance of genmon and add on "
                    "running on a given system. ",
                    "genmon"),
          )),
    AddOn("genhomeassistant", "Home Assistant MQTT Discovery",
          "Publish MQTT auto-discovery messages for Home Assistant integration",
          icon="homeassistant", url=WIKI + "#genhomeassistantpy-optional",
          conf="genhomeassistant.conf",
          params=(
              Param("mqtt_address", "string", "MQTT Server Address",
                    "Address of your MQTT broker server (IP address or hostname).",
                    "", "required InternetAddress"),
              Param("mqtt_port", "int", "MQTT Port",
                    "Port of the MQTT broker. Default is 1883 (or 8883 for TLS).",
                    1883, "required digits"),
              Param("username", "string", "Username",
                    "Username for MQTT broker authentication (leave empty if not required).",
                    "", "minmax:4:50"),
              Param("password", "password", "Password",
                    "Password for MQTT broker authentication (leave empty if not required).",
                    ""),
              Param("discovery_prefix", "string", "Discovery Prefix",
                    "Home Assistant MQTT discovery prefix. Default is 'homeassistant'. Only "
                    "change if you configured a different prefix in HA.",
                    "homeassistant"),
              Param("base_topic", "string", "Base Topic",
                    "Base topic for state and command messages. Default is 'genmon'.",
                    "genmon"),
              Param("device_id", "string", "Device ID",
                    "Unique device identifier used in entity IDs. Change if running multiple "
                    "genmon instances.",
                    "generator"),
              Param("device_name", "string", "Device Name",
                    "Friendly device name shown in Home Assistant.",
                    "Generator"),
              Param("poll_interval", "int", "Poll Interval",
                    "Interval in seconds between polling genmon for status updates. Default is "
                    "3.",
                    3.0, read=float),
              Param("discovery_interval", "int", "Discovery Interval",
                    "Interval in seconds to republish discovery messages. Set to 0 to only "
                    "publish on startup. Default is 300.",
                    300),
              Param("blacklist", "string", "Entity Blacklist",
                    "Comma-separated list of strings. Entities with names containing these "
                    "strings will not be created. Matches against entity name, ID, and data "
                    "path.",
                    "Tiles"),
              Param("include_monitor_stats", "boolean", "Include Monitor Stats",
                    "Include platform/monitor statistics (CPU, memory, etc.) as entities.",
                    True),
              Param("include_weather", "boolean", "Include Weather",
                    "Include weather data entities if weather is configured in genmon.",
                    True),
              Param("include_logs", "boolean", "Include Logs",
                    "Include log entries as sensor attributes.",
                    False),
              Param("numeric_json", "boolean", "Use Numeric JSON",
                    "Use numeric JSON format when querying genmon (cleaner values without "
                    "embedded units).",
                    True),
              Param("monitor_address", "string", "Genmon Address",
                    "IP address of genmon if running on a different system. Leave empty for "
                    "localhost.",
                    "", "InternetAddress"),
              Param("cert_authority_path", "string", "CA Certificate Path",
                    "Full path to Certificate Authority file. Leave empty to not use SSL/TLS.",
                    ""),
              Param("tls_version", "list", "TLS Version",
                    "(Optional) TLS version used. Auto (the default) uses TLS 1.2 or newer, "
                    "whatever the broker supports. Most brokers no longer allow 1.0 or 1.1. "
                    "This is ignored if a CA cert file is not used.",
                    "Auto", "Auto,1.3,1.2,1.1,1.0"),
              Param("cert_reqs", "list", "Certificate Requirements",
                    "Certificate requirements that the client imposes on the broker.",
                    "Required", "None,Optional,Required"),
              Param("client_cert_path", "string", "Client Certificate Path",
                    "Full path to client certificate file for MTLS.",
                    ""),
              Param("client_key_path", "string", "Client Key Path",
                    "Full path to client key file for MTLS.",
                    ""),
              Param("client_id", "string", "Client ID",
                    "Unique MQTT client identifier. Must be unique per genmon instance.",
                    "genmon_ha"),
              Param("button_passcode", "password", "Button Passcode",
                    "Passcode for controllers that require authentication for remote commands "
                    "(e.g. MEBAY). Leave empty if not required.",
                    ""),
          )),
    AddOn("genslack", "Notifications via Slack",
          "Send Genmon and utility state changes via Slack service",
          icon="slack", url=WIKI + "#genslackpy-optional", conf="genslack.conf",
          params=(
              Param("webhook_url", "string", "Web Hook URL",
                    "Full Slack Webhook URL. Retrieve from Slack custom integration "
                    "configuration.",
                    "", "required HTTPAddress"),
              Param("channel", "string", "Channel",
                    "Slack channel to which the message will be sent.",
                    ""),
              Param("username", "string", "Username",
                    "Slack username.",
                    "", "required username"),
              Param("icon_emoji", "string", "Icon Emoji",
                    "Emoji that appears as the icon of the user who sent the message i.e. "
                    ":red_circle:n",
                    ":red_circle:"),
              Param("title_link", "string", "Title Link",
                    "Use this to make the title of the message a link i.e. link to the genmon "
                    "web interface.",
                    "", "HTTPAddress"),
          )
          + NOTIFY_PARAMS
          + RETRY_PARAMS),
    AddOn("gencallmebot", "Notifications via CallMeBot",
          "Send Genmon and utility state changes via CallMeBot service",
          icon="callmebot", url=WIKI + "#gencallmebotpy-optional", conf="gencallmebot.conf",
          params=(
              Param("notification_type", "list", "Notification Type",
                    "Type of CallMeBot Notifications. For more information, see "
                    "http://www.callmebot.com.",
                    "", "WhatsApp,Telegram,Signal"),
              Param("api_key", "string", "API Key",
                    "API Key required for WhatsApp Notifications.",
                    ""),
              Param("username", "string", "Username",
                    "CallMeBot username required for Telegram Notifications.",
                    "", "required username"),
              Param("recipient_number", "string", "Recipient Number",
                    "Recipient Number required for WhatsApp Notification. Must be without "
                    "spaces and start with a plus. For Signal this must be the numeric key "
                    "sent to your signal account when registering with CallMeBot (in the form "
                    "xxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)",
                    ""),
          )
          + NOTIFY_PARAMS
          + RETRY_PARAMS),
    AddOn("genexercise", "Enhanced Exercise",
          "Add additional exercise cycles with new functionality for Evolution/Nexus "
          "Controllers",
          icon="selftest", url=WIKI + "#genexercisepy-optional", conf="genexercise.conf",
          when="evo_nexus_name",
          params=(
              Param("exercise_type", "list", "Exercise Type",
                    "Quiet Exercise (reduced RPM, Hz and Voltage), Normal Exercise, Exercise "
                    "with Transfer Switch Activated.",
                    "Normal", "Quiet,Normal,Transfer"),
              Param("exercise_frequency", "list", "Exercise Frequency",
                    "Exercise Frequency options are Daily, Weekly, Biweekly,Monthly  or "
                    "Post-Controller (immediately after the controller exercise cycle). Hour, "
                    "Minute, Month, Day of Week are ignored if Post-Controller exercise "
                    "frequency is enabled.",
                    "Monthly", "Daily,Weekly,Biweekly,Monthly,Post-Controller"),
              Param("use_gen_time", "boolean", "Use Generator Time",
                    "Enable to use the generator time for the exercise cycle, otherwise it "
                    "will use the system time.",
                    False),
              Param("exercise_hour", "int", "Exercise Time Hour",
                    "The hour of the exercise time. Valid input is 0 - 23.",
                    12, "required digits range:0:23"),
              Param("exercise_minute", "int", "Exercise Time Minute",
                    "The minute of the exercise time.  Valid input is 0 - 59",
                    0, "required digits range:0:59"),
              Param("exercise_day_of_month", "int", "Exercise Day of Month",
                    "The day of month if monthly exercise is selected.",
                    1, "required digits range:1:28"),
              Param("exercise_day_of_week", "list", "Exercise Day of the Week",
                    "Exercise day of the week, if Weekly or Biweekly exercise frequency is "
                    "selected.",
                    "Monday", "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday"),
              Param("exercise_duration", "float", "Exercise Duration",
                    "The duration of the exercise time. Note: this time does not include "
                    "warmup time for Transfer type exercise cycles.",
                    12, "number range:5:60"),
              Param("exercise_warmup", "float", "Warmup Duration",
                    "The duration of the warmup time. Note: this time only applies to the "
                    "transfer type of exercise cycle. Zero will disable the warmup period.",
                    0, "number range:0:30"),
          )),
    AddOn("genemail2sms", "Mobile Carrier Email to SMS",
          "Send Genmon and utility state changes via carrier email to SMS service",
          icon="text", url=WIKI + "#genemail2smspy-optional", conf="genemail2sms.conf",
          params=(
              Param("destination", "string", "Email to SMS address",
                    "Email to SMS email recipient. Must be a valid email address",
                    "", "required email"),
          )
          + NOTIFY_PARAMS),
    AddOn("gencentriconnect", "Centri My Propane External Tank Fuel Monitor",
          "Integrates Centriconnect.com propane tank sensor data",
          icon="centri", url=WIKI + "#gencentriconnectpy-optional", conf="gencentriconnect.conf",
          params=(
              Param("user_id", "string", "User ID",
                    "User ID. Note that this is a long series of numbers and dashes in this "
                    "format: 36e551aa-c215-4c9b-8c70-ba7729687654",
                    "", "required min:36"),
              Param("device_id", "string", "Device ID",
                    "Device ID. Note that this is a long series of numbers and dashes in this "
                    "format: 36e551aa-c215-4c9b-8c70-ba7729687654",
                    "", "required min:36"),
              Param("device_auth", "password", "Device Authentication Code",
                    "Device Auth for Centri propane tank sensor. This number is provided in "
                    "the box with the sensor.",
                    "", "required min:6"),
              Param("poll_frequency", "int", "Poll Frequency",
                    "The duration in minutes between poll of tank data. Note this must be "
                    "equal or larger than 288 minutes as the maximum number of polls per day "
                    "is around 5.",
                    288, "number range:288:20000", read=float),
              Param("check_battery", "boolean", "Check Sensor Battery",
                    "If enabled, and email will be sent if the battery level on the sensor is "
                    "critical. Outbound email must be enabled for this to function.",
                    False),
              Param("check_reading", "boolean", "Check for Missed Readings",
                    "If enabled, and email will be sent if the sensor has not performed a "
                    "reading within 50 hours. Outbound email must be enabled for this to "
                    "function.",
                    False),
          )),
    AddOn("gentankutil", "External Tank Fuel Monitor",
          "Integrates tankutility.com propane tank sensor data",
          icon="tankutility", url=WIKI + "#gentankutilpy-optional", conf="gentankutil.conf",
          params=(
              Param("tank_name", "string", "Tank Name",
                    "Tank name as defined in tankutility.com",
                    "", "minmax:1:50"),
              Param("tank_name_2", "string", "Tank Name 2 (Optional)",
                    "Second tank name, if applicable",
                    "", "minmax:1:50"),
              Param("username", "string", "Username",
                    "Username at tankutility.com",
                    "", "required email"),
              Param("password", "password", "Password",
                    "Password at tankutility.com",
                    "", "minmax:4:50"),
              Param("poll_frequency", "float", "Poll Frequency",
                    "The duration in minutes between poll of tank data.",
                    60, "number"),
              Param("check_battery", "boolean", "Check Sensor Battery",
                    "If enabled, and email will be sent if the battery level on the sensor is "
                    "critical. Outbound email must be enabled for this to function.",
                    False),
              Param("check_reading", "boolean", "Check for Missed Readings",
                    "If enabled, and email will be sent if the sensor has not performed a "
                    "reading within 50 hours. Outbound email must be enabled for this to "
                    "function.",
                    False),
          )),
    AddOn("genneevo", "Nee Vo Tank Fuel Monitor",
          "Integrates Nee-Vo propane tank sensor data",
          icon="neevo", url=WIKI + "#genneevopy-optional", conf="genneevo.conf",
          params=(
              Param("tank_name", "string", "Tank Name",
                    "Tank name",
                    "Propane Tank", "minmax:1:50"),
              Param("username", "string", "Username",
                    "Username from Nee-vo app",
                    "", "required email"),
              Param("password", "password", "Password",
                    "Password from Nee-vo app",
                    "", "minmax:4:50"),
              Param("capacity", "int", "Tank Capacity (gallons)",
                    "Tank capacity in gallons. Set to 0 to use on line data.",
                    0, "number"),
              Param("serial_number", "string", "Serial Number",
                    "Optional: only use a specific tank by serial number (leave blank for "
                    "first tank)",
                    ""),
              Param("poll_frequency", "float", "Poll Frequency",
                    "The duration in minutes between poll of tank data.",
                    60, "number"),
          )),
    AddOn("gentankdiy", "DIY Fuel Tank Gauge Sensor",
          "Integrates DIY tank gauge sensor for Genmon",
          icon="rpi", url=WIKI + "#gentankdiypy-optional", conf="gentankdiy.conf", checks=("i2c",),
          params=(
              Param("poll_frequency", "float", "Poll Frequency",
                    "The duration in minutes between poll of tank data.",
                    60, "number"),
              Param("gauge_type", "list", "Sensor Type",
                    "DIY sensor type. Valid options are Type 1 and Type 2.",
                    "1", "1,2"),
          )),
    AddOn("genalexa", "Amazon Alexa voice commands",
          "Allow Amazon Alexa to start and stop the generator",
          icon="alexa", url=WIKI + "#genalexapy-optional", conf="genalexa.conf",
          params=(
              Param("name", "string", "Name for generator device",
                    "Name to call the generator device, i.e. 'generator'",
                    "generator", "minmax:4:50"),
          )),
    AddOn("gensnmp", "SNMP Support",
          "Allow Genmon to respond to SNMP requests",
          icon="snmp", url=WIKI + "#gensnmppy-optional", conf="gensnmp.conf",
          params=(
              Param("poll_frequency", "float", "Poll Interval",
                    "The time in seconds between requesting status from genmon. The default "
                    "value is 2 seconds.",
                    2.0, "number"),
              Param("enterpriseid", "int", "Enterprise ID",
                    "The enterprise ID used in the SNMP Object Identifier (OID). The genmon "
                    "SNMP enterprise ID is 58399.",
                    58399, "required digits"),
              Param("community", "string", "SNMP Community",
                    "SNMP Community string",
                    "public", "minmax:4:50"),
              Param("use_numeric", "boolean", "Numerics only",
                    "If enabled will return numeric values (no units) in the Status, "
                    "Maintenance (Evo/Nexus only) and Outage data.",
                    False),
              Param("use_integer", "boolean", "Force Integers",
                    "If enabled, integer values (no units) will be returned when applicable in "
                    "the Status, Maintenance (Evo/Nexus only) and Outage data. Enabling this "
                    "value also enables 'Use Numerics'. Floating point numeric values are "
                    "returned as strings",
                    False),
          )),
    AddOn("gentemp", "External Temperature Sensors",
          "Allow the display of external temperature sensor data",
          icon="rpi", url=WIKI + "#gentemppy-optional", conf="gentemp.conf", checks=("1wire",),
          params=(
              Param("poll_frequency", "float", "Poll Interval",
                    "The time in seconds that the temperature data is polled. The default "
                    "value is 2 seconds.",
                    2.0, "number"),
              Param("use_metric", "boolean", "Use Metric",
                    "enable to use Celsius, disable for Fahrenheit",
                    False),
              Param("blacklist", "string", "Sensor Device Blacklist",
                    "Comma separated blacklist. If these values are found in 1 wire temperature "
                    "sensor device names the sensor will be ignored.",
                    ""),
              Param("device_labels", "string", "Sensor Names",
                    "Comma separated list of sensor names. These names will be displayed for "
                    "each sensor. DS18B20 sensors are first, then type K thermocouples, each "
                    "in order of their device ID. "
                    "Blacklisted devices are skipped.",
                    ""),
              Param("device_nominal_values", "string", "Sensor Nominal Values",
                    "Comma separated list of nominal temperature values for the sensor. "
                    "Nominal values help determine where the gauge green area ends and the "
                    "yellow begins. The order of these values must match the order of the "
                    "Sensor Names. Leave blank to disable External Temp Sensor gauges.",
                    ""),
              Param("device_max_values", "string", "Sensor Maximum Values",
                    "Comma separated list of maximum temperature values for the sensor. This "
                    "is the maximum gauge value. The order of these values must match the "
                    "order of the Sensor Names. Leave blank to disable External Temp Sensor "
                    "gauges.",
                    ""),
              Param("device_min_values", "string", "Sensor Minimum Values",
                    "Comma separated list of minimum temperature values for the sensor. This "
                    "is the minimum gauge value. The order of these values must match the "
                    "order of the Sensor Names. Leave blank to set all sensors minimum value "
                    "to zero.",
                    ""),
          )),
    AddOn("gencthat", "External Current Transformer (CT) Sensors",
          "Support for Raspberry pi HAT with CTs from PintSize.me.",
          icon="rpi", url=WIKI + "#gencthatpy-optional", conf="gencthat.conf", checks=("spi1",),
          params=(
              Param("poll_frequency", "float", "Poll Interval",
                    "The time in seconds that the sensors are polled. The default value is 15 "
                    "seconds.",
                    15.0, "number"),
              Param("strict", "boolean", "Strict Usage of CT data",
                    "Set to true to only use the CT data if the generator utility line is in "
                    "an outage.",
                    False),
          )),
    AddOn("genmopeka", "Mopeka Pro Propane Tank Sensor",
          "Support Mopeka Pro Propane Tanks Sensor",
          icon="mopeka", url=WIKI + "#genmopekapy-optional", conf="genmopeka.conf",
          libraries=("fluids",),
          params=(
              Param("poll_frequency", "float", "Poll Interval",
                    "The time in minutes that the sensors are polled. The default value is 60 "
                    "minutes.",
                    60, "number"),
              Param("tank_address", "string", "Sensor Address",
                    "This value is MAC address of the sensor. It must be in a format using hex "
                    "numbers separated by colons (i.e. 9a:03:2b:67:25:12). Multiple tank "
                    "sensors (up to 4) may be used with commas between each address",
                    ""),
              Param("tank_type", "list", "Tank Size",
                    "Type of tank used. If Custom is used then Max and Min values must be "
                    "setup in /etc/genmon/genmopeka.conf",
                    "",
                    "20_LB,30_LB,40_LB,100_LB,200_LB,120_GAL,120_GAL_HORIZ,250_GAL,500_GAL,"
                    "1000_GAL,Custom"),
              Param("send_notices", "boolean", "Send Notices",
                    "Send email notices if unable to communicate with the senor or the sensor "
                    "battery is low. Note: outbound email must be setup for this to work.",
                    False),
          )),
    # Native Home Assistant integration
    AddOn("genhalink", "Home Assistant Integration (Native)",
          "Native Home Assistant integration via REST/WebSocket API. No MQTT broker required.",
          icon="homeassistant", url=WIKI + "#genhalinkpy-optional", conf="genhalink.conf",
          params=(
              Param("port", "int", "API Server Port",
                    "Port for the REST/WebSocket API server.",
                    9083, "required digits range:1024:65535"),
              Param("api_key", "readonly", "API Key (read-only)",
                    "API key for authentication (auto-generated). Copy this value into Home "
                    "Assistant when adding the integration.",
                    "", special="api_key"),
              Param("poll_interval", "int", "Poll Interval",
                    "Interval in seconds between polling genmon for status updates. Default is "
                    "3.",
                    3.0, "number", read=float),
              Param("blacklist", "string", "Excluded Data Paths",
                    "Comma-separated keywords to exclude from the API. Matches any data path "
                    "containing the keyword (case-insensitive). Top-level sections: Status, "
                    "Maintenance, Outage, Monitor, Tiles. Examples: 'Tiles' (UI tiles), "
                    "'Weather' (weather data), 'Platform Stats' (CPU/memory), 'Last Log "
                    "Entries' (log snippets). You can also target specific values like 'Serial "
                    "Number' or 'CRC Errors'.",
                    "Tiles"),
              Param("include_monitor_stats", "boolean", "Include Monitor Stats",
                    "Include monitor/platform statistics (CPU temp, WiFi, memory).",
                    True),
              Param("include_weather", "boolean", "Include Weather",
                    "Include weather data if available.",
                    True),
              Param("zeroconf_enabled", "boolean", "Zeroconf Discovery",
                    "Enable Zeroconf/mDNS broadcasting so Home Assistant can auto-discover "
                    "this generator. Disable for manual/fixed IP setup only.",
                    True),
          )),
    # Native Hubitat integration
    AddOn("genhubitat", "Native Hubitat Integration via REST/WebSocket API",
          "Native Hubitat integration via REST/WebSocket API. No MQTT broker required.",
          icon="hubitat", url=WIKI + "#genhubitatpy-optional", conf="genhubitat.conf",
          params=(
              Param("port", "int", "API Server Port",
                    "Port for the REST/WebSocket API server.",
                    9084, "required digits range:1024:65535"),
              Param("api_key", "readonly", "API Key (read-only)",
                    "API key for authentication (auto-generated). Copy this value into Hubitat "
                    "when adding the integration.",
                    "", special="api_key"),
              Param("poll_interval", "int", "Poll Interval",
                    "Interval in seconds between polling genmon for status updates. Default is "
                    "3.",
                    3.0, "number", read=float),
              Param("blacklist", "string", "Excluded Data Paths",
                    "Comma-separated keywords to exclude from the API, matching any data path "
                    "containing the keyword (case-insensitive). For the noisy diagnostics that "
                    "dominate the Hubitat event count (CPU temperature/usage, memory, disk, "
                    "WiFi signal), use the 'Include Monitor Stats' toggle instead; for outside "
                    "temperature and conditions, use 'Include Weather'. Use this field for "
                    "individual values those toggles don't cover, such as 'Battery Voltage' or "
                    "'Battery Charger Current', or to drop a single field while keeping the "
                    "rest of the monitor stats. The default 'Tiles' excludes the web UI's tile "
                    "data, which Hubitat does not use.",
                    "Tiles"),
              Param("include_monitor_stats", "boolean", "Include Monitor Stats",
                    "Include monitor/platform statistics (CPU temp, WiFi, memory).",
                    True),
              Param("include_weather", "boolean", "Include Weather",
                    "Include weather data if available.",
                    True),
          )),
    AddOn("genotodata", "Otodata TM6030 Propane Tank Sensor",
          "Support Otodata TM6030 Propane Tank Sensor",
          icon="otodata", url=WIKI + "#genotodatapy-optional", conf="genotodata.conf",
          libraries=("bleak",),
          params=(
              Param("tank_name", "string", "Tank Name",
                    "Display name for this tank in the genmon web interface.",
                    "Propane Tank"),
              Param("capacity", "int", "Tank Capacity (gallons)",
                    "Tank capacity in gallons. Set to 0 to omit from genmon data.",
                    0, "number"),
              Param("poll_frequency", "int", "Poll Interval (minutes)",
                    "The time in minutes between BLE scan cycles. Default is 5 minutes.",
                    5, "number"),
              Param("scan_time", "float", "Scan Duration (seconds)",
                    "Seconds to listen for BLE advertisements per scan cycle. Increase if the "
                    "sensor is far from the Pi.",
                    30.0, "number"),
              Param("mac_address", "string", "Sensor MAC Address",
                    "Optional: restrict readings to a specific sensor MAC address (e.g. "
                    "aa:bb:cc:dd:ee:ff). Leave blank to use the first Otodata device found.",
                    ""),
          )),
)

