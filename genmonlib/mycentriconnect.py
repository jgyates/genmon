#!/usr/bin/env python
# ------------------------------------------------------------
#    FILE: mycentriconnect.py
# PURPOSE: Handle web interacetion and parsing of centriconnect REST API
#
#  AUTHOR: Jason G Yates
#    DATE: 12-May-2025
# Free software. Use at your own risk.
# MODIFICATIONS:
# ------------------------------------------------------------

from __future__ import print_function

import sys

import requests
import threading

try:
    from genmonlib.mycommon import MyCommon

except Exception as e1:
    print(
        "\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n"
    )
    print(
        "Please see the project documentation at https://github.com/jgyates/genmon.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)


class centriconnect(MyCommon):

    # ------------ centriconnect::init---------------------------------------------
    def __init__(self, user_id, device_id, device_auth, log, debug=False):

        self.log = log
        self.debug = debug
        self.user_id = user_id
        self.device_id = device_id
        self.device_auth = device_auth
        self.token = ""
        self.BASEURL = 'https://api.centriconnect.com'
        # Construct the full URL with path parameters
        endpoint = f'/centriconnect/{self.user_id}/device/{self.device_id}/all-data'
        self.url = self.BASEURL + endpoint
        self.LogDebug(f"URL: {self.url}")
        self.DataLock = threading.Lock()
        
        self.Data = None

    # ------------ centriconnect::GetData------------------------------------------
    def GetData(self):
        try:

            if not self.InitOK(nodata = True):
                return None

            # Provide DeviceAuth code as a Query Parameter.
            params = {
                'device_auth': self.device_auth, ## Device Authentication Code (i.e. 123456)
            }

            try:
                # Make the GET request with query parameters
                response = requests.get(self.url, params=params)
                response.raise_for_status()  # Check for HTTP errors

                # Parse the JSON response if available
                data = response.json()

                # data should look like this:
                '''
                {
                    "36e551aa-c215-4c9b-8c70-ba77296878cc": {         # Device ID as the root key
                    "AlertStatus": "Low Level",                       # Alert status indicating the current status of the device (e.g., "Low Level", "Normal", etc for tank alerts)
                    "Altitude": 281.68231201171875,                   # Most recent altitude reading from the device's GPS in meters
                    "BatteryVolts": 4.047032833099365,                # Battery voltage level (4.0V is 100%, 3.5V is the lowest threshold - units are shipped out at 110%)
                    "DeviceID": "36e551aa-c215-4c9b-8c70-ba77296878cc", # Unique identifier for the device
                    "DeviceName": "White Cloud",                      # User-assigned name for the device
                    "DeviceTempCelsius"                               # Device Temperature in Celsius
                    "DeviceTempFahrenheit"                            # Device Temperature in Fahrenheit
                    "LastPostTimeIso": "2024-10-25 18:00:35.378000",  # ISO 8601 timestamp for the last data post
                    "Latitude": 43.526187896728516,                   # Last recorded latitude coordinate for the device's location
                    "Longitude": -85.62322998046875,                  # Last recorded longitude coordinate for the device's location
                    "NextPostTimeIso": "2024-10-26 00:00:35.378000",  # ISO 8601 timestamp for the next scheduled data post
                    "SignalQualLTE": -117.0,                          # LTE signal quality, represented in RSSI (received signal strength indicator)
                    "SolarVolts": 1.692307710647583,                  # Voltage level from the solar cell (0-2.5V; 2.5V indicates high solar input)
                    "TankLevel": 42.0,                                # Tank level as a percentage of total capacity
                    "TankSize": 500,                                  # User-defined size of the tank being monitored
                    "TankSizeUnit": "Gallons",                        # Unit of the tank size (e.g., "Gallons" or "Liters")
                    "VersionHW": "3.1",                               # Hardware version of the device
                    "VersionLTE": "1.15"                              # LTE module version used by the device
                    }
                }
                '''
                self.LogDebug('Response JSON:')
                self.LogDebug(data)

            except requests.exceptions.HTTPError as http_err:
                self.LogErrorLine(f'HTTP error occurred: {http_err}')  # HTTP error
            except requests.exceptions.ConnectionError as conn_err:
                self.LogErrorLine(f'Connection error occurred: {conn_err}')  # Network problem
            except requests.exceptions.Timeout as timeout_err:
                self.LogErrorLine(f'Timeout error occurred: {timeout_err}')  # Request timed out
            except requests.exceptions.RequestException as req_err:
                self.LogErrorLine(f'An error occurred: {req_err}')  # Any other request issues
            except ValueError:
                self.LogErrorLine('Response content is not valid JSON')
            else:
                self.LogDebug('API call was successful.')

                if "Result" in data.keys() and data["Result"] == "Device does not exist.":
                    self.LogError("Error: invalid device ID")
                    return None
                elif "Results" in data.keys():
                    self.LogError(f"Error: Unknown Error: {data['Results']}")
                with self.DataLock:
                    self.Data = data
            return self.Data
        except Exception as e1:
            self.LogErrorLine("Error in centriconnect:GetData : " + str(e1))
            return None
    # ---------- centriconnect::InitOK------------------------------------------
    def InitOK(self, nodata = False):

        if not nodata:
            if self.Data == None:
                self.LogDebug("Error in centriconnect::GetData: No data.")
                return False
        
        if self.device_id == None or not len(self.device_id):
            self.LogDebug("Error in centriconnect::GetData: invalid device ID")
            return False
        if self.user_id == None or not len(self.user_id):
            self.LogDebug("Error in centriconnect::GetData: invalid user name")
            return False
        if self.device_auth == None or not len(self.device_auth):
            self.LogDebug("Error in centriconnect::GetData: invalid device auth")
            return False
        return True
    # ---------- centriconnect::GetValue----------------------------------------
    def GetValue(self, valuename):
        try:
            if not self.InitOK():
                return None
            
            with self.DataLock:
                return self.Data[self.device_id][valuename]
        except Exception as e1:
            self.LogErrorLine("centriconnect: Error in GetValue: (" + str(valuename) + "):" + str(e1))
            return None

    # ---------- centriconnect::GetCapacity-------------------------------------
    def GetCapacity(self):
        try:
            if not self.InitOK():
                return None
            return self.GetValue("TankSize")
        except Exception as e1:
            self.LogErrorLine("centriconnect: Error in GetCapacity: " + str(e1))
            return None

    # ---------- centriconnect::GetBattery--------------------------------------
    def GetBattery(self):
        try:
            if not self.InitOK():
                return None

            # Battery voltage level (4.0V is 100%, 3.5V is the lowest threshold - units are shipped out at 110%)
            battery_volts = float(self.GetValue("BatteryVolts"))
            if battery_volts <= 3.6:
                return "Critical"
            elif battery_volts <3.7:
                return "Warning"
            else:
                return "OK"
        except Exception as e1:
            self.LogErrorLine("centriconnect: Error in GetBattery: " + str(e1))
            return "Unknown"

    # ---------- centriconnect::GetPercentage-----------------------------------
    def GetPercentage(self):
        try:
            if not self.InitOK():
                return None

            return round(float(self.GetValue("TankLevel")),2)

        except Exception as e1:
            self.LogErrorLine("centriconnect: Error in GetPercentage: " + str(e1))
            return 0.0
        
    # ---------- centriconnect::GetTemp-----------------------------------------
    def GetTemp(self, use_metric = False):
        try:
            if not self.InitOK():
                return None
            
            if use_metric:
                temp_param = "DeviceTempCelsius"
            else:
                temp_param = "DeviceTempFahrenheit" 
            return round(float(self.GetValue(temp_param)),2)

        except Exception as e1:
            self.LogErrorLine("centriconnect: Error in GetTemp: " + str(e1))
            return 0.0
