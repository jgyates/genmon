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
import os, sys, subprocess, re
import collections
import mycommon

#------------ MyPlatform class -------------------------------------------------
class MyPlatform(mycommon.MyCommon):

    #------------ MyPlatform::init----------------------------------------------
    def __init__(self, log = None):
        self.log = log

    #------------ MyPlatform::GetInfo-------------------------------------------
    def GetInfo(self):

        PlatformInfo = self.GetPlatformInfo()
        OSInfo = self.GetOSInfo()

        if OSInfo == None and PlatformInfo == None:
            return {}

        if PlatformInfo == None:
            return OSInfo
        if OSInfo == None:
            return PlatformInfo

        return self.MergeDicts(PlatformInfo, OSInfo)

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

    #------------ MyPlatform::GetRaspberryPiInfo -------------------------------
    def GetRaspberryPiInfo(self):

        if not self.IsPlatformRaspberryPi():
            return None
        PiInfo = collections.OrderedDict()

        try:
            try:
                process = Popen(['/opt/vc/bin/vcgencmd', 'measure_temp'], stdout=PIPE)
                output, _error = process.communicate()
                PiInfo["CPU Temperature"] = "%.2f C" % float(output[output.index('=') + 1:output.rindex("'")])
            except Exception as e1:
                # for non rasbpian based systems
                process = Popen(['cat', '/sys/class/thermal/thermal_zone0/temp'], stdout=PIPE)
                output, _error = process.communicate()
                TempStr = str(float(output) / 1000) + " C"
                PiInfo["CPU Temperature"] = TempStr

            try:
                process = Popen(['cat', '/proc/device-tree/model'], stdout=PIPE)
                output, _error = process.communicate()
                PiInfo["Pi Model"] = str(output.encode('ascii', 'ignore')).rstrip("\x00")
            except:
                pass
            try:
                file = open("/sys/devices/platform/soc/soc:firmware/get_throttled")
                status = file.read()
                PiInfo = self.MergeDicts(PiInfo, self.ParseThrottleStatus(int(status, 16)))
            except Exception as e1:
                pass

        except Exception as e1:
            self.LogErrorLine("Error in GetRaspberryPiInfo: " + str(e1))

        return PiInfo

    #------------ MyPlatform::ParseThrottleStatus ------------------------------
    def ParseThrottleStatus(self, status):

        PiThrottleInfo = collections.OrderedDict()

        StatusStr = ""

        if (status & 0x40000):
            StatusStr += "Has occured. "
        if (status & 0x4):
            StatusStr += "Throttling Active. "

        if StatusStr == "":
            StatusStr += "OK"

        PiThrottleInfo["Pi CPU Frequecy Throttling"] = StatusStr

        StatusStr = ""
        if (status & 0x20000):
            StatusStr += "Has occured. "
        if (status & 0x2):
            StatusStr += "ARM frequency capped. "

        if StatusStr == "":
            StatusStr += "OK"

        PiThrottleInfo["Pi ARM Frequency Cap"] = StatusStr

        StatusStr = ""
        if (status & 0x10000):
            StatusStr += "Has occured. "
        if (status & 0x1):
            StatusStr += "Undervoltage Detected. "

        if StatusStr == "":
            StatusStr += "OK"

        PiThrottleInfo["Pi Undervoltage"] = StatusStr
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
        LinuxInfo = collections.OrderedDict()

        try:
            CPU_Pct=str(round(float(os.popen('''grep 'cpu ' /proc/stat | awk '{usage=($2+$4)*100/($2+$4+$5)} END {print usage }' ''').readline()),2))
            if len(CPU_Pct):
                LinuxInfo["CPU Utilization"] = CPU_Pct + "%"
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
                LinuxInfo["OS Name"] = OSReleaseInfo["NAME"]
                LinuxInfo["OS Version"] = OSReleaseInfo["VERSION"]

            try:
                adapter = os.popen("ip link | grep BROADCAST | grep -v NO-CARRIER | grep -m 1 LOWER_UP  | awk -F'[:. ]' '{print $3}'").readline().rstrip("\n")
                #output, _error = process.communicate()
                LinuxInfo["Network Interface Used"] = adapter
                try:
                    if "wlan" in adapter:
                        LinuxInfo = self.MergeDicts(LinuxInfo, self.GetWiFiInfo(adapter))
                except Exception as e1:
                    pass
            except:
                pass
        except Exception as e1:
            self.LogErrorLine("Error in GetLinuxInfo: " + str(e1))

        return LinuxInfo

    #------------ MyPlatform::GetWiFiSignalStrength ----------------------------
    def GetWiFiSignalStrength(self, adapter):
        result = subprocess.check_output(['sudo', 'iw', adapter, 'link'])
        match = re.search('signal: -(\d+) dBm', result)
        return match.group(1)

    #------------ MyPlatform::GetWiFiSignalQuality -----------------------------
    def GetWiFiSignalQuality(self, adapter):
        result = subprocess.check_output(['sudo', 'iwconfig', adapter])
        match = re.search('Link Quality=([\s\S]*?) ', result)
        return match.group(1)

    #------------ MyPlatform::GetWiFiSignalQuality -----------------------------
    def GetWiFiInfo(self, adapter):

        WiFiInfo = collections.OrderedDict()

        try:
            with open("/proc/net/wireless", "r") as f:
                for line in f:
                    if not adapter in line:
                        continue
                    ListItems = line.split()
                    if len(ListItems) > 4:
                        WiFiInfo["WLAN Signal Level"] = ListItems[3].replace(".", "") + " dBm"
                        WiFiInfo["WLAN Signal Quality"] = ListItems[2].replace(".", "") + "/70"
                        WiFiInfo["WLAN Signal Noise"] = ListItems[4].replace(".", "") + " dBm"
        except Exception as e1:
            pass
        return WiFiInfo
