#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: genmon.py
# PURPOSE: Monitor for Generator
#
#  AUTHOR: Jason G Yates
#    DATE: 05-Oct-2016
#          23-Apr-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

from __future__ import print_function       # For python 3.x compatibility with print function

import datetime, time, sys, signal, os, threading, socket
import atexit, json, collections, random, getopt
import re
from subprocess import PIPE, Popen

try:
    from genmonlib.mylog import SetupLogger
    from genmonlib.myconfig import MyConfig
    from genmonlib.mymail import MyMail
    from genmonlib.mythread import MyThread
    from genmonlib.mysupport import MySupport
    from genmonlib.mypipe import MyPipe
    from genmonlib.generac_evolution import Evolution
    from genmonlib.generac_HPanel import HPanel
    from genmonlib.myweather import MyWeather
    from genmonlib.program_defaults import ProgramDefaults
except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)

GENMON_VERSION = "V1.15.11"

#------------ Monitor class ----------------------------------------------------
class Monitor(MySupport):

    def __init__(self, ConfigFilePath = ProgramDefaults.ConfPath):
        super(Monitor, self).__init__()

        self.ProgramName = "Generator Monitor"
        self.Version = "Unknown"
        self.log = None
        self.IsStopping = False
        self.ProgramComplete = False
        if ConfigFilePath == None or ConfigFilePath == "":
            self.ConfigFilePath = ProgramDefaults.ConfPath
        else:
            self.ConfigFilePath = ConfigFilePath

        self.ConnectionList = []    # list of incoming connections for heartbeat
        # defautl values
        self.SiteName = "Home"
        self.ServerSocket = None
        self.ServerSocketPort = ProgramDefaults.ServerPort    # server socket for nagios heartbeat and command/status
        self.IncomingEmailFolder = "Generator"
        self.ProcessedEmailFolder = "Generator/Processed"

        self.FeedbackLogFile = os.path.join(self.ConfigFilePath, "feedback.json")
        self.LogLocation = ProgramDefaults.LogPath
        self.LastLogFileSize = 0
        self.NumberOfLogSizeErrors = 0
        # set defaults for optional parameters
        self.NewInstall = False         # True if newly installed or newly upgraded version
        self.FeedbackEnabled = False    # True if sending autoated feedback on missing information
        self.FeedbackMessages = {}
        self.OneTimeMessages = {}
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
        self.UpdateAvailable = False

        # Time Sync Related Data
        self.bSyncTime = False          # Sync gen to system time
        self.bSyncDST = False           # sync time at DST change
        self.bDST = False               # Daylight Savings Time active if True
        # simulation
        self.Simulation = False
        self.SimulationFile = None

        self.console = SetupLogger("genmon_console", log_file = "", stream = True)

        if not MySupport.PermissionsOK():
            self.LogConsole("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'.")
            sys.exit(1)

        if not os.path.isfile(os.path.join(self.ConfigFilePath, 'genmon.conf')):
            self.LogConsole("Missing config file : " + os.path.join(self.ConfigFilePath, 'genmon.conf'))
            sys.exit(1)
        if not os.path.isfile(os.path.join(self.ConfigFilePath, 'mymail.conf')):
            self.LogConsole("Missing config file : " + os.path.join(self.ConfigFilePath, 'mymail.conf'))
            sys.exit(1)

        self.config = MyConfig(filename = os.path.join(self.ConfigFilePath, 'genmon.conf'), section = "GenMon", log = self.console)
        # read config file
        if not self.GetConfig():
            self.LogConsole("Failure in Monitor GetConfig")
            sys.exit(1)

        # log errors in this module to a file
        self.log = SetupLogger("genmon", os.path.join(self.LogLocation, "genmon.log"))

        self.config.log = self.log

        if self.IsLoaded(): # this checks based on the port used for the API
            self.LogConsole("ERROR: genmon.py is already loaded.")
            self.LogError("ERROR: genmon.py is already loaded.")
            sys.exit(1)

        # this check is based on the file name.
        if MySupport.IsRunning(os.path.basename(__file__), multi_instance = self.multi_instance):
            self.LogConsole("ERROR: genmon.py is already loaded.")
            self.LogError("ERROR: genmon.py is already loaded (2).")
            sys.exit(1)

        if self.NewInstall:
            self.LogError("New version detected: Old = %s, New = %s" % (self.Version, ProgramDefaults.GENMON_VERSION))
            self.Version = ProgramDefaults.GENMON_VERSION

        self.ProgramStartTime = datetime.datetime.now()     # used for com metrics
        # this will wait one day for an update, change to
        #  datetime.datetime(1, 1, 1, 0, 0) to check immediately on load
        self.LastSofwareUpdateCheck = datetime.datetime.now()

        signal.signal(signal.SIGTERM, self.SignalClose)
        signal.signal(signal.SIGINT, self.SignalClose)

        # start thread to accept incoming sockets for nagios heartbeat and command / status clients
        self.Threads["InterfaceServerThread"] = MyThread(self.InterfaceServerThread, Name = "InterfaceServerThread")

        # init mail, start processing incoming email
        self.mail = MyMail(monitor=True, incoming_folder = self.IncomingEmailFolder,
            processed_folder =self.ProcessedEmailFolder,incoming_callback = self.ProcessCommand,
            loglocation = self.LogLocation, ConfigFilePath = ConfigFilePath)

        self.Threads = self.MergeDicts(self.Threads, self.mail.Threads)
        self.MailInit = True

        self.FeedbackPipe = MyPipe("Feedback", self.FeedbackReceiver,
            log = self.log, ConfigFilePath = self.ConfigFilePath)
        self.Threads = self.MergeDicts(self.Threads, self.FeedbackPipe.Threads)
        self.MessagePipe = MyPipe("Message", self.MessageReceiver, log = self.log,
            nullpipe = self.mail.DisableSNMP, ConfigFilePath = self.ConfigFilePath)
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
                self.Controller = HPanel(self.log, newinstall = self.NewInstall, simulation = self.Simulation, simulationfile = self.SimulationFile, message = self.MessagePipe, feedback = self.FeedbackPipe, config = self.config)
            else:
                self.Controller = Evolution(self.log, self.NewInstall, simulation = self.Simulation, simulationfile = self.SimulationFile, message = self.MessagePipe, feedback = self.FeedbackPipe, config = self.config)
            self.Threads = self.MergeDicts(self.Threads, self.Controller.Threads)

        except Exception as e1:
            self.LogErrorLine("Error opening controller device: " + str(e1))
            sys.exit(1)


        self.StartThreads()

        self.ProcessFeedbackInfo()

        # send mail to tell we are starting
        self.MessagePipe.SendMessage("Generator Monitor Starting at " + self.SiteName, "Generator Monitor Starting at " + self.SiteName , msgtype = "info")

        self.LogError("GenMon Loaded for site: " + self.SiteName + " using python " + str(sys.version_info.major) + "." + str(sys.version_info.minor))

    # ------------------------ Monitor::StartThreads----------------------------
    def StartThreads(self, reload = False):

        try:
            # start thread to accept incoming sockets for nagios heartbeat
            self.Threads["ComWatchDog"] = MyThread(self.ComWatchDog, Name = "ComWatchDog")

            if self.bSyncDST or self.bSyncTime:     # Sync time thread
                self.Threads["TimeSyncThread"] = MyThread(self.TimeSyncThread, Name = "TimeSyncThread")

            if not self.DisableWeather and not self.WeatherAPIKey == None and len(self.WeatherAPIKey) and not self.WeatherLocation == None and len(self.WeatherLocation):
                Unit = 'metric' if self.UseMetric else 'imperial'
                self.MyWeather = MyWeather(self.WeatherAPIKey, location = self.WeatherLocation, unit = Unit, log = self.log)
                self.Threads = self.MergeDicts(self.Threads, self.MyWeather.Threads)
        except Exception as e1:
            self.LogErrorLine("Error in StartThreads: " + str(e1))

    # -------------------- Monitor::GetConfig-----------------------------------
    def GetConfig(self):

        try:
            if self.config.HasOption('sitename'):
                self.SiteName = self.config.ReadValue('sitename')

            self.multi_instance =  self.config.ReadValue('multi_instance', return_type = bool, default = False)

            if self.config.HasOption('incoming_mail_folder'):
                self.IncomingEmailFolder = self.config.ReadValue('incoming_mail_folder')     # imap folder for incoming mail

            if self.config.HasOption('processed_mail_folder'):
                self.ProcessedEmailFolder = self.config.ReadValue('processed_mail_folder')   # imap folder for processed mail
            #  server_port, must match value in myclient.py and check_monitor_system.py and any calling client apps
            if self.config.HasOption('server_port'):
                self.ServerSocketPort = self.config.ReadValue('server_port', return_type = int)

            self.LogLocation = self.config.ReadValue('loglocation', default = ProgramDefaults.LogPath)

            self.UserDefinedDataPath = self.config.ReadValue('userdatalocation', default = os.path.dirname(os.path.realpath(__file__)))

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

            self.AdditionalWatchdogTime = self.config.ReadValue('watchdog_addition', return_type = int, default = 0)

            if self.config.HasOption('version'):
                self.Version = self.config.ReadValue('version')
                if not self.Version == ProgramDefaults.GENMON_VERSION:
                    self.config.WriteValue('version', ProgramDefaults.GENMON_VERSION)
                    self.NewInstall = True
            else:
                self.config.WriteValue('version', ProgramDefaults.GENMON_VERSION)
                self.NewInstall = True
                self.Version = ProgramDefaults.GENMON_VERSION
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

            self.UpdateCheck = self.config.ReadValue('update_check', return_type = bool, default = True)
            self.UserURL = self.config.ReadValue('user_url',  default = "").strip()

        except Exception as e1:
            self.Console("Missing config file or config file entries (genmon): " + str(e1))
            return False

        return True

    #---------------------------------------------------------------------------
    def ProcessFeedbackInfo(self):

        try:
            if self.FeedbackEnabled:
                for Key, Entry in self.FeedbackMessages.items():
                    self.MessagePipe.SendMessage("Generator Monitor Submission", Entry , recipient = self.MaintainerAddress, files = self.GetLogFileNames(), msgtype = "error")
                # delete unsent Messages
                if os.path.isfile(self.FeedbackLogFile):
                    os.remove(self.FeedbackLogFile)
        except Exception as e1:
            self.LogErrorLine("Error in ProcessFeedbackInfo: " + str(e1))

    #---------------------------------------------------------------------------
    def FeedbackReceiver(self, Message):

        try:
            FeedbackDict = {}
            FeedbackDict = json.loads(Message)
            self.SendFeedbackInfo(FeedbackDict["Reason"],
                Always = FeedbackDict["Always"], Message = FeedbackDict["Message"],
                FullLogs = FeedbackDict["FullLogs"], NoCheck = FeedbackDict["NoCheck"])

        except Exception as e1:
            self.LogErrorLine("Error in  FeedbackReceiver: " + str(e1))
            self.LogError("Size : " + str(len(Message)))
            self.LogError("Message : " + str(Message))
    #---------------------------------------------------------------------------
    def MessageReceiver(self, Message):

        try:
            MessageDict = {}
            MessageDict = json.loads(Message)

            if MessageDict["onlyonce"]:
                Subject = self.OneTimeMessages.get(MessageDict["subjectstr"], None)
                if Subject == None:
                    self.OneTimeMessages[MessageDict["subjectstr"]] = MessageDict["msgstr"]
                else:
                    return

            self.mail.sendEmail(MessageDict["subjectstr"],
                MessageDict["msgstr"], recipient = MessageDict["recipient"],
                files = MessageDict["files"], deletefile= MessageDict["deletefile"],
                msgtype= MessageDict["msgtype"])

        except Exception as e1:
            self.LogErrorLine("Error in  MessageReceiver: " + str(e1))
    #---------------------------------------------------------------------------
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
                msgbody += self.printToString(self.ProcessDispatch(self.GetStartInfo(NoTile = True),""))
                if not self.bDisablePlatformStats:
                    msgbody += self.printToString(self.ProcessDispatch({"Platform Stats" : self.GetPlatformStats()},""))
                msgbody += self.Controller.DisplayRegisters(AllRegs = FullLogs)

                msgbody += "\n" + self.GetSupportData() + "\n"
                if self.FeedbackEnabled:
                    self.MessagePipe.SendMessage("Generator Monitor Submission", msgbody , recipient = self.MaintainerAddress, files = self.GetLogFileNames(), msgtype = "error")

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

    #---------- Monitor::GetSupportData-----------------------------------------
    def GetSupportData(self):

        SupportData = collections.OrderedDict()
        try:
            SupportData["Program Run Time"] = self.GetProgramRunTime()
            SupportData["Monitor Health"] = self.GetSystemHealth()
            SupportData["StartInfo"] = self.GetStartInfo(NoTile = True)
            if not self.bDisablePlatformStats:
                SupportData["PlatformStats"] = self.GetPlatformStats()
            SupportData["Data"] = self.Controller.DisplayRegisters(AllRegs = True, DictOut = True)
            # Raw Modbus data
            SupportData["Registers"] = self.Controller.Registers
            SupportData["Strings"] = self.Controller.Strings
            SupportData["FileData"] = self.Controller.FileData
        except Exception as e1:
            self.LogErrorLine("Error in GetSupportData: " + str(e1))

        try:
            # indent 4 will keep some mail servers from having problems.
            return json.dumps(SupportData, indent=4, sort_keys=False)
        except Exception as e1:
            self.LogErrorLine("Error in GetSupportData (2): " + str(e1))
            return "Error Getting JSON data: " + str(e1)

    #---------- Monitor::GetLogFileNames----------------------------------------
    def GetLogFileNames(self):

        try:
            LogList = []
            FilesToSend = ["genmon.log", "genserv.log", "mymail.log", "myserial.log",
                "mymodbus.log", "gengpio.log", "gengpioin.log", "gensms.log",
                "gensms_modem.log", "genmqtt.log", "genpushover.log", "gensyslog.log",
                "genloader.log", "myserialtcp.log", "genlog.log", "genslack.log",
                "genexercise.log","genemail2sms.log", "gentankutil.log", "genalexa.log",
                "gensnmp.log","gentemp.log", "gentankdiy.log", "gengpioledblink.log"]
            for File in FilesToSend:
                LogFile = self.LogLocation + File
                if os.path.isfile(LogFile):
                    LogList.append(LogFile)
            return LogList
        except Exception as e1:
            return None

    #---------- Monitor::SendSupportInfo----------------------------------------
    def SendSupportInfo(self, SendLogs = True):

        try:
            if not self.EmailSendIsEnabled():
                self.LogError("Error in SendSupportInfo: send email is not enabled")
                return "Send Email is not enabled."

            msgbody = ""
            msgbody += self.printToString(self.ProcessDispatch(self.GetStartInfo(NoTile = True),""))
            if not self.bDisablePlatformStats:
                msgbody += self.printToString(self.ProcessDispatch({"Platform Stats" : self.GetPlatformStats()},""))

            msgbody += self.Controller.DisplayRegisters(AllRegs = True)

            # get data in JSON format
            msgbody += "\n" + self.GetSupportData()  + "\n"
            msgtitle = "Generator Monitor Log File Submission"
            if SendLogs == True:
                LogList = self.GetLogFileNames()
            else:
                msgtitle = "Generator Monitor Register Submission"
                LogList = None
            self.MessagePipe.SendMessage(msgtitle, msgbody , recipient = self.MaintainerAddress, files = LogList, msgtype = "error")
            return "Log files submitted"
        except Exception as e1:
            self.LogErrorLine("Error in SendSupportInfo: " + str(e1))

    #---------- process command from email and socket --------------------------
    def ProcessCommand(self, command, fromsocket = False):

        LocalError = False
        command = command.decode('utf-8')
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
            if(not command.lower().startswith( 'generator:' )):
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

        if command.lower().startswith('generator:'):
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
            "setremote"     : [self.Controller.SetGeneratorRemoteCommand, (command.lower(),), False],
            "testcommand"   : [self.Controller.TestCommand, (command.lower(),), False],
            "network_status": [self.InternetConnected, (), False],
            "help"          : [self.DisplayHelp, (), False],                   # display help screen
            ## These commands are used by the web / socket interface only
            "power_log_json"    : [self.Controller.GetPowerHistory, (command.lower(),), True],
            "power_log_clear"   : [self.Controller.ClearPowerLog, (), True],
            "fuel_log_clear"    : [self.Controller.ClearFuelLog, (), True],
            "start_info_json"   : [self.GetStartInfo, (), True],
            "registers_json"    : [self.Controller.DisplayRegisters, (False, True), True],  # display registers
            "allregs_json"      : [self.Controller.DisplayRegisters, (True, True), True],   # display registers
            "logs_json"         : [self.Controller.DisplayLogs, (True, True), True],
            "status_json"       : [self.Controller.DisplayStatus, (True,), True],
            "status_num_json"   : [self.Controller.DisplayStatus, (True,True), True],
            "maint_json"        : [self.Controller.DisplayMaintenance, (True,), True],
            "maint_num_json"    : [self.Controller.DisplayMaintenance, (True,True), True],
            "monitor_json"      : [self.DisplayMonitor, (True,), True],
            "monitor_num_json"  : [self.DisplayMonitor, (True,True), True],
            "weather_json"      : [self.DisplayWeather, (True,), True],
            "outage_json"       : [self.Controller.DisplayOutage, (True,), True],
            "outage_num_json"   : [self.Controller.DisplayOutage, (True,True), True],
            "gui_status_json"   : [self.GetStatusForGUI, (), True],
            "get_maint_log_json": [self.Controller.GetMaintLogJSON, (), True],
            "add_maint_log"     : [self.Controller.AddEntryToMaintLog, (command,), True],    # Do not do command.lower() since this input is JSON
            "delete_row_maint_log" : [self.Controller.DeleteMaintLogRow, (command.lower(),), True],
            "edit_row_maint_log" : [self.Controller.EditMaintLogRow, (command,), True],    # Do not do command.lower() since this input is JSON
            "clear_maint_log"   : [self.Controller.ClearMaintLog, (), True],
            "getsitename"       : [self.GetSiteName, (), True],
            "getbase"           : [self.Controller.GetBaseStatus, (), True],    #  (UI changes color based on exercise, running , ready status)
            "gethealth"         : [self.GetSystemHealth, (), True],
            "getregvalue"       : [self.Controller.GetRegValue, (command.lower(),), True],     # only used for debug purposes, read a cached register value
            "readregvalue"      : [self.Controller.ReadRegValue, (command.lower(),), True],    # only used for debug purposes, Read Register Non Cached
            "getdebug"          : [self.GetDeadThreadName, (), True],           # only used for debug purposes. If a thread crashes it tells you the thread name
            "sendregisters"     : [self.SendSupportInfo, (False,), True],
            "sendlogfiles"      : [self.SendSupportInfo, (True,), True],
            "support_data_json" : [self.GetSupportData, (), True],
            "set_tank_data"     : [self.Controller.SetExternalTankData, (command,), True],
            "set_temp_data"     : [self.Controller.SetExternalTemperatureData, (command,), True],
            "set_power_data"    : [self.Controller.SetExternalCTData, (command,), True]
        }

        CommandList = command.split(' ')

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
            self.LogErrorLine("Error Processing Commands: " + command + ": "+ str(e1))

        if not ValidCommand:
            msgbody += "No valid command recognized."
        if not fromsocket:
            self.MessagePipe.SendMessage(msgsubject, msgbody, msgtype = "warn")
            return ""       # ignored by email module
        else:
            msgbody += "EndOfMessage"
            return msgbody

    #------------ Monitor::DisplayHelp -----------------------------------------
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
        outstring += self.printToString("                  if Enhanced Exercise Frequency is supported by")
        outstring += self.printToString("                  your generator:")
        outstring += self.printToString("                      i.e. setexercise=Monday,13:30,BiWeekly")
        outstring += self.printToString("                      i.e. setexercise=15,13:30,Monthly")
        outstring += self.printToString("   setquiet    - enable or disable exercise quiet mode, ")
        outstring += self.printToString("                      i.e.  setquiet=on or setquiet=off")
        outstring += self.printToString("   setremote   - issue remote command. format is setremote=command, ")
        outstring += self.printToString("                      where command is start, stop, starttransfer,")
        outstring += self.printToString("                      startexercise. i.e. setremote=start")
        outstring += self.printToString("   help        - Display help on commands")
        outstring += self.printToString("   exit        - Exit this program")
        outstring += self.printToString("   sendlogfiles - Send log files to the developer if outbound email is setup.")
        outstring += self.printToString("                      is setup.")

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

    #------------ Monitor::GetProgramRunTime -----------------------------------
    def GetProgramRunTime(self):
        try:
            ProgramRunTime = datetime.datetime.now() - self.ProgramStartTime
            outstr = str(ProgramRunTime).split(".")[0]  # remove microseconds from string
            return self.ProgramName + " running for " + outstr + "."
        except Exception as e1:
            self.LogErrorLine("Error in GetProgramRunTime:" + str(e1))
            return "Unknown"
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
            FileName = os.path.join(self.UserDefinedDataPath, "userdefined.json")

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
    def DisplayMonitor(self, DictOut = False, JSONNum = False):

        try:
            Monitor = collections.OrderedDict()
            MonitorData = []
            Monitor["Monitor"] = MonitorData
            GenMonStats = []
            SerialStats = []
            MonitorData.append({"Generator Monitor Stats" : GenMonStats})
            MonitorData.append({"Communication Stats" : self.Controller.GetCommStatus()})

            GenMonStats.append({"Monitor Health" :  self.GetSystemHealth()})
            GenMonStats.append({"Controller" : self.Controller.GetController(Actual = False)})

            GenMonStats.append({"Run time" : self.GetProgramRunTime()})
            if self.Controller.PowerMeterIsSupported():
                GenMonStats.append({"Power log file size" : self.Controller.GetPowerLogFileDetails()})
            GenMonStats.append({"Generator Monitor Version" : ProgramDefaults.GENMON_VERSION})
            GenMonStats.append({"Update Available" : "Yes" if self.UpdateAvailable else "No"})

            if not self.bDisablePlatformStats:
                PlatformStats = self.GetPlatformStats()
                if not PlatformStats == None:
                    MonitorData.append({"Platform Stats" : PlatformStats})

            WeatherData = self.GetWeatherData()
            if not WeatherData == None and len(WeatherData):
                MonitorData.append({"Weather" : WeatherData})

            UserData = self.GetUserDefinedData()
            if UserData != None and len(UserData):
                try:
                    MonitorData.append({"External Data" : UserData})
                except Exception as e1:
                    self.LogErrorLine("Error in appending user data: " + str(e1))
            if not DictOut:
                return self.printToString(self.ProcessDispatch(Monitor,""))
        except Exception as e1:
            self.LogErrorLine("Error in DisplayMonitor: " + str(e1))
        return Monitor

    #------------ Monitor::GetStartInfo-----------------------------------------
    def GetStartInfo(self, NoTile = False):

        StartInfo = collections.OrderedDict()
        StartInfo["version"] = ProgramDefaults.GENMON_VERSION
        StartInfo["sitename"] = self.SiteName
        StartInfo["python"] = str(sys.version_info.major) + "." + str(sys.version_info.minor)
        try:
            import time
            if self.is_dst:
                StartInfo["zone"] = time.tzname[1]
            else:
                StartInfo["zone"] = time.tzname[0]
        except:
            pass
        ControllerStartInfo = self.Controller.GetStartInfo(NoTile = NoTile)
        StartInfo = self.MergeDicts(StartInfo, ControllerStartInfo)
        return StartInfo

    #------------ Monitor::GetStatusForGUI -------------------------------------
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
        # Monitor Time
        Status["MonitorTime"] = datetime.datetime.now().strftime("%m/%d/%Y %H:%M")
        # Engine run hours
        Status["RunHours"] = self.Controller.GetRunHours()
        ReturnDict = self.MergeDicts(Status, self.Controller.GetStatusForGUI())

        return ReturnDict

    #-------------Monitor::GetSystemHealth--------------------------------------
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

    #----------  Monitor::StartTimeThread---------------------------------------
    def StartTimeThread(self):

        # This is done is a separate thread as not to block any return email processing
        # since we attempt to sync with generator time
        MyThread(self.Controller.SetGeneratorTimeDate, Name = "SetTimeThread")
        return "Time Set: Command Sent\n"

    #----------  Monitor::TimeSyncThread----------------------------------------
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
                    self.LogError("DST change")

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

        NoticeSent = False
        LastActiveTime = datetime.datetime.now()
        counter = 0
        while True:
            if self.WaitForExit("ComWatchDog", 1):
                return
            if counter > 30:
                self.LogError("WARNING: Initilization not complete after 30 seconds, possible communication failure. Check cabling.")
                break
            counter += 1
            if self.Controller.InitComplete:
                break

        if self.Controller.ModBus.UseTCP:
            WatchDogPollTime = 8.0
        else:
            WatchDogPollTime = 2.0

        try:
            WatchDogPollTime += float(self.Controller.ModBus.ModBusPacketTimoutMS / 1000)
        except:
            self.LogErrorLine("Error in ComWatchDog: " + str(e1))


        WatchDogPollTime += self.AdditionalWatchdogTime

        while True:
            try:
                # check for software update
                self.CheckSoftwareUpdate()
                self.CommunicationsActive = self.Controller.ComminicationsIsActive()

                if self.CommunicationsActive:
                    LastActiveTime = datetime.datetime.now()
                    if NoticeSent:
                        NoticeSent = False
                        msgbody = "Generator Monitor communications with the controller has been restored at " + self.SiteName
                        msgbody += "\n" + self.DisplayMonitor()
                        self.MessagePipe.SendMessage("Generator Monitor Communication Restored at " + self.SiteName, msgbody , msgtype = "info")
                else:
                    if self.GetDeltaTimeMinutes(datetime.datetime.now() - LastActiveTime) > (1 + self.AdditionalWatchdogTime) :
                        if not NoticeSent:
                            NoticeSent = True
                            msgbody = "Generator Monitor is not communicating with the controller at " + self.SiteName
                            msgbody += "\n" + self.DisplayMonitor()
                            self.MessagePipe.SendMessage("Generator Monitor Communication WARNING at " + self.SiteName, msgbody , msgtype = "error")

            except Exception as e1:
                self.LogErrorLine("Error in ComWatchDog: " + str(e1))

            if self.WaitForExit("ComWatchDog", WatchDogPollTime):
                return
    #---------- Monitor::CheckSoftwareUpdate------------------------------------
    def CheckSoftwareUpdate(self):

        if not self.UpdateCheck:
            return
        try:
            if self.GetDeltaTimeMinutes(datetime.datetime.now() - self.LastSofwareUpdateCheck) > 1440 :     # check every day
                self.LastSofwareUpdateCheck = datetime.datetime.now()
                # Do the check
                try:
                    url = "https://raw.githubusercontent.com/jgyates/genmon/master/genmonlib/program_defaults.py"
                    try:
                        # For Python 3.0 and later
                        from urllib.request import urlopen
                    except ImportError:
                        # Fall back to Python 2's urllib2
                        from urllib2 import urlopen

                    data = urlopen(url).read(4000) # read only first 4000 chars
                    data = data.decode('ascii')
                    data = data.split("\n") # then split it into lines

                    for line in data:

                        if 'GENMON_VERSION = "V' in line:
                            import re
                            quoted = re.compile('"([^"]*)"')
                            for value in quoted.findall(line):
                                if value != ProgramDefaults.GENMON_VERSION:
                                    # Update Available
                                    title = self.ProgramName + " Software Update " + value + " is available for site " + self.SiteName
                                    msgbody = "\nA software update is available for the " + self.ProgramName + ". The new version (" + value + ") can be updated on the About page of the web interface. The current version installed is " + ProgramDefaults.GENMON_VERSION + ". You can disable this email from being sent on the Settings page."
                                    if len(self.UserURL):
                                        msgbody += "\n\nWeb Interface URL: " + self.UserURL
                                    msgbody += "\n\nChange Log: https://raw.githubusercontent.com/jgyates/genmon/master/changelog.md"
                                    self.MessagePipe.SendMessage(title , msgbody, msgtype = "info", onlyonce = True)
                                    self.UpdateAvailable = True

                except Exception as e1:
                    self.LogErrorLine("Error checking for software update: " + str(e1))

        except Exception as e1:
            self.LogErrorLine("Error in CheckSoftwareUpdate: " + str(e1))

    #---------- Monitor::LogFileIsOK--------------------------------------------
    def LogFileIsOK(self):

        try:
            if not self.Controller.InitComplete:
                return True

            LogFile = os.path.join(self.LogLocation, "genmon.log")

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

            statusstr = ""
            if self.Controller == None:
                outstr = "WARNING: System Initializing"
                conn.sendall(outstr.encode())
            else:
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
                    if len(data):
                        if self.Controller == None:
                            outstr = "Retry, System Initializing"
                        else:
                            outstr = self.ProcessCommand(data, True)
                        conn.sendall(outstr.encode("utf-8"))
                    else:
                        # socket closed remotely
                        break
                except socket.timeout:
                    if self.IsStopping:
                        break
                    continue
                except socket.error as msg:
                    try:
                        self.ConnectionList.remove(conn)
                        conn.close()
                    except:
                        pass
                    break

        except socket.error as msg:
            self.LogError("Error in SocketWorkThread: " + str(msg))
            pass

        try:
            self.ConnectionList.remove(conn)
            conn.close()
        except:
            pass
        # end SocketWorkThread

    #----------  interface for heartbeat server thread -------------------------
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
                #self.LogError('Connected with ' + addr[0] + ':' + str(addr[1]))
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
                self.LogErrorLine("Exception in InterfaceServerThread" + str(e1))
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

    # ----------Monitor::SignalClose--------------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(1)

    #---------------------Monitor::Close----------------------------------------
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

#------------------- Command-line interface for monitor ------------------------
if __name__=='__main__': #

    try:
        ConfigFilePath = ProgramDefaults.ConfPath
        opts, args = getopt.getopt(sys.argv[1:],"c:",["configpath="])
    except getopt.GetoptError:
        console.error("Invalid command line argument.")
        sys.exit(2)

    for opt, arg in opts:

        if opt in ("-c", "--configpath"):
            ConfigFilePath = arg
            ConfigFilePath = ConfigFilePath.strip()

    #Start things up
    MyMonitor = Monitor(ConfigFilePath = ConfigFilePath)

    try:
        while not MyMonitor.ProgramComplete:
            time.sleep(0.01)
        sys.exit(0)
    except:
        sys.exit(1)
