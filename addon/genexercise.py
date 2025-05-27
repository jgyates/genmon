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

except ImportError as e_imp_genmon:
    # Logger not available yet, print to stderr
    sys.stderr.write(
        "\n\nFATAL ERROR: This program requires the genmonlib modules.\n"
        "These modules should be located in the 'genmonlib' directory, typically one level above the 'addon' directory.\n"
        "Please ensure the genmonlib directory and its contents are correctly placed and accessible.\n"
        "Consult the project documentation at https://github.com/jgyates/genmon for installation details.\n"
    )
    sys.stderr.write(f"Specific import error: {e_imp_genmon}\n")
    sys.exit(2) # Exit if core components are missing.

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
        config_file_full_path = os.path.join(ConfigFilePath, "genexercise.conf")

        try:
            self.log.info(f"Reading configuration from: {config_file_full_path}")
            self.config = MyConfig(
                filename=config_file_full_path,
                section="genexercise",
                log=self.log,
            )

            self.ExerciseType = self.config.ReadValue("exercise_type", default="Normal")
            self.ExerciseHour = self.config.ReadValue("exercise_hour", return_type=int, default=12)
            self.ExerciseMinute = self.config.ReadValue("exercise_minute", return_type=int, default=0)
            self.ExerciseDayOfMonth = self.config.ReadValue("exercise_day_of_month", return_type=int, default=1)
            self.ExerciseDayOfWeek = self.config.ReadValue("exercise_day_of_week", default="Monday")
            self.ExerciseDuration = self.config.ReadValue("exercise_duration", return_type=float, default=12.0) # Ensure float
            self.ExerciseWarmup = self.config.ReadValue("exercise_warmup", return_type=float, default=0.0) # Ensure float
            self.ExerciseFrequency = self.config.ReadValue("exercise_frequency", default="Monthly")
            self.MonitorAddress = self.config.ReadValue("monitor_address", default=ProgramDefaults.LocalHost)
            self.ExerciseNthDayOfMonth = self.config.ReadValue("exercise_nth_day_of_month", return_type=int, default=0)
            self.LastExerciseTime = self.config.ReadValue("last_exercise", default=None)
            self.UseGeneratorTime = self.config.ReadValue("use_gen_time", return_type=bool, default=False)
            self.debug = self.config.ReadValue("debug", return_type=bool, default=False)

            # Validate settings
            valid_exercise_types = ["normal", "quiet", "transfer"]
            if self.ExerciseType.lower() not in valid_exercise_types:
                self.log.warning(f"Invalid ExerciseType '{self.ExerciseType}', defaulting to 'Normal'. Valid options: {valid_exercise_types}")
                self.ExerciseType = "Normal"
            
            if not (0 <= self.ExerciseHour <= 23):
                self.log.warning(f"Invalid ExerciseHour '{self.ExerciseHour}', defaulting to 12.")
                self.ExerciseHour = 12
            if not (0 <= self.ExerciseMinute <= 59):
                self.log.warning(f"Invalid ExerciseMinute '{self.ExerciseMinute}', defaulting to 0.")
                self.ExerciseMinute = 0

            valid_days_of_week = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            if self.ExerciseDayOfWeek.lower() not in valid_days_of_week:
                self.log.warning(f"Invalid ExerciseDayOfWeek '{self.ExerciseDayOfWeek}', defaulting to 'Monday'. Valid options: {valid_days_of_week}")
                self.ExerciseDayOfWeek = "Monday"

            if not (1 <= self.ExerciseDayOfMonth <= 28): # Safest upper limit for all months
                self.log.warning(f"Invalid ExerciseDayOfMonth '{self.ExerciseDayOfMonth}', defaulting to 1.")
                self.ExerciseDayOfMonth = 1
            
            if not (5 <= self.ExerciseDuration <= 60): # Assuming these are practical limits
                self.log.warning(f"Invalid ExerciseDuration '{self.ExerciseDuration}', defaulting to 12 minutes. Min=5, Max=60.")
                self.ExerciseDuration = 12.0
            
            if not (0 <= self.ExerciseWarmup <= 30): # Assuming practical limits
                self.log.warning(f"Invalid ExerciseWarmup '{self.ExerciseWarmup}', defaulting to 0 minutes. Min=0, Max=30.")
                self.ExerciseWarmup = 0.0

            valid_frequencies = ["daily", "weekly", "biweekly", "monthly", "post-controller"]
            if self.ExerciseFrequency.lower() not in valid_frequencies:
                self.log.warning(f"Invalid ExerciseFrequency '{self.ExerciseFrequency}', defaulting to 'Monthly'. Valid options: {valid_frequencies}")
                self.ExerciseFrequency = "Monthly"

            if self.MonitorAddress: self.MonitorAddress = self.MonitorAddress.strip()
            if not self.MonitorAddress: self.MonitorAddress = ProgramDefaults.LocalHost

            if not (0 <= self.ExerciseNthDayOfMonth <= 5) : # 0 means not used
                self.log.warning(f"Invalid ExerciseNthDayOfMonth '{self.ExerciseNthDayOfMonth}', defaulting to 0 (disabled). Valid: 0-5.")
                self.ExerciseNthDayOfMonth = 0

            if self.ExerciseFrequency.lower() == "monthly":
                if self.ExerciseNthDayOfMonth == 0:
                    self.LogDebug(f"Monthly exercise scheduled for day {self.ExerciseDayOfMonth} of the month.")
                else:
                    self.LogDebug(f"Monthly exercise scheduled for the {self.ExerciseNthDayOfMonth} x {self.ExerciseDayOfWeek}.")

        except FileNotFoundError:
            err_msg = f"GenExercise.__init__: Configuration file '{config_file_full_path}' not found."
            self.LogErrorLine(err_msg) # LogErrorLine should be from MySupport
            if self.console: self.console.error(err_msg)
            sys.exit(1)
        except (KeyError, ValueError) as e_conf_parse:
            err_msg = f"GenExercise.__init__: Error parsing configuration from '{config_file_full_path}': {e_conf_parse}"
            self.LogErrorLine(err_msg)
            if self.console: self.console.error(err_msg)
            sys.exit(1)
        except Exception as e_conf_generic: # Catch-all for other config related errors
            err_msg = f"GenExercise.__init__: Unexpected error reading or validating configuration: {e_conf_generic}"
            self.LogErrorLine(err_msg)
            if self.console: self.console.error(err_msg)
            sys.exit(1)

        try:
            self.log.info(f"Connecting to genmon server at {self.MonitorAddress}:{port}")
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
            self.LogErrorLine(f"GenExercise.__init__: Error during ClientInterface setup or initial checks: {e_client_setup}")
            if self.console: self.console.error(f"Error in GenExercise init: {e_client_setup}")
            sys.exit(1)
        except Exception as e_init_main: # Fallback for any other unexpected error in init
            self.LogErrorLine(f"GenExercise.__init__: Unexpected critical error: {e_init_main}")
            if self.console: self.console.error(f"Unexpected critical error in GenExercise init: {e_init_main}")
            sys.exit(1)

    # ----------  GenExercise::SendCommand --------------------------------------
    def SendCommand(self, Command):

        if len(Command) == 0:
            return "Invalid Command"

        try:
            with self.AccessLock:
                data = self.Generator.ProcessMonitorCommand(Command)
            return data
        except (socket.error, ConnectionRefusedError, TimeoutError, OSError) as e_sock: # More specific network errors
            self.LogErrorLine(f"SendCommand: Socket/OS error for command '{Command}': {e_sock}")
            return "" # Return empty string or error indicator
        except Exception as e_send_cmd: # Other errors from ClientInterface or unexpected
            self.LogErrorLine(f"SendCommand: Unexpected error for command '{Command}': {e_send_cmd}")
            return ""

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
        except json.JSONDecodeError as e_json:
            self.LogErrorLine(f"CheckGeneratorRequirement: Error decoding JSON from start_info_json: {e_json}. Data: '{data[:100]}...'")
            return False
        except KeyError as ke:
            self.LogErrorLine(f"CheckGeneratorRequirement: 'Controller' key missing in start_info_json: {ke}")
            return False
        except Exception as e_check_req:
            self.LogErrorLine(f"CheckGeneratorRequirement: Unexpected error: {e_check_req}")
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
            self.LogDebug(f"Last Exercise Cycle recorded: {NowString}")
        except IOError as ioe: # If MyConfig.WriteValue can raise IOError
            self.LogErrorLine(f"WriteLastExerciseTime: IOError writing last exercise time to config: {ioe}")
        except Exception as e_write_time:
            self.LogErrorLine(f"WriteLastExerciseTime: Unexpected error: {e_write_time}")

    # ---------- GenExercise::TimeForExercise-----------------------------------
    def TimeForExercise(self):
        try:
            if self.UseGeneratorTime:
                TimeNow = self.GetGeneratorTime()
                if TimeNow is None: # GetGeneratorTime might return None on error
                    self.log.error("TimeForExercise: Could not get generator time, defaulting to system time for this check.")
                    TimeNow = datetime.datetime.now()
            else:
                TimeNow = datetime.datetime.now()
            
            if TimeNow.hour != self.ExerciseHour or TimeNow.minute != self.ExerciseMinute:
                return False

            weekDays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
            WeekDayString = weekDays[TimeNow.weekday()]
            current_frequency = self.ExerciseFrequency.lower()

            if current_frequency == "daily":
                return True
            if current_frequency == "weekly" and self.ExerciseDayOfWeek.lower() == WeekDayString.lower():
                return True
            if current_frequency == "biweekly" and self.ExerciseDayOfWeek.lower() == WeekDayString.lower():
                if self.LastExerciseTime is None:
                    return True # First time, allow exercise
                try:
                    LastExerciseTimeDT = datetime.datetime.strptime(self.LastExerciseTime, "%A %B %d, %Y %H:%M:%S")
                    if (TimeNow - LastExerciseTimeDT).days >= 14:
                        return True
                except ValueError as ve:
                    self.LogErrorLine(f"TimeForExercise: Error parsing LastExerciseTime '{self.LastExerciseTime}': {ve}. Allowing exercise as a precaution.")
                    return True # Allow exercise if last time is corrupt
                return False
            if current_frequency == "monthly":
                if self.ExerciseNthDayOfMonth == 0 and TimeNow.day == self.ExerciseDayOfMonth: # Specific day of month
                    return True
                if 1 <= self.ExerciseNthDayOfMonth <= 5 and self.IsNthWeekDay(TimeNow, self.ExerciseNthDayOfMonth, weekDays.index(self.ExerciseDayOfWeek.capitalize())):
                    return True
            # "post-controller" is handled by a different thread/logic, not this time check.
            return False
        except ValueError as ve_time: # For strptime issues if date format is unexpectedly different
             self.LogErrorLine(f"TimeForExercise: ValueError processing time/date: {ve_time}")
        except Exception as e_time_exercise:
            self.LogErrorLine(f"TimeForExercise: Unexpected error: {e_time_exercise}")
        return False # Default to False on any error

    # ---------- GenExercise::IsNthWeekDay--------------------------------------
    def IsNthWeekDay(self, current_time, n, target_weekday_index):
        try:
            import calendar
            # target_weekday_index: 0 for Monday, 6 for Sunday (matches datetime.weekday())
            days_in_month = calendar.monthrange(current_time.year, current_time.month)[1]
            
            occurrence_count = 0
            for day_num in range(1, days_in_month + 1):
                date_in_month = datetime.date(current_time.year, current_time.month, day_num)
                if date_in_month.weekday() == target_weekday_index:
                    occurrence_count += 1
                    if occurrence_count == n and current_time.day == day_num:
                        return True
            return False
        except Exception as e_nth_day: # Catch any unexpected error
            self.LogErrorLine(f"IsNthWeekDay: Unexpected error: {e_nth_day}")
            return False

    # ---------- GenExercise::GetGeneratorTime----------------------------------
    def GetGeneratorTime(self):
        try:
            GenTimeStr = ""
            data = self.SendCommand("generator: status_json")
            Status = {} # Ensure Status is defined for the error case below
            data = self.SendCommand("generator: status_json")
            if not data:
                self.LogError("GetGeneratorTime: No data received from status_json command.")
                return None # Indicate failure to get time

            Status = json.loads(data)
            # Use .get() for safer dictionary access
            time_list_of_dicts = Status.get("Status", {}).get("Time")
            if time_list_of_dicts:
                # Assuming FindDictValueInListByKey is robust or handles its own errors
                gen_time_str = self.FindDictValueInListByKey("Generator Time", time_list_of_dicts)
                if gen_time_str and isinstance(gen_time_str, str) and gen_time_str.strip():
                    try:
                        return datetime.datetime.strptime(gen_time_str, "%A %B %d, %Y %H:%M")
                    except ValueError as ve:
                        self.LogErrorLine(f"GetGeneratorTime: Error parsing generator time string '{gen_time_str}': {ve}")
                        return None # Parsing failed
                else:
                    self.log.warning("GetGeneratorTime: 'Generator Time' not found or empty in status. Genmon might be starting.")
            else:
                self.log.warning("GetGeneratorTime: 'Time' section not found in status. Genmon might be starting.")
            return None # Return None if time cannot be determined
        except json.JSONDecodeError as e_json_time:
            self.LogErrorLine(f"GetGeneratorTime: Error decoding JSON from status_json: {e_json_time}. Data: '{data[:100]}...'")
            return None
        except KeyError as ke_time:
            self.LogErrorLine(f"GetGeneratorTime: KeyError accessing time data in status: {ke_time}")
            return None
        except Exception as e_get_time_generic:
            self.LogErrorLine(f"GetGeneratorTime: Unexpected error: {e_get_time_generic}")
            return None # Default to None on any error

    # ---------- GenExercise::ExerciseThread------------------------------------
    def ExerciseThread(self):
        self.log.info("ExerciseThread started.")
        time.sleep(1) # Initial delay
        while not self.Exiting: # Assuming self.Exiting is set by Close() or signal handler
            try:
                if not self.ExerciseActive:
                    if self.TimeForExercise(): # This method now handles its exceptions
                        self.log.info("ExerciseThread: Time for scheduled exercise. Starting exercise.")
                        self.StartExercise() # This method also handles its exceptions
                
                # Use the WaitForExit method from MyThread if available, otherwise simple sleep
                if hasattr(self, 'WaitForExit') and callable(self.WaitForExit):
                    if self.WaitForExit("ExerciseThread", float(self.PollTime)):
                        break # Exit signal received
                else: # Fallback sleep
                    for _ in range(int(self.PollTime / 0.1)): # Break sleep into smaller chunks
                        if self.Exiting: break
                        time.sleep(0.1)
                    if self.Exiting: break

            except Exception as e_thread_loop: # Catch any unexpected error in the loop
                self.LogErrorLine(f"ExerciseThread: Unexpected error in main loop: {e_thread_loop}")
                # Consider a longer sleep or backoff after an unexpected error
                time.sleep(float(self.PollTime) * 5) # Wait longer after an error
        self.log.info("ExerciseThread: Exiting.")

    # ---------- GenExercise::PostExerciseThread------------------------------------
    #  Start exercise cycle after an exercise has completed.
    def PostExerciseThread(self):
        self.log.info("PostExerciseThread started.")
        time.sleep(1)
        
        if self.ExerciseFrequency.lower() != "post-controller":
            self.log.error("PostExerciseThread: Invalid configuration - thread started without 'post-controller' frequency. Exiting thread.")
            return

        while not self.Exiting:
            try:
                if not self.ExerciseActive:
                    status = self.SendCommand("generator: getbase")
                    if status is None: # SendCommand might return None or empty on error
                        self.log.warning("PostExerciseThread: Failed to get generator status. Retrying.")
                        time.sleep(self.PollTime) # Wait before retrying
                        continue

                    if status.lower() == "exercising":
                        if not self.ControllerExercise: # Log only on first detection
                            self.log.info("PostExerciseThread: Controller-initiated exercise detected. Waiting for it to complete.")
                        self.ControllerExercise = True
                    elif self.ControllerExercise and self.ReadyToExercise(): # Was exercising, now ready
                        self.log.info("PostExerciseThread: Controller exercise completed. Starting post-controller enhanced exercise.")
                        self.ControllerExercise = False # Reset flag
                        self.StartExercise() 
                    # else: # Not exercising and not previously in controller exercise, or not ready
                        # if self.debug: self.LogDebug(f"PostExerciseThread: Current status '{status}', ControllerExercise flag: {self.ControllerExercise}")
                # else: # self.ExerciseActive is True (our exercise is running)
                #    if self.ControllerExercise: # If our exercise started while controller flag was set
                #        self.log.info("PostExerciseThread: Enhanced exercise started. Resetting ControllerExercise flag.")
                #        self.ControllerExercise = False
                
                if hasattr(self, 'WaitForExit') and callable(self.WaitForExit):
                    if self.WaitForExit("PostExerciseThread", float(self.PollTime)):
                        break
                else:
                    for _ in range(int(self.PollTime / 0.1)):
                        if self.Exiting: break
                        time.sleep(0.1)
                    if self.Exiting: break
                        
            except Exception as e_post_thread_loop:
                self.LogErrorLine(f"PostExerciseThread: Unexpected error in main loop: {e_post_thread_loop}")
                time.sleep(float(self.PollTime) * 5)
        self.log.info("PostExerciseThread: Exiting.")


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

    log = None # Initialize for use in signal_handler if setup fails
    console = None
    GenExerciseInstance = None # Initialize for finally block

    try:
        (
            console,
            ConfigFilePath,
            address,
            port,
            loglocation,
            log, # Properly configured logger
        ) = MySupport.SetupAddOnProgram("genexercise")

        # Now that log is configured, set signal handlers
        signal.signal(signal.SIGINT, signal_handler) # For Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler) # For service stop

        GenExerciseInstance = GenExercise(
            log=log,
            loglocation=loglocation,
            ConfigFilePath=ConfigFilePath,
            host=address,
            port=port,
            console=console,
        )
        # GenExercise __init__ now handles its critical errors and sys.exit if needed

        log.info("genexercise.py main loop started. Monitoring for exercise times or signals.")
        while not GenExerciseInstance.Exiting: # Rely on a flag in the instance
            time.sleep(0.5) # Keep main thread alive, actual work done in threads
        
        log.info("genexercise.py main loop exiting gracefully.")
        sys.exit(0) # Normal exit after loop termination

    except KeyboardInterrupt:
        if log: log.info("__main__: KeyboardInterrupt received. Initiating shutdown via signal_handler.")
        else: print("__main__: KeyboardInterrupt received. Shutting down.", file=sys.stderr)
        signal_handler(signal.SIGINT, None) # Manually invoke if loop was bypassed
    except SystemExit: # Allow sys.exit to pass through
        if log: log.info("__main__: SystemExit called.")
        else: print("__main__: SystemExit called.", file=sys.stderr)
        raise # Re-raise to ensure exit
    except Exception as e_main_fatal: # Catch-all for any unexpected error during main setup or minimal loop
        err_msg = f"__main__: An unhandled critical error occurred: {e_main_fatal}"
        if log: log.error(err_msg, exc_info=True)
        else: sys.stderr.write(err_msg + "\n")
        if console: console.error(err_msg)
        sys.exit(1)
    finally:
        if GenExerciseInstance is not None and hasattr(GenExerciseInstance, 'Close'):
            if log: log.info("__main__: Ensuring GenExerciseInstance is closed in finally block.")
            GenExerciseInstance.Close()
        if log: log.info("__main__: Application terminated.")
        else: print("__main__: Application terminated.", file=sys.stderr)
