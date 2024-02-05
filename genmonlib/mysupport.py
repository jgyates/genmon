#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: mysupport.py
# PURPOSE: support functions in major classes
#
#  AUTHOR: Jason G Yates
#    DATE: 21-Apr-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import collections
import getopt
import os
import socket
import sys
import threading
import time
import re

from genmonlib.mycommon import MyCommon
from genmonlib.myconfig import MyConfig
from genmonlib.mylog import SetupLogger
from genmonlib.myplatform import MyPlatform
from genmonlib.program_defaults import ProgramDefaults

# Fix Python 2.x. unicode type
if sys.version_info[0] >= 3:  # PYTHON 3
    unicode = str
# ------------ MySupport class --------------------------------------------------
class MySupport(MyCommon):
    def __init__(self, simulation=False):
        super(MySupport, self).__init__()
        self.Simulation = simulation
        self.CriticalLock = threading.Lock()  # Critical Lock (writing conf file)

    # ------------ MySupport::LogToFile------------------------------------------
    def LogToFile(self, File, *argv):
        if self.Simulation:
            return
        if not len(File):
            return ""

        if not len(argv):
            return ""
        try:
            modarg = []
            # remove any non printable chars
            for arg in argv:
                arg = self.removeNonPrintable(arg)
                if len(arg):
                    modarg.append(arg)
            outdata = ","
            outdata = outdata.join(modarg) + "\n"
            with open(File, "a") as LogFile:  # opens file
                LogFile.write(outdata)
                LogFile.flush()
        except Exception as e1:
            self.LogError("Error in  LogToFile : File: %s: %s " % (File, str(e1)))

    # ------------ MySupport::CopyFile-------------------------------------------
    @staticmethod
    def CopyFile(source, destination, move=False, log=None):

        try:
            if not os.path.isfile(source):
                if log != None:
                    log.error("Error in CopyFile : source file not found.")
                return False

            path = os.path.dirname(destination)
            if not os.path.isdir(path):
                if log != None:
                    log.error("Creating " + path)
                os.mkdir(path)
            with os.fdopen(os.open(source, os.O_RDONLY), "r") as source_fd:
                data = source_fd.read()
                with os.fdopen(
                    os.open(destination, os.O_CREAT | os.O_RDWR), "w"
                ) as dest_fd:
                    dest_fd.write(data)
                    dest_fd.flush()
                    os.fsync(dest_fd)

            if move:
                os.remove(source)
            return True
        except Exception as e1:
            if log != None:
                log.error("Error in CopyFile : " + str(source) + " : " + str(e1))
            return False

    # ------------ MySupport::GetSiteName----------------------------------------
    def GetSiteName(self):
        return self.SiteName

    # ------------------------ MySupport::IsLoaded -----------------------------
    # return true if program is already loaded
    def IsLoaded(self):

        Socket = None

        try:
            # create an INET, STREAMing socket
            Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # now connect to the server on our port
            Socket.connect((ProgramDefaults.LocalHost, self.ServerSocketPort))
            Socket.close()
            return True
        except Exception as e1:
            if Socket != None:
                Socket.close()
            return False

    # ------------ MySupport::GetPlatformStats ----------------------------------
    def GetPlatformStats(self, usemetric=None, JSONNum=False):

        if not usemetric == None:
            bMetric = usemetric
        else:
            bMetric = self.UseMetric
        Platform = MyPlatform(self.log, bMetric)

        return Platform.GetInfo(JSONNum=JSONNum)

    # ----------  MySupport::RegExIsValid---------------------------------
    def RegExIsValid(self, input_str):
        try:
            re.compile(input_str)
            return True
        except Exception as e1:
            return False
    # ---------- MySupport::InternetConnected------------------------------------
    # Note: this function, if the internet connection is not present could
    # take some time to complete due to the network timeout
    def InternetConnected(self):
        try:
            if MyPlatform.InternetConnected():
                Status = "OK"
            else:
                Status = "Disconnected"

            return Status
        except Exception as e1:
            return "Unknown" + ":" + str(e1)

    # ---------- MySupport::GetDeadThreadName------------------------------------
    def GetDeadThreadName(self):

        RetStr = ""
        ThreadNames = ""
        for Name, MyThreadObj in self.Threads.items():
            ThreadNames += Name + " "
            if not MyThreadObj.IsAlive():
                RetStr += MyThreadObj.Name() + " "

        if RetStr == "":
            RetStr = "All threads alive: " + ThreadNames

        return RetStr

    # ---------- MySupport::KillThread------------------------------------------
    def KillThread(self, Name, CleanupSelf=False):

        try:
            MyThreadObj = self.Threads.get(Name, None)
            if MyThreadObj == None:
                self.LogError("Error getting thread name in KillThread: " + Name)
                return False

            if not CleanupSelf:
                MyThreadObj.Stop()
                MyThreadObj.WaitForThreadToEnd()
        except Exception as e1:
            self.LogError("Error in KillThread ( " + Name + "): " + str(e1))
            return

    # ---------------------MySupport::StartAllThreads----------------------------
    def StartAllThreads(self):

        for key, ThreadInfo in self.Threads.items():
            ThreadInfo.Start()

    # ---------- MySupport:: AreThreadsAlive-------------------------------------
    # ret true if all threads are alive
    def AreThreadsAlive(self):

        for Name, MyThreadObj in self.Threads.items():
            if not MyThreadObj.IsAlive():
                return False

        return True

    # ---------- MySupport::IsStopSignaled--------------------------------------
    def IsStopSignaled(self, Name):

        Thread = self.Threads.get(Name, None)
        if Thread == None:
            self.LogError("Error getting thread name in IsStopSignaled: " + Name)
            return False

        return Thread.StopSignaled()

    # ---------- MySupport::WaitForExit-----------------------------------------
    def WaitForExit(self, Name, timeout=None):

        Thread = self.Threads.get(Name, None)
        if Thread == None:
            self.LogError("Error getting thread name in WaitForExit: " + Name)
            return False

        return Thread.Wait(timeout)

    # ------------ MySupport::UnitsOut ------------------------------------------
    # output data based on the NoString flag, in put is a string value with units
    def UnitsOut(self, input, type=None, NoString=False):

        try:
            if not NoString:
                return input
            InputArray = input.strip().split(" ")
            if len(InputArray) == 1:
                return input
            if len(InputArray) == 2 or len(InputArray) == 3:
                if (
                    len(InputArray) == 3
                ):  # this handles two word untis like 'cubic feet'
                    InputArray[1] = InputArray[1] + " " + InputArray[2]
                if type == int:
                    InputArray[0] = int(InputArray[0])
                elif type == float:
                    InputArray[0] = float(InputArray[0])
                else:
                    self.LogError("Invalid type for UnitsOut: " + input)
                    return input
                return self.ValueOut(
                    value=InputArray[0], unit=InputArray[1], NoString=NoString
                )
            else:
                self.LogError("Invalid input for UnitsOut: " + input)
                return input
        except Exception as e1:
            self.LogErrorLine("Error in SplitUnits: " + str(e1))
            return input

    # ------------ MySupport::ValueOut ------------------------------------------
    # output data based on NoString flag, either return a string with a unit or a
    # numeric value
    def ValueOut(self, value, unit, NoString=False):
        try:

            if NoString:
                ReturnDict = collections.OrderedDict()
                ReturnDict["unit"] = unit
                DefaultReturn = ReturnDict
            else:
                DefaultReturn = ""
            if isinstance(value, int):
                if not NoString:
                    return "%d %s" % (int(value), str(unit))
                else:
                    ReturnDict["type"] = "int"
                    ReturnDict["value"] = value
                    return ReturnDict
            elif isinstance(value, float):
                if not NoString:
                    return "%.2f %s" % (float(value), str(unit))
                else:
                    ReturnDict["type"] = "float"
                    ReturnDict["value"] = round(value, 2)
                    return ReturnDict
            elif sys.version_info[0] < 3 and isinstance(value, long):
                if not NoString:
                    return "%d %s" % (int(value), str(unit))
                else:
                    ReturnDict["type"] = "long"
                    ReturnDict["value"] = value
                    return ReturnDict
            else:
                self.LogError(
                    "Unsupported type in ValueOut: "
                    + str(type(value))
                    + " : "
                    + str(unit)
                    + " : "
                    + str(value)
                )
                return DefaultReturn
        except Exception as e1:
            self.LogErrorLine("Error in ValueOut: " + str(e1))
            return DefaultReturn

    # -------------MySupport:GetIntFromString------------------------------------
    def GetIntFromString(self, input_string, byte_offset, length=1, decimal=False):

        try:
            if len(input_string) < byte_offset + length:
                self.LogError(
                    "Invalid length in GetIntFromString: " + str(input_string)
                )
                return 0
            StringOffset = byte_offset * 2
            StringOffsetEnd = StringOffset + (length * 2)
            if StringOffset == StringOffsetEnd:
                if decimal:
                    return int(input_string[StringOffset])
                return int(input_string[StringOffset], 16)
            else:
                if decimal:
                    return int(input_string[StringOffset:StringOffsetEnd])
                return int(input_string[StringOffset:StringOffsetEnd], 16)
        except Exception as e1:
            self.LogErrorLine("Error in GetIntFromString: " + str(e1))
            return 0

    # ----------  MySupport::HexStringToString  ---------------------------------
    def HexStringToString(self, input):

        try:
            if not len(input):
                return ""
            if not self.StringIsHex(input):
                return ""
            ByteArray = bytearray.fromhex(input)
            if ByteArray[0] == 0:
                return ""
            End = ByteArray.find(b"\0")
            if End != -1:
                ByteArray = ByteArray[:End]
            return str(ByteArray.decode("ascii"))
        except Exception as e1:
            if self.debug:
                self.LogErrorLine("Error in HexStringToString: " + str(e1))
            return ""

    # ----------  MySupport::StringIsHex  ---------------------------------------
    def StringIsHex(self, input):
        try:
            if " " in input:
                return False
            int(input, 16)
            return True
        except:
            return False

    # ------------ MySupport::GetDispatchItem -----------------------------------
    def GetDispatchItem(self, item, key=None):

        NoneType = type(None)

        if isinstance(item, str):
            return item
        if sys.version_info[0] < 3 and isinstance(item, unicode):
            return str(item)
        elif callable(item):
            return item()
        elif isinstance(item, int):
            return str(item)
        elif sys.version_info[0] < 3 and isinstance(item, (int, long)):
            return str(item)
        elif isinstance(item, float):
            return str(item)
        elif sys.version_info[0] >= 3 and isinstance(item, (bytes)):
            return str(item)
        elif isinstance(item, NoneType):
            return "None"
        else:
            self.LogError(
                "Unable to convert type %s in GetDispatchItem" % str(type(item))
            )
            self.LogError("Item: " + str(key) + ":" + str(item))
            return ""
        
    # ------------ MySupport::IsString -----------------------------------------
    def IsString(self, inputvalue):

        try:
            temp = inputvalue.lower()
            return True
        except:
            return False
    # ------------ MySupport::ProcessDispatch -----------------------------------
    # This function is recursive, it will turn a dict with callable functions into
    # all of the callable functions resolved to stings (by calling the functions).
    # If string output is needed instead of a dict output, ProcessDispatchToString
    # is called
    def ProcessDispatch(self, node, InputBuffer, indent=0):

        if isinstance(InputBuffer, str):
            return self.ProcessDispatchToString(node, InputBuffer, indent)

        if isinstance(node, dict):
            for key, item in node.items():
                if isinstance(item, dict):
                    NewDict = collections.OrderedDict()
                    InputBuffer[key] = self.ProcessDispatch(item, NewDict)
                elif isinstance(item, list):
                    InputBuffer[key] = []
                    for listitem in item:
                        if isinstance(listitem, dict):
                            NewDict2 = collections.OrderedDict()
                            InputBuffer[key].append(
                                self.ProcessDispatch(listitem, NewDict2)
                            )
                        else:
                            self.LogError(
                                "Invalid type in ProcessDispatch %s " % str(type(node))
                            )
                else:
                    InputBuffer[key] = self.GetDispatchItem(item, key=key)
        else:
            self.LogError("Invalid type in ProcessDispatch %s " % str(type(node)))

        return InputBuffer

    # ------------ MySupport::ProcessDispatchToString --------------------------
    # This function is recursive, it will turn a dict with callable functions into
    # a printable string with indentation and formatting
    def ProcessDispatchToString(self, node, InputBuffer, indent=0):

        if not isinstance(InputBuffer, str):
            return ""

        if isinstance(node, dict):
            for key, item in node.items():
                if isinstance(item, dict):
                    InputBuffer += "\n" + ("    " * indent) + str(key) + " : \n"
                    InputBuffer = self.ProcessDispatchToString(
                        item, InputBuffer, indent + 1
                    )
                elif isinstance(item, list):
                    InputBuffer += "\n" + ("    " * indent) + str(key) + " : \n"
                    for listitem in item:
                        if isinstance(listitem, dict):
                            InputBuffer = self.ProcessDispatchToString(
                                listitem, InputBuffer, indent + 1
                            )
                        elif isinstance(listitem, str) or isinstance(listitem, unicode):
                            InputBuffer += (
                                ("    " * (indent + 1))
                                + self.GetDispatchItem(listitem, key=key)
                                + "\n"
                            )
                        else:
                            self.LogError(
                                "Invalid type in ProcessDispatchToString %s %s (2)"
                                % (key, str(type(listitem)))
                            )
                    if len(item) > 1:
                        InputBuffer += "\n"
                else:
                    InputBuffer += (
                        ("    " * indent)
                        + str(key)
                        + " : "
                        + self.GetDispatchItem(item, key=key)
                        + "\n"
                    )
        else:
            self.LogError(
                "Invalid type in ProcessDispatchToString %s " % str(type(node))
            )
        return InputBuffer

    # ----------  Controller::GetNumBitsChanged----------------------------------
    def GetNumBitsChanged(self, FromValue, ToValue):

        if not len(FromValue) or not len(ToValue):
            return 0, 0
        MaskBitsChanged = int(FromValue, 16) ^ int(ToValue, 16)
        NumBitsChanged = MaskBitsChanged
        count = 0
        while NumBitsChanged:
            count += NumBitsChanged & 1
            NumBitsChanged >>= 1

        return count, MaskBitsChanged

    # ----------  MySupport::GetDeltaTimeMinutes-------------------------------
    def GetDeltaTimeMinutes(self, DeltaTime):

        try:
            total_sec = DeltaTime.total_seconds()
            return int(total_sec / 60)
        except:
            days, seconds = float(DeltaTime.days), float(DeltaTime.seconds)
            delta_hours = days * 24.0 + seconds // 3600.0
            delta_minutes = (seconds % 3600.0) // 60.0

            return delta_hours * 60.0 + delta_minutes

    # ---------------------MySupport::ReadCSVFile--------------------------------
    # read a CSV file, return a list of lists
    # lines starting with # will be ignored as they will treated as comments
    def ReadCSVFile(self, FileName):
        try:
            ReturnedList = []
            with open(FileName, "r") as CSVFile:
                for line in CSVFile:
                    line = (
                        line.strip()
                    )  # remove newline at beginning / end and trailing whitespace
                    if not len(line):
                        continue
                    if line[0] == "#":  # comment?
                        continue
                    Items = line.split(",")
                    ReturnedList.append(Items)

            return ReturnedList
        except Exception as e1:
            self.LogErrorLine("Error in ReadCSVFile: " + FileName + " : " + str(e1))
            return []

    # ------------ MySupport::GetWANIp-------------------------------------------
    def GetWANIp(self):

        try:
            import requests

            ip = requests.get("http://ipinfo.io/json").json()["ip"]
            return ip.strip()
        except Exception as e1:
            self.LogErrorLine("Error getting WAN IP: " + str(e1))
            return "Unknown"

    # ------------ MySupport::GetNetworkIp---------------------------------------
    def GetNetworkIp(self):
        try:
            return str(
                (
                    (
                        [
                            ip
                            for ip in socket.gethostbyname_ex(socket.gethostname())[2]
                            if not ip.startswith("127.")
                        ]
                        or [
                            [
                                (
                                    s.connect(("8.8.8.8", 53)),
                                    s.getsockname()[0],
                                    s.close(),
                                )
                                for s in [
                                    socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                                ]
                            ][0][1]
                        ]
                    )
                    + ["no IP found"]
                )[0]
            )
        except:
            return "Unknown"

    # ------------ MySupport::IsRunning------------------------------------------
    @staticmethod
    def IsRunning(prog_name, log=None, multi_instance=False):

        if multi_instance:  # do we allow multiple instances
            return False  # return False so the program will load anyway
        try:
            import psutil
        except:
            return False  # incase psutil is not installed load anyway
        try:
            prog_name = os.path.basename(prog_name)
            for q in psutil.process_iter():
                if q.name().lower().startswith("python"):
                    if len(q.cmdline()) > 1:
                        script_name = os.path.basename(q.cmdline()[1])
                        if (
                            len(q.cmdline()) > 1
                            and prog_name == script_name
                            and q.pid != os.getpid()
                        ):
                            return True
        except Exception as e1:
            if log != None:
                log.error(
                    "Error in IsRunning: " + str(e1) + ": " + MySupport.GetErrorLine()
                )
                return True
        return False

    # ---------------------MySupport::GetErrorLine--------------------------------
    @staticmethod
    def GetErrorLine():
        exc_type, exc_obj, exc_tb = sys.exc_info()
        if exc_tb == None:
            return ""
        else:
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            lineno = exc_tb.tb_lineno
            return fname + ":" + str(lineno)

    # ------------ MySupport::SetupAddOnProgram----------------------------------
    @staticmethod
    def SetupAddOnProgram(prog_name):
        console = SetupLogger(prog_name + "_console", log_file="", stream=True)

        if not MySupport.PermissionsOK():
            console.error(
                "\nYou need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.\n"
            )
            sys.exit(2)

        HelpStr = (
            "\nsudo python "
            + prog_name
            + ".py -a <IP Address or localhost> -c <path to "
            + prog_name
            + " config file>\n"
        )

        ConfigFilePath = ProgramDefaults.ConfPath
        address = ProgramDefaults.LocalHost

        try:
            opts, args = getopt.getopt(
                sys.argv[1:], "hc:a:", ["help", "configpath=", "address="]
            )
        except getopt.GetoptError:
            console.error("Invalid command line argument.")
            sys.exit(2)

        for opt, arg in opts:
            if opt == "-h":
                console.error(HelpStr)
                sys.exit()
            elif opt in ("-a", "--address"):
                address = arg
            elif opt in ("-c", "--configpath"):
                ConfigFilePath = arg.strip()

        try:
            port, loglocation, multi_instance = MySupport.GetGenmonInitInfo(
                ConfigFilePath, log=console
            )
            log = SetupLogger(
                "client_" + prog_name, os.path.join(loglocation, prog_name + ".log")
            )

            if not prog_name.lower().endswith(".py"):
                prog_name += ".py"

            attempts = 0
            while True:
                if MySupport.IsRunning(
                    prog_name=prog_name, log=log, multi_instance=multi_instance
                ):
                    if attempts >= 4:
                        raise Exception("The program %s is already loaded" % prog_name)
                    else:
                        attempts += 1
                        time.sleep(1)
                else:
                    break

        except Exception as e1:
            console.error("Error : " + str(e1))
            log.error("Error : " + str(e1) + ": " + MySupport.GetErrorLine())
            sys.exit(1)

        return console, ConfigFilePath, address, port, loglocation, log

    # ---------------------MySupport::GetGenmonInitInfo--------------------------
    @staticmethod
    def GetGenmonInitInfo(configfilepath=MyCommon.DefaultConfPath, log=None):

        if configfilepath == None or configfilepath == "":
            configfilepath = MyCommon.DefaultConfPath

        config = MyConfig(
            os.path.join(configfilepath, "genmon.conf"), section="GenMon", log=log
        )
        loglocation = config.ReadValue("loglocation", default=ProgramDefaults.LogPath)
        port = config.ReadValue(
            "server_port", return_type=int, default=ProgramDefaults.ServerPort
        )
        multi_instance = config.ReadValue(
            "multi_instance", return_type=bool, default=False
        )
        return port, loglocation, multi_instance

    # ---------------------MySupport::PermissionsOK------------------------------
    @staticmethod
    def PermissionsOK():

        if MyPlatform.IsOSLinux() and os.geteuid() == 0:
            return True
        if MyPlatform.IsOSWindows():
            return True
        else:
            return False
