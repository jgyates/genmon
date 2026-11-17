#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_genlog.py
# PURPOSE: Tests for addon/genlog.py: which file it logs to (-f on the command
#          line, or filename in genlog.conf).
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_genlog
#
# -------------------------------------------------------------------------------

import logging
import os
import shutil
import sys
import tempfile
import unittest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_DIR)
sys.path.insert(0, os.path.join(REPO_DIR, "addon"))

import genlog


class GenLogFileNameTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="genlog_test_") + os.sep
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        # a GenLog without its __init__ (which connects to genmon)
        self.genlog = genlog.GenLog.__new__(genlog.GenLog)
        self.genlog.log = logging.getLogger("test_genlog")
        self.genlog.log.addHandler(logging.NullHandler())
        self.genlog.log.propagate = False
        self.genlog.console = None

    def write_conf(self, text):
        with open(os.path.join(self.folder, "genlog.conf"), "w") as f:
            f.write(text)

    def test_file_name_from_genlog_conf(self):
        self.write_conf("[genlog]\nfilename = /data/mylog.csv\n")
        self.assertEqual(self.genlog.GetOutputFileName(None, self.folder), "/data/mylog.csv")
        self.assertEqual(self.genlog.GetOutputFileName("  ", self.folder), "/data/mylog.csv")

    def test_command_line_is_used_first(self):
        self.write_conf("[genlog]\nfilename = /data/mylog.csv\n")
        self.assertEqual(self.genlog.GetOutputFileName(" /tmp/other.csv ", self.folder),
                         "/tmp/other.csv")

    def test_default_genlog_conf(self):
        shutil.copy(os.path.join(REPO_DIR, "conf", "genlog.conf"), self.folder)
        self.assertEqual(self.genlog.GetOutputFileName(None, self.folder),
                         "/home/pi/genmon/LogFile.csv")

    def test_no_file_name(self):
        # genlog.py then stops with "Missing output file name"
        self.assertEqual(self.genlog.GetOutputFileName(None, self.folder), "")
        self.write_conf("[genlog]\n")
        self.assertEqual(self.genlog.GetOutputFileName(None, self.folder), "")


if __name__ == "__main__":
    unittest.main()
