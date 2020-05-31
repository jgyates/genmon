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

import sys, signal, os, socket, atexit, time, subprocess, json, threading, signal, errno, collections, getopt

try:
    from flask import Flask, render_template, request, jsonify, session, send_file
except Exception as e1:
    print("\n\nThis program requires the Flask library. Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)


try:
    from genmonlib.myclient import ClientInterface
    from genmonlib.mylog import SetupLogger
    from genmonlib.myconfig import MyConfig
    from genmonlib.mymail import MyMail
    from genmonlib.mysupport import MySupport
    from genmonlib.program_defaults import ProgramDefaults

except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the original github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)

try:
    from urllib.parse import urlparse
    from urllib.parse import parse_qs
    from urllib.parse import parse_qsl
except ImportError:
    from urlparse import urlparse
    from urlparse import parse_qs
    from urlparse import parse_qsl

import re, datetime


#-------------------------------------------------------------------------------
app = Flask(__name__,static_url_path='')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 300

HTTPAuthUser = None
HTTPAuthPass = None
HTTPAuthUser_RO = None
HTTPAuthPass_RO = None
LdapServer = None
LdapBase = None
LdapAdminGroup = None
LdapReadOnlyGroup = None

bUseSecureHTTP = False
bUseSelfSignedCert = True
SSLContext = None
HTTPPort = 8000
loglocation = ProgramDefaults.LogPath
clientport = ProgramDefaults.ServerPort
log = None
console = None
AppPath = ""
favicon = "favicon.ico"
ConfigFilePath = ProgramDefaults.ConfPath

MAIL_SECTION = "MyMail"
GENMON_SECTION = "GenMon"

Closing = False
Restarting = False
ControllerType = "generac_evo_nexus"
CriticalLock = threading.Lock()
CachedToolTips = {}
CachedRegisterDescriptions = {}
#-------------------------------------------------------------------------------
@app.route('/logout')
def logout():
    try:
        # remove the session data
        if HTTPAuthUser != None and HTTPAuthPass != None:
            session['logged_in'] = False
            session['write_access'] = False
        return root()
    except Exception as e1:
        LogError("Error on logout: " + str(e1))
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
@app.route('/low', methods=['GET'])
def lowbandwidth():

    if HTTPAuthUser != None and HTTPAuthPass != None:
        if not session.get('logged_in'):
            return render_template('index_lowbandwith.html')
        else:
            return app.send_static_file('index_lowbandwith.html')
    else:
        return app.send_static_file('index_lowbandwith.html')

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
    elif doLdapLogin(request.form['username'], request.form['password']):
        return root()
    elif request.form['username'] != "":
        LogError("Invalid login: " + request.form['username'])
        return render_template('login.html')
    else:
        return render_template('login.html')

#-------------------------------------------------------------------------------
def doLdapLogin(username, password):
    if LdapServer == None or LdapServer == "":
        return False
    try:
        import ldap
    except ImportError:
        LogError("LDAP import not found, run 'sudo apt-get -y install python-ldap'")
        return False

    conn = ldap.initialize(LdapServer)
    conn.protocol_version = 3
    conn.set_option(ldap.OPT_REFERRALS, 0)
    try:
        conn.simple_bind_s(username, password)
    except:
        LogError("Invalid login via LDAP: " + username)
        return False

    HasAdmin = False
    HasReadOnly = False
    SplitName = username.split('\\')
    AccountName = SplitName[1]
    AccountName = AccountName.strip()
    ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
    search_filter="(&(objectClass=*)(member=uid="+AccountName+",$LdapBase))"
    account_filter = "sAMAccountName="+AccountName
    results = conn.search_s(LdapBase, ldap.SCOPE_SUBTREE, account_filter, ['memberOf'])
    for result in results:
        if type(result[1]) is dict:
            for groupList in result[1].values():
                for group in groupList:
                    LogError("Group: " + group)
                    if group.upper().find("CN="+LdapAdminGroup.upper()+",") >= 0:
                        HasAdmin = True
                    elif group.upper().find("CN="+LdapReadOnlyGroup.upper()+",") >= 0:
                        HasReadOnly = True

    session['logged_in'] = HasAdmin or HasReadOnly
    session['write_access'] = HasAdmin
    if HasAdmin:
        LogError("Admin Login via LDAP")
    elif HasReadOnly:
        LogError("Limited Rights Login via LDAP")
    else:
        LogError("No rights for valid login via LDAP")

    return HasAdmin or HasReadOnly

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
        #LogError(request.url)
        if command in ["status", "status_json", "outage", "outage_json", "maint", "maint_json",
            "logs", "logs_json", "monitor", "monitor_json", "registers_json", "allregs_json",
            "start_info_json", "gui_status_json", "power_log_json", "power_log_clear",
            "getbase", "getsitename","setexercise", "setquiet", "setremote",
            "settime", "sendregisters", "sendlogfiles", "getdebug", "status_num_json",
            "get_maint_log_json", "add_maint_log", "clear_maint_log" ]:
            finalcommand = "generator: " + command

            try:
                if command in ["setexercise", "setquiet", "setremote", "add_maint_log"] and not session.get('write_access', True):
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
                if command == "add_maint_log":
                    # use direct method instead of request.args.get due to unicoode
                    # input for add_maint_log for international users
                    input = request.args['add_maint_log']
                    finalcommand += "=" + input

                data = MyClientInterface.ProcessMonitorCommand(finalcommand)

            except Exception as e1:
                data = "Retry"
                LogError("Error on command function: " + str(e1))

            if command in ["status_json", "outage_json", "maint_json", "monitor_json", "logs_json",
                "registers_json", "allregs_json", "start_info_json", "gui_status_json", "power_log_json",
                "status_num_json", "get_maint_log_json"]:

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

        elif command in ["settings"]:
            if session.get('write_access', True):
                data =  ReadSettingsFromFile()
                return json.dumps(data, sort_keys = False)
            else:
                return "Access denied"

        elif command in ["notifications"]:
            data = ReadNotificationsFromFile()
            return jsonify(data)
        elif command in ["setnotifications"]:
            if session.get('write_access', True):
                SaveNotifications(request.args.get('setnotifications', 0, type=str))
            return "OK"

        # Add on items
        elif command in ["get_add_on_settings", "set_add_on_settings"]:
            if session.get('write_access', True):
                if command == "get_add_on_settings":
                    data = GetAddOnSettings()
                    return json.dumps(data, sort_keys = False)
                elif command == "set_add_on_settings":
                    SaveAddOnSettings(request.args.get('set_add_on_settings', default = None, type=str))
                else:
                    return "OK"
            return "OK"

        elif command in ["get_advanced_settings", "set_advanced_settings"]:
            if session.get('write_access', True):
                if command == "get_advanced_settings":
                    data = ReadAdvancedSettingsFromFile()
                    return json.dumps(data, sort_keys = False)
                elif command == "set_advanced_settings":
                    SaveAdvancedSettings(request.args.get('set_advanced_settings', default = None, type=str))
                else:
                    return "OK"
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
        elif command in ["backup"]:
            if session.get('write_access', True):
                Backup()    # Create backup file
                # Now send the file
                pathtofile = os.path.dirname(os.path.realpath(__file__))
                return send_file(pathtofile + "/genmon_backup.tar.gz", as_attachment=True)
        elif command in ["test_email"]:
            return SendTestEmail(request.args.get('test_email', default = None, type=str))
        else:
            return render_template('command_template.html', command = command)
    except Exception as e1:
        LogErrorLine("Error in Process Command: " + command + ": " + str(e1))
        return render_template('command_template.html', command = command)

#-------------------------------------------------------------------------------
def SendTestEmail(query_string):
    try:
        if query_string == None or not  len(query_string):
            return "No parameters given for email test."
        parameters = json.loads(query_string)
        if not len(parameters):
            return "No parameters"    # nothing to change

    except:
        LogErrorLine("Error getting parameters in SendTestEmail: " + str(e1))
        return "Error getting parameters in email test: " + str(e1)
    try:
        smtp_server =  str(parameters['smtp_server'])
        smtp_server = smtp_server.strip()
        smtp_port =  int(parameters['smtp_port'])
        email_account = str(parameters['email_account'])
        email_account = email_account.strip()
        sender_account = str(parameters['sender_account'])
        sender_account = sender_account.strip()
        if not len(sender_account):
            sender_account == None
        sender_name = str(parameters['sender_name'])
        sender_name = sender_name.strip()
        if not len(sender_name):
            sender_name == None
        recipient = str(parameters['recipient'])
        recipient = recipient.strip()
        password = str(parameters['password'])
        if parameters['use_ssl'].lower() == 'true':
            use_ssl = True
        else:
            use_ssl = False

        if parameters['tls_disable'].lower() == 'true':
            tls_disable = True
        else:
            tls_disable = False

        if parameters['smtpauth_disable'].lower() == 'true':
            smtpauth_disable = True
        else:
            smtpauth_disable = False

    except Exception as e1:
        LogErrorLine("Error parsing parameters in SendTestEmail: " + str(e1))
        LogError(str(parameters))
        return "Error parsing parameters in email test: " + str(e1)

    try:
        ReturnMessage = MyMail.TestSendSettings(
              smtp_server = smtp_server,
              smtp_port = smtp_port,
              email_account = email_account,
              sender_account = sender_account,
              sender_name = sender_name,
              recipient = recipient,
              password = password,
              use_ssl = use_ssl,
              tls_disable = tls_disable,
              smtpauth_disable = smtpauth_disable
        )
        return ReturnMessage
    except Exception as e1:
        LogErrorLine("Error sending test email : " + str(e1))
        return "Error sending test email : " + str(e1)
#-------------------------------------------------------------------------------
def GetAddOns():
    AddOnCfg = collections.OrderedDict()

    # Default icon name should be "Genmon" to get a generic icon
    try:
        # GENGPIO
        Temp = collections.OrderedDict()
        AddOnCfg['gengpio'] = collections.OrderedDict()
        AddOnCfg['gengpio']['enable'] = ConfigFiles[GENLOADER_CONFIG].ReadValue("enable", return_type = bool, section = "gengpio", default = False)
        AddOnCfg['gengpio']['title'] = "Genmon GPIO Outputs"
        AddOnCfg['gengpio']['description'] = "Genmon will set Raspberry Pi GPIO outputs (see documentation for details)"
        AddOnCfg['gengpio']['icon'] = "rpi"
        AddOnCfg['gengpio']['url'] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gengpiopy-optional"
        AddOnCfg['gengpio']['parameters'] = None

        # GENGPIOIN
        AddOnCfg['gengpioin'] = collections.OrderedDict()
        AddOnCfg['gengpioin']['enable'] = ConfigFiles[GENLOADER_CONFIG].ReadValue("enable", return_type = bool, section = "gengpioin", default = False)
        AddOnCfg['gengpioin']['title'] = "Genmon GPIO Inputs"
        AddOnCfg['gengpioin']['description'] = "Genmon will set Raspberry Pi GPIO inputs (see documentation for details)"
        AddOnCfg['gengpioin']['icon'] = "rpi"
        AddOnCfg['gengpioin']['url'] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gengpioinpy-optional"
        AddOnCfg['gengpioin']['parameters'] = collections.OrderedDict()
        AddOnCfg['gengpioin']['parameters']['trigger'] = CreateAddOnParam(
            ConfigFiles[GENGPIOIN_CONFIG].ReadValue("trigger", return_type = str, default = "falling"),
            'list',
            "Set GPIO input to trigger on rising or falling edge.",
            bounds = 'falling,rising,both',
            display_name = "GPIO Edge Trigger")
        AddOnCfg['gengpioin']['parameters']['resistorpull'] = CreateAddOnParam(
            ConfigFiles[GENGPIOIN_CONFIG].ReadValue("resistorpull", return_type = str, default = "up"),
            'list',
            "Set GPIO input internal pull up or pull down resistor.",
            bounds = 'up,down,off',
            display_name = "Internal resistor pull")
        AddOnCfg['gengpioin']['parameters']['bounce'] = CreateAddOnParam(
            ConfigFiles[GENGPIOIN_CONFIG].ReadValue("bounce", return_type = int, default = 0),
            'int',
            "Minimum interval in milliseconds between valid input channges. Zero to disable, or positive whole number.",
            bounds = 'number',
            display_name = "Software Debounce")

        #GENLOG
        AddOnCfg['genlog'] = collections.OrderedDict()
        AddOnCfg['genlog']['enable'] = ConfigFiles[GENLOADER_CONFIG].ReadValue("enable", return_type = bool, section = "genlog", default = False)
        AddOnCfg['genlog']['title'] = "Notifications to CSV Log"
        AddOnCfg['genlog']['description'] = "Log Genmon and utility state changes to a file. Log file is in text CSV format."
        AddOnCfg['genlog']['icon'] = "csv"
        AddOnCfg['genlog']['url'] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genlogpy-optional"
        AddOnCfg['genlog']['parameters'] = collections.OrderedDict()
        Args = ConfigFiles[GENLOADER_CONFIG].ReadValue("args", return_type = str, section = "genlog", default = False)
        ArgList = Args.split()
        if len(ArgList) == 2:
            Value = ArgList[1]
        else:
            Value = ""
        AddOnCfg['genlog']['parameters']['Log File Name'] = CreateAddOnParam(
            Value,
            'string',
            'Filename for log. Full path of the file must be included (i.e. /home/pi/genmon/LogFile.csv)',
            bounds = "required UnixFile",
            display_name = "Log File Name" )


        #GENSMS
        AddOnCfg['gensms'] = collections.OrderedDict()
        AddOnCfg['gensms']['enable'] = ConfigFiles[GENLOADER_CONFIG].ReadValue("enable", return_type = bool, section = "gensms", default = False)
        AddOnCfg['gensms']['title'] = "Notifications via SMS - Twilio"
        AddOnCfg['gensms']['description'] = "Send Genmon and utility state changes via Twilio SMS"
        AddOnCfg['gensms']['icon'] = "twilio"
        AddOnCfg['gensms']['url'] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensmspy-optional"
        AddOnCfg['gensms']['parameters'] = collections.OrderedDict()

        AddOnCfg['gensms']['parameters']['accountsid'] = CreateAddOnParam(
            ConfigFiles[GENSMS_CONFIG].ReadValue("accountsid", return_type = str, default = ""),
            'string',
            "Twilio account SID. This can be obtained from a valid Twilio account",
            bounds = 'required minmax:10:50',
            display_name = "Twilio Account SID")
        AddOnCfg['gensms']['parameters']['authtoken'] = CreateAddOnParam(
            ConfigFiles[GENSMS_CONFIG].ReadValue("authtoken", return_type = str, default = ""),
            'string',
            "Twilio authentication token. This can be obtained from a valid Twilio account",
            bounds = 'required minmax:10:50',
            display_name = "Twilio Authentication Token")
        AddOnCfg['gensms']['parameters']['to_number'] = CreateAddOnParam(
            ConfigFiles[GENSMS_CONFIG].ReadValue("to_number", return_type = str, default = ""),
            'string',
            "Mobile number to send SMS message to. This can be any mobile number.",
            bounds = 'required InternationalPhone',
            display_name = "Recipient Phone Number")
        AddOnCfg['gensms']['parameters']['from_number'] = CreateAddOnParam(
            ConfigFiles[GENSMS_CONFIG].ReadValue("from_number", return_type = str, default = ""),
            'string',
            "Number to send SMS message from. This should be a twilio phone number.",
            bounds = 'required InternationalPhone',
            display_name = "Twilio Phone Number")

        #GENSMS_MODEM
        AddOnCfg['gensms_modem'] = collections.OrderedDict()
        AddOnCfg['gensms_modem']['enable'] = ConfigFiles[GENLOADER_CONFIG].ReadValue("enable", return_type = bool, section = "gensms_modem", default = False)
        AddOnCfg['gensms_modem']['title'] = "Notifications via SMS - LTE Hat"
        AddOnCfg['gensms_modem']['description'] = "Send Genmon and utility state changes via cellular SMS (additional hardware required)"
        AddOnCfg['gensms_modem']['icon'] = "sms"
        AddOnCfg['gensms_modem']['url'] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensms_modempy-optional"
        AddOnCfg['gensms_modem']['parameters'] = collections.OrderedDict()

        AddOnCfg['gensms_modem']['parameters']['recipient'] = CreateAddOnParam(
            ConfigFiles[MYMODEM_CONFIG].ReadValue("recipient", return_type = str, default = ""),
            'string',
            "Mobile number to send SMS message. This can be any mobile number. No dashes or spaces.",
            bounds = 'required InternationalPhone',
            display_name = "Recipient Phone Number")
        AddOnCfg['gensms_modem']['parameters']['port'] = CreateAddOnParam(
            ConfigFiles[MYMODEM_CONFIG].ReadValue("port", return_type = str, default = ""),
            'string',
            "This is the serial device to send AT modem commands. This *must* be different from the serial port used by the generator monitor software.",
            bounds = 'required UnixDevice',
            display_name = "Modem Serial Port")

        AddOnCfg['gensms_modem']['parameters']['rate'] = CreateAddOnParam(
            ConfigFiles[MYMODEM_CONFIG].ReadValue("rate", return_type = int, default = 115200),
            'int',
            "The baud rate for the port. Use 115200 for the LTEPiHat.",
            bounds = 'required digits',
            display_name = "Modem Serial Rate")
        AddOnCfg['gensms_modem']['parameters']['log_at_commands'] = CreateAddOnParam(
            ConfigFiles[MYMODEM_CONFIG].ReadValue("log_at_commands", return_type = bool, default = False),
            'boolean',
            "Enable to log at commands to the log file.",
            display_name = "Log AT Commands")
        # modem type - select the type of modem used. For future use. Presently "LTEPiHat" is the only option
        #modem_type = LTEPiHat

        #GENPUSHOVER
        AddOnCfg['genpushover'] = collections.OrderedDict()
        AddOnCfg['genpushover']['enable'] = ConfigFiles[GENLOADER_CONFIG].ReadValue("enable", return_type = bool, section = "genpushover", default = False)
        AddOnCfg['genpushover']['title'] = "Notifications via Pushover"
        AddOnCfg['genpushover']['description'] = "Send Genmon and utility state changes via Pushover service"
        AddOnCfg['genpushover']['icon'] = "pushover"
        AddOnCfg['genpushover']['url'] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genpushoverpy-optional"
        AddOnCfg['genpushover']['parameters'] = collections.OrderedDict()

        AddOnCfg['genpushover']['parameters']['appid'] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue("appid", return_type = str, default = ""),
            'string',
            "Pushover app ID.",
            bounds = 'required minmax:5:50',
            display_name = "Application ID")
        AddOnCfg['genpushover']['parameters']['userid'] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue("userid", return_type = str, default = ""),
            'string',
            "Pushover user ID.",
            bounds = 'required minmax:5:50',
            display_name = "User ID")
        AddOnCfg['genpushover']['parameters']['pushsound'] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue("pushsound", return_type = str, default = "updown"),
            'string',
            "Notification sound identifier. See https://pushover.net/api#sounds for a full list of sound IDs",
            bounds = 'minmax:3:20',
            display_name = "Push Sound")

        # GENSYSLOG
        AddOnCfg['gensyslog'] = collections.OrderedDict()
        AddOnCfg['gensyslog']['enable'] = ConfigFiles[GENLOADER_CONFIG].ReadValue("enable", return_type = bool, section = "gensyslog", default = False)
        AddOnCfg['gensyslog']['title'] = "Linux System Logging"
        AddOnCfg['gensyslog']['description'] = "Write generator and utility state changes to system log (/var/log/system)"
        AddOnCfg['gensyslog']['icon'] = "linux"
        AddOnCfg['gensyslog']['url'] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensyslogpy-optional"
        AddOnCfg['gensyslog']['parameters'] = None

        #GENMQTT
        AddOnCfg['genmqtt'] = collections.OrderedDict()
        AddOnCfg['genmqtt']['enable'] = ConfigFiles[GENLOADER_CONFIG].ReadValue("enable", return_type = bool, section = "genmqtt", default = False)
        AddOnCfg['genmqtt']['title'] = "MQTT integration"
        AddOnCfg['genmqtt']['description'] = "Export Genmon data and status to MQTT server for automation integration"
        AddOnCfg['genmqtt']['icon'] = "mqtt"
        AddOnCfg['genmqtt']['url'] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genmqttpy-optional"
        AddOnCfg['genmqtt']['parameters'] = collections.OrderedDict()

        AddOnCfg['genmqtt']['parameters']['mqtt_address'] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue("mqtt_address", return_type = str, default = ""),
            'string',
            "Address of your MQTT server.",
            bounds = 'required IPAddress',
            display_name = "MQTT Server Address")
        AddOnCfg['genmqtt']['parameters']['mqtt_port'] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue("mqtt_port", return_type = int, default = 1833),
            'int',
            "The port of the MQTT server in a decimal number.",
            bounds = 'required digits',
            display_name = "MQTT Server Port Number")
        AddOnCfg['genmqtt']['parameters']['username'] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue("username", return_type = str, default = ""),
            'string',
            "This value is used for the username if your MQTT server requires authentication. Leave blank for no authentication.",
            bounds = 'minmax:4:50',
            display_name = "MQTT Authentication Username")
        AddOnCfg['genmqtt']['parameters']['password'] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue("password", return_type = str, default = ""),
            'string',
            "This value is used for the password if your MQTT server requires authentication. Leave blank for no authentication or no password.",
            bounds = 'minmax:4:50',
            display_name = "MQTT Authentication Password")
        AddOnCfg['genmqtt']['parameters']['poll_interval'] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue("poll_interval", return_type = float, default = 2.0),
            'float',
            "The time in seconds between requesting status from genmon. The default value is 2 seconds.",
            bounds = 'number',
            display_name = "Poll Interval")
        AddOnCfg['genmqtt']['parameters']['root_topic'] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue("root_topic", return_type = str, default = ""),
            'string',
            "(Optional) Prepend this value to the MQTT data path i.e. 'Home' would result in 'Home/generator/...''",
            bounds = 'minmax 1:50',
            display_name = "Root Topic")
        AddOnCfg['genmqtt']['parameters']['blacklist'] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue("blacklist", return_type = str, default = ""),
            'string',
            "(Optional) Names of data not exported to the MQTT server, separated by commas.",
            bounds = '',
            display_name = "Blacklist Filter")
        AddOnCfg['genmqtt']['parameters']['flush_interval'] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue("flush_interval", return_type = float, default = 0),
            'float',
            "(Optional) Time in seconds where even unchanged values will be published to their MQTT topic. Set to zero to disable flushing.",
            bounds = 'number',
            display_name = "Flush Interval")
        AddOnCfg['genmqtt']['parameters']['numeric_json'] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue("numeric_json", return_type = bool, default = False),
            'boolean',
            "If enabled will return numeric values in the Status, Maintenance (Evo/Nexus only) and Outage topics as a JSON string which can be converted to an object with integer or float values.",
            bounds = '',
            display_name = "JSON for Numerics")
        AddOnCfg['genmqtt']['parameters']['cert_authority_path'] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue("cert_authority_path", return_type = str, default = ""),
            'string',
            "(Optional) Full path to Certificate Authority file. Leave empty to not use SSL/TLS. If used port will be forced to 8883.",
            bounds = '',
            display_name = "SSL/TLS CA certificate file")
        AddOnCfg['genmqtt']['parameters']['tls_version'] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue("tls_version", return_type = str, default = "1.0"),
            'list',
            "(Optional) TLS version used (integer). Default is 1.0. Must be 1.0, 1.1, or 1.2. This is ignored if a CA cert file is not used. ",
            bounds = '1.0,1.1,1.2',
            display_name = "TLS Version")
        AddOnCfg['genmqtt']['parameters']['cert_reqs'] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue("cert_reqs", return_type = str, default = "Required"),
            'list',
            "(Optional) Defines the certificate requirements that the client imposes on the broker. Used if Certificate Authority file is used.",
            bounds = 'None,Optional,Required',
            display_name = "Certificate Requirements")


        #GENSLACK
        AddOnCfg['genslack'] = collections.OrderedDict()
        AddOnCfg['genslack']['enable'] = ConfigFiles[GENLOADER_CONFIG].ReadValue("enable", return_type = bool, section = "genslack", default = False)
        AddOnCfg['genslack']['title'] = "Notifications via Slack"
        AddOnCfg['genslack']['description'] = "Send Genmon and utility state changes via Slack service"
        AddOnCfg['genslack']['icon'] = "slack"
        AddOnCfg['genslack']['url'] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genslackpy-optional"
        AddOnCfg['genslack']['parameters'] = collections.OrderedDict()

        AddOnCfg['genslack']['parameters']['webhook_url'] = CreateAddOnParam(
            ConfigFiles[GENSLACK_CONFIG].ReadValue("webhook_url", return_type = str, default = ""),
            'string',
            "Full Slack Webhook URL. Retrieve from Slack custom integration configuration.",
            bounds = 'required HTTPAddress',
            display_name = "Web Hook URL")
        AddOnCfg['genslack']['parameters']['channel'] = CreateAddOnParam(
            ConfigFiles[GENSLACK_CONFIG].ReadValue("channel", return_type = str, default = ""),
            'string',
            "Slack channel to which the message will be sent.",
            display_name = "Channel")
        AddOnCfg['genslack']['parameters']['username'] = CreateAddOnParam(
            ConfigFiles[GENSLACK_CONFIG].ReadValue("username", return_type = str, default = ""),
            'string',
            "Slack username.",
            bounds = 'required username',
            display_name = "Username")
        AddOnCfg['genslack']['parameters']['icon_emoji'] = CreateAddOnParam(
            ConfigFiles[GENSLACK_CONFIG].ReadValue("icon_emoji", return_type = str, default = ":red_circle:"),
            'string',
            "Emoji that appears as the icon of the user who sent the message i.e. :red_circle:n",
             bounds = '',
             display_name = "Icon Emoji")
        AddOnCfg['genslack']['parameters']['title_link'] = CreateAddOnParam(
            ConfigFiles[GENSLACK_CONFIG].ReadValue("title_link", return_type = str, default = request.url_root),
            'string',
            "Use this to make the title of the message a link i.e. link to the genmon web interface.",
            bounds = 'HTTPAddress',
            display_name = "Title Link")

        # GENEXERCISE
        ControllerInfo = GetControllerInfo("controller").lower()
        if "evolution" in ControllerInfo or "nexus" in ControllerInfo:
            AddOnCfg['genexercise'] = collections.OrderedDict()
            AddOnCfg['genexercise']['enable'] = ConfigFiles[GENLOADER_CONFIG].ReadValue("enable", return_type = bool, section = "genexercise", default = False)
            AddOnCfg['genexercise']['title'] = "Enhanced Exercise"
            AddOnCfg['genexercise']['description'] = "Add additional exercise cycles with new functionality for Evolution/Nexus Controllers"
            AddOnCfg['genexercise']['icon'] = "selftest"
            AddOnCfg['genexercise']['url'] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genexercisepy-optional"
            AddOnCfg['genexercise']['parameters'] = collections.OrderedDict()

            AddOnCfg['genexercise']['parameters']['exercise_type'] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue("exercise_type", return_type = str, default = "Normal"),
                'list',
                "Quiet Exercise (reducded RPM, Hz and Voltage), Normal Exercise or Exercise with Transfer Switch Activated.",
                bounds = 'Quiet,Normal,Transfer',
                display_name = "Exercise Type")
            AddOnCfg['genexercise']['parameters']['exercise_frequency'] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue("exercise_frequency", return_type = str, default = "Monthly"),
                'list',
                "Exercise Frequency options are Weekly, Biweekly, or Monthly",
                bounds = 'Weekly,Biweekly,Monthly',
                display_name = "Exercise Frequency")
            AddOnCfg['genexercise']['parameters']['use_gen_time'] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue("use_gen_time", return_type = bool, default = False),
                'boolean',
                "Enable to use the generator time for the exercise cycle, otherwise it will use the system time.",
                display_name = "Use Generator Time")
            AddOnCfg['genexercise']['parameters']['exercise_hour'] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue("exercise_hour", return_type = int, default = 12),
                'int',
                "The hour of the exercise time. Valid input is 0 - 23.",
                bounds = "required digits range:0:23",
                display_name = "Exercise Time Hour")
            AddOnCfg['genexercise']['parameters']['exercise_minute'] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue("exercise_minute", return_type = int, default = 0),
                'int',
                "The minute of the exercise time.  Valid input is 0 - 59",
                bounds = "required digits range:0:59",
                display_name = "Exercise Time Minute")
            AddOnCfg['genexercise']['parameters']['exercise_day_of_month'] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue("exercise_day_of_month", return_type = int, default = 1),
                'int',
                "The day of month if monthly exercise is selected.",
                bounds = "required digits range:1:28",
                display_name = "Exercise Day of Month")
            AddOnCfg['genexercise']['parameters']['exercise_day_of_week'] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue("exercise_day_of_week", return_type = str, default = "Monday"),
                'list',
                "Exercise day of the week, if Weekly or Biweekly exercise frequency is selected.",
                bounds = "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday",
                display_name = "Exercise Day of the Week")
            AddOnCfg['genexercise']['parameters']['exercise_duration'] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue("exercise_duration", return_type = float, default = 12),
                'float',
                "The duration of the exercise time. Note: this time does not include warmup time for Transfer type exercise cycles.",
                bounds = 'number range:5:60',
                display_name = "Exercise Duration")
            AddOnCfg['genexercise']['parameters']['exercise_warmup'] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue("exercise_warmup", return_type = float, default = 0),
                'float',
                "The duration of the warmup time. Note: this time only appies to the transfer type of exercise cycle. Zero will disable the warmup period.",
                bounds = 'number range:0:30',
                display_name = "Warmup Duration")

        #GENEMAIL2SMS
        AddOnCfg['genemail2sms'] = collections.OrderedDict()
        AddOnCfg['genemail2sms']['enable'] = ConfigFiles[GENLOADER_CONFIG].ReadValue("enable", return_type = bool, section = "genemail2sms", default = False)
        AddOnCfg['genemail2sms']['title'] = "Mobile Carrier Email to SMS"
        AddOnCfg['genemail2sms']['description'] = "Send Genmon and utility state changes via carrier email to SMS service"
        AddOnCfg['genemail2sms']['icon'] = "text"
        AddOnCfg['genemail2sms']['url'] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genemail2smspy-optional"
        AddOnCfg['genemail2sms']['parameters'] = collections.OrderedDict()

        AddOnCfg['genemail2sms']['parameters']['destination'] = CreateAddOnParam(
            ConfigFiles[GENEMAIL2SMS_CONFIG].ReadValue("destination", return_type = str, default = ""),
            'string',
            "Email to SMS email recipient. Must be a valid email address",
            bounds = 'required email',
            display_name = "Email to SMS address")

        #GENTANKUTIL
        AddOnCfg['gentankutil'] = collections.OrderedDict()
        AddOnCfg['gentankutil']['enable'] = ConfigFiles[GENLOADER_CONFIG].ReadValue("enable", return_type = bool, section = "gentankutil", default = False)
        AddOnCfg['gentankutil']['title'] = "External Tank Fuel Monitor"
        AddOnCfg['gentankutil']['description'] = "Integrates tankutility.com propane tank sensor data"
        AddOnCfg['gentankutil']['icon'] = "tankutility"
        AddOnCfg['gentankutil']['url'] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gentankutilpy-optional"
        AddOnCfg['gentankutil']['parameters'] = collections.OrderedDict()

        AddOnCfg['gentankutil']['parameters']['tank_name'] = CreateAddOnParam(
            ConfigFiles[GENTANKUTIL_CONFIG].ReadValue("tank_name", return_type = str, default = ""),
            'string',
            "Tank name as defined in tankutility.com",
            bounds = 'minmax:1:50',
            display_name = "Tank Name")
        AddOnCfg['gentankutil']['parameters']['username'] = CreateAddOnParam(
            ConfigFiles[GENTANKUTIL_CONFIG].ReadValue("username", return_type = str, default = ""),
            'string',
            "Username at tankutility.com",
            bounds = 'required email',
            display_name = "Username")
        AddOnCfg['gentankutil']['parameters']['password'] = CreateAddOnParam(
            ConfigFiles[GENTANKUTIL_CONFIG].ReadValue("password", return_type = str, default = ""),
            'string',
            "Password at tankutility.com",
            bounds = 'minmax:4:50',
            display_name = "Password")
        AddOnCfg['gentankutil']['parameters']['poll_frequency'] = CreateAddOnParam(
            ConfigFiles[GENTANKUTIL_CONFIG].ReadValue("poll_frequency", return_type = float, default = 0),
            'float',
            "The duration in minutes between poll of tank data.",
            bounds = 'number',
            display_name = "Poll Frequency")

        #GENALEXA
        AddOnCfg['genalexa'] = collections.OrderedDict()
        AddOnCfg['genalexa']['enable'] = ConfigFiles[GENLOADER_CONFIG].ReadValue("enable", return_type = bool, section = "genalexa", default = False)
        AddOnCfg['genalexa']['title'] = "Amazon Alexa voice commands"
        AddOnCfg['genalexa']['description'] = "Allow Amazon Alexa to start and stop the generator"
        AddOnCfg['genalexa']['icon'] = "alexa"
        AddOnCfg['genalexa']['url'] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genalexapy-optional"
        AddOnCfg['genalexa']['parameters'] = collections.OrderedDict()

        AddOnCfg['genalexa']['parameters']['name'] = CreateAddOnParam(
            ConfigFiles[GENALEXA_CONFIG].ReadValue("name", return_type = str, default = ""),
            'string',
            "Name to call the generator device, i.e. 'generator'",
            bounds = 'minmax:4:50',
            display_name = "Name for generator device")

        #GENSNMP
        AddOnCfg['gensnmp'] = collections.OrderedDict()
        AddOnCfg['gensnmp']['enable'] = ConfigFiles[GENLOADER_CONFIG].ReadValue("enable", return_type = bool, section = "gensnmp", default = False)
        AddOnCfg['gensnmp']['title'] = "SNMP Support"
        AddOnCfg['gensnmp']['description'] = "Allow Genmon to respond to SNMP requests"
        AddOnCfg['gensnmp']['icon'] = "snmp"
        AddOnCfg['gensnmp']['url'] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensnmppy-optional"
        AddOnCfg['gensnmp']['parameters'] = collections.OrderedDict()

        AddOnCfg['gensnmp']['parameters']['poll_frequency'] = CreateAddOnParam(
            ConfigFiles[GENSNMP_CONFIG].ReadValue("poll_frequency", return_type = float, default = 2.0),
            'float',
            "The time in seconds between requesting status from genmon. The default value is 2 seconds.",
            bounds = 'number',
            display_name = "Poll Interval")
        AddOnCfg['gensnmp']['parameters']['enterpriseid'] = CreateAddOnParam(
            ConfigFiles[GENSNMP_CONFIG].ReadValue("enterpriseid", return_type = int, default = 9999),
            'int',
            "The enterprise ID used in the SNMP Object Identifier (OID).",
            bounds = 'required digits',
            display_name = "Enterprise ID")
        AddOnCfg['gensnmp']['parameters']['community'] = CreateAddOnParam(
            ConfigFiles[GENSNMP_CONFIG].ReadValue("community", return_type = str, default = "public"),
            'string',
            "SNMP Community string",
            bounds = 'minmax:4:50',
            display_name = "SNMP Community")

    except Exception as e1:
        LogErrorLine("Error in GetAddOns: " + str(e1))

    return AddOnCfg
#------------ MyCommon::StripJson ------------------------------------------
def StripJson(InputString):
    for char in '{}[]"':
        InputString = InputString.replace(char,'')
    return InputString

#------------ MyCommon::DictToString ---------------------------------------
def DictToString(InputDict, ExtraStrip = False):

    if InputDict == None:
        return ""
    ReturnString = json.dumps(InputDict,sort_keys=False, indent = 4, separators=(' ', ': '))
    return ReturnString
    if ExtraStrip:
        ReturnString = ReturnString.replace("} \n","")
    return StripJson(ReturnString)
#-------------------------------------------------------------------------------
def CreateAddOnParam(value = "", type = "string", description = "", bounds = "", display_name = ""):

    # Bounds are defined in ReadSettingsFromFile comments
    Parameter = collections.OrderedDict()
    Parameter['value'] = value
    Parameter['type'] = type
    Parameter['description'] = description
    Parameter['bounds'] = bounds
    Parameter['display_name'] = display_name
    return Parameter
#-------------------------------------------------------------------------------
def GetAddOnSettings():
    try:
        return GetAddOns()
    except Exception as e1:
        LogErrorLine("Error in GetAddOnSettings: " + str(e1))
        return {}

#-------------------------------------------------------------------------------
def SaveAddOnSettings(query_string):
    try:
        if query_string == None:
            LogError("Empty query string in SaveAddOnSettings")
            return

        settings = json.loads(query_string)
        if not len(settings):
            return      # nothing to change

        ConfigDict ={
            "genmon" : ConfigFiles[GENMON_CONFIG],
            "mymail" : ConfigFiles[MAIL_CONFIG],
            "genloader" : ConfigFiles[GENLOADER_CONFIG],
            "gensms" : ConfigFiles[GENSMS_CONFIG],
            "gensms_modem" : ConfigFiles[MYMODEM_CONFIG],
            "genpushover" : ConfigFiles[GENPUSHOVER_CONFIG],
            "genmqtt" : ConfigFiles[GENMQTT_CONFIG],
            "genslack" : ConfigFiles[GENSLACK_CONFIG],
            "genlog" : ConfigFiles[GENLOADER_CONFIG],
            "gensyslog" : ConfigFiles[GENLOADER_CONFIG],
            "gengpio" : ConfigFiles[GENLOADER_CONFIG],
            "gengpioin" : ConfigFiles[GENGPIOIN_CONFIG],
            "genexercise" : ConfigFiles[GENEXERCISE_CONFIG],
            "genemail2sms" : ConfigFiles[GENEMAIL2SMS_CONFIG],
            "gentankutil" : ConfigFiles[GENTANKUTIL_CONFIG],
            "genalexa" : ConfigFiles[GENALEXA_CONFIG],
            "gensnmp" : ConfigFiles[GENSNMP_CONFIG]
        }

        for module, entries in settings.items():   # module
            ParameterConfig = ConfigDict.get(module, None)
            if ParameterConfig == None:
                LogError("Invalid module in SaveAddOnSettings: " + module)
                continue
            # Find if it needs to be enabled / disabled or if there are parameters
            for basesettings, basevalues in entries.items():    # base settings
                if basesettings == 'enable':
                    ConfigFiles[GENLOADER_CONFIG].WriteValue("enable", basevalues, section = module)
                    if module == "gentankutil":
                        # update genmon.conf also to let it know that it should watch for external fuel data
                        ConfigFiles[GENMON_CONFIG].WriteValue("use_external_fuel_data", basevalues, section = "genmon")
                if basesettings == 'parameters':
                    for params, paramvalue in basevalues.items():
                        if module == "genlog" and params == "Log File Name":
                            ConfigFiles[GENLOADER_CONFIG].WriteValue("args", "-f " + paramvalue, section = module)
                        else:
                            ParameterConfig.WriteValue(params, paramvalue)

        Restart()
        return
    except Exception as e1:
        LogErrorLine("Error in SaveAddOnSettings: " + str(e1))
        return

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
        EmailsStr = ConfigFiles[MAIL_CONFIG].ReadValue("email_recipient")

        for email in EmailsStr.split(","):
            email = email.strip()
            EmailsToNotify.append(email)

        SortOrder = 1
        for email in EmailsToNotify:
            Notify = ConfigFiles[MAIL_CONFIG].ReadValue(email, default = "")
            if Notify == "":
                NotificationSettings[email] = [SortOrder]
            else:
                NotificationSettings[email] = [SortOrder, Notify]
    except Exception as e1:
        LogErrorLine("Error in ReadNotificationsFromFile: " + str(e1))

    return NotificationSettings

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
    notifications = dict(parse_qs(query_string, 1))
    notifications_order_string = ",".join([v[0] for v in parse_qsl(query_string, 1)])

    oldEmailsList = []
    oldNotifications = {}
    oldEmailRecipientString = ""
    try:
        with CriticalLock:
            # get existing settings
            if ConfigFiles[MAIL_CONFIG].HasOption("email_recipient"):
                oldEmailRecipientString = ConfigFiles[MAIL_CONFIG].ReadValue("email_recipient")
                oldEmailRecipientString.strip()
                oldEmailsList = oldEmailRecipientString.split(",")
                for oldEmailItem in oldEmailsList:
                    if ConfigFiles[MAIL_CONFIG].HasOption(oldEmailItem):
                        oldNotifications[oldEmailItem] = ConfigFiles[MAIL_CONFIG].ReadValue(oldEmailItem)

            # compare, remove notifications if needed
            for oldEmailItem in oldEmailsList:
                if not oldEmailItem in notifications.keys() and ConfigFiles[MAIL_CONFIG].HasOption(oldEmailItem):
                    ConfigFiles[MAIL_CONFIG].WriteValue(oldEmailItem, "", remove = True)

            # add / update the entries
            # update email recipient if needed
            if oldEmailRecipientString != notifications_order_string:
                ConfigFiles[MAIL_CONFIG].WriteValue("email_recipient", notifications_order_string)

            # update catigories
            for newEmail, newCats in notifications.items():
                # remove catigories if needed from existing emails
                if not len(newCats[0]) and ConfigFiles[MAIL_CONFIG].HasOption(newEmail):
                    ConfigFiles[MAIL_CONFIG].WriteValue(newEmail, "", remove = True)
                # update or add catigories
                if len(newCats[0]):
                    ConfigFiles[MAIL_CONFIG].WriteValue(newEmail, newCats[0])

        Restart()
    except Exception as e1:
        LogErrorLine("Error in SaveNotifications: " + str(e1))
    return

#-------------------------------------------------------------------------------
def ReadSingleConfigValue(entry, filename = None, section = None, type = "string", default = "", bounds = None):

    try:

        try:
            if filename == None:
                config = ConfigFiles[GENMON_CONFIG]
            else:
                config = ConfigFiles[filename]
        except Exception as e1:
            LogErrorLine("Unknow file in UpdateConfigFile: " + filename + ": " + str(e1))
            return default

        if section != None:
            config.SetSection(section)

        if not config.HasOption(entry):
            return default

        if type.lower() == "string" or type == "password":
            return config.ReadValue(entry)
        elif type.lower() == "boolean":
            return config.ReadValue(entry, return_type = bool, default = default, NoLog = True)
        elif type.lower() == "int":
            return config.ReadValue(entry, return_type = int, default = default, NoLog = True)
        elif type.lower() == "float":
            return config.ReadValue(entry, return_type = float, default = default, NoLog = True)
        elif type.lower() == 'list':
            Value = config.ReadValue(entry)
            if bounds != None:
                DefaultList = bounds.split(",")
                if Value.lower() in (name.lower() for name in DefaultList):
                    return Value
                else:
                    LogError("Warning: Reading Config File (value not in list): %s : %s" % (entry,Value))
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
def ReadAdvancedSettingsFromFile():

    ConfigSettings =  collections.OrderedDict()
    try:
        # This option is not displayed as it will break the link between genmon and genserv
        ConfigSettings["server_port"] = ['int', 'Server Port', 5, ProgramDefaults.ServerPort, "", 0, GENMON_CONFIG, GENMON_SECTION,"server_port"]
        # this option is not displayed as this will break the modbus comms, only for debugging
        ConfigSettings["address"] = ['string', 'Modbus slave address', 6, "9d", "", 0 , GENMON_CONFIG, GENMON_SECTION, "address"]
        ConfigSettings["response_address"] = ['string', 'Modbus slave transmit address', 6, "", "", 0 , GENMON_CONFIG, GENMON_SECTION, "response_address"]
        ConfigSettings["additional_modbus_timeout"] = ['float', 'Additional Modbus Timeout (sec)', 7, "0.0", "", 0, GENMON_CONFIG, GENMON_SECTION, "additional_modbus_timeout"]
        ConfigSettings["controllertype"] = ['list', 'Controller Type', 8, "generac_evo_nexus", "", "generac_evo_nexus,h_100", GENMON_CONFIG, GENMON_SECTION, "controllertype"]
        ConfigSettings["loglocation"] = ['string', 'Log Directory',9, ProgramDefaults.LogPath, "", "required UnixDir", GENMON_CONFIG, GENMON_SECTION, "loglocation"]
        ConfigSettings["userdatalocation"] = ['string', 'User Defined Data Directory',10, os.path.dirname(os.path.realpath(__file__))  + "/", "", "required UnixDir", GENMON_CONFIG, GENMON_SECTION, "userdatalocation"]
        ConfigSettings["enabledebug"] = ['boolean', 'Enable Debug', 11, False, "", 0, GENMON_CONFIG, GENMON_SECTION, "enabledebug"]
        ConfigSettings["ignore_unknown"] = ['boolean', 'Ignore Unknown Values', 12, False, "", 0, GENMON_CONFIG, GENMON_SECTION, "ignore_unknown"]
        # These settings are not displayed as the auto-detect controller will set these
        # these are only to be used to override the auto-detect
        #ConfigSettings["uselegacysetexercise"] = ['boolean', 'Use Legacy Exercise Time', 9, False, "", 0, GENMON_CONFIG, GENMON_SECTION, "uselegacysetexercise"]
        #ConfigSettings["liquidcooled"] = ['boolean', 'Force Controller Type (cooling)', 10, False, "", 0, GENMON_CONFIG, GENMON_SECTION, "liquidcooled"]
        #ConfigSettings["evolutioncontroller"] = ['boolean', 'Force Controller Type (Evo/Nexus)', 11, True, "", 0, GENMON_CONFIG, GENMON_SECTION, "evolutioncontroller"]
        # remove outage log, this will always be in the same location
        #ConfigSettings["outagelog"] = ['string', 'Outage Log', 12, "/home/pi/genmon/outage.txt", "", "required UnixFile", GENMON_CONFIG, GENMON_SECTION, "outagelog"]
        ConfigSettings["serialnumberifmissing"] = ['string', 'Serial Number if Missing', 13, "", "", 0, GENMON_CONFIG, GENMON_SECTION, "serialnumberifmissing"]
        ConfigSettings["additionalrunhours"] = ['string', 'Additional Run Hours', 14, "", "", 0, GENMON_CONFIG, GENMON_SECTION, "additionalrunhours"]
        ConfigSettings["subtractfuel"] = ['float', 'Subtract Fuel', 15, "0.0", "", 0, GENMON_CONFIG, GENMON_SECTION, "subtractfuel"]
        #ConfigSettings["kwlog"] = ['string', 'Power Log Name / Disable', 16, "", "", 0, GENMON_CONFIG, GENMON_SECTION, "kwlog"]
        if ControllerType != 'h_100':
            ConfigSettings["usenominallinevolts"] = ['boolean', 'Use Nominal Volts Override', 17, False, "", 0, GENMON_CONFIG, GENMON_SECTION, "usenominallinevolts"]
            ConfigSettings["nominallinevolts"] = ['int', 'Override nominal line voltage in UI', 18, "240", "", 0, GENMON_CONFIG, GENMON_SECTION,"nominallinevolts"]

        ConfigSettings["kwlogmax"] = ['string', 'Maximum size Power Log (MB)', 19, "", "", 0, GENMON_CONFIG, GENMON_SECTION, "kwlogmax"]
        ConfigSettings["currentdivider"] = ['float', 'Current Divider', 20, "", "", 0, GENMON_CONFIG, GENMON_SECTION, "currentdivider"]
        ConfigSettings["currentoffset"] = ['string', 'Current Offset', 21, "", "", 0, GENMON_CONFIG, GENMON_SECTION, "currentoffset"]
        ConfigSettings["disableplatformstats"] = ['boolean', 'Disable Platform Stats', 22, False, "", 0, GENMON_CONFIG, GENMON_SECTION, "disableplatformstats"]
        ConfigSettings["https_port"] = ['int', 'Override HTTPS port', 23, "", "", 0, GENMON_CONFIG, GENMON_SECTION, "https_port"]
        ConfigSettings["user_url"] = ['string', 'User URL', 24, "", "", 0, GENMON_CONFIG, GENMON_SECTION, "user_url"]


        for entry, List in ConfigSettings.items():
            if List[6] == GENMON_CONFIG:
                # filename, section = None, type = "string", entry, default = "", bounds = None):
                (ConfigSettings[entry])[3] = ReadSingleConfigValue(entry = List[8], filename = GENMON_CONFIG, section =  List[7], type = List[0], default = List[3], bounds = List[5])
            else:
                LogError("Invaild Config File in ReadAdvancedSettingsFromFile: " + str(List[6]))

        GetToolTips(ConfigSettings)
    except Exception as e1:
        self.LogErrorLine("Error in ReadAdvancedSettingsFromFile: " + str(e1))
    return ConfigSettings

#-------------------------------------------------------------------------------
def SaveAdvancedSettings(query_string):
    try:

        if query_string == None:
            LogError("Empty query string in SaveAdvancedSettings")
            return
        # e.g. {'displayunknown': ['true']}
        settings = dict(parse_qs(query_string, 1))
        if not len(settings):
            # nothing to change
            return
        CurrentConfigSettings = ReadAdvancedSettingsFromFile()
        with CriticalLock:
            for Entry in settings.keys():
                ConfigEntry = CurrentConfigSettings.get(Entry, None)
                if ConfigEntry != None:
                    ConfigFile = CurrentConfigSettings[Entry][6]
                    Value = settings[Entry][0]
                    Section = CurrentConfigSettings[Entry][7]
                else:
                    LogError("Invalid setting in SaveAdvancedSettings: " + str(Entry))
                    continue
                UpdateConfigFile(ConfigFile,Section, Entry, Value)
        Restart()
    except Exception as e1:
        LogErrorLine("Error Update Config File (SaveAdvancedSettings): " + str(e1))
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
    ConfigSettings["use_serial_tcp"] = ['boolean', 'Enable Serial over TCP/IP', 2, False, "", "", GENMON_CONFIG, GENMON_SECTION, "use_serial_tcp"]
    ConfigSettings["port"] = ['string', 'Port for Serial Communication', 3, "/dev/serial0", "", "required UnixDevice", GENMON_CONFIG, GENMON_SECTION, "port"]
    ConfigSettings["serial_tcp_address"] = ['string', 'Serial Server TCP/IP Address', 4, "", "", "InternetAddress", GENMON_CONFIG, GENMON_SECTION, "serial_tcp_address"]
    ConfigSettings["serial_tcp_port"] = ['int', 'Serial Server TCP/IP Port', 5, "8899", "", "digits", GENMON_CONFIG, GENMON_SECTION, "serial_tcp_port"]

    if ControllerType != 'h_100':
        ConfigSettings["disableoutagecheck"] = ['boolean', 'Do Not Check for Outages', 17, False, "", "", GENMON_CONFIG, GENMON_SECTION, "disableoutagecheck"]

    ConfigSettings["syncdst"] = ['boolean', 'Sync Daylight Savings Time', 22, False, "", "", GENMON_CONFIG, GENMON_SECTION, "syncdst"]
    ConfigSettings["synctime"] = ['boolean', 'Sync Time', 23, False, "", "", GENMON_CONFIG, GENMON_SECTION, "synctime"]
    ConfigSettings["metricweather"] = ['boolean', 'Use Metric Units', 24, False, "", "", GENMON_CONFIG, GENMON_SECTION, "metricweather"]
    ConfigSettings["optimizeforslowercpu"] = ['boolean', 'Optimize for slower CPUs', 25, False, "", "", GENMON_CONFIG, GENMON_SECTION, "optimizeforslowercpu"]
    ConfigSettings["disablepowerlog"] = ['boolean', 'Disable Power / Current Display', 26, False, "", "", GENMON_CONFIG, GENMON_SECTION, "disablepowerlog"]
    ConfigSettings["autofeedback"] = ['boolean', 'Automated Feedback', 29, False, "", "", GENMON_CONFIG, GENMON_SECTION, "autofeedback"]
    ConfigSettings["update_check"] = ['boolean', 'Check for Software Update', 30, True, "", "", GENMON_CONFIG, GENMON_SECTION, "update_check"]

    ConfigSettings["nominalfrequency"] = ['list', 'Rated Frequency', 101, "60", "", "50,60", GENMON_CONFIG, GENMON_SECTION, "nominalfrequency"]
    ConfigSettings["nominalrpm"] = ['int', 'Nominal RPM', 102, "3600", "", "required digits range:1500:4000", GENMON_CONFIG, GENMON_SECTION, "nominalrpm"]
    ConfigSettings["nominalkw"] = ['int', 'Maximum kW Output', 103, "22", "", "required digits range:0:1000", GENMON_CONFIG, GENMON_SECTION, "nominalkw"]
    ConfigSettings["fueltype"] = ['list', 'Fuel Type', 104, "Natural Gas", "", "Natural Gas,Propane,Diesel,Gasoline", GENMON_CONFIG, GENMON_SECTION, "fueltype"]
    ConfigSettings["tanksize"] = ['int', 'Fuel Tank Size', 105, "0", "", "required digits range:0:2000", GENMON_CONFIG, GENMON_SECTION, "tanksize"]

    ControllerInfo = GetControllerInfo("controller").lower()
    if "liquid cooled" in ControllerInfo and "evolution" in ControllerInfo and GetControllerInfo("fueltype").lower() == "diesel":
        ConfigSettings["usesensorforfuelgauge"] = ['boolean', 'Use Sensor for Fuel Gauge', 106, True, "", "", GENMON_CONFIG, GENMON_SECTION, "usesensorforfuelgauge"]

    if ControllerType == 'h_100':
        Choices = "120/208,120/240,230/400,240/415,277/480,347/600"
        ConfigSettings["voltageconfiguration"] = ['list', 'Line to Neutral / Line to Line', 107, "277/480", "", Choices, GENMON_CONFIG, GENMON_SECTION, "voltageconfiguration"]
        ConfigSettings["nominalbattery"] = ['list', 'Nomonal Battery Voltage', 108, "24", "", "12,24", GENMON_CONFIG, GENMON_SECTION, "nominalbattery"]
        ConfigSettings["hts_transfer_switch"] = ['boolean', 'HTS/MTS/STS Transfer Switch', 109, False, "", "", GENMON_CONFIG, GENMON_SECTION, "hts_transfer_switch"]
    else: #ControllerType == "generac_evo_nexus":
        ConfigSettings["enhancedexercise"] = ['boolean', 'Enhanced Exercise Time', 109, False, "", "", GENMON_CONFIG, GENMON_SECTION, "enhancedexercise"]

    ConfigSettings["smart_transfer_switch"] = ['boolean', 'Smart Transfer Switch', 110, False, "", "", GENMON_CONFIG, GENMON_SECTION, "smart_transfer_switch"]
    ConfigSettings["displayunknown"] = ['boolean', 'Display Unknown Sensors', 111, False, "", "", GENMON_CONFIG, GENMON_SECTION, "displayunknown"]

    # These do not appear to work on reload, some issue with Flask
    ConfigSettings["usehttps"] = ['boolean', 'Use Secure Web Settings', 200, False, "", "", GENMON_CONFIG, GENMON_SECTION, "usehttps"]
    ConfigSettings["useselfsignedcert"] = ['boolean', 'Use Self-signed Certificate', 203, True, "", "", GENMON_CONFIG, GENMON_SECTION, "useselfsignedcert"]
    ConfigSettings["keyfile"] = ['string', 'https Key File', 204, "", "", "UnixFile", GENMON_CONFIG, GENMON_SECTION, "keyfile"]
    ConfigSettings["certfile"] = ['string', 'https Certificate File', 205, "", "", "UnixFile", GENMON_CONFIG, GENMON_SECTION, "certfile"]
    ConfigSettings["http_user"] = ['string', 'Web Username', 206, "", "", "minmax:4:50", GENMON_CONFIG, GENMON_SECTION, "http_user"]
    ConfigSettings["http_pass"] = ['password', 'Web Password', 207, "", "", "minmax:4:50", GENMON_CONFIG, GENMON_SECTION, "http_pass"]
    ConfigSettings["http_user_ro"] = ['string', 'Limited Rights User Username', 208, "", "", "minmax:4:50", GENMON_CONFIG, GENMON_SECTION, "http_user_ro"]
    ConfigSettings["http_pass_ro"] = ['password', 'Limited Rights User Password', 209, "", "", "minmax:4:50", GENMON_CONFIG, GENMON_SECTION, "http_pass_ro"]
    ConfigSettings["http_port"] = ['int', 'Port of WebServer', 210, 8000, "", "required digits", GENMON_CONFIG, GENMON_SECTION, "http_port"]
    ConfigSettings["favicon"] = ['string', 'FavIcon', 220, "", "", "minmax:8:255", GENMON_CONFIG, GENMON_SECTION, "favicon"]
    # This does not appear to work on reload, some issue with Flask

    #
    #ConfigSettings["disableemail"] = ['boolean', 'Disable Email Usage', 300, True, "", "", MAIL_CONFIG, MAIL_SECTION, "disableemail"]
    ConfigSettings["disablesmtp"] = ['boolean', 'Disable Sending Email', 300, False, "", "", MAIL_CONFIG, MAIL_SECTION, "disablesmtp"]
    ConfigSettings["email_account"] = ['string', 'Email Account', 301, "myemail@gmail.com", "", "minmax:3:50", MAIL_CONFIG, MAIL_SECTION, "email_account"]
    ConfigSettings["email_pw"] = ['password', 'Email Password', 302, "password", "", "max:50", MAIL_CONFIG, MAIL_SECTION, "email_pw"]
    ConfigSettings["sender_account"] = ['string', 'Sender Address', 303, "no-reply@gmail.com", "", "email", MAIL_CONFIG, MAIL_SECTION, "sender_account"]
    ConfigSettings["sender_name"] = ['string', 'Sender Name', 304, "", "", "max:50", MAIL_CONFIG, MAIL_SECTION, "sender_name"]
    # email_recipient setting will be handled on the notification screen
    ConfigSettings["smtp_server"] = ['string', 'SMTP Server <br><small>(leave emtpy to disable)</small>', 305, "smtp.gmail.com", "", "InternetAddress", MAIL_CONFIG, MAIL_SECTION, "smtp_server"]
    ConfigSettings["smtp_port"] = ['int', 'SMTP Server Port', 307, 587, "", "digits", MAIL_CONFIG, MAIL_SECTION, "smtp_port"]
    ConfigSettings["ssl_enabled"] = ['boolean', 'Use SSL Encryption', 308, False, "", "", MAIL_CONFIG, MAIL_SECTION, "ssl_enabled"]
    ConfigSettings["tls_disable"] = ['boolean', 'Disable TLS Encryption', 309, False, "", "", MAIL_CONFIG, MAIL_SECTION, "tls_disable"]
    ConfigSettings["smtpauth_disable"] = ['boolean', 'Disable SMTP Auth', 309, False, "", "", MAIL_CONFIG, MAIL_SECTION, "smtpauth_disable"]

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
                # filename, section = None, type = "string", entry, default = "", bounds = None):
                (ConfigSettings[entry])[3] = ReadSingleConfigValue(entry = List[8], filename = GENMON_CONFIG, section =  List[7], type = List[0], default = List[3], bounds = List[5])
            elif List[6] == MAIL_CONFIG:
                (ConfigSettings[entry])[3] = ReadSingleConfigValue(entry = List[8], filename = MAIL_CONFIG, section = List[7], type = List[0], default = List[3])
            else:
                LogError("Invaild Config File in ReadSettingsFromFile: " + str(List[6]))

        GetToolTips(ConfigSettings)
    except Exception as e1:
        LogErrorLine("Error in ReadSettingsFromFile: " + entry + ": "+ str(e1))

    return ConfigSettings


#-------------------------------------------------------------------------------
def GetAllConfigValues(FileName, section):

    ReturnDict = {}
    try:
        config = MyConfig(filename = FileName, section = section)

        for (key, value) in config.GetList():
            ReturnDict[key.lower()] = value
    except Exception as e1:
        LogErrorLine("Error GetAllConfigValues: " + FileName + ": "+ str(e1) )

    return ReturnDict

#-------------------------------------------------------------------------------
def GetControllerInfo(request = None):

    ReturnValue = "Evolution, Air Cooled"
    try:
        if request.lower() == "controller":
            ReturnValue = "Evolution, Air Cooled"
        if request.lower() == "fueltype":
            ReturnValue = "Propane"

        if not len(GStartInfo):
            return ReturnValue

        if request.lower() == "controller":
            return GStartInfo["Controller"]
        if request.lower() == "fueltype":
            return GStartInfo["fueltype"]
    except Exception as e1:
        LogErrorLine("Error in GetControllerInfo: " + str(e1))
        pass

    return ReturnValue

#-------------------------------------------------------------------------------
def CacheToolTips():

    global CachedToolTips
    global ControllerType
    global CachedRegisterDescriptions

    try:
        config_section = "generac_evo_nexus"
        pathtofile = os.path.dirname(os.path.realpath(__file__))

        # get controller used
        if ConfigFiles[GENMON_CONFIG].HasOption('controllertype'):
            config_section = ConfigFiles[GENMON_CONFIG].ReadValue('controllertype')
        else:
            config_section = "generac_evo_nexus"

        if not len(config_section):
            config_section = "generac_evo_nexus"

        # H_100
        ControllerType = config_section

        if ControllerType == "h_100":
            try:
                if len(GStartInfo["Controller"]) and not "H-100" in GStartInfo["Controller"]:
                    # Controller is G-Panel
                    config_section = "g_panel"

            except Exception as e1:
                LogError("Error reading Controller Type for H-100: " + str(e1))
        CachedRegisterDescriptions = GetAllConfigValues(pathtofile + "/data/tooltips.txt", config_section)

        CachedToolTips = GetAllConfigValues(pathtofile + "/data/tooltips.txt", "ToolTips")

    except Exception as e1:
        LogErrorLine("Error reading tooltips.txt " + str(e1) )

#-------------------------------------------------------------------------------
def GetToolTips(ConfigSettings):

    try:

        for entry, List in ConfigSettings.items():
            try:
                (ConfigSettings[entry])[4] = CachedToolTips[entry.lower()]
            except:
                #self.LogError("Error in GetToolTips: " + entry)
                pass    # TODO

    except Exception as e1:
        LogErrorLine("Error in GetToolTips: " + str(e1))

#-------------------------------------------------------------------------------
def SaveSettings(query_string):

    try:

        # e.g. {'displayunknown': ['true']}
        settings = dict(parse_qs(query_string, 1))
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

        try:
            config = ConfigFiles[FileName]
        except Exception as e1:
            LogErrorLine("Unknow file in UpdateConfigFile: " + FileName + ": " + str(e1))
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

    try:
        Restarting = True
        if sys.version_info >= (3, 0):
            if not RunBashScript("startgenmon.sh restart -p 3 -c " + ConfigFilePath):
                LogError("Error in Restart")
        else:
            if not RunBashScript("startgenmon.sh restart -c " + ConfigFilePath):
                LogError("Error in Restart")
    except Exception as e1:
        LogErrorLine("Error in Restart: " + str(e1))
#-------------------------------------------------------------------------------
def Update():
    # update
    try:
        if sys.version_info >= (3, 0):
            if not RunBashScript("genmonmaint.sh -u -n -p 3"):
                LogError("Error in Update")
        else:
            if not RunBashScript("genmonmaint.sh -u -n"):   # update no prompt
                LogError("Error in Update")
        # now restart
        Restart()
    except Exception as e1:
        LogErrorLine("Error in Update: " + str(e1))

#-------------------------------------------------------------------------------
def Backup():
    # update
    if not RunBashScript("genmonmaint.sh -b -c " + ConfigFilePath):   # backup
        LogError("Error in Backup")

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
        if not os.path.isfile(CertFile):
            LogConsole("Missing cert file : " + CertFile)
            return False
        if not os.path.isfile(KeyFile):
            LogConsole("Missing key file : " + KeyFile)
            return False
    except Exception as e1:
        LogErrorLine("Error in CheckCertFiles: Unable to open Cert or Key file: " + CertFile + ", " + KeyFile + " : "+ str(e1))
        return False

    return True
#-------------------------------------------------------------------------------
def generate_adhoc_ssl_context():
        #Generates an adhoc SSL context web server.
        try:
            from OpenSSL import crypto
            import ssl

            import tempfile
            import atexit
            from random import random

            cert = crypto.X509()
            cert.set_serial_number(int(random() * sys.maxsize))
            cert.gmtime_adj_notBefore(0)
            cert.gmtime_adj_notAfter(60 * 60 * 24 * 365)

            subject = cert.get_subject()
            subject.CN = '*'
            subject.O = 'Dummy Certificate'

            issuer = cert.get_issuer()
            issuer.CN = 'Untrusted Authority'
            issuer.O = 'Self-Signed'

            pkey = crypto.PKey()
            pkey.generate_key(crypto.TYPE_RSA, 2048)
            cert.set_pubkey(pkey)
            cert.sign(pkey, 'sha256')

            cert_handle, cert_file = tempfile.mkstemp()
            pkey_handle, pkey_file = tempfile.mkstemp()
            atexit.register(os.remove, pkey_file)
            atexit.register(os.remove, cert_file)

            os.write(cert_handle, crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
            os.write(pkey_handle, crypto.dump_privatekey(crypto.FILETYPE_PEM, pkey))
            os.close(cert_handle)
            os.close(pkey_handle)
            # ctx = ssl.SSLContext(ssl.PROTOCOL_TLS)
            ctx = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
            ctx.load_cert_chain(cert_file, pkey_file)
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        except Exception as e1:
            LogError("Error in generate_adhoc_ssl_context: " + str(e1))
            return None
#-------------------------------------------------------------------------------
def LoadConfig():

    global log
    global clientport
    global loglocation
    global bUseSecureHTTP
    global LdapServer
    global LdapBase
    global LdapAdminGroup
    global LdapReadOnlyGroup

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
    LdapServer = None
    LdapBase = None
    LdapAdminGroup = None
    LdapReadOnlyGroup = None

    try:

        # heartbeat server port, must match value in check_generator_system.py and any calling client apps
        if ConfigFiles[GENMON_CONFIG].HasOption('server_port'):
            clientport = ConfigFiles[GENMON_CONFIG].ReadValue('server_port', return_type = int, default = ProgramDefaults.ServerPort)

        if ConfigFiles[GENMON_CONFIG].HasOption('loglocation'):
            loglocation = ConfigFiles[GENMON_CONFIG].ReadValue('loglocation')

        # log errors in this module to a file
        log = SetupLogger("genserv", loglocation + "genserv.log")

        if ConfigFiles[GENMON_CONFIG].HasOption('usehttps'):
            bUseSecureHTTP = ConfigFiles[GENMON_CONFIG].ReadValue('usehttps', return_type = bool)

        if ConfigFiles[GENMON_CONFIG].HasOption('http_port'):
            HTTPPort = ConfigFiles[GENMON_CONFIG].ReadValue('http_port', return_type = int, default = 8000)

        if ConfigFiles[GENMON_CONFIG].HasOption('favicon'):
            favicon = ConfigFiles[GENMON_CONFIG].ReadValue('favicon')

        # user name and password require usehttps = True
        if bUseSecureHTTP:
            if ConfigFiles[GENMON_CONFIG].HasOption('ldap_server'):
                LdapServer = ConfigFiles[GENMON_CONFIG].ReadValue('ldap_server', default = "")
                LdapServer = LdapServer.strip()
                if LdapServer == "":
                    LdapServer = None
                else:
                    if ConfigFiles[GENMON_CONFIG].HasOption('ldap_base'):
                        LdapBase = ConfigFiles[GENMON_CONFIG].ReadValue('ldap_base', default = "")
                    if ConfigFiles[GENMON_CONFIG].HasOption('ldap_admingroup'):
                        LdapAdminGroup = ConfigFiles[GENMON_CONFIG].ReadValue('ldap_admingroup', default = "")
                    if ConfigFiles[GENMON_CONFIG].HasOption('ldap_readonlygroup'):
                        LdapReadOnlyGroup = ConfigFiles[GENMON_CONFIG].ReadValue('ldap_readonlygroup', default = "")
                    if LdapBase == "":
                        LdapBase = None
                    if LdapAdminGroup == "":
                        LdapAdminGroup = None
                    if LdapReadOnlyGroup == "":
                        LdapReadOnlyGroup = None
                    if LdapReadOnlyGroup == None and LdapAdminGroup == None or LdapBase == None:
                        LdapServer = None

            if ConfigFiles[GENMON_CONFIG].HasOption('http_user'):
                HTTPAuthUser = ConfigFiles[GENMON_CONFIG].ReadValue('http_user', default = "")
                HTTPAuthUser = HTTPAuthUser.strip()
                 # No user name or pass specified, disable
                if HTTPAuthUser == "":
                    HTTPAuthUser = None
                    HTTPAuthPass = None
                elif ConfigFiles[GENMON_CONFIG].HasOption('http_pass'):
                    HTTPAuthPass = ConfigFiles[GENMON_CONFIG].ReadValue('http_pass', default = "")
                    HTTPAuthPass = HTTPAuthPass.strip()
                if HTTPAuthUser != None and HTTPAuthPass != None:
                    if ConfigFiles[GENMON_CONFIG].HasOption('http_user_ro'):
                        HTTPAuthUser_RO = ConfigFiles[GENMON_CONFIG].ReadValue('http_user_ro', default = "")
                        HTTPAuthUser_RO = HTTPAuthUser_RO.strip()
                        if HTTPAuthUser_RO == "":
                            HTTPAuthUser_RO = None
                            HTTPAuthPass_RO = None
                        elif ConfigFiles[GENMON_CONFIG].HasOption('http_pass_ro'):
                            HTTPAuthPass_RO = ConfigFiles[GENMON_CONFIG].ReadValue('http_pass_ro', default = "")
                            HTTPAuthPass_RO = HTTPAuthPass_RO.strip()

            HTTPSPort = ConfigFiles[GENMON_CONFIG].ReadValue('https_port', return_type = int, default = 443)

        if bUseSecureHTTP:
            app.secret_key = os.urandom(12)
            OldHTTPPort = HTTPPort
            HTTPPort = HTTPSPort
            if ConfigFiles[GENMON_CONFIG].HasOption('useselfsignedcert'):
                bUseSelfSignedCert = ConfigFiles[GENMON_CONFIG].ReadValue('useselfsignedcert', return_type = bool)

                if bUseSelfSignedCert:
                    SSLContext = generate_adhoc_ssl_context()   #  create our own self signed cert
                    if SSLContext == None:
                        SSLContext = 'adhoc'    # Use Flask supplied self signed cert
                else:
                    if ConfigFiles[GENMON_CONFIG].HasOption('certfile') and ConfigFiles[GENMON_CONFIG].HasOption('keyfile'):
                        CertFile = ConfigFiles[GENMON_CONFIG].ReadValue('certfile')
                        KeyFile = ConfigFiles[GENMON_CONFIG].ReadValue('keyfile')
                        if CheckCertFiles(CertFile, KeyFile):
                            SSLContext = (CertFile, KeyFile)    # tuple
                        else:
                            # if we get here then we have a username/login, but do not use SSL
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
        MyClientInterface.Close()
    except Exception as e1:
        LogErrorLine("Error in close: " + str(e1))

    LogError("genserv closed.")
    if not NoExit:
        sys.exit(0)

#-------------------------------------------------------------------------------
if __name__ == "__main__":

    address=ProgramDefaults.LocalHost
    ConfigFilePath='/etc/'

    # log errors in this module to a file
    console = SetupLogger("genserv_console", log_file = "", stream = True)

    HelpStr = '\nsudo python genserv.py -a <IP Address or localhost> -c <path to genmon config file>\n'

    try:
        ConfigFilePath = ProgramDefaults.ConfPath
        opts, args = getopt.getopt(sys.argv[1:],"hc:a:",["help","configpath=","address="])
    except getopt.GetoptError:
        console.error("Invalid command line argument.")
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            console.error(HelpStr)
            sys.exit()
        elif opt in ("-a", "--address"):
            address = arg
        elif opt in ("-c", "--configpath"):
            ConfigFilePath = arg
            ConfigFilePath = ConfigFilePath.strip()
    # NOTE: signal handler is not compatible with the exception handler around app.run()
    #atexit.register(Close)
    #signal.signal(signal.SIGTERM, Close)
    #signal.signal(signal.SIGINT, Close)

    MAIL_CONFIG = ConfigFilePath + "mymail.conf"
    GENMON_CONFIG = ConfigFilePath + "genmon.conf"
    GENLOADER_CONFIG = ConfigFilePath + "genloader.conf"
    GENSMS_CONFIG = ConfigFilePath + "gensms.conf"
    MYMODEM_CONFIG = ConfigFilePath + "mymodem.conf"
    GENPUSHOVER_CONFIG = ConfigFilePath + "genpushover.conf"
    GENMQTT_CONFIG = ConfigFilePath + "genmqtt.conf"
    GENSLACK_CONFIG = ConfigFilePath + "genslack.conf"
    GENGPIOIN_CONFIG = ConfigFilePath + "gengpioin.conf"
    GENEXERCISE_CONFIG = ConfigFilePath + "genexercise.conf"
    GENEMAIL2SMS_CONFIG = ConfigFilePath + "genemail2sms.conf"
    GENTANKUTIL_CONFIG = ConfigFilePath + "gentankutil.conf"
    GENALEXA_CONFIG = ConfigFilePath + "genalexa.conf"
    GENSNMP_CONFIG = ConfigFilePath + "gensnmp.conf"

    if os.geteuid() != 0:
        LogConsole("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'.")
        sys.exit(1)

    ConfigFileList = [GENMON_CONFIG, MAIL_CONFIG, GENLOADER_CONFIG, GENSMS_CONFIG, MYMODEM_CONFIG, GENPUSHOVER_CONFIG, GENMQTT_CONFIG, GENSLACK_CONFIG, GENGPIOIN_CONFIG, GENEXERCISE_CONFIG, GENEMAIL2SMS_CONFIG, GENTANKUTIL_CONFIG, GENALEXA_CONFIG, GENSNMP_CONFIG]

    for ConfigFile in ConfigFileList:
        if not os.path.isfile(ConfigFile):
            LogConsole("Missing config file : " + ConfigFile)
            sys.exit(1)

    ConfigFiles = {}
    for ConfigFile in ConfigFileList:
        ConfigFiles[ConfigFile] = MyConfig(filename = ConfigFile, log = console)

    AppPath = sys.argv[0]
    if not LoadConfig():
        LogConsole("Error reading configuraiton file.")
        sys.exit(1)

    for ConfigFile in ConfigFileList:
        ConfigFiles[ConfigFile].log = log

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

    startcount = 0
    while startcount <= 4:
        try:
            MyClientInterface = ClientInterface(host = address, port = clientport, log = log)
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

    try:
        data = MyClientInterface.ProcessMonitorCommand("generator: start_info_json")
        GStartInfo = json.loads(data)
    except Exception as e1:
        LogError("Error getting start info : " + str(e1))
        LogError("Data returned from start_info_json: "  + data)
        sys.exit(1)

    CacheToolTips()
    while True:
        try:
            app.run(host="0.0.0.0", port=HTTPPort, threaded = True, ssl_context=SSLContext, use_reloader = False, debug = False)

        except Exception as e1:
            LogErrorLine("Error in app.run: " + str(e1))
            #Errno 98
            if e1.errno != errno.EADDRINUSE: # and e1.errno != errno.EIO:
                sys.exit(1)
            time.sleep(2)
            if Closing:
                sys.exit(0)
            Restart()
