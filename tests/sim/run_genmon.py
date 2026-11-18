#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: run_genmon.py
# PURPOSE: Starts genmon.py for the simulator tests (tests/test_genmon_sim.py)
#          as a normal user. genmon needs root on Linux (it stops with "You
#          need to have root privileges"); the tests run in temporary folders
#          and need no root, so this skips that check, in this process only,
#          and then runs genmon.py as usual.
#
#   USAGE: python3 tests/sim/run_genmon.py <genmon.py arguments>
#              e.g. python3 tests/sim/run_genmon.py -c <config folder>
#
# -------------------------------------------------------------------------------

import os
import runpy
import sys

REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GENMON = os.path.join(REPO_DIR, "genmon.py")

sys.path.insert(0, REPO_DIR)
from genmonlib.mysupport import MySupport  # noqa: E402

MySupport.PermissionsOK = staticmethod(lambda: True)

sys.argv = [GENMON] + sys.argv[1:]
runpy.run_path(GENMON, run_name="__main__")
