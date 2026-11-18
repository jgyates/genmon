#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_lint.py
# PURPOSE: Runs tests/run_lint.sh (pyflakes checks of the Python code and
#          shellcheck of the shell scripts) with the other tests, so one
#          command checks everything.
#
#          Skipped when uv (uvx) is not installed, or on GitHub, where the
#          separate "Lint" job runs it once.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_lint
#
# -------------------------------------------------------------------------------

import os
import shutil
import subprocess
import unittest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINT_SCRIPT = os.path.join(REPO_DIR, "tests", "run_lint.sh")


@unittest.skipIf(shutil.which("uvx") is None, "uv (uvx) is not installed")
@unittest.skipIf(os.environ.get("GITHUB_ACTIONS") == "true", "the Lint job runs it on GitHub")
@unittest.skipIf(not os.path.isdir(os.path.join(REPO_DIR, ".git")), "not a git repository")
class LintTests(unittest.TestCase):

    def test_lint(self):
        result = subprocess.run(["bash", LINT_SCRIPT], cwd=REPO_DIR, capture_output=True,
                                text=True, timeout=600)
        self.assertEqual(result.returncode, 0, "\n" + result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
