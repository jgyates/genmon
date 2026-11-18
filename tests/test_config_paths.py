#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_config_paths.py
# PURPOSE: The config folder (-c) and log folder (-l) work with or without a
#          trailing slash, and with spaces in the folder names:
#            - genmonmaint.sh backup, restore and log archive
#            - startgenmon.sh passing -c to genloader.py
#            - genmon.py: the files sent with "sendlogfiles"
#            - genloader.py: moving old config files (OneTimeMaint)
#            - genserv.py: running the scripts (backup / restore from the web
#              page)
#
#          The shell scripts run in a temporary copy of the genmon folder, with
#          fake sudo, python3 and apt-get first on the PATH: nothing is
#          installed and nothing runs as root.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_config_paths
#
# -------------------------------------------------------------------------------

import logging
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from unittest import mock

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_DIR)

FAKE_COMMANDS = {
    # run the command as this user
    "sudo": '#!/bin/bash\nexec "$@"\n',
    # the scripts ask python3 for its version (to find a managed Python
    # install); 0.0 is never one. A script run with it is recorded.
    "python3": '#!/bin/bash\nif [ "$1" = "-c" ]; then echo 0; exit 0; fi\n'
               'printf "%s\\n" "$@" > "$GENMON_TEST_RECORD"\n',
    "apt-get": "#!/bin/bash\nexit 0\n",
}


@unittest.skipUnless(shutil.which("bash") and shutil.which("tar"), "needs bash and tar")
class ShellScriptTests(unittest.TestCase):

    def setUp(self):
        # the real path (on macOS /var is a link to /private/var)
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="genmon paths "))
        self.addCleanup(shutil.rmtree, self.root)
        self.genmon = self.path("gen mon")
        os.mkdir(self.genmon)
        for script in ["genmonmaint.sh", "startgenmon.sh"]:
            shutil.copy(os.path.join(REPO_DIR, script), self.genmon)
        bin_dir = self.path("bin")
        os.mkdir(bin_dir)
        for name, text in FAKE_COMMANDS.items():
            with open(os.path.join(bin_dir, name), "w") as f:
                f.write(text)
            os.chmod(os.path.join(bin_dir, name), 0o755)
        self.record = self.path("record.txt")
        self.env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ["PATH"],
                        GENMON_TEST_RECORD=self.record)

    def path(self, *names):
        return os.path.join(self.root, *names)

    def run_script(self, *args):
        result = subprocess.run(["bash", args[0]] + list(args[1:]), cwd=self.genmon, env=self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                timeout=60, stdin=subprocess.DEVNULL)
        return result.stdout

    def config_folder(self, name):
        folder = self.path(name)
        os.mkdir(folder)
        with open(os.path.join(folder, "genmon.conf"), "w") as f:
            f.write("[GenMon]\nsitename = Test\n")
        return folder

    def test_backup_and_restore(self):
        for slash in ["", "/"]:
            with self.subTest(slash=slash or "no slash"):
                config = self.config_folder("etc genmon" + slash.replace("/", " s"))
                self.run_script("genmonmaint.sh", "-b", "-c", config + slash)
                archive = os.path.join(self.genmon, "genmon_backup.tar.gz")
                with tarfile.open(archive) as tar:
                    # the files, not the folder (genmon_backup/genmon/...)
                    self.assertIn("genmon_backup/genmon.conf", tar.getnames())

                backup = self.path("my backup.tar.gz")
                shutil.move(archive, backup)
                restored = self.path("restored conf" + slash.replace("/", " s"))
                os.mkdir(restored)
                self.run_script("genmonmaint.sh", "-t", backup, "-c", restored + slash)
                self.assertTrue(os.path.isfile(os.path.join(restored, "genmon.conf")))
                # the restore history, in the config folder
                with open(os.path.join(restored, "restore.txt")) as f:
                    self.assertEqual(f.read().splitlines()[1], backup)

    def test_archive_logs(self):
        logs = self.path("log files")
        os.mkdir(logs)
        with open(os.path.join(logs, "genmon.log"), "w") as f:
            f.write("log\n")
        self.run_script("genmonmaint.sh", "-l", logs)  # no trailing slash
        with tarfile.open(os.path.join(self.genmon, "genmon_logs.tar.gz")) as tar:
            self.assertIn("genmon_logs/genmon.log", tar.getnames())

    def test_start_passes_the_config_folder(self):
        # one argument, even with a space in it
        config = self.path("etc genmon")
        self.run_script("startgenmon.sh", "start", "-c", config)
        with open(self.record) as f:
            self.assertEqual(f.read().splitlines(),
                             [os.path.join(self.genmon, "genloader.py"), "-s", "-c", config])
        os.remove(self.record)
        self.run_script("startgenmon.sh", "stop")
        with open(self.record) as f:
            self.assertEqual(f.read().splitlines(), [os.path.join(self.genmon, "genloader.py"), "-x"])


# -------------------------------------------------------------------------------
class PythonPathTests(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="genmon_paths_")
        self.addCleanup(shutil.rmtree, self.root)

    def make(self, folder, name):
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name)
        with open(path, "w") as f:
            f.write("x\n")
        return path

    def test_sendlogfiles(self):
        # the files from the log and config folders (they were left out
        # without a trailing slash)
        import genmon

        log_file = self.make(os.path.join(self.root, "log"), "genmon.log")
        data_file = self.make(os.path.join(self.root, "conf"), "update.txt")
        for slash in ["", "/"]:
            with self.subTest(slash=slash or "no slash"):
                monitor = types.SimpleNamespace(
                    LogLocation=os.path.join(self.root, "log") + slash,
                    ConfigFilePath=os.path.join(self.root, "conf") + slash,
                    LogErrorLine=mock.Mock())
                files = [os.path.normpath(f) for f in genmon.Monitor.GetLogFileNames(monitor)]
                self.assertEqual(files, [log_file, data_file])

    def test_one_time_maint(self):
        # old config files in the genmon folder are moved into the config
        # folder, with or without a trailing slash
        import genloader

        for slash in ["", "/"]:
            with self.subTest(slash=slash or "no slash"):
                genmon_dir = os.path.join(self.root, "genmon" + slash.replace("/", "s"))
                conf = os.path.join(self.root, "conf" + slash.replace("/", "s"))
                old = self.make(genmon_dir, "outage.txt")
                log = logging.getLogger("paths_test")
                log.handlers, log.propagate = [logging.NullHandler()], False
                real_isfile = os.path.isfile

                def isfile(path):
                    # this computer's /etc is left alone
                    return False if str(path).startswith("/etc/") else real_isfile(path)

                with mock.patch.object(genloader.os.path, "dirname", return_value=genmon_dir), \
                        mock.patch.object(genloader.os.path, "realpath", side_effect=lambda p: p), \
                        mock.patch.object(genloader.os.path, "isfile", side_effect=isfile):
                    genloader.Loader.OneTimeMaint(conf + slash, log)
                self.assertTrue(os.path.isfile(os.path.join(conf, "outage.txt")))
                self.assertFalse(os.path.exists(old))


# -------------------------------------------------------------------------------
class GenservScriptTests(unittest.TestCase):
    """genserv runs genmonmaint.sh / startgenmon.sh with the folders quoted
    (backup, restore and logs from the web page)."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from genserv_fixture import GenServFixture

        cls.fixture = GenServFixture("open").start()
        cls.genserv = cls.fixture.instance

    @classmethod
    def tearDownClass(cls):
        cls.fixture.stop()

    def last_command(self):
        return self.fixture.shell_calls()[-1]

    def test_folders_with_spaces(self):
        import shlex

        saved = (self.genserv.ConfigFilePath, self.genserv.loglocation)
        self.addCleanup(setattr, self.genserv, "ConfigFilePath", saved[0])
        self.addCleanup(setattr, self.genserv, "loglocation", saved[1])
        self.genserv.ConfigFilePath = "/home/pi/my gen/conf"
        self.genserv.loglocation = "/home/pi/my gen/logs/"
        script = "<RUN>/genmonmaint.sh"  # the fixture shows its folder as <RUN>

        self.genserv.Backup()
        self.assertEqual(shlex.split(self.last_command()[len("SHELL "):]),
                         ["/bin/bash", script, "-b", "-c", "/home/pi/my gen/conf"])
        self.genserv.RestoreBackup("/tmp/my backup.tar.gz")
        self.assertEqual(shlex.split(self.last_command()[len("SHELL "):]),
                         ["/bin/bash", script, "-t", "/tmp/my backup.tar.gz", "-c", "/home/pi/my gen/conf"])
        self.genserv.GetLogs()
        self.assertIn(["-l", "/home/pi/my gen/logs/"],
                      [shlex.split(c[len("SHELL "):])[2:4] for c in self.fixture.shell_calls()])


if __name__ == "__main__":
    unittest.main()
