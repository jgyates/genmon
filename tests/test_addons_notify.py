#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_addons_notify.py
# PURPOSE: Tests for the notification add-ons (addon/genslack.py, gensms.py,
#          genpushover.py, gencallmebot.py, genemail2sms.py, gensms_modem.py,
#          gensms_voip.py, gensyslog.py) and the code they share:
#          genmonlib/mynotify.py (which generator events cause a message, and the
#          notify_* settings) and genmonlib/mymsgqueue.py (sending and retrying).
#
#          Nothing is sent: genmon, threads and the services (Slack, Twilio,
#          Pushover, CallMeBot, email, the LTE modem, voip.ms, syslog) are
#          fakes, see addon_fixture.py.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_addons_notify
#
# -------------------------------------------------------------------------------

import json
import os
import sys
import types
import unittest
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests  # noqa: E402

from addon_fixture import AddOnFixture  # noqa: E402


class FakeResponse(object):
    def __init__(self, status_code=200, text="ok"):
        self.status_code, self.text = status_code, text


class FakePost(object):
    """requests.post: records the calls, answers with status_code."""

    def __init__(self):
        self.calls, self.status_code = [], 200

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.status_code)


SLACK_SETTINGS = {"webhook_url": "https://hooks.slack.example/T1", "username": "genmon",
                  "channel": "", "title_link": ""}


# -------------------------------------------------------------------------------
class NotifyTestCase(unittest.TestCase):

    def start_slack(self, **settings):
        self.post = FakePost()
        conf = dict(SLACK_SETTINGS)
        conf.update(settings)
        fixture = AddOnFixture("genslack", "GenSlack", conf,
                               patches=[((requests, "post"), self.post)])
        self.addCleanup(fixture.stop)
        return fixture.start()

    def slack_messages(self):
        return [json.loads(kwargs["data"])["attachments"][0]["fields"][0]["value"]
                for url, kwargs in self.post.calls]

    def poll_and_send(self, fixture):
        fixture.poll()
        fixture.send_queued()
        messages = self.slack_messages()
        self.post.calls = []
        return messages


# -------------------------------------------------------------------------------
class GenNotifyTests(NotifyTestCase):
    """Which changes in genmon cause a message (genmonlib/mynotify.py), with genslack."""

    def test_first_poll(self):
        # the add-on starts: the current state is reported once
        fixture = self.start_slack()
        self.assertEqual(self.poll_and_send(fixture), [
            "Test Site: Utility Service is Up",
            "Test Site: System Health : OK",
            "Test Site: Software Is Up To Date",
            "Test Site: Pi Health : OK",
            "Test Site: Generator Ready",
        ])
        # nothing changed: no messages
        self.assertEqual(self.poll_and_send(fixture), [])

    def test_generator_states(self):
        fixture = self.start_slack()
        self.poll_and_send(fixture)
        for base, message in [("EXERCISING", "Generator Exercising"),
                              ("RUNNING", "Generator Running"),
                              ("RUNNING-MANUAL", "Generator Running in Manual Mode"),
                              ("ALARM", "Generator Alarm"),
                              ("SERVICEDUE", "Generator Service Due"),
                              ("OFF", "Generator Off"),
                              ("MANUAL", "Generator Manual"),
                              ("READY", "Generator Ready")]:
            with self.subTest(base=base):
                fixture.state["base"] = base
                self.assertEqual(self.poll_and_send(fixture), ["Test Site: " + message])

    def test_outage(self):
        fixture = self.start_slack()
        self.poll_and_send(fixture)
        fixture.state["outage"] = "Yes"
        self.assertEqual(self.poll_and_send(fixture), ["Test Site: Utility Service is Down"])
        fixture.state["outage"] = "No"
        self.assertEqual(self.poll_and_send(fixture), ["Test Site: Utility Service is Up"])

    def test_software_update(self):
        fixture = self.start_slack()
        self.poll_and_send(fixture)
        fixture.state["update"] = "Yes"
        self.assertEqual(self.poll_and_send(fixture), ["Test Site: Software Update Available"])

    def test_system_health(self):
        fixture = self.start_slack()
        self.poll_and_send(fixture)
        fixture.state["health"] = "WARNING: System Initializing"
        self.assertEqual(self.poll_and_send(fixture),
                         ["Test Site: System Health : WARNING: System Initializing"])

    def test_fuel(self):
        fixture = self.start_slack()
        self.poll_and_send(fixture)
        fixture.state["fuel"] = "Low"
        self.assertEqual(self.poll_and_send(fixture), ["Test Site: Fuel Level is Low"])
        fixture.state["fuel"] = "OK"
        self.assertEqual(self.poll_and_send(fixture), ["Test Site: Fuel Level is OK"])

    def test_pi_health(self):
        fixture = self.start_slack()
        self.poll_and_send(fixture)
        fixture.state["undervoltage"] = "Undervoltage Detected"
        self.assertEqual(self.poll_and_send(fixture),
                         ["Test Site: Pi Health :  Pi Undervoltage:Undervoltage Detected"])

    def test_notify_settings(self):
        # notify_* on the Add-Ons page turn categories of messages off
        fixture = self.start_slack(notify_info="False", notify_outage="False",
                                   notify_sw_update="False", notify_pi_state="False")
        self.assertEqual(self.poll_and_send(fixture), [])
        fixture.state.update(base="RUNNING", outage="Yes", update="Yes", undervoltage="Low")
        self.assertEqual(self.poll_and_send(fixture), [])
        fixture.state["base"] = "ALARM"  # notify_error is still on
        self.assertEqual(self.poll_and_send(fixture), ["Test Site: Generator Alarm"])

    def test_notify_warning(self):
        fixture = self.start_slack(notify_warning="False")
        self.poll_and_send(fixture)
        fixture.state.update(base="SERVICEDUE", fuel="Low")
        self.assertEqual(self.poll_and_send(fixture), [])


# -------------------------------------------------------------------------------
class MessageQueueTests(NotifyTestCase):
    """Sending and retrying (genmonlib/mymsgqueue.py), with genslack."""

    def test_failed_message_is_kept(self):
        fixture = self.start_slack()
        fixture.poll()
        self.post.status_code = 500
        fixture.send_queued()
        # the oldest message is retried before the others
        self.assertEqual(len(self.post.calls), 1)
        queued = [item[0] for item in reversed(fixture.addon.Queue.MessageQueue)]
        self.assertEqual(queued[0], "Utility Service is Up")
        self.assertEqual(len(queued), 5)
        self.post.status_code = 200
        self.post.calls = []
        fixture.send_queued()
        self.assertEqual(len(self.slack_messages()), 5)
        self.assertEqual(fixture.addon.Queue.MessageQueue, [])

    def test_message_dropped_after_max_retry_time(self):
        fixture = self.start_slack(max_retry_time="0")
        fixture.poll()
        self.post.status_code = 500
        for _ in range(5):
            fixture.send_queued()
        self.assertEqual(fixture.addon.Queue.MessageQueue, [])


# -------------------------------------------------------------------------------
class SlackTests(NotifyTestCase):

    def test_message_format(self):
        fixture = self.start_slack(channel="#generator", title_link="https://genmon.example",
                                   icon_emoji=":zap:")
        fixture.poll()
        fixture.send_queued()
        url, kwargs = self.post.calls[0]
        self.assertEqual(url, "https://hooks.slack.example/T1")
        self.assertEqual(kwargs["headers"], {"Content-Type": "application/json"})
        self.assertEqual(kwargs["timeout"], 30)
        self.assertEqual(json.loads(kwargs["data"]), {
            "username": "genmon", "icon_emoji": ":zap:", "channel": "#generator",
            "attachments": [{"title": "GenMon Alert", "title_link": "https://genmon.example",
                             "fields": [{"title": "Status", "value": "Test Site: Utility Service is Up",
                                         "short": "false"}]}]})

    def test_optional_settings_left_out(self):
        fixture = self.start_slack(icon_emoji="")
        fixture.poll()
        fixture.send_queued()
        data = json.loads(self.post.calls[0][1]["data"])
        self.assertNotIn("channel", data)
        self.assertNotIn("title_link", data["attachments"][0])
        self.assertEqual(data["icon_emoji"], ":red_circle:")


# -------------------------------------------------------------------------------
class SMSTests(unittest.TestCase):
    """gensms.py, Twilio"""

    def setUp(self):
        self.sent = []
        sent = self.sent

        self.fail_once = set()
        fail_once = self.fail_once

        class Messages(object):
            def create(self, to, from_, body):
                if to in fail_once:
                    fail_once.discard(to)
                    raise RuntimeError("Twilio error for " + to)
                sent.append((to, from_, body))
                return types.SimpleNamespace(sid="SM%d" % len(sent))

        class Client(object):
            def __init__(self, account, token):
                self.account, self.token = account, token
                self.messages = Messages()

        twilio = types.ModuleType("twilio")
        rest = types.ModuleType("twilio.rest")
        rest.Client = Client
        twilio.rest = rest
        self.fixture = AddOnFixture("gensms", "GenSMS", {
            "accountsid": "AC123", "authtoken": "token", "from_number": "+15550000000",
            "to_number": "+15551111111, +15552222222"},
            modules={"twilio": twilio, "twilio.rest": rest})
        self.addCleanup(self.fixture.stop)
        self.fixture.start()

    def test_sent_to_each_number(self):
        self.fixture.poll()
        self.fixture.send_queued()
        first = [s for s in self.sent if s[2] == "Test Site: Utility Service is Up"]
        self.assertEqual(first, [("+15551111111", "+15550000000", "Test Site: Utility Service is Up"),
                                 ("+15552222222", "+15550000000", "Test Site: Utility Service is Up")])
        self.assertEqual(len(self.sent), 10)

    def test_retry_only_to_numbers_that_failed(self):
        self.fixture.poll()
        self.fixture.send_queued()
        self.sent.clear()
        self.fail_once.add("+15552222222")
        self.fixture.state["outage"] = "Yes"
        self.fixture.poll()
        self.fixture.send_queued()  # the second number fails
        self.fixture.send_queued()  # the retry
        down = [s[0] for s in self.sent if s[2] == "Test Site: Utility Service is Down"]
        self.assertEqual(down, ["+15551111111", "+15552222222"])
        self.assertEqual(self.fixture.addon.Queue.MessageQueue, [])


# -------------------------------------------------------------------------------
class PushoverTests(unittest.TestCase):
    """genpushover.py, Pushover (chump library)"""

    def setUp(self):
        self.sent = []
        sent = self.sent
        self.fail_once = set()
        fail_once = self.fail_once

        class Message(object):
            id = "message-id"

            def __init__(self, user, message, priority, sound):
                self.fields = (user, message, priority, sound)

            def send(self):
                if self.fields[0] in fail_once:
                    fail_once.discard(self.fields[0])
                    raise RuntimeError("Pushover error")
                sent.append(self.fields)

        class User(object):
            is_authenticated = True

            def __init__(self, user_id):
                self.user_id = user_id

            def create_message(self, message, priority, sound):
                return Message(self.user_id, message, priority, sound)

        class Application(object):
            is_authenticated = True

            def __init__(self, app_id):
                self.app_id = app_id

            def get_user(self, user_id):
                return User(user_id)

        chump = types.ModuleType("chump")
        chump.Application = Application
        chump.LOWEST, chump.LOW, chump.NORMAL, chump.HIGH, chump.EMERGENCY = -2, -1, 0, 1, 2
        self.chump = chump
        self.settings = {"appid": "a" * 30, "userid": "u" * 30, "pushsound": "updown"}

    def start(self, **settings):
        conf = dict(self.settings)
        conf.update(settings)
        fixture = AddOnFixture("genpushover", "GenPushover", conf, modules={"chump": self.chump})
        self.addCleanup(fixture.stop)
        return fixture.start()

    def test_message_and_priority(self):
        fixture = self.start(outage_priority="HIGH")
        fixture.poll()
        fixture.send_queued()
        self.sent.clear()
        fixture.state["outage"] = "Yes"
        fixture.poll()
        fixture.send_queued()
        self.assertEqual(self.sent, [("u" * 30, "Test Site: Utility Service is Down", 1, "updown")])

    def test_extra_users_only_get_their_categories(self):
        fixture = self.start(extra_userid="e" * 30, extra_notify_outage="False")
        fixture.poll()
        fixture.send_queued()
        self.sent.clear()
        fixture.state["outage"] = "Yes"
        fixture.poll()
        fixture.send_queued()
        self.assertEqual([s[0] for s in self.sent], ["u" * 30])
        self.sent.clear()
        fixture.state["base"] = "RUNNING"
        fixture.poll()
        fixture.send_queued()
        self.assertEqual(sorted(s[0] for s in self.sent), ["e" * 30, "u" * 30])


    def test_retry_only_to_users_that_failed(self):
        fixture = self.start(extra_userid="e" * 30)
        fixture.poll()
        fixture.send_queued()
        self.sent.clear()
        self.fail_once.add("e" * 30)
        fixture.state["outage"] = "Yes"
        fixture.poll()
        fixture.send_queued()  # the extra user fails
        fixture.send_queued()  # the retry
        down = [s[0] for s in self.sent if s[1] == "Test Site: Utility Service is Down"]
        self.assertEqual(down, ["u" * 30, "e" * 30])
        self.assertEqual(fixture.addon.Queue.MessageQueue, [])

# -------------------------------------------------------------------------------
class CallMeBotTests(unittest.TestCase):
    """gencallmebot.py"""

    def start(self, **settings):
        self.post = FakePost()
        fixture = AddOnFixture("gencallmebot", "GenCallMeBot", settings,
                               patches=[((requests, "post"), self.post)], loop_in_init=True)
        self.addCleanup(fixture.stop)
        return fixture.start()

    def test_whatsapp(self):
        fixture = self.start(notification_type="WhatsApp", recipient_number="+15551111111",
                             api_key="12345")
        fixture.poll()
        fixture.send_queued()
        url = self.post.calls[0][0]
        self.assertTrue(url.startswith(
            "https://api.callmebot.com/whatsapp.php?phone=+15551111111&apikey=12345&text="), url)
        self.assertEqual(urllib.parse.unquote(url.split("&text=")[1]),
                         "Test Site: Utility Service is Up")
        self.assertEqual(self.post.calls[0][1], {"timeout": 30})

    def test_telegram(self):
        fixture = self.start(notification_type="Telegram", username="@me")
        fixture.poll()
        fixture.send_queued()
        self.assertTrue(self.post.calls[0][0].startswith("http://api.callmebot.com/text.php?user=@me&text="))



# -------------------------------------------------------------------------------
def first_poll_messages(fixture):
    fixture.poll()
    fixture.send_queued()


class Email2SMSTests(unittest.TestCase):
    """genemail2sms.py: an email to the phone company's email to SMS address"""

    def test_email_sent(self):
        sent = []

        class FakeMail(object):
            def __init__(self, **kwargs):
                pass

            def sendEmail(self, subject, message, recipient=None, **kwargs):
                sent.append((subject, message, recipient))

            def Close(self):
                pass

        fixture = AddOnFixture("genemail2sms", "GenEmail2SMS",
                               {"destination": "5551111111@sms.example.com"},
                               patches=[("MyMail", FakeMail)])
        self.addCleanup(fixture.stop)
        fixture.start()
        first_poll_messages(fixture)
        sent.clear()
        fixture.state["outage"] = "Yes"
        fixture.poll()
        # the site name is genmon.conf's sitename, the copy from conf/ is "SiteName"
        self.assertEqual(sent, [("Generator Notice at SiteName", "Utility Service is Down",
                                 "5551111111@sms.example.com")])


class SMSModemTests(unittest.TestCase):
    """gensms_modem.py: SMS from an LTE modem (genmonlib/mymodem.py)"""

    def test_message_sent(self):
        sent = []
        folder = {}

        class FakeModem(object):
            InitComplete = True

            def __init__(self, log=None, loglocation=None, ConfigFilePath=None):
                folder["path"] = ConfigFilePath

            def GetConfig(self):
                from genmonlib.myconfig import MyConfig
                return MyConfig(filename=os.path.join(folder["path"], "mymodem.conf"),
                                section="MyModem")

            def GetInfo(self, ReturnString=False):
                return "fake modem"

            def SendMessage(self, message=None, recipient=None, msgtype="error"):
                sent.append(message)

            def Close(self):
                pass

        # mymodem.py imports the Raspberry Pi GPIO library
        gpio = types.ModuleType("RPi.GPIO")
        rpi = types.ModuleType("RPi")
        rpi.GPIO = gpio
        fixture = AddOnFixture("gensms_modem", "GenSMSModem", {"notify_info": "False"},
                               modules={"RPi": rpi, "RPi.GPIO": gpio},
                               patches=[("LTEPiHat", FakeModem)])
        self.addCleanup(fixture.stop)
        fixture.start()
        first_poll_messages(fixture)
        # notify_info in mymodem.conf is off: no generator state messages
        self.assertNotIn("Generator Ready", " ".join(sent))
        sent.clear()
        fixture.state["outage"] = "Yes"
        fixture.poll()
        self.assertEqual(sent, ["Utility Service is Down"])


class VoipTests(unittest.TestCase):
    """gensms_voip.py: SMS from voip.ms (genmonlib/myvoipms.py)"""

    def setUp(self):
        self.sent = []
        self.fail_once = set()
        sent, fail_once = self.sent, self.fail_once

        class FakeVoip(object):
            def __init__(self, **kwargs):
                pass

            def SendSMS(self, destination, message):
                if destination in fail_once:
                    fail_once.discard(destination)
                    return False
                sent.append((destination, message))
                return True

        self.fixture = AddOnFixture("gensms_voip", "GenSMSVoip", {
            "username": "me@example.com", "password": "pw", "did": "555-000-0000",
            "destination": "+1-555-111-1111, 5552222222"}, patches=[("MyVoipMs", FakeVoip)])
        self.addCleanup(self.fixture.stop)
        self.fixture.start()

    def test_sent_to_each_number(self):
        first_poll_messages(self.fixture)
        up = [s[0] for s in self.sent if s[1] == "Test Site: Utility Service is Up"]
        self.assertEqual(up, [15551111111, 5552222222])

    def test_retry_only_to_numbers_that_failed(self):
        first_poll_messages(self.fixture)
        self.sent.clear()
        self.fail_once.add(5552222222)
        self.fixture.state["outage"] = "Yes"
        self.fixture.poll()
        self.fixture.send_queued()
        self.fixture.send_queued()
        down = [s[0] for s in self.sent if s[1] == "Test Site: Utility Service is Down"]
        self.assertEqual(down, [15551111111, 5552222222])
        self.assertEqual(self.fixture.addon.Queue.MessageQueue, [])


class SyslogTests(unittest.TestCase):
    """gensyslog.py: messages to the system log"""

    def test_logged(self):
        logged = []
        fake_syslog = types.SimpleNamespace(
            openlog=lambda ident: logged.append(("open", ident)),
            syslog=lambda message: logged.append(("log", message)),
            closelog=lambda: logged.append(("close",)))
        fixture = AddOnFixture("gensyslog", "GenSyslog", {}, patches=[("syslog", fake_syslog)])
        self.addCleanup(fixture.stop)
        fixture.start()
        first_poll_messages(fixture)
        logged.clear()
        fixture.state["base"] = "RUNNING"
        fixture.poll()
        self.assertIn(("open", "genmon"), logged)
        self.assertIn(("log", "Generator Running"), logged)
        self.assertEqual(logged[-1], ("close",))


if __name__ == "__main__":
    unittest.main()
