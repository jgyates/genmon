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
import hashlib
import hmac
import json
import os
import os.path
import secrets
import signal
import subprocess
import sys
import threading
import time
import uuid

try:
    from flask import (
        Flask,
        Response,
        jsonify,
        make_response,
        redirect,
        render_template,
        request,
        send_file,
        send_from_directory,
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
    from genmonlib.myfileutil import AtomicWrite
    from genmonlib.mylog import SetupLogger
    from genmonlib.mymail import MyMail
    from genmonlib.mysupport import MySupport
    from genmonlib.myplatform import MyPlatform
    from genmonlib.program_defaults import ProgramDefaults
    from genmonlib.genservsettings import (
        ADVANCED_SETTINGS,
        GENMON_DIR,
        IMPORT_CONFIG_FILES,
        Dynamic,
    )

except Exception as e1:
    print(
        "\n\nThis program requires the modules located in the genmonlib directory in the original github repository.\n"
    )
    print(
        "Please see the project documentation at https://github.com/jgyates/genmon.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)

from urllib.parse import urlparse
from urllib.parse import parse_qs
from urllib.parse import parse_qsl

import datetime
import re

# -------------------------------------------------------------------------------
app = Flask(__name__, static_url_path="")

# Enable gzip compression when flask-compress is available; big bandwidth win
# for slow/remote clients. Silently skipped if the package is not installed.
try:
    from flask_compress import Compress

    Compress(app)
except Exception:
    pass

# -------------------------------------------------------------------------------
# ServePage is the documented call for genservext.py extensions (see the wiki,
# "Extend genserv.py"). It serves a page from the static folder, showing the
# login page first if a login is required. It is defined here, before
# genservext.py is imported below, so the extension can import it with
# "from __main__ import app, ServePage".
def ServePage(page_file):
    return GenServInstance.ServePage(page_file)


# this allows the flask support to be extended on a per site basis but sill allow for
# updates via the main github repository. If genservex.py exists, load it
if os.path.isfile(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "genservext.py")
):
    import genservext

app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 300


# -------------------------------------------------------------------------------
# One /cmd/ command, see GenServ.COMMANDS.
#   handler  None: the command is passed to genmon as "generator: <name>".
#            Otherwise the name of the GenServ method that answers it.
#   write    needs write access; the dispatcher refuses read only users
#   post     POST only, with the X-CSRFToken header; a GET returns 405
#   param    request value added to the genmon command as "=<value>"
#   maxlen   if set, the value is required, null bytes and newlines are
#            removed and it is cut to this length
#   json     genmon replies with JSON, which is returned unchanged; other
#            genmon replies are returned as a JSON string
# A read only user gets "Read Only Mode" for a genmon command with write set,
# and "Access denied" for the others.
Cmd = collections.namedtuple(
    "Cmd", "handler write post param maxlen json",
    defaults=(None, False, False, None, None, False),
)


# -------------------------------------------------------------------------------
class GenServ(MySupport):

    # /cmd/<command> commands. To add a command, add it here (and for one
    # genserv answers itself, the method named as its handler).
    COMMANDS = {
        # passed to genmon, reading
        "status": Cmd(),
        "status_json": Cmd(json=True),
        "status_num_json": Cmd(json=True),
        "outage": Cmd(),
        "outage_json": Cmd(json=True),
        "outage_num_json": Cmd(json=True),
        "maint": Cmd(),
        "maint_json": Cmd(json=True),
        "maint_num_json": Cmd(json=True),
        "logs": Cmd(),
        "logs_json": Cmd(json=True),
        "monitor": Cmd(),
        "monitor_json": Cmd(json=True),
        "monitor_num_json": Cmd(json=True),
        "registers_json": Cmd(json=True),
        "allregs_json": Cmd(json=True),
        "start_info_json": Cmd("CmdStartInfo"),
        "gui_status_json": Cmd(json=True),
        "power_log_json": Cmd(json=True, param="power_log_json"),
        "sensor_log_json": Cmd("CmdSensorLog"),
        "sensor_names_json": Cmd(json=True),
        "get_maint_log_json": Cmd(json=True),
        "support_data_json": Cmd(json=True),
        "getbase": Cmd(),
        "getsitename": Cmd(),
        "getdebug": Cmd(),
        # passed to genmon, changing something
        "setexercise": Cmd(write=True, post=True, param="setexercise"),
        "setquiet": Cmd(write=True, post=True, param="setquiet"),
        "setremote": Cmd(write=True, post=True, param="setremote"),
        "settime": Cmd(write=True, post=True),
        "set_button_command": Cmd(write=True, post=True, param="set_button_command", maxlen=512),
        "add_maint_log": Cmd(write=True, post=True, param="add_maint_log", maxlen=2048),
        "edit_row_maint_log": Cmd(write=True, post=True, param="edit_row_maint_log", maxlen=2048),
        "delete_row_maint_log": Cmd(write=True, post=True, param="delete_row_maint_log", maxlen=512),
        "clear_maint_log": Cmd(write=True, post=True),
        "clear_aux_alarm_log": Cmd(write=True, post=True),
        "power_log_clear": Cmd(write=True, post=True),
        "fuel_log_clear": Cmd(write=True, post=True),
        "sensor_log_clear": Cmd(write=True, post=True),
        # send a notification, the value is the JSON message genmon expects
        "notify_message": Cmd(write=True, post=True, param="notify_message", maxlen=2048),
        # email the registers / logs to the developer; allowed for read only users
        "sendregisters": Cmd(post=True),
        "sendlogfiles": Cmd(post=True),
        # answered by genserv
        "csrf_token": Cmd("CmdCSRFToken"),
        "getfavicon": Cmd("CmdFavicon"),
        "getreglabels": Cmd("CmdRegisterLabels"),
        "settings": Cmd("CmdSettings", write=True),
        "setsettings": Cmd("CmdSetSettings", write=True, post=True),
        "get_advanced_settings": Cmd("CmdAdvancedSettings", write=True),
        "set_advanced_settings": Cmd("CmdSetAdvancedSettings", write=True, post=True),
        "get_add_on_settings": Cmd("CmdAddOnSettings", write=True),
        "set_add_on_settings": Cmd("CmdSetAddOnSettings", write=True, post=True),
        "notifications": Cmd("CmdNotifications", write=True),
        "setnotifications": Cmd("CmdSetNotifications", write=True, post=True),
        "get_ui_prefs": Cmd("CmdUIPrefs"),
        "set_ui_prefs": Cmd("CmdSetUIPrefs", write=True, post=True),
        "test_email": Cmd("CmdTestEmail", write=True, post=True),
        "backup": Cmd("CmdBackup", write=True, post=True),
        "get_logs": Cmd("CmdGetLogs", write=True, post=True),
        "updatesoftware": Cmd("CmdUpdateSoftware", write=True, post=True),
        "restart": Cmd("CmdRestart", write=True, post=True),
        "stop": Cmd("CmdStop", write=True, post=True),
        "shutdown": Cmd("CmdShutdown", write=True, post=True),
        "reboot": Cmd("CmdReboot", write=True, post=True),
    }

    # /cmd/ commands only accepted as POST (with the X-CSRFToken header, see
    # csrf_check); a GET returns 405.
    POST_ONLY_COMMANDS = frozenset(name for name, cmd in COMMANDS.items() if cmd.post)

    # Extensions treated as long-lived static assets that browsers may cache.
    STATIC_ASSET_EXTENSIONS = (
        "css", "js", "png", "jpg", "jpeg", "gif", "svg", "ico",
        "woff", "woff2", "ttf", "webmanifest",
    )

    # Seconds a new HTTPS connection gets to finish its TLS handshake.
    TLSHandshakeTimeout = 30

    MAIL_SECTION = "MyMail"
    GENMON_SECTION = "GenMon"

    # config files used by genserv, attribute name : file name
    CONFIG_FILE_NAMES = collections.OrderedDict([
        ("GENMON_CONFIG", "genmon.conf"),
        ("MAIL_CONFIG", "mymail.conf"),
        ("GENLOADER_CONFIG", "genloader.conf"),
        ("GENSMS_CONFIG", "gensms.conf"),
        ("MYMODEM_CONFIG", "mymodem.conf"),
        ("GENPUSHOVER_CONFIG", "genpushover.conf"),
        ("GENMQTT_CONFIG", "genmqtt.conf"),
        ("GENMQTTIN_CONFIG", "genmqttin.conf"),
        ("GENSLACK_CONFIG", "genslack.conf"),
        ("GENCALLMEBOT_CONFIG", "gencallmebot.conf"),
        ("GENGPIOIN_CONFIG", "gengpioin.conf"),
        ("GENGPIOLEDBLINK_CONFIG", "gengpioledblink.conf"),
        ("GENEXERCISE_CONFIG", "genexercise.conf"),
        ("GENEMAIL2SMS_CONFIG", "genemail2sms.conf"),
        ("GENTANKUTIL_CONFIG", "gentankutil.conf"),
        ("GENNEEVO_CONFIG", "genneevo.conf"),
        ("GENCENTRICONNECT_CONFIG", "gencentriconnect.conf"),
        ("GENTANKDIY_CONFIG", "gentankdiy.conf"),
        ("GENALEXA_CONFIG", "genalexa.conf"),
        ("GENSNMP_CONFIG", "gensnmp.conf"),
        ("GENTEMP_CONFIG", "gentemp.conf"),
        ("GENCTHAT_CONFIG", "gencthat.conf"),
        ("GENMOPEKA_CONFIG", "genmopeka.conf"),
        ("GENOTODATA_CONFIG", "genotodata.conf"),
        ("GENSMS_VOIP_CONFIG", "gensms_voip.conf"),
        ("GENHOMEASSISTANT_CONFIG", "genhomeassistant.conf"),
        ("GENHALINK_CONFIG", "genhalink.conf"),
        ("GENHUBITAT_CONFIG", "genhubitat.conf"),
    ])

    # ------------ GenServ::init-------------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=ProgramDefaults.ConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):

        super(GenServ, self).__init__()

        self.log = log
        self.console = console
        self.loglocation = loglocation
        self.ConfigFilePath = ConfigFilePath
        self.MonitorAddress = host
        self.clientport = port
        self.debug = False

        # authentication / LDAP
        self.HTTPAuthUser = None
        self.HTTPAuthPass = None
        self.HTTPAuthUser_RO = None
        self.HTTPAuthPass_RO = None
        self.LdapServer = None
        self.LdapBase = None
        self.DomainNetbios = None
        self.LdapAdminGroup = None
        self.LdapReadOnlyGroup = None

        # MFA
        self.mail = None
        self.bUseMFA = False
        self.bMfaEnrolled = False
        self.SecretMFAKey = None
        self.MFA_URL = None
        self.RememberMeDays = 0
        self.MfaTrustDays = 90
        self.bMfaTrustExtend = False
        self.LastOTPSendTime = None
        self.PASSKEYS_PATH = None

        # HTTP / HTTPS
        self.bUseSecureHTTP = False
        self.CertMode = "selfsigned"  # selfsigned | localca | custom
        # When True, allow the web UI to be embedded in an iframe from any site
        self.bAllowIframe = False
        self.SSLContext = None
        self.HTTPPort = 8000
        self.OldHTTPPort = None
        self.ListenIPAddress = "0.0.0.0"
        self.RedirectServer = None
        self.favicon = "favicon.ico"
        self.AppPath = ""

        # login lockout
        self.WebUILocked = False
        self.LoginAttempts = 0
        self.MaxLoginAttempts = 5
        self.LockOutDuration = 5 * 60
        self.LastLoginTime = datetime.datetime.now()
        self.LastFailedLoginTime = datetime.datetime.now()
        self.securityMessageSent = None

        self.wait_for_init_seconds = 15  # wait for genmon this amount of seconds
        self.Closing = False
        self.Restarting = False
        self.ControllerType = "generac_evo_nexus"
        self.CachedToolTips = {}
        self.CachedRegisterDescriptions = {}
        self.MyClientInterface = None
        self.GStartInfo = {}
        self.OperatingSystem = "unknown"

        signal.signal(signal.SIGTERM, self.SignalClose)
        signal.signal(signal.SIGINT, self.SignalClose)

        # full path of each config file, e.g. self.GENMON_CONFIG
        ConfigFileList = []
        for attr, filename in self.CONFIG_FILE_NAMES.items():
            setattr(self, attr, os.path.join(self.ConfigFilePath, filename))
            ConfigFileList.append(getattr(self, attr))

        for ConfigFile in ConfigFileList:
            if not os.path.isfile(ConfigFile):
                self.LogConsole("Missing config file : " + ConfigFile)
                sys.exit(1)

        self.ConfigFiles = {}
        for ConfigFile in ConfigFileList:
            if self.log == None:
                configlog = self.console
            else:
                configlog = self.log
            self.ConfigFiles[ConfigFile] = MyConfig(filename=ConfigFile, log=configlog)

        self.AppPath = sys.argv[0]
        if not self.LoadConfig():
            self.LogConsole("Error reading configuration file.")
            self.LogDebug("Error reading configuration file.")
            sys.exit(1)

        for ConfigFile in ConfigFileList:
            self.ConfigFiles[ConfigFile].log = self.log

        if MyPlatform.IsOSLinux():
            self.OperatingSystem = "linux"
        elif MyPlatform.IsOSWindows():
            self.OperatingSystem = "windows"
        else:
            self.OperatingSystem = "unknown"
            import platform
            self.LogError("Operating System: " + str(platform.system()))

        self.LogError(
            "Starting "
            + self.AppPath
            + ", Port:"
            + str(self.HTTPPort)
            + ", Secure HTTP: "
            + str(self.bUseSecureHTTP)
            + ", CertMode: "
            + str(self.CertMode)
            + ", UseMFA:"
            + str(self.bUseMFA)
            + ", OS:"
            + str(self.OperatingSystem)
            + ", Config:"
            + str(self.ConfigFilePath)
        )
        # validate needed files are present
        for required_file in ["startgenmon.sh", "genmonmaint.sh"]:
            filename = os.path.join(
                os.path.dirname(os.path.realpath(__file__)), required_file
            )
            if not os.path.isfile(filename):
                self.LogError("Required file missing : " + required_file)
                sys.exit(1)

        self.MyClientInterface = ClientInterface(
            host=self.MonitorAddress, port=self.clientport, log=self.log
        )

        # This waits for genmon to init the serial port etc
        if not self.MyClientInterface.WaitForReady(timeout=self.wait_for_init_seconds):
            self.LogError(f" Timeout waiting for genmon to become ready")

        # This waits for comms (serial, TCP, etc) to read the generator data
        Start = datetime.datetime.now()
        init_ok = False
        data = ""
        while (datetime.datetime.now() - Start).total_seconds() < self.wait_for_init_seconds:
            data = self.MyClientInterface.ProcessMonitorCommand("generator: gethealth")
            if "OK" in data:
                init_ok = True
                self.LogConsole(f" OK - Init complete: {data}")
                self.LogDebug(f" OK - Init complete: {data}")
                break
        if init_ok == False:
            self.LogError(f"Warning: genmon init not complete after {self.wait_for_init_seconds} seconds: {data}")

        # Now get the base info about the controller and genmon settings
        try:
            data = self.MyClientInterface.ProcessMonitorCommand("generator: start_info_json")
            self.GStartInfo = json.loads(data)
        except Exception as e1:
            self.LogError("Error getting start info : " + str(e1))
            self.LogError("Data returned from start_info_json: " + data)
            sys.exit(1)

        self.CacheToolTips()

        self.RegisterRoutes()

    # ------------ GenServ::RegisterRoutes---------------------------------------
    # Flask routes and request hooks implemented as GenServ methods. The endpoint
    # names match the method names so url_for() and the endpoint checks in
    # csrf_check are unchanged.
    def RegisterRoutes(self):

        app.before_request(self.csrf_check)
        app.after_request(self.add_header)
        app.context_processor(self.inject_asset_helpers)
        app.add_url_rule('/', endpoint="root", view_func=self.root, methods=['GET'])
        app.add_url_rule('/locked', endpoint="locked", view_func=self.locked, methods=['GET'])
        app.add_url_rule('/upload', endpoint="upload", view_func=self.upload, methods=['POST'])
        app.add_url_rule('/download/ca.crt', endpoint="download_ca_der", view_func=self.download_ca_der)
        app.add_url_rule('/import/ca.crt', endpoint="import_ca_inline", view_func=self.import_ca_inline)
        app.add_url_rule('/download/ca.pem', endpoint="download_ca_pem", view_func=self.download_ca_pem)
        app.add_url_rule('/cmd/<command>', endpoint="command", view_func=self.command, methods=['GET', 'POST'])
        # login, MFA, backup codes and passkeys
        app.add_url_rule('/logout', endpoint="logout", view_func=self.logout)
        app.add_url_rule('/', endpoint="do_admin_login", view_func=self.do_admin_login, methods=['POST'])
        app.add_url_rule('/mfa', endpoint="mfa_auth", view_func=self.mfa_auth, methods=['POST'])
        app.add_url_rule('/mfa/verify_setup', endpoint="mfa_verify_setup", view_func=self.mfa_verify_setup, methods=['POST'])
        app.add_url_rule('/send_otp', endpoint="send_otp", view_func=self.send_otp, methods=['POST'])
        app.add_url_rule('/backup_codes/generate', endpoint="generate_backup_codes", view_func=self.generate_backup_codes, methods=['POST'])
        app.add_url_rule('/backup_codes/count', endpoint="backup_codes_count", view_func=self.backup_codes_count, methods=['GET'])
        app.add_url_rule('/passkey/register/begin', endpoint="passkey_register_begin", view_func=self.passkey_register_begin, methods=['POST'])
        app.add_url_rule('/passkey/register/complete', endpoint="passkey_register_complete", view_func=self.passkey_register_complete, methods=['POST'])
        app.add_url_rule('/passkey/auth/begin', endpoint="passkey_auth_begin", view_func=self.passkey_auth_begin, methods=['POST'])
        app.add_url_rule('/passkey/auth/complete', endpoint="passkey_auth_complete", view_func=self.passkey_auth_complete, methods=['POST'])
        app.add_url_rule('/passkey/list', endpoint="passkey_list", view_func=self.passkey_list, methods=['GET'])
        app.add_url_rule('/passkey/delete', endpoint="passkey_delete", view_func=self.passkey_delete, methods=['POST'])
        app.add_url_rule('/passkey/login/begin', endpoint="passkey_login_begin", view_func=self.passkey_login_begin, methods=['POST'])
        app.add_url_rule('/passkey/login/complete', endpoint="passkey_login_complete", view_func=self.passkey_login_complete, methods=['POST'])

    # ------------ GenServ::Run--------------------------------------------------
    # start the web server, does not return until the server stops
    def Run(self):

        if self.bUseSecureHTTP and self.OldHTTPPort is not None and self.OldHTTPPort != self.HTTPPort:
            t = threading.Thread(target=self.StartHTTPRedirectServer, daemon=True)
            t.start()

        WebSSLContext = self.SSLContext
        WebRequestHandler = None
        if self.SSLContext is not None:
            WebSSLContext, deferred = self.DeferTLSHandshake(self.SSLContext)
            if deferred:
                WebRequestHandler = self.MakeTLSHandshakeRequestHandler()

        try:
            app.run(
                host=self.ListenIPAddress,
                port=self.HTTPPort,
                threaded=True,
                ssl_context=WebSSLContext,
                request_handler=WebRequestHandler,
                use_reloader=False,
                debug=False,
            )

        except Exception as e1:
            self.LogErrorLine("Error in app.run: " + str(e1))
            # Errno 98
            if getattr(e1, "errno", None) != errno.EADDRINUSE:  # and e1.errno != errno.EIO:
                sys.exit(1)
            # retry once
            try:
                self.LogError("Retrying app.run()")
                time.sleep(2)
                app.run(
                    host=self.ListenIPAddress,
                    port=self.HTTPPort,
                    threaded=True,
                    ssl_context=WebSSLContext,
                    request_handler=WebRequestHandler,
                    use_reloader=False,
                    debug=False,
                )
            except Exception as e2:
                self.LogErrorLine("Error in app.run (2): " + str(e2))
            sys.exit(0)

    # ------------ GenServ::ServePage--------------------------------------------
    # serve a page from the static folder, showing the login page first if a
    # login is required. Used by genservext.py extensions through the module
    # level ServePage function.
    def ServePage(self, page_file):

        if self.LoginActive() and not session.get("logged_in"):
            return self._render_login()
        return app.send_static_file(page_file)

    # -------------------------------------------------------------------------------
    def StartHTTPRedirectServer(self):
        """Start a lightweight HTTP server on OldHTTPPort that 301-redirects
        every request to the HTTPS port.  Runs in a daemon thread so it dies
        with the main process."""
        import http.server
        import socketserver

        redirect_port = self.OldHTTPPort
        target_port = self.HTTPPort  # already set to HTTPSPort at this point

        class RedirectHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                host = self.headers.get("Host", "localhost").split(":")[0]
                if target_port == 443:
                    location = "https://" + host + self.path
                else:
                    location = "https://" + host + ":" + str(target_port) + self.path
                # Serve an HTML page with JS redirect instead of a raw 302.
                # Chrome aggressively caches 301/302 redirects for IP addresses,
                # making it impossible to reach the HTTP site after HTTPS is disabled.
                # An HTML page is not cached as a redirect by the browser.
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                page = (
                    "<!DOCTYPE html><html><head>"
                    '<meta http-equiv="refresh" content="1;url={loc}">'
                    "</head><body>"
                    '<p>Redirecting to <a href="{loc}">{loc}</a>&hellip;</p>'
                    "<script>location.replace('{loc}');</script>"
                    "</body></html>"
                ).format(loc=location)
                self.wfile.write(page.encode("utf-8"))

            do_POST = do_GET
            do_PUT = do_GET
            do_DELETE = do_GET
            do_HEAD = do_GET

            def log_message(self, format, *args):
                pass  # suppress request logs

        # A thread per connection and a timeout, so a client that connects and sends
        # nothing can't stop the redirect from answering everyone else.
        RedirectHandler.timeout = 30

        class ThreadedRedirectServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
            daemon_threads = True

        try:
            socketserver.TCPServer.allow_reuse_address = True
            self.RedirectServer = ThreadedRedirectServer(
                (self.ListenIPAddress, redirect_port), RedirectHandler
            )
            self.LogDebug(
                "HTTP->HTTPS redirect active on port "
                + str(redirect_port)
                + " -> "
                + str(target_port)
            )
            self.RedirectServer.serve_forever()
        except Exception as e1:
            self.LogErrorLine(
                "Unable to start HTTP redirect server on port "
                + str(redirect_port)
                + ": "
                + str(e1)
            )

    def DeferTLSHandshake(self, ssl_context):
        """Returns (context, deferred): an SSL context that leaves the TLS handshake
        of each connection to the thread that handles it (see
        MakeTLSHandshakeRequestHandler), and whether that worked.

        The Flask / werkzeug server otherwise does the handshake in the single
        thread that accepts connections, with no timeout, so one client that
        connects and never finishes the handshake (a device that dropped off the
        network mid-connect, a port scanner) stops genserv from accepting any other
        connection until that client goes away, which may be never. tests/test_web_stall.py
        reproduces it. On any error the context is returned unchanged."""
        try:
            import ssl

            from werkzeug.serving import generate_adhoc_ssl_context as _wz_adhoc
            from werkzeug.serving import load_ssl_context

            context = ssl_context
            if isinstance(context, tuple):
                context = load_ssl_context(*context)
            elif context == "adhoc":
                context = _wz_adhoc()
            if not isinstance(context, ssl.SSLContext):
                return ssl_context, False

            wrap_socket = context.wrap_socket

            # werkzeug wraps the listening socket with this, and accept() wraps each
            # new connection with it too, passing on do_handshake_on_connect.
            def deferred_wrap_socket(sock, *args, **kwargs):
                kwargs["do_handshake_on_connect"] = False
                return wrap_socket(sock, *args, **kwargs)

            context.wrap_socket = deferred_wrap_socket
            return context, True
        except Exception as e1:
            self.LogErrorLine("Error in DeferTLSHandshake: " + str(e1))
            return ssl_context, False

    # -------------------------------------------------------------------------------
    def MakeTLSHandshakeRequestHandler(self):
        """werkzeug's request handler, doing the TLS handshake deferred by
        DeferTLSHandshake first, in this connection's own thread and with a timeout."""
        import socket
        import ssl

        from werkzeug.serving import WSGIRequestHandler

        # handle() below has its own self (the request handler)
        genserv = self

        class TLSHandshakeRequestHandler(WSGIRequestHandler):
            def handle(self):
                if isinstance(self.connection, ssl.SSLSocket):
                    previous_timeout = self.connection.gettimeout()
                    try:
                        self.connection.settimeout(genserv.TLSHandshakeTimeout)
                        self.connection.do_handshake()
                        self.connection.settimeout(previous_timeout)
                    except socket.timeout:
                        genserv.LogError(
                            "TLS handshake from "
                            + str(self.client_address[0])
                            + " did not finish within "
                            + str(genserv.TLSHandshakeTimeout)
                            + " seconds, connection dropped"
                        )
                        return
                    except Exception as e1:
                        genserv.LogDebug(
                            "TLS handshake from "
                            + str(self.client_address[0])
                            + " failed: "
                            + str(e1)
                        )
                        return
                WSGIRequestHandler.handle(self)

        return TLSHandshakeRequestHandler

    # -------------------------------------------------------------------------------
    # return False if File not present
    def CheckCertFiles(self, CertFile, KeyFile):

        try:
            if not os.path.isfile(CertFile):
                self.LogConsole("Missing cert file : " + CertFile)
                self.LogError("Missing cert file : " + CertFile)
                return False
            if not os.path.isfile(KeyFile):
                self.LogConsole("Missing key file : " + KeyFile)
                self.LogError("Missing key file : " + KeyFile)
                return False
        except Exception as e1:
            self.LogErrorLine(
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
    def generate_local_ca(self, config_path):
        """Generate (or load existing) a local CA key + self-signed CA certificate.

        Files: {config_path}/ca.key, {config_path}/ca.crt
        Returns (ca_cert, ca_key) as cryptography x509.Certificate / RSAPrivateKey.

        Uses the modern ``cryptography`` library directly because pyOpenSSL 25+
        removed ``X509.add_extensions()`` / ``X509Extension``.
        """
        import datetime as _dt
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        ca_key_path = os.path.join(config_path, "ca.key")
        ca_crt_path = os.path.join(config_path, "ca.crt")

        if os.path.isfile(ca_key_path) and os.path.isfile(ca_crt_path):
            with open(ca_key_path, "rb") as f:
                ca_key = serialization.load_pem_private_key(f.read(), password=None)
            with open(ca_crt_path, "rb") as f:
                ca_cert = x509.load_pem_x509_certificate(f.read())
            self.LogDebug("Local CA loaded from " + ca_crt_path)
            return ca_cert, ca_key

        # Generate new CA
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "Genmon Local CA"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Genmon"),
        ])

        # Use naive UTC for not_valid_before/after: cryptography <42 requires it;
        # >=42 accepts it with a DeprecationWarning (still not an error as of 48).
        now = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(ca_key.public_key())
            .serial_number(int.from_bytes(os.urandom(16), "big"))
            .not_valid_before(now - _dt.timedelta(minutes=5))
            .not_valid_after(now + _dt.timedelta(days=10 * 365))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=0), critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=False,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
                critical=False,
            )
            .sign(private_key=ca_key, algorithm=hashes.SHA256())
        )

        with open(ca_key_path, "wb") as f:
            f.write(
                ca_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
        os.chmod(ca_key_path, 0o600)
        with open(ca_crt_path, "wb") as f:
            f.write(ca_cert.public_bytes(serialization.Encoding.PEM))

        self.LogDebug("Local CA created: " + ca_crt_path)
        return ca_cert, ca_key

    # -------------------------------------------------------------------------------
    def _get_all_local_ips(self):
        """Return a set of all non-loopback IPv4 addresses on this machine.

        Tries multiple discovery methods so the server certificate SAN covers
        every address a browser might use to connect, even when the Pi has no
        internet access at startup.
        """
        import socket
        import subprocess

        ips = set()

        # Method 1: hostname -I  (Linux, most reliable on Raspberry Pi)
        try:
            out = subprocess.check_output(["hostname", "-I"], timeout=5,
                                          stderr=subprocess.DEVNULL).decode()
            for token in out.split():
                if ":" not in token:          # skip IPv6
                    ips.add(token.strip())
        except Exception:
            pass

        # Method 2: getaddrinfo on the local hostname
        try:
            hn = socket.gethostname()
            for info in socket.getaddrinfo(hn, None):
                addr = info[4][0]
                if addr and not addr.startswith("127.") and ":" not in addr:
                    ips.add(addr)
        except Exception:
            pass

        # Method 3: UDP connect trick (finds default-route LAN IP)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
            s.close()
        except Exception:
            pass

        ips.discard("127.0.0.1")
        return ips

    # -------------------------------------------------------------------------------
    def generate_server_cert(self, ca_cert, ca_key, config_path):
        """Generate (or reuse) a server certificate signed by the local CA.

        Files: {config_path}/server.key, {config_path}/server.crt
        Auto-regenerates if missing or expiring within 30 days.
        Returns (server_crt_path, server_key_path) file paths.

        Uses the modern ``cryptography`` library directly (pyOpenSSL 25+ removed
        ``X509.add_extensions`` / ``X509Extension`` / ``get_extension``).
        """
        import datetime as _dt
        import ipaddress as _ipaddr
        import socket

        from cryptography import x509
        from cryptography.x509.oid import NameOID, ExtensionOID, ExtendedKeyUsageOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        srv_key_path = os.path.join(config_path, "server.key")
        srv_crt_path = os.path.join(config_path, "server.crt")

        regen = False
        if not os.path.isfile(srv_key_path) or not os.path.isfile(srv_crt_path):
            regen = True
        else:
            # Check expiry and required extensions
            try:
                with open(srv_crt_path, "rb") as f:
                    existing = x509.load_pem_x509_certificate(f.read())
                try:
                    expiry = existing.not_valid_after_utc
                    now_utc = _dt.datetime.now(_dt.timezone.utc)
                except AttributeError:
                    # cryptography < 42 fallback
                    expiry = existing.not_valid_after.replace(tzinfo=_dt.timezone.utc)
                    now_utc = _dt.datetime.now(_dt.timezone.utc)
                if expiry - now_utc < _dt.timedelta(days=30):
                    self.LogDebug("Server cert expiring soon, regenerating.")
                    regen = True
                # Check for required extensions
                has_eku = False
                has_san = False
                existing_san_names = set()
                try:
                    existing.extensions.get_extension_for_oid(
                        ExtensionOID.EXTENDED_KEY_USAGE
                    )
                    has_eku = True
                except x509.ExtensionNotFound:
                    pass
                try:
                    san = existing.extensions.get_extension_for_oid(
                        ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                    ).value
                    has_san = True
                    for n in san.get_values_for_type(x509.DNSName):
                        existing_san_names.add(n)
                    for ip in san.get_values_for_type(x509.IPAddress):
                        existing_san_names.add(str(ip))
                except x509.ExtensionNotFound:
                    pass
                if not has_eku:
                    self.LogDebug("Server cert missing extendedKeyUsage, regenerating.")
                    regen = True
                elif not has_san:
                    self.LogDebug("Server cert missing subjectAltName, regenerating.")
                    regen = True
                else:
                    # Log any IPs not covered by the SAN but do NOT
                    # regenerate — that would invalidate every browser
                    # that already trusts the current cert and leave the
                    # user stuck on a spinner after a settings-save restart.
                    local_ips = self._get_all_local_ips()
                    missing = [a for a in local_ips if a not in existing_san_names]
                    if missing:
                        self.LogDebug(
                            "Note: IP(s) " + ", ".join(sorted(missing))
                            + " not in server cert SAN.  Cert kept to preserve"
                            + " browser trust.  Re-enable HTTPS in settings to"
                            + " force a new certificate."
                        )
            except Exception:
                regen = True

        if not regen:
            self.LogDebug("Server cert reused: " + srv_crt_path)
            return srv_crt_path, srv_key_path

        # Build SAN list
        san_dns = set()
        san_ip = set()
        san_dns.add("localhost")
        try:
            hn = socket.gethostname()
            if hn:
                san_dns.add(hn)
                san_dns.add(hn + ".local")   # mDNS / Avahi
            try:
                fqdn = socket.getfqdn()
                if fqdn and fqdn != hn:
                    san_dns.add(fqdn)
            except Exception:
                pass
        except Exception:
            pass
        for addr in self._get_all_local_ips():
            san_ip.add(addr)
        san_ip.add("127.0.0.1")

        san_objects = [x509.DNSName(n) for n in sorted(san_dns)]
        for addr in sorted(san_ip):
            try:
                san_objects.append(x509.IPAddress(_ipaddr.ip_address(addr)))
            except ValueError:
                continue
        san_string = ", ".join(
            sorted(["DNS:" + n for n in san_dns] + ["IP:" + a for a in san_ip])
        )

        srv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        cn = socket.gethostname() or "genmon"
        subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Genmon"),
        ])

        # Use naive UTC for not_valid_before/after: cryptography <42 requires it;
        # >=42 accepts it with a DeprecationWarning (still not an error as of 48).
        now = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert.subject)
            .public_key(srv_key.public_key())
            .serial_number(int.from_bytes(os.urandom(16), "big"))
            .not_valid_before(now - _dt.timedelta(minutes=5))
            .not_valid_after(now + _dt.timedelta(days=365))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None), critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=True,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                critical=False,
            )
            .add_extension(
                x509.SubjectAlternativeName(san_objects), critical=False,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
                critical=False,
            )
        )

        srv_cert = builder.sign(private_key=ca_key, algorithm=hashes.SHA256())

        with open(srv_key_path, "wb") as f:
            f.write(
                srv_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
        os.chmod(srv_key_path, 0o600)
        with open(srv_crt_path, "wb") as f:
            f.write(srv_cert.public_bytes(serialization.Encoding.PEM))

        self.LogDebug("Server cert generated: " + srv_crt_path + " SAN=" + san_string)
        return srv_crt_path, srv_key_path

    # -------------------------------------------------------------------------------
    def _get_cert_info(self):
        """Return a JSON string with certificate status info for the UI."""
        import json as _json

        info = {"mode": self.CertMode}

        def _load_cert(path):
            from cryptography import x509
            with open(path, "rb") as f:
                return x509.load_pem_x509_certificate(f.read())

        def _cn(cert):
            from cryptography.x509.oid import NameOID
            try:
                attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
                return attrs[0].value if attrs else ""
            except Exception:
                return ""

        def _date(dt):
            return dt.strftime("%Y-%m-%d") if dt is not None else ""

        def _not_before(cert):
            try:
                return cert.not_valid_before_utc
            except AttributeError:
                return cert.not_valid_before

        def _not_after(cert):
            try:
                return cert.not_valid_after_utc
            except AttributeError:
                return cert.not_valid_after

        def _san_string(cert):
            from cryptography import x509
            from cryptography.x509.oid import ExtensionOID
            try:
                san = cert.extensions.get_extension_for_oid(
                    ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                ).value
            except x509.ExtensionNotFound:
                return ""
            parts = []
            for n in san.get_values_for_type(x509.DNSName):
                parts.append("DNS:" + n)
            for ip in san.get_values_for_type(x509.IPAddress):
                parts.append("IP:" + str(ip))
            return ", ".join(sorted(parts))

        try:
            if self.CertMode == "selfsigned":
                info["detail"] = "Ephemeral \u2014 regenerated on each restart"
            elif self.CertMode == "localca":
                ca_path = os.path.join(self.ConfigFilePath, "ca.crt")
                srv_path = os.path.join(self.ConfigFilePath, "server.crt")
                if os.path.isfile(ca_path):
                    ca = _load_cert(ca_path)
                    info["ca_cn"] = _cn(ca)
                    info["ca_created"] = _date(_not_before(ca))
                if os.path.isfile(srv_path):
                    srv = _load_cert(srv_path)
                    info["srv_expiry"] = _date(_not_after(srv))
                    san = _san_string(srv)
                    if san:
                        info["san"] = san
            elif self.CertMode == "custom":
                cert_file = self.ConfigFiles[self.GENMON_CONFIG].ReadValue("certfile") if self.GENMON_CONFIG in self.ConfigFiles else ""
                key_file = self.ConfigFiles[self.GENMON_CONFIG].ReadValue("keyfile") if self.GENMON_CONFIG in self.ConfigFiles else ""
                info["certfile"] = cert_file or ""
                info["keyfile"] = key_file or ""
                if cert_file and os.path.isfile(cert_file):
                    c = _load_cert(cert_file)
                    info["expiry"] = _date(_not_after(c))
        except Exception as e1:
            info["error"] = str(e1)
        return _json.dumps(info)

    # -------------------------------------------------------------------------------
    def generate_adhoc_ssl_context(self):
        # Generates an adhoc SSL context for the web server.
        try:
            import ssl

            try:
                from werkzeug.serving import generate_adhoc_ssl_context as _wz_ctx
                return _wz_ctx()
            except Exception as e1:
                self.LogErrorLine("generate_adhoc_ssl_context: " + str(e1))

            # Fallback: try pyOpenSSL-based generation
            import atexit
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
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.load_cert_chain(cert_file, pkey_file)
            return ctx
        except Exception as e1:
            self.LogError("Error in generate_adhoc_ssl_context: " + str(e1))
            return None

    # -------------------------------------------------------------------------------
    def generate_persistent_selfsigned(self, config_path):
        """Generate (or load existing) a persistent self-signed certificate.

        Files: {config_path}/selfsigned.key, {config_path}/selfsigned.crt
        Returns an ssl.SSLContext, or None on failure.
        """
        import ssl

        from OpenSSL import crypto

        key_path = os.path.join(config_path, "selfsigned.key")
        crt_path = os.path.join(config_path, "selfsigned.crt")

        need_generate = False
        if os.path.isfile(key_path) and os.path.isfile(crt_path):
            try:
                with open(crt_path, "rb") as f:
                    cert = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
                if cert.has_expired():
                    self.LogError("Self-signed certificate expired, regenerating.")
                    need_generate = True
                else:
                    self.LogDebug("Persistent self-signed cert loaded from " + crt_path)
            except Exception as e1:
                self.LogErrorLine("Error loading self-signed cert, regenerating: " + str(e1))
                need_generate = True
        else:
            need_generate = True

        if need_generate:
            try:
                pkey = crypto.PKey()
                pkey.generate_key(crypto.TYPE_RSA, 2048)

                cert = crypto.X509()
                cert.set_serial_number(int.from_bytes(os.urandom(16), "big"))
                cert.gmtime_adj_notBefore(0)
                cert.gmtime_adj_notAfter(60 * 60 * 24 * 365)  # 1 year

                subject = cert.get_subject()
                subject.CN = "*"
                subject.O = "Genmon Self-Signed"

                cert.set_issuer(subject)
                cert.set_pubkey(pkey)
                cert.sign(pkey, "sha256")

                with open(key_path, "wb") as f:
                    f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, pkey))
                os.chmod(key_path, 0o600)
                with open(crt_path, "wb") as f:
                    f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))

                self.LogDebug("Persistent self-signed cert created: " + crt_path)
            except Exception as e1:
                self.LogError("Error generating persistent self-signed cert: " + str(e1))
                return None

        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.load_cert_chain(crt_path, key_path)
            return ctx
        except Exception as e1:
            self.LogError("Error loading persistent self-signed cert into SSLContext: " + str(e1))
            return None

    # -------------------------------------------------------------------------------
    def LoadConfig(self):

        self.HTTPAuthPass = None
        self.HTTPAuthUser = None
        self.SSLContext = None
        self.LdapServer = None
        self.LdapBase = None
        self.DomainNetbios = None
        self.LdapAdminGroup = None
        self.LdapReadOnlyGroup = None

        try:

            self.debug = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                "debug", return_type=bool, default=False
            )
            # heartbeat server port, must match value in check_generator_system.py and any calling client apps
            if self.ConfigFiles[self.GENMON_CONFIG].HasOption("server_port"):
                self.clientport = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                    "server_port", return_type=int, default=ProgramDefaults.ServerPort
                )

            self.wait_for_init_seconds = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                    "wait_for_init_seconds", return_type=int, default=15
                    )

            self.bUseMFA = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                "usemfa", return_type=bool, default=False
            )
            self.bMfaEnrolled = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                "mfa_enrolled", return_type=bool, default=False
            )
            # Migration: if MFA was already enabled before the enrolled flag
            # existed, mark it as enrolled so the QR code stays hidden.
            if self.bUseMFA and not self.bMfaEnrolled:
                self.bMfaEnrolled = True
                self.ConfigFiles[self.GENMON_CONFIG].WriteValue("mfa_enrolled", "True")
            # If MFA was disabled, clear enrollment and rotate the secret so
            # re-enabling MFA forces a fresh QR scan.
            if not self.bUseMFA and self.bMfaEnrolled:
                self.bMfaEnrolled = False
                self.ConfigFiles[self.GENMON_CONFIG].WriteValue("mfa_enrolled", "False")
                self.SecretMFAKey = str(pyotp.random_base32())
                self.ConfigFiles[self.GENMON_CONFIG].WriteValue("secretmfa", str(self.SecretMFAKey))
            # Always read/generate the secret key and build the provisioning
            # URL so the QR code is ready to display in settings even before
            # the user enables MFA.
            if self.SecretMFAKey is None:
                self.SecretMFAKey = self.ConfigFiles[self.GENMON_CONFIG].ReadValue("secretmfa", default=None)

            if self.SecretMFAKey == None or self.SecretMFAKey == "":
                self.SecretMFAKey = str(pyotp.random_base32())
                self.ConfigFiles[self.GENMON_CONFIG].WriteValue("secretmfa", str(self.SecretMFAKey))

            self.SetupMFA()

            if self.ConfigFiles[self.GENMON_CONFIG].HasOption("usehttps"):
                self.bUseSecureHTTP = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                    "usehttps", return_type=bool
                )
            if not self.bUseSecureHTTP:
                # dont use MFA unless HTTPS is enabled
                self.bUseMFA = False

            # Allow iframe embedding from any origin. Default False keeps framing
            # blocked (X-Frame-Options DENY + CSP frame-ancestors 'none').
            self.bAllowIframe = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                "allow_iframe", return_type=bool, default=False
            )

            self.ListenIPAddress = self.ConfigFiles[self.GENMON_CONFIG].ReadValue("flask_listen_ip_address", default="0.0.0.0")

            if self.ConfigFiles[self.GENMON_CONFIG].HasOption("http_port"):
                self.HTTPPort = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                    "http_port", return_type=int, default=8000
                )

            if self.ConfigFiles[self.GENMON_CONFIG].HasOption("favicon"):
                self.favicon = self.ConfigFiles[self.GENMON_CONFIG].ReadValue("favicon")

            self.MaxLoginAttempts = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                "max_login_attempts", return_type=int, default=5
            )
            self.LockOutDuration = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                "login_lockout_seconds", return_type=int, default=(5 * 60)
            )

            # user name and password require usehttps = True
            if self.bUseSecureHTTP:
                if self.ConfigFiles[self.GENMON_CONFIG].HasOption("ldap_server"):
                    self.LdapServer = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                        "ldap_server", default=""
                    )
                    self.LdapServer = self.LdapServer.strip()
                    if self.LdapServer == "":
                        self.LdapServer = None
                    else:
                        if self.ConfigFiles[self.GENMON_CONFIG].HasOption("ldap_base"):
                            self.LdapBase = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                                "ldap_base", default=""
                            )
                        if self.ConfigFiles[self.GENMON_CONFIG].HasOption("domain_netbios"):
                            self.DomainNetbios = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                                "domain_netbios", default=""
                            )
                        if self.ConfigFiles[self.GENMON_CONFIG].HasOption("ldap_admingroup"):
                            self.LdapAdminGroup = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                                "ldap_admingroup", default=""
                            )
                        if self.ConfigFiles[self.GENMON_CONFIG].HasOption("ldap_readonlygroup"):
                            self.LdapReadOnlyGroup = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                                "ldap_readonlygroup", default=""
                            )
                        if self.LdapBase == "":
                            self.LdapBase = None
                        if self.DomainNetbios == "":
                            self.DomainNetbios = None
                        if self.LdapAdminGroup == "":
                            self.LdapAdminGroup = None
                        if self.LdapReadOnlyGroup == "":
                            self.LdapReadOnlyGroup = None
                        if (
                            self.LdapReadOnlyGroup == None
                            and self.LdapAdminGroup == None
                            or self.LdapBase == None
                            or self.DomainNetbios == None
                        ):
                            self.LdapServer = None

                if self.ConfigFiles[self.GENMON_CONFIG].HasOption("http_user"):
                    self.HTTPAuthUser = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                        "http_user", default=""
                    )
                    self.HTTPAuthUser = self.HTTPAuthUser.strip()
                    # No user name or pass specified, disable
                    if self.HTTPAuthUser == "":
                        self.HTTPAuthUser = None
                        self.HTTPAuthPass = None
                    elif self.ConfigFiles[self.GENMON_CONFIG].HasOption("http_pass"):
                        self.HTTPAuthPass = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                            "http_pass", default=""
                        )
                        self.HTTPAuthPass = self.HTTPAuthPass.strip()
                    if self.HTTPAuthUser != None and self.HTTPAuthPass != None:
                        if self.ConfigFiles[self.GENMON_CONFIG].HasOption("http_user_ro"):
                            self.HTTPAuthUser_RO = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                                "http_user_ro", default=""
                            )
                            self.HTTPAuthUser_RO = self.HTTPAuthUser_RO.strip()
                            if self.HTTPAuthUser_RO == "":
                                self.HTTPAuthUser_RO = None
                                self.HTTPAuthPass_RO = None
                            elif self.ConfigFiles[self.GENMON_CONFIG].HasOption("http_pass_ro"):
                                self.HTTPAuthPass_RO = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                                    "http_pass_ro", default=""
                                )
                                self.HTTPAuthPass_RO = self.HTTPAuthPass_RO.strip()

                HTTPSPort = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                    "https_port", return_type=int, default=443
                )

            # --- persistent secret key (survives restarts) ---
            # Rotate the key when the auth mode changes (e.g. HTTP→HTTPS)
            # so stale session cookies from a previous mode are invalidated.
            stored_key = self.ConfigFiles[self.GENMON_CONFIG].ReadValue("secret_key", default="")
            current_auth_mode = "auth" if (self.bUseSecureHTTP and self.LoginActive()) else "open"
            stored_auth_mode = self.ConfigFiles[self.GENMON_CONFIG].ReadValue("secret_key_auth_mode", default="")
            if not stored_key or stored_auth_mode != current_auth_mode:
                stored_key = secrets.token_hex(24)
                self.ConfigFiles[self.GENMON_CONFIG].WriteValue("secret_key", stored_key)
                self.ConfigFiles[self.GENMON_CONFIG].WriteValue("secret_key_auth_mode", current_auth_mode)
            app.secret_key = bytes.fromhex(stored_key)

            # --- session cookie hardening ---
            app.config["SESSION_COOKIE_SECURE"] = True  # always set; harmless if not HTTPS
            app.config["SESSION_COOKIE_HTTPONLY"] = True
            app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

            # --- remember-me / session lifetime ---
            # Seed defaults for new settings so existing installs get them in the config
            if not self.ConfigFiles[self.GENMON_CONFIG].HasOption("remember_me_days"):
                self.ConfigFiles[self.GENMON_CONFIG].WriteValue("remember_me_days", "0")
            if not self.ConfigFiles[self.GENMON_CONFIG].HasOption("mfa_trust_extend"):
                self.ConfigFiles[self.GENMON_CONFIG].WriteValue("mfa_trust_extend", "False")
            if not self.ConfigFiles[self.GENMON_CONFIG].HasOption("mfa_trust_days"):
                self.ConfigFiles[self.GENMON_CONFIG].WriteValue("mfa_trust_days", "90")

            self.RememberMeDays = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                "remember_me_days", return_type=int, default=0
            )
            if self.RememberMeDays > 0:
                app.permanent_session_lifetime = datetime.timedelta(days=self.RememberMeDays)

            # --- MFA trust browser ---
            self.MfaTrustDays = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                "mfa_trust_days", return_type=int, default=90
            )
            self.bMfaTrustExtend = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                "mfa_trust_extend", return_type=bool, default=False
            )

            if self.bUseSecureHTTP:
                self.OldHTTPPort = self.HTTPPort
                self.HTTPPort = HTTPSPort
                self.LogDebug("HTTPS enabled: will redirect HTTP port " + str(self.OldHTTPPort) + " -> HTTPS port " + str(self.HTTPPort))

                # --- cert_mode migration (backward compat) ---
                # DEPRECATED: "useselfsignedcert" (bool) was replaced by "cert_mode"
                # (selfsigned | localca | custom) in March 2026.  This block converts
                # the old setting on first run so existing installs upgrade seamlessly.
                # After the first start cert_mode is written to the config and this
                # migration path is never taken again.  The UI now exposes cert_mode
                # only — do NOT remove this block while any user might still have
                # useselfsignedcert in their genmon.conf.
                if not self.ConfigFiles[self.GENMON_CONFIG].HasOption("cert_mode"):
                    if self.ConfigFiles[self.GENMON_CONFIG].HasOption("useselfsignedcert"):
                        old = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                            "useselfsignedcert", return_type=bool
                        )
                        self.CertMode = "selfsigned" if old else "custom"
                    else:
                        self.CertMode = "selfsigned"
                    self.ConfigFiles[self.GENMON_CONFIG].WriteValue("cert_mode", self.CertMode)
                else:
                    self.CertMode = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                        "cert_mode", default="selfsigned"
                    )
                    if self.CertMode not in ("selfsigned", "localca", "custom"):
                        self.CertMode = "selfsigned"

                if self.CertMode == "selfsigned":
                    self.SSLContext = self.generate_persistent_selfsigned(self.ConfigFilePath)
                    if self.SSLContext is None:
                        self.SSLContext = self.generate_adhoc_ssl_context()
                        if self.SSLContext is None:
                            self.SSLContext = "adhoc"
                elif self.CertMode == "localca":
                    try:
                        ca_cert, ca_key = self.generate_local_ca(self.ConfigFilePath)
                        srv_crt, srv_key = self.generate_server_cert(
                            ca_cert, ca_key, self.ConfigFilePath
                        )
                        self.SSLContext = (srv_crt, srv_key)
                    except Exception as e1:
                        self.LogErrorLine("Error setting up Local CA cert: " + str(e1))
                        self.SSLContext = self.generate_adhoc_ssl_context()
                        if self.SSLContext is None:
                            self.SSLContext = "adhoc"
                elif self.CertMode == "custom":
                    if self.ConfigFiles[self.GENMON_CONFIG].HasOption("certfile") and self.ConfigFiles[
                        self.GENMON_CONFIG
                    ].HasOption("keyfile"):
                        CertFile = self.ConfigFiles[self.GENMON_CONFIG].ReadValue("certfile")
                        KeyFile = self.ConfigFiles[self.GENMON_CONFIG].ReadValue("keyfile")
                        if self.CheckCertFiles(CertFile, KeyFile):
                            self.SSLContext = (CertFile, KeyFile)
                        else:
                            self.LogError("Missing key / cert files: reverting to self signed cert.")
                            self.SSLContext = self.generate_adhoc_ssl_context()
                            if self.SSLContext is None:
                                self.SSLContext = "adhoc"
                    else:
                        self.LogError("Custom cert files not configured, falling back to self-signed")
                        self.SSLContext = self.generate_adhoc_ssl_context()
                        if self.SSLContext is None:
                            self.SSLContext = "adhoc"

            return True
        except Exception as e1:
            self.LogError("Missing config file or config file entries: " + str(e1))
            return False

    # ---------------------SetupMFA--------------------------------------------------
    def SetupMFA(self):

        try:
            self.mail = MyMail(ConfigFilePath=self.ConfigFilePath, loglocation=self.loglocation)
            account = self.mail.SenderAccount
        except Exception as e1:
            self.LogErrorLine("Error setting up mail for 2FA (ConfigFilePath=" + str(self.ConfigFilePath) + "): " + str(e1))
            account = "genmon"
        try:
            self.MFA_URL = pyotp.totp.TOTP(self.SecretMFAKey).provisioning_uri(
                name=account, issuer_name="Genmon"
            )
        except Exception as e1:
            self.LogErrorLine("Error setting up 2FA: " + str(e1))

    # -------------------------------------------------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()

    # -------------------------------------------------------------------------------
    def Close(self):

        if self.Closing:
            return
        self.Closing = True
        try:
            if self.RedirectServer is not None:
                self.RedirectServer.shutdown()
        except Exception:
            pass
        try:
            if self.MyClientInterface is not None:
                self.MyClientInterface.Close()
        except Exception as e1:
            self.LogErrorLine("Error in close: " + str(e1))

        sys.exit(0)

    # -------------------------------------------------------------------------------
    def ReadSettingsFromFile(self):

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
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "sitename",
        ]
        ConfigSettings["use_serial_tcp"] = [
            "boolean",
            "Enable Serial over TCP/IP",
            2,
            False,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "use_serial_tcp",
        ]
        ConfigSettings["port"] = [
            "string",
            "Port for Serial Communication",
            3,
            "/dev/serial0",
            "",
            "required UnixDevice",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "port",
        ]
        ConfigSettings["serial_tcp_address"] = [
            "string",
            "Serial Server TCP/IP Address",
            4,
            "",
            "",
            "InternetAddress",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "serial_tcp_address",
        ]
        ConfigSettings["serial_tcp_port"] = [
            "int",
            "Serial Server TCP/IP Port",
            5,
            "8899",
            "",
            "digits",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "serial_tcp_port",
        ]
        ConfigSettings["serial_tcp_keepalive"] = [
            "boolean",
            "Enable TCP Keep Alive",
            6,
            False,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "serial_tcp_keepalive",
        ]
        ConfigSettings["modbus_tcp"] = [
            "boolean",
            "Use Modbus TCP protocol",
            6,
            False,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "modbus_tcp",
        ]

        ConfigSettings["disableoutagecheck"] = [
            "boolean",
            "Do Not Check for Outages",
            17,
            False,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "disableoutagecheck",
        ]
        if self.GStartInfo["SetGenTime"]:
            ConfigSettings["syncdst"] = [
                "boolean",
                "Sync Daylight Savings Time",
                22,
                False,
                "",
                "",
                self.GENMON_CONFIG,
                self.GENMON_SECTION,
                "syncdst",
            ]
            ConfigSettings["synctime"] = [
                "boolean",
                "Sync Time",
                23,
                False,
                "",
                "",
                self.GENMON_CONFIG,
                self.GENMON_SECTION,
                "synctime",
            ]
        ConfigSettings["metricweather"] = [
            "boolean",
            "Use Metric Units",
            24,
            False,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "metricweather",
        ]
        ConfigSettings["optimizeforslowercpu"] = [
            "boolean",
            "Optimize for slower CPUs",
            25,
            False,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "optimizeforslowercpu",
        ]
        ConfigSettings["disablepowerlog"] = [
            "boolean",
            "Disable Power / Current Display",
            26,
            False,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "disablepowerlog",
        ]
        ConfigSettings["disablesensorlog"] = [
            "boolean",
            "Disable Sensor Log",
            27,
            False,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "disablesensorlog",
        ]
        ConfigSettings["sensorlogmax"] = [
                "string",
                "Maximum size Sensor Log (MB)",
                70,
                "5",
                "",
                0,
                self.GENMON_CONFIG,
                self.GENMON_SECTION,
                "sensorlogmax",
            ]
        ConfigSettings["max_sensorlog_entries"] = [
                "int",
                "Maximum Entries in Sensor Log",
                71,
                "2000",
                "digits",
                0,
                self.GENMON_CONFIG,
                self.GENMON_SECTION,
                "max_sensorlog_entries",
            ]
        ConfigSettings["autofeedback"] = [
            "boolean",
            "Automated Feedback",
            29,
            False,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "autofeedback",
        ]
        ConfigSettings["update_check"] = [
            "boolean",
            "Check for Software Update",
            30,
            True,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "update_check",
        ]

        ConfigSettings["nominalfrequency"] = [
            "list",
            "Rated Frequency",
            101,
            "60",
            "",
            "50,60",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "nominalfrequency",
        ]
        ConfigSettings["nominalrpm"] = [
            "int",
            "Nominal RPM",
            102,
            "3600",
            "",
            "required digits range:1500:4000",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "nominalrpm",
        ]
        ConfigSettings["nominalkw"] = [
            "int",
            "Maximum kW Output",
            103,
            "22",
            "",
            "required digits range:0:1000",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "nominalkw",
        ]
        ConfigSettings["fueltype"] = [
            "list",
            "Fuel Type",
            104,
            "Natural Gas",
            "",
            "Natural Gas,Propane,Diesel,Gasoline",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "fueltype",
        ]
        ConfigSettings["tanksize"] = [
            "int",
            "Fuel Tank Size",
            105,
            "0",
            "",
            "required digits range:0:10000",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "tanksize",
        ]

        ControllerInfo = self.GetControllerInfo("controller").lower()
        if (
            "liquid cooled" in ControllerInfo
            and "evolution" in ControllerInfo
            and self.GetControllerInfo("fueltype").lower() == "diesel"
        ):
            ConfigSettings["usesensorforfuelgauge"] = [
                "boolean",
                "Use Sensor for Fuel Gauge",
                106,
                True,
                "",
                "",
                self.GENMON_CONFIG,
                self.GENMON_SECTION,
                "usesensorforfuelgauge",
            ]

        if self.ControllerType == "h_100" or self.ControllerType == "powerzone_pro":
            Choices = "120/208,120/240,230/400,240/415,277/480,347/600"
            ConfigSettings["voltageconfiguration"] = [
                "list",
                "Line to Neutral / Line to Line",
                107,
                "277/480",
                "",
                Choices,
                self.GENMON_CONFIG,
                self.GENMON_SECTION,
                "voltageconfiguration",
            ]
            ConfigSettings["hts_transfer_switch"] = [
                "boolean",
                "HTS/MTS/STS Transfer Switch",
                109,
                False,
                "",
                "",
                self.GENMON_CONFIG,
                self.GENMON_SECTION,
                "hts_transfer_switch",
            ]
            ConfigSettings["usesensorforfuelgauge"] = [
                "boolean",
                "Use Sensor for Fuel Gauge",
                106,
                False,
                "",
                "",
                self.GENMON_CONFIG,
                self.GENMON_SECTION,
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
                self.GENMON_CONFIG,
                self.GENMON_SECTION,
                "enhancedexercise",
            ]

        if self.ControllerType == "custom":
            ConfigSettings["nominalbattery"] = [
                    "list",
                    "Nominal Battery Voltage",
                    108,
                    "24",
                    "",
                    "12,24",
                    self.GENMON_CONFIG,
                    self.GENMON_SECTION,
                    "nominalbattery",
                ]

        ConfigSettings["smart_transfer_switch"] = [
            "boolean",
            "Smart Transfer Switch",
            110,
            False,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "smart_transfer_switch",
        ]
        ConfigSettings["displayunknown"] = [
            "boolean",
            "Display Experimental Data",
            111,
            False,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "displayunknown",
        ]

        if self.ControllerType == "h_100":
            ConfigSettings["industrialoutagecheck"] = [
                "boolean",
                "Outage Notice on Transfer State Change",
                112,
                False,
                "",
                "",
                self.GENMON_CONFIG,
                self.GENMON_SECTION,
                "industrialoutagecheck",
            ]

        # These do not appear to work on reload, some issue with Flask
        ConfigSettings["usehttps"] = [
            "boolean",
            "Use Secure Web Server",
            200,
            False,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "usehttps",
        ]
        ConfigSettings["cert_mode"] = [
            "list",
            "Certificate Mode",
            203,
            "selfsigned",
            "",
            "selfsigned,localca,custom",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "cert_mode",
        ]
        ConfigSettings["keyfile"] = [
            "string",
            "https Key File",
            204,
            "",
            "",
            "UnixFile",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "keyfile",
        ]
        ConfigSettings["certfile"] = [
            "string",
            "https Certificate File",
            205,
            "",
            "",
            "UnixFile",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "certfile",
        ]
        ConfigSettings["http_user"] = [
            "string",
            "Web Username",
            206,
            "",
            "",
            "minmax:4:50",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "http_user",
        ]
        ConfigSettings["http_pass"] = [
            "password",
            "Web Password",
            207,
            "",
            "",
            "minmax:4:50",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "http_pass",
        ]
        ConfigSettings["http_user_ro"] = [
            "string",
            "Limited Rights User Username",
            208,
            "",
            "",
            "minmax:4:50",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "http_user_ro",
        ]
        ConfigSettings["http_pass_ro"] = [
            "password",
            "Limited Rights User Password",
            209,
            "",
            "",
            "minmax:4:50",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "http_pass_ro",
        ]
        ConfigSettings["http_port"] = [
            "int",
            "Port of WebServer",
            215,
            8000,
            "",
            "required digits",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "http_port",
        ]
        ConfigSettings["allow_iframe"] = [
            "boolean",
            "Allow Embedding in an iframe",
            216,
            False,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "allow_iframe",
        ]
        ConfigSettings["favicon"] = [
            "string",
            "FavIcon",
            220,
            "",
            "",
            "minmax:8:255",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "favicon",
        ]
        ConfigSettings["system_theme"] = [
            "boolean",
            "Select light or dark theme based on the browser/system setting",
            221,
            False,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "system_theme",
        ]
        ConfigSettings["usemfa"] = [
            "boolean",
            "Use Multi-Factor Authentication",
            210,
            False,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "usemfa",
        ]
        # this value is for display only, it can not be changed by the web app
        # Only expose the provisioning URL when running over HTTPS so the
        # base32 secret is never transmitted in cleartext.
        # When MFA is already enrolled, suppress the provisioning URL so the
        # secret key is never re-exposed after initial setup.
        mfa_url_value = None
        if self.bUseSecureHTTP and not self.bMfaEnrolled:
            mfa_url_value = self.MFA_URL
            if not mfa_url_value and self.SecretMFAKey:
                try:
                    mfa_url_value = pyotp.totp.TOTP(self.SecretMFAKey).provisioning_uri(
                        "genmon", issuer_name="Genmon"
                    )
                except Exception:
                    pass
        ConfigSettings["mfa_url"] = [
            "qrcode",
            "MFA QRCode",
            212,
            mfa_url_value,
            "",
            "",
            None,
            None,
            "mfa_url",
        ]
        ConfigSettings["mfa_enrolled"] = [
            "boolean",
            "MFA Enrolled",
            212.5,
            self.bMfaEnrolled,
            "",
            "",
            None,
            None,
            "mfa_enrolled",
        ]
        # Info-only flag so the JS settings UI can show whether email OTP is available
        email_ok = (self.mail is not None and not getattr(self.mail, 'DisableEmail', True)
                    and not getattr(self.mail, 'DisableSMTP', True))
        ConfigSettings["email_configured"] = [
            "boolean",
            "Email Configured",
            212.6,
            email_ok,
            "",
            "",
            None,
            None,
            "email_configured",
        ]
        # Info-only cert status for the UI cert wizard
        ConfigSettings["cert_info"] = [
            "string",
            "Certificate Info",
            203.5,
            self._get_cert_info(),
            "",
            "",
            None,
            None,
            "cert_info",
        ]
        ConfigSettings["remember_me_days"] = [
            "int",
            "Remember Me (days, 0 = browser session only)",
            215,
            0,
            "",
            "minmax:0:365",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "remember_me_days",
        ]
        ConfigSettings["mfa_trust_extend"] = [
            "boolean",
            "Remember this browser & don't ask for MFA again",
            216,
            False,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "mfa_trust_extend",
        ]
        ConfigSettings["mfa_trust_days"] = [
            "int",
            "Days to remember (never use on shared computers)",
            217,
            90,
            "",
            "minmax:1:365",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "mfa_trust_days",
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
            self.MAIL_CONFIG,
            self.MAIL_SECTION,
            "disablesmtp",
        ]
        ConfigSettings["email_account"] = [
            "string",
            "Email Account",
            301,
            "myemail@gmail.com",
            "",
            "minmax:3:50",
            self.MAIL_CONFIG,
            self.MAIL_SECTION,
            "email_account",
        ]
        ConfigSettings["email_pw"] = [
            "password",
            "Email Password",
            302,
            "password",
            "",
            "max:70",
            self.MAIL_CONFIG,
            self.MAIL_SECTION,
            "email_pw",
        ]
        ConfigSettings["sender_account"] = [
            "string",
            "Sender Address",
            303,
            "no-reply@gmail.com",
            "",
            "email",
            self.MAIL_CONFIG,
            self.MAIL_SECTION,
            "sender_account",
        ]
        ConfigSettings["sender_name"] = [
            "string",
            "Sender Name",
            304,
            "",
            "",
            "max:50",
            self.MAIL_CONFIG,
            self.MAIL_SECTION,
            "sender_name",
        ]
        # email_recipient setting will be handled on the notification screen
        ConfigSettings["smtp_server"] = [
            "string",
            "SMTP Server",
            305,
            "smtp.gmail.com",
            "",
            "InternetAddress",
            self.MAIL_CONFIG,
            self.MAIL_SECTION,
            "smtp_server",
        ]
        ConfigSettings["smtp_port"] = [
            "int",
            "SMTP Server Port",
            307,
            587,
            "",
            "digits",
            self.MAIL_CONFIG,
            self.MAIL_SECTION,
            "smtp_port",
        ]
        ConfigSettings["ssl_enabled"] = [
            "boolean",
            "Use SSL Encryption",
            308,
            False,
            "",
            "",
            self.MAIL_CONFIG,
            self.MAIL_SECTION,
            "ssl_enabled",
        ]
        ConfigSettings["tls_disable"] = [
            "boolean",
            "Disable TLS Encryption",
            309,
            False,
            "",
            "",
            self.MAIL_CONFIG,
            self.MAIL_SECTION,
            "tls_disable",
        ]
        ConfigSettings["use_html"] = [
            "boolean",
            "Use HTML Email Format",
            310,
            False,
            "",
            "",
            self.MAIL_CONFIG,
            self.MAIL_SECTION,
            "use_html",
        ]
        ConfigSettings["smtpauth_disable"] = [
            "boolean",
            "Disable SMTP Auth",
            309,
            False,
            "",
            "",
            self.MAIL_CONFIG,
            self.MAIL_SECTION,
            "smtpauth_disable",
        ]

        ConfigSettings["disableimap"] = [
            "boolean",
            "Disable Receiving Email",
            400,
            False,
            "",
            "",
            self.MAIL_CONFIG,
            self.MAIL_SECTION,
            "disableimap",
        ]
        ConfigSettings["imap_server"] = [
            "string",
            "IMAP Server",
            401,
            "imap.gmail.com",
            "",
            "InternetAddress",
            self.MAIL_CONFIG,
            self.MAIL_SECTION,
            "imap_server",
        ]
        ConfigSettings["readonlyemailcommands"] = [
            "boolean",
            "Disable Email Write Commands",
            402,
            False,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "readonlyemailcommands",
        ]
        ConfigSettings["incoming_mail_folder"] = [
            "string",
            "Incoming Mail Folder",
            403,
            "Generator",
            "",
            "minmax:1:1500",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "incoming_mail_folder",
        ]
        ConfigSettings["processed_mail_folder"] = [
            "string",
            "Mail Processed Folder",
            404,
            "Generator/Processed",
            "",
            "minmax:1:255",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "processed_mail_folder",
        ]

        ConfigSettings["disableweather"] = [
            "boolean",
            "Disable Weather Functionality",
            500,
            False,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "disableweather",
        ]
        ConfigSettings["weatherkey"] = [
            "string",
            "Openweathermap.org API key",
            501,
            "",
            "",
            "required minmax:4:50",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "weatherkey",
        ]
        ConfigSettings["weatherlocation"] = [
            "string",
            "Location to report weather",
            502,
            "",
            "",
            "required minmax:4:50",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "weatherlocation",
        ]
        ConfigSettings["minimumweatherinfo"] = [
            "boolean",
            "Display Minimum Weather Info",
            504,
            True,
            "",
            "",
            self.GENMON_CONFIG,
            self.GENMON_SECTION,
            "minimumweatherinfo",
        ]

        try:
            # Get all the config values
            for entry, List in ConfigSettings.items():
                if List[6] == self.GENMON_CONFIG:
                    # filename, section = None, type = "string", entry, default = "", bounds = None):
                    (ConfigSettings[entry])[3] = self.ReadSingleConfigValue(
                        entry=List[8],
                        filename=self.GENMON_CONFIG,
                        section=List[7],
                        type=List[0],
                        default=List[3],
                        bounds=List[5],
                    )
                elif List[6] == self.MAIL_CONFIG:
                    (ConfigSettings[entry])[3] = self.ReadSingleConfigValue(
                        entry=List[8],
                        filename=self.MAIL_CONFIG,
                        section=List[7],
                        type=List[0],
                        default=List[3],
                    )
                elif List[6] == None:
                    # info-only fields: refresh runtime-computed values
                    if entry == "cert_info":
                        (ConfigSettings[entry])[3] = self._get_cert_info()
                else:
                    self.LogError("Invaild Config File in ReadSettingsFromFile: " + str(List[6]))

            self.GetToolTips(ConfigSettings)
        except Exception as e1:
            self.LogErrorLine("Error in ReadSettingsFromFile: " + entry + ": " + str(e1))

        return ConfigSettings

    # -------------------------------------------------------------------------------
    def SaveSettings(self, query_string):

        try:

            # e.g. {'displayunknown': ['true']}
            settings = dict(parse_qs(query_string, 1))
            if not len(settings):
                # nothing to change
                return
            CurrentConfigSettings = self.ReadSettingsFromFile()

            # --- Auth cascading rules ---
            # If username is removed, also clear password and disable MFA
            http_user = settings.get("http_user", [None])[0]
            if http_user is not None and http_user.strip() == "":
                settings["http_pass"] = [""]
                settings["usemfa"] = ["false"]
            # If password is missing but username is set, don't allow
            http_pass = settings.get("http_pass", [None])[0]
            if http_user is not None and http_user.strip() != "" and http_pass is not None and http_pass.strip() == "":
                self.LogError("SaveSettings: username set without password, clearing both")
                settings["http_user"] = [""]
                settings["http_pass"] = [""]
                settings["usemfa"] = ["false"]
            # Same for read-only account
            http_user_ro = settings.get("http_user_ro", [None])[0]
            if http_user_ro is not None and http_user_ro.strip() == "":
                settings["http_pass_ro"] = [""]

            changed = False
            with self.CriticalLock:
                for Entry in settings.keys():
                    ConfigEntry = CurrentConfigSettings.get(Entry, None)
                    if ConfigEntry != None:
                        ConfigFile = CurrentConfigSettings[Entry][6]
                        Value = settings[Entry][0]
                        Section = CurrentConfigSettings[Entry][7]
                        # CurrentConfigSettings[Entry][3] is the current value
                        CurrentValue = str(CurrentConfigSettings[Entry][3]) if CurrentConfigSettings[Entry][3] is not None else ""
                        # Normalize for comparison: JS sends 'true'/'false' lowercase,
                        # Python str(True) gives 'True' — case-insensitive compare
                        if Value.strip().lower() == CurrentValue.strip().lower():
                            continue  # skip unchanged settings to reduce SD card writes
                    else:
                        self.LogError("Invalid setting: " + str(Entry))
                        continue
                    self.UpdateConfigFile(ConfigFile, Section, Entry, Value)
                    changed = True
            if changed:
                self.Restart()
        except Exception as e1:
            self.LogErrorLine("Error Update Config File (SaveSettings): " + str(e1))

    # -------------------------------------------------------------------------------
    def GetAllConfigValues(self, FileName, section):

        ReturnDict = {}
        try:
            config = MyConfig(filename=FileName, section=section, log=self.log)

            if config == None:
                return ReturnDict
            for (key, value) in config.GetList():
                ReturnDict[key.lower()] = value
        except Exception as e1:
            self.LogErrorLine(
                "Error GetAllConfigValues: " + FileName + ": " + section + ": " + str(e1)
            )

        return ReturnDict

    # -------------------------------------------------------------------------------
    def ReadSingleConfigValue(self, 
        entry, filename=None, section=None, type="string", default="", bounds=None
    ):

        try:

            try:
                if filename == None:
                    config = self.ConfigFiles[self.GENMON_CONFIG]
                else:
                    config = self.ConfigFiles[filename]
            except Exception as e1:
                self.LogErrorLine(
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
                        self.LogError(
                            "Warning: Reading Config File (value not in list): %s : %s"
                            % (entry, Value)
                        )
                    return default
                else:
                    self.LogError(
                        "Error Reading Config File (bounds not provided): %s : %s"
                        % (entry, Value)
                    )
                    return default
            else:
                self.LogError(
                    "Error Reading Config File (unknown type): %s : %s" % (entry, type)
                )
                return default

        except Exception as e1:
            self.LogErrorLine("Error Reading Config File (ReadSingleConfigValue): " + str(e1))
            return default

    # ---------------------MySupport::UpdateConfigFile-------------------------------
    # Add or update config item
    def UpdateConfigFile(self, FileName, section, Entry, Value):

        try:

            if FileName == None or section == None or Entry == None or Value == None:
                return False
            if FileName == "" or section == "" or Entry == "":
                return False
            try:
                config = self.ConfigFiles[FileName]
            except Exception as e1:
                self.LogErrorLine(
                    "Unknow file in UpdateConfigFile: " + FileName + ": " + str(e1)
                )
                return False

            config.SetSection(section)
            return config.WriteValue(Entry, Value)

        except Exception as e1:
            self.LogErrorLine("Error Update Config File (UpdateConfigFile): " + str(e1))
            return False

    # -------------------------------------------------------------------------------
    def GetImportConfigFileNames(self):

        try:
            path = os.path.join(
                os.path.dirname(os.path.realpath(__file__)), "data", "controller"
            )
            listing = os.listdir(path)
            listing.sort()
            return ",".join(listing)
        except Exception as e1:
            self.LogErrorLine("Error Reading Config File (ReadSingleConfigValue): " + str(e1))
            return ""

    # -------------------------------------------------------------------------------
    def GetControllerInfo(self, request=None):

        ReturnValue = "Evolution, Air Cooled"
        try:
            if request.lower() == "controller":
                ReturnValue = "Evolution, Air Cooled"
            if request.lower() == "fueltype":
                ReturnValue = "Propane"

            if not len(self.GStartInfo):
                return ReturnValue

            if request.lower() == "controller":
                return self.GStartInfo["Controller"]
            if request.lower() == "fueltype":
                return self.GStartInfo["fueltype"]
        except Exception as e1:
            self.LogErrorLine("Error in GetControllerInfo: " + str(e1))
            pass

        return ReturnValue

    # -------------------------------------------------------------------------------
    def ReadAdvancedSettingsFromFile(self):

        return self.ReadSettingsTable(ADVANCED_SETTINGS, "ReadAdvancedSettingsFromFile")

    # -------------------------------------------------------------------------------
    # True if a setting with this "when" condition is shown (see genservsettings.py)
    def SettingShown(self, when):

        if when is None:
            return True
        if when == "custom":
            return self.ControllerType == "custom"
        if when == "evo_nexus":
            return self.ControllerType == "generac_evo_nexus"
        if when == "not_h100":
            return self.ControllerType != "h_100"
        if when == "h100":
            return self.ControllerType == "h_100"
        if when == "nexus":
            return (self.ControllerType != "h_100"
                    and "nexus" in self.GetControllerInfo("controller").lower())
        if when == "linux":
            return bool(self.GStartInfo.get("Linux", False))
        self.LogError("Unknown setting condition: " + str(when))
        return False

    # -------------------------------------------------------------------------------
    # The value of a Dynamic default or bounds (see genservsettings.py)
    def SettingValue(self, value):

        if not isinstance(value, Dynamic):
            return value
        if value is GENMON_DIR:
            return os.path.dirname(os.path.realpath(__file__))
        if value is IMPORT_CONFIG_FILES:
            return self.GetImportConfigFileNames()
        raise ValueError("Unknown setting value: " + value.name)

    # -------------------------------------------------------------------------------
    # Build a settings page from a table in genservsettings.py: the settings that
    # are shown, each with its current value read from its config file
    def ReadSettingsTable(self, table, caller):

        Files = {
            "genmon": (self.GENMON_CONFIG, self.GENMON_SECTION),
            "mail": (self.MAIL_CONFIG, self.MAIL_SECTION),
        }
        ConfigSettings = collections.OrderedDict()
        try:
            for setting in table:
                if not self.SettingShown(setting.when):
                    continue
                if setting.file not in Files:
                    self.LogError("Invaild Config File in " + caller + ": " + str(setting.file))
                    continue
                FileName, Section = Files[setting.file]
                bounds = self.SettingValue(setting.bounds)
                value = self.ReadSingleConfigValue(
                    entry=setting.key,
                    filename=FileName,
                    section=Section,
                    type=setting.type,
                    default=self.SettingValue(setting.default),
                    bounds=bounds,
                )
                ConfigSettings[setting.key] = [
                    setting.type, setting.title, setting.sort, value, "", bounds,
                    FileName, Section, setting.key,
                ]
            self.GetToolTips(ConfigSettings)
        except Exception as e1:
            self.LogErrorLine("Error in " + caller + ": " + str(e1))
        return ConfigSettings

    # -------------------------------------------------------------------------------
    def SaveAdvancedSettings(self, query_string):
        try:

            if query_string == None:
                self.LogError("Empty query string in SaveAdvancedSettings")
                return
            # e.g. {'displayunknown': ['true']}
            settings = dict(parse_qs(query_string, 1))
            if not len(settings):
                # nothing to change
                return
            CurrentConfigSettings = self.ReadAdvancedSettingsFromFile()
            with self.CriticalLock:
                for Entry in settings.keys():
                    ConfigEntry = CurrentConfigSettings.get(Entry, None)
                    if ConfigEntry != None:
                        ConfigFile = CurrentConfigSettings[Entry][6]
                        Value = settings[Entry][0]
                        Section = CurrentConfigSettings[Entry][7]
                    else:
                        self.LogError("Invalid setting in SaveAdvancedSettings: " + str(Entry))
                        continue
                    self.UpdateConfigFile(ConfigFile, Section, Entry, Value)
            self.Restart()
        except Exception as e1:
            self.LogErrorLine("Error Update Config File (SaveAdvancedSettings): " + str(e1))

    # -------------------------------------------------------------------------------
    def ReadNotificationsFromFile(self):

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
            EmailsStr = self.ConfigFiles[self.MAIL_CONFIG].ReadValue("email_recipient")

            for email in EmailsStr.split(","):
                email = email.strip()
                EmailsToNotify.append(email)

            SortOrder = 1
            for email in EmailsToNotify:
                Notify = self.ConfigFiles[self.MAIL_CONFIG].ReadValue(email, default="")
                if Notify == "":
                    NotificationSettings[email] = [SortOrder]
                else:
                    NotificationSettings[email] = [SortOrder, Notify]
        except Exception as e1:
            self.LogErrorLine("Error in ReadNotificationsFromFile: " + str(e1))

        return NotificationSettings

    # -------------------------------------------------------------------------------
    def SaveNotifications(self, query_string):

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
            with self.CriticalLock:
                # get existing settings
                if self.ConfigFiles[self.MAIL_CONFIG].HasOption("email_recipient"):
                    oldEmailRecipientString = self.ConfigFiles[self.MAIL_CONFIG].ReadValue(
                        "email_recipient"
                    )
                    oldEmailRecipientString.strip()
                    oldEmailsList = oldEmailRecipientString.split(",")
                    for oldEmailItem in oldEmailsList:
                        if self.ConfigFiles[self.MAIL_CONFIG].HasOption(oldEmailItem):
                            oldNotifications[oldEmailItem] = self.ConfigFiles[
                                self.MAIL_CONFIG
                            ].ReadValue(oldEmailItem)

                # compare, remove notifications if needed
                for oldEmailItem in oldEmailsList:
                    if not oldEmailItem in notifications.keys() and self.ConfigFiles[
                        self.MAIL_CONFIG
                    ].HasOption(oldEmailItem):
                        self.ConfigFiles[self.MAIL_CONFIG].WriteValue(oldEmailItem, "", remove=True)

                # add / update the entries
                # update email recipient if needed
                if oldEmailRecipientString != notifications_order_string:
                    self.ConfigFiles[self.MAIL_CONFIG].WriteValue(
                        "email_recipient", notifications_order_string
                    )

                # update catigories
                for newEmail, newCats in notifications.items():
                    # remove catigories if needed from existing emails
                    if not len(newCats[0]) and self.ConfigFiles[self.MAIL_CONFIG].HasOption(newEmail):
                        self.ConfigFiles[self.MAIL_CONFIG].WriteValue(newEmail, "", remove=True)
                    # update or add catigories
                    if len(newCats[0]):
                        self.ConfigFiles[self.MAIL_CONFIG].WriteValue(newEmail, newCats[0])

            self.Restart()
        except Exception as e1:
            self.LogErrorLine("Error in SaveNotifications: " + str(e1))
        return

    # -------------------------------------------------------------------------------
    def SendTestEmail(self, query_string):
        try:
            if query_string == None or not len(query_string):
                return jsonify({"error": "No parameters given for email test."})
            parameters = json.loads(query_string)
            if not len(parameters):
                return jsonify({"error": "No parameters"})  # nothing to change return

        except Exception as e1:
            self.LogErrorLine("Error getting parameters in SendTestEmail: " + str(e1))
            return jsonify({"error": "Error getting parameters in email test: " + str(e1)})
        try:
            smtp_server = str(parameters["smtp_server"])
            smtp_server = smtp_server.strip()
            smtp_port = int(parameters["smtp_port"])
            email_account = str(parameters["email_account"])
            email_account = email_account.strip()
            sender_account = str(parameters["sender_account"])
            sender_account = sender_account.strip()
            if not len(sender_account):
                sender_account = None
            sender_name = str(parameters["sender_name"])
            sender_name = sender_name.strip()
            if not len(sender_name):
                sender_name = None
            recipient = str(parameters["recipient"])
            recipient = recipient.strip()
            password = str(parameters["password"])
            use_ssl = parameters["use_ssl"] in (True, "true", "True", "1", 1)
            tls_disable = parameters["tls_disable"] in (True, "true", "True", "1", 1)
            smtpauth_disable = parameters["smtpauth_disable"] in (True, "true", "True", "1", 1)
            use_html = parameters.get("use_html", False) in (True, "true", "True", "1", 1)

        except Exception as e1:
            self.LogErrorLine("Error parsing parameters in SendTestEmail: " + str(e1))
            self.LogError(str(parameters))
            return jsonify({"error": "Error parsing parameters in email test: " + str(e1)})

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
                use_html=use_html,
            )
            return jsonify({"message": ReturnMessage})
        except Exception as e1:
            self.LogErrorLine("Error sending test email : " + str(e1))
            return jsonify({"error": "Error sending test email : " + str(e1)})

    # -------------------------------------------------------------------------------
    def CacheToolTips(self):

        try:

            foundRegText = False
            config_section = "generac_evo_nexus"
            pathtofile = os.path.dirname(os.path.realpath(__file__))
            try:
                data = self.MyClientInterface.ProcessMonitorCommand("generator: getreglabels_json")
                regdata = json.loads(data)
                if len(regdata):
                    self.CachedRegisterDescriptions = regdata
                    foundRegText = True
            except Exception as e1:
                self.LogErrorLine("Error in CacheToolTips reading reg data")

            # get controller used
            if self.ConfigFiles[self.GENMON_CONFIG].HasOption("controllertype"):
                config_section = self.ConfigFiles[self.GENMON_CONFIG].ReadValue("controllertype")
            else:
                config_section = "generac_evo_nexus"

            if not len(config_section):
                config_section = "generac_evo_nexus"

            # H_100
            self.ControllerType = config_section

            if self.ControllerType == "h_100":
                try:
                    if (
                        len(self.GStartInfo["Controller"])
                        and not "H-100" in self.GStartInfo["Controller"]
                    ):
                        # Controller is G-Panel
                        config_section = "g_panel"

                except Exception as e1:
                    self.LogError("Error reading Controller Type for H-100: " + str(e1))
            if not foundRegText:
                self.CachedRegisterDescriptions = {"Holding":self.GetAllConfigValues(
                    os.path.join(pathtofile, "data", "tooltips.txt"), config_section
                )}

            self.CachedToolTips = self.GetAllConfigValues(
                os.path.join(pathtofile, "data", "tooltips.txt"), "ToolTips"
            )

        except Exception as e1:
            self.LogErrorLine("Error reading tooltips.txt " + str(e1))

    # -------------------------------------------------------------------------------
    def GetToolTips(self, ConfigSettings):

        try:

            for entry, List in ConfigSettings.items():
                try:
                    (ConfigSettings[entry])[4] = self.CachedToolTips[entry.lower()]
                except:
                    # self.LogError("Error in GetToolTips: " + entry)
                    pass  # TODO

        except Exception as e1:
            self.LogErrorLine("Error in GetToolTips: " + str(e1))

    # -------------------------------------------------------------------------------
    def GetAddOns(self):
        AddOnCfg = collections.OrderedDict()

        # Default icon name should be "Genmon" to get a generic icon
        try:
            # GENGPIO
            Temp = collections.OrderedDict()
            AddOnCfg["gengpio"] = collections.OrderedDict()
            AddOnCfg["gengpio"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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
            AddOnCfg["gengpioin"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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
            AddOnCfg["gengpioin"]["parameters"]["trigger"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENGPIOIN_CONFIG].ReadValue(
                    "trigger", return_type=str, default="falling"
                ),
                "list",
                "Set GPIO input to trigger on rising or falling edge.",
                bounds="falling,rising,both",
                display_name="GPIO Edge Trigger",
            )
            AddOnCfg["gengpioin"]["parameters"]["resistorpull"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENGPIOIN_CONFIG].ReadValue(
                    "resistorpull", return_type=str, default="up"
                ),
                "list",
                "Set GPIO input internal pull up or pull down resistor.",
                bounds="up,down,off",
                display_name="Internal resistor pull",
            )
            AddOnCfg["gengpioin"]["parameters"]["bounce"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENGPIOIN_CONFIG].ReadValue(
                    "bounce", return_type=int, default=0
                ),
                "int",
                "Minimum interval in milliseconds between valid input changes. Zero to disable, or positive whole number.",
                bounds="number",
                display_name="Software Debounce",
            )

            # GENGPIOLEDBLINK
            AddOnCfg["gengpioledblink"] = collections.OrderedDict()
            AddOnCfg["gengpioledblink"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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
            AddOnCfg["gengpioledblink"]["parameters"]["ledpin"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENGPIOLEDBLINK_CONFIG].ReadValue(
                    "ledpin", return_type=int, default=12
                ),
                "int",
                "GPIO pin number that an LED is connected (valid numbers are 0 - 27)",
                bounds="required digits range:0:27",
                display_name="GPIO LED pin",
            )

            # GENLOG
            AddOnCfg["genlog"] = collections.OrderedDict()
            AddOnCfg["genlog"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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
            Args = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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
            AddOnCfg["genlog"]["parameters"]["Log File Name"] = self.CreateAddOnParam(
                Value,
                "string",
                "Filename for log. Full path of the file must be included (i.e. /home/pi/genmon/LogFile.csv)",
                bounds="required UnixFile",
                display_name="Log File Name",
            )

            # GENSMS
            AddOnCfg["gensms"] = collections.OrderedDict()
            AddOnCfg["gensms"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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

            AddOnCfg["gensms"]["parameters"]["accountsid"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENSMS_CONFIG].ReadValue(
                    "accountsid", return_type=str, default=""
                ),
                "string",
                "Twilio account SID. This can be obtained from a valid Twilio account",
                bounds="required minmax:10:50",
                display_name="Twilio Account SID",
            )
            AddOnCfg["gensms"]["parameters"]["authtoken"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENSMS_CONFIG].ReadValue(
                    "authtoken", return_type=str, default=""
                ),
                "string",
                "Twilio authentication token. This can be obtained from a valid Twilio account",
                bounds="required minmax:10:50",
                display_name="Twilio Authentication Token",
            )
            AddOnCfg["gensms"]["parameters"]["to_number"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENSMS_CONFIG].ReadValue(
                    "to_number", return_type=str, default=""
                ),
                "string",
                "Mobile number to send SMS message to. This can be any mobile number. Separate multilpe recipients with commas.",
                bounds="required InternationalPhone",
                display_name="Recipient Phone Number",
            )
            AddOnCfg["gensms"]["parameters"]["from_number"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENSMS_CONFIG].ReadValue(
                    "from_number", return_type=str, default=""
                ),
                "string",
                "Number to send SMS message from. This should be a twilio phone number.",
                bounds="required InternationalPhone",
                display_name="Twilio Phone Number",
            )

            AddOnCfg = self.AddNotificationAddOnParam(AddOnCfg, "gensms", self.GENSMS_CONFIG)
            AddOnCfg = self.AddRetryAddOnParam(AddOnCfg, "gensms", self.GENSMS_CONFIG)

            # GENSMS_VOIP
            Description = "SMS Support vis VoIP using voip.ms"
            try:
                import voipms
            except Exception as e1:
                Description = (
                    Description
                    + "<br/><font color='red'>The required libraries for this add on are not installed. They will be installaled on the when the proram is restarted.</font>"
                )

            AddOnCfg["gensms_voip"] = collections.OrderedDict()
            AddOnCfg["gensms_voip"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
                "enable", return_type=bool, section="gensms_voip", default=False
            )
            AddOnCfg["gensms_voip"]["title"] = "SMS via VoIP using voip.ms"

            AddOnCfg["gensms_voip"]["description"] = Description
            AddOnCfg["gensms_voip"]["icon"] = "voipms"
            AddOnCfg["gensms_voip"][
                "url"
            ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensms_voippy-optional"
            AddOnCfg["gensms_voip"]["parameters"] = collections.OrderedDict()

            AddOnCfg["gensms_voip"]["parameters"]["username"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENSMS_VOIP_CONFIG].ReadValue(
                    "username", return_type=str, default=""
                ),
                "string",
                "Voip.ms account username",
                bounds="required minmax:5:50",
                display_name="VoIP.ms User Name",
            )
            AddOnCfg["gensms_voip"]["parameters"]["password"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENSMS_VOIP_CONFIG].ReadValue(
                    "password", return_type=str, default=""
                ),
                "password",
                "VoIP.ms API password. This is NOT the account login, but rather then API password",
                bounds="required minmax:8:50",
                display_name="VoIP.ms API password",
            )
            AddOnCfg["gensms_voip"]["parameters"]["did"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENSMS_VOIP_CONFIG].ReadValue(
                    "did", return_type=str, default=""
                ),
                "string",
                "DID number for your voip.ms account to send the SMS.",
                bounds="required InternationalPhone",
                display_name="Sender DID Number",
            )
            AddOnCfg["gensms_voip"]["parameters"]["destination"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENSMS_VOIP_CONFIG].ReadValue(
                    "destination", return_type=str, default=""
                ),
                "string",
                "Mobile number to send SMS message to. This can be any mobile number. Separate multilpe recipients with commas.",
                bounds="required InternationalPhone",
                display_name="Recipient Phone Number",
            )
            # GENSMS_MODEM
            AddOnCfg["gensms_modem"] = collections.OrderedDict()
            AddOnCfg["gensms_modem"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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

            AddOnCfg["gensms_modem"]["parameters"]["recipient"] = self.CreateAddOnParam(
                self.ConfigFiles[self.MYMODEM_CONFIG].ReadValue(
                    "recipient", return_type=str, default=""
                ),
                "string",
                "Mobile number to send SMS message. This can be any mobile number. No dashes or spaces.",
                bounds="required InternationalPhone",
                display_name="Recipient Phone Number",
            )
            AddOnCfg["gensms_modem"]["parameters"]["port"] = self.CreateAddOnParam(
                self.ConfigFiles[self.MYMODEM_CONFIG].ReadValue("port", return_type=str, default=""),
                "string",
                "This is the serial device to send AT modem commands. This *must* be different from the serial port used by the generator monitor software.",
                bounds="required UnixDevice",
                display_name="Modem Serial Port",
            )

            AddOnCfg["gensms_modem"]["parameters"]["rate"] = self.CreateAddOnParam(
                self.ConfigFiles[self.MYMODEM_CONFIG].ReadValue(
                    "rate", return_type=int, default=115200
                ),
                "int",
                "The baud rate for the port. Use 115200 for the LTEPiHat.",
                bounds="required digits",
                display_name="Modem Serial Rate",
            )
            AddOnCfg["gensms_modem"]["parameters"]["log_at_commands"] = self.CreateAddOnParam(
                self.ConfigFiles[self.MYMODEM_CONFIG].ReadValue(
                    "log_at_commands", return_type=bool, default=False
                ),
                "boolean",
                "Enable to log at commands to the log file.",
                display_name="Log AT Commands",
            )

            AddOnCfg = self.AddNotificationAddOnParam(AddOnCfg, "gensms_modem", self.MYMODEM_CONFIG)

            # modem type - select the type of modem used. For future use. Presently "LTEPiHat" is the only option
            # modem_type = LTEPiHat

            # GENPUSHOVER
            AddOnCfg["genpushover"] = collections.OrderedDict()
            AddOnCfg["genpushover"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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

            AddOnCfg["genpushover"]["parameters"]["appid"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "appid", return_type=str, default=""
                ),
                "string",
                "Pushover app ID. This is generated by pushover.net when an application is created for your account.",
                bounds="required minmax:30:30",
                display_name="Application ID",
            )
            AddOnCfg["genpushover"]["parameters"]["userid"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "userid", return_type=str, default=""
                ),
                "string",
                "Pushover User Key. Note: this is not your login user name but a key generated by pushover.net for your account. "
                "To send notifications to more than one person, enter multiple user (or group) keys separated by spaces and/or commas, "
                "e.g. 'key1 key2 key3'. These keys all receive the same notifications. If you wish to send different "
                "notification types to other users, please use the Additional Recipient(s) key and adjust the settings for that user.",
                bounds="required minmax:30:500",
                display_name="Pushover User Key",
            )
            AddOnCfg["genpushover"]["parameters"]["pushsound"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "pushsound", return_type=str, default="updown"
                ),
                "string",
                "Notification sound identifier. See https://pushover.net/api#sounds for a full list of sound IDs. All sounds must be lower case.",
                bounds="minmax:3:20",
                display_name="Push Sound",
            )
            AddOnCfg["genpushover"]["parameters"]["alarm_priority"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "alarm_priority", return_type=str, default="NORMAL"
                ),
                "list",
                "Alarm Notification priority identifier. See https://pushover.net/api#priority",
                bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
                display_name="Alarm Priority",
            )
            AddOnCfg["genpushover"]["parameters"]["sw_update_priority"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "sw_update_priority", return_type=str, default="NORMAL"
                ),
                "list",
                "Software Update Notification priority identifier. See https://pushover.net/api#priority",
                bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
                display_name="Software Update Priority",
            )
            AddOnCfg["genpushover"]["parameters"][
                "system_health_priority"
            ] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "system_health_priority", return_type=str, default="NORMAL"
                ),
                "list",
                "System Health Notification priority identifier. See https://pushover.net/api#priority",
                bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
                display_name="System Health Priority",
            )
            AddOnCfg["genpushover"]["parameters"]["fuel_priority"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "fuel_priority", return_type=str, default="NORMAL"
                ),
                "list",
                "Fuel Level Notification priority identifier. See https://pushover.net/api#priority",
                bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
                display_name="Fuel Level Priority",
            )
            AddOnCfg["genpushover"]["parameters"]["outage_priority"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "outage_priority", return_type=str, default="NORMAL"
                ),
                "list",
                "Outage Notification priority identifier. See https://pushover.net/api#priority",
                bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
                display_name="Outage Priority",
            )
            AddOnCfg["genpushover"]["parameters"][
                "switch_state_priority"
            ] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "switch_state_priority", return_type=str, default="NORMAL"
                ),
                "list",
                "Switch State Notification priority identifier. See https://pushover.net/api#priority",
                bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
                display_name="Switch State Priority",
            )
            AddOnCfg["genpushover"]["parameters"]["run_state_priority"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "run_state_priority", return_type=str, default="NORMAL"
                ),
                "list",
                "Run State Notification priority identifier. See https://pushover.net/api#priority",
                bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
                display_name="Run State Priority",
            )
            AddOnCfg["genpushover"]["parameters"][
                "service_state_priority"
            ] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "service_state_priority", return_type=str, default="NORMAL"
                ),
                "list",
                "Service State Notification priority identifier. See https://pushover.net/api#priority",
                bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
                display_name="Service State Priority",
            )
            AddOnCfg["genpushover"]["parameters"]["pi_state_priority"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "pi_state_priority", return_type=str, default="NORMAL"
                ),
                "list",
                "Pi Hardware Sensor State Notification priority identifier. See https://pushover.net/api#priority",
                bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
                display_name="Pi Hardware Sensor State Priority",
            )

            AddOnCfg = self.AddNotificationAddOnParam(
                AddOnCfg, "genpushover", self.GENPUSHOVER_CONFIG
            )

            AddOnCfg["genpushover"]["parameters"]["extra_userid"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "extra_userid", return_type=str, default=""
                ),
                "string",
                "Optional additional Pushover user (or group) key(s), separated by spaces and/or commas, for recipients who "
                "should only receive some notification categories (e.g. a family member who only wants outage alerts). Use "
                "the 'Additional Recipient(s)' Notify settings below to choose which categories they receive. A category "
                "must also be enabled above for it to be sent to these recipients.",
                bounds="minmax:0:500",
                display_name="Additional Recipient(s) User Key",
            )
            AddOnCfg["genpushover"]["parameters"]["extra_notify_error"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "extra_notify_error", return_type=bool, default=True
                ),
                "boolean",
                "Send messages for errors (Generator Alarms) to the Additional Recipient(s) above.",
                display_name="Additional Recipient(s) Notify for Errors",
            )
            AddOnCfg["genpushover"]["parameters"]["extra_notify_warn"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "extra_notify_warn", return_type=bool, default=True
                ),
                "boolean",
                "Send messages for warnings (service due, fuel low) to the Additional Recipient(s) above.",
                display_name="Additional Recipient(s) Notify for Warnings",
            )
            AddOnCfg["genpushover"]["parameters"]["extra_notify_info"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "extra_notify_info", return_type=bool, default=True
                ),
                "boolean",
                "Send messages for information (switch state change, engine state change, exercising) to the Additional "
                "Recipient(s) above.",
                display_name="Additional Recipient(s) Notify for Information",
            )
            AddOnCfg["genpushover"]["parameters"]["extra_notify_outage"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "extra_notify_outage", return_type=bool, default=True
                ),
                "boolean",
                "Send messages for outages to the Additional Recipient(s) above.",
                display_name="Additional Recipient(s) Notify for Outages",
            )
            AddOnCfg["genpushover"]["parameters"][
                "extra_notify_sw_update"
            ] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "extra_notify_sw_update", return_type=bool, default=True
                ),
                "boolean",
                "Send messages for software updates to the Additional Recipient(s) above.",
                display_name="Additional Recipient(s) Notify for Software Updates",
            )
            AddOnCfg["genpushover"]["parameters"][
                "extra_notify_pi_state"
            ] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENPUSHOVER_CONFIG].ReadValue(
                    "extra_notify_pi_state", return_type=bool, default=True
                ),
                "boolean",
                "Send messages for Pi hardware sensor status to the Additional Recipient(s) above.",
                display_name="Additional Recipient(s) Notify for Pi Hardware Issues",
            )

            AddOnCfg = self.AddRetryAddOnParam(AddOnCfg, "genpushover", self.GENPUSHOVER_CONFIG)

            # GENSYSLOG
            AddOnCfg["gensyslog"] = collections.OrderedDict()
            AddOnCfg["gensyslog"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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
            AddOnCfg["genmqtt"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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

            AddOnCfg["genmqtt"]["parameters"]["mqtt_address"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "mqtt_address", return_type=str, default=""
                ),
                "string",
                "Address of your MQTT server.",
                bounds="required InternetAddress",
                display_name="MQTT Server Address",
            )
            AddOnCfg["genmqtt"]["parameters"]["mqtt_port"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "mqtt_port", return_type=int, default=1833
                ),
                "int",
                "The port of the MQTT server in a decimal number.",
                bounds="required digits",
                display_name="MQTT Server Port Number",
            )
            AddOnCfg["genmqtt"]["parameters"]["username"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "username", return_type=str, default=""
                ),
                "string",
                "This value is used for the username if your MQTT server requires authentication. Leave blank for no authentication.",
                bounds="minmax:4:50",
                display_name="MQTT Authentication Username",
            )
            AddOnCfg["genmqtt"]["parameters"]["password"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "password", return_type=str, default=""
                ),
                "password",
                "This value is used for the password if your MQTT server requires authentication. Leave blank for no authentication or no password.",
                bounds="minmax:4:50",
                display_name="MQTT Authentication Password",
            )
            AddOnCfg["genmqtt"]["parameters"]["poll_interval"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "poll_interval", return_type=float, default=2.0
                ),
                "float",
                "The time in seconds between requesting status from genmon. The default value is 2 seconds.",
                bounds="number",
                display_name="Poll Interval",
            )
            AddOnCfg["genmqtt"]["parameters"]["root_topic"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "root_topic", return_type=str, default=""
                ),
                "string",
                "(Optional) Prepend this value to the MQTT data path i.e. 'Home' would result in 'Home/generator/...''",
                bounds="minmax:1:50",
                display_name="Root Topic",
            )
            AddOnCfg["genmqtt"]["parameters"]["blacklist"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "blacklist", return_type=str, default=""
                ),
                "string",
                "(Optional) Names of data not exported to the MQTT server, separated by commas.",
                bounds="",
                display_name="Blacklist Filter",
            )
            AddOnCfg["genmqtt"]["parameters"]["flush_interval"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "flush_interval", return_type=float, default=0
                ),
                "float",
                "(Optional) Time in seconds where even unchanged values will be published to their MQTT topic. Set to zero to disable flushing.",
                bounds="number",
                display_name="Flush Interval",
            )
            AddOnCfg["genmqtt"]["parameters"]["numeric_json"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "numeric_json", return_type=bool, default=False
                ),
                "boolean",
                "If enabled will return numeric values in the Status, Maintenance and Outage topics as separate topics for unit, type and value.",
                bounds="",
                display_name="Numeric Topics",
            )
            AddOnCfg["genmqtt"]["parameters"]["numeric_json_object"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "numeric_json_object", return_type=bool, default=False
                ),
                "boolean",
                "If enabled will return a JSON object for numeric values in the Status, Maintenance and Outage topics as an object with unit, type and value members.",
                bounds="",
                display_name="JSON for Numerics",
            )
            AddOnCfg["genmqtt"]["parameters"]["strlist_json"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "strlist_json", return_type=bool, default=False
                ),
                "boolean",
                "If enabled will return a JSON list for any list of strings like the Outage log. Does not apply if JSON for Numerics is enabled.",
                bounds="",
                display_name="JSON for String Lists",
            )
            AddOnCfg["genmqtt"]["parameters"]["remove_spaces"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "remove_spaces", return_type=bool, default=False
                ),
                "boolean",
                "If enabled any spaces in the topic path will be converted to underscores",
                bounds="",
                display_name="Remove Spaces in Topic Path",
            )
            AddOnCfg["genmqtt"]["parameters"]["retain"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "retain", return_type=bool, default=False
                ),
                "boolean",
                "If enabled, published messages will be retained by the MQTT broker server after a the Add On disconnects from the server.",
                bounds="",
                display_name="Retain Data",
            )
            AddOnCfg["genmqtt"]["parameters"]["cert_authority_path"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "cert_authority_path", return_type=str, default=""
                ),
                "string",
                "(Optional) Full path to Certificate Authority file. Leave empty to not use SSL/TLS. If used port will be forced to 8883.",
                bounds="",
                display_name="SSL/TLS CA certificate file",
            )
            AddOnCfg["genmqtt"]["parameters"]["client_cert_path"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "client_cert_path", return_type=str, default=""
                ),
                "string",
                "Optional. Full path the client certificate file. Leave empty to not use MTLS.",
                bounds="",
                display_name="Client Certificate File",
            )
            AddOnCfg["genmqtt"]["parameters"]["client_key_path"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "client_key_path", return_type=str, default=""
                ),
                "string",
                "Optional. Full path the client key file. Leave empty to not use MTLS.",
                bounds="",
                display_name="Client Key File",
            )
            AddOnCfg["genmqtt"]["parameters"]["tls_version"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "tls_version", return_type=str, default="1.0"
                ),
                "list",
                "(Optional) TLS version used (integer). Default is 1.0. Must be 1.0, 1.1, or 1.2. This is ignored if a CA cert file is not used. ",
                bounds="1.0,1.1,1.2",
                display_name="TLS Version",
            )
            AddOnCfg["genmqtt"]["parameters"]["cert_reqs"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "cert_reqs", return_type=str, default="Required"
                ),
                "list",
                "(Optional) Defines the certificate requirements that the client imposes on the broker. Used if Certificate Authority file is used.",
                bounds="None,Optional,Required",
                display_name="Certificate Requirements",
            )
            AddOnCfg["genmqtt"]["parameters"]["client_id"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTT_CONFIG].ReadValue(
                    "client_id", return_type=str, default="genmon"
                ),
                "string",
                "Unique identifier. Must be unique for each instance of genmon and add on running on a given system. ",
                bounds="",
                display_name="Client ID",
            )

            # GENMQTTIN
            AddOnCfg["genmqttin"] = collections.OrderedDict()
            AddOnCfg["genmqttin"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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

            AddOnCfg["genmqttin"]["parameters"]["topics"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "topics", return_type=str, default=""
                ),
                "string",
                "Comma separated list of MQTT topics to subscribe and import into genmon. All topics must return a numeric value or a string representation of a numeric value.",
                bounds="",
                display_name="Topics",
            )
            AddOnCfg["genmqttin"]["parameters"]["labels"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "labels", return_type=str, default=""
                ),
                "string",
                "Comma separated list of display names for each topic listed above. These will be the displayed label for each topic value.",
                bounds="",
                display_name="Displayed Name",
            )
            AddOnCfg["genmqttin"]["parameters"]["units"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "units", return_type=str, default=""
                ),
                "string",
                "Comma separated list of units for each topic listed above. If no labled is used for a given topic, use a space. If using the imported MQTT data for genmon calculations, for power use W or kW, for current use A, for voltage use V. ",
                bounds="",
                display_name="Units",
            )
            AddOnCfg["genmqttin"]["parameters"]["types"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "types", return_type=str, default=""
                ),
                "string",
                "Comma separated list of value types for each topic listed above. Valid types are: ct1,ct2,ctpower1,ctpower2,fuel,temperature,power,current,voltage or pressure. See the wiki entry for this add on for more details.",
                bounds="",
                display_name="Sensor Type",
            )
            AddOnCfg["genmqttin"]["parameters"]["exclude_gauge"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "exclude_gauge", return_type=str, default=""
                ),
                "string",
                "Comma separated list of Displayed Names that will not be displayed as a gauge. If you enable 'Use Data for Calculations' then you can remove duplicate gagues with this setting if they show up in the user interface.",
                bounds="",
                display_name="Exclude Gauge",
            )
            AddOnCfg["genmqttin"]["parameters"]["nominal_values"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "nominal_values", return_type=str, default=""
                ),
                "string",
                "Comma separated list of nominal values for each topic listed above.",
                bounds="",
                display_name="Nominal Values",
            )
            AddOnCfg["genmqttin"]["parameters"]["maximum_values"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "maximum_values", return_type=str, default=""
                ),
                "string",
                "Comma separated list of maximum values for each topic listed above.",
                bounds="",
                display_name="Maximum Values",
            )

            AddOnCfg["genmqttin"]["parameters"]["use_for_power_fuel"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "use_for_power_fuel", return_type=bool, default=False
                ),
                "boolean",
                "If enabled, the data from sensor types fuel,power,current,ct1,ct2,voltageleg1, voltageleg2, ctpower1 and ctpower2 will be imported and used for power and fuel calculations (instead of just displaying) within genmon.",
                bounds="",
                display_name="Use Data for Calculations",
            )
            AddOnCfg["genmqttin"]["parameters"]["strict"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "strict", return_type=bool, default=False
                ),
                "boolean",
                "If enabled, genmon will only use Data for Calculations if the generator utility line is in an outage. If your sensors are connected after the transfer switch (i.e. utility and generator are monitored) the you will want to enable this setting to keep genmon from using the sensor readings when there is not an outage.",
                bounds="",
                display_name="Strict Import Rules",
            )
            AddOnCfg["genmqttin"]["parameters"]["mqtt_address"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "mqtt_address", return_type=str, default=""
                ),
                "string",
                "Address of your MQTT server.",
                bounds="required InternetAddress",
                display_name="MQTT Server Address",
            )
            AddOnCfg["genmqttin"]["parameters"]["mqtt_port"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "mqtt_port", return_type=int, default=1833
                ),
                "int",
                "The port of the MQTT server in a decimal number.",
                bounds="required digits",
                display_name="MQTT Server Port Number",
            )
            AddOnCfg["genmqttin"]["parameters"]["username"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "username", return_type=str, default=""
                ),
                "string",
                "This value is used for the username if your MQTT server requires authentication. Leave blank for no authentication.",
                bounds="minmax:4:50",
                display_name="MQTT Authentication Username",
            )
            AddOnCfg["genmqttin"]["parameters"]["password"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "password", return_type=str, default=""
                ),
                "password",
                "This value is used for the password if your MQTT server requires authentication. Leave blank for no authentication or no password.",
                bounds="minmax:4:50",
                display_name="MQTT Authentication Password",
            )
            AddOnCfg["genmqttin"]["parameters"]["cert_authority_path"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "cert_authority_path", return_type=str, default=""
                ),
                "string",
                "(Optional) Full path to Certificate Authority file. Leave empty to not use SSL/TLS. If used port will be forced to 8883.",
                bounds="",
                display_name="SSL/TLS CA certificate file",
            )
            AddOnCfg["genmqttin"]["parameters"]["client_cert_path"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "client_cert_path", return_type=str, default=""
                ),
                "string",
                "Optional. Full path the client certificate file. Leave empty to not use MTLS.",
                bounds="",
                display_name="Client Certificate File",
            )
            AddOnCfg["genmqttin"]["parameters"]["client_key_path"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "client_key_path", return_type=str, default=""
                ),
                "string",
                "Optional. Full path the client key file. Leave empty to not use MTLS.",
                bounds="",
                display_name="Client Key File",
            )
            AddOnCfg["genmqttin"]["parameters"]["tls_version"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "tls_version", return_type=str, default="1.0"
                ),
                "list",
                "(Optional) TLS version used (integer). Default is 1.0. Must be 1.0, 1.1, or 1.2. This is ignored if a CA cert file is not used. ",
                bounds="1.0,1.1,1.2",
                display_name="TLS Version",
            )
            AddOnCfg["genmqttin"]["parameters"]["cert_reqs"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "cert_reqs", return_type=str, default="Required"
                ),
                "list",
                "(Optional) Defines the certificate requirements that the client imposes on the broker. Used if Certificate Authority file is used.",
                bounds="None,Optional,Required",
                display_name="Certificate Requirements",
            )
            AddOnCfg["genmqttin"]["parameters"]["client_id"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENMQTTIN_CONFIG].ReadValue(
                    "client_id", return_type=str, default="genmon"
                ),
                "string",
                "Unique identifier. Must be unique for each instance of genmon and add on running on a given system. ",
                bounds="",
                display_name="Client ID",
            )
            # GENHOMEASSISTANT
            AddOnCfg["genhomeassistant"] = collections.OrderedDict()
            AddOnCfg["genhomeassistant"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
                "enable", return_type=bool, section="genhomeassistant", default=False
            )
            AddOnCfg["genhomeassistant"]["title"] = "Home Assistant MQTT Discovery"
            AddOnCfg["genhomeassistant"][
                "description"
            ] = "Publish MQTT auto-discovery messages for Home Assistant integration"
            AddOnCfg["genhomeassistant"]["icon"] = "homeassistant"
            AddOnCfg["genhomeassistant"][
                "url"
            ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genhomeassistantpy-optional"
            AddOnCfg["genhomeassistant"]["parameters"] = collections.OrderedDict()

            AddOnCfg["genhomeassistant"]["parameters"]["mqtt_address"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "mqtt_address", return_type=str, default=""
                ),
                "string",
                "Address of your MQTT broker server (IP address or hostname).",
                bounds="required InternetAddress",
                display_name="MQTT Server Address",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["mqtt_port"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "mqtt_port", return_type=int, default=1883
                ),
                "int",
                "Port of the MQTT broker. Default is 1883 (or 8883 for TLS).",
                bounds="required digits",
                display_name="MQTT Port",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["username"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "username", return_type=str, default=""
                ),
                "string",
                "Username for MQTT broker authentication (leave empty if not required).",
                bounds="minmax:4:50",
                display_name="Username",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["password"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "password", return_type=str, default=""
                ),
                "password",
                "Password for MQTT broker authentication (leave empty if not required).",
                bounds="",
                display_name="Password",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["discovery_prefix"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "discovery_prefix", return_type=str, default="homeassistant"
                ),
                "string",
                "Home Assistant MQTT discovery prefix. Default is 'homeassistant'. Only change if you configured a different prefix in HA.",
                bounds="",
                display_name="Discovery Prefix",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["base_topic"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "base_topic", return_type=str, default="genmon"
                ),
                "string",
                "Base topic for state and command messages. Default is 'genmon'.",
                bounds="",
                display_name="Base Topic",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["device_id"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "device_id", return_type=str, default="generator"
                ),
                "string",
                "Unique device identifier used in entity IDs. Change if running multiple genmon instances.",
                bounds="",
                display_name="Device ID",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["device_name"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "device_name", return_type=str, default="Generator"
                ),
                "string",
                "Friendly device name shown in Home Assistant.",
                bounds="",
                display_name="Device Name",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["poll_interval"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "poll_interval", return_type=float, default=3.0
                ),
                "int",
                "Interval in seconds between polling genmon for status updates. Default is 3.",
                bounds="",
                display_name="Poll Interval",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["discovery_interval"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "discovery_interval", return_type=int, default=300
                ),
                "int",
                "Interval in seconds to republish discovery messages. Set to 0 to only publish on startup. Default is 300.",
                bounds="",
                display_name="Discovery Interval",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["blacklist"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "blacklist", return_type=str, default="Tiles"
                ),
                "string",
                "Comma-separated list of strings. Entities with names containing these strings will not be created. Matches against entity name, ID, and data path.",
                bounds="",
                display_name="Entity Blacklist",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["include_monitor_stats"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "include_monitor_stats", return_type=bool, default=True
                ),
                "boolean",
                "Include platform/monitor statistics (CPU, memory, etc.) as entities.",
                bounds="",
                display_name="Include Monitor Stats",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["include_weather"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "include_weather", return_type=bool, default=True
                ),
                "boolean",
                "Include weather data entities if weather is configured in genmon.",
                bounds="",
                display_name="Include Weather",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["include_logs"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "include_logs", return_type=bool, default=False
                ),
                "boolean",
                "Include log entries as sensor attributes.",
                bounds="",
                display_name="Include Logs",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["numeric_json"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "numeric_json", return_type=bool, default=True
                ),
                "boolean",
                "Use numeric JSON format when querying genmon (cleaner values without embedded units).",
                bounds="",
                display_name="Use Numeric JSON",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["monitor_address"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "monitor_address", return_type=str, default=""
                ),
                "string",
                "IP address of genmon if running on a different system. Leave empty for localhost.",
                bounds="InternetAddress",
                display_name="Genmon Address",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["cert_authority_path"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "cert_authority_path", return_type=str, default=""
                ),
                "string",
                "Full path to Certificate Authority file. Leave empty to not use SSL/TLS.",
                bounds="",
                display_name="CA Certificate Path",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["tls_version"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "tls_version", return_type=str, default="1.2"
                ),
                "list",
                "TLS version to use. Default is 1.2. Ignored if CA certificate is not used.",
                bounds="1.0,1.1,1.2",
                display_name="TLS Version",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["cert_reqs"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "cert_reqs", return_type=str, default="Required"
                ),
                "list",
                "Certificate requirements that the client imposes on the broker.",
                bounds="None,Optional,Required",
                display_name="Certificate Requirements",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["client_cert_path"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "client_cert_path", return_type=str, default=""
                ),
                "string",
                "Full path to client certificate file for MTLS.",
                bounds="",
                display_name="Client Certificate Path",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["client_key_path"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "client_key_path", return_type=str, default=""
                ),
                "string",
                "Full path to client key file for MTLS.",
                bounds="",
                display_name="Client Key Path",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["client_id"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "client_id", return_type=str, default="genmon_ha"
                ),
                "string",
                "Unique MQTT client identifier. Must be unique per genmon instance.",
                bounds="",
                display_name="Client ID",
            )
            AddOnCfg["genhomeassistant"]["parameters"]["button_passcode"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG].ReadValue(
                    "button_passcode", return_type=str, default=""
                ),
                "password",
                "Passcode for controllers that require authentication for remote commands (e.g. MEBAY). Leave empty if not required.",
                bounds="",
                display_name="Button Passcode",
            )
            # GENSLACK
            AddOnCfg["genslack"] = collections.OrderedDict()
            AddOnCfg["genslack"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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

            AddOnCfg["genslack"]["parameters"]["webhook_url"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENSLACK_CONFIG].ReadValue(
                    "webhook_url", return_type=str, default=""
                ),
                "string",
                "Full Slack Webhook URL. Retrieve from Slack custom integration configuration.",
                bounds="required HTTPAddress",
                display_name="Web Hook URL",
            )
            AddOnCfg["genslack"]["parameters"]["channel"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENSLACK_CONFIG].ReadValue(
                    "channel", return_type=str, default=""
                ),
                "string",
                "Slack channel to which the message will be sent.",
                display_name="Channel",
            )
            AddOnCfg["genslack"]["parameters"]["username"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENSLACK_CONFIG].ReadValue(
                    "username", return_type=str, default=""
                ),
                "string",
                "Slack username.",
                bounds="required username",
                display_name="Username",
            )
            AddOnCfg["genslack"]["parameters"]["icon_emoji"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENSLACK_CONFIG].ReadValue(
                    "icon_emoji", return_type=str, default=":red_circle:"
                ),
                "string",
                "Emoji that appears as the icon of the user who sent the message i.e. :red_circle:n",
                bounds="",
                display_name="Icon Emoji",
            )
            AddOnCfg["genslack"]["parameters"]["title_link"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENSLACK_CONFIG].ReadValue(
                    "title_link", return_type=str, default=""
                ),
                "string",
                "Use this to make the title of the message a link i.e. link to the genmon web interface.",
                bounds="HTTPAddress",
                display_name="Title Link",
            )

            AddOnCfg = self.AddNotificationAddOnParam(AddOnCfg, "genslack", self.GENSLACK_CONFIG)
            AddOnCfg = self.AddRetryAddOnParam(AddOnCfg, "genslack", self.GENSLACK_CONFIG)

            # GENCALLMEBOT
            AddOnCfg["gencallmebot"] = collections.OrderedDict()
            AddOnCfg["gencallmebot"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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

            AddOnCfg["gencallmebot"]["parameters"]["notification_type"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENCALLMEBOT_CONFIG].ReadValue(
                    "notification_type", return_type=str, default=""
                ),
                "list",
                "Type of CallMeBot Notifications. For more information, see http://www.callmebot.com.",
                bounds="WhatsApp,Telegram,Signal",  # Facebook, 
                display_name="Notification Type",
            )
            AddOnCfg["gencallmebot"]["parameters"]["api_key"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENCALLMEBOT_CONFIG].ReadValue(
                    "api_key", return_type=str, default=""
                ),
                "string",
                "API Key required for WhatsApp Notifications.", # and Facebook Messanger, Signal 
                display_name="API Key",
            )
            AddOnCfg["gencallmebot"]["parameters"]["username"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENCALLMEBOT_CONFIG].ReadValue(
                    "username", return_type=str, default=""
                ),
                "string",
                "CallMeBot username required for Telegram Notifications.",
                bounds="required username",
                display_name="Username",
            )
            AddOnCfg["gencallmebot"]["parameters"]["recipient_number"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENCALLMEBOT_CONFIG].ReadValue(
                    "recipient_number", return_type=str, default="+1XXXXXXXXXX"
                ),
                "string",
                "Recipient Number requried for WhatsApp Notification. Must be without spaces and start with a plus. For Signal this must be the numeric key sent to your signal account when registering with CallMeBot (in the form xxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)",
                bounds="",
                display_name="Recipient Number",
            )

            AddOnCfg = self.AddNotificationAddOnParam(AddOnCfg, "gencallmebot", self.GENCALLMEBOT_CONFIG)
            AddOnCfg = self.AddRetryAddOnParam(AddOnCfg, "gencallmebot", self.GENCALLMEBOT_CONFIG)

            # GENEXERCISE
            ControllerInfo = self.GetControllerInfo("controller").lower()
            if "evolution" in ControllerInfo or "nexus" in ControllerInfo:
                AddOnCfg["genexercise"] = collections.OrderedDict()
                AddOnCfg["genexercise"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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

                AddOnCfg["genexercise"]["parameters"]["exercise_type"] = self.CreateAddOnParam(
                    self.ConfigFiles[self.GENEXERCISE_CONFIG].ReadValue(
                        "exercise_type", return_type=str, default="Normal"
                    ),
                    "list",
                    "Quiet Exercise (reduced RPM, Hz and Voltage), Normal Exercise, Exercise with Transfer Switch Activated.",
                    bounds="Quiet,Normal,Transfer",
                    display_name="Exercise Type",
                )
                AddOnCfg["genexercise"]["parameters"][
                    "exercise_frequency"
                ] = self.CreateAddOnParam(
                    self.ConfigFiles[self.GENEXERCISE_CONFIG].ReadValue(
                        "exercise_frequency", return_type=str, default="Monthly"
                    ),
                    "list",
                    "Exercise Frequency options are Daily, Weekly, Biweekly,Monthly  or Post-Controller (immediately after the controller exercise cycle). Hour, Minute, Month, Day of Week are ignored if Post-Controller exercise frequency is enabled.",
                    bounds="Daily,Weekly,Biweekly,Monthly,Post-Controller",
                    display_name="Exercise Frequency",
                )
                AddOnCfg["genexercise"]["parameters"]["use_gen_time"] = self.CreateAddOnParam(
                    self.ConfigFiles[self.GENEXERCISE_CONFIG].ReadValue(
                        "use_gen_time", return_type=bool, default=False
                    ),
                    "boolean",
                    "Enable to use the generator time for the exercise cycle, otherwise it will use the system time.",
                    display_name="Use Generator Time",
                )
                AddOnCfg["genexercise"]["parameters"]["exercise_hour"] = self.CreateAddOnParam(
                    self.ConfigFiles[self.GENEXERCISE_CONFIG].ReadValue(
                        "exercise_hour", return_type=int, default=12
                    ),
                    "int",
                    "The hour of the exercise time. Valid input is 0 - 23.",
                    bounds="required digits range:0:23",
                    display_name="Exercise Time Hour",
                )
                AddOnCfg["genexercise"]["parameters"]["exercise_minute"] = self.CreateAddOnParam(
                    self.ConfigFiles[self.GENEXERCISE_CONFIG].ReadValue(
                        "exercise_minute", return_type=int, default=0
                    ),
                    "int",
                    "The minute of the exercise time.  Valid input is 0 - 59",
                    bounds="required digits range:0:59",
                    display_name="Exercise Time Minute",
                )
                AddOnCfg["genexercise"]["parameters"][
                    "exercise_day_of_month"
                ] = self.CreateAddOnParam(
                    self.ConfigFiles[self.GENEXERCISE_CONFIG].ReadValue(
                        "exercise_day_of_month", return_type=int, default=1
                    ),
                    "int",
                    "The day of month if monthly exercise is selected.",
                    bounds="required digits range:1:28",
                    display_name="Exercise Day of Month",
                )
                AddOnCfg["genexercise"]["parameters"][
                    "exercise_day_of_week"
                ] = self.CreateAddOnParam(
                    self.ConfigFiles[self.GENEXERCISE_CONFIG].ReadValue(
                        "exercise_day_of_week", return_type=str, default="Monday"
                    ),
                    "list",
                    "Exercise day of the week, if Weekly or Biweekly exercise frequency is selected.",
                    bounds="Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday",
                    display_name="Exercise Day of the Week",
                )
                AddOnCfg["genexercise"]["parameters"][
                    "exercise_duration"
                ] = self.CreateAddOnParam(
                    self.ConfigFiles[self.GENEXERCISE_CONFIG].ReadValue(
                        "exercise_duration", return_type=float, default=12
                    ),
                    "float",
                    "The duration of the exercise time. Note: this time does not include warmup time for Transfer type exercise cycles.",
                    bounds="number range:5:60",
                    display_name="Exercise Duration",
                )
                AddOnCfg["genexercise"]["parameters"]["exercise_warmup"] = self.CreateAddOnParam(
                    self.ConfigFiles[self.GENEXERCISE_CONFIG].ReadValue(
                        "exercise_warmup", return_type=float, default=0
                    ),
                    "float",
                    "The duration of the warmup time. Note: this time only appies to the transfer type of exercise cycle. Zero will disable the warmup period.",
                    bounds="number range:0:30",
                    display_name="Warmup Duration",
                )

            # GENEMAIL2SMS
            AddOnCfg["genemail2sms"] = collections.OrderedDict()
            AddOnCfg["genemail2sms"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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

            AddOnCfg["genemail2sms"]["parameters"]["destination"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENEMAIL2SMS_CONFIG].ReadValue(
                    "destination", return_type=str, default=""
                ),
                "string",
                "Email to SMS email recipient. Must be a valid email address",
                bounds="required email",
                display_name="Email to SMS address",
            )

            AddOnCfg = self.AddNotificationAddOnParam(
                AddOnCfg, "genemail2sms", self.GENEMAIL2SMS_CONFIG
            )

            # GENCENTRICONNECT
            AddOnCfg["gencentriconnect"] = collections.OrderedDict()
            AddOnCfg["gencentriconnect"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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

            AddOnCfg["gencentriconnect"]["parameters"]["user_id"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENCENTRICONNECT_CONFIG].ReadValue(
                    "user_id", return_type=str, default=""
                ),
                "string",
                "User ID. Note that this is a long series of numbers and dashes in this format: 36e551aa-c215-4c9b-8c70-ba7729687654",
                bounds="required min:36",
                display_name="User ID",
            )
            AddOnCfg["gencentriconnect"]["parameters"]["device_id"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENCENTRICONNECT_CONFIG].ReadValue(
                    "device_id", return_type=str, default=""
                ),
                "string",
                "Device ID. Note that this is a long series of numbers and dashes in this format: 36e551aa-c215-4c9b-8c70-ba7729687654",
                bounds="required min:36",
                display_name="Device ID",
            )
            AddOnCfg["gencentriconnect"]["parameters"]["device_auth"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENCENTRICONNECT_CONFIG].ReadValue(
                    "device_auth", return_type=str, default=""
                ),
                "password",
                "Device Auth for Centri propane tank sensor. This number is provided in the box with the sensor.",
                bounds="required min:6",
                display_name="Device Authentication Code",
            )
            AddOnCfg["gencentriconnect"]["parameters"]["poll_frequency"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENCENTRICONNECT_CONFIG].ReadValue(
                    "poll_frequency", return_type=float, default=0
                ),
                "int",
                "The duration in minutes between poll of tank data. Note this must be equal or larger than 288 minutes as the maximum number of polls per day is around 5.",
                bounds="number range:288:20000",
                display_name="Poll Frequency",
            )
            AddOnCfg["gencentriconnect"]["parameters"]["check_battery"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENCENTRICONNECT_CONFIG].ReadValue(
                    "check_battery", return_type=bool, default=False
                ),
                "boolean",
                "If enabled, and email will be sent if the battery level on the sensor is critical. Outbound email must be enabled for this to function.",
                bounds="",
                display_name="Check Sensor Battery",
            )
            AddOnCfg["gencentriconnect"]["parameters"]["check_reading"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENCENTRICONNECT_CONFIG].ReadValue(
                    "check_reading", return_type=bool, default=False
                ),
                "boolean",
                "If enabled, and email will be sent if the sensor has not performed a reading within 50 hours. Outbound email must be enabled for this to function.",
                bounds="",
                display_name="Check for Missed Readings",
            )

            # GENTANKUTIL
            AddOnCfg["gentankutil"] = collections.OrderedDict()
            AddOnCfg["gentankutil"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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

            AddOnCfg["gentankutil"]["parameters"]["tank_name"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENTANKUTIL_CONFIG].ReadValue(
                    "tank_name", return_type=str, default=""
                ),
                "string",
                "Tank name as defined in tankutility.com",
                bounds="minmax:1:50",
                display_name="Tank Name",
            )
            AddOnCfg["gentankutil"]["parameters"]["tank_name_2"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENTANKUTIL_CONFIG].ReadValue(
                    "tank_name_2", return_type=str, default=""
                ),
                "string",
                "Second tank name, if applicable",
                bounds="minmax:1:50",
                display_name="Tank Name 2 (Optional)",
            )
            AddOnCfg["gentankutil"]["parameters"]["username"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENTANKUTIL_CONFIG].ReadValue(
                    "username", return_type=str, default=""
                ),
                "string",
                "Username at tankutility.com",
                bounds="required email",
                display_name="Username",
            )
            AddOnCfg["gentankutil"]["parameters"]["password"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENTANKUTIL_CONFIG].ReadValue(
                    "password", return_type=str, default=""
                ),
                "password",
                "Password at tankutility.com",
                bounds="minmax:4:50",
                display_name="Password",
            )
            AddOnCfg["gentankutil"]["parameters"]["poll_frequency"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENTANKUTIL_CONFIG].ReadValue(
                    "poll_frequency", return_type=float, default=0
                ),
                "float",
                "The duration in minutes between poll of tank data.",
                bounds="number",
                display_name="Poll Frequency",
            )
            AddOnCfg["gentankutil"]["parameters"]["check_battery"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENTANKUTIL_CONFIG].ReadValue(
                    "check_battery", return_type=bool, default=False
                ),
                "boolean",
                "If enabled, and email will be sent if the battery level on the sensor is critical. Outbound email must be enabled for this to function.",
                bounds="",
                display_name="Check Sensor Battery",
            )
            AddOnCfg["gentankutil"]["parameters"]["check_reading"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENTANKUTIL_CONFIG].ReadValue(
                    "check_reading", return_type=bool, default=False
                ),
                "boolean",
                "If enabled, and email will be sent if the sensor has not performed a reading within 50 hours. Outbound email must be enabled for this to function.",
                bounds="",
                display_name="Check for Missed Readings",
            )

            # GENNEEVO
            AddOnCfg["genneevo"] = collections.OrderedDict()
            AddOnCfg["genneevo"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
                "enable", return_type=bool, section="genneevo", default=False
            )
            AddOnCfg["genneevo"]["title"] = "Nee Vo Tank Fuel Monitor"
            AddOnCfg["genneevo"][
                "description"
            ] = "Integrates Nee-Vo propane tank sensor data"
            AddOnCfg["genneevo"]["icon"] = "neevo"
            AddOnCfg["genneevo"][
                "url"
            ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genneevopy-optional"
            AddOnCfg["genneevo"]["parameters"] = collections.OrderedDict()
            AddOnCfg["genneevo"]["parameters"]["tank_name"] = self.CreateAddOnParam(
            self.ConfigFiles[self.GENNEEVO_CONFIG].ReadValue(
                    "tank_name", return_type=str, default=""
                ),
                "string",
                "Tank name",
                bounds="minmax:1:50",
                display_name="Tank Name",
            )
            AddOnCfg["genneevo"]["parameters"]["username"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENNEEVO_CONFIG].ReadValue(
                    "username", return_type=str, default=""
                ),
                "string",
                "Username from Nee-vo app",
                bounds="required email",
                display_name="Username",
            )
            AddOnCfg["genneevo"]["parameters"]["password"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENNEEVO_CONFIG].ReadValue(
                    "password", return_type=str, default=""
                ),
                "password",
                "Password from Nee-vo app",
                bounds="minmax:4:50",
                display_name="Password",
            )
            AddOnCfg["genneevo"]["parameters"]["capacity"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENNEEVO_CONFIG].ReadValue(
                    "capacity", return_type=int, default=0
                ),
                "int",
                "Tank capacity in gallons. Set to 0 to use on line data.",
                bounds="number",
                display_name="Tank Capacity (gallons)",
            )
            AddOnCfg["genneevo"]["parameters"]["serial_number"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENNEEVO_CONFIG].ReadValue(
                    "serial_number", return_type=str, default=""
                ),
                "string",
                "Optional: only use a specific tank by serial number (leave blank for first tank)",
                bounds="",
                display_name="Serial Number",
            )
            AddOnCfg["genneevo"]["parameters"]["poll_frequency"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENNEEVO_CONFIG].ReadValue(
                    "poll_frequency", return_type=float, default=0
                ),
                "float",
                "The duration in minutes between poll of tank data.",
                bounds="number",
                display_name="Poll Frequency",
            )
            # GENTANKDIY
            AddOnCfg["gentankdiy"] = collections.OrderedDict()
            AddOnCfg["gentankdiy"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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

            AddOnCfg["gentankdiy"]["parameters"]["poll_frequency"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENTANKDIY_CONFIG].ReadValue(
                    "poll_frequency", return_type=float, default=0
                ),
                "float",
                "The duration in minutes between poll of tank data.",
                bounds="number",
                display_name="Poll Frequency",
            )
            AddOnCfg["gentankdiy"]["parameters"]["gauge_type"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENTANKDIY_CONFIG].ReadValue(
                    "gauge_type", return_type=str, default="1"
                ),
                "list",
                "DIY sensor type. Valid options are Type 1 and Type 2.",
                bounds="1,2",
                display_name="Sensor Type",
            )

            # GENALEXA
            AddOnCfg["genalexa"] = collections.OrderedDict()
            AddOnCfg["genalexa"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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

            AddOnCfg["genalexa"]["parameters"]["name"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENALEXA_CONFIG].ReadValue("name", return_type=str, default=""),
                "string",
                "Name to call the generator device, i.e. 'generator'",
                bounds="minmax:4:50",
                display_name="Name for generator device",
            )

            # GENSNMP
            AddOnCfg["gensnmp"] = collections.OrderedDict()
            AddOnCfg["gensnmp"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
                "enable", return_type=bool, section="gensnmp", default=False
            )
            AddOnCfg["gensnmp"]["title"] = "SNMP Support"
            AddOnCfg["gensnmp"]["description"] = "Allow Genmon to respond to SNMP requests"
            AddOnCfg["gensnmp"]["icon"] = "snmp"
            AddOnCfg["gensnmp"][
                "url"
            ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensnmppy-optional"
            AddOnCfg["gensnmp"]["parameters"] = collections.OrderedDict()

            AddOnCfg["gensnmp"]["parameters"]["poll_frequency"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENSNMP_CONFIG].ReadValue(
                    "poll_frequency", return_type=float, default=2.0
                ),
                "float",
                "The time in seconds between requesting status from genmon. The default value is 2 seconds.",
                bounds="number",
                display_name="Poll Interval",
            )
            AddOnCfg["gensnmp"]["parameters"]["enterpriseid"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENSNMP_CONFIG].ReadValue(
                    "enterpriseid", return_type=int, default=58399
                ),
                "int",
                "The enterprise ID used in the SNMP Object Identifier (OID). The genmon SNMP enterprise ID is 58399.",
                bounds="required digits",
                display_name="Enterprise ID",
            )
            AddOnCfg["gensnmp"]["parameters"]["community"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENSNMP_CONFIG].ReadValue(
                    "community", return_type=str, default="public"
                ),
                "string",
                "SNMP Community string",
                bounds="minmax:4:50",
                display_name="SNMP Community",
            )
            AddOnCfg["gensnmp"]["parameters"]["use_numeric"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENSNMP_CONFIG].ReadValue(
                    "use_numeric", return_type=bool, default=False
                ),
                "boolean",
                "If enabled will return numeric values (no units) in the Status, Maintenance (Evo/Nexus only) and Outage data.",
                bounds="",
                display_name="Numerics only",
            )
            AddOnCfg["gensnmp"]["parameters"]["use_integer"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENSNMP_CONFIG].ReadValue(
                    "use_integer", return_type=bool, default=False
                ),
                "boolean",
                "If enabled, integer values (no units) will be returned when applicable in the Status, Maintenance (Evo/Nexus only) and Outage data. Enabling this value also enables 'Use Numerics'. Floating point numberic values are returned as strings",
                bounds="",
                display_name="Force Integers",
            )

            # GENTEMP
            AddOnCfg["gentemp"] = collections.OrderedDict()
            AddOnCfg["gentemp"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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

            AddOnCfg["gentemp"]["parameters"]["poll_frequency"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENTEMP_CONFIG].ReadValue(
                    "poll_frequency", return_type=float, default=2.0
                ),
                "float",
                "The time in seconds that the temperature data is polled. The default value is 2 seconds.",
                bounds="number",
                display_name="Poll Interval",
            )
            AddOnCfg["gentemp"]["parameters"]["use_metric"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENTEMP_CONFIG].ReadValue(
                    "use_metric", return_type=bool, default=False
                ),
                "boolean",
                "enable to use Celsius, disable for Fahrenheit",
                bounds="",
                display_name="Use Metric",
            )
            AddOnCfg["gentemp"]["parameters"]["blacklist"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENTEMP_CONFIG].ReadValue(
                    "blacklist", return_type=str, default=""
                ),
                "string",
                "Comma separated blacklist. If these vaues are found in 1 wire temperature sensor device names the sensor will be ignored.",
                bounds="",
                display_name="Sensor Device Blacklist",
            )
            AddOnCfg["gentemp"]["parameters"]["device_labels"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENTEMP_CONFIG].ReadValue(
                    "device_labels", return_type=str, default=""
                ),
                "string",
                "Comma separated list of sensor names. These names will be displayed for each sensor. DS18B20 sensors are first, then type K thermocouples. Blacklisted devices are skipped.",
                bounds="",
                display_name="Sensor Names",
            )
            AddOnCfg["gentemp"]["parameters"]["device_nominal_values"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENTEMP_CONFIG].ReadValue(
                    "device_nominal_values", return_type=str, default=""
                ),
                "string",
                "Comma separated list of nominal temperature values for the sensor. Nominal values help determine where the gauge green area ends and the yellow begins. The order of these values must match the order of the Sensor Names. Leave blank to disable External Temp Sensor gauges.",
                bounds="",
                display_name="Sensor Nominal Values",
            )
            AddOnCfg["gentemp"]["parameters"]["device_max_values"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENTEMP_CONFIG].ReadValue(
                    "device_max_values", return_type=str, default=""
                ),
                "string",
                "Comma separated list of maximum temperature values for the sensor. This is the maximum gauge value. The order of these values must match the order of the Sensor Names. Leave blank to disable External Temp Sensor gauges.",
                bounds="",
                display_name="Sensor Maximum Values",
            )
            AddOnCfg["gentemp"]["parameters"]["device_min_values"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENTEMP_CONFIG].ReadValue(
                    "device_min_values", return_type=str, default=""
                ),
                "string",
                "Comma separated list of minimum temperature values for the sensor. This is the minimum gauge value. The order of these values must match the order of the Sensor Names. Leave blank to set all sensors minimum value to zero.",
                bounds="",
                display_name="Sensor Minimum Values",
            )
            # GENSENSORHAT
            AddOnCfg["gencthat"] = collections.OrderedDict()
            AddOnCfg["gencthat"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
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

            AddOnCfg["gencthat"]["parameters"]["poll_frequency"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENCTHAT_CONFIG].ReadValue(
                    "poll_frequency", return_type=float, default=2.0
                ),
                "float",
                "The time in seconds that the sensors are polled. The default value is 15 seconds.",
                bounds="number",
                display_name="Poll Interval",
            )
            AddOnCfg["gencthat"]["parameters"]["strict"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENCTHAT_CONFIG].ReadValue(
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
                        + "<br/><font color='red'>The required libraries for this add on are not installed. They will be installaled on the when the proram is restarted.</font>"
                    )

                AddOnCfg["genmopeka"] = collections.OrderedDict()
                AddOnCfg["genmopeka"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
                    "enable", return_type=bool, section="genmopeka", default=False
                )
                AddOnCfg["genmopeka"]["title"] = "Mopeka Pro Propane Tank Sensor"

                AddOnCfg["genmopeka"]["description"] = Description
                AddOnCfg["genmopeka"]["icon"] = "mopeka"
                AddOnCfg["genmopeka"][
                    "url"
                ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genmopekapy-optional"
                AddOnCfg["genmopeka"]["parameters"] = collections.OrderedDict()

                AddOnCfg["genmopeka"]["parameters"]["poll_frequency"] = self.CreateAddOnParam(
                    self.ConfigFiles[self.GENMOPEKA_CONFIG].ReadValue(
                        "poll_frequency", return_type=float, default=60
                    ),
                    "float",
                    "The time in minutes that the sensors are polled. The default value is 60 minutes.",
                    bounds="number",
                    display_name="Poll Interval",
                )
                AddOnCfg["genmopeka"]["parameters"]["tank_address"] = self.CreateAddOnParam(
                    self.ConfigFiles[self.GENMOPEKA_CONFIG].ReadValue(
                        "tank_address", return_type=str, default=""
                    ),
                    "string",
                    "This value is MAC address of the sensor. It must be in a format using hex numbers separated by colons (i.e. 9a:03:2b:67:25:12). Multiple tank sensors (up to 4) may be used with commas between each address",
                    bounds="",
                    display_name="Sensor Address",
                )
                AddOnCfg["genmopeka"]["parameters"]["tank_type"] = self.CreateAddOnParam(
                    self.ConfigFiles[self.GENMOPEKA_CONFIG].ReadValue(
                        "tank_type", return_type=str, default="1"
                    ),
                    "list",
                    "Type of tank used. If Custom is used then Max and Min values must be setup in /etc/genmon/genmopeka.conf",
                    bounds="20_LB,30_LB,40_LB,100_LB,200_LB,120_GAL,120_GAL_HORIZ,250_GAL,500_GAL,1000_GAL,Custom",
                    display_name="Tank Size",
                )
                AddOnCfg["genmopeka"]["parameters"]["send_notices"] = self.CreateAddOnParam(
                    self.ConfigFiles[self.GENMOPEKA_CONFIG].ReadValue(
                        "send_notices", return_type=bool, default=False
                    ),
                    "boolean",
                    "Send email notices if unable to communicate with the senor or the sensor battery is low. Note: outbound email must be setup for this to work.",
                    bounds="",
                    display_name="Send Notices",
                )

            # GENHALINK - Native Home Assistant Integration
            AddOnCfg["genhalink"] = collections.OrderedDict()
            AddOnCfg["genhalink"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
                "enable", return_type=bool, section="genhalink", default=False
            )
            AddOnCfg["genhalink"]["title"] = "Home Assistant Integration (Native)"
            AddOnCfg["genhalink"][
                "description"
            ] = "Native Home Assistant integration via REST/WebSocket API. No MQTT broker required."
            AddOnCfg["genhalink"]["icon"] = "homeassistant"
            AddOnCfg["genhalink"][
                "url"
            ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genhalinkpy-optional"
            AddOnCfg["genhalink"]["parameters"] = collections.OrderedDict()

            AddOnCfg["genhalink"]["parameters"]["port"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHALINK_CONFIG].ReadValue(
                    "port", return_type=int, default=9083
                ),
                "int",
                "Port for the REST/WebSocket API server.",
                bounds="required digits range:1024:65535",
                display_name="API Server Port",
            )
            genhalink_api_key = self.ConfigFiles[self.GENHALINK_CONFIG].ReadValue(
                "api_key", return_type=str, default=""
            )
            if not genhalink_api_key:
                genhalink_api_key = str(uuid.uuid4())
                self.ConfigFiles[self.GENHALINK_CONFIG].WriteValue("api_key", genhalink_api_key)
                self.LogError("Auto-generated API key for genhalink")
            AddOnCfg["genhalink"]["parameters"]["api_key"] = self.CreateAddOnParam(
                genhalink_api_key,
                "readonly",
                "API key for authentication (auto-generated). Copy this value into Home Assistant when adding the integration.",
                bounds="",
                display_name="API Key (read-only)",
            )
            AddOnCfg["genhalink"]["parameters"]["poll_interval"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHALINK_CONFIG].ReadValue(
                    "poll_interval", return_type=float, default=3.0
                ),
                "int",
                "Interval in seconds between polling genmon for status updates. Default is 3.",
                bounds="number",
                display_name="Poll Interval",
            )
            AddOnCfg["genhalink"]["parameters"]["blacklist"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHALINK_CONFIG].ReadValue(
                    "blacklist", return_type=str, default="Tiles"
                ),
                "string",
                "Comma-separated keywords to exclude from the API. Matches any data path containing the keyword (case-insensitive). Top-level sections: Status, Maintenance, Outage, Monitor, Tiles. Examples: 'Tiles' (UI tiles), 'Weather' (weather data), 'Platform Stats' (CPU/memory), 'Last Log Entries' (log snippets). You can also target specific values like 'Serial Number' or 'CRC Errors'.",
                bounds="",
                display_name="Excluded Data Paths",
            )
            AddOnCfg["genhalink"]["parameters"]["include_monitor_stats"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHALINK_CONFIG].ReadValue(
                    "include_monitor_stats", return_type=bool, default=True
                ),
                "boolean",
                "Include monitor/platform statistics (CPU temp, WiFi, memory).",
                bounds="",
                display_name="Include Monitor Stats",
            )
            AddOnCfg["genhalink"]["parameters"]["include_weather"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHALINK_CONFIG].ReadValue(
                    "include_weather", return_type=bool, default=True
                ),
                "boolean",
                "Include weather data if available.",
                bounds="",
                display_name="Include Weather",
            )
            AddOnCfg["genhalink"]["parameters"]["zeroconf_enabled"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHALINK_CONFIG].ReadValue(
                    "zeroconf_enabled", return_type=bool, default=True
                ),
                "boolean",
                "Enable Zeroconf/mDNS broadcasting so Home Assistant can auto-discover this generator. Disable for manual/fixed IP setup only.",
                bounds="",
                display_name="Zeroconf Discovery",
            )


            # GENHUBITAT - Native Hubitat Integration
            AddOnCfg["genhubitat"] = collections.OrderedDict()
            AddOnCfg["genhubitat"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
                "enable", return_type=bool, section="genhubitat", default=False
            )
            AddOnCfg["genhubitat"]["title"] = "Native Hubitat Integration via REST/WebSocket API"
            AddOnCfg["genhubitat"][
                "description"
            ] = "Native Hubitat integration via REST/WebSocket API. No MQTT broker required."
            AddOnCfg["genhubitat"]["icon"] = "hubitat"
            AddOnCfg["genhubitat"][
                "url"
            ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genhubitatpy-optional"
            AddOnCfg["genhubitat"]["parameters"] = collections.OrderedDict()

            AddOnCfg["genhubitat"]["parameters"]["port"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHUBITAT_CONFIG].ReadValue(
                    "port", return_type=int, default=9084
                ),
                "int",
                "Port for the REST/WebSocket API server.",
                bounds="required digits range:1024:65535",
                display_name="API Server Port",
            )
            genhubitat_api_key = self.ConfigFiles[self.GENHUBITAT_CONFIG].ReadValue(
                "api_key", return_type=str, default=""
            )
            if not genhubitat_api_key:
                genhubitat_api_key = str(uuid.uuid4())
                self.ConfigFiles[self.GENHUBITAT_CONFIG].WriteValue("api_key", genhubitat_api_key)
                self.LogError("Auto-generated API key for genhubitat")
            AddOnCfg["genhubitat"]["parameters"]["api_key"] = self.CreateAddOnParam(
                genhubitat_api_key,
                "readonly",
                "API key for authentication (auto-generated). Copy this value into Hubitat when adding the integration.",
                bounds="",
                display_name="API Key (read-only)",
            )
            AddOnCfg["genhubitat"]["parameters"]["poll_interval"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHUBITAT_CONFIG].ReadValue(
                    "poll_interval", return_type=float, default=3.0
                ),
                "int",
                "Interval in seconds between polling genmon for status updates. Default is 3.",
                bounds="number",
                display_name="Poll Interval",
            )
            AddOnCfg["genhubitat"]["parameters"]["blacklist"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHUBITAT_CONFIG].ReadValue(
                    "blacklist", return_type=str, default="Tiles"
                ),
                "string",
                "Comma-separated keywords to exclude from the API, matching any data path containing the keyword (case-insensitive). For the noisy diagnostics that dominate the Hubitat event count (CPU temperature/usage, memory, disk, WiFi signal), use the 'Include Monitor Stats' toggle instead; for outside temperature and conditions, use 'Include Weather'. Use this field for individual values those toggles don't cover, such as 'Battery Voltage' or 'Battery Charger Current', or to drop a single field while keeping the rest of the monitor stats. The default 'Tiles' excludes the web UI's tile data, which Hubitat does not use.",
                bounds="",
                display_name="Excluded Data Paths",
            )
            AddOnCfg["genhubitat"]["parameters"]["include_monitor_stats"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHUBITAT_CONFIG].ReadValue(
                    "include_monitor_stats", return_type=bool, default=True
                ),
                "boolean",
                "Include monitor/platform statistics (CPU temp, WiFi, memory).",
                bounds="",
                display_name="Include Monitor Stats",
            )
            AddOnCfg["genhubitat"]["parameters"]["include_weather"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENHUBITAT_CONFIG].ReadValue(
                    "include_weather", return_type=bool, default=True
                ),
                "boolean",
                "Include weather data if available.",
                bounds="",
                display_name="Include Weather",
            )

        except Exception as e1:
            self.LogErrorLine("Error in GetAddOns: " + str(e1))

        # GENOTODATA
        if sys.version_info >= (3, 7):
            Description = "Support Otodata TM6030 Propane Tank Sensor"
            try:
                import bleak
            except Exception as e1:
                Description = (
                    Description
                    + "<br/><font color='red'>The required libraries for this add on "
                    "are not installed. They will be installaled on the when the proram is restarted.</font>"
                )

            AddOnCfg["genotodata"] = collections.OrderedDict()
            AddOnCfg["genotodata"]["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
                "enable", return_type=bool, section="genotodata", default=False
            )
            AddOnCfg["genotodata"]["title"] = "Otodata TM6030 Propane Tank Sensor"
            AddOnCfg["genotodata"]["description"] = Description
            AddOnCfg["genotodata"]["icon"] = "otodata"
            AddOnCfg["genotodata"]["url"] = (
                "https://github.com/jgyates/genmon/wiki/"
                "1----Software-Overview#genotodatapy-optional"
            )
            AddOnCfg["genotodata"]["parameters"] = collections.OrderedDict()

            AddOnCfg["genotodata"]["parameters"]["tank_name"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENOTODATA_CONFIG].ReadValue(
                    "tank_name", return_type=str, default="Propane Tank"
                ),
                "string",
                "Display name for this tank in the genmon web interface.",
                bounds="",
                display_name="Tank Name",
            )
            AddOnCfg["genotodata"]["parameters"]["capacity"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENOTODATA_CONFIG].ReadValue(
                    "capacity", return_type=int, default=0
                ),
                "int",
                "Tank capacity in gallons. Set to 0 to omit from genmon data.",
                bounds="number",
                display_name="Tank Capacity (gallons)",
            )
            AddOnCfg["genotodata"]["parameters"]["poll_frequency"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENOTODATA_CONFIG].ReadValue(
                    "poll_frequency", return_type=int, default=5
                ),
                "int",
                "The time in minutes between BLE scan cycles. Default is 5 minutes.",
                bounds="number",
                display_name="Poll Interval (minutes)",
            )
            AddOnCfg["genotodata"]["parameters"]["scan_time"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENOTODATA_CONFIG].ReadValue(
                    "scan_time", return_type=float, default=30.0
                ),
                "float",
                "Seconds to listen for BLE advertisements per scan cycle. "
                "Increase if the sensor is far from the Pi.",
                bounds="number",
                display_name="Scan Duration (seconds)",
            )
            AddOnCfg["genotodata"]["parameters"]["mac_address"] = self.CreateAddOnParam(
                self.ConfigFiles[self.GENOTODATA_CONFIG].ReadValue(
                    "mac_address", return_type=str, default=""
                ),
                "string",
                "Optional: restrict readings to a specific sensor MAC address "
                "(e.g. aa:bb:cc:dd:ee:ff). Leave blank to use the first Otodata device found.",
                bounds="",
                display_name="Sensor MAC Address",
            )

        return AddOnCfg

    # ------------ AddNotificationAddOnParam ----------------------------------------
    def AddNotificationAddOnParam(self, AddOnCfg, addon_name, config_file):

        try:
            AddOnCfg[addon_name]["parameters"]["notify_error"] = self.CreateAddOnParam(
                self.ConfigFiles[config_file].ReadValue(
                    "notify_error", return_type=bool, default=True
                ),
                "boolean",
                "Send messages for errors (Generator Alarms).",
                display_name="Notify for Errors",
            )
            AddOnCfg[addon_name]["parameters"]["notify_warn"] = self.CreateAddOnParam(
                self.ConfigFiles[config_file].ReadValue(
                    "notify_warn", return_type=bool, default=True
                ),
                "boolean",
                "Send messages for warnings (service due, fuel low).",
                display_name="Notify for Warnings",
            )
            AddOnCfg[addon_name]["parameters"]["notify_info"] = self.CreateAddOnParam(
                self.ConfigFiles[config_file].ReadValue(
                    "notify_info", return_type=bool, default=True
                ),
                "boolean",
                "Send messages for information (switch state change, engine state change, exercising).",
                display_name="Notify for Information",
            )
            AddOnCfg[addon_name]["parameters"]["notify_outage"] = self.CreateAddOnParam(
                self.ConfigFiles[config_file].ReadValue(
                    "notify_outage", return_type=bool, default=True
                ),
                "boolean",
                "Send messages for outages.",
                display_name="Notify for Outages",
            )
            AddOnCfg[addon_name]["parameters"]["notify_sw_update"] = self.CreateAddOnParam(
                self.ConfigFiles[config_file].ReadValue(
                    "notify_sw_update", return_type=bool, default=True
                ),
                "boolean",
                "Send messages for software updates.",
                display_name="Notify for Software Updates",
            )
            AddOnCfg[addon_name]["parameters"]["notify_pi_state"] = self.CreateAddOnParam(
                self.ConfigFiles[config_file].ReadValue(
                    "notify_pi_state", return_type=bool, default=True
                ),
                "boolean",
                "Send messages for Pi hardware sensor status (CPU throttling, undervoltage, etc).",
                display_name="Notify for Pi Hardware Issues",
            )
        except Exception as e1:
            self.LogErrorLine("Error in AddNotificationAddOnParam: " + str(e1))

        return AddOnCfg

    # ------------ AddRetryAddOnParam -----------------------------------------------
    def AddRetryAddOnParam(self, AddOnCfg, addon_name, config_file):

        try:
            AddOnCfg[addon_name]["parameters"]["max_retry_time"] = self.CreateAddOnParam(
                value=self.ConfigFiles[config_file].ReadValue(
                    "max_retry_time", return_type=int, default=600
                ),
                type="int",
                description="Maximum number of seconds to retry a failed message before dropping the message.",
                display_name="Max Retry Duration (seconds)",
            )
            AddOnCfg[addon_name]["parameters"]["default_wait"] = self.CreateAddOnParam(
                value=self.ConfigFiles[config_file].ReadValue(
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
            self.LogErrorLine("Error in AddRetryAddOnParam: " + str(e1))
        return AddOnCfg

    # -------------------------------------------------------------------------------
    def CreateAddOnParam(self, 
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
    def GetAddOnSettings(self):
        try:
            return self.GetAddOns()
        except Exception as e1:
            self.LogErrorLine("Error in GetAddOnSettings: " + str(e1))
            return {}

    # -------------------------------------------------------------------------------
    def SaveAddOnSettings(self, query_string):
        try:
            if query_string == None:
                self.LogError("Empty query string in SaveAddOnSettings")
                return

            settings = json.loads(query_string)
            if not len(settings):
                return  # nothing to change

            ConfigDict = {
                "genmon": self.ConfigFiles[self.GENMON_CONFIG],
                "mymail": self.ConfigFiles[self.MAIL_CONFIG],
                "genloader": self.ConfigFiles[self.GENLOADER_CONFIG],
                "gensms": self.ConfigFiles[self.GENSMS_CONFIG],
                "gensms_modem": self.ConfigFiles[self.MYMODEM_CONFIG],
                "genpushover": self.ConfigFiles[self.GENPUSHOVER_CONFIG],
                "genmqtt": self.ConfigFiles[self.GENMQTT_CONFIG],
                "genmqttin": self.ConfigFiles[self.GENMQTTIN_CONFIG],
                "genslack": self.ConfigFiles[self.GENSLACK_CONFIG],
                "gencallmebot": self.ConfigFiles[self.GENCALLMEBOT_CONFIG],
                "genlog": self.ConfigFiles[self.GENLOADER_CONFIG],
                "gensyslog": self.ConfigFiles[self.GENLOADER_CONFIG],
                "gengpio": self.ConfigFiles[self.GENLOADER_CONFIG],
                "gengpioin": self.ConfigFiles[self.GENGPIOIN_CONFIG],
                "gengpioledblink": self.ConfigFiles[self.GENGPIOLEDBLINK_CONFIG],
                "genexercise": self.ConfigFiles[self.GENEXERCISE_CONFIG],
                "genemail2sms": self.ConfigFiles[self.GENEMAIL2SMS_CONFIG],
                "gentankutil": self.ConfigFiles[self.GENTANKUTIL_CONFIG],
                "genneevo": self.ConfigFiles[self.GENNEEVO_CONFIG],
                "gencentriconnect": self.ConfigFiles[self.GENCENTRICONNECT_CONFIG],
                "gentankdiy": self.ConfigFiles[self.GENTANKDIY_CONFIG],
                "genalexa": self.ConfigFiles[self.GENALEXA_CONFIG],
                "gensnmp": self.ConfigFiles[self.GENSNMP_CONFIG],
                "gentemp": self.ConfigFiles[self.GENTEMP_CONFIG],
                "gencthat": self.ConfigFiles[self.GENCTHAT_CONFIG],
                "genmopeka": self.ConfigFiles[self.GENMOPEKA_CONFIG],
                "genotodata": self.ConfigFiles[self.GENOTODATA_CONFIG],
                "gensms_voip": self.ConfigFiles[self.GENSMS_VOIP_CONFIG],
                "genhomeassistant": self.ConfigFiles[self.GENHOMEASSISTANT_CONFIG],
                "genhalink": self.ConfigFiles[self.GENHALINK_CONFIG],
                "genhubitat": self.ConfigFiles[self.GENHUBITAT_CONFIG],
            }

            for module, entries in settings.items():  # module
                ParameterConfig = ConfigDict.get(module, None)
                if ParameterConfig == None:
                    self.LogError("Invalid module in SaveAddOnSettings: " + module)
                    continue
                # Find if it needs to be enabled / disabled or if there are parameters
                for basesettings, basevalues in entries.items():  # base settings
                    if basesettings == "enable":
                        self.ConfigFiles[self.GENLOADER_CONFIG].WriteValue(
                            "enable", basevalues, section=module
                        )
                        # TODO This may not be needed now
                        if module in ["gentankutil", "gentankdiy", "genneevo"]:
                            # update genmon.conf also to let it know that it should watch for external fuel data
                            self.ConfigFiles[self.GENMON_CONFIG].WriteValue(
                                "use_external_fuel_data", basevalues, section="genmon"
                            )

                        if module == "genhalink" and basevalues.lower() == "true":
                            # Auto-generate API key if empty when addon is enabled
                            current_key = self.ConfigFiles[self.GENHALINK_CONFIG].ReadValue(
                                "api_key", return_type=str, default=""
                            )
                            if not current_key:
                                new_key = str(uuid.uuid4())
                                self.ConfigFiles[self.GENHALINK_CONFIG].WriteValue("api_key", new_key)
                                self.LogError("Auto-generated API key for genhalink")

                        if module == "genhubitat" and basevalues.lower() == "true":
                            # Auto-generate API key if empty when addon is enabled
                            current_key = self.ConfigFiles[self.GENHUBITAT_CONFIG].ReadValue(
                                "api_key", return_type=str, default=""
                            )
                            if not current_key:
                                new_key = str(uuid.uuid4())
                                self.ConfigFiles[self.GENHUBITAT_CONFIG].WriteValue("api_key", new_key)
                                self.LogError("Auto-generated API key for genhubitat")
                    if basesettings == "parameters":
                        for params, paramvalue in basevalues.items():
                            if module == "genlog" and params == "Log File Name":
                                self.ConfigFiles[self.GENLOADER_CONFIG].WriteValue(
                                    "args", "-f " + paramvalue, section=module
                                )
                            else:
                                ParameterConfig.WriteValue(params, paramvalue)

            self.Restart()
            return
        except Exception as e1:
            self.LogErrorLine("Error in SaveAddOnSettings: " + str(e1))
            return

    # -------------------------------------------------------------------------------
    # This will reboot the pi
    def Reboot(self):

        subprocess.run(["sudo", "reboot"])

    # -------------------------------------------------------------------------------
    # This will shutdown the pi
    def Shutdown(self):

        subprocess.run(["sudo", "shutdown", "-h"])

    # -------------------------------------------------------------------------------
    # This will restart the Flask App
    def Restart(self):

        try:
            self.Restarting = True
            threading.Thread(target=self._do_restart, daemon=True).start()
        except Exception as e1:
            self.LogErrorLine("Error in Restart: " + str(e1))

    # -------------------------------------------------------------------------------
    # Separate thread to restart so the flask request will return
    def _do_restart(self):
        time.sleep(2)
        if not self.RunBashScript("startgenmon.sh restart -c " + self.ConfigFilePath):
            self.LogError("Error in Restart")

    # -------------------------------------------------------------------------------
    def Update(self):
        # update
        try:
            if not self.RunBashScript("genmonmaint.sh -u -n", log = True):
                self.LogError("Error in Update")
            # now restart
            self.Restart()
        except Exception as e1:
            self.LogErrorLine("Error in Update: " + str(e1))

    # -------------------------------------------------------------------------------
    def GitHubCodeHash(self):
        try:
            output, bSuccess = self.RunBashScript("genmonmaint.sh -v", log = False, return_output=True)
            if not bSuccess:
                self.LogError("Error in Update")
                return "Unknown"
            return output.strip()
        except Exception as e1:
            self.LogErrorLine("Error in Update: " + str(e1))
            return "Unknown"

    # -------------------------------------------------------------------------------
    def GetLogs(self):
        # update
        if not self.RunBashScript("genmonmaint.sh -l " + self.loglocation):  # archive logs
            self.LogError("Error in GetLogs")

    # -------------------------------------------------------------------------------
    def Backup(self):
        # update
        if not self.RunBashScript("genmonmaint.sh -b -c " + self.ConfigFilePath):  # backup
            self.LogError("Error in Backup")

    # -------------------------------------------------------------------------------
    def RestoreBackup(self, ArchivePath):
        return self.RunBashScript("genmonmaint.sh -t " + ArchivePath + " -c " + self.ConfigFilePath)

    # -------------------------------------------------------------------------------
    def RunBashScript(self, ScriptName, log = False, return_output = False):

        try:

            if self.OperatingSystem == "windows":
                ScriptName = ScriptName.replace(".sh", ".bat")
                pathtoscript = os.path.dirname(os.path.realpath(__file__))
                command = os.path.join(pathtoscript, "OtherApps", "win",ScriptName)
            else:
                pathtoscript = os.path.dirname(os.path.realpath(__file__))
                script = os.path.join(pathtoscript, ScriptName)
                command = "/bin/bash "
                command = command + script
            self.LogError("Script: " + command)

            success = True
            try:
                output = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as e:
                # the script ran but returned an error, keep its output for the log
                output = e.output
                success = False

            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            if log or not success:
                self.LogError(command + ": \n" + output)
            if return_output:
                return output, success
            return success

        except Exception as e1:
            self.LogErrorLine("Error in RunBashScript: (" + ScriptName + ") : " + str(e1))
            if return_output:
                return "", False
            return False

    # -------------------------------------------------------------------------------
    def csrf_check(self):
        """Block cross-origin state-changing requests (CSRF protection).

        Every non-GET request must carry a valid X-CSRFToken header. If the
        browser also sends Origin/Referer, it must match this host.

        Reverse-proxy aware: trusts X-Forwarded-Host so that the browser's
        Origin (the public domain) matches even when Flask sees the backend
        address as request.host.
        """
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return  # safe methods; state-changing /cmd/ commands reject GET in command()
        # Login endpoints are protected by credentials, not session — exempt from CSRF
        if request.endpoint in ("do_admin_login", "passkey_login_begin", "passkey_login_complete", "mfa_auth"):
            return
        expected = self.CSRFToken()
        supplied = request.headers.get("X-CSRFToken", "")
        if not expected or not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
            self.LogError("CSRF blocked: missing or invalid X-CSRFToken header: " + request.path)
            return jsonify({"error": "CSRF validation failed"}), 403
        origin = request.headers.get("Origin")
        referer = request.headers.get("Referer")
        if not origin and not referer:
            return  # non-browser client (integration, script) with a valid token
        # Build the set of hosts we trust: the direct host Flask sees plus
        # any X-Forwarded-Host a reverse proxy (Caddy, nginx, etc.) provides.
        trusted_hosts = {request.host}
        fwd_host = request.headers.get("X-Forwarded-Host")
        if fwd_host:
            # X-Forwarded-Host may be a comma-separated list; trust all entries
            for h in fwd_host.split(","):
                trusted_hosts.add(h.strip())
        if origin:
            parsed = urlparse(origin)
            if parsed.netloc not in trusted_hosts:
                self.LogError("CSRF blocked: Origin mismatch: " + origin
                         + " (trusted: " + ", ".join(sorted(trusted_hosts)) + ")")
                return jsonify({"error": "Cross-origin request blocked"}), 403
        elif referer:
            parsed = urlparse(referer)
            if parsed.netloc not in trusted_hosts:
                self.LogError("CSRF blocked: Referer mismatch: " + referer
                         + " (trusted: " + ", ".join(sorted(trusted_hosts)) + ")")
                return jsonify({"error": "Cross-origin request blocked"}), 403

    # -------------------------------------------------------------------------------
    def add_header(self, r):
        """
        Set cache headers (long-lived for versioned static assets, no-store for
        everything else) and add security headers.
        """
        if self._is_static_asset_request(request.path):
            # Versioned assets (referenced with ?v=<mtime>) can be cached forever;
            # unversioned assets get a short cache so updates still propagate.
            if request.args.get("v"):
                r.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                r.headers["Cache-Control"] = "public, max-age=3600"
        else:
            r.headers[
                "Cache-Control"
            ] = "no-cache, no-store, must-revalidate, public, max-age=0"
            r.headers["Pragma"] = "no-cache"
            r.headers["Expires"] = "0"

        # --- security headers ---
        r.headers["X-Content-Type-Options"] = "nosniff"
        r.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        r.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # Framing is blocked by default. When embedding is allowed, drop
        # X-Frame-Options (its ALLOW-FROM is deprecated) and open CSP
        # frame-ancestors so the page can load inside an iframe.
        if self.bAllowIframe:
            frame_ancestors = "*"
        else:
            frame_ancestors = "'none'"
            r.headers["X-Frame-Options"] = "DENY"
        r.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self' https://raw.githubusercontent.com; "
            "frame-ancestors " + frame_ancestors
        )

        # When HTTPS is off, tell browsers to stop forcing HTTPS (clears cached HSTS)
        if not self.bUseSecureHTTP:
            r.headers["Strict-Transport-Security"] = "max-age=0"

        return r

    def inject_asset_helpers(self):
        # asset_ver() returns the file mtime so templates can append ?v=<mtime>,
        # busting the browser cache automatically whenever an asset is updated.
        def asset_ver(rel_path):
            try:
                full = os.path.join(app.static_folder, rel_path.lstrip("/"))
                return str(int(os.path.getmtime(full)))
            except Exception:
                return "1"

        return dict(asset_ver=asset_ver, csrf_token=self.CSRFToken)

    def _is_static_asset_request(self, path):
        # sw.js must always revalidate so service-worker updates propagate quickly.
        if path == "/sw.js":
            return False
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        return ext in self.STATIC_ASSET_EXTENSIONS

    # -------------------------------------------------------------------------------
    def CSRFToken(self):
        """Install-wide CSRF token sent back in the X-CSRFToken header.

        Derived from app.secret_key, so it needs no cookie (the session cookie is
        Secure and therefore not stored by browsers over plain HTTP) and changes
        whenever the secret key is regenerated. Other sites can neither read it
        (same-origin policy) nor send a custom header cross-origin without a CORS
        preflight, which genserv never approves."""
        key = app.secret_key
        if not key:
            return ""
        if isinstance(key, str):
            key = key.encode("utf-8")
        return hmac.new(key, b"genmon-csrf-v1", hashlib.sha256).hexdigest()

    # -------------------------------------------------------------------------------
    def HasWriteAccess(self):
        """Return True if the current request has write access.
        When authentication is disabled everyone gets full access.
        When authentication is enabled the session must carry an explicit True."""
        if not self.LoginActive():
            return True
        return session.get("write_access", False)

    # -------------------------------------------------------------------------------
    def LoginActive(self):

        if self.HTTPAuthUser != None and self.HTTPAuthPass != None or self.LdapServer != None:
            return True
        return False

    # -------------------------------------------------------------------------------
    def root(self):

        if self.bUseMFA:
            if not "mfa_ok" in session or not session["mfa_ok"] == True:
                session["logged_in"] = False
                session["write_access"] = False
                session["mfa_ok"] = False
        return self.RenderPage("index.html", theme=self.get_theme_pref())

    # -------------------------------------------------------------------------------
    def locked(self):

        self.LogError("Locked Page")
        return render_template("locked.html", theme=self.get_theme_pref())

    # -------------------------------------------------------------------------------
    def RenderPage(self, page_file, **kwargs):

        if self.LoginActive():
            if not session.get("logged_in"):
                return self._render_login()
            else:
                return render_template(page_file, **kwargs)
        else:
            return render_template(page_file, **kwargs)

    # -------------------------------------------------------------------------------
    def get_theme_pref(self):
        try:
            system_theme = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                "system_theme", return_type=bool, section="GenMon", default=False
            )
            if system_theme:
                return "system"
            raw = self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                "ui_prefs", return_type=str, section="GenMon", default="{}"
            )
            return json.loads(raw).get("theme", "dark")
        except Exception:
            return "dark"

    # -------------------------------------------------------------------------------
    def upload(self):

        try:
            if not self.HasWriteAccess():
                return jsonify({"status": "error", "message": "Write access required."}), 403

            if "file" not in request.files:
                return jsonify({"status": "error", "message": "No file provided."}), 400

            f = request.files["file"]
            if f.filename == "":
                return jsonify({"status": "error", "message": "No file selected."}), 400

            if not f.filename.lower().endswith(".tar.gz"):
                return jsonify({"status": "error", "message": "Invalid file type. Expected a .tar.gz archive."}), 400

            # Read into memory and enforce size limit (10 MB)
            data = f.read()
            MAX_UPLOAD = 10 * 1024 * 1024
            if len(data) > MAX_UPLOAD:
                return jsonify({"status": "error", "message": "File too large. Maximum size is 10 MB."}), 400

            import tarfile, io, tempfile

            # Validate it's a real tar.gz archive
            try:
                buf = io.BytesIO(data)
                with tarfile.open(fileobj=buf, mode="r:gz") as tf:
                    names = tf.getnames()
                    # Security: reject path traversal
                    for name in names:
                        if name.startswith("/") or ".." in name:
                            return jsonify({"status": "error", "message": "Archive contains unsafe paths."}), 400
                    # Sanity check: must contain genmon_backup/ with at least one .conf
                    has_conf = any(
                        n.startswith("genmon_backup/") and n.endswith(".conf") for n in names
                    )
                    if not has_conf:
                        return jsonify({"status": "error", "message": "Archive does not appear to be a valid genmon backup (no genmon_backup/*.conf found)."}), 400
            except tarfile.TarError:
                return jsonify({"status": "error", "message": "File is not a valid tar.gz archive."}), 400

            # Save to temp file and run restore script
            pathtofile = os.path.dirname(os.path.realpath(__file__))
            upload_path = os.path.join(pathtofile, "genmon_restore_upload.tar.gz")
            try:
                with open(upload_path, "wb") as out:
                    out.write(data)
                if not self.RestoreBackup(upload_path):
                    return jsonify({"status": "error", "message": "Restore script failed. Check server logs."}), 500
            finally:
                if os.path.exists(upload_path):
                    os.remove(upload_path)

            threading.Thread(target=self.Restart, daemon=True).start()
            return jsonify({"status": "ok", "message": "Configuration restored. Service is restarting\u2026"})

        except Exception as e1:
            self.LogErrorLine("Error in upload: " + str(e1))
            return jsonify({"status": "error", "message": "Server error during upload."}), 500

    # -------------------------------------------------------------------------------
    def download_ca_der(self):
        """Serve the Local CA certificate in DER format for browser import."""
        try:
            ca_path = os.path.join(self.ConfigFilePath, "ca.crt")
            if not os.path.isfile(ca_path):
                return "CA certificate not found", 404
            from OpenSSL import crypto

            with open(ca_path, "rb") as f:
                ca_cert = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
            der = crypto.dump_certificate(crypto.FILETYPE_ASN1, ca_cert)
            return Response(
                der,
                mimetype="application/x-x509-ca-cert",
                headers={"Content-Disposition": "attachment; filename=genmon-ca.crt"},
            )
        except Exception as e1:
            self.LogErrorLine("Error in download_ca_der: " + str(e1))
            return "Error serving certificate", 500

    # -------------------------------------------------------------------------------
    def import_ca_inline(self):
        """Serve the CA cert inline (no attachment header) so Firefox opens its
        native import dialog and Chrome/Edge download it automatically."""
        try:
            ca_path = os.path.join(self.ConfigFilePath, "ca.crt")
            if not os.path.isfile(ca_path):
                return "CA certificate not found", 404
            from OpenSSL import crypto

            with open(ca_path, "rb") as f:
                ca_cert = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
            der = crypto.dump_certificate(crypto.FILETYPE_ASN1, ca_cert)
            return Response(der, mimetype="application/x-x509-ca-cert")
        except Exception as e1:
            self.LogErrorLine("Error in import_ca_inline: " + str(e1))
            return "Error serving certificate", 500

    # -------------------------------------------------------------------------------
    def download_ca_pem(self):
        """Serve the Local CA certificate in PEM format."""
        try:
            ca_path = os.path.join(self.ConfigFilePath, "ca.crt")
            if not os.path.isfile(ca_path):
                return "CA certificate not found", 404
            with open(ca_path, "rb") as f:
                pem_data = f.read()
            return Response(
                pem_data,
                mimetype="application/x-pem-file",
                headers={"Content-Disposition": "attachment; filename=genmon-ca.pem"},
            )
        except Exception as e1:
            self.LogErrorLine("Error in download_ca_pem: " + str(e1))
            return "Error serving certificate", 500

    # -------------------------------------------------------------------------------
    def command(self, command):

        if command in self.POST_ONLY_COMMANDS and request.method != "POST":
            self.LogError("Rejected GET for state-changing command: " + command)
            response = jsonify({"error": "Use POST with the X-CSRFToken header for this command"})
            response.status_code = 405
            response.headers["Allow"] = "POST"
            return response
        if self.Closing or self.Restarting:
            return jsonify("Closing")
        if not self.LoginActive():

            # Not everything sent to this function is a json string
            # so try to jsonify it and if that fails just return the
            # original string
            commandResponse = self.ProcessCommand(command)
            try:
                # Validate it is JSON and set Content-Type to application/json.
                # Return the original string as-is (not re-serialized via
                # jsonify/json.dumps) so key order set by the command handler
                # (e.g. sort_keys=False responses) is preserved; jsonify()
                # sorts keys alphabetically by default and would destroy it.
                json.loads(commandResponse)
                return Response(commandResponse, mimetype="application/json")
            except Exception as e1:
                return commandResponse
        if not session.get("logged_in"):
            return self._render_login()
        else:
            commandResponse = self.ProcessCommand(command)
            try:
                json.loads(commandResponse)
                return Response(commandResponse, mimetype="application/json")
            except Exception as e1:
                return commandResponse

    # -------------------------------------------------------------------------------
    # answer a /cmd/ command, as set out in COMMANDS
    def ProcessCommand(self, command):

        try:
            cmd = self.COMMANDS.get(command)
            if cmd is None:
                return render_template("command_template.html", command=command, theme=self.get_theme_pref())

            if cmd.write and not self.HasWriteAccess():
                return jsonify("Read Only Mode") if cmd.handler is None else "Access denied"

            if cmd.handler is None:
                data = self.SendCommandToGenmon(command, cmd)
                return data if cmd.json else jsonify(data)

            response = getattr(self, cmd.handler)()
            if response is None:
                self.LogError("No response for command: " + command)
                return jsonify("OK")
            return response
        except Exception as e1:
            self.LogErrorLine("Error in Process Command: " + command + ": " + str(e1))
            return render_template("command_template.html", command=command, theme=self.get_theme_pref())

    # -------------------------------------------------------------------------------
    # send a /cmd/ command to genmon, adding its parameter, and return the reply
    def SendCommandToGenmon(self, command, cmd, finalcommand=None):

        try:
            if finalcommand is None:
                finalcommand = "generator: " + command
                if cmd.param is not None and cmd.maxlen is not None:
                    # Sanitize command parameters: strip null bytes and newlines
                    # to prevent header/log injection, cap length to limit abuse.
                    # (request.values[] not .get(), for unicode input from
                    # international users)
                    value = request.values[cmd.param]
                    value = value.replace("\x00", "").replace("\n", " ").replace("\r", " ")[: cmd.maxlen]
                    finalcommand += "=" + value
                elif cmd.param is not None:
                    # example: /cmd/setquiet?setquiet=off
                    value = request.values.get(cmd.param, 0, type=str)
                    if value:
                        finalcommand += "=" + value
            return self.MyClientInterface.ProcessMonitorCommand(finalcommand)
        except Exception as e1:
            self.LogErrorLine("Error on command function: " + str(e1))
            return "Retry"

    # ------------ /cmd/ commands answered by genserv (see COMMANDS) ----------------
    def CmdStartInfo(self):

        data = self.SendCommandToGenmon("start_info_json", self.COMMANDS["start_info_json"])
        try:
            StartInfo = json.loads(data)
            StartInfo["write_access"] = self.HasWriteAccess()
            if not StartInfo["write_access"]:
                StartInfo["pages"]["settings"] = False
                StartInfo["pages"]["notifications"] = False
                StartInfo["pages"]["addons"] = False
            StartInfo["LoginActive"] = self.LoginActive()
            StartInfo["code_hash"] = self.GitHubCodeHash()
            data = json.dumps(StartInfo, sort_keys=False)
        except Exception as e1:
            self.LogErrorLine("Error in JSON parse / decode: " + str(e1))
        return data

    def CmdSensorLog(self):

        # example: /cmd/sensor_log_json?sensor_log_json=1440&sensor=Oil+Temp
        finalcommand = "generator: sensor_log_json"
        try:
            minutes = request.values.get("sensor_log_json", 0, type=str)
            sensor = request.values.get("sensor", "", type=str)
            if minutes and sensor:
                finalcommand += "=" + minutes + "&sensor=" + sensor
        except Exception as e1:
            self.LogErrorLine("Error on command function: " + str(e1))
            return "Retry"
        return self.SendCommandToGenmon("sensor_log_json", self.COMMANDS["sensor_log_json"], finalcommand)

    def CmdCSRFToken(self):
        # for integrations: send back as X-CSRFToken header on POST requests
        return jsonify({"csrf_token": self.CSRFToken()})

    def CmdFavicon(self):
        return jsonify(self.favicon)

    def CmdRegisterLabels(self):
        return jsonify(self.CachedRegisterDescriptions)

    def CmdSettings(self):
        return json.dumps(self.ReadSettingsFromFile(), sort_keys=False)

    def CmdSetSettings(self):
        self.SaveSettings(request.values.get("setsettings", 0, type=str))
        return "OK"

    def CmdAdvancedSettings(self):
        return json.dumps(self.ReadAdvancedSettingsFromFile(), sort_keys=False)

    def CmdSetAdvancedSettings(self):
        self.SaveAdvancedSettings(request.values.get("set_advanced_settings", default=None, type=str))
        return "OK"

    def CmdAddOnSettings(self):
        return json.dumps(self.GetAddOnSettings(), sort_keys=False)

    def CmdSetAddOnSettings(self):
        self.SaveAddOnSettings(request.values.get("set_add_on_settings", default=None, type=str))
        return "OK"

    def CmdNotifications(self):
        return jsonify(self.ReadNotificationsFromFile())

    def CmdSetNotifications(self):
        self.SaveNotifications(request.values.get("setnotifications", 0, type=str))
        return "OK"

    # UI preferences (saved in genmon.conf, no restart)
    def CmdUIPrefs(self):
        try:
            return self.ConfigFiles[self.GENMON_CONFIG].ReadValue(
                "ui_prefs", return_type=str, section="GenMon", default="{}"
            )
        except Exception:
            return "{}"

    def CmdSetUIPrefs(self):
        raw = request.values.get("set_ui_prefs", "{}", type=str)
        if len(raw) > 16384:  # 16 KB cap to prevent memory/storage abuse
            return "Error: payload too large"
        try:
            # validate, then store on a single line: valid JSON
            # may contain newlines, which would corrupt the conf
            raw = json.dumps(json.loads(raw), separators=(",", ":"))
        except Exception:
            return "Error: invalid JSON"
        if not self.ConfigFiles[self.GENMON_CONFIG].WriteValue("ui_prefs", raw, section="GenMon"):
            return "Error: unable to save preferences"
        return "OK"

    def CmdTestEmail(self):
        return self.SendTestEmail(request.values.get("test_email", default=None, type=str))

    def CmdBackup(self):
        self.Backup()  # Create backup file
        # Now send the file
        pathtofile = os.path.dirname(os.path.realpath(__file__))
        return send_file(os.path.join(pathtofile, "genmon_backup.tar.gz"), as_attachment=True)

    def CmdGetLogs(self):
        self.GetLogs()  # Create log archive file
        # Now send the file
        pathtofile = os.path.dirname(os.path.realpath(__file__))
        return send_file(os.path.join(pathtofile, "genmon_logs.tar.gz"), as_attachment=True)

    def CmdUpdateSoftware(self):
        self.Update()
        return jsonify("OK")

    def CmdRestart(self):
        self.Restart()
        return jsonify("OK")

    def CmdStop(self):
        self.Close()
        sys.exit(0)

    def CmdShutdown(self):
        self.Shutdown()
        sys.exit(0)

    def CmdReboot(self):
        self.Reboot()
        sys.exit(0)

    # -------------------------------------------------------------------------------
    def logout(self):
        try:
            # remove the session data
            if self.LoginActive():
                session["logged_in"] = False
                session["write_access"] = False
                session["mfa_ok"] = False
                self._clear_provisional_login()
            return redirect(url_for("root"))
        except Exception as e1:
            self.LogError("Error on logout: " + str(e1))

    # -------------------------------------------------------------------------------
    def _render_login(self):
        """Render login page with theme and passkey availability."""
        has_pk = self.bUseMFA and self.bUseSecureHTTP and bool(self._load_passkeys())
        return render_template("login.html", theme=self.get_theme_pref(), has_passkeys=has_pk, remember_me_enabled=self.RememberMeDays > 0)

    # -------------------------------------------------------------------------------
    def admin_login_helper(self):

        self.LoginAttempts = 0
        try:
            # remember-me: make session persistent if checkbox was checked and days > 0
            if request.form.get("remember_me") and self.RememberMeDays > 0:
                session.permanent = True

            if self.bUseMFA:
                # Check MFA trust cookie before showing MFA screen
                trust_user = self._check_mfa_trust_cookie()
                if trust_user and trust_user == session.get("username", ""):
                    self._complete_mfa_login()
                    resp = redirect(url_for("root"))
                    resp = self._set_mfa_trust_cookie(resp, trust_user)
                    return resp
                # GetOTP()
                email_ok = self.mail is not None and not getattr(self.mail, 'DisableEmail', True) and not getattr(self.mail, 'DisableSMTP', True)
                uname = session.get("username", "").lower()
                bc_data = self._load_backup_codes()
                has_bc = len(bc_data.get(uname, [])) > 0
                response = make_response(render_template("mfa.html", theme=self.get_theme_pref(), trust_enabled=self.bMfaTrustExtend, trust_days=self.MfaTrustDays, email_available=email_ok, has_backup_codes=has_bc))
                return response
            else:
                return redirect(url_for("root"))
        except Exception as e1:
            self.LogErrorLine("Error in admin_login_helper: " + str(e1))
            return False

    # -------------------------------------------------------------------------------
    def do_admin_login(self):

        self.CheckLockOutDuration()
        if self.WebUILocked:
            next_time = (datetime.datetime.now() - self.LastFailedLoginTime).total_seconds()
            str_seconds = str(int(self.LockOutDuration - next_time))
            response = make_response(render_template("locked.html", time=str_seconds, theme=self.get_theme_pref()))
            response.headers["Content-type"] = "text/html; charset=utf-8"
            response.mimetype = "text/html; charset=utf-8"
            return response

        submitted_user = request.form["username"].lower()
        submitted_pass = request.form["password"]

        # Timing-safe comparisons to prevent user/password enumeration
        admin_user_ok = secrets.compare_digest(submitted_user, (self.HTTPAuthUser or "").lower())
        admin_pass_ok = secrets.compare_digest(submitted_pass, self.HTTPAuthPass or "")
        ro_user_ok = secrets.compare_digest(submitted_user, (self.HTTPAuthUser_RO or "").lower())
        ro_pass_ok = secrets.compare_digest(submitted_pass, self.HTTPAuthPass_RO or "")

        if admin_user_ok and admin_pass_ok:
            if not self.bUseMFA:
                #do not set this until MFA is success
                session["logged_in"] = True
                session["write_access"] = True
            else:
                session["provisional_login"] = True
                session["provisional_write_access"] = True
            session["username"] = submitted_user
            self.LogError("Admin Login")
            return self.admin_login_helper()
        elif ro_user_ok and ro_pass_ok:
            if not self.bUseMFA:
                #do not set this until MFA is success
                session["logged_in"] = True
                session["write_access"] = False
            else:
                session["provisional_login"] = True
                session["provisional_write_access"] = False
            session["username"] = submitted_user
            self.LogError("Limited Rights Login")
            return self.admin_login_helper()
        elif self.doLdapLogin(request.form["username"], request.form["password"]):
            session["username"] = request.form["username"].lower()
            if self.bUseMFA:
                # same as the local accounts above: do not grant access until MFA
                # succeeds, doLdapLogin has set the access the user will get
                session["provisional_login"] = session.get("logged_in", False)
                session["provisional_write_access"] = session.get("write_access", False)
                session["logged_in"] = False
                session["write_access"] = False
            return self.admin_login_helper()
        elif request.form["username"] != "":
            self.LogError("Invalid login: " + request.form["username"])
            self.CheckFailedLogin()
            return self._render_login()
        else:
            self.LogError(f"Unknown login error: user: {request.form['username']}")
            self.LogError(f"admin ok: {admin_user_ok}, admin pass ok: {admin_pass_ok}, ro user: {ro_user_ok}, ro pass: {ro_pass_ok}")
            return self._render_login()

    # -------------------------------------------------------------------------------
    def CheckLockOutDuration(self):

        if self.MaxLoginAttempts == 0:
            return

        if self.LoginAttempts >= self.MaxLoginAttempts:
            if (
                datetime.datetime.now() - self.LastFailedLoginTime
            ).total_seconds() > self.LockOutDuration:
                self.WebUILocked = False
                self.LoginAttempts = 0
            else:
                self.WebUILocked = True
                # send message to user only once every 4 hours
                if self.securityMessageSent == None or (
                    (datetime.datetime.now() - self.securityMessageSent).total_seconds()
                    > (4 * 60 * 60)
                ):

                    message = {
                        "title": "Security Warning",
                        "body": "Genmon login is locked due to exceeding the maximum login attempts.",
                        "type": "error",
                        "oncedaily": False,
                        "onlyonce": False,
                    }
                    command = "generator: notify_message=" + json.dumps(message)

                    data = self.MyClientInterface.ProcessMonitorCommand(command)
                    self.securityMessageSent = datetime.datetime.now()

    # -------------------------------------------------------------------------------
    def CheckFailedLogin(self):

        self.LoginAttempts += 1
        self.LastFailedLoginTime = datetime.datetime.now()

        self.CheckLockOutDuration()

    # -------------------------------------------------------------------------------
    def doLdapLogin(self, username, password):
        if self.LdapServer == None or self.LdapServer == "":
            return False
        try:
            from ldap3 import ALL, Connection, Server
            from ldap3.utils.dn import escape_rdn
            from ldap3.utils.conv import escape_filter_chars
        except ImportError as importException:
            self.LogError(
                "LDAP3 import not found, run 'sudo pip install ldap3 && sudo pip3 install ldap3'"
            )
            self.LogError(importException)
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
            self.LogError("Using domain name in config file")
            DomainName = self.DomainNetbios
            AccountName = username.strip()
        try:
            server = Server(self.LdapServer, get_info=ALL)
            conn = Connection(
                server,
                user="{}\\{}".format(DomainName, AccountName),
                password=password,
                auto_bind=True,
            )
            escaped_account = escape_filter_chars(AccountName)
            loginbasestr = "(&(objectclass=user)(sAMAccountName=%s))" % escaped_account
            conn.search(
                self.LdapBase,
                loginbasestr,
                attributes=["memberOf"],
            )
            for user in sorted(conn.entries):
                for group in user.memberOf:
                    if group.upper().find("CN=" + self.LdapAdminGroup.upper() + ",") >= 0:
                        HasAdmin = True
                    elif group.upper().find("CN=" + self.LdapReadOnlyGroup.upper() + ",") >= 0:
                        HasReadOnly = True
            conn.unbind()
        except Exception as eld1:
            import traceback
            self.LogError("Error in LDAP login. Check credentials and config parameters")
            self.LogDebug("LDAP login exception: " + repr(eld1))
            self.LogDebug("LDAP login traceback: " + traceback.format_exc())

        session["logged_in"] = HasAdmin or HasReadOnly
        session["write_access"] = HasAdmin
        if HasAdmin:
            self.LogError("Admin Login via LDAP for user: " + AccountName)
        elif HasReadOnly:
            self.LogError("Limited Rights Login via LDAP for user: " + AccountName)
        else:
            self.LogError("No rights for login via LDAP for user: " + AccountName)

        return HasAdmin or HasReadOnly

    # -------------------------------------------------------------------------------
    def _get_mfa_trust_serializer(self):
        from itsdangerous import URLSafeTimedSerializer
        return URLSafeTimedSerializer(app.secret_key, salt="mfa-trust")

    # -------------------------------------------------------------------------------
    def _set_mfa_trust_cookie(self, response, username):
        s = self._get_mfa_trust_serializer()
        token = s.dumps({"u": username})
        response.set_cookie(
            "mfa_trust", token,
            max_age=self.MfaTrustDays * 86400,
            httponly=True, secure=True, samesite="Lax",
        )
        return response

    # -------------------------------------------------------------------------------
    def _check_mfa_trust_cookie(self):
        if not self.bMfaTrustExtend:
            return None
        token = request.cookies.get("mfa_trust")
        if not token:
            return None
        try:
            s = self._get_mfa_trust_serializer()
            data = s.loads(token, max_age=self.MfaTrustDays * 86400)
            return data.get("u")
        except Exception:
            return None

    # --------------------------------------------------------------------------
    def mfa_auth(self):

        try:
            if self.bUseMFA:
                code = request.form.get("code", "")
                verified = False
                # Check if this is a backup code (8 hex chars) or TOTP (6 digits)
                if len(code) == 8 and all(c in "0123456789abcdef" for c in code.lower()):
                    verified = self._validate_backup_code(session.get("username", ""), code)
                else:
                    verified = self.ValidateOTP(code)

                if verified:
                    self._complete_mfa_login()
                    resp = redirect(url_for("root"))
                    # Set MFA trust cookie if checkbox was checked and trust is enabled
                    if self.bMfaTrustExtend and request.form.get("trust_browser"):
                        username = session.get("username", "")
                        resp = self._set_mfa_trust_cookie(resp, username)
                    return resp
                else:
                    session["logged_in"] = False
                    session["write_access"] = False
                    session["mfa_ok"] = False
                    # a failed code means starting again with the password
                    self._clear_provisional_login()
                    self.CheckFailedLogin()  # count toward brute-force lockout
                    return redirect(url_for("logout"))
            else:
                return redirect(url_for("root"))
        except Exception as e1:
            self.LogErrorLine("Error in mfa_auth: " + str(e1))

        return self._render_login()

    # -------------------------------------------------------------------------------
    # When MFA is enabled, a correct password only sets provisional_login /
    # provisional_write_access. Access is granted here once the second factor (MFA
    # code, backup code or MFA trust cookie) has been verified.
    def _complete_mfa_login(self):

        session["mfa_ok"] = True
        session["logged_in"] = session.get("provisional_login", False)
        session["write_access"] = session.get("provisional_write_access", False)
        self._clear_provisional_login()

    # -------------------------------------------------------------------------------
    # forget a password check that has not been completed with MFA, so the next
    # login has to start with the password again
    def _clear_provisional_login(self):

        session.pop("provisional_login", None)
        session.pop("provisional_write_access", None)

    # ---------------------ValidateOTP-----------------------------------------------
    def ValidateOTP(self, password):

        if self.bUseMFA:
            try:
                TimeOTP = pyotp.TOTP(self.SecretMFAKey, interval=30)
                # valid_window=2 accepts codes from ±2 time steps (covers ~2 min)
                # so email-delivered codes remain valid while the user reads & types.
                return TimeOTP.verify(password, valid_window=2)
            except Exception as e1:
                self.LogErrorLine("Error in ValidateOTP: " + str(e1))
        return False

    # ---------------------GetOTP----------------------------------------------------
    def GetOTP(self):
        try:
            if self.bUseMFA:
                TimeOTP = pyotp.TOTP(self.SecretMFAKey, interval=30)
                OTP = TimeOTP.now()
                msgbody = "\nThis password will expire in 30 seconds: " + str(OTP)
                self.mail.sendEmail("Generator Monitor login one time password", msgbody)
                return OTP
        except Exception as e1:
            self.LogErrorLine("Error in GetOTP: " + str(e1))

    # ---------------------MFA setup verify & reset----------------------------------
    def mfa_verify_setup(self):
        """Verify a TOTP code during initial enrollment and mark MFA as enrolled."""
        try:
            if not session.get("logged_in") or not session.get("write_access"):
                return jsonify(status="error", msg="Unauthorized"), 403
            code = (request.json or {}).get("code", "").strip()
            if not code or len(code) != 6 or not code.isdigit():
                return jsonify(status="error", msg="Enter a 6-digit code"), 400
            totp = pyotp.TOTP(self.SecretMFAKey, interval=30)
            if totp.verify(code, valid_window=1):
                self.bMfaEnrolled = True
                self.ConfigFiles[self.GENMON_CONFIG].WriteValue("mfa_enrolled", "True")
                return jsonify(status="ok")
            return jsonify(status="error", msg="Code incorrect. Check your authenticator and try again.")
        except Exception as e1:
            self.LogErrorLine("Error in mfa_verify_setup: " + str(e1))
            return jsonify(status="error", msg="Verification failed"), 500

    # ---------------------send_otp route--------------------------------------------
    def send_otp(self):
        try:
            # only during the MFA step of a login (password already accepted)
            if not session.get("provisional_login"):
                return jsonify(status="error", msg="Not authorized"), 403
            if self.mail is None:
                return jsonify(status="error", msg="Email is not configured"), 500
            if self.mail.DisableEmail or self.mail.DisableSMTP:
                return jsonify(status="error", msg="Email sending is disabled in config"), 500
            with self.CriticalLock:  # thread-safe rate limiting to prevent concurrent bypass
                now = time.time()
                if self.LastOTPSendTime and (now - self.LastOTPSendTime) < 60:
                    return jsonify(status="error", msg="Please wait before requesting another code")
                self.LastOTPSendTime = now
            if not self.bUseMFA:
                return jsonify(status="error", msg="MFA is not enabled"), 400
            TimeOTP = pyotp.TOTP(self.SecretMFAKey, interval=30)
            OTP = TimeOTP.now()
            msgbody = "\nThis password will expire in 30 seconds: " + str(OTP)
            # Send synchronously so SMTP errors are reported to the user
            sent = self.mail.sendEmailDirectMIME(
                "error",
                "Generator Monitor login one time password",
                msgbody,
            )
            if not sent:
                return jsonify(status="error", msg="SMTP send failed — check email settings and server logs")
            return jsonify(status="ok")
        except Exception as e1:
            self.LogErrorLine("Error in send_otp: " + str(e1))
            return jsonify(status="error", msg="Failed to send code"), 500  # generic; details logged server-side only

    # ---------------------Backup Codes----------------------------------------------
    def _backup_codes_path(self):
        return os.path.join(self.ConfigFilePath, "backup_codes.json")

    def _load_backup_codes(self):
        path = self._backup_codes_path()
        if os.path.isfile(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    # --------------------------------------------------------------------------
    def _save_backup_codes(self, data):
        # owner-only; contains hashed backup codes. The file is created 0600 before
        # any data is written, so the contents are never readable by others.
        AtomicWrite(self._backup_codes_path(), json.dumps(data, indent=2), mode=0o600)

    # --------------------------------------------------------------------------
    def _hash_code(self, code):
        return hashlib.sha256(code.encode("utf-8")).hexdigest()

    # --------------------------------------------------------------------------
    def GenerateBackupCodes(self, username):
        codes = [secrets.token_hex(4) for _ in range(10)]
        hashed = [self._hash_code(c) for c in codes]
        data = self._load_backup_codes()
        data[username.lower()] = hashed
        self._save_backup_codes(data)
        return codes

    # --------------------------------------------------------------------------
    def _validate_backup_code(self, username, code):
        data = self._load_backup_codes()
        user = username.lower()
        user_codes = data.get(user, [])
        h = self._hash_code(code.lower())
        if h in user_codes:
            user_codes.remove(h)
            data[user] = user_codes
            self._save_backup_codes(data)
            return True
        return False

    # --------------------------------------------------------------------------
    def generate_backup_codes(self):
        try:
            if not session.get("logged_in") or not session.get("write_access"):
                return jsonify(status="error", msg="Unauthorized"), 403
            username = session.get("username", "")
            codes = self.GenerateBackupCodes(username)
            return jsonify(status="ok", codes=codes)
        except Exception as e1:
            self.LogErrorLine("Error in generate_backup_codes: " + str(e1))
            return jsonify(status="error", msg="Failed to generate codes"), 500

    # --------------------------------------------------------------------------
    def backup_codes_count(self):
        try:
            if not session.get("logged_in"):
                return jsonify(status="error", msg="Unauthorized"), 403
            username = session.get("username", "")
            data = self._load_backup_codes()
            remaining = len(data.get(username.lower(), []))
            return jsonify(status="ok", count=remaining)
        except Exception as e1:
            self.LogErrorLine("Error in backup_codes_count: " + str(e1))
            return jsonify(status="error", msg="Error"), 500

    # --------------------------------------------------------------------------
    def _passkeys_path(self):
        if self.PASSKEYS_PATH is None:
            self.PASSKEYS_PATH = os.path.join(self.ConfigFilePath, "passkeys.json")
        return self.PASSKEYS_PATH

    # --------------------------------------------------------------------------
    def _load_passkeys(self):
        path = self._passkeys_path()
        if os.path.isfile(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    # --------------------------------------------------------------------------
    def _save_passkeys(self, data):
        # owner-only; contains passkey public keys. The file is created 0600 before
        # any data is written, so the contents are never readable by others.
        AtomicWrite(self._passkeys_path(), json.dumps(data, indent=2), mode=0o600)

    # ---------------------Passkey Login (passwordless from login page)--------------
    def _find_user_by_credential(self, cred_id_raw):
        """Reverse-lookup: find username and passkey entry by raw credential ID."""
        import base64
        data = self._load_passkeys()
        for username, keys in data.items():
            for pk in keys:
                pk_id = base64.urlsafe_b64decode(pk["credential_id"] + "==")
                if pk_id == cred_id_raw:
                    return username, pk, data
        return None, None, data

    # --------------------------------------------------------------------------
    def passkey_register_begin(self):
        try:
            if not (self.bUseMFA and self.bUseSecureHTTP):
                return jsonify(error="Passkeys require MFA and HTTPS"), 400
            if not session.get("logged_in") or not session.get("write_access"):
                return jsonify(error="Unauthorized"), 403
            from webauthn import generate_registration_options, options_to_json
            from webauthn.helpers.structs import (
                AuthenticatorSelectionCriteria,
                ResidentKeyRequirement,
                UserVerificationRequirement,
            )
            import base64
            username = session.get("username", "admin")
            user_id = hashlib.sha256(username.encode()).digest()
            rp_id = request.host.split(":")[0]
            existing = self._load_passkeys().get(username.lower(), [])
            exclude_creds = []
            for pk in existing:
                from webauthn.helpers.structs import PublicKeyCredentialDescriptor
                exclude_creds.append(PublicKeyCredentialDescriptor(id=base64.urlsafe_b64decode(pk["credential_id"] + "==")))
            options = generate_registration_options(
                rp_id=rp_id,
                rp_name="Genmon",
                user_id=user_id,
                user_name=username,
                user_display_name=username,
                authenticator_selection=AuthenticatorSelectionCriteria(
                    resident_key=ResidentKeyRequirement.PREFERRED,
                    user_verification=UserVerificationRequirement.PREFERRED,
                ),
                exclude_credentials=exclude_creds,
            )
            session["webauthn_reg_challenge"] = base64.urlsafe_b64encode(options.challenge).decode().rstrip("=")
            return app.response_class(options_to_json(options), mimetype="application/json")
        except Exception as e1:
            self.LogErrorLine("Error in passkey_register_begin: " + str(e1))
            return jsonify(error="Registration failed"), 500
    # --------------------------------------------------------------------------
    def passkey_register_complete(self):
        try:
            if not (self.bUseMFA and self.bUseSecureHTTP):
                return jsonify(error="Passkeys require MFA and HTTPS"), 400
            if not session.get("logged_in") or not session.get("write_access"):
                return jsonify(error="Unauthorized"), 403
            from webauthn import verify_registration_response
            import base64
            username = session.get("username", "admin")
            rp_id = request.host.split(":")[0]
            challenge_b64 = session.pop("webauthn_reg_challenge", None)
            if not challenge_b64:
                return jsonify(error="No pending registration"), 400
            # Restore padding
            challenge_b64 += "=" * (4 - len(challenge_b64) % 4)
            expected_challenge = base64.urlsafe_b64decode(challenge_b64)
            body = request.get_json()
            verification = verify_registration_response(
                credential=body,
                expected_challenge=expected_challenge,
                expected_rp_id=rp_id,
                expected_origin=request.host_url.rstrip("/"),
            )
            cred_id_b64 = base64.urlsafe_b64encode(verification.credential_id).decode().rstrip("=")
            public_key_b64 = base64.urlsafe_b64encode(verification.credential_public_key).decode().rstrip("=")
            data = self._load_passkeys()
            user_keys = data.get(username.lower(), [])
            passkey_name = body.get("name", "Passkey " + str(len(user_keys) + 1))
            user_keys.append({
                "credential_id": cred_id_b64,
                "public_key": public_key_b64,
                "sign_count": verification.sign_count,
                "name": passkey_name,
            })
            data[username.lower()] = user_keys
            self._save_passkeys(data)
            return jsonify(status="ok", name=passkey_name)
        except Exception as e1:
            self.LogErrorLine("Error in passkey_register_complete: " + str(e1))
            return jsonify(error="Registration verification failed"), 500

    # --------------------------------------------------------------------------
    def passkey_auth_begin(self):
        try:
            if not (self.bUseMFA and self.bUseSecureHTTP):
                return jsonify(error="Passkeys require MFA and HTTPS"), 400
            from webauthn import generate_authentication_options, options_to_json
            from webauthn.helpers.structs import PublicKeyCredentialDescriptor
            import base64
            username = session.get("username", "")
            data = self._load_passkeys()
            user_keys = data.get(username.lower(), [])
            if not user_keys:
                return jsonify(error="No passkeys registered"), 400
            allow_creds = []
            for pk in user_keys:
                allow_creds.append(PublicKeyCredentialDescriptor(
                    id=base64.urlsafe_b64decode(pk["credential_id"] + "==")
                ))
            rp_id = request.host.split(":")[0]
            options = generate_authentication_options(
                rp_id=rp_id,
                allow_credentials=allow_creds,
            )
            session["webauthn_auth_challenge"] = base64.urlsafe_b64encode(options.challenge).decode().rstrip("=")
            return app.response_class(options_to_json(options), mimetype="application/json")
        except Exception as e1:
            self.LogErrorLine("Error in passkey_auth_begin: " + str(e1))
            return jsonify(error="Authentication failed"), 500

    # --------------------------------------------------------------------------
    def passkey_auth_complete(self):
        try:
            if not (self.bUseMFA and self.bUseSecureHTTP):
                return jsonify(error="Passkeys require MFA and HTTPS"), 400
            from webauthn import verify_authentication_response
            import base64
            username = session.get("username", "")
            rp_id = request.host.split(":")[0]
            challenge_b64 = session.pop("webauthn_auth_challenge", None)
            if not challenge_b64:
                return jsonify(error="No pending authentication"), 400
            challenge_b64 += "=" * (4 - len(challenge_b64) % 4)
            expected_challenge = base64.urlsafe_b64decode(challenge_b64)
            body = request.get_json()
            cred_id_raw = base64.urlsafe_b64decode(body.get("rawId", "") + "==")
            data = self._load_passkeys()
            user_keys = data.get(username.lower(), [])
            matched_key = None
            for pk in user_keys:
                pk_id = base64.urlsafe_b64decode(pk["credential_id"] + "==")
                if pk_id == cred_id_raw:
                    matched_key = pk
                    break
            if not matched_key:
                return jsonify(error="Verification failed"), 400  # generic error to prevent credential enumeration
            public_key = base64.urlsafe_b64decode(matched_key["public_key"] + "==")
            verification = verify_authentication_response(
                credential=body,
                expected_challenge=expected_challenge,
                expected_rp_id=rp_id,
                expected_origin=request.host_url.rstrip("/"),
                credential_public_key=public_key,
                credential_current_sign_count=matched_key.get("sign_count", 0),
            )
            matched_key["sign_count"] = verification.new_sign_count
            self._save_passkeys(data)
            session["mfa_ok"] = True
            return jsonify(status="ok")
        except Exception as e1:
            self.LogErrorLine("Error in passkey_auth_complete: " + str(e1))
            return jsonify(error="Passkey verification failed"), 500

    # --------------------------------------------------------------------------
    def passkey_list(self):
        try:
            if not session.get("logged_in"):
                return jsonify(error="Unauthorized"), 403
            username = session.get("username", "")
            data = self._load_passkeys()
            user_keys = data.get(username.lower(), [])
            result = [{"name": pk.get("name", "Passkey"), "credential_id": pk["credential_id"]} for pk in user_keys]
            return jsonify(status="ok", passkeys=result)
        except Exception as e1:
            self.LogErrorLine("Error in passkey_list: " + str(e1))
            return jsonify(error="Error"), 500

    # --------------------------------------------------------------------------
    def passkey_delete(self):
        try:
            if not session.get("logged_in") or not session.get("write_access"):
                return jsonify(error="Unauthorized"), 403
            username = session.get("username", "")
            cred_id = request.get_json().get("credential_id", "")
            data = self._load_passkeys()
            user_keys = data.get(username.lower(), [])
            data[username.lower()] = [pk for pk in user_keys if pk["credential_id"] != cred_id]
            self._save_passkeys(data)
            return jsonify(status="ok")
        except Exception as e1:
            self.LogErrorLine("Error in passkey_delete: " + str(e1))
            return jsonify(error="Error"), 500

    # --------------------------------------------------------------------------
    def passkey_login_begin(self):
        try:
            if self.WebUILocked:  # shared lockout with password login
                return jsonify(error="Too many failed attempts, try again later"), 429
            if not (self.bUseMFA and self.bUseSecureHTTP):
                return jsonify(error="Passkeys require MFA and HTTPS"), 400
            from webauthn import generate_authentication_options, options_to_json
            from webauthn.helpers.structs import PublicKeyCredentialDescriptor
            import base64
            # Gather ALL passkeys across all users for discoverable credential flow
            data = self._load_passkeys()
            allow_creds = []
            for username, keys in data.items():
                for pk in keys:
                    allow_creds.append(PublicKeyCredentialDescriptor(
                        id=base64.urlsafe_b64decode(pk["credential_id"] + "==")
                    ))
            if not allow_creds:
                return jsonify(error="No passkeys registered"), 400
            rp_id = request.host.split(":")[0]
            options = generate_authentication_options(
                rp_id=rp_id,
                allow_credentials=allow_creds,
            )
            session["webauthn_login_challenge"] = base64.urlsafe_b64encode(options.challenge).decode().rstrip("=")
            return app.response_class(options_to_json(options), mimetype="application/json")
        except Exception as e1:
            self.LogErrorLine("Error in passkey_login_begin: " + str(e1))
            return jsonify(error="Authentication failed"), 500

    # --------------------------------------------------------------------------
    def passkey_login_complete(self):
        try:
            if self.WebUILocked:  # shared lockout with password login
                return jsonify(error="Too many failed attempts, try again later"), 429
            self.CheckLockOutDuration()
            if not (self.bUseMFA and self.bUseSecureHTTP):
                return jsonify(error="Passkeys require MFA and HTTPS"), 400
            from webauthn import verify_authentication_response
            import base64
            rp_id = request.host.split(":")[0]
            challenge_b64 = session.pop("webauthn_login_challenge", None)
            if not challenge_b64:
                return jsonify(error="No pending authentication"), 400
            challenge_b64 += "=" * (4 - len(challenge_b64) % 4)
            expected_challenge = base64.urlsafe_b64decode(challenge_b64)
            body = request.get_json()
            cred_id_raw = base64.urlsafe_b64decode(body.get("rawId", "") + "==")
            username, matched_key, data = self._find_user_by_credential(cred_id_raw)
            if not matched_key:
                return jsonify(error="Verification failed"), 400  # generic error to prevent credential enumeration
            public_key = base64.urlsafe_b64decode(matched_key["public_key"] + "==")
            verification = verify_authentication_response(
                credential=body,
                expected_challenge=expected_challenge,
                expected_rp_id=rp_id,
                expected_origin=request.host_url.rstrip("/"),
                credential_public_key=public_key,
                credential_current_sign_count=matched_key.get("sign_count", 0),
            )
            matched_key["sign_count"] = verification.new_sign_count
            self._save_passkeys(data)
            # Determine access level from username
            write = username.lower() == self.HTTPAuthUser.lower() if self.HTTPAuthUser else False
            # Regenerate session to prevent session fixation
            session.clear()
            session["logged_in"] = True
            session["write_access"] = write
            session["mfa_ok"] = True
            session["username"] = username
            self.LogError("Passkey Login: " + username)
            return jsonify(status="ok")
        except Exception as e1:
            self.LogErrorLine("Error in passkey_login_complete: " + str(e1))
            self.CheckFailedLogin()
            return jsonify(error="Passkey verification failed"), 500


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

    GenServInstance = GenServ(
        log=log,
        loglocation=loglocation,
        ConfigFilePath=ConfigFilePath,
        host=address,
        port=port,
        console=console,
    )
    GenServInstance.Run()
