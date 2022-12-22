#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: voipms.py
# PURPOSE: Send text message using voip.ms service
#
#  AUTHOR: Jason G Yates
#    DATE: 06-05-2021
#
# MODIFICATIONS:
#
# USAGE:
#
#-------------------------------------------------------------------------------

import os, sys

from genmonlib.mysupport import MySupport


#------------ MyVoipMs class -------------------------------------------------
class MyVoipMs(MySupport):

    #------------ MyVoipMs::init------------------------------------------------
    def __init__(self, log = None, console = None, username = None, password = None, did = None, debug = False):
        self.log = log
        self.console = console
        self.username = username
        self.password = password
        self.did = did
        self.debug = debug

        self.debug = False
        try:
            from voipms import VoipMs
            # https://github.com/4doom4/python-voipms
            self.client = VoipMs(self.username, self.password)

            # IP addresses allowed to send SMS
            ipaddresses = self.client.general.get.ip()
            # WAN IP address of this computer
            wanipaddress = self.GetWANIp()

            self.LogDebug("WanIP: " + str(wanipaddress) + " Client IP: " + str(ipaddresses))
            # Allowed ip must match our WAN IP
            if wanipaddress != ipaddresses['ip']:
                self.LogError("Warning WanIP and VoipMS IP addresses do not match: " + str(wanipaddress) + ": " +  ipaddresses['ip'])

        except Exception as e1:
            self.LogErrorLine("Error in MyVoipMs:init: " + str(e1))
            sys.exit(1)
    #------------ MyVoipMs::SendSMS-----------------------------------------------
    def SendSMS(self, destination, message):
        try:
            status = self.client.dids.send.sms(self.did, destination, message)
            if status["status"] != 'success':
                self.LogError("Error sending SMS: " + str(status))
                return False
            return True
        except Exception as e1:
            self.LogErrorLine("Error in MyVoipMs:SendSMS: " + str(e1))
            return False
