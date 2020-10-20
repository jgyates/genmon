#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: gentankutil.py
# PURPOSE: gentankutil.py add enhanced external tank data to genmon
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

except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)

class tankutility(MyCommon):

    #------------ tankutility::init---------------------------------------------
    def __init__(self, username, password, log, debug = False):

        self.log = log
        self.username = username
        self.password = password
        self.token = ""
        self.BASEURL = "https://data.tankutility.com/api/"
        self.DeviceIDs = []
        self.DeviceCount = 0
        self.debug = debug
        self.Data = None
    #------------ tankutility::Login--------------------------------------------
    def Login(self):
        try:
            ## Register user name and password with the API and get an authorization token for subsequent queries
            url = self.urljoin(self.BASEURL,"getToken")
            query = requests.get(url, auth=(self.username, self.password))
            if query.status_code != 200:
                self.LogError("Error logging in, error code: " + str(query.status_code ))
                return False
            else:
                response = query.json()
                self.LogDebug("Login: " + str(response))
                try:
                    if response['error'] != '':
                        self.LogError("API reports an account error: " + str(response['error']))
                        return False
                except:
                    pass
                self.token = response['token']
                return True
        except Exception as e1:
            self.LogErrorLine("Error in tankutility:Login: " + str(e1))
            return False
    #------------ tankutility::GetDevices---------------------------------------
    def GetDevices(self):
        try:
            if not len(self.token):
                self.LogError("Error in tankutility::GetDevices: not logged in")
                return False
            url = self.urljoin(self.BASEURL,"devices")
            params = (('token', self.token),)
            query = requests.get(url, params=params)
            if query.status_code != 200:
                self.LogError("Unable to obtain device list from the API, Error code: " + str(query.status_code ))
                return False
            else:
                response = query.json()
                self.LogDebug("GetDevices: " + str(response))
                self.DeviceIDs = response['devices']

                return True
        except Exception as e1:
            self.LogErrorLine("Error in tankutility:GetDevices : " + str(e1))
            return False
    #------------ tankutility::GetData------------------------------------------
    def GetData(self, deviceID):
        try:
            if not len(deviceID):
                return None
            if not len(self.token):
                self.LogError("Error in tankutility::GetDevices: not logged in")
                return None
            url = self.urljoin(self.BASEURL,"devices", deviceID)
            params = (('token', self.token),)
            query = requests.get(url, params=params)
            if query.status_code != 200:
                self.LogError("Unable to obtain device info from the API, Error code: " + str(query.status_code ) + ": " + str(deviceID))
                return None
            else:
                response = query.json()
                self.Data = response["device"]
                self.LogDebug("GetData: ID = " + str(deviceID) + " : "+ str(response))
                return self.Data
        except Exception as e1:
            self.LogErrorLine("Error in tankutility:GetData : " + str(e1))
            return None
    #------------ tankutility::GetIDFromName------------------------------------------
    def GetIDFromName(self, name):
        try:
            if not self.GetDevices():
                self.LogError("GetDevices failed in tankutility:GetIDFromName")
                return ""
            if not len(self.DeviceIDs):
                self.LogError("Not devices returned in tankutility:GetIDFromName")
                return ""
            name = name.strip()
            if name == "" or name == None:      # assume only one device
                return self.DeviceIDs[0]
            for device in self.DeviceIDs:
                tankdata = self.GetData(device)
                if tankdata == None:
                    continue
                if tankdata["name"].lower() == name.lower():
                    self.Data = tankdata
                    return device
            return ""
        except Exception as e1:
            self.LogErrorLine("Error in tankutility:GetIDFromName: " + str(e1))
            return ""
    # ---------- GenTankData::GetCapacity---------------------------------------
    def GetCapacity(self):
        try:
            return self.Data["capacity"]
        except Exception as e1:
            self.LogErrorLine("Error in GenTankData: GetCapacity: " + str(e1))
            return 0

    # ---------- GenTankData::GetPercentage-------------------------------------
    def GetPercentage(self):
        try:
            return round(float(self.Data["lastReading"]["tank"]),2)
        except Exception as e1:
            self.LogErrorLine("Error in GenTankData: GetPercentage: " + str(e1))
            return 0.0

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

        self.LogFileName = os.path.join(loglocation, "gentankutil.log")
        self.AccessLock = threading.Lock()
        # log errors in this module to a file
        self.log = SetupLogger("gentankutil", self.LogFileName)

        self.console = SetupLogger("gentankutil_console", log_file = "", stream = True)

        self.MonitorAddress = host
        self.PollTime =  2
        self.TankID = ""
        self.debug = False
        configfile = os.path.join(ConfigFilePath, 'gentankutil.conf')
        try:
            if not os.path.isfile(configfile):
                self.LogConsole("Missing config file : " + configfile)
                self.LogError("Missing config file : " + configfile)
                sys.exit(1)

            self.config = MyConfig(filename = configfile, section = 'gentankutil', log = self.log)

            self.PollTime = self.config.ReadValue('poll_frequency', return_type = float, default = 60)
            self.debug = self.config.ReadValue('debug', return_type = bool, default = False)
            self.username = self.config.ReadValue('username', default = "")
            self.password = self.config.ReadValue('password', default = "")
            self.tank_name = self.config.ReadValue('tank_name', default = "")

            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost

        except Exception as e1:
            self.LogErrorLine("Error reading " + configfile + ": " + str(e1))
            self.LogConsole("Error reading " + configfile + ": " + str(e1))
            sys.exit(1)

        if self.username == "" or self.username == None or self.password == "" or self.password == None:
            self.LogError("Invalid user name or password, exiting")
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

            #if not self.CheckGeneratorRequirement():
            #    self.LogError("Requirements not met. Exiting.")
            #    sys.exit(1)

            self.tank = tankutility(self.username, self.password, self.log, debug = self.debug)
            # start thread monitor time for exercise
            self.Threads["TankCheckThread"] = MyThread(self.TankCheckThread, Name = "TankCheckThread", start = False)
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
    #----------  GenTankData::CheckGeneratorRequirement ------------------------
    def CheckGeneratorRequirement(self):

        try:
            data = self.SendCommand("generator: start_info_json")
            StartInfo = {}
            StartInfo = json.loads(data)
            if not "evolution" in StartInfo["Controller"].lower() and not "nexus" in StartInfo["Controller"].lower():
                self.LogError("Error: Only Evolution or Nexus controllers are supported for this feature: " + StartInfo["Controller"])
                return False
            return True
        except Exception as e1:
            self.LogErrorLine("Error in CheckGeneratorRequirement: " + str(e1))
            return False


    # ---------- GenTankData::Login---------------------------------------------
    def Login(self, force = False):

        if force:
            self.TankID = ""
        if len(self.TankID):
            # already logged in
            return True
        if not self.tank.Login():
            return False
        self.TankID = self.tank.GetIDFromName(self.tank_name)
        if not len(self.TankID):
            return False
        return True

    # ---------- GenTankData::TankCheckThread-----------------------------------
    def TankCheckThread(self):

        time.sleep(1)
        LastLoginTime = datetime.datetime.now()
        while True:
            try:
                NUMBER_OF_SECONDS = 60 * 60 * 12    # 12 hours

                if ((datetime.datetime.now() - LastLoginTime).total_seconds() > NUMBER_OF_SECONDS) or not len(self.TankID):
                    self.LogDebug("Login ")
                    if not self.Login(force = True):
                        self.LogError("Error logging in in TankCheckThread, retrying")

                dataforgenmon = {}

                tankdata = self.tank.GetData(self.TankID)
                if tankdata != None:
                    dataforgenmon["Tank Name"] = tankdata["name"]
                    dataforgenmon["Capacity"] = self.tank.GetCapacity()
                    dataforgenmon["Percentage"] = self.tank.GetPercentage()

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
