#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_mymail.py
# PURPOSE: Tests for genmonlib/mymail.py: reading mymail.conf, who gets which
#          message type, the email genmon sends (headers, text and HTML body,
#          attachments, BCC), how it talks to the SMTP server (SSL, STARTTLS,
#          login), the send queue, the "test email" button, and email commands
#          read over IMAP.
#
#          smtplib and imaplib are replaced by fakes, so nothing is sent or read.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_mymail
#
# -------------------------------------------------------------------------------

import email
import logging
import os
import shutil
import sys
import tempfile
import ssl
import unittest
from email import policy
from unittest import mock

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_DIR)

from genmonlib import mymail
from genmonlib.mymail import MyMail

LOG = logging.getLogger("test_mymail")
LOG.addHandler(logging.NullHandler())
LOG.propagate = False


# -------------------------------------------------------------------------------
class FakeSMTP(object):
    """Records what genmon does with smtplib.SMTP / SMTP_SSL."""

    sessions = []
    fail_on = None  # "connect", "cert", "login" or "sendmail"

    def __init__(self, server, port, context=None):
        if FakeSMTP.fail_on == "connect":
            raise OSError("connection refused")
        if FakeSMTP.fail_on == "cert":
            raise ssl.SSLCertVerificationError(
                "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate")
        self.server, self.port, self.calls, self.sent = server, port, [], []
        self.context = context
        self.ssl = context is not None and type(self).__name__ == "FakeSMTP_SSL"
        FakeSMTP.sessions.append(self)

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self, context=None):
        self.calls.append("starttls")
        self.context = context

    def login(self, user, password):
        self.calls.append(("login", user, password))
        if FakeSMTP.fail_on == "login":
            raise OSError("bad password")

    def sendmail(self, sender, recipients, message):
        self.calls.append("sendmail")
        if FakeSMTP.fail_on == "sendmail":
            raise OSError("recipient refused")
        self.sent.append((sender, recipients, message))

    def quit(self):
        self.calls.append("quit")


class FakeSMTP_SSL(FakeSMTP):
    pass


def parse(message_bytes):
    return email.message_from_bytes(message_bytes, policy=policy.default)


def text_part(message, subtype="plain"):
    for part in message.walk():
        if part.get_content_type() == "text/" + subtype:
            return part.get_content()
    return None


# -------------------------------------------------------------------------------
class MailTestCase(unittest.TestCase):

    CONF = {
        "disableemail": "False",
        "disablesmtp": "False",
        "disableimap": "True",
        "email_account": "account@example.com",
        "email_pw": "secret",
        "sender_account": "genmon@example.com",
        "sender_name": "My Generator",
        "email_recipient": "all@example.com,outage@example.com,errors@example.com",
        "outage@example.com": "outage",
        "errors@example.com": "error,warn",
        "smtp_server": "smtp.example.com",
        "smtp_port": "587",
        "ssl_enabled": "False",
        "tls_disable": "False",
        "use_html": "False",
        "usebcc": "False",
        "imap_server": "",
    }

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="mymail_test_") + os.sep
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        FakeSMTP.sessions = []
        FakeSMTP.fail_on = None
        for name, fake in [("SMTP", FakeSMTP), ("SMTP_SSL", FakeSMTP_SSL)]:
            patcher = mock.patch.object(mymail.smtplib, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def make_mail(self, **settings):
        conf = dict(self.CONF)
        conf.update(settings)
        with open(os.path.join(self.folder, "mymail.conf"), "w") as f:
            f.write("[MyMail]\n")
            for key, value in conf.items():
                f.write("%s = %s\n" % (key, value))
        mail = MyMail(ConfigFilePath=self.folder, log=LOG, start=False)
        self.addCleanup(mail.Close)
        return mail

    def sent(self, index=-1):
        sender, recipients, message = FakeSMTP.sessions[index].sent[-1]
        return sender, recipients, parse(message)


# -------------------------------------------------------------------------------
class ConfigTests(MailTestCase):

    def test_settings_read(self):
        mail = self.make_mail(smtp_port="2525", ssl_enabled="True", use_html="True")
        self.assertEqual(mail.SMTPServer, "smtp.example.com")
        self.assertEqual(mail.SMTPPort, 2525)
        self.assertTrue(mail.SSLEnabled)
        self.assertTrue(mail.UseHTML)
        self.assertEqual(mail.SenderAccount, "genmon@example.com")

    def test_sender_defaults_to_account(self):
        mail = self.make_mail(sender_account="")
        self.assertEqual(mail.SenderAccount, "account@example.com")

    def test_recipients_by_message_type(self):
        # an address with no categories gets every type
        mail = self.make_mail()
        self.assertEqual(mail.GetRecipientByType("outage", None),
                         "all@example.com,outage@example.com")
        self.assertEqual(mail.GetRecipientByType("error", None), "all@example.com,errors@example.com")
        self.assertEqual(mail.GetRecipientByType("warn", None), "all@example.com,errors@example.com")
        self.assertEqual(mail.GetRecipientByType("info", None), "all@example.com")
        # a recipient given by the caller is used as it is
        self.assertEqual(mail.GetRecipientByType("info", "x@example.com"), "x@example.com")

    def test_fuel_recipients(self):
        # low fuel warnings have their own category (before 2.0.3 they were "warn")
        mail = self.make_mail(email_recipient="all@example.com,fuel@example.com,warn@example.com",
                              **{"fuel@example.com": "fuel", "warn@example.com": "warn"})
        self.assertEqual(mail.GetRecipientByType("fuel", None), "all@example.com,fuel@example.com")
        self.assertEqual(mail.GetRecipientByType("warn", None), "all@example.com,warn@example.com")

    def test_software_update_recipients(self):
        mail = self.make_mail(email_recipient="all@example.com,updates@example.com,info@example.com",
                              **{"updates@example.com": "software_update", "info@example.com": "info"})
        self.assertEqual(mail.GetRecipientByType("software_update", None),
                         "all@example.com,updates@example.com")
        self.assertEqual(mail.GetRecipientByType("info", None), "all@example.com,info@example.com")

    def test_no_recipient_for_a_type(self):
        mail = self.make_mail(email_recipient="outage@example.com")
        self.assertIsNone(mail.GetRecipientByType("info", None))

    def test_disable_email(self):
        mail = self.make_mail(disableemail="True")
        mail.sendEmail("subject", "body")
        self.assertEqual(mail.EmailSendQueue, [])
        self.assertNotIn("SendMailThread", mail.Threads)

    def test_disable_smtp(self):
        mail = self.make_mail(disablesmtp="True")
        mail.sendEmail("subject", "body")
        self.assertEqual(mail.EmailSendQueue, [])


# -------------------------------------------------------------------------------
class SendTests(MailTestCase):

    def test_send_plain_text(self):
        mail = self.make_mail()
        self.assertTrue(mail.sendEmailDirectMIME("outage", "Power out", "Utility : 0 V\n"))
        session = FakeSMTP.sessions[-1]
        self.assertEqual((session.server, session.port), ("smtp.example.com", 587))
        self.assertEqual(session.calls, ["starttls", "ehlo", ("login", "account@example.com", "secret"),
                                         "sendmail", "quit"])
        sender, recipients, message = self.sent()
        self.assertEqual(sender, "genmon@example.com")
        self.assertEqual(recipients, ["<all@example.com>", "<outage@example.com>"])
        self.assertEqual(message["From"], "My Generator <genmon@example.com>")
        self.assertEqual(message["To"], "all@example.com, outage@example.com")
        self.assertEqual(message["Subject"], "Power out")
        self.assertIsNone(message["Bcc"])
        body = text_part(message)
        self.assertIn("Utility : 0 V", body)
        self.assertRegex(body, r"Time: \d\d:\d\d:\d\d [AP]M")
        self.assertIsNone(text_part(message, "html"))

    def test_one_recipient(self):
        mail = self.make_mail(email_recipient="only@example.com")
        mail.sendEmailDirectMIME("info", "subject", "body")
        self.assertEqual(self.sent()[1], "<only@example.com>")

    def test_no_recipient_sends_nothing(self):
        mail = self.make_mail(email_recipient="outage@example.com")
        self.assertTrue(mail.sendEmailDirectMIME("info", "subject", "body"))
        self.assertEqual(FakeSMTP.sessions, [])

    def test_bcc(self):
        mail = self.make_mail(usebcc="True")
        mail.sendEmailDirectMIME("outage", "subject", "body")
        message = self.sent()[2]
        self.assertIsNone(message["To"])
        self.assertEqual(message["Bcc"], "all@example.com, outage@example.com")

    def test_html(self):
        mail = self.make_mail(use_html="True")
        mail.sendEmailDirectMIME("info", "subject", "Status :\nEngine : Off\nLink : https://x.example\n")
        message = self.sent()[2]
        self.assertIn("Engine : Off", text_part(message))
        html = text_part(message, "html")
        self.assertIn("<h2", html)
        self.assertIn(">Engine</th>", html)
        self.assertIn(">Off</td>", html)
        # the text is still sent for mail programs that do not show HTML
        self.assertEqual(len([p for p in message.walk() if p.get_content_maintype() == "text"]), 2)

    def test_force_text(self):
        mail = self.make_mail(use_html="True")
        mail.sendEmailDirectMIME("info", "subject", "body", force_text=True)
        self.assertIsNone(text_part(self.sent()[2], "html"))

    def test_attachment(self):
        mail = self.make_mail()
        path = os.path.join(self.folder, "registers.txt")
        with open(path, "w") as f:
            f.write("register data")
        mail.sendEmailDirectMIME("info", "subject", "body", files=[path], deletefile=True)
        attachments = [p for p in self.sent()[2].walk() if p.get_filename()]
        self.assertEqual([p.get_filename() for p in attachments], ["registers.txt"])
        self.assertEqual(attachments[0].get_content(), b"register data")
        self.assertFalse(os.path.exists(path))

    def test_missing_attachment_still_sends(self):
        mail = self.make_mail()
        self.assertTrue(mail.sendEmailDirectMIME("info", "subject", "body",
                                                 files=[os.path.join(self.folder, "nofile")]))
        self.assertEqual(len(FakeSMTP.sessions[-1].sent), 1)

    def test_ssl(self):
        mail = self.make_mail(ssl_enabled="True", smtp_port="465")
        mail.sendEmailDirectMIME("info", "subject", "body")
        session = FakeSMTP.sessions[-1]
        self.assertIsInstance(session, FakeSMTP_SSL)
        self.assertEqual(session.port, 465)
        self.assertNotIn("starttls", session.calls)

    def test_tls_disabled(self):
        mail = self.make_mail(tls_disable="True")
        mail.sendEmailDirectMIME("info", "subject", "body")
        self.assertNotIn("starttls", FakeSMTP.sessions[-1].calls)

    def test_server_certificate(self):
        # checked by default; ssl_verify_cert = False accepts a self signed
        # certificate (SSL and STARTTLS)
        for settings, verify in [({}, True), ({"ssl_verify_cert": "False"}, False),
                                 ({"ssl_enabled": "True", "ssl_verify_cert": "False"}, False)]:
            with self.subTest(settings=settings):
                mail = self.make_mail(**settings)
                mail.sendEmailDirectMIME("info", "subject", "body")
                context = FakeSMTP.sessions[-1].context
                self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED if verify else ssl.CERT_NONE)
                self.assertEqual(context.check_hostname, verify)

    def test_no_login(self):
        for settings in [{"smtpauth_disable": "True"}, {"email_pw": ""}]:
            with self.subTest(settings=settings):
                FakeSMTP.sessions = []
                mail = self.make_mail(**settings)
                mail.sendEmailDirectMIME("info", "subject", "body")
                self.assertFalse([c for c in FakeSMTP.sessions[-1].calls if c[0] == "login"])

    def test_international_domain(self):
        self.assertEqual(MyMail.FilterAddress(" me@bücher.example "), "me@xn--bcher-kva.example")
        self.assertEqual(MyMail.FilterAddress(["a@bücher.example", "b@example.com"]),
                         ["a@xn--bcher-kva.example", "b@example.com"])

    def test_send_failures(self):
        for fail_on in ["connect", "login", "sendmail"]:
            with self.subTest(fail_on=fail_on):
                FakeSMTP.sessions = []
                mail = self.make_mail()
                FakeSMTP.fail_on = fail_on
                self.assertFalse(mail.sendEmailDirectMIME("info", "subject", "body"))
                if fail_on != "connect":
                    self.assertEqual(FakeSMTP.sessions[-1].calls[-1], "quit")
                FakeSMTP.fail_on = None


# -------------------------------------------------------------------------------
class QueueTests(MailTestCase):

    def test_queue_is_first_in_first_out(self):
        mail = self.make_mail()
        for n in range(3):
            mail.sendEmail("subject %d" % n, "body", msgtype="outage")
        # SendMailThread takes from the end of the list
        self.assertEqual([mail.EmailSendQueue.pop()[1] for _ in range(3)],
                         ["subject 0", "subject 1", "subject 2"])

    def test_send_thread_sends_the_queue(self):
        mail = self.make_mail()
        mail.sendEmail("first", "body", msgtype="outage")
        mail.sendEmail("second", "body", msgtype="outage")
        with mock.patch.object(mail, "WaitForExit", return_value=True), \
                mock.patch.object(mymail.time, "sleep"):
            mail.SendMailThread()
        self.assertEqual([parse(s.sent[0][2])["Subject"] for s in FakeSMTP.sessions],
                         ["first", "second"])
        self.assertEqual(mail.EmailSendQueue, [])

    def test_failed_email_is_kept_to_retry(self):
        mail = self.make_mail()
        mail.sendEmail("subject", "body", msgtype="outage")
        FakeSMTP.fail_on = "sendmail"
        with mock.patch.object(mail, "WaitForExit", return_value=True), \
                mock.patch.object(mymail.time, "sleep"):
            mail.SendMailThread()
        self.assertEqual([item[1] for item in mail.EmailSendQueue], ["subject"])


# -------------------------------------------------------------------------------
class TestEmailTests(MailTestCase):
    """The "send test email" button on the Settings page."""

    SETTINGS = dict(smtp_server="smtp.example.com", smtp_port=587, email_account="me@example.com",
                    sender_account="genmon@example.com", sender_name="Gen",
                    recipient="you@example.com", password="pw", use_ssl=False, tls_disable=False,
                    smtpauth_disable=False)

    def test_success(self):
        self.assertEqual(MyMail.TestSendSettings(**self.SETTINGS), "Success")
        session = FakeSMTP.sessions[-1]
        self.assertIn(("login", "me@example.com", "pw"), session.calls)
        message = parse(session.sent[-1][2])
        self.assertEqual(message["Subject"], "Genmon Test Email")
        self.assertEqual(message["From"], "Gen <genmon@example.com>")
        self.assertIn("Test email from genmon", text_part(message))

    def test_html(self):
        MyMail.TestSendSettings(use_html=True, **self.SETTINGS)
        self.assertIsNotNone(text_part(parse(FakeSMTP.sessions[-1].sent[-1][2]), "html"))

    def test_invalid_settings(self):
        for change, error in [({"smtp_server": ""}, "Invalid SMTP server"),
                              ({"recipient": ""}, "Invalid email recipient"),
                              ({"smtp_port": "587"}, "Invalid SMTP port"),
                              ({"use_ssl": "no"}, "Invalid Use SSL value"),
                              ({"tls_disable": "no"}, "Invalid TLS Disable value")]:
            with self.subTest(change=change):
                settings = dict(self.SETTINGS, **change)
                self.assertIn(error, MyMail.TestSendSettings(**settings))
        self.assertEqual(FakeSMTP.sessions, [])

    def test_server_certificate(self):
        MyMail.TestSendSettings(**self.SETTINGS)
        self.assertEqual(FakeSMTP.sessions[-1].context.verify_mode, ssl.CERT_REQUIRED)
        MyMail.TestSendSettings(verify_cert=False, **self.SETTINGS)
        self.assertEqual(FakeSMTP.sessions[-1].context.verify_mode, ssl.CERT_NONE)
        self.assertIn("Invalid Verify Server Certificate value",
                      MyMail.TestSendSettings(verify_cert="no", **self.SETTINGS))

    def test_certificate_error_hint(self):
        # a self signed certificate: the error says which setting to change
        FakeSMTP.fail_on = "cert"
        message = MyMail.TestSendSettings(**self.SETTINGS)
        self.assertIn("CERTIFICATE_VERIFY_FAILED", message)
        self.assertIn("turn off Verify Server Certificate", message)

    def test_server_error_is_reported(self):
        FakeSMTP.fail_on = "login"
        self.assertEqual(MyMail.TestSendSettings(**self.SETTINGS), "Error sending email: bad password")


# -------------------------------------------------------------------------------
class ConvertTextToHTMLTests(unittest.TestCase):

    def test_layout(self):
        html = MyMail.ConvertTextToHTML(
            "Status :\nEngine State : Running <test>\n\nhttps://example.com/x\nplain line")
        self.assertIn(">Status</h2>", html)
        self.assertIn('<th scope="row"', html)
        self.assertIn(">Engine State</th>", html)
        self.assertIn(">Running &lt;test&gt;</td>", html)
        self.assertIn('><a href="https://example.com/x">https://example.com/x</a></p>', html)
        self.assertIn(">plain line</p>", html)
        self.assertTrue(html.startswith("<!DOCTYPE html>"))

    def test_empty(self):
        self.assertIn("<p></p>", MyMail.ConvertTextToHTML(None))

    def test_links(self):
        # a value that is an http(s) address is a link (e.g. the change log in
        # the software update email); other text and other schemes are not
        html = MyMail.ConvertTextToHTML(
            "Change Log: https://github.com/jgyates/genmon/blob/master/changelog.md\n"
            "Web Interface URL : http://192.0.2.1:8000/?a=1&b=\"2\"\n"
            "Script : javascript:alert(1)\n"
            "Note : see https://example.com for more")
        self.assertIn('<a href="https://github.com/jgyates/genmon/blob/master/changelog.md">'
                      'https://github.com/jgyates/genmon/blob/master/changelog.md</a></td>', html)
        self.assertIn('<a href="http://192.0.2.1:8000/?a=1&amp;b=&quot;2&quot;">', html)
        self.assertNotIn("javascript:alert(1)</a>", html)
        self.assertIn(">see https://example.com for more</td>", html)
        self.assertEqual(html.count("<a "), 2)


# -------------------------------------------------------------------------------
class FakeIMAP(object):
    """A mailbox with messages; like a real server, expunge renumbers them."""

    def __init__(self, messages):
        self.messages = list(messages)  # raw message bytes, sequence number = index + 1
        self.deleted = set()
        self.copied = []

    def login(self, user, password):
        return "OK", [b""]

    def select(self, folder):
        return "OK", [str(len(self.messages)).encode()]

    def search(self, charset, criteria):
        numbers = [n for n in range(len(self.messages))
                   if criteria != "UNDELETED" or n not in self.deleted]
        return "OK", [" ".join(str(n + 1) for n in numbers).encode()]

    def fetch(self, num, parts):
        index = int(num) - 1
        if index >= len(self.messages):
            return "OK", [None]
        return "OK", [(b"1 (RFC822)", self.messages[index])]

    def copy(self, num, folder):
        self.copied.append(self.messages[int(num) - 1])
        return "OK", [b""]

    def store(self, num, flags, value):
        self.deleted.add(int(num) - 1)
        return "OK", [b""]

    def expunge(self):
        self.messages = [m for i, m in enumerate(self.messages) if i not in self.deleted]
        self.deleted = set()
        return "OK", [b""]

    def close(self):
        pass

    def logout(self):
        pass


def raw_message(subject):
    return ("From: me@example.com\r\nTo: genmon@example.com\r\nSubject: %s\r\n\r\nbody\r\n"
            % subject).encode()


class EmailCommandTests(MailTestCase):
    """Commands sent to genmon by email (IMAP), e.g. a subject "generator: status"."""

    def read_mailbox(self, imap):
        received = []
        mail = self.make_mail(disableimap="False", imap_server="imap.example.com")
        mail.Monitor = True
        mail.IncomingFolder, mail.ProcessedFolder = "Generator", "Generator/Processed"
        mail.IncomingCallback = received.append
        with mock.patch.object(mymail.imaplib, "IMAP4_SSL", return_value=imap), \
                mock.patch.object(mail, "WaitForExit", return_value=True):
            mail.EmailCommandThread()
        return received

    def test_command_read_and_moved(self):
        imap = FakeIMAP([raw_message("generator: status")])
        self.assertEqual(self.read_mailbox(imap), ["generator: status"])
        self.assertEqual(len(imap.copied), 1)
        self.assertEqual(imap.messages, [])


    def test_several_commands_at_once(self):
        # the messages are numbered by position; deleting one renumbers the rest,
        # so they are all deleted together after they are read
        imap = FakeIMAP([raw_message("generator: status"), raw_message("generator: outage"),
                         raw_message("generator: maint")])
        self.assertEqual(self.read_mailbox(imap),
                         ["generator: status", "generator: outage", "generator: maint"])
        self.assertEqual(len(imap.copied), 3)
        self.assertEqual(imap.messages, [])

    def test_command_not_repeated_after_an_error(self):
        # an error part way through: the commands already done are not run again
        imap = FakeIMAP([raw_message("generator: status"), raw_message("generator: outage")])
        received = []
        mail = self.make_mail(disableimap="False", imap_server="imap.example.com")
        mail.Monitor = True
        mail.IncomingFolder, mail.ProcessedFolder = "Generator", "Generator/Processed"

        def callback(subject):
            received.append(subject)
            if subject == "generator: outage" and received.count(subject) == 1:
                raise RuntimeError("test error")

        mail.IncomingCallback = callback
        # wait after the error, wait before reconnecting, then stop after the next pass
        waits = iter([False, False, True])
        with mock.patch.object(mymail.imaplib, "IMAP4_SSL", return_value=imap), \
                mock.patch.object(mail, "WaitForExit", side_effect=lambda *a: next(waits, True)):
            mail.EmailCommandThread()
        self.assertEqual(received, ["generator: status", "generator: outage", "generator: outage"])
        self.assertEqual(imap.messages, [])

    def test_empty_mailbox(self):
        imap = FakeIMAP([])
        self.assertEqual(self.read_mailbox(imap), [])

if __name__ == "__main__":
    unittest.main()
