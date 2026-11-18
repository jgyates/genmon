#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_addon_exercise.py
# PURPOSE: Tests for addon/genexercise.py, which exercises the generator on its
#          own schedule: when an exercise is due (daily, weekly, biweekly,
#          monthly by day or by Nth weekday, using this computer's or the
#          generator's clock), the commands it sends to start and stop each
#          type of exercise (normal, quiet, transfer with or without warmup),
#          and exercising after the controller's own exercise.
#
#          genmon, the clock and the timers are fakes, see addon_fixture.py.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_addon_exercise
#
# -------------------------------------------------------------------------------

import datetime
import json
import os
import sys
import threading
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from addon_fixture import AddOnFixture  # noqa: E402

START = "generator: setremote=start"
START_EXERCISE = "generator: setremote=startexercise"
START_TRANSFER = "generator: setremote=starttransfer"
STOP = "generator: setremote=stop"
REMOTE = "generator: setremote="


class FakeTimer(object):
    """threading.Timer: recorded, and fired by the test."""

    timers = []

    def __init__(self, interval, function):
        self.interval, self.function = interval, function
        FakeTimer.timers.append(self)

    def start(self):
        pass

    def cancel(self):
        pass


class ExerciseTestCase(unittest.TestCase):

    def setUp(self):
        FakeTimer.timers = []
        self.now = datetime.datetime(2026, 11, 2, 12, 0, 0)  # a Monday, 12:00
        test = self

        class FakeDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return test.now

        self.clock = types.SimpleNamespace(datetime=FakeDateTime, date=datetime.date,
                                           timedelta=datetime.timedelta)

    def start(self, controller="Evolution 2.0, Air Cooled", base="READY", **settings):
        conf = {"exercise_type": "Normal", "exercise_frequency": "Weekly",
                "exercise_day_of_week": "Monday", "exercise_hour": "12", "exercise_minute": "0",
                "exercise_day_of_month": "1", "exercise_nth_day_of_month": "0",
                "exercise_duration": "15", "exercise_warmup": "0", "use_gen_time": "False"}
        conf.update(settings)
        fixture = AddOnFixture("genexercise", "GenExercise", conf,
                               patches=[("datetime", self.clock),
                                        ((threading, "Timer"), FakeTimer)])
        fixture.state["base"] = base
        fixture.state["answers"] = {"start_info_json": json.dumps({"Controller": controller})}
        self.addCleanup(fixture.stop)
        return fixture.start()

    def remote(self, fixture):
        return [c for c in fixture.genmon.commands if c.startswith(REMOTE)]


# -------------------------------------------------------------------------------
class ScheduleTests(ExerciseTestCase):
    """GenExercise.TimeForExercise"""

    def due(self, fixture, when):
        self.now = when
        return fixture.addon.TimeForExercise()

    def test_weekly(self):
        fixture = self.start(exercise_frequency="Weekly", exercise_day_of_week="Wednesday",
                             exercise_hour="9", exercise_minute="30")
        self.assertTrue(self.due(fixture, datetime.datetime(2026, 11, 4, 9, 30)))   # Wednesday
        self.assertFalse(self.due(fixture, datetime.datetime(2026, 11, 4, 9, 31)))
        self.assertFalse(self.due(fixture, datetime.datetime(2026, 11, 5, 9, 30)))  # Thursday

    def test_daily(self):
        fixture = self.start(exercise_frequency="Daily", exercise_hour="6", exercise_minute="0")
        self.assertTrue(self.due(fixture, datetime.datetime(2026, 11, 5, 6, 0)))
        self.assertFalse(self.due(fixture, datetime.datetime(2026, 11, 5, 7, 0)))

    def test_monthly_day(self):
        fixture = self.start(exercise_frequency="Monthly", exercise_day_of_month="15")
        self.assertTrue(self.due(fixture, datetime.datetime(2026, 11, 15, 12, 0)))
        self.assertFalse(self.due(fixture, datetime.datetime(2026, 11, 16, 12, 0)))

    def test_monthly_nth_weekday(self):
        # the second Tuesday of November 2026 is the 10th
        fixture = self.start(exercise_frequency="Monthly", exercise_day_of_week="Tuesday",
                             exercise_nth_day_of_month="2")
        self.assertTrue(self.due(fixture, datetime.datetime(2026, 11, 10, 12, 0)))
        self.assertFalse(self.due(fixture, datetime.datetime(2026, 11, 3, 12, 0)))
        self.assertFalse(self.due(fixture, datetime.datetime(2026, 11, 17, 12, 0)))

    def test_biweekly(self):
        fixture = self.start(exercise_frequency="Biweekly",
                             last_exercise="Monday October 26, 2026 12:00:00")
        self.assertFalse(self.due(fixture, datetime.datetime(2026, 11, 2, 12, 0)))  # 7 days
        self.assertTrue(self.due(fixture, datetime.datetime(2026, 11, 9, 12, 0)))   # 14 days

    def test_biweekly_counts_from_the_last_exercise(self):
        # after an exercise, the next one is two weeks later (not one)
        fixture = self.start(exercise_frequency="Biweekly")
        self.now = datetime.datetime(2026, 11, 2, 12, 0)
        fixture.addon.StartExercise()
        self.assertFalse(self.due(fixture, datetime.datetime(2026, 11, 9, 12, 0)))
        self.assertTrue(self.due(fixture, datetime.datetime(2026, 11, 16, 12, 0)))
        # and it is saved, for after a restart
        self.assertEqual(fixture.addon.config.ReadValue("last_exercise"),
                         "Monday November 02, 2026 12:00:00")

    def test_biweekly_with_an_empty_last_exercise(self):
        fixture = self.start(exercise_frequency="Biweekly", last_exercise="")
        self.assertTrue(self.due(fixture, datetime.datetime(2026, 11, 2, 12, 0)))

    def test_generator_clock(self):
        # the time from the generator (status_json), not this computer's
        fixture = self.start(use_gen_time="True")
        fixture.state["answers"]["status_json"] = json.dumps({"Status": [
            {"Time": [{"Generator Time": "Monday November 9, 2026 12:00"}]}]})
        self.now = datetime.datetime(2026, 11, 9, 8, 15)
        self.assertTrue(fixture.addon.TimeForExercise())


# -------------------------------------------------------------------------------
class ExerciseTests(ExerciseTestCase):
    """GenExercise.StartExercise / StopExercise / PostWarmup"""

    def test_normal(self):
        fixture = self.start(exercise_type="Normal")
        fixture.addon.StartExercise()
        self.assertEqual(self.remote(fixture), [START])
        timer = FakeTimer.timers[-1]
        self.assertEqual(timer.interval, 15 * 60.0)
        timer.function()
        self.assertEqual(self.remote(fixture), [START, STOP])

    def test_quiet(self):
        fixture = self.start(exercise_type="Quiet")
        fixture.addon.StartExercise()
        self.assertEqual(self.remote(fixture), [START_EXERCISE])

    def test_transfer(self):
        fixture = self.start(exercise_type="Transfer")
        fixture.addon.StartExercise()
        self.assertEqual(self.remote(fixture), [START_TRANSFER])

    def test_transfer_with_warmup(self):
        fixture = self.start(exercise_type="Transfer", exercise_warmup="5")
        fixture.addon.StartExercise()
        self.assertEqual(self.remote(fixture), [START])
        warmup = FakeTimer.timers[-1]
        self.assertEqual(warmup.interval, 5 * 60.0)
        fixture.state["base"] = "RUNNING"
        warmup.function()
        self.assertEqual(self.remote(fixture), [START, START_TRANSFER])
        self.assertEqual(FakeTimer.timers[-1].interval, 15 * 60.0)

    def test_transfer_warmup_not_running(self):
        # the generator did not start: no transfer, stop instead
        fixture = self.start(exercise_type="Transfer", exercise_warmup="5")
        fixture.addon.StartExercise()
        FakeTimer.timers[-1].function()
        self.assertEqual(self.remote(fixture), [START, STOP])

    def test_not_ready(self):
        for base in ["OFF", "MANUAL", "ALARM", "RUNNING"]:
            with self.subTest(base=base):
                fixture = self.start(base=base)
                fixture.addon.StartExercise()
                self.assertEqual([c for c in self.remote(fixture) if c != STOP], [])

    def test_service_due_is_ready(self):
        fixture = self.start(base="SERVICEDUE")
        fixture.addon.StartExercise()
        self.assertEqual(self.remote(fixture), [START])

    def test_only_one_exercise_at_a_time(self):
        fixture = self.start()
        fixture.addon.StartExercise()
        fixture.addon.StartExercise()
        self.assertEqual(self.remote(fixture), [START])

    def test_exercise_thread_starts_when_due(self):
        fixture = self.start()
        fixture.run_thread("ExerciseThread")
        self.assertEqual(self.remote(fixture), [START])


# -------------------------------------------------------------------------------
class StartupTests(ExerciseTestCase):

    def test_stops_an_exercise_left_running(self):
        fixture = self.start(base="EXERCISING")
        self.assertEqual(self.remote(fixture), [STOP])

    def test_needs_evolution_or_nexus(self):
        with self.assertRaises(SystemExit):
            self.start(controller="H-100 Controller")

    def test_after_the_controller_exercise(self):
        fixture = self.start(exercise_frequency="Post-Controller")
        self.assertIn("PostExerciseThread", fixture.addon.Threads)
        fixture.state["base"] = "EXERCISING"
        waits = []

        def wait(*args):
            # the controller's exercise, then ready: our exercise starts
            waits.append(args)
            fixture.state["base"] = "READY"
            return len(waits) > 1

        with mock.patch.object(fixture.addon, "WaitForExit", side_effect=wait), \
                mock.patch.object(fixture.module.time, "sleep"):
            fixture.addon.PostExerciseThread()
        self.assertEqual(self.remote(fixture), [START])


if __name__ == "__main__":
    unittest.main()
