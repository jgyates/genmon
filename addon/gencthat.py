#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: gencthat.py
# PURPOSE: gencthat.py add external current transformers via a RPi hat
#
#  AUTHOR: jgyates
#    DATE: 12-07-2021
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------


import datetime
import json
import os
import signal
import sys
import threading
import time
from shutil import copyfile

try:
    from spidev import SpiDev
except Exception as e1:
    print("\n\nThis program requires the spidev module to be installed.\n")
    print("Error: " + str(e1))
    sys.exit(2)

try:
    # this will add the parent of the genmonlib folder to the path
    # if we are one level below the genmonlib parent (e.g. in the addon folder)
    file_root = os.path.dirname(os.path.realpath(__file__))
    parent_root = os.path.abspath(os.path.join(file_root, os.pardir))
    if os.path.isdir(os.path.join(parent_root, "genmonlib")):
        sys.path.insert(1, parent_root)

    from genmonlib.myclient import ClientInterface
    from genmonlib.mycommon import MyCommon
    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
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

# ------------ MCP3008 class ----------------------------------------------------
class MCP3008(MyCommon):
    # ----------  MCP3008::init -------------------------------------------------
    def __init__(self, bus=0, device=0, log=None):
        self.log = log
        self.console = None
        self.bus, self.device = bus, device

        try:
            self.spi = SpiDev()
            self.open()
            self.spi.max_speed_hz = 250000  # 250kHz
        except Exception as e1:
            self.LogErrorLine("Error in MPC308 init: " + str(e1))
            self.FatalError("Error on opening SPI device: enable SPI or install CT HAT")

    # ----------  MCP3008::open -------------------------------------------------
    def open(self):

        try:
            self.spi.open(self.bus, self.device)
            self.spi.max_speed_hz = 250000  # 250kHz
        except Exception as e1:
            self.LogErrorLine("Error in MPC308 open: " + str(e1))

    # ----------  MCP3008::read -------------------------------------------------
    def read(self, channel=0):
        try:
            adc = self.spi.xfer2([1, (8 + channel) << 4, 0])
            data = ((adc[1] & 3) << 8) + adc[2]
            return data
        except Exception as e1:
            self.LogErrorLine("Error in MPC308 read: " + str(e1))

    # ----------  MCP3008::close ------------------------------------------------
    def close(self):
        try:
            self.spi.close()
        except Exception as e1:
            self.LogErrorLine("Error in MPC308 close: " + str(e1))


# ------------ GenCTHat class ---------------------------------------------------
class GenCTHat(MySupport):

    # ------------ GenCTHat::init------------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):

        super(GenCTHat, self).__init__()

        # https://tutorials-raspberrypi.com/mcp3008-read-out-analog-signals-on-the-raspberry-pi/
        # https://forums.raspberrypi.com/viewtopic.php?t=237182

        self.LogFileName = os.path.join(loglocation, "gencthat.log")
        self.AccessLock = threading.Lock()

        self.log = log
        self.console = console

        self.MonitorAddress = host
        self.PollTime = 2
        self.SampleTimeMS = 34
        self.debug = False
        self.ConfigFileName = "gencthat.conf"
        configfile = os.path.join(ConfigFilePath, self.ConfigFileName)
        try:
            if not os.path.isfile(configfile):
                self.LogConsole("Missing config file : " + configfile)
                self.LogError("Missing config file : " + configfile)
                sys.exit(1)

            self.config = MyConfig(
                filename=configfile, section="gencthat", log=self.log
            )

            self.Multiplier = self.config.ReadValue(
                "multiplier", return_type=float, default=0.488
            )
            # this checks to see if an old version of the conf file is in use and replaces it
            if self.Multiplier == 0.218:
                self.ConfPath = os.path.join(
                    os.path.dirname(os.path.realpath(__file__)), "conf"
                )
                if os.path.isfile(os.path.join(self.ConfPath, self.ConfigFileName)):
                    copyfile(
                        os.path.join(self.ConfPath, self.ConfigFileName), configfile
                    )
                    self.LogError(
                        "Copied "
                        + os.path.join(self.ConfPath, self.ConfigFileName)
                        + " to "
                        + configfile
                    )
                    self.config = MyConfig(
                        filename=configfile, section="gencthat", log=self.log
                    )
                else:
                    self.LogError(
                        "Error: unable to find config file: "
                        + os.path.join(self.ConfPath, self.ConfigFileName)
                    )

            self.SampleTimeMS = self.config.ReadValue(
                "sample_time_ms", return_type=int, default=34
            )
            self.Multiplier = self.config.ReadValue(
                "multiplier", return_type=float, default=0.488
            )
            self.PollTime = self.config.ReadValue(
                "poll_frequency", return_type=float, default=60
            )
            self.powerfactor = self.config.ReadValue(
                "powerfactor", return_type=float, default=1.0
            )
            self.bus = self.config.ReadValue("bus", return_type=int, default=1)
            self.device = self.config.ReadValue("device", return_type=int, default=0)
            self.strict = self.config.ReadValue(
                "strict", return_type=bool, default=False
            )
            self.singlelegthreshold = self.config.ReadValue(
                "singlelegthreshold", return_type=float, default=0.6
            )
            self.debug = self.config.ReadValue("debug", return_type=bool, default=False)

            self.LogDebug("Multiplier: " + str(self.Multiplier))
            
            if self.MonitorAddress != None:
                self.MonitorAddress = self.MonitorAddress.strip()

            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost

        except Exception as e1:
            self.LogErrorLine("Error reading " + configfile + ": " + str(e1))
            self.LogConsole("Error reading " + configfile + ": " + str(e1))
            sys.exit(1)

        try:

            self.adc = MCP3008(bus=self.bus, device=self.device, log=self.log)
            self.adc.open()

            self.Generator = ClientInterface(
                host=self.MonitorAddress, port=port, log=self.log
            )

            # if not self.CheckGeneratorRequirement():
            #    self.LogError("Requirements not met. Exiting.")
            #    sys.exit(1)

            # start thread monitor time for exercise
            self.Threads["SensorCheckThread"] = MyThread(
                self.SensorCheckThread, Name="SensorCheckThread", start=False
            )
            self.Threads["SensorCheckThread"].Start()

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

        except Exception as e1:
            self.LogErrorLine("Error in GenCTHat init: " + str(e1))
            self.console.error("Error in GenCTHat init: " + str(e1))
            sys.exit(1)

    # ----------  GenCTHat::SendCommand -----------------------------------------
    def SendCommand(self, Command):

        if len(Command) == 0:
            return "Invalid Command"

        try:
            with self.AccessLock:
                data = self.Generator.ProcessMonitorCommand(Command)
        except Exception as e1:
            self.LogErrorLine("Error calling  ProcessMonitorCommand: " + str(Command))
            data = ""

        return data

    # ----------  GenCTHat::CheckGeneratorRequirement ---------------------------
    def CheckGeneratorRequirement(self):

        try:
            data = self.SendCommand("generator: start_info_json")
            StartInfo = {}
            StartInfo = json.loads(data)
            if (
                not "evolution" in StartInfo["Controller"].lower()
                and not "nexus" in StartInfo["Controller"].lower()
            ):
                self.LogError(
                    "Error: Only Evolution or Nexus controllers are supported for this feature: "
                    + StartInfo["Controller"]
                )
                return False
            return True
        except Exception as e1:
            self.LogErrorLine("Error in CheckGeneratorRequirement: " + str(e1))
            return False

    # ---------- GenCTHat::MillisecondsElapsed----------------------------------
    def MillisecondsElapsed(self, ReferenceTime):

        CurrentTime = datetime.datetime.now()
        Delta = CurrentTime - ReferenceTime
        return Delta.total_seconds() * 1000

    # ---------- GenCTHat::SensorCheckThread------------------------------------
    def SensorCheckThread(self):

        time.sleep(1)
        while True:
            try:
                CT1 = None
                CT2 = None
                CTReading1 = []
                CTReading2 = []

                for i in range(5):
                    CT1 = self.GetCTReading(channel=0)
                    if CT1 != None:
                        CTReading1.append(CT1)
                    CT2 = self.GetCTReading(channel=1)
                    if CT2 != None:
                        CTReading2.append(CT2)

                if len(CTReading1):
                    CT1 = min(CTReading1)
                else:
                    CT1 = None
                if len(CTReading2):
                    CT2 = min(CTReading2)
                else:
                    CT2 = None

                if CT1 == None or CT2 == None:
                    if self.WaitForExit("SensorCheckThread", float(self.PollTime)):
                        return
                    continue

                if CT1 <= self.singlelegthreshold:
                    CT1 = 0
                if CT2 <= self.singlelegthreshold:
                    CT2 = 0

                self.LogDebug("CT1: %.2f, CT2: %.2f" % (CT1, CT2))

                data = {}
                data["strict"] = self.strict
                data["current"] = CT1 + CT2
                data["ctdata"] = [CT1, CT2]
                data["powerfactor"] = self.powerfactor
                data['from'] = "gencthat"
                return_string = json.dumps(data)
                self.Generator.ProcessMonitorCommand(
                    "generator: set_power_data=" + return_string
                )

                if self.WaitForExit("SensorCheckThread", float(self.PollTime)):
                    return
            except Exception as e1:
                self.LogErrorLine("Error in SensorCheckThread: " + str(e1))
                if self.WaitForExit("SensorCheckThread", float(self.PollTime)):
                    return

    # ----------GenCTHat::GetCTReading------------------------------------------
    def GetCTReading(self, channel=0):

        try:
            StartTime = datetime.datetime.now()
            num_samples = 0
            max = 0
            min = 512
            return_data = 0
            while True:

                sample = self.adc.read(channel=channel)

                if sample > max:
                    max = sample
                if sample < min:
                    min = sample
                num_samples += 1

                msElapsed = self.MillisecondsElapsed(StartTime)
                if msElapsed > self.SampleTimeMS:
                    break

            if max == 0 and min == 512:
                self.LogDebug("No data read in GetCTSample")
                return 0
            else:
                offset = max - 512
                if 511 - min > offset:
                    offset = 511 - min
                if offset <= 2:
                    offset = 0  # 1 or 2 is most likely just noise on the clamps or in the traces on the board

            self.LogDebug(
                "channel: %d, sample: %d, max: %d, min: %d, ms elapsed: %d, num samples %d"
                % (channel, sample, max, min, msElapsed, num_samples)
            )

            if max == min == 0:
                self.LogDebug("NULL readings, device not responding")
                return None
            return_data = offset * self.Multiplier
            return return_data

        except Exception as e1:
            self.LogErrorLine("Error in GetCTReading: " + str(e1))
            return 0

    # ----------GenCTHat::SignalClose-------------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(1)

    # ----------GenCTHat::Close-------------------------------------------------
    def Close(self):
        self.KillThread("SensorCheckThread")
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
    ) = MySupport.SetupAddOnProgram("gencthat")

    GenCTHatInstance = GenCTHat(
        log=log,
        loglocation=loglocation,
        ConfigFilePath=ConfigFilePath,
        host=address,
        port=port,
        console=console,
    )

    while True:
        time.sleep(0.5)

    sys.exit(1)
