#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_mysupport.py
# PURPOSE: Tests for genmonlib/mysupport.py, the shared helpers of genmon, the
#          controllers and the add-ons: copying and logging to files, values
#          with units (text or JSON numbers), hex strings, the status / log
#          output as text or dictionaries, threads, and starting an add-on
#          (command line, genmon.conf, already running).
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_mysupport
#
# -------------------------------------------------------------------------------

import collections
import datetime
import io
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genmonlib import mysupport  # noqa: E402
from genmonlib.mysupport import MySupport  # noqa: E402
from genmonlib.mythread import MyThread  # noqa: E402


class SupportTestCase(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="mysupport_")
        self.addCleanup(shutil.rmtree, self.folder)
        self.s = MySupport()
        self.s.log = logging.getLogger("mysupport_test")
        self.s.log.handlers, self.s.log.propagate = [], False
        self.errors = []

        class Collect(logging.Handler):
            def emit(handler, record):
                self.errors.append(record.getMessage())

        self.s.log.addHandler(Collect())
        self.s.console = None

    def path(self, name):
        return os.path.join(self.folder, name)


# -------------------------------------------------------------------------------
class FileTests(SupportTestCase):

    def test_copy(self):
        with open(self.path("a"), "w") as f:
            f.write("new contents\n")
        self.assertTrue(MySupport.CopyFile(self.path("a"), self.path("sub/b")))
        with open(self.path("sub/b")) as f:
            self.assertEqual(f.read(), "new contents\n")
        self.assertTrue(os.path.isfile(self.path("a")))

    def test_copy_over_a_longer_file(self):
        # the old file is replaced (its end was left after the new contents)
        with open(self.path("a"), "w") as f:
            f.write("short\n")
        with open(self.path("b"), "w") as f:
            f.write("a much longer old file\n")
        self.assertTrue(MySupport.CopyFile(self.path("a"), self.path("b"), move=True))
        with open(self.path("b")) as f:
            self.assertEqual(f.read(), "short\n")
        self.assertFalse(os.path.exists(self.path("a")))

    def test_copy_no_source(self):
        log = mock.Mock()
        self.assertFalse(MySupport.CopyFile(self.path("none"), self.path("b"), log=log))
        log.error.assert_called_once()

    def test_log_to_file(self):
        self.s.LogToFile(self.path("log.csv"), "11/02/26 12:00:00", "Running\x07", "")
        self.s.LogToFile(self.path("log.csv"), "11/02/26 12:10:00", "Stopped")
        with open(self.path("log.csv")) as f:
            self.assertEqual(f.read(), "11/02/26 12:00:00,Running\n11/02/26 12:10:00,Stopped\n")

    def test_log_to_file_simulation(self):
        MySupport(simulation=True).LogToFile(self.path("log.csv"), "x")
        self.assertFalse(os.path.exists(self.path("log.csv")))

    def test_csv(self):
        with open(self.path("f.csv"), "w") as f:
            f.write("# comment\n\n1,2,3\n a,b \n")
        self.assertEqual(self.s.ReadCSVFile(self.path("f.csv")), [["1", "2", "3"], ["a", "b"]])
        self.assertEqual(self.s.ReadCSVFile(self.path("none.csv")), [])


# -------------------------------------------------------------------------------
class ValueTests(SupportTestCase):

    def test_value_out(self):
        self.assertEqual(self.s.ValueOut(240, "V"), "240 V")
        self.assertEqual(self.s.ValueOut(13.456, "V"), "13.46 V")
        self.assertEqual(self.s.ValueOut(240, "V", NoString=True),
                         collections.OrderedDict([("unit", "V"), ("type", "int"), ("value", 240)]))
        self.assertEqual(self.s.ValueOut(13.456, "V", NoString=True)["value"], 13.46)
        self.assertEqual(self.s.ValueOut("x", "V"), "")
        self.assertEqual(self.s.ValueOut("x", "V", NoString=True), {"unit": "V"})

    def test_units_out(self):
        self.assertEqual(self.s.UnitsOut("240 V"), "240 V")
        self.assertEqual(self.s.UnitsOut("240 V", type=int, NoString=True)["value"], 240)
        self.assertEqual(self.s.UnitsOut("5.5 cubic feet", type=float, NoString=True),
                         {"unit": "cubic feet", "type": "float", "value": 5.5})
        self.assertEqual(self.s.UnitsOut("Unknown", type=int, NoString=True), "Unknown")
        self.assertEqual(self.s.UnitsOut("12 V", NoString=True), "12 V")  # no type

    def test_hex(self):
        self.assertEqual(self.s.HexStringToString("48656c6c6f00ffff"), "Hello")
        self.assertEqual(self.s.HexStringToString("00656c"), "")
        self.assertEqual(self.s.HexStringToString("not hex"), "")
        self.assertTrue(self.s.StringIsHex("0aF3"))
        self.assertFalse(self.s.StringIsHex("0a F3"))
        self.assertFalse(self.s.StringIsHex("xyz"))
        self.assertEqual(self.s.GetIntFromString("0a1b2c", 1), 0x1b)
        self.assertEqual(self.s.GetIntFromString("0a1b2c", 1, length=2), 0x1b2c)
        self.assertEqual(self.s.GetIntFromString("0a1234", 1, length=2, decimal=True), 1234)
        self.assertEqual(self.s.GetIntFromString("0a", 3), 0)

    def test_bits_and_words(self):
        self.assertEqual(self.s.GetNumBitsChanged("00ff", "0f0f"), (8, 0x0ff0))
        self.assertEqual(self.s.GetNumBitsChanged("", "01"), (0, 0))
        self.assertEqual(self.s.SwapWords32(0x00010002), 0x00020001)

    def test_minutes(self):
        self.assertEqual(self.s.GetDeltaTimeMinutes(datetime.timedelta(hours=2, minutes=5)), 125)

    def test_regex(self):
        self.assertTrue(self.s.RegExIsValid("^[0-9]+$"))
        self.assertFalse(self.s.RegExIsValid("[0-9"))


# -------------------------------------------------------------------------------
class DispatchTests(SupportTestCase):

    STATUS = collections.OrderedDict([("Status", [
        {"Engine": [{"State": "Running"}, {"RPM": 3600}, {"Volts": 13.2}]},
        {"Alarms": ["Low Oil", "High Temp"]},
        {"Called": lambda: "from a function"}])])

    def test_to_dictionary(self):
        result = self.s.ProcessDispatch(self.STATUS, collections.OrderedDict())
        engine = result["Status"][0]["Engine"]
        self.assertEqual(engine, [{"State": "Running"}, {"RPM": "3600"}, {"Volts": "13.2"}])
        self.assertEqual(result["Status"][2], {"Called": "from a function"})

    def test_to_text(self):
        text = self.s.ProcessDispatch(self.STATUS, "")
        self.assertIn("Status : \n", text)
        self.assertIn("        State : Running\n", text)
        self.assertIn("        Low Oil\n", text)
        self.assertIn("    Called : from a function\n", text)

    def test_dispatch_items(self):
        self.assertEqual(self.s.GetDispatchItem(None), "None")
        self.assertEqual(self.s.GetDispatchItem(b"x"), "b'x'")
        self.assertEqual(self.s.GetDispatchItem(("a",)), "")
        self.assertTrue(any("Unable to convert" in e for e in self.errors))


# -------------------------------------------------------------------------------
class ThreadTests(SupportTestCase):

    def test_threads(self):
        stopped = threading.Event()

        def worker():
            while not self.s.WaitForExit("Worker", 0.01):
                pass
            stopped.set()

        self.s.Threads["Worker"] = MyThread(worker, Name="Worker")
        self.assertEqual(self.s.Threads["Worker"].Name(), "Worker")
        self.assertTrue(self.s.AreThreadsAlive())
        self.assertIn("All threads alive", self.s.GetDeadThreadName())
        self.assertFalse(self.s.IsStopSignaled("Worker"))
        self.s.KillThread("Worker")
        self.assertTrue(stopped.wait(5))
        self.assertFalse(self.s.AreThreadsAlive())
        self.assertEqual(self.s.GetDeadThreadName().strip(), "Worker")

    def test_thread_name(self):
        # Name() works (a Name attribute hid it, calling it raised an error)
        thread = MyThread(lambda: None, start=False)
        self.assertEqual(thread.Name(), "<lambda>")

    def test_unknown_thread(self):
        self.assertFalse(self.s.KillThread("Nothing"))
        self.assertFalse(self.s.IsStopSignaled("Nothing"))
        with mock.patch.object(mysupport.time, "sleep") as sleep:
            self.assertFalse(self.s.WaitForExit("Nothing", 1))
        sleep.assert_called_once_with(1)


# -------------------------------------------------------------------------------
class CodeHashTests(SupportTestCase):
    """GetCodeHash: the commit of a git checkout, read from its .git folder
    (as "git rev-parse --short HEAD", without running git)."""

    def git(self, *args, cwd=None):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
                   GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        return subprocess.check_output(["git"] + list(args), cwd=cwd or self.repo, env=env,
                                       stderr=subprocess.DEVNULL).decode().strip()

    def make_repo(self):
        self.repo = os.path.join(self.folder, "repo")
        os.makedirs(self.repo)
        self.git("init", "-q", "-b", "master")
        for n in range(2):
            with open(os.path.join(self.repo, "f.txt"), "w") as f:
                f.write(str(n))
            self.git("add", "f.txt")
            self.git("commit", "-q", "--no-gpg-sign", "-m", str(n))

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_same_as_git(self):
        self.make_repo()
        short = self.git("rev-parse", "--short=7", "HEAD")
        with self.subTest("branch"):
            self.assertEqual(MySupport.GetCodeHash(self.repo), short)
        with self.subTest("packed refs (after git gc)"):
            self.git("pack-refs", "--all")
            self.assertFalse(os.path.exists(os.path.join(self.repo, ".git", "refs", "heads", "master")))
            self.assertEqual(MySupport.GetCodeHash(self.repo), short)
        with self.subTest("detached HEAD"):
            self.git("checkout", "-q", "HEAD~1")
            self.assertEqual(MySupport.GetCodeHash(self.repo), self.git("rev-parse", "--short=7", "HEAD"))
            self.git("checkout", "-q", "master")
        with self.subTest("worktree (.git is a file)"):
            tree = os.path.join(self.folder, "tree")
            self.git("worktree", "add", "-q", "-b", "other", tree, "HEAD~1")
            self.assertTrue(os.path.isfile(os.path.join(tree, ".git")))
            self.assertEqual(MySupport.GetCodeHash(tree), self.git("rev-parse", "--short=7", "HEAD", cwd=tree))

    def test_not_a_checkout(self):
        # e.g. genmon downloaded as a zip file
        self.assertEqual(MySupport.GetCodeHash(self.folder), "Unknown")
        git_dir = os.path.join(self.folder, ".git")
        os.makedirs(git_dir)
        with open(os.path.join(git_dir, "HEAD"), "w") as f:
            f.write("ref: refs/heads/missing\n")
        self.assertEqual(MySupport.GetCodeHash(self.folder), "Unknown")
        with open(os.path.join(git_dir, "HEAD"), "w") as f:
            f.write("not a commit\n")
        self.assertEqual(MySupport.GetCodeHash(self.folder), "Unknown")

    def test_this_checkout(self):
        # genmon's own folder (no argument)
        code_hash = MySupport.GetCodeHash()
        if os.path.exists(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".git")):
            self.assertRegex(code_hash, r"^[0-9a-f]{7}$")
        else:
            self.assertEqual(code_hash, "Unknown")


class AddOnStartTests(SupportTestCase):

    def conf(self, **values):
        from genmonlib.myconfig import MyConfig
        shutil.copy(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "conf", "genmon.conf"), self.folder)
        config = MyConfig(filename=self.path("genmon.conf"), section="GenMon")
        for key, value in dict({"loglocation": self.folder}, **values).items():
            config.WriteValue(key, value)

    def setup(self, argv, extra_options=None, running=False):
        # the console messages (errors on purpose) are kept in self.console,
        # not printed with the test results
        self.console = io.StringIO()
        with mock.patch.object(sys, "argv", ["genfoo.py"] + argv), \
                mock.patch.object(sys, "stderr", self.console), \
                mock.patch.object(MySupport, "PermissionsOK", return_value=True), \
                mock.patch.object(MySupport, "IsRunning", return_value=running), \
                mock.patch.object(mysupport.time, "sleep"):
            return MySupport.SetupAddOnProgram("genfoo", extra_options=extra_options)

    def test_command_line(self):
        self.conf(server_port="9999")
        console, path, address, port, loglocation, log = self.setup(
            ["-c", self.folder, "-a", "192.0.2.4"])
        self.assertEqual((path, address, port, loglocation), (self.folder, "192.0.2.4", 9999, self.folder))
        self.assertTrue(os.path.isfile(self.path("genfoo.log")))

    def test_extra_options(self):
        self.conf()
        result = self.setup(["-c", self.folder, "-f", " /tmp/out.csv "],
                            extra_options={"f": ("filename", "<file>")})
        self.assertEqual(result[6], {"filename": "/tmp/out.csv"})

    def test_already_running(self):
        self.conf()
        with self.assertRaises(SystemExit):
            self.setup(["-c", self.folder], running=True)
        self.assertIn("genfoo.py is already loaded", self.console.getvalue())

    def test_invalid_option(self):
        with self.assertRaises(SystemExit):
            self.setup(["-x"])
        self.assertIn("Invalid command line argument", self.console.getvalue())

    def test_bad_genmon_conf(self):
        # the error is reported (it raised a NameError: no log yet)
        with mock.patch.object(MySupport, "GetGenmonInitInfo", side_effect=ValueError("bad conf")):
            with self.assertRaises(SystemExit) as stop:
                self.setup(["-c", self.folder])
        self.assertEqual(stop.exception.code, 1)
        self.assertIn("bad conf", self.console.getvalue())

    def test_permissions(self):
        # root on Linux; Windows and macOS without root
        for platform, euid, expected in [("linux", 0, True), ("linux", 1000, False),
                                         ("darwin", 501, True), ("win32", None, True)]:
            with self.subTest(platform=platform, euid=euid), \
                    mock.patch.object(sys, "platform", platform), \
                    mock.patch.object(mysupport.os, "geteuid", return_value=euid, create=True):
                self.assertEqual(MySupport.PermissionsOK(), expected)

    def test_init_info(self):
        self.conf(server_port="9100", multi_instance="True")
        self.assertEqual(MySupport.GetGenmonInitInfo(self.folder), (9100, self.folder, True))

    def test_is_running(self):
        me = types.SimpleNamespace(name=lambda: "python3", cmdline=lambda: ["python3", "/x/genfoo.py"],
                                   pid=os.getpid())
        other = types.SimpleNamespace(name=lambda: "python3", cmdline=lambda: ["python3", "genfoo.py"],
                                      pid=os.getpid() + 1)
        fake = types.SimpleNamespace(process_iter=lambda: [me])
        with mock.patch.dict(sys.modules, {"psutil": fake}):
            self.assertFalse(MySupport.IsRunning("genfoo.py"))
            fake.process_iter = lambda: [me, other]
            self.assertTrue(MySupport.IsRunning("genfoo.py"))
            self.assertFalse(MySupport.IsRunning("genfoo.py", multi_instance=True))


if __name__ == "__main__":
    unittest.main()
