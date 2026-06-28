#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: otodata_discover.py
# PURPOSE: Discovery utility for Otodata TM5030, TM5040, and TM6030 Bluetooth
#          Low Energy propane tank sensors. Performs a BLE scan and displays
#          the MAC address, model, and current fill level of every Otodata
#          sensor found.
#
#          No button press is required — Otodata sensors broadcast their fill
#          level continuously. The device rotates through several advertisement
#          local names per cycle, e.g.:
#              "TM5040 28580758"     <- model / serial
#              "310410.1|0|-64"      <- raw sensor data
#              "level: 49.3 % horiz" <- fill level (what we want)
#          A 30-second scan window is used to ensure at least one level
#          advertisement is received from nearby sensors.
#
#          Use this utility to find your sensor's MAC address for optional use
#          in the genotodata addon configuration (mac_address setting).
#
#  AUTHOR: Brian Wilson
#    DATE: 2024
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import asyncio
import os
import re
import signal
import sys

# Adds higher directory to python modules path.
sys.path.append(os.path.dirname(sys.path[0]))

try:
    from bleak import BleakScanner
except Exception as e1:
    print("\n\nThis program is used to discover Otodata TM5030/TM5040/TM6030 propane tank sensors.")
    managedfile = (
        "/usr/lib/python"
        + str(sys.version_info.major)
        + "."
        + str(sys.version_info.minor)
        + "/EXTERNALLY-MANAGED"
    )
    if os.path.isfile(managedfile):
        print("\n\nYou appear to be running in a managed python environment. To run this program see this page: ")
        print("\n\n https://github.com/jgyates/genmon/wiki/Appendix-S---Working-in-a-Managed-Python-Environment\n")
    else:
        print("\nThe required python libraries are not installed. You must run the setup script first.\n")
        print("\n\n https://github.com/jgyates/genmon/wiki/3.3--Setup-genmon-software")
        print("\n\nError: " + str(e1))
    sys.exit(2)

LEVEL_REGEX = re.compile(r"level:\s*([0-9]+(?:\.[0-9]+)?)\s*%", re.IGNORECASE)
MODEL_REGEX = re.compile(r"\bTM[0-9]{4}\b", re.IGNORECASE)
SCAN_TIME = 30  # seconds — device cycles through several advertisement types per pass


# ----------SignalClose--------------------------------------------------------
def SignalClose(signum, frame):
    sys.exit(1)


# ------------------GetErrorInfo-------------------------------------------------
def GetErrorInfo():
    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    lineno = exc_tb.tb_lineno
    return fname + ":" + str(lineno)


# ------------------ScanForSensors-----------------------------------------------
async def ScanForSensors():
    discovered = {}

    def _callback(device, adv_data):
        addr = device.address.lower()

        # The device sends different local names in consecutive advertisement
        # packets. device.name is cached by BlueZ (typically the model name)
        # and does not update each packet, so we check adv_data.local_name
        # independently to catch the level advertisement.
        local = (adv_data.local_name if adv_data else None) or ""
        candidates = []
        if device.name:
            candidates.append(device.name)
        if local and local != device.name:
            candidates.append(local)

        for name in candidates:
            if not name:
                continue

            # Capture model name from "TM5030 XXXXXXXX" style advertisements
            m_model = MODEL_REGEX.search(name)
            if m_model:
                entry = discovered.setdefault(addr, {"address": device.address})
                if "model" not in entry:
                    entry["model"] = m_model.group(0).upper()

            # Capture fill level from "level: 49.3 % horiz" style advertisements
            m_level = LEVEL_REGEX.search(name)
            if m_level:
                entry = discovered.setdefault(addr, {"address": device.address})
                entry["level"] = float(m_level.group(1))

    scanner = BleakScanner(detection_callback=_callback)
    await scanner.start()
    await asyncio.sleep(SCAN_TIME)
    await scanner.stop()

    # Return only devices where a level reading was received
    return {k: v for k, v in discovered.items() if "level" in v}


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
        print("\nNOTE: This program will look for Otodata TM5030, TM5040, and TM6030 propane tank sensors.")
        print("      No button press is required. Sensors broadcast their level continuously.\n")
        print("Starting Discovery (%d seconds)..." % SCAN_TIME)
        try:
            loop = asyncio.new_event_loop()
            discovered = loop.run_until_complete(ScanForSensors())
            loop.close()
        except Exception as e1:
            print(
                "Error during BLE scan. Validate that Bluetooth is enabled: "
                + str(e1)
                + " "
                + GetErrorInfo()
            )
            print("\n")
            sys.exit(2)

        print("\nFinished Discovery. Found %d sensor(s):\n" % len(discovered))
        for sensor in discovered.values():
            print("Sensor Address: " + str(sensor["address"]))
            print("Model:          " + sensor.get("model", "Unknown"))
            print("Tank Level:     %.1f%%" % sensor["level"])
            print("\n")
        if discovered:
            print("Use the sensor address above as the mac_address parameter in the genotodata addon settings.")
            print("If mac_address is left blank, the addon will use the first Otodata sensor it finds.\n")
        else:
            print("No Otodata sensors found. If you have an Otodata sensor, ensure it is within")
            print("Bluetooth range of your system and try again.\n")
    except Exception as e1:
        print("Program Error (main): " + str(e1) + " " + GetErrorInfo())
        print("\n")
        sys.exit(2)
