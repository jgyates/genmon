#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: genexercise.py
# PURPOSE: genexercise.py add enhanced exercise functionality for Evolution and Nexus cotrollers
#
#  AUTHOR: jgyates
#    DATE: 02-23-2019
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------


import datetime, time, sys, signal, os, threading, collections, json, ssl
import atexit, getopt

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

#------------ GenExercise class ------------------------------------------------
class GenExercise(MySupport):

    #------------ GenExercise::init---------------------------------------------
    def __init__(self,
        log = None,
        loglocation = ProgramDefaults.LogPath,
        ConfigFilePath = MyCommon.DefaultConfPath,
        host = ProgramDefaults.LocalHost,
        port = ProgramDefaults.ServerPort):

        super(GenExercise, self).__init__()

        self.LogFileName = os.path.join(loglocation, "genexercise.log")
        self.AccessLock = threading.Lock()
        # log errors in this module to a file
        self.log = SetupLogger("genexercise", self.LogFileName)

        self.console = SetupLogger("genexercise_console", log_file = "", stream = True)

        self.MonitorAddress = host
        self.PollTime =  2
        self.ExerciseActive = False
        self.Debug = False

        try:
            self.config = MyConfig(filename = os.path.join(ConfigFilePath, 'genexercise.conf'), section = 'genexercise', log = self.log)

            self.ExerciseType = self.config.ReadValue('exercise_type', default = "Normal")
            self.ExerciseHour = self.config.ReadValue('exercise_hour', return_type = int, default = 12)
            self.ExerciseMinute = self.config.ReadValue('exercise_minute', return_type = int, default = 0)
            self.ExerciseDayOfMonth = self.config.ReadValue('exercise_day_of_month', return_type = int, default = 1)
            self.ExerciseDayOfWeek = self.config.ReadValue('exercise_day_of_week',  default = "Monday")
            self.ExerciseDuration = self.config.ReadValue('exercise_duration', return_type = float, default = 12)
            self.ExerciseWarmup = self.config.ReadValue('exercise_warmup', return_type = float, default = 0)
            self.ExerciseFrequency = self.config.ReadValue('exercise_frequency',  default = "Monthly")
            self.MonitorAddress = self.config.ReadValue('monitor_address', default = ProgramDefaults.LocalHost)
            self.LastExerciseTime = self.config.ReadValue('last_exercise',  default = None)
            self.UseGeneratorTime = self.config.ReadValue('use_gen_time',  return_type = bool, default = False)
            self.Debug = self.config.ReadValue('debug', return_type = bool, default = False)

            # Validate settings
            if not self.ExerciseType.lower() in ["normal","quiet", "transfer"]:
                self.ExerciseType = "normal"
            if self.ExerciseHour  > 23 or self.ExerciseHour < 0:
                self.ExerciseHour = 12
            if self.ExerciseMinute  > 59 or self.ExerciseMinute < 0:
                self.ExerciseMinute = 0
            if not self.ExerciseDayOfWeek.lower() in ["monday", "tuesday", "wednesday","thursday","friday","saturday","sunday"]:
                self.ExerciseDayOfWeek = "Monday"
            if self.ExerciseDayOfMonth  > 28 or self.ExerciseDayOfMonth < 1:
                self.ExerciseDayOfMonth = 1
            if self.ExerciseDuration  > 60:
                self.ExerciseDuration = 60
            if self.ExerciseDuration  < 5:
                self.ExerciseDuration = 5
            if self.ExerciseWarmup  > 30:
                self.ExerciseWarmup = 30
            if self.ExerciseWarmup  < 0:
                self.ExerciseWarmup = 0
            if not self.ExerciseFrequency.lower() in ["weekly","biweekly", "monthly"]:
                self.ExerciseFrequency = "Monthly"

            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost

        except Exception as e1:
            self.LogErrorLine("Error reading " + os.path.join(ConfigFilePath, "genexercise.conf") + ": " + str(e1))
            self.console.error("Error reading " + os.path.join(ConfigFilePath, "genexercise.conf") + ": " + str(e1))
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
                self.LogErrorLine("Error in genexercise init: "  + str(e1))

            if not self.CheckGeneratorRequirement():
                self.LogError("Requirements not met. Exiting.")
                sys.exit(1)

            # start thread monitor time for exercise
            self.Threads["ExerciseThread"] = MyThread(self.ExerciseThread, Name = "ExerciseThread", start = False)
            self.Threads["ExerciseThread"].Start()

            try:
                if self.ExerciseFrequency.lower() == "monthly":
                    DayStr = "Day " + str(self.ExerciseDayOfMonth)
                else:
                    DayStr = str(self.ExerciseDayOfWeek)

                self.LogError("Execise: " + self.ExerciseType + ", " + self.ExerciseFrequency + " at "
                    + str(self.ExerciseHour) + ":" + str(self.ExerciseMinute) + " on " + DayStr + " for "
                    + str(self.ExerciseDuration) + " min. Warmup: " + str(self.ExerciseWarmup))
                self.DebugOutput("Debug Enabled")
            except Exception as e1:
                self.LogErrorLine(str(e1))
            atexit.register(self.Close)
            signal.signal(signal.SIGTERM, self.Close)
            signal.signal(signal.SIGINT, self.Close)

        except Exception as e1:
            self.LogErrorLine("Error in GenExercise init: " + str(e1))
            self.console.error("Error in GenExercise init: " + str(e1))
            sys.exit(1)

    #----------  GenExercise::SendCommand --------------------------------------
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
    #----------  GenExercise::CheckGeneratorRequirement ------------------------
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

    # ---------- GenExercise::PostWarmup----------------------------------------
    def PostWarmup(self):

        # check to see if the generator is running
        status = self.SendCommand("generator: getbase")
        if not status.lower() in ["running", "exercising"]:
            self.LogError("WARNING: generator not running post warmup. Transfer switch not activated.")
            self.SendCommand("generator: setremote=stop")
            return

        self.SendCommand("generator: setremote=starttransfer")
        self.DebugOutput("Starting transfer exercise cycle (post warmup).")
        # set timer to stop
        self.StopTimer = threading.Timer(float(self.ExerciseDuration  * 60.0), self.StopExercise)
        self.StopTimer.start()

    # ---------- GenExercise::ReadyToExercise-----------------------------------
    def ReadyToExercise(self):

        status = self.SendCommand("generator: getbase")
        if not status.lower() in ["ready"]:
            self.LogError("Generator not in Ready state, exercise cycle not started")
            return False
        return True
    # ---------- GenExercise::StartExercise-------------------------------------
    def StartExercise(self):

        if self.ExerciseActive:
            # already active
            return

        # Start generator
        if self.ExerciseType.lower() == "normal" and self.ReadyToExercise():
            self.SendCommand("generator: setremote=start")
            self.DebugOutput("Starting normal exercise cycle.")
            self.StopTimer = threading.Timer(float(self.ExerciseDuration  * 60.0), self.StopExercise)
            self.StopTimer.start()
        elif self.ExerciseType.lower() == "quiet" and self.ReadyToExercise():
            self.SendCommand("generator: setremote=startexercise")
            self.DebugOutput("Starting quiet exercise cycle.")
            self.StopTimer = threading.Timer(float(self.ExerciseDuration  * 60.0), self.StopExercise)
            self.StopTimer.start()
        elif self.ExerciseType.lower() == "transfer" and self.ReadyToExercise():
            if self.ExerciseWarmup == 0:
                self.SendCommand("generator: setremote=starttransfer")
                self.DebugOutput("Starting transfer exercise cycle.")
                self.StopTimer = threading.Timer(float(self.ExerciseDuration  * 60.0), self.StopExercise)
                self.StopTimer.start()
            else:
                self.SendCommand("generator: setremote=start")
                self.DebugOutput("Starting warmup for transfer exercise cycle.")
                # start timer for post warmup transition to starttransfer command
                self.WarmupTimer = threading.Timer(float(self.ExerciseWarmup  * 60.0), self.PostWarmup)
                self.WarmupTimer.start()
        else:
            self.LogError("Invalid mode in StartExercise: " + str(self.ExerciseType))
            return
        self.WriteLastExerciseTime()
        self.ExerciseActive = True

    # ---------- GenExercise::StopExercise--------------------------------------
    def StopExercise(self):

        if self.ExerciseActive:
            self.SendCommand("generator: setremote=stop")
            self.DebugOutput("Stopping exercise cycle.")
            self.ExerciseActive = False
        else:
            self.DebugOutput("Calling Stop Exercise (not needed)")

    # ---------- GenExercise::DebugOutput-----------------------------
    def DebugOutput(self, Message):

        if self.Debug:
            self.LogError(Message)

    # ---------- GenExercise::WriteLastExerciseTime-----------------------------
    def WriteLastExerciseTime(self):

        try:
            NowString = datetime.datetime.now().strftime("%A %B %d, %Y %H:%M:%S")
            if self.ExerciseFrequency.lower() == "biweekly":
                self.config.WriteValue("last_exercise", NowString)
                self.config.LastExerciseTime = NowString
            self.DebugOutput("Last Exercise Cycle: " + NowString)
        except Exception as e1:
            self.LogErrorLine("Error in WriteLastExerciseTime: " + str(e1))

    # ---------- GenExercise::TimeForExercise-----------------------------------
    def TimeForExercise(self):
        try:
            if self.UseGeneratorTime:
                TimeNow = self.GetGeneratorTime()
            else:
                TimeNow = datetime.datetime.now()
            if TimeNow.hour != self.ExerciseHour or TimeNow.minute != self.ExerciseMinute:
                return False

            weekDays = ("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")

            WeekDayString = weekDays[TimeNow.weekday()]

            if not self.ExerciseFrequency.lower() in ["weekly", "biweekly", "monthly"]:
                self.LogError("Invalid Exercise Frequency in TimeForExercise: " + str(self.ExerciseFrequency))
                return False
            if self.ExerciseFrequency.lower() == "weekly" and self.ExerciseDayOfWeek.lower() == WeekDayString.lower():
                return True
            elif self.ExerciseFrequency.lower() == "biweekly"  and self.ExerciseDayOfWeek.lower() == WeekDayString.lower():
                if self.LastExerciseTime == None:
                    return True
                LastExerciseTime = datetime.datetime.strptime(self.LastExerciseTime, "%A %B %d, %Y %H:%M:%S")
                if (TimeNow -  LastExerciseTime).days >= 14:
                    return True
                return False
            elif self.ExerciseFrequency.lower() == "monthly" and TimeNow.day == self.ExerciseDayOfMonth:
                return True
            else:
                return False
        except Exception as e1:
            self.LogErrorLine("Error in TimeForExercise: " + str(e1))
        return False
    # ---------- GenExercise::GetGeneratorTime----------------------------------
    def GetGeneratorTime(self):
        try:
            GenTimeStr = ""
            data = self.SendCommand("generator: status_json")
            Status = {}
            Status = json.loads(data)
            TimeDict = self.FindDictValueInListByKey("Time", Status["Status"])
            if TimeDict != None:
                TimeDictStr = self.FindDictValueInListByKey("Generator Time", TimeDict)
                if TimeDictStr != None or not len(TimeDictStr):
                    GenTimeStr = TimeDictStr
                    # Format is "Wednesday March 6, 2019 13:10" or " "Friday May 3, 2019 11:11"
                    GenTime = datetime.datetime.strptime(GenTimeStr, "%A %B %d, %Y %H:%M")
                else:
                    self.LogError("Error getting generator time! Genmon may be starting up.")
                    GenTime = datetime.datetime.now()
            else:
                self.LogError("Error getting generator time (2)!")
                GenTime = datetime.datetime.now()
            return GenTime
        except Exception as e1:
            self.LogErrorLine("Error in GetGeneratorTime: " + str(e1) + ": " + GenTimeStr)
            return datetime.datetime.now()
    # ---------- GenExercise::ExerciseThread------------------------------------
    def ExerciseThread(self):

        time.sleep(1)
        while True:
            try:
                if not self.ExerciseActive:
                    if self.TimeForExercise():
                        self.StartExercise()
                if self.WaitForExit("ExerciseThread", float(self.PollTime)):
                    return
            except Exception as e1:
                self.LogErrorLine("Error in ExerciseThread: " + str(e1))
                if self.WaitForExit("ExerciseThread", float(self.PollTime)):
                    return

    # ----------GenExercise::Close----------------------------------------------
    def Close(self):
        self.KillThread("ExerciseThread")

        if self.ExerciseActive:
            try:
                self.WarmupTimer.cancel()
            except:
                pass
            try:
                self.StopTimer.cancel()
            except:
                pass
            self.StopExercise()
        self.Generator.Close()
#-------------------------------------------------------------------------------
if __name__ == "__main__":

    console = SetupLogger("genexerciselog_console", log_file = "", stream = True)
    HelpStr = '\nsudo python genexercise.py -a <IP Address or localhost> -c <path to genmon config file>\n'
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
    log = SetupLogger("client", loglocation + "genexercise.log")

    GenExerciseInstance = GenExercise(log = log, loglocation = loglocation, ConfigFilePath = ConfigFilePath, host = address, port = port)

    while True:
        time.sleep(0.5)

    sys.exit(1)
