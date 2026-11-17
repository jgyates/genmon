#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: coverage_report.py
# PURPOSE: Run the tests in tests/ and report which code they run (test
#          coverage), for every .py file in the repository and addon/, including
#          files the tests never import (shown as 0%).
#
#          The genserv tests run a copy of genserv.py from a temporary folder
#          (see genserv_fixture.py); this script maps that copy back to the
#          repository's genserv.py and genmonlib/.
#
#          Needs the coverage package: python3 -m pip install coverage
#
#   USAGE: from the root of the repository:
#              python3 tests/coverage_report.py
#          also write an HTML report (one page per file, missed lines marked):
#              python3 tests/coverage_report.py --html <folder>
#
# -------------------------------------------------------------------------------

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RC_FILE = """[run]
parallel = True
data_file = {work}/data/.coverage
source =
    {repo}
    {repo}/addon
    {work}/tmp
omit =
    */tests/*
    */genenv/*
    */site-packages/*
    */genservext.py
    */OtherApps/*

[paths]
genmon =
    {repo}
    */genserv_run_*/genmon

[report]
skip_empty = True
"""


def main():
    parser = argparse.ArgumentParser(description="Test coverage report for genmon")
    parser.add_argument("--html", metavar="FOLDER", help="also write an HTML report here")
    args = parser.parse_args()

    if importlib.util.find_spec("coverage") is None:
        print("The coverage package is not installed: python3 -m pip install coverage")
        return 2

    work = tempfile.mkdtemp(prefix="genmon_coverage_")
    try:
        os.makedirs(os.path.join(work, "data"))
        os.makedirs(os.path.join(work, "tmp"))
        rc_file = os.path.join(work, "coveragerc")
        with open(rc_file, "w") as f:
            f.write(RC_FILE.format(work=work, repo=REPO_DIR))
        # the tests' temporary folders go under work/tmp, so they are measured
        env = dict(os.environ, TMPDIR=os.path.join(work, "tmp"))
        run = [sys.executable, "-m", "coverage"]

        tests = subprocess.run(
            run + ["run", "--rcfile", rc_file, "-m", "unittest", "discover", "-s", "tests"],
            cwd=REPO_DIR, env=env)
        subprocess.run(run + ["combine", "--rcfile", rc_file, "-q"], cwd=REPO_DIR, check=True)
        subprocess.run(run + ["report", "--rcfile", rc_file, "-i", "--sort=-miss"],
                       cwd=REPO_DIR, check=True)
        if args.html:
            html = os.path.abspath(args.html)
            subprocess.run(run + ["html", "--rcfile", rc_file, "-i", "-q", "-d", html],
                           cwd=REPO_DIR, check=True)
            print("HTML report: " + os.path.join(html, "index.html"))
        if tests.returncode != 0:
            print("\nNote: some tests failed, see above.")
        return tests.returncode
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
