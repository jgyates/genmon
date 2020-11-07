#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: program_defaults.py
# PURPOSE: default values
#
#  AUTHOR: Jason G Yates
#    DATE: 10-May-2019
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import sys

#------------ ProgramDefaults class ---------------------------------------------
class ProgramDefaults(object):

    if 'win' in sys.platform:  
        
        #--Windows change, not sure these are the best paths to use in Windows, but they can work
        
        ConfPath = ".\\conf\\"
        LogPath = ".\\log\\"
    else:
        ConfPath = "/etc/genmon/"
        LogPath = "/var/log/"

    ServerPort = 9082
    LocalHost =  "127.0.0.1"
    GENMON_VERSION = "V1.15.09"
