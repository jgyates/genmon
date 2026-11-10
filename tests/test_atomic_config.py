#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: test_atomic_config.py
# PURPOSE: Unit tests for crash-safe file writes (genmonlib/myfileutil.py) and
#          the MyConfig write paths that use them.
#
# USAGE: from the root of the repository:
#           python -m unittest discover -s tests
#
# -------------------------------------------------------------------------------

import multiprocessing
import os
import shutil
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genmonlib import myfileutil
from genmonlib.myconfig import MyConfig
from genmonlib.myfileutil import AtomicWrite, FileLock

SAMPLE_CONF = """# comment line
[GenMon]
port = /dev/serial0
loglocation = /var/log/

[Other]
key = value
"""


class QuietConfig(MyConfig):
    """MyConfig that records errors instead of needing a logger."""

    def __init__(self, *args, **kwargs):
        self.Errors = []
        super(QuietConfig, self).__init__(*args, **kwargs)

    def LogError(self, Message, Error=None):
        self.Errors.append(Message)

    def LogErrorLine(self, Message, Error=None):
        self.Errors.append(Message)


class AtomicWriteTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "file.json")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_creates_and_replaces(self):
        AtomicWrite(self.path, "first")
        AtomicWrite(self.path, "second")
        with open(self.path) as f:
            self.assertEqual(f.read(), "second")

    def test_bytes(self):
        AtomicWrite(self.path, b"\x00\x01")
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), b"\x00\x01")

    def test_failure_leaves_original_and_no_temp_files(self):
        AtomicWrite(self.path, "original")
        with mock.patch.object(myfileutil.os, "fsync", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                AtomicWrite(self.path, "new contents")
        with open(self.path) as f:
            self.assertEqual(f.read(), "original")
        self.assertEqual(os.listdir(self.dir), ["file.json"])

    def test_explicit_mode(self):
        AtomicWrite(self.path, "secret", mode=0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_preserves_existing_mode(self):
        with open(self.path, "w") as f:
            f.write("x")
        os.chmod(self.path, 0o640)
        AtomicWrite(self.path, "y")
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o640)

    def test_writes_through_symlink(self):
        real = os.path.join(self.dir, "real.conf")
        AtomicWrite(real, "old")
        link = os.path.join(self.dir, "link.conf")
        os.symlink(real, link)
        AtomicWrite(link, "new")
        self.assertTrue(os.path.islink(link))
        with open(real) as f:
            self.assertEqual(f.read(), "new")


class MyConfigWriteTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "genmon.conf")
        with open(self.path, "w") as f:
            f.write(SAMPLE_CONF)
        self.conf = QuietConfig(filename=self.path, section="GenMon")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def read(self):
        with open(self.path) as f:
            return f.read()

    def test_update_existing_value(self):
        self.assertTrue(self.conf.WriteValue("port", "/dev/ttyUSB0"))
        self.assertIn("port = /dev/ttyUSB0\n", self.read())
        self.assertIn("# comment line\n", self.read())
        self.assertEqual(self.conf.ReadValue("port"), "/dev/ttyUSB0")

    def test_add_value_to_section(self):
        self.assertTrue(self.conf.WriteValue("newkey", "1"))
        text = self.read()
        # added at the end of [GenMon], before [Other]
        self.assertLess(text.index("newkey = 1"), text.index("[Other]"))

    def test_add_value_to_last_section(self):
        self.assertTrue(self.conf.WriteValue("other2", "2", section="Other"))
        self.assertTrue(self.read().endswith("other2 = 2\n"))

    def test_remove_value(self):
        self.assertTrue(self.conf.WriteValue("loglocation", "", remove=True))
        self.assertNotIn("loglocation", self.read())

    def test_write_section(self):
        self.assertTrue(self.conf.WriteSection("NewSection"))
        self.assertTrue(self.conf.WriteValue("a", "b", section="NewSection"))
        self.assertIn("[NewSection]\na = b\n", self.read())

    def test_newline_in_value_rejected(self):
        before = self.read()
        self.assertFalse(self.conf.WriteValue("ui_prefs", '{\n  "a": 1\n}'))
        self.assertFalse(self.conf.WriteValue("port", "x\r[Injected]"))
        self.assertEqual(self.read(), before)

    def test_newline_in_entry_rejected(self):
        before = self.read()
        self.assertFalse(self.conf.WriteValue("bad\nkey", "1"))
        self.assertFalse(self.conf.WriteSection("Bad\nSection"))
        self.assertEqual(self.read(), before)

    def test_non_string_value_rejected(self):
        self.assertFalse(self.conf.WriteValue("port", 5))

    def test_failed_write_keeps_original(self):
        before = self.read()
        with mock.patch.object(myfileutil.os, "replace", side_effect=OSError("boom")):
            self.assertFalse(self.conf.WriteValue("port", "/dev/ttyUSB0"))
        self.assertEqual(self.read(), before)
        leftovers = [n for n in os.listdir(self.dir) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    @unittest.skipIf(myfileutil.fcntl is None, "fcntl not available")
    def test_concurrent_writers_in_separate_processes(self):
        # WriteValue must not lose or corrupt data when several processes
        # write the same file. Each worker writes its own key.
        ctx = multiprocessing.get_context("spawn")
        procs = [
            ctx.Process(target=_write_many, args=(self.path, "worker%d" % i, 25))
            for i in range(4)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(60)
            self.assertEqual(p.exitcode, 0)
        conf = QuietConfig(filename=self.path, section="GenMon")
        for i in range(4):
            self.assertEqual(conf.ReadValue("worker%d" % i), "24")
        self.assertEqual(conf.ReadValue("port"), "/dev/serial0")
        self.assertEqual(conf.ReadValue("key", section="Other"), "value")


def _write_many(path, key, count):
    conf = QuietConfig(filename=path, section="GenMon")
    for n in range(count):
        if not conf.WriteValue(key, str(n), section="GenMon"):
            raise SystemExit(1)


if __name__ == "__main__":
    unittest.main()
