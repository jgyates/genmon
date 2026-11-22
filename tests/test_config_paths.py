#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_config_paths.py
# PURPOSE: The config folder (-c) and log folder (-l) work with or without a
#          trailing slash, and with spaces in the folder names:
#            - genmonmaint.sh backup, restore and log archive
#            - startgenmon.sh passing -c to genloader.py
#          and genmonmaint.sh stops an install or update on Python older
#          than MIN_PYTHON in genmonlib/program_defaults.py, or an update to a version that
#          needs a newer Python (startgenmon.sh still accepts the old -p
#          option).
#            - genmon.py: the files sent with "sendlogfiles"
#            - genloader.py: moving old config files (OneTimeMaint)
#            - genserv.py: running the scripts (backup / restore from the web
#              page)
#
#          The shell scripts run in a temporary copy of the genmon folder, with
#          fake sudo, python3, apt-get and git first on the PATH: nothing is
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
    # A Python of version GENMON_TEST_PYTHON_VERSION (3.11.2, or 3.7.3 with
    # GENMON_TEST_OLD_PYTHON set). The scripts ask python3 for its version (to
    # find a managed Python install); 0.0 is never one. The version check
    # (sys.exit) runs in the real Python with sys.version_info set to that
    # version. A script run with it is recorded.
    "python3": '#!/bin/bash\n'
               'VERSION="${GENMON_TEST_PYTHON_VERSION:-3.11.2}"\n'
               '[ -n "$GENMON_TEST_OLD_PYTHON" ] && VERSION=3.7.3\n'
               'if [ "$1" = "-V" ]; then echo "Python $VERSION"; exit 0; fi\n'
               'if [ "$1" = "-c" ]; then\n'
               '  case "$2" in *sys.exit*)\n'
               '    exec "$GENMON_TEST_REAL_PYTHON" -c \'import sys; v, code = sys.argv[1:3]; '
               'sys.argv = ["-c"] + sys.argv[3:]; '
               'sys.version_info = tuple(int(n) for n in v.split(".")); exec(code)\' '
               '"$VERSION" "$2" "${@:3}";;\n'
               '  esac\n'
               '  echo 0; exit 0\n'
               'fi\n'
               'printf "%s\\n" "$@" > "$GENMON_TEST_RECORD"\n',
    "apt-get": '#!/bin/bash\necho "APT-GET $*"\n',
    # "git show origin/master:genmonlib/program_defaults.py" prints
    # GENMON_TEST_NEW_DEFAULTS, that file of the version an update would install
    "git": '#!/bin/bash\n'
           'echo "GIT $*"\n'
           'if [ "$1" = "show" ] && [ -n "$GENMON_TEST_NEW_DEFAULTS" ]; then cat "$GENMON_TEST_NEW_DEFAULTS"; fi\n',
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
        # genmonmaint.sh reads MIN_PYTHON in genmonlib/program_defaults.py
        os.mkdir(os.path.join(self.genmon, "genmonlib"))
        shutil.copy(os.path.join(REPO_DIR, "genmonlib", "program_defaults.py"),
                    os.path.join(self.genmon, "genmonlib"))
        bin_dir = self.path("bin")
        os.mkdir(bin_dir)
        for name, text in FAKE_COMMANDS.items():
            with open(os.path.join(bin_dir, name), "w") as f:
                f.write(text)
            os.chmod(os.path.join(bin_dir, name), 0o755)
        self.record = self.path("record.txt")
        self.env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ["PATH"],
                        GENMON_TEST_RECORD=self.record, GENMON_TEST_REAL_PYTHON=sys.executable)

    def path(self, *names):
        return os.path.join(self.root, *names)

    def run_script(self, *args, env=None, returncode=False):
        result = subprocess.run(["bash", args[0]] + list(args[1:]), cwd=self.genmon, env=env or self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                timeout=60, stdin=subprocess.DEVNULL)
        if returncode:
            return result.returncode, result.stdout
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

    def test_start_ignores_the_old_python_option(self):
        # older installs have "start -p 3" in the crontab entry
        config = self.path("etc genmon")
        self.run_script("startgenmon.sh", "start", "-p", "3", "-c", config)
        with open(self.record) as f:
            self.assertEqual(f.read().splitlines(),
                             [os.path.join(self.genmon, "genloader.py"), "-s", "-c", config])

    def test_old_python_stops_install_and_update(self):
        old = dict(self.env, GENMON_TEST_OLD_PYTHON="1")
        config = self.config_folder("etc genmon")
        for option in ["-i", "-u"]:
            with self.subTest(option=option):
                code, output = self.run_script("genmonmaint.sh", option, "-n", "-c", config,
                                               env=old, returncode=True)
                self.assertEqual(code, 1)
                self.assertIn("ERROR: Genmon requires Python 3.9 or later. This system has Python 3.7.3.", output)
                self.assertNotIn("APT-GET", output)  # nothing installed
                self.assertNotIn("GIT", output)      # not updated

    def test_old_python_still_backs_up(self):
        # a backup is needed before upgrading the operating system
        old = dict(self.env, GENMON_TEST_OLD_PYTHON="1")
        config = self.config_folder("etc genmon")
        code, output = self.run_script("genmonmaint.sh", "-b", "-c", config, env=old, returncode=True)
        self.assertEqual(code, 0, output)
        self.assertNotIn("requires Python", output)
        self.assertTrue(os.path.isfile(os.path.join(self.genmon, "genmon_backup.tar.gz")))

    def test_update_runs_on_a_supported_python(self):
        config = self.config_folder("etc genmon")
        code, output = self.run_script("genmonmaint.sh", "-u", "-n", "-c", config, returncode=True)
        self.assertNotIn("requires Python", output)
        self.assertIn("GIT reset --hard origin/master", output)

    def test_no_python_2_option(self):
        code, output = self.run_script("genmonmaint.sh", "-p", "3", returncode=True)
        self.assertEqual(code, 1)
        self.assertIn("Invalid Option: -p", output)

    def test_version_check_matches_program_defaults(self):
        # genmonmaint.sh reads its minimum from MIN_PYTHON in program_defaults.py:
        # that version updates, the one before it does not (the same check
        # as an install, which runs too long here with the fake commands)
        from genmonlib.program_defaults import ProgramDefaults
        major, minor = ProgramDefaults.MIN_PYTHON
        config = self.config_folder("etc genmon")
        for version, ok in [("%d.%d.0" % (major, minor), True), ("%d.%d.9" % (major, minor - 1), False)]:
            with self.subTest(version=version):
                code, output = self.run_script("genmonmaint.sh", "-u", "-n", "-c", config, returncode=True,
                                               env=dict(self.env, GENMON_TEST_PYTHON_VERSION=version))
                self.assertEqual("requires Python" not in output, ok, output)
                if not ok:
                    self.assertEqual(code, 1)
                    self.assertIn("ERROR: Genmon requires Python %d.%d or later. "
                                  "This system has Python %s." % (major, minor, version), output)

    def new_defaults(self, minimum):
        # program_defaults.py of the version an update would install
        path = self.path("new program_defaults.py")
        with open(path, "w") as f:
            f.write("class ProgramDefaults(object):\n    MIN_PYTHON = %r\n" % (minimum,))
        return dict(self.env, GENMON_TEST_NEW_DEFAULTS=path)

    def test_update_stops_when_the_new_version_needs_a_newer_python(self):
        config = self.config_folder("etc genmon")
        code, output = self.run_script("genmonmaint.sh", "-u", "-n", "-c", config, returncode=True,
                                       env=self.new_defaults((3, 12)))
        self.assertEqual(code, 1)
        self.assertIn("ERROR: The new version of genmon requires Python 3.12 or later. "
                      "This system has Python 3.11.2. Genmon was not updated.", output)
        self.assertIn("GIT fetch origin", output)
        self.assertNotIn("GIT reset", output)  # nothing changed

    def test_update_to_a_version_this_python_supports(self):
        config = self.config_folder("etc genmon")
        for minimum in [(3, 9), (3, 11)]:
            with self.subTest(minimum=minimum):
                code, output = self.run_script("genmonmaint.sh", "-u", "-n", "-c", config, returncode=True,
                                               env=self.new_defaults(minimum))
                self.assertEqual(code, 0, output)
                self.assertIn("GIT reset --hard origin/master", output)

    def test_update_from_github_without_min_python(self):
        # a program_defaults.py without the MIN_PYTHON line: genmon 2.0's 3.9
        config = self.config_folder("etc genmon")
        code, output = self.run_script("genmonmaint.sh", "-u", "-n", "-c", config, returncode=True)
        self.assertEqual(code, 0, output)
        self.assertIn("GIT reset --hard origin/master", output)


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
