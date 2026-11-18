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
    from genmonlib.mymail import MyMail
    from genmonlib.mysupport import MySupport
    from genmonlib.myplatform import MyPlatform
    from genmonlib.program_defaults import ProgramDefaults
    from genmonlib.genservsettings import (
        ADDON_CHECKS,
        ADDONS,
        ADVANCED_SETTINGS,
        MISSING_LIBRARY_NOTE,
        CERT_INFO,
        EMAIL_CONFIGURED,
        GENMON_DIR,
        IMPORT_CONFIG_FILES,
        MAIN_SETTINGS,
        MFA_ENROLLED,
        MFA_URL,
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
    import genservext  # noqa: F401  (runs the site's extension)

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

    # core config files used by genserv, attribute name : file name. The add-on
    # config files are in the ADDONS table (genservsettings.py).
    CONFIG_FILE_NAMES = collections.OrderedDict([
        ("GENMON_CONFIG", "genmon.conf"),
        ("MAIL_CONFIG", "mymail.conf"),
        ("GENLOADER_CONFIG", "genloader.conf"),
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

        # genmon.conf, mymail.conf and genloader.conf are required
        for ConfigFile in ConfigFileList:
            if not os.path.isfile(ConfigFile):
                self.LogConsole("Missing config file : " + ConfigFile)
                sys.exit(1)

        # a missing add-on config file only hides that add-on (genloader normally
        # copies missing config files from the conf folder when it starts)
        for addon in ADDONS:
            if addon.conf is None:
                continue
            ConfigFile = self.AddOnConfigFile(addon)
            if os.path.isfile(ConfigFile):
                ConfigFileList.append(ConfigFile)
            else:
                self.LogError("Missing config file, add-on " + addon.name + " not shown: " + ConfigFile)

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
        elif MyPlatform.IsOSMac():
            self.OperatingSystem = "mac"
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
            self.LogError(" Timeout waiting for genmon to become ready")

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

            # Fallback: a certificate made here (cryptography)
            import atexit
            import tempfile

            key_pem, cert_pem = self._make_selfsigned_cert("Dummy Certificate", days=365)

            cert_handle, cert_file = tempfile.mkstemp()
            pkey_handle, pkey_file = tempfile.mkstemp()
            atexit.register(os.remove, pkey_file)
            atexit.register(os.remove, cert_file)

            os.write(cert_handle, cert_pem)
            os.write(pkey_handle, key_pem)
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
    @staticmethod
    def _make_selfsigned_cert(organization, days):
        """A self-signed certificate (common name "*") and its new RSA key:
        (key PEM, certificate PEM) as bytes."""
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "*"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
        ])
        # naive UTC: cryptography < 42 requires it (later versions accept it)
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(int.from_bytes(os.urandom(16), "big") >> 1)
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=days))
            .sign(key, hashes.SHA256())
        )
        key_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return key_pem, cert.public_bytes(serialization.Encoding.PEM)

    # -------------------------------------------------------------------------------
    def generate_persistent_selfsigned(self, config_path):
        """Generate (or load existing) a persistent self-signed certificate.

        Files: {config_path}/selfsigned.key, {config_path}/selfsigned.crt
        Returns an ssl.SSLContext, or None on failure.
        """
        import ssl

        from cryptography import x509

        key_path = os.path.join(config_path, "selfsigned.key")
        crt_path = os.path.join(config_path, "selfsigned.crt")

        need_generate = False
        if os.path.isfile(key_path) and os.path.isfile(crt_path):
            try:
                with open(crt_path, "rb") as f:
                    cert = x509.load_pem_x509_certificate(f.read())
                try:
                    not_after = cert.not_valid_after_utc
                except AttributeError:  # cryptography < 42: naive UTC
                    not_after = cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)
                if not_after <= datetime.datetime.now(datetime.timezone.utc):
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
                key_pem, cert_pem = self._make_selfsigned_cert("Genmon Self-Signed", days=365)
                # the key is never readable by others, even while written
                AtomicWrite(key_path, key_pem, mode=0o600)
                AtomicWrite(crt_path, cert_pem)

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

        return self.ReadSettingsTable(MAIN_SETTINGS, "ReadSettingsFromFile")

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
        if when == "h100_pzp":
            return self.ControllerType in ("h_100", "powerzone_pro")
        if when == "not_h100_pzp":
            return self.ControllerType not in ("h_100", "powerzone_pro")
        if when == "evo_lc_diesel":
            ControllerInfo = self.GetControllerInfo("controller").lower()
            return ("liquid cooled" in ControllerInfo and "evolution" in ControllerInfo
                    and self.GetControllerInfo("fueltype").lower() == "diesel")
        if when == "evo_nexus_name":
            ControllerInfo = self.GetControllerInfo("controller").lower()
            return "evolution" in ControllerInfo or "nexus" in ControllerInfo
        if when == "linux":
            return bool(self.GStartInfo.get("Linux", False))
        if when == "setgentime":
            return bool(self.GStartInfo.get("SetGenTime", False))
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
        if value is MFA_URL:
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
            return mfa_url_value
        if value is MFA_ENROLLED:
            return self.bMfaEnrolled
        if value is EMAIL_CONFIGURED:
            return (self.mail is not None and not getattr(self.mail, "DisableEmail", True)
                    and not getattr(self.mail, "DisableSMTP", True))
        if value is CERT_INFO:
            return self._get_cert_info()
        raise ValueError("Unknown setting value: " + value.name)

    # -------------------------------------------------------------------------------
    # Build a settings page from a table in genservsettings.py: the settings that
    # are shown, each with its current value read from its config file. The page
    # sorts the settings by the 3rd item, so that is the position in the table.
    def ReadSettingsTable(self, table, caller):

        Files = {
            "genmon": (self.GENMON_CONFIG, self.GENMON_SECTION),
            "mail": (self.MAIL_CONFIG, self.MAIL_SECTION),
            None: (None, None),  # worked out by genserv, not saved
        }
        ConfigSettings = collections.OrderedDict()
        try:
            for position, setting in enumerate(table, 1):
                if not self.SettingShown(setting.when):
                    continue
                if setting.file not in Files:
                    self.LogError("Invaild Config File in " + caller + ": " + str(setting.file))
                    continue
                FileName, Section = Files[setting.file]
                bounds = self.SettingValue(setting.bounds)
                if FileName is None:
                    value = self.SettingValue(setting.default)
                else:
                    value = self.ReadSingleConfigValue(
                        entry=setting.key,
                        filename=FileName,
                        section=Section,
                        type=setting.type,
                        default=self.SettingValue(setting.default),
                        bounds=bounds,
                    )
                ConfigSettings[setting.key] = [
                    setting.type, setting.title, position, value, "", bounds,
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
            except Exception:
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
        try:
            for addon in ADDONS:
                if self.SettingShown(addon.when) and self.AddOnAvailable(addon):
                    AddOnCfg[addon.name] = self.ReadAddOn(addon)
        except Exception as e1:
            self.LogErrorLine("Error in GetAddOns: " + str(e1))
        return AddOnCfg

    # -------------------------------------------------------------------------------
    # One add-on from the ADDONS table in genservsettings.py, as the browser gets it
    def ReadAddOn(self, addon):

        AddOn = collections.OrderedDict()
        AddOn["enable"] = self.ConfigFiles[self.GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section=addon.name, default=False
        )
        AddOn["title"] = addon.title
        AddOn["description"] = self.AddOnDescription(addon)
        AddOn["icon"] = addon.icon
        AddOn["url"] = addon.url
        if addon.params is None:
            AddOn["parameters"] = None
        else:
            AddOn["parameters"] = collections.OrderedDict()
            for param in addon.params:
                AddOn["parameters"][param.key] = self.ReadAddOnParam(addon, param)
        return AddOn

    # -------------------------------------------------------------------------------
    # The add-on's description, with a note if a library or hardware it needs is missing
    def AddOnDescription(self, addon):

        Description = addon.description
        for library in addon.libraries:
            try:
                __import__(library)
            except Exception:
                Description += MISSING_LIBRARY_NOTE
                break
        for check in addon.checks:
            if check == "i2c":
                missing = not os.path.exists("/dev/i2c-1") and not os.path.exists("/dev/i2c-2")
            elif check == "1wire":
                missing = not os.path.isdir("/sys/bus/w1/")
            elif check == "spi1":
                missing = not os.path.exists("/dev/spidev1.0")
            else:
                self.LogError("Unknown add-on check: " + str(check))
                continue
            if missing:
                Description += ADDON_CHECKS[check]
        return Description

    # -------------------------------------------------------------------------------
    # False if the add-on's config file was missing when genserv started
    def AddOnAvailable(self, addon):

        return addon.conf is None or self.AddOnConfigFile(addon) in self.ConfigFiles

    # -------------------------------------------------------------------------------
    # Full path of the config file an add-on's parameters are saved in
    def AddOnConfigFile(self, addon):

        if addon.conf is None:
            return self.GENLOADER_CONFIG
        return os.path.join(self.ConfigFilePath, addon.conf)

    # -------------------------------------------------------------------------------
    # One add-on parameter with its current value
    def ReadAddOnParam(self, addon, param):

        ReadTypes = {"int": int, "float": float, "boolean": bool}
        config = self.ConfigFiles[self.AddOnConfigFile(addon)]
        if param.special == "api_key":
            Value = self.GetAddOnAPIKey(addon, param)
        else:
            Value = config.ReadValue(
                param.key,
                return_type=param.read or ReadTypes.get(param.type, str),
                default=param.default,
            )
        return self.CreateAddOnParam(
            Value, param.type, param.description, bounds=param.bounds, display_name=param.title
        )

    # -------------------------------------------------------------------------------
    # An add-on's API key; one is made and saved if the config file has none
    def GetAddOnAPIKey(self, addon, param):

        config = self.ConfigFiles[self.AddOnConfigFile(addon)]
        key = config.ReadValue(param.key, return_type=str, default="")
        if not key:
            key = str(uuid.uuid4())
            config.WriteValue(param.key, key)
            self.LogError("Auto-generated API key for " + addon.name)
        return key

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

            # only add-ons in the ADDONS table and their parameters are saved
            AddOns = {addon.name: addon for addon in ADDONS}
            for module, entries in settings.items():  # module
                addon = AddOns.get(module)
                if addon is None:
                    self.LogError("Invalid module in SaveAddOnSettings: " + str(module))
                    continue
                if not self.AddOnAvailable(addon):
                    self.LogError("Missing config file for add-on in SaveAddOnSettings: " + module)
                    continue
                Params = {param.key: param for param in (addon.params or ())}
                # Find if it needs to be enabled / disabled or if there are parameters
                for basesettings, basevalues in entries.items():  # base settings
                    if basesettings == "enable":
                        if str(basevalues).lower() not in ("true", "false"):
                            self.LogError("Invalid enable value in SaveAddOnSettings: " + module)
                            continue
                        self.ConfigFiles[self.GENLOADER_CONFIG].WriteValue(
                            "enable", basevalues, section=module
                        )
                        # TODO This may not be needed now
                        if module in ["gentankutil", "gentankdiy", "genneevo"]:
                            # update genmon.conf also to let it know that it should watch for external fuel data
                            self.ConfigFiles[self.GENMON_CONFIG].WriteValue(
                                "use_external_fuel_data", basevalues, section="genmon"
                            )
                        if basevalues.lower() == "true":
                            # make an API key if the add-on has none when it is enabled
                            for param in Params.values():
                                if param.special == "api_key":
                                    self.GetAddOnAPIKey(addon, param)
                    if basesettings == "parameters":
                        for key, value in basevalues.items():
                            param = Params.get(key)
                            if param is None or param.type == "readonly":
                                self.LogError(
                                    "Invalid parameter in SaveAddOnSettings: " + module + ": " + str(key)
                                )
                                continue
                            value = str(value)
                            if "\n" in value or "\r" in value:
                                # a new line would add other entries to the config file
                                self.LogError(
                                    "Invalid value in SaveAddOnSettings: " + module + ": " + key
                                )
                                continue
                            self.ConfigFiles[self.AddOnConfigFile(addon)].WriteValue(key, value)

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

            import tarfile, io

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
    @staticmethod
    def _ca_cert_der(ca_path):
        """The certificate in the PEM file ca_path, in DER format (bytes)."""
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization

        with open(ca_path, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())
        return ca_cert.public_bytes(serialization.Encoding.DER)

    # -------------------------------------------------------------------------------
    def download_ca_der(self):
        """Serve the Local CA certificate in DER format for browser import."""
        try:
            ca_path = os.path.join(self.ConfigFilePath, "ca.crt")
            if not os.path.isfile(ca_path):
                return "CA certificate not found", 404
            der = self._ca_cert_der(ca_path)
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
            der = self._ca_cert_der(ca_path)
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
            except Exception:
                return commandResponse
        if not session.get("logged_in"):
            return self._render_login()
        else:
            commandResponse = self.ProcessCommand(command)
            try:
                json.loads(commandResponse)
                return Response(commandResponse, mimetype="application/json")
            except Exception:
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

                    self.MyClientInterface.ProcessMonitorCommand(command)
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
