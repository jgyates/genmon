#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: genmqtt.py
# PURPOSE: genmqtt.py is a client interface for a MQTT server / broker
#
#  AUTHOR: jgyates
#    DATE: 08-10-2018
#
# MODIFICATIONS:
#------------------------------------------------------------


import datetime, time, sys, signal, os, threading, collections, json
import atexit

#The following is need to install the mqtt module: pip install paho-mqtt

try:
   import paho.mqtt.client as mqtt
except:
   print("\n\nThe program requies the paho-mqtt module to be installed. Please use 'sudo pip install paho-mqtt' to install.\n")
   sys.exit(2)
try:
    from genmonlib import mycommon, mysupport, myclient, mylog, mythread
except:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    sys.exit(2)

try:
    from ConfigParser import RawConfigParser
except ImportError as e:
    from configparser import RawConfigParser
#------------ MyGenPush class -----------------------------------------------------
class MyGenPush(mysupport.MySupport):

    #------------ MyGenPush::init--------------------------------------------------
    def __init__(self,
        host="127.0.0.1",
        port=9082,
        log = None,
        callback = None,
        polltime = None,
        blacklist = None):

        super(MyGenPush, self).__init__()
        self.Callback = callback

        if polltime == None:
            self.PollTime = 3
        else:
            self.PollTime = float(polltime)

        if log != None:
            self.log = log
        else:
            # log errors in this module to a file
            self.log = mylog.SetupLogger("client", "/var/log/mygenpush.log")

        self.console = mylog.SetupLogger("mygenpush_console", log_file = "", stream = True)

        self.AccessLock = threading.Lock()
        self.BlackList = blacklist
        self.LastValues = {}
        try:
            startcount = 0
            while startcount <= 10:
                try:
                    self.Generator = myclient.ClientInterface(host = host, log = log)
                    break
                except Exception as e1:
                    startcount += 1
                    if startcount >= 10:
                        self.console.info("genmon not loaded.")
                        self.LogError("Unable to connect to genmon.")
                        sys.exit(1)
                    time.sleep(1)
                    continue
            # start thread to accept incoming sockets for nagios heartbeat
            self.Threads["PollingThread"] = mythread.MyThread(self.MainPollingThread, Name = "PollingThread")

        except Exception as e1:
            self.LogErrorLine("Error in mygenpush init: "  + str(e1))

    #----------  MyGenPush::SendCommand ---------------------------------
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

    # ---------- MyGenPush::MainPollingThread-------------------------------
    def MainPollingThread(self):

        while True:
            try:

                statusdata = self.SendCommand("generator: status_json")
                outagedata = self.SendCommand("generator: outage_json")
                monitordata = self.SendCommand("generator: monitor_json")
                maintdata = self.SendCommand("generator: maint_json")
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

    #------------ MySupport::CheckDictForChanges ---------------------------
    # This function is recursive, it will turn a nested dict into a flat dict keys
    # that have a directory structure with corrposonding values and deteermine if
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
                   for listitem in item:
                       if isinstance(listitem, dict):
                           self.CheckDictForChanges(listitem, CurrentPath)
                       elif isinstance(listitem, str) or isinstance(listitem, unicode):
                           CurrentPath = PathPrefix + "/" + str(key)
                           #todo list support
                           pass
                       else:
                           self.LogError("Invalid type in CheckDictForChanges: %s %s (2)" % (key, type(listitem)))
               else:
                   CurrentPath = PathPrefix + "/" + str(key)
                   self.CheckForChanges(CurrentPath, str(item))
        else:
           self.LogError("Invalid type in CheckDictForChanges %s " % type(node))

    # ---------- MyGenPush::CheckForChanges-------------------------------------
    def CheckForChanges(self, Path, Value):

        try:

            if self.BlackList != None:
                for BlackItem in self.BlackList:
                    if BlackItem.lower() in Path.lower():
                        return
            LastValue = self.LastValues.get(str(Path), None)

            if LastValue == None or LastValue != str(Value):
                self.LastValues[str(Path)] = str(Value)
                if self.Callback != None:
                    self.Callback(str(Path), str(Value))

        except Exception as e1:
             self.LogErrorLine("Error in mygenpush:CheckForChanges: " + str(e1))
    # ---------- MyGenPush::Close-----------------------------------------------
    def Close(self):
        self.KillThread("PollingThread")
        self.Generator.Close()

#------------ MyMQTT class -----------------------------------------------------
class MyMQTT(mycommon.MyCommon):

    #------------ MyMQTT::init--------------------------------------------------
    def __init__(self, log = None):
        super(MyMQTT, self).__init__()

        self.LogFileName = "/var/log/genmqtt.log"

        if log != None:
            self.log = log
        else:
            # log errors in this module to a file
            self.log = mylog.SetupLogger("client", self.LogFileName)

        # cleanup
        # test
        self.console = mylog.SetupLogger("mymqtt_console", log_file = "", stream = True)

        self.Username = None
        self.Password = None
        self.Address = None
        self.Topic = None

        self.MQTTAddress = "127.0.0.1"
        self.MonitorAddress = "127.0.0.1"
        self.Port = 1883
        self.Topic = "generator"
        self.TopicRoot = None
        self.BlackList = None
        self.PollTime = 2
        self.Debug = False

        try:

            # read config file
            config = RawConfigParser()
            # config parser reads from current directory, when running form a cron tab this is
            # not defined so we specify the full path
            config.read('/etc/genmqtt.conf')

            CONFIG_SECTION = "genmqtt"
            if config.has_option(CONFIG_SECTION, 'username'):
                self.Username = config.get(CONFIG_SECTION, 'username')
            if config.has_option(CONFIG_SECTION, 'password'):
                self.Password = config.get(CONFIG_SECTION, 'password')

            self.MQTTAddress = config.get(CONFIG_SECTION, 'mqtt_address')
            if config.has_option(CONFIG_SECTION, 'monitor_address'):
                self.MonitorAddress = config.get(CONFIG_SECTION, 'monitor_address')
            if config.has_option(CONFIG_SECTION, 'mqtt_port'):
                self.MQTTPort = config.getint(CONFIG_SECTION, 'mqtt_port')

            if config.has_option(CONFIG_SECTION, 'poll_interval'):
                self.PollTime = config.getfloat(CONFIG_SECTION, 'poll_interval')
            if config.has_option(CONFIG_SECTION, 'root_topic'):
                self.TopicRoot = config.get(CONFIG_SECTION, 'root_topic')
            if config.has_option(CONFIG_SECTION, 'blacklist'):
                BlackList = config.get(CONFIG_SECTION, 'blacklist')
                self.BlackList = BlackList.strip().split(",")
            if config.has_option(CONFIG_SECTION, 'debug'):
                self.Debug = config.getboolean(CONFIG_SECTION, 'debug')
        except Exception as e1:
            log.error("Error reading /etc/genmqtt.conf: " + str(e1))
            console.error("Error reading /etc/genmqtt.conf: " + str(e1))
            sys.exit(1)

        try:
            self.MQTTclient = mqtt.Client(client_id = "genmon")
            if self.Username != None and len(self.Username) and self.Password != None:
                self.MQTTclient.username_pw_set(self.Username, password=self.Password)

            self.MQTTclient.on_connect = self.on_connect
            self.MQTTclient.on_message = self.on_message

            self.MQTTclient.connect(self.MQTTAddress, self.Port, 60)

            self.Push = MyGenPush(host = self.MonitorAddress, log = self.log, callback = self.PublishCallback, polltime = self.PollTime , blacklist = self.BlackList)

            atexit.register(self.Close)
            signal.signal(signal.SIGTERM, self.Close)
            signal.signal(signal.SIGINT, self.Close)

            self.MQTTclient.loop_start()
        except Exception as e1:
            self.LogErrorLine("Error in MyMQTT init: " + str(e1))
            self.console.error("Error in MyMQTT init: " + str(e1))
            sys.exit(1)
    #------------ MyMQTT::PublishCallback---------------------------------------
    # Callback to publish data via MQTT
    def PublishCallback(self, name, value):

        try:
            if self.TopicRoot != None and len(self.TopicRoot):
                FullPath = self.TopicRoot + "/" + str(name)
            else:
                FullPath = str(name)

            if self.Debug:
                self.console.info("Publish:  " + FullPath  + ": " + str(value))

            self.MQTTclient.publish(FullPath, str(value))
        except Exception as e1:
            self.LogErrorLine("Error in MyMQTT:PublishCallback: " + str(e1))
    #------------ MyMQTT::on_connect--------------------------------------------
    # The callback for when the client receives a CONNACK response from the server.
    def on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            self.LogError("Error connecting to MQTT server: return code: " + str(rc))
        self.console.info("Connected with result code "+str(rc))

        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        self.MQTTclient.subscribe(self.Topic + "/#")

    #------------ MyMQTT::on_message--------------------------------------------
    # The callback for when a PUBLISH message is received from the server.
    def on_message(self, client, userdata, msg):

        if self.Debug:
            self.console.info("Confirmed: " + msg.topic + ": " + str(msg.payload))

    # ---------- MyMQTT::Close--------------------------------------------------
    def Close(self):
        self.Push.Close()
#-------------------------------------------------------------------------------
def Main():

    if os.geteuid() != 0:
        print("\nYou need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.\n")
        sys.exit(2)

    InstanceMQTT = MyMQTT()

    while True:
        time.sleep(0.5)

    sys.exit(1)
#-------------------------------------------------------------------------------
if __name__ == "__main__":
    Main()
