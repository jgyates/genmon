#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: genserv.py
# PURPOSE: Flask app for generator monitor web app
#
#  AUTHOR: Jason G Yates
#    DATE: 20-Dec-2016
#
# MODIFICATIONS:
#------------------------------------------------------------

from flask import Flask, render_template, request, jsonify, session
import sys, signal, os, socket, atexit, time, subprocess
import mylog, myclient, mythread
import urlparse
import re

try:
    from ConfigParser import RawConfigParser
except ImportError as e:
    from configparser import RawConfigParser

#------------------------------------------------------------
app = Flask(__name__,static_url_path='')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 300

HTTPAuthUser = None
HTTPAuthPass = None
bUseSecureHTTP = False
bUseSelfSignedCert = True
SSLContext = None
HTTPPort = 8000
loglocation = "/var/log/"
clientport = 0
log = None
AppPath = ""

MAIL_CONFIG = "/etc/mymail.conf"
GENMON_CONFIG = "/etc/genmon.conf"

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
        return root()
    else:
        return render_template('login.html')

#------------------------------------------------------------
@app.route("/cmd/<command>")
def command(command):

    if HTTPAuthUser == None or HTTPAuthPass == None:
        return ProcessCommand(command)

    if not session.get('logged_in'):
               return render_template('login.html')
    else:
        return ProcessCommand(command)

#------------------------------------------------------------
def ProcessCommand(command):

    if command in ["status", "status_json", "outage", "outage_json", "maint", "maint_json", "logs", "logs_json", "monitor", "monitor_json", "registers_json", "allregs_json", "getbase", "getsitename", "setexercise", "setquiet", "getexercise","setremote", "settime", "reload"]:
        finalcommand = "generator: " + command
        try:
            if command == "setexercise":
                settimestr = request.args.get('setexercise', 0, type=str)
                finalcommand += "=" + settimestr
            if command == "setquiet":
                setquietstr = request.args.get('setquiet', 0, type=str)
                finalcommand += "=" + setquietstr
            if command == "setremote":
                setremotestr = request.args.get('setremote', 0, type=str)
                finalcommand += "=" + setremotestr

            data = MyClientInterface.ProcessMonitorCommand(finalcommand)

        except Exception as e1:
            data = "Retry"
            log.error("Error on command function" + str(e1))

        if command == "reload":
                Reload()                # reload Flask App

        if command in ["status_json", "outage_json", "maint_json", "monitor_json", "logs_json", "registers_json", "allregs_json"]:
            return data
        return jsonify(data)

    elif command in ["update"]:
        Update()
        return "OK"

    elif command in ["notifications"]:
        data = ReadNotificationsFromFile()
        return jsonify(data)

    elif command in ["settings"]:
        data =  ReadSettingsFromFile()
        return jsonify(data)

    elif command in ["setnotifications"]:
        SaveNotifications(request.args.get('setnotifications', 0, type=str));
        return "OK"

    elif command in ["setsettings"]:
        # SaveSettings((request.args.get('setsettings', 0, type=str)));
        SaveSettings(request.args.get('setsettings', 0, type=str));
        return "OK"

    else:
        return render_template('command_template.html', command = command)

#------------------------------------------------------------
def SaveNotifications(query_string):
    notifications = dict(urlparse.parse_qs(query_string, 1))
    oldEmails = []

    notifications_order_string = ",".join([v[0] for v in urlparse.parse_qsl(query_string, 1)])

    try:
        # Read contents from file as a single string
        file_handle = open(MAIL_CONFIG, 'r')
        file_string = file_handle.read()
        file_handle.close()

        for line in file_string.splitlines():
           if not line.isspace():
              parts = findConfigLine(line)
              if (parts and (len(parts) >= 5) and parts[3] and (not parts[3].isspace()) and parts[2] and (parts[2] == "email_recipient")):
                 oldEmails = parts[4].split(",")

        activeSection = 0;
        skip = 0;
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
                  activeSection = 1;
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
        #MyClientInterface.ProcessMonitorCommand("generator: reload")
        #Reload()
        Restart()

    except Exception as e1:
        log.error("Error Update Config File: " + str(e1))

#------------------------------------------------------------
def ReadSingleConfigValue(file, section, type, entry, default):

    try:
        config = RawConfigParser()
        # config parser reads from current directory, when running form a cron tab this is
        # not defined so we specify the full path
        config.read(file)

        if not config.has_option(section, entry):
            return default

        if type == "string":
            return config.get(section, entry)
        elif type == "boolean":
            return config.getboolean(section, entry)
        elif type == "int":
            return config.getint(section, entry)
        else:
            return default

    except Exception as e1:
        log.error("Error Reading Config File (ReadSingleConfigValue): " + str(e1))
        return default

#------------------------------------------------------------
def WriteSignleConfigValue(file, section, entry, value, remove = False):

    try:
        config = RawConfigParser()
        config.read(file)

        if remove:
            if config.has_option(section, entry):
                config.remove_option(section, entry)
        else:
            config.set(section, entry, str(value))

        # Writing our configuration file disk
        with open(file, 'wb') as configfile:
            config.write(configfile)

    except Exception as e1:
        log.error("Error Writing Config File (WriteSignleConfigValue): " + str(e1))

#------------------------------------------------------------
def WriteNotificationsToFile(query_string):

    # TODO merge query_string
    # e.g. {'displayunknown': ['true']}
    settings = dict(urlparse.parse_qs(query_string, 1))

    NotificationSettings = ReadNotificationsFromFile()

    EmailList = []
    for email, Notifications in NotificationSettings.items():
        EmailList.append(email)
        if len(Notifications):
            NoticeString = ",".join(Notifications )
            WriteSignleConfigValue(MAIL_CONFIG, "MyMail", email, NoticeString)
        else:
            # if no explicit notification, remove the notification entry (all notifications)
            WriteSignleConfigValue(MAIL_CONFIG, "MyMail", email, "", remove = True)

    EmailsString = ",".join(EmailList )

    WriteSignleConfigValue(MAIL_CONFIG, "MyMail", "email_recipient", EmailsString)

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

    return NotificationSettings

#------------------------------------------------------------
def ReadSettingsFromFile():

    ### array containing information on the parameters
    ## 1st: type of attribute
    ## 2nd: Attribute title
    ## 3rd: Sort Key
    ## 4th: current value (will be populated further below)
    ## 5th: tooltip (will be populated further below)
    ## 6th: parameter is currently disabled (will be populated further below)
    ConfigSettings =  {
                "sitename" : ['string', 'Site Name', 1, "SiteName", "", 0],
                "port" : ['string', 'Port for Serial Communication', 2, "/dev/serial0", "", 0],
                "incoming_mail_folder" : ['string', 'Incoming Mail folder<br><small>(if IMAP enabled)</small>', 151, "Generator", "", 0],
                "processed_mail_folder" : ['string', 'Mail Processed folder<br><small>(if IMAP enabled)</small>', 152, "Generator/Processed","", 0],
                # This option is not displayed as it will break the link between genmon and genserv
                #"server_port" : ['int', 'Server Port', 5, 9082, "", 0],
                # this option is not displayed as this will break the modbus comms, only for debugging
                #"address" : ['string', 'Modbus slave address', 6, "9d", "", 0 ],
                "loglocation" : ['string', 'Log Directory', 7, "/var/log/", "", 0],
                #"displayoutput" : ['boolean', 'Output to Console', 50, False, "", 0],
                #"displaymonitor" : ['boolean', 'Display Monitor Status', 51, False, "", 0],
                #"displayregisters" : ['boolean', 'Display Register Status', 52, False, "", 0],
                #"displaystatus" : ['boolean', 'Display Status', 53, False, "", 0],
                #"displaymaintenance" : ['boolean', 'Display Maintenance', 54, False, "", 0],
                #"enabledebug" : ['boolean', 'Enable Debug', 14, False, "", 0],
                "displayunknown" : ['boolean', 'Display Unknown Sensors', 15, False, "", 0],
                "disableoutagecheck" : ['boolean', 'Do not check for outages', 17, False, "", 0],
                # These settings are not displayed as the auto-detect controller will set these
                # these are only to be used to override the auto-detect
                #"uselegacysetexercise" : ['boolean', 'Use Legacy Exercise Time', 43, False, "", 0],
                #"liquidcooled" : ['boolean', 'Liquid Cooled', 41, False, "", 0],
                #"evolutioncontroller" : ['boolean', 'Evolution Controler', 42, True, "", 0],
                "petroleumfuel" : ['boolean', 'Petroleum Fuel', 40, False, "", 0],
                "outagelog" : ['string', 'Outage Log', 8, "/home/pi/genmon/outage.txt", "", 0],
                "syncdst" : ['boolean', 'Sync Daylight Savings Time', 22, False, "", 0],
                "synctime" : ['boolean', 'Sync Time', 23, False, "", 0],
                "enhancedexercise" : ['boolean', 'Enhanced Exercise Time', 44, False, "", 0],

                # These do not appear to work on reload, some issue with Flask
                "usehttps" : ['boolean', 'Use Secure Web Settings', 25, False, "", 0],
                "useselfsignedcert" : ['boolean', 'Use Self-signed Certificate', 26, True, "", 0],
                "keyfile" : ['string', 'https key file', 27, "", "", 0],
                "certfile" : ['string', 'https certificate File', 28, "", "", 0],
                "http_user" : ['string', 'Web user name', 29, "", "", 0],
                "http_pass" : ['string', 'Web password', 30, "", "", 0],
                # This does not appear to work on reload, some issue with Flask
                "http_port" : ['int', 'Port of WebServer', 24, 8000, "", 0],

                "disableemail" : ['boolean', 'Disable Email usage', 101, True, "", 0],
                "email_pw" : ['string', 'Email Password', 103, "password", "", 0],
                "email_account" : ['string', 'Email Account', 102, "myemail@gmail.com", "", 0],
                "sender_account" : ['string', 'Sender Account', 104, "no-reply@gmail.com", "", 0],
                # "email_recipient" : ['string', 'Email Recepient<br><small>(comma delimited)</small>', 105], # will be handled on the notification screen
                "smtp_server" : ['string', 'SMTP Server <br><small>(leave emtpy to disable)</small>', 106, "smtp.gmail.com", "", 0],
                "imap_server" : ['string', 'IMAP Server <br><small>(leave emtpy to disable)</small>', 150, "imap.gmail.com", "", 0],
                "smtp_port" : ['int', 'SMTP Server Port', 107, 587, "", 0],
                "ssl_enabled" : ['boolean', 'SMTP Server SSL Enabled', 108, False, "", 0]}


    for entry, List in ConfigSettings.items():
        (ConfigSettings[entry])[3] = ReadSingleConfigValue(GENMON_CONFIG, "GenMon", List[0], entry, List[3])

    for entry, List in ConfigSettings.items():
        (ConfigSettings[entry])[3] = ReadSingleConfigValue(MAIL_CONFIG, "MyMail", List[0], entry, List[3])

    GetToolTips(ConfigSettings)

    return ConfigSettings

#------------------------------------------------------------
def WriteSettingsToFile(query_string):

    #TODO merge query string
    # e.g. {'displayunknown': ['true']}
    settings = dict(urlparse.parse_qs(query_string, 1))

    ConfigSettings = ReadSettingsFromFile()

    MailSettings = ["ssl_enabled", "smtp_port", "imap_server", "smtp_server", "sender_account", "email_recipient", "email_account", "email_pw", "disableemail"]

    File = ""
    Section = ""
    for entry, List in ConfigSettings.items():
        File = GENMON_CONFIG
        Section = "GenMon"
        if entry in MailSettings:
            File = MAIL_CONFIG
            Section = "MyMail"
        WriteSignleConfigValue(File, Section, entry, List[3])

#------------------------------------------------------------
def GetToolTips(ConfigSettings):

    pathtofile = os.path.dirname(os.path.realpath(__file__))
    for entry, List in ConfigSettings.items():
        (ConfigSettings[entry])[4] = ReadSingleConfigValue(pathtofile + "/tooltips.txt", "ToolTips", "string", entry, "")

#------------------------------------------------------------
def SaveSettings(query_string):

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
        #MyClientInterface.ProcessMonitorCommand("generator: reload")
        #Reload()
        Restart()
    except Exception as e1:
        log.error("Error Update Config File (SaveSettings): " + str(e1))

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
# This will reload the Flask App if use_reloader = True is enabled on the app.run command
def Reload():
    #os.system('touch ' + AppPath)      # reloader must be set to True to use this
    try:
        log.error("Reloading: " + sys.executable + " " + __file__ )
        os.execl(sys.executable, 'python', __file__, *sys.argv[1:])
    except Exception as e1:
        log.error("Error in Reload: " + str(e1))

#------------------------------------------------------------
# This will restart the Flask App
def Restart():

    if not RunBashScript("startgenmon.sh restart"):
        log.error("Error in Restart")

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
        log.error("Error in RunBashScript: " + str(e1))
        return False
#------------------------------------------------------------
# return False if File not present
def CheckCertFiles(CertFile, KeyFile):

    try:
        with open(CertFile,"r") as MyCertFile:
            with open(KeyFile,"r") as MyKeyFile:
                return True
    except Exception as e1:
        log.error("Unable to open Cert or Key file: " + str(e1))
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
    global SSLContext

    HTTPAuthPass = None
    HTTPAuthUser = None
    SSLContext = None
    try:
        config = RawConfigParser()
        # config parser reads from current directory, when running form a cron tab this is
        # not defined so we specify the full path
        config.read('/etc/genmon.conf')
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
if __name__ == "__main__":
    address='localhost' if len(sys.argv)<2 else sys.argv[1]

    AppPath = sys.argv[0]
    LoadConfig()

    log.error("Starting " + AppPath + ", Port:" + str(HTTPPort) + ", Secure HTTP: " + str(bUseSecureHTTP) + ", SelfSignedCert: " + str(bUseSelfSignedCert))

    # validate needed files are present
    file = os.path.dirname(os.path.realpath(__file__)) + "/startgenmon.sh"
    if not ValidateFilePresent(file):
        log.error("Required file missing")

    file = os.path.dirname(os.path.realpath(__file__)) + "/genmonmaint.sh"
    if not ValidateFilePresent(file):
        log.error("Required file missing")

    MyClientInterface = myclient.ClientInterface(host = address,port=clientport, log = log)

    while True:
        try:
            app.run(host="0.0.0.0", port=HTTPPort, threaded = True, ssl_context=SSLContext, use_reloader = False, debug = False)

        except Exception as e1:
            log.error("Error in app.run:" + str(e1))
            time.sleep(2)
            Restart()

