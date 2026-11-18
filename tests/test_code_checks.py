#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_code_checks.py
# PURPOSE: Checks of the source code that keep known problems from coming back.
#
#          - every web request (requests.get / post / ...) has a timeout:
#            without one, a server that stops answering hangs the program (or an
#            add-on's message queue) for ever
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_code_checks
#
# -------------------------------------------------------------------------------

import ast
import glob
import os
import unittest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUEST_FUNCTIONS = {"get", "post", "put", "patch", "delete", "head", "request"}


def python_files():
    for pattern in ["*.py", "genmonlib/*.py", "addon/*.py", "OtherApps/*.py"]:
        for path in sorted(glob.glob(os.path.join(REPO_DIR, pattern))):
            yield path


class CodeCheckTests(unittest.TestCase):

    def test_web_requests_have_a_timeout(self):
        missing = []
        for path in python_files():
            with open(path, "rb") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in REQUEST_FUNCTIONS
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "requests"
                        and not any(k.arg == "timeout" for k in node.keywords)):
                    missing.append("%s:%d" % (os.path.relpath(path, REPO_DIR), node.lineno))
        self.assertEqual(missing, [], "requests calls without timeout=")


if __name__ == "__main__":
    unittest.main()
