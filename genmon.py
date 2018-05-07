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

try:
    from ConfigParser import RawConfigParser
except ImportError as e:
    from configparser import RawConfigParser

from genmonlib import mymail, mylog, mythread, mypipe, mysupport, generac_evolution, generac_HPanel


GENMON_VERSION = "V1.7.8"

#------------ Monitor class --------------------------------------------
class Monitor(mysupport.MySupport):

    def __init__(self):
        super(Monitor, self).__init__()
        self.ProgramName = "Generator Monitor"
        self.Version = "Unknown"
        self.ConnectionList = []    # list of incoming connections for heartbeat
        # defautl values
        self.SiteName = "Home"
        self.ServerSocket = 9082    # server socket for nagios heartbeat and command/status
        self.IncomingEmailFolder = "Generator"
        self.ProcessedEmailFolder = "Generator/Processed"

        self.PowerLogMaxSize = 15       # 15 MB max size
        self.PowerLog =  os.path.dirname(os.path.realpath(__file__)) + "/kwlog.txt"
        self.FeedbackLogFile = os.path.dirname(os.path.realpath(__file__)) + "/feedback.json"

        # set defaults for optional parameters
        self.NewInstall = False         # True if newly installed or newly upgraded version
        self.FeedbackEnabled = False    # True if sending autoated feedback on missing information
        self.FeedbackMessages = {}
        self.MailInit = False       # set to true once mail is init
        self.CommunicationsActive = False   # Flag to let the heartbeat thread know we are communicating
        self.Controller = None
        self.ControllerSelected = None

        # Time Sync Related Data
        self.bSyncTime = False          # Sync gen to system time
        self.bSyncDST = False           # sync time at DST change
        self.bDST = False               # Daylight Savings Time active if True
        self.bSimulation = False

        # read config file
        if not self.GetConfig():
            raise Exception("Failure in Monitor GetConfig: " + str(e1))
            return None

        # log errors in this module to a file
        self.log = mylog.SetupLogger("genmon", self.LogLocation + "genmon.log")

        if self.NewInstall:
            self.LogError("New version detected: Old = %s, New = %s" % (self.Version, GENMON_VERSION))
            self.Version = GENMON_VERSION

        self.ProgramStartTime = datetime.datetime.now()     # used for com metrics

        self.OutageStartTime = self.ProgramStartTime    # if these two are the same, no outage has occured
        self.LastOutageDuration = self.OutageStartTime - self.OutageStartTime

        atexit.register(self.Close)

        self.FeedbackPipe = mypipe.MyPipe("Feedback", self.FeedbackReceiver, log = self.log)
        self.Threads = self.MergeDicts(self.Threads, self.FeedbackPipe.Threads)
        self.MessagePipe = mypipe.MyPipe("Message", self.MessageReceiver, log = self.log)
        self.Threads = self.MergeDicts(self.Threads, self.MessagePipe.Threads)

        try:
            #Starting device connection
            if self.bSimulation:
                self.LogError("Simulation Running")
            if not self.ControllerSelected == None:
                self.LogError("Selected Controller: " + str(self.ControllerSelected))
            else:
                self.ControllerSelected = "generac_evo_nexus"

            if self.ControllerSelected.lower() == "h_100" :
                self.Controller = generac_HPanel.HPanel(self.log, newinstall = self.NewInstall, simulation = self.bSimulation)
            else:
                self.Controller = generac_evolution.Evolution(self.log, self.NewInstall, simulation = self.bSimulation)
            self.Threads = self.MergeDicts(self.Threads, self.Controller.Threads)

        except Exception as e1:
            self.FatalError("Error opening controller device: " + str(e1))
            return None

        # init mail, start processing incoming email
        self.mail = mymail.MyMail(monitor=True, incoming_folder = self.IncomingEmailFolder, processed_folder =self.ProcessedEmailFolder,incoming_callback = self.ProcessCommand)
        self.Threads = self.MergeDicts(self.Threads, self.mail.Threads)
        self.MailInit = True

        # send mail to tell we are starting
        self.MessagePipe.SendMessage("Generator Monitor Starting at " + self.SiteName, "Generator Monitor Starting at " + self.SiteName , msgtype = "info")

        self.ProcessFeedbackInfo()
        self.StartThreads()

        self.LogError("GenMon Loadded for site: " + self.SiteName)

    # ------------------------ Monitor::StartThreads----------------------------
    def StartThreads(self, reload = False):

        # start thread to accept incoming sockets for nagios heartbeat
        self.Threads["ComWatchDog"] = mythread.MyThread(self.ComWatchDog, Name = "ComWatchDog")

        if not reload:
            # This thread remains open during a reload
            # start thread to accept incoming sockets for nagios heartbeat and command / status clients
            self.Threads["InterfaceServerThread"] = mythread.MyThread(self.InterfaceServerThread, Name = "InterfaceServerThread")

        # start thread to accept incoming sockets for nagios heartbeat
        self.Threads["PowerMeter"] = mythread.MyThread(self.PowerMeter, Name = "PowerMeter")

        if self.bSyncDST or self.bSyncTime:     # Sync time thread
            self.Threads["TimeSyncThread"] = mythread.MyThread(self.TimeSyncThread, Name = "TimeSyncThread")

    # -------------------- Monitor::GetConfig-----------------------------------
    def GetConfig(self, reload = False):

        ConfigSection = "GenMon"
        try:
            # read config file
            config = RawConfigParser()
            # config parser reads from current directory, when running form a cron tab this is
            # not defined so we specify the full path
            config.read('/etc/genmon.conf')

            # getfloat() raises an exception if the value is not a float
            # getint() and getboolean() also do this for their respective types

            if config.has_option(ConfigSection, 'sitename'):
                self.SiteName = config.get(ConfigSection, 'sitename')

            if config.has_option(ConfigSection, 'incoming_mail_folder'):
                self.IncomingEmailFolder = config.get(ConfigSection, 'incoming_mail_folder')     # imap folder for incoming mail

            if config.has_option(ConfigSection, 'processed_mail_folder'):
                self.ProcessedEmailFolder = config.get(ConfigSection, 'processed_mail_folder')   # imap folder for processed mail
            #  server_port, must match value in myclient.py and check_monitor_system.py and any calling client apps
            if config.has_option(ConfigSection, 'server_port'):
                self.ServerSocketPort = config.getint(ConfigSection, 'server_port')

            if config.has_option(ConfigSection, 'loglocation'):
                self.LogLocation = config.get(ConfigSection, 'loglocation')

            if config.has_option(ConfigSection, 'kwlog'):
                self.PowerLog = config.get(ConfigSection, 'kwlog')
            if config.has_option(ConfigSection, 'kwlogmax'):
                self.PowerLogMaxSize = config.getint(ConfigSection, 'kwlogmax')

            if config.has_option(ConfigSection, 'syncdst'):
                self.bSyncDST = config.getboolean(ConfigSection, 'syncdst')
            if config.has_option(ConfigSection, 'synctime'):
                self.bSyncTime = config.getboolean(ConfigSection, 'synctime')

            if config.has_option(ConfigSection, 'simulation'):
                self.bSimulation = config.getboolean(ConfigSection, 'simulation')

            if config.has_option(ConfigSection, 'controllertype'):
                self.ControllerSelected = config.get(ConfigSection, 'controllertype')

            if config.has_option(ConfigSection, 'version'):
                self.Version = config.get(ConfigSection, 'version')
                if not self.Version == GENMON_VERSION:
                    self.AddItemToConfFile('version', GENMON_VERSION)
                    self.NewInstall = True
            else:
                self.AddItemToConfFile('version', GENMON_VERSION)
                self.NewInstall = True
            if config.has_option(ConfigSection, "autofeedback"):
                self.FeedbackEnabled = config.getboolean(ConfigSection, 'autofeedback')
            else:
                self.AddItemToConfFile('autofeedback', "False")
                self.FeedbackEnabled = False
            # Load saved feedback log if log is present
            if os.path.isfile(self.FeedbackLogFile):
                with open(self.FeedbackLogFile) as infile:
                    self.FeedbackMessages = json.load(infile)

        except Exception as e1:
            if not reload:
                raise Exception("Missing config file or config file entries: " + str(e1))
            else:
                self.LogErrorLine("Error reloading config file" + str(e1))
            return False

        return True

    #------------------------------------------------------------
    def ProcessFeedbackInfo(self):

        if self.FeedbackEnabled:
            for Key, Entry in self.FeedbackMessages.items():
                self.MessagePipe.SendMessage("Generator Monitor Submission", Entry , recipient = "generatormonitor.software@gmail.com", msgtype = "error")
            # delete unsent Messages
            if os.path.isfile(self.FeedbackLogFile):
                os.remove(self.FeedbackLogFile)

    #------------------------------------------------------------
    def FeedbackReceiver(self, Message):

        try:
            FeedbackDict = {}
            FeedbackDict = json.loads(Message)
            self.SendFeedbackInfo(FeedbackDict["Reason"], FeedbackDict["Always"], FeedbackDict["Message"], FeedbackDict["FullLogs"])
        except Exception as e1:
            self.LogErrorLine("Error in  FeedbackReceiver: " + str(e1))

    #------------------------------------------------------------
    def MessageReceiver(self, Message):

        try:
            MessageDict = {}
            MessageDict = json.loads(Message)
            self.mail.sendEmail(MessageDict["subjectstr"], MessageDict["msgstr"], MessageDict["recipient"], MessageDict["files"],MessageDict["deletefile"] ,MessageDict["msgtype"])
        except Exception as e1:
            self.LogErrorLine("Error in  MessageReceiver: " + str(e1))
    #------------------------------------------------------------
    def SendFeedbackInfo(self, Reason, Always = False, Message = None, FullLogs = False):
        try:
            if self.NewInstall or Always:

                CheckedSent = self.FeedbackMessages.get(Reason, "")

                if not CheckedSent == "":
                    return

                msgbody = "Reason = " + Reason + "\n"
                if Message != None:
                    msgbody += "Message : " + Message + "\n"
                msgbody += "Version: " + GENMON_VERSION
                msgbody += self.DictToString(self.Controller.GetStartInfo())
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

    #---------- Monitor::SendRegisters------------------------------------------
    def SendRegisters(self):

        msgbody = ""
        msgbody += "Version: " + GENMON_VERSION
        msgbody += self.DictToString(self.Controller.GetStartInfo())
        msgbody += self.Controller.DisplayRegisters(AllRegs = True)
        self.MessagePipe.SendMessage("Generator Monitor Register Submission", msgbody , recipient = self.MaintainerAddress, msgtype = "info")
        return "Registers submitted"

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
            "help"          : [self.DisplayHelp, (), False],                   # display help screen
            "setremote"     : [self.Controller.SetGeneratorRemoteStartStop, (command.lower(),), False],
            ## These commands are used by the web / socket interface only
            "power_log_json"    : [self.GetPowerHistory, (command.lower(),), True],
            "power_log_clear"   : [self.ClearPowerLog, (), True],
            "start_info_json"   : [self.Controller.GetStartInfo, (), True],
            "registers_json"    : [self.Controller.DisplayRegisters, (False, True), True],  # display registers
            "allregs_json"      : [self.Controller.DisplayRegisters, (True, True), True],   # display registers
            "logs_json"         : [self.Controller.DisplayLogs, (True, True), True],
            "status_json"       : [self.Controller.DisplayStatus, (True,), True],
            "maint_json"        : [self.Controller.DisplayMaintenance, (True,), True],
            "monitor_json"      : [self.DisplayMonitor, (True,), True],
            "outage_json"       : [self.Controller.DisplayOutage, (True,), True],
            "gui_status_json"   : [self.GetStatusForGUI, (), True],
            "getsitename"       : [self.GetSiteName, (), True],
            "getbase"           : [self.Controller.GetBaseStatus, (), True],    #  (UI changes color based on exercise, running , ready status)
            "gethealth"         : [self.GetSystemHealth, (), True],
            #"getexercise"       : [self.Controller.GetParsedExerciseTime, (), True],
            "getregvalue"       : [self.Controller.GetRegValue, (command.lower(),), True],     # only used for debug purposes, read a cached register value
            "readregvalue"      : [self.Controller.ReadRegValue, (command.lower(),), True],    # only used for debug purposes, Read Register Non Cached
            "getdebug"          : [self.GetDeadThreadName, (), True],           # only used for debug purposes. If a thread crashes it tells you the thread name
            "sendregisters"     : [self.SendRegisters, (), True]
        }

        CommandList = command.split(b' ')    # PYTHON3

        try:
            for item in CommandList:
                if not len(item):
                    continue
                item = item.strip()
                LookUp = item
                if "=" in item:
                    BaseCmd = item.split('=')
                    LookUp = BaseCmd[0]
                ExecList = CommandDict.get(LookUp.lower(),None)
                if ExecList == None:
                    continue
                if ExecList[0] == None:
                    continue
                if not fromsocket and ExecList[2]:
                    continue
                # Execut Command
                ReturnMessage = ExecList[0](*ExecList[1])

                if item.lower().endswith("_json"):
                    msgbody += json.dumps(ReturnMessage, sort_keys=False)
                else:
                    msgbody += ReturnMessage

                if not fromsocket:
                    msgbody += "\n"
        except Exception as e1:
            self.LogErrorLine("Error Processing Commands: " + str(e1))

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

    #------------ Monitor::DisplayMonitor --------------------------------------------
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

            if not DictOut:
                return self.printToString(self.ProcessDispatch(Monitor,""))
        except Exception as e1:
            self.LogErrorLine("Error in DisplayMonitor: " + str(e1))
        return Monitor

    #------------ Monitor::GetSiteName-------------------------------
    def GetSiteName(self):
        return self.SiteName

    #------------ Monitor::PrunePowerLog-------------------------
    def PrunePowerLog(self, Minutes):

        if not Minutes:
            return self.ClearPowerLog()

        try:
            CmdString = "power_log_json=%d" % Minutes
            PowerLog = self.GetPowerHistory(CmdString, NoReduce = True)

            LogSize = os.path.getsize(self.PowerLog)
            self.ClearPowerLog()

            # is the file size too big?
            if LogSize / (1024*1024) >= self.PowerLogMaxSize:
                return "OK"

            if LogSize / (1024*1024) >= self.PowerLogMaxSize * 0.8:
                msgbody = "The kwlog file size is 80% of the maximum. Once the log reaches 100% of the maximum size the log will be reset."
                self.MessagePipe.SendMessage("Notice: Log file size warning" , msgbody, msgtype = "warn")

            # Write oldest log entries first
            for Items in reversed(PowerLog):
                self.LogToFile(self.PowerLog, Items[0], Items[1])

            LogSize = os.path.getsize(self.PowerLog)
            if LogSize == 0:
                TimeStamp = datetime.datetime.now().strftime('%x %X')
                self.LogToFile(self.PowerLog, TimeStamp, "0.0")

            return "OK"

        except Exception as e1:
            self.LogErrorLine("Error in  ClearPowerLog: " + str(e1))
            return "Error in  ClearPowerLog: " + str(e1)

    #------------ Monitor::ClearPowerLog-------------------------
    def ClearPowerLog(self):

        try:
            if not len(self.PowerLog):
                return "Power Log Disabled"

            if not os.path.isfile(self.PowerLog):
                return "Power Log is empty"
            os.remove(self.PowerLog)

            # add zero entry to note the start of the log
            TimeStamp = datetime.datetime.now().strftime('%x %X')
            self.LogToFile(self.PowerLog, TimeStamp, "0.0")

            return "Power Log cleared"
        except Exception as e1:
            self.LogErrorLine("Error in  ClearPowerLog: " + str(e1))
            return "Error in  ClearPowerLog: " + str(e1)

    #------------ Monitor::ReducePowerSamples-------------------------
    def ReducePowerSamplesOld(self, PowerList, MaxSize):

        if MaxSize == 0:
            self.LogError("RecducePowerSamples: Error: Max size is zero")
            return []

        if len(PowerList) < MaxSize:
            self.LogError("RecducePowerSamples: Error: Can't reduce ")
            return PowerList

        try:
            Sample = int(len(PowerList) / MaxSize)
            Remain = int(len(PowerList) % MaxSize)

            NewList = []
            Count = 0
            for Count in range(len(PowerList)):
                TimeStamp, KWValue = PowerList[Count]
                if float(KWValue) == 0:
                        NewList.append([TimeStamp,KWValue])
                elif ( Count % Sample == 0 ):
                    NewList.append([TimeStamp,KWValue])

            # if we have too many entries due to a remainder or not removing zero samples, then delete some
            if len(NewList) > MaxSize:
                return RemovePowerSamples(NewList, MaxSize)
        except Exception as e1:
            self.LogErrorLine("Error in RecducePowerSamples: %s" % str(e1))
            return PowerList

        return NewList

    #------------ Monitor::RemovePowerSamples-------------------------
    def RemovePowerSamples(List, MaxSize):

        try:
            if len(List) <= MaxSize:
                self.LogError("RemovePowerSamples: Error: Can't remove ")
                return List

            Extra = len(List) - MaxSize
            for Count in range(Extra):
                    # assume first and last sampels are zero samples so don't select thoes
                    self.MarkNonZeroKwEntry(List, random.randint(1, len(List) - 2))

            TempList = []
            for TimeStamp, KWValue in List:
                if not TimeStamp == "X":
                    TempList.append([TimeStamp, KWValue])
            return TempList
        except Exception as e1:
            self.LogErrorLine("Error in RemovePowerSamples: %s" % str(e1))
            return List

    #------------ Monitor::MarkNonZeroKwEntry-------------------------
    #       RECURSIVE
    def MarkNonZeroKwEntry(self, List, Index):

        try:
            TimeStamp, KwValue = List[Index]
            if not KwValue == "X" and not float(KwValue) == 0.0:
                List[Index] = ["X", "X"]
                return
            else:
                MarkNonZeroKwEntry(List, Index - 1)
                return
        except Exception as e1:
            self.LogErrorLine("Error in MarkNonZeroKwEntry: %s" % str(e1))
        return

    #------------ Monitor::ReducePowerSamples-------------------------
    def ReducePowerSamples(self, PowerList, MaxSize):

        if MaxSize == 0:
            self.LogError("RecducePowerSamples: Error: Max size is zero")
            return []

        periodMaxSamples = MaxSize
        NewList = []
        try:
            CurrentTime = datetime.datetime.now()
            secondPerSample = 0
            prevMax = 0
            currMax = 0
            currTime = CurrentTime
            prevTime = CurrentTime + datetime.timedelta(minutes=1)
            currSampleTime = CurrentTime
            prevBucketTime = CurrentTime # prevent a 0 to be written the first time
            nextBucketTime = CurrentTime - datetime.timedelta(seconds=1)

            for Count in range(len(PowerList)):
               TimeStamp, KWValue = PowerList[Count]
               struct_time = time.strptime(TimeStamp, "%x %X")
               delta_sec = (CurrentTime - datetime.datetime.fromtimestamp(time.mktime(struct_time))).total_seconds()
               if 0 <= delta_sec <= datetime.timedelta(minutes=60).total_seconds():
                   secondPerSample = int(datetime.timedelta(minutes=60).total_seconds() / periodMaxSamples)
               if datetime.timedelta(minutes=60).total_seconds() <= delta_sec <=  datetime.timedelta(hours=24).total_seconds():
                   secondPerSample = int(datetime.timedelta(hours=23).total_seconds() / periodMaxSamples)
               if datetime.timedelta(hours=24).total_seconds() <= delta_sec <= datetime.timedelta(days=7).total_seconds():
                   secondPerSample = int(datetime.timedelta(days=6).total_seconds() / periodMaxSamples)
               if datetime.timedelta(days=7).total_seconds() <= delta_sec <= datetime.timedelta(days=31).total_seconds():
                   secondPerSample = int(datetime.timedelta(days=25).total_seconds() / periodMaxSamples)

               currSampleTime = CurrentTime - datetime.timedelta(seconds=(int(delta_sec / secondPerSample)*secondPerSample))
               if (currSampleTime != currTime):
                   if ((currMax > 0) and (prevBucketTime != prevTime)):
                       NewList.append([prevBucketTime.strftime('%x %X'), 0.0])
                   if ((currMax > 0) or ((currMax == 0) and (prevMax > 0))):
                       NewList.append([currTime.strftime('%x %X'), currMax])
                   if ((currMax > 0) and (nextBucketTime != currSampleTime)):
                       NewList.append([nextBucketTime.strftime('%x %X'), 0.0])
                   prevMax = currMax
                   prevTime = currTime
                   currMax = KWValue
                   currTime = currSampleTime
                   prevBucketTime  = CurrentTime - datetime.timedelta(seconds=((int(delta_sec / secondPerSample)+1)*secondPerSample))
                   nextBucketTime  = CurrentTime - datetime.timedelta(seconds=((int(delta_sec / secondPerSample)-1)*secondPerSample))
               else:
                   currMax = max(currMax, KWValue)


            NewList.append([currTime.strftime('%x %X'), currMax])
        except Exception as e1:
            self.LogErrorLine("Error in RecducePowerSamples: %s" % str(e1))
            return PowerList

        return NewList

    #------------ Monitor::-------------------------
    def GetPowerHistory(self, CmdString, NoReduce = False):

        KWHours = False
        msgbody = "Invalid command syntax for command power_log_json"

        try:
            if not len(self.PowerLog):
                # power log disabled
                return []

            if not len(CmdString):
                self.LogError("Error in GetPowerHistory: Invalid input")
                return []

            #Format we are looking for is "power_log_json=5" or "power_log_json" or "power_log_json=1000,kw"
            CmdList = CmdString.split("=")

            if len(CmdList) > 2:
                self.LogError("Validation Error: Error parsing command string in GetPowerHistory (parse): " + CmdString)
                return msgbody

            CmdList[0] = CmdList[0].strip()

            if not CmdList[0].lower() == "power_log_json":
                self.LogError("Validation Error: Error parsing command string in GetPowerHistory (parse2): " + CmdString)
                return msgbody

            if len(CmdList) == 2:
                ParseList = CmdList[1].split(",")
                if len(ParseList) == 1:
                    Minutes = int(CmdList[1].strip())
                elif len(ParseList) == 2:
                    Minutes = int(ParseList[0].strip())
                    if ParseList[1].strip().lower() == "kw":
                        KWHours = True
                else:
                    self.LogError("Validation Error: Error parsing command string in GetPowerHistory (parse3): " + CmdString)
                    return msgbody

            else:
                Minutes = 0
        except Exception as e1:
            self.LogErrorLine("Error in  GetPowerHistory (Parse): %s : %s" % (CmdString,str(e1)))
            return msgbody

        try:
            # check to see if a log file exist yet
            if not os.path.isfile(self.PowerLog):
                return []

            PowerList = []

            with open(self.PowerLog,"r") as LogFile:     #opens file
                CurrentTime = datetime.datetime.now()
                try:
                    for line in LogFile:
                        line = line.strip()                  # remove whitespace at beginning and end

                        if not len(line):
                            continue
                        if line[0] == "#":                  # comment
                            continue
                        Items = line.split(",")
                        if len(Items) != 2:
                            continue

                        if Minutes:
                            struct_time = time.strptime(Items[0], "%x %X")
                            LogEntryTime = datetime.datetime.fromtimestamp(time.mktime(struct_time))
                            Delta = CurrentTime - LogEntryTime
                            if self.GetDeltaTimeMinutes(Delta) < Minutes :
                                PowerList.insert(0, [Items[0], Items[1]])
                        else:
                            PowerList.insert(0, [Items[0], Items[1]])
                    #Shorten list to 1000 if specific duration requested
                    if not KWHours and len(PowerList) > 500 and Minutes and not NoReduce:
                        PowerList = self.ReducePowerSamples(PowerList, 500)
                except Exception as e1:
                    self.LogErrorLine("Error in  GetPowerHistory (parse file): " + str(e1))
                    # continue to the next line

            if KWHours:
                TotalTime = datetime.timedelta(seconds=0)
                TotalPower = 0
                LastTime = None
                for Items in PowerList:
                    Power = float(Items[1])
                    struct_time = time.strptime(Items[0], "%x %X")
                    LogEntryTime = datetime.datetime.fromtimestamp(time.mktime(struct_time))
                    if LastTime == None or Power == 0:
                        TotalTime += LogEntryTime - LogEntryTime
                    else:
                        TotalTime += LastTime - LogEntryTime
                    LastTime = LogEntryTime

                    TotalPower += Power
                # return KW Hours
                return "%.2f" % ((TotalTime.total_seconds() / 3600) * TotalPower)

            return PowerList

        except Exception as e1:
            self.LogErrorLine("Error in  GetPowerHistory: " + str(e1))
            msgbody = "Error in  GetPowerHistory: " + str(e1)
            return msgbody

    #----------  Monitor::PowerMeter-------------------------------------
    #----------  Monitors Power Output
    def PowerMeter(self):

        if not len(self.PowerLog):
            self.LogError("Power Log Disabled")
            self.KillThread("PowerMeter", CleanupSelf = True)
            return

        # make sure system is up and running otherwise we will not know which controller is present
        while True:
            time.sleep(1)
            if self.Controller.InitComplete:
                break
            if self.IsStopSignaled("PowerMeter"):
                return

        if not self.Controller.PowerMeterIsSupported():
            self.KillThread("PowerMeter", CleanupSelf = True)
            return

        self.LogError("Power Log Started")
        # if log file is empty or does not exist, make a zero entry in log to denote start of collection
        if not os.path.isfile(self.PowerLog) or os.path.getsize(self.PowerLog) == 0:
            TimeStamp = datetime.datetime.now().strftime('%x %X')
            self.LogToFile(self.PowerLog, TimeStamp, "0.0")

        LastValue = 0.0
        LastPruneTime = datetime.datetime.now()
        while True:
            try:
                time.sleep(5)

                # Housekeeping on kw Log
                if self.GetDeltaTimeMinutes(datetime.datetime.now() - LastPruneTime) > 1440 :     # check every day
                    self.PrunePowerLog(43800)   # delete log entries greater than one month
                    LastPruneTime = datetime.datetime.now()

                # Time to exit?
                if self.IsStopSignaled("PowerMeter"):
                    return
                KWOut = self.removeAlpha(self.Controller.GetPowerOutput())
                KWFloat = float(KWOut)

                if LastValue == KWFloat:
                    continue

                if LastValue == 0:
                    StartTime = datetime.datetime.now() - datetime.timedelta(seconds=1)
                    TimeStamp = StartTime.strftime('%x %X')
                    self.LogToFile(self.PowerLog, TimeStamp, str(LastValue))

                LastValue = KWFloat
                # Log to file
                TimeStamp = datetime.datetime.now().strftime('%x %X')
                self.LogToFile(self.PowerLog, TimeStamp, str(KWFloat))

            except Exception as e1:
                self.LogErrorLine("Error in PowerMeter: " + str(e1))


    #------------ Monitor::GetStatusForGUI ------------------------------------
    def GetStatusForGUI(self):

        Status = {}

        Status["UnsentFeedback"] = str(os.path.isfile(self.FeedbackLogFile))
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

        while True:
            time.sleep(1)
            if self.Controller.InitComplete:
                break
            if self.IsStopSignaled("TimeSyncThread"):
                return

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

            for x in range(0, 60):
                for y in range(0, 60):
                    time.sleep(1)
                    if self.IsStopSignaled("TimeSyncThread"):
                        return

    #----------  Monitor::is_dst-------------------------------------
    def is_dst(self):
        #Determine whether or not Daylight Savings Time (DST) is currently in effect
        t = time.localtime()
        isdst = t.tm_isdst
        return (isdst != 0)

    #----------  Monitor::ComWatchDog-------------------------------------
    #----------  monitors receive data status to make sure we are still communicating
    def ComWatchDog(self):

        self.CommunicationsActive = False

        while True:

            self.CommunicationsActive = self.Controller.ComminicationsIsActive()
            time.sleep(2)

            if self.IsStopSignaled("ComWatchDog"):
                break

    #---------- Monitor:: AreThreadsAlive----------------------------------
    # ret true if all threads are alive
    def AreThreadsAlive(self):

        for Name, MyThreadObj in self.Threads.items():
            if not MyThreadObj.IsAlive():
                return False

        return True

    #---------- Monitor::GetDeadThreadName----------------------------------
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
                    self.ConnectionList.remove(conn)
                    conn.close()
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
            except Exception as e1:
                self.LogErrorLine("Excpetion in InterfaceServerThread" + str(e1))
                time.sleep(0.5)
                continue

        self.ServerSocket.close()
        #

    #---------------------Monitor::Close------------------------
    def Close(self):

        if self.MailInit:
            self.MessagePipe.SendMessage("Generator Monitor Stopping at " + self.SiteName, "Generator Monitor Stopping at " + self.SiteName, msgtype = "info" )

        for item in self.ConnectionList:
            try:
                item.close()
            except:
                continue
            self.ConnectionList.remove(item)

        if(self.ServerSocket):
            self.ServerSocket.shutdown(socket.SHUT_RDWR)
            self.ServerSocket.close()

        if not self.Controller == None:
            if self.Controller.InitComplete:
                self.Controller.Close()

        self.FeedbackPipe.Close()
        self.MessagePipe.Close()

#----------  Signal Handler ------------------------------------------
def signal_handler(signal, frame):


    sys.exit(0)

    # end signal_handler

#------------------- Command-line interface for monitor -----------------#
if __name__=='__main__': #


    # Set the signal handler
    signal.signal(signal.SIGINT, signal_handler)

    #Start things up
    MyMonitor = Monitor()

    while True:
        time.sleep(1)
