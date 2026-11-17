#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_genserv_auth.py
# PURPOSE: Tests for the genserv.py login: admin and read only users, the
#          login lockout, multi-factor authentication (MFA) and the local CA
#          certificate downloads.
#
#          genserv runs with a fake genmon connection and fake email, see
#          genserv_fixture.py.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_genserv_auth
#
# -------------------------------------------------------------------------------

import glob
import json
import os
import sys
import re
import unittest

import pyotp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from genserv_fixture import (
    ADMIN_PASS, ADMIN_USER, MFA_SECRET, RO_PASS, RO_USER, GenServFixture,
)

# write commands and the data a browser sends with them
WRITE_COMMANDS = [
    ("setquiet", {"setquiet": "off"}),
    ("setremote", {"setremote": "stop"}),
    ("setexercise", {"setexercise": "Monday,13:00,Weekly"}),
    ("settime", {}),
    ("power_log_clear", {}),
    ("setsettings", {"setsettings": "sitename=ReadOnlySite"}),
    ("set_advanced_settings", {"set_advanced_settings": "address=99"}),
    ("set_add_on_settings", {"set_add_on_settings": json.dumps(
        {"genlog": {"enable": "true", "parameters": {"Log File Name": "/tmp/ro.csv"}}})}),
    ("setnotifications", {"setnotifications": "ro@example.com=outage"}),
    ("set_ui_prefs", {"set_ui_prefs": json.dumps({"theme": "light"})}),
    ("test_email", {"test_email": "{}"}),
    ("backup", {}),
    ("get_logs", {}),
    ("updatesoftware", {}),
    ("restart", {}),
    ("stop", {}),
    ("shutdown", {}),
    ("reboot", {}),
    ("notify_message", {"notify_message": json.dumps({"title": "t", "body": "b", "type": "info"})}),
]

# how genserv refuses a write command for a read only user (the web UI shows
# "Write access required" for both)
DENIED_REPLIES = ["Read Only Mode", "Access denied"]


def otp_code():
    return pyotp.TOTP(MFA_SECRET, interval=30).now()


def reply_text(response):
    return response.get_data(as_text=True).strip().strip('"')


# -------------------------------------------------------------------------------
class LoginTests(unittest.TestCase):
    """Admin and read only users, password only."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = GenServFixture("auth").start()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.stop()

    def setUp(self):
        self.fixture.new_session()

    def conf_files(self):
        files = {}
        for path in sorted(glob.glob(os.path.join(self.fixture.conf_dir, "*"))):
            with open(path, "rb") as f:
                files[os.path.basename(path)] = f.read()
        return files

    def test_redirect_server_requested(self):
        self.assertIn("REDIRECT SERVER", self.fixture.calls)

    def test_login_page_before_login(self):
        before = len(self.fixture.calls)
        for path in ["/", "/cmd/status_json"]:
            with self.subTest(path=path):
                r = self.fixture.get(path)
                self.assertEqual(r.status_code, 200)
                self.assertIn("Genmon &mdash; Login", r.get_data(as_text=True))
        self.assertEqual(self.fixture.calls[before:], [])

    def test_wrong_password(self):
        r = self.fixture.login(ADMIN_USER, "wrong")
        self.assertIn("Genmon &mdash; Login", r.get_data(as_text=True))
        self.assertFalse(self.fixture.is_logged_in())

    def test_admin_login_and_write(self):
        r = self.fixture.login(ADMIN_USER, ADMIN_PASS)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(self.fixture.is_logged_in())
        self.fixture.post_cmd("setquiet", {"setquiet": "off"})
        self.assertIn("generator: setquiet=off", self.fixture.calls)

    def test_logout(self):
        self.fixture.login(ADMIN_USER, ADMIN_PASS)
        self.fixture.logout()
        self.assertFalse(self.fixture.is_logged_in())

    def test_read_only_user_can_read(self):
        r = self.fixture.login(RO_USER, RO_PASS)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(self.fixture.is_logged_in())

    def test_read_only_user_pages(self):
        # the web UI hides the pages a read only user can not use
        self.fixture.login(RO_USER, RO_PASS)
        pages = self.fixture.get_json("/cmd/start_info_json")["pages"]
        for page in ["settings", "notifications", "addons"]:
            with self.subTest(page=page):
                self.assertIs(pages.get(page), False)

    def test_read_only_user_does_not_get_settings(self):
        self.fixture.login(RO_USER, RO_PASS)
        for command in ["settings", "get_advanced_settings", "get_add_on_settings", "notifications"]:
            with self.subTest(command=command):
                self.assertEqual(reply_text(self.fixture.get("/cmd/" + command)), "Access denied")

    def test_read_only_user_cannot_write(self):
        self.fixture.login(RO_USER, RO_PASS)
        conf_before = self.conf_files()
        for command, data in WRITE_COMMANDS:
            with self.subTest(command=command):
                before = len(self.fixture.calls)
                try:
                    r = self.fixture.post_cmd(command, data)
                except SystemExit:
                    self.fail("read only user stopped genserv with " + command)
                self.assertLess(r.status_code, 500)
                self.assertIn(reply_text(r), DENIED_REPLIES)
                new_calls = self.fixture.calls[before:]
                self.assertEqual([c for c in new_calls if c.startswith(("SHELL", "RUN"))], [])
                self.assertEqual([c for c in new_calls if command in c], [])
                self.assertNotIn("TestSendSettings", " ".join(new_calls))
        self.assertEqual(self.conf_files(), conf_before)
        self.assertFalse(self.fixture.instance.Closing)

    def test_read_only_user_refused_every_write_command(self):
        # every command marked write in the command table, so a new one is covered too
        self.fixture.login(RO_USER, RO_PASS)
        conf_before = self.conf_files()
        commands = sorted(n for n, c in self.fixture.instance.COMMANDS.items() if c.write)
        self.assertTrue(commands)
        for command in commands:
            with self.subTest(command=command):
                before = len(self.fixture.calls)
                if command in self.fixture.instance.POST_ONLY_COMMANDS:
                    r = self.fixture.post_cmd(command, {command: "1"})
                else:
                    r = self.fixture.get("/cmd/" + command)
                self.assertIn(reply_text(r), DENIED_REPLIES)
                self.assertEqual(self.fixture.calls[before:], [])
        self.assertEqual(self.conf_files(), conf_before)


# -------------------------------------------------------------------------------
class LockoutTests(unittest.TestCase):
    """Too many wrong passwords lock the login."""

    def setUp(self):
        self.fixture = GenServFixture("auth").start()

    def tearDown(self):
        self.fixture.stop()

    def lock(self):
        r = None
        for _ in range(self.fixture.instance.MaxLoginAttempts + 1):
            r = self.fixture.login(ADMIN_USER, "wrong")
        return r

    def countdown_seconds(self, response):
        match = re.search(r'id="countdown" data-seconds="(\d*)"', response.get_data(as_text=True))
        self.assertIsNotNone(match, "countdown not found on the locked page")
        return int(match.group(1))

    def test_locked_page_counts_down(self):
        r = self.lock()
        self.assertIn("Genmon &mdash; Locked", r.get_data(as_text=True))
        seconds = self.countdown_seconds(r)
        self.assertGreater(seconds, 0)
        self.assertLessEqual(seconds, self.fixture.instance.LockOutDuration)

    def test_right_password_refused_while_locked(self):
        self.lock()
        self.fixture.login(ADMIN_USER, ADMIN_PASS)
        self.assertFalse(self.fixture.is_logged_in())

    def test_locked_route(self):
        self.lock()
        r = self.fixture.get("/locked")
        # this page does not know the time left, so it shows no countdown
        self.assertIn("Genmon &mdash; Locked", r.get_data(as_text=True))
        self.assertIn('data-seconds=""', r.get_data(as_text=True))


# -------------------------------------------------------------------------------
class MFATests(unittest.TestCase):
    """Password, then a code from an authenticator app or an email."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = GenServFixture("auth_mfa").start()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.stop()

    def setUp(self):
        self.fixture.new_session()

    def emails_sent(self):
        return self.fixture.calls.count("sendEmailDirectMIME")

    def mfa(self, code, **extra):
        data = {"code": code}
        data.update(extra)
        return self.fixture.post("/mfa", data=data)

    def test_password_alone_is_not_enough(self):
        r = self.fixture.login(ADMIN_USER, ADMIN_PASS)
        page = self.fixture.get("/").get_data(as_text=True) if r.status_code == 302 else r.get_data(as_text=True)
        self.assertIn("Multi-Factor Authentication", page)
        self.assertFalse(self.fixture.is_logged_in())

    def test_password_and_code(self):
        self.fixture.login(ADMIN_USER, ADMIN_PASS)
        self.mfa(otp_code())
        self.assertTrue(self.fixture.is_logged_in())
        self.fixture.post_cmd("setquiet", {"setquiet": "off"})
        self.assertIn("generator: setquiet=off", self.fixture.calls)

    def test_email_code_during_mfa_step(self):
        self.fixture.login(ADMIN_USER, ADMIN_PASS)
        before = self.emails_sent()
        self.fixture.post("/send_otp", headers=self.fixture.csrf_headers())
        self.assertEqual(self.emails_sent(), before + 1)

    def test_no_email_code_without_password(self):
        before = self.emails_sent()
        self.fixture.post("/send_otp", headers=self.fixture.csrf_headers())
        self.assertEqual(self.emails_sent(), before)

    def test_code_without_password(self):
        self.mfa(otp_code())
        self.assertFalse(self.fixture.is_logged_in())

    def test_code_after_logout(self):
        self.fixture.login(ADMIN_USER, ADMIN_PASS)
        self.mfa(otp_code())
        self.fixture.logout()
        self.mfa(otp_code())
        self.assertFalse(self.fixture.is_logged_in())

    def test_wrong_code_then_right_code(self):
        self.fixture.login(RO_USER, RO_PASS)
        self.mfa("000000")
        self.assertFalse(self.fixture.is_logged_in())
        # the wrong code ended the login, so the password is needed again
        self.mfa(otp_code())
        self.assertFalse(self.fixture.is_logged_in())

    def test_trust_this_browser(self):
        self.fixture.login(ADMIN_USER, ADMIN_PASS)
        self.mfa(otp_code(), trust_browser="on")
        self.assertTrue(self.fixture.is_logged_in())
        self.fixture.logout()
        self.assertFalse(self.fixture.is_logged_in())
        # the same browser now only needs the password
        self.fixture.login(ADMIN_USER, ADMIN_PASS)
        self.assertTrue(self.fixture.is_logged_in())

    def test_read_only_user_stays_read_only(self):
        self.fixture.login(RO_USER, RO_PASS)
        self.mfa(otp_code())
        self.assertTrue(self.fixture.is_logged_in())
        r = self.fixture.post_cmd("setquiet", {"setquiet": "off"})
        self.assertIn(reply_text(r), DENIED_REPLIES)

    def test_ldap_login_needs_code(self):
        from flask import session

        def fake_ldap_login(username, password):
            # sets the session like the real doLdapLogin does
            if username == "ldapuser" and password == "ldappw":
                session["logged_in"] = True
                session["write_access"] = True
                return True
            return False

        instance = self.fixture.instance
        original = instance.__dict__.get("doLdapLogin")
        instance.doLdapLogin = fake_ldap_login
        try:
            self.fixture.login("ldapuser", "ldappw")
            self.assertFalse(self.fixture.is_logged_in())
            self.mfa(otp_code())
            self.assertTrue(self.fixture.is_logged_in())
            self.fixture.post_cmd("setquiet", {"setquiet": "off"})
            self.assertIn("generator: setquiet=off", self.fixture.calls)
        finally:
            if original is None:
                del instance.doLdapLogin
            else:
                instance.doLdapLogin = original


# -------------------------------------------------------------------------------
class LocalCATests(unittest.TestCase):
    """HTTPS with a certificate from genmon's own local CA."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = GenServFixture("auth_localca").start()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.stop()

    def test_ca_certificate_downloads(self):
        from OpenSSL import crypto

        # served without a login, so a browser can import it first
        der = self.fixture.get("/download/ca.crt")
        pem = self.fixture.get("/download/ca.pem")
        imported = self.fixture.get("/import/ca.crt")
        for r in [der, pem, imported]:
            self.assertEqual(r.status_code, 200)
        der_cert = crypto.load_certificate(crypto.FILETYPE_ASN1, der.get_data())
        pem_cert = crypto.load_certificate(crypto.FILETYPE_PEM, pem.get_data())
        self.assertEqual(der_cert.digest("sha256"), pem_cert.digest("sha256"))
        self.assertEqual(imported.get_data(), der.get_data())


if __name__ == "__main__":
    unittest.main()
