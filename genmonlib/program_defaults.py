#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: program_defaults.py
# PURPOSE: default values
#
#  AUTHOR: Jason G Yates
#    DATE: 10-May-2019
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------


# ------------ ProgramDefaults class ---------------------------------------------
class ProgramDefaults(object):
    ConfPath = "/etc/genmon/"
    LogPath = "/var/log/"
    ServerPort = 9082
    LocalHost = "127.0.0.1"
    GENMON_VERSION = "2.0.4"
    # oldest Python genmon runs on (genmon 2.0 and later need 3.9, see
    # README.md). genloader.py will not start on an older one, and
    # genmonmaint.sh reads this line (keep it on one line, as "(3, 9)") to
    # stop an install, or an update to a version that needs a newer Python.
    MIN_PYTHON = (3, 9)
