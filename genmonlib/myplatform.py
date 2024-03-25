#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: myplatform.py
# PURPOSE: Platform Specific Code
#
#  AUTHOR: Jason G Yates
#    DATE: 20-May-2018
#
# MODIFICATIONS:
#
# USAGE:
#
# -------------------------------------------------------------------------------
import datetime
import os
import re
import subprocess
import sys
from subprocess import PIPE, Popen

from genmonlib.mycommon import MyCommon


# ------------ MyPlatform class -------------------------------------------------
class MyPlatform(MyCommon):

    # ------------ MyPlatform::init----------------------------------------------
    def __init__(self, log=None, usemetric=True, debug=None):
        self.log = log
        self.UseMetric = usemetric
        self.debug = debug

    # ------------ MyPlatform::GetInfo-------------------------------------------
    def GetInfo(self, JSONNum=False):

        Info = []

        PlatformInfo = self.GetPlatformInfo()

        if PlatformInfo != None:
            Info.extend(PlatformInfo)

        OSInfo = self.GetOSInfo()

        if OSInfo != None:
            Info.extend(OSInfo)

        Info.append({"System Time": self.GetSystemTime()})
        return Info

    # ------------ MyPlatform::GetSystemTime-------------------------------------
    def GetSystemTime(self):

        return datetime.datetime.now().strftime("%A %B %-d, %Y %H:%M:%S")

    # ------------ MyPlatform::GetPlatformInfo-----------------------------------
    def GetPlatformInfo(self, JSONNum=False):

        if self.IsPlatformRaspberryPi():
            return self.GetRaspberryPiInfo()
        else:
            return None

    # ------------ MyPlatform::GetOSInfo-----------------------------------------
    def GetOSInfo(self, JSONNum=False):

        if self.IsOSLinux():
            return self.GetLinuxInfo()
        return None

    # ------------ MyPlatform::PlatformBitDepth----------------------------------
    def PlatformBitDepth(self):
        try:
            import platform

            if platform.architecture()[0] == "32bit":
                return "32"
            elif platform.architecture()[0] == "64bit":
                return "64"
            else:
                return "Unknown"
        except Exception as e1:
            self.LogErrorLine("Error in PlatformBitDepth: " + str(e1))
            "Unknown"

    # ------------ MyPlatform::IsOSLinux-----------------------------------------
    @staticmethod
    def IsOSLinux():

        if "linux" in sys.platform:
            return True
        return False

    # ------------ MyPlatform::IsOSWindows-----------------------------------------
    @staticmethod
    def IsOSWindows():

        if "win" in sys.platform:
            return True
        return False

    # ------------ MyPlatform::IsPlatformRaspberryPi-----------------------------
    def IsPlatformRaspberryPi(self, raise_on_errors=False):

        try:
            model = self.GetRaspberryPiModel(bForce = True)
            if model != None and "raspberry" in model.lower():
                return True 
            
            with open("/proc/cpuinfo", "r") as cpuinfo:
                found = False
                for line in cpuinfo:
                    if line.startswith("Hardware"):
                        found = True
                        label, value = line.strip().split(":", 1)
                        value = value.strip()
                        if value not in (
                            "BCM2708",
                            "BCM2709",
                            "BCM2835",
                            "BCM2836",
                            "BCM2711",
                        ):
                            if raise_on_errors:
                                raise ValueError(
                                    "This system does not appear to be a Raspberry Pi."
                                )
                            else:
                                return False
                if not found:
                    if raise_on_errors:
                        raise ValueError(
                            "Unable to determine if this system is a Raspberry Pi."
                        )
                    else:
                        return False
        except IOError:
            if raise_on_errors:
                raise ValueError("Unable to open `/proc/cpuinfo`.")
            else:
                return False

        return True

    # ------------ Evolution:GetRaspberryPiTemp ---------------------------------
    def GetRaspberryPiTemp(self, ReturnFloat=False, JSONNum=False):

        # get CPU temp
        try:
            if ReturnFloat:
                DefaultReturn = 0.0
            else:
                DefaultReturn = "0"

            if not self.IsOSLinux():
                return DefaultReturn
            try:
                if os.path.exists("/usr/bin/vcgencmd"):
                    binarypath = "/usr/bin/vcgencmd"
                else:
                    binarypath = "/opt/vc/bin/vcgencmd"

                process = Popen([binarypath, "measure_temp"], stdout=PIPE)
                output, _error = process.communicate()
                output = output.decode("utf-8")
                if sys.version_info[0] >= 3:
                    output = str(output)  # convert byte array to string for python3

                TempCelciusFloat = float(
                    output[output.index("=") + 1 : output.rindex("'")]
                )

            except Exception as e1:
                # for non rasbpian based systems
                tempfilepath = self.GetHwMonParamPath("temp1_input")
                if tempfilepath == None:
                    tempfilepath = "/sys/class/thermal/thermal_zone0/temp"

                if os.path.exists(tempfilepath):
                    process = Popen(["cat", tempfilepath], stdout=PIPE)
                    output, _error = process.communicate()
                    output = output.decode("utf-8")

                    TempCelciusFloat = float(float(output) / 1000)
                else:
                    # not sure what OS this is, possibly docker image
                    return DefaultReturn
            if self.UseMetric:
                if not ReturnFloat:
                    return "%.2f C" % TempCelciusFloat
                else:
                    return round(TempCelciusFloat, 2)
            else:
                if not ReturnFloat:
                    return "%.2f F" % float(
                        self.ConvertCelsiusToFahrenheit(TempCelciusFloat)
                    )
                else:
                    return round(
                        float(self.ConvertCelsiusToFahrenheit(TempCelciusFloat)), 2
                    )
        except Exception as e1:
            self.LogErrorLine("Error in GetRaspberryPiTemp: " + str(e1))
        return DefaultReturn

    # ------------ MyPlatform::GetRaspberryPiModel -----------------------------
    def GetRaspberryPiModel(self, bForce = False):
        try:
            if bForce == False and not self.IsPlatformRaspberryPi():
                return None
        
            process = Popen(["cat", "/proc/device-tree/model"], stdout=PIPE)
            output, _error = process.communicate()
            if sys.version_info[0] >= 3:
                output = output.decode("utf-8")
            return str(output.rstrip("\x00"))
        except Exception as e1:
            return None
    # ------------ MyPlatform::GetRaspberryPiInfo -------------------------------
    def GetRaspberryPiInfo(self, JSONNum=False):

        if not self.IsPlatformRaspberryPi():
            return None
        PiInfo = []

        try:
            PiInfo.append(
                {"CPU Temperature": self.GetRaspberryPiTemp(ReturnFloat=False)}
            )
            try:
                model = self.GetRaspberryPiModel()
                PiInfo.append({"Pi Model": model})
            except:
                pass
            try:
                ThrottledStatus = self.GetThrottledStatus()
                if len(ThrottledStatus):
                    PiInfo.extend(ThrottledStatus)
            except Exception as e1:
                pass

        except Exception as e1:
            self.LogErrorLine("Error in GetRaspberryPiInfo: " + str(e1))

        return PiInfo

    # ------------ MyPlatform::ParseThrottleStatus ------------------------------
    def ParseThrottleStatus(self, status):

        PiThrottleInfo = []

        StatusStr = ""

        if status & 0x40000:
            StatusStr += "Has occurred. "
        if status & 0x4:
            StatusStr += "Throttling Active. "

        if StatusStr == "":
            StatusStr += "OK"

        PiThrottleInfo.append({"Pi CPU Frequency Throttling": StatusStr})

        StatusStr = ""
        if status & 0x20000:
            StatusStr += "Has occurred. "
        if status & 0x2:
            StatusStr += "ARM frequency capped. "

        if StatusStr == "":
            StatusStr += "OK"

        PiThrottleInfo.append({"Pi ARM Frequency Cap": StatusStr})

        StatusStr = ""
        if status & 0x10000:
            StatusStr += "Has occurred. "
        if status & 0x1:
            StatusStr += "Undervoltage Detected. "

        if StatusStr == "":
            StatusStr += "OK"

        PiThrottleInfo.append({"Pi Undervoltage": StatusStr})
        return PiThrottleInfo

    # ------------ MyPlatform::GetThrottledStatus -------------------------------
    def GetThrottledStatus(self):

        try:
            if os.path.exists("/usr/bin/vcgencmd"):
                binarypath = "/usr/bin/vcgencmd"
            else:
                binarypath = "/opt/vc/bin/vcgencmd"

            process = Popen([binarypath, "get_throttled"], stdout=PIPE)
            output, _error = process.communicate()
            output = output.decode("utf-8")
            hex_val = output.split("=")[1].strip()
            get_throttled = int(hex_val, 16)
            return self.ParseThrottleStatus(get_throttled)

        except Exception as e1:
            try:
                # if we get here then vcgencmd is not found, try an alternate approach
                # /sys/class/hwmon/hwmonX/in0_lcrit_alarm
                throttle_file = self.GetHwMonParamPath("in0_lcrit_alarm")

                if throttle_file != None:
                    file = open(throttle_file)
                else:
                    # this method is depricated
                    file = open("/sys/devices/platform/soc/soc:firmware/get_throttled")
                status = file.read()
                return self.ParseThrottleStatus(int(status))
            except Exception as e1:
                return []

    # ------------ MyPlatform::GetHwMonParamPath --------------------------------
    def GetHwMonParamPath(self, param):

        try:
            for i in range(5):
                hwmon_path = "/sys/class/hwmon/hwmon%d" % (i) + "/" + str(param)
                if os.path.exists(hwmon_path):
                    return hwmon_path
        except Exception as e1:
            self.LogError("Error in GetHwMonParamPath: " + str(e1))
        return None

    # ------------ MyPlatform::GetLinuxInfo -------------------------------------
    def GetLinuxInfo(self, JSONNum=False):

        if not self.IsOSLinux():  # call staticfuntion
            return None
        LinuxInfo = []

        try:
            CPU_Pct = str(
                round(
                    float(
                        os.popen(
                            """grep 'cpu ' /proc/stat | awk '{usage=($2+$4)*100/($2+$4+$5)} END {print usage }' """
                        ).readline()
                    ),
                    2,
                )
            )
            if len(CPU_Pct):
                LinuxInfo.append({"CPU Utilization": CPU_Pct + "%"})
        except:
            pass
        try:
            with open("/etc/os-release", "r") as f:
                OSReleaseInfo = {}
                for line in f:
                    if not "=" in line:
                        continue
                    k, v = line.rstrip().split("=")
                    # .strip('"') will remove if there or else do nothing
                    OSReleaseInfo[k] = v.strip('"')
                LinuxInfo.append({"OS Name": OSReleaseInfo["NAME"]})
                if "VERSION" in OSReleaseInfo:
                  LinuxInfo.append({"OS Version" : OSReleaseInfo["VERSION"]})
                elif "VERSION_ID" in OSReleaseInfo:
                  LinuxInfo.append({"OS Version" : OSReleaseInfo["VERSION_ID"]})
            try:
                with open("/proc/uptime", "r") as f:
                    uptime_seconds = float(f.readline().split()[0])
                    uptime_string = str(datetime.timedelta(seconds=uptime_seconds))
                    LinuxInfo.append(
                        {"System Uptime": uptime_string.split(".")[0]}
                    )  # remove microseconds
            except Exception as e1:
                pass

            try:
                adapter = (
                    os.popen(
                        "ip link | grep BROADCAST | grep -v NO-CARRIER | grep -m 1 LOWER_UP  | awk -F'[:. ]' '{print $3}'"
                    )
                    .readline()
                    .rstrip("\n")
                )
                # output, _error = process.communicate()
                LinuxInfo.append({"Network Interface Used": adapter})
                try:
                    if adapter.startswith("wl"):
                        LinuxInfo.extend(self.GetWiFiInfo(adapter))
                except Exception as e1:
                    pass

            except:
                pass
        except Exception as e1:
            self.LogErrorLine("Error in GetLinuxInfo: " + str(e1))

        return LinuxInfo

    # ------------ MyPlatform::GetWiFiSignalStrength ----------------------------
    def GetWiFiSignalStrength(self, ReturnInt=True, JSONNum=False):

        try:
            if ReturnInt == True:
                DefaultReturn = 0
            else:
                DefaultReturn = 0

            if not self.IsOSLinux():  # call staticfuntion
                return DefaultReturn

            adapter = (
                os.popen(
                    "ip link | grep BROADCAST | grep -v NO-CARRIER | grep -m 1 LOWER_UP  | awk -F'[:. ]' '{print $3}'"
                )
                .readline()
                .rstrip("\n")
            )

            if not adapter.startswith("wl"):
                return DefaultReturn

            signal = self.GetWiFiSignalStrengthFromAdapter(adapter)
            signal = int(signal) * -1
            return signal
        except Exception as e1:
            self.LogErrorLine("Error in GetWiFiSignalStrength: " + str(e1))
            return DefaultReturn

    # ------------ MyPlatform::GetWiFiSignalStrengthFromAdapter -----------------
    def GetWiFiSignalStrengthFromAdapter(self, adapter, JSONNum=False):
        try:
            result = subprocess.check_output(["iw", adapter, "link"])
            if sys.version_info[0] >= 3:
                result = result.decode("utf-8")
            match = re.search("signal: -(\d+) dBm", result)
            return match.group(1)
        except Exception as e1:
            return "0"

    # ------------ MyPlatform::GetWiFiSignalQuality -----------------------------
    def GetWiFiSignalQuality(self, adapter, JSONNum=False):
        try:
            result = subprocess.check_output(["iwconfig", adapter])
            if sys.version_info[0] >= 3:
                result = result.decode("utf-8")
            match = re.search("Link Quality=([\s\S]*?) ", result)
            return match.group(1)
        except Exception as e1:
            return ""

    # ------------ MyPlatform::GetWiFiSSID --------------------------------------
    def GetWiFiSSID(self, adapter):
        try:
            result = subprocess.check_output(["iwconfig", adapter])
            if sys.version_info[0] >= 3:
                result = result.decode("utf-8")
            match = re.search('ESSID:"([\s\S]*?)"', result)
            return match.group(1)
        except Exception as e1:
            return ""

    # ------------ MyPlatform::GetWiFiInfo --------------------------------------
    def GetWiFiInfo(self, adapter, JSONNum=False):

        WiFiInfo = []

        try:
            with open("/proc/net/wireless", "r") as f:
                for line in f:
                    if not adapter in line:
                        continue
                    ListItems = line.split()
                    if len(ListItems) > 4:

                        signal = self.GetWiFiSignalStrength(JSONNum=JSONNum)
                        if signal != 0:
                            WiFiInfo.append({"WLAN Signal Level": str(signal) + " dBm"})
                        else:
                            WiFiInfo.append({"WLAN Signal Level": ListItems[3].replace(".", "") + " dBm"})
                        # Note that some WLAN drivers make this value based from 0 - 70, others are 0-100
                        # There is no standard on the range
                        try:
                            WiFiInfo.append(
                                {
                                    "WLAN Signal Quality": self.GetWiFiSignalQuality(adapter, JSONNum=JSONNum)
                                }
                            )
                        except:
                            WiFiInfo.append(
                                {
                                    "WLAN Signal Quality": ListItems[2].replace(".", "")
                                    + "/70"
                                }
                            )

                        WiFiInfo.append(
                            {
                                "WLAN Signal Noise": ListItems[4].replace(".", "")
                                + " dBm"
                            }
                        )
            essid = self.GetWiFiSSID(adapter)
            if essid != None and essid != "":
                WiFiInfo.append({"WLAN ESSID": essid})
        except Exception as e1:
            pass
        return WiFiInfo

    # ------------ MyPlatform::InternetConnected --------------------------------
    # Note: this function, if the network connection is not present could
    # take some time to complete due to the network timeout
    @staticmethod
    def InternetConnected():

        if sys.version_info[0] < 3:
            import httplib
        else:
            import http.client as httplib

        conn = httplib.HTTPConnection("www.google.com", timeout=2)
        try:
            conn.request("HEAD", "/")
            conn.close()
            return True
        except:
            conn.close()
            return False
