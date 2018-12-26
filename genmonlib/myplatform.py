#!/usr/bin/env python
#-------------------------------------------------------------------------------
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
#-------------------------------------------------------------------------------
from subprocess import PIPE, Popen
import os, sys, subprocess, re, datetime
import collections

from genmonlib.mycommon import MyCommon

#------------ MyPlatform class -------------------------------------------------
class MyPlatform(MyCommon):

    #------------ MyPlatform::init----------------------------------------------
    def __init__(self, log = None, usemetric = True):
        self.log = log
        self.UseMetric = usemetric

    #------------ MyPlatform::GetInfo-------------------------------------------
    def GetInfo(self):

        PlatformInfo = self.GetPlatformInfo()
        OSInfo = self.GetOSInfo()
        if OSInfo == None and PlatformInfo == None:
            return []

        if PlatformInfo == None:
            return OSInfo
        if OSInfo == None:
            return PlatformInfo

        PlatformInfo.extend(OSInfo)
        return PlatformInfo

    #------------ MyPlatform::GetPlatformInfo-----------------------------------
    def GetPlatformInfo(self):

        if self.IsPlatformRaspberryPi():
            return self.GetRaspberryPiInfo()
        else:
            return None

    #------------ MyPlatform::GetOSInfo-----------------------------------------
    def GetOSInfo(self):

        if self.IsOSLinux():
            return self.GetLinuxInfo()
        return None
    #------------ MyPlatform::IsOSLinux-----------------------------------------
    def IsOSLinux(self):

        if "linux" in sys.platform:
            return True

    #------------ MyPlatform::IsPlatformRaspberryPi-----------------------------
    def IsPlatformRaspberryPi(self, raise_on_errors=False):

        try:
            with open('/proc/cpuinfo', 'r') as cpuinfo:
                found = False
                for line in cpuinfo:
                    if line.startswith('Hardware'):
                        found = True
                        label, value = line.strip().split(':', 1)
                        value = value.strip()
                        if value not in ('BCM2708','BCM2709','BCM2835','BCM2836'):
                            if raise_on_errors:
                                raise ValueError('This system does not appear to be a Raspberry Pi.')
                            else:
                                return False
                if not found:
                    if raise_on_errors:
                        raise ValueError('Unable to determine if this system is a Raspberry Pi.')
                    else:
                        return False
        except IOError:
            if raise_on_errors:
                raise ValueError('Unable to open `/proc/cpuinfo`.')
            else:
                return False

        return True

    #------------ MyPlatform::ConvertCelsiusToFahrenheit -----------------------
    def ConvertCelsiusToFahrenheit(self, Celsius):

        return (9.0/5.0 * Celsius + 32)

    #------------ MyPlatform::GetRaspberryPiInfo -------------------------------
    def GetRaspberryPiInfo(self):

        if not self.IsPlatformRaspberryPi():
            return None
        PiInfo = []

        try:
            try:
                process = Popen(['/opt/vc/bin/vcgencmd', 'measure_temp'], stdout=PIPE)
                output, _error = process.communicate()
                if self.UseMetric:
                    PiInfo.append({"CPU Temperature" : "%.2f C" % float(output[output.index('=') + 1:output.rindex("'")])})
                else:
                    PiInfo.append({"CPU Temperature" : "%.2f F" % self.ConvertCelsiusToFahrenheit(float(output[output.index('=') + 1:output.rindex("'")]))})
            except Exception as e1:
                self.LogError(str(e1))
                # for non rasbpian based systems
                process = Popen(['cat', '/sys/class/thermal/thermal_zone0/temp'], stdout=PIPE)
                output, _error = process.communicate()
                if self.UseMetric:
                    TempStr = str(float(output) / 1000) + " C"
                else:
                    TempStr = str(self.ConvertCelsiusToFahrenheit(float(output) / 1000)) + " F"
                PiInfo.append({"CPU Temperature" : TempStr})

            try:
                process = Popen(['cat', '/proc/device-tree/model'], stdout=PIPE)
                output, _error = process.communicate()
                PiInfo.append({"Pi Model" : str(output.encode('ascii', 'ignore')).rstrip("\x00")})
            except:
                pass
            try:
                file = open("/sys/devices/platform/soc/soc:firmware/get_throttled")
                status = file.read()
                PiInfo.extend(self.ParseThrottleStatus(int(status, 16)))
            except Exception as e1:
                pass

        except Exception as e1:
            self.LogErrorLine("Error in GetRaspberryPiInfo: " + str(e1))

        return PiInfo

    #------------ MyPlatform::ParseThrottleStatus ------------------------------
    def ParseThrottleStatus(self, status):

        PiThrottleInfo = []

        StatusStr = ""

        if (status & 0x40000):
            StatusStr += "Has occurred. "
        if (status & 0x4):
            StatusStr += "Throttling Active. "

        if StatusStr == "":
            StatusStr += "OK"

        PiThrottleInfo.append({"Pi CPU Frequency Throttling" : StatusStr})

        StatusStr = ""
        if (status & 0x20000):
            StatusStr += "Has occurred. "
        if (status & 0x2):
            StatusStr += "ARM frequency capped. "

        if StatusStr == "":
            StatusStr += "OK"

        PiThrottleInfo.append({"Pi ARM Frequency Cap" : StatusStr})

        StatusStr = ""
        if (status & 0x10000):
            StatusStr += "Has occurred. "
        if (status & 0x1):
            StatusStr += "Undervoltage Detected. "

        if StatusStr == "":
            StatusStr += "OK"

        PiThrottleInfo.append({"Pi Undervoltage" : StatusStr})
        return PiThrottleInfo

    #------------ MyPlatform::GetThrottledStatus -------------------------------
    def GetThrottledStatus():

        try:
            file = open("/sys/devices/platform/soc/soc:firmware/get_throttled")
            status = file.read()

            get_throttled = int(status, 16)
            StatusStr = ParseThrottleStatus(get_throttled)

        except:
            pass

    #------------ MyPlatform::GetLinuxInfo -------------------------------------
    def GetLinuxInfo(self):

        if not self.IsOSLinux():
            return None
        LinuxInfo = []

        try:
            CPU_Pct=str(round(float(os.popen('''grep 'cpu ' /proc/stat | awk '{usage=($2+$4)*100/($2+$4+$5)} END {print usage }' ''').readline()),2))
            if len(CPU_Pct):
                LinuxInfo.append({"CPU Utilization" : CPU_Pct + "%"})
        except:
            pass
        try:
            with open("/etc/os-release", "r") as f:
                OSReleaseInfo = {}
                for line in f:
                    if not "=" in line:
                        continue
                    k,v = line.rstrip().split("=")
                    # .strip('"') will remove if there or else do nothing
                    OSReleaseInfo[k] = v.strip('"')
                LinuxInfo.append({"OS Name" : OSReleaseInfo["NAME"]})
                LinuxInfo.append({"OS Version" : OSReleaseInfo["VERSION"]})

            try:
                with open('/proc/uptime', 'r') as f:
                    uptime_seconds = float(f.readline().split()[0])
                    uptime_string = str(datetime.timedelta(seconds = uptime_seconds))
                    LinuxInfo.append({"System Uptime" : uptime_string.split(".")[0] })   # remove microseconds
            except Exception as e1:
                pass

            try:
                adapter = os.popen("ip link | grep BROADCAST | grep -v NO-CARRIER | grep -m 1 LOWER_UP  | awk -F'[:. ]' '{print $3}'").readline().rstrip("\n")
                #output, _error = process.communicate()
                LinuxInfo.append({"Network Interface Used" : adapter})
                try:
                    if adapter.startswith('wl'):
                        LinuxInfo.extend(self.GetWiFiInfo(adapter))
                except Exception as e1:
                    pass
            except:
                pass
        except Exception as e1:
            self.LogErrorLine("Error in GetLinuxInfo: " + str(e1))

        return LinuxInfo

    #------------ MyPlatform::GetWiFiSignalStrength ----------------------------
    def GetWiFiSignalStrength(self, adapter):
        try:
            result = subprocess.check_output(['iw', adapter, 'link'])
            match = re.search('signal: -(\d+) dBm', result)
            return match.group(1)
        except Exception as e1:
            return ""

    #------------ MyPlatform::GetWiFiSignalQuality -----------------------------
    def GetWiFiSignalQuality(self, adapter):
        try:
            result = subprocess.check_output(['iwconfig', adapter])
            match = re.search('Link Quality=([\s\S]*?) ', result)
            return match.group(1)
        except Exception as e1:
            return ""

    #------------ MyPlatform::GetWiFiInfo --------------------------------------
    def GetWiFiInfo(self, adapter):

        WiFiInfo = []

        try:
            with open("/proc/net/wireless", "r") as f:
                for line in f:
                    if not adapter in line:
                        continue
                    ListItems = line.split()
                    if len(ListItems) > 4:
                        WiFiInfo.append({"WLAN Signal Level" : ListItems[3].replace(".", "") + " dBm"})
                        # Note that some WLAN drivers make this value based from 0 - 70, others are 0-100
                        # There is no standard on the range
                        try:
                            WiFiInfo.append({"WLAN Signal Quality" : self.GetWiFiSignalQuality(adapter)})
                        except:
                            WiFiInfo.append({"WLAN Signal Quality" : ListItems[2].replace(".", "")  + "/70"})

                        WiFiInfo.append({"WLAN Signal Noise" : ListItems[4].replace(".", "") + " dBm"})
        except Exception as e1:
            pass
        return WiFiInfo
