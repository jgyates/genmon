#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: gentankdiy2.py
# PURPOSE: gentankdiy2.py add enhanced external tank data for TLE5501 sensor to genmon
#
#  AUTHOR: jgyates
#    DATE: 06-18-2019
#
# MODIFICATIONS:
#   2020-10-04 C. Case New version of gentankdiy.py for using the Hall Effect
#     Infinieon TLE5501 E0001 TMR-based angle sensor.  This code uses
#     two of the outputs from this IC (SIN_P and COS_P) to calculate the
#     angle of the pointer on the dial. See:
#     www.infineon.com/cms/en/product/sensor/magnetic-sensors/magnetic-position-sensors/angle-sensors/tle5501-e0001/
#
#     Coded to use the ADS1015 and ADS1115 A/D converters, but has only been tested with the ADS1015.
#-------------------------------------------------------------------------------

import datetime, time, sys, signal, os, threading, json
import atexit, getopt

try:
    from genmonlib.myclient import ClientInterface
    from genmonlib.mylog import SetupLogger
    from genmonlib.myconfig import MyConfig
    from genmonlib.mysupport import MySupport
    from genmonlib.mycommon import MyCommon
    from genmonlib.mythread import MyThread
    from genmonlib.program_defaults import ProgramDefaults
    from genmonlib.gaugediy2 import GaugeDIY2
    
except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)

#------------ GenTankData class ------------------------------------------------
class GenTankData(MySupport):
   
    #------------ GenTankData::init---------------------------------------------
    def __init__(self,
                 log = None,
                 loglocation = ProgramDefaults.LogPath,
                 ConfigFilePath = MyCommon.DefaultConfPath,
                 host = ProgramDefaults.LocalHost,
                 port = ProgramDefaults.ServerPort):

        super(GenTankData, self).__init__()

        self.LogFileName = loglocation + "gentankdiy2.log"
        self.AccessLock = threading.Lock()

        # log errors in this module to a file
        self.log = SetupLogger("gentankdiy2", self.LogFileName)
        self.console = SetupLogger("gentankdiy2_console", log_file = "", stream = True)

        self.MonitorAddress = host
        self.debug = False

        configfile = ConfigFilePath + 'gentankdiy2.conf'
        try:
            if not os.path.isfile(configfile):
                err_msg = f"Missing config file : {configfile}"
                self.LogConsole(err_msg)
                self.LogError(err_msg)
                sys.exit(1)

            self.config = MyConfig(filename = configfile, section = 'gentankdiy2', log = self.log)

            #Get gauge object used to read the propane tank guage (dial) using the TLE5501 sensor and
            #the ADS1015 or ADS1115 A/D converter and read in the config file.  Config file is read in 
            #in GaugeDIY2 because GaugeDIY2 is alos used in DIY2TankSensorCalibrate.py and it needs
            #to have the parmeters from and write to the config file
            self.gauge = GaugeDIY2(self.config)

            #Initialze the ADS1x15 
            init_err_msg = self.gauge.InitADC()

            if len(init_err_msg):
                self.LogError(f"InitADC failed, '{init_err_msg}', exiting")
                sys.exit(1)

            self.debug = self.config.ReadValue('debug', return_type = bool, default = False)

            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost

        except Exception as e1:
            err_msg = f"Error reading {configfile}: {str(e1)}"
            self.LogErrorLine(err_msg)
            self.LogConsole(err_msg)
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

            # start thread monitor time for getting tank dial gauge readings
            self.Threads[self.TankCheckThread.__name__] = MyThread(self.TankCheckThread, Name = self.TankCheckThread.__name__)

            atexit.register(self.Close)
            signal.signal(signal.SIGTERM, self.Close)
            signal.signal(signal.SIGINT, self.Close)

        except Exception as e1:
            err_msg = f"Error in GenTankData init: {str(e1)}"
            self.LogErrorLine(err_msg)
            self.console.error(err_msg)
            sys.exit(1)

    #----------  GenTankData::SendCommand --------------------------------------
    def SendCommand(self, Command):

        if len(Command) == 0: return "Invalid Command"

        try:
            with self.AccessLock:
                data = self.Generator.ProcessMonitorCommand(Command)

        except Exception as e1:
            self.LogErrorLine(f"Error calling  ProcessMonitorCommand: {str(Command)}")
            data = ""

        return data
 
    # ---------- GenTankData::TankCheckThread-----------------------------------
    def TankCheckThread(self):

        time.sleep(1)

        while True:
            try:
                tankdata = self.gauge.GetGaugeData()
                if tankdata != None:
                    dataforgenmon = {"Tank Name": "External Tank", "Capacity": 0, "Percentage": tankdata}
                    retVal = self.SendCommand("generator: set_tank_data=" + json.dumps(dataforgenmon))
                    self.LogDebug(retVal)

            except Exception as e1:
                self.LogErrorLine(f"Error in '{self.TankCheckThread.__name__}': " + str(e1))
                
            if self.WaitForExit(self.TankCheckThread.__name__, float(self.gauge.PollTime * 60)): return

    # ----------GenTankData::Close----------------------------------------------
    def Close(self):
        self.KillThread(self.TankCheckThread.__name__)
        self.Generator.Close()
#-------------------------------------------------------------------------------
if __name__ == "__main__":

    console = SetupLogger("gentankdata_console", log_file = "", stream = True)
    HelpStr = '\nsudo python gentankdata.py -a <IP Address or localhost> -c <path to genmon config file>\n'

    MySupport.CheckRootPrivileges()

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
            ConfigFilePath = arg.strip()
    
    port, loglocation = MySupport.GetGenmonInitInfo(ConfigFilePath, log = console)
    log = SetupLogger("client", loglocation + "gentankdatadiy2.log")

    GenTankDataInstance = GenTankData(log = log, loglocation = loglocation, ConfigFilePath = ConfigFilePath, host = address, port = port)

    # Wait forever until process is kill'ed
    while True:
        time.sleep(0.5)

    sys.exit(1)
