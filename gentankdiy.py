#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: gentankdiy.py
# PURPOSE: gentankdiy.py add enhanced external tank data to genmon
#
#  AUTHOR: jgyates
#    DATE: 06-18-2019
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------


import datetime, time, sys, signal, os, threading, collections, json, ssl
import atexit, getopt, requests

try:
    from genmonlib.myclient import ClientInterface
    from genmonlib.mylog import SetupLogger
    from genmonlib.myconfig import MyConfig
    from genmonlib.mysupport import MySupport
    from genmonlib.mycommon import MyCommon
    from genmonlib.mythread import MyThread
    from genmonlib.program_defaults import ProgramDefaults
    import smbus

except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)


#------------ GenTankData class ------------------------------------------------
class GenTankData(MySupport):

    # The device is the ADS1115 I2C ADC
    # reference python http://www.smartypies.com/projects/ads1115-with-raspberrypi-and-python/ads1115runner/
    RESET_ADDRESS = 0b0000000
    RESET_COMMAND = 0b00000110
    POINTER_CONVERSION = 0x0
    POINTER_CONFIGURATION = 0x1
    POINTER_LOW_THRESHOLD = 0x2
    POINTER_HIGH_THRESHOLD = 0x3
    #------------ GenTankData::init---------------------------------------------
    def __init__(self,
        log = None,
        loglocation = ProgramDefaults.LogPath,
        ConfigFilePath = MyCommon.DefaultConfPath,
        host = ProgramDefaults.LocalHost,
        port = ProgramDefaults.ServerPort):

        super(GenTankData, self).__init__()

        self.LogFileName = os.path.join(loglocation, "gentankdiy.log")
        self.AccessLock = threading.Lock()
        # log errors in this module to a file
        self.log = SetupLogger("gentankdiy", self.LogFileName)

        self.console = SetupLogger("gentankdiy_console", log_file = "", stream = True)

        self.MonitorAddress = host
        self.PollTime =  2
        self.debug = False

        configfile = os.path.join(ConfigFilePath, 'gentankdiy.conf')
        try:
            if not os.path.isfile(configfile):
                self.LogConsole("Missing config file : " + configfile)
                self.LogError("Missing config file : " + configfile)
                sys.exit(1)

            self.config = MyConfig(filename = configfile, section = 'gentankdiy', log = self.log)

            self.PollTime = self.config.ReadValue('poll_frequency', return_type = float, default = 60)
            self.debug = self.config.ReadValue('debug', return_type = bool, default = False)
            self.i2c_address = self.config.ReadValue('i2c_address', return_type = int, default = 72)
            self.mv_per_step = self.config.ReadValue('mv_per_step', return_type = int, default = 125)
            self.Multiplier = self.config.ReadValue('volts_to_percent_multiplier', return_type = float, default = 20.0)
            # I2C channel 1 is connected to the GPIO pins
            self.i2c_channel = self.config.ReadValue('i2c_channel', return_type = int, default = 1)

            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost

        except Exception as e1:
            self.LogErrorLine("Error reading " + configfile + ": " + str(e1))
            self.LogConsole("Error reading " + configfile + ": " + str(e1))
            sys.exit(1)

        try:

            try:
                startcount = 0
                while startcount <= 10:
                    try:
                        self.Generator = ClientInterface(host = self.MonitorAddress, port = port, log = self.log)
                        break
                    except Exception as e1:
                        startcount += 1
                        if startcount >= 10:
                            self.console.info("genmon not loaded.")
                            self.LogError("Unable to connect to genmon.")
                            sys.exit(1)
                        time.sleep(1)
                        continue

            except Exception as e1:
                self.LogErrorLine("Error in GenTankData init: "  + str(e1))

            # start thread monitor time for exercise
            self.Threads["TankCheckThread"] = MyThread(self.TankCheckThread, Name = "TankCheckThread", start = False)

            if not self.InitADC():
                self.LogError("InitADC failed, exiting")
                sys.exit(1)

            self.Threads["TankCheckThread"].Start()

            atexit.register(self.Close)
            signal.signal(signal.SIGTERM, self.Close)
            signal.signal(signal.SIGINT, self.Close)

        except Exception as e1:
            self.LogErrorLine("Error in GenTankData init: " + str(e1))
            self.console.error("Error in GenTankData init: " + str(e1))
            sys.exit(1)

    #----------  GenTankData::SendCommand --------------------------------------
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

    # ---------- GenTankData::InitADC-------------------------------------------
    def InitADC(self):

        try:

            # I2C channel 1 is connected to the GPIO pins
            self.I2Cbus = smbus.SMBus(self.i2c_channel)

            # Reset ADC
            self.I2Cbus.write_byte(self.RESET_ADDRESS, self.RESET_COMMAND)

            # set config register  and start conversion
            # ANC1 and GND, 4.096v, 128s/s
            # Customized - Port A0 and 4.096 V input
            # 0b11000011; # bit 15-8  = 0xC3
            # bit 15 flag bit for single shot
            # Bits 14-12 input selection:
            # 100 ANC0; 101 ANC1; 110 ANC2; 111 ANC3
            # Bits 11-9 Amp gain. Default to 010 here 001 P19
            # Bit 8 Operational mode of the ADS1115.
            # 0 : Continuous conversion mode
            # 1 : Power-down single-shot mode (default)
            CONFIG_VALUE_1 = 0xC3
            # bits 7-0  0b10000101 = 0x85
            # Bits 7-5 data rate default to 100 for 128SPS
            # Bits 4-0  comparator functions see spec sheet.
            CONFIG_VALUE_2 = 0x85
            self.I2Cbus.write_i2c_block_data(self.i2c_address, self.POINTER_CONFIGURATION, [CONFIG_VALUE_1,CONFIG_VALUE_2] )

            self.LogDebug("I2C Init complete: success")

        except Exception as e1:
            self.LogErrorLine("Error calling InitADC: " + str(e1))
            return False

        return True
    # ---------- GenTankData::GetGaugeData--------------------------------------
    def GetGaugeData(self):
        try:

            val = self.I2Cbus.read_i2c_block_data(self.i2c_address, self.POINTER_CONVERSION, 2)

            self.LogDebug(str(val))
            # convert display results
            reading = val[0] << 8 | val[1]

            if (reading < 0):
                reading = 0

            #reading = self.I2Cbus.read_word_data(self.i2c_address, self.i2c_channel)
            volts = round(float(reading * (float(self.mv_per_step) / 1000000.0)),2)
            gauge_data = float(self.Multiplier) * volts
            self.LogDebug("Reading Gauge Data: %4.2f%%" % gauge_data)
            return gauge_data

        except Exception as e1:
            self.LogErrorLine("Error calling  GetGaugeData: " + str(e1))
            return 0.0

    # ---------- GenTankData::TankCheckThread-----------------------------------
    def TankCheckThread(self):

        time.sleep(1)

        while True:
            try:

                dataforgenmon = {}

                tankdata = self.GetGaugeData()
                if tankdata != None:
                    dataforgenmon["Tank Name"] = "External Tank"
                    dataforgenmon["Capacity"] = 0
                    dataforgenmon["Percentage"] = self.GetGaugeData()

                    retVal = self.SendCommand("generator: set_tank_data=" + json.dumps(dataforgenmon))
                    self.LogDebug(retVal)
                if self.WaitForExit("TankCheckThread", float(self.PollTime * 60)):
                    return
            except Exception as e1:
                self.LogErrorLine("Error in TankCheckThread: " + str(e1))
                if self.WaitForExit("TankCheckThread", float(self.PollTime * 60)):
                    return

    # ----------GenTankData::Close----------------------------------------------
    def Close(self):
        self.KillThread("TankCheckThread")
        self.Generator.Close()
#-------------------------------------------------------------------------------
if __name__ == "__main__":

    console = SetupLogger("gentankdata_console", log_file = "", stream = True)
    HelpStr = '\nsudo python gentankdata.py -a <IP Address or localhost> -c <path to genmon config file>\n'
    if os.geteuid() != 0:
        console.error("\nYou need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.\n")
        sys.exit(2)

    try:
        ConfigFilePath = ProgramDefaults.ConfPath
        address = ProgramDefaults.LocalHost
        opts, args = getopt.getopt(sys.argv[1:],"hc:a:",["help","configpath=","address="])
    except getopt.GetoptError:
        console.error("Invalid command line argument.")
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            console.error(HelpStr)
            sys.exit()
        elif opt in ("-a", "--address"):
            address = arg
        elif opt in ("-c", "--configpath"):
            ConfigFilePath = arg
            ConfigFilePath = ConfigFilePath.strip()

    port, loglocation = MySupport.GetGenmonInitInfo(ConfigFilePath, log = console)
    log = SetupLogger("client", loglocation + "gentankdata.log")

    GenTankDataInstance = GenTankData(log = log, loglocation = loglocation, ConfigFilePath = ConfigFilePath, host = address, port = port)

    while True:
        time.sleep(0.5)

    sys.exit(1)
