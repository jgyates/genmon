# -------------------------------------------------------------------------------
#    FILE: mopekautility.py
# PURPOSE: app for mopeka pro sensor support
#
#  AUTHOR: Jason G Yates
#    DATE: 2-Aug-2022
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import os
import signal
import sys
import time
from subprocess import PIPE, Popen

# Adds higher directory to python modules path.
sys.path.append(os.path.dirname(sys.path[0]))  

try:
    import bleson
    from genmonlib.mymopeka import MopekaBT, ScanningMode
except Exception as e1:
    print("\n\nThis program is used to support using the Mopeka BT sensor with genmon.")

    managedfile = "/usr/lib/python" + str(sys.version_info.major) + "." + str(sys.version_info.minor) + "/EXTERNALLY-MANAGED"
    if os.path.isfile(managedfile):
        print("\n\nYou appear to be running in a managed python environemnt. To run this program see this page: ")
        print("\n\n  https://github.com/jgyates/genmon/wiki/Appendix-S---Working-in-a-Managed-Python-Environment\n")
    else:
        print("\nThe required python libraries are not installed. You must run the setup script first.\n")
        print("\n\n   https://github.com/jgyates/genmon/wiki/3.3--Setup-genmon-software")
    
    print("\n\nError: " + str(e1))
    sys.exit(2)


# ----------SignalClose--------------------------------------------------------
def SignalClose(signum, frame):

    sys.exit(1)


# -------------------------------------------------------------------------------
def CheckServiceOutput(Output):

    try:
        for line in iter(Output.splitlines()):
            if sys.version_info[0] >= 3:
                line = line.decode()
            if "Loaded:" in line:
                line = line.strip()
                lineitems = line.split(";")
                if len(lineitems) >= 2 and "disabled" in lineitems[1].lower():
                    return True
                else:
                    return False
        return False
    except Exception as e1:
        print("Program Error: (CheckServiceOutput): " + str(e1) + " " + GetErrorInfo())
        sys.exit(2)


# -------------------------------------------------------------------------------
def ServiceIsEnabled(servicename):
    try:
        process = Popen(["systemctl", "status", servicename], stdout=PIPE)
        output, _error = process.communicate()
        rc = process.returncode
        return not CheckServiceOutput(output)

    except Exception as e1:
        print("Program Error (ServiceIsEnabled): " + str(e1) + " " + GetErrorInfo())
        sys.exit(2)


# ------------------GetErrorInfo-------------------------------------------------
def GetErrorInfo():
    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    lineno = exc_tb.tb_lineno
    return fname + ":" + str(lineno)


# ------------------main---------------------------------------------------------
if __name__ == "__main__":

    if os.geteuid() != 0:
        print(
            "You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting."
        )
        sys.exit(2)

    try:

        signal.signal(signal.SIGTERM, SignalClose)
        signal.signal(signal.SIGINT, SignalClose)

        service = MopekaBT(mode = ScanningMode.DISCOVERY)

        print("\nNOTE: This program will look for Mopeka Pro Sensors. The SYNC button must be pressed and held for the discovery process to work.\n")
        print("Starting Discovery....")

        try:
            service.Start()
        except Exception as e1:
            print("Error starting discovery. Validate that Blootooth is enabled: " + str(e1) + " " + GetErrorInfo())
            print("\n")
            sys.exit(2)

        time.sleep(5)
        service.Stop()

        print("Discovery Stats: \n")
        print("\tProcessed Advertisments: " + str(service.processed_advertisments))
        print("\tIgnored Advertisments: " + str(service.ignored_advertisments))
        print("\tZero Length Advertisments: " + str(service.zero_lenght_advertisments))
        print(f"\nFinished Discovery.  Found {len(service.discovered_sensors)} new sensor(s):\n")

        for sensor in service.discovered_sensors.values():
            print("Sensor Address:  " + str(sensor.address))
            print("Battery Percentage:  " + str(sensor.last_reading.BatteryPercent) + "%%")
            print("Sensor Temperature:  " + str(sensor.last_reading.TemperatureInCelsius) + " C")
            print("Tank Level Reading:  " + str(sensor.last_reading.TankLevelInMM) + "mm")
            print("\n")

        if len(service.discovered_sensors):
            print("Use the sensor address above as the tank address parameter in the genmon add on settings.\n")

    except Exception as e1:
        print("Program Error (main): " + str(e1) + " " + GetErrorInfo())
        print("\n")
        sys.exit(2)
