#!/usr/bin/env python
# ------------------------------------------------------------
#    FILE: example_button.py
# PURPOSE:
#
#  AUTHOR: Jason G Yates
#    DATE: 10-Apr-2025
# Free software. Use at your own risk.
# MODIFICATIONS:
# ------------------------------------------------------------


import os
import sys

# Adds higher directory to python modules path (e.g. ~/genmon)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(sys.path[0]))))  

try:
    from genmonlib.mylog import SetupLogger
except Exception as e1:
    print("\n\nThis is an example script and requires the directory structure of the genmon project to run.")
    print("Error: " + str(e1))
    sys.exit(1)

loglocation = "/var/log"
scriptbasename = os.path.splitext(os.path.basename(__file__))[0]

# -------------------------------------------------------------------------------
if __name__ == "__main__":


    log = SetupLogger("scriptbasename", os.path.join(loglocation, scriptbasename + ".log"))
    
    log.error("Running script " + scriptbasename)
    sys.exit(0)