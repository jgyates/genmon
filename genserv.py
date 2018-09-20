#-------------------------------------------------------------------------------
#    FILE: genserv.py
# PURPOSE: Flask app for generator monitor web app
#
#  AUTHOR: Jason G Yates
#    DATE: 20-Dec-2016
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

from __future__ import print_function

try:
    from flask import Flask, render_template, request, jsonify, session
except:
    print("\n\nThis program requires the Flask library. Please see the project documentation at https://github.com/jgyates/genmon.\n")
    sys.exit(2)

import sys, signal, os, socket, atexit, time, subprocess, json, threading, signal, errno, collections

try:
    from genmonlib import mylog, myclient, myconfig
except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the original github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)


import urlparse
import re, httplib, datetime


#-------------------------------------------------------------------------------
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
MAIL_SECTION = "MyMail"
GENMON_CONFIG = "/etc/genmon.conf"
GENMON_SECTION = "GenMon"
GENLOADER_CONFIG = "/etc/genloader.conf"

Closing = False
Restarting = False
ControllerType = "generac_evo_nexus"
CriticalLock = threading.Lock()
CachedToolTips = {}
CachedRegisterDescriptions = {}

#-------------------------------------------------------------------------------
@app.after_request
def add_header(r):
    """
    Force cache header
    """
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, public, max-age=0"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"

    return r
#-------------------------------------------------------------------------------
@app.route('/', methods=['GET'])
def root():

    if HTTPAuthUser != None and HTTPAuthPass != None:
        if not session.get('logged_in'):
            return render_template('login.html')
        else:
            return app.send_static_file('index.html')
    else:
        return app.send_static_file('index.html')

#-------------------------------------------------------------------------------
@app.route('/internal', methods=['GET'])
def display_internal():

    if HTTPAuthUser != None and HTTPAuthPass != None:
        if not session.get('logged_in'):
            return render_template('login.html')
        else:
            return app.send_static_file('internal.html')
    else:
        return app.send_static_file('internal.html')

#-------------------------------------------------------------------------------
@app.route('/', methods=['POST'])
def do_admin_login():

    if request.form['password'] == HTTPAuthPass and request.form['username'] == HTTPAuthUser:
        session['logged_in'] = True
        session['write_access'] = True
        LogError("Admin Login")
        return root()
    elif request.form['password'] == HTTPAuthPass_RO and request.form['username'] == HTTPAuthUser_RO:
        session['logged_in'] = True
        session['write_access'] = False
        LogError("Limited Rights Login")
        return root()
    else:
        return render_template('login.html')

#-------------------------------------------------------------------------------
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

#-------------------------------------------------------------------------------
def ProcessCommand(command):

    try:
        if command in ["status", "status_json", "outage", "outage_json", "maint", "maint_json",
            "logs", "logs_json", "monitor", "monitor_json", "registers_json", "allregs_json",
            "start_info_json", "gui_status_json", "power_log_json", "power_log_clear",
            "getbase", "getsitename","setexercise", "setquiet", "setremote",
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
                LogError("Error on command function: " + str(e1))

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
                        LogErrorLine("Error in JSON parse / decode: " + str(e1))
                return data
            return jsonify(data)

        elif command in ["updatesoftware"]:
            if session.get('write_access', True):
                Update()
                return "OK"
            else:
                return "Access denied"

        elif command in ["getfavicon"]:
            return jsonify(favicon)

        elif command in ["notifications"]:
            data = ReadNotificationsFromFile()
            return jsonify(data)

        elif command in ["settings"]:
            if session.get('write_access', True):
                data =  ReadSettingsFromFile()
                return json.dumps(data, sort_keys = False)
            else:
                return "Access denied"

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
                Close()
                sys.exit(0)
        elif command in ["shutdown"]:
            if session.get('write_access', True):
                Shutdown()
                sys.exit(0)
        else:
            return render_template('command_template.html', command = command)
    except Exception as e1:
        LogErrorLine("Error in Process Command: " + str(e1))
        return render_template('command_template.html', command = command)

#-------------------------------------------------------------------------------
def SaveNotifications(query_string):

    '''
    email_recipient = email1@gmail.com,email2@gmail.com
    email1@gmail.com = outage,info
    email2@gmail.com = outage,info,error

    notifications = {'email1@gmail.com': ['outage,info'], 'email2@gmail.com': ['outage,info,error']}
    notifications_order_string = email1@gmail.com,email2@gmail.com

    or

    email_recipient = email1@gmail.com

    notifications = {'email1@gmail.com': ['']}
    notifications_order_string = email1@gmail.com

    '''
    notifications = dict(urlparse.parse_qs(query_string, 1))
    notifications_order_string = ",".join([v[0] for v in urlparse.parse_qsl(query_string, 1)])

    oldEmailsList = []
    oldNotifications = {}
    oldEmailRecipientString = ""
    try:
        with CriticalLock:
            # get existing settings
            if mymail_config.HasOption("email_recipient"):
                oldEmailRecipientString = mymail_config.ReadValue("email_recipient")
                oldEmailRecipientString.strip()
                oldEmailsList = oldEmailRecipientString.split(",")
                for oldEmailItem in oldEmailsList:
                    if mymail_config.HasOption(oldEmailItem):
                        oldNotifications[oldEmailItem] = mymail_config.ReadValue(oldEmailItem)

            # compare, remove notifications if needed
            for oldEmailItem in oldEmailsList:
                if not oldEmailItem in notifications.keys() and mymail_config.HasOption(oldEmailItem):
                    mymail_config.WriteValue(oldEmailItem, "", remove = True)

            # add / update the entries
            # update email recipient if needed
            if oldEmailRecipientString != notifications_order_string:
                mymail_config.WriteValue("email_recipient", notifications_order_string)

            # update catigories
            for newEmail, newCats in notifications.items():
                # remove catigories if needed from existing emails
                if not len(newCats[0]) and mymail_config.HasOption(newEmail):
                    mymail_config.WriteValue(newEmail, "", remove = True)
                # update or add catigories
                if len(newCats[0]):
                    mymail_config.WriteValue(newEmail, newCats[0])

        Restart()
    except Exception as e1:
        LogErrorLine("Error in SaveNotifications: " + str(e1))
    return

#-------------------------------------------------------------------------------
def ReadSingleConfigValue(filename, section, type, entry, default, bounds = None):

    try:

        if filename == GENMON_CONFIG:
            config = genmon_config
        elif filename == MAIL_CONFIG:
            config = mymail_config
        elif filename == GENLOADER_CONFIG:
            config = genloader_config
        else:
            LogError("Unknow file in UpdateConfigFile: " + filename)
            return default

        config.SetSection(section)

        if not config.HasOption(entry):
            return default

        if type.lower() == "string" or type == "password":
            return config.ReadValue(entry)
        elif type.lower() == "boolean":
            return config.ReadValue(entry, return_type = bool)
        elif type.lower() == "int":
            return config.ReadValue(entry, return_type = int)
        elif type.lower() == 'list':
            Value = config.ReadValue(entry)
            if bounds != None:
                DefaultList = bounds.split(",")
                if Value.lower() in (name.lower() for name in DefaultList):
                    return Value
                else:
                    LogError("Error Reading Config File (value not in list): %s : %s" % (entry,Value))
                return default
            else:
                LogError("Error Reading Config File (bounds not provided): %s : %s" % (entry,Value))
                return default
        else:
            LogError("Error Reading Config File (unknown type): %s : %s" % (entry,type))
            return default

    except Exception as e1:
        LogErrorLine("Error Reading Config File (ReadSingleConfigValue): " + str(e1))
        return default

#-------------------------------------------------------------------------------
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
        EmailsStr = mymail_config.ReadValue("email_recipient")

        for email in EmailsStr.split(","):
            email = email.strip()
            EmailsToNotify.append(email)

        SortOrder = 1
        for email in EmailsToNotify:
            Notify = mymail_config.ReadValue(email, default = "")
            if Notify == "":
                NotificationSettings[email] = [SortOrder]
            else:
                NotificationSettings[email] = [SortOrder, Notify]
    except Exception as e1:
        LogErrorLine("Error in ReadNotificationsFromFile: " + str(e1))

    return NotificationSettings

#-------------------------------------------------------------------------------
def ReadSettingsFromFile():

    ### array containing information on the parameters
    ## 1st: type of attribute
    ## 2nd: Attribute title
    ## 3rd: Sort Key
    ## 4th: current value (will be populated further below)
    ## 5th: tooltip (will be populated further below)
    ## 6th: validation rule if type is string or int (see below). If type is list, this is a comma delimited list of options
    ## 7th: Config file
    ## 8th: config file section
    ## 9th: config file entry name
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


    ConfigSettings =  collections.OrderedDict()
    ConfigSettings["sitename"] = ['string', 'Site Name', 1, "SiteName", "", "required minmax:4:50", GENMON_CONFIG, GENMON_SECTION, "sitename"]
    ConfigSettings["port"] = ['string', 'Port for Serial Communication', 2, "/dev/serial0", "", "required UnixDevice", GENMON_CONFIG, GENMON_SECTION, "port"]
    # This option is not displayed as it will break the link between genmon and genserv
    #ConfigSettings["server_port"] = ['int', 'Server Port', 5, 9082, "", 0, GENMON_CONFIG, GENMON_SECTION,"server_port"]
    # this option is not displayed as this will break the modbus comms, only for debugging
    #ConfigSettings["address"] = ['string', 'Modbus slave address', 6, "9d", "", 0 , GENMON_CONFIG, GENMON_SECTION, "address"]
    #ConfigSettings["loglocation"] = ['string', 'Log Directory', 7, "/var/log/", "", "required UnixDir", GENMON_CONFIG, GENMON_SECTION, "loglocation"]
    #ConfigSettings["enabledebug"] = ['boolean', 'Enable Debug', 14, False, "", 0, GENMON_CONFIG, GENMON_SECTION, "enabledebug"]
    # These settings are not displayed as the auto-detect controller will set these
    # these are only to be used to override the auto-detect
    #ConfigSettings["uselegacysetexercise"] = ['boolean', 'Use Legacy Exercise Time', 43, False, "", 0, GENMON_CONFIG, GENMON_SECTION, "uselegacysetexercise"]
    #ConfigSettings["liquidcooled"] = ['boolean', 'Liquid Cooled', 41, False, "", 0, GENMON_CONFIG, GENMON_SECTION, "liquidcooled"]
    #ConfigSettings["evolutioncontroller"] = ['boolean', 'Evolution Controler', 42, True, "", 0, GENMON_CONFIG, GENMON_SECTION, "evolutioncontroller"]
    # remove outage log, this will always be in the same location
    #ConfigSettings["outagelog"] = ['string', 'Outage Log', 8, "/home/pi/genmon/outage.txt", "", 0, GENMON_CONFIG, GENMON_SECTION, "outagelog"]

    if ControllerType != 'h_100':
        ConfigSettings["disableoutagecheck"] = ['boolean', 'Do Not Check for Outages', 17, False, "", "", GENMON_CONFIG, GENMON_SECTION, "disableoutagecheck"]
        
    ConfigSettings["syncdst"] = ['boolean', 'Sync Daylight Savings Time', 22, False, "", "", GENMON_CONFIG, GENMON_SECTION, "syncdst"]
    ConfigSettings["synctime"] = ['boolean', 'Sync Time', 23, False, "", "", GENMON_CONFIG, GENMON_SECTION, "synctime"]
    ConfigSettings["metricweather"] = ['boolean', 'Use Metric Units', 24, False, "", "", GENMON_CONFIG, GENMON_SECTION, "metricweather"]
    ConfigSettings["optimizeforslowercpu"] = ['boolean', 'Optimize for slower CPUs', 25, False, "", "", GENMON_CONFIG, GENMON_SECTION, "optimizeforslowercpu"]
    ConfigSettings["autofeedback"] = ['boolean', 'Automated Feedback', 29, False, "", "", GENMON_CONFIG, GENMON_SECTION, "autofeedback"]
    ConfigSettings["gensyslog"] = ['boolean', 'Status Changes to System Log', 30, False, "", "", GENLOADER_CONFIG, "gensyslog", "enable"]

    ConfigSettings["nominalfrequency"] = ['list', 'Rated Frequency', 101, "60", "", "50,60", GENMON_CONFIG, GENMON_SECTION, "nominalfrequency"]
    ConfigSettings["nominalrpm"] = ['int', 'Nominal RPM', 102, "3600", "", "required digits range:1500:4000", GENMON_CONFIG, GENMON_SECTION, "nominalrpm"]
    ConfigSettings["nominalkw"] = ['int', 'Maximum kW Output', 103, "22", "", "required digits range:0:1000", GENMON_CONFIG, GENMON_SECTION, "nominalkw"]
    ConfigSettings["fueltype"] = ['list', 'Fuel Type', 104, "Natural Gas", "", "Natural Gas,Propane,Diesel,Gasoline", GENMON_CONFIG, GENMON_SECTION, "fueltype"]
    ConfigSettings["tanksize"] = ['int', 'Fuel Tank Size', 105, "0", "", "required digits range:0:2000", GENMON_CONFIG, GENMON_SECTION, "tanksize"]
    if ControllerType == 'h_100':
        Choices = "120/208,120/240,230/400,240/415,277/480,347/600"
        ConfigSettings["voltageconfiguration"] = ['list', 'Line to Neutral / Line to Line', 105, "277/480", "", Choices, GENMON_CONFIG, GENMON_SECTION, "voltageconfiguration"]
        ConfigSettings["nominalbattery"] = ['list', 'Nomonal Battery Voltage', 106, "24", "", "12,24", GENMON_CONFIG, GENMON_SECTION, "nominalbattery"]
    else: #ControllerType == "generac_evo_nexus":
        ConfigSettings["enhancedexercise"] = ['boolean', 'Enhanced Exercise Time', 105, False, "", "", GENMON_CONFIG, GENMON_SECTION, "enhancedexercise"]

    ConfigSettings["displayunknown"] = ['boolean', 'Display Unknown Sensors', 111, False, "", "", GENMON_CONFIG, GENMON_SECTION, "displayunknown"]

    # These do not appear to work on reload, some issue with Flask
    ConfigSettings["usehttps"] = ['boolean', 'Use Secure Web Settings', 200, False, "", "", GENMON_CONFIG, GENMON_SECTION, "usehttps"]
    ConfigSettings["useselfsignedcert"] = ['boolean', 'Use Self-signed Certificate', 203, True, "", "", GENMON_CONFIG, GENMON_SECTION, "useselfsignedcert"]
    ConfigSettings["keyfile"] = ['string', 'https Key File', 204, "", "", "UnixFile", GENMON_CONFIG, GENMON_SECTION, "keyfile"]
    ConfigSettings["certfile"] = ['string', 'https Certificate File', 205, "", "", "UnixFile", GENMON_CONFIG, GENMON_SECTION, "certfile"]
    ConfigSettings["http_user"] = ['string', 'Web Username', 206, "", "", "minmax:4:50", GENMON_CONFIG, GENMON_SECTION, "http_user"]
    ConfigSettings["http_pass"] = ['string', 'Web Password', 207, "", "", "minmax:4:50", GENMON_CONFIG, GENMON_SECTION, "http_pass"]
    ConfigSettings["http_user_ro"] = ['string', 'Limited Rights User Username', 208, "", "", "minmax:4:50", GENMON_CONFIG, GENMON_SECTION, "http_user_ro"]
    ConfigSettings["http_pass_ro"] = ['string', 'Limited Rights User Password', 209, "", "", "minmax:4:50", GENMON_CONFIG, GENMON_SECTION, "http_pass_ro"]
    ConfigSettings["http_port"] = ['int', 'Port of WebServer', 210, 8000, "", "required digits", GENMON_CONFIG, GENMON_SECTION, "http_port"]
    ConfigSettings["favicon"] = ['string', 'FavIcon', 220, "", "", "minmax:8:255", GENMON_CONFIG, GENMON_SECTION, "favicon"]
    # This does not appear to work on reload, some issue with Flask

    #
    #ConfigSettings["disableemail"] = ['boolean', 'Disable Email Usage', 300, True, "", "", MAIL_CONFIG, MAIL_SECTION, "disableemail"]
    ConfigSettings["disablesmtp"] = ['boolean', 'Disable Sending Email', 300, False, "", "", MAIL_CONFIG, MAIL_SECTION, "disablesmtp"]
    ConfigSettings["email_account"] = ['string', 'Email Account', 301, "myemail@gmail.com", "", "minmax:3:50", MAIL_CONFIG, MAIL_SECTION, "email_account"]
    ConfigSettings["email_pw"] = ['password', 'Email Password', 302, "password", "", "max:50", MAIL_CONFIG, MAIL_SECTION, "email_pw"]
    ConfigSettings["sender_account"] = ['string', 'Sender Account', 303, "no-reply@gmail.com", "", "email", MAIL_CONFIG, MAIL_SECTION, "sender_account"]
    # email_recipient setting will be handled on the notification screen
    ConfigSettings["smtp_server"] = ['string', 'SMTP Server <br><small>(leave emtpy to disable)</small>', 305, "smtp.gmail.com", "", "InternetAddress", MAIL_CONFIG, MAIL_SECTION, "smtp_server"]
    ConfigSettings["smtp_port"] = ['int', 'SMTP Server Port', 307, 587, "", "digits", MAIL_CONFIG, MAIL_SECTION, "smtp_port"]
    ConfigSettings["ssl_enabled"] = ['boolean', 'SMTP Server SSL Enabled', 308, False, "", "", MAIL_CONFIG, MAIL_SECTION, "ssl_enabled"]

    ConfigSettings["disableimap"] = ['boolean', 'Disable Receiving Email', 400, False, "", "", MAIL_CONFIG, MAIL_SECTION, "disableimap"]
    ConfigSettings["imap_server"] = ['string', 'IMAP Server <br><small>(leave emtpy to disable)</small>', 401, "imap.gmail.com", "", "InternetAddress", MAIL_CONFIG, MAIL_SECTION, "imap_server"]
    ConfigSettings["readonlyemailcommands"] = ['boolean', 'Disable Email Write Commands',402, False, "", "", GENMON_CONFIG, GENMON_SECTION, "readonlyemailcommands"]
    ConfigSettings["incoming_mail_folder"] = ['string', 'Incoming Mail Folder<br><small>(if IMAP enabled)</small>', 403, "Generator", "", "minmax:1:1500", GENMON_CONFIG, GENMON_SECTION, "incoming_mail_folder"]
    ConfigSettings["processed_mail_folder"] = ['string', 'Mail Processed Folder<br><small>(if IMAP enabled)</small>', 404, "Generator/Processed","", "minmax:1:255", GENMON_CONFIG, GENMON_SECTION, "processed_mail_folder"]

    ConfigSettings["disableweather"] = ['boolean', 'Disable Weather Functionality', 500, False, "", "", GENMON_CONFIG, GENMON_SECTION, "disableweather"]
    ConfigSettings["weatherkey"] = ['string', 'Openweathermap.org API key', 501, "", "", "required minmax:4:50", GENMON_CONFIG, GENMON_SECTION, "weatherkey"]
    ConfigSettings["weatherlocation"] = ['string', 'Location to report weather', 502, "", "", "required minmax:4:50", GENMON_CONFIG, GENMON_SECTION, "weatherlocation"]
    ConfigSettings["minimumweatherinfo"] = ['boolean', 'Display Minimum Weather Info', 504, True, "", "", GENMON_CONFIG, GENMON_SECTION, "minimumweatherinfo"]

    try:
        # Get all the config values
        for entry, List in ConfigSettings.items():
            if List[6] == GENMON_CONFIG:
                (ConfigSettings[entry])[3] = ReadSingleConfigValue(GENMON_CONFIG, "GenMon", List[0], List[8], List[3], List[5])
            elif List[6] == MAIL_CONFIG:
                (ConfigSettings[entry])[3] = ReadSingleConfigValue(MAIL_CONFIG, "MyMail", List[0], List[8], List[3])
            elif List[6] == GENLOADER_CONFIG:
                (ConfigSettings[entry])[3] = ReadSingleConfigValue(GENLOADER_CONFIG, List[7], List[0], List[8], List[3])

        GetToolTips(ConfigSettings)
    except Exception as e1:
        LogErrorLine("Error in ReadSettingsFromFile: " + entry + ": "+ str(e1))

    return ConfigSettings


#-------------------------------------------------------------------------------
def GetAllConfigValues(FileName, section):

    ReturnDict = {}
    try:
        config = myconfig.MyConfig(filename = FileName, section = section)

        for (key, value) in config.GetList():
            ReturnDict[key.lower()] = value
    except Exception as e1:
        LogErrorLine("Error GetAllConfigValues: " + FileName + ": "+ str(e1) )

    return ReturnDict

#-------------------------------------------------------------------------------
def CacheToolTips():

    global CachedToolTips
    global ControllerType
    global CachedRegisterDescriptions

    try:
        config_section = "generac_evo_nexus"
        pathtofile = os.path.dirname(os.path.realpath(__file__))

        # get controller used
        if genmon_config.HasOption('controllertype'):
            config_section = genmon_config.ReadValue('controllertype')
        else:
            config_section = "generac_evo_nexus"

        if not len(config_section):
            config_section = "generac_evo_nexus"

        ControllerType = config_section

        CachedRegisterDescriptions = GetAllConfigValues(pathtofile + "/tooltips.txt", config_section)

        CachedToolTips = GetAllConfigValues(pathtofile + "/tooltips.txt", "ToolTips")

    except Exception as e1:
        LogErrorLine("Error reading tooltips.txt " + str(e1) )

#-------------------------------------------------------------------------------
def GetToolTips(ConfigSettings):

    try:
        pathtofile = os.path.dirname(os.path.realpath(__file__))
        for entry, List in ConfigSettings.items():
            try:
                (ConfigSettings[entry])[4] = CachedToolTips[entry.lower()]
            except:
                pass    # TODO

    except Exception as e1:
        LogErrorLine("Error in GetToolTips: " + str(e1))

#-------------------------------------------------------------------------------
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
                    Section = CurrentConfigSettings[Entry][7]
                else:
                    LogError("Invalid setting: " + str(Entry))
                    continue
                UpdateConfigFile(ConfigFile,Section, Entry, Value)
        Restart()
    except Exception as e1:
        LogErrorLine("Error Update Config File (SaveSettings): " + str(e1))

#---------------------MySupport::UpdateConfigFile-------------------------------
# Add or update config item
def UpdateConfigFile(FileName, section, Entry, Value):

    try:

        if FileName == GENMON_CONFIG:
            config = genmon_config
        elif FileName == MAIL_CONFIG:
            config = mymail_config
        elif FileName == GENLOADER_CONFIG:
            config = genloader_config
        else:
            LogError("Unknow file in UpdateConfigFile: " + FileName)
            return False

        config.SetSection(section)
        return config.WriteValue(Entry, Value)

    except Exception as e1:
        LogErrorLine("Error Update Config File (UpdateConfigFile): " + str(e1))
        return False

#-------------------------------------------------------------------------------
# This will shutdown the pi
def Shutdown():
    os.system("sudo shutdown -h now")
#-------------------------------------------------------------------------------
# This will restart the Flask App
def Restart():

    global Restarting

    Restarting = True
    if not RunBashScript("startgenmon.sh restart"):
        LogError("Error in Restart")

#-------------------------------------------------------------------------------
def Update():
    # update
    if not RunBashScript("genmonmaint.sh updatenp"):   # update no prompt
        LogError("Error in Update")
    # now restart
    Restart()

#-------------------------------------------------------------------------------
def RunBashScript(ScriptName):
    try:
        pathtoscript = os.path.dirname(os.path.realpath(__file__))
        command = "/bin/bash "
        LogError("Script: " + command + pathtoscript + "/" + ScriptName)
        subprocess.call(command + pathtoscript + "/" + ScriptName, shell=True)
        return True

    except Exception as e1:
        LogErrorLine("Error in RunBashScript: (" + ScriptName + ") : " + str(e1))
        return False

#-------------------------------------------------------------------------------
# return False if File not present
def CheckCertFiles(CertFile, KeyFile):

    try:
        with open(CertFile,"r") as MyCertFile:
            with open(KeyFile,"r") as MyKeyFile:
                return True
    except Exception as e1:
        LogErrorLine("Error in CheckCertFiles: Unable to open Cert or Key file: " + CertFile + ", " + KeyFile + " : "+ str(e1))
        return False

    return True
#-------------------------------------------------------------------------------
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

        # heartbeat server port, must match value in check_generator_system.py and any calling client apps
        if genmon_config.HasOption('server_port'):
            clientport = genmon_config.ReadValue('server_port', return_type = int, default = 0)

        if genmon_config.HasOption('loglocation'):
            loglocation = genmon_config.ReadValue('loglocation')

        # log errors in this module to a file
        log = mylog.SetupLogger("genserv", loglocation + "genserv.log")

        if genmon_config.HasOption('usehttps'):
            bUseSecureHTTP = genmon_config.ReadValue('usehttps', return_type = bool)

        if genmon_config.HasOption('http_port'):
            HTTPPort = genmon_config.ReadValue('http_port', return_type = int, default = 8000)

        if genmon_config.HasOption('favicon'):
            favicon = genmon_config.ReadValue('favicon')

        # user name and password require usehttps = True
        if bUseSecureHTTP:
            if genmon_config.HasOption('http_user'):
                HTTPAuthUser = genmon_config.ReadValue('http_user', default = "")
                HTTPAuthUser = HTTPAuthUser.strip()
                 # No user name or pass specified, disable
                if HTTPAuthUser == "":
                    HTTPAuthUser = None
                    HTTPAuthPass = None
                elif genmon_config.HasOption('http_pass'):
                    HTTPAuthPass = genmon_config.ReadValue('http_pass', default = "")
                    HTTPAuthPass = HTTPAuthPass.strip()
                if HTTPAuthUser != None and HTTPAuthPass != None:
                    if genmon_config.HasOption('http_user_ro'):
                        HTTPAuthUser_RO = genmon_config.ReadValue('http_user_ro', default = "")
                        HTTPAuthUser_RO = HTTPAuthUser_RO.strip()
                        if HTTPAuthUser_RO == "":
                            HTTPAuthUser_RO = None
                            HTTPAuthPass_RO = None
                        elif genmon_config.HasOption('http_pass_ro'):
                            HTTPAuthPass_RO = genmon_config.ReadValue('http_pass_ro', default = "")
                            HTTPAuthPass_RO = HTTPAuthPass_RO.strip()

            HTTPSPort = genmon_config.ReadValue('https_port', return_type = int, default = 443)

        if bUseSecureHTTP:
            app.secret_key = os.urandom(12)
            OldHTTPPort = HTTPPort
            HTTPPort = HTTPSPort
            if genmon_config.HasOption('useselfsignedcert'):
                bUseSelfSignedCert = genmon_config.ReadValue('useselfsignedcert', return_type = bool)

                if bUseSelfSignedCert:
                    SSLContext = 'adhoc'
                else:
                    if genmon_config.HasOption('certfile') and genmon_config.HasOption('keyfile'):
                        CertFile = genmon_config.ReadValue('certfile')
                        KeyFile = genmon_config.ReadValue('keyfile')
                        if CheckCertFiles(CertFile, KeyFile):
                            SSLContext = (CertFile, KeyFile)    # tuple
                        else:
                            HTTPPort = OldHTTPPort
                            SSLContext = None
            else:
                # if we get here then usehttps is enabled but not option for useselfsignedcert
                # so revert to HTTP
                HTTPPort = OldHTTPPort

        return True
    except Exception as e1:
        LogConsole("Missing config file or config file entries: " + str(e1))
        return False

#---------------------LogConsole------------------------------------------------
def LogConsole( Message):
    if not console == None:
        console.error(Message)

#---------------------LogError--------------------------------------------------
def LogError(Message):
    if not log == None:
        log.error(Message)
#---------------------FatalError------------------------------------------------
def FatalError(Message):
    if not log == None:
        log.error(Message)
    raise Exception(Message)
#---------------------LogErrorLine----------------------------------------------
def LogErrorLine(Message):
    if not log == None:
        LogError(Message + " : " + GetErrorLine())

#---------------------GetErrorLine----------------------------------------------
def GetErrorLine():
    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    lineno = exc_tb.tb_lineno
    return fname + ":" + str(lineno)

#-------------------------------------------------------------------------------
def Close(NoExit = False):

    global Closing

    if Closing:
        return
    Closing = True
    try:
        '''
        LogError("Close server..")

        with app.app_context():
            func = request.environ.get('werkzeug.server.shutdown')
            if func is None:
                LogError("Not running with the Werkzeug Server")
            func()

            LogError("Server closed.")
        '''

        MyClientInterface.Close()
    except Exception as e1:
        LogErrorLine("Error in close: " + str(e1))

    LogError("genserv closed.")
    if not NoExit:
        sys.exit(0)

#-------------------------------------------------------------------------------
if __name__ == "__main__":
    address='localhost' if len(sys.argv) <=2 else sys.argv[1]

    ConfigFilePath='/etc/' if len(sys.argv) <=3 else sys.argv[2]

    MAIL_CONFIG = ConfigFilePath + "mymail.conf"
    GENMON_CONFIG = ConfigFilePath + "genmon.conf"

    # NOTE: signal handler is not compatible with the exception handler around app.run()
    #atexit.register(Close)
    #signal.signal(signal.SIGTERM, Close)
    #signal.signal(signal.SIGINT, Close)

    # log errors in this module to a file
    console = mylog.SetupLogger("genserv_console", log_file = "", stream = True)

    if os.geteuid() != 0:
        LogConsole("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'.")
        sys.exit(1)

    if not os.path.isfile(GENMON_CONFIG):
        LogConsole("Missing config file : " + GENMON_CONFIG)
        sys.exit(1)

    if not os.path.isfile(MAIL_CONFIG):
        LogConsole("Missing config file : " + MAIL_CONFIG)
        sys.exit(1)

    genmon_config = myconfig.MyConfig(filename = GENMON_CONFIG, section = GENMON_SECTION, log = console)
    mymail_config = myconfig.MyConfig(filename = MAIL_CONFIG, section = MAIL_SECTION, log = console)
    genloader_config = myconfig.MyConfig(filename = GENLOADER_CONFIG, section = "genmon", log = console)

    AppPath = sys.argv[0]
    if not LoadConfig():
        LogConsole("Error reading configuraiton file.")
        sys.exit(1)

    genmon_config.log = log
    mymail_config.log = log
    genloader_config.log = log

    LogError("Starting " + AppPath + ", Port:" + str(HTTPPort) + ", Secure HTTP: " + str(bUseSecureHTTP) + ", SelfSignedCert: " + str(bUseSelfSignedCert))

    # validate needed files are present
    filename = os.path.dirname(os.path.realpath(__file__)) + "/startgenmon.sh"
    if not os.path.isfile(filename):
        LogError("Required file missing : startgenmon.sh")
        sys.exit(1)

    filename = os.path.dirname(os.path.realpath(__file__)) + "/genmonmaint.sh"
    if not os.path.isfile(filename):
        LogError("Required file missing : genmonmaint.sh")
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
                LogConsole("Error: genmon not loaded.")
                sys.exit(1)
            time.sleep(1)
            continue

    Start = datetime.datetime.now()

    while ((datetime.datetime.now() - Start).total_seconds() < 10):
        data = MyClientInterface.ProcessMonitorCommand("generator: gethealth")
        if "OK" in data:
            LogConsole(" OK - Init complete.")
            break

    while True:
        try:
            app.run(host="0.0.0.0", port=HTTPPort, threaded = True, ssl_context=SSLContext, use_reloader = False, debug = False)

        except Exception as e1:
            LogErrorLine("Error in app.run: " + str(e1))
            if e1.errno != errno.EADDRINUSE:   #Errno 98
                sys.exit(0)
            time.sleep(2)
            if Closing:
                sys.exit(0)
            Restart()
