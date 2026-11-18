#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: genlog.py
# PURPOSE: genmon.py support program to allow logging of generator
# run time
#
#  AUTHOR: Jason G Yates
#    DATE: 19-Apr-2016
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import os
import signal
import sys
import threading
import time
from datetime import datetime

try:
    # this will add the parent of the genmonlib folder to the path
    # if we are one level below the genmonlib parent (e.g. in the addon folder)
    file_root = os.path.dirname(os.path.realpath(__file__))
    parent_root = os.path.abspath(os.path.join(file_root, os.pardir))
    if os.path.isdir(os.path.join(parent_root, "genmonlib")):
        sys.path.insert(1, parent_root)

    from genmonlib.myclient import ClientInterface
    from genmonlib.myconfig import MyConfig
    from genmonlib.mycommon import MyCommon
    from genmonlib.mysupport import MySupport
    from genmonlib.mythread import MyThread
    from genmonlib.program_defaults import ProgramDefaults
except Exception as e1:
    print(
        "\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n"
    )
    print(
        "Please see the project documentation at https://github.com/jgyates/genmon.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)


# ------------ GenLog class -----------------------------------------------------
class GenLog(MySupport):

    # ------------ GenLog::init--------------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
        filename=None,
    ):

        super(GenLog, self).__init__()

        self.LogFileName = os.path.join(loglocation, "genlog.log")
        self.AccessLock = threading.Lock()
        # log errors in this module to a file
        self.log = log
        self.console = console

        self.MonitorAddress = host
        self.debug = False
        self.PollTime = 5
        self.LastEvent = ""
        self.Generator = None

        if self.MonitorAddress != None:
            self.MonitorAddress = self.MonitorAddress.strip()

        if self.MonitorAddress == None or not len(self.MonitorAddress):
            self.MonitorAddress = ProgramDefaults.LocalHost

        self.OutputFileName = self.GetOutputFileName(filename, ConfigFilePath)

        self.LogConsole("Address is " + self.MonitorAddress)
        self.LogConsole("Output file is " + self.OutputFileName)
        self.LogConsole("Config File Path is " + ConfigFilePath)

        if not len(self.OutputFileName):
            Message = "Missing output file name (filename in genlog.conf, or -f <outputfile>)"
            self.LogConsole(Message)
            self.LogError(Message)
            sys.exit(2)

        try:
            self.Generator = ClientInterface(
                host=self.MonitorAddress, port=port, log=self.log
            )

            # start thread to monitor and log generator state changes
            self.Threads["GenLogThread"] = MyThread(
                self.GenLogThread, Name="GenLogThread", start=False
            )
            self.Threads["GenLogThread"].Start()

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

        except Exception as e1:
            self.LogErrorLine("Error in GenLog init: " + str(e1))
            self.LogConsole("Error in GenLog init: " + str(e1))
            sys.exit(1)

    # ------------------- GenLog::GetOutputFileName -----------------------------
    # The file to log to: -f on the command line if given, otherwise filename in
    # genlog.conf
    def GetOutputFileName(self, filename, ConfigFilePath):

        if filename != None and len(filename.strip()):
            return filename.strip()
        try:
            ConfigFile = os.path.join(ConfigFilePath, "genlog.conf")
            if not os.path.isfile(ConfigFile):
                self.LogError("Missing config file " + ConfigFile)
                return ""
            config = MyConfig(filename=ConfigFile, section="genlog", log=self.log)
            return config.ReadValue("filename", default="").strip()
        except Exception as e1:
            self.LogErrorLine("Error reading genlog.conf: " + str(e1))
            return ""

    # ------------------- GenLog::ExcelDate -------------------------------------
    def ExcelDate(self, date1):
        temp = datetime(1899, 12, 30)  # Note, not 31st Dec but 30th!
        delta = date1 - temp
        return str(float(delta.days) + (float(delta.seconds) / 86400))

    # ------------------- GenLog::LogDataToFile ---------------------------------
    def LogDataToFile(self, fileName, logtime, Event):

        try:
            with open(fileName, "a") as LogFile:  # opens file
                if os.stat(fileName).st_size == 0:
                    LogFile.write("Time,Event\n")

                LogFile.write(self.ExcelDate(logtime) + "," + Event + "\n")
                LogFile.flush()
        except Exception as e1:
            self.LogErrorLine("Error in LogDataToFile: " + str(e1))

    # ----------  GenLog::SendCommand -------------------------------------------
    def SendCommand(self, Command):

        if len(Command) == 0:
            return "Invalid Command"

        try:
            with self.AccessLock:
                data = self.Generator.ProcessMonitorCommand(Command)
        except Exception:
            self.LogErrorLine("Error calling ProcessMonitorCommand: " + str(Command))
            data = ""

        return data

    # ---------- GenLog::GenLogThread--------------------------------------------
    def GenLogThread(self):

        while True:
            try:
                data = self.SendCommand("generator: getbase")

                if len(data) and self.LastEvent != data:
                    self.LastEvent = data
                    self.LogDataToFile(self.OutputFileName, datetime.now(), data)

                if self.WaitForExit("GenLogThread", float(self.PollTime)):
                    return

            except Exception as e1:
                self.LogErrorLine("Error in GenLogThread: " + str(e1))
                if self.WaitForExit("GenLogThread", float(self.PollTime)):
                    return

    # ----------GenLog::SignalClose----------------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(0)

    # ----------GenLog::Close----------------------------------------------------
    def Close(self):

        self.KillThread("GenLogThread")
        if self.Generator != None:
            self.Generator.Close()


# -------------------------------------------------------------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
        extra_args,
    ) = MySupport.SetupAddOnProgram(
        "genlog", extra_options={"f": ("filename", "<outputfile>")}
    )

    GenLogInstance = GenLog(
        log=log,
        loglocation=loglocation,
        ConfigFilePath=ConfigFilePath,
        host=address,
        port=port,
        console=console,
        filename=extra_args["filename"],
    )

    while True:
        time.sleep(0.5)

    sys.exit(1)
