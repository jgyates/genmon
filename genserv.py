# -------------------------------------------------------------------------------
#    FILE: genserv.py
# PURPOSE: Flask app for generator monitor web app
#
#  AUTHOR: Jason G Yates
#    DATE: 20-Dec-2016
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

from __future__ import print_function

import collections
import errno
import json
import os
import os.path
import signal
import subprocess
import sys
import threading
import time

try:
    from flask import (
        Flask,
        jsonify,
        make_response,
        redirect,
        render_template,
        request,
        send_file,
        session,
        url_for,
    )
except Exception as e1:
    print(
        "\n\nThis program requires the Flask library. Please see the project documentation at https://github.com/jgyates/genmon.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)

try:
    import pyotp
except Exception as e1:
    print(
        "\n\nThis program requires the pyotp library. Please see the project documentation at https://github.com/jgyates/genmon.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)

try:
    from genmonlib.myclient import ClientInterface
    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.mymail import MyMail
    from genmonlib.mysupport import MySupport
    from genmonlib.program_defaults import ProgramDefaults

except Exception as e1:
    print(
        "\n\nThis program requires the modules located in the genmonlib directory in the original github repository.\n"
    )
    print(
        "Please see the project documentation at https://github.com/jgyates/genmon.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)

if sys.version_info[0] < 3:
    from urlparse import parse_qs, parse_qsl, urlparse
else:
    from urllib.parse import urlparse
    from urllib.parse import parse_qs
    from urllib.parse import parse_qsl

import datetime
import re

# -------------------------------------------------------------------------------
app = Flask(__name__, static_url_path="")

# this allows the flask support to be extended on a per site basis but sill allow for
# updates via the main github repository. If genservex.py exists, load it
if os.path.isfile(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "genservext.py")
):
    import genservext

app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 300

HTTPAuthUser = None
HTTPAuthPass = None
HTTPAuthUser_RO = None
HTTPAuthPass_RO = None
LdapServer = None
LdapBase = None
DomainNetbios = None
LdapAdminGroup = None
LdapReadOnlyGroup = None

mail = None
bUseMFA = False
SecretMFAKey = None
MFA_URL = None
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

WebUILocked = False
LoginAttempts = 0
MaxLoginAttempts = 5
LockOutDuration = 5 * 60
LastLoginTime = datetime.datetime.now()
LastFailedLoginTime = datetime.datetime.now()
securityMessageSent = None

Closing = False
Restarting = False
ControllerType = "generac_evo_nexus"
CriticalLock = threading.Lock()
CachedToolTips = {}
CachedRegisterDescriptions = {}
# -------------------------------------------------------------------------------
@app.route("/logout")
def logout():
    try:
        # remove the session data
        if LoginActive():
            session["logged_in"] = False
            session["write_access"] = False
            session["mfa_ok"] = False
        return redirect(url_for("root"))
    except Exception as e1:
        LogError("Error on logout: " + str(e1))


# -------------------------------------------------------------------------------
@app.after_request
def add_header(r):
    """
    Force cache header
    """
    r.headers[
        "Cache-Control"
    ] = "no-cache, no-store, must-revalidate, public, max-age=0"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"

    return r


# -------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def root():

    if bUseMFA:
        if not "mfa_ok" in session or not session["mfa_ok"] == True:
            session["logged_in"] = False
            session["write_access"] = False
            session["mfa_ok"] = False
            redirect(url_for("root"))
    return ServePage("index.html")


# -------------------------------------------------------------------------------
@app.route("/verbose", methods=["GET"])
def verbose():

    return ServePage("index_verbose.html")


# -------------------------------------------------------------------------------
@app.route("/low", methods=["GET"])
def lowbandwidth():

    return ServePage("index_lowbandwith.html")


# -------------------------------------------------------------------------------
@app.route("/internal", methods=["GET"])
def display_internal():

    return ServePage("internal.html")


# -------------------------------------------------------------------------------
@app.route("/locked", methods=["GET"])
def locked():

    LogError("Locked Page")
    return render_template("locked.html")

# -------------------------------------------------------------------------------
@app.route("/upload", methods=["PUT"])
def upload():
    # TODO
    LogError("genserv: Upload")
    return redirect(url_for("root"))

# -------------------------------------------------------------------------------
def ServePage(page_file):

    if LoginActive():
        if not session.get("logged_in"):
            return render_template("login.html")
        else:
            return app.send_static_file(page_file)
    else:
        return app.send_static_file(page_file)


# -------------------------------------------------------------------------------
@app.route("/mfa", methods=["POST"])
def mfa_auth():

    try:
        if bUseMFA:
            if ValidateOTP(request.form["code"]):
                session["mfa_ok"] = True
                return redirect(url_for("root"))
            else:
                session["logged_in"] = False
                session["write_access"] = False
                session["mfa_ok"] = False
                return redirect(url_for("logout"))
        else:
            return redirect(url_for("root"))
    except Exception as e1:
        LogErrorLine("Error in mfa_auth: " + str(e1))

    return render_template("login.html")


# -------------------------------------------------------------------------------
def admin_login_helper():

    global LoginAttempts

    LoginAttempts = 0
    try:
        if bUseMFA:
            # GetOTP()
            response = make_response(render_template("mfa.html"))
            return response
        else:
            return redirect(url_for("root"))
    except Exception as e1:
        LogErrorLine("Error in admin_login_helper: " + str(e1))
        return False


# -------------------------------------------------------------------------------
@app.route("/", methods=["POST"])
def do_admin_login():

    CheckLockOutDuration()
    if WebUILocked:
        next_time = (datetime.datetime.now() - LastFailedLoginTime).total_seconds()
        str_seconds = str(int(LockOutDuration - next_time))
        response = make_response(render_template("locked.html", time=str_seconds))
        response.headers["Content-type"] = "text/html; charset=utf-8"
        response.mimetype = "text/html; charset=utf-8"
        return response

    if (
        request.form["password"] == HTTPAuthPass
        and request.form["username"].lower() == HTTPAuthUser.lower()
    ):
        session["logged_in"] = True
        session["write_access"] = True
        LogError("Admin Login")
        return admin_login_helper()
    elif (
        request.form["password"] == HTTPAuthPass_RO
        and request.form["username"].lower() == HTTPAuthUser_RO.lower()
    ):
        session["logged_in"] = True
        session["write_access"] = False
        LogError("Limited Rights Login")
        return admin_login_helper()
    elif doLdapLogin(request.form["username"], request.form["password"]):
        return admin_login_helper()
    elif request.form["username"] != "":
        LogError("Invalid login: " + request.form["username"])
        CheckFailedLogin()
        return render_template("login.html")
    else:
        return render_template("login.html")


# -------------------------------------------------------------------------------
def CheckLockOutDuration():

    global WebUILocked
    global LoginAttempts
    global securityMessageSent

    if MaxLoginAttempts == 0:
        return

    if LoginAttempts >= MaxLoginAttempts:
        if (
            datetime.datetime.now() - LastFailedLoginTime
        ).total_seconds() > LockOutDuration:
            WebUILocked = False
            LoginAttempts = 0
        else:
            WebUILocked = True
            # send message to user only once every 4 hours
            if securityMessageSent == None or (
                (datetime.datetime.now() - securityMessageSent).total_seconds()
                > (4 * 60)
            ):

                message = {
                    "title": "Security Warning",
                    "body": "Genmon login is locked due to exceeding the maximum login attempts.",
                    "type": "error",
                    "oncedaily": False,
                    "onlyonce": False,
                }
                command = "generator: notify_message=" + json.dumps(message)

                data = MyClientInterface.ProcessMonitorCommand(command)
                securityMessageSent = datetime.datetime.now()


# -------------------------------------------------------------------------------
def CheckFailedLogin():

    global LoginAttempts
    global WebUILocked
    global LastFailedLoginTime

    LoginAttempts += 1
    LastFailedLoginTime = datetime.datetime.now()

    CheckLockOutDuration()


# -------------------------------------------------------------------------------
def doLdapLogin(username, password):
    if LdapServer == None or LdapServer == "":
        return False
    try:
        from ldap3 import ALL, NTLM, Connection, Server
        from ldap3.utils.dn import escape_rdn
        from ldap3.utils.conv import escape_filter_chars
    except ImportError as importException:
        LogError(
            "LDAP3 import not found, run 'sudo pip install ldap3 && sudo pip3 install ldap3'"
        )
        LogError(importException)
        return False

    HasAdmin = False
    HasReadOnly = False
    try:
        SplitName = username.split("\\")
        DomainName = SplitName[0]
        DomainName = DomainName.strip()
        AccountName = SplitName[1]
        AccountName = AccountName.strip()
    except IndexError:
        LogError("Using domain name in config file")
        DomainName = DomainNetbios
        AccountName = username.strip()
    try:
        server = Server(LdapServer, get_info=ALL)
        conn = Connection(
            server,
            user="{}\\{}".format(DomainName, AccountName),
            password=password,
            authentication=NTLM,
            auto_bind=True,
        )
        loginbasestr = escape_filter_chars("(&(objectclass=user)(sAMAccountName=" + AccountName + "))")
        conn.search(
            LdapBase,
            loginbasestr,
            attributes=["memberOf"],
        )
        for user in sorted(conn.entries):
            for group in user.memberOf:
                if group.upper().find("CN=" + LdapAdminGroup.upper() + ",") >= 0:
                    HasAdmin = True
                elif group.upper().find("CN=" + LdapReadOnlyGroup.upper() + ",") >= 0:
                    HasReadOnly = True
        conn.unbind()
    except Exception:
        LogError("Error in LDAP login. Check credentials and config parameters")

    session["logged_in"] = HasAdmin or HasReadOnly
    session["write_access"] = HasAdmin
    if HasAdmin:
        LogError("Admin Login via LDAP")
    elif HasReadOnly:
        LogError("Limited Rights Login via LDAP")
    else:
        LogError("No rights for login via LDAP")

    return HasAdmin or HasReadOnly


# -------------------------------------------------------------------------------
@app.route("/cmd/<command>")
def command(command):

    if Closing or Restarting:
        return jsonify("Closing")
    if HTTPAuthUser == None or HTTPAuthPass == None:
        return ProcessCommand(command)

    if not session.get("logged_in"):
        return render_template("login.html")
    else:
        return ProcessCommand(command)


# -------------------------------------------------------------------------------
def ProcessCommand(command):

    try:
        command_list = [
            "status",
            "status_json",
            "outage",
            "outage_json",
            "maint",
            "maint_json",
            "logs",
            "logs_json",
            "monitor",
            "monitor_json",
            "registers_json",
            "allregs_json",
            "start_info_json",
            "gui_status_json",
            "power_log_json",
            "power_log_clear",
            "getbase",
            "getsitename",
            "setexercise",
            "setquiet",
            "setremote",
            "settime",
            "sendregisters",
            "sendlogfiles",
            "getdebug",
            "status_num_json",
            "maint_num_json",
            "monitor_num_json",
            "outage_num_json",
            "get_maint_log_json",
            "add_maint_log",
            "clear_maint_log",
            "delete_row_maint_log",
            "edit_row_maint_log",
            "support_data_json",
            "fuel_log_clear",
            "notify_message",
            "set_button_command",
        ]
        # LogError(request.url)
        if command in command_list:
            finalcommand = "generator: " + command

            try:
                if command in [
                    "setexercise",
                    "setquiet",
                    "setremote",
                    "add_maint_log",
                    "delete_row_maint_log",
                    "edit_row_maint_log",
                ] and not session.get("write_access", True):
                    return jsonify("Read Only Mode")

                if command == "setexercise":
                    settimestr = request.args.get("setexercise", 0, type=str)
                    if settimestr:
                        finalcommand += "=" + settimestr
                elif command == "setquiet":
                    # /cmd/setquiet?setquiet=off
                    setquietstr = request.args.get("setquiet", 0, type=str)
                    if setquietstr:
                        finalcommand += "=" + setquietstr
                elif command == "setremote":
                    setremotestr = request.args.get("setremote", 0, type=str)
                    if setremotestr:
                        finalcommand += "=" + setremotestr

                if command == "power_log_json":
                    # example: /cmd/power_log_json?power_log_json=1440
                    setlogstr = request.args.get("power_log_json", 0, type=str)
                    if setlogstr:
                        finalcommand += "=" + setlogstr
                if command == "add_maint_log":
                    # use direct method instead of request.args.get due to unicoode
                    # input for add_maint_log for international users
                    input = request.args["add_maint_log"]
                    finalcommand += "=" + input
                if command == "delete_row_maint_log":
                    # use direct method instead of request.args.get due to unicoode
                    # input for add_maint_log for international users
                    input = request.args["delete_row_maint_log"]
                    finalcommand += "=" + input
                if command == "edit_row_maint_log":
                    # use direct method instead of request.args.get due to unicoode
                    # input for add_maint_log for international users
                    input = request.args["edit_row_maint_log"]
                    finalcommand += "=" + input
                if command == "set_button_command":
                    input = request.args["set_button_command"]
                    finalcommand += "=" + input
                data = MyClientInterface.ProcessMonitorCommand(finalcommand)

            except Exception as e1:
                data = "Retry"
                LogErrorLine("Error on command function: " + str(e1))

            if command in [
                "status_json",
                "outage_json",
                "maint_json",
                "monitor_json",
                "logs_json",
                "registers_json",
                "allregs_json",
                "start_info_json",
                "gui_status_json",
                "power_log_json",
                "status_num_json",
                "maint_num_json",
                "monitor_num_json",
                "outage_num_json",
                "get_maint_log_json",
                "support_data_json",
            ]:

                if command in ["start_info_json"]:
                    try:
                        StartInfo = json.loads(data)
                        StartInfo["write_access"] = session.get("write_access", True)
                        if not StartInfo["write_access"]:
                            StartInfo["pages"]["settings"] = False
                            StartInfo["pages"]["notifications"] = False
                        StartInfo["LoginActive"] = LoginActive()
                        data = json.dumps(StartInfo, sort_keys=False)
                    except Exception as e1:
                        LogErrorLine("Error in JSON parse / decode: " + str(e1))
                return data
            return jsonify(data)

        elif command in ["updatesoftware"]:
            if session.get("write_access", True):
                Update()
                return "OK"
            else:
                return "Access denied"

        elif command in ["getfavicon"]:
            return jsonify(favicon)

        elif command in ["settings"]:
            if session.get("write_access", True):
                data = ReadSettingsFromFile()
                return json.dumps(data, sort_keys=False)
            else:
                return "Access denied"

        elif command in ["notifications"]:
            data = ReadNotificationsFromFile()
            return jsonify(data)
        elif command in ["setnotifications"]:
            if session.get("write_access", True):
                SaveNotifications(request.args.get("setnotifications", 0, type=str))
            return "OK"

        # Add on items
        elif command in ["get_add_on_settings", "set_add_on_settings"]:
            if session.get("write_access", True):
                if command == "get_add_on_settings":
                    data = GetAddOnSettings()
                    return json.dumps(data, sort_keys=False)
                elif command == "set_add_on_settings":
                    SaveAddOnSettings(
                        request.args.get("set_add_on_settings", default=None, type=str)
                    )
                else:
                    return "OK"
            return "OK"

        elif command in ["get_advanced_settings", "set_advanced_settings"]:
            if session.get("write_access", True):
                if command == "get_advanced_settings":
                    data = ReadAdvancedSettingsFromFile()
                    return json.dumps(data, sort_keys=False)
                elif command == "set_advanced_settings":
                    SaveAdvancedSettings(
                        request.args.get(
                            "set_advanced_settings", default=None, type=str
                        )
                    )
                else:
                    return "OK"
            return "OK"

        elif command in ["setsettings"]:
            if session.get("write_access", True):
                SaveSettings(request.args.get("setsettings", 0, type=str))
            return "OK"

        elif command in ["getreglabels"]:
            return jsonify(CachedRegisterDescriptions)

        elif command in ["restart"]:
            if session.get("write_access", True):
                Restart()
        elif command in ["stop"]:
            if session.get("write_access", True):
                Close()
                sys.exit(0)
        elif command in ["shutdown"]:
            if session.get("write_access", True):
                Shutdown()
                sys.exit(0)
        elif command in ["reboot"]:
            if session.get("write_access", True):
                Reboot()
                sys.exit(0)
        elif command in ["backup"]:
            if session.get("write_access", True):
                Backup()  # Create backup file
                # Now send the file
                pathtofile = os.path.dirname(os.path.realpath(__file__))
                return send_file(
                    os.path.join(pathtofile, "genmon_backup.tar.gz"), as_attachment=True
                )
        elif command in ["get_logs"]:
            if session.get("write_access", True):
                GetLogs()  # Create log archive file
                # Now send the file
                pathtofile = os.path.dirname(os.path.realpath(__file__))
                return send_file(
                    os.path.join(pathtofile, "genmon_logs.tar.gz"), as_attachment=True
                )
        elif command in ["test_email"]:
            return SendTestEmail(request.args.get("test_email", default=None, type=str))
        else:
            return render_template("command_template.html", command=command)
    except Exception as e1:
        LogErrorLine("Error in Process Command: " + command + ": " + str(e1))
        return render_template("command_template.html", command=command)


# -------------------------------------------------------------------------------
def LoginActive():

    if HTTPAuthUser != None and HTTPAuthPass != None or LdapServer != None:
        return True
    return False


# -------------------------------------------------------------------------------
def SendTestEmail(query_string):
    try:
        if query_string == None or not len(query_string):
            return "No parameters given for email test."
        parameters = json.loads(query_string)
        if not len(parameters):
            return "No parameters"  # nothing to change return

    except Exception as e1:
        LogErrorLine("Error getting parameters in SendTestEmail: " + str(e1))
        return "Error getting parameters in email test: " + str(e1)
    try:
        smtp_server = str(parameters["smtp_server"])
        smtp_server = smtp_server.strip()
        smtp_port = int(parameters["smtp_port"])
        email_account = str(parameters["email_account"])
        email_account = email_account.strip()
        sender_account = str(parameters["sender_account"])
        sender_account = sender_account.strip()
        if not len(sender_account):
            sender_account == None
        sender_name = str(parameters["sender_name"])
        sender_name = sender_name.strip()
        if not len(sender_name):
            sender_name == None
        recipient = str(parameters["recipient"])
        recipient = recipient.strip()
        password = str(parameters["password"])
        if parameters["use_ssl"].lower() == "true":
            use_ssl = True
        else:
            use_ssl = False

        if parameters["tls_disable"].lower() == "true":
            tls_disable = True
        else:
            tls_disable = False

        if parameters["smtpauth_disable"].lower() == "true":
            smtpauth_disable = True
        else:
            smtpauth_disable = False

    except Exception as e1:
        LogErrorLine("Error parsing parameters in SendTestEmail: " + str(e1))
        LogError(str(parameters))
        return "Error parsing parameters in email test: " + str(e1)

    try:
        ReturnMessage = MyMail.TestSendSettings(
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            email_account=email_account,
            sender_account=sender_account,
            sender_name=sender_name,
            recipient=recipient,
            password=password,
            use_ssl=use_ssl,
            tls_disable=tls_disable,
            smtpauth_disable=smtpauth_disable,
        )
        return ReturnMessage
    except Exception as e1:
        LogErrorLine("Error sending test email : " + str(e1))
        return "Error sending test email : " + str(e1)


# -------------------------------------------------------------------------------
def GetAddOns():
    AddOnCfg = collections.OrderedDict()

    # Default icon name should be "Genmon" to get a generic icon
    try:
        # GENGPIO
        Temp = collections.OrderedDict()
        AddOnCfg["gengpio"] = collections.OrderedDict()
        AddOnCfg["gengpio"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gengpio", default=False
        )
        AddOnCfg["gengpio"]["title"] = "Genmon GPIO Outputs"
        AddOnCfg["gengpio"][
            "description"
        ] = "Genmon will set Raspberry Pi GPIO outputs (see documentation for details)"
        AddOnCfg["gengpio"]["icon"] = "rpi"
        AddOnCfg["gengpio"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gengpiopy-optional"
        AddOnCfg["gengpio"]["parameters"] = None

        # GENGPIOIN
        AddOnCfg["gengpioin"] = collections.OrderedDict()
        AddOnCfg["gengpioin"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gengpioin", default=False
        )
        AddOnCfg["gengpioin"]["title"] = "Genmon GPIO Inputs"
        AddOnCfg["gengpioin"][
            "description"
        ] = "Genmon will set Raspberry Pi GPIO inputs (see documentation for details)"
        AddOnCfg["gengpioin"]["icon"] = "rpi"
        AddOnCfg["gengpioin"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gengpioinpy-optional"
        AddOnCfg["gengpioin"]["parameters"] = collections.OrderedDict()
        AddOnCfg["gengpioin"]["parameters"]["trigger"] = CreateAddOnParam(
            ConfigFiles[GENGPIOIN_CONFIG].ReadValue(
                "trigger", return_type=str, default="falling"
            ),
            "list",
            "Set GPIO input to trigger on rising or falling edge.",
            bounds="falling,rising,both",
            display_name="GPIO Edge Trigger",
        )
        AddOnCfg["gengpioin"]["parameters"]["resistorpull"] = CreateAddOnParam(
            ConfigFiles[GENGPIOIN_CONFIG].ReadValue(
                "resistorpull", return_type=str, default="up"
            ),
            "list",
            "Set GPIO input internal pull up or pull down resistor.",
            bounds="up,down,off",
            display_name="Internal resistor pull",
        )
        AddOnCfg["gengpioin"]["parameters"]["bounce"] = CreateAddOnParam(
            ConfigFiles[GENGPIOIN_CONFIG].ReadValue(
                "bounce", return_type=int, default=0
            ),
            "int",
            "Minimum interval in milliseconds between valid input changes. Zero to disable, or positive whole number.",
            bounds="number",
            display_name="Software Debounce",
        )

        # GENGPIOLEDBLINK
        AddOnCfg["gengpioledblink"] = collections.OrderedDict()
        AddOnCfg["gengpioledblink"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gengpioledblink", default=False
        )
        AddOnCfg["gengpioledblink"]["title"] = "Genmon GPIO Output to blink LED"
        AddOnCfg["gengpioledblink"][
            "description"
        ] = "Genmon will blink LED connected to GPIO pin to indicate genmon status"
        AddOnCfg["gengpioledblink"]["icon"] = "rpi"
        AddOnCfg["gengpioledblink"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gengpioledblinkpy-optional"
        AddOnCfg["gengpioledblink"]["parameters"] = collections.OrderedDict()
        AddOnCfg["gengpioledblink"]["parameters"]["ledpin"] = CreateAddOnParam(
            ConfigFiles[GENGPIOLEDBLINK_CONFIG].ReadValue(
                "ledpin", return_type=int, default=12
            ),
            "int",
            "GPIO pin number that an LED is connected (valid numbers are 0 - 27)",
            bounds="required digits range:0:27",
            display_name="GPIO LED pin",
        )

        # GENLOG
        AddOnCfg["genlog"] = collections.OrderedDict()
        AddOnCfg["genlog"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="genlog", default=False
        )
        AddOnCfg["genlog"]["title"] = "Notifications to CSV Log"
        AddOnCfg["genlog"][
            "description"
        ] = "Log Genmon and utility state changes to a file. Log file is in text CSV format."
        AddOnCfg["genlog"]["icon"] = "csv"
        AddOnCfg["genlog"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genlogpy-optional"
        AddOnCfg["genlog"]["parameters"] = collections.OrderedDict()
        Args = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "args",
            return_type=str,
            section="genlog",
            default="-f /home/pi/genmon/LogFile.csv",
        )
        ArgList = Args.split()
        if len(ArgList) == 2:
            Value = ArgList[1]
        else:
            Value = ""
        AddOnCfg["genlog"]["parameters"]["Log File Name"] = CreateAddOnParam(
            Value,
            "string",
            "Filename for log. Full path of the file must be included (i.e. /home/pi/genmon/LogFile.csv)",
            bounds="required UnixFile",
            display_name="Log File Name",
        )

        # GENSMS
        AddOnCfg["gensms"] = collections.OrderedDict()
        AddOnCfg["gensms"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gensms", default=False
        )
        AddOnCfg["gensms"]["title"] = "Notifications via SMS - Twilio"
        AddOnCfg["gensms"][
            "description"
        ] = "Send Genmon and utility state changes via Twilio SMS"
        AddOnCfg["gensms"]["icon"] = "twilio"
        AddOnCfg["gensms"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensmspy-optional"
        AddOnCfg["gensms"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gensms"]["parameters"]["accountsid"] = CreateAddOnParam(
            ConfigFiles[GENSMS_CONFIG].ReadValue(
                "accountsid", return_type=str, default=""
            ),
            "string",
            "Twilio account SID. This can be obtained from a valid Twilio account",
            bounds="required minmax:10:50",
            display_name="Twilio Account SID",
        )
        AddOnCfg["gensms"]["parameters"]["authtoken"] = CreateAddOnParam(
            ConfigFiles[GENSMS_CONFIG].ReadValue(
                "authtoken", return_type=str, default=""
            ),
            "string",
            "Twilio authentication token. This can be obtained from a valid Twilio account",
            bounds="required minmax:10:50",
            display_name="Twilio Authentication Token",
        )
        AddOnCfg["gensms"]["parameters"]["to_number"] = CreateAddOnParam(
            ConfigFiles[GENSMS_CONFIG].ReadValue(
                "to_number", return_type=str, default=""
            ),
            "string",
            "Mobile number to send SMS message to. This can be any mobile number. Separate multilpe recipients with commas.",
            bounds="required InternationalPhone",
            display_name="Recipient Phone Number",
        )
        AddOnCfg["gensms"]["parameters"]["from_number"] = CreateAddOnParam(
            ConfigFiles[GENSMS_CONFIG].ReadValue(
                "from_number", return_type=str, default=""
            ),
            "string",
            "Number to send SMS message from. This should be a twilio phone number.",
            bounds="required InternationalPhone",
            display_name="Twilio Phone Number",
        )

        AddOnCfg = AddNotificationAddOnParam(AddOnCfg, "gensms", GENSMS_CONFIG)
        AddOnCfg = AddRetryAddOnParam(AddOnCfg, "gensms", GENSMS_CONFIG)

        # GENSMS_VOIP
        Description = "SMS Support vis VoIP using voip.ms"
        try:
            import voipms
        except Exception as e1:
            Description = (
                Description
                + "<br/><font color='red'>The required libraries for this add on are not installed, please run the installation script.</font>"
            )

        AddOnCfg["gensms_voip"] = collections.OrderedDict()
        AddOnCfg["gensms_voip"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gensms_voip", default=False
        )
        AddOnCfg["gensms_voip"]["title"] = "SMS via VoIP using voip.ms"

        AddOnCfg["gensms_voip"]["description"] = Description
        AddOnCfg["gensms_voip"]["icon"] = "voipms"
        AddOnCfg["gensms_voip"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensms_voippy-optional"
        AddOnCfg["gensms_voip"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gensms_voip"]["parameters"]["username"] = CreateAddOnParam(
            ConfigFiles[GENSMS_VOIP_CONFIG].ReadValue(
                "username", return_type=str, default=""
            ),
            "string",
            "Voip.ms account username",
            bounds="required minmax:5:50",
            display_name="VoIP.ms User Name",
        )
        AddOnCfg["gensms_voip"]["parameters"]["password"] = CreateAddOnParam(
            ConfigFiles[GENSMS_VOIP_CONFIG].ReadValue(
                "password", return_type=str, default=""
            ),
            "password",
            "VoIP.ms API password. This is NOT the account login, but rather then API password",
            bounds="required minmax:8:50",
            display_name="VoIP.ms API password",
        )
        AddOnCfg["gensms_voip"]["parameters"]["did"] = CreateAddOnParam(
            ConfigFiles[GENSMS_VOIP_CONFIG].ReadValue(
                "did", return_type=str, default=""
            ),
            "string",
            "DID number for your voip.ms account to send the SMS.",
            bounds="required InternationalPhone",
            display_name="Sender DID Number",
        )
        AddOnCfg["gensms_voip"]["parameters"]["destination"] = CreateAddOnParam(
            ConfigFiles[GENSMS_VOIP_CONFIG].ReadValue(
                "destination", return_type=str, default=""
            ),
            "string",
            "Mobile number to send SMS message to. This can be any mobile number. Separate multilpe recipients with commas.",
            bounds="required InternationalPhone",
            display_name="Recipient Phone Number",
        )
        # GENSMS_MODEM
        AddOnCfg["gensms_modem"] = collections.OrderedDict()
        AddOnCfg["gensms_modem"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gensms_modem", default=False
        )
        AddOnCfg["gensms_modem"]["title"] = "Notifications via SMS - LTE Hat"
        AddOnCfg["gensms_modem"][
            "description"
        ] = "Send Genmon and utility state changes via cellular SMS (additional hardware required)"
        AddOnCfg["gensms_modem"]["icon"] = "sms"
        AddOnCfg["gensms_modem"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensms_modempy-optional"
        AddOnCfg["gensms_modem"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gensms_modem"]["parameters"]["recipient"] = CreateAddOnParam(
            ConfigFiles[MYMODEM_CONFIG].ReadValue(
                "recipient", return_type=str, default=""
            ),
            "string",
            "Mobile number to send SMS message. This can be any mobile number. No dashes or spaces.",
            bounds="required InternationalPhone",
            display_name="Recipient Phone Number",
        )
        AddOnCfg["gensms_modem"]["parameters"]["port"] = CreateAddOnParam(
            ConfigFiles[MYMODEM_CONFIG].ReadValue("port", return_type=str, default=""),
            "string",
            "This is the serial device to send AT modem commands. This *must* be different from the serial port used by the generator monitor software.",
            bounds="required UnixDevice",
            display_name="Modem Serial Port",
        )

        AddOnCfg["gensms_modem"]["parameters"]["rate"] = CreateAddOnParam(
            ConfigFiles[MYMODEM_CONFIG].ReadValue(
                "rate", return_type=int, default=115200
            ),
            "int",
            "The baud rate for the port. Use 115200 for the LTEPiHat.",
            bounds="required digits",
            display_name="Modem Serial Rate",
        )
        AddOnCfg["gensms_modem"]["parameters"]["log_at_commands"] = CreateAddOnParam(
            ConfigFiles[MYMODEM_CONFIG].ReadValue(
                "log_at_commands", return_type=bool, default=False
            ),
            "boolean",
            "Enable to log at commands to the log file.",
            display_name="Log AT Commands",
        )

        AddOnCfg = AddNotificationAddOnParam(AddOnCfg, "gensms_modem", MYMODEM_CONFIG)

        # modem type - select the type of modem used. For future use. Presently "LTEPiHat" is the only option
        # modem_type = LTEPiHat

        # GENPUSHOVER
        AddOnCfg["genpushover"] = collections.OrderedDict()
        AddOnCfg["genpushover"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="genpushover", default=False
        )
        AddOnCfg["genpushover"]["title"] = "Notifications via Pushover"
        AddOnCfg["genpushover"][
            "description"
        ] = "Send Genmon and utility state changes via Pushover service"
        AddOnCfg["genpushover"]["icon"] = "pushover"
        AddOnCfg["genpushover"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genpushoverpy-optional"
        AddOnCfg["genpushover"]["parameters"] = collections.OrderedDict()

        AddOnCfg["genpushover"]["parameters"]["appid"] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "appid", return_type=str, default=""
            ),
            "string",
            "Pushover app ID. This is generated by pushover.net when an application is created for your account.",
            bounds="required minmax:30:30",
            display_name="Application ID",
        )
        AddOnCfg["genpushover"]["parameters"]["userid"] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "userid", return_type=str, default=""
            ),
            "string",
            "Pushover User Key. Note: this is not your login user name but a key generated by pushover.net for your account",
            bounds="required minmax:30:30",
            display_name="Pushover User Key",
        )
        AddOnCfg["genpushover"]["parameters"]["pushsound"] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "pushsound", return_type=str, default="updown"
            ),
            "string",
            "Notification sound identifier. See https://pushover.net/api#sounds for a full list of sound IDs. All sounds must be lower case.",
            bounds="minmax:3:20",
            display_name="Push Sound",
        )
        AddOnCfg["genpushover"]["parameters"]["alarm_priority"] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "alarm_priority", return_type=str, default="NORMAL"
            ),
            "list",
            "Alarm Notification priority identifier. See https://pushover.net/api#priority",
            bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
            display_name="Alarm Priority",
        )
        AddOnCfg["genpushover"]["parameters"]["sw_update_priority"] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "sw_update_priority", return_type=str, default="NORMAL"
            ),
            "list",
            "Software Update Notification priority identifier. See https://pushover.net/api#priority",
            bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
            display_name="Software Update Priority",
        )
        AddOnCfg["genpushover"]["parameters"][
            "system_health_priority"
        ] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "system_health_priority", return_type=str, default="NORMAL"
            ),
            "list",
            "System Health Notification priority identifier. See https://pushover.net/api#priority",
            bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
            display_name="System Health Priority",
        )
        AddOnCfg["genpushover"]["parameters"]["fuel_priority"] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "fuel_priority", return_type=str, default="NORMAL"
            ),
            "list",
            "Fuel Level Notification priority identifier. See https://pushover.net/api#priority",
            bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
            display_name="Fuel Level Priority",
        )
        AddOnCfg["genpushover"]["parameters"]["outage_priority"] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "outage_priority", return_type=str, default="NORMAL"
            ),
            "list",
            "Fuel Level Notification priority identifier. See https://pushover.net/api#priority",
            bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
            display_name="Outage Priority",
        )
        AddOnCfg["genpushover"]["parameters"][
            "switch_state_priority"
        ] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "switch_state_priority", return_type=str, default="NORMAL"
            ),
            "list",
            "Switch State Notification priority identifier. See https://pushover.net/api#priority",
            bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
            display_name="Switch State Priority",
        )
        AddOnCfg["genpushover"]["parameters"]["run_state_priority"] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "run_state_priority", return_type=str, default="NORMAL"
            ),
            "list",
            "Run State Notification priority identifier. See https://pushover.net/api#priority",
            bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
            display_name="Run State Priority",
        )
        AddOnCfg["genpushover"]["parameters"][
            "service_state_priority"
        ] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "service_state_priority", return_type=str, default="NORMAL"
            ),
            "list",
            "Service State Notification priority identifier. See https://pushover.net/api#priority",
            bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
            display_name="Service State Priority",
        )
        AddOnCfg["genpushover"]["parameters"]["pi_state_priority"] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "pi_state_priority", return_type=str, default="NORMAL"
            ),
            "list",
            "Pi Hardware Sensor State Notification priority identifier. See https://pushover.net/api#priority",
            bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
            display_name="Pi Hardware Sensor State Priority",
        )

        AddOnCfg = AddNotificationAddOnParam(
            AddOnCfg, "genpushover", GENPUSHOVER_CONFIG
        )
        AddOnCfg = AddRetryAddOnParam(AddOnCfg, "genpushover", GENPUSHOVER_CONFIG)

        # GENSYSLOG
        AddOnCfg["gensyslog"] = collections.OrderedDict()
        AddOnCfg["gensyslog"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gensyslog", default=False
        )
        AddOnCfg["gensyslog"]["title"] = "Linux System Logging"
        AddOnCfg["gensyslog"][
            "description"
        ] = "Write generator and utility state changes to system log (/var/log/syslog)"
        AddOnCfg["gensyslog"]["icon"] = "linux"
        AddOnCfg["gensyslog"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensyslogpy-optional"
        AddOnCfg["gensyslog"]["parameters"] = None

        # GENMQTT
        AddOnCfg["genmqtt"] = collections.OrderedDict()
        AddOnCfg["genmqtt"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="genmqtt", default=False
        )
        AddOnCfg["genmqtt"]["title"] = "MQTT integration"
        AddOnCfg["genmqtt"][
            "description"
        ] = "Export Genmon data and status to MQTT server for automation integration"
        AddOnCfg["genmqtt"]["icon"] = "mqtt"
        AddOnCfg["genmqtt"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genmqttpy-optional"
        AddOnCfg["genmqtt"]["parameters"] = collections.OrderedDict()

        AddOnCfg["genmqtt"]["parameters"]["mqtt_address"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "mqtt_address", return_type=str, default=""
            ),
            "string",
            "Address of your MQTT server.",
            bounds="required IPAddress",
            display_name="MQTT Server Address",
        )
        AddOnCfg["genmqtt"]["parameters"]["mqtt_port"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "mqtt_port", return_type=int, default=1833
            ),
            "int",
            "The port of the MQTT server in a decimal number.",
            bounds="required digits",
            display_name="MQTT Server Port Number",
        )
        AddOnCfg["genmqtt"]["parameters"]["username"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "username", return_type=str, default=""
            ),
            "string",
            "This value is used for the username if your MQTT server requires authentication. Leave blank for no authentication.",
            bounds="minmax:4:50",
            display_name="MQTT Authentication Username",
        )
        AddOnCfg["genmqtt"]["parameters"]["password"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "password", return_type=str, default=""
            ),
            "password",
            "This value is used for the password if your MQTT server requires authentication. Leave blank for no authentication or no password.",
            bounds="minmax:4:50",
            display_name="MQTT Authentication Password",
        )
        AddOnCfg["genmqtt"]["parameters"]["poll_interval"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "poll_interval", return_type=float, default=2.0
            ),
            "float",
            "The time in seconds between requesting status from genmon. The default value is 2 seconds.",
            bounds="number",
            display_name="Poll Interval",
        )
        AddOnCfg["genmqtt"]["parameters"]["root_topic"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "root_topic", return_type=str, default=""
            ),
            "string",
            "(Optional) Prepend this value to the MQTT data path i.e. 'Home' would result in 'Home/generator/...''",
            bounds="minmax:1:50",
            display_name="Root Topic",
        )
        AddOnCfg["genmqtt"]["parameters"]["blacklist"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "blacklist", return_type=str, default=""
            ),
            "string",
            "(Optional) Names of data not exported to the MQTT server, separated by commas.",
            bounds="",
            display_name="Blacklist Filter",
        )
        AddOnCfg["genmqtt"]["parameters"]["flush_interval"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "flush_interval", return_type=float, default=0
            ),
            "float",
            "(Optional) Time in seconds where even unchanged values will be published to their MQTT topic. Set to zero to disable flushing.",
            bounds="number",
            display_name="Flush Interval",
        )
        AddOnCfg["genmqtt"]["parameters"]["numeric_json"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "numeric_json", return_type=bool, default=False
            ),
            "boolean",
            "If enabled will return numeric values in the Status, Maintenance and Outage topics as separate topics for unit, type and value.",
            bounds="",
            display_name="Numeric Topics",
        )
        AddOnCfg["genmqtt"]["parameters"]["numeric_json_object"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "numeric_json_object", return_type=bool, default=False
            ),
            "boolean",
            "If enabled will return a JSON object for numeric values in the Status, Maintenance and Outage topics as an object with unit, type and value members.",
            bounds="",
            display_name="JSON for Numerics",
        )
        AddOnCfg["genmqtt"]["parameters"]["strlist_json"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "strlist_json", return_type=bool, default=False
            ),
            "boolean",
            "If enabled will return a JSON list for any list of strings like the Outage log. Does not apply if JSON for Numerics is enabled.",
            bounds="",
            display_name="JSON for String Lists",
        )
        AddOnCfg["genmqtt"]["parameters"]["remove_spaces"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "remove_spaces", return_type=bool, default=False
            ),
            "boolean",
            "If enabled any spaces in the topic path will be converted to underscores",
            bounds="",
            display_name="Remove Spaces in Topic Path",
        )
        AddOnCfg["genmqtt"]["parameters"]["retain"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "retain", return_type=bool, default=False
            ),
            "boolean",
            "If enabled, published messages will be retained by the MQTT broker server after a the Add On disconnects from the server.",
            bounds="",
            display_name="Retain Data",
        )
        AddOnCfg["genmqtt"]["parameters"]["cert_authority_path"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "cert_authority_path", return_type=str, default=""
            ),
            "string",
            "(Optional) Full path to Certificate Authority file. Leave empty to not use SSL/TLS. If used port will be forced to 8883.",
            bounds="",
            display_name="SSL/TLS CA certificate file",
        )
        AddOnCfg["genmqtt"]["parameters"]["client_cert_path"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "client_cert_path", return_type=str, default=""
            ),
            "string",
            "Optional. Full path the client certificate file. Leave empty to not use MTLS.",
            bounds="",
            display_name="Client Certificate File",
        )
        AddOnCfg["genmqtt"]["parameters"]["client_key_path"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "client_key_path", return_type=str, default=""
            ),
            "string",
            "Optional. Full path the client key file. Leave empty to not use MTLS.",
            bounds="",
            display_name="Client Key File",
        )
        AddOnCfg["genmqtt"]["parameters"]["tls_version"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "tls_version", return_type=str, default="1.0"
            ),
            "list",
            "(Optional) TLS version used (integer). Default is 1.0. Must be 1.0, 1.1, or 1.2. This is ignored if a CA cert file is not used. ",
            bounds="1.0,1.1,1.2",
            display_name="TLS Version",
        )
        AddOnCfg["genmqtt"]["parameters"]["cert_reqs"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "cert_reqs", return_type=str, default="Required"
            ),
            "list",
            "(Optional) Defines the certificate requirements that the client imposes on the broker. Used if Certificate Authority file is used.",
            bounds="None,Optional,Required",
            display_name="Certificate Requirements",
        )
        AddOnCfg["genmqtt"]["parameters"]["client_id"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "client_id", return_type=str, default="genmon"
            ),
            "string",
            "Unique identifier. Must be unique for each instance of genmon and add on running on a given system. ",
            bounds="",
            display_name="Client ID",
        )

        # GENMQTTIN
        AddOnCfg["genmqttin"] = collections.OrderedDict()
        AddOnCfg["genmqttin"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="genmqttin", default=False
        )
        AddOnCfg["genmqttin"]["title"] = "MQTT Sensor Input"
        AddOnCfg["genmqttin"][
            "description"
        ] = "Import data from MQTT broker for genmon use"
        AddOnCfg["genmqttin"]["icon"] = "mqtt"
        AddOnCfg["genmqttin"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genmqttinpy-optional"
        AddOnCfg["genmqttin"]["parameters"] = collections.OrderedDict()

        AddOnCfg["genmqttin"]["parameters"]["topics"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "topics", return_type=str, default=""
            ),
            "string",
            "Comma separated list of MQTT topics to subscribe and import into genmon. All topics must return a numeric value or a string representation of a numeric value.",
            bounds="",
            display_name="Topics",
        )
        AddOnCfg["genmqttin"]["parameters"]["labels"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "labels", return_type=str, default=""
            ),
            "string",
            "Comma separated list of display names for each topic listed above. These will be the displayed label for each topic value.",
            bounds="",
            display_name="Displayed Name",
        )
        AddOnCfg["genmqttin"]["parameters"]["units"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "units", return_type=str, default=""
            ),
            "string",
            "Comma separated list of units for each topic listed above. If no labled is used for a given topic, use a space. If using the imported MQTT data for genmon calculations, for power use W or kW, for current use A, for voltage use V. ",
            bounds="",
            display_name="Units",
        )
        AddOnCfg["genmqttin"]["parameters"]["types"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "types", return_type=str, default=""
            ),
            "string",
            "Comma separated list of value types for each topic listed above. Valid types are: ct1,ct2,ctpower1,ctpower2,fuel,temperature,power,current,voltage or pressure. See the wiki entry for this add on for more details.",
            bounds="",
            display_name="Sensor Type",
        )
        AddOnCfg["genmqttin"]["parameters"]["exclude_gauge"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "exclude_gauge", return_type=str, default=""
            ),
            "string",
            "Comma separated list of Displayed Names that will not be displayed as a gauge. If you enable 'Use Data for Calculations' then you can remove duplicate gagues with this setting if they show up in the user interface.",
            bounds="",
            display_name="Exclude Gauge",
        )
        AddOnCfg["genmqttin"]["parameters"]["nominal_values"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "nominal_values", return_type=str, default=""
            ),
            "string",
            "Comma separated list of nominal values for each topic listed above.",
            bounds="",
            display_name="Nominal Values",
        )
        AddOnCfg["genmqttin"]["parameters"]["maximum_values"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "maximum_values", return_type=str, default=""
            ),
            "string",
            "Comma separated list of maximum values for each topic listed above.",
            bounds="",
            display_name="Maximum Values",
        )

        AddOnCfg["genmqttin"]["parameters"]["use_for_power_fuel"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "use_for_power_fuel", return_type=bool, default=False
            ),
            "boolean",
            "If enabled, the data from sensor types fuel,power,current,ct1,ct2,voltageleg1, voltageleg2, ctpower1 and ctpower2 will be imported and used for power and fuel calculations (instead of just displaying) within genmon.",
            bounds="",
            display_name="Use Data for Calculations",
        )
        AddOnCfg["genmqttin"]["parameters"]["strict"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "strict", return_type=bool, default=False
            ),
            "boolean",
            "If enabled, genmon will only use Data for Calculations if the generator utility line is in an outage. If your sensors are connected after the transfer switch (i.e. utility and generator are monitored) the you will want to enable this setting to keep genmon from using the sensor readings when there is not an outage.",
            bounds="",
            display_name="Strict Import Rules",
        )
        AddOnCfg["genmqttin"]["parameters"]["mqtt_address"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "mqtt_address", return_type=str, default=""
            ),
            "string",
            "Address of your MQTT server.",
            bounds="required IPAddress",
            display_name="MQTT Server Address",
        )
        AddOnCfg["genmqttin"]["parameters"]["mqtt_port"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "mqtt_port", return_type=int, default=1833
            ),
            "int",
            "The port of the MQTT server in a decimal number.",
            bounds="required digits",
            display_name="MQTT Server Port Number",
        )
        AddOnCfg["genmqttin"]["parameters"]["username"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "username", return_type=str, default=""
            ),
            "string",
            "This value is used for the username if your MQTT server requires authentication. Leave blank for no authentication.",
            bounds="minmax:4:50",
            display_name="MQTT Authentication Username",
        )
        AddOnCfg["genmqttin"]["parameters"]["password"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "password", return_type=str, default=""
            ),
            "password",
            "This value is used for the password if your MQTT server requires authentication. Leave blank for no authentication or no password.",
            bounds="minmax:4:50",
            display_name="MQTT Authentication Password",
        )
        AddOnCfg["genmqttin"]["parameters"]["cert_authority_path"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "cert_authority_path", return_type=str, default=""
            ),
            "string",
            "(Optional) Full path to Certificate Authority file. Leave empty to not use SSL/TLS. If used port will be forced to 8883.",
            bounds="",
            display_name="SSL/TLS CA certificate file",
        )
        AddOnCfg["genmqttin"]["parameters"]["client_cert_path"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "client_cert_path", return_type=str, default=""
            ),
            "string",
            "Optional. Full path the client certificate file. Leave empty to not use MTLS.",
            bounds="",
            display_name="Client Certificate File",
        )
        AddOnCfg["genmqttin"]["parameters"]["client_key_path"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "client_key_path", return_type=str, default=""
            ),
            "string",
            "Optional. Full path the client key file. Leave empty to not use MTLS.",
            bounds="",
            display_name="Client Key File",
        )
        AddOnCfg["genmqttin"]["parameters"]["tls_version"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "tls_version", return_type=str, default="1.0"
            ),
            "list",
            "(Optional) TLS version used (integer). Default is 1.0. Must be 1.0, 1.1, or 1.2. This is ignored if a CA cert file is not used. ",
            bounds="1.0,1.1,1.2",
            display_name="TLS Version",
        )
        AddOnCfg["genmqttin"]["parameters"]["cert_reqs"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "cert_reqs", return_type=str, default="Required"
            ),
            "list",
            "(Optional) Defines the certificate requirements that the client imposes on the broker. Used if Certificate Authority file is used.",
            bounds="None,Optional,Required",
            display_name="Certificate Requirements",
        )
        AddOnCfg["genmqttin"]["parameters"]["client_id"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "client_id", return_type=str, default="genmon"
            ),
            "string",
            "Unique identifier. Must be unique for each instance of genmon and add on running on a given system. ",
            bounds="",
            display_name="Client ID",
        )
        # GENSLACK
        AddOnCfg["genslack"] = collections.OrderedDict()
        AddOnCfg["genslack"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="genslack", default=False
        )
        AddOnCfg["genslack"]["title"] = "Notifications via Slack"
        AddOnCfg["genslack"][
            "description"
        ] = "Send Genmon and utility state changes via Slack service"
        AddOnCfg["genslack"]["icon"] = "slack"
        AddOnCfg["genslack"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genslackpy-optional"
        AddOnCfg["genslack"]["parameters"] = collections.OrderedDict()

        AddOnCfg["genslack"]["parameters"]["webhook_url"] = CreateAddOnParam(
            ConfigFiles[GENSLACK_CONFIG].ReadValue(
                "webhook_url", return_type=str, default=""
            ),
            "string",
            "Full Slack Webhook URL. Retrieve from Slack custom integration configuration.",
            bounds="required HTTPAddress",
            display_name="Web Hook URL",
        )
        AddOnCfg["genslack"]["parameters"]["channel"] = CreateAddOnParam(
            ConfigFiles[GENSLACK_CONFIG].ReadValue(
                "channel", return_type=str, default=""
            ),
            "string",
            "Slack channel to which the message will be sent.",
            display_name="Channel",
        )
        AddOnCfg["genslack"]["parameters"]["username"] = CreateAddOnParam(
            ConfigFiles[GENSLACK_CONFIG].ReadValue(
                "username", return_type=str, default=""
            ),
            "string",
            "Slack username.",
            bounds="required username",
            display_name="Username",
        )
        AddOnCfg["genslack"]["parameters"]["icon_emoji"] = CreateAddOnParam(
            ConfigFiles[GENSLACK_CONFIG].ReadValue(
                "icon_emoji", return_type=str, default=":red_circle:"
            ),
            "string",
            "Emoji that appears as the icon of the user who sent the message i.e. :red_circle:n",
            bounds="",
            display_name="Icon Emoji",
        )
        AddOnCfg["genslack"]["parameters"]["title_link"] = CreateAddOnParam(
            ConfigFiles[GENSLACK_CONFIG].ReadValue(
                "title_link", return_type=str, default=""
            ),
            "string",
            "Use this to make the title of the message a link i.e. link to the genmon web interface.",
            bounds="HTTPAddress",
            display_name="Title Link",
        )

        AddOnCfg = AddNotificationAddOnParam(AddOnCfg, "genslack", GENSLACK_CONFIG)
        AddOnCfg = AddRetryAddOnParam(AddOnCfg, "genslack", GENSLACK_CONFIG)

        # GENCALLMEBOT
        AddOnCfg["gencallmebot"] = collections.OrderedDict()
        AddOnCfg["gencallmebot"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gencallmebot", default=False
        )
        AddOnCfg["gencallmebot"]["title"] = "Notifications via CallMeBot"
        AddOnCfg["gencallmebot"][
            "description"
        ] = "Send Genmon and utility state changes via CallMeBot service"
        AddOnCfg["gencallmebot"]["icon"] = "callmebot"
        AddOnCfg["gencallmebot"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gencallmebotpy-optional"
        AddOnCfg["gencallmebot"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gencallmebot"]["parameters"]["notification_type"] = CreateAddOnParam(
            ConfigFiles[GENCALLMEBOT_CONFIG].ReadValue(
                "notification_type", return_type=str, default=""
            ),
            "list",
            "Type of CallMeBot Notifications. For more information, see http://www.callmebot.com.",
            bounds="WhatsApp,Telegram,Signal",  # Facebook, 
            display_name="Notification Type",
        )
        AddOnCfg["gencallmebot"]["parameters"]["api_key"] = CreateAddOnParam(
            ConfigFiles[GENCALLMEBOT_CONFIG].ReadValue(
                "api_key", return_type=str, default=""
            ),
            "string",
            "API Key required for WhatsApp Notifications.", # and Facebook Messanger, Signal 
            display_name="API Key",
        )
        AddOnCfg["gencallmebot"]["parameters"]["username"] = CreateAddOnParam(
            ConfigFiles[GENCALLMEBOT_CONFIG].ReadValue(
                "username", return_type=str, default=""
            ),
            "string",
            "CallMeBot username required for Telegram Notifications.",
            bounds="required username",
            display_name="Username",
        )
        AddOnCfg["gencallmebot"]["parameters"]["recipient_number"] = CreateAddOnParam(
            ConfigFiles[GENCALLMEBOT_CONFIG].ReadValue(
                "recipient_number", return_type=str, default="+1XXXXXXXXXX"
            ),
            "string",
            "Recipient Number requried for WhatsApp Notification. Must be without spaces and start with a plus. For Signal this must be the numeric key sent to your signal account when registering with CallMeBot (in the form xxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)",
            bounds="",
            display_name="Recipient Number",
        )

        AddOnCfg = AddNotificationAddOnParam(AddOnCfg, "gencallmebot", GENCALLMEBOT_CONFIG)
        AddOnCfg = AddRetryAddOnParam(AddOnCfg, "gencallmebot", GENCALLMEBOT_CONFIG)

        # GENEXERCISE
        ControllerInfo = GetControllerInfo("controller").lower()
        if "evolution" in ControllerInfo or "nexus" in ControllerInfo:
            AddOnCfg["genexercise"] = collections.OrderedDict()
            AddOnCfg["genexercise"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
                "enable", return_type=bool, section="genexercise", default=False
            )
            AddOnCfg["genexercise"]["title"] = "Enhanced Exercise"
            AddOnCfg["genexercise"][
                "description"
            ] = "Add additional exercise cycles with new functionality for Evolution/Nexus Controllers"
            AddOnCfg["genexercise"]["icon"] = "selftest"
            AddOnCfg["genexercise"][
                "url"
            ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genexercisepy-optional"
            AddOnCfg["genexercise"]["parameters"] = collections.OrderedDict()

            AddOnCfg["genexercise"]["parameters"]["exercise_type"] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue(
                    "exercise_type", return_type=str, default="Normal"
                ),
                "list",
                "Quiet Exercise (reduced RPM, Hz and Voltage), Normal Exercise, Exercise with Transfer Switch Activated.",
                bounds="Quiet,Normal,Transfer",
                display_name="Exercise Type",
            )
            AddOnCfg["genexercise"]["parameters"][
                "exercise_frequency"
            ] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue(
                    "exercise_frequency", return_type=str, default="Monthly"
                ),
                "list",
                "Exercise Frequency options are Daily, Weekly, Biweekly,Monthly  or Post-Controller (immediately after the controller exercise cycle). Hour, Minute, Month, Day of Week are ignored if Post-Controller exercise frequency is enabled.",
                bounds="Daily,Weekly,Biweekly,Monthly,Post-Controller",
                display_name="Exercise Frequency",
            )
            AddOnCfg["genexercise"]["parameters"]["use_gen_time"] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue(
                    "use_gen_time", return_type=bool, default=False
                ),
                "boolean",
                "Enable to use the generator time for the exercise cycle, otherwise it will use the system time.",
                display_name="Use Generator Time",
            )
            AddOnCfg["genexercise"]["parameters"]["exercise_hour"] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue(
                    "exercise_hour", return_type=int, default=12
                ),
                "int",
                "The hour of the exercise time. Valid input is 0 - 23.",
                bounds="required digits range:0:23",
                display_name="Exercise Time Hour",
            )
            AddOnCfg["genexercise"]["parameters"]["exercise_minute"] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue(
                    "exercise_minute", return_type=int, default=0
                ),
                "int",
                "The minute of the exercise time.  Valid input is 0 - 59",
                bounds="required digits range:0:59",
                display_name="Exercise Time Minute",
            )
            AddOnCfg["genexercise"]["parameters"][
                "exercise_day_of_month"
            ] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue(
                    "exercise_day_of_month", return_type=int, default=1
                ),
                "int",
                "The day of month if monthly exercise is selected.",
                bounds="required digits range:1:28",
                display_name="Exercise Day of Month",
            )
            AddOnCfg["genexercise"]["parameters"][
                "exercise_day_of_week"
            ] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue(
                    "exercise_day_of_week", return_type=str, default="Monday"
                ),
                "list",
                "Exercise day of the week, if Weekly or Biweekly exercise frequency is selected.",
                bounds="Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday",
                display_name="Exercise Day of the Week",
            )
            AddOnCfg["genexercise"]["parameters"][
                "exercise_duration"
            ] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue(
                    "exercise_duration", return_type=float, default=12
                ),
                "float",
                "The duration of the exercise time. Note: this time does not include warmup time for Transfer type exercise cycles.",
                bounds="number range:5:60",
                display_name="Exercise Duration",
            )
            AddOnCfg["genexercise"]["parameters"]["exercise_warmup"] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue(
                    "exercise_warmup", return_type=float, default=0
                ),
                "float",
                "The duration of the warmup time. Note: this time only appies to the transfer type of exercise cycle. Zero will disable the warmup period.",
                bounds="number range:0:30",
                display_name="Warmup Duration",
            )

        # GENEMAIL2SMS
        AddOnCfg["genemail2sms"] = collections.OrderedDict()
        AddOnCfg["genemail2sms"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="genemail2sms", default=False
        )
        AddOnCfg["genemail2sms"]["title"] = "Mobile Carrier Email to SMS"
        AddOnCfg["genemail2sms"][
            "description"
        ] = "Send Genmon and utility state changes via carrier email to SMS service"
        AddOnCfg["genemail2sms"]["icon"] = "text"
        AddOnCfg["genemail2sms"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genemail2smspy-optional"
        AddOnCfg["genemail2sms"]["parameters"] = collections.OrderedDict()

        AddOnCfg["genemail2sms"]["parameters"]["destination"] = CreateAddOnParam(
            ConfigFiles[GENEMAIL2SMS_CONFIG].ReadValue(
                "destination", return_type=str, default=""
            ),
            "string",
            "Email to SMS email recipient. Must be a valid email address",
            bounds="required email",
            display_name="Email to SMS address",
        )

        AddOnCfg = AddNotificationAddOnParam(
            AddOnCfg, "genemail2sms", GENEMAIL2SMS_CONFIG
        )

        # GENCENTRICONNECT
        AddOnCfg["gencentriconnect"] = collections.OrderedDict()
        AddOnCfg["gencentriconnect"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gencentriconnect", default=False
        )
        AddOnCfg["gencentriconnect"]["title"] = "Centri My Propane External Tank Fuel Monitor"
        AddOnCfg["gencentriconnect"][
            "description"
        ] = "Integrates Centriconnect.com propane tank sensor data"
        AddOnCfg["gencentriconnect"]["icon"] = "centri"
        AddOnCfg["gencentriconnect"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gencentriconnectpy-optional"
        AddOnCfg["gencentriconnect"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gencentriconnect"]["parameters"]["user_id"] = CreateAddOnParam(
            ConfigFiles[GENCENTRICONNECT_CONFIG].ReadValue(
                "user_id", return_type=str, default=""
            ),
            "string",
            "User ID. Note that this is a long series of numbers and dashes in this format: 36e551aa-c215-4c9b-8c70-ba7729687654",
            bounds="required min:36",
            display_name="User ID",
        )
        AddOnCfg["gencentriconnect"]["parameters"]["device_id"] = CreateAddOnParam(
            ConfigFiles[GENCENTRICONNECT_CONFIG].ReadValue(
                "device_id", return_type=str, default=""
            ),
            "string",
            "Device ID. Note that this is a long series of numbers and dashes in this format: 36e551aa-c215-4c9b-8c70-ba7729687654",
            bounds="required min:36",
            display_name="Device ID",
        )
        AddOnCfg["gencentriconnect"]["parameters"]["device_auth"] = CreateAddOnParam(
            ConfigFiles[GENCENTRICONNECT_CONFIG].ReadValue(
                "device_auth", return_type=str, default=""
            ),
            "password",
            "Device Auth for Centri propane tank sensor. This number is provided in the box with the sensor.",
            bounds="required min:6",
            display_name="Device Authentication Code",
        )
        AddOnCfg["gencentriconnect"]["parameters"]["poll_frequency"] = CreateAddOnParam(
            ConfigFiles[GENCENTRICONNECT_CONFIG].ReadValue(
                "poll_frequency", return_type=float, default=0
            ),
            "int",
            "The duration in minutes between poll of tank data. Note this must be equal or larger than 288 minutes as the maximum number of polls per day is around 5.",
            bounds="number range:288:20000",
            display_name="Poll Frequency",
        )
        AddOnCfg["gencentriconnect"]["parameters"]["check_battery"] = CreateAddOnParam(
            ConfigFiles[GENCENTRICONNECT_CONFIG].ReadValue(
                "check_battery", return_type=bool, default=False
            ),
            "boolean",
            "If enabled, and email will be sent if the battery level on the sensor is critical. Outbound email must be enabled for this to function.",
            bounds="",
            display_name="Check Sensor Battery",
        )
        AddOnCfg["gencentriconnect"]["parameters"]["check_reading"] = CreateAddOnParam(
            ConfigFiles[GENCENTRICONNECT_CONFIG].ReadValue(
                "check_reading", return_type=bool, default=False
            ),
            "boolean",
            "If enabled, and email will be sent if the sensor has not performed a reading within 50 hours. Outbound email must be enabled for this to function.",
            bounds="",
            display_name="Check for Missed Readings",
        )

        # GENTANKUTIL
        AddOnCfg["gentankutil"] = collections.OrderedDict()
        AddOnCfg["gentankutil"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gentankutil", default=False
        )
        AddOnCfg["gentankutil"]["title"] = "External Tank Fuel Monitor"
        AddOnCfg["gentankutil"][
            "description"
        ] = "Integrates tankutility.com propane tank sensor data"
        AddOnCfg["gentankutil"]["icon"] = "tankutility"
        AddOnCfg["gentankutil"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gentankutilpy-optional"
        AddOnCfg["gentankutil"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gentankutil"]["parameters"]["tank_name"] = CreateAddOnParam(
            ConfigFiles[GENTANKUTIL_CONFIG].ReadValue(
                "tank_name", return_type=str, default=""
            ),
            "string",
            "Tank name as defined in tankutility.com",
            bounds="minmax:1:50",
            display_name="Tank Name",
        )
        AddOnCfg["gentankutil"]["parameters"]["tank_name_2"] = CreateAddOnParam(
            ConfigFiles[GENTANKUTIL_CONFIG].ReadValue(
                "tank_name_2", return_type=str, default=""
            ),
            "string",
            "Second tank name, if applicable",
            bounds="minmax:1:50",
            display_name="Tank Name 2 (Optional)",
        )
        AddOnCfg["gentankutil"]["parameters"]["username"] = CreateAddOnParam(
            ConfigFiles[GENTANKUTIL_CONFIG].ReadValue(
                "username", return_type=str, default=""
            ),
            "string",
            "Username at tankutility.com",
            bounds="required email",
            display_name="Username",
        )
        AddOnCfg["gentankutil"]["parameters"]["password"] = CreateAddOnParam(
            ConfigFiles[GENTANKUTIL_CONFIG].ReadValue(
                "password", return_type=str, default=""
            ),
            "password",
            "Password at tankutility.com",
            bounds="minmax:4:50",
            display_name="Password",
        )
        AddOnCfg["gentankutil"]["parameters"]["poll_frequency"] = CreateAddOnParam(
            ConfigFiles[GENTANKUTIL_CONFIG].ReadValue(
                "poll_frequency", return_type=float, default=0
            ),
            "float",
            "The duration in minutes between poll of tank data.",
            bounds="number",
            display_name="Poll Frequency",
        )
        AddOnCfg["gentankutil"]["parameters"]["check_battery"] = CreateAddOnParam(
            ConfigFiles[GENTANKUTIL_CONFIG].ReadValue(
                "check_battery", return_type=bool, default=False
            ),
            "boolean",
            "If enabled, and email will be sent if the battery level on the sensor is critical. Outbound email must be enabled for this to function.",
            bounds="",
            display_name="Check Sensor Battery",
        )
        AddOnCfg["gentankutil"]["parameters"]["check_reading"] = CreateAddOnParam(
            ConfigFiles[GENTANKUTIL_CONFIG].ReadValue(
                "check_reading", return_type=bool, default=False
            ),
            "boolean",
            "If enabled, and email will be sent if the sensor has not performed a reading within 50 hours. Outbound email must be enabled for this to function.",
            bounds="",
            display_name="Check for Missed Readings",
        )

        # GENTANKDIY
        AddOnCfg["gentankdiy"] = collections.OrderedDict()
        AddOnCfg["gentankdiy"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gentankdiy", default=False
        )
        AddOnCfg["gentankdiy"]["title"] = "DIY Fuel Tank Gauge Sensor"
        Description = "Integrates DIY tank gauge sensor for Genmon"
        if (
            os.path.exists("/dev/i2c-1") == False
            and os.path.exists("/dev/i2c-2") == False
        ):
            Description = (
                Description
                + "<br/><font color='red'>The I2C bus not enabled but required for this add-on to function.</font>"
            )
        AddOnCfg["gentankdiy"]["description"] = Description
        AddOnCfg["gentankdiy"]["icon"] = "rpi"
        AddOnCfg["gentankdiy"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gentankdiypy-optional"
        AddOnCfg["gentankdiy"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gentankdiy"]["parameters"]["poll_frequency"] = CreateAddOnParam(
            ConfigFiles[GENTANKDIY_CONFIG].ReadValue(
                "poll_frequency", return_type=float, default=0
            ),
            "float",
            "The duration in minutes between poll of tank data.",
            bounds="number",
            display_name="Poll Frequency",
        )
        AddOnCfg["gentankdiy"]["parameters"]["gauge_type"] = CreateAddOnParam(
            ConfigFiles[GENTANKDIY_CONFIG].ReadValue(
                "gauge_type", return_type=str, default="1"
            ),
            "list",
            "DIY sensor type. Valid options are Type 1 and Type 2.",
            bounds="1,2",
            display_name="Sensor Type",
        )

        # GENALEXA
        AddOnCfg["genalexa"] = collections.OrderedDict()
        AddOnCfg["genalexa"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="genalexa", default=False
        )
        AddOnCfg["genalexa"]["title"] = "Amazon Alexa voice commands"
        AddOnCfg["genalexa"][
            "description"
        ] = "Allow Amazon Alexa to start and stop the generator"
        AddOnCfg["genalexa"]["icon"] = "alexa"
        AddOnCfg["genalexa"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genalexapy-optional"
        AddOnCfg["genalexa"]["parameters"] = collections.OrderedDict()

        AddOnCfg["genalexa"]["parameters"]["name"] = CreateAddOnParam(
            ConfigFiles[GENALEXA_CONFIG].ReadValue("name", return_type=str, default=""),
            "string",
            "Name to call the generator device, i.e. 'generator'",
            bounds="minmax:4:50",
            display_name="Name for generator device",
        )

        # GENSNMP
        AddOnCfg["gensnmp"] = collections.OrderedDict()
        AddOnCfg["gensnmp"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gensnmp", default=False
        )
        AddOnCfg["gensnmp"]["title"] = "SNMP Support"
        AddOnCfg["gensnmp"]["description"] = "Allow Genmon to respond to SNMP requests"
        AddOnCfg["gensnmp"]["icon"] = "snmp"
        AddOnCfg["gensnmp"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensnmppy-optional"
        AddOnCfg["gensnmp"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gensnmp"]["parameters"]["poll_frequency"] = CreateAddOnParam(
            ConfigFiles[GENSNMP_CONFIG].ReadValue(
                "poll_frequency", return_type=float, default=2.0
            ),
            "float",
            "The time in seconds between requesting status from genmon. The default value is 2 seconds.",
            bounds="number",
            display_name="Poll Interval",
        )
        AddOnCfg["gensnmp"]["parameters"]["enterpriseid"] = CreateAddOnParam(
            ConfigFiles[GENSNMP_CONFIG].ReadValue(
                "enterpriseid", return_type=int, default=58399
            ),
            "int",
            "The enterprise ID used in the SNMP Object Identifier (OID). The genmon SNMP enterprise ID is 58399.",
            bounds="required digits",
            display_name="Enterprise ID",
        )
        AddOnCfg["gensnmp"]["parameters"]["community"] = CreateAddOnParam(
            ConfigFiles[GENSNMP_CONFIG].ReadValue(
                "community", return_type=str, default="public"
            ),
            "string",
            "SNMP Community string",
            bounds="minmax:4:50",
            display_name="SNMP Community",
        )
        AddOnCfg["gensnmp"]["parameters"]["use_numeric"] = CreateAddOnParam(
            ConfigFiles[GENSNMP_CONFIG].ReadValue(
                "use_numeric", return_type=bool, default=False
            ),
            "boolean",
            "If enabled will return numeric values (no units) in the Status, Maintenance (Evo/Nexus only) and Outage data.",
            bounds="",
            display_name="Numerics only",
        )
        AddOnCfg["gensnmp"]["parameters"]["use_integer"] = CreateAddOnParam(
            ConfigFiles[GENSNMP_CONFIG].ReadValue(
                "use_integer", return_type=bool, default=False
            ),
            "boolean",
            "If enabled, integer values (no units) will be returned when applicable in the Status, Maintenance (Evo/Nexus only) and Outage data. Enabling this value also enables 'Use Numerics'. Floating point numberic values are returned as strings",
            bounds="",
            display_name="Force Integers",
        )

        # GENTEMP
        AddOnCfg["gentemp"] = collections.OrderedDict()
        AddOnCfg["gentemp"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gentemp", default=False
        )
        AddOnCfg["gentemp"]["title"] = "External Temperature Sensors"
        Description = "Allow the display of external temperature sensor data"
        # TODO linux specific check
        if os.path.isdir("/sys/bus/w1/") == False:
            Description = (
                Description
                + "<br/><font color='red'>1-wire is not enabled but is required</font>"
            )
        AddOnCfg["gentemp"]["description"] = Description
        AddOnCfg["gentemp"]["icon"] = "rpi"
        AddOnCfg["gentemp"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gentemppy-optional"
        AddOnCfg["gentemp"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gentemp"]["parameters"]["poll_frequency"] = CreateAddOnParam(
            ConfigFiles[GENTEMP_CONFIG].ReadValue(
                "poll_frequency", return_type=float, default=2.0
            ),
            "float",
            "The time in seconds that the temperature data is polled. The default value is 2 seconds.",
            bounds="number",
            display_name="Poll Interval",
        )
        AddOnCfg["gentemp"]["parameters"]["use_metric"] = CreateAddOnParam(
            ConfigFiles[GENTEMP_CONFIG].ReadValue(
                "use_metric", return_type=bool, default=False
            ),
            "boolean",
            "enable to use Celsius, disable for Fahrenheit",
            bounds="",
            display_name="Use Metric",
        )
        AddOnCfg["gentemp"]["parameters"]["blacklist"] = CreateAddOnParam(
            ConfigFiles[GENTEMP_CONFIG].ReadValue(
                "blacklist", return_type=str, default=""
            ),
            "string",
            "Comma separated blacklist. If these vaues are found in 1 wire temperature sensor device names the sensor will be ignored.",
            bounds="",
            display_name="Sensor Device Blacklist",
        )
        AddOnCfg["gentemp"]["parameters"]["device_labels"] = CreateAddOnParam(
            ConfigFiles[GENTEMP_CONFIG].ReadValue(
                "device_labels", return_type=str, default=""
            ),
            "string",
            "Comma separated list of sensor names. These names will be displayed for each sensor. DS18B20 sensors are first, then type K thermocouples. Blacklisted devices are skipped.",
            bounds="",
            display_name="Sensor Names",
        )
        AddOnCfg["gentemp"]["parameters"]["device_nominal_values"] = CreateAddOnParam(
            ConfigFiles[GENTEMP_CONFIG].ReadValue(
                "device_nominal_values", return_type=str, default=""
            ),
            "string",
            "Comma separated list of nominal temperature values for the sensor. Nominal values help determine where the gauge green area ends and the yellow begins. The order of these values must match the order of the Sensor Names. Leave blank to disable External Temp Sensor gauges.",
            bounds="",
            display_name="Sensor Nominal Values",
        )
        AddOnCfg["gentemp"]["parameters"]["device_max_values"] = CreateAddOnParam(
            ConfigFiles[GENTEMP_CONFIG].ReadValue(
                "device_max_values", return_type=str, default=""
            ),
            "string",
            "Comma separated list of maximum temperature values for the sensor. This is the maximum gauge value. The order of these values must match the order of the Sensor Names. Leave blank to disable External Temp Sensor gauges.",
            bounds="",
            display_name="Sensor Maximum Values",
        )
        AddOnCfg["gentemp"]["parameters"]["device_min_values"] = CreateAddOnParam(
            ConfigFiles[GENTEMP_CONFIG].ReadValue(
                "device_min_values", return_type=str, default=""
            ),
            "string",
            "Comma separated list of minimum temperature values for the sensor. This is the minimum gauge value. The order of these values must match the order of the Sensor Names. Leave blank to set all sensors minimum value to zero.",
            bounds="",
            display_name="Sensor Minimum Values",
        )
        # GENSENSORHAT
        AddOnCfg["gencthat"] = collections.OrderedDict()
        AddOnCfg["gencthat"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gencthat", default=False
        )
        AddOnCfg["gencthat"]["title"] = "External Current Transformer (CT) Sensors"
        Description = "Support for Raspberry pi HAT with CTs from PintSize.me."
        # TODO linux specific check
        if os.path.exists("/dev/spidev1.0") == False:
            Description = (
                Description
                + "<br/><font color='red'>The SPI bus number one is not enabled but required for this add-on to function.</font>"
            )
        AddOnCfg["gencthat"]["description"] = Description
        AddOnCfg["gencthat"]["icon"] = "rpi"
        AddOnCfg["gencthat"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gencthatpy-optional"
        AddOnCfg["gencthat"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gencthat"]["parameters"]["poll_frequency"] = CreateAddOnParam(
            ConfigFiles[GENCTHAT_CONFIG].ReadValue(
                "poll_frequency", return_type=float, default=2.0
            ),
            "float",
            "The time in seconds that the sensors are polled. The default value is 15 seconds.",
            bounds="number",
            display_name="Poll Interval",
        )
        AddOnCfg["gencthat"]["parameters"]["strict"] = CreateAddOnParam(
            ConfigFiles[GENCTHAT_CONFIG].ReadValue(
                "strict", return_type=bool, default=False
            ),
            "boolean",
            "Set to true to only use the CT data if the generator utility line is in an outage.",
            bounds="",
            display_name="Strict Usage of CT data",
        )

        # GENMOPEKA
        if sys.version_info >= (3, 7):
            Description = "Support Mopeka Pro Propane Tanks Sensor"
            try:
                import fluids
            except Exception as e1:
                Description = (
                    Description
                    + "<br/><font color='red'>The required libraries for this add on are not installed, please run the installation script.</font>"
                )

            AddOnCfg["genmopeka"] = collections.OrderedDict()
            AddOnCfg["genmopeka"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
                "enable", return_type=bool, section="genmopeka", default=False
            )
            AddOnCfg["genmopeka"]["title"] = "Mopeka Pro Propane Tank Sensor"

            AddOnCfg["genmopeka"]["description"] = Description
            AddOnCfg["genmopeka"]["icon"] = "mopeka"
            AddOnCfg["genmopeka"][
                "url"
            ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genmopekapy-optional"
            AddOnCfg["genmopeka"]["parameters"] = collections.OrderedDict()

            AddOnCfg["genmopeka"]["parameters"]["poll_frequency"] = CreateAddOnParam(
                ConfigFiles[GENMOPEKA_CONFIG].ReadValue(
                    "poll_frequency", return_type=float, default=60
                ),
                "float",
                "The time in minutes that the sensors are polled. The default value is 60 minutes.",
                bounds="number",
                display_name="Poll Interval",
            )
            AddOnCfg["genmopeka"]["parameters"]["tank_address"] = CreateAddOnParam(
                ConfigFiles[GENMOPEKA_CONFIG].ReadValue(
                    "tank_address", return_type=str, default=""
                ),
                "string",
                "This value is MAC address of the sensor. It must be in a format using hex numbers separated by colons (i.e. 9a:03:2b:67:25:12). Multiple tank sensors (up to 4) may be used with commas between each address",
                bounds="",
                display_name="Sensor Address",
            )
            AddOnCfg["genmopeka"]["parameters"]["tank_type"] = CreateAddOnParam(
                ConfigFiles[GENMOPEKA_CONFIG].ReadValue(
                    "tank_type", return_type=str, default="1"
                ),
                "list",
                "Type of tank used. If Custom is used then Max and Min values must be setup in /etc/genmon/genmopeka.conf",
                bounds="20_LB,30_LB,40_LB,100_LB,200_LB,120_GAL,120_GAL_HORIZ,250_GAL,500_GAL,1000_GAL,Custom",
                display_name="Tank Size",
            )
            AddOnCfg["genmopeka"]["parameters"]["send_notices"] = CreateAddOnParam(
                ConfigFiles[GENMOPEKA_CONFIG].ReadValue(
                    "send_notices", return_type=bool, default=False
                ),
                "boolean",
                "Send email notices if unable to communicate with the senor or the sensor battery is low. Note: outbound email must be setup for this to work.",
                bounds="",
                display_name="Send Notices",
            )
        
    except Exception as e1:
        LogErrorLine("Error in GetAddOns: " + str(e1))

    return AddOnCfg


# ------------ AddNotificationAddOnParam ----------------------------------------
def AddNotificationAddOnParam(AddOnCfg, addon_name, config_file):

    try:
        AddOnCfg[addon_name]["parameters"]["notify_error"] = CreateAddOnParam(
            ConfigFiles[config_file].ReadValue(
                "notify_error", return_type=bool, default=True
            ),
            "boolean",
            "Send messages for errors (Generator Alarms).",
            display_name="Notify for Errors",
        )
        AddOnCfg[addon_name]["parameters"]["notify_warn"] = CreateAddOnParam(
            ConfigFiles[config_file].ReadValue(
                "notify_warn", return_type=bool, default=True
            ),
            "boolean",
            "Send messages for warnings (service due, fuel low).",
            display_name="Notify for Warnings",
        )
        AddOnCfg[addon_name]["parameters"]["notify_info"] = CreateAddOnParam(
            ConfigFiles[config_file].ReadValue(
                "notify_info", return_type=bool, default=True
            ),
            "boolean",
            "Send messages for information (switch state change, engine state change, exercising).",
            display_name="Notify for Information",
        )
        AddOnCfg[addon_name]["parameters"]["notify_outage"] = CreateAddOnParam(
            ConfigFiles[config_file].ReadValue(
                "notify_outage", return_type=bool, default=True
            ),
            "boolean",
            "Send messages for outages.",
            display_name="Notify for Outages",
        )
        AddOnCfg[addon_name]["parameters"]["notify_sw_update"] = CreateAddOnParam(
            ConfigFiles[config_file].ReadValue(
                "notify_sw_update", return_type=bool, default=True
            ),
            "boolean",
            "Send messages for software updates.",
            display_name="Notify for Software Updates",
        )
        AddOnCfg[addon_name]["parameters"]["notify_pi_state"] = CreateAddOnParam(
            ConfigFiles[config_file].ReadValue(
                "notify_pi_state", return_type=bool, default=True
            ),
            "boolean",
            "Send messages for Pi hardware sensor status (CPU throttling, undervoltage, etc).",
            display_name="Notify for Pi Hardware Issues",
        )
    except Exception as e1:
        LogErrorLine("Error in AddNotificationAddOnParam: " + str(e1))

    return AddOnCfg


# ------------ AddRetryAddOnParam -----------------------------------------------
def AddRetryAddOnParam(AddOnCfg, addon_name, config_file):

    try:
        AddOnCfg[addon_name]["parameters"]["max_retry_time"] = CreateAddOnParam(
            value=ConfigFiles[config_file].ReadValue(
                "max_retry_time", return_type=int, default=600
            ),
            type="int",
            description="Maximum number of seconds to retry a failed message before dropping the message.",
            display_name="Max Retry Duration (seconds)",
        )
        AddOnCfg[addon_name]["parameters"]["default_wait"] = CreateAddOnParam(
            value=ConfigFiles[config_file].ReadValue(
                "default_wait", return_type=int, default=120
            ),
            type="int",
            description="The number of seconds to wait before retrying a failed message.",
            display_name="Retry Interval (seconds)",
        )
        # This paramerter is not exposed but a valid conf file setting
        #AddOnCfg[addon_name]["parameters"]["minimum_wait_between_messages"] = CreateAddOnParam(
        #    value=ConfigFiles[config_file].ReadValue(
        #        "minimum_wait_between_messages", return_type=int, default=0
        #    ),
        #    type="int",
        #    description="The minimum of seconds to wait between sending a message. This is typically zero, except for Callmebot Signal Messaging (should be at least 2 seconds) or other messaging apps that have minimum delays.",
        #    display_name="Min Time Between Messages (seconds)",
        #)
    except Exception as e1:
        LogErrorLine("Error in AddRetryAddOnParam: " + str(e1))
    return AddOnCfg


# ------------ MyCommon::StripJson ----------------------------------------------
def StripJson(InputString):
    for char in '{}[]"':
        InputString = InputString.replace(char, "")
    return InputString


# ------------ MyCommon::DictToString -------------------------------------------
def DictToString(InputDict, ExtraStrip=False):

    if InputDict == None:
        return ""
    ReturnString = json.dumps(
        InputDict, sort_keys=False, indent=4, separators=(" ", ": ")
    )
    return ReturnString
    if ExtraStrip:
        ReturnString = ReturnString.replace("} \n", "")
    return StripJson(ReturnString)


# -------------------------------------------------------------------------------
def CreateAddOnParam(
    value="", type="string", description="", bounds="", display_name=""
):

    # Bounds are defined in ReadSettingsFromFile comments
    Parameter = collections.OrderedDict()
    Parameter["value"] = value
    Parameter["type"] = type
    Parameter["description"] = description
    Parameter["bounds"] = bounds
    Parameter["display_name"] = display_name
    return Parameter


# -------------------------------------------------------------------------------
def GetAddOnSettings():
    try:
        return GetAddOns()
    except Exception as e1:
        LogErrorLine("Error in GetAddOnSettings: " + str(e1))
        return {}


# -------------------------------------------------------------------------------
def SaveAddOnSettings(query_string):
    try:
        if query_string == None:
            LogError("Empty query string in SaveAddOnSettings")
            return

        settings = json.loads(query_string)
        if not len(settings):
            return  # nothing to change

        ConfigDict = {
            "genmon": ConfigFiles[GENMON_CONFIG],
            "mymail": ConfigFiles[MAIL_CONFIG],
            "genloader": ConfigFiles[GENLOADER_CONFIG],
            "gensms": ConfigFiles[GENSMS_CONFIG],
            "gensms_modem": ConfigFiles[MYMODEM_CONFIG],
            "genpushover": ConfigFiles[GENPUSHOVER_CONFIG],
            "genmqtt": ConfigFiles[GENMQTT_CONFIG],
            "genmqttin": ConfigFiles[GENMQTTIN_CONFIG],
            "genslack": ConfigFiles[GENSLACK_CONFIG],
            "gencallmebot": ConfigFiles[GENCALLMEBOT_CONFIG],
            "genlog": ConfigFiles[GENLOADER_CONFIG],
            "gensyslog": ConfigFiles[GENLOADER_CONFIG],
            "gengpio": ConfigFiles[GENLOADER_CONFIG],
            "gengpioin": ConfigFiles[GENGPIOIN_CONFIG],
            "gengpioledblink": ConfigFiles[GENGPIOLEDBLINK_CONFIG],
            "genexercise": ConfigFiles[GENEXERCISE_CONFIG],
            "genemail2sms": ConfigFiles[GENEMAIL2SMS_CONFIG],
            "gentankutil": ConfigFiles[GENTANKUTIL_CONFIG],
            "gencentriconnect": ConfigFiles[GENCENTRICONNECT_CONFIG],
            "gentankdiy": ConfigFiles[GENTANKDIY_CONFIG],
            "genalexa": ConfigFiles[GENALEXA_CONFIG],
            "gensnmp": ConfigFiles[GENSNMP_CONFIG],
            "gentemp": ConfigFiles[GENTEMP_CONFIG],
            "gencthat": ConfigFiles[GENCTHAT_CONFIG],
            "genmopeka": ConfigFiles[GENMOPEKA_CONFIG],
            "gensms_voip": ConfigFiles[GENSMS_VOIP_CONFIG],
        }

        for module, entries in settings.items():  # module
            ParameterConfig = ConfigDict.get(module, None)
            if ParameterConfig == None:
                LogError("Invalid module in SaveAddOnSettings: " + module)
                continue
            # Find if it needs to be enabled / disabled or if there are parameters
            for basesettings, basevalues in entries.items():  # base settings
                if basesettings == "enable":
                    ConfigFiles[GENLOADER_CONFIG].WriteValue(
                        "enable", basevalues, section=module
                    )
                    # TODO This may not be needed now
                    if module == "gentankutil":
                        # update genmon.conf also to let it know that it should watch for external fuel data
                        ConfigFiles[GENMON_CONFIG].WriteValue(
                            "use_external_fuel_data", basevalues, section="genmon"
                        )
                    if module == "gentankdiy":
                        # update genmon.conf also to let it know that it should watch for external fuel data
                        ConfigFiles[GENMON_CONFIG].WriteValue(
                            "use_external_fuel_data_diy", basevalues, section="genmon"
                        )

                if basesettings == "parameters":
                    for params, paramvalue in basevalues.items():
                        if module == "genlog" and params == "Log File Name":
                            ConfigFiles[GENLOADER_CONFIG].WriteValue(
                                "args", "-f " + paramvalue, section=module
                            )
                        else:
                            ParameterConfig.WriteValue(params, paramvalue)

        Restart()
        return
    except Exception as e1:
        LogErrorLine("Error in SaveAddOnSettings: " + str(e1))
        return


# -------------------------------------------------------------------------------
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
            Notify = ConfigFiles[MAIL_CONFIG].ReadValue(email, default="")
            if Notify == "":
                NotificationSettings[email] = [SortOrder]
            else:
                NotificationSettings[email] = [SortOrder, Notify]
    except Exception as e1:
        LogErrorLine("Error in ReadNotificationsFromFile: " + str(e1))

    return NotificationSettings


# -------------------------------------------------------------------------------
def SaveNotifications(query_string):

    """
    email_recipient = email1@gmail.com,email2@gmail.com
    email1@gmail.com = outage,info
    email2@gmail.com = outage,info,error

    notifications = {'email1@gmail.com': ['outage,info'], 'email2@gmail.com': ['outage,info,error']}
    notifications_order_string = email1@gmail.com,email2@gmail.com

    or

    email_recipient = email1@gmail.com

    notifications = {'email1@gmail.com': ['']}
    notifications_order_string = email1@gmail.com

    """
    notifications = dict(parse_qs(query_string, 1))
    notifications_order_string = ",".join([v[0] for v in parse_qsl(query_string, 1)])

    oldEmailsList = []
    oldNotifications = {}
    oldEmailRecipientString = ""
    try:
        with CriticalLock:
            # get existing settings
            if ConfigFiles[MAIL_CONFIG].HasOption("email_recipient"):
                oldEmailRecipientString = ConfigFiles[MAIL_CONFIG].ReadValue(
                    "email_recipient"
                )
                oldEmailRecipientString.strip()
                oldEmailsList = oldEmailRecipientString.split(",")
                for oldEmailItem in oldEmailsList:
                    if ConfigFiles[MAIL_CONFIG].HasOption(oldEmailItem):
                        oldNotifications[oldEmailItem] = ConfigFiles[
                            MAIL_CONFIG
                        ].ReadValue(oldEmailItem)

            # compare, remove notifications if needed
            for oldEmailItem in oldEmailsList:
                if not oldEmailItem in notifications.keys() and ConfigFiles[
                    MAIL_CONFIG
                ].HasOption(oldEmailItem):
                    ConfigFiles[MAIL_CONFIG].WriteValue(oldEmailItem, "", remove=True)

            # add / update the entries
            # update email recipient if needed
            if oldEmailRecipientString != notifications_order_string:
                ConfigFiles[MAIL_CONFIG].WriteValue(
                    "email_recipient", notifications_order_string
                )

            # update catigories
            for newEmail, newCats in notifications.items():
                # remove catigories if needed from existing emails
                if not len(newCats[0]) and ConfigFiles[MAIL_CONFIG].HasOption(newEmail):
                    ConfigFiles[MAIL_CONFIG].WriteValue(newEmail, "", remove=True)
                # update or add catigories
                if len(newCats[0]):
                    ConfigFiles[MAIL_CONFIG].WriteValue(newEmail, newCats[0])

        Restart()
    except Exception as e1:
        LogErrorLine("Error in SaveNotifications: " + str(e1))
    return


# -------------------------------------------------------------------------------
def ReadSingleConfigValue(
    entry, filename=None, section=None, type="string", default="", bounds=None
):

    try:

        try:
            if filename == None:
                config = ConfigFiles[GENMON_CONFIG]
            else:
                config = ConfigFiles[filename]
        except Exception as e1:
            LogErrorLine(
                "Unknow file in UpdateConfigFile: " + filename + ": " + str(e1)
            )
            return default

        if section != None:
            config.SetSection(section)

        if not config.HasOption(entry):
            return default

        if type.lower() == "string" or type == "password":
            return config.ReadValue(entry)
        elif type.lower() == "boolean":
            return config.ReadValue(
                entry, return_type=bool, default=default, NoLog=True
            )
        elif type.lower() == "int":
            return config.ReadValue(entry, return_type=int, default=default, NoLog=True)
        elif type.lower() == "float":
            return config.ReadValue(
                entry, return_type=float, default=default, NoLog=True
            )
        elif type.lower() == "list":
            Value = config.ReadValue(entry)
            if bounds != None:
                DefaultList = bounds.split(",")
                if Value.lower() in (name.lower() for name in DefaultList):
                    return Value
                else:
                    LogError(
                        "Warning: Reading Config File (value not in list): %s : %s"
                        % (entry, Value)
                    )
                return default
            else:
                LogError(
                    "Error Reading Config File (bounds not provided): %s : %s"
                    % (entry, Value)
                )
                return default
        else:
            LogError(
                "Error Reading Config File (unknown type): %s : %s" % (entry, type)
            )
            return default

    except Exception as e1:
        LogErrorLine("Error Reading Config File (ReadSingleConfigValue): " + str(e1))
        return default


# -------------------------------------------------------------------------------
def GetImportConfigFileNames():

    try:
        path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "data", "controller"
        )
        listing = os.listdir(path)
        return ",".join(listing)
    except Exception as e1:
        LogErrorLine("Error Reading Config File (ReadSingleConfigValue): " + str(e1))
        return ""


# -------------------------------------------------------------------------------
def ReadAdvancedSettingsFromFile():

    ConfigSettings = collections.OrderedDict()
    try:
        # This option is not displayed as it will break the link between genmon and genserv
        ConfigSettings["server_port"] = [
            "int",
            "Server Port",
            5,
            ProgramDefaults.ServerPort,
            "",
            "digits",
            GENMON_CONFIG,
            GENMON_SECTION,
            "server_port",
        ]
        # this option is not displayed as this will break the modbus comms, only for debugging
        ConfigSettings["address"] = [
            "string",
            "Modbus slave address",
            6,
            "9d",
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "address",
        ]
        ConfigSettings["response_address"] = [
            "string",
            "Modbus slave transmit address",
            7,
            "",
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "response_address",
        ]
        ConfigSettings["additional_modbus_timeout"] = [
            "float",
            "Additional Modbus Timeout (sec)",
            8,
            "0.0",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "additional_modbus_timeout",
        ]
        ConfigSettings["use_modbus_fc4"] = [
            "boolean",
            "Use Modbus FC4 instead of FC3",
            9,
            False,
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "use_modbus_fc4",
        ]
        ConfigSettings["serial_rate"] = [
            "int",
            "Serial Data Rate",
            10,
            9600,
            "",
            "digits",
            GENMON_CONFIG,
            GENMON_SECTION,
            "serial_rate",
        ]
        ConfigSettings["serial_parity"] = [
            "list",
            "Serial Parity",
            11,
            "None",
            "",
            "None,Even,Odd",
            GENMON_CONFIG,
            GENMON_SECTION,
            "serial_parity",
        ]
        ConfigSettings["forceserialuse"] = [
            "boolean",
            "Force Use of Serial Port on Errors",
            12,
            False,
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "forceserialuse",
        ]
        ConfigSettings["watchdog_addition"] = [
            "float",
            "Additional Watchdog Timeout (sec)",
            13,
            "0.0",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "watchdog_addition",
        ]
        ConfigSettings["controllertype"] = [
            "list",
            "Controller Type",
            14,
            "generac_evo_nexus",
            "",
            "generac_evo_nexus,h_100,powerzone,custom",
            GENMON_CONFIG,
            GENMON_SECTION,
            "controllertype",
        ]

        import_config_files = GetImportConfigFileNames()
        ConfigSettings["import_config_file"] = [
            "list",
            "Custom Controller Config File",
            21,
            "Evolution_Liquid_Cooled.json",
            "",
            import_config_files,
            GENMON_CONFIG,
            GENMON_SECTION,
            "import_config_file",
        ]
        ConfigSettings["phase"] = [
            "int",
            "Generator Phase",
            22,
            "1",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "phase",
        ]
        ConfigSettings["loglocation"] = [
            "string",
            "Log Directory",
            23,
            ProgramDefaults.LogPath,
            "",
            "required UnixDir",
            GENMON_CONFIG,
            GENMON_SECTION,
            "loglocation",
        ]
        ConfigSettings["userdatalocation"] = [
            "string",
            "User Defined Data Directory",
            24,
            os.path.dirname(os.path.realpath(__file__)),
            "",
            "required UnixDir",
            GENMON_CONFIG,
            GENMON_SECTION,
            "userdatalocation",
        ]
        ConfigSettings["ignore_unknown"] = [
            "boolean",
            "Ignore Unknown Values",
            25,
            False,
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "ignore_unknown",
        ]
        ConfigSettings["alternate_date_format"] = [
            "boolean",
            "Alternate Date Format",
            26,
            False,
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "alternate_date_format",
        ]

        # These settings are not displayed as the auto-detect controller will set these
        # these are only to be used to override the auto-detect
        # ConfigSettings["liquidcooled"] = ['boolean', 'Force Controller Type (cooling)', 30, False, "", 0, GENMON_CONFIG, GENMON_SECTION, "liquidcooled"]
        # ConfigSettings["evolutioncontroller"] = ['boolean', 'Force Controller Type (Evo/Nexus)', 31, True, "", 0, GENMON_CONFIG, GENMON_SECTION, "evolutioncontroller"]
        # remove outage log, this will always be in the same location
        # ConfigSettings["outagelog"] = ['string', 'Outage Log', 32, "/home/pi/genmon/outage.txt", "", "required UnixFile", GENMON_CONFIG, GENMON_SECTION, "outagelog"]
        ConfigSettings["serialnumberifmissing"] = [
            "string",
            "Serial Number if Missing",
            36,
            "",
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "serialnumberifmissing",
        ]
        ConfigSettings["additionalrunhours"] = [
            "float",
            "Additional Run Hours",
            37,
            "",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "additionalrunhours",
        ]
        ConfigSettings["estimated_load"] = [
            "float",
            "Estimated Load",
            38,
            "0.0",
            "",
            "required range:0:1",
            GENMON_CONFIG,
            GENMON_SECTION,
            "estimated_load",
        ]
        ConfigSettings["subtractfuel"] = [
            "float",
            "Subtract Fuel",
            39,
            "0.0",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "subtractfuel",
        ]
        if ControllerType == "generac_evo_nexus":
            ConfigSettings["unbalanced_capacity"] = [
                "float",
                "Unbalanced Load Capacity",
                46,
                "0",
                "",
                "range:0:0.50",
                GENMON_CONFIG,
                GENMON_SECTION,
                "unbalanced_capacity",
            ]
        # ConfigSettings["kwlog"] = ['string', 'Power Log Name / Disable', 36, "", "", 0, GENMON_CONFIG, GENMON_SECTION, "kwlog"]
        if ControllerType != "h_100":
            ConfigSettings["usenominallinevolts"] = [
                "boolean",
                "Use Nominal Volts Override",
                45,
                False,
                "",
                0,
                GENMON_CONFIG,
                GENMON_SECTION,
                "usenominallinevolts",
            ]
            ConfigSettings["nominallinevolts"] = [
                "int",
                "Override nominal line voltage in UI",
                46,
                "240",
                "",
                "digits",
                GENMON_CONFIG,
                GENMON_SECTION,
                "nominallinevolts",
            ]
            ConfigSettings["outage_notice_delay"] = [
                "int",
                "Outage Notice Delay",
                47,
                "0",
                "",
                "digits",
                GENMON_CONFIG,
                GENMON_SECTION,
                "outage_notice_delay",
            ]
            ConfigSettings["min_outage_duration"] = [
                "int",
                "Minimum Outage Duration",
                48,
                "0",
                "",
                "digits",
                GENMON_CONFIG,
                GENMON_SECTION,
                "min_outage_duration",
            ]
            ConfigSettings["outage_notice_interval"] = [
                "int",
                "Outage Recurring Notice Interval (minutes)",
                49,
                "0",
                "",
                "digits",
                GENMON_CONFIG,
                GENMON_SECTION,
                "outage_notice_interval",
            ]
            ControllerInfo = GetControllerInfo("controller").lower()
            if "nexus" in ControllerInfo:
                ConfigSettings["nexus_legacy_freq"] = [
                    "boolean",
                    "Use Nexus Legacy Frequency",
                    50,
                    True,
                    "",
                    0,
                    GENMON_CONFIG,
                    GENMON_SECTION,
                    "nexus_legacy_freq",
                ]
                # this is setup automatically for Nexus controllers
                # ConfigSettings["uselegacysetexercise"] = ['boolean', 'Use Legacy Exercise Time', 49, False, "", 0, GENMON_CONFIG, GENMON_SECTION, "uselegacysetexercise"]
        else:
            ConfigSettings["usecalculatedpower"] = [
                "boolean",
                "Use Calculated Power",
                45,
                False,
                "",
                0,
                GENMON_CONFIG,
                GENMON_SECTION,
                "usecalculatedpower",
            ]

        ConfigSettings["fuel_units"] = [
            "list",
            "Fuel Units",
            55,
            "gal",
            "",
            "gal,cubic feet",
            GENMON_CONFIG,
            GENMON_SECTION,
            "fuel_units",
        ]
        ConfigSettings["half_rate"] = [
            "float",
            "Fuel Rate Half Load",
            56,
            "0.0",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "half_rate",
        ]
        ConfigSettings["full_rate"] = [
            "float",
            "Fuel Rate Full Load",
            57,
            "0.0",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "full_rate",
        ]

        ConfigSettings["enable_fuel_log"] = [
            "boolean",
            "Log Fuel Level to File",
            60,
            False,
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "enable_fuel_log",
        ]
        ConfigSettings["fuel_log_freq"] = [
            "float",
            "Fuel Log Frequency",
            61,
            "15.0",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "fuel_log_freq",
        ]
        # ConfigSettings["fuel_log"] = ['string', 'Fuel Log Path and File Name', 62, "", "", 0, GENMON_CONFIG, GENMON_SECTION, "/etc/genmon/fuellog.txt"]

        ConfigSettings["kwlogmax"] = [
            "string",
            "Maximum size Power Log (MB)",
            70,
            "",
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "kwlogmax",
        ]
        ConfigSettings["max_powerlog_entries"] = [
            "int",
            "Maximum Entries in Power Log",
            71,
            "8000",
            "digits",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "min_powerlog_entries",
        ]
        
        ConfigSettings["currentdivider"] = [
            "float",
            "Current Divider",
            72,
            "",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "currentdivider",
        ]
        ConfigSettings["currentoffset"] = [
            "float",
            "Current Offset",
            73,
            "",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "currentoffset",
        ]
        ConfigSettings["legacy_power"] = [
            "boolean",
            "Use Legacy Power Calculation",
            74,
            False,
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "legacy_power",
        ]

        ConfigSettings["disableplatformstats"] = [
            "boolean",
            "Disable Platform Stats",
            80,
            False,
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "disableplatformstats",
        ]
        ConfigSettings["https_port"] = [
            "int",
            "Override HTTPS port",
            81,
            "",
            "",
            "digits",
            GENMON_CONFIG,
            GENMON_SECTION,
            "https_port",
        ]
        ConfigSettings["user_url"] = [
            "string",
            "User URL",
            82,
            "",
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "user_url",
        ]
        ConfigSettings["extend_wait"] = [
            "int",
            "Extend email retry",
            83,
            "0",
            "",
            "digits",
            MAIL_CONFIG,
            MAIL_SECTION,
            "extend_wait",
        ]
        ConfigSettings["multi_instance"] = [
            "boolean",
            "Allow Multiple Genmon Instances",
            85,
            False,
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "multi_instance",
        ]

        ConfigSettings["max_login_attempts"] = [
            "int",
            "Maxmum login attempts before temporary lockout",
            96,
            5,
            "",
            "digits",
            GENMON_CONFIG,
            GENMON_SECTION,
            "max_login_attempts",
        ]
        ConfigSettings["login_lockout_seconds"] = [
            "int",
            "Login lockout duration in seconds",
            97,
            (5 * 60),
            "",
            "digits",
            GENMON_CONFIG,
            GENMON_SECTION,
            "login_lockout_seconds",
        ]

        try:
            if GStartInfo["Linux"]:
                ConfigSettings["uselinuxwifisignalgauge"] = [
                    "boolean",
                    "Show Wifi Signal Strength Gauge",
                    108,
                    True,
                    "",
                    0,
                    GENMON_CONFIG,
                    GENMON_SECTION,
                    "uselinuxwifisignalgauge",
                ]
            if GStartInfo["Linux"]:
                ConfigSettings["wifiispercent"] = [
                    "boolean",
                    "Wifi Gauge is percentage",
                    108,
                    False,
                    "",
                    0,
                    GENMON_CONFIG,
                    GENMON_SECTION,
                    "wifiispercent",
                ]
            if GStartInfo["Linux"]:
                ConfigSettings["useraspberrypicputempgauge"] = [
                    "boolean",
                    "Show CPU Temperature Gauge",
                    109,
                    True,
                    "",
                    0,
                    GENMON_CONFIG,
                    GENMON_SECTION,
                    "useraspberrypicputempgauge",
                ]
        except:
            pass

        for entry, List in ConfigSettings.items():
            if List[6] == GENMON_CONFIG:
                # filename, section = None, type = "string", entry, default = "", bounds = None):
                (ConfigSettings[entry])[3] = ReadSingleConfigValue(
                    entry=List[8],
                    filename=GENMON_CONFIG,
                    section=List[7],
                    type=List[0],
                    default=List[3],
                    bounds=List[5],
                )
            elif List[6] == MAIL_CONFIG:
                (ConfigSettings[entry])[3] = ReadSingleConfigValue(
                    entry=List[8],
                    filename=MAIL_CONFIG,
                    section=List[7],
                    type=List[0],
                    default=List[3],
                    bounds=List[5],
                )
            else:
                LogError(
                    "Invaild Config File in ReadAdvancedSettingsFromFile: "
                    + str(List[6])
                )

        GetToolTips(ConfigSettings)
    except Exception as e1:
        LogErrorLine("Error in ReadAdvancedSettingsFromFile: " + str(e1))
    return ConfigSettings


# -------------------------------------------------------------------------------
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
                UpdateConfigFile(ConfigFile, Section, Entry, Value)
        Restart()
    except Exception as e1:
        LogErrorLine("Error Update Config File (SaveAdvancedSettings): " + str(e1))


# -------------------------------------------------------------------------------
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

    ConfigSettings = collections.OrderedDict()
    ConfigSettings["sitename"] = [
        "string",
        "Site Name",
        1,
        "SiteName",
        "",
        "required minmax:4:50",
        GENMON_CONFIG,
        GENMON_SECTION,
        "sitename",
    ]
    ConfigSettings["use_serial_tcp"] = [
        "boolean",
        "Enable Serial over TCP/IP",
        2,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "use_serial_tcp",
    ]
    ConfigSettings["port"] = [
        "string",
        "Port for Serial Communication",
        3,
        "/dev/serial0",
        "",
        "required UnixDevice",
        GENMON_CONFIG,
        GENMON_SECTION,
        "port",
    ]
    ConfigSettings["serial_tcp_address"] = [
        "string",
        "Serial Server TCP/IP Address",
        4,
        "",
        "",
        "InternetAddress",
        GENMON_CONFIG,
        GENMON_SECTION,
        "serial_tcp_address",
    ]
    ConfigSettings["serial_tcp_port"] = [
        "int",
        "Serial Server TCP/IP Port",
        5,
        "8899",
        "",
        "digits",
        GENMON_CONFIG,
        GENMON_SECTION,
        "serial_tcp_port",
    ]
    ConfigSettings["modbus_tcp"] = [
        "boolean",
        "Use Modbus TCP protocol",
        6,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "modbus_tcp",
    ]

    ConfigSettings["disableoutagecheck"] = [
        "boolean",
        "Do Not Check for Outages",
        17,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "disableoutagecheck",
    ]

    if GStartInfo["SetGenTime"]:
        ConfigSettings["syncdst"] = [
            "boolean",
            "Sync Daylight Savings Time",
            22,
            False,
            "",
            "",
            GENMON_CONFIG,
            GENMON_SECTION,
            "syncdst",
        ]
        ConfigSettings["synctime"] = [
            "boolean",
            "Sync Time",
            23,
            False,
            "",
            "",
            GENMON_CONFIG,
            GENMON_SECTION,
            "synctime",
        ]
    ConfigSettings["metricweather"] = [
        "boolean",
        "Use Metric Units",
        24,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "metricweather",
    ]
    ConfigSettings["optimizeforslowercpu"] = [
        "boolean",
        "Optimize for slower CPUs",
        25,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "optimizeforslowercpu",
    ]
    ConfigSettings["disablepowerlog"] = [
        "boolean",
        "Disable Power / Current Display",
        26,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "disablepowerlog",
    ]
    ConfigSettings["autofeedback"] = [
        "boolean",
        "Automated Feedback",
        29,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "autofeedback",
    ]
    ConfigSettings["update_check"] = [
        "boolean",
        "Check for Software Update",
        30,
        True,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "update_check",
    ]

    ConfigSettings["nominalfrequency"] = [
        "list",
        "Rated Frequency",
        101,
        "60",
        "",
        "50,60",
        GENMON_CONFIG,
        GENMON_SECTION,
        "nominalfrequency",
    ]
    ConfigSettings["nominalrpm"] = [
        "int",
        "Nominal RPM",
        102,
        "3600",
        "",
        "required digits range:1500:4000",
        GENMON_CONFIG,
        GENMON_SECTION,
        "nominalrpm",
    ]
    ConfigSettings["nominalkw"] = [
        "int",
        "Maximum kW Output",
        103,
        "22",
        "",
        "required digits range:0:1000",
        GENMON_CONFIG,
        GENMON_SECTION,
        "nominalkw",
    ]
    ConfigSettings["fueltype"] = [
        "list",
        "Fuel Type",
        104,
        "Natural Gas",
        "",
        "Natural Gas,Propane,Diesel,Gasoline",
        GENMON_CONFIG,
        GENMON_SECTION,
        "fueltype",
    ]
    ConfigSettings["tanksize"] = [
        "int",
        "Fuel Tank Size",
        105,
        "0",
        "",
        "required digits range:0:10000",
        GENMON_CONFIG,
        GENMON_SECTION,
        "tanksize",
    ]

    ControllerInfo = GetControllerInfo("controller").lower()
    if (
        "liquid cooled" in ControllerInfo
        and "evolution" in ControllerInfo
        and GetControllerInfo("fueltype").lower() == "diesel"
    ):
        ConfigSettings["usesensorforfuelgauge"] = [
            "boolean",
            "Use Sensor for Fuel Gauge",
            106,
            True,
            "",
            "",
            GENMON_CONFIG,
            GENMON_SECTION,
            "usesensorforfuelgauge",
        ]

    if ControllerType == "h_100" or ControllerType == "powerzone":
        Choices = "120/208,120/240,230/400,240/415,277/480,347/600"
        ConfigSettings["voltageconfiguration"] = [
            "list",
            "Line to Neutral / Line to Line",
            107,
            "277/480",
            "",
            Choices,
            GENMON_CONFIG,
            GENMON_SECTION,
            "voltageconfiguration",
        ]
        ConfigSettings["hts_transfer_switch"] = [
            "boolean",
            "HTS/MTS/STS Transfer Switch",
            109,
            False,
            "",
            "",
            GENMON_CONFIG,
            GENMON_SECTION,
            "hts_transfer_switch",
        ]
        ConfigSettings["usesensorforfuelgauge"] = [
            "boolean",
            "Use Sensor for Fuel Gauge",
            106,
            False,
            "",
            "",
            GENMON_CONFIG,
            GENMON_SECTION,
            "usesensorforfuelgauge",
        ]
    else:  # ControllerType == "generac_evo_nexus":
        ConfigSettings["enhancedexercise"] = [
            "boolean",
            "Enhanced Exercise Time",
            109,
            False,
            "",
            "",
            GENMON_CONFIG,
            GENMON_SECTION,
            "enhancedexercise",
        ]
    
    if ControllerType == "custom":
        ConfigSettings["nominalbattery"] = [
                "list",
                "Nomonal Battery Voltage",
                108,
                "24",
                "",
                "12,24",
                GENMON_CONFIG,
                GENMON_SECTION,
                "nominalbattery",
            ]

    ConfigSettings["smart_transfer_switch"] = [
        "boolean",
        "Smart Transfer Switch",
        110,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "smart_transfer_switch",
    ]
    ConfigSettings["displayunknown"] = [
        "boolean",
        "Display Unknown Sensors",
        111,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "displayunknown",
    ]

    if ControllerType == "h_100":
        ConfigSettings["industrialoutagecheck"] = [
            "boolean",
            "Outage Notice on Transfer State Change",
            112,
            False,
            "",
            "",
            GENMON_CONFIG,
            GENMON_SECTION,
            "industrialoutagecheck",
        ]

    # These do not appear to work on reload, some issue with Flask
    ConfigSettings["usehttps"] = [
        "boolean",
        "Use Secure Web Settings",
        200,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "usehttps",
    ]
    ConfigSettings["useselfsignedcert"] = [
        "boolean",
        "Use Self-signed Certificate",
        203,
        True,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "useselfsignedcert",
    ]
    ConfigSettings["keyfile"] = [
        "string",
        "https Key File",
        204,
        "",
        "",
        "UnixFile",
        GENMON_CONFIG,
        GENMON_SECTION,
        "keyfile",
    ]
    ConfigSettings["certfile"] = [
        "string",
        "https Certificate File",
        205,
        "",
        "",
        "UnixFile",
        GENMON_CONFIG,
        GENMON_SECTION,
        "certfile",
    ]
    ConfigSettings["http_user"] = [
        "string",
        "Web Username",
        206,
        "",
        "",
        "minmax:4:50",
        GENMON_CONFIG,
        GENMON_SECTION,
        "http_user",
    ]
    ConfigSettings["http_pass"] = [
        "password",
        "Web Password",
        207,
        "",
        "",
        "minmax:4:50",
        GENMON_CONFIG,
        GENMON_SECTION,
        "http_pass",
    ]
    ConfigSettings["http_user_ro"] = [
        "string",
        "Limited Rights User Username",
        208,
        "",
        "",
        "minmax:4:50",
        GENMON_CONFIG,
        GENMON_SECTION,
        "http_user_ro",
    ]
    ConfigSettings["http_pass_ro"] = [
        "password",
        "Limited Rights User Password",
        209,
        "",
        "",
        "minmax:4:50",
        GENMON_CONFIG,
        GENMON_SECTION,
        "http_pass_ro",
    ]
    ConfigSettings["http_port"] = [
        "int",
        "Port of WebServer",
        215,
        8000,
        "",
        "required digits",
        GENMON_CONFIG,
        GENMON_SECTION,
        "http_port",
    ]
    ConfigSettings["favicon"] = [
        "string",
        "FavIcon",
        220,
        "",
        "",
        "minmax:8:255",
        GENMON_CONFIG,
        GENMON_SECTION,
        "favicon",
    ]
    ConfigSettings["usemfa"] = [
        "boolean",
        "Use Multi-Factor Authentication",
        210,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "usemfa",
    ]
    # this value is for display only, it can not be changed by the web app
    ConfigSettings["mfa_url"] = [
        "qrcode",
        "MFA QRCode",
        212,
        MFA_URL,
        "",
        "",
        None,
        None,
        "mfa_url",
    ]

    #
    # ConfigSettings["disableemail"] = ['boolean', 'Disable Email Usage', 300, True, "", "", MAIL_CONFIG, MAIL_SECTION, "disableemail"]
    ConfigSettings["disablesmtp"] = [
        "boolean",
        "Disable Sending Email",
        300,
        False,
        "",
        "",
        MAIL_CONFIG,
        MAIL_SECTION,
        "disablesmtp",
    ]
    ConfigSettings["email_account"] = [
        "string",
        "Email Account",
        301,
        "myemail@gmail.com",
        "",
        "minmax:3:50",
        MAIL_CONFIG,
        MAIL_SECTION,
        "email_account",
    ]
    ConfigSettings["email_pw"] = [
        "password",
        "Email Password",
        302,
        "password",
        "",
        "max:70",
        MAIL_CONFIG,
        MAIL_SECTION,
        "email_pw",
    ]
    ConfigSettings["sender_account"] = [
        "string",
        "Sender Address",
        303,
        "no-reply@gmail.com",
        "",
        "email",
        MAIL_CONFIG,
        MAIL_SECTION,
        "sender_account",
    ]
    ConfigSettings["sender_name"] = [
        "string",
        "Sender Name",
        304,
        "",
        "",
        "max:50",
        MAIL_CONFIG,
        MAIL_SECTION,
        "sender_name",
    ]
    # email_recipient setting will be handled on the notification screen
    ConfigSettings["smtp_server"] = [
        "string",
        "SMTP Server <br><small>(leave emtpy to disable)</small>",
        305,
        "smtp.gmail.com",
        "",
        "InternetAddress",
        MAIL_CONFIG,
        MAIL_SECTION,
        "smtp_server",
    ]
    ConfigSettings["smtp_port"] = [
        "int",
        "SMTP Server Port",
        307,
        587,
        "",
        "digits",
        MAIL_CONFIG,
        MAIL_SECTION,
        "smtp_port",
    ]
    ConfigSettings["ssl_enabled"] = [
        "boolean",
        "Use SSL Encryption",
        308,
        False,
        "",
        "",
        MAIL_CONFIG,
        MAIL_SECTION,
        "ssl_enabled",
    ]
    ConfigSettings["tls_disable"] = [
        "boolean",
        "Disable TLS Encryption",
        309,
        False,
        "",
        "",
        MAIL_CONFIG,
        MAIL_SECTION,
        "tls_disable",
    ]
    ConfigSettings["smtpauth_disable"] = [
        "boolean",
        "Disable SMTP Auth",
        309,
        False,
        "",
        "",
        MAIL_CONFIG,
        MAIL_SECTION,
        "smtpauth_disable",
    ]

    ConfigSettings["disableimap"] = [
        "boolean",
        "Disable Receiving Email",
        400,
        False,
        "",
        "",
        MAIL_CONFIG,
        MAIL_SECTION,
        "disableimap",
    ]
    ConfigSettings["imap_server"] = [
        "string",
        "IMAP Server <br><small>(leave emtpy to disable)</small>",
        401,
        "imap.gmail.com",
        "",
        "InternetAddress",
        MAIL_CONFIG,
        MAIL_SECTION,
        "imap_server",
    ]
    ConfigSettings["readonlyemailcommands"] = [
        "boolean",
        "Disable Email Write Commands",
        402,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "readonlyemailcommands",
    ]
    ConfigSettings["incoming_mail_folder"] = [
        "string",
        "Incoming Mail Folder<br><small>(if IMAP enabled)</small>",
        403,
        "Generator",
        "",
        "minmax:1:1500",
        GENMON_CONFIG,
        GENMON_SECTION,
        "incoming_mail_folder",
    ]
    ConfigSettings["processed_mail_folder"] = [
        "string",
        "Mail Processed Folder<br><small>(if IMAP enabled)</small>",
        404,
        "Generator/Processed",
        "",
        "minmax:1:255",
        GENMON_CONFIG,
        GENMON_SECTION,
        "processed_mail_folder",
    ]

    ConfigSettings["disableweather"] = [
        "boolean",
        "Disable Weather Functionality",
        500,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "disableweather",
    ]
    ConfigSettings["weatherkey"] = [
        "string",
        "Openweathermap.org API key",
        501,
        "",
        "",
        "required minmax:4:50",
        GENMON_CONFIG,
        GENMON_SECTION,
        "weatherkey",
    ]
    ConfigSettings["weatherlocation"] = [
        "string",
        "Location to report weather",
        502,
        "",
        "",
        "required minmax:4:50",
        GENMON_CONFIG,
        GENMON_SECTION,
        "weatherlocation",
    ]
    ConfigSettings["minimumweatherinfo"] = [
        "boolean",
        "Display Minimum Weather Info",
        504,
        True,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "minimumweatherinfo",
    ]

    try:
        # Get all the config values
        for entry, List in ConfigSettings.items():
            if List[6] == GENMON_CONFIG:
                # filename, section = None, type = "string", entry, default = "", bounds = None):
                (ConfigSettings[entry])[3] = ReadSingleConfigValue(
                    entry=List[8],
                    filename=GENMON_CONFIG,
                    section=List[7],
                    type=List[0],
                    default=List[3],
                    bounds=List[5],
                )
            elif List[6] == MAIL_CONFIG:
                (ConfigSettings[entry])[3] = ReadSingleConfigValue(
                    entry=List[8],
                    filename=MAIL_CONFIG,
                    section=List[7],
                    type=List[0],
                    default=List[3],
                )
            elif List[6] == None:
                # intentionally do not write or read from config file
                pass
            else:
                LogError("Invaild Config File in ReadSettingsFromFile: " + str(List[6]))

        GetToolTips(ConfigSettings)
    except Exception as e1:
        LogErrorLine("Error in ReadSettingsFromFile: " + entry + ": " + str(e1))

    return ConfigSettings


# -------------------------------------------------------------------------------
def GetAllConfigValues(FileName, section):

    ReturnDict = {}
    try:
        config = MyConfig(filename=FileName, section=section, log=log)

        if config == None:
            return ReturnDict
        for (key, value) in config.GetList():
            ReturnDict[key.lower()] = value
    except Exception as e1:
        LogErrorLine(
            "Error GetAllConfigValues: " + FileName + ": " + section + ": " + str(e1)
        )

    return ReturnDict


# -------------------------------------------------------------------------------
def GetControllerInfo(request=None):

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


# -------------------------------------------------------------------------------
def CacheToolTips():

    global CachedToolTips
    global ControllerType
    global CachedRegisterDescriptions

    try:

        foundRegText = False
        config_section = "generac_evo_nexus"
        pathtofile = os.path.dirname(os.path.realpath(__file__))
        try:
            data = MyClientInterface.ProcessMonitorCommand("generator: getreglabels_json")
            regdata = json.loads(data)
            if len(regdata):
                CachedRegisterDescriptions = regdata
                foundRegText = True
        except Exception as e1:
            LogErrorLine("Error in CacheToolTips reading reg data")

        # get controller used
        if ConfigFiles[GENMON_CONFIG].HasOption("controllertype"):
            config_section = ConfigFiles[GENMON_CONFIG].ReadValue("controllertype")
        else:
            config_section = "generac_evo_nexus"

        if not len(config_section):
            config_section = "generac_evo_nexus"

        # H_100
        ControllerType = config_section

        if ControllerType == "h_100":
            try:
                if (
                    len(GStartInfo["Controller"])
                    and not "H-100" in GStartInfo["Controller"]
                ):
                    # Controller is G-Panel
                    config_section = "g_panel"

            except Exception as e1:
                LogError("Error reading Controller Type for H-100: " + str(e1))
        if not foundRegText:
            CachedRegisterDescriptions = {"Holding":GetAllConfigValues(
                os.path.join(pathtofile, "data", "tooltips.txt"), config_section
            )}

        CachedToolTips = GetAllConfigValues(
            os.path.join(pathtofile, "data", "tooltips.txt"), "ToolTips"
        )

    except Exception as e1:
        LogErrorLine("Error reading tooltips.txt " + str(e1))


# -------------------------------------------------------------------------------
def GetToolTips(ConfigSettings):

    try:

        for entry, List in ConfigSettings.items():
            try:
                (ConfigSettings[entry])[4] = CachedToolTips[entry.lower()]
            except:
                # self.LogError("Error in GetToolTips: " + entry)
                pass  # TODO

    except Exception as e1:
        LogErrorLine("Error in GetToolTips: " + str(e1))


# -------------------------------------------------------------------------------
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
                UpdateConfigFile(ConfigFile, Section, Entry, Value)
        Restart()
    except Exception as e1:
        LogErrorLine("Error Update Config File (SaveSettings): " + str(e1))


# ---------------------MySupport::UpdateConfigFile-------------------------------
# Add or update config item
def UpdateConfigFile(FileName, section, Entry, Value):

    try:

        if FileName == None or section == None or Entry == None or Value == None:
            return False
        if FileName == "" or section == "" or Entry == "":
            return False
        try:
            config = ConfigFiles[FileName]
        except Exception as e1:
            LogErrorLine(
                "Unknow file in UpdateConfigFile: " + FileName + ": " + str(e1)
            )
            return False

        config.SetSection(section)
        return config.WriteValue(Entry, Value)

    except Exception as e1:
        LogErrorLine("Error Update Config File (UpdateConfigFile): " + str(e1))
        return False


# -------------------------------------------------------------------------------
# This will reboot the pi
def Reboot():
    os.system("sudo reboot now")


# -------------------------------------------------------------------------------
# This will shutdown the pi
def Shutdown():
    os.system("sudo shutdown -h now")


# -------------------------------------------------------------------------------
# This will restart the Flask App
def Restart():

    global Restarting

    try:
        Restarting = True
        if sys.version_info >= (3, 0):
            if not RunBashScript("startgenmon.sh restart -p 3 -c " + ConfigFilePath):
                LogError("Error in Restart")
        else:
            # begining with V1.18.0 the following command will default restart with python 3
            if not RunBashScript("startgenmon.sh restart -c " + ConfigFilePath):
                LogError("Error in Restart")
    except Exception as e1:
        LogErrorLine("Error in Restart: " + str(e1))


# -------------------------------------------------------------------------------
def Update():
    # update
    try:
        if sys.version_info >= (3, 0):
            if not RunBashScript("genmonmaint.sh -u -n -p 3", log = True):
                LogError("Error in Update")
        else:
            if not RunBashScript("genmonmaint.sh -u -n -p 2"):  # update no prompt
                LogError("Error in Update")
        # now restart
        Restart()
    except Exception as e1:
        LogErrorLine("Error in Update: " + str(e1))


# -------------------------------------------------------------------------------
def GetLogs():
    # update
    if not RunBashScript("genmonmaint.sh -l " + loglocation):  # archive logs
        LogError("Error in GetLogs")


# -------------------------------------------------------------------------------
def Backup():
    # update
    if not RunBashScript("genmonmaint.sh -b -c " + ConfigFilePath):  # backup
        LogError("Error in Backup")


# -------------------------------------------------------------------------------
def RunBashScript(ScriptName, log = False):
    try:
        pathtoscript = os.path.dirname(os.path.realpath(__file__))
        script = os.path.join(pathtoscript, ScriptName)
        command = "/bin/bash "
        LogError("Script: " + command + script)
        if log == False:
            subprocess.call(command + script, shell=True)
        else:
            try:
                output = subprocess.check_output(command + script, shell=True, stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as e:
                output = e.output.decode()

            if sys.version_info >= (3, 0):
                output = output.decode()
            LogError(command + script + ": \n" +  output)
        return True

    except Exception as e1:
        LogErrorLine("Error in RunBashScript: (" + ScriptName + ") : " + str(e1))
        return False


# -------------------------------------------------------------------------------
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
        LogErrorLine(
            "Error in CheckCertFiles: Unable to open Cert or Key file: "
            + CertFile
            + ", "
            + KeyFile
            + " : "
            + str(e1)
        )
        return False

    return True


# -------------------------------------------------------------------------------
def generate_adhoc_ssl_context():
    # Generates an adhoc SSL context web server.
    try:
        import atexit
        import ssl
        import tempfile
        from random import random

        from OpenSSL import crypto

        cert = crypto.X509()
        cert.set_serial_number(int(random() * sys.maxsize))
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(60 * 60 * 24 * 365)

        subject = cert.get_subject()
        subject.CN = "*"
        subject.O = "Dummy Certificate"

        issuer = cert.get_issuer()
        issuer.CN = "Untrusted Authority"
        issuer.O = "Self-Signed"

        pkey = crypto.PKey()
        pkey.generate_key(crypto.TYPE_RSA, 2048)
        cert.set_pubkey(pkey)
        cert.sign(pkey, "sha256")

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


# -------------------------------------------------------------------------------
def LoadConfig():

    global log
    global clientport
    global loglocation
    global bUseMFA
    global SecretMFAKey
    global bUseSecureHTTP
    global LdapServer
    global LdapBase
    global DomainNetbios
    global LdapAdminGroup
    global LdapReadOnlyGroup

    global ListenIPAddress
    global HTTPPort
    global HTTPAuthUser
    global HTTPAuthPass
    global HTTPAuthUser_RO
    global HTTPAuthPass_RO
    global SSLContext
    global favicon
    global MaxLoginAttempts
    global LockOutDuration

    HTTPAuthPass = None
    HTTPAuthUser = None
    SSLContext = None
    LdapServer = None
    LdapBase = None
    DomainNetbios = None
    LdapAdminGroup = None
    LdapReadOnlyGroup = None

    try:

        # heartbeat server port, must match value in check_generator_system.py and any calling client apps
        if ConfigFiles[GENMON_CONFIG].HasOption("server_port"):
            clientport = ConfigFiles[GENMON_CONFIG].ReadValue(
                "server_port", return_type=int, default=ProgramDefaults.ServerPort
            )

        bUseMFA = ConfigFiles[GENMON_CONFIG].ReadValue(
            "usemfa", return_type=bool, default=False
        )
        SecretMFAKey = ConfigFiles[GENMON_CONFIG].ReadValue("secretmfa", default=None)

        if SecretMFAKey == None or SecretMFAKey == "":
            SecretMFAKey = str(pyotp.random_base32())
            ConfigFiles[GENMON_CONFIG].WriteValue("secretmfa", str(SecretMFAKey))

        SetupMFA()

        if ConfigFiles[GENMON_CONFIG].HasOption("usehttps"):
            bUseSecureHTTP = ConfigFiles[GENMON_CONFIG].ReadValue(
                "usehttps", return_type=bool
            )
        if not bUseSecureHTTP:
            # dont use MFA unless HTTPS is enabled
            bUseMFA = False

        ListenIPAddress = ConfigFiles[GENMON_CONFIG].ReadValue("flask_listen_ip_address", default="0.0.0.0")
        
        if ConfigFiles[GENMON_CONFIG].HasOption("http_port"):
            HTTPPort = ConfigFiles[GENMON_CONFIG].ReadValue(
                "http_port", return_type=int, default=8000
            )

        if ConfigFiles[GENMON_CONFIG].HasOption("favicon"):
            favicon = ConfigFiles[GENMON_CONFIG].ReadValue("favicon")

        MaxLoginAttempts = ConfigFiles[GENMON_CONFIG].ReadValue(
            "max_login_attempts", return_type=int, default=5
        )
        LockOutDuration = ConfigFiles[GENMON_CONFIG].ReadValue(
            "login_lockout_seconds", return_type=int, default=(5 * 60)
        )

        # user name and password require usehttps = True
        if bUseSecureHTTP:
            if ConfigFiles[GENMON_CONFIG].HasOption("ldap_server"):
                LdapServer = ConfigFiles[GENMON_CONFIG].ReadValue(
                    "ldap_server", default=""
                )
                LdapServer = LdapServer.strip()
                if LdapServer == "":
                    LdapServer = None
                else:
                    if ConfigFiles[GENMON_CONFIG].HasOption("ldap_base"):
                        LdapBase = ConfigFiles[GENMON_CONFIG].ReadValue(
                            "ldap_base", default=""
                        )
                    if ConfigFiles[GENMON_CONFIG].HasOption("domain_netbios"):
                        DomainNetbios = ConfigFiles[GENMON_CONFIG].ReadValue(
                            "domain_netbios", default=""
                        )
                    if ConfigFiles[GENMON_CONFIG].HasOption("ldap_admingroup"):
                        LdapAdminGroup = ConfigFiles[GENMON_CONFIG].ReadValue(
                            "ldap_admingroup", default=""
                        )
                    if ConfigFiles[GENMON_CONFIG].HasOption("ldap_readonlygroup"):
                        LdapReadOnlyGroup = ConfigFiles[GENMON_CONFIG].ReadValue(
                            "ldap_readonlygroup", default=""
                        )
                    if LdapBase == "":
                        LdapBase = None
                    if DomainNetbios == "":
                        DomainNetbios = None
                    if LdapAdminGroup == "":
                        LdapAdminGroup = None
                    if LdapReadOnlyGroup == "":
                        LdapReadOnlyGroup = None
                    if (
                        LdapReadOnlyGroup == None
                        and LdapAdminGroup == None
                        or LdapBase == None
                        or DomainNetbios == None
                    ):
                        LdapServer = None

            if ConfigFiles[GENMON_CONFIG].HasOption("http_user"):
                HTTPAuthUser = ConfigFiles[GENMON_CONFIG].ReadValue(
                    "http_user", default=""
                )
                HTTPAuthUser = HTTPAuthUser.strip()
                # No user name or pass specified, disable
                if HTTPAuthUser == "":
                    HTTPAuthUser = None
                    HTTPAuthPass = None
                elif ConfigFiles[GENMON_CONFIG].HasOption("http_pass"):
                    HTTPAuthPass = ConfigFiles[GENMON_CONFIG].ReadValue(
                        "http_pass", default=""
                    )
                    HTTPAuthPass = HTTPAuthPass.strip()
                if HTTPAuthUser != None and HTTPAuthPass != None:
                    if ConfigFiles[GENMON_CONFIG].HasOption("http_user_ro"):
                        HTTPAuthUser_RO = ConfigFiles[GENMON_CONFIG].ReadValue(
                            "http_user_ro", default=""
                        )
                        HTTPAuthUser_RO = HTTPAuthUser_RO.strip()
                        if HTTPAuthUser_RO == "":
                            HTTPAuthUser_RO = None
                            HTTPAuthPass_RO = None
                        elif ConfigFiles[GENMON_CONFIG].HasOption("http_pass_ro"):
                            HTTPAuthPass_RO = ConfigFiles[GENMON_CONFIG].ReadValue(
                                "http_pass_ro", default=""
                            )
                            HTTPAuthPass_RO = HTTPAuthPass_RO.strip()

            HTTPSPort = ConfigFiles[GENMON_CONFIG].ReadValue(
                "https_port", return_type=int, default=443
            )

        app.secret_key = os.urandom(12)
        if bUseSecureHTTP:
            OldHTTPPort = HTTPPort
            HTTPPort = HTTPSPort
            if ConfigFiles[GENMON_CONFIG].HasOption("useselfsignedcert"):
                bUseSelfSignedCert = ConfigFiles[GENMON_CONFIG].ReadValue(
                    "useselfsignedcert", return_type=bool
                )

                if bUseSelfSignedCert:
                    SSLContext = (
                        generate_adhoc_ssl_context()
                    )  #  create our own self signed cert
                    if SSLContext == None:
                        SSLContext = "adhoc"  # Use Flask supplied self signed cert
                else:
                    if ConfigFiles[GENMON_CONFIG].HasOption("certfile") and ConfigFiles[
                        GENMON_CONFIG
                    ].HasOption("keyfile"):
                        CertFile = ConfigFiles[GENMON_CONFIG].ReadValue("certfile")
                        KeyFile = ConfigFiles[GENMON_CONFIG].ReadValue("keyfile")
                        if CheckCertFiles(CertFile, KeyFile):
                            SSLContext = (CertFile, KeyFile)  # tuple
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


# ---------------------ValidateOTP-----------------------------------------------
def ValidateOTP(password):

    if bUseMFA:
        try:
            TimeOTP = pyotp.TOTP(SecretMFAKey, interval=30)
            return TimeOTP.verify(password)
        except Exception as e1:
            LogErrorLine("Error in ValidateOTP: " + str(e1))
    return False


# ---------------------GetOTP----------------------------------------------------
def GetOTP():
    try:
        if bUseMFA:
            TimeOTP = pyotp.TOTP(SecretMFAKey, interval=30)
            OTP = TimeOTP.now()
            msgbody = "\nThis password will expire in 30 seconds: " + str(OTP)
            mail.sendEmail("Generator Monitor login one time password", msgbody)
            return OTP
    except Exception as e1:
        LogErrorLine("Error in GetOTP: " + str(e1))


# ---------------------SetupMFA--------------------------------------------------
def SetupMFA():

    global MFA_URL
    global mail

    try:
        mail = MyMail(ConfigFilePath=ConfigFilePath)
        MFA_URL = pyotp.totp.TOTP(SecretMFAKey).provisioning_uri(
            mail.SenderAccount, issuer_name="Genmon"
        )
        # MFA_URL += "&image=https://raw.githubusercontent.com/jgyates/genmon/master/static/images/Genmon.png"
    except Exception as e1:
        LogErrorLine("Error setting up 2FA: " + str(e1))


# ---------------------LogConsole------------------------------------------------
def LogConsole(Message):
    if not console == None:
        console.error(Message)


# ---------------------LogError--------------------------------------------------
def LogError(Message):
    if not log == None:
        log.error(Message)


# ---------------------FatalError------------------------------------------------
def FatalError(Message):
    if not log == None:
        log.error(Message)
    raise Exception(Message)


# ---------------------LogErrorLine----------------------------------------------
def LogErrorLine(Message):
    if not log == None:
        LogError(Message + " : " + GetErrorLine())


# ---------------------GetErrorLine----------------------------------------------
def GetErrorLine():
    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    lineno = exc_tb.tb_lineno
    return fname + ":" + str(lineno)


# -------------------------------------------------------------------------------
def SignalClose(signum, frame):

    Close()


# -------------------------------------------------------------------------------
def Close():

    global Closing

    if Closing:
        return
    Closing = True
    try:
        MyClientInterface.Close()
    except Exception as e1:
        LogErrorLine("Error in close: " + str(e1))

    sys.exit(0)


# -------------------------------------------------------------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("genserv")

    signal.signal(signal.SIGTERM, SignalClose)
    signal.signal(signal.SIGINT, SignalClose)

    MAIL_CONFIG = os.path.join(ConfigFilePath, "mymail.conf")
    GENMON_CONFIG = os.path.join(ConfigFilePath, "genmon.conf")
    GENLOADER_CONFIG = os.path.join(ConfigFilePath, "genloader.conf")
    GENSMS_CONFIG = os.path.join(ConfigFilePath, "gensms.conf")
    MYMODEM_CONFIG = os.path.join(ConfigFilePath, "mymodem.conf")
    GENPUSHOVER_CONFIG = os.path.join(ConfigFilePath, "genpushover.conf")
    GENMQTT_CONFIG = os.path.join(ConfigFilePath, "genmqtt.conf")
    GENMQTTIN_CONFIG = os.path.join(ConfigFilePath, "genmqttin.conf")
    GENSLACK_CONFIG = os.path.join(ConfigFilePath, "genslack.conf")
    GENCALLMEBOT_CONFIG = os.path.join(ConfigFilePath, "gencallmebot.conf")
    GENGPIOIN_CONFIG = os.path.join(ConfigFilePath, "gengpioin.conf")
    GENGPIOLEDBLINK_CONFIG = os.path.join(ConfigFilePath, "gengpioledblink.conf")
    GENEXERCISE_CONFIG = os.path.join(ConfigFilePath, "genexercise.conf")
    GENEMAIL2SMS_CONFIG = os.path.join(ConfigFilePath, "genemail2sms.conf")
    GENTANKUTIL_CONFIG = os.path.join(ConfigFilePath, "gentankutil.conf")
    GENCENTRICONNECT_CONFIG = os.path.join(ConfigFilePath, "gencentriconnect.conf")
    GENTANKDIY_CONFIG = os.path.join(ConfigFilePath, "gentankdiy.conf")
    GENALEXA_CONFIG = os.path.join(ConfigFilePath, "genalexa.conf")
    GENSNMP_CONFIG = os.path.join(ConfigFilePath, "gensnmp.conf")
    GENTEMP_CONFIG = os.path.join(ConfigFilePath, "gentemp.conf")
    GENCTHAT_CONFIG = os.path.join(ConfigFilePath, "gencthat.conf")
    GENMOPEKA_CONFIG = os.path.join(ConfigFilePath, "genmopeka.conf")
    GENSMS_VOIP_CONFIG = os.path.join(ConfigFilePath, "gensms_voip.conf")

    ConfigFileList = [
        GENMON_CONFIG,
        MAIL_CONFIG,
        GENLOADER_CONFIG,
        GENSMS_CONFIG,
        MYMODEM_CONFIG,
        GENPUSHOVER_CONFIG,
        GENMQTT_CONFIG,
        GENMQTTIN_CONFIG,
        GENSLACK_CONFIG,
        GENCALLMEBOT_CONFIG,
        GENGPIOIN_CONFIG,
        GENGPIOLEDBLINK_CONFIG,
        GENEXERCISE_CONFIG,
        GENEMAIL2SMS_CONFIG,
        GENTANKUTIL_CONFIG,
        GENCENTRICONNECT_CONFIG,
        GENTANKDIY_CONFIG,
        GENALEXA_CONFIG,
        GENSNMP_CONFIG,
        GENTEMP_CONFIG,
        GENCTHAT_CONFIG,
        GENMOPEKA_CONFIG,
        GENSMS_VOIP_CONFIG,
    ]

    for ConfigFile in ConfigFileList:
        if not os.path.isfile(ConfigFile):
            LogConsole("Missing config file : " + ConfigFile)
            sys.exit(1)

    ConfigFiles = {}
    for ConfigFile in ConfigFileList:
        if log == None:
            configlog = console
        else:
            configlog = log
        ConfigFiles[ConfigFile] = MyConfig(filename=ConfigFile, log=configlog)

    AppPath = sys.argv[0]
    if not LoadConfig():
        LogConsole("Error reading configuraiton file.")
        sys.exit(1)

    for ConfigFile in ConfigFileList:
        ConfigFiles[ConfigFile].log = log

    LogError(
        "Starting "
        + AppPath
        + ", Port:"
        + str(HTTPPort)
        + ", Secure HTTP: "
        + str(bUseSecureHTTP)
        + ", SelfSignedCert: "
        + str(bUseSelfSignedCert)
        + ", UseMFA:"
        + str(bUseMFA)
    )
    # validate needed files are present
    filename = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "startgenmon.sh"
    )
    if not os.path.isfile(filename):
        LogError("Required file missing : startgenmon.sh")
        sys.exit(1)

    filename = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "genmonmaint.sh"
    )
    if not os.path.isfile(filename):
        LogError("Required file missing : genmonmaint.sh")
        sys.exit(1)

    MyClientInterface = ClientInterface(host=address, port=clientport, log=log)

    Start = datetime.datetime.now()

    while (datetime.datetime.now() - Start).total_seconds() < 10:
        data = MyClientInterface.ProcessMonitorCommand("generator: gethealth")
        if "OK" in data:
            LogConsole(" OK - Init complete.")
            break

    try:
        data = MyClientInterface.ProcessMonitorCommand("generator: start_info_json")
        GStartInfo = json.loads(data)
    except Exception as e1:
        LogError("Error getting start info : " + str(e1))
        LogError("Data returned from start_info_json: " + data)
        sys.exit(1)

    CacheToolTips()
    try:
        app.run(
            host=ListenIPAddress,
            port=HTTPPort,
            threaded=True,
            ssl_context=SSLContext,
            use_reloader=False,
            debug=False,
        )

    except Exception as e1:
        LogErrorLine("Error in app.run: " + str(e1))
        # Errno 98
        if e1.errno != errno.EADDRINUSE:  # and e1.errno != errno.EIO:
            sys.exit(1)
        # retry once
        try:
            LogError("Retrying app.run()")
            time.sleep(2)
            app.run(
                host=ListenIPAddress,
                port=HTTPPort,
                threaded=True,
                ssl_context=SSLContext,
                use_reloader=False,
                debug=False,
            )
        except Exception as e2:
            LogErrorLine("Error in app.run (2): " + str(e2))
        sys.exit(0)
