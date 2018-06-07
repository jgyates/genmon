#------------------------------------------------------------
#    FILE: genserv.py
# PURPOSE: Flask app for generator monitor web app
#
#  AUTHOR: Jason G Yates
#    DATE: 20-Dec-2016
#
# MODIFICATIONS:
#------------------------------------------------------------

from __future__ import print_function

from flask import Flask, render_template, request, jsonify, session
import sys, signal, os, socket, atexit, time, subprocess, json, threading, signal
from genmonlib import mylog, myclient, mythread
import urlparse
import re, httplib, datetime

try:
    from ConfigParser import RawConfigParser
except ImportError as e:
    from configparser import RawConfigParser

#------------------------------------------------------------
app = Flask(__name__,static_url_path='')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 300

HTTPAuthUser = None
HTTPAuthPass = None
HTTPAuthUser_RO = None
HTTPAuthPass_RO = None

bUseSecureHTTP = False
bUseSelfSignedCert = True
SSLContext = None
HTTPPort = 8000
loglocation = "/var/log/"
clientport = 0
log = None
console = None
AppPath = ""
favicon = "favicon.ico"
ConfigFilePath = "/etc/"
MAIL_CONFIG = "/etc/mymail.conf"
GENMON_CONFIG = "/etc/genmon.conf"
Closing = False
Restarting = False
CriticalLock = threading.Lock()
CachedToolTips = {}
CachedRegisterDescriptions = {}

#------------------------------------------------------------
@app.after_request
def add_header(r):
    """
    Force cache header
    """
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, public, max-age=0"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"

    return r
#------------------------------------------------------------
@app.route('/', methods=['GET'])
def root():

    if HTTPAuthUser != None and HTTPAuthPass != None:
        if not session.get('logged_in'):
            return render_template('login.html')
        else:
            return app.send_static_file('index.html')
    else:
        return app.send_static_file('index.html')

#------------------------------------------------------------
@app.route('/internal', methods=['GET'])
def display_internal():

    if HTTPAuthUser != None and HTTPAuthPass != None:
        if not session.get('logged_in'):
            return render_template('login.html')
        else:
            return app.send_static_file('internal.html')
    else:
        return app.send_static_file('internal.html')

#------------------------------------------------------------
@app.route('/', methods=['POST'])
def do_admin_login():

    if request.form['password'] == HTTPAuthPass and request.form['username'] == HTTPAuthUser:
        session['logged_in'] = True
        session['write_access'] = True
        log.info("Admin Login")
        return root()
    elif request.form['password'] == HTTPAuthPass_RO and request.form['username'] == HTTPAuthUser_RO:
        session['logged_in'] = True
        session['write_access'] = False
        log.info("Limited Rights Login")
        return root()
    else:
        return render_template('login.html')

#------------------------------------------------------------
@app.route("/cmd/<command>")
def command(command):

    if Closing or Restarting:
        return jsonify("Closing")
    if HTTPAuthUser == None or HTTPAuthPass == None:
        return ProcessCommand(command)

    if not session.get('logged_in'):
        return render_template('login.html')
    else:
        return ProcessCommand(command)

#------------------------------------------------------------
def ProcessCommand(command):

    try:
        if command in ["status", "status_json", "outage", "outage_json", "maint", "maint_json",
            "logs", "logs_json", "monitor", "monitor_json", "registers_json", "allregs_json",
            "start_info_json", "gui_status_json", "power_log_json", "power_log_clear",
            "getbase", "getsitename","setexercise", "setquiet", "getexercise", "setremote",
            "settime", "sendregisters", "sendlogfiles", "getdebug" ]:
            finalcommand = "generator: " + command

            try:
                if command in ["setexercise", "setquiet", "setremote"] and not session.get('write_access', True):
                    return jsonify("Read Only Mode")

                if command == "setexercise":
                    settimestr = request.args.get('setexercise', 0, type=str)
                    if settimestr:
                        finalcommand += "=" + settimestr
                elif command == "setquiet":
                    # /cmd/setquiet?setquiet=off
                    setquietstr = request.args.get('setquiet', 0, type=str)
                    if setquietstr:
                        finalcommand += "=" + setquietstr
                elif command == "setremote":
                    setremotestr = request.args.get('setremote', 0, type=str)
                    if setremotestr:
                        finalcommand += "=" + setremotestr

                if command == "power_log_json":
                    # example: /cmd/power_log_json?power_log_json=1440
                    setlogstr = request.args.get('power_log_json', 0, type=str)
                    if setlogstr:
                        finalcommand += "=" + setlogstr
                data = MyClientInterface.ProcessMonitorCommand(finalcommand)

            except Exception as e1:
                data = "Retry"
                log.error("Error on command function: " + str(e1))

            if command in ["status_json", "outage_json", "maint_json", "monitor_json", "logs_json",
                "registers_json", "allregs_json", "start_info_json", "gui_status_json", "power_log_json"]:

                if command in ["start_info_json"]:
                    try:
                        StartInfo = json.loads(data)
                        StartInfo["write_access"] = session.get('write_access', True)
                        if not StartInfo["write_access"]:
                            StartInfo["pages"]["settings"] = False
                            StartInfo["pages"]["notifications"] = False
                        data = json.dumps(StartInfo, sort_keys=False)
                    except Exception as e1:
                        log.error("Error in JSON parse / decode: " + str(e1))
                return data
            return jsonify(data)

        elif command in ["updatesoftware"]:
            if session.get('write_access', True):
                Update()
            return "OK"

        elif command in ["getfavicon"]:
            return jsonify(favicon)

        elif command in ["notifications"]:
            data = ReadNotificationsFromFile()
            return jsonify(data)

        elif command in ["settings"]:
            data =  ReadSettingsFromFile()
            return jsonify(data)

        elif command in ["setnotifications"]:
            if session.get('write_access', True):
                SaveNotifications(request.args.get('setnotifications', 0, type=str))
            return "OK"

        elif command in ["setsettings"]:
            if session.get('write_access', True):
                SaveSettings(request.args.get('setsettings', 0, type=str))
            return "OK"

        elif command in ["getreglabels"]:
            return jsonify(CachedRegisterDescriptions)

        elif command in ["restart"]:
            if session.get('write_access', True):
                Restart()
        elif command in ["stop"]:
            if session.get('write_access', True):
                sys.exit(0)
        else:
            return render_template('command_template.html', command = command)
    except Exception as e1:
        log.error("Error in Process Command: " + str(e1))
        return render_template('command_template.html', command = command)

#------------------------------------------------------------
def SaveNotifications(query_string):
    notifications = dict(urlparse.parse_qs(query_string, 1))
    oldEmails = []

    notifications_order_string = ",".join([v[0] for v in urlparse.parse_qsl(query_string, 1)])

    try:
        with CriticalLock:
            # Read contents from file as a single string
            file_handle = open(MAIL_CONFIG, 'r')
            file_string = file_handle.read()
            file_handle.close()

            for line in file_string.splitlines():
               if not line.isspace():
                  parts = findConfigLine(line)
                  if (parts and (len(parts) >= 5) and parts[3] and (not parts[3].isspace()) and parts[2] and (parts[2] == "email_recipient")):
                     oldEmails = parts[4].split(",")

            activeSection = 0
            skip = 0
            # Write contents to file.
            # Using mode 'w' truncates the file.
            file_handle = open(MAIL_CONFIG, 'w')
            for line in file_string.splitlines():
               if not line.isspace():
                  parts = findConfigLine(line)
                  if (activeSection == 1):
                      if (parts and (len(parts) >= 5) and parts[3] and (not parts[3].isspace()) and parts[2] and (parts[2] in oldEmails)):
                          #skip line to delete previous configuration
                          skip = 1
                      else:
                          #lets write the new configuration
                          for email in notifications.keys():
                              if (notifications[email][0].strip() != ""):
                                 line = email + " = " + notifications[email][0] + "\n" + line
                          activeSection = 0
                  elif (parts and (len(parts) >= 5) and parts[3] and (not parts[3].isspace()) and parts[2] and (parts[2] == "email_recipient")):
                      myList = list(parts)
                      myList[1] = ""
                      myList[4] = notifications_order_string
                      line = "".join(myList)
                      activeSection = 1
               else:
                  if (activeSection == 1):
                     for email in notifications.keys():
                        if (notifications[email][0].strip() != ""):
                           line = email + " = " + notifications[email][0] + "\n" + line
                     activeSection = 0

               if (skip == 0):
                 file_handle.write(line+"\n")
               skip = 0

            file_handle.close()
        Restart()

    except Exception as e1:
        log.error("Error Update Config File: " + str(e1))

#------------------------------------------------------------
def ReadSingleConfigValue(file, section, type, entry, default, bounds = None):

    try:
        config = RawConfigParser()
        # config parser reads from current directory, when running form a cron tab this is
        # not defined so we specify the full path
        config.read(file)

        if not config.has_option(section, entry):
            return default

        if type.lower() == "string" or type == "password":
            return config.get(section, entry)
        elif type.lower() == "boolean":
            return config.getboolean(section, entry)
        elif type.lower() == "int":
            return config.getint(section, entry)
        elif type.lower() == 'list':
            Value = config.get(section, entry)
            if bounds != None:
                DefaultList = bounds.split(",")
                if Value.lower() in (name.lower() for name in DefaultList):
                    return Value
                else:
                    log.error("Error Reading Config File (value not in list): %s : %s" % (entry,Value))
                return default
            else:
                log.error("Error Reading Config File (bounds not provided): %s : %s" % (entry,Value))
                return default
        else:
            log.error("Error Reading Config File (unknown type): %s : %s" % (entry,type))
            return default

    except Exception as e1:
        log.error("Error Reading Config File (ReadSingleConfigValue): " + str(e1))
        return default

#------------------------------------------------------------
def ReadNotificationsFromFile():


    ### array containing information on the parameters
    ## 1st: email address
    ## 2nd: sort order, aka row number
    ## 3rd: comma delimited list of notidications that are enabled
    NotificationSettings = {}
    # e.g. {'myemail@gmail.com': [1]}
    # e.g. {'myemail@gmail.com': [1, 'error,warn,info']}

    EmailsToNotify = []
    try:
        # There should be only one "email_recipient" entry
        EmailsStr = ReadSingleConfigValue(MAIL_CONFIG, "MyMail", "string", "email_recipient", "")

        for email in EmailsStr.split(","):
            email = email.strip()
            EmailsToNotify.append(email)

        SortOrder = 1
        for email in EmailsToNotify:
            Notify = ReadSingleConfigValue(MAIL_CONFIG, "MyMail", "string", email, "")
            if Notify == "":
                NotificationSettings[email] = [SortOrder]
            else:
                NotificationSettings[email] = [SortOrder, Notify]
    except Exception as e1:
        log.error("Error in ReadNotificationsFromFile: " + str(e1))

    return NotificationSettings

#------------------------------------------------------------
def ReadSettingsFromFile():

    ### array containing information on the parameters
    ## 1st: type of attribute
    ## 2nd: Attribute title
    ## 3rd: Sort Key
    ## 4th: current value (will be populated further below)
    ## 5th: tooltip (will be populated further below)
    ## 6th: validation rule if type is string or int (see below). If type is list, this is a comma delimited list of options
    ## 7th: Config file
    ## Validation Rules:
    ##         A rule must be in this format rule:param where rule is the name of the rule and param is a rule parameter,
    ##         for example minmax:10:50 will use the minmax rule with two arguments, 10 and 50.
    ##             required: The field is required. Only works with text inputs.
    ##             digits: Only digits.
    ##             number: Must be a number.
    ##             username: Must be between 4 and 32 characters long and start with a letter. You may use letters, numbers, underscores, and one dot.
    ##             email: Must be a valid email.
    ##             pass: Must be at least 6 characters long, and contain at least one number, one uppercase and one lowercase letter.
    ##             strongpass: Must be at least 8 characters long and contain at least one uppercase and one lowercase letter and one number or special character.
    ##             phone: Must be a valid US phone number.
    ##             zip: Must be a valid US zip code
    ##             url: Must be a valid URL.
    ##             range:min:max: Must be a number between min and max. Usually combined with number or digits.
    ##             min:min: Must be at least min characters long.
    ##             max:max: Must be no more that max characters long.
    ##             minmax:min:max: Must be between min and max characters long.
    ##             minoption:min: Must have at least min checkboxes or radios selected.
    ##             maxoption:max: Must have no more than max checkboxes or radios selected.
    ##             select:default: Make a select required, where default is the value of the default option.
    ##             extension:ext: Validates file inputs. You can have as many ext as you want.
    ##             equalto:name: Must be equal to another field where name is the name of the field.
    ##             date:format: Must a valid date in any format. The default is mm/dd/yyyy but you can pass any format with any separator, ie. date:yyyy-mm-dd.
    ##             InternetAddress: url without http in front.
    ##             UnixFile: Unix file file.
    ##             UnixDir: Unix file path.
    ##             UnixDevice: Unix file path starting with /dev/.


    ConfigSettings =  {
                "sitename" : ['string', 'Site Name', 1, "SiteName", "", "required minmax:4:50", GENMON_CONFIG],
                "port" : ['string', 'Port for Serial Communication', 2, "/dev/serial0", "", "required UnixDevice", GENMON_CONFIG],
                # This option is not displayed as it will break the link between genmon and genserv
                #"server_port" : ['int', 'Server Port', 5, 9082, "", 0, GENMON_CONFIG],
                # this option is not displayed as this will break the modbus comms, only for debugging
                #"address" : ['string', 'Modbus slave address', 6, "9d", "", 0 , GENMON_CONFIG],
                #"loglocation" : ['string', 'Log Directory', 7, "/var/log/", "", "required UnixDir", GENMON_CONFIG],
                #"enabledebug" : ['boolean', 'Enable Debug', 14, False, "", 0, GENMON_CONFIG],
                "disableoutagecheck" : ['boolean', 'Do Not Check for Outages', 17, False, "", "", GENMON_CONFIG],
                # These settings are not displayed as the auto-detect controller will set these
                # these are only to be used to override the auto-detect
                #"uselegacysetexercise" : ['boolean', 'Use Legacy Exercise Time', 43, False, "", 0, GENMON_CONFIG],
                #"liquidcooled" : ['boolean', 'Liquid Cooled', 41, False, "", 0, GENMON_CONFIG],
                #"evolutioncontroller" : ['boolean', 'Evolution Controler', 42, True, "", 0, GENMON_CONFIG],
                # remove outage log, this will always be in the same location
                #"outagelog" : ['string', 'Outage Log', 8, "/home/pi/genmon/outage.txt", "", 0, GENMON_CONFIG],
                "syncdst" : ['boolean', 'Sync Daylight Savings Time', 22, False, "", "", GENMON_CONFIG],
                "synctime" : ['boolean', 'Sync Time', 23, False, "", "", GENMON_CONFIG],
                "metricweather"  : ['boolean', 'Use Metric Units', 24, False, "", "", GENMON_CONFIG],
                "autofeedback" : ['boolean', 'Automated Feedback', 29, False, "", "", GENMON_CONFIG],

                #"model" : ['string', 'Generator Model', 100, "Generic Evolution Air Cooled", "", 0],
                "nominalfrequency": ['list', 'Rated Frequency', 101, "60", "", "50,60", GENMON_CONFIG],
                "nominalRPM" : ['int', 'Nominal RPM', 102, "3600", "", "required digits range:1500:4000", GENMON_CONFIG],
                "nominalKW": ['int', 'Maximum kW Output', 103, "22", "", "required digits range:1:700", GENMON_CONFIG],
                "fueltype" : ['list', 'Fuel Type', 104, "Natural Gas", "", "Natural Gas,Propane,Diesel,Gasoline", GENMON_CONFIG],

                #
                "enhancedexercise" : ['boolean', 'Enhanced Exercise Time', 105, False, "", "", GENMON_CONFIG],
                "displayunknown" : ['boolean', 'Display Unknown Sensors', 106, False, "", "", GENMON_CONFIG],

                # These do not appear to work on reload, some issue with Flask
                "usehttps" : ['boolean', 'Use Secure Web Settings', 200, False, "", "", GENMON_CONFIG],
                "useselfsignedcert" : ['boolean', 'Use Self-signed Certificate', 203, True, "", "", GENMON_CONFIG],
                "keyfile" : ['string', 'https Key File', 204, "", "", "UnixFile", GENMON_CONFIG],
                "certfile" : ['string', 'https Certificate File', 205, "", "", "UnixFile", GENMON_CONFIG],
                "http_user" : ['string', 'Web Username', 206, "", "", "minmax:4:50", GENMON_CONFIG],
                "http_pass" : ['string', 'Web Password', 207, "", "", "minmax:4:50", GENMON_CONFIG],
                #"http_user_ro" : ['string', 'Limited User Web Username', 208, "", "", "minmax:4:50", GENMON_CONFIG],
                #"http_pass_ro" : ['string', 'Limited User Web Password', 209, "", "", "minmax:4:50", GENMON_CONFIG],
                "http_port" : ['int', 'Port of WebServer', 210, 8000, "", "required digits", GENMON_CONFIG],
                "favicon" : ['string', 'FavIcon', 220, "", "", "minmax:8:255", GENMON_CONFIG],
                # This does not appear to work on reload, some issue with Flask

                # TODO Michael : remove disableemail, uncomment disablesmtp, disableimap and disablesmtp
                "disableemail" : ['boolean', 'Disable Email Usage', 300, True, "", "", MAIL_CONFIG],
                #"disablesmtp"  : ['boolean', 'Disable Sending Email', 300, True, "", "", MAIL_CONFIG],
                "email_account" : ['string', 'Email Account', 301, "myemail@gmail.com", "", "minmax:3:50", MAIL_CONFIG],
                "email_pw" : ['password', 'Email Password', 302, "password", "", "max:50", MAIL_CONFIG],
                "sender_account" : ['string', 'Sender Account', 303, "no-reply@gmail.com", "", "email", MAIL_CONFIG],
                # "email_recipient" : ['string', 'Email Recepient<br><small>(comma delimited)</small>', 105], # will be handled on the notification screen
                "smtp_server" : ['string', 'SMTP Server <br><small>(leave emtpy to disable)</small>', 305, "smtp.gmail.com", "", "InternetAddress", MAIL_CONFIG],
                "smtp_port" : ['int', 'SMTP Server Port', 307, 587, "", "digits", MAIL_CONFIG],
                "ssl_enabled" : ['boolean', 'SMTP Server SSL Enabled', 308, False, "", "", MAIL_CONFIG],

                #"disableimap"  : ['boolean', 'Disable Receiving Email', 400, True, "", "", MAIL_CONFIG],
                "imap_server" : ['string', 'IMAP Server <br><small>(leave emtpy to disable)</small>', 401, "imap.gmail.com", "", "InternetAddress", MAIL_CONFIG],
                "readonlyemailcommands" : ['boolean', 'Disable Email Write Commands',402, False, "", "", GENMON_CONFIG],
                "incoming_mail_folder" : ['string', 'Incoming Mail Folder<br><small>(if IMAP enabled)</small>', 403, "Generator", "", "minmax:1:1500", GENMON_CONFIG],
                "processed_mail_folder" : ['string', 'Mail Processed Folder<br><small>(if IMAP enabled)</small>', 404, "Generator/Processed","", "minmax:1:255", GENMON_CONFIG],

                #"disableweather"  : ['boolean', 'Disable Weather Functionality', 500, True, "", "", GENMON_CONFIG],
                "weatherkey" : ['string', 'Openweathermap.org API key', 501, "", "", "required minmax:4:50", GENMON_CONFIG],
                "weatherlocation" : ['string', 'Location to report weather', 502, "", "", "required minmax:4:50", GENMON_CONFIG],
                "minimumweatherinfo"  : ['boolean', 'Display Minimum Weather Info', 504, True, "", "", GENMON_CONFIG]
                }

    try:
        # TODO optimize this
        #MailConfig = GetAllConfigValues(MAIL_CONFIG, "MyMail")
        #GenmonConfig = GetAllConfigValues(GENMON_CONFIG, "GenMon")

        for entry, List in ConfigSettings.items():
            (ConfigSettings[entry])[3] = ReadSingleConfigValue(GENMON_CONFIG, "GenMon", List[0], entry, List[3], List[5])

        for entry, List in ConfigSettings.items():
            (ConfigSettings[entry])[3] = ReadSingleConfigValue(MAIL_CONFIG, "MyMail", List[0], entry, List[3])

        GetToolTips(ConfigSettings)
    except Exception as e1:
        log.error("Error in ReadSettingsFromFile: " + str(e1))

    return ConfigSettings


#------------------------------------------------------------
def GetRegisterDescriptions():

    ReturnDict = {}
    try:
        for (key, value) in CachedRegisterDescriptions.items():
            ReturnDict[key] = value
    except Exception as e1:
        log.error("Error in GetRegisterDescriptions: " + str(e1))
    return ReturnDict

#------------------------------------------------------------
def GetAllConfigValues(FileName, section):

    ReturnDict = {}
    try:
        config = RawConfigParser()
        config.read(FileName)
        for (key, value) in config.items(section):
            ReturnDict[key.lower()] = value
    except Exception as e1:
        log.error("Error GetAllConfigValues: " + FileName + ": "+ str(e1) )

    return ReturnDict

#------------------------------------------------------------
def CacheToolTips():

    global CachedToolTips

    try:
        config_section = "generac_evo_nexus"
        pathtofile = os.path.dirname(os.path.realpath(__file__))

        # get controller used
        config = RawConfigParser()
        config.read(GENMON_CONFIG)
        if config.has_option("GenMon", 'controllertype'):
            config_section = config.get("GenMon", 'controllertype')
        else:
            config_section = "generac_evo_nexus"

        CachedRegisterDescriptions = GetAllConfigValues(pathtofile + "/tooltips.txt", config_section)

        CachedToolTips = GetAllConfigValues(pathtofile + "/tooltips.txt", "ToolTips")

    except Exception as e1:
        log.error("Error reading tooltips.txt " + str(e1) )

#------------------------------------------------------------
def GetToolTips(ConfigSettings):

    try:
        pathtofile = os.path.dirname(os.path.realpath(__file__))
        for entry, List in ConfigSettings.items():
            (ConfigSettings[entry])[4] = CachedToolTips[entry.lower()]

    except Exception as e1:
        log.error("Error in GetToolTips: " + str(e1))

#------------------------------------------------------------
def SaveSettings(query_string):

    try:

        # e.g. {'displayunknown': ['true']}
        settings = dict(urlparse.parse_qs(query_string, 1))
        if not len(settings):
            # nothing to change
            return
        CurrentConfigSettings = ReadSettingsFromFile()
        with CriticalLock:
            for Entry in settings.keys():
                ConfigEntry = CurrentConfigSettings.get(Entry, None)
                if ConfigEntry != None:
                    ConfigFile = CurrentConfigSettings[Entry][6]
                    Value = settings[Entry][0]
                else:
                    log.error("Invalid setting: " + str(Entry))
                    continue
                UpdateConfigFile(ConfigFile,Entry, Value)
        Restart()
    except Exception as e1:
        log.error("Error Update Config File (SaveSettings): " + str(e1))
#------------------------------------------------------------
# THIS CAN BE REMOVED
def SaveSettings2(query_string):

    # e.g. {'displayunknown': ['true']}
    settings = dict(urlparse.parse_qs(query_string, 1))

    try:
        for configFile in [MAIL_CONFIG, GENMON_CONFIG]:
            # Read contents from file as a single string
            file_handle = open(configFile, 'r')
            file_string = file_handle.read()
            file_handle.close()

            # Write contents to file.
            # Using mode 'w' truncates the file.
            file_handle = open(configFile, 'w')
            for line in file_string.splitlines():
                if not line.isspace():
                    parts = findConfigLine(line)
                    for setting in settings.keys():
                        if (parts and (len(parts) >= 5) and parts[3] and (not parts[3].isspace()) and parts[2] and (parts[2] == setting)):
                            myList = list(parts)
                            if ((parts[1] is not None) and (not parts[1].isspace())):
                                # remove comment
                                myList[1] = ""
                            elif (parts[1] is None):
                                myList[1] = ""
                            myList[4] = settings[setting][0]
                            line = "".join(myList)
                file_handle.write(line+"\n")
            file_handle.close()
        Restart()
    except Exception as e1:
        log.error("Error Update Config File (SaveSettings): " + str(e1))

#---------------------MySupport::UpdateConfigFile------------------------
# Add or update config item
def UpdateConfigFile(FileName, Entry, Value):

    try:

        Found = False
        ConfigFile = open(FileName,'r')
        FileString = ConfigFile.read()
        ConfigFile.close()

        ConfigFile = open(FileName,'w')
        for line in FileString.splitlines():
            if not line.isspace():                  # blank lines
                newLine = line.strip()              # strip leading spaces
                if len(newLine):
                    if not newLine[0] == "#":           # not a comment
                        items = newLine.split(' ')      # split items in line by spaces
                        for strings in items:           # loop thru items
                            strings = strings.strip()   # strip any whitespace
                            if Entry == strings or strings.lower().startswith(Entry+"="):        # is this our value?
                                line = Entry + " = " + Value    # replace it
                                Found = True
                                break

            ConfigFile.write(line+"\n")
        if not Found:
            ConfigFile.write(Entry + " = " + Value + "\n")
        ConfigFile.close()
        return True

    except Exception as e1:
        log.error("Error in UpdateConfigFile: " + str(e1))
        return False

#------------------------------------------------------------
def findConfigLine(line):
    match = re.search(
        r"""^          # Anchor to start of line
        (\s*)          # $1: Zero or more leading ws chars
        (?:(\#\s*)?)   # $2: is it commented out
        (?:            # Begin group for optional var=value.
          (\S+)        # $3: Variable name. One or more non-spaces.
          (\s*=\s*)    # $4: Assignment operator, optional ws
          (            # $5: Everything up to comment or EOL.
            [^#\\]*    # Unrolling the loop 1st normal*.
            (?:        # Begin (special normal*)* construct.
              \\.      # special is backslash-anything.
              [^#\\]*  # More normal*.
            )*         # End (special normal*)* construct.
          )            # End $5: Value.
        )?             # End group for optional var=value.
        ((?:\#.*)?)    # $6: Optional comment.
        $              # Anchor to end of line""",
        line, re.MULTILINE | re.VERBOSE)
    if match :
      return match.groups()
    else:
      return []

#------------------------------------------------------------
# This will restart the Flask App
def Restart():

    global Restarting

    Restarting = True
    if not RunBashScript("startgenmon.sh restart"):
        log.error("Error in Restart")

#------------------------------------------------------------
def RestartThread():

    time.sleep(0.25)
    if not RunBashScript("startgenmon.sh restart"):
        log.error("Error in Restart")

#------------------------------------------------------------
# This will restart the Flask App
def StartRestart():

    ThreadObj = threading.Thread(target = RestartThread, name = "RestartThread")
    ThreadObj.daemon = True
    ThreadObj.start()       # start thread


#------------------------------------------------------------
def Update():
    # update
    if not RunBashScript("genmonmaint.sh updatenp"):   # update no prompt
        log.error("Error in Update")
    # now restart
    Restart()

#------------------------------------------------------------
def RunBashScript(ScriptName):
    try:
        pathtoscript = os.path.dirname(os.path.realpath(__file__))
        command = "/bin/bash "
        log.error("Script: " + command + pathtoscript + "/" + ScriptName)
        subprocess.call(command + pathtoscript + "/" + ScriptName, shell=True)
        return True

    except Exception as e1:
        log.error("Error in RunBashScript: (" + ScriptName + ") : " + str(e1))
        return False

#------------------------------------------------------------
# return False if File not present
def CheckCertFiles(CertFile, KeyFile):

    try:
        with open(CertFile,"r") as MyCertFile:
            with open(KeyFile,"r") as MyKeyFile:
                return True
    except Exception as e1:
        log.error("Error in CheckCertFiles: Unable to open Cert or Key file: " + CertFile + ", " + KeyFile + " : "+ str(e1))
        return False

    return True
#------------------------------------------------------------
def LoadConfig():

    global log
    global clientport
    global loglocation
    global bUseSecureHTTP
    global HTTPPort
    global HTTPAuthUser
    global HTTPAuthPass
    global HTTPAuthUser_RO
    global HTTPAuthPass_RO
    global SSLContext
    global favicon

    HTTPAuthPass = None
    HTTPAuthUser = None
    SSLContext = None
    try:
        config = RawConfigParser()
        # config parser reads from current directory, when running form a cron tab this is
        # not defined so we specify the full path
        config.read(GENMON_CONFIG)

        # heartbeat server port, must match value in check_generator_system.py and any calling client apps
        if config.has_option('GenMon', 'server_port'):
            clientport = config.getint('GenMon', 'server_port')

        if config.has_option('GenMon', 'loglocation'):
            loglocation = config.get("GenMon", 'loglocation')

        # log errors in this module to a file
        log = mylog.SetupLogger("genserv", loglocation + "genserv.log")

        if config.has_option('GenMon', 'usehttps'):
            bUseSecureHTTP = config.getboolean('GenMon', 'usehttps')

        if config.has_option('GenMon', 'http_port'):
            HTTPPort = config.getint('GenMon', 'http_port')

        if config.has_option('GenMon', 'favicon'):
            favicon = config.get('GenMon', 'favicon')

        # user name and password require usehttps = True
        if bUseSecureHTTP:
            if config.has_option('GenMon', 'http_user'):
                HTTPAuthUser = config.get('GenMon', 'http_user')
                HTTPAuthUser = HTTPAuthUser.strip()
                 # No user name or pass specified, disable
                if HTTPAuthUser == "":
                    HTTPAuthUser = None
                    HTTPAuthPass = None
                elif config.has_option('GenMon', 'http_pass'):
                    HTTPAuthPass = config.get('GenMon', 'http_pass')
                    HTTPAuthPass = HTTPAuthPass.strip()
                if HTTPAuthUser != None and HTTPAuthPass != None:
                    if config.has_option('GenMon', 'http_user_ro'):
                        HTTPAuthUser_RO = config.get('GenMon', 'http_user_ro')
                        HTTPAuthUser_RO = HTTPAuthUser_RO.strip()
                        if HTTPAuthUser_RO == "":
                            HTTPAuthUser_RO = None
                            HTTPAuthPass_RO = None
                        elif config.has_option('GenMon', 'http_pass_ro'):
                            HTTPAuthPass_RO = config.get('GenMon', 'http_pass_ro')
                            HTTPAuthPass_RO = HTTPAuthPass_RO.strip()

        if bUseSecureHTTP:
            app.secret_key = os.urandom(12)
            OldHTTPPort = HTTPPort
            HTTPPort = 443
            if config.has_option('GenMon', 'useselfsignedcert'):
                bUseSelfSignedCert = config.getboolean('GenMon', 'useselfsignedcert')

                if bUseSelfSignedCert:
                    SSLContext = 'adhoc'
                else:
                    if config.has_option('GenMon', 'certfile') and config.has_option('GenMon', 'keyfile'):
                        CertFile = config.get('GenMon', 'certfile')
                        KeyFile = config.get('GenMon', 'keyfile')
                        if CheckCertFiles(CertFile, KeyFile):
                            SSLContext = (CertFile, KeyFile)    # tuple
                        else:
                            HTTPPort = OldHTTPPort
                            SSLContext = None
            else:
                # if we get here then usehttps is enabled but not option for useselfsignedcert
                # so revert to HTTP
                HTTPPort = OldHTTPPort

    except Exception as e1:
        log.error("Missing config file or config file entries: " + str(e1))

#------------------------------------------------------------
def ValidateFilePresent(FileName):
    try:
        with open(FileName,"r") as TestFile:     #
            return True
    except Exception as e1:
            log.error("File (%s) not present." % FileName)
            return False
#------------------------------------------------------------
def Close(NoExit = False):

    global Closing
    if Closing:
        return
    Closing = True
    log.error("Close server..")
    try:
        with app.app_context():
            func = request.environ.get('werkzeug.server.shutdown')
            if func is None:
                log.error("Not running with the Werkzeug Server")
            func()
    except Exception as e1:
        log.error("Error in close: " + str(e1))

    log.error("Server closed.")
    if not NoExit:
        sys.exit(0)

#------------------------------------------------------------
if __name__ == "__main__":
    address='localhost' if len(sys.argv) <=2 else sys.argv[1]

    ConfigFilePath='/etc/' if len(sys.argv) <=3 else sys.argv[2]

    MAIL_CONFIG = ConfigFilePath + "mymail.conf"
    GENMON_CONFIG = ConfigFilePath + "genmon.conf"

    #atexit.register(Close)
    #signal.signal(signal.SIGTERM, Close)

    AppPath = sys.argv[0]
    LoadConfig()

    # log errors in this module to a file
    console = mylog.SetupLogger("genserv_console", log_file = "", stream = True)

    log.info("Starting " + AppPath + ", Port:" + str(HTTPPort) + ", Secure HTTP: " + str(bUseSecureHTTP) + ", SelfSignedCert: " + str(bUseSelfSignedCert))

    # validate needed files are present
    file = os.path.dirname(os.path.realpath(__file__)) + "/startgenmon.sh"
    if not ValidateFilePresent(file):
        log.error("Required file missing : startgenmon.sh")
        sys.exit(1)

    file = os.path.dirname(os.path.realpath(__file__)) + "/genmonmaint.sh"
    if not ValidateFilePresent(file):
        log.error("Required file missing : genmonmaint.sh")
        sys.exit(1)

    CacheToolTips()

    startcount = 0
    while startcount <= 4:
        try:
            MyClientInterface = myclient.ClientInterface(host = address,port=clientport, log = log)
            break
        except Exception as e1:
            startcount += 1
            if startcount >= 4:
                console.error("Error: genmon not loaded.")
                sys.exit(1)
            time.sleep(1)
            continue

    Start = datetime.datetime.now()

    while ((datetime.datetime.now() - Start).total_seconds() < 10):
        data = MyClientInterface.ProcessMonitorCommand("generator: gethealth")
        if "OK" in data:
            console.info(" OK - Init complete.")
            break

    while True:
        try:
            app.run(host="0.0.0.0", port=HTTPPort, threaded = True, ssl_context=SSLContext, use_reloader = False, debug = False)

        except Exception as e1:
            log.error("Error in app.run:" + str(e1))
            time.sleep(2)
            Restart()
