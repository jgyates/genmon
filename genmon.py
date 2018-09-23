#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: genmon.py
# PURPOSE: Monitor for Generator
#
#  AUTHOR: Jason G Yates
#    DATE: 05-Oct-2016
#          23-Apr-2018
#
# MODIFICATIONS:
#------------------------------------------------------------

from __future__ import print_function       # For python 3.x compatibility with print function

import datetime, time, sys, signal, os, threading, socket
import atexit, json, collections, random
import httplib, re
from subprocess import PIPE, Popen

try:
    from genmonlib import mymail, mylog, mythread, mypipe, mysupport, generac_evolution, generac_HPanel, myplatform, myweather, myconfig
except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)

GENMON_VERSION = "V1.10.4"

#------------ Monitor class --------------------------------------------
class Monitor(mysupport.MySupport):

    def __init__(self, ConfigFilePath = None):
        super(Monitor, self).__init__()
        self.ProgramName = "Generator Monitor"
        self.Version = "Unknown"
        self.log = None
        self.IsStopping = False
        self.ProgramComplete = False
        if ConfigFilePath == None:
            self.ConfigFilePath = "/etc/"
        else:
            self.ConfigFilePath = ConfigFilePath

        self.ConnectionList = []    # list of incoming connections for heartbeat
        # defautl values
        self.SiteName = "Home"
        self.ServerSocket = None
        self.ServerSocketPort = 9082    # server socket for nagios heartbeat and command/status
        self.IncomingEmailFolder = "Generator"
        self.ProcessedEmailFolder = "Generator/Processed"

        self.FeedbackLogFile = os.path.dirname(os.path.realpath(__file__)) + "/feedback.json"
        self.LogLocation = "/var/log/"
        self.LastLogFileSize = 0
        self.NumberOfLogSizeErrors = 0
        # set defaults for optional parameters
        self.NewInstall = False         # True if newly installed or newly upgraded version
        self.FeedbackEnabled = False    # True if sending autoated feedback on missing information
        self.FeedbackMessages = {}
        self.MailInit = False       # set to true once mail is init
        self.CommunicationsActive = False   # Flag to let the heartbeat thread know we are communicating
        self.Controller = None
        self.ControllerSelected = None
        self.bDisablePlatformStats = False
        self.ReadOnlyEmailCommands = False
        self.SlowCPUOptimization = False
        # weather parameters
        self.WeatherAPIKey = None
        self.WeatherLocation = None
        self.UseMetric = False
        self.WeatherMinimum = True
        self.DisableWeather = False
        self.MyWeather = None

        # Time Sync Related Data
        self.bSyncTime = False          # Sync gen to system time
        self.bSyncDST = False           # sync time at DST change
        self.bDST = False               # Daylight Savings Time active if True
        # simulation
        self.Simulation = False
        self.SimulationFile = None

        self.console = mylog.SetupLogger("genmon_console", log_file = "", stream = True)

        if os.geteuid() != 0:
            self.LogConsole("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'.")
            sys.exit(1)

        if not os.path.isfile(self.ConfigFilePath + 'genmon.conf'):
            self.LogConsole("Missing config file : " + self.ConfigFilePath + 'genmon.conf')
            sys.exit(1)
        if not os.path.isfile(self.ConfigFilePath + 'mymail.conf'):
            self.LogConsole("Missing config file : " + self.ConfigFilePath + 'mymail.conf')
            sys.exit(1)

        # log errors in this module to a file
        self.log = mylog.SetupLogger("genmon", self.LogLocation + "genmon.log")

        self.config = myconfig.MyConfig(filename = self.ConfigFilePath + 'genmon.conf', section = "GenMon", log = self.console)
        # read config file
        if not self.GetConfig():
            self.LogConsole("Failure in Monitor GetConfig")
            sys.exit(1)

        # log errors in this module to a file
        self.log = mylog.SetupLogger("genmon", self.LogLocation + "genmon.log")

        self.config.log = self.log

        if self.IsLoaded():
            self.LogConsole("ERROR: genmon.py is already loaded.")
            self.LogError("ERROR: genmon.py is already loaded.")
            sys.exit(1)


        if self.NewInstall:
            self.LogError("New version detected: Old = %s, New = %s" % (self.Version, GENMON_VERSION))
            self.Version = GENMON_VERSION

        self.ProgramStartTime = datetime.datetime.now()     # used for com metrics

        atexit.register(self.Close)
        signal.signal(signal.SIGTERM, self.Close)
        signal.signal(signal.SIGINT, self.Close)

        # start thread to accept incoming sockets for nagios heartbeat and command / status clients
        self.Threads["InterfaceServerThread"] = mythread.MyThread(self.InterfaceServerThread, Name = "InterfaceServerThread")

        # init mail, start processing incoming email
        self.mail = mymail.MyMail(monitor=True, incoming_folder = self.IncomingEmailFolder, processed_folder =self.ProcessedEmailFolder,incoming_callback = self.ProcessCommand)
        self.Threads = self.MergeDicts(self.Threads, self.mail.Threads)
        self.MailInit = True

        self.FeedbackPipe = mypipe.MyPipe("Feedback", self.FeedbackReceiver, log = self.log)
        self.Threads = self.MergeDicts(self.Threads, self.FeedbackPipe.Threads)
        self.MessagePipe = mypipe.MyPipe("Message", self.MessageReceiver, log = self.log, nullpipe = self.mail.DisableSNMP)
        self.Threads = self.MergeDicts(self.Threads, self.MessagePipe.Threads)

        try:
            #Starting device connection
            if self.Simulation:
                self.LogError("Simulation Running")
            if not self.ControllerSelected == None and len(self.ControllerSelected):
                self.LogError("Selected Controller: " + str(self.ControllerSelected))
            else:
                self.ControllerSelected = "generac_evo_nexus"

            if self.ControllerSelected.lower() == "h_100" :
                self.Controller = generac_HPanel.HPanel(self.log, newinstall = self.NewInstall, simulation = self.Simulation, simulationfile = self.SimulationFile, message = self.MessagePipe, feedback = self.FeedbackPipe, config = self.config)
            else:
                self.Controller = generac_evolution.Evolution(self.log, self.NewInstall, simulation = self.Simulation, simulationfile = self.SimulationFile, message = self.MessagePipe, feedback = self.FeedbackPipe, config = self.config)
            self.Threads = self.MergeDicts(self.Threads, self.Controller.Threads)

        except Exception as e1:
            self.FatalError("Error opening controller device: " + str(e1))
            return None

        self.StartThreads()

        self.ProcessFeedbackInfo()

        # send mail to tell we are starting
        self.MessagePipe.SendMessage("Generator Monitor Starting at " + self.SiteName, "Generator Monitor Starting at " + self.SiteName , msgtype = "info")

        self.LogError("GenMon Loaded for site: " + self.SiteName)

    # ------------------------ Monitor::StartThreads----------------------------
    def StartThreads(self, reload = False):

        try:
            # start thread to accept incoming sockets for nagios heartbeat
            self.Threads["ComWatchDog"] = mythread.MyThread(self.ComWatchDog, Name = "ComWatchDog")

            if self.bSyncDST or self.bSyncTime:     # Sync time thread
                self.Threads["TimeSyncThread"] = mythread.MyThread(self.TimeSyncThread, Name = "TimeSyncThread")

            if not self.DisableWeather and not self.WeatherAPIKey == None and len(self.WeatherAPIKey) and not self.WeatherLocation == None and len(self.WeatherLocation):
                Unit = 'metric' if self.UseMetric else 'imperial'
                self.MyWeather = myweather.MyWeather(self.WeatherAPIKey, location = self.WeatherLocation, unit = Unit, log = self.log)
                self.Threads = self.MergeDicts(self.Threads, self.MyWeather.Threads)
        except Exception as e1:
            self.LogErrorLine("Error in StartThreads: " + str(e1))

    # -------------------- Monitor::GetConfig-----------------------------------
    def GetConfig(self):

        try:
            if self.config.HasOption('sitename'):
                self.SiteName = self.config.ReadValue('sitename')

            if self.config.HasOption('incoming_mail_folder'):
                self.IncomingEmailFolder = self.config.ReadValue('incoming_mail_folder')     # imap folder for incoming mail

            if self.config.HasOption('processed_mail_folder'):
                self.ProcessedEmailFolder = self.config.ReadValue('processed_mail_folder')   # imap folder for processed mail
            #  server_port, must match value in myclient.py and check_monitor_system.py and any calling client apps
            if self.config.HasOption('server_port'):
                self.ServerSocketPort = self.config.ReadValue('server_port', return_type = int)

            if self.config.HasOption('loglocation'):
                self.LogLocation = self.config.ReadValue('loglocation')

            if self.config.HasOption('syncdst'):
                self.bSyncDST = self.config.ReadValue('syncdst', return_type = bool)
            if self.config.HasOption('synctime'):
                self.bSyncTime = self.config.ReadValue('synctime', return_type = bool)

            if self.config.HasOption('disableplatformstats'):
                self.bDisablePlatformStats = self.config.ReadValue('disableplatformstats', return_type = bool)

            if self.config.HasOption('simulation'):
                self.Simulation = self.config.ReadValue('simulation', return_type = bool)

            if self.config.HasOption('simulationfile'):
                self.SimulationFile = self.config.ReadValue('simulationfile')

            if self.config.HasOption('controllertype'):
                self.ControllerSelected = self.config.ReadValue('controllertype')

            if self.config.HasOption('disableweather'):
                self.DisableWeather = self.config.ReadValue('disableweather', return_type = bool)
            else:
                self.DisableWeather = False

            if self.config.HasOption('weatherkey'):
                self.WeatherAPIKey = self.config.ReadValue('weatherkey')

            if self.config.HasOption('weatherlocation'):
                self.WeatherLocation = self.config.ReadValue('weatherlocation')

            if self.config.HasOption('metricweather'):
                self.UseMetric = self.config.ReadValue('metricweather', return_type = bool)

            if self.config.HasOption('minimumweatherinfo'):
                self.WeatherMinimum = self.config.ReadValue('minimumweatherinfo', return_type = bool)

            if self.config.HasOption('readonlyemailcommands'):
                self.ReadOnlyEmailCommands = self.config.ReadValue('readonlyemailcommands', return_type = bool)

            if self.config.HasOption('optimizeforslowercpu'):
                self.SlowCPUOptimization = self.config.ReadValue('optimizeforslowercpu', return_type = bool)

            if self.config.HasOption('version'):
                self.Version = self.config.ReadValue('version')
                if not self.Version == GENMON_VERSION:
                    self.config.WriteValue('version', GENMON_VERSION)
                    self.NewInstall = True
            else:
                self.config.WriteValue('version', GENMON_VERSION)
                self.NewInstall = True
                self.Version = GENMON_VERSION
            if self.config.HasOption("autofeedback"):
                self.FeedbackEnabled = self.config.ReadValue('autofeedback', return_type = bool)
            else:
                self.config.WriteValue('autofeedback', "False")
                self.FeedbackEnabled = False
            # Load saved feedback log if log is present
            if os.path.isfile(self.FeedbackLogFile):
                try:
                    with open(self.FeedbackLogFile) as infile:
                        self.FeedbackMessages = json.load(infile)
                except Exception as e1:
                    os.remove(self.FeedbackLogFile)
        except Exception as e1:
            self.LogErrorLine("Missing config file or config file entries (genmon): " + str(e1))
            return False

        return True

    #------------------------------------------------------------
    def ProcessFeedbackInfo(self):

        try:
            if self.FeedbackEnabled:
                for Key, Entry in self.FeedbackMessages.items():
                    self.MessagePipe.SendMessage("Generator Monitor Submission", Entry , recipient = "generatormonitor.software@gmail.com", msgtype = "error")
                # delete unsent Messages
                if os.path.isfile(self.FeedbackLogFile):
                    os.remove(self.FeedbackLogFile)
        except Exception as e1:
            self.LogErrorLine("Error in ProcessFeedbackInfo: " + str(e1))

    #------------------------------------------------------------
    def FeedbackReceiver(self, Message):

        try:
            FeedbackDict = {}
            FeedbackDict = json.loads(Message)
            self.SendFeedbackInfo(FeedbackDict["Reason"], FeedbackDict["Always"], FeedbackDict["Message"], FeedbackDict["FullLogs"], FeedbackDict["NoCheck"])
        except Exception as e1:
            self.LogErrorLine("Error in  FeedbackReceiver: " + str(e1))
            self.LogError("Size : " + str(len(Message)))
            self.LogError("Message : " + str(Message))
    #------------------------------------------------------------
    def MessageReceiver(self, Message):

        try:
            MessageDict = {}
            MessageDict = json.loads(Message)
            self.mail.sendEmail(MessageDict["subjectstr"], MessageDict["msgstr"], MessageDict["recipient"], MessageDict["files"],MessageDict["deletefile"] ,MessageDict["msgtype"])
        except Exception as e1:
            self.LogErrorLine("Error in  MessageReceiver: " + str(e1))
    #------------------------------------------------------------
    def SendFeedbackInfo(self, Reason, Always = False, Message = None, FullLogs = True, NoCheck = False):
        try:
            if self.NewInstall or Always:

                CheckedSent = self.FeedbackMessages.get(Reason, "")

                if not CheckedSent == "" and not NoCheck:
                    return

                if not NoCheck:
                    self.LogError(Reason + " : " + Message)

                msgbody = "Reason = " + Reason + "\n"
                if Message != None:
                    msgbody += "Message : " + Message + "\n"
                msgbody += self.DictToString(self.GetStartInfo(NoTile = True))
                if not self.bDisablePlatformStats:
                    msgbody +=  self.DictToString(self.GetPlatformStats())
                msgbody += self.Controller.DisplayRegisters(AllRegs = FullLogs)
                if self.FeedbackEnabled:
                    self.MessagePipe.SendMessage("Generator Monitor Submission", msgbody , recipient = self.MaintainerAddress, msgtype = "error")

                self.FeedbackMessages[Reason] = msgbody
                # if feedback not enabled, save the log to file
                if not self.FeedbackEnabled:
                    with open(self.FeedbackLogFile, 'w') as outfile:
                        json.dump(self.FeedbackMessages, outfile, sort_keys = True, indent = 4, ensure_ascii = False)
        except Exception as e1:
            self.LogErrorLine("Error in SendFeedbackInfo: " + str(e1))

    #---------- Monitor::EmailSendIsEnabled-------------------------------------
    def EmailSendIsEnabled(self):

        EmailThread = self.Threads.get("SendMailThread",None)
        if EmailThread == None:
            return False
        return True

    #---------- Monitor::SendRegisters------------------------------------------
    def SendRegisters(self):

        if not self.EmailSendIsEnabled():
            return "Send Email is not enabled."

        msgbody = ""
        msgbody += self.DictToString(self.GetStartInfo(NoTile = True))
        if not self.bDisablePlatformStats:
            msgbody +=  self.DictToString(self.GetPlatformStats())
        msgbody += self.Controller.DisplayRegisters(AllRegs = True)
        self.MessagePipe.SendMessage("Generator Monitor Register Submission", msgbody , recipient = self.MaintainerAddress, msgtype = "info")
        return "Registers submitted"

    #---------- Monitor::SendLogFiles------------------------------------------
    def SendLogFiles(self):

        if not self.EmailSendIsEnabled():
            return "Send Email is not enabled."

        msgbody = ""
        msgbody += self.DictToString(self.GetStartInfo(NoTile = True))
        if not self.bDisablePlatformStats:
            msgbody +=  self.DictToString(self.GetPlatformStats())
        msgbody += self.Controller.DisplayRegisters(AllRegs = True)

        LogList = []
        FilesToSend = ["genmon.log", "genserv.log", "mymail.log", "myserial.log", "mymodbus.log", "gengpio.log", "gengpioin.log", "gensms.log", "gensms_modem.log", "genmqtt.log", "genpushover.log", "gensyslog.log", "genloader.log"]
        for File in FilesToSend:
            LogFile = self.LogLocation + File
            if os.path.isfile(LogFile):
                LogList.append(LogFile)
        self.MessagePipe.SendMessage("Generator Monitor Log File Submission", msgbody , recipient = self.MaintainerAddress, files = LogList, msgtype = "info")
        return "Log files submitted"

    #---------- process command from email and socket --------------------------
    def ProcessCommand(self, command, fromsocket = False):

        LocalError = False

        msgsubject = "Generator Command Response at " + self.SiteName
        if not fromsocket:
            msgbody = "\n"
        else:
            msgbody = ""

        if(len(command)) == 0:
            msgsubject = "Error in Generator Command (Lenght is zero)"
            msgbody += "Invalid GENERATOR command: zero length command."
            LocalError = True

        if not LocalError:
            if(not command.lower().startswith( b'generator:' )):         # PYTHON3
                msgsubject = "Error in Generator Command (command prefix)"
                msgbody += "Invalid GENERATOR command: all commands must be prefixed by \"generator: \""
                LocalError = True

        if LocalError:
            if not fromsocket:
                self.MessagePipe.SendMessage(msgsubject, msgbody, msgtype = "error")
                return ""       # ignored by email module
            else:
                msgbody += "EndOfMessage"
                return msgbody

        if command.lower().startswith(b'generator:'):
            command = command[len('generator:'):]

        CommandDict = {
            "registers"     : [self.Controller.DisplayRegisters,(False,), False],         # display registers
            "allregs"       : [self.Controller.DisplayRegisters, (True,), False],         # display registers
            "logs"          : [self.Controller.DisplayLogs, (True, False), False],
            "status"        : [self.Controller.DisplayStatus, (), False],                 # display decoded generator info
            "maint"         : [self.Controller.DisplayMaintenance, (), False],
            "monitor"       : [self.DisplayMonitor, (), False],
            "outage"        : [self.Controller.DisplayOutage, (), False],
            "settime"       : [self.StartTimeThread, (), False],                  # set time and date
            "setexercise"   : [self.Controller.SetGeneratorExerciseTime, (command.lower(),), False],
            "setquiet"      : [self.Controller.SetGeneratorQuietMode, ( command.lower(),), False],
            "setremote"     : [self.Controller.SetGeneratorRemoteStartStop, (command.lower(),), False],
            "help"          : [self.DisplayHelp, (), False],                   # display help screen
            ## These commands are used by the web / socket interface only
            "power_log_json"    : [self.Controller.GetPowerHistory, (command.lower(),), True],
            "power_log_clear"   : [self.Controller.ClearPowerLog, (), True],
            "start_info_json"   : [self.GetStartInfo, (), True],
            "registers_json"    : [self.Controller.DisplayRegisters, (False, True), True],  # display registers
            "allregs_json"      : [self.Controller.DisplayRegisters, (True, True), True],   # display registers
            "logs_json"         : [self.Controller.DisplayLogs, (True, True), True],
            "status_json"       : [self.Controller.DisplayStatus, (True,), True],
            "maint_json"        : [self.Controller.DisplayMaintenance, (True,), True],
            "monitor_json"      : [self.DisplayMonitor, (True,), True],
            "weather_json"      : [self.DisplayWeather, (True,), True],
            "outage_json"       : [self.Controller.DisplayOutage, (True,), True],
            "gui_status_json"   : [self.GetStatusForGUI, (), True],
            "getsitename"       : [self.GetSiteName, (), True],
            "getbase"           : [self.Controller.GetBaseStatus, (), True],    #  (UI changes color based on exercise, running , ready status)
            "gethealth"         : [self.GetSystemHealth, (), True],
            "getregvalue"       : [self.Controller.GetRegValue, (command.lower(),), True],     # only used for debug purposes, read a cached register value
            "readregvalue"      : [self.Controller.ReadRegValue, (command.lower(),), True],    # only used for debug purposes, Read Register Non Cached
            "getdebug"          : [self.GetDeadThreadName, (), True],           # only used for debug purposes. If a thread crashes it tells you the thread name
            "sendregisters"     : [self.SendRegisters, (), True],
            "sendlogfiles"      : [self.SendLogFiles, (), True]
        }

        CommandList = command.split(b' ')    # PYTHON3

        ValidCommand = False
        try:
            for item in CommandList:
                if not len(item):
                    continue
                item = item.strip()
                LookUp = item
                if "=" in item:
                    BaseCmd = item.split('=')
                    LookUp = BaseCmd[0]
                # check if we disallow write commands via email
                if self.ReadOnlyEmailCommands and not fromsocket and LookUp in ["settime", "setexercise", "setquiet", "setremote"]:
                    continue

                ExecList = CommandDict.get(LookUp.lower(),None)
                if ExecList == None:
                    continue
                if ExecList[0] == None:
                    continue
                if not fromsocket and ExecList[2]:
                    continue
                # Execut Command
                ReturnMessage = ExecList[0](*ExecList[1])

                ValidCommand = True

                if LookUp.lower().endswith("_json") and not isinstance(ReturnMessage, str):
                    msgbody += json.dumps(ReturnMessage, sort_keys=False)
                else:
                    msgbody += ReturnMessage

                if not fromsocket:
                    msgbody += "\n"
        except Exception as e1:
            self.LogErrorLine("Error Processing Commands: " + str(e1))

        if not ValidCommand:
            msgbody += "No valid command recognized."
        if not fromsocket:
            self.MessagePipe.SendMessage(msgsubject, msgbody, msgtype = "warn")
            return ""       # ignored by email module
        else:
            msgbody += "EndOfMessage"
            return msgbody

    #------------ Monitor::DisplayHelp ----------------------------------------
    def DisplayHelp(self):

        outstring = ""
        outstring += "Help:\n"
        outstring += self.printToString("\nCommands:")
        outstring += self.printToString("   status      - display engine and line information")
        outstring += self.printToString("   maint       - display maintenance and service information")
        outstring += self.printToString("   outage      - display current and last outage (since program launched)")
        outstring += self.printToString("                       info, also shows utility min and max values")
        outstring += self.printToString("   monitor     - display communication statistics and monitor health")
        outstring += self.printToString("   logs        - display all alarm, on/off, and maintenance logs")
        outstring += self.printToString("   registers   - display contents of registers being monitored")
        outstring += self.printToString("   settime     - set generator time to system time")
        outstring += self.printToString("   setexercise - set the exercise time of the generator. ")
        outstring += self.printToString("                      i.e. setexercise=Monday,13:30,Weekly")
        outstring += self.printToString("                   if Enhanced Exercise Frequency is supported by your generator:")
        outstring += self.printToString("                      i.e. setexercise=Monday,13:30,BiWeekly")
        outstring += self.printToString("                      i.e. setexercise=15,13:30,Monthly")
        outstring += self.printToString("   setquiet    - enable or disable exercise quiet mode, ")
        outstring += self.printToString("                      i.e.  setquiet=on or setquiet=off")
        outstring += self.printToString("   setremote   - issue remote command. format is setremote=command, ")
        outstring += self.printToString("                      where command is start, stop, starttransfer,")
        outstring += self.printToString("                      startexercise. i.e. setremote=start")
        outstring += self.printToString("   help        - Display help on commands")
        outstring += self.printToString("\n")

        outstring += self.printToString("To clear the Alarm/Warning message, press OFF on the control panel keypad")
        outstring += self.printToString("followed by the ENTER key. To access Dealer Menu on the Evolution")
        outstring += self.printToString("controller, from the top menu selection (SYSTEM, DATE/TIME,BATTERY, SUB-MENUS)")
        outstring += self.printToString("enter UP UP ESC DOWN UP ESC UP, then go to the dealer menu and press enter.")
        outstring += self.printToString("For liquid cooled models a level 2 dealer code can be entered, ESC UP UP DOWN")
        outstring += self.printToString("DOWN ESC ESC, then navigate to the dealer menu and press enter.")
        outstring += self.printToString("Passcode for Nexus controller is ESC, UP, UP ESC, DOWN, UP, ESC, UP, UP, ENTER.")
        outstring += self.printToString("\n")

        return outstring

    #------------ Monitor::GetWeatherData --------------------------------------
    def GetWeatherData(self, ForUI = False):

        if self.MyWeather == None:
            return None

        ReturnData = self.MyWeather.GetWeather(minimum = self.WeatherMinimum, ForUI = ForUI)

        if not len(ReturnData):
            return None
        return ReturnData

    #------------ Monitor::GetUserDefinedData ----------------------------------
    # this assumes one json object, the file can be formatted (i.e. on multiple
    # lines) or can be on a single line
    def GetUserDefinedData(self):

        try:
            FileName = os.path.dirname(os.path.realpath(__file__)) + "/userdefined.json"

            if not os.path.isfile(FileName):
                return None

            if os.path.getsize(FileName) == 0:
                return None

            with open(FileName) as f:
                data = json.load(f,object_pairs_hook=collections.OrderedDict)
            return data
        except Exception as e1:
            self.LogErrorLine("Error in GetUserDefinedData: " + str(e1))
        return None

    #------------ Monitor::DisplayWeather --------------------------------------
    def DisplayWeather(self, DictOut = False):

        WeatherData = collections.OrderedDict()

        try:
            ReturnData = self.GetWeatherData()
            if not ReturnData == None and len(ReturnData):
                WeatherData["Weather"] = ReturnData

            if not DictOut:
                return self.printToString(self.ProcessDispatch(WeatherData,""))
        except Exception as e1:
            self.LogErrorLine("Error in DisplayWeather: " + str(e1))

        return WeatherData

    #------------ Monitor::DisplayMonitor --------------------------------------
    def DisplayMonitor(self, DictOut = False):

        try:
            Monitor = collections.OrderedDict()
            MonitorData = collections.OrderedDict()
            Monitor["Monitor"] = MonitorData
            GenMonStats = collections.OrderedDict()
            SerialStats = collections.OrderedDict()
            MonitorData["Generator Monitor Stats"] = GenMonStats
            MonitorData["Serial Stats"] = self.Controller.GetCommStatus()

            GenMonStats["Monitor Health"] =  self.GetSystemHealth()
            GenMonStats["Controller"] = self.Controller.GetController(Actual = False)

            ProgramRunTime = datetime.datetime.now() - self.ProgramStartTime
            outstr = str(ProgramRunTime).split(".")[0]  # remove microseconds from string
            GenMonStats["Run time"] = self.ProgramName + " running for " + outstr + "."
            GenMonStats["Generator Monitor Version"] = GENMON_VERSION

            if not self.bDisablePlatformStats:
                PlatformStats = self.GetPlatformStats()
                if not PlatformStats == None:
                    MonitorData["Platform Stats"] = PlatformStats

            WeatherData = self.GetWeatherData()
            if not WeatherData == None and len(WeatherData):
                MonitorData["Weather"] = WeatherData

            UserData = self.GetUserDefinedData()
            if not UserData == None and len(UserData):
                MonitorData["External Data"] = UserData

            if not DictOut:
                return self.printToString(self.ProcessDispatch(Monitor,""))
        except Exception as e1:
            self.LogErrorLine("Error in DisplayMonitor: " + str(e1))
        return Monitor

    #------------ Monitor::GetStartInfo-----------------------------------------
    def GetStartInfo(self, NoTile = False):

        StartInfo = collections.OrderedDict()
        StartInfo["version"] = GENMON_VERSION
        StartInfo["sitename"] = self.SiteName
        ControllerStartInfo = self.Controller.GetStartInfo(NoTile = NoTile)
        StartInfo = self.MergeDicts(StartInfo, ControllerStartInfo)

        return StartInfo

    #------------ Monitor::GetStatusForGUI ------------------------------------
    def GetStatusForGUI(self):

        Status = {}

        Status["SystemHealth"] = self.GetSystemHealth()
        Status["UnsentFeedback"] = str(os.path.isfile(self.FeedbackLogFile))

        if not self.bDisablePlatformStats:
            PlatformStats = self.GetPlatformStats(usemetric = True)
            if not PlatformStats == None and len(PlatformStats):
                Status["PlatformStats"] = PlatformStats
        WeatherData = self.GetWeatherData(ForUI = True)
        if not WeatherData == None and len(WeatherData):
            Status["Weather"] = WeatherData
        ReturnDict = self.MergeDicts(Status, self.Controller.GetStatusForGUI())

        return ReturnDict

    #-------------Monitor::GetSystemHealth--------------------------------
    #   returns the health of the monitor program
    def GetSystemHealth(self):

        outstr = ""
        if not self.Controller.InitComplete:
            outstr += "System Initializing. "
        if not self.AreThreadsAlive():
            outstr += " Threads are dead. "
        if  not self.CommunicationsActive:
            outstr += " Not receiving data. "
        if not self.LogFileIsOK():
            outstr += " Log file is reporting errors."

        if len(outstr) == 0:
            outstr = "OK"
        return outstr

    #----------  Monitor::StartTimeThread-------------------------------------
    def StartTimeThread(self):

        # This is done is a separate thread as not to block any return email processing
        # since we attempt to sync with generator time
        mythread.MyThread(self.Controller.SetGeneratorTimeDate, Name = "SetTimeThread")
        return "Time Set: Command Sent\n"

    #----------  Monitor::TimeSyncThread-------------------------------------
    def TimeSyncThread(self):

        self.bDST = self.is_dst()   # set initial DST state

        time.sleep(0.25)
        while True:
            if self.WaitForExit("TimeSyncThread", 1):  # ten min
                return
            if self.Controller.InitComplete:
                break

        # if we are not always syncing, then set the time once
        if not self.bSyncTime:
            self.StartTimeThread()

        while True:

            if self.bSyncDST:
                if self.bDST != self.is_dst():  # has DST changed?
                    self.bDST = self.is_dst()   # update Flag
                    # time changed so some comm stats may be off
                    self.Controller.ResetCommStats()
                    # set new time
                    self.StartTimeThread()           # start settime thread
                    self.MessagePipe.SendMessage("Generator Time Update at " + self.SiteName, "Time updated due to daylight savings time change", msgtype = "info")

            if self.bSyncTime:
                # update gen time
                self.StartTimeThread()

            if self.WaitForExit("TimeSyncThread", 60 * 60):  # 1 hour
                return


    #----------  Monitor::is_dst------------------------------------------------
    def is_dst(self):
        #Determine whether or not Daylight Savings Time (DST) is currently in effect
        t = time.localtime()
        isdst = t.tm_isdst
        return (isdst != 0)

    #----------  Monitor::ComWatchDog-------------------------------------------
    #----------  monitors receive data status to make sure we are still communicating
    def ComWatchDog(self):

        self.CommunicationsActive = False
        time.sleep(0.25)
        while True:
            if self.WaitForExit("ComWatchDog", 1):
                return
            if self.Controller.InitComplete:
                break

        while True:

            self.CommunicationsActive = self.Controller.ComminicationsIsActive()

            if self.WaitForExit("ComWatchDog", 2):
                return

    #---------- Monitor::LogFileIsOK--------------------------------------------
    def LogFileIsOK(self):

        try:
            if not self.Controller.InitComplete:
                return True

            LogFile = self.LogLocation + "genmon.log"

            LogFileSize = os.path.getsize(LogFile)
            if LogFileSize <= self.LastLogFileSize:     # log is unchanged or has rotated
                self.LastLogFileSize = LogFileSize
                self.NumberOfLogSizeErrors = 0
                return True

            LogFileSizeDiff = LogFileSize - self.LastLogFileSize
            self.LastLogFileSize = LogFileSize
            if LogFileSizeDiff >= 100:
                self.NumberOfLogSizeErrors += 1
                if self.NumberOfLogSizeErrors > 3:
                    return False
            else:
                self.NumberOfLogSizeErrors = 0
            return True
        except Exception as e1:
            self.LogErrorLine("Error in LogFileIsOK: " + str(e1))
        return True

    #----------  Monitor::SocketWorkThread-------------------------------------
    #  This thread spawns for each connection established by a client
    #  in InterfaceServerThread
    def SocketWorkThread(self, conn):

        try:

            conn.settimeout(2)   # only blok on recv for a small amount of time

            statusstr = ""
            if self.Controller.SystemInAlarm():
                statusstr += "CRITICAL: System in alarm! "
            HealthStr = self.GetSystemHealth()
            if HealthStr != "OK":
                statusstr += "WARNING: " + HealthStr
            if statusstr == "":
                statusstr = "OK "

            outstr = statusstr + ": "+ self.Controller.GetOneLineStatus()
            conn.sendall(outstr.encode())

            while True:
                try:
                    data = conn.recv(1024)

                    outstr = self.ProcessCommand(data, True)
                    conn.sendall(outstr.encode())
                except socket.timeout:
                    continue
                except socket.error as msg:
                    try:
                        self.ConnectionList.remove(conn)
                        conn.close()
                    except:
                        pass
                    break

        except socket.error as msg:
            self.ConnectionList.remove(conn)
            conn.close()

        # end SocketWorkThread

    #----------  interface for heartbeat server thread -------------
    def InterfaceServerThread(self):

        #create an INET, STREAMing socket
        self.ServerSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # set some socket options so we can resuse the port
        self.ServerSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.ServerSocket.settimeout(.5)
        #bind the socket to a host, and a port
        self.ServerSocket.bind(('', self.ServerSocketPort))
        #become a server socket
        self.ServerSocket.listen(5)

        #wait to accept a connection - blocking call
        while True:
            try:
                conn, addr = self.ServerSocket.accept()
                #self.printToString( 'Connected with ' + addr[0] + ':' + str(addr[1]))
                conn.settimeout(0.5)
                self.ConnectionList.append(conn)
                SocketThread = threading.Thread(target=self.SocketWorkThread, args = (conn,), name = "SocketWorkThread")
                SocketThread.daemon = True
                SocketThread.start()       # start server thread
            except socket.timeout:
                if self.IsStopping:
                    break
                continue
            except Exception as e1:
                if self.IsStopping:
                    break
                self.LogErrorLine("Excpetion in InterfaceServerThread" + str(e1))
                if self.WaitForExit("InterfaceServerThread", 0.5 ):
                    break
                continue

        if self.ServerSocket != None:
            if len(self.ConnectionList):
                try:
                    self.ServerSocket.shutdown(socket.SHUT_RDWR)
                except:
                    pass
            self.ServerSocket.close()
            self.ServerSocket = None
        #

    #---------------------Monitor::Close------------------------
    def Close(self):

        # we dont really care about the errors that may be generated on shutdown
        try:
            self.IsStopping = True

            try:
                if self.MyWeather != None:
                    self.MyWeather.Close()
            except:
                pass

            try:
                if self.bSyncDST or self.bSyncTime:
                    self.KillThread("TimeSyncThread")
            except:
                pass

            try:
                self.KillThread("ComWatchDog")
            except:
                pass

            try:
                if not self.Controller == None:
                    self.Controller.Close()
            except:
                pass

            #
            try:
                self.mail.Close()
            except:
                pass
            try:
                for item in self.ConnectionList:
                    try:
                        item.close()
                    except:
                        continue
                    self.ConnectionList.remove(item)
            except:
                pass

            try:
                if(self.ServerSocket != None):
                    self.ServerSocket.shutdown(socket.SHUT_RDWR)
                    self.ServerSocket.close()
                self.KillThread("InterfaceServerThread")
            except:
                pass

            try:
                self.FeedbackPipe.Close()
            except:
                pass
            try:
                self.MessagePipe.Close()
            except:
                pass

            # Tell any remaining threads to stop
            for name, object in self.Threads.items():
                try:
                    if self.Threads[name].IsAlive():
                        self.Threads[name].Stop()
                except Exception as e1:
                    self.LogErrorLine("Error killing thread in Monitor Close: " + name + ":" + str(e1))

        except Exception as e1:
            self.LogErrorLine("Error Closing Monitor: " + str(e1))

        with self.CriticalLock:
            self.LogError("Generator Monitor Shutdown")

        try:

            self.ProgramComplete = True
            sys.exit(0)
        except:
            pass

#------------------- Command-line interface for monitor -----------------#
if __name__=='__main__': #
    ConfigFilePath = None if len(sys.argv)<2 else sys.argv[1]

    #Start things up
    MyMonitor = Monitor(ConfigFilePath = ConfigFilePath)

    try:
        while not MyMonitor.ProgramComplete:
            time.sleep(0.01)
        sys.exit(0)
    except:
        sys.exit(1)
