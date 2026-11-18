#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_genloader.py
# PURPOSE: Tests for genloader.py: reading and checking genloader.conf, the
#          load order, which libraries are needed and whether they are
#          installed, the list of libraries compared with requirements.txt
#          and the imports in the programs, starting and stopping
#          modules, running pip and other commands, replacing genloader.conf,
#          and the one time file move.
#
#          The tests make a Loader without running its __init__ (which would
#          read /etc/genmon and start programs) and replace the calls that start
#          processes with fakes, so nothing is installed, started or killed.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_genloader
#
# -------------------------------------------------------------------------------

import ast
import glob
import json
import logging
import re
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_DIR)

import genloader


class ListHandler(logging.Handler):
    def __init__(self):
        super(ListHandler, self).__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


class FakeProcess(object):
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.output = (stdout, stderr)
        self.pid = 4321

    def communicate(self):
        return self.output


def make_logger(name):
    logger = logging.getLogger("test_genloader_" + name)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = ListHandler()
    logger.addHandler(handler)
    return logger, handler


# -------------------------------------------------------------------------------
class GenLoaderTests(unittest.TestCase):

    def setUp(self):
        self.loader = genloader.Loader.__new__(genloader.Loader)
        self.loader.log, self.log = make_logger("log")
        self.loader.console, _ = make_logger("console")
        self.loader.HardStop = False
        self.loader.bSystemIsNotLinux = False
        self.loader.bSystemIsWindows = False
        self.loader.ConfigFilePath = "/etc/genmon/"
        self.loader.PIDFile = "/nonexistent/genloader.pids"

    def test_python_version(self):
        with mock.patch.object(genloader.sys, "version_info", (3, 9, 2)):
            self.assertTrue(self.loader.PythonSupported())
        self.assertEqual(self.log.messages, [])
        with mock.patch.object(genloader.sys, "version_info", (3, 7, 3)):
            self.assertFalse(self.loader.PythonSupported())
        self.assertIn("ERROR: genmon needs Python 3.9 or higher, this is Python 3.7. "
                      "The genmon modules were not started.", self.log.messages)

    def test_is_windows(self):
        for platform, expected in [("win32", True), ("darwin", False), ("linux", False)]:
            with self.subTest(platform=platform):
                with mock.patch.object(genloader.sys, "platform", platform):
                    self.assertEqual(genloader.Loader.IsWindows(), expected)

    # ---- LibraryIsInstalled -----------------------------------------------
    def test_parse_version(self):
        for text, expected in [("7.1.21", (7, 1, 21)), ("2.0.0rc1", (2, 0, 0)),
                               ("1.6.1.post0", (1, 6, 1)), ("unknown", None)]:
            with self.subTest(version=text):
                self.assertEqual(genloader.Loader.ParseVersion(text), expected)

    def test_installed_version(self):
        with mock.patch.object(genloader.metadata, "version", return_value="1.2.3") as version:
            self.assertEqual(genloader.Loader.InstalledVersion(
                "bleson @ git+https://github.com/TheCellule/python-bleson"), "1.2.3")
        version.assert_called_once_with("bleson")
        # a name pip spells differently from the package information
        dist = mock.Mock(version="24.2.1", metadata={"Name": "pyOpenSSL"})
        with mock.patch.object(genloader.metadata, "version",
                               side_effect=genloader.metadata.PackageNotFoundError("pyopenssl")), \
                mock.patch.object(genloader.metadata, "distributions", return_value=[dist]):
            self.assertEqual(genloader.Loader.InstalledVersion("pyopenssl"), "24.2.1")
            self.assertIsNone(genloader.Loader.InstalledVersion("not_installed"))

    def installed(self, found=True, version=None, needed=None, **kwargs):
        spec = object() if found else None
        with mock.patch.object(genloader.importlib.util, "find_spec", return_value=spec) as find, \
                mock.patch.object(genloader.importlib, "import_module") as imp, \
                mock.patch.object(genloader.Loader, "InstalledVersion", return_value=version):
            result = self.loader.LibraryIsInstalled("pyotp", needed, installname="pyotp", **kwargs)
        return result, find, imp

    def test_library_is_installed(self):
        self.assertTrue(self.installed()[0])
        self.assertFalse(self.installed(found=False)[0])
        # the library is found, not imported
        _, find, imp = self.installed()
        find.assert_called_once_with("pyotp")
        imp.assert_not_called()

    def test_library_version(self):
        # pyotp has no __version__, so this was never checked before
        self.assertTrue(self.installed(version="2.9.0", needed="2.3.0")[0])
        self.assertFalse(self.installed(version="2.0.0", needed="2.3.0")[0])
        self.assertIn("Need update on pyotp from 2.0.0 to 2.3.0", self.log.messages)
        self.assertTrue(self.installed(version="2.3.0rc1", needed="2.3.0")[0])
        # no package information: the version is not known, accept it
        self.assertTrue(self.installed(version=None, needed="2.3.0")[0])

    def test_library_test_import(self):
        # ldap3 can be installed but fail to import (pyasn1 version)
        result, find, imp = self.installed(testimport=True)
        self.assertTrue(result)
        imp.assert_called_once_with("pyotp")
        with mock.patch.object(genloader.importlib, "import_module", side_effect=ImportError("x")):
            self.assertFalse(self.loader.LibraryIsInstalled("ldap3", testimport=True))

    # ---- LoadModule ---------------------------------------------------------
    def start(self, args):
        with mock.patch.object(genloader.subprocess, "Popen", return_value=FakeProcess()) as popen, \
                mock.patch.object(self.loader, "UpdatePID", return_value=True):
            self.assertTrue(self.loader.LoadModule("/genmon/addon", "genlog.py", args=args))
        return popen.call_args

    def test_start_module_without_args(self):
        # a section with no args entry gives None
        for args in [None, "", "   "]:
            with self.subTest(args=args):
                call = self.start(args)
                self.assertEqual(call[0][0], [sys.executable, "/genmon/addon/genlog.py",
                                              "-c", "/etc/genmon/"])

    def test_start_module_with_args(self):
        call = self.start("  -f   /home/pi/LogFile.csv ")
        self.assertEqual(call[0][0], [sys.executable, "/genmon/addon/genlog.py",
                                      "-f", "/home/pi/LogFile.csv", "-c", "/etc/genmon/"])

    def test_module_output_not_piped(self):
        # genloader exits after starting the modules, nothing would read a pipe
        call = self.start(None)
        for stream in ["stdout", "stderr", "stdin"]:
            self.assertEqual(call[1][stream], subprocess.DEVNULL)

    # ---- InstallLibrary / ExecuteCommandList ------------------------------
    def run_pip(self, process):
        with mock.patch.object(genloader, "Popen", return_value=process), \
                mock.patch.object(self.loader, "CheckBaseSoftware", return_value=True):
            return self.loader.InstallLibrary("chump")

    def test_install_library_ok_with_warning(self):
        # pip writes warnings to stderr even when the install works
        self.assertTrue(self.run_pip(FakeProcess(0, stderr=b"WARNING: Running pip as root")))
        self.assertEqual(self.log.messages, [])

    def test_install_library_failed(self):
        self.assertFalse(self.run_pip(FakeProcess(1, stderr=b"ERROR: No matching distribution")))
        self.assertTrue(any("No matching distribution" in m for m in self.log.messages))

    def test_execute_command_list(self):
        cases = [(FakeProcess(0, stderr=b"W: some warning"), True),
                 (FakeProcess(100, stderr=b"E: failed"), False)]
        for process, expected in cases:
            with self.subTest(returncode=process.returncode):
                with mock.patch.object(genloader, "Popen", return_value=process):
                    self.assertEqual(self.loader.ExecuteCommandList(["apt-get", "update"]), expected)
        with mock.patch.object(genloader, "Popen", side_effect=FileNotFoundError("cmake")):
            self.assertFalse(self.loader.ExecuteCommandList(["cmake", "--version"]))

    # ---- StopModules ------------------------------------------------------
    def test_stop_continues_after_an_error(self):
        self.loader.LoadOrder = ["genslack", "genlog", "genmon"]
        self.loader.CachedConfig = {
            name: {"module": name + ".py", "pid": 100 + n, "hardstop": False}
            for n, name in enumerate(self.loader.LoadOrder)
        }
        stopped = []

        def unload(module, **kwargs):
            stopped.append(module)
            if module == "genlog.py":
                raise RuntimeError("test error")
            return True

        with mock.patch.object(self.loader, "UnloadModule", side_effect=unload):
            self.assertFalse(self.loader.StopModules())
        self.assertEqual(stopped, ["genslack.py", "genlog.py", "genmon.py"])

    # ---- OneTimeMaint -----------------------------------------------------
    def test_one_time_maint_logs_errors(self):
        # an error moving the old files is logged (a plain logger, no LogLine)
        log, handler = make_logger("maint")
        with mock.patch.object(genloader.os.path, "isfile", return_value=True), \
                mock.patch.object(genloader.os.path, "isdir", return_value=False), \
                mock.patch.object(genloader.os, "mkdir", side_effect=OSError("read only")), \
                mock.patch.object(genloader.MySupport, "CopyFile", side_effect=OSError("copy")):
            self.assertTrue(genloader.Loader.OneTimeMaint("/nonexistent/genmon/", log))
        self.assertIn("Error validating target directory: read only", handler.messages)


    # ---- CopyConfFile / GetConfig -----------------------------------------
    def conf_dirs(self):
        folder = tempfile.mkdtemp(prefix="genloader_test_")
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        self.loader.ConfPath = os.path.join(REPO_DIR, "conf")
        self.loader.ConfigFileName = "genloader.conf"
        self.loader.configfile = os.path.join(folder, "genloader.conf")
        return folder

    def test_replacing_conf_file_keeps_a_backup(self):
        folder = self.conf_dirs()
        with open(self.loader.configfile, "w") as f:
            f.write("[genmon]\nmodule = genmon.py\n# the user's file\n")
        self.assertTrue(self.loader.CopyConfFile())
        backups = glob.glob(os.path.join(folder, "genloader.conf.bak-*"))
        self.assertEqual(len(backups), 1)
        with open(backups[0]) as f:
            self.assertIn("# the user's file", f.read())
        with open(self.loader.configfile) as f, \
                open(os.path.join(REPO_DIR, "conf", "genloader.conf")) as default:
            self.assertEqual(f.read(), default.read())
        self.assertTrue(any(backups[0] in m for m in self.log.messages))

    def test_copying_missing_conf_file_makes_no_backup(self):
        folder = self.conf_dirs()
        self.assertTrue(self.loader.CopyConfFile())
        self.assertTrue(os.path.isfile(self.loader.configfile))
        self.assertEqual(glob.glob(os.path.join(folder, "genloader.conf.bak-*")), [])

    def test_get_config_starts_over(self):
        from genmonlib.myconfig import MyConfig

        self.conf_dirs()
        self.loader.CopyConfFile()
        self.loader.config = MyConfig(filename=self.loader.configfile, section="genmon",
                                      log=self.loader.log)
        self.loader.NewInstall = False
        self.loader.Upgrade = False
        self.loader.CachedConfig = {"old_module": {"enable": True}}
        self.assertTrue(self.loader.GetConfig())
        self.assertNotIn("old_module", self.loader.CachedConfig)
        self.assertIn("genserv", self.loader.CachedConfig)

    # ---- PIDIsModule / UnloadModule ---------------------------------------
    def fake_psutil(self, cmdline=None, error=None):
        module = types.ModuleType("psutil")

        class NoSuchProcess(Exception):
            pass

        class AccessDenied(Exception):
            pass

        class Process(object):
            def __init__(self, pid):
                if error == "gone":
                    raise NoSuchProcess(pid)
                self.pid = pid

            def cmdline(self):
                if error == "denied":
                    raise AccessDenied(self.pid)
                return cmdline

        module.NoSuchProcess = NoSuchProcess
        module.AccessDenied = AccessDenied
        module.Process = Process
        return mock.patch.dict(sys.modules, {"psutil": module})

    def test_pid_is_module(self):
        cmdline = [sys.executable, "/home/pi/genmon/addon/genlog.py", "-c", "/etc/genmon/"]
        with self.fake_psutil(cmdline):
            self.assertTrue(self.loader.PIDIsModule(123, "genlog.py"))
            self.assertTrue(self.loader.PIDIsModule("123", "genlog.py"))
            self.assertFalse(self.loader.PIDIsModule(123, "genslack.py"))
            self.assertFalse(self.loader.PIDIsModule("", "genlog.py"))
        with self.fake_psutil(error="gone"):
            self.assertFalse(self.loader.PIDIsModule(123, "genlog.py"))
        with self.fake_psutil(error="denied"):
            self.assertTrue(self.loader.PIDIsModule(123, "genlog.py"))  # can not tell

    def test_pid_is_module_without_psutil(self):
        data = b"/usr/bin/python3\0/home/pi/genmon/genserv.py\0-c\0/etc/genmon/\0"
        with mock.patch.dict(sys.modules, {"psutil": None}), \
                mock.patch.object(genloader.os.path, "isdir", return_value=True), \
                mock.patch.object(genloader.os.path, "isfile", return_value=True), \
                mock.patch("builtins.open", mock.mock_open(read_data=data)):
            self.assertTrue(self.loader.PIDIsModule(123, "genserv.py"))
            self.assertFalse(self.loader.PIDIsModule(123, "genmon.py"))
        with mock.patch.dict(sys.modules, {"psutil": None}), \
                mock.patch.object(genloader.os.path, "isdir", return_value=True), \
                mock.patch.object(genloader.os.path, "isfile", return_value=False):
            self.assertFalse(self.loader.PIDIsModule(123, "genserv.py"))

    def unload(self, cmdline):
        with self.fake_psutil(cmdline), \
                mock.patch.object(genloader, "Popen", return_value=FakeProcess()) as popen, \
                mock.patch.object(self.loader, "UpdatePID", return_value=True) as update:
            self.assertTrue(self.loader.UnloadModule("genlog.py", pid=123, UsePID=True))
        update.assert_called_once_with("genlog.py", "")
        return popen

    def test_stop_module_by_pid(self):
        popen = self.unload([sys.executable, "/home/pi/genmon/addon/genlog.py"])
        self.assertEqual(popen.call_args[0][0], ["kill", "123"])

    def test_old_pid_is_not_killed(self):
        # the PID now belongs to another program
        popen = self.unload(["/usr/sbin/sshd", "-D"])
        popen.assert_not_called()



# -------------------------------------------------------------------------------
class GenLoaderConfigTests(unittest.TestCase):
    """GetConfig, ValidateConfig, GetLoadOrder, GetModuleList and StartModules,
    with a copy of conf/genloader.conf in a temporary config folder."""

    def setUp(self):
        from genmonlib.myconfig import MyConfig

        self.folder = tempfile.mkdtemp(prefix="genloader_conf_") + os.sep
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        loader = genloader.Loader.__new__(genloader.Loader)
        loader.log, self.log = make_logger("conf_log")
        loader.console, _ = make_logger("conf_console")
        loader.ConfigFilePath = self.folder
        loader.PIDFile = os.path.join(self.folder, "genloader.pids")
        loader.ConfigFileName = "genloader.conf"
        loader.configfile = os.path.join(self.folder, "genloader.conf")
        loader.ConfPath = os.path.join(REPO_DIR, "conf")
        loader.ModulePath = REPO_DIR
        loader.bSystemIsNotLinux = False
        loader.MultiInstance = False
        loader.NewInstall = False
        loader.Upgrade = False
        loader.CachedConfig = {}
        shutil.copy(os.path.join(REPO_DIR, "conf", "genloader.conf"), loader.configfile)
        loader.config = MyConfig(filename=loader.configfile, section="genmon", log=loader.log)
        self.loader = loader
        self.MyConfig = MyConfig

    def remove_section(self, section):
        with open(self.loader.configfile) as f:
            lines = f.read().split("\n")
        out, skip = [], False
        for line in lines:
            if line.startswith("["):
                skip = line.strip() == "[" + section + "]"
            if not skip:
                out.append(line)
        with open(self.loader.configfile, "w") as f:
            f.write("\n".join(out))
        self.loader.config = self.MyConfig(filename=self.loader.configfile, section="genmon",
                                           log=self.loader.log)

    def write_conf(self, filename, section, values):
        with open(os.path.join(self.folder, filename), "w") as f:
            f.write("[" + section + "]\n")
            for key, value in values.items():
                f.write("%s = %s\n" % (key, value))

    # ---- GetConfig --------------------------------------------------------
    def test_get_config(self):
        import configparser

        template = configparser.RawConfigParser()
        template.read(self.loader.configfile)
        self.assertTrue(self.loader.GetConfig())
        self.assertEqual(sorted(self.loader.CachedConfig),
                         sorted(s for s in template.sections() if s != "genloader"))
        genmon = self.loader.CachedConfig["genmon"]
        self.assertEqual(genmon["module"], "genmon.py")
        self.assertIs(genmon["enable"], True)
        self.assertEqual(genmon["priority"], 0)
        self.assertEqual(genmon["postloaddelay"], 4)
        self.assertEqual(genmon["conffile"], "genmon.conf,mymail.conf")
        self.assertIs(self.loader.CachedConfig["genslack"]["enable"], False)

    def test_get_config_adds_missing_add_on(self):
        self.remove_section("genslack")
        self.assertTrue(self.loader.GetConfig())
        genslack = self.loader.CachedConfig["genslack"]
        self.assertEqual(genslack["module"], "genslack.py")
        self.assertEqual(genslack["conffile"], "genslack.conf")
        self.assertIs(genslack["enable"], False)
        self.assertIn("Warning: Missing entry: genslack, adding entry", self.log.messages)

    def test_get_config_missing_genmon_section(self):
        self.remove_section("genmon")
        self.assertFalse(self.loader.GetConfig())

    def edit_conf(self, section, option, value):
        # set (or with value None remove) an option in the test genloader.conf
        with open(self.loader.configfile) as f:
            lines = f.read().split("\n")
        out, current = [], None
        for line in lines:
            if line.startswith("["):
                current = line.strip()[1:-1]
            elif current == section and line.split("=")[0].strip() == option:
                if value is not None:
                    out.append(option + " = " + value)
                continue
            out.append(line)
        with open(self.loader.configfile, "w") as f:
            f.write("\n".join(out))
        self.loader.config = self.MyConfig(filename=self.loader.configfile, section="genmon",
                                           log=self.loader.log)

    def test_get_config_adds_any_missing_template_section(self):
        # gensms was not in the old list of sections to add
        self.remove_section("gensms")
        self.assertTrue(self.loader.GetConfig())
        self.assertEqual(self.loader.CachedConfig["gensms"]["module"], "gensms.py")
        self.assertEqual(self.loader.CachedConfig["gensms"]["conffile"], "gensms.conf")
        self.assertEqual(self.loader.CachedConfig["gensms"]["priority"], 2)

    def test_get_config_adds_missing_option(self):
        self.edit_conf("genslack", "priority", None)
        self.assertTrue(self.loader.GetConfig())
        self.assertEqual(self.loader.CachedConfig["genslack"]["priority"], 2)
        self.assertIn("Adding priority to genslack", self.log.messages)

    def test_get_config_fills_empty_conffile(self):
        # an old genloader.conf had an empty conffile for gengpio
        self.edit_conf("gengpio", "conffile", "")
        self.edit_conf("gensyslog", "conffile", "")  # gensyslog has no config file
        self.assertTrue(self.loader.GetConfig())
        self.assertEqual(self.loader.CachedConfig["gengpio"]["conffile"], "gengpio.conf")
        self.assertEqual(self.loader.CachedConfig["gensyslog"]["conffile"], "")

    def test_get_config_keeps_user_values_and_sections(self):
        self.edit_conf("genslack", "enable", "True")
        self.edit_conf("gensyslog", "args", "-x test")
        with open(self.loader.configfile, "a") as f:
            f.write("\n[mymodule]\nmodule = mymodule.py\nenable = False\nhardstop = False\n"
                    "conffile =\nargs =\npriority = 5\n")
        self.loader.config = self.MyConfig(filename=self.loader.configfile, section="genmon",
                                           log=self.loader.log)
        self.assertTrue(self.loader.GetConfig())
        self.assertIs(self.loader.CachedConfig["genslack"]["enable"], True)
        self.assertEqual(self.loader.CachedConfig["gensyslog"]["args"], "-x test")
        self.assertEqual(self.loader.CachedConfig["mymodule"]["priority"], 5)

    def test_get_config_without_template(self):
        self.loader.ConfPath = os.path.join(self.folder, "no_conf_folder")
        self.assertTrue(self.loader.GetConfig())
        self.assertIn("genslack", self.loader.CachedConfig)

    def test_maintenance_uses_config_folder(self):
        # renames <config folder>/templogs/templog* to sensordata/sensor*
        os.mkdir(os.path.join(self.folder, "templogs"))
        open(os.path.join(self.folder, "templogs", "templog_test.csv"), "w").close()
        self.loader.Maintenance()
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "sensordata", "sensor_test.csv")))

    # ---- PIDs (genloader.pids) --------------------------------------------
    def add_option(self, section, option, value):
        with open(self.loader.configfile) as f:
            text = f.read()
        text = text.replace("[" + section + "]\n", "[" + section + "]\n" + option + " = " + value + "\n", 1)
        with open(self.loader.configfile, "w") as f:
            f.write(text)
        self.loader.config = self.MyConfig(filename=self.loader.configfile, section="genmon",
                                           log=self.loader.log)

    def conf_text(self):
        with open(self.loader.configfile) as f:
            return f.read()

    def pid_file(self):
        with open(self.loader.PIDFile) as f:
            return json.load(f)

    def test_pids_are_not_saved_in_genloader_conf(self):
        self.loader.GetConfig()
        before = self.conf_text()
        self.assertTrue(self.loader.UpdatePID("genslack.py", 1234))
        self.assertTrue(self.loader.UpdatePID("genmon.py", 99))
        self.assertEqual(self.pid_file(), {"genmon": 99, "genslack": 1234})
        self.assertTrue(self.loader.UpdatePID("genslack.py", ""))
        self.assertEqual(self.pid_file(), {"genmon": 99})
        self.assertEqual(self.conf_text(), before)

    def test_old_pids_moved_from_genloader_conf(self):
        self.add_option("genslack", "pid", "1234")
        self.add_option("genmon", "pid", "")
        self.assertTrue(self.loader.GetConfig())
        self.assertEqual(self.loader.CachedConfig["genslack"]["pid"], 1234)
        self.assertEqual(self.loader.CachedConfig["genmon"]["pid"], 0)
        self.assertEqual(self.pid_file(), {"genslack": 1234})
        self.assertNotIn("pid =", self.conf_text())
        self.assertTrue(any(m.startswith("Moved the module PIDs") for m in self.log.messages))

    def test_restored_genloader_conf_with_pids(self):
        # genloader.pids exists, the old entries in genloader.conf are not used
        with open(self.loader.PIDFile, "w") as f:
            json.dump({"genserv": 55}, f)
        self.add_option("genserv", "pid", "99")
        self.assertTrue(self.loader.GetConfig())
        self.assertEqual(self.loader.CachedConfig["genserv"]["pid"], 55)
        self.assertEqual(self.pid_file(), {"genserv": 55})
        self.assertNotIn("pid =", self.conf_text())
        self.assertIn("Removed old PID entries from genloader.conf", self.log.messages)

    def test_damaged_pid_file(self):
        with open(self.loader.PIDFile, "w") as f:
            f.write("not json")
        self.assertTrue(self.loader.GetConfig())
        self.assertEqual(self.loader.CachedConfig["genmon"]["pid"], 0)
        self.assertTrue(self.loader.UpdatePID("genmon.py", 77))
        self.assertEqual(self.pid_file(), {"genmon": 77})

    def test_start_then_stop_uses_pid_file(self):
        self.loader.GetConfig()
        self.loader.HardStop = False
        with mock.patch.object(genloader.subprocess, "Popen", return_value=FakeProcess()):
            self.assertTrue(self.loader.LoadModule(REPO_DIR, "genserv.py", args=""))
        self.assertEqual(self.pid_file(), {"genserv": 4321})
        self.loader.GetConfig()  # the next genloader run
        self.assertEqual(self.loader.CachedConfig["genserv"]["pid"], 4321)
        self.loader.LoadOrder = ["genserv"]
        with mock.patch.object(self.loader, "PIDIsModule", return_value=True), \
                mock.patch.object(genloader, "Popen", return_value=FakeProcess()) as popen:
            self.assertTrue(self.loader.StopModules())
        self.assertEqual(popen.call_args[0][0], ["kill", "4321"])
        self.assertEqual(self.pid_file(), {})

    # ---- genlog file name moved from args to genlog.conf -----------------
    def genlog_conf(self):
        return self.MyConfig(filename=os.path.join(self.folder, "genlog.conf"),
                             section="genlog").ReadValue("filename", default=None)

    def test_genlog_args_moved_to_genlog_conf(self):
        # an older genloader.conf (genlog.conf does not exist yet)
        self.edit_conf("genlog", "conffile", "")
        self.edit_conf("genlog", "args", "-f /data/mylog.csv")
        self.assertTrue(self.loader.GetConfig())
        self.assertEqual(self.genlog_conf(), "/data/mylog.csv")
        self.assertEqual(self.loader.CachedConfig["genlog"]["args"], "")
        self.assertEqual(self.loader.CachedConfig["genlog"]["conffile"], "genlog.conf")
        self.assertIn("Moved the genlog file name (/data/mylog.csv) from genloader.conf to "
                      + os.path.join(self.folder, "genlog.conf"), self.log.messages)
        # the next run leaves it alone
        self.log.messages.clear()
        self.assertTrue(self.loader.GetConfig())
        self.assertEqual(self.genlog_conf(), "/data/mylog.csv")
        self.assertFalse(any("genlog" in m for m in self.log.messages))

    def test_genlog_args_replace_default_in_genlog_conf(self):
        # genlog.conf was already copied with the default file name
        shutil.copy(os.path.join(REPO_DIR, "conf", "genlog.conf"), self.folder)
        self.edit_conf("genlog", "args", "-f /data/mylog.csv")
        self.assertTrue(self.loader.GetConfig())
        self.assertEqual(self.genlog_conf(), "/data/mylog.csv")

    def test_genlog_other_args_not_moved(self):
        self.edit_conf("genlog", "args", "-x something")
        self.assertTrue(self.loader.GetConfig())
        self.assertEqual(self.loader.CachedConfig["genlog"]["args"], "-x something")
        self.assertIsNone(self.genlog_conf())

    # ---- ValidateConfig ---------------------------------------------------
    def test_validate_config_copies_missing_conf_files(self):
        self.loader.GetConfig()
        self.assertTrue(self.loader.ValidateConfig())
        for name in ["genmon.conf", "mymail.conf", "genslack.conf", "mymodem.conf"]:
            with self.subTest(file=name):
                self.assertTrue(os.path.isfile(os.path.join(self.folder, name)))

    def test_validate_config_enabled_module_missing(self):
        self.loader.GetConfig()
        self.loader.CachedConfig["genslack"].update(enable=True, module="no_such_module.py")
        self.assertFalse(self.loader.ValidateConfig())

    def test_validate_config_genmon_not_enabled(self):
        self.loader.GetConfig()
        self.loader.CachedConfig["genmon"]["enable"] = False
        self.assertFalse(self.loader.ValidateConfig())

    # ---- GetLoadOrder -----------------------------------------------------
    def test_load_order(self):
        # highest priority number first (genloader stops in this order and
        # starts in the reverse order); no priority counts as 99
        self.loader.CachedConfig = {
            "genmon": {"priority": 0}, "genserv": {"priority": 1}, "genlog": {"priority": 2},
            "genslack": {"priority": 2}, "custom": {"priority": None}, "bad": {"priority": -1},
        }
        self.assertEqual(self.loader.GetLoadOrder(),
                         ["bad", "custom", "genlog", "genslack", "genserv", "genmon"])

    # ---- GetModuleList ----------------------------------------------------
    def libraries(self, enabled):
        self.loader.GetConfig()
        for name in enabled:
            self.loader.CachedConfig[name]["enable"] = True
        return [m["install"] for m in self.loader.GetModuleList()]

    def test_libraries_for_base_only(self):
        self.write_conf("genmon.conf", "GenMon", {"usemfa": "False"})
        libraries = self.libraries([])
        self.assertIn("flask", libraries)
        self.assertIn("pyserial", libraries)
        for name in ["paho-mqtt", "chump", "aiohttp", "zeroconf", "webauthn"]:
            self.assertNotIn(name, libraries)

    def test_libraries_for_enabled_add_ons(self):
        self.write_conf("genhalink.conf", "genhalink", {"zeroconf_enabled": "True"})
        self.write_conf("genhubitat.conf", "genhubitat", {"zeroconf_enabled": "True"})
        libraries = self.libraries(["genmqtt", "genhomeassistant", "genhalink", "genhubitat"])
        # each library once, even when several add-ons need it
        self.assertEqual(libraries.count("paho-mqtt"), 1)
        self.assertEqual(libraries.count("aiohttp"), 1)
        self.assertEqual(libraries.count("zeroconf"), 1)
        self.assertNotIn("chump", libraries)

    def test_libraries_for_features(self):
        # zeroconf only when the add-on is enabled and its option is on
        self.write_conf("genhalink.conf", "genhalink", {"zeroconf_enabled": "False"})
        self.assertNotIn("zeroconf", self.libraries(["genhalink"]))
        self.write_conf("genhalink.conf", "genhalink", {"zeroconf_enabled": "True"})
        self.assertNotIn("zeroconf", self.libraries([]))
        self.assertIn("zeroconf", self.libraries(["genhalink"]))
        # webauthn (passkeys) only with MFA
        self.write_conf("genmon.conf", "GenMon", {"usemfa": "True"})
        self.assertIn("webauthn", self.libraries([]))

    # ---- StartModules -----------------------------------------------------
    def test_start_modules(self):
        # the class works without genloader.py's __main__ (multi_instance is
        # an attribute, not a global)
        self.loader.GetConfig()
        self.loader.CachedConfig["genslack"]["enable"] = True
        self.loader.LoadOrder = self.loader.GetLoadOrder()
        self.loader.HardStop = False
        started = []

        def load(path, module, args=None):
            started.append(module)
            return True

        with mock.patch.object(genloader.MySupport, "IsRunning", return_value=False), \
                mock.patch.object(self.loader, "LoadModule", side_effect=load), \
                mock.patch.object(genloader.time, "sleep"):
            self.assertTrue(self.loader.StartModules())
        enabled = [m for m in reversed(self.loader.LoadOrder) if self.loader.CachedConfig[m]["enable"]]
        self.assertEqual(started, [self.loader.CachedConfig[m]["module"] for m in enabled])
        self.assertEqual(started[0], "genmon.py")
        self.assertIn("genslack.py", started)



# -------------------------------------------------------------------------------
class DependencyListTests(unittest.TestCase):
    """genloader's list of libraries (GetDependencyRegistry), requirements.txt
    (used by genmonmaint.sh) and the imports in the programs agree."""

    # in genloader's list but not requirements.txt, and why
    ONLY_GENLOADER = {
        "fluids": "left out of requirements.txt on purpose (slow to build, fails on 32 bit "
                  "trixie); genloader installs it when genmopeka is enabled",
        "mopeka-pro-check": "only for genmopeka's use_old_lib option",
    }
    # in requirements.txt but not genloader's list, and why
    ONLY_REQUIREMENTS = {
        "flask-compress": "optional, genserv skips compression without it",
        "configparser": "part of Python 3",
    }
    # libraries where the versions differ, and why
    VERSION_DIFFERENCES = {
        "pyotp": "genloader needs at least 2.3.0, requirements.txt installs the newest",
    }
    # imports that are not in genloader's list, and why
    OTHER_IMPORTS = {
        "requests": "installed with twilio and pyowm",
        "cryptography": "installed with pyopenssl",
        "werkzeug": "installed with flask",
        "itsdangerous": "installed with flask",
        "flask_compress": "optional, see flask-compress",
        "RPi": "installed by genmonmaint.sh (rpi-lgpio or RPi.GPIO)",
        "genmonext": "optional user extension",
        "genservext": "optional user extension",
    }

    @staticmethod
    def name(text):
        # "bleson @ git+..." or "paho-mqtt==1.6.1" -> "bleson", "paho-mqtt"
        return re.sub(r"[-_.]+", "-", re.split(r"[\s@=<>\[]", text.strip())[0]).lower()

    @classmethod
    def setUpClass(cls):
        loader = genloader.Loader.__new__(genloader.Loader)
        registry = loader.GetDependencyRegistry()
        cls.dependencies = list(registry["base"])
        for group in registry["addons"] + registry["features"]:
            cls.dependencies += group["dependencies"]
        cls.genloader = {cls.name(d["install"]): d["version"] for d in cls.dependencies}
        cls.requirements = {}
        with open(os.path.join(REPO_DIR, "requirements.txt")) as f:
            for line in f:
                line = line.split("#")[0].strip()
                if line:
                    version = line.split("==")[1].strip() if "==" in line else None
                    cls.requirements[cls.name(line)] = version

    def test_genloader_libraries_in_requirements(self):
        for name in sorted(self.genloader):
            with self.subTest(library=name):
                if name not in self.ONLY_GENLOADER:
                    self.assertIn(name, self.requirements)

    def test_requirements_in_genloader(self):
        for name in sorted(self.requirements):
            with self.subTest(library=name):
                if name not in self.ONLY_REQUIREMENTS:
                    self.assertIn(name, self.genloader)

    def test_versions_match(self):
        for name in sorted(set(self.genloader) & set(self.requirements)):
            with self.subTest(library=name):
                if name not in self.VERSION_DIFFERENCES:
                    self.assertEqual(self.genloader[name], self.requirements[name])

    def test_explained_differences_are_current(self):
        for name in self.ONLY_GENLOADER:
            self.assertIn(name, self.genloader)
            self.assertNotIn(name, self.requirements)
        for name in self.ONLY_REQUIREMENTS:
            self.assertIn(name, self.requirements)
            self.assertNotIn(name, self.genloader)

    def test_program_imports_are_installed(self):
        # every library a program imports is in genloader's list (or explained)
        known = {d["import"].split(".")[0] for d in self.dependencies} | set(self.OTHER_IMPORTS)
        local = {os.path.splitext(os.path.basename(p))[0]
                 for p in glob.glob(os.path.join(REPO_DIR, "*.py"))
                 + glob.glob(os.path.join(REPO_DIR, "addon", "*.py"))} | {"genmonlib"}
        stdlib = set(getattr(sys, "stdlib_module_names", ())) or None
        if stdlib is None:
            self.skipTest("needs Python 3.10 or later (sys.stdlib_module_names)")
        programs = [os.path.join(REPO_DIR, n) for n in ["genmon.py", "genserv.py"]]
        programs += sorted(glob.glob(os.path.join(REPO_DIR, "addon", "*.py")))
        for path in programs:
            with open(path) as f:
                tree = ast.parse(f.read())
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports |= {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    imports.add(node.module.split(".")[0])
            for module in sorted(imports - stdlib - local):
                with self.subTest(program=os.path.basename(path), library=module):
                    self.assertIn(module, known)


# -------------------------------------------------------------------------------
class StrayPackageTests(unittest.TestCase):
    """Loader.RemoveStrayPackages: the "tests" package bleson installs by
    mistake is removed, using only bleson's own install record."""

    def setUp(self):
        self.site = tempfile.mkdtemp(prefix="genloader_site_")
        self.addCleanup(shutil.rmtree, self.site)
        sys.path.insert(0, self.site)
        self.addCleanup(sys.path.remove, self.site)

    def install(self, name, files):
        """A fake installed library: its files and its RECORD."""
        info = os.path.join(self.site, name + "-1.0.dist-info")
        os.mkdir(info)
        with open(os.path.join(info, "METADATA"), "w") as f:
            f.write("Metadata-Version: 2.1\nName: %s\nVersion: 1.0\n" % name)
        record = []
        for path in files:
            full = os.path.join(self.site, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as f:
                f.write("x")
            record.append(path + ",,")
        record.append(name + "-1.0.dist-info/RECORD,,")
        with open(os.path.join(info, "RECORD"), "w") as f:
            f.write("\n".join(record) + "\n")

    def path(self, *names):
        return os.path.join(self.site, *names)

    def test_removed(self):
        self.install("fakelib", ["fakelib/__init__.py", "tests/__init__.py", "tests/test_one.py",
                                 "tests/__pycache__/test_one.cpython-313.pyc"])
        # compiled later by another Python version (not in the record)
        with open(self.path("tests", "__pycache__", "test_one.cpython-311.pyc"), "w") as f:
            f.write("x")
        removed = genloader.Loader.RemoveStrayPackages({"fakelib": "tests"})
        self.assertEqual(removed, ["fakelib: " + self.path("tests")])
        self.assertFalse(os.path.exists(self.path("tests")))
        # the library itself is kept
        self.assertTrue(os.path.isfile(self.path("fakelib", "__init__.py")))

    def test_other_files_kept(self):
        # a file in the folder that the library did not install is never removed
        self.install("fakelib", ["tests/__init__.py", "tests/test_one.py"])
        with open(self.path("tests", "someone_else.py"), "w") as f:
            f.write("x")
        self.assertEqual(genloader.Loader.RemoveStrayPackages({"fakelib": "tests"}), [])
        self.assertEqual(os.listdir(self.path("tests")), ["someone_else.py"])

    def test_not_installed(self):
        self.assertEqual(genloader.Loader.RemoveStrayPackages({"no_such_library_x": "tests"}), [])
        self.assertIn("bleson", genloader.Loader.STRAY_PACKAGES)


if __name__ == "__main__":
    unittest.main()
