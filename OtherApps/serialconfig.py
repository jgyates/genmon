# -------------------------------------------------------------------------------
#    FILE: serialconfig.py
# PURPOSE: app for serial port status / disable on raspberry pi
#
#  AUTHOR: Jason G Yates
#    DATE: 26-May-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

# https://www.raspberrypi.com/documentation/computers/configuration.html#configuring-uarts

import getopt
import os
import sys
import re
from shutil import copyfile
import subprocess
from subprocess import PIPE, Popen

BOOT_CONFIG = "/boot/config.txt"
CMD_LINE = "/boot/cmdline.txt"
CMD_LINE_SERIAL_CONSOLE = "console=serial0,115200"

SERIAL0 = "/dev/serial0"
GETTY_SERVICE_NAME = "serial-getty@ttys0.service"
HCIUART_SERVIE_NAME = "hciuart"
FileList = [BOOT_CONFIG, CMD_LINE]

# -------------------------------------------------------------------------------
def PreFileHousekeeping(FileName, Restore=False):
    try:
        # Note bak2 file is expendable, bak1 file is original file
        if Restore:
            if os.path.isfile(FileName + ".bak1"):
                copyfile(FileName + ".bak1", FileName)
                print("Restored %s to %s" % (FileName + ".bak1", FileName))
            else:
                print("Not backup file exist for " + FileName)
                return False
        else:
            if not os.path.isfile(FileName):
                print("Error: unable to locate " + FileName)
                return False

            if not os.path.isfile(FileName + ".bak1"):
                copyfile(FileName, FileName + ".bak1")
            else:
                print("Backup file already exist: " + FileName + ".bak1")
        return True
    except Exception as e1:
        print("Error: " + str(e1))
        return False


# ---------------------MySupport::AddItemToConfFile------------------------
# Add or update config item
def AddItemToConfFile(FileName, Entry, Value, Check=False):

    try:
        Found = False
        ConfigFile = open(FileName, "r")
        FileString = ConfigFile.read()
        ConfigFile.close()
        if not Check:
            ConfigFile = open(FileName, "w")
        for line in FileString.splitlines():
            if not line.isspace():  # blank lines
                newLine = line.strip()  # strip leading spaces
                if len(newLine):
                    if not newLine[0] == "#":  # not a comment
                        items = newLine.split(" ")  # split items in line by spaces
                        for strings in items:  # loop thru items
                            strings = strings.strip()  # strip any whitespace
                            if Entry == strings or strings.lower().startswith(
                                Entry + "="
                            ):  # is this our value?
                                valueindex = strings.find('=')
                                myvalue = strings[valueindex+1:]
                                if myvalue.lower() == Value:
                                    Found = True
                                break

            if not Check:
                ConfigFile.write(line + "\n")
        if not Found and not Check:
            # write entry at end
            ConfigFile.write(Entry + "=" + Value + "\n")
        ConfigFile.close()
        if Check:
            return Found
        return True

    except Exception as e1:
        print(
            "\nError writing config file: "
            + FileName
            + ": "
            + str(e1)
            + " "
            + GetErrorInfo()
        )
        sys.exit(2)


# ---------------------MySupport::RemoveItemFromConfFile------------------------
# Remoce config item or validate it is not there
def RemoveItemFromConfFile(FileName, Entry, Value, Check=False):

    try:
        Found = False
        ConfigFile = open(FileName, "r")
        FileString = ConfigFile.read()
        ConfigFile.close()
        if not Check:
            ConfigFile = open(FileName, "w")
        for line in FileString.splitlines():
            Found = False
            if not line.isspace():  # blank lines
                newLine = line.strip()  # strip leading spaces
                if len(newLine):
                    if not newLine[0] == "#":  # not a comment
                        items = newLine.split(" ")  # split items in line by spaces
                        for strings in items:  # loop thru items
                            strings = strings.strip()  # strip any whitespace
                            if Entry == strings or strings.lower().startswith(
                                Entry + "="
                            ):  # is this our value?
                                myitems = strings.split("=")
                                if (
                                    len(myitems) >= 2
                                    and myitems[1].strip().lower() == Value
                                ):
                                    Found = True
                                break
            if not Check:
                if not Found:
                    ConfigFile.write(line + "\n")
        if not Check:
            ConfigFile.close()
        if Check:
            return not Found

        return True

    except Exception as e1:
        print(
            "\nError in removing item from config file: "
            + FileName
            + ": "
            + str(e1)
            + " "
            + GetErrorInfo()
        )
        sys.exit(2)


# -------------------------------------------------------------------------------
def ProcessCmdLineFile(FileName, Entry, Check=True):

    try:
        Found = False
        ConfigFile = open(FileName, "r")
        FileString = ConfigFile.read()
        ConfigFile.close()

        if not Check:
            ConfigFile = open(FileName, "w")
        for line in FileString.splitlines():
            if Entry in line:
                if not Check:
                    line = line.replace(Entry, "")
                Found = True

            if not Check:
                ConfigFile.write(line + "\n")
        if not Check:
            ConfigFile.close()
            return True
        return not Found

    except Exception as e1:
        print(
            "\nError processing Files"
            + FileName
            + ": "
            + str(e1)
            + " "
            + GetErrorInfo()
        )
        sys.exit(2)


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


# -------------------------------------------------------------------------------
def ServiceIsDisabled(servicename):
    try:
        process = Popen(["systemctl", "status", servicename], stdout=PIPE)
        output, _error = process.communicate()
        rc = process.returncode
        return CheckServiceOutput(output)

    except Exception as e1:
        print("Program Error (ServiceIsDisabled): " + str(e1) + " " + GetErrorInfo())
        sys.exit(2)


# -------------------------------------------------------------------------------
def DisableService(servicename, enable=False):
    try:
        if not enable:
            process = Popen(["systemctl", "stop", servicename], stdout=PIPE)
            output, _error = process.communicate()
            rc = process.returncode
            process = Popen(["systemctl", "disable", servicename], stdout=PIPE)
            output, _error = process.communicate()
            rc = process.returncode
            return True
        else:
            process = Popen(["systemctl", "enable", servicename], stdout=PIPE)
            output, _error = process.communicate()
            rc = process.returncode
            return True
    except Exception as e1:
        print(
            "Program Error (DisableService): "
            + str(enable)
            + ": "
            + str(e1)
            + " "
            + GetErrorInfo()
        )
        sys.exit(2)
# ------------------FileContains------------------------------------------------
def FileContains(filename, search_string):

    if os.path.isfile(filename):
        with open(filename) as f:
            if search_string in f.read():
                return True
    return False
# ------------------CheckFileLocations------------------------------------------
def CheckFileLocations():
    global BOOT_CONFIG
    global CMD_LINE
    global FileList
    try:

        # check if /boot/config.txt or /boot/firmware/config.txt should be used
        # check if /boot/comdline.txt or /boot/firmware/cmdline.txt should be used
        if not os.path.isfile(BOOT_CONFIG):
            BOOT_CONFIG = "/boot/firmware/config.txt"
        else:
            if FileContains(BOOT_CONFIG,"DO NOT EDIT"):
                BOOT_CONFIG = "/boot/firmware/config.txt"
        if not os.path.isfile(CMD_LINE):
            CMD_LINE = "/boot/firmware/cmdline.txt"
        else:
            # it exist but should not be used.
            if FileContains(CMD_LINE,"DO NOT EDIT"):
                CMD_LINE = "/boot/firmware/cmdline.txt"
        
        FileList = []
        FileList.append(BOOT_CONFIG)
        FileList.append(CMD_LINE)
        print("\nUsing files: " + BOOT_CONFIG + " and " + CMD_LINE) 

    except Exception as e1:
        print("Error checking for file locations: " + str(e1))

# ------------------RestoreFiles------------------------------------------------
def RestoreFiles():

    print("Restoring...")
    for File in FileList:
        if not PreFileHousekeeping(File, Restore=True):
            print("Error restoring files, aborting.")
            return False

    print("Restore Complete.")
    return True


# ------------------GetErrorInfo-------------------------------------------------
def GetErrorInfo():
    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    lineno = exc_tb.tb_lineno
    return fname + ":" + str(lineno)

# ------------ UseLegacySerialEnable -------------------------------------------
def UseLegacySerialEnable():
    try:
        model = GetRaspberryPiModel()

        if model == None:
            return True 
        
        PiMajorVersion = re.search(r'\d+', model).group()
        if int(PiMajorVersion) >= 5:
            return False
        return True
    except Exception as e1:
        print("Error in UseLegacySerialEnable: " + GetErrorInfo())
        return False
# ------------ IsPlatformRaspberryPi -------------------------------------------
def IsPlatformRaspberryPi():
    try: 
        model = GetRaspberryPiModel()
        if model != None and "raspberry" in model.lower():
            return True 
        return False
    except Exception as e1:
        print("Error in IsPlatformRaspberryPi: " + GetErrorInfo())
        return False
# ------------ GetRaspberryPiModel ---------------------------------------------
def GetRaspberryPiModel():
    try:    
        process = Popen(["cat", "/proc/device-tree/model"], stdout=PIPE)
        output, _error = process.communicate()
        if sys.version_info[0] >= 3:
            output = output.decode("utf-8")
        return str(output.rstrip("\x00"))
    except Exception as e1:
        return None

# ------------------main---------------------------------------------------------
if __name__ == "__main__":

    HelpStr = "\npython3 serialconfig.py [-r -e -c -b]\n"
    HelpStr += "   Example: python3 serialconfig.py -e\n"
    HelpStr += "            python3 serialconfig.py -c\n"
    HelpStr += "\n      -e  Enable serial port"
    HelpStr += "\n      -r  Restore modified files"
    HelpStr += "\n      -c  Check status of serial port"
    HelpStr += "\n      -b  Leave Bluetooth enabled (Pi 3 and 4 only)"
    HelpStr += "\n      -d  Disable Bluetooth (may be needed on some pi models), default"
    HelpStr += "\n \n"

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hercb", [])
    except getopt.GetoptError:
        print(HelpStr)
        sys.exit(2)

    Check = False
    Enable = False
    Restore = False
    Bluetooth = False

    for opt, arg in opts:
        if opt == "-h":
            print(HelpStr)
            sys.exit()
        elif opt in ("-e", "--enable"):
            Enable = True
        elif opt in ("-r", "--restore"):
            Restore = True
        elif opt in ("-c", "--check"):
            Check = True
        elif opt in ("-b", "--bluetooth"):
            Bluetooth = True
        elif opt in ("-d", "--disablebluetooth"):
            Bluetooth = False

    if Check and Enable or Check and Restore or Enable and Restore:
        print("\nOnly one option can be selected.")
        sys.exit(2)

    if not Check and not Enable and not Restore:
        print("\nNo option selected.")
        print(HelpStr)
        sys.exit(2)

    if os.geteuid() != 0:
        print(
            "You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting."
        )
        sys.exit(2)

    if not IsPlatformRaspberryPi():
        print("Expecting a Raspberry Pi platform. Pi not detected. Exiting.")
        sys.exit(2)

    CheckFileLocations()

    for File in FileList:
        if not os.path.isfile(File):
            print("Error: unable to find file " + File)
            sys.exit(2)

    bUseLegacy = UseLegacySerialEnable()
    if not bUseLegacy:
        Bluetooth = False

    print("\nModel: " + GetRaspberryPiModel())

    if Restore:
        if RestoreFiles():
            sys.exit(0)
        sys.exit(1)

    if Enable:
        for File in FileList:
            if not PreFileHousekeeping(File):
                print("Error backing up files, aborting.")
                sys.exit(2)

    print("")

    try:
        if Bluetooth:
            EnableDict = {
                "Enable UART": [
                    AddItemToConfFile,
                    (BOOT_CONFIG, "enable_uart", "1", False),
                ],
                "Change BT serial port": [
                    AddItemToConfFile,
                    (BOOT_CONFIG, "dtoverlay", "miniuart-bt", False),
                ],
                "Enable Turbo clocking": [
                    AddItemToConfFile,
                    (BOOT_CONFIG, "force_turbo", "1", False),
                ],
                "Disable BT Disable Overlay": [
                    RemoveItemFromConfFile,
                    (BOOT_CONFIG, "dtoverlay", "disable-bt", False),
                ],
                "Disable serial console": [
                    ProcessCmdLineFile,
                    (CMD_LINE, CMD_LINE_SERIAL_CONSOLE, False),
                ],
                "Disable serial console service": [
                    DisableService,
                    (GETTY_SERVICE_NAME,),
                ],
                "Enable BT service service": [
                    DisableService,
                    (HCIUART_SERVIE_NAME, True),
                ],
            }

            CheckDict = {
                "Checking : Is enable UART in boot config": [
                    AddItemToConfFile,
                    (BOOT_CONFIG, "enable_uart", "1", True),
                ],
                "Checking : BT alternate serial port": [
                    AddItemToConfFile,
                    (BOOT_CONFIG, "dtoverlay", "miniuart-bt", True),
                ],
                "Checking : Turbo Clocking": [
                    AddItemToConfFile,
                    (BOOT_CONFIG, "force_turbo", "1", True),
                ],
                "Checking : Disable BT Disable Overlay": [
                    RemoveItemFromConfFile,
                    (BOOT_CONFIG, "dtoverlay", "disable-bt", True),
                ],
                "Checking : Serial console command line removed": [
                    ProcessCmdLineFile,
                    (CMD_LINE, CMD_LINE_SERIAL_CONSOLE, True),
                ],
                "Checking : Serial console service disabled": [
                    ServiceIsDisabled,
                    (GETTY_SERVICE_NAME,),
                ],
                "Checking : BT service enabled": [
                    ServiceIsEnabled,
                    (HCIUART_SERVIE_NAME,),
                ],
            }
        else:
            if bUseLegacy:
                EnableDict = {
                    "Enable UART": [
                        AddItemToConfFile,
                        (BOOT_CONFIG, "enable_uart", "1", False),
                    ],
                    "Change BT serial port": [
                        AddItemToConfFile,
                        (BOOT_CONFIG, "dtoverlay", "miniuart-bt", False),
                    ],
                    "Disable BT": [
                        AddItemToConfFile,
                        (BOOT_CONFIG, "dtoverlay", "disable-bt", False),
                    ],
                    "Disable serial console": [
                        ProcessCmdLineFile,
                        (CMD_LINE, CMD_LINE_SERIAL_CONSOLE, False),
                    ],
                    "Disable serial console service": [
                        DisableService,
                        (GETTY_SERVICE_NAME,),
                    ],
                    "Disable BT service service": [DisableService, (HCIUART_SERVIE_NAME,)],
                }

                CheckDict = {
                    "Checking : Is enable UART in boot config": [
                        AddItemToConfFile,
                        (BOOT_CONFIG, "enable_uart", "1", True),
                    ],
                    "Checking : Is BT overlay disabled": [
                        AddItemToConfFile,
                        (BOOT_CONFIG, "dtoverlay", "disable-bt", True),
                    ],
                    "Checking : Serial console command line removed": [
                        ProcessCmdLineFile,
                        (CMD_LINE, CMD_LINE_SERIAL_CONSOLE, True),
                    ],
                    "Checking : Serial console service disabled": [
                        ServiceIsDisabled,
                        (GETTY_SERVICE_NAME,),
                    ],
                    "Checking : BT service disabled": [
                        ServiceIsDisabled,
                        (HCIUART_SERVIE_NAME,),
                    ],
                }
            else: # not not use legacy
                EnableDict = {
                    "Enable UART": [
                        AddItemToConfFile,
                        (BOOT_CONFIG, "dtparam", "uart0=on", False),
                    ]
                }

                CheckDict = {
                    "Checking : Is enable UART in boot config": [
                        AddItemToConfFile,
                        (BOOT_CONFIG, "dtparam", "uart0=on", True),
                    ],
                }
        if Check:
            Lookup = CheckDict
        else:
            Lookup = EnableDict

        CheckCount = 0
        for key, ListItems in Lookup.items():

            ReturnValue = ListItems[0](*ListItems[1])

            if ReturnValue:
                CheckCount += 1
            if Check:
                status = "OK" if ReturnValue else "Fail"
            else:
                status = "Success" if ReturnValue else "Failure"
            print(key + ": " + status)

        if CheckCount == len(Lookup):
            print(
                "\nSerial port settings are OK. A reboot is needed if changes were made.\n"
            )
            sys.exit(0)
        else:
            print(
                "\nSerial port may not work as expected. Not all required settings changes were detected.\n"
            )
            sys.exit(2)
    except Exception as e1:
        print("Program Error (main): " + str(e1) + " " + GetErrorInfo())
        sys.exit(2)
