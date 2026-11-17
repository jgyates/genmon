#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_genserv_web.py
# PURPOSE: Tests for the genserv.py web server without a login: pages, the
#          /cmd/ commands passed to genmon, the POST / CSRF / cross origin
#          checks, security headers, and genservext.py extensions.
#
#          genserv runs with a fake genmon connection, see genserv_fixture.py.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_genserv_web
#
# -------------------------------------------------------------------------------

import json
import os
import sys
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from genserv_fixture import ADMIN_PASS, ADMIN_USER, GenServFixture

# /cmd/ commands a browser reads with GET
GET_COMMANDS = [
    "status_json", "start_info_json", "csrf_token", "getfavicon", "settings",
    "notifications", "get_add_on_settings", "get_advanced_settings", "get_ui_prefs",
    "getreglabels", "getbase", "gui_status_json", "monitor_json", "getsitename",
]

# an extension like the example in the wiki (Appendix C)
EXTENSION_SOURCE = '''
from __main__ import app, ServePage

@app.route("/testit")
def testit():
    return ServePage("manifest.webmanifest")
'''


# -------------------------------------------------------------------------------
class GenServOpenTests(unittest.TestCase):
    """genserv with no login (the default install)."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = GenServFixture("open").start()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.stop()

    def setUp(self):
        self.fixture.new_session()

    def new_calls(self, before):
        return self.fixture.calls[before:]

    def test_main_page(self):
        r = self.fixture.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("<title>Genmon</title>", r.get_data(as_text=True))

    def test_static_files(self):
        for path in ["/favicon.ico", "/sw.js", "/manifest.webmanifest"]:
            with self.subTest(path=path):
                self.assertEqual(self.fixture.get(path).status_code, 200)

    def test_unknown_page(self):
        self.assertEqual(self.fixture.get("/nonexistent_page").status_code, 404)

    def test_security_headers(self):
        r = self.fixture.get("/")
        self.assertEqual(r.headers.get("X-Frame-Options"), "DENY")
        self.assertIn("frame-ancestors 'none'", r.headers.get("Content-Security-Policy", ""))

    def test_command_passed_to_genmon(self):
        r = self.fixture.get("/cmd/status_json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(json.loads(r.get_data(as_text=True)),
                         {"fake_response_for": "generator: status_json"})

    def test_csrf_token_command(self):
        token = self.fixture.get_json("/cmd/csrf_token")["csrf_token"]
        self.assertEqual({"X-CSRFToken": token}, self.fixture.csrf_headers())

    def test_get_commands_answer(self):
        for command in GET_COMMANDS:
            with self.subTest(command=command):
                r = self.fixture.get("/cmd/" + command)
                self.assertEqual(r.status_code, 200)
                self.assertTrue(r.get_data())

    def test_unknown_command_does_not_fail(self):
        self.assertLess(self.fixture.get("/cmd/bogus_command").status_code, 500)

    def test_post_only_commands_reject_get(self):
        for command in sorted(self.fixture.instance.POST_ONLY_COMMANDS):
            with self.subTest(command=command):
                before = len(self.fixture.calls)
                r = self.fixture.get("/cmd/" + command)
                self.assertEqual(r.status_code, 405)
                self.assertEqual(self.new_calls(before), [])

    def test_post_without_csrf_token_is_refused(self):
        before = len(self.fixture.calls)
        r = self.fixture.post_cmd("setquiet", {"setquiet": "off"}, csrf=False)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.new_calls(before), [])

    def test_post_with_wrong_csrf_token_is_refused(self):
        before = len(self.fixture.calls)
        r = self.fixture.post_cmd("setquiet", {"setquiet": "off"}, csrf=False,
                                  headers={"X-CSRFToken": "not-the-token"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.new_calls(before), [])

    def test_cross_origin_post_is_refused(self):
        before = len(self.fixture.calls)
        r = self.fixture.post_cmd("setquiet", {"setquiet": "off"},
                                  headers={"Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.new_calls(before), [])

    def test_post_command_passed_to_genmon(self):
        r = self.fixture.post_cmd("setquiet", {"setquiet": "off"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("generator: setquiet=off", self.fixture.calls)


# -------------------------------------------------------------------------------
class GenServExtensionTests(unittest.TestCase):
    """A genservext.py extension using "from __main__ import app, ServePage"."""

    @classmethod
    def setUpClass(cls):
        cls.ext_dir = tempfile.mkdtemp(prefix="genservext_")
        ext_file = os.path.join(cls.ext_dir, "genservext.py")
        with open(ext_file, "w") as f:
            f.write(EXTENSION_SOURCE)
        cls.fixture = GenServFixture("auth", extension_file=ext_file).start()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.stop()
        shutil.rmtree(cls.ext_dir, ignore_errors=True)

    def setUp(self):
        self.fixture.new_session()

    def test_extension_page_needs_login(self):
        r = self.fixture.get("/testit")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Login", r.get_data(as_text=True))

    def test_extension_page_after_login(self):
        self.fixture.login(ADMIN_USER, ADMIN_PASS)
        r = self.fixture.get("/testit")
        self.assertEqual(r.status_code, 200)
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "static", "manifest.webmanifest"), "rb") as f:
            self.assertEqual(r.get_data(), f.read())


if __name__ == "__main__":
    unittest.main()
