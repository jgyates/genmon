#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_genserv_settings.py
# PURPOSE: Tests for the genserv.py settings pages and maintenance commands:
#          what each save writes to the config files, what the pages read back,
#          and which scripts the maintenance commands run.
#
#          SnapshotTests compares everything the settings pages send to the
#          browser, and every config file change a fixed set of saves makes
#          (and what the pages show afterwards), with
#          tests/data/genserv_snapshot.json. It is the check that a change
#          to how genserv handles settings did not change what the browser sees
#          or what is written to the config files.
#
#          The snapshot also changes when a setting is added or changed on
#          purpose (in genserv.py or in conf/*.conf). Then check the
#          differences the test prints, and if they are what you expected, make
#          a new snapshot:
#              GENSERV_UPDATE_SNAPSHOT=1 python3 -m unittest tests.test_genserv_settings
#
#          genserv runs with a fake genmon connection and no shell scripts are
#          run, see genserv_fixture.py.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_genserv_settings
#
# -------------------------------------------------------------------------------

import difflib
import glob
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import genserv_fixture
from genserv_fixture import GenServFixture

SNAPSHOT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "genserv_snapshot.json")

# pages the snapshot records
SNAPSHOT_PAGES = ["settings", "get_advanced_settings", "get_add_on_settings", "notifications", "get_ui_prefs"]

# saves the snapshot records, in order: (command, value sent by the browser)
SNAPSHOT_SAVES = [
    ("setsettings", "sitename=SnapshotSite&displayunknown=true&nominalfrequency=50"),
    ("set_advanced_settings", "address=64&kwlogmax=2.0"),
    ("set_add_on_settings", json.dumps({
        "genlog": {"enable": "true", "parameters": {"filename": "/home/pi/snapshot.csv"}},
        "genslack": {"enable": "false", "parameters": {
            "channel": "snapshot", "webhook_url": "https://hooks.slack.com/x"}},
        "gensms_voip": {"enable": "true", "parameters": {"did": "555-1234"}},
    })),
    ("setnotifications", "a@example.com=outage,info&b@example.com=error"),
    ("set_ui_prefs", json.dumps({"theme": "light"})),
]

# genhalink / genhubitat make a random API key when none is set
UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

MISSING_LIBRARIES_PATTERN = re.compile(r"<br/><font color='red'>The required libraries[^<]*</font>")

SNAPSHOT_HINT = ("differs from tests/data/genserv_snapshot.json; if this change is intended, "
                 "make a new snapshot with GENSERV_UPDATE_SNAPSHOT=1")

RESTART = "SHELL /bin/bash <RUN>/startgenmon.sh restart -c <CONF>/"


# -------------------------------------------------------------------------------
class SettingsTestCase(unittest.TestCase):
    """Each test gets its own genserv and its own copy of conf/."""

    def setUp(self):
        self.fixture = GenServFixture("open").start()

    def tearDown(self):
        self.fixture.stop()

    def save(self, command, value):
        r = self.fixture.post_cmd(command, {command: value})
        self.assertEqual(r.status_code, 200)
        return r

    def setting(self, page, key):
        # the value shown on a settings page (4th item of the setting's list)
        return self.fixture.get_json("/cmd/" + page)[key][3]


# -------------------------------------------------------------------------------
class SaveTests(SettingsTestCase):
    def test_settings(self):
        self.save("setsettings", "sitename=TestSite2&displayunknown=true&nominalfrequency=50")
        self.assertEqual(self.fixture.conf_value("genmon.conf", "sitename", "GenMon"), "TestSite2")
        self.assertEqual(self.fixture.conf_value("genmon.conf", "displayunknown", "GenMon"), "true")
        self.assertEqual(self.fixture.conf_value("genmon.conf", "nominalfrequency", "GenMon"), "50")
        self.assertEqual(self.setting("settings", "sitename"), "TestSite2")
        self.assertIn(RESTART, self.fixture.shell_calls())

    def test_advanced_settings(self):
        self.save("set_advanced_settings", "address=64")
        self.assertEqual(self.fixture.conf_value("genmon.conf", "address", "GenMon"), "64")
        self.assertEqual(self.setting("get_advanced_settings", "address"), "64")
        self.assertIn(RESTART, self.fixture.shell_calls())

    def test_advanced_settings_read_back(self):
        # every advanced setting is read from the config entry it is saved to
        for key, item in self.fixture.get_json("/cmd/get_advanced_settings").items():
            with self.subTest(setting=key):
                self.assertEqual(item[8], key)
        self.save("set_advanced_settings", "max_powerlog_entries=5000")
        self.assertEqual(self.fixture.conf_value("genmon.conf", "max_powerlog_entries", "GenMon"),
                         "5000")
        self.assertEqual(self.setting("get_advanced_settings", "max_powerlog_entries"), 5000)

    def test_add_on_settings(self):
        self.save("set_add_on_settings", json.dumps({
            "genlog": {"enable": "true", "parameters": {"filename": "/home/pi/test.csv"}},
            "genslack": {"enable": "false", "parameters": {"channel": "testchannel"}},
        }))
        # enable is in genloader.conf, the parameters in the add-on's config file
        self.assertEqual(self.fixture.conf_value("genloader.conf", "enable", "genlog"), "true")
        self.assertEqual(self.fixture.conf_value("genlog.conf", "filename", "genlog"), "/home/pi/test.csv")
        self.assertEqual(self.fixture.conf_value("genloader.conf", "args", "genlog"), "")
        self.assertEqual(self.fixture.conf_value("genloader.conf", "enable", "genslack"), "false")
        self.assertEqual(self.fixture.conf_value("genslack.conf", "channel", "genslack"), "testchannel")
        addons = self.fixture.get_json("/cmd/get_add_on_settings")
        self.assertTrue(addons["genlog"]["enable"])
        self.assertEqual(addons["genlog"]["parameters"]["filename"]["value"], "/home/pi/test.csv")
        self.assertIn(RESTART, self.fixture.shell_calls())

    def test_add_on_save_only_writes_table_parameters(self):
        files = ["genmon.conf", "mymail.conf", "genloader.conf", "genslack.conf", "genhalink.conf"]
        before = {name: self.fixture.read_conf(name) for name in files}
        self.save("set_add_on_settings", json.dumps({
            # a parameter not in the table, a read only one, and a new line in a value
            "genslack": {"parameters": {"no_such_parameter": "1", "username": "a\nenable = true"}},
            "genhalink": {"parameters": {"api_key": "changed"}},
            # not add-ons
            "genmon": {"parameters": {"http_pass": "x"}},
            "mymail": {"parameters": {"email_pw": "x"}},
            "genloader": {"enable": "true"},
            "no_such_addon": {"enable": "true"},
            # enable is true or false only
            "gensms": {"enable": "true\nmodule = other.py"},
        }))
        for name in files:
            with self.subTest(file=name):
                self.assertEqual(self.fixture.read_conf(name), before[name])
        # a parameter that is in the table is written even if the config file
        # does not have the entry yet
        self.assertIsNone(self.fixture.conf_value("genslack.conf", "title_link", "genslack"))
        self.save("set_add_on_settings", json.dumps(
            {"genslack": {"parameters": {"title_link": "https://example.com"}}}))
        self.assertEqual(self.fixture.conf_value("genslack.conf", "title_link", "genslack"),
                         "https://example.com")

    def test_missing_add_on_config_file(self):
        # only that add-on is left off the page, and it can not be saved
        self.fixture.stop()
        self.fixture = GenServFixture("open", missing_conf=["genslack.conf"]).start()
        page = self.fixture.get_json("/cmd/get_add_on_settings")
        self.assertNotIn("genslack", page)
        self.assertIn("genpushover", page)
        self.save("set_add_on_settings", json.dumps(
            {"genslack": {"enable": "true", "parameters": {"channel": "x"}}}))
        self.assertFalse(os.path.exists(self.fixture.conf_path("genslack.conf")))
        self.assertNotEqual(self.fixture.conf_value("genloader.conf", "enable", "genslack"), "true")

    def test_missing_required_config_file(self):
        self.fixture.stop()
        for name in ["genmon.conf", "mymail.conf", "genloader.conf"]:
            with self.subTest(file=name):
                with self.assertRaises(SystemExit):
                    GenServFixture("open", missing_conf=[name]).start()
        self.fixture = GenServFixture("open").start()

    def test_notifications(self):
        self.save("setnotifications", "a@example.com=outage,info&b@example.com=error")
        self.assertEqual(self.fixture.conf_value("mymail.conf", "email_recipient", "MyMail"),
                         "a@example.com,b@example.com")
        self.assertEqual(self.fixture.get_json("/cmd/notifications"),
                         {"a@example.com": [1, "outage,info"], "b@example.com": [1, "error"]})

    def test_ui_prefs(self):
        r = self.save("set_ui_prefs", json.dumps({"theme": "light"}))
        self.assertEqual(r.get_data(as_text=True), "OK")
        self.assertEqual(self.fixture.get_json("/cmd/get_ui_prefs"), {"theme": "light"})
        # saved without a restart
        self.assertEqual(self.fixture.shell_calls(), [])

    def test_ui_prefs_not_json(self):
        before = self.fixture.read_conf("genmon.conf")
        r = self.save("set_ui_prefs", "{not json")
        self.assertEqual(r.get_data(as_text=True), "Error: invalid JSON")
        self.assertEqual(self.fixture.read_conf("genmon.conf"), before)

    def test_test_email(self):
        r = self.save("test_email", json.dumps({
            "smtp_server": "smtp.example.com", "smtp_port": "25", "email_account": "a@example.com",
            "sender_account": "", "sender_name": "", "recipient": "b@example.com", "password": "x",
            "use_ssl": "false", "tls_disable": "false", "smtpauth_disable": "true"}))
        self.assertEqual(json.loads(r.get_data(as_text=True)), {"message": "Success"})
        self.assertIn("TestSendSettings smtp.example.com", self.fixture.calls)


# -------------------------------------------------------------------------------
class MaintenanceCommandTests(SettingsTestCase):
    def run_command(self, command):
        r = self.fixture.post_cmd(command)
        self.assertEqual(r.status_code, 200)
        return r

    def test_backup(self):
        r = self.run_command("backup")
        self.assertEqual(r.get_data(), b"test archive")
        self.assertEqual(self.fixture.shell_calls(), ["SHELL /bin/bash <RUN>/genmonmaint.sh -b -c <CONF>/"])

    def test_get_logs(self):
        r = self.run_command("get_logs")
        self.assertEqual(r.get_data(), b"test archive")
        self.assertEqual(self.fixture.shell_calls(), ["SHELL /bin/bash <RUN>/genmonmaint.sh -l <LOG>/"])

    def test_update_software(self):
        r = self.run_command("updatesoftware")
        self.assertEqual(json.loads(r.get_data(as_text=True)), "OK")
        self.assertEqual(self.fixture.shell_calls(), [
            "SHELL /bin/bash <RUN>/genmonmaint.sh -u -n", RESTART])

    def test_restart(self):
        r = self.run_command("restart")
        self.assertEqual(json.loads(r.get_data(as_text=True)), "OK")
        self.assertEqual(self.fixture.shell_calls(), [RESTART])

    def test_reboot(self):
        with self.assertRaises(SystemExit):
            self.fixture.post_cmd("reboot")
        self.assertEqual(self.fixture.shell_calls(), ["RUN sudo reboot"])

    def test_shutdown(self):
        with self.assertRaises(SystemExit):
            self.fixture.post_cmd("shutdown")
        self.assertEqual(self.fixture.shell_calls(), ["RUN sudo shutdown -h"])


# -------------------------------------------------------------------------------
class SettingsTableTests(SettingsTestCase):
    """The settings tables in genmonlib/genservsettings.py."""

    TYPES = ["string", "password", "int", "float", "boolean", "list", "qrcode"]
    # conditions genserv knows (GenServ.SettingShown); an unknown one is never shown
    CONDITIONS = [None, "custom", "evo_nexus", "not_h100", "h100", "h100_pzp", "not_h100_pzp",
                  "nexus", "evo_lc_diesel", "linux", "setgentime", "evo_nexus_name"]

    def check_table(self, table_name, command):
        instance = self.fixture.instance
        table = self.fixture.module_globals[table_name]
        # a key is only in the table twice with different conditions
        self.assertEqual(len(table), len({(s.key, s.when) for s in table}), "duplicate key")
        # the page shows the settings in table order
        page = self.fixture.get_json("/cmd/" + command)
        shown = []
        for s in table:
            if s.key in page and instance.SettingShown(s.when) and s.key not in shown:
                shown.append(s.key)
        self.assertEqual(sorted(page, key=lambda k: page[k][2]), shown)
        for s in table:
            with self.subTest(setting=s.key):
                self.assertIn(s.type, self.TYPES)
                self.assertIn(s.file, ["genmon", "mail", None])
                if s.type == "list":
                    self.assertTrue(instance.SettingValue(s.bounds), "list without choices")
                self.assertIn(s.when, self.CONDITIONS)

    def test_advanced_settings_table(self):
        self.check_table("ADVANCED_SETTINGS", "get_advanced_settings")

    def test_main_settings_table(self):
        self.check_table("MAIN_SETTINGS", "settings")

    def test_settings_shown_for_controller(self):
        # the default test setup is an Evolution controller on Linux that can set the time
        keys = set(self.fixture.get_json("/cmd/settings"))
        self.assertTrue({"enhancedexercise", "synctime", "cert_info", "smtp_server"} <= keys)
        self.assertFalse({"voltageconfiguration", "nominalbattery", "usesensorforfuelgauge"} & keys)
        self.fixture.stop()
        self.fixture = GenServFixture("open", settings={"controllertype": "h_100"}).start()
        page = self.fixture.get_json("/cmd/settings")
        self.assertTrue({"voltageconfiguration", "industrialoutagecheck",
                         "usesensorforfuelgauge"} <= set(page))
        self.assertNotIn("enhancedexercise", page)

    def test_add_ons_table(self):
        globals_ = self.fixture.module_globals
        table = globals_["ADDONS"]
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.assertEqual(len(table), len({a.name for a in table}), "duplicate add-on")
        confs = [a.conf for a in table if a.conf]
        self.assertEqual(len(confs), len(set(confs)), "two add-ons use one config file")
        # the page shows the add-ons in table order
        page = self.fixture.get_json("/cmd/get_add_on_settings")
        self.assertEqual(list(page), [a.name for a in table if a.name in page])
        for a in table:
            with self.subTest(addon=a.name):
                self.assertIn(a.when, self.CONDITIONS)
                for check in a.checks:
                    self.assertIn(check, globals_["ADDON_CHECKS"])
                if a.conf:
                    # genloader copies a missing config file from conf/
                    self.assertTrue(os.path.isfile(os.path.join(repo, "conf", a.conf)), a.conf)
                params = a.params or ()
                self.assertEqual(len(params), len({p.key for p in params}), "duplicate parameter")
                for p in params:
                    self.assertIn(p.type, self.TYPES + ["readonly"])
                    self.assertIn(p.special, [None, "api_key"])
                    if p.type == "list":
                        self.assertTrue(p.bounds, p.key + ": list without choices")
                if a.name in page:
                    shown = page[a.name]["parameters"]
                    self.assertEqual(None if a.params is None else [p.key for p in a.params],
                                     None if shown is None else list(shown))

    def test_add_on_shown_for_controller(self):
        page = self.fixture.get_json("/cmd/get_add_on_settings")
        self.assertIn("genexercise", page)
        self.fixture.stop()
        saved = genserv_fixture.START_INFO
        genserv_fixture.START_INFO = dict(saved, Controller="H-100")
        try:
            self.fixture = GenServFixture("open").start()
            self.assertNotIn("genexercise", self.fixture.get_json("/cmd/get_add_on_settings"))
        finally:
            genserv_fixture.START_INFO = saved

    def test_add_on_api_key_made_when_missing(self):
        page = self.fixture.get_json("/cmd/get_add_on_settings")
        key = page["genhalink"]["parameters"]["api_key"]["value"]
        self.assertRegex(key, r"^[0-9a-f-]{36}$")
        self.assertEqual(self.fixture.conf_value("genhalink.conf", "api_key"), key)
        # the same key next time
        page = self.fixture.get_json("/cmd/get_add_on_settings")
        self.assertEqual(page["genhalink"]["parameters"]["api_key"]["value"], key)

    def test_advanced_settings_shown_for_controller(self):
        # the default test setup is an Evolution controller on Linux
        keys = set(self.fixture.get_json("/cmd/get_advanced_settings"))
        self.assertTrue({"unbalanced_capacity", "usenominallinevolts",
                         "uselinuxwifisignalgauge"} <= keys)
        self.assertFalse({"ignore_alarms", "usecalculatedpower", "nexus_legacy_freq"} & keys)
        self.fixture.stop()
        self.fixture = GenServFixture("open", settings={"controllertype": "h_100"}).start()
        keys = set(self.fixture.get_json("/cmd/get_advanced_settings"))
        self.assertIn("usecalculatedpower", keys)
        self.assertFalse({"unbalanced_capacity", "usenominallinevolts", "ignore_alarms"} & keys)


# -------------------------------------------------------------------------------
class SnapshotTests(SettingsTestCase):
    def normalize(self, text):
        # temporary folders and random keys are different on every run
        for folder, label in [(self.fixture.conf_dir, "<CONF>/"), (self.fixture.run_dir, "<RUN>")]:
            suffix = os.sep if folder.endswith(os.sep) else ""
            for path in [os.path.realpath(folder) + suffix, folder]:
                text = text.replace(path, label)
        text = UUID_PATTERN.sub("<UUID>", text)
        # depends on the machine, not on genserv: an add-on's "libraries are not
        # installed" note, and macOS .DS_Store files in folder listings
        text = MISSING_LIBRARIES_PATTERN.sub("", text)
        return text.replace(".DS_Store,", "").replace(",.DS_Store", "")

    def page(self, command):
        return json.loads(self.normalize(self.fixture.get("/cmd/" + command).get_data(as_text=True)))

    def conf_files(self):
        files = {}
        for path in sorted(glob.glob(os.path.join(self.fixture.conf_dir, "*"))):
            with open(path) as f:
                files[os.path.basename(path)] = self.normalize(f.read()).splitlines()
        return files

    def take_snapshot(self):
        snapshot = {"pages": {}, "saves": [], "config_changes": {}, "pages_after_saves": {}}
        for command in SNAPSHOT_PAGES:
            snapshot["pages"][command] = self.page(command)

        before = self.conf_files()
        for command, value in SNAPSHOT_SAVES:
            calls_before = len(self.fixture.calls)
            r = self.save(command, value)
            snapshot["saves"].append({
                "command": command,
                "reply": r.get_data(as_text=True),
                "calls": self.fixture.calls[calls_before:],
            })
        after = self.conf_files()
        for name in sorted(set(before) | set(after)):
            diff = list(difflib.unified_diff(before.get(name, []), after.get(name, []), lineterm="", n=0))
            if diff:
                # leave out the "---" / "+++" file header lines
                snapshot["config_changes"][name] = diff[2:]
        # only the entries the saves changed (None for an entry that went away)
        for command in SNAPSHOT_PAGES:
            old_page, new_page = snapshot["pages"][command], self.page(command)
            snapshot["pages_after_saves"][command] = {
                key: new_page.get(key) for key in sorted(set(old_page) | set(new_page))
                if old_page.get(key) != new_page.get(key)
            }
        return snapshot

    def test_snapshot(self):
        snapshot = self.take_snapshot()
        if os.environ.get("GENSERV_UPDATE_SNAPSHOT"):
            os.makedirs(os.path.dirname(SNAPSHOT_FILE), exist_ok=True)
            with open(SNAPSHOT_FILE, "w") as f:
                json.dump(snapshot, f, indent=1, sort_keys=True)
                f.write("\n")
            self.skipTest("snapshot written to " + SNAPSHOT_FILE)
        if not os.path.isfile(SNAPSHOT_FILE):
            self.fail("no snapshot, make one with GENSERV_UPDATE_SNAPSHOT=1")
        with open(SNAPSHOT_FILE) as f:
            expected = json.load(f)

        self.maxDiff = None
        # compare entry by entry, so a failure names the setting that changed
        for part in ["pages", "pages_after_saves"]:
            for page in sorted(set(expected[part]) | set(snapshot[part])):
                old_page, new_page = expected[part].get(page, {}), snapshot[part].get(page, {})
                for key in sorted(set(old_page) | set(new_page)):
                    with self.subTest(part=part, page=page, entry=key):
                        self.assertEqual(new_page.get(key), old_page.get(key), SNAPSHOT_HINT)
        for name in sorted(set(expected["config_changes"]) | set(snapshot["config_changes"])):
            with self.subTest(part="config_changes", file=name):
                self.assertEqual(snapshot["config_changes"].get(name), expected["config_changes"].get(name),
                                 SNAPSHOT_HINT)
        with self.subTest(part="saves"):
            self.assertEqual(snapshot["saves"], expected["saves"], SNAPSHOT_HINT)


if __name__ == "__main__":
    unittest.main()
