#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: mytankutility.py
# PURPOSE: Handle web interacetion and parsing of tankutility.com
#
#  AUTHOR: Jason G Yates
#    DATE: 24-Feb-2021
# Free software. Use at your own risk.
# MODIFICATIONS:
#------------------------------------------------------------

from __future__ import print_function

import requests, sys

try:
    from genmonlib.mycommon import MyCommon
    from genmonlib.mysupport import MySupport

except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)

class tankutility(MyCommon):

    #------------ tankutility::init---------------------------------------------
    def __init__(self, username, password, log, debug = False):

        self.log = log
        self.username = username
        self.password = password
        self.token = ""
        self.BASEURL = "https://data.tankutility.com/api/"
        self.DeviceIDs = []
        self.DeviceCount = 0
        self.debug = debug
        self.Data = None
    #------------ tankutility::Login--------------------------------------------
    def Login(self):
        try:
            ## Register user name and password with the API and get an authorization token for subsequent queries
            url = self.urljoin(self.BASEURL,"getToken")
            query = requests.get(url, auth=(self.username, self.password))
            if query.status_code != 200:
                self.LogError("tankutility: Error logging in, error code: " + str(query.status_code ))
                return False
            else:
                response = query.json()
                self.LogDebug("Login: " + str(response))
                try:
                    if response['error'] != '':
                        self.LogError("tankutility: API reports an account error: " + str(response['error']))
                        return False
                except:
                    pass
                self.token = response['token']
                return True
        except Exception as e1:
            self.LogErrorLine("Error in tankutility:Login: " + str(e1))
            return False
    #------------ tankutility::GetDevices---------------------------------------
    def GetDevices(self):
        try:
            if not len(self.token):
                self.LogError("Error in tankutility::GetDevices: not logged in")
                return False
            url = self.urljoin(self.BASEURL,"devices")
            params = (('token', self.token),)
            query = requests.get(url, params=params)
            if query.status_code != 200:
                self.LogError("tankutility: Unable to obtain device list from the API, Error code: " + str(query.status_code ))
                return False
            else:
                response = query.json()
                self.LogDebug("tankutility: GetDevices: " + str(response))
                self.DeviceIDs = response['devices']

                return True
        except Exception as e1:
            self.LogErrorLine("Error in tankutility:GetDevices : " + str(e1))
            return False
    #------------ tankutility::GetData------------------------------------------
    def GetData(self, deviceID):
        try:
            if not len(deviceID):
                return None
            if not len(self.token):
                self.LogError("Error in tankutility::GetData: not logged in")
                return None
            url = self.urljoin(self.BASEURL,"devices", deviceID)
            params = (('token', self.token),)
            query = requests.get(url, params=params)
            if query.status_code != 200:
                self.LogError("tankutility: Unable to obtain device info from the API, Error code: " + str(query.status_code ) + ": " + str(deviceID))
                return None
            else:
                response = query.json()
                self.Data = response["device"]
                self.LogDebug("tankutility: GetData: ID = " + str(deviceID) + " : "+ str(response))
                return self.Data
        except Exception as e1:
            self.LogErrorLine("Error in tankutility:GetData : " + str(e1))
            return None
    #------------ tankutility::GetIDFromName------------------------------------------
    def GetIDFromName(self, name):
        try:
            if not self.GetDevices():
                self.LogError("tankutility: GetDevices failed in tankutility:GetIDFromName")
                return ""
            if not len(self.DeviceIDs):
                self.LogError("Not devices returned in tankutility: GetIDFromName")
                return ""
            name = name.strip()
            if name == "" or name == None:      # assume only one device
                return self.DeviceIDs[0]
            for device in self.DeviceIDs:
                tankdata = self.GetData(device)
                if tankdata == None:
                    continue
                if tankdata["name"].lower() == name.lower():
                    self.Data = tankdata
                    return device
            return ""
        except Exception as e1:
            self.LogErrorLine("Error in tankutility:GetIDFromName: " + str(e1))
            return ""
    # ---------- GenTankData::GetReadingTemperature-----------------------------
    def GetReadingTemperature(self):
        try:
            return self.Data["lastReading"]["temperature"]
        except Exception as e1:
            self.LogErrorLine("tankutility: Error in GetReadingTemperature: " + str(e1))
            return 0
    # ---------- GenTankData::GetReadingTime------------------------------------
    def GetReadingEpochTime(self):
        try:
            return self.Data["lastReading"]["time"]
        except Exception as e1:
            self.LogErrorLine("tankutility: Error in GetReadingTime: " + str(e1))
            return 0
    # ---------- GenTankData::GetCapacity---------------------------------------
    def GetCapacity(self):
        try:
            return self.Data["capacity"]
        except Exception as e1:
            self.LogErrorLine("tankutility: Error in GetCapacity: " + str(e1))
            return 0

    # ---------- GenTankData::GetPercentage-------------------------------------
    def GetPercentage(self):
        try:
            return round(float(self.Data["lastReading"]["tank"]),2)
        except Exception as e1:
            self.LogErrorLine("tankutility: Error in GetPercentage: " + str(e1))
            return 0.0
