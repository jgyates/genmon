#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: genexercise.py
# PURPOSE: genexercise.py add enhanced exercise functionality for Evolution and Nexus cotrollers
#
#  AUTHOR: jgyates
#    DATE: 02-23-2019
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

# ------------ GenExercise class ------------------------------------------------
class GenExercise(MySupport):

    # ------------ GenExercise::init---------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):

        super(GenExercise, self).__init__()

        self.AccessLock = threading.Lock()

        self.log = log
        self.console = console

        self.MonitorAddress = host
        self.PollTime = 2
        self.ExerciseActive = False
        self.debug = False
        self.ControllerExercise = False

        try:
            self.config = MyConfig(
                filename=os.path.join(ConfigFilePath, "genexercise.conf"),
                section="genexercise",
                log=self.log,
            )

            self.ExerciseType = self.config.ReadValue("exercise_type", default="Normal")
            self.ExerciseHour = self.config.ReadValue(
                "exercise_hour", return_type=int, default=12
            )
            self.ExerciseMinute = self.config.ReadValue(
                "exercise_minute", return_type=int, default=0
            )
            self.ExerciseDayOfMonth = self.config.ReadValue(
                "exercise_day_of_month", return_type=int, default=1
            )
            self.ExerciseDayOfWeek = self.config.ReadValue(
                "exercise_day_of_week", default="Monday"
            )
            self.ExerciseDuration = self.config.ReadValue(
                "exercise_duration", return_type=float, default=12
            )
            self.ExerciseWarmup = self.config.ReadValue(
                "exercise_warmup", return_type=float, default=0
            )
            self.ExerciseFrequency = self.config.ReadValue(
                "exercise_frequency", default="Monthly"
            )
            self.MonitorAddress = self.config.ReadValue(
                "monitor_address", default=ProgramDefaults.LocalHost
            )
            self.ExerciseNthDayOfMonth = self.config.ReadValue(
                "exercise_nth_day_of_month", return_type=int, default=0
            )

            self.LastExerciseTime = self.config.ReadValue("last_exercise", default=None)
            self.UseGeneratorTime = self.config.ReadValue("use_gen_time", return_type=bool, default=False)

            self.debug = self.config.ReadValue("debug", return_type=bool, default=False)

            # Validate settings
            if not self.ExerciseType.lower() in ["normal", "quiet", "transfer"]:
                self.ExerciseType = "normal"
            if self.ExerciseHour > 23 or self.ExerciseHour < 0:
                self.ExerciseHour = 12
            if self.ExerciseMinute > 59 or self.ExerciseMinute < 0:
                self.ExerciseMinute = 0
            if not self.ExerciseDayOfWeek.lower() in [
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            ]:
                self.ExerciseDayOfWeek = "Monday"
            if self.ExerciseDayOfMonth > 28 or self.ExerciseDayOfMonth < 1:
                self.ExerciseDayOfMonth = 1
            if self.ExerciseDuration > 60:
                self.ExerciseDuration = 60
            if self.ExerciseDuration < 5:
                self.ExerciseDuration = 5
            if self.ExerciseWarmup > 30:
                self.ExerciseWarmup = 30
            if self.ExerciseWarmup < 0:
                self.ExerciseWarmup = 0
            if not self.ExerciseFrequency.lower() in ["daily","weekly", "biweekly", "monthly", "post-controller"]:
                self.ExerciseFrequency = "Monthly"

            if self.MonitorAddress != None:
                self.MonitorAddress = self.MonitorAddress.strip()

            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost

            if self.ExerciseNthDayOfMonth > 5 or self.ExerciseNthDayOfMonth < 1:
                self.ExerciseNthDayOfMonth = 0
            if self.ExerciseFrequency.lower() == "monthly":
                if self.ExerciseNthDayOfMonth == 0:
                    self.LogDebug("Monthly Day of Month option used")
                else:
                    self.LogDebug("Exercise monthly on the %d x %s" %(self.ExerciseNthDayOfMonth, self.ExerciseDayOfWeek))
        except Exception as e1:
            self.LogErrorLine(
                "Error reading "
                + os.path.join(ConfigFilePath, "genexercise.conf")
                + ": "
                + str(e1)
            )
            self.console.error(
                "Error reading "
                + os.path.join(ConfigFilePath, "genexercise.conf")
                + ": "
                + str(e1)
            )
            sys.exit(1)

        try:

            self.Generator = ClientInterface(
                host=self.MonitorAddress, port=port, log=self.log
            )

            if not self.CheckGeneratorRequirement():
                self.LogError("Requirements not met. Exiting.")
                sys.exit(1)

            status = self.SendCommand("generator: getbase")
            if status.lower() in ["exercising"]:
                self.SendCommand("generator: setremote=stop")
            # start thread monitor time for exercise
            if self.ExerciseFrequency.lower() in ["daily","weekly","biweekly","monthly"]:
                self.Threads["ExerciseThread"] = MyThread(
                    self.ExerciseThread, Name="ExerciseThread", start=False)
                self.Threads["ExerciseThread"].Start()
            elif self.ExerciseFrequency.lower() in ["post-controller"]:
                self.Threads["PostExerciseThread"] = MyThread(
                    self.PostExerciseThread, Name="PostExerciseThread", start=False)
                self.Threads["PostExerciseThread"].Start()
            else:
                self.LogError("Exiting: Invalid exercise frequency: " + str(self.ExerciseFrequency))
                sys.exit(1)

            try:
                if self.ExerciseFrequency.lower() == "monthly":
                    if self.ExerciseNthDayOfMonth == 0:
                        DayStr = "Day " + str(self.ExerciseDayOfMonth)
                    else:
                        DayStr = str(self.ExerciseDayOfWeek) + " X " + str(self.ExerciseNthDayOfMonth)
                else:
                    DayStr = str(self.ExerciseDayOfWeek)
                if self.ExerciseFrequency.lower() in ["weekly","biweekly","monthly"]:
                    self.LogError(
                        "Exercise: "
                        + self.ExerciseType
                        + ", "
                        + self.ExerciseFrequency
                        + " at "
                        + str(self.ExerciseHour)
                        + ":"
                        + str(self.ExerciseMinute)
                        + " on "
                        + DayStr
                        + " for "
                        + str(self.ExerciseDuration)
                        + " min. Warmup: "
                        + str(self.ExerciseWarmup)
                    )
                elif self.ExerciseFrequency.lower() in ["daily"]:
                    self.LogError(
                        "Exercise: "
                        + self.ExerciseType
                        + ", "
                        + self.ExerciseFrequency
                        + " at "
                        + str(self.ExerciseHour)
                        + ":"
                        + str(self.ExerciseMinute)
                        + " for "
                        + str(self.ExerciseDuration)
                        + " min. Warmup: "
                        + str(self.ExerciseWarmup)
                    )
                elif self.ExerciseFrequency.lower() in ["post-controller"]:
                    self.LogError("Exercise: post controller exercise, " + self.ExerciseType + ", " + "for " + str(self.ExerciseDuration))
                self.LogDebug("Debug Enabled")
            except Exception as e1:
                self.LogErrorLine(str(e1))

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

        except Exception as e1:
            self.LogErrorLine("Error in GenExercise init: " + str(e1))
            self.console.error("Error in GenExercise init: " + str(e1))
            sys.exit(1)

    # ----------  GenExercise::SendCommand --------------------------------------
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

    # ----------  GenExercise::CheckGeneratorRequirement ------------------------
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

    # ---------- GenExercise::PostWarmup----------------------------------------
    def PostWarmup(self):

        # check to see if the generator is running
        status = self.SendCommand("generator: getbase")
        if not status.lower() in ["running", "exercising"]:
            self.LogError(
                "WARNING: generator not running post warmup. Transfer switch not activated."
            )
            self.SendCommand("generator: setremote=stop")
            return

        self.SendCommand("generator: setremote=starttransfer")
        self.LogDebug("Starting transfer exercise cycle (post warmup).")
        # set timer to stop
        self.StopTimer = threading.Timer(
            float(self.ExerciseDuration * 60.0), self.StopExercise
        )
        self.StopTimer.start()

    # ---------- GenExercise::ReadyToExercise-----------------------------------
    def ReadyToExercise(self):

        status = self.SendCommand("generator: getbase")
        if not status.lower() in ["ready", "servicedue"]:
            self.LogError("Generator not in Ready state, exercise cycle not started: " + str(status))
            return False
        return True

    # ---------- GenExercise::StartExercise-------------------------------------
    def StartExercise(self):

        if self.ExerciseActive:
            # already active
            return

        # Start generator
        if not self.ReadyToExercise():
            return
        
        if self.ExerciseType.lower() == "normal" and self.ReadyToExercise():
            self.SendCommand("generator: setremote=start")
            self.LogDebug("Starting normal exercise cycle.")
            self.StopTimer = threading.Timer(
                float(self.ExerciseDuration * 60.0), self.StopExercise
            )
            self.StopTimer.start()
        elif self.ExerciseType.lower() == "quiet" and self.ReadyToExercise():
            self.SendCommand("generator: setremote=startexercise")
            self.LogDebug("Starting quiet exercise cycle.")
            self.StopTimer = threading.Timer(
                float(self.ExerciseDuration * 60.0), self.StopExercise
            )
            self.StopTimer.start()
        elif self.ExerciseType.lower() == "transfer" and self.ReadyToExercise():
            if self.ExerciseWarmup == 0:
                self.SendCommand("generator: setremote=starttransfer")
                self.LogDebug("Starting transfer exercise cycle.")
                self.StopTimer = threading.Timer(
                    float(self.ExerciseDuration * 60.0), self.StopExercise
                )
                self.StopTimer.start()
            else:
                self.SendCommand("generator: setremote=start")
                self.LogDebug("Starting warmup for transfer exercise cycle.")
                # start timer for post warmup transition to starttransfer command
                self.WarmupTimer = threading.Timer(
                    float(self.ExerciseWarmup * 60.0), self.PostWarmup
                )
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
            self.LogDebug("Stopping exercise cycle.")
            self.ExerciseActive = False
        else:
            self.LogDebug("Calling Stop Exercise (not needed)")

    # ---------- GenExercise::WriteLastExerciseTime-----------------------------
    def WriteLastExerciseTime(self):

        try:
            NowString = datetime.datetime.now().strftime("%A %B %d, %Y %H:%M:%S")
            if self.ExerciseFrequency.lower() == "biweekly":
                self.config.WriteValue("last_exercise", NowString)
                self.config.LastExerciseTime = NowString
            self.LogDebug("Last Exercise Cycle: " + NowString)
        except Exception as e1:
            self.LogErrorLine("Error in WriteLastExerciseTime: " + str(e1))

    # ---------- GenExercise::TimeForExercise-----------------------------------
    def TimeForExercise(self):
        try:
            if self.UseGeneratorTime:
                TimeNow = self.GetGeneratorTime()
            else:
                TimeNow = datetime.datetime.now()
            if (
                TimeNow.hour != self.ExerciseHour
                or TimeNow.minute != self.ExerciseMinute
            ):
                return False
            ## if we get past this line then the time is correct
            weekDays = (
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            )

            WeekDayString = weekDays[TimeNow.weekday()]

            if not self.ExerciseFrequency.lower() in ["daily","weekly", "biweekly", "monthly", "post-controller"]:
                self.LogError(
                    "Invalid Exercise Frequency in TimeForExercise: "
                    + str(self.ExerciseFrequency)
                )
                return False
            if (self.ExerciseFrequency.lower() == "daily"):
                return True 
            if (
                self.ExerciseFrequency.lower() == "weekly"
                and self.ExerciseDayOfWeek.lower() == WeekDayString.lower()
            ):
                return True
            elif (
                self.ExerciseFrequency.lower() == "biweekly"
                and self.ExerciseDayOfWeek.lower() == WeekDayString.lower()
            ):
                if self.LastExerciseTime == None:
                    return True
                LastExerciseTime = datetime.datetime.strptime(
                    self.LastExerciseTime, "%A %B %d, %Y %H:%M:%S"
                )
                if (TimeNow - LastExerciseTime).days >= 14:
                    return True
                return False
            elif (
                self.ExerciseFrequency.lower() == "monthly"
                and TimeNow.day == self.ExerciseDayOfMonth
                and self.ExerciseNthDayOfMonth == 0
            ):
                return True
            elif (self.ExerciseFrequency.lower() == "monthly" 
                  and self.ExerciseNthDayOfMonth <= 5 and self.ExerciseNthDayOfMonth >= 1
                  and self.IsNthWeekDay(TimeNow, self.ExerciseNthDayOfMonth, weekDays.index(self.ExerciseDayOfWeek.capitalize()))
                  ):
                return True
            else:
                return False
        except Exception as e1:
            self.LogErrorLine("Error in TimeForExercise: " + str(e1))
        return False
    # ---------- GenExercise::IsNthWeekDay--------------------------------------
    def IsNthWeekDay(self, current_time, n, weekday):
        try:
            import calendar
            # Note that weekday = 0 for monday, 6 for sunday
            daysInMonth = calendar.monthrange(current_time.year, current_time.month)[1]

            count = 0
            for day in range(daysInMonth):
                today = datetime.date(current_time.year, current_time.month, day+1)
                today_weekday = today.weekday()
                if today_weekday == weekday:
                    count += 1
                    if n == count:
                        if current_time.day == (day+1):
                            return True 
        except Exception as e1:
            self.LogErrorLine("Error in IsNthWeekDay: " + str(e1))

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
                if TimeDictStr != None and len(TimeDictStr):
                    GenTimeStr = TimeDictStr
                    # Format is "Wednesday March 6, 2019 13:10" or " "Friday May 3, 2019 11:11"
                    GenTime = datetime.datetime.strptime(
                        GenTimeStr, "%A %B %d, %Y %H:%M"
                    )
                else:
                    self.LogError(
                        "Error getting generator time! Genmon may be starting up."
                    )
                    GenTime = datetime.datetime.now()
            else:
                self.LogError("Error getting generator time (2)!")
                GenTime = datetime.datetime.now()
            return GenTime
        except Exception as e1:
            self.LogErrorLine(
                "Error in GetGeneratorTime: " + str(e1) + ": " + GenTimeStr
            )
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
    # ---------- GenExercise::ExerciseThread------------------------------------
    #  Start exercise cycle after an exercise has completed.
    def PostExerciseThread(self):

        time.sleep(1)
        
        if not self.ExerciseFrequency.lower() in ["post-controller"]:
            self.LogDebug("Error: PostExerciseThread entered without proper initilization. Exiting thread.")
            return
        while True:
            try:
                # get base status, is it exercise, ignore if we started the cycle
                if not self.ExerciseActive:
                    status = self.SendCommand("generator: getbase")
                    if status.lower() in ["exercising"]:
                        # yes, set flag, wait for stop
                        self.LogDebug("Controller Exercise detected, waiting for stop.")
                        self.ControllerExercise = True
                    elif self.ReadyToExercise() and self.ControllerExercise == True:
                        # start our exercise cycle
                        self.ControllerExercise = False
                        self.LogDebug("Controller Exercise stopped, start our exercise cycle.")
                        self.StartExercise()
                    else:
                        self.LogDebug("Status: " + str(status))
                else:
                    if self.ControllerExercise:
                        self.ControllerExercise = False
                        self.LogDebug("Reset controller exercise ")
                if self.WaitForExit("PostExerciseThread", float(self.PollTime)):
                    return
            except Exception as e1:
                self.LogErrorLine("Error in PostExerciseThread: " + str(e1))
                if self.WaitForExit("PostExerciseThread", float(self.PollTime)):
                    return

    # ----------GenExercise::SignalClose----------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(1)

    # ----------GenExercise::Close----------------------------------------------
    def Close(self):
        if not self.ExerciseFrequency.lower() in ["post-controller"]:
            self.KillThread("ExerciseThread")
        else:
            self.KillThread("PostExerciseThread")

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


# -------------------------------------------------------------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("genexercise")

    GenExerciseInstance = GenExercise(
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
