#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: genserv_fixture.py
# PURPOSE: Shared setup for the genserv.py tests (test_genserv_*.py). Not a test
#          file itself.
#
#          GenServFixture starts genserv.py the way __main__ does, without a
#          generator, without genmon running and without opening a port:
#
#          - genserv.py is copied to a temporary folder, next to links to the
#            repository's static, templates, genmonlib and data folders and the
#            shell scripts, so files genserv writes next to itself (backups,
#            logs) stay out of the repository.
#          - conf/*.conf is copied to a temporary config folder, and the
#            settings for the chosen mode are written to genmon.conf.
#          - The genmon connection (ClientInterface) answers every command with
#            canned JSON, mail is faked, app.run does nothing, and
#            subprocess.check_output / subprocess.run are replaced, so no shell
#            script, reboot or shutdown runs. Every command is recorded in
#            fixture.calls.
#
#          GENSERV_PY=<file> in the environment tests that copy of genserv.py
#          instead of the one in the repository.
#
#          Modes: "open" (no login), "auth" (HTTPS, admin and read only users),
#          "auth_mfa" (adds MFA), "auth_localca" (HTTPS with a local CA).
#
#   USAGE: used by the test files, for example:
#              fixture = GenServFixture("auth")
#              fixture.start()
#              fixture.login(ADMIN_USER, ADMIN_PASS)
#              r = fixture.get("/cmd/status_json")
#              fixture.stop()
#
# -------------------------------------------------------------------------------

import glob
import json
import logging
import os
import runpy
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from unittest import mock

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

ADMIN_USER = "admin"
ADMIN_PASS = "secretpw"
RO_USER = "viewer"
RO_PASS = "viewpw"
# 32 characters (160 bits): newer pyotp versions refuse short secrets
MFA_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
BASE_URL = "https://localhost"  # the session cookie is Secure, so use https

# what the fake genmon returns for "generator: start_info_json"
START_INFO = {
    "fueltype": "Natural Gas",
    "model": "Test",
    "nominalKW": "22",
    "nominalRPM": "3600",
    "nominalfrequency": "60",
    "phase": "1",
    "Controller": "Evolution 2.0, Air Cooled",
    "Actual": "Evolution 2.0",
    "Linux": True,
    "RaspberryPi": True,
    "Platform": "pi",
    "SetGenTime": True,
    "import_config_file": None,
    "buttons": [],
    "pages": {},
    "version": "V1.0",
    "sitename": "TestSite",
    "UseMetric": False,
    "Sensors": {},
}

# files and folders genserv expects next to genserv.py
LINKED_FILES = ["static", "templates", "genmonlib", "data", "startgenmon.sh", "genmonmaint.sh"]


# -------------------------------------------------------------------------------
class GenServFixture(object):
    def __init__(self, mode="open", settings=None, extension_file=None, missing_conf=None):

        self.mode = mode
        self.missing_conf = missing_conf or []  # config files removed before genserv starts
        self.extra_settings = settings or {}
        self.extension_file = extension_file
        self.calls = []  # genmon commands, emails and shell commands, in order
        self.patches = []
        self.old_signals = {}
        self.added_path = None
        self.app = None
        self.instance = None
        self.module_globals = None
        self.client = None
        self.threads_before = set(threading.enumerate())

    # ---------------------------------------------------------------------------
    def start(self):

        # a fixed name under the temporary folder, so a coverage report can map
        # .../genserv_run_*/genmon/genserv.py back to the repository's genserv.py
        self.run_dir = os.path.join(tempfile.mkdtemp(prefix="genserv_run_"), "genmon")
        os.mkdir(self.run_dir)
        self.conf_dir = tempfile.mkdtemp(prefix="genserv_conf_") + os.sep
        self.log_dir = tempfile.mkdtemp(prefix="genserv_log_") + os.sep
        try:
            self._prepare_files()
            self._start_patches()
            self._run_main()
        except BaseException:
            self.stop()
            raise
        self.client = self.app.test_client()
        return self

    # ---------------------------------------------------------------------------
    def stop(self):

        self.wait_for_threads()
        for p in reversed(self.patches):
            p.stop()
        self.patches = []
        for signum, handler in self.old_signals.items():
            signal.signal(signum, handler)
        self.old_signals = {}
        if self.added_path is not None and self.added_path in sys.path:
            sys.path.remove(self.added_path)
        sys.modules.pop("genservext", None)
        logger = logging.getLogger("genserv_test_" + str(id(self)))
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
        run_parent = os.path.dirname(self.run_dir) if getattr(self, "run_dir", None) else None
        for folder in [run_parent, getattr(self, "conf_dir", None), getattr(self, "log_dir", None)]:
            if folder:
                shutil.rmtree(folder, ignore_errors=True)

    # ---------------------------------------------------------------------------
    def _prepare_files(self):

        for name in LINKED_FILES:
            os.symlink(os.path.join(REPO_DIR, name), os.path.join(self.run_dir, name))
        # GENSERV_PY=<file> tests another copy of genserv.py (for example an older version)
        source = os.environ.get("GENSERV_PY") or os.path.join(REPO_DIR, "genserv.py")
        shutil.copy(source, os.path.join(self.run_dir, "genserv.py"))
        if self.extension_file:
            shutil.copy(self.extension_file, os.path.join(self.run_dir, "genservext.py"))
            sys.path.insert(0, self.run_dir)
            self.added_path = self.run_dir
            sys.modules.pop("genservext", None)
        # files the backup and log commands send back (the faked scripts do not make them)
        for name in ["genmon_backup.tar.gz", "genmon_logs.tar.gz"]:
            with open(os.path.join(self.run_dir, name), "wb") as f:
                f.write(b"test archive")

        for f in glob.glob(os.path.join(REPO_DIR, "conf", "*.conf")):
            if os.path.basename(f) not in self.missing_conf:
                shutil.copy(f, self.conf_dir)

        from genmonlib.myconfig import MyConfig

        settings = {
            # fixed secrets so every run gives the same tokens and pages
            "secret_key": "ab" * 24,
            "secretmfa": MFA_SECRET,
            "secret_key_auth_mode": "open",
        }
        if self.mode.startswith("auth"):
            settings.update({
                "secret_key_auth_mode": "auth",
                "usehttps": "True",
                "cert_mode": "selfsigned",
                "http_user": ADMIN_USER,
                "http_pass": ADMIN_PASS,
                "http_user_ro": RO_USER,
                "http_pass_ro": RO_PASS,
            })
        if self.mode == "auth_mfa":
            settings.update({"usemfa": "True", "mfa_enrolled": "True", "mfa_trust_extend": "True"})
        if self.mode == "auth_localca":
            settings["cert_mode"] = "localca"
        settings.update(self.extra_settings)

        if "genmon.conf" not in self.missing_conf:
            config = MyConfig(filename=self.conf_path("genmon.conf"), section="GenMon")
            for key, value in settings.items():
                config.WriteValue(key, value)

    # ---------------------------------------------------------------------------
    def _start_patches(self):

        import flask
        import genmonlib.myclient
        import genmonlib.mymail
        import genmonlib.myplatform
        import genmonlib.mysupport

        fixture = self

        class FakeClient(object):
            def __init__(self, *args, **kwargs):
                pass

            def WaitForReady(self, timeout=0):
                return True

            def ProcessMonitorCommand(self, cmd):
                fixture.calls.append(cmd)
                if cmd == "generator: gethealth":
                    return "OK"
                if cmd == "generator: start_info_json":
                    return json.dumps(START_INFO)
                if "reglabels" in cmd or cmd.startswith("generator: get_register_labels"):
                    return json.dumps({})
                return json.dumps({"fake_response_for": cmd})

            def Close(self):
                pass

        class FakeMail(object):
            SenderAccount = "genmon@example.com"
            DisableEmail = False
            DisableSMTP = False

            def __init__(self, *args, **kwargs):
                pass

            def sendEmail(self, *args, **kwargs):
                fixture.calls.append("sendEmail")
                return True

            def sendEmailDirectMIME(self, *args, **kwargs):
                fixture.calls.append("sendEmailDirectMIME")
                return True

            @staticmethod
            def TestSendSettings(**kwargs):
                fixture.calls.append("TestSendSettings " + str(kwargs.get("smtp_server")))
                fixture.test_email_settings = kwargs
                return "Success"

        def fake_check_output(cmd, *args, **kwargs):
            fixture.calls.append("SHELL " + fixture._command_text(cmd))
            return b"script ok output"

        def fake_run(cmd, *args, **kwargs):
            fixture.calls.append("RUN " + fixture._command_text(cmd))
            return subprocess.CompletedProcess(cmd, 0)

        log = logging.getLogger("genserv_test_" + str(id(self)))
        log.propagate = False
        log.addHandler(logging.FileHandler(os.path.join(self.log_dir, "genserv.log")))
        console = logging.getLogger("genserv_test_console")
        console.propagate = False
        if not console.handlers:
            console.addHandler(logging.NullHandler())
        setup_result = (console, self.conf_dir, "127.0.0.1", 9082, self.log_dir, log)

        self.patches = [
            mock.patch.object(genmonlib.myclient, "ClientInterface", FakeClient),
            mock.patch.object(genmonlib.mymail, "MyMail", FakeMail),
            mock.patch.object(flask.Flask, "run", lambda *args, **kwargs: None),
            mock.patch.object(genmonlib.mysupport.MySupport, "SetupAddOnProgram",
                              staticmethod(lambda *args, **kwargs: setup_result)),
            # the same on every machine, so shell commands use the .sh names
            mock.patch.object(genmonlib.myplatform.MyPlatform, "IsOSLinux", staticmethod(lambda: True)),
            mock.patch.object(subprocess, "check_output", fake_check_output),
            mock.patch.object(subprocess, "run", fake_run),
        ]
        for p in self.patches:
            p.start()
        for signum in [signal.SIGINT, signal.SIGTERM]:
            self.old_signals[signum] = signal.getsignal(signum)

    # ---------------------------------------------------------------------------
    def _run_main(self):

        target = os.path.join(self.run_dir, "genserv.py")
        old_argv = sys.argv
        sys.argv = [target]

        # In HTTPS mode Run() starts the HTTP -> HTTPS redirect server, which
        # opens a real port (8000 by default, in use on a running genmon). Record
        # it instead of starting it.
        fixture = self
        original_start = threading.Thread.start

        def thread_start(thread):
            target_func = getattr(thread, "_target", None)
            if getattr(target_func, "__name__", "") == "StartHTTPRedirectServer":
                fixture.calls.append("REDIRECT SERVER")
                return
            original_start(thread)

        try:
            with mock.patch.object(threading.Thread, "start", thread_start):
                module_globals = runpy.run_path(target, run_name="__main__")
        finally:
            sys.argv = old_argv
        if "GenServInstance" not in module_globals:
            raise RuntimeError(
                "genserv.py (" + (os.environ.get("GENSERV_PY") or os.path.join(REPO_DIR, "genserv.py"))
                + ") did not create GenServInstance; these tests need the class based genserv.py")
        self.app = module_globals["app"]
        self.instance = module_globals["GenServInstance"]
        # run_path returns a copy of the module globals, use the live ones
        self.module_globals = self.app.view_functions["root"].__globals__

        # A restart runs startgenmon.sh from a thread after 2 seconds. Run it
        # straight away (still through the faked shell) so it cannot run after
        # the fakes are removed, and so tests do not have to wait.
        instance = self.instance

        def restart_now():
            instance.RunBashScript("startgenmon.sh restart -c " + instance.ConfigFilePath)

        instance._do_restart = restart_now

    # ---------------------------------------------------------------------------
    def wait_for_threads(self, timeout=5):

        # wait for threads genserv started (restart) to finish
        for t in threading.enumerate():
            if t is not threading.current_thread() and t not in self.threads_before:
                t.join(timeout)
        if self.instance is not None:
            self.instance.Restarting = False

    # ---------------------------------------------------------------------------
    def _command_text(self, cmd):

        if isinstance(cmd, (list, tuple)):
            cmd = " ".join(str(c) for c in cmd)
        cmd = str(cmd)
        for folder, label in [(self.run_dir, "<RUN>"), (self.conf_dir, "<CONF>/"), (self.log_dir, "<LOG>/")]:
            # macOS temp folders are reached through a link (/var -> /private/var)
            for path in [os.path.realpath(folder) + (os.sep if folder.endswith(os.sep) else ""), folder]:
                cmd = cmd.replace(path, label)
        return cmd

    # ------------------------------------------------------------- helpers -----
    def conf_path(self, filename):
        return os.path.join(self.conf_dir, filename)

    def read_conf(self, filename):
        with open(self.conf_path(filename)) as f:
            return f.read()

    def conf_value(self, filename, key, section=None):
        from genmonlib.myconfig import MyConfig

        config = MyConfig(filename=self.conf_path(filename), section=section)
        return config.ReadValue(key, default=None)

    def shell_calls(self):
        return [c for c in self.calls if c.startswith(("SHELL ", "RUN "))]

    def csrf_headers(self):
        with self.app.app_context():
            return {"X-CSRFToken": self.instance.CSRFToken()}

    def _finish(self, response):
        # read the body and close the response, so files Flask sends are closed
        response.get_data()
        response.close()
        return response

    def get(self, path, **kwargs):
        return self._finish(self.client.get(path, base_url=BASE_URL, **kwargs))

    def post(self, path, **kwargs):
        response = self._finish(self.client.post(path, base_url=BASE_URL, **kwargs))
        # saves restart genmon from a thread; let it finish so the next request
        # is not answered with "Closing"
        self.wait_for_threads()
        return response

    def post_cmd(self, command, data=None, csrf=True, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        if csrf:
            headers.update(self.csrf_headers())
        return self.post("/cmd/" + command, data=data or {}, headers=headers, **kwargs)

    def get_json(self, path):
        return json.loads(self.get(path).get_data(as_text=True))

    def login(self, username, password):
        return self.post("/", data={"username": username, "password": password})

    def logout(self):
        return self.get("/logout")

    def new_session(self):
        # a new browser: no cookies, and no OTP rate limit or login lockout left over
        self.client = self.app.test_client()
        self.instance.LastOTPSendTime = None
        self.instance.LoginAttempts = 0
        self.instance.WebUILocked = False

    def is_logged_in(self):
        # status_json is passed to genmon only for a logged in session
        before = len(self.calls)
        self.get("/cmd/status_json")
        return any("status_json" in c for c in self.calls[before:])
