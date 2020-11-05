#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: genmqtt.py
# PURPOSE: genmqtt.py is a client interface for a MQTT server / broker
#
#  AUTHOR: jgyates
#    DATE: 08-10-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------


import datetime, time, sys, signal, os, threading, collections, json, ssl
import atexit, getopt

#The following is need to install the mqtt module: pip install paho-mqtt

try:
   import paho.mqtt.client as mqtt
except Exception as e1:
   print("\n\nThe program requies the paho-mqtt module to be installed. Please use 'sudo pip install paho-mqtt' to install.\n")
   print("Error: " + str(e1))
   sys.exit(2)
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

#------------ MyGenPush class --------------------------------------------------
class MyGenPush(MySupport):

    #------------ MyGenPush::init-----------------------------------------------
    def __init__(self,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        log = None,
        callback = None,
        polltime = None,
        blacklist = None,
        flush_interval = float('inf'),
        use_numeric = False,
        debug = False,
        loglocation = ProgramDefaults.LogPath):

        super(MyGenPush, self).__init__()
        self.Callback = callback

        self.UseNumeric = use_numeric
        self.debug = debug
        self.Exiting = False

        if polltime == None:
            self.PollTime = 3
        else:
            self.PollTime = float(polltime)

        if log != None:
            self.log = log
        else:
            # log errors in this module to a file
            self.log = SetupLogger("client", os.path.join(loglocation, "mygenpush.log"))

        self.console = SetupLogger("mygenpush_console", log_file = "", stream = True)

        self.AccessLock = threading.Lock()
        self.BlackList = blacklist
        self.LastValues = {}
        self.FlushInterval = flush_interval
        self.LastChange = {}

        try:
            startcount = 0
            while startcount <= 10:
                try:
                    self.Generator = ClientInterface(host = host, port = port, log = log)
                    break
                except Exception as e1:
                    startcount += 1
                    if startcount >= 10:
                        self.LogDebug("genmon not loaded.")
                        self.LogError("Unable to connect to genmon.")
                        sys.exit(1)
                    time.sleep(1)
                    continue

            self.GetGeneratorStartInfo()
            # start thread to accept incoming sockets for nagios heartbeat
            self.Threads["PollingThread"] = MyThread(self.MainPollingThread, Name = "PollingThread", start = False)
            self.Threads["PollingThread"].Start()

        except Exception as e1:
            self.LogErrorLine("Error in mygenpush init: "  + str(e1))

    #----------  MyGenPush::ControllerIsEvolution2 -----------------------------
    def ControllerIsEvolution2(self):
        try:
            if "evolution 2.0" in self.StartInfo["Controller"].lower():
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in ControllerIsEvolution2: " + str(e1))
            return False

    #----------  MyGenPush::ControllerIsEvolutionNexus -------------------------
    def ControllerIsEvolutionNexus(self):
        try:
            if self.ControllerIsEvolution() or self.ControllerIsNexus:
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in ControllerIsEvolutionNexus: " + str(e1))
            return False

    #----------  MyGenPush::ControllerIsEvolution ------------------------------
    def ControllerIsEvolution(self):
        try:
            if "evolution" in self.StartInfo["Controller"].lower():
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in ControllerIsEvolution: " + str(e1))
            return False
    #----------  MyGenPush::ControllerIsNexius ---------------------------------
    def ControllerIsNexius(self):
        try:
            if "nexus" in self.StartInfo["Controller"].lower():
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in ControllerIsNexius: " + str(e1))
            return False
    #----------  MyGenPush::ControllerIsGeneracH100 ----------------------------
    def ControllerIsGeneracH100(self):
        try:
            if "h-100" in self.StartInfo["Controller"].lower() or "g-panel" in self.StartInfo["Controller"].lower():
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in ControllerIsGeneracH100: " + str(e1))
            return False
    #----------  MyGenPush::GetGeneratorStartInfo ------------------------------
    def GetGeneratorStartInfo(self):

        try:
            data = self.SendCommand("generator: start_info_json")
            self.StartInfo = {}
            self.StartInfo = json.loads(data)

            return True
        except Exception as e1:
            self.LogErrorLine("Error in GetGeneratorStartInfo: " + str(e1))
            return False

    #----------  MyGenPush::SendCommand ----------------------------------------
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

    # ---------- MyGenPush::MainPollingThread-----------------------------------
    def MainPollingThread(self):

        while True:
            try:

                if not self.UseNumeric:
                    statusdata = self.SendCommand("generator: status_json")
                    maintdata = self.SendCommand("generator: maint_json")
                    outagedata = self.SendCommand("generator: outage_json")
                    monitordata = self.SendCommand("generator: monitor_json")
                else:
                    statusdata = self.SendCommand("generator: status_num_json")
                    maintdata = self.SendCommand("generator: maint_num_json")
                    outagedata = self.SendCommand("generator: outage_num_json")
                    monitordata = self.SendCommand("generator: monitor_num_json")

                try:
                    GenmonDict = {}
                    TempDict = {}
                    TempDict = json.loads(statusdata)
                    GenmonDict["Status"] = TempDict["Status"]
                    TempDict = json.loads(maintdata)
                    GenmonDict["Maintenance"] = TempDict["Maintenance"]
                    TempDict = json.loads(outagedata)
                    GenmonDict["Outage"] = TempDict["Outage"]
                    TempDict = json.loads(monitordata)
                    GenmonDict["Monitor"] = TempDict["Monitor"]
                    self.CheckDictForChanges(GenmonDict, "generator")

                except Exception as e1:
                    self.LogErrorLine("Unable to get status: " + str(e1))

                if self.WaitForExit("PollingThread", float(self.PollTime)):
                    return
            except Exception as e1:
                self.LogErrorLine("Error in mynotify:MainPollingThread: " + str(e1))
                if self.WaitForExit("PollingThread", float(self.PollTime)):
                    return

    #------------ MySupport::CheckDictForChanges -------------------------------
    # This function is recursive, it will turn a nested dict into a flat dict keys
    # that have a directory structure with corrposonding values and determine if
    # anyting changed. If it has then call our callback function
    def CheckDictForChanges(self, node, PathPrefix):

        CurrentPath = PathPrefix
        if not isinstance(PathPrefix, str):
           return ""

        if isinstance(node, dict):
           for key, item in node.items():
               if isinstance(item, dict):
                   CurrentPath = PathPrefix + "/" + str(key)
                   self.CheckDictForChanges(item, CurrentPath)
               elif isinstance(item, list):
                   CurrentPath = PathPrefix + "/" + str(key)
                   if self.ListIsStrings(item):
                       # if this is a list of strings, the join the list to one comma separated string
                       self.CheckForChanges(CurrentPath, ', '.join(item))
                   else:
                       for listitem in item:
                           if isinstance(listitem, dict):
                               self.CheckDictForChanges(listitem, CurrentPath)
                           else:
                               self.LogError("Invalid type in CheckDictForChanges: %s %s (2)" % (key, str(type(listitem))))
               else:
                   CurrentPath = PathPrefix + "/" + str(key)
                   self.CheckForChanges(CurrentPath, item)
        else:
           self.LogError("Invalid type in CheckDictForChanges %s " % str(type(node)))
    # ---------- MyGenPush::ListIsStrings---------------------------------------
    # return true if every element of list is a string
    def ListIsStrings(self, listinput):

        try:
            if not isinstance(listinput, list):
                return False
            for item in listinput:
                if sys.version_info[0] < 3:
                    if not (isinstance(item, str) or isinstance(item, unicode)):
                        return False
                else:
                    if not (isinstance(item, str) or isinstance(item, bytes)):
                        return False
            return True
        except Exception as e1:
            self.LogErrorLine("Error in ListIsStrings: " + str(e1))
            return False

    # ---------- MyGenPush::CheckForChanges-------------------------------------
    def CheckForChanges(self, Path, Value):

        try:

            if self.BlackList != None:
                for BlackItem in self.BlackList:
                    if BlackItem.lower() in Path.lower():
                        return
            LastValue = self.LastValues.get(str(Path), None)
            LastChange = self.LastChange.get(str(Path), 0)

            if LastValue == None or LastValue != Value or (time.time() - LastChange) > self.FlushInterval:
                self.LastValues[str(Path)] = Value
                self.LastChange[str(Path)] = time.time()
                if self.Callback != None:
                    self.Callback(str(Path), Value)

        except Exception as e1:
             self.LogErrorLine("Error in mygenpush:CheckForChanges: " + str(e1))
    # ---------- MyGenPush::Close-----------------------------------------------
    def Close(self):
        self.Exiting = True
        self.KillThread("PollingThread")
        self.Generator.Close()

#------------ MyMQTT class -----------------------------------------------------
class MyMQTT(MyCommon):

    #------------ MyMQTT::init--------------------------------------------------
    def __init__(self,
        log = None,
        loglocation = ProgramDefaults.LogPath,
        host = ProgramDefaults.LocalHost,
        port = ProgramDefaults.ServerPort,
        configfilepath = ProgramDefaults.ConfPath):

        super(MyMQTT, self).__init__()

        self.LogFileName = os.path.join(loglocation, "genmqtt.log")

        if log != None:
            self.log = log
        else:
            # log errors in this module to a file
            self.log = SetupLogger("client", self.LogFileName)

        # cleanup
        # test
        self.console = SetupLogger("mymqtt_console", log_file = "", stream = True)

        self.Exiting = False
        self.Username = None
        self.Password = None

        self.MQTTAddress = None
        self.MonitorAddress = host
        self.MQTTPort = 1883
        self.TopicRoot = None
        self.BlackList = None
        self.UseNumeric = False
        self.RemoveSpaces = False
        self.PollTime = 2
        self.FlushInterval = float('inf')   # default to inifite flush interval (e.g., never)
        self.debug = False

        try:
            config = MyConfig(filename =  os.path.join(configfilepath, 'genmqtt.conf'), section = 'genmqtt', log = log)

            self.Username = config.ReadValue('username')

            self.Password = config.ReadValue('password')

            self.ClientID = config.ReadValue('client_id', default = "genmon")

            self.MQTTAddress = config.ReadValue('mqtt_address')

            if self.MQTTAddress == None or not len(self.MQTTAddress):
                log.error("Error: invalid MQTT server address")
                console.error("Error: invalid MQTT server address")
                sys.exit(1)

            self.MonitorAddress = config.ReadValue('monitor_address', default = self.MonitorAddress)
            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost

            self.MQTTPort = config.ReadValue('mqtt_port', return_type = int, default = 1883)
            self.PollTime = config.ReadValue('poll_interval', return_type = float, default = 2.0)
            self.UseNumeric = config.ReadValue('numeric_json', return_type = bool, default = False)
            self.RemoveSpaces = config.ReadValue('remove_spaces', return_type = bool, default = False)
            self.TopicRoot = config.ReadValue('root_topic')

            if self.TopicRoot != None:
                self.TopicRoot = self.TopicRoot.strip()
                self.LogDebug("Root Topic : " + self.TopicRoot)

            if self.TopicRoot == None or not len(self.TopicRoot):
                self.TopicRoot = None

            #http://www.steves-internet-guide.com/mosquitto-tls/
            self.CertificateAuthorityPath =  config.ReadValue('cert_authority_path', default = "")
            self.TLSVersion = config.ReadValue('tls_version', return_type = str, default = "1.0")
            self.CertReqs = config.ReadValue('cert_reqs', return_type = str, default = "Required")

            BlackList = config.ReadValue('blacklist')

            if BlackList != None:
                if len(BlackList):
                    BList = BlackList.strip().split(",")
                    if len(BList):
                        self.BlackList = []
                        for Items in BList:
                            self.BlackList.append(Items.strip())

            self.debug = config.ReadValue('debug', return_type = bool, default = False)

            if config.HasOption('flush_interval'):
                self.FlushInterval = config.ReadValue('flush_interval', return_type = float, default = float('inf'))
                if self.FlushInterval == 0:
                    self.FlushInterval = float('inf')
            else:
                self.FlushInterval = float('inf')
        except Exception as e1:
            self.LogErrorLine("Error reading " + os.path.join(configfilepath, "genmqtt.conf") + " : " + str(e1))
            self.console.error("Error reading " + os.path.join(configfilepath, "genmqtt.conf") + " : " + str(e1))
            sys.exit(1)

        try:
            self.MQTTclient = mqtt.Client(client_id = self.ClientID)
            if self.Username != None and len(self.Username) and self.Password != None:
                self.MQTTclient.username_pw_set(self.Username, password=self.Password)

            self.MQTTclient.on_connect = self.on_connect
            self.MQTTclient.on_message = self.on_message


            if len(self.CertificateAuthorityPath):
                if os.path.isfile(self.CertificateAuthorityPath):
                    cert_reqs = ssl.CERT_REQUIRED
                    if self.CertReqs.lower() == "required":
                        cert_reqs = ssl.CERT_REQUIRED
                    elif self.CertReqs.lower() == "optional":
                        cert_reqs = ssl.CERT_REQUIRED
                    elif self.CertReqs.lower() == "none":
                        cert_reqs = ssl.CERT_NONE
                    else:
                        self.LogError("Error: invalid cert required specified, defaulting to required: " + self.CertReq)

                    use_tls = ssl.PROTOCOL_TLSv1
                    if self.TLSVersion == "1.0" or self.TLSVersion == "1":
                        use_tls = ssl.PROTOCOL_TLSv1
                    elif self.TLSVersion == "1.1":
                        use_tls = ssl.PROTOCOL_TLSv1_1
                    elif self.TLSVersion == "1.2":
                        use_tls = ssl.PROTOCOL_TLSv1_2
                    else:
                        self.LogError("Error: invalid TLS version specified, defaulting to 1.0: " + self.TLSVersion)
                    self.MQTTclient.tls_set(ca_certs = self.CertificateAuthorityPath,cert_reqs = cert_reqs, tls_version = use_tls )
                    self.MQTTPort = 8883    # port for SSL
                else:
                    self.LogError("Error: Unable to  find CA cert file: " + self.CertificateAuthorityPath)

            self.MQTTclient.connect(self.MQTTAddress, self.MQTTPort, 60)

            self.Push = MyGenPush(host = self.MonitorAddress,
                log = self.log, callback = self.PublishCallback,
                polltime = self.PollTime , blacklist = self.BlackList,
                flush_interval = self.FlushInterval, use_numeric = self.UseNumeric,
                debug = self.debug, port = port, loglocation = loglocation)

            atexit.register(self.Close)
            signal.signal(signal.SIGTERM, self.Close)
            signal.signal(signal.SIGINT, self.Close)

            self.MQTTclient.loop_start()
        except Exception as e1:
            self.LogErrorLine("Error in MyMQTT init: " + str(e1))
            self.console.error("Error in MyMQTT init: " + str(e1))
            sys.exit(1)
    #------------ MyMQTT::AppendRoot---------------------------------------
    def AppendRoot(self, name):

        if self.TopicRoot != None and len(self.TopicRoot):
            ReturnPath = self.TopicRoot + "/" + str(name)
        else:
            ReturnPath = str(name)
        return ReturnPath

    #------------ MyMQTT::PublishCallback---------------------------------------
    # Callback to publish data via MQTT
    def PublishCallback(self, name, value):

        try:
            FullPath = self.AppendRoot(name)

            if self.RemoveSpaces:
                FullPath = FullPath.replace(" ", "_")

            if self.debug:
                self.LogDebug("Publish:  " + FullPath  + ": " + str(value) + ": " + str(type(value)))

            self.MQTTclient.publish(FullPath, value)
        except Exception as e1:
            self.LogErrorLine("Error in MyMQTT:PublishCallback: " + str(e1))

    #------------ MyMQTT::on_connect--------------------------------------------
    # The callback for when the client receives a CONNACK response from the server.
    def on_connect(self, client, userdata, flags, rc):

        try:
            if rc != 0:
                self.LogError("Error connecting to MQTT server: return code: " + str(rc))
            self.LogDebug("Connected with result code "+str(rc))

            # Subscribing in on_connect() means that if we lose the connection and
            # reconnect then subscriptions will be renewed.
            if self.TopicRoot != None and len(self.TopicRoot):
                FullPath = self.TopicRoot + "/generator"
            else:
                FullPath = "generator"
            self.MQTTclient.subscribe(FullPath + "/#")

        except Exception as e1:
            self.LogErrorLine("Error in MyMQTT:on_connect: " + str(e1))


    #------------ MyMQTT::on_message--------------------------------------------
    # The callback for when a PUBLISH message is received from the server.
    def on_message(self, client, userdata, message):

        try:
            if self.debug:
                self.LogDebug("Confirmed: " + message.topic + ": " + str(message.payload))
            # parse topic
            command = str(message.payload.decode("utf-8"))
            if self.TopicRoot != None and len(self.TopicRoot):
                FullPath = self.TopicRoot + "/generator/command"
            else:
                FullPath = "generator/command"

            if message.topic.lower() != (FullPath.lower()):
                return

            # write command
            if command != None and len(command):
                self.Push.SendCommand("generator: " + command)
                self.LogDebug("Command Sent: " + command)
        except Exception as e1:
            self.LogErrorLine("Error in MyMQTT:on_message: " + str(e1))

    # ---------- MyMQTT::Close--------------------------------------------------
    def Close(self):
        self.LogDebug("Exiting MyMQTT")
        self.Push.Close()
        self.Exiting = True
#-------------------------------------------------------------------------------
if __name__ == "__main__":

    address=ProgramDefaults.LocalHost

    console = SetupLogger("genmqtt_console_", log_file = "", stream = True)
    HelpStr = '\nsudo python genmqtt.py -a <IP Address or localhost> -c <path to genmon config file>\n'
    if os.geteuid() != 0:
        console.error("\nYou need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.\n")
        sys.exit(2)

    try:
        ConfigFilePath = ProgramDefaults.ConfPath
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

    InstanceMQTT = MyMQTT(host = address, port = port, loglocation = loglocation, configfilepath = ConfigFilePath)

    while not InstanceMQTT.Exiting:
        time.sleep(0.5)

    sys.exit(1)
