#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_addon_defaults.py
# PURPOSE: Checks that the Add-Ons page and the add-on programs agree on each
#          add-on parameter: the add-on reads the entry the page saves, and both
#          use the same default when the config file does not have the entry.
#
#          The page's parameters are in the ADDONS table in
#          genmonlib/genservsettings.py. The add-on's reads are found by
#          looking for config.ReadValue("entry", ..., default=...) in
#          addon/<add-on>.py, or in genmonlib/ if the add-on file does not read
#          the entry itself (for example notify_* in mynotify.py).
#
#          If an add-on reads an entry in a way this test can not see (for
#          example a name made at run time), add it to NOT_COMPARED with the
#          reason.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_addon_defaults
#
# -------------------------------------------------------------------------------

import ast
import glob
import os
import sys
import unittest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_DIR)

from genmonlib.genservsettings import ADDONS

# (add-on, entry): why the defaults are not compared
NOT_COMPARED = {
    ("genpushover", "alarm_priority"): "read by GetPriorityFromConf(), default NORMAL",
    ("genpushover", "sw_update_priority"): "read by GetPriorityFromConf(), default NORMAL",
    ("genpushover", "system_health_priority"): "read by GetPriorityFromConf(), default NORMAL",
    ("genpushover", "fuel_priority"): "read by GetPriorityFromConf(), default NORMAL",
    ("genpushover", "outage_priority"): "read by GetPriorityFromConf(), default NORMAL",
    ("genpushover", "switch_state_priority"): "read by GetPriorityFromConf(), default NORMAL",
    ("genpushover", "run_state_priority"): "read by GetPriorityFromConf(), default NORMAL",
    ("genpushover", "service_state_priority"): "read by GetPriorityFromConf(), default NORMAL",
    ("genpushover", "pi_state_priority"): "read by GetPriorityFromConf(), default NORMAL",
    ("genpushover", "extra_notify_error"): 'read as "extra_notify_" + category, default True',
    ("genpushover", "extra_notify_warn"): 'read as "extra_notify_" + category, default True',
    ("genpushover", "extra_notify_info"): 'read as "extra_notify_" + category, default True',
    ("genpushover", "extra_notify_outage"): 'read as "extra_notify_" + category, default True',
    ("genpushover", "extra_notify_sw_update"): 'read as "extra_notify_" + category, default True',
    ("genpushover", "extra_notify_pi_state"): 'read as "extra_notify_" + category, default True',
    ("genmqtt", "flush_interval"): "the add-on treats 0 as no flush, the same as its default inf",
    ("genhomeassistant", "monitor_address"): "empty means the local genmon, the add-on's default",
    ("genhomeassistant", "blacklist"): 'the add-on default is the variable default_blacklist = "Tiles"',
    ("gensms_modem", "recipient"): "mymodem.py uses the recipient passed to MyModem (None)",
}


def find_reads(path):
    # {entry: [(default, line)]} for config.ReadValue("entry", ..., default=...)
    reads = {}
    with open(path) as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "ReadValue"):
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        keywords = {k.arg: k.value for k in node.keywords}
        default = keywords.get("default")
        try:
            value = None if default is None else ast.literal_eval(default)
        except ValueError:
            value = ("expression", ast.unparse(default) if hasattr(ast, "unparse") else "?")
        reads.setdefault(node.args[0].value, []).append((value, node.lineno))
    return reads


def same_default(page, addon):
    if page in ("", None) and addon in ("", None):
        return True  # not set
    if isinstance(page, bool) or isinstance(addon, bool):
        return str(page).lower() == str(addon).lower()
    if isinstance(page, (int, float)) and isinstance(addon, (int, float)):
        return float(page) == float(addon)
    if isinstance(page, str) and isinstance(addon, (int, float)):
        return page == str(addon)  # a list choice, e.g. "1"
    return page == addon


# -------------------------------------------------------------------------------
class AddOnDefaultsTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.lib_reads = {}
        for path in sorted(glob.glob(os.path.join(REPO_DIR, "genmonlib", "*.py"))):
            for key, found in find_reads(path).items():
                for value, line in found:
                    cls.lib_reads.setdefault(key, []).append((value, os.path.basename(path), line))

    def test_add_on_defaults_match_page(self):
        problems = []
        for addon in ADDONS:
            path = os.path.join(REPO_DIR, "addon", addon.name + ".py")
            reads = find_reads(path)
            for param in addon.params or ():
                if param.special or (addon.name, param.key) in NOT_COMPARED:
                    continue
                where = "%s %s (page default %r)" % (addon.name, param.key, param.default)
                if param.key in reads:
                    # every read in the add-on must use the page's default
                    for value, line in reads[param.key]:
                        if not same_default(param.default, value):
                            problems.append("%s: addon/%s.py:%d default %r"
                                            % (where, addon.name, line, value))
                elif param.key in self.lib_reads:
                    # genmonlib: one of the reads must use the page's default
                    found = self.lib_reads[param.key]
                    if not any(same_default(param.default, value) for value, _, _ in found):
                        problems.append("%s: genmonlib defaults %s" % (
                            where, ", ".join("%s:%d %r" % (f, l, v) for v, f, l in found)))
                else:
                    problems.append("%s: not read by the add-on or genmonlib" % where)
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_genloader_template_has_every_add_on(self):
        # genloader starts the add-ons listed in genloader.conf; a new install gets
        # conf/genloader.conf
        import configparser

        template = configparser.RawConfigParser()
        template.read(os.path.join(REPO_DIR, "conf", "genloader.conf"))
        for addon in ADDONS:
            with self.subTest(addon=addon.name):
                self.assertTrue(template.has_section(addon.name))
                self.assertEqual(template.get(addon.name, "module"), addon.name + ".py")
                if addon.conf:
                    self.assertIn(addon.conf, template.get(addon.name, "conffile"))

    def test_not_compared_list_is_current(self):
        params = {(a.name, p.key) for a in ADDONS for p in a.params or ()}
        for entry in NOT_COMPARED:
            with self.subTest(entry=entry):
                self.assertIn(entry, params, "no longer an add-on parameter, remove it")


if __name__ == "__main__":
    unittest.main()
