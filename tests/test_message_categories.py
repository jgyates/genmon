#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_message_categories.py
# PURPOSE: Tests for messages that have their own notification category (the
#          categories on the Notifications page): low fuel warnings
#          (GeneratorController.CheckFuelLevel in genmonlib/controller.py, "fuel")
#          and the software update notice (Monitor.CheckSoftwareUpdate in
#          genmon.py, "software_update").
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_message_categories
#
# -------------------------------------------------------------------------------

import datetime
import io
import os
import sys
import unittest
from unittest import mock

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_DIR)

import genmon
from genmonlib.controller import GeneratorController
from genmonlib.program_defaults import ProgramDefaults


class FuelWarningTests(unittest.TestCase):

    def check(self, level):
        # a controller without its __init__ (which needs a generator connection)
        controller = GeneratorController.__new__(GeneratorController)
        controller.SiteName = "Test Site"
        controller.MessagePipe = mock.Mock()
        controller.log = None
        controller.console = None
        with mock.patch.object(controller, "FuelSensorSupported", return_value=True), \
                mock.patch.object(controller, "ExternalFuelDataSupported", return_value=False), \
                mock.patch.object(controller, "FuelTankCalculationSupported", return_value=False), \
                mock.patch.object(controller, "GetFuelLevel", return_value=level):
            ok = controller.CheckFuelLevel()
        return ok, controller.FuelLevelOK, controller.MessagePipe.SendMessage.call_args_list

    def test_below_ten_percent(self):
        ok, level_ok, calls = self.check(8.0)
        self.assertFalse(ok)
        self.assertFalse(level_ok)
        self.assertEqual(len(calls), 1)
        title, body = calls[0][0]
        self.assertEqual(title, "Warning: Fuel Level Low (10%) at Test Site")
        self.assertIn("Fuel Level is 8.0%", body)
        self.assertEqual(calls[0][1], {"msgtype": "fuel", "onlyonce": True})

    def test_below_twenty_percent(self):
        ok, level_ok, calls = self.check(15.0)
        self.assertFalse(ok)
        self.assertEqual(calls[0][0][0], "Warning: Fuel Level Low (20%) at Test Site")
        self.assertEqual(calls[0][1]["msgtype"], "fuel")

    def test_enough_fuel(self):
        ok, level_ok, calls = self.check(50.0)
        self.assertTrue(ok)
        self.assertTrue(level_ok)
        self.assertEqual(calls, [])



class SoftwareUpdateTests(unittest.TestCase):

    def check(self, latest_version):
        # a Monitor without its __init__ (which starts genmon)
        monitor = genmon.Monitor.__new__(genmon.Monitor)
        monitor.UpdateCheck = True
        monitor.LastSoftwareUpdateCheck = datetime.datetime.now() - datetime.timedelta(days=2)
        monitor.ProgramName = "Generator Monitor"
        monitor.SiteName = "Test Site"
        monitor.UserURL = ""
        monitor.UpdateAvailable = False
        monitor.MessagePipe = mock.Mock()
        monitor.log = None
        monitor.console = None
        # program_defaults.py as read from github
        page = ('class ProgramDefaults(object):\n    GENMON_VERSION = "%s"\n'
                % latest_version).encode("ascii")
        with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(page)):
            monitor.CheckSoftwareUpdate()
        return monitor, monitor.MessagePipe.SendMessage.call_args_list

    def test_update_available(self):
        monitor, calls = self.check("99.0.0")
        self.assertTrue(monitor.UpdateAvailable)
        self.assertEqual(len(calls), 1)
        title, body = calls[0][0]
        self.assertEqual(title, "Generator Monitor Software Update 99.0.0 is available for site Test Site")
        self.assertIn("The current version installed is " + ProgramDefaults.GENMON_VERSION, body)
        self.assertEqual(calls[0][1], {"msgtype": "software_update", "onlyonce": True})

    def test_up_to_date(self):
        monitor, calls = self.check(ProgramDefaults.GENMON_VERSION)
        self.assertFalse(monitor.UpdateAvailable)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
