#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_genmon_sim.py
# PURPOSE: End to end tests of genmon.py and the controller code: genmon runs
#          against tests/sim/gensim.py, a generator simulator that answers
#          genmon's Modbus requests from a register file (a genmon register
#          dump, e.g. from "send registers").
#
#          The register files are not in the repository (they come from real
#          generators), so these tests only run when GENMON_CAPTURES is set to
#          a folder with a captures.json file:
#
#            {
#              "captures": [
#                {
#                  "name": "evo_ac",
#                  "file": "EvoAC/EvoAC_11kw_NG.txt",
#                  "controllertype": "generac_evo_nexus",
#                  "address": "9d",
#                  "model": "G0070330",
#                  "nominalkw": "11",
#                  "controller": "Evolution, Air Cooled"
#                }
#              ]
#            }
#
#          file          the register file, relative to the captures.json folder
#                        (or a full path)
#          controllertype, address
#                        genmon.conf settings for this controller
#          model, nominalkw
#                        genmon.conf settings. These must be set: without them
#                        genmon looks up the serial number on the internet
#          controller    expected start of the controller genmon detects
#          fueltype      optional genmon.conf setting
#          log_errors_allowed
#                        optional list of texts; genmon.log lines with "error"
#                        that contain one of them are not reported
#
#          For each capture the test starts gensim and genmon (each on a free
#          port, with temporary config, log and data folders), and checks that
#          genmon starts, detects the controller, answers the read commands, and
#          logs no errors. If the captures.json folder has a "snapshots" folder,
#          the answers are also compared with snapshots/<name>.json (times are
#          masked). The snapshots are kept with the captures, not in the
#          repository, since they show decoded data such as the serial number.
#          Make new snapshots with:
#              GENMON_SIM_UPDATE=1 GENMON_CAPTURES=<folder> python3 -m unittest tests.test_genmon_sim
#
#   USAGE: from the root of the repository:
#              GENMON_CAPTURES=<folder> python3 -m unittest tests.test_genmon_sim
#
# -------------------------------------------------------------------------------

import contextlib
import glob
import io
import json
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_DIR)

CAPTURES_DIR = os.environ.get("GENMON_CAPTURES")
GENSIM = os.path.join(REPO_DIR, "tests", "sim", "gensim.py")
START_TIMEOUT = 90  # seconds for genmon to connect and read the controller

# read commands a client (genserv, add-ons) uses, and whether the answer is JSON
READ_COMMANDS = {
    "gethealth": False, "getsitename": False, "getbase": False,
    "status": False, "maint": False, "outage": False, "monitor": False, "logs": False,
    "registers": False, "start_info_json": True, "status_json": True,
    "status_num_json": True, "maint_json": True, "maint_num_json": True,
    "outage_json": True, "outage_num_json": True, "monitor_json": True,
    "monitor_num_json": True, "logs_json": True, "registers_json": True,
    "allregs_json": True, "gui_status_json": True, "power_log_json": True,
    "get_maint_log_json": True, "getreglabels_json": True, "sensor_names_json": True,
}
# answers compared with the snapshots
SNAPSHOT_COMMANDS = ["status_json", "maint_json", "outage_json", "logs_json", "registers_json"]


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def load_captures():
    if not CAPTURES_DIR:
        return []
    with open(os.path.join(CAPTURES_DIR, "captures.json")) as f:
        return json.load(f)["captures"]


# times and dates change with every run
MASKS = [
    (re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(\.\d+)?"), "<DATETIME>"),
    (re.compile(r"\b\d{1,2}:\d{2}:\d{2}\b"), "<TIME>"),
]


def mask(text):
    for pattern, replacement in MASKS:
        text = pattern.sub(replacement, text)
    return text


def normalize(command, answer):
    # an answer as it is compared with the snapshot
    answer = json.loads(mask(json.dumps(answer)))
    if command == "registers_json":
        # the counters change with every read, and the list is in read order
        registers = {}
        for name, value in answer.get("Registers", {}).items():
            if isinstance(value, list):
                merged = {}
                for item in value:
                    merged.update(item)
                registers[name] = dict(sorted(merged.items()))
        answer = {"Registers": registers}
    return answer


# -------------------------------------------------------------------------------
class SimulatedGenerator(object):
    """gensim and genmon for one capture, in temporary folders."""

    def __init__(self, capture):
        self.capture = capture
        self.folder = tempfile.mkdtemp(prefix="genmon_sim_")
        self.conf = os.path.join(self.folder, "conf") + os.sep
        self.logs = os.path.join(self.folder, "log") + os.sep
        self.data = os.path.join(self.folder, "data") + os.sep
        self.sim = os.path.join(self.folder, "sim") + os.sep
        for path in [self.conf, self.logs, self.data, self.sim]:
            os.mkdir(path)
        self.processes = []
        self.consoles = []
        self.client = None

    def register_file(self):
        path = self.capture["file"]
        if not os.path.isabs(path):
            path = os.path.join(CAPTURES_DIR, path)
        return path

    def start(self):
        from genmonlib.myconfig import MyConfig

        sim_port, genmon_port = free_port(), free_port()
        self.genmon_port = genmon_port
        with open(os.path.join(self.sim, "gensim.conf"), "w") as f:
            f.write("[gensim]\naddress = %s\nregister_file = %s\nserver_socket = %d\n"
                    "bind_address = 127.0.0.1\nlog_location = %s\n"
                    % (self.capture["address"], self.register_file(), sim_port, self.sim))

        for path in glob.glob(os.path.join(REPO_DIR, "conf", "*.conf")):
            shutil.copy(path, self.conf)
        settings = {
            "sitename": "SimTest",
            "use_serial_tcp": "True",
            "serial_tcp_address": "127.0.0.1",
            "serial_tcp_port": str(sim_port),
            "modbus_tcp": "False",
            "server_port": str(genmon_port),
            "address": self.capture["address"],
            "controllertype": self.capture["controllertype"],
            # a known model and kW, so genmon does not look up the serial
            # number on the internet
            "model": self.capture["model"],
            "nominalkw": self.capture["nominalkw"],
            "loglocation": self.logs,
            "userdatalocation": self.data,
            "update_check": "False",
            "autofeedback": "False",
            "disableweather": "True",
        }
        if "fueltype" in self.capture:
            settings["fueltype"] = self.capture["fueltype"]
        config = MyConfig(filename=os.path.join(self.conf, "genmon.conf"), section="GenMon")
        for key, value in settings.items():
            config.WriteValue(key, value)
        mail = MyConfig(filename=os.path.join(self.conf, "mymail.conf"), section="MyMail")
        for key in ["disableemail", "disablesmtp", "disableimap"]:
            mail.WriteValue(key, "True")

        self.processes.append(self.run([sys.executable, GENSIM, self.sim], "gensim_console.txt"))
        self.wait_for_port(sim_port, 15, "gensim")
        self.processes.append(self.run(
            [sys.executable, os.path.join(REPO_DIR, "genmon.py"), "-c", self.conf],
            "genmon_console.txt"))
        self.wait_for_genmon()
        return self

    def run(self, command, console_file):
        console = open(os.path.join(self.folder, console_file), "w")
        self.consoles.append(console)
        return subprocess.Popen(command, cwd=self.folder, stdout=console, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL)

    def check_running(self):
        for process in self.processes:
            if process.poll() is not None:
                raise RuntimeError("%s stopped:\n%s" % (process.args[1], self.console_text()))

    def wait_for_port(self, port, timeout, name):
        end = time.time() + timeout
        while time.time() < end:
            self.check_running()
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    return
            except OSError:
                time.sleep(0.2)
        raise RuntimeError(name + " did not start:\n" + self.console_text())

    def wait_for_genmon(self):
        from genmonlib.myclient import ClientInterface

        self.wait_for_port(self.genmon_port, 30, "genmon")
        # the client prints genmon's greeting (e.g. "CRITICAL: System in alarm!")
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.client = ClientInterface(host="127.0.0.1", port=self.genmon_port,
                                          loglocation=self.logs)
        self.client.console = logging.getLogger("genmon_sim_quiet")
        self.client.console.addHandler(logging.NullHandler())
        self.client.console.propagate = False
        # "OK" once the controller is initialized and data is coming in
        end = time.time() + START_TIMEOUT
        health = ""
        while time.time() < end:
            self.check_running()
            health = self.command("gethealth")
            if health.strip() == "OK":
                return
            time.sleep(1)
        raise RuntimeError("genmon did not get ready (" + health + "):\n" + self.genmon_log())

    def command(self, name):
        return self.client.ProcessMonitorCommand("generator: " + name)

    def wait_until_steady(self, commands, timeout=60):
        # genmon keeps reading (e.g. the logs) after it is ready; wait until the
        # answers stop changing
        previous = None
        end = time.time() + timeout
        while time.time() < end:
            self.check_running()
            current = {c: normalize(c, json.loads(self.command(c))) for c in commands}
            if current == previous:
                return current
            previous = current
            time.sleep(3)
        raise RuntimeError("genmon's answers did not settle in %d seconds" % timeout)

    def genmon_log(self):
        path = os.path.join(self.logs, "genmon.log")
        if not os.path.isfile(path):
            return ""
        with open(path) as f:
            return f.read()

    def console_text(self):
        text = ""
        for name in ["gensim_console.txt", "genmon_console.txt"]:
            path = os.path.join(self.folder, name)
            if os.path.isfile(path):
                with open(path) as f:
                    text += "--- " + name + "\n" + f.read()[-3000:]
        return text

    def stop(self):
        if self.client is not None:
            try:
                self.client.Close()
            except Exception:
                pass
        for process in reversed(self.processes):
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(5)
        for console in self.consoles:
            console.close()
        for name in ["client", "client_console"]:
            logger = logging.getLogger(name)
            for handler in list(logger.handlers):
                handler.close()
                logger.removeHandler(handler)
        shutil.rmtree(self.folder, ignore_errors=True)


# -------------------------------------------------------------------------------
@unittest.skipUnless(CAPTURES_DIR, "set GENMON_CAPTURES to a folder with captures.json")
class GenmonSimulatorTests(unittest.TestCase):

    def test_captures(self):
        captures = load_captures()
        self.assertTrue(captures, "captures.json lists no captures")
        snapshots = os.path.join(CAPTURES_DIR, "snapshots")
        for capture in captures:
            with self.subTest(capture=capture["name"]):
                sim = SimulatedGenerator(capture)
                try:
                    sim.start()
                    self.check_capture(sim, capture, snapshots)
                finally:
                    sim.stop()

    def check_capture(self, sim, capture, snapshots):
        info = json.loads(sim.command("start_info_json"))
        self.assertTrue(info["Controller"].startswith(capture["controller"]), info["Controller"])

        answers = {}
        for name, is_json in READ_COMMANDS.items():
            answer = sim.command(name)
            self.assertTrue(answer, name + ": no answer")
            if is_json:
                try:
                    answers[name] = json.loads(answer)
                except ValueError:
                    self.fail(name + ": not JSON: " + answer[:200])

        log = sim.genmon_log()
        # never send a serial number to the internet from a test
        self.assertNotIn("Looking up model info on internet", log)
        # genmon's data files go to its config folder (genmon.py -c)
        self.assertNotIn("/etc/genmon/", log)
        allowed = capture.get("log_errors_allowed", [])
        errors = [line for line in log.splitlines()
                  if "error" in line.lower() and not any(a in line for a in allowed)]
        self.assertEqual(errors, [], "errors in genmon.log")

        if os.path.isdir(snapshots):
            self.check_snapshot(capture["name"], sim.wait_until_steady(SNAPSHOT_COMMANDS), snapshots)

    def check_snapshot(self, name, current, snapshots):
        path = os.path.join(snapshots, name + ".json")
        if os.environ.get("GENMON_SIM_UPDATE") or not os.path.isfile(path):
            with open(path, "w") as f:
                json.dump(current, f, indent=1, sort_keys=True)
            return
        with open(path) as f:
            saved = json.load(f)
        for command in SNAPSHOT_COMMANDS:
            with self.subTest(snapshot=name, command=command):
                self.assertEqual(current[command], saved.get(command))


if __name__ == "__main__":
    unittest.main()
