#!/usr/bin/env python3
# ------------------------------------------------------------
#    FILE: test_genmon_api.py
# PURPOSE: Checks a running genmon.py and genserv.py: sends the read commands
#          to genmon (port 9082) and to the genserv web interface (/cmd/), and
#          checks every reply. Also checks that genserv passes on the same data
#          genmon returns.
#
#          This is a script to run against a live install (for example on the
#          Pi after an update), not a unit test: the unit tests in this folder
#          use a fake genmon. "python3 -m unittest discover -s tests" imports
#          this file but finds no tests in it.
#
#          By default only commands that read are sent. -x also sends the
#          commands that do something: settime (sets the generator clock), and
#          sendregisters / sendlogfiles (email the registers / log files to the
#          genmon developer).
#
#   USAGE: python3 test_genmon_api.py [options]
#
#          -a  address of genmon / genserv (default localhost)
#          -p  genmon port (default 9082)
#          -w  web port (default 8000, or 443 with -s)
#          -s  use HTTPS (the certificate is not checked, it is usually self signed)
#          -u  web interface user name, if a login is required
#          -P  web interface password
#          -o  MFA code, if the login uses multi-factor authentication
#          -m  only test genmon, not genserv
#          -g  only test genserv, not genmon
#          -x  also send settime, sendregisters and sendlogfiles
#          -v  print every reply
#          -h  help
#
#          Exit code 0 if every check passed, 1 if any failed.
#
# EXAMPLE: python3 test_genmon_api.py
#          python3 test_genmon_api.py -a genmon.local -s -u admin -P password
#
#  AUTHOR: Jason G Yates
#    DATE: 25-Apr-2018
# MODIFICATIONS: Nov-2026 Python 3, HTTPS / login / MFA / CSRF support, checks
#          replies (pass / fail and exit code), read only by default.
# ------------------------------------------------------------

import getopt
import json
import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genmonlib.mycommon import MyCommon
from genmonlib.mylog import SetupLogger
from genmonlib.program_defaults import ProgramDefaults

# genmon commands, sent as "generator: <command>"
GENMON_READ_COMMANDS = [
    "status", "maint", "outage", "monitor", "logs", "registers", "allregs",
    "network_status", "help",
    "status_json", "status_num_json", "maint_json", "maint_num_json",
    "outage_json", "outage_num_json", "monitor_json", "monitor_num_json",
    "logs_json", "registers_json", "allregs_json", "start_info_json",
    "gui_status_json", "weather_json", "power_log_json", "sensor_names_json",
    "get_maint_log_json", "support_data_json", "getreglabels_json",
    "getsitename", "getbase", "gethealth", "getdebug",
    "getregvalue=0000", "readregvalue=0000",
]
GENMON_WRITE_COMMANDS = ["settime", "sendregisters", "sendlogfiles"]

# genserv /cmd/ commands passed on to genmon
GENSERV_READ_COMMANDS = [
    "status", "status_json", "status_num_json", "maint", "maint_json", "maint_num_json",
    "outage", "outage_json", "outage_num_json", "monitor", "monitor_json", "monitor_num_json",
    "logs", "logs_json", "registers_json", "allregs_json", "start_info_json",
    "gui_status_json", "power_log_json", "sensor_names_json", "get_maint_log_json",
    "support_data_json", "getbase", "getsitename", "getdebug",
]
# genserv /cmd/ commands genserv answers itself
GENSERV_OWN_COMMANDS = ["getfavicon", "getreglabels", "csrf_token", "get_ui_prefs"]
# answered only for a user with write access (or with no login)
GENSERV_SETTINGS_COMMANDS = ["settings", "notifications", "get_add_on_settings", "get_advanced_settings"]
# POST only, need the CSRF token
GENSERV_WRITE_COMMANDS = ["settime", "sendregisters", "sendlogfiles"]

# commands whose data genserv must pass on unchanged (top level keys compared,
# the values change from one moment to the next)
COMPARE_COMMANDS = ["status_json", "maint_json", "outage_json", "monitor_json", "logs_json", "start_info_json"]

LOGIN_PAGE_MARKER = "Genmon &mdash; Login"
MFA_PAGE_MARKER = "Multi-Factor Authentication"


# ----------  Signal Handler ------------------------------------------
def signal_handler(signal, frame):
    sys.exit(0)


# ------------ MyTest class -----------------------------------------------------
class MyTest(MyCommon):
    def __init__(self, address="localhost", serverport=ProgramDefaults.ServerPort, webport=None,
                 https=False, user=None, password=None, otp=None, write=False, verbose=False):
        super(MyTest, self).__init__()

        self.Address = address
        self.ServerPort = serverport
        self.UseHTTPS = https
        self.WebPort = webport if webport else ("443" if https else "8000")
        self.User = user
        self.Password = password
        self.OTP = otp
        self.Write = write
        self.Verbose = verbose

        self.console = SetupLogger("test_genmon_api_console", log_file="", stream=True)
        self.log = self.console

        self.Passed = 0
        self.Failed = []
        self.Skipped = 0
        self.GenmonData = {}  # replies from genmon, to compare with genserv
        self.Session = None
        self.CSRFToken = None
        self.WriteAccess = True

        signal.signal(signal.SIGINT, signal_handler)

    # ---------------------------------------------------------------------------
    def Result(self, ok, name, detail="", reply=None):

        if ok is None:
            self.Skipped += 1
            status = "SKIP"
        elif ok:
            self.Passed += 1
            status = "PASS"
        else:
            self.Failed.append(name)
            status = "FAIL"
        self.LogConsole(status + "  " + name + (": " + detail if detail else ""))
        if self.Verbose and reply is not None and name.split(" ")[-1] in GENSERV_SETTINGS_COMMANDS:
            # the settings pages hold passwords and API keys, do not print them
            self.LogConsole("(reply not printed, it contains passwords and keys)")
        elif self.Verbose and reply is not None:
            self.LogConsole(reply if isinstance(reply, str) else json.dumps(reply, indent=2))

    # ---------------------------------------------------------------------------
    def CheckGenmonReply(self, command, reply):

        # returns (ok, detail, parsed reply)
        if reply is None or not len(reply):
            return False, "empty reply", None
        if reply.strip() == "Retry":
            return False, "genmon did not answer (Retry)", None
        if "No valid command recognized" in reply:
            return False, "genmon does not know this command", None
        if command.split("=")[0].endswith("_json"):
            try:
                data = json.loads(reply)
            except ValueError as e1:
                return False, "not valid JSON: " + str(e1), None
            return True, type(data).__name__ + " of " + str(len(data)), data
        if command == "gethealth" and reply.strip() != "OK":
            return False, "health is " + reply.strip(), None
        return True, str(len(reply)) + " characters", None

    # ---------------------------------------------------------------------------
    def TestGenMon(self):

        self.LogConsole("\n--- genmon at " + self.Address + ":" + str(self.ServerPort))
        from genmonlib.myclient import ClientInterface

        try:
            client = ClientInterface(host=self.Address, port=self.ServerPort, log=self.log)
        except SystemExit:
            # ClientInterface exits when it can not connect
            self.Result(False, "genmon connect", "unable to connect, is genmon running?")
            return

        commands = list(GENMON_READ_COMMANDS)
        if self.Write:
            commands += GENMON_WRITE_COMMANDS
        try:
            for command in commands:
                reply = client.ProcessMonitorCommand("generator: " + command)
                ok, detail, data = self.CheckGenmonReply(command, reply)
                if data is not None:
                    self.GenmonData[command] = data
                self.Result(ok, "genmon " + command, detail, reply)
        except Exception as e1:
            self.Result(False, "genmon", "error: " + str(e1))
        finally:
            client.Close()

    # ---------------------------------------------------------------------------
    def URL(self, path):

        scheme = "https" if self.UseHTTPS else "http"
        return scheme + "://" + self.Address + ":" + str(self.WebPort) + path

    # ---------------------------------------------------------------------------
    def WebGet(self, path):
        return self.Session.get(self.URL(path), verify=False, timeout=30)

    # ---------------------------------------------------------------------------
    def WebPost(self, path, data=None, headers=None):
        return self.Session.post(self.URL(path), data=data or {}, headers=headers or {},
                                 verify=False, timeout=30)

    # ---------------------------------------------------------------------------
    def WebLogin(self):

        # returns True if the commands can be sent
        r = self.WebGet("/")
        page = r.text
        # with HTTPS on, genserv answers the HTTP port with a redirect page
        if not self.UseHTTPS and ("Redirecting to" in page and "https://" in page or r.url.startswith("https")):
            self.Result(False, "genserv connect", "this port redirects to HTTPS, use -s and the HTTPS port")
            return False
        if LOGIN_PAGE_MARKER not in page:
            self.Result(True, "genserv connect", "no login required")
            return True
        if not self.User:
            self.Result(False, "genserv login", "a login is required, use -u and -P")
            return False

        r = self.WebPost("/", data={"username": self.User, "password": self.Password or ""})
        if MFA_PAGE_MARKER in r.text:
            if not self.OTP:
                self.Result(False, "genserv login", "MFA is required, use -o with a current code")
                return False
            self.WebPost("/mfa", data={"code": self.OTP})

        r = self.WebGet("/cmd/getsitename")
        if LOGIN_PAGE_MARKER in r.text or MFA_PAGE_MARKER in r.text:
            self.Result(False, "genserv login", "login failed (user name, password or MFA code)")
            return False
        self.Result(True, "genserv login", "logged in as " + self.User)
        return True

    # ---------------------------------------------------------------------------
    def CheckWebReply(self, command, response):

        # returns (ok, detail, parsed reply)
        if response.status_code != 200:
            return False, "HTTP status " + str(response.status_code), None
        if LOGIN_PAGE_MARKER in response.text:
            return False, "got the login page (session lost?)", None
        try:
            data = response.json()
        except ValueError:
            return False, "not valid JSON", None
        if data in ["Retry", "Access denied", "Read Only Mode"]:
            return False, "reply is " + data, None
        if command.endswith("_json") and not isinstance(data, (dict, list)):
            return False, "expected JSON data, got " + type(data).__name__, None
        return True, type(data).__name__ + " of " + str(len(data)) if hasattr(data, "__len__") else "", data

    # ---------------------------------------------------------------------------
    def TestGenServ(self):

        self.LogConsole("\n--- genserv at " + self.URL("/"))
        try:
            import requests
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except ImportError:
            self.Result(False, "genserv", "the requests library is not installed")
            return

        self.Session = requests.Session()
        try:
            if not self.WebLogin():
                return

            r = self.WebGet("/cmd/start_info_json")
            try:
                self.WriteAccess = bool(r.json().get("write_access", True))
            except Exception:
                pass

            for command in GENSERV_READ_COMMANDS + GENSERV_OWN_COMMANDS:
                r = self.WebGet("/cmd/" + command)
                ok, detail, data = self.CheckWebReply(command, r)
                self.Result(ok, "genserv " + command, detail, r.text)
                if ok and command == "csrf_token":
                    self.CSRFToken = data.get("csrf_token")
                if ok and command in COMPARE_COMMANDS:
                    self.Compare(command, data)

            for command in GENSERV_SETTINGS_COMMANDS:
                if not self.WriteAccess:
                    self.Result(None, "genserv " + command, "needs write access")
                    continue
                r = self.WebGet("/cmd/" + command)
                ok, detail, data = self.CheckWebReply(command, r)
                if ok and not isinstance(data, dict):
                    ok, detail = False, "expected the settings, got " + str(data)[:40]
                self.Result(ok, "genserv " + command, detail, r.text)

            # POST only commands must refuse GET
            r = self.WebGet("/cmd/sendregisters")
            self.Result(r.status_code == 405, "genserv GET of a POST only command",
                        "HTTP status " + str(r.status_code) + " (expected 405)")
            # ...and a GET with a wrong token in the URL (nothing is changed)
            r = self.WebGet("/cmd/setremote?setremote=stop&csrf_token=not-the-token")
            self.Result(r.status_code == 405, "genserv GET with a wrong csrf_token",
                        "HTTP status " + str(r.status_code) + " (expected 405)")

            if self.Write:
                headers = {"X-CSRFToken": self.CSRFToken or ""}
                for command in GENSERV_WRITE_COMMANDS:
                    r = self.WebPost("/cmd/" + command, headers=headers)
                    ok, detail, _ = self.CheckWebReply(command, r)
                    self.Result(ok, "genserv POST " + command, detail, r.text)
                # a GET with the token in the URL (tools that can only call a URL)
                r = self.WebGet("/cmd/settime?csrf_token=" + (self.CSRFToken or ""))
                ok, detail, _ = self.CheckWebReply("settime", r)
                self.Result(ok, "genserv GET settime with csrf_token", detail, r.text)

        except Exception as e1:
            self.Result(False, "genserv", "error: " + str(e1))

    # ---------------------------------------------------------------------------
    def Compare(self, command, web_data):

        genmon_data = self.GenmonData.get(command)
        if genmon_data is None:
            return  # genmon not tested, or its reply was not valid
        name = "genserv " + command + " matches genmon"
        if isinstance(genmon_data, dict) and isinstance(web_data, dict):
            # genserv adds keys to start_info_json, so only look for missing ones
            missing = [k for k in genmon_data if k not in web_data]
            self.Result(not missing, name, ("missing " + ", ".join(missing)) if missing else "same keys")
        else:
            same = type(genmon_data) == type(web_data)
            self.Result(same, name, "same type" if same else "different type")

    # ---------------------------------------------------------------------------
    def Summary(self):

        self.LogConsole("\n" + str(self.Passed) + " passed, " + str(len(self.Failed)) + " failed, "
                        + str(self.Skipped) + " skipped")
        if self.Failed:
            self.LogConsole("Failed: " + ", ".join(self.Failed))
        return 0 if not self.Failed else 1


# -------------------------------------------------------------------------------
if __name__ == "__main__":

    HelpStr = "\npython3 test_genmon_api.py [-a address] [-p genmon port] [-w web port] [-s] "
    HelpStr += "[-u user -P password [-o MFA code]] [-m | -g] [-x] [-v]\n\n"
    HelpStr += "      -a    address of genmon / genserv (default localhost)\n"
    HelpStr += "      -p    genmon port (default " + str(ProgramDefaults.ServerPort) + ")\n"
    HelpStr += "      -w    web port (default 8000, or 443 with -s)\n"
    HelpStr += "      -s    use HTTPS\n"
    HelpStr += "      -u    web interface user name\n"
    HelpStr += "      -P    web interface password\n"
    HelpStr += "      -o    MFA code\n"
    HelpStr += "      -m    only test genmon\n"
    HelpStr += "      -g    only test genserv\n"
    HelpStr += "      -x    also send settime, sendregisters and sendlogfiles (sets the generator\n"
    HelpStr += "            clock, emails registers / logs to the genmon developer)\n"
    HelpStr += "      -v    print every reply\n"
    HelpStr += "      -h    help\n"

    try:
        opts, args = getopt.getopt(
            sys.argv[1:], "ha:p:w:su:P:o:mgxv",
            ["help", "address=", "port=", "webport=", "https", "user=", "password=", "otp=",
             "genmon-only", "genserv-only", "write", "verbose"])
    except getopt.GetoptError:
        print("Invalid command line argument." + HelpStr)
        sys.exit(2)

    options = {}
    genmon_only = genserv_only = False
    try:
        for opt, arg in opts:
            if opt in ("-h", "--help"):
                print(HelpStr)
                sys.exit(0)
            elif opt in ("-a", "--address"):
                options["address"] = arg
            elif opt in ("-p", "--port"):
                options["serverport"] = int(arg)
            elif opt in ("-w", "--webport"):
                options["webport"] = arg
            elif opt in ("-s", "--https"):
                options["https"] = True
            elif opt in ("-u", "--user"):
                options["user"] = arg
            elif opt in ("-P", "--password"):
                options["password"] = arg
            elif opt in ("-o", "--otp"):
                options["otp"] = arg
            elif opt in ("-m", "--genmon-only"):
                genmon_only = True
            elif opt in ("-g", "--genserv-only"):
                genserv_only = True
            elif opt in ("-x", "--write"):
                options["write"] = True
            elif opt in ("-v", "--verbose"):
                options["verbose"] = True
    except Exception as e1:
        print("Error parsing: " + str(e1))
        sys.exit(2)

    Test = MyTest(**options)
    if not genserv_only:
        Test.TestGenMon()
    if not genmon_only:
        Test.TestGenServ()
    sys.exit(Test.Summary())
