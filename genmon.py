#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: genmon.py
# PURPOSE: Monitor for Generator
#
#  AUTHOR: Jason G Yates
#    DATE: 05-Oct-2016
#          23-Apr-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

from __future__ import (  # For python 3.x compatibility with print function
    print_function,
)

import collections
import datetime
import getopt
import json
import os
import signal
import socket
import sys
import threading
import time

try:
    from genmonlib.custom_controller import CustomController
    from genmonlib.generac_evolution import Evolution
    from genmonlib.generac_HPanel import HPanel
    from genmonlib.generac_powerzone import PowerZone
    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.mymail import MyMail
    from genmonlib.mypipe import MyPipe
    from genmonlib.myplatform import MyPlatform
    from genmonlib.mysupport import MySupport
    from genmonlib.mythread import MyThread
    from genmonlib.myweather import MyWeather
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

# ------------ Monitor class ----------------------------------------------------
class Monitor(MySupport):
    def __init__(self, ConfigFilePath=ProgramDefaults.ConfPath):
        super(Monitor, self).__init__() # Initialize the MySupport parent class

        # --- Basic Program Information ---
        self.ProgramName = "Generator Monitor" # Name of the program
        self.Version = "Unknown"               # Program version, updated from config or defaults
        self.log = None                        # Primary logger instance, initialized later

        # --- Program Lifecycle Flags ---
        # self.IsStopping: Set to True when the program is in the process of shutting down.
        #                 Used by threads to know when to terminate their loops.
        self.IsStopping = False
        # self.ProgramComplete: Set to True when the program has completed all shutdown procedures
        #                      and is ready to exit.
        self.ProgramComplete = False

        # --- Path Variables ---
        # self.ConfigFilePath: Absolute path to the directory containing configuration files (e.g., /etc/genmon/).
        #                     Defaults to ProgramDefaults.ConfPath if not provided or empty.
        if ConfigFilePath == None or ConfigFilePath == "":
            self.ConfigFilePath = ProgramDefaults.ConfPath
        else:
            self.ConfigFilePath = ConfigFilePath
        # self.FeedbackLogFile: Full path to the JSON file used for storing feedback messages
        #                      if they cannot be sent immediately (e.g., email is down).
        self.FeedbackLogFile = os.path.join(self.ConfigFilePath, "feedback.json")
        # self.LogLocation: Path to the directory where log files (genmon.log, etc.) will be stored.
        #                  Defaults to ProgramDefaults.LogPath.
        self.LogLocation = ProgramDefaults.LogPath

        self.LastLogFileSize = 0               # Used for monitoring log file growth/issues.
        self.NumberOfLogSizeErrors = 0         # Counter for log file size anomalies.

        # --- Server-related Attributes (for command/status interface) ---
        self.ConnectionList = []               # List of active client socket connections.
        self.SiteName = "Home"                 # User-defined site name, read from genmon.conf.
        self.ServerSocket = None               # The main server socket object.
        # self.ServerIPAddress: IP address for the server socket to bind to.
        #                      Empty string usually means bind to all available interfaces.
        self.ServerIPAddress = ""
        # self.ServerSocketPort: Port number for the server socket. Defaults to ProgramDefaults.ServerPort.
        self.ServerSocketPort = ProgramDefaults.ServerPort

        # --- Email-related Attributes ---
        # self.IncomingEmailFolder: Name of the IMAP folder to check for incoming email commands.
        self.IncomingEmailFolder = "Generator"
        # self.ProcessedEmailFolder: Name of the IMAP folder where processed emails are moved.
        self.ProcessedEmailFolder = "Generator/Processed"
        self.MailInit = False                  # Flag: True if MyMail has been successfully initialized.

        # --- Feedback and Message Pipe Attributes ---
        # self.FeedbackEnabled: Boolean flag indicating if automated feedback (to developer) is enabled.
        self.FeedbackEnabled = False
        # self.FeedbackMessages: Dictionary to store feedback messages read from FeedbackLogFile on startup.
        self.FeedbackMessages = {}
        # self.CommunicationsActive: Flag set by ComWatchDog, True if data is being actively received
        #                           from the generator controller.
        self.CommunicationsActive = False

        # --- Controller and Weather-related Attributes ---
        self.Controller = None                 # Instance of the active generator controller class (e.g., Evolution, HPanel).
        self.ControllerSelected = None         # String identifying the type of controller selected in genmon.conf.
        self.MyWeather = None                  # Instance of MyWeather class for fetching weather data.
        # Weather configuration options, read from genmon.conf:
        self.WeatherAPIKey = None
        self.WeatherLocation = None
        self.UseMetric = False                 # Use metric units for weather if True.
        self.WeatherMinimum = True             # Fetch minimal weather info if True.
        self.DisableWeather = False            # Disable weather fetching if True.

        # --- Software Update Attributes ---
        self.UpdateAvailable = False           # Flag: True if a software update for genmon is available.
        self.UpdateVersion = None              # String: Version number of the available update.

        # --- Time Synchronization Attributes ---
        # self.bSyncTime: Boolean, if True, periodically sync generator time to system time.
        self.bSyncTime = False
        # self.bSyncDST: Boolean, if True, sync generator time when Daylight Savings Time changes.
        self.bSyncDST = False
        # self.bDST: Boolean, current Daylight Savings Time status (True if DST is active).
        self.bDST = False

        # --- Simulation Mode Attributes ---
        self.Simulation = False                # Boolean, if True, run in simulation mode using data from SimulationFile.
        self.SimulationFile = None             # Path to the file containing simulation data.

        # --- Miscellaneous Configuration Flags ---
        self.NewInstall = False                # Flag: True if a new installation or version upgrade is detected.
        self.bDisablePlatformStats = False     # Boolean, if True, disable collection/display of platform (OS) stats.
        self.ReadOnlyEmailCommands = False     # Boolean, if True, disallow email commands that modify settings.
        self.SlowCPUOptimization = False       # Boolean, if True, enable optimizations for slower CPUs.

        # --- Initial Setup ---
        # Setup a console logger for early messages before file logging is fully configured.
        self.console = SetupLogger("genmon_console", log_file="", stream=True)

        # Check for root privileges, essential for some operations.
        if not MySupport.PermissionsOK():
            self.LogConsole(
                "You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'."
            )
            sys.exit(1) # Exit if not root.

        # Check for essential configuration files (genmon.conf, mymail.conf).
        if not os.path.isfile(os.path.join(self.ConfigFilePath, "genmon.conf")):
            self.LogConsole(
                "Missing config file : "
                + os.path.join(self.ConfigFilePath, "genmon.conf")
            )
            sys.exit(1)
        if not os.path.isfile(os.path.join(self.ConfigFilePath, "mymail.conf")):
            self.LogConsole(
                "Missing config file : "
                + os.path.join(self.ConfigFilePath, "mymail.conf")
            )
            sys.exit(1)

        # Initialize MyConfig to read settings from genmon.conf.
        self.config = MyConfig(
            filename=os.path.join(self.ConfigFilePath, "genmon.conf"),
            section="GenMon", # Default section for genmon-specific settings.
            log=self.console, # Use console logger for initial config reading.
        )
        # Read configuration settings from genmon.conf into instance attributes.
        if not self.GetConfig(): # GetConfig populates attributes like self.SiteName, self.LogLocation, etc.
            self.LogConsole("Failure in Monitor GetConfig. Check genmon.conf and logs. Exiting.")
            sys.exit(1) # Exit if config loading fails.

        # Now that LogLocation is known from GetConfig, setup the main file logger.
        self.log = SetupLogger("genmon", os.path.join(self.LogLocation, "genmon.log"))
        # Update MyConfig instance to use the main file logger for subsequent operations.
        self.config.log = self.log

        # Check if another instance of genmon.py is already running.
        # First check is based on the server port defined in ProgramDefaults.
        if self.IsLoaded():
            self.LogConsole("ERROR: genmon.py is already loaded (port check failed).")
            self.LogError("ERROR: genmon.py is already loaded (port check failed).")
            sys.exit(1)
        # Second check is based on the script filename, respecting multi_instance setting from config.
        if MySupport.IsRunning(
            os.path.basename(__file__), multi_instance=self.multi_instance
        ):
            self.LogConsole("ERROR: genmon.py is already loaded (process name check failed).")
            self.LogError("ERROR: genmon.py is already loaded (process name check failed).")
            sys.exit(1)

        # Handle new installation or version upgrade.
        if self.NewInstall: # self.NewInstall is set in GetConfig if versions differ.
            self.LogError(
                "New version detected or initial install: Config version was %s, Program version is %s"
                % (self.Version, ProgramDefaults.GENMON_VERSION)
            )
            self.Version = ProgramDefaults.GENMON_VERSION # Ensure self.Version reflects current program version.

        self.ProgramStartTime = datetime.datetime.now()  # Record program start time for uptime calculation.
        # Initialize last software update check time. For immediate check, set to a very old date.
        # Default is to wait one day before the first check.
        self.LastSoftwareUpdateCheck = datetime.datetime.now()

        # Setup signal handlers for graceful shutdown on SIGTERM or SIGINT.
        signal.signal(signal.SIGTERM, self.SignalClose)
        signal.signal(signal.SIGINT, self.SignalClose)

        # --- Load genmonext.py (External Extensions) ---
        # This allows users to extend genmon's functionality (e.g., GPIO actions)
        # by creating a genmonext.py file in the same directory as genmon.py.
        # This external module can intercept commands or add custom logic without
        # modifying the core genmon files, thus simplifying updates.
        self.genmonext = None # Initialize to None.
        genmonext_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "genmonext.py")
        if os.path.isfile(genmonext_path):
            try:
                import genmonext # Dynamically import the module.
                self.genmonext = genmonext.GenmonExt(log=self.log) # Instantiate its main class.
                self.log.info("Successfully loaded external extension module: genmonext.py")
            except Exception as e_ext:
                self.LogErrorLine(f"Error loading genmonext.py: {str(e_ext)}. Proceeding without external extensions.")
                self.genmonext = None # Ensure it's None if loading failed.


        # Start the InterfaceServerThread to listen for incoming socket connections
        # (used for client commands, status requests, and Nagios heartbeats).
        self.Threads["InterfaceServerThread"] = MyThread(
            self.InterfaceServerThread, Name="InterfaceServerThread"
        )

        # Initialize email functionality (MyMail).
        try:
            self.mail = MyMail(
                monitor=True, # Indicates this is the main monitoring instance.
                incoming_folder=self.IncomingEmailFolder,
                processed_folder=self.ProcessedEmailFolder,
                incoming_callback=self.ProcessCommand, # Method to call for processing email commands.
                loglocation=self.LogLocation,
                ConfigFilePath=ConfigFilePath,
            )
            self.Threads = self.MergeDicts(self.Threads, self.mail.Threads) # Add mail threads to main thread dict.
            self.MailInit = True # Mark mail as initialized.
        except Exception as e1:
            self.LogErrorLine("Error loading mail support (MyMail initialization failed): " + str(e1))
            sys.exit(1) # Exit if mail setup fails, as it's often critical.

        # --- Initialize Inter-Process Communication Pipes (MyPipe) ---
        # self.FeedbackPipe: Used by controller modules to send feedback information (e.g., error reports)
        #                   back to the main Monitor class for processing (e.g., emailing to developer).
        self.FeedbackPipe = MyPipe(
            "Feedback", # Pipe name.
            self.FeedbackReceiver, # Callback method in Monitor to handle received feedback.
            log=self.log,
            debug = self.debug,
            ConfigFilePath=self.ConfigFilePath,
        )
        self.Threads = self.MergeDicts(self.Threads, self.FeedbackPipe.Threads)
        # self.MessagePipe: Used by various parts of genmon (including controller) to send
        #                  general messages (e.g., alerts, status updates) to be emailed to the user.
        self.MessagePipe = MyPipe(
            "Message", # Pipe name.
            self.MessageReceiver, # Callback method in Monitor to handle messages for emailing.
            log=self.log,
            debug = self.debug,
            nullpipe=self.mail.DisableSNMP, # If SNMP is disabled in mail, this might make pipe a no-op.
            ConfigFilePath=self.ConfigFilePath,
        )
        self.Threads = self.MergeDicts(self.Threads, self.MessagePipe.Threads)

        # Initialize the generator controller communication.
        try:
            if self.Simulation:
                self.LogError("Simulation Mode is Active, using data from: " + str(self.SimulationFile))

            # Determine which controller class to instantiate based on ControllerSelected from config.
            if not self.ControllerSelected or not len(self.ControllerSelected):
                self.ControllerSelected = "generac_evo_nexus" # Default if not specified.
            self.LogError("Selected Controller Type: " + str(self.ControllerSelected))

            # Instantiate the appropriate controller class.
            if self.ControllerSelected.lower() == "h_100":
                self.Controller = HPanel(
                    self.log,
                    newinstall=self.NewInstall,
                    simulation=self.Simulation,
                    simulationfile=self.SimulationFile,
                    message=self.MessagePipe,    # Pipe for sending messages (alerts).
                    feedback=self.FeedbackPipe,  # Pipe for sending feedback.
                    config=self.config,          # MyConfig instance for controller-specific settings.
                )
            elif self.ControllerSelected.lower() == "powerzone":
                self.Controller = PowerZone(
                    self.log,
                    newinstall=self.NewInstall,
                    simulation=self.Simulation,
                    simulationfile=self.SimulationFile,
                    message=self.MessagePipe,
                    feedback=self.FeedbackPipe,
                    config=self.config,
                )
            elif self.ControllerSelected.lower() == "custom":
                self.Controller = CustomController( # For user-defined controller logic.
                    self.log,
                    newinstall=self.NewInstall,
                    simulation=self.Simulation,
                    simulationfile=self.SimulationFile,
                    message=self.MessagePipe,
                    feedback=self.FeedbackPipe,
                    config=self.config,
                )
            else: # Default to Generac Evolution controller.
                self.Controller = Evolution(
                    self.log,
                    self.NewInstall,
                    simulation=self.Simulation,
                    simulationfile=self.SimulationFile,
                    message=self.MessagePipe,
                    feedback=self.FeedbackPipe,
                    config=self.config,
                )
            # Add controller's threads (e.g., serial communication thread) to the main thread dictionary.
            self.Threads = self.MergeDicts(self.Threads, self.Controller.Threads)

        except Exception as e1:
            self.LogErrorLine("Error initializing or opening connection to the generator controller device: " + str(e1))
            sys.exit(1) # Exit if controller cannot be initialized.

        # Start all registered threads (controller threads, pipe threads, server threads, etc.).
        self.StartThreads()

        # Process any feedback information that might have been logged previously.
        self.ProcessFeedbackInfo()

        # Send a startup notification email.
        IP = self.GetNetworkIp() # Get current IP address.
        self.MessagePipe.SendMessage(
            "Generator Monitor Starting at " + self.SiteName,
            "Generator Monitor Starting at "
            + self.SiteName
            + " using IP address "
            + IP,
            msgtype="info", # Message type for email classification.
        )

        # Log successful startup.
        self.LogError(
            "GenMon Loaded for site: "
            + self.SiteName
            + " using python "
            + str(sys.version_info.major)
            + "."
            + str(sys.version_info.minor)
            + ": VEnv: "
            + str(self.InVirtualEnvironment()) # Check if running in a virtual environment.
        )

    # ------------------------ Monitor::StartThreads----------------------------
    def StartThreads(self, reload=False):
        """
        Initializes and starts various background threads used by genmon.

        This method is responsible for creating and starting threads for:
        -   `ComWatchDog`: Monitors communication with the generator controller.
        -   `TimeSyncThread`: Handles synchronization of the generator's time
            with the system time, especially around Daylight Savings Time changes,
            if `self.bSyncDST` or `self.bSyncTime` is enabled.
        -   Weather fetching (`MyWeather` thread): If weather fetching is enabled
            (not `self.DisableWeather`) and API key/location are provided, it
            initializes the `MyWeather` object, which internally starts its own
            thread for periodic weather updates.

        The created thread objects are stored in `self.Threads`, a dictionary
        mapping thread names to `MyThread` instances.

        Args:
            reload (bool, optional): This parameter is present but not currently
                                     used within the method's logic. It might be
                                     intended for future use if threads need to
                                     be reloaded or restarted dynamically.
                                     Defaults to False.
        """
        try:
            # Start the Communications Watchdog thread.
            # This thread monitors if data is being received from the generator controller.
            self.Threads["ComWatchDog"] = MyThread(self.ComWatchDog, Name="ComWatchDog")

            # Start the Time Synchronization Thread if enabled in the configuration.
            # This thread handles syncing the generator's clock with the system clock,
            # particularly for DST changes or periodic forced syncs.
            if self.bSyncDST or self.bSyncTime:  # Check if either DST sync or periodic time sync is enabled.
                self.Threads["TimeSyncThread"] = MyThread(
                    self.TimeSyncThread, Name="TimeSyncThread"
                )

            # Initialize and start weather fetching thread if weather is enabled and configured.
            if (
                not self.DisableWeather  # Weather fetching is not disabled.
                and self.WeatherAPIKey is not None and len(self.WeatherAPIKey) # API key is provided.
                and self.WeatherLocation is not None and len(self.WeatherLocation) # Location is provided.
            ):
                # Determine unit system (metric or imperial) for weather data.
                Unit = "metric" if self.UseMetric else "imperial"
                # Create MyWeather instance, which starts its own internal update thread.
                self.MyWeather = MyWeather(
                    self.WeatherAPIKey,
                    location=self.WeatherLocation,
                    unit=Unit,
                    log=self.log, # Pass the main logger to MyWeather.
                )
                # Add threads created by MyWeather (if any, though usually it's self-contained) to genmon's thread list.
                self.Threads = self.MergeDicts(self.Threads, self.MyWeather.Threads)
                self.log.info("Weather fetching thread initialized and started via MyWeather.")
            else:
                self.log.info("Weather fetching is disabled or Weather API key/location not configured. Weather thread not started.")

        except Exception as e1:
            self.LogErrorLine(f"Error in StartThreads during initialization of one or more threads: {str(e1)}")
            # Depending on which thread failed, this could be a critical error.
            # For now, it logs and continues, other parts of genmon might still function.

    # -------------------- Monitor::GetConfig-----------------------------------
    def GetConfig(self):
        """
        Reads configuration settings from the `genmon.conf` file and populates
        the corresponding instance attributes of the Monitor class.

        This method uses the `self.config` (a `MyConfig` instance initialized
        in `__init__`) to read various options from the "[GenMon]" section of
        `genmon.conf`. For each option, it typically checks if the option exists
        and then reads its value, often with type conversion (e.g., to boolean
        or integer) and default values if the option is missing.

        Key configuration options read include:
        -   `sitename`: A user-friendly name for the monitoring site.
        -   `debug`: Enables or disables debug logging and features.
        -   `multi_instance`: Allows or disallows multiple instances of genmon.py.
        -   Email settings: `incoming_mail_folder`, `processed_mail_folder`.
        -   Server settings: `server_port` for the command/status interface,
            `genmon_server_address` for binding the server socket.
        -   Log and data paths: `loglocation`, `userdatalocation`.
        -   Time synchronization: `syncdst` (sync on DST change), `synctime` (periodic sync).
        -   Platform statistics: `disableplatformstats` to turn off OS-level stats.
        -   Simulation mode: `simulation` (enable/disable), `simulationfile` (path to data).
        -   Controller type: `controllertype` (e.g., "h_100", "powerzone", "custom", "generac_evo_nexus").
        -   Weather settings: `disableweather`, `weatherkey` (API key), `weatherlocation`,
            `metricweather` (use metric units), `minimumweatherinfo` (fetch minimal data).
        -   Command restrictions: `readonlyemailcommands` to disallow settings changes via email.
        -   Performance: `optimizeforslowercpu`, `watchdog_addition` (extra time for comms watchdog).
        -   Version tracking: Reads `version` and `install` (install timestamp) from config,
            compares with `ProgramDefaults.GENMON_VERSION` to detect new installs or upgrades,
            and updates these values in the config if necessary. Sets `self.NewInstall` flag.
        -   Automated feedback: `autofeedback` to enable/disable sending diagnostic data.
        -   Software update checks: `update_check` (enable/disable), `user_url` (custom URL for web UI).

        If critical options are missing or if errors occur during reading (though
        `MyConfig` handles many defaults), it logs an error and may cause program exit.

        Returns:
            bool: True if all essential configurations are read successfully.
                  False if a critical error occurs during configuration reading
                  (e.g., `MyConfig` raises an unhandled exception, though this
                  is less likely due to its default value handling).
        """
        try:
            # Read 'sitename': User-defined name for the location being monitored.
            if self.config.HasOption("sitename"):
                self.SiteName = self.config.ReadValue("sitename")

            # Read 'debug': Enables detailed logging and potentially other debug features.
            self.debug = self.config.ReadValue("debug", return_type=bool, default=False)

            # Read 'multi_instance': Allows multiple instances of genmon.py to run if True.
            # Used by MySupport.IsRunning() to determine if another instance is an error.
            self.multi_instance = self.config.ReadValue(
                "multi_instance", return_type=bool, default=False
            )

            # --- Email Configuration ---
            # Read 'incoming_mail_folder': IMAP folder for incoming email commands.
            if self.config.HasOption("incoming_mail_folder"):
                self.IncomingEmailFolder = self.config.ReadValue(
                    "incoming_mail_folder"
                )
            # Read 'processed_mail_folder': IMAP folder where processed emails are moved.
            if self.config.HasOption("processed_mail_folder"):
                self.ProcessedEmailFolder = self.config.ReadValue(
                    "processed_mail_folder"
                )

            # --- Server Socket Configuration (for client commands/status) ---
            # Read 'server_port': TCP port for the command/status server. Must match client configurations.
            if self.config.HasOption("server_port"):
                self.ServerSocketPort = self.config.ReadValue(
                    "server_port", return_type=int # Ensure it's an integer.
                )
            # Read 'genmon_server_address': IP address for the server socket to bind to.
            # Default is empty string, meaning bind to all available interfaces (0.0.0.0 or ::).
            self.ServerIPAddress = self.config.ReadValue("genmon_server_address", default = "")

            # --- Log and Data Locations ---
            # Read 'loglocation': Directory path for storing log files (genmon.log, etc.).
            # Defaults to ProgramDefaults.LogPath if not specified.
            self.LogLocation = self.config.ReadValue(
                "loglocation", default=ProgramDefaults.LogPath
            )
            # Read 'userdatalocation': Path for user-defined data files (e.g., userdefined.json).
            # Defaults to the directory where genmon.py is located.
            self.UserDefinedDataPath = self.config.ReadValue(
                "userdatalocation", default=os.path.dirname(os.path.realpath(__file__))
            )

            # --- Time Synchronization Settings ---
            # Read 'syncdst': If True, synchronize generator time when Daylight Savings Time changes.
            if self.config.HasOption("syncdst"):
                self.bSyncDST = self.config.ReadValue("syncdst", return_type=bool)
            # Read 'synctime': If True, periodically synchronize generator time with system time.
            if self.config.HasOption("synctime"):
                self.bSyncTime = self.config.ReadValue("synctime", return_type=bool)

            # --- Platform Statistics ---
            # Read 'disableplatformstats': If True, disable collection/display of OS platform stats (CPU, memory, etc.).
            if self.config.HasOption("disableplatformstats"):
                self.bDisablePlatformStats = self.config.ReadValue(
                    "disableplatformstats", return_type=bool
                )

            # --- Simulation Mode Settings ---
            # Read 'simulation': If True, run in simulation mode (uses data from a file instead of live controller).
            if self.config.HasOption("simulation"):
                self.Simulation = self.config.ReadValue("simulation", return_type=bool)
            # Read 'simulationfile': Path to the file containing data for simulation mode.
            if self.config.HasOption("simulationfile"):
                self.SimulationFile = self.config.ReadValue("simulationfile")

            # --- Controller Type ---
            # Read 'controllertype': Specifies the type of generator controller (e.g., "h_100", "powerzone", "custom").
            # This determines which controller class (HPanel, PowerZone, CustomController, Evolution) is instantiated.
            if self.config.HasOption("controllertype"):
                self.ControllerSelected = self.config.ReadValue("controllertype")

            # --- Weather Settings ---
            # Read 'disableweather': If True, disable all weather fetching functionality.
            if self.config.HasOption("disableweather"):
                self.DisableWeather = self.config.ReadValue(
                    "disableweather", return_type=bool
                )
            else:
                self.DisableWeather = False # Default to weather being enabled if option is missing.
            # Read 'weatherkey': API key for the weather service (e.g., OpenWeatherMap).
            if self.config.HasOption("weatherkey"):
                self.WeatherAPIKey = self.config.ReadValue("weatherkey")
            # Read 'weatherlocation': Location string for weather data (e.g., "City,Country" or zip code).
            if self.config.HasOption("weatherlocation"):
                self.WeatherLocation = self.config.ReadValue("weatherlocation")
            # Read 'metricweather': If True, use metric units (Celsius, kph) for weather data. Imperial (Fahrenheit, mph) otherwise.
            if self.config.HasOption("metricweather"):
                self.UseMetric = self.config.ReadValue(
                    "metricweather", return_type=bool
                )
            # Read 'minimumweatherinfo': If True, fetch only essential/minimal weather information.
            if self.config.HasOption("minimumweatherinfo"):
                self.WeatherMinimum = self.config.ReadValue(
                    "minimumweatherinfo", return_type=bool
                )

            # --- Command Security and Performance ---
            # Read 'readonlyemailcommands': If True, disallow email commands that modify generator settings.
            if self.config.HasOption("readonlyemailcommands"):
                self.ReadOnlyEmailCommands = self.config.ReadValue(
                    "readonlyemailcommands", return_type=bool
                )
            # Read 'optimizeforslowercpu': If True, enable optimizations that might reduce CPU load (e.g., less frequent polling).
            if self.config.HasOption("optimizeforslowercpu"):
                self.SlowCPUOptimization = self.config.ReadValue(
                    "optimizeforslowercpu", return_type=bool
                )
            # Read 'watchdog_addition': Additional time (in seconds) for the communications watchdog timeout.
            # Allows tuning for slower or less reliable communication links.
            self.AdditionalWatchdogTime = self.config.ReadValue(
                "watchdog_addition", return_type=int, default=0 # Defaults to 0 if not specified.
            )

            # --- Version and Installation Tracking ---
            # Read 'version': The version of genmon last recorded in this config file.
            if self.config.HasOption("version"):
                self.Version = self.config.ReadValue("version") # Store the version from config.
                # Compare with current program version. If different, it's an upgrade (or downgrade).
                if not self.Version == ProgramDefaults.GENMON_VERSION:
                    self.config.WriteValue("version", ProgramDefaults.GENMON_VERSION) # Update config with current version.
                    self.NewInstall = True # Flag as NewInstall (used for upgrades too).
            else: # If 'version' option is missing entirely, it's a new installation.
                self.config.WriteValue("version", ProgramDefaults.GENMON_VERSION) # Write current version to config.
                self.NewInstall = True # Flag as NewInstall.
                self.Version = ProgramDefaults.GENMON_VERSION # Set current version.
                # Record the installation timestamp.
                self.config.WriteValue("install", str(datetime.datetime.now()))
            # Read 'install': The timestamp of the initial installation (or when this logic was first run).
            # If 'install' option is missing (e.g., older config), try to use file's last access time as a heuristic.
            if not self.config.HasOption("install"):
                try:
                    stat = os.stat(self.config.FileName) # Get file stats for genmon.conf.
                    # Use last access time (st_atime) as an approximation for install time.
                    self.config.WriteValue("install", str(datetime.datetime.fromtimestamp(stat.st_atime)))
                except: # If getting file stats fails, mark as Unknown.
                    self.config.WriteValue("install", "Unknown")
            self.InstallTime = self.config.ReadValue("install", default = "Unknown") # Read the install timestamp.

            # --- Automated Feedback Settings ---
            # Read 'autofeedback': If True, enable sending automated diagnostic feedback (e.g., to developer).
            if self.config.HasOption("autofeedback"):
                self.FeedbackEnabled = self.config.ReadValue(
                    "autofeedback", return_type=bool
                )
            else: # If option is missing, default to False and write it to config.
                self.config.WriteValue("autofeedback", "False")
                self.FeedbackEnabled = False
            # Load any previously saved (unsent) feedback messages from the feedback log file.
            if os.path.isfile(self.FeedbackLogFile):
                try:
                    with open(self.FeedbackLogFile) as infile:
                        self.FeedbackMessages = json.load(infile) # Load messages from JSON file.
                except Exception as e1: # If loading fails (e.g., corrupt file), remove the file.
                    self.LogErrorLine(f"Error loading feedback log file '{self.FeedbackLogFile}': {e1}. Removing it.")
                    os.remove(self.FeedbackLogFile)

            # --- Software Update Check Settings ---
            # Read 'update_check': If True (default), enable checking for genmon software updates.
            self.UpdateCheck = self.config.ReadValue(
                "update_check", return_type=bool, default=True
            )
            # Read 'user_url': A user-defined URL for their genmon web interface, included in update notifications.
            self.UserURL = self.config.ReadValue("user_url", default="").strip()

            # Read 'update_check_user': GitHub username for software update checks.
            self.UpdateCheckUser = self.config.ReadValue(
                "update_check_user", default="jgyates"
            ).strip()
            # Read 'update_check_repo': GitHub repository name for software update checks.
            self.UpdateCheckRepo = self.config.ReadValue(
                "update_check_repo", default="genmon"
            ).strip()

            # Read 'update_check_branch': GitHub branch for software update checks.
            self.UpdateCheckBranch = self.config.ReadValue(
                "update_check_branch", default="master"
            ).strip()

        except Exception as e1: # Catch any other unexpected errors during config reading.
            self.Console( # Use Console as self.log might not be fully set up if GetConfig fails early.
                "CRITICAL ERROR: Missing essential config file entries or error reading genmon.conf: " + str(e1) +
                ". Please check your configuration. Exiting."
            )
            return False # Indicate failure to load configuration.

        return True # All configurations read successfully.

    # ---------------------------------------------------------------------------
    def ProcessFeedbackInfo(self):
        """
        Processes and sends any stored feedback messages.

        This method is called during genmon startup. It checks if automated
        feedback is enabled (`self.FeedbackEnabled`). If so, it iterates through
        any messages stored in `self.FeedbackMessages` (which are loaded from
        `self.FeedbackLogFile` during `GetConfig`).

        For each stored feedback message, it sends an email to the maintainer
        (`self.MaintainerAddress`) via `self.MessagePipe.SendMessage`. The email
        includes the feedback entry (which contains the reason and diagnostic data)
        and attaches relevant log files obtained from `self.GetLogFileNames()`.

        After attempting to send all stored feedback messages, it deletes the
        `self.FeedbackLogFile` to prevent resending the same information on the
        next startup. This implies a "send once" attempt for stored feedback.
        """
        try:
            # Only process if automated feedback is enabled in genmon.conf.
            if self.FeedbackEnabled:
                if not self.FeedbackMessages: # Check if there are any messages to process.
                    self.log.info("ProcessFeedbackInfo: No stored feedback messages to process.")
                    return

                self.log.info(f"ProcessFeedbackInfo: Found {len(self.FeedbackMessages)} stored feedback messages. Attempting to send them.")
                # Iterate through each stored feedback entry.
                # Key is often the "Reason" string, Entry is the detailed message body.
                for Key, Entry in self.FeedbackMessages.items():
                    self.MessagePipe.SendMessage(
                        "Generator Monitor Submission (from stored feedback)", # Email subject.
                        Entry, # The body of the feedback message.
                        recipient=self.MaintainerAddress, # Developer/maintainer email address.
                        files=self.GetLogFileNames(),     # Attach current log files.
                        msgtype="error", # Typically sent as "error" type for visibility.
                    )
                    self.log.info(f"Sent stored feedback for reason: {Key}")

                # After attempting to send all stored messages, delete the feedback log file
                # to prevent resending them on the next startup.
                if os.path.isfile(self.FeedbackLogFile):
                    try:
                        os.remove(self.FeedbackLogFile)
                        self.log.info(f"Removed feedback log file: {self.FeedbackLogFile}")
                    except OSError as oe:
                        self.LogErrorLine(f"Error removing feedback log file '{self.FeedbackLogFile}': {oe}")
            else:
                self.log.info("ProcessFeedbackInfo: Automated feedback is disabled. Skipping processing of stored feedback messages.")
        except Exception as e1:
            self.LogErrorLine(f"Error in ProcessFeedbackInfo while processing stored feedback: {str(e1)}")

    # ---------------------------------------------------------------------------
    def FeedbackReceiver(self, Message):
        """
        Callback method to handle feedback messages received via the FeedbackPipe.

        This method is registered as the callback for `self.FeedbackPipe`. When
        another part of genmon (typically a controller module) sends a feedback
        message through this pipe, this method is invoked.

        The `Message` is expected to be a JSON string containing a dictionary
        with keys like "Reason", "Always", "Message", "FullLogs", and "NoCheck".
        This method parses the JSON string and then calls `self.SendFeedbackInfo()`
        with the extracted parameters to construct and potentially send the
        feedback information.

        Args:
            Message (str): A JSON string representing the feedback data.
                           Example:
                           '{
                               "Reason": "Communication Error",
                               "Always": false,
                               "Message": "Failed to read Modbus register.",
                               "FullLogs": true,
                               "NoCheck": false
                           }'
        """
        try:
            self.log.debug(f"FeedbackReceiver: Received message via pipe: {Message[:200]}...") # Log snippet
            # Parse the incoming JSON string into a Python dictionary.
            FeedbackDict = json.loads(Message)

            # Call SendFeedbackInfo with the parameters extracted from the dictionary.
            # .get() is used for optional parameters to provide defaults if they are missing.
            self.SendFeedbackInfo(
                FeedbackDict.get("Reason", "Unknown Reason"), # Reason for the feedback.
                Always=FeedbackDict.get("Always", False),     # Send even if not NewInstall.
                Message=FeedbackDict.get("Message", ""),      # Additional custom message.
                FullLogs=FeedbackDict.get("FullLogs", True),  # Include full logs or minimal info.
                NoCheck=FeedbackDict.get("NoCheck", False)    # Bypass some checks in SendFeedbackInfo.
            )
        except json.JSONDecodeError as jde:
            self.LogErrorLine(f"Error in FeedbackReceiver: Failed to decode JSON message: {str(jde)}. Message (first 200 chars): '{Message[:200]}'")
        except KeyError as ke:
            self.LogErrorLine(f"Error in FeedbackReceiver: Missing expected key in JSON message: {str(ke)}. Message: {Message}")
        except Exception as e1:
            self.LogErrorLine(f"Error in FeedbackReceiver while processing message: {str(e1)}")
            self.LogError(f"FeedbackReceiver - Size of problematic message: {len(Message)}")
            self.LogError(f"FeedbackReceiver - Problematic message content (first 500 chars): {Message[:500]}")

    # ---------------------------------------------------------------------------
    def MessageReceiver(self, Message):
        """
        Callback method to handle general messages received via the MessagePipe
        and send them as emails.

        This method is registered as the callback for `self.MessagePipe`.
        Various parts of genmon can send messages (e.g., alerts, status updates,
        notifications) through this pipe to be emailed to the user or other
        configured recipients.

        The `Message` is expected to be a JSON string containing a dictionary
        with details for the email, such as "subjectstr", "msgstr" (body),
        "recipient", "files" (to attach), "deletefile" (after sending), and
        "msgtype".

        It uses `self.mail.sendEmail()` to dispatch the email.

        Args:
            Message (str): A JSON string representing the email data.
                           Example:
                           '{
                               "subjectstr": "Generator Alert",
                               "msgstr": "Generator has started.",
                               "recipient": "user@example.com",
                               "files": ["/path/to/log.txt"],
                               "deletefile": true,
                               "msgtype": "alert"
                           }'
        """
        try:
            self.log.debug(f"MessageReceiver: Received message via pipe for emailing: {Message[:200]}...") # Log snippet
            # Parse the incoming JSON string into a Python dictionary.
            MessageDict = json.loads(Message)

            # Call MyMail's sendEmail method with parameters extracted from the dictionary.
            # .get() is used for optional parameters to provide defaults if they are missing.
            self.mail.sendEmail(
                MessageDict.get("subjectstr", "Genmon Notification"), # Email subject.
                MessageDict.get("msgstr", ""),                      # Email body.
                recipient=MessageDict.get("recipient", None),       # Recipient address(es).
                files=MessageDict.get("files", None),               # List of files to attach.
                deletefile=MessageDict.get("deletefile", False),    # Delete attached files after sending.
                msgtype=MessageDict.get("msgtype", "info")          # Message type for email classification/filtering.
            )
        except json.JSONDecodeError as jde:
            self.LogErrorLine(f"Error in MessageReceiver: Failed to decode JSON message: {str(jde)}. Message (first 200 chars): '{Message[:200]}'")
        except KeyError as ke:
            self.LogErrorLine(f"Error in MessageReceiver: Missing expected key in JSON message: {str(ke)}. Message: {Message}")
        except Exception as e1:
            self.LogErrorLine(f"Error in MessageReceiver while processing message for email: {str(e1)}")

    # ---------------------------------------------------------------------------
    def SendFeedbackInfo(
        self, Reason, Always=False, Message=None, FullLogs=True, NoCheck=False
    ):
        """
        Sends diagnostic feedback information, typically to the genmon developer.

        This method constructs a detailed feedback message including the reason,
        system startup information, platform statistics, communication statistics,
        and raw Modbus register data.

        The feedback is sent as an email via `self.MessagePipe.SendMessage` if
        `self.FeedbackEnabled` is True. If feedback is not enabled, the message
        is stored locally in `self.FeedbackLogFile` (a JSON file) to be
        potentially sent later if feedback is enabled or by `ProcessFeedbackInfo`
        on next startup.

        Args:
            Reason (str): A string describing the reason for sending the feedback
                          (e.g., "NewInstall", "CommunicationError"). This is used
                          as part of the email body and as a key if storing the
                          message locally.
            Always (bool, optional): If True, feedback is sent regardless of the
                                     `self.NewInstall` status. If False (default),
                                     feedback for some reasons might only be sent
                                     if `self.NewInstall` is True. The `NoCheck`
                                     parameter can also influence this.
            Message (str, optional): An additional custom message string to include
                                     in the feedback body. Defaults to None.
            FullLogs (bool, optional): This parameter is present but not directly
                                       used in the current implementation to decide
                                       between full or minimal logs for *this specific*
                                       feedback. Log attachment is handled by
                                       `GetLogFileNames()`. It might be a placeholder
                                       for future granularity. Defaults to True.
            NoCheck (bool, optional): If True, bypasses a check that prevents
                                      sending the same "Reason" more than once
                                      from the stored `self.FeedbackMessages`.
                                      Defaults to False.

        Side Effects:
            - Sends an email if `self.FeedbackEnabled` is True.
            - Writes to `self.FeedbackLogFile` if `self.FeedbackEnabled` is False.
            - Updates `self.FeedbackMessages` dictionary in memory.
        """
        try:
            # Feedback is typically sent on a new install or if 'Always' is True.
            if self.NewInstall or Always:

                # Check if feedback for this specific 'Reason' has already been sent/logged in this session,
                # unless NoCheck is True (which forces sending/logging).
                CheckedSent = self.FeedbackMessages.get(Reason, "")
                if not CheckedSent == "" and not NoCheck: # If already processed and NoCheck is False
                    self.log.debug(f"Feedback for reason '{Reason}' already processed in this session and NoCheck is False. Skipping.")
                    return # Skip sending/logging again for this reason in this session.

                # Log the reason and message if NoCheck is False (standard logging).
                if not NoCheck:
                    log_entry = f"Preparing feedback for reason: {Reason}"
                    if Message:
                        log_entry += f" - Custom Message: {Message}"
                    self.LogError(log_entry) # LogError is used, implies higher importance.

                # Construct the main body of the feedback message.
                msgbody = "Reason = " + Reason + "\n"
                if Message != None: # Append custom message if provided.
                    msgbody += "Message : " + Message + "\n"

                # Add system startup information (version, sitename, OS, Python version, etc.).
                # ProcessDispatch formats the dictionary from GetStartInfo into a string.
                msgbody += self.printToString(
                    self.ProcessDispatch(self.GetStartInfo(NoTile=True), "") # NoTile for compact format.
                )
                # Add platform statistics (CPU, memory, disk, etc.) if not disabled.
                if not self.bDisablePlatformStats:
                    msgbody += self.printToString(
                        self.ProcessDispatch(
                            {"Platform Stats": self.GetPlatformStats()}, ""
                        )
                    )
                # Add communication statistics from the controller.
                msgbody += self.printToString(
                    self.ProcessDispatch(
                        {"Comm Stats": self.Controller.GetCommStatus()}, ""
                    )
                )

                # Add detailed support data (includes raw Modbus registers, health, etc.) in JSON format.
                msgbody += "\n" + self.GetSupportData() + "\n"

                # If automated feedback is enabled in genmon.conf, send the feedback via email.
                if self.FeedbackEnabled:
                    self.log.info(f"Automated feedback enabled. Sending feedback for reason '{Reason}' via MessagePipe.")
                    self.MessagePipe.SendMessage(
                        "Generator Monitor Submission (Feedback)", # Email subject.
                        msgbody,                                  # Constructed message body.
                        recipient=self.MaintainerAddress,         # Developer/maintainer email.
                        files=self.GetLogFileNames(),             # Attach relevant log files.
                        msgtype="error", # Often sent as "error" type for higher visibility.
                    )
                else: # If feedback is not enabled, store the message in the feedback log file.
                    self.log.info(f"Automated feedback disabled. Storing feedback for reason '{Reason}' in '{self.FeedbackLogFile}'.")

                # Store the sent/logged feedback message in memory to avoid resending for the same reason
                # within the same session (unless NoCheck is True).
                self.FeedbackMessages[Reason] = msgbody

                # If feedback is not enabled, write the updated FeedbackMessages dictionary to the JSON log file.
                # This persists it for potential sending by ProcessFeedbackInfo on next startup if enabled then.
                if not self.FeedbackEnabled:
                    try:
                        with open(self.FeedbackLogFile, "w") as outfile:
                            json.dump(
                                self.FeedbackMessages, # The entire dictionary of feedback messages.
                                outfile,
                                sort_keys=True,       # Sort keys for consistent file output.
                                indent=4,             # Pretty-print JSON with indentation.
                                ensure_ascii=False    # Allow non-ASCII characters.
                            )
                        self.log.info(f"Successfully wrote updated feedback messages to '{self.FeedbackLogFile}'.")
                    except IOError as ioe:
                        self.LogErrorLine(f"IOError writing feedback log file '{self.FeedbackLogFile}': {ioe}")
                    except Exception as e_json_dump:
                         self.LogErrorLine(f"Error dumping feedback messages to JSON file '{self.FeedbackLogFile}': {e_json_dump}")
        except Exception as e1:
            self.LogErrorLine(f"Error in SendFeedbackInfo for reason '{Reason}': {str(e1)}")

    # ---------- Monitor::EmailSendIsEnabled-------------------------------------
    def EmailSendIsEnabled(self):
        """
        Checks if the email sending thread (`SendMailThread`) is active.

        This method accesses `self.Threads` (a dictionary of `MyThread` objects)
        to find the thread named "SendMailThread". If this thread exists and is
        alive (running), it indicates that the email sending functionality,
        managed by the `MyMail` class, is operational.

        Returns:
            bool: True if the "SendMailThread" exists and is alive.
                  False otherwise (e.g., thread not found, not started, or stopped).
        """
        # Attempt to get the 'SendMailThread' object from the Threads dictionary.
        EmailThread = self.Threads.get("SendMailThread", None)
        if EmailThread == None: # If the thread doesn't exist in the dictionary.
            return False
        return EmailThread.is_alive() # Check if the thread is currently running.

    # ---------- Monitor::GetSupportData-----------------------------------------
    def GetSupportData(self):
        """
        Collects a comprehensive set of diagnostic and support data from genmon
        and its controller, formatted as a JSON string.

        This method gathers various pieces of information useful for troubleshooting
        and support, including:
        -   Program run time.
        -   Installation timestamp.
        -   Current system health status.
        -   Selected controller type.
        -   Basic startup information (genmon version, Python version, OS, etc.).
        -   Communication statistics with the generator controller.
        -   Platform statistics (CPU, memory, disk usage), if not disabled.
        -   Raw Modbus register data (Holding registers, Strings, FileData, Coils, Inputs)
            read from the generator controller.

        The collected data is structured in an `OrderedDict` to maintain a somewhat
        predictable order and then serialized into a JSON string with indentation
        for readability.

        Returns:
            str: A JSON string containing the collected support data.
                 Returns an error message string if JSON serialization fails.
        """
        SupportData = collections.OrderedDict() # Use OrderedDict to maintain key order.
        try:
            # Gather various pieces of system and program information.
            SupportData["Program Run Time"] = self.GetProgramRunTime()
            SupportData["Install"] = self.InstallTime
            SupportData["Monitor Health"] = self.GetSystemHealth()
            SupportData["Controller Selected"] = self.ControllerSelected.lower() # Store controller type in lowercase.
            SupportData["StartInfo"] = self.GetStartInfo(NoTile=True) # NoTile for compact format.
            SupportData["Comm Stats"] = self.Controller.GetCommStatus()

            # Include platform (OS) statistics if not disabled in the config.
            if not self.bDisablePlatformStats:
                SupportData["PlatformStats"] = self.GetPlatformStats()

            # Include raw Modbus data from the controller.
            # The original code had a commented-out line for DisplayRegisters(AllRegs=True, DictOut=True).
            # The following directly accesses the raw register data attributes from the controller.
            SupportData["Holding Registers (Raw)"] = self.Controller.Holding # Modbus Holding Registers.
            SupportData["String Registers (Raw)"] = self.Controller.Strings   # Decoded String Registers.
            SupportData["File Data Registers (Raw)"] = self.Controller.FileData # Data read via file transfer mode.
            SupportData["Coil Registers (Raw)"] = self.Controller.Coils       # Modbus Coil Registers.
            SupportData["Input Registers (Raw)"] = self.Controller.Inputs     # Modbus Discrete Input Registers.
        except Exception as e1:
            self.LogErrorLine(f"Error encountered while gathering data in GetSupportData: {str(e1)}")
            # SupportData might be partially populated, which is acceptable.

        try:
            # Serialize the collected data to a JSON string.
            # `indent=4` makes the JSON output human-readable.
            # `sort_keys=False` is used with OrderedDict to preserve the insertion order.
            return json.dumps(SupportData, indent=4, sort_keys=False)
        except Exception as e1: # Handle errors during JSON serialization.
            self.LogErrorLine(f"Error serializing support data to JSON in GetSupportData: {str(e1)}")
            return f'{{"Error": "Failed to serialize support data to JSON: {str(e1)}" }}' # Return a JSON error object.

    # ---------- Monitor::GetLogFileNames----------------------------------------
    def GetLogFileNames(self):
        """
        Compiles a list of full paths to genmon-related log files and data files
        that are useful for support and diagnostics.

        This method defines two lists:
        -   `FilesToSend`: Contains basenames of log files typically found in
            `self.LogLocation` (e.g., /var/log/genmon/).
        -   `DataFilesToSend`: Contains basenames of other data files (like
            `update.txt`) typically found in `self.ConfigFilePath`
            (e.g., /etc/genmon/).

        It iterates through these lists, constructs the full path for each file,
        checks if the file exists using `os.path.isfile()`, and if so, adds
        the full path to `LogList`.

        This list of file paths is primarily used when sending support information
        or feedback emails, allowing relevant logs and data to be attached.

        Returns:
            list of str or None: A list containing the absolute paths to all existing
                                 log and data files identified. Returns None if an
                                 unexpected exception occurs during the process.
        """
        try:
            LogList = [] # Initialize an empty list to store full file paths.

            # List of standard log file basenames.
            FilesToSend = [
                "genmon.log", "genserv.log", "mymail.log", "myserial.log",
                "mymodbus.log", "gengpio.log", "gengpioin.log", "gensms.log",
                "gensms_modem.log", "genmqtt.log", "genmqttin.log", "genpushover.log",
                "gensyslog.log", "genloader.log", "myserialtcp.log", "genlog.log",
                "genslack.log", "gencallmebot.log", "genexercise.log", "genemail2sms.log",
                "gencentriconnect.log", "gentankutil.log", "genalexa.log", "gensnmp.log",
                "gentemp.log", "gentankdiy.log", "gengpioledblink.log", "gencthat.log",
                "genmopeka.log", "gencustomgpio.log", "gensms_voip.log",
            ]
            # List of other data files (e.g., update timestamp).
            DataFilesToSend = [
                "update.txt" # Stores timestamp of the last software update.
            ]

            # Check for log files in self.LogLocation (e.g., /var/log/genmon/).
            for file_basename in FilesToSend:
                full_log_path = os.path.join(self.LogLocation, file_basename) # Construct full path.
                if os.path.isfile(full_log_path): # Check if the file exists.
                    LogList.append(full_log_path) # Add to list if it exists.

            # Check for data files in self.ConfigFilePath (e.g., /etc/genmon/).
            for file_basename in DataFilesToSend:
                full_data_file_path = os.path.join(self.ConfigFilePath, file_basename) # Construct full path.
                if os.path.isfile(full_data_file_path): # Check if the file exists.
                    LogList.append(full_data_file_path) # Add to list if it exists.

            return LogList # Return the list of existing file paths.
        except Exception as e1: # Catch any unexpected errors.
            self.LogErrorLine(f"Error in GetLogFileNames while compiling list of log/data files: {str(e1)}")
            return None # Return None on error.

    # ---------- Monitor::SendSupportInfo----------------------------------------
    def SendSupportInfo(self, SendLogs=True):
        """
        Constructs and sends a support information email.

        This method is typically triggered by a user command (e.g., "sendlogfiles"
        or "sendregisters" from the web UI or email). It gathers various pieces
        of diagnostic information:
        -   Basic startup info (`GetStartInfo`).
        -   Platform statistics (`GetPlatformStats`), if not disabled.
        -   Communication statistics (`Controller.GetCommStatus`).
        -   Comprehensive support data in JSON format (`GetSupportData`), which
            includes raw Modbus registers and other detailed states.

        This information is compiled into an email body.
        -   If `SendLogs` is True (default), it also attaches log files obtained
            from `GetLogFileNames()` to the email. The email subject will reflect
            "Log File Submission".
        -   If `SendLogs` is False, no logs are attached, and the subject indicates
            "Register Submission".

        The email is sent to the configured maintainer address (`self.MaintainerAddress`)
        via `self.MessagePipe.SendMessage`.

        Args:
            SendLogs (bool, optional): If True, log files are attached to the
                                       support email. Defaults to True.

        Returns:
            str: A status message indicating "Log files submitted", "Register data submitted",
                 or an error message if email sending is not enabled or if an
                 exception occurs.
        """
        try:
            # Check if email sending functionality is enabled and operational.
            if not self.EmailSendIsEnabled():
                error_msg = "Error in SendSupportInfo: Email sending is not enabled or not functional. Cannot send support info."
                self.LogError(error_msg)
                return error_msg # Return error message to the caller.

            # Construct the main body of the support email.
            msgbody = ""
            # Add system startup information.
            msgbody += self.printToString(
                self.ProcessDispatch(self.GetStartInfo(NoTile=True), "") # NoTile for compact format.
            )
            # Add platform statistics if not disabled.
            if not self.bDisablePlatformStats:
                msgbody += self.printToString(
                    self.ProcessDispatch(
                        {"Platform Stats": self.GetPlatformStats()}, ""
                    )
                )
            # Add communication statistics.
            msgbody += self.printToString(
                self.ProcessDispatch(
                    {"Comm Stats": self.Controller.GetCommStatus()}, ""
                )
            )

            # The original code had a commented line: #msgbody += self.Controller.DisplayRegisters(AllRegs=True)
            # This is now covered by GetSupportData() which includes raw registers.

            # Append the comprehensive support data in JSON format.
            msgbody += "\n--- JSON Support Data ---\n" + self.GetSupportData() + "\n--- End JSON Support Data ---\n"

            # Determine email subject and if logs should be attached.
            if SendLogs:
                msgtitle = self.SiteName + ": Generator Monitor Log File Submission"
                LogList = self.GetLogFileNames() # Get list of log files to attach.
                response_message = "Log files submitted successfully."
            else:
                msgtitle = self.SiteName + ": Generator Monitor Register Submission"
                LogList = None # No logs attached.
                response_message = "Register data submitted successfully."

            # Send the email via MessagePipe.
            self.MessagePipe.SendMessage(
                msgtitle,
                msgbody,
                recipient=self.MaintainerAddress, # Send to the configured maintainer.
                files=LogList,                    # Attach files if LogList is populated.
                msgtype="error", # Often sent as "error" type for higher visibility/filtering.
            )
            self.log.info(f"Support information sent: {response_message}")
            return response_message
        except Exception as e1:
            error_msg = f"Error in SendSupportInfo: {str(e1)}"
            self.LogErrorLine(error_msg)
            return error_msg # Return error message.

    # ---------- Send message ---------------------------------------------------
    def SendMessage(self, CmdString):
        """
        Parses a command string to send a custom notification message.

        The `CmdString` is expected to be in the format:
        `notify_message={"title": "My Title", "body": "My message body", "type": "info", "onlyonce": false, "oncedaily": false}`
        where:
        -   `title`: The subject/title of the notification.
        -   `body`: The main content of the notification.
        -   `type`: Message type (e.g., "info", "warn", "error"), used for email
                  classification or UI presentation.
        -   `onlyonce` (optional, bool): If True, the message is sent only once
                                       (tracked by MessagePipe).
        -   `oncedaily` (optional, bool): If True, the message is sent at most
                                        once per day (tracked by MessagePipe).

        It extracts these parameters from the JSON payload within `CmdString`
        and then uses `self.MessagePipe.SendMessage` to dispatch the notification,
        which typically results in an email being sent.

        Args:
            CmdString (str): The command string containing the JSON payload with
                             notification details.

        Returns:
            str: "OK" if the message was successfully parsed and dispatched to
                 MessagePipe. Returns an error string if parsing fails or an
                 exception occurs.
        """
        try:
            self.LogDebug("ENTER SendMessage")
            if CmdString == None or CmdString == "": # Validate command string.
                return "Error: invalid command in SendMessage (empty command string)"

            # Command string is expected to be "notify_message=JSON_PAYLOAD".
            # Split to get the JSON_PAYLOAD part.
            CmdParts = CmdString.split("=", 1) # Split only on the first "=".
            if len(CmdParts) != 2:
                self.LogError(
                    f"Validation Error: Error parsing command string in SendMessage. Expected format 'notify_message=JSON_DATA', got: {CmdString}"
                )
                return "Error in SendMessage: Invalid command format."

            # Load the JSON payload into a dictionary.
            json_payload_data = json.loads(CmdParts[1])

            # Extract data from the JSON payload.
            message_title = self.SiteName + ": " + json_payload_data.get("title", "Notification") # Default title if missing.
            message_body = json_payload_data.get("body", "")
            message_type = json_payload_data.get("type", "info") # Default type "info".
            send_only_once = json_payload_data.get("onlyonce", False)
            send_once_daily = json_payload_data.get("oncedaily", False)

            self.LogDebug(f"SendMessage details: Title='{message_title}', Type='{message_type}', OnlyOnce={send_only_once}, OnceDaily={send_once_daily}, Body='{message_body[:100]}...'")

            # Dispatch the message via MessagePipe.
            self.MessagePipe.SendMessage(
                message_title,
                message_body,
                msgtype=message_type,
                onlyonce=send_only_once,
                oncedaily=send_once_daily
            )
            return "OK" # Indicate successful dispatch.
        except json.JSONDecodeError as jde:
            self.LogErrorLine(f"Error in SendMessage: Failed to decode JSON payload: {str(jde)}. Command string: {CmdString}")
            return f"Error in SendMessage: JSON decode error - {str(jde)}"
        except KeyError as ke:
            self.LogErrorLine(f"Error in SendMessage: Missing expected key in JSON payload: {str(ke)}. Command string: {CmdString}")
            return f"Error in SendMessage: Missing key in JSON - {str(ke)}"
        except Exception as e1:
            self.LogErrorLine(f"Error in SendMessage: {str(e1)}. Command string: {CmdString}")
            return f"Error in SendMessage: {str(e1)}"
        # Original code had "return OK" outside try/except which is unreachable if an exception occurs.
        # It should only return "OK" on successful dispatch.

    # ------------ Monitor::DisplayHelp -----------------------------------------
    def DisplayHelp(self):
        """
        Generates a help string listing available commands and their descriptions.

        This method constructs a multi-line string that provides usage information
        for various commands accepted by genmon (e.g., "status", "maint", "settime").
        It also includes tips for accessing dealer menus on different generator
        controller types (Evolution, Nexus).

        The output is formatted for readability, typically for display on a console
        or in an email response.

        Returns:
            str: A formatted string containing help information.
        """
        outstring = "" # Initialize an empty string to build the help message.
        outstring += "Help:\n" # Main title.

        # Use self.printToString to format each line. While printToString might seem
        # like it prints to console, in this context (if called from ProcessCommand for email)
        # it would be part of building a string for an email body.
        # If DisplayHelp is called directly and its output printed, then it goes to console.
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
        # "exit" command is mentioned but not explicitly in CommandDict; likely handled by client or implies general program exit.
        outstring += self.printToString("   exit        - Exit this program")
        outstring += self.printToString("   sendlogfiles - Send log files to the developer if outbound email is setup.")
        # The second "is setup." seems like a typo in original.
        # outstring += self.printToString("                      is setup.") # Original line, likely a typo.

        outstring += self.printToString("\n") # Add spacing.

        # Tips for physical panel operations.
        outstring += self.printToString("To clear the Alarm/Warning message, press OFF on the control panel keypad")
        outstring += self.printToString("followed by the ENTER key. To access Dealer Menu on the Evolution")
        outstring += self.printToString("controller, from the top menu selection (SYSTEM, DATE/TIME,BATTERY, SUB-MENUS)")
        outstring += self.printToString("enter UP UP ESC DOWN UP ESC UP, then go to the dealer menu and press enter.")
        outstring += self.printToString("For liquid cooled models a level 2 dealer code can be entered, ESC UP UP DOWN")
        outstring += self.printToString("DOWN ESC ESC, then navigate to the dealer menu and press enter.")
        outstring += self.printToString("Passcode for Nexus controller is ESC, UP, UP ESC, DOWN, UP, ESC, UP, UP, ENTER.")
        outstring += self.printToString("\n")

        return outstring # Return the complete help string.

    # ------------ Monitor::GetProgramRunTime -----------------------------------
    def GetProgramRunTime(self):
        """
        Calculates and returns the program's current uptime.

        It subtracts the `self.ProgramStartTime` (recorded in `__init__`)
        from the current time (`datetime.datetime.now()`) to get a `timedelta`.
        This `timedelta` is then converted to a string, and microseconds are
        removed for cleaner display.

        Returns:
            str: A string representing the program's uptime (e.g.,
                 "Generator Monitor running for 1 day, 2:30:05.")
                 Returns "Unknown" if an error occurs during calculation.
        """
        try:
            # Calculate the difference between current time and program start time.
            ProgramRunTime = datetime.datetime.now() - self.ProgramStartTime
            # Convert timedelta to string and remove microseconds part (after '.').
            outstr = str(ProgramRunTime).split(".")[0]
            return f"{self.ProgramName} running for {outstr}."
        except Exception as e1:
            self.LogErrorLine(f"Error in GetProgramRunTime: {str(e1)}")
            return "Unknown" # Return "Unknown" if uptime calculation fails.

    # ------------ Monitor::GetWeatherData --------------------------------------
    def GetWeatherData(self, ForUI=False, JSONNum=False):
        """
        Retrieves weather data using the `MyWeather` instance.

        If `self.MyWeather` (the weather fetching object) is not initialized
        (e.g., weather is disabled or not configured), this method returns None.
        Otherwise, it calls the `GetWeather` method of the `MyWeather` object,
        passing along flags for UI formatting and numeric JSON output.

        Args:
            ForUI (bool, optional): Passed to `MyWeather.GetWeather`. If True,
                                    the weather data may be formatted or structured
                                    specifically for display in a user interface.
                                    Defaults to False.
            JSONNum (bool, optional): Passed to `MyWeather.GetWeather`. If True,
                                      numeric weather values might be returned
                                      without units or in a specific numeric format
                                      suitable for JSON processing where numbers
                                      are preferred over strings with units.
                                      Defaults to False.

        Returns:
            dict or None: A dictionary containing weather data if successfully
                          retrieved and if the weather module is active. The
                          structure of this dictionary is determined by `MyWeather.GetWeather`.
                          Returns None if `self.MyWeather` is not initialized or
                          if `GetWeather` returns no data.
        """
        # Check if the MyWeather object has been initialized.
        if self.MyWeather is None:
            self.log.debug("GetWeatherData called but MyWeather object is not initialized (weather likely disabled or not configured).")
            return None # Return None if weather fetching is not set up.

        # Call the GetWeather method of the MyWeather instance.
        # Pass through parameters that might affect formatting or content.
        ReturnData = self.MyWeather.GetWeather(
            minimum=self.WeatherMinimum, # Use the instance's setting for minimal data.
            ForUI=ForUI,
            JSONNum=JSONNum
        )

        # Check if the returned data is empty (e.g., an empty dict or list).
        if not ReturnData: # Handles None, empty list, empty dict.
            self.log.debug("MyWeather.GetWeather returned no data.")
            return None
        return ReturnData # Return the weather data.

    # ------------ Monitor::GetUserDefinedData ----------------------------------
    # this assumes one json object, the file can be formatted (i.e. on multiple
    # lines) or can be on a single line
    def GetUserDefinedData(self, JSONNum=False):
        """
        Reads and parses user-defined data from `userdefined.json`.

        This method attempts to load data from a JSON file named `userdefined.json`,
        which is expected to be located in `self.UserDefinedDataPath` (configurable,
        defaults to genmon's script directory).

        The `userdefined.json` file allows users to provide custom key-value pairs
        that can be displayed in the genmon interface or used by external extensions.
        The data is loaded into an `OrderedDict` to preserve the order of items
        as defined in the JSON file.

        Args:
            JSONNum (bool, optional): This parameter is present but not currently
                                      used in the logic of this method. It might
                                      be intended for future use where numeric
                                      values from the JSON could be specially
                                      processed. Defaults to False.

        Returns:
            collections.OrderedDict or None: An OrderedDict containing the data
                                             from `userdefined.json` if the file
                                             exists, is not empty, and is valid JSON.
                                             Returns None if the file does not exist,
                                             is empty, or if a JSON parsing error
                                             or any other exception occurs.
        """
        try:
            # Construct the full path to the userdefined.json file.
            FileName = os.path.join(self.UserDefinedDataPath, "userdefined.json")

            # Check if the file exists.
            if not os.path.isfile(FileName):
                self.log.debug(f"GetUserDefinedData: File not found at '{FileName}'.")
                return None # File does not exist.
            # Check if the file is empty (0 bytes).
            if os.path.getsize(FileName) == 0:
                self.log.debug(f"GetUserDefinedData: File '{FileName}' is empty.")
                return None # File is empty.

            # Open and load the JSON data from the file.
            # `object_pairs_hook=collections.OrderedDict` ensures that the order
            # of items from the JSON file is preserved in the returned dictionary.
            with open(FileName) as f:
                data = json.load(f, object_pairs_hook=collections.OrderedDict)
            self.log.debug(f"Successfully loaded data from '{FileName}'.")
            return data # Return the loaded data.
        except json.JSONDecodeError as jde:
            self.LogErrorLine(f"Error in GetUserDefinedData: Failed to decode JSON from '{FileName}': {str(jde)}")
            return None # JSON parsing error.
        except Exception as e1: # Catch any other errors (e.g., file permission issues).
            self.LogErrorLine(f"Error in GetUserDefinedData while processing '{FileName}': {str(e1)}")
            return None # Other error.

    # ------------ Monitor::DisplayWeather --------------------------------------
    def DisplayWeather(self, DictOut=False):
        """
        Retrieves weather data and formats it for display or dictionary output.

        This method calls `self.GetWeatherData()` to fetch the current weather
        information. If successful, it wraps this data under a "Weather" key
        in an `OrderedDict`.

        If `DictOut` is False (default), it then processes this OrderedDict
        through `self.printToString(self.ProcessDispatch(...))` to generate a
        formatted string suitable for text-based output (e.g., email, console).
        If `DictOut` is True, it returns the OrderedDict directly.

        Args:
            DictOut (bool, optional): If True, the method returns the weather data
                                      as an OrderedDict. If False (default), it
                                      returns a formatted string.

        Returns:
            str or collections.OrderedDict or None:
                - If `DictOut` is False: A formatted string of weather data, or
                  an empty string if no data is available or an error occurs.
                - If `DictOut` is True: An OrderedDict containing the weather data
                  under the key "Weather", or an empty OrderedDict if no data.
                - Returns the OrderedDict (even if empty) on exception if DictOut is True,
                  or an empty string if DictOut is False and an exception occurs.
        """
        WeatherDataContainer = collections.OrderedDict() # Use OrderedDict to maintain structure.

        try:
            # Get the raw weather data.
            RawReturnData = self.GetWeatherData() # Fetches data, possibly None.

            # If weather data was successfully retrieved and is not empty.
            if RawReturnData is not None and len(RawReturnData) > 0:
                WeatherDataContainer["Weather"] = RawReturnData # Nest it under "Weather" key.

            # If text output is required, format the dictionary into a string.
            if not DictOut:
                # ProcessDispatch and printToString are used for text formatting.
                # If WeatherDataContainer is empty, this should result in an empty or minimal string.
                return self.printToString(self.ProcessDispatch(WeatherDataContainer, ""))
        except Exception as e1:
            self.LogErrorLine(f"Error in DisplayWeather: {str(e1)}")
            # If an error occurs and text output was requested, return an empty string.
            if not DictOut:
                return ""
            # If DictOut was true, WeatherDataContainer (possibly empty) is returned by the finally block or after try.

        # Return the OrderedDict if DictOut is True, or if an error occurred and DictOut was True.
        return WeatherDataContainer


    # ------------ Monitor::DisplayMonitor --------------------------------------
    def DisplayMonitor(self, DictOut=False, JSONNum=False):
        """
        Collects and formats various monitoring statistics about genmon itself,
        the generator controller, platform, and weather.

        This method aggregates data from several sources:
        -   Genmon's own health and runtime statistics (`GetSystemHealth`, `GetProgramRunTime`).
        -   Controller communication statistics (`Controller.GetCommStatus`).
        -   Generator controller type (`Controller.GetController`).
        -   Power log file details if supported (`Controller.GetPowerLogFileDetails`).
        -   Current genmon version and update availability.
        -   Platform (OS) statistics (`GetPlatformStats`), if not disabled.
        -   Weather data (`GetWeatherData`), if enabled.
        -   User-defined data from `userdefined.json` (`GetUserDefinedData`).

        The collected information is structured in an `OrderedDict`.
        If `DictOut` is False (default), this OrderedDict is formatted into a
        string using `self.printToString(self.ProcessDispatch(...))`.
        If `DictOut` is True, the OrderedDict is returned directly.
        The `JSONNum` flag is passed to `GetPlatformStats` and might influence
        how numeric values are formatted if the output is intended for JSON.

        Args:
            DictOut (bool, optional): If True, returns the data as an OrderedDict.
                                      If False (default), returns a formatted string.
            JSONNum (bool, optional): Passed to `GetPlatformStats`. If True,
                                      numeric values might be formatted for JSON.
                                      Defaults to False.

        Returns:
            str or collections.OrderedDict:
                - If `DictOut` is False: A formatted string of monitoring data, or
                  an empty string if an error occurs during formatting.
                - If `DictOut` is True: An OrderedDict containing the monitoring data.
                  Returns an empty OrderedDict if a major error occurs early, or
                  a partially filled one if errors occur during data collection.
        """
        MonitorRootDict = collections.OrderedDict() # Root dictionary for all monitor data.
        try:
            MonitorDataList = [] # List to hold various sections of monitor data.
            MonitorRootDict["Monitor"] = MonitorDataList # Main key "Monitor" holds a list of sections.

            # Section 1: Generator Monitor Stats
            GenMonStatsList = []
            MonitorDataList.append({"Generator Monitor Stats": GenMonStatsList}) # Add as a dict with one key.
            GenMonStatsList.append({"Monitor Health": self.GetSystemHealth()})
            GenMonStatsList.append({"Controller": self.Controller.GetController(Actual=False)}) # Get configured controller type.
            GenMonStatsList.append({"Run time": self.GetProgramRunTime()})
            if self.Controller.PowerMeterIsSupported(): # If the controller supports power metering.
                GenMonStatsList.append(
                    {"Power log file size": self.Controller.GetPowerLogFileDetails()}
                )
            GenMonStatsList.append({"Generator Monitor Version": ProgramDefaults.GENMON_VERSION})
            GenMonStatsList.append({"Update Available": "Yes" if self.UpdateAvailable else "No"})

            # Section 2: Communication Stats from the Controller
            MonitorDataList.append({"Communication Stats": self.Controller.GetCommStatus()})

            # Section 3: Platform (OS) Stats, if not disabled
            if not self.bDisablePlatformStats:
                PlatformStats = self.GetPlatformStats(JSONNum=JSONNum) # Pass JSONNum.
                if PlatformStats is not None: # Ensure GetPlatformStats returned something.
                    MonitorDataList.append({"Platform Stats": PlatformStats})

            # Section 4: Weather Data, if available
            WeatherData = self.GetWeatherData() # Standard weather data format.
            if WeatherData is not None and len(WeatherData) > 0:
                MonitorDataList.append({"Weather": WeatherData})

            # Section 5: User-Defined Data, if available
            UserData = self.GetUserDefinedData() # JSONNum is not used by GetUserDefinedData.
            if UserData is not None and len(UserData) > 0:
                try:
                    MonitorDataList.append({"External Data": UserData})
                except Exception as e1: # Should not happen if UserData is already a dict.
                    self.LogErrorLine(f"Error in DisplayMonitor while appending user data: {str(e1)}")

            # If text output is required, format the entire MonitorRootDict.
            if not DictOut:
                return self.printToString(self.ProcessDispatch(MonitorRootDict, ""))
        except Exception as e1:
            self.LogErrorLine(f"Error in DisplayMonitor while collecting data: {str(e1)}")
            if not DictOut: # If error and text output, return empty string.
                return ""

        # Return the OrderedDict if DictOut is True or if an error occurred during string formatting.
        return MonitorRootDict


    # ------------ Monitor::GetStartInfo-----------------------------------------
    def GetStartInfo(self, NoTile=False):
        """
        Collects basic startup information about genmon and the system.

        This method gathers key details that are useful for understanding the
        environment in which genmon is running, including:
        -   Genmon version (`ProgramDefaults.GENMON_VERSION`).
        -   Site name (`self.SiteName`).
        -   Installation timestamp (`self.InstallTime`).
        -   Python version (`sys.version_info` and `platform.python_version()`).
        -   Platform (OS) type (`sys.platform`).
        -   OS bit depth (e.g., 32-bit, 64-bit) via `MyPlatform`.
        -   Current timezone name (`time.tzname`).
        -   Startup information from the generator controller module
            (`self.Controller.GetStartInfo`).

        The information is collected into an `OrderedDict`.

        Args:
            NoTile (bool, optional): Passed to `self.Controller.GetStartInfo()`.
                                     If True, the controller might return data
                                     in a more compact or non-tiled format.
                                     Defaults to False.

        Returns:
            collections.OrderedDict: An OrderedDict containing the startup information.
        """
        StartInfo = collections.OrderedDict() # Use OrderedDict to maintain key order.

        # Basic genmon and system info.
        StartInfo["version"] = ProgramDefaults.GENMON_VERSION
        StartInfo["sitename"] = self.SiteName
        StartInfo["install"] = self.InstallTime # Installation timestamp from genmon.conf.
        StartInfo["python_sys"] = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        StartInfo["platform_os"] = str(sys.platform)

        # More detailed Python and OS info using 'platform' module.
        try:
            import platform # Standard library module.
            StartInfo["python_platform"] = str(platform.python_version()) # More precise Python version.

            # Get OS bit depth (32/64-bit) using MyPlatform helper class.
            PlatformHelper = MyPlatform(log=self.log, usemetric=True, debug=self.debug) # usemetric/debug likely not relevant here.
            StartInfo["os_bits"] = PlatformHelper.PlatformBitDepth()
        except Exception as e1:
            self.LogErrorLine(f"Error in GetStartInfo while getting platform details: {str(e1)}")
            # Continue, as these are supplementary details.

        # Get current timezone information.
        try:
            import time # Standard library module.
            # time.tzname is a tuple: (standard time zone name, daylight saving time zone name).
            # self.is_dst() determines if DST is currently active.
            StartInfo["timezone"] = time.tzname[1] if self.is_dst() else time.tzname[0]
        except Exception as e_tz:
            self.LogErrorLine(f"Error in GetStartInfo while getting timezone: {str(e_tz)}")
            StartInfo["timezone"] = "Unknown"

        # Merge with startup information from the specific generator controller module.
        # The controller provides details about its own initialization and hardware.
        ControllerStartInfo = self.Controller.GetStartInfo(NoTile=NoTile) # Pass NoTile flag.
        StartInfo = self.MergeDicts(StartInfo, ControllerStartInfo) # Merge controller info into main dict.

        return StartInfo

    # ------------ Monitor::GetStatusForGUI -------------------------------------
    def GetStatusForGUI(self):
        """
        Aggregates various status information intended for use by a GUI client
        (e.g., the web interface).

        This method collects a wide range of data points:
        -   Genmon system health (`GetSystemHealth`).
        -   Indication if unsent feedback logs exist.
        -   Platform (OS) statistics (`GetPlatformStats`), if not disabled.
        -   Weather data (`GetWeatherData`), formatted for UI.
        -   Current monitor time.
        -   Generator engine run hours (`Controller.GetRunHours`).
        -   Controller's date format preference (`Controller.bAlternateDateFormat`).
        -   Current genmon version.
        -   Detailed status information from the generator controller module
            itself (`Controller.GetStatusForGUI`).

        All collected data is merged into a single dictionary.

        Returns:
            dict: A dictionary containing the aggregated status information.
                  The structure depends on the data returned by the various
                  helper methods and the controller's `GetStatusForGUI` method.
        """
        Status = {} # Initialize an empty dictionary to hold status data.

        # Basic genmon health and feedback status.
        Status["SystemHealth"] = self.GetSystemHealth()
        Status["UnsentFeedback"] = str(os.path.isfile(self.FeedbackLogFile)) # "True" or "False" as a string.

        # Platform (OS) statistics, if enabled.
        if not self.bDisablePlatformStats:
            PlatformStats = self.GetPlatformStats(usemetric=True) # Get stats, potentially with metric units.
            if PlatformStats is not None and len(PlatformStats) > 0:
                Status["PlatformStats"] = PlatformStats

        # Weather data, formatted for UI.
        WeatherData = self.GetWeatherData(ForUI=True) # ForUI=True might affect formatting.
        if WeatherData is not None and len(WeatherData) > 0:
            Status["Weather"] = WeatherData

        # Current time on the monitor system.
        Status["MonitorTime"] = datetime.datetime.now().strftime("%m/%d/%Y %H:%M") # Formatted time string.

        # Generator-specific information from the controller.
        Status["RunHours"] = self.Controller.GetRunHours() # Engine run hours.
        Status["AltDateformat"] = self.Controller.bAlternateDateFormat # Controller's date format preference.
        Status["version"] = ProgramDefaults.GENMON_VERSION # Current genmon software version.

        # Merge all the above with the detailed status from the controller module.
        # The controller's GetStatusForGUI() provides the bulk of generator-specific status.
        ReturnDict = self.MergeDicts(Status, self.Controller.GetStatusForGUI())

        return ReturnDict

    # -------------Monitor::GetSystemHealth--------------------------------------
    #   returns the health of the monitor program
    def GetSystemHealth(self):
        """
        Assesses and returns a string indicating the overall health of the genmon system.

        It checks several conditions:
        -   If the controller is still initializing (`self.Controller.InitComplete`).
        -   If all essential background threads are alive (`self.AreThreadsAlive`).
        -   If communication with the generator controller is active (`self.CommunicationsActive`).
        -   If the main log file (`genmon.log`) is reporting an unusual number of
            errors or growing too quickly (`self.LogFileIsOK`).

        If all checks pass, it returns "OK". Otherwise, it concatenates messages
        describing any issues found into a single status string.

        Returns:
            str: "OK" if all checks pass. Otherwise, a string detailing the
                 health issues (e.g., "System Initializing. Threads are dead. ").
        """
        outstr = "" # Initialize an empty string to accumulate health messages.

        # Check if the generator controller module has completed its initialization.
        if not self.Controller.InitComplete:
            outstr += "System Initializing. " # Add if controller is not ready.

        # Check if all critical background threads are running.
        if not self.AreThreadsAlive(): # self.AreThreadsAlive() is inherited from MySupport.
            outstr += "Critical Threads are dead. " # Add if any essential thread has stopped.

        # Check if communication with the generator controller is active.
        # This flag is updated by ComWatchDog based on data from the controller.
        if not self.CommunicationsActive:
            outstr += "Not receiving data from controller. " # Add if no data is being received.

        # Check if the main log file (genmon.log) seems healthy (not growing excessively, no excessive errors).
        if not self.LogFileIsOK():
            outstr += "Log file is reporting errors or growing too fast." # Add if log file issues are detected.

        # If outstr is still empty, all checks passed, so system is "OK".
        if len(outstr) == 0:
            outstr = "OK"

        return outstr.strip() # Return the health status string (strip trailing space if any).

    # ----------  Monitor::StartTimeThread---------------------------------------
    def StartTimeThread(self):
        """
        Initiates setting the generator's time and date in a separate thread.

        This method creates and starts a new `MyThread` instance that will execute
        `self.Controller.SetGeneratorTimeDate()`. Running this in a separate
        thread prevents the main flow (especially if called from an email command
        processor) from blocking while genmon communicates with the generator
        to set its time.

        Returns:
            str: A confirmation message "Time Set: Command Sent\n". This indicates
                 that the command to set the time has been dispatched, not that
                 it has necessarily completed successfully.
        """
        # Create a new thread that will call the SetGeneratorTimeDate method of the controller.
        # This allows the time setting operation to occur asynchronously.
        MyThread(self.Controller.SetGeneratorTimeDate, Name="SetTimeThread")
        self.log.info("Started SetTimeThread to synchronize generator time with system time.")
        return "Time Set: Command Sent\n" # Confirmation that the command was initiated.

    # ----------  Monitor::TimeSyncThread----------------------------------------
    def TimeSyncThread(self):
        """
        Background thread to manage periodic time synchronization and Daylight
        Savings Time (DST) adjustments for the generator's clock.

        This thread runs continuously and performs two main functions if enabled
        via `genmon.conf` settings (`self.bSyncDST`, `self.bSyncTime`):

        1.  **DST Change Synchronization (`self.bSyncDST`):**
            -   It monitors for changes in the system's DST status by comparing
                the current `self.is_dst()` result with a stored state (`self.bDST`).
            -   If a DST change is detected:
                -   Updates `self.bDST`.
                -   Resets communication statistics in the controller (as time jumps
                    can affect these).
                -   Calls `self.StartTimeThread()` to initiate setting the new
                    time on the generator.
                -   Sends a notification email about the time update.

        2.  **Periodic Time Synchronization (`self.bSyncTime`):**
            -   If enabled, it periodically calls `self.StartTimeThread()` to
                resynchronize the generator's clock with the system clock.
                This ensures the generator's time doesn't drift significantly.

        The thread waits for the controller to complete its initialization before
        starting its main loop. If only DST sync is enabled but not periodic sync,
        it performs an initial time set once the controller is ready.
        The main loop typically sleeps for 1 hour between checks.
        """
        self.log.info("TimeSyncThread started.")
        # Set initial DST state based on current system DST.
        self.bDST = self.is_dst()
        self.log.info(f"Initial DST state: {self.bDST}")

        # Initial short sleep to allow other components to initialize.
        time.sleep(0.25)

        # Wait for the generator controller to complete its initialization.
        init_wait_counter = 0
        while True:
            if self.WaitForExit("TimeSyncThread", 1):  # Check for program shutdown every second.
                self.log.info("TimeSyncThread exiting during controller init wait.")
                return
            if self.Controller.InitComplete:
                self.log.info("TimeSyncThread: Controller initialization complete.")
                break
            init_wait_counter +=1
            if init_wait_counter > 60: # Timeout if controller doesn't init in ~1 minute.
                self.log.error("TimeSyncThread: Controller did not complete initialization after 60s. Thread might not function correctly.")
                # Depending on requirements, could exit or proceed with caution.
                # For now, let it proceed; time sync might still work if controller eventually inits.
                break


        # If periodic time sync (`bSyncTime`) is NOT enabled (but DST sync might be),
        # perform an initial time set once the controller is ready.
        if not self.bSyncTime and (self.bSyncDST or self.Controller.InitComplete): # Ensure controller is ready for initial sync
            self.log.info("TimeSyncThread: Performing initial time set as periodic sync (bSyncTime) is disabled.")
            self.StartTimeThread()

        # Main loop for the thread.
        while True:
            # If DST synchronization is enabled.
            if self.bSyncDST:
                current_dst_status = self.is_dst()
                if self.bDST != current_dst_status:  # Check if DST status has changed.
                    self.log.info(f"Daylight Savings Time change detected. Old DST: {self.bDST}, New DST: {current_dst_status}.")
                    self.bDST = current_dst_status  # Update stored DST state.

                    # Time has changed, so communication statistics might be skewed. Reset them.
                    self.Controller.ResetCommStats()
                    self.log.info("Reset communication stats due to DST change.")

                    # Initiate setting the new time on the generator.
                    self.StartTimeThread()

                    # Send a notification email about the time update.
                    self.MessagePipe.SendMessage(
                        "Generator Time Update at " + self.SiteName,
                        "Generator time updated due to Daylight Savings Time change.",
                        msgtype="info",
                    )
                    self.LogError("DST change detected and generator time sync initiated.") # LogError for higher visibility.

            # If periodic time synchronization (`bSyncTime`) is enabled.
            if self.bSyncTime:
                self.log.info("TimeSyncThread: Performing periodic generator time synchronization.")
                self.StartTimeThread() # Initiate setting the time on the generator.

            # Wait for 1 hour (3600 seconds) or until program shutdown is requested.
            if self.WaitForExit("TimeSyncThread", 60 * 60):
                self.log.info("TimeSyncThread exiting.")
                return

    # ----------  Monitor::is_dst------------------------------------------------
    def is_dst(self):
        """
        Determines whether Daylight Savings Time (DST) is currently in effect
        based on the system's local time settings.

        It uses `time.localtime()` to get the current local time structure,
        which includes a `tm_isdst` attribute.
        -   `tm_isdst > 0`: DST is in effect.
        -   `tm_isdst == 0`: DST is not in effect.
        -   `tm_isdst < 0`: Information not available.

        Returns:
            bool: True if DST is currently in effect (tm_isdst > 0).
                  False if DST is not in effect (tm_isdst == 0) or if
                  information is unavailable (tm_isdst < 0).
        """
        # Get the current local time tuple.
        t = time.localtime()
        # tm_isdst is non-zero if DST is in effect.
        # It's > 0 if DST is active, 0 if not, -1 if information unavailable.
        # We consider > 0 as DST active.
        isdst_active = t.tm_isdst > 0
        return isdst_active

    # ----------  Monitor::ComWatchDog-------------------------------------------
    # ----------  monitors receive data status to make sure we are still communicating
    def ComWatchDog(self):
        """
        Monitors the communication status with the generator controller and
        sends notifications if communication is lost or restored.

        This method runs in its own thread (`ComWatchDog` thread) and performs
        the following key functions:
        1.  **Initial Wait for Controller Initialization:**
            -   It first waits for the generator controller (`self.Controller`)
                to complete its initialization (`self.Controller.InitComplete`).
            -   There's a timeout for this initial wait (30 seconds). If the
                controller doesn't initialize within this time, a warning is
                logged, suggesting a possible communication failure (e.g., cabling issue).
        2.  **Calculate Watchdog Poll Time:**
            -   Determines `WatchDogPollTime`, which is the interval at which
                this watchdog checks communication status.
            -   The base poll time is different for TCP (8.0s) vs. serial (2.0s)
                Modbus connections.
            -   It adds the Modbus packet timeout (`ModBusPacketTimoutMS`) and
                any user-defined `AdditionalWatchdogTime` (from `genmon.conf`)
                to this base time, making the watchdog more lenient for slower
                or less reliable connections.
        3.  **Main Monitoring Loop:**
            -   Continuously checks if genmon is shutting down (`self.WaitForExit`).
            -   Periodically calls `self.CheckSoftwareUpdate()` to check for new
                genmon software versions.
            -   Calls `self.Controller.ComminicationsIsActive()` to get the current
                communication state from the controller module. This flag is typically
                set by the controller's own communication thread when data is
                successfully received.
            -   **Lost Communication Logic:**
                -   If `self.CommunicationsActive` is False, it checks how long
                  it has been since communication was last active (`LastActiveTime`).
                -   If this duration exceeds a threshold (1 minute + `AdditionalWatchdogTime`),
                  and a "communication lost" notification hasn't already been sent
                  (`NoticeSent` is False), it sends an email alert via `self.MessagePipe`
                  and sets `NoticeSent = True`.
            -   **Restored Communication Logic:**
                -   If `self.CommunicationsActive` is True, it updates `LastActiveTime`.
                -   If a "communication lost" notice had been previously sent
                  (`NoticeSent` was True), it means communication has just been
                  restored. It then sends a "communication restored" email alert
                  and resets `NoticeSent = False`.
        """
        self.CommunicationsActive = False # Initialize as False.
        time.sleep(0.25) # Brief initial pause.

        NoticeSent = False # Flag to track if a "communication lost" notice has been sent.
        LastActiveTime = datetime.datetime.now() # Timestamp of the last known active communication.

        # --- Explain the initial wait loop for self.Controller.InitComplete ---
        # This loop waits for the generator controller to signal that its initialization
        # process is complete (e.g., serial port opened, initial data read).
        # The ComWatchDog should not start its main monitoring duties until the
        # controller is ready to communicate.
        counter = 0 # Counter for the initialization timeout.
        while True:
            if self.WaitForExit("ComWatchDog", 1): # Check every 1 second if genmon is shutting down.
                return # Exit thread if program is stopping.
            if counter > 30: # Timeout after 30 seconds.
                self.LogError(
                    "WARNING: ComWatchDog: Controller initialization not complete after 30 seconds. "
                    "This might indicate a communication failure with the generator (e.g., incorrect serial port, cabling issue, controller off). "
                    "The communication watchdog might not function correctly."
                )
                break # Exit init wait loop, ComWatchDog might still try to run but likely report comms down.
            counter += 1
            if self.Controller.InitComplete: # Check flag set by the controller module.
                self.log.info("ComWatchDog: Controller initialization complete. Starting communication monitoring.")
                break # Exit init wait loop and proceed to main monitoring.

        # --- Clarify the calculation of WatchDogPollTime ---
        # `WatchDogPollTime` is the interval at which this watchdog thread will wake up
        # to check the communication status.
        # It's calculated based on the connection type and configured timeouts to avoid
        # false positives for communication loss during normal delays.
        if self.Controller.ModBus.UseTCP: # If using Modbus TCP (Ethernet/WiFi).
            WatchDogPollTime = 8.0 # Base poll time for TCP is longer due to network latencies.
        else: # If using serial Modbus.
            WatchDogPollTime = 2.0 # Base poll time for serial is shorter.

        try:
            # Add the configured Modbus packet timeout (converted from ms to seconds)
            # to the poll time. This ensures the watchdog waits at least as long as
            # a single Modbus transaction might take.
            WatchDogPollTime += float(
                self.Controller.ModBus.ModBusPacketTimoutMS / 1000
            )
        except Exception as e1:
            self.LogErrorLine(f"Error in ComWatchDog calculating poll time from ModBusPacketTimoutMS: {str(e1)}. Using base poll time.")

        # Add any user-defined additional watchdog time from `genmon.conf` (`watchdog_addition`).
        # This allows users to further extend the poll time for very slow or unreliable connections.
        WatchDogPollTime += self.AdditionalWatchdogTime
        self.log.info(f"ComWatchDog poll time set to: {WatchDogPollTime:.2f} seconds.")

        # --- Main Monitoring Loop ---
        while True:
            try:
                # Periodically check for software updates for genmon.
                self.CheckSoftwareUpdate()

                # Get the current communication status from the controller module.
                # The controller module is responsible for setting this flag based on its data reception.
                self.CommunicationsActive = self.Controller.ComminicationsIsActive()

                # --- Detail the logic for checking self.CommunicationsActive and sending notifications ---
                if self.CommunicationsActive:
                    # If communication is active:
                    LastActiveTime = datetime.datetime.now() # Update the timestamp of the last known active communication.
                    if NoticeSent: # If a "communication lost" notice was previously sent...
                        NoticeSent = False # Reset the flag as communication is now restored.
                        # Send a "communication restored" notification.
                        msgbody = (
                            "Generator Monitor communications with the generator controller has been RESTORED at site: "
                            + self.SiteName
                        )
                        msgbody += "\n\nCurrent Monitor Status:\n" + self.DisplayMonitor() # Include current monitor status.
                        self.MessagePipe.SendMessage(
                            "Generator Monitor Communication RESTORED at "
                            + self.SiteName,
                            msgbody,
                            msgtype="error", # Often uses "error" type for visibility, even for good news.
                        )
                        self.log.info("ComWatchDog: Communication with controller has been restored.")
                else:
                    # If communication is NOT active:
                    # Calculate how long (in minutes) it has been since communication was last active.
                    # The threshold is 1 minute plus any additional configured watchdog time.
                    minutes_since_last_active = self.GetDeltaTimeMinutes(
                        datetime.datetime.now() - LastActiveTime
                    )
                    threshold_minutes = 1 + (self.AdditionalWatchdogTime / 60.0) # Convert additional seconds to minutes for comparison

                    if minutes_since_last_active > threshold_minutes:
                        if not NoticeSent: # If a "communication lost" notice has NOT been sent yet...
                            NoticeSent = True # Set the flag to prevent repeated notices.
                            # Send a "communication lost" notification.
                            msgbody = (
                                "Generator Monitor is NOT COMMUNICATING with the generator controller at site: "
                                + self.SiteName
                                + f". No communication for approximately {minutes_since_last_active:.1f} minutes."
                            )
                            msgbody += "\n\nPlease check cabling, controller status, and genmon logs.\n"
                            msgbody += "\nCurrent Monitor Status (may be stale):\n" + self.DisplayMonitor()
                            self.MessagePipe.SendMessage(
                                "Generator Monitor Communication WARNING at "
                                + self.SiteName,
                                msgbody,
                                msgtype="error", # Use "error" type for alerts.
                            )
                            self.log.warning(f"ComWatchDog: Communication with controller lost for over {threshold_minutes:.1f} minutes. Notification sent.")
            except Exception as e1:
                self.LogErrorLine("Error in ComWatchDog main loop: " + str(e1))

            # Wait for WatchDogPollTime before the next check, or exit if genmon is stopping.
            if self.WaitForExit("ComWatchDog", WatchDogPollTime):
                return # Exit thread if program is stopping.

    # ---------- Monitor::CheckSoftwareUpdate------------------------------------
    def CheckSoftwareUpdate(self):
        """
        Periodically checks for software updates for genmon by fetching the
        `program_defaults.py` file from the master branch of the jgyates/genmon
        GitHub repository.

        This method performs the following steps:
        1.  **Update Check Enabled:** First, it checks if software update checks
            are enabled via `self.UpdateCheck` (read from `genmon.conf`). If not,
            it exits early.
        2.  **Time Since Last Check:** It checks if enough time has passed since
            the last update check (`self.LastSoftwareUpdateCheck`). The default
            interval is 1440 minutes (1 day). This prevents excessive checking.
        3.  **Fetch `program_defaults.py`:**
            -   It constructs the URL to the raw `program_defaults.py` file on GitHub.
            -   It uses `urllib.request.urlopen` (or `urllib2.urlopen` for Python 2)
                to fetch the content of this file. It reads only the first 4000
                characters to avoid downloading a potentially large file if the URL
                is incorrect or hijacked, and to find the version string quickly.
            -   The fetched data (bytes) is decoded to ASCII and then split into lines.
        4.  **Parse for Version:**
            -   It iterates through the lines of the fetched file, looking for a
                line that contains the string `GENMON_VERSION = "V`. This is the
                line defining the latest version in `program_defaults.py`.
            -   It uses a regular expression (`re.compile('"([^"]*)"')`) to extract
                the version string enclosed in double quotes (e.g., "V1.2.3").
        5.  **Compare Versions and Notify:**
            -   If the extracted version string from GitHub (`value`) is different
                from the currently running version (`ProgramDefaults.GENMON_VERSION`),
                it means an update is available.
            -   It constructs a notification title and message. The message includes
                the new version, current version, a link to the web UI (if `self.UserURL`
                is set), and a link to the changelog.
            -   It sends this notification as an email via `self.MessagePipe.SendMessage`
                using `msgtype="info"` and `onlyonce=True` (to prevent repeated
                notifications for the same update version until genmon is restarted
                or the version changes again).
            -   It sets `self.UpdateAvailable = True` and `self.UpdateVersion = value`
                to make this information available to other parts of genmon (e.g., web UI).
        6.  **Error Handling:** Catches exceptions during the HTTP request or parsing
            and logs them.

        This method is typically called periodically by another thread, such as `ComWatchDog`.
        """
        # --- Explain the condition for checking (time since last check) ---
        # First, check if software update checks are enabled in genmon.conf.
        if not self.UpdateCheck:
            return # Exit if update checks are disabled.

        try:
            # Check if at least 1440 minutes (1 day) have passed since the last software update check.
            # This prevents checking too frequently.
            if (
                self.GetDeltaTimeMinutes(
                    datetime.datetime.now() - self.LastSoftwareUpdateCheck # Time elapsed since last check.
                )
                > 1440 # 1440 minutes = 24 hours.
            ):
                self.LastSoftwareUpdateCheck = datetime.datetime.now() # Update the timestamp of the last check.

                # --- Detail the process of fetching and parsing program_defaults.py from GitHub ---
                self.log.info("Performing daily check for software updates from GitHub...")
                try:
                    # URL to the raw program_defaults.py file in the master branch of the genmon repository.
                    url = f"https://raw.githubusercontent.com/{self.UpdateCheckUser}/{self.UpdateCheckRepo}/{self.UpdateCheckBranch}/genmonlib/program_defaults.py"

                    # Use appropriate urllib version based on Python version.
                    if sys.version_info[0] < 3: # Python 2.x
                        from urllib2 import urlopen # Fall back to Python 2's urllib2.
                    else: # Python 3.x
                        from urllib.request import urlopen # Use Python 3's urllib.request.

                    # Fetch the content of the URL. Read only the first 4000 characters
                    # to limit data transfer and quickly find the version string.
                    response_bytes = urlopen(url).read(4000)
                    # Decode the fetched bytes to an ASCII string (program_defaults.py is expected to be ASCII).
                    # Errors in decoding will be caught by the outer exception handler.
                    file_content_str = response_bytes.decode("ascii")
                    # Split the content into a list of lines for easier parsing.
                    lines_from_file = file_content_str.split("\n")

                    # --- Explain the logic for comparing versions and sending update notifications ---
                    # Iterate through each line of the fetched file content.
                    for line in lines_from_file:
                        # Look for the line defining GENMON_VERSION (e.g., 'GENMON_VERSION = "V1.2.3"').
                        if 'GENMON_VERSION = "V' in line:
                            import re # Import regular expression module.
                            # Regular expression to extract the version string within double quotes.
                            # "([^"]*)" captures any characters inside double quotes.
                            quoted_version_regex = re.compile('"([^"]*)"')
                            # Find all occurrences of quoted strings on this line.
                            # Should typically be just one (the version string).
                            found_versions = quoted_version_regex.findall(line)

                            for github_version_str in found_versions: # Iterate through found version strings (usually one).
                                # Compare the version from GitHub with the currently running version.
                                if github_version_str != ProgramDefaults.GENMON_VERSION:
                                    # If versions differ, an update is available.
                                    self.log.info(f"Software update detected. Current version: {ProgramDefaults.GENMON_VERSION}, Available version: {github_version_str}")
                                    # Construct notification title and message.
                                    title = (
                                        self.ProgramName
                                        + " Software Update "
                                        + github_version_str # New version.
                                        + " is available for site "
                                        + self.SiteName
                                    )
                                    msgbody = (
                                        "\nA software update is available for the "
                                        + self.ProgramName
                                        + ". The new version ("
                                        + github_version_str # New version.
                                        + ") can be updated on the About page of the web interface. "
                                        + "The current version installed is "
                                        + ProgramDefaults.GENMON_VERSION # Current version.
                                        + ". You can disable this email from being sent on the Settings page of the web UI."
                                    )
                                    # If a user-defined URL for the web interface is configured, add it to the message.
                                    if len(self.UserURL):
                                        msgbody += (
                                            "\n\nWeb Interface URL: " + self.UserURL
                                        )
                                    # Add a link to the changelog.
                                    msgbody += "\n\nChange Log: https://raw.githubusercontent.com/jgyates/genmon/master/changelog.md"

                                    # Send the update notification email via MessagePipe.
                                    # `onlyonce=True` ensures this specific version update is notified only once
                                    # (MessagePipe tracks messages sent with this flag).
                                    self.MessagePipe.SendMessage(
                                        title, msgbody, msgtype="info", onlyonce=True
                                    )

                                    # Set flags to indicate an update is available.
                                    self.UpdateAvailable = True
                                    self.UpdateVersion = github_version_str
                                    # Once the version line is found and processed, no need to check further lines.
                                    break # Exit the inner loop (found_versions).
                            # Once the GENMON_VERSION line is processed, exit the outer loop (lines_from_file).
                            break
                except Exception as e1: # Handle errors during fetching, decoding, or parsing.
                    self.LogErrorLine("Error checking for software update (e.g., network issue, GitHub access problem): " + str(e1))
        except Exception as e1: # Handle errors in the time checking logic itself.
            self.LogErrorLine("Error in CheckSoftwareUpdate (outer try block): " + str(e1))

    # ---------- Monitor::LogFileIsOK--------------------------------------------
    def LogFileIsOK(self):
        """
        Checks the health of the main genmon log file (`genmon.log`).

        This method monitors the size of `genmon.log`. It's designed to detect
        if the log file is growing excessively fast, which might indicate
        repetitive errors or other issues causing spammy logging.

        Logic:
        -   If the controller is not yet initialized, it assumes everything is fine.
        -   It gets the current size of `genmon.log`.
        -   If the current size is less than or equal to the last recorded size
            (`self.LastLogFileSize`), it means the log has not grown or has been
            rotated. In this case, it resets an error counter and returns True.
        -   If the log file has grown, it calculates the difference in size.
        -   If the growth (`LogFileSizeDiff`) is 100 bytes or more (a heuristic
            threshold for "significant" growth between checks), it increments
            `self.NumberOfLogSizeErrors`.
        -   If `self.NumberOfLogSizeErrors` exceeds 3, it means the log has shown
            significant growth multiple times consecutively, and the method
            returns False (log file is not OK).
        -   If the growth is less than 100 bytes, `self.NumberOfLogSizeErrors` is reset.

        This provides a basic mechanism to detect runaway logging.

        Returns:
            bool: True if the log file seems healthy (not growing excessively fast
                  or has been rotated). False if it has grown significantly for
                  several consecutive checks. Returns True if an exception occurs
                  during the check (fail-safe).
        """
        try:
            # If the controller isn't fully initialized, it's too early to assess log health reliably.
            if not self.Controller.InitComplete:
                return True # Assume OK during initialization.

            # Construct the full path to the main genmon log file.
            LogFile = os.path.join(self.LogLocation, "genmon.log")
            if not os.path.isfile(LogFile): # If log file doesn't exist, can't check it.
                self.log.warning("LogFileIsOK: genmon.log not found. Cannot check its status.")
                return True # Assume OK if no log file to check.

            # Get the current size of the log file.
            LogFileSize = os.path.getsize(LogFile)

            # If log size hasn't increased (or shrunk, e.g., due to rotation), it's considered OK.
            if LogFileSize <= self.LastLogFileSize:
                self.LastLogFileSize = LogFileSize # Update last known size.
                self.NumberOfLogSizeErrors = 0     # Reset error counter.
                return True # Log is OK.

            # Calculate the difference in size since the last check.
            LogFileSizeDiff = LogFileSize - self.LastLogFileSize
            self.LastLogFileSize = LogFileSize # Update last known size for the next check.

            # If the log file grew by 100 bytes or more (heuristic for significant growth).
            if LogFileSizeDiff >= 100:
                self.NumberOfLogSizeErrors += 1 # Increment consecutive error count.
                # If this has happened more than 3 times consecutively, flag the log as not OK.
                if self.NumberOfLogSizeErrors > 3:
                    self.log.warning(f"LogFileIsOK: genmon.log has grown significantly ({LogFileSizeDiff} bytes) for {self.NumberOfLogSizeErrors} consecutive checks. May indicate excessive logging.")
                    return False # Log file is potentially problematic.
            else:
                # If growth was less than 100 bytes, reset the consecutive error counter.
                self.NumberOfLogSizeErrors = 0

            return True # Log file is OK for this check.
        except Exception as e1: # Catch any errors during file operations.
            self.LogErrorLine(f"Error in LogFileIsOK: {str(e1)}")
            return True # Fail-safe: assume log is OK if an error occurs during the check itself.

    # ----------  Monitor::SocketWorkThread-------------------------------------
    #  This thread spawns for each connection established by a client
    #  in InterfaceServerThread
    def SocketWorkThread(self, conn):
        """
        Handles communication with a single connected client socket.

        This method runs in its own thread, created by `InterfaceServerThread`
        for each new client connection. It's responsible for:
        1.  **Initial Status Send:** Upon connection, it immediately sends a
            one-line status message to the client. This message includes:
            -   "WARNING: System Initializing" if the controller is not yet ready.
            -   Otherwise, it combines system health ("OK", "WARNING: ...",
                "CRITICAL: ...") with a one-line status from the controller
                (`self.Controller.GetOneLineStatus()`).
        2.  **Command Processing Loop:**
            -   It enters a loop to continuously receive data (commands) from
                the client socket (`conn.recv()`).
            -   If data is received:
                -   It calls `self.ProcessCommand(data, fromsocket=True)` to
                    process the command.
                -   The response from `ProcessCommand` (which ends with
                    "EndOfMessage") is sent back to the client.
            -   If `conn.recv()` returns empty data, it means the client has
                closed the connection, so the loop breaks.
        3.  **Error and Timeout Handling:**
            -   Handles `socket.timeout` during `conn.recv()`, allowing the
                loop to continue unless `self.IsStopping` is True.
            -   Catches `socket.error` (e.g., connection reset) to break the loop.
        4.  **Cleanup:** When the loop terminates (client disconnects or error),
            it removes the connection from `self.ConnectionList` and closes
            the client socket `conn`.

        Args:
            conn (socket.socket): The connected client socket object.
        """
        try:
            # --- Initial Status Send ---
            status_string_to_send = ""
            if self.Controller is None or not self.Controller.InitComplete: # Check if controller is ready.
                status_string_to_send = "WARNING: System Initializing"
            else:
                # Build status string based on alarm state and system health.
                if self.Controller.SystemInAlarm():
                    status_string_to_send += "CRITICAL: System in alarm! "

                HealthStr = self.GetSystemHealth() # Get overall system health.
                if HealthStr != "OK":
                    status_string_to_send += "WARNING: " + HealthStr # Append health warnings if any.

                if not status_string_to_send: # If no critical/warning messages, start with "OK".
                    status_string_to_send = "OK "

                # Append the controller's one-line status summary.
                status_string_to_send += ": " + self.Controller.GetOneLineStatus()

            conn.sendall(status_string_to_send.encode()) # Send initial status (UTF-8 encoded).

            # --- Command Processing Loop ---
            while True: # Loop indefinitely to receive commands.
                try:
                    # Receive data from the client (up to a large buffer size).
                    # Max size is set to handle potentially large JSON strings.
                    data = conn.recv(2098152)

                    if len(data): # If data was received.
                        if self.Controller is None or not self.Controller.InitComplete:
                            response_str = "Retry, System Initializing"
                        else:
                            # Process the received command. `fromsocket=True` indicates the source.
                            response_str = self.ProcessCommand(data, fromsocket=True)

                        # Send the response back to the client (UTF-8 encoded).
                        # ProcessCommand appends "EndOfMessage" to socket responses.
                        conn.sendall(response_str.encode("utf-8"))
                    else:
                        # If recv returns empty data, it means the client closed the connection.
                        self.log.info(f"SocketWorkThread: Client {conn.getpeername() if hasattr(conn, 'getpeername') else 'unknown'} closed connection.")
                        break # Exit the loop.
                except socket.timeout: # If conn.recv() times out (socket is non-blocking with timeout).
                    if self.IsStopping: # If genmon is shutting down, exit the loop.
                        self.log.info("SocketWorkThread: Exiting due to IsStopping flag during socket timeout.")
                        break
                    continue # Otherwise, continue waiting for data.
                except socket.error as msg: # Handle socket errors (e.g., connection reset).
                    self.log.error(f"SocketWorkThread: Socket error: {str(msg)}. Closing connection.")
                    # Attempt to clean up the connection from the list and close it.
                    try:
                        self.ConnectionList.remove(conn)
                        conn.close()
                    except: # Ignore errors during this cleanup.
                        pass
                    break # Exit the loop.
        except socket.error as msg: # Catch socket errors that might occur outside the loop (e.g., on initial sendall).
            self.LogError(f"Error in SocketWorkThread (outer try block): {str(msg)}")
            pass # Log and let finally block handle cleanup.
        finally:
            # --- Cleanup ---
            # Ensure the connection is removed from the list and closed, regardless of how the loop exited.
            try:
                if conn in self.ConnectionList: # Check if it's still in the list.
                    self.ConnectionList.remove(conn)
                conn.close() # Close the client socket.
                self.log.debug("SocketWorkThread: Cleaned up and closed client connection.")
            except: # Ignore any errors during final cleanup.
                pass
        # End of SocketWorkThread

    # ----------  interface for heartbeat server thread -------------------------
    def InterfaceServerThread(self):
        """
        Listens for incoming client connections on a server socket and spawns
        a `SocketWorkThread` for each accepted connection.

        This method runs in its own thread (`InterfaceServerThread`) and acts
        as the main server loop for genmon's command/status interface.

        It performs the following steps:
        1.  **Socket Creation and Binding:**
            -   Creates a TCP/IP socket (`socket.AF_INET`, `socket.SOCK_STREAM`).
            -   Sets the `SO_REUSEADDR` socket option to allow quick restarts
                of genmon without "address already in use" errors.
            -   Sets a short timeout (0.5s) on the server socket to make the
                `accept()` call non-blocking indefinitely, allowing the loop
                to periodically check `self.IsStopping`.
            -   Binds the socket to `self.ServerIPAddress` (often all interfaces)
                and `self.ServerSocketPort`.
            -   Puts the socket into listening mode (`listen(5)`).
        2.  **Accept Loop:**
            -   Enters a loop to continuously accept new client connections.
            -   `self.ServerSocket.accept()` waits for a connection. If a timeout
                occurs, and `self.IsStopping` is True, the loop breaks.
            -   When a client connects:
                -   Logs the connection (commented out in original).
                -   Sets a timeout on the new client socket `conn`.
                -   Adds `conn` to `self.ConnectionList` (mostly for tracking,
                    though cleanup might be handled by SocketWorkThread itself).
                -   Creates and starts a new `SocketWorkThread`, passing it the
                    `conn` object to handle communication with that specific client.
                    This thread is set as a daemon thread so it doesn't prevent
                    genmon from exiting.
        3.  **Error Handling:** Catches `socket.timeout` (to check `IsStopping`)
            and other exceptions during the accept loop, logging them and
            continuing or breaking as appropriate.
        4.  **Server Socket Cleanup:** When the loop terminates (due to
            `self.IsStopping`), it attempts to shut down and close all active
            client connections in `self.ConnectionList` and then closes the
            main server socket `self.ServerSocket`.
        """
        try:
            # Create an INET (IPv4), STREAMing (TCP) socket.
            self.ServerSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Allow reuse of the local address, preventing "Address already in use" on quick restarts.
            self.ServerSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Set a timeout on the server socket's blocking operations (like accept()).
            # This allows the loop to periodically check for the IsStopping flag.
            self.ServerSocket.settimeout(0.5) # 0.5 seconds timeout.

            # Bind the socket to the configured IP address and port.
            # self.ServerIPAddress defaults to "" (all interfaces).
            self.log.info(f"InterfaceServerThread: Binding server socket to {self.ServerIPAddress if self.ServerIPAddress else '0.0.0.0'}:{self.ServerSocketPort}")
            self.ServerSocket.bind((self.ServerIPAddress, self.ServerSocketPort))

            # Enable the server to accept connections; 5 is the typical backlog size.
            self.ServerSocket.listen(5)
            self.log.info("InterfaceServerThread: Server socket listening for connections.")
        except socket.error as se:
            self.LogError(f"CRITICAL: InterfaceServerThread failed to bind or listen on socket {self.ServerIPAddress}:{self.ServerSocketPort}: {se}. Command interface will be unavailable.")
            self.ServerSocket = None # Ensure ServerSocket is None so cleanup doesn't try to close an invalid socket.
            return # Exit the thread if socket setup fails.
        except Exception as e_setup:
            self.LogError(f"CRITICAL: Unexpected error setting up InterfaceServerThread socket: {e_setup}. Command interface will be unavailable.")
            self.ServerSocket = None
            return

        # Main loop to accept client connections.
        while True:
            try:
                # Wait for an incoming connection. accept() is blocking but respects the timeout.
                conn, addr = self.ServerSocket.accept()
                # Log the new connection (original code had this commented out).
                self.log.info(f"InterfaceServerThread: Accepted connection from {addr[0]}:{str(addr[1])}")

                conn.settimeout(0.5) # Set a timeout for operations on the client socket.
                self.ConnectionList.append(conn) # Add to list of active connections.

                # Create a new thread to handle this client connection.
                # Pass the SocketWorkThread method and the connection object `conn`.
                client_thread = threading.Thread(
                    target=self.SocketWorkThread, args=(conn,), name=f"SocketWorkThread-{addr[0]}"
                )
                client_thread.daemon = True # Daemonize so it doesn't block program exit.
                client_thread.start()   # Start the client handling thread.

            except socket.timeout: # Timeout occurred on self.ServerSocket.accept().
                if self.IsStopping: # If genmon is shutting down, exit the server loop.
                    self.log.info("InterfaceServerThread: IsStopping flag is set. Shutting down server thread.")
                    break
                continue # Otherwise, continue listening.
            except Exception as e1: # Handle other exceptions during accept() or thread creation.
                if self.IsStopping: # If shutting down, break.
                    self.log.info(f"InterfaceServerThread: Exiting due to IsStopping flag during exception: {str(e1)}")
                    break
                self.LogErrorLine(f"Exception in InterfaceServerThread accept loop: {str(e1)}")
                # Brief pause before retrying to prevent rapid looping on persistent errors.
                if self.WaitForExit("InterfaceServerThreadRecovery", 0.5):
                    break # Exit if shutdown requested during recovery pause.
                continue # Continue listening.

        # --- Server Socket Cleanup ---
        # This section is reached when the `while True` loop breaks (typically due to `self.IsStopping`).
        if self.ServerSocket is not None:
            self.log.info("InterfaceServerThread: Closing active client connections and server socket.")
            # Close all active client connections that might still be in ConnectionList.
            # Note: SocketWorkThread is primarily responsible for its own connection cleanup.
            # This is an additional safety net.
            active_connections_at_shutdown = list(self.ConnectionList) # Iterate over a copy.
            for client_conn in active_connections_at_shutdown:
                try:
                    client_conn.shutdown(socket.SHUT_RDWR) # Politely try to shut down read/write.
                    client_conn.close()
                    if client_conn in self.ConnectionList: # Ensure it's removed.
                         self.ConnectionList.remove(client_conn)
                except: # Ignore errors during this client connection cleanup.
                    pass

            # Close the main server socket.
            try:
                self.ServerSocket.close()
                self.log.info("InterfaceServerThread: Server socket closed.")
            except Exception as e_close_server:
                self.LogErrorLine(f"InterfaceServerThread: Error closing server socket: {e_close_server}")
            self.ServerSocket = None # Mark as closed.
        # End of InterfaceServerThread

    # ----------Monitor::SignalClose--------------------------------------------
    def SignalClose(self, signum, frame):
        """
        Signal handler for SIGTERM and SIGINT.

        This method is registered as the handler for termination signals.
        When genmon receives SIGTERM (e.g., from `systemctl stop genmon`) or
        SIGINT (e.g., Ctrl+C), this method is called.

        It initiates the graceful shutdown process by calling `self.Close()`
        and then exits the program with status code 1.

        Args:
            signum (int): The signal number received.
            frame (frame object): The current stack frame at the time of the signal.
        """
        self.log.warning(f"SignalClose: Received signal {signum}. Initiating shutdown...")
        self.Close() # Call the main shutdown method.
        sys.exit(1) # Exit program. Status 1 often indicates termination by signal.

    # ---------------------Monitor::Close----------------------------------------
    def Close(self):
        """
        Performs a graceful shutdown of the genmon application.

        This method is called when genmon is exiting, either due to a signal
        (SIGTERM, SIGINT) or potentially other shutdown commands. It's responsible
        for cleanly stopping all active components:
        1.  Sets `self.IsStopping = True` to signal all threads to terminate.
        2.  Closes the weather module (`self.MyWeather`), if active.
        3.  Kills specific threads like `TimeSyncThread` and `ComWatchDog`.
        4.  Closes the generator controller connection (`self.Controller.Close()`).
        5.  Closes the email module (`self.mail.Close()`).
        6.  Closes all active client socket connections from `self.ConnectionList`.
        7.  Shuts down and closes the main server socket (`self.ServerSocket`) and
            kills the `InterfaceServerThread`.
        8.  Closes inter-process communication pipes (`self.FeedbackPipe`, `self.MessagePipe`).
        9.  Iterates through all remaining threads in `self.Threads` and attempts
            to stop them if they are still alive.
        10. Logs a final shutdown message.
        11. Sets `self.ProgramComplete = True` and attempts `sys.exit(0)`.

        Error handling is included for each step to ensure that a failure in
        closing one component does not prevent attempts to close others.
        """
        self.log.info("Close method called. Initiating genmon shutdown sequence...")
        # we dont really care about the errors that may be generated on shutdown
        try:
            # Signal all threads that the program is stopping.
            # Threads should check self.IsStopping in their main loops.
            self.IsStopping = True
            self.log.debug("IsStopping flag set to True.")

            # Close Weather module (MyWeather itself handles its thread).
            try:
                if self.MyWeather is not None:
                    self.log.debug("Closing MyWeather module...")
                    self.MyWeather.Close()
            except Exception as e_weather_close:
                self.LogErrorLine(f"Exception during MyWeather.Close(): {e_weather_close}")
                pass # Continue shutdown.

            # Kill TimeSyncThread if it was started.
            try:
                if self.bSyncDST or self.bSyncTime: # Check if it was ever enabled.
                    self.log.debug("Attempting to kill TimeSyncThread...")
                    self.KillThread("TimeSyncThread") # MySupport.KillThread handles stopping.
            except Exception as e_kill_timesync:
                self.LogErrorLine(f"Exception killing TimeSyncThread: {e_kill_timesync}")
                pass

            # Kill ComWatchDog thread.
            try:
                self.log.debug("Attempting to kill ComWatchDog thread...")
                self.KillThread("ComWatchDog")
            except Exception as e_kill_watchdog:
                self.LogErrorLine(f"Exception killing ComWatchDog thread: {e_kill_watchdog}")
                pass

            # Close the generator controller connection.
            # The controller's Close() method should handle its own threads and resources.
            try:
                if self.Controller is not None:
                    self.log.debug("Closing Controller module...")
                    self.Controller.Close()
            except Exception as e_controller_close:
                self.LogErrorLine(f"Exception during Controller.Close(): {e_controller_close}")
                pass

            # Close the email module (MyMail).
            # MyMail.Close() should handle its threads (e.g., SendMailThread, CheckMailThread).
            try:
                if hasattr(self, 'mail') and self.mail is not None:
                    self.log.debug("Closing MyMail module...")
                    self.mail.Close()
            except Exception as e_mail_close:
                self.LogErrorLine(f"Exception during MyMail.Close(): {e_mail_close}")
                pass

            # Close any active client socket connections.
            # Iterate over a copy of the list as items might be removed.
            active_client_connections = list(self.ConnectionList)
            if active_client_connections:
                self.log.debug(f"Closing {len(active_client_connections)} active client socket connections...")
            for item_conn in active_client_connections:
                try:
                    item_conn.close()
                    if item_conn in self.ConnectionList: # Defensively remove if still there.
                         self.ConnectionList.remove(item_conn)
                except Exception as e_client_conn_close:
                    self.LogErrorLine(f"Exception closing a client connection: {e_client_conn_close}")
                    continue # Continue to close other connections.

            # Shutdown and close the main server socket and its thread.
            try:
                if self.ServerSocket is not None:
                    self.log.debug("Shutting down and closing server socket...")
                    self.ServerSocket.shutdown(socket.SHUT_RDWR) # Politely shutdown read/write.
                    self.ServerSocket.close()
                self.KillThread("InterfaceServerThread") # Stop the server accept loop thread.
            except Exception as e_server_socket_close:
                 self.LogErrorLine(f"Exception closing server socket or killing InterfaceServerThread: {e_server_socket_close}")
                 pass

            # Close inter-process communication pipes.
            try:
                if hasattr(self, 'FeedbackPipe') and self.FeedbackPipe is not None:
                    self.log.debug("Closing FeedbackPipe...")
                    self.FeedbackPipe.Close()
            except Exception as e_fbpipe_close:
                self.LogErrorLine(f"Exception during FeedbackPipe.Close(): {e_fbpipe_close}")
                pass
            try:
                if hasattr(self, 'MessagePipe') and self.MessagePipe is not None:
                    self.log.debug("Closing MessagePipe...")
                    self.MessagePipe.Close()
            except Exception as e_msgpipe_close:
                self.LogErrorLine(f"Exception during MessagePipe.Close(): {e_msgpipe_close}")
                pass

            # Final pass: tell any remaining threads managed by MySupport to stop.
            # This is a catch-all for threads that might not have been explicitly closed/killed above.
            self.log.debug("Stopping any remaining managed threads...")
            for thread_name, thread_obj in self.Threads.items():
                try:
                    if thread_obj.is_alive(): # Check if MyThread instance is alive.
                        self.log.info(f"Requesting stop for thread: {thread_name}")
                        thread_obj.Stop() # Call MyThread's Stop() method.
                except Exception as e1:
                    self.LogErrorLine(
                        f"Error trying to stop thread '{thread_name}' in Monitor Close: {str(e1)}"
                    )

        except Exception as e1: # Catch-all for errors during the shutdown sequence itself.
            self.LogErrorLine(f"Error during Monitor Close sequence: {str(e1)}")

        # Log final shutdown message. Use CriticalLock if available (from MySupport) for thread safety.
        if hasattr(self, 'CriticalLock'):
            with self.CriticalLock:
                self.LogError("Generator Monitor Shutdown Complete.")
        else:
            self.LogError("Generator Monitor Shutdown Complete.")


        try:
            # Mark program as complete and attempt a clean system exit.
            self.ProgramComplete = True
            self.log.info("Exiting genmon.py now.")
            sys.exit(0) # Normal exit.
        except SystemExit: # Catch SystemExit if it's raised by sys.exit(0) itself.
            self.log.info("sys.exit(0) called.")
        except Exception as e_final_exit: # Catch any other very late errors.
            self.LogErrorLine(f"Exception during final sys.exit in Close(): {e_final_exit}")
            # Fall through, as process will likely terminate anyway.


# ------------------- Command-line interface for monitor ------------------------
if __name__ == "__main__":  #

    try:
        ConfigFilePath = ProgramDefaults.ConfPath
        opts, args = getopt.getopt(sys.argv[1:], "c:", ["configpath="])
    except getopt.GetoptError:
        print("Invalid command line argument.")
        sys.exit(2)

    for opt, arg in opts:

        if opt in ("-c", "--configpath"):
            ConfigFilePath = arg
            ConfigFilePath = ConfigFilePath.strip()

    # Start things up
    MyMonitor = Monitor(ConfigFilePath=ConfigFilePath)

    try:
        while not MyMonitor.ProgramComplete:
            time.sleep(0.01)
        sys.exit(0)
    except:
        sys.exit(1)
