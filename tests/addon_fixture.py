#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: addon_fixture.py
# PURPOSE: Runs an add-on (genslack.py, gentankutil.py, ...) in a test, without
#          genmon, threads or network:
#
#          - genmon is a FakeGenmon: the test sets the generator state (READY,
#            RUNNING, ...), utility outage, software update, system health, fuel
#            and Pi health it reports.
#          - threads (genmonlib.mythread.MyThread) are not started; the test runs
#            one pass of the add-on's polling (poll()) and then sends what the
#            add-on queued (send_queued()).
#          - the libraries an add-on sends with (requests, chump, twilio, ...) are
#            fakes from the test, which record what would be sent.
#
#          Used by test_addons_notify.py and test_addons_data.py.
# -------------------------------------------------------------------------------

import glob
import importlib
import json
import logging
import os
import shutil
import signal
import sys
import tempfile
from unittest import mock

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_DIR = os.path.join(REPO_DIR, "addon")
for path in [REPO_DIR, ADDON_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

from genmonlib import mymsgqueue, mynotify  # noqa: E402


class StopPolling(BaseException):
    # not an Exception, so the add-on's "except Exception" does not catch it
    pass


# -------------------------------------------------------------------------------
class FakeGenmon(object):
    """genmon's answers to the commands an add-on sends (ClientInterface)."""

    def __init__(self, state):
        self.state = state
        self.commands = []

    def __call__(self, *args, **kwargs):
        # used as the ClientInterface class: every connection shares the state
        return self

    def ProcessMonitorCommand(self, command):
        self.commands.append(command)
        s = self.state
        name = command.replace("generator: ", "")
        if name == "getsitename":
            return s["sitename"]
        if name == "getbase":
            return s["base"]
        if name == "outage_json":
            return json.dumps({"Outage": [{"Status": "OK"}, {"System In Outage": s["outage"]}]})
        if name == "monitor_json":
            return json.dumps({"Monitor": [
                {"Generator Monitor Stats": [{"Monitor Health": s["health"]},
                                             {"Update Available": s["update"]}]},
                {"Communication Stats": []},
                {"Platform Stats": [{"Pi CPU Frequency Throttling": s["throttling"]},
                                    {"Pi ARM Frequency Cap": "OK"},
                                    {"Pi Undervoltage": s["undervoltage"]}]},
            ]})
        if name == "maint_json":
            return json.dumps({"Maintenance": [{"Fuel Level State": s["fuel"]}]})
        return ""

    def Close(self):
        pass


class FakeThread(object):
    """genmonlib.mythread.MyThread that never starts a thread."""

    def __init__(self, ThreadFunction, Name=None, start=True):
        self.function, self.name = ThreadFunction, Name

    def Start(self, timeout=None):
        pass

    def Stop(self):
        pass

    def StopSignaled(self):
        return True

    def IsAlive(self):
        return False

    def Wait(self, timeout=None):
        pass

    def WaitForThreadToEnd(self, Timeout=None):
        pass

    def Name(self):
        return self.name


# -------------------------------------------------------------------------------
class AddOnFixture(object):

    def __init__(self, module_name, class_name, settings, modules=None, patches=None,
                 loop_in_init=False, reimport=None):
        """module_name: e.g. "genslack"; class_name: e.g. "GenSlack".
        settings: values for its config file (the rest come from conf/).
        modules: fake third party modules, e.g. {"chump": fake_chump}.
        patches: (target, value) pairs for mock.patch, e.g. requests.post.
        loop_in_init: the add-on's __init__ ends in a "while True: time.sleep()"
        loop (gencallmebot.py); the first sleep raises an error to end it.
        reimport: modules to import again with the fake modules in place, e.g.
        ["genmonlib.gaugediy"] (which imports smbus)."""
        self.loop_in_init = loop_in_init
        self.reimport = reimport or []
        self.module_name, self.class_name = module_name, class_name
        self.settings, self.fake_modules = settings, modules or {}
        self.extra_patches = patches or []
        self.state = {"sitename": "Test Site", "base": "READY", "outage": "No", "update": "No",
                      "health": "OK", "fuel": "OK", "throttling": "OK", "undervoltage": "OK"}
        self.genmon = FakeGenmon(self.state)
        self.patches = []

    def start(self):
        self.folder = tempfile.mkdtemp(prefix="addon_test_") + os.sep
        self.write_config()
        self.log = logging.getLogger("addon_test_" + self.module_name)
        self.log.handlers = [logging.NullHandler()]
        self.log.propagate = False

        patches = [
            mock.patch.dict(sys.modules, self.fake_modules),
            mock.patch.object(mynotify, "ClientInterface", self.genmon),
            mock.patch.object(mynotify, "MyThread", FakeThread),
            mock.patch.object(mymsgqueue, "MyThread", FakeThread),
            mock.patch.object(signal, "signal"),
        ]
        for patch in patches:
            patch.start()
            self.patches.append(patch)
        # import (or import again) with the fake modules in place; the
        # sys.modules patch above puts the old modules back afterwards
        for name in self.reimport:
            sys.modules.pop(name, None)
        sys.modules.pop(self.module_name, None)
        self.module = importlib.import_module(self.module_name)
        for target, value in [("ClientInterface", self.genmon), ("MyThread", FakeThread)]:
            if hasattr(self.module, target):
                patch = mock.patch.object(self.module, target, value)
                patch.start()
                self.patches.append(patch)
        for target, value in self.extra_patches:
            patch = mock.patch.object(self.module, target, value) if isinstance(target, str) \
                else mock.patch.object(target[0], target[1], value)
            patch.start()
            self.patches.append(patch)

        cls = getattr(self.module, self.class_name)
        args = dict(log=self.log, loglocation=self.folder, ConfigFilePath=self.folder,
                    host="127.0.0.1", port=9082, console=self.log)
        if self.loop_in_init:
            with mock.patch.object(self.module.time, "sleep",
                                   side_effect=RuntimeError("end of the test's __init__")):
                self.addon = cls(**args)
        else:
            self.addon = cls(**args)
        # the add-on's GenNotify (genmonlib/mynotify.py), if it has one
        self.notify = getattr(self.addon, "Notify", None) or getattr(self.addon, "GenNotify", None)
        return self

    def write_config(self):
        from genmonlib.myconfig import MyConfig

        for path in glob.glob(os.path.join(REPO_DIR, "conf", "*.conf")):
            shutil.copy(path, self.folder)
        # the config file and section of the add-on's settings
        name, section = {"gensms_modem": ("mymodem.conf", "MyModem")}.get(
            self.module_name, (self.module_name + ".conf", self.module_name))
        config = MyConfig(filename=os.path.join(self.folder, name), section=section)
        for key, value in self.settings.items():
            config.WriteValue(key, str(value))

    def poll(self):
        """One pass of the add-on's polling of genmon (mynotify)."""
        with mock.patch.object(mynotify.time, "sleep", side_effect=StopPolling):
            try:
                self.notify.MainPollingThread()
            except StopPolling:
                pass

    def run_thread(self, name):
        """One pass of one of the add-on's threads (e.g. "TankCheckThread"):
        the thread's waits return "exit" and sleeps return at once."""
        function = self.addon.Threads[name].function
        with mock.patch.object(self.addon, "WaitForExit", return_value=True), \
                mock.patch.object(self.module.time, "sleep"):
            function()

    def commands(self, prefix):
        """The genmon commands the add-on sent that start with prefix, e.g.
        "generator: set_tank_data=": the rest of each, as JSON if it is JSON."""
        result = []
        for command in self.genmon.commands:
            if command.startswith(prefix):
                value = command[len(prefix):]
                try:
                    value = json.loads(value)
                except ValueError:
                    pass
                result.append(value)
        return result

    def send_queued(self):
        """Send what the add-on queued, as its queue thread would. (Some add-ons
        have no queue and send when the event happens.)"""
        queue = getattr(self.addon, "Queue", None)
        if queue is None:
            return
        with mock.patch.object(queue, "WaitForExit", return_value=True), \
                mock.patch.object(mymsgqueue.time, "sleep"):
            queue.QueueWorker()

    def stop(self):
        try:
            self.addon.Close()
        except BaseException:
            pass
        for patch in reversed(self.patches):
            patch.stop()
        self.patches = []
        sys.modules.pop(self.module_name, None)
        shutil.rmtree(self.folder, ignore_errors=True)
