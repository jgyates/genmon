#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_myclient.py
# PURPOSE: Tests for genmonlib/myclient.py, the connection genserv and the
#          add-ons use to talk to genmon: waiting for genmon to be ready.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_myclient
#
# -------------------------------------------------------------------------------

import logging
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genmonlib import myclient  # noqa: E402
from genmonlib.myclient import ClientInterface  # noqa: E402


class WaitForReadyTests(unittest.TestCase):

    def client(self, answers):
        """A ClientInterface without a connection; genmon answers each
        start_info_json request with the next of answers."""
        client = ClientInterface.__new__(ClientInterface)
        client.log = logging.getLogger("myclient_test")
        client.log.handlers, client.log.propagate = [logging.NullHandler()], False
        client.console = client.log
        self.requests = []

        def ask(command):
            self.requests.append(command)
            answer = answers.pop(0) if answers else "Retry, genmon is starting"
            if isinstance(answer, Exception):
                raise answer
            return answer

        client.ProcessMonitorCommand = ask
        return client

    def test_ready(self):
        client = self.client(['{"version": "2.0.3"}'])
        with mock.patch.object(myclient.time, "sleep") as sleep:
            self.assertTrue(client.WaitForReady(timeout=5))
        sleep.assert_not_called()
        self.assertEqual(self.requests, ["generator: start_info_json"])

    def test_waits_between_requests(self):
        # a pause before asking again (it asked in a tight loop, logging an
        # error each time, while genmon was starting)
        client = self.client(["Retry", OSError("not connected"), '{"version": "2.0.3"}'])
        with mock.patch.object(myclient.time, "sleep") as sleep:
            self.assertTrue(client.WaitForReady(timeout=5))
        self.assertEqual(len(self.requests), 3)
        self.assertEqual(sleep.call_args_list, [mock.call(1), mock.call(1)])

    def test_timeout(self):
        client = self.client([])
        real_sleep = time.sleep
        with mock.patch.object(myclient.time, "sleep", side_effect=lambda s: real_sleep(0.02)):
            self.assertFalse(client.WaitForReady(timeout=0.1))
        self.assertLess(len(self.requests), 10)


if __name__ == "__main__":
    unittest.main()
