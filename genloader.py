# -------------------------------------------------------------------------------
#    FILE: genloader.py
# PURPOSE: app for loading specific moduels for genmon
#
#  AUTHOR: Jason G Yates
#    DATE: 12-Sept-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------
"""
This module defines the `Loader` class, which is responsible for managing the
lifecycle (start, stop, restart), configuration, and dependencies of various
`genmon` application modules and add-ons. It acts as the central orchestrator,
reading a main configuration file (`genloader.conf`) to determine which modules
to load, their parameters, and their load order. It also handles system checks
for required libraries and tools, attempting to install them if missing.
"""

import getopt
import os
import subprocess
import sys
import time
from shutil import copyfile, move
from subprocess import PIPE, Popen

try:
    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.mysupport import MySupport
    from genmonlib.program_defaults import ProgramDefaults

except ImportError as e1:
    # This is a critical failure if core libraries are missing.
    # Logging to console is the only option here as logger might not be set up.
    print("\n\nFATAL ERROR: This program requires the genmonlib modules (MyConfig, SetupLogger, MySupport, ProgramDefaults).")
    print("These modules should be located in the 'genmonlib' directory, typically alongside genloader.py.")
    print("Please ensure the genmonlib directory and its contents are correctly placed and accessible.")
    print("Consult the project documentation at https://github.com/jgyates/genmon for installation details.\n")
    print(f"Specific import error: {str(e1)}")
    sys.exit(2) # Exit if core components are missing.

# ------------ Loader class -----------------------------------------------------
class Loader(MySupport):
    """
    Central orchestrator for managing genmon application modules.

    The Loader class handles the initialization, starting, stopping, and
    configuration management of various genmon modules as defined in
    `genloader.conf`. It performs system checks for dependencies, attempts
    to install missing libraries, and manages the lifecycle of each module.

    Key Attributes:
        Start (bool): Flag indicating if modules should be started.
        Stop (bool): Flag indicating if modules should be stopped.
        HardStop (bool): Flag indicating if modules should be stopped forcefully (e.g., kill -9).
        ConfigFilePath (str): Path to the directory containing configuration files.
        configfile (str): Full path to the main `genloader.conf` file.
        ModulePath (str): Path to the directory where main genmon modules reside.
        ConfPath (str): Path to the directory containing default configuration files.
        config (MyConfig): `MyConfig` instance for managing `genloader.conf`.
        CachedConfig (dict): A dictionary holding the configurations for all managed modules,
                             loaded from `genloader.conf`.
        LoadOrder (list): A list of module names (sections from `genloader.conf`) sorted
                          by their defined priority, determining start/stop order.
        PipChecked (bool): Flag indicating if pip's presence has been checked.
        AptUpdated (bool): Flag indicating if `apt-get update` has been run in this session.
        NewInstall (bool): Flag set if a new installation is detected (e.g., no version in config).
        Upgrade (bool): Flag set if the config version is older than the program version.
        version (str): Current program version, typically from ProgramDefaults.
        pipProgram (str): The command to use for pip ('pip2' or 'pip3').
        log (logging.Logger): Logger instance inherited and configured via MySupport.
        console (logging.Logger): Logger for console-only output.
    """
    def __init__(
        self,
        start=False,
        stop=False,
        hardstop=False,
        loglocation=None, # Default to None, MySupport will handle ProgramDefaults.LogPath
        log=None,
        localinit=False,
        ConfigFilePath=None, # Default to None, MySupport will handle ProgramDefaults.ConfPath
    ):
        """
        Initializes the Loader instance.

        This complex constructor performs several critical setup tasks:
        1.  Sets initial operational flags (Start, Stop, HardStop).
        2.  Sets up a temporary "bootstrap" logger if no external logger is provided.
        3.  Initializes the parent class `MySupport`, which finalizes logging and
            determines `ConfigFilePath` and other inherited attributes.
        4.  Determines paths (`ModulePath`, `ConfPath`, `configfile`). The `localinit`
            parameter affects `configfile` path: if True, `genloader.conf` is expected
            in the current working directory; otherwise, it's in `ConfigFilePath`.
        5.  If `Start` is True, performs system checks for dependencies (`CheckSystem`).
        6.  Ensures the configuration directory (`ConfigFilePath`) exists.
        7.  Ensures `genloader.conf` exists, copying it from defaults if necessary.
        8.  Initializes `MyConfig` to manage `genloader.conf`.
        9.  Loads and validates the configuration (`GetConfig`, `ValidateConfig`),
            attempting to recover by copying defaults if these steps fail.
        10. Determines module load order (`GetLoadOrder`).
        11. If `Stop` flag is set, stops modules.
        12. If `Start` flag is set, starts modules.

        Args:
            start (bool, optional): If True, modules will be started. Defaults to False.
            stop (bool, optional): If True, modules will be stopped. Defaults to False.
            hardstop (bool, optional): If True, modules will be stopped forcefully.
                                       Defaults to False.
            loglocation (str, optional): Path to the directory for log files.
                                         Used by the bootstrap logger if `log` is None.
                                         MySupport will use ProgramDefaults.LogPath if this is None.
            log (logging.Logger, optional): An external logger instance. If None,
                                            one is created.
            localinit (bool, optional): If True, `genloader.conf` is expected in the
                                        current directory. Otherwise, it's in `ConfigFilePath`.
                                        This also affects how `MySupport` initializes paths.
                                        Defaults to False.
            ConfigFilePath (str, optional): The primary path for configuration files.
                                            If None, `MySupport` will use `ProgramDefaults.ConfPath`.
        """
        # --- Initial operational flags ---
        self.Start = start
        self.Stop = stop
        self.HardStop = hardstop
        self.PipChecked = False # Tracks if pip availability check has been done
        self.AptUpdated = False # Tracks if apt-get update has been run this session
        self.NewInstall = False # Flag for new installations (e.g., based on config version)
        self.Upgrade = False    # Flag for upgrades (based on config version vs program version)
        self.version = None     # Stores the current program version

        # --- Bootstrap logger setup ---
        loader_specific_logger = None
        if log is None: # log is the argument to Loader.__init__
            try:
                effective_log_location = loglocation if loglocation else ProgramDefaults.LogPath
                loader_specific_logger = SetupLogger("genloader_bootstrap",
                                                     os.path.join(effective_log_location, "genloader_bootstrap.log"))
                loader_specific_logger.info("Bootstrap logger initialized by Loader.")
            except Exception as e_log_setup:
                print(f"CRITICAL: Loader's bootstrap logger setup failed: {e_log_setup}. Using fallback PrintLogger.", file=sys.stderr)
                class PrintLoggerInit: # Renamed to avoid potential scope collision if defined again later
                    def info(self, msg): print(f"INFO: {msg}")
                    def error(self, msg): print(f"ERROR: {msg}", file=sys.stderr)
                    def debug(self, msg): print(f"DEBUG: {msg}")
                    def LogErrorLine(self, msg): self.error(f"[LINE_UNKNOWN] {msg}")
                loader_specific_logger = PrintLoggerInit()
        else:
            loader_specific_logger = log

        self.log = loader_specific_logger
        
        # --- MySupport superclass initialization ---
        try:
            intended_loader_log = self.log # Save Loader's chosen logger

            super(Loader, self).__init__() # This will set self.log to None via MyCommon

            self.log = intended_loader_log # Restore Loader's logger

            if self.log is None:
                # Fallback if intended_loader_log itself was None (e.g. external log was None)
                # or if something else went very wrong.
                print("CRITICAL ERROR: self.log is unexpectedly None after restoration. Re-creating PrintLogger for core functions.", file=sys.stderr)
                class PrintLoggerDefensive:
                    def info(self, msg): print(f"INFO_DEFENSIVE: {msg}")
                    def error(self, msg): print(f"ERROR_DEFENSIVE: {msg}", file=sys.stderr)
                    def debug(self, msg): print(f"DEBUG_DEFENSIVE: {msg}")
                    def LogErrorLine(self, msg): self.error(f"[LINE_UNKNOWN_DEFENSIVE] {msg}")
                self.log = PrintLoggerDefensive()
                self.log.error("Defensive PrintLogger activated because self.log was None after restoration from superclass init.")
            else:
                # Using "debug" level for this internal mechanism clarification, "info" might be too verbose for users.
                self.log.debug("Loader's logger restored after superclass initialization (which sets self.log to None via MyCommon).")

            # Determine and set ConfigFilePath for the Loader instance.
            if ConfigFilePath is None:
                self.ConfigFilePath = ProgramDefaults.ConfPath
            else:
                self.ConfigFilePath = ConfigFilePath

        except Exception as e_super_init:
            # Ensure self.log is usable for this error message
            if self.log is None:
                # Attempt to use intended_loader_log if it exists and is valid, otherwise new PrintLogger
                current_intended_log = locals().get('intended_loader_log')
                if current_intended_log is not None:
                    self.log = current_intended_log
                else:
                    class PrintLoggerExRecovery:
                        def info(self, msg): print(f"INFO_EX_RECOVERY: {msg}")
                        def error(self, msg): print(f"ERROR_EX_RECOVERY: {msg}", file=sys.stderr)
                        def debug(self, msg): print(f"DEBUG_EX_RECOVERY: {msg}")
                        def LogErrorLine(self, msg): self.error(f"[LINE_UNKNOWN_EX_RECOVERY] {msg}")
                    self.log = PrintLoggerExRecovery()
                self.log.error("CRITICAL: self.log was None during superclass init exception. Restored/Recreated for this error message.")
            self.log.error(f"CRITICAL: Error during MySupport initialization: {str(e_super_init)}. Functionality will be severely limited.")
            # Consider sys.exit(2) here if MySupport init is absolutely vital and failed

        # --- Pip program determination ---
        # Selects 'pip2' for Python 2 and 'pip3' for Python 3 to ensure correct package management.
        if sys.version_info[0] < 3:
            self.pipProgram = "pip2"
        else:
            self.pipProgram = "pip3"

        # --- Config file path setup ---
        # self.ConfigFilePath should now be reliably set by MySupport's initialization.
        # If it's not set, genloader cannot find its main configuration file and cannot proceed.
        if not hasattr(self, 'ConfigFilePath') or not self.ConfigFilePath:
             self.log.error("CRITICAL: ConfigFilePath not set after MySupport init. Cannot determine genloader.conf location. Exiting.")
             sys.exit(2) # Exit if the configuration path is unknown.

        self.ConfigFileName = "genloader.conf" # The name of the main configuration file for genloader.
        # The `localinit` flag determines the location of `genloader.conf`:
        # - If True, `genloader.conf` is expected in the current working directory (os.getcwd()).
        # - If False (default), `genloader.conf` is expected in `self.ConfigFilePath` (e.g., /etc/genmon/).
        if localinit:
            self.configfile = self.ConfigFileName # Path is just the filename for current dir.
            self.log.info(f"localinit is True: Expecting '{self.ConfigFileName}' in current directory: {os.getcwd()}")
        else:
            self.configfile = os.path.join(self.ConfigFilePath, self.ConfigFileName) # Full path.
            self.log.info(f"localinit is False: Expecting '{self.ConfigFileName}' in config path: {self.ConfigFilePath}")
        
        # --- Module and Default Config Paths (internal to genloader's structure) ---
        # ModulePath is the directory where this script (genloader.py) itself resides.
        # This is used as a base to find core module scripts and default configurations.
        self.ModulePath = os.path.dirname(os.path.realpath(__file__))
        # ConfPath is the 'conf' subdirectory within ModulePath. This directory contains
        # default versions of configuration files (e.g., genmon.conf, genloader.conf).
        self.ConfPath = os.path.join(self.ModulePath, "conf")

        # --- Console Logger Setup (for direct user feedback) ---
        # Sets up a logger that outputs directly to the console (stdout).
        # This is used for messages like "Starting module X..." that should be visible to the user.
        try:
            self.console = SetupLogger("genloader_console", log_file="", stream=True) # stream=True directs to console.
        except Exception as e_console_log:
            self.log.error(f"Error setting up console logger: {str(e_console_log)}")
            class PrintConsole: # Fallback if SetupLogger fails for console.
                def error(self, msg): print(f"CONSOLE_ERROR: {msg}", file=sys.stderr)
                def info(self, msg): print(f"CONSOLE_INFO: {msg}")
            self.console = PrintConsole()

        # --- Main Initialization Sequence (System Checks, Config Handling, Module Lifecycle) ---
        try:
            # --- System checks (if starting modules) ---
            # If the 'Start' flag is active, perform system checks for required libraries and tools.
            # This must be done before attempting to load any modules.
            if self.Start:
                self.log.info("Start flag is set. Performing system readiness checks (libraries, tools)...")
                if not self.CheckSystem(): # CheckSystem handles logging of its own detailed errors.
                    self.log.error("System readiness check failed. Some dependencies might be missing. Cannot start modules. Exiting.")
                    sys.exit(2) # Exit if system checks fail, as modules may not run correctly.

            self.CachedConfig = {} # Initialize an empty dictionary to store cached module configurations.

            # --- Config directory and file ensuring ---
            # Ensure the main configuration directory (e.g., /etc/genmon/) exists. Create if not.
            if not os.path.isdir(self.ConfigFilePath):
                self.log.info(f"Configuration directory '{self.ConfigFilePath}' does not exist. Attempting to create it.")
                try:
                    os.makedirs(self.ConfigFilePath, exist_ok=True) # exist_ok=True prevents error if dir already exists.
                    self.log.info(f"Successfully created configuration directory: {self.ConfigFilePath}")
                except OSError as oe: # Catch OS-level errors like permission issues.
                    self.LogErrorLine(f"OSError creating target config directory '{self.ConfigFilePath}': {str(oe)}. Check permissions and path. Exiting.")
                    sys.exit(2) 
                except Exception as e_mkdir: # Catch any other unexpected errors.
                    self.LogErrorLine(f"Unexpected error creating target config directory '{self.ConfigFilePath}': {str(e_mkdir)}. Exiting.")
                    sys.exit(2) 

            # Ensure `genloader.conf` exists in `self.configfile` path. If not, copy it from the default location.
            if not os.path.isfile(self.configfile):
                self.log.info(
                    f"Main config file '{self.configfile}' not found. Attempting to copy from default: "
                    f"{os.path.join(self.ConfPath, self.ConfigFileName)}"
                )
                if not self.CopyConfFile(): # CopyConfFile handles its own logging.
                    self.log.error(f"Failed to copy main configuration file ('{self.ConfigFileName}'). This is a critical error. Exiting.")
                    sys.exit(2) # Exit if the main config file cannot be established.
            
            # --- MyConfig initialization ---
            # Initialize MyConfig to manage `genloader.conf`. This object will be used for all reads/writes
            # to the main configuration file. A default section "genmon" is passed, though operations
            # will typically specify their target section.
            try:
                self.config = MyConfig(filename=self.configfile, section="genmon", log=self.log)
            except Exception as e_myconfig_init:
                self.LogErrorLine(f"Failed to initialize MyConfig with '{self.configfile}': {str(e_myconfig_init)}. Exiting.")
                sys.exit(2) # Exit if MyConfig fails to initialize.

            # --- Config loading, validation, and recovery ---
            # This sequence is crucial:
            # 1. Attempt to load the configuration using GetConfig().
            # 2. If GetConfig() fails, assume `genloader.conf` might be corrupt or missing critical parts.
            #    Try to recover by copying the default `genloader.conf` over the existing one.
            #    Then, re-attempt GetConfig().
            # 3. If GetConfig() succeeds, proceed to ValidateConfig().
            # 4. If ValidateConfig() fails, also assume a problematic configuration.
            #    Attempt recovery (copy default) and then re-attempt both GetConfig() and ValidateConfig().
            # This provides a robust mechanism to self-heal from common configuration issues.

            # First attempt to load configuration.
            if not self.GetConfig(): # GetConfig logs its own detailed errors.
                self.log.info("Initial attempt to load configuration (GetConfig) failed. Attempting recovery by copying default config.")
                if not self.CopyConfFile(): # CopyConfFile logs its own errors.
                     self.log.error("Failed to copy/restore main configuration file after GetConfig() failure. Exiting.")
                     sys.exit(2)
                self.log.info("Retrying GetConfig after copying default configuration.")
                try: # Re-initialize MyConfig as the file content has changed.
                    self.config = MyConfig(filename=self.configfile, section="genmon", log=self.log)
                except Exception as e_myconfig_reinit:
                    self.LogErrorLine(f"Failed to re-initialize MyConfig after copy: {str(e_myconfig_reinit)}. Exiting.")
                    sys.exit(2)
                if not self.GetConfig(): # Second attempt to load config.
                    self.log.error("Second attempt to load configuration (GetConfig) failed even after copying default. Critical failure. Exiting.")
                    sys.exit(2)

            # First attempt to validate configuration.
            if not self.ValidateConfig(): # ValidateConfig logs its own detailed errors.
                self.log.info("Initial configuration validation (ValidateConfig) failed. Attempting recovery by copying default config.")
                if not self.CopyConfFile(): # CopyConfFile logs its own errors.
                     self.log.error("Failed to copy/restore main configuration file after ValidateConfig() failure. Exiting.")
                     sys.exit(2)
                self.log.info("Retrying configuration load and validation after copying default configuration.")
                try: # Re-initialize MyConfig again.
                    self.config = MyConfig(filename=self.configfile, section="genmon", log=self.log)
                except Exception as e_myconfig_reinit_val:
                    self.LogErrorLine(f"Failed to re-initialize MyConfig for validation retry: {str(e_myconfig_reinit_val)}. Exiting.")
                    sys.exit(2)
                if not self.GetConfig(): # Must re-load config after copy for validation to use fresh data.
                    self.log.error("Failed to re-load configuration (GetConfig) after copy during validation retry. Exiting.")
                    sys.exit(2)
                if not self.ValidateConfig(): # Second attempt to validate.
                    self.log.error("Second attempt to validate configuration (ValidateConfig) failed even after copying default. Critical failure. Exiting.")
                    sys.exit(2)

            # Determine module load order based on 'priority' settings in the (now loaded and validated) config.
            self.LoadOrder = self.GetLoadOrder() # GetLoadOrder logs its own errors if any.

            # --- Module start/stop logic based on operational flags ---
            # If the 'Stop' flag is set, proceed to stop modules.
            if self.Stop:
                self.log.info("Stop flag is set. Processing stop for configured modules...")
                self.StopModules() # StopModules handles its own logging.
                time.sleep(2) # A brief pause to allow modules time to shut down cleanly.

            # If the 'Start' flag is set, proceed to start modules.
            # This occurs after stopping if both flags were set (e.g., for a restart operation).
            if self.Start:
                self.log.info("Start flag is set. Processing start for configured and enabled modules...")
                self.StartModules() # StartModules handles its own logging.

        except SystemExit: # Allow sys.exit() calls from earlier checks (e.g., permission denied) to propagate cleanly.
            self.log.info("SystemExit called during Loader initialization sequence. Exiting.")
            raise # Re-raise the SystemExit exception.
        except Exception as e_init_main: # Catch-all for any other unhandled exceptions during the main __init__ sequence.
            self.LogErrorLine(f"CRITICAL UNHANDLED ERROR during Loader initialization sequence: {str(e_init_main)}")
            # Depending on the state, self.log might be the bootstrap logger or the finalized MySupport logger.
            sys.exit(3) # Exit due to a critical unhandled error in initialization.

    # ---------------------------------------------------------------------------
    def CopyConfFile(self):
        """
        Copies the default `genloader.conf` file from the installation's `conf`
        directory (self.ConfPath) to the active configuration path (`self.configfile`).

        This method is typically invoked during initialization if `genloader.conf`
        is missing from the active configuration path (e.g., /etc/genmon/) or
        if a configuration recovery process is triggered due to errors in an
        existing `genloader.conf`. It ensures that the target directory for
        `self.configfile` exists before attempting the copy operation, creating
        it if necessary.

        Returns:
            bool: True if the `genloader.conf` file was copied successfully,
                  False if the source file doesn't exist, the target directory
                  cannot be created, or the copy operation itself fails due to
                  I/O errors, permission issues, or other exceptions.
        """
        # Path to the source (default) genloader.conf in the installation directory.
        source_conf_file = os.path.join(self.ConfPath, self.ConfigFileName)
        # Path to the target genloader.conf in the active configuration directory.
        target_conf_file = self.configfile # self.configfile is the full path (e.g., /etc/genmon/genloader.conf)

        try:
            # Pre-check 1: Verify that the source (default) configuration file actually exists.
            if not os.path.isfile(source_conf_file):
                self.log.error(f"Default configuration file '{source_conf_file}' not found. Cannot copy to '{target_conf_file}'.")
                return False # Cannot proceed if the source file is missing.
            
            # Pre-check 2: Ensure the destination directory for the target config file exists.
            # Although the __init__ method also attempts to create self.ConfigFilePath,
            # this serves as a safeguard, especially if CopyConfFile is called independently
            # or if initial creation in __init__ failed silently (though unlikely with current error handling).
            target_dir = os.path.dirname(target_conf_file) # Get the directory part (e.g., /etc/genmon/)
            if not os.path.isdir(target_dir):
                self.log.info(f"Target directory '{target_dir}' for config file '{self.ConfigFileName}' does not exist. Attempting to create it.")
                try:
                    os.makedirs(target_dir, exist_ok=True) # Create directory, exist_ok=True means no error if it already exists.
                    self.log.info(f"Successfully created target directory '{target_dir}'.")
                except OSError as oe_dir: # Catch OS errors during directory creation (e.g., permission denied).
                    self.LogErrorLine(f"OSError creating directory '{target_dir}' for config file: {str(oe_dir)}. Cannot copy config file.")
                    return False # Cannot copy if target directory creation fails.
            
            # Perform the copy operation.
            self.log.info(f"Attempting to copy default config from '{source_conf_file}' to '{target_conf_file}'.")
            copyfile(source_conf_file, target_conf_file) # Uses shutil.copyfile for the operation.
            self.log.info(f"Successfully copied default config from '{source_conf_file}' to '{target_conf_file}'.")
            return True # Indicate success.
        except IOError as ioe: # Catch specific I/O errors related to the copyfile operation itself (e.g., disk full).
            self.LogErrorLine(f"IOError during config file copy from '{source_conf_file}' to '{target_conf_file}': {str(ioe)}")
            return False
        except OSError as ose: # Catch broader OS errors (e.g., permissions on files, path issues not caught by makedirs).
            self.LogErrorLine(f"OSError during config file copy operation (source: '{source_conf_file}', target: '{target_conf_file}'): {str(ose)}")
            return False
        except Exception as e_copy: # Catch any other unexpected errors during the copy process.
            self.LogErrorLine(f"Unexpected error copying config file from '{source_conf_file}' to '{target_conf_file}': {str(e_copy)}")
            return False

    # ---------------------------------------------------------------------------
    def CheckSystem(self):
        """
        Checks if required Python libraries are installed and attempts to install them if missing.

        It iterates through a predefined list of modules (`ModuleList`), where each entry
        specifies the import name, pip install name, and an optional required version.
        It uses `LibraryIsInstalled` to check and `InstallLibrary` to install.
        Also calls `CheckToolsNeeded` to ensure system tools like `cmake` are available.

        Returns:
            bool: True if all checks pass and necessary installations succeed, False otherwise.
        """
        self.log.info("Starting system check for required libraries and tools...")
        # --- module_list_definitions ---
        # This list defines Python libraries required by genmon and its modules.
        # Each entry is a list: [import_name, pip_install_name, optional_required_version].
        # - import_name: The name used in Python's `import` statement (e.g., "paho.mqtt.client").
        # - pip_install_name: The name used in `pip install` (e.g., "paho-mqtt").
        # - optional_required_version: If a specific version is needed, it's specified here (e.g., "2.10.0").
        #   If None, any version is acceptable, or the latest will be installed.
        module_list_definitions = [
            ["flask", "flask", None], # For genserv (web interface)
            ["serial", "pyserial", None], # For serial communication (e.g., genmon, modem modules)
            ["crcmod", "crcmod", None], # For CRC calculations, often with serial protocols
            ["pyowm", "pyowm", "2.10.0"], # For genweather (OpenWeatherMap); version is important due to API changes.
                                         # Note: FixPyOWMMaintIssues might handle specific nuances for pyowm versions.
            ["pytz", "pytz", None], # For timezone handling
            ["pysnmp", "pysnmp", None], # For gensnmp (SNMP communication)
            ["ldap3", "ldap3", None], # For LDAP authentication (if used)
            ["smbus", "smbus", None], # For I2C communication (e.g., some sensor modules on Raspberry Pi)
            ["pyotp", "pyotp", "2.3.0"], # For Time-based One-Time Passwords (e.g., multi-factor auth)
            ["psutil", "psutil", None], # For system process and utilization information
            ["chump", "chump", None], # For genpushover (Pushover notifications)
            ["twilio", "twilio", None], # For gensms (Twilio SMS notifications)
            ["paho.mqtt.client", "paho-mqtt", "1.6.1"], # For genmqtt and genmqttin (MQTT communication)
            ["OpenSSL", "pyopenssl", None], # For SSL/TLS support, often a dependency for secure connections
            ["spidev", "spidev", None], # For SPI communication (e.g., some hardware interfaces)
            ["voipms", "voipms", "0.2.5"] # For gensms_voip (VoIP.ms SMS notifications)
            # Example of a conditionally checked module (original code had 'fluids' commented out like this):
            # ['fluids', 'fluids', None] # This library might only be checked/installed if a specific condition is met.
        ]
        # --- any_installation_failed ---
        # This flag tracks if any library installation attempt fails during the CheckSystem process.
        # It's initialized to False and set to True if any call to InstallLibrary returns False.
        # The final return value of CheckSystem depends on this flag.
        any_installation_failed = False

        # First, check for essential system tools (like cmake) that might be needed by some Python libraries.
        if not self.CheckToolsNeeded(): # CheckToolsNeeded logs its own errors if tools are missing/fail to install.
            self.log.error("CheckToolsNeeded reported errors. System readiness check might be incomplete or subsequent library installations might fail.")
            # Depending on how critical these tools are, one could set any_installation_failed = True here,
            # or rely on subsequent Python library install failures to catch the issue.

        # Iterate through the list of required Python libraries.
        for import_name, install_name, required_version in module_list_definitions:
            # --- Conditional check for the 'fluids' library (example from original code) ---
            # This demonstrates how a library check can be made conditional. For instance, 'fluids'
            # might only be compatible with Python 3.6+ or specific hardware.
            if (import_name == "fluids") and sys.version_info < (3, 6): # Example condition.
                self.log.debug(f"Skipping check for '{install_name}' as it requires Python 3.6+ (current: {sys.version_info.major}.{sys.version_info.minor}).")
                continue # Skip to the next library in the list.

            # Check if the library is already installed and importable.
            if not self.LibraryIsInstalled(import_name): # LibraryIsInstalled logs its attempts.
                self.log.info(
                    f"Warning: Required Python library '{install_name}' (for import '{import_name}') not found. Attempting installation..."
                )
                # Attempt to install the library if it's missing.
                if not self.InstallLibrary(install_name, version=required_version): # InstallLibrary logs details of success/failure.
                    self.log.error(f"Error: Failed to install Python library '{install_name}'. This may impact functionality.")
                    any_installation_failed = True # Mark that at least one installation failed.

                # Specific post-install action for ldap3: pyasn1 is a common dependency that sometimes causes issues.
                # Modern pip usually handles dependencies well, so this explicit check might be less needed
                # but is retained from original logic as a safeguard or for older pip versions.
                if import_name == "ldap3" and not self.LibraryIsInstalled("pyasn1"):
                    self.log.info("Attempting to update/install 'pyasn1' as it's a common dependency for 'ldap3' and might resolve import issues.")
                    if not self.InstallLibrary("pyasn1", update=True): # Try to install or update pyasn1.
                         self.log.warning("Failed to install/update 'pyasn1' for 'ldap3'. This might or might not cause issues with LDAP functionality.")
                         # Not necessarily setting any_installation_failed = True for a sub-dependency here,
                         # as ldap3 might still work or the user might resolve it manually.

        # After checking all libraries, determine the overall success.
        if any_installation_failed:
            self.log.error("One or more required Python libraries could not be installed. System readiness check failed. Some genmon features may not work.")
            return False # Indicates failure.
        else:
            self.log.info("System check for Python libraries completed. All appear to be installed or were successfully installed.")
            return True # Indicates success.
        # Removed original try-except Exception as e_checksys, as individual methods (InstallLibrary, etc.)
        # should handle their own specific exceptions and log them appropriately.

    # ---------------------------------------------------------------------------
    def ExecuteCommandList(self, execute_list, env=None):
        """
        Executes an external command as a subprocess using `subprocess.Popen`.

        This utility method is designed to run a command with specified arguments,
        capture its standard output (stdout) and standard error (stderr) streams,
        and check the command's exit (return) code. It logs detailed information
        about the command execution, including the command itself, its output,
        and any errors encountered.

        Args:
            execute_list (list of str): A list where the first element is the
                                        executable command (e.g., "pip", "sudo")
                                        and subsequent elements are its arguments
                                        (e.g., "install", "flask"). All elements
                                        are converted to strings before execution.
            env (dict, optional): A dictionary of environment variables to set
                                  for the command's execution context. If None
                                  (default), the command inherits the environment
                                  of the current Python process.

        Returns:
            bool: True if the command executed successfully (i.e., return code is 0).
                  False if the command fails (non-zero return code), if the
                  command executable is not found (FileNotFoundError), or if
                  any other `subprocess.SubprocessError` or unexpected exception
                  occurs during execution.
        """
        try:
            # Ensure all elements in execute_list are strings, as Popen expects this.
            execute_list_str = [str(item) for item in execute_list]
            self.log.debug(f"Executing command: {' '.join(execute_list_str)}") # Log the command being run.
            
            # Start the subprocess. stdout and stderr are piped to capture their output.
            # `env=env` passes the custom environment if provided.
            process = Popen(execute_list_str, stdout=PIPE, stderr=PIPE, env=env)
            # Wait for the command to complete and get its output and error streams (as bytes).
            output_bytes, error_bytes = process.communicate()
            return_code = process.returncode # Get the exit code of the command.

            # Decode output and error streams from bytes to string using system's default encoding.
            # 'errors="replace"' ensures that undecodable bytes are replaced with a placeholder,
            # preventing decode errors from halting the process.
            output_str = output_bytes.decode(sys.getdefaultencoding(), errors='replace').strip() if output_bytes else ""
            error_str = error_bytes.decode(sys.getdefaultencoding(), errors='replace').strip() if error_bytes else ""

            # Check the return code. A non-zero code typically indicates an error.
            if return_code != 0:
                log_message = f"Error executing command: '{' '.join(execute_list_str)}'. Return Code: {return_code}"
                if output_str: # Include stdout if it's not empty.
                    log_message += f"\nStdout: {output_str}"
                if error_str: # Include stderr if it's not empty.
                    log_message += f"\nStderr: {error_str}"
                self.log.error(log_message) # Log the comprehensive error message.
                return False # Indicate failure.
            
            # Log non-empty stderr even on success (return code 0), as it might contain warnings or important notices.
            if error_str:
                self.log.info(f"Stderr from successful command '{' '.join(execute_list_str)}' (RC=0):\n{error_str}")

            self.log.debug(f"Command '{' '.join(execute_list_str)}' executed successfully (RC=0).")
            return True # Indicate success.
        except FileNotFoundError: # Specific error if the command executable itself (execute_list[0]) is not found.
            self.LogErrorLine(f"Error in ExecuteCommandList: Command '{execute_list[0]}' not found. Ensure it is installed and in the system's PATH.")
            return False
        except subprocess.SubprocessError as spe: # Catch other errors related to Popen or communicate (e.g., OS errors).
            self.LogErrorLine(f"Subprocess error executing '{' '.join(map(str,execute_list))}': {str(spe)}")
            return False
        except Exception as e_exec: # Catch any other unexpected errors during command execution.
            self.LogErrorLine(f"Unexpected error in ExecuteCommandList for '{' '.join(map(str,execute_list))}': {str(e_exec)}")
            return False

    # ---------------------------------------------------------------------------
    def CheckToolsNeeded(self):
        """
        Checks for essential system tools, specifically `cmake`, which may be
        required as a build dependency for some Python libraries (e.g., dlib,
        which might be a transitive dependency for other packages).

        If `cmake` is not found (checked by running `cmake --version`), this
        method attempts to install it using the system's package manager (`apt-get`
        on Debian-based systems). Before attempting installation, it ensures that
        `apt-get update` has been run at least once in the current genloader
        session to refresh package lists.

        Returns:
            bool: True if `cmake` is already present or is successfully installed.
                  False if `apt-get update` fails, if `cmake` installation fails,
                  or if any other unexpected error occurs.
        """
        try:
            self.log.info("Checking for required system tool: cmake.")
            command_list_cmake_check = ["cmake", "--version"] # Command to check if cmake is installed.

            # Attempt to execute 'cmake --version'. If it fails, cmake is likely not installed or not in PATH.
            if not self.ExecuteCommandList(command_list_cmake_check): # ExecuteCommandList logs detailed errors on failure.
                self.log.info("'cmake --version' command failed, indicating cmake is not installed or not in the system PATH. Attempting to install cmake via apt-get.")
                
                # Run 'apt-get update' if it hasn't been done already in this session.
                # This is important to ensure package lists are up-to-date before trying to install.
                if not self.AptUpdated:
                    self.log.info("Running 'apt-get update' before attempting to install cmake.")
                    # Command for 'apt-get update', using -yqq for non-interactive and quiet operation.
                    # --allow-releaseinfo-change is added for robustness on systems where release info might have changed.
                    cmd_apt_update_allow_rls = ["sudo", "apt-get", "-yqq", "--allow-releaseinfo-change", "update"]
                    cmd_apt_update_normal = ["sudo", "apt-get", "-yqq", "update"] # Fallback without --allow-releaseinfo-change
                    
                    # Try 'apt-get update' with --allow-releaseinfo-change first.
                    if not self.ExecuteCommandList(cmd_apt_update_allow_rls):
                        self.log.info("First 'apt-get update' attempt failed (with --allow-releaseinfo-change). Retrying standard 'apt-get update'...")
                        # If the first attempt fails, try the standard update command.
                        if not self.ExecuteCommandList(cmd_apt_update_normal):
                            self.log.error("Error: Unable to run 'apt-get update' successfully even after retry. Cannot proceed with cmake installation.")
                            return False # Cannot install cmake if 'apt-get update' fails.
                    self.AptUpdated = True # Mark that 'apt-get update' has been run for this session.
                    self.log.info("'apt-get update' completed successfully.")
                
                # Attempt to install cmake using 'apt-get install'.
                self.log.info("Attempting to install cmake using 'apt-get install -yqq cmake'.")
                # DEBIAN_FRONTEND=noninteractive is set in the environment to prevent apt-get
                # from prompting for user input during installation, which would hang the script.
                custom_env = os.environ.copy()
                custom_env["DEBIAN_FRONTEND"] = "noninteractive"
                install_cmd_list_cmake = ["sudo", "apt-get", "-yqq", "install", "cmake"]

                if not self.ExecuteCommandList(install_cmd_list_cmake, env=custom_env): # ExecuteCommandList logs errors on failure.
                    self.log.error("Error: Failed to install cmake via 'apt-get'. Some Python libraries requiring cmake may fail to install.")
                    return False # cmake installation failed.
                self.log.info("cmake installed successfully via apt-get.")
            else:
                # If 'cmake --version' executed successfully, cmake is already installed.
                self.log.info("cmake is already installed and accessible in the system PATH.")
            return True # cmake is present or was successfully installed.
        except Exception as e_tools: # Catch any other unexpected errors.
            self.LogErrorLine(f"Unexpected error in CheckToolsNeeded while checking/installing cmake: {str(e_tools)}")
            return False

    # ---------------------------------------------------------------------------
    def CheckBaseSoftware(self):
        """
        Checks if `pip` (Python's package installer) is installed and accessible.

        It performs this check by attempting to run `python -m pip -V` (where
        `python` is `sys.executable`, the current Python interpreter). This is
        a robust way to check for `pip` associated with the running Python.
        If this command fails (indicating `pip` is missing or not configured
        correctly for this Python environment), it calls `self.InstallBaseSoftware()`
        to attempt an installation of `pip`.

        The `self.PipChecked` flag is used to ensure this check is performed
        only once per genloader session if successful, to avoid redundant checks.

        Returns:
            bool: True if `pip` is found to be available or is successfully
                  installed by `InstallBaseSoftware()`. False if `pip` is not
                  available and the attempt to install it also fails, or if an
                  unexpected error occurs during the check.
        """
        try:
            # If pip check was already performed and successful in this session, skip redundant checks.
            if self.PipChecked:
                self.log.debug("Pip check previously performed and successful. Skipping.")
                return True

            self.log.info("Checking for pip (Python package installer) availability...")
            # Command to check pip version: `python -m pip -V`. A non-zero return code indicates issues.
            # Using `sys.executable` ensures we check for pip associated with the current Python interpreter.
            command_list_pip_check = [sys.executable, "-m", "pip", "-V"]

            # ExecuteCommandList will log detailed errors if the command fails.
            if not self.ExecuteCommandList(command_list_pip_check):
                self.log.info(f"'{sys.executable} -m pip -V' command failed. This usually means pip is not installed or not configured correctly for this Python environment. Attempting to install base software (pip).")
                # If pip is not found or the check command fails, attempt to install it.
                if not self.InstallBaseSoftware(): # InstallBaseSoftware logs its own success/failure details.
                    self.log.error("Failed to install base software (pip) after the check indicated it was missing or misconfigured. Python package management will not be possible.")
                    self.PipChecked = False # Explicitly mark as failed for this session to allow re-checks if necessary.
                    return False # Pip installation failed.
            else:
                # If 'python -m pip -V' succeeded, pip is installed and accessible.
                self.log.info("pip is installed and accessible for the current Python interpreter.")

            self.PipChecked = True # Mark pip as checked and available for this session.
            return True
        except Exception as e_basesw: # Catch any other unexpected errors during the check.
            self.LogErrorLine(f"Unexpected error during CheckBaseSoftware: {str(e_basesw)}")
            # As a fallback, attempt to install pip, similar to the original logic's catch-all.
            # This is less likely to succeed if the primary check path already encountered issues,
            # but it's retained for robustness.
            self.log.info("Attempting to install base software (pip) as a fallback due to an unexpected error in CheckBaseSoftware.")
            if not self.InstallBaseSoftware(): # InstallBaseSoftware logs its own errors.
                 self.log.error("Fallback attempt to install base software (pip) also failed.")
            self.PipChecked = False # Ensure PipChecked is false if we hit an exception path and installation fails.
            return False # Indicate failure due to unexpected error.

    # ---------------------------------------------------------------------------
    def InstallBaseSoftware(self):
        """
        Installs `pip` (Python's package installer) using the system's package
        manager (`apt-get` on Debian-based systems).

        This method determines the correct `pip` package name to install
        (`python-pip` for Python 2, `python3-pip` for Python 3) based on the
        currently running Python version (`sys.version_info`).
        Before attempting the installation, it ensures that `apt-get update`
        has been run at least once in the current genloader session to refresh
        package lists, using the `self.AptUpdated` flag to track this.
        The installation is performed non-interactively.

        Returns:
            bool: True if `pip` is successfully installed via `apt-get`.
                  False if `apt-get update` fails, if the `pip` installation
                  command fails, or if any other unexpected error occurs.
        """
        try:
            # Determine the correct pip package name based on the major Python version.
            # For Python 3.x, it's 'python3-pip'; for Python 2.x, it's 'python-pip'.
            pip_install_program = "python3-pip" if sys.version_info[0] >= 3 else "python-pip"
            self.log.info(f"Attempting to install base software: {pip_install_program} using apt-get.")

            # Run 'apt-get update' if it hasn't been done already in this session.
            # This ensures package lists are current before trying to install pip.
            if not self.AptUpdated:
                self.log.info(f"Running 'apt-get update' before installing {pip_install_program}.")
                # Commands for 'apt-get update', with -yqq for non-interactive and quiet operation.
                # Includes --allow-releaseinfo-change for robustness on systems with changed release info.
                cmd_apt_update_allow_rls = ["sudo", "apt-get", "-yqq", "--allow-releaseinfo-change", "update"]
                cmd_apt_update_normal = ["sudo", "apt-get", "-yqq", "update"] # Fallback command.
                
                # Try 'apt-get update' with --allow-releaseinfo-change first.
                if not self.ExecuteCommandList(cmd_apt_update_allow_rls):
                    self.log.info("First 'apt-get update' attempt failed (with --allow-releaseinfo-change). Retrying standard 'apt-get update'...")
                    # If the first attempt fails, try the standard update command.
                    if not self.ExecuteCommandList(cmd_apt_update_normal):
                        self.log.error(f"Error: Unable to run 'apt-get update' successfully. Cannot proceed with installing {pip_install_program}.")
                        return False # Cannot install pip if 'apt-get update' fails.
                self.AptUpdated = True # Mark that 'apt-get update' has been run for this session.
                self.log.info("'apt-get update' completed successfully.")
            
            # Prepare for non-interactive installation by setting DEBIAN_FRONTEND.
            # This prevents apt-get from hanging by asking for user input.
            custom_env = os.environ.copy()
            custom_env["DEBIAN_FRONTEND"] = "noninteractive"
            # Command to install the determined pip package.
            command_list_pip_install = ["sudo", "apt-get", "-yqq", "install", pip_install_program]
            
            # Execute the pip installation command using ExecuteCommandList.
            if not self.ExecuteCommandList(command_list_pip_install, env=custom_env): # ExecuteCommandList logs errors on failure.
                self.log.error(f"Error: Failed to install {pip_install_program} via 'apt-get'.")
                return False # Pip installation failed.

            self.log.info(f"{pip_install_program} (pip for Python {sys.version_info[0]}.x) installed successfully via apt-get.")
            return True # Pip installation succeeded.
        except Exception as e_installbase: # Catch any other unexpected errors.
            self.LogErrorLine(f"Unexpected error in InstallBaseSoftware while trying to install pip: {str(e_installbase)}")
            return False

    # ---------------------------------------------------------------------------
    @staticmethod
    def OneTimeMaint(ConfigFilePath, log): # log is passed directly, not self.log
        """
        Performs one-time maintenance tasks, primarily focused on migrating old
        data and log files from their previous locations (often relative to the
        script's directory or within `genmonlib`) to the standardized
        `ConfigFilePath` (e.g., /etc/genmon/ or a user-defined path).

        This is a static method, meaning it can be called without an instance
        of the Loader class (e.g., `Loader.OneTimeMaint(...)`). It checks for
        the existence of a predefined list of files (specified in
        `file_migration_list`) in known old locations. If found, these files
        are moved to the `ConfigFilePath`. The method also ensures that the
        `ConfigFilePath` directory itself exists, creating it if necessary.

        This helps maintain a clean directory structure and ensures that data
        from older installations is preserved and accessible in the new standard
        location.

        Args:
            ConfigFilePath (str): The target absolute path for configuration, data,
                                  and log files (e.g., "/etc/genmon"). This is
                                  where old files will be moved.
            log (logging.Logger): An external logger instance (not `self.log`)
                                  to be used for logging maintenance activities.
                                  This is necessary because `OneTimeMaint` is
                                  static and doesn't have access to `self.log`.

        Returns:
            bool: True if the maintenance tasks were performed successfully,
                  or if no maintenance was deemed necessary (e.g., no old files
                  found). False if a critical error occurred during the process,
                  such as failure to create the `ConfigFilePath` directory or
                  an unhandled exception during file moving operations.
        """
        # Determine the script's directory (where genloader.py resides) and the
        # path to the 'genmonlib' directory, as these were common locations for old files.
        script_dir = os.path.dirname(os.path.realpath(__file__))
        genmonlib_dir = os.path.join(script_dir, "genmonlib")

        # Defines a list of files to potentially migrate.
        # The dictionary maps the file's basename to the directory prefix where it might be found.
        # Paths are constructed relative to `script_dir` or `genmonlib_dir`.
        file_migration_list = {
            "feedback.json": script_dir,    # Old feedback data file
            "outage.txt": script_dir,       # Old outage log
            "kwlog.txt": script_dir,        # Old keyword log
            "maintlog.json": script_dir,    # Old maintenance log
            "Feedback_dat": genmonlib_dir,  # Older data file from genmonlib
            "Message_dat": genmonlib_dir,   # Older message data file from genmonlib
        }
        # Note: Migration of files from system-wide locations like a very old /etc/genmon.conf
        # (if it was ever used directly by genloader for these specific data files) would be more complex
        # and needs careful consideration of system-wide vs. local installations.
        # The current logic focuses on files that were typically bundled within the application's own structure.

        # Heuristic check to see if migration is likely needed.
        # If specific key files (known to be in old locations) are absent, AND a very old global
        # config like /etc/genmon.conf (which might imply an even older setup not covered here)
        # also doesn't exist, then assume maintenance is already done or not applicable (e.g., fresh install).
        key_old_files_for_check = [
            os.path.join(genmonlib_dir, "Message_dat"), # A key data file from an old location.
            os.path.join(script_dir, "maintlog.json"), # Another key log file from an old location.
        ]
        if not any(os.path.isfile(f) for f in key_old_files_for_check) and not os.path.isfile("/etc/genmon.conf"):
            log.info("OneTimeMaint: Key source files for migration not found in typical old locations, and /etc/genmon.conf (an indicator of very old setups) doesn't exist. Skipping file migration tasks.")
            return True # Nothing to do, or maintenance already performed.

        try:
            # Ensure the target configuration directory (ConfigFilePath) exists. Create if not.
            if not os.path.isdir(ConfigFilePath):
                log.info(f"OneTimeMaint: Target configuration directory '{ConfigFilePath}' does not exist. Attempting to create it.")
                try:
                    os.makedirs(ConfigFilePath, exist_ok=True) # exist_ok=True prevents error if dir already exists.
                    log.info(f"OneTimeMaint: Successfully created target directory: {ConfigFilePath}")
                except OSError as oe: # Catch OS-level errors like permission issues.
                    log.error(f"OneTimeMaint: OSError creating target config directory '{ConfigFilePath}': {str(oe)}", exc_info=True)
                    return False # Cannot proceed if target directory creation fails.
                except Exception as e_mkdir: # Catch any other unexpected errors during directory creation.
                     log.error(f"OneTimeMaint: Unexpected error creating target config directory '{ConfigFilePath}': {str(e_mkdir)}", exc_info=True)
                     return False

            files_moved_count = 0 # Counter for successfully moved files.
            # Iterate through the defined list of files to check and migrate.
            for file_basename, source_path_prefix in file_migration_list.items():
                source_file_full_path = os.path.join(source_path_prefix, file_basename) # Full path to the old file.
                target_file_full_path = os.path.join(ConfigFilePath, file_basename)   # Full path to the new location.

                if os.path.isfile(source_file_full_path): # Check if the source (old) file exists.
                    try:
                        log.info(f"OneTimeMaint: Moving '{source_file_full_path}' to '{target_file_full_path}'")
                        move(source_file_full_path, target_file_full_path) # shutil.move handles cross-filesystem moves if needed.
                        files_moved_count += 1
                        log.info(f"OneTimeMaint: Successfully moved '{file_basename}' to '{ConfigFilePath}'.")
                    except FileNotFoundError: # Should ideally not happen if os.path.isfile was true just before.
                        log.warning(f"OneTimeMaint: Source file '{source_file_full_path}' disappeared before it could be moved. Skipping this file.")
                    except (IOError, OSError) as e_move_io_os: # Catch file I/O or OS errors during the move operation.
                        log.error(f"OneTimeMaint: IOError/OSError moving '{source_file_full_path}' to '{target_file_full_path}': {str(e_move_io_os)}", exc_info=True)
                        # Continue to try moving other files, but log the error.
                    except Exception as e_move_other: # Catch other unexpected errors during the move.
                        log.error(f"OneTimeMaint: Unexpected error moving '{source_file_full_path}': {str(e_move_other)}", exc_info=True)
                # else: # If the source file doesn't exist, silently skip it. No need to log for each non-existent old file.
                    # log.debug(f"OneTimeMaint: Source file '{source_file_full_path}' not found for moving. Skipping.")

            if files_moved_count > 0:
                 log.info(f"OneTimeMaint: Completed moving {files_moved_count} files into '{ConfigFilePath}'.")
            else:
                 log.info("OneTimeMaint: No files were moved. This may be because they were already moved previously, or the source files were not found in the specified old locations.")
            return True # Maintenance process completed (even if some individual moves failed but were logged).

        except Exception as e_maint_outer: # Catch any other unexpected error in the outer maintenance logic.
            log.error(f"OneTimeMaint: Unexpected critical error during the one-time maintenance process: {str(e_maint_outer)}", exc_info=True)
            return False # Indicate that the overall maintenance process encountered a critical failure.

    # ---------------------------------------------------------------------------
    def FixPyOWMMaintIssues(self):
        """
        Addresses potential compatibility issues with the `pyowm` (OpenWeatherMap)
        library by ensuring a specific known-compatible version is installed.

        Newer versions of `pyowm` (beyond 2.x series, e.g., 3.x) introduced
        breaking changes that are incompatible with how genmon uses the library.
        This method checks the currently installed version of `pyowm`.
        - If `pyowm` is not installed, it attempts to install the known-good version.
        - If an incompatible (too new) version is detected, it attempts to
          uninstall the current version and then install the known-good version.
        - The "known-good" version is typically "2.10.0" for Python 3 and
          "2.9.0" for Python 2 (though Python 2 is largely obsolete).

        This is often called during new installations (`self.NewInstall` is True)
        or if `UpdateIfNeeded` detects a need for it.

        Returns:
            bool: True if `pyowm` is found to be at an acceptable version or is
                  successfully "fixed" (reinstalled to the correct version).
                  False if `pyowm` is missing and cannot be installed, if
                  uninstallation of a newer version fails, if installation of the
                  target version fails, or if any other unexpected error occurs.
        """
        try:
            # Attempt to import pyowm first. If it's not installed, ImportError will be raised.
            try:
                import pyowm # Standard import to check availability.
            except ImportError:
                self.log.error("FixPyOWMMaintIssues: The 'pyowm' library is not installed.")
                # If pyowm is missing entirely, attempt to install the known-good version.
                self.log.info("Attempting to install the required version of 'pyowm' as it's currently missing.")
                # Determine the target version based on Python major version.
                required_version_for_install = "2.10.0" if sys.version_info[0] >= 3 else "2.9.0" # Py3 vs Py2
                if self.InstallLibrary("pyowm", version=required_version_for_install): # InstallLibrary logs its own success/failure.
                    self.log.info(f"Successfully installed 'pyowm' version {required_version_for_install}. A restart of genloader/genmon might be needed for changes to take full effect.")
                    return True # Successfully installed missing pyowm.
                else:
                    self.log.error("Failed to install the missing 'pyowm' library during FixPyOWMMaintIssues. Weather functionality may be affected.")
                    return False # Failed to install missing pyowm.

            # Determine the target "known good" version string based on Python version.
            # This is the version we want to ensure is installed.
            required_version_str = "2.10.0" if sys.version_info[0] >= 3 else "2.9.0"

            # Get the currently installed version of pyowm.
            installed_version_str = self.GetLibararyVersion("pyowm") # This method logs its own errors if version cannot be found.

            if installed_version_str is None:
                self.log.error("FixPyOWMMaintIssues: Could not determine the installed version of 'pyowm' even though it seems to be importable. Cannot proceed with version check and fix.")
                return False # Cannot proceed if installed version is unknown.

            # Compare the installed version with the required "known good" version.
            # self.VersionTuple converts version strings like "2.10.0" to tuples (2, 10, 0) for easy comparison.
            # If the installed version is less than or equal to the required version, it's considered acceptable.
            # (This primarily targets issues with versions newer than 2.x).
            if self.VersionTuple(installed_version_str) <= self.VersionTuple(required_version_str):
                self.log.info(f"Installed 'pyowm' version {installed_version_str} is acceptable (expected <= {required_version_str}). No fix needed for pyowm.")
                return True # Current version is acceptable.

            # If the installed version is newer than required (e.g., a 3.x version when 2.10.0 is expected),
            # attempt to uninstall the current version and then install the correct one.
            self.log.info(
                f"FixPyOWMMaintIssues: Found installed 'pyowm' version {installed_version_str}, which is newer than the required/tested version {required_version_str}. "
                f"Attempting to uninstall the current version and reinstall version {required_version_str}."
            )

            # Uninstall the current (newer, problematic) version of pyowm.
            if not self.InstallLibrary("pyowm", uninstall=True): # InstallLibrary with uninstall=True handles the uninstallation.
                self.log.error("FixPyOWMMaintIssues: Failed to uninstall the current (newer) version of 'pyowm'. Cannot proceed with installing the correct version.")
                return False 
            
            self.log.info(f"Successfully uninstalled current 'pyowm'. Now attempting to install required version {required_version_str}.")

            # Install the known-good version of pyowm.
            if not self.InstallLibrary("pyowm", version=required_version_str): # InstallLibrary handles the installation.
                self.log.error(f"FixPyOWMMaintIssues: Failed to install the required version {required_version_str} of 'pyowm' after uninstalling the newer one.")
                return False

            self.log.info(f"FixPyOWMMaintIssues: Successfully uninstalled newer 'pyowm' and installed required version {required_version_str}. A restart might be needed.")
            return True # Successfully fixed pyowm version.
        except Exception as e_fixpyowm: # Catch any other unexpected errors during the process.
            self.LogErrorLine(f"Unexpected error in FixPyOWMMaintIssues while managing 'pyowm' version: {str(e_fixpyowm)}")
            return False

    # ---------------------------------------------------------------------------
    def GetLibararyVersion(self, libraryname, importonly=False):
        """
        Attempts to determine the installed version of a specified Python library.

        This method employs two primary strategies:
        1. **Import and `__version__` Attribute:** It first tries to import the
           library using `importlib.import_module()`. If successful, it attempts
           to access a `__version__` attribute on the imported module, which is
           a common convention for libraries to expose their version string.
        2. **`pip show` Command:** If the import method fails (e.g., library not
           found, no `__version__` attribute) and `importonly` is False, it
           falls back to executing the command `python -m pip show <libraryname>`.
           It then parses the output of this command to find a line starting
           with "Version:", from which it extracts the version string.

        The `importonly` parameter allows restricting the check to only the import
        method, which can be faster if `pip show` is not needed or desired.

        Args:
            libraryname (str): The import name of the library (e.g., "pyserial",
                               "paho.mqtt.client", "pyowm"). This is the name
                               used in Python's `import` statement.
            importonly (bool, optional): If True, the method only attempts to
                                         get the version via import and `__version__`
                                         attribute, and does not fall back to using
                                         `pip show`. Defaults to False.

        Returns:
            str or None: The version string of the library if found (e.g., "2.10.0").
                         Returns None if the library cannot be imported, if no
                         `__version__` attribute is found (and `importonly` is True
                         or `pip show` also fails), if `pip show` fails to find the
                         package or its version, or if any other error occurs.
        """
        try:
            self.log.debug(f"Attempting to get version for library: '{libraryname}' (importonly={importonly})")
            
            # Attempt 1: Import the library and check for a __version__ attribute.
            # This is often the quickest and most direct way if the library follows conventions.
            try:
                import importlib # Standard library for dynamic imports.
                my_module = importlib.import_module(libraryname) # Dynamically import the library by its name.
                version_attr = getattr(my_module, '__version__', None) # Try to get the __version__ attribute.
                if version_attr: # If __version__ exists and is not None/empty.
                    self.log.debug(f"Found version '{str(version_attr)}' for library '{libraryname}' via importlib and __version__ attribute.")
                    return str(version_attr) # Ensure it's returned as a string.
                # If __version__ attribute is not found or is None, log it and proceed (unless importonly).
                self.log.debug(f"Module '{libraryname}' imported successfully, but no __version__ attribute was found or it was None.")
            except ImportError: # If importlib.import_module(libraryname) fails.
                self.log.info(f"Library '{libraryname}' not found via importlib (ImportError). It might not be installed.")
                if importonly: return None # If only import was requested and it failed, return None.
                # Otherwise (if not importonly), proceed to try `pip show`.
            except Exception as e_import: # Catch other potential errors during import or getattr.
                self.LogErrorLine(f"Error importing library '{libraryname}' or accessing its __version__ attribute: {str(e_import)}")
                if importonly: return None # If only import was requested and it had other errors, return None.
                # Otherwise (if not importonly), proceed to try `pip show`.

            # If `importonly` was True and we reached here, it means the import either
            # succeeded but no `__version__` was found, or the import itself failed in a way
            # other than ImportError but was caught. In such cases, honor `importonly`.
            if importonly:
                 self.log.debug(f"importonly is True and version not found via import for '{libraryname}'. Returning None without trying pip show.")
                 return None

            # Attempt 2: Use 'pip show <libraryname>' to get the version.
            # This is a fallback if the import method didn't yield a version.
            self.log.info(f"Trying to get version of library '{libraryname}' using 'pip show' command.")

            # Ensure pip itself is available, especially on Linux systems where it might not be by default.
            # This check might be somewhat redundant if CheckBaseSoftware() runs earlier in broader operational flows,
            # but it's a good safeguard here.
            if "linux" in sys.platform: # sys.platform can be 'linux', 'win32', 'darwin', etc.
                if not self.CheckBaseSoftware(): # CheckBaseSoftware logs its own errors if pip is missing/uninstalls.
                    self.log.error(f"Cannot get library version for '{libraryname}' via pip: Base software (pip) check failed. Pip might not be installed.")
                    return None # Cannot use pip show if pip itself is not working.

            # Construct the command: `python -m pip show <libraryname>`
            command_list_pip_show = [sys.executable, "-m", "pip", "show", libraryname]
            self.log.debug(f"Executing pip show command: {' '.join(command_list_pip_show)}")
            
            # Execute the command and capture output.
            process = Popen(command_list_pip_show, stdout=PIPE, stderr=PIPE)
            output_bytes, error_bytes = process.communicate() # Get stdout and stderr as bytes.
            return_code = process.returncode # Get the exit code.

            # Decode output and error streams.
            output_str = output_bytes.decode(sys.getdefaultencoding(), errors='replace').strip() if output_bytes else ""
            error_str = error_bytes.decode(sys.getdefaultencoding(), errors='replace').strip() if error_bytes else ""

            if return_code != 0: # `pip show` command failed (e.g., package not found).
                self.log.error(f"Error using 'pip show {libraryname}': Return Code={return_code}. Stderr: {error_str}")
                return None # Failed to get version via pip show.

            # Parse the output of 'pip show' for the line starting with "Version:".
            for line in output_str.splitlines():
                line = line.strip()
                if line.lower().startswith("version:"): # Case-insensitive check for "Version:".
                    version_found_str = line.split(":", 1)[1].strip() # Extract the version part.
                    self.log.info(f"Found version '{version_found_str}' for library '{libraryname}' via 'pip show'.")
                    return version_found_str # Return the found version string.
            
            # If the "Version:" line was not found in the output of `pip show`.
            self.log.info(f"Could not find 'Version:' line in 'pip show {libraryname}' output. The package might not be installed via pip, or the output format is unexpected.")
            return None # Version line not found.

        except subprocess.SubprocessError as spe: # Catch errors related to Popen/communicate itself.
            self.LogErrorLine(f"Subprocess error occurred while getting version for '{libraryname}' using pip show: {str(spe)}")
            return None
        except Exception as e_getver: # Catch any other unexpected errors during the entire process.
            self.LogErrorLine(f"Unexpected error in GetLibararyVersion for '{libraryname}': {str(e_getver)}")
            return None

    # ---------------------------------------------------------------------------
    def LibraryIsInstalled(self, libraryname):
        """
        Checks if a specified Python library is installed and can be imported.

        This method uses the `importlib.import_module()` function to attempt
        a dynamic import of the given `libraryname`. If the import is successful,
        the library is considered installed. If an `ImportError` occurs, it means
        the library is not installed or not found in the Python path.

        Args:
            libraryname (str): The import name of the library to check (e.g.,
                               "flask", "pyserial", "paho.mqtt.client"). This is
                               the name used in a Python `import` statement.

        Returns:
            bool: True if the library can be successfully imported (meaning it is
                  installed and accessible). False if an `ImportError` is raised
                  (library not installed or not found), or if any other exception
                  occurs during the import attempt (indicating a potentially
                  problematic or broken installation).
        """
        try:
            import importlib # Standard library for dynamic imports.
            importlib.import_module(libraryname) # Attempt to import the library by its name.
            # If import_module succeeds without raising an exception, the library is installed.
            self.log.debug(f"Library '{libraryname}' is installed and importable (import successful).")
            return True
        except ImportError: # Specifically catch ImportError, which clearly indicates the library is not found.
            self.log.info(f"Library '{libraryname}' is NOT installed or not found in Python path (ImportError during check).")
            return False # Library is not installed.
        except Exception as e_isinst: # Catch other potential errors during the import attempt (e.g., a broken package).
            self.LogErrorLine(f"An unexpected error occurred while checking if library '{libraryname}' is installed (e.g., import error beyond typical ImportError): {str(e_isinst)}")
            return False # Assume not installed or problematic if any other error occurs during import.

    # ---------------------------------------------------------------------------
    def InstallLibrary(self, libraryname, update=False, version=None, uninstall=False):
        """
        Installs, updates, or uninstalls a specified Python library using `pip`.

        This method constructs and executes the appropriate `pip` command
        (e.g., `pip install <lib>`, `pip install <lib>==<version>`,
        `pip install -U <lib>`, `pip uninstall <lib>`) based on the provided
        arguments. It uses `sys.executable -m pip` to ensure `pip` associated
        with the current Python interpreter is used.

        Before installation or update (but not uninstallation), it checks if
        `pip` itself is available using `self.CheckBaseSoftware()`, especially
        on Linux systems.

        Args:
            libraryname (str): The name of the library as it is known by pip
                               (e.g., "pyserial", "paho-mqtt").
            update (bool, optional): If True, attempts to update the library to
                                     the latest version (equivalent to
                                     `pip install --upgrade <libraryname>`).
                                     Defaults to False.
            version (str, optional): If a specific version string is provided
                                     (e.g., "2.10.0"), attempts to install that
                                     exact version (e.g., `pip install <libraryname>==2.10.0`).
                                     If provided, `version` takes precedence over
                                     the `update` flag. Defaults to None.
            uninstall (bool, optional): If True, attempts to uninstall the
                                        library (e.g., `pip uninstall -y <libraryname>`).
                                        Defaults to False.

        Returns:
            bool: True if the `pip` command executes successfully (return code 0).
                  False if `pip` is not available (and not uninstalling), if the
                  `pip` command fails (non-zero return code), or if any other
                  `subprocess.SubprocessError` or unexpected exception occurs.
        """
        try:
            target_library_spec = libraryname # Default pip target is just the library name.
            action_description = "install"    # Default action description for logging.
            
            # Determine the exact pip command and refine the action description based on flags.
            if uninstall:
                action_description = f"uninstalling '{libraryname}'"
                # `pip uninstall` command will be constructed later.
            elif version: # Specific version installation takes precedence over a generic update.
                target_library_spec = f"{libraryname}=={version}" # Format for specific version (e.g., libraryname==1.2.3).
                action_description = f"installing specific version '{target_library_spec}'"
            elif update: # Generic update to the latest version.
                action_description = f"updating '{libraryname}' (to latest)"
                # `pip install --upgrade` command will be constructed later.
            else: # Default action: install the library (latest version unless specified by internal pip defaults).
                action_description = f"installing '{libraryname}'"

            self.log.info(f"Attempting to perform pip operation: {action_description}.")

            # Ensure pip is available before trying to use it, unless we are uninstalling
            # (as uninstalling might be attempted even if pip's full environment is problematic).
            if "linux" in sys.platform and not uninstall: # Check on Linux, more likely to need explicit pip setup.
                if not self.CheckBaseSoftware(): # CheckBaseSoftware logs its own errors if pip is missing.
                    self.log.error(f"Cannot {action_description}: Base software (pip) check failed. Pip might not be installed or accessible.")
                    return False # Cannot proceed if pip is not available.

            # Construct the pip command list for Popen.
            # Uses `sys.executable -m pip` to invoke pip for the current Python interpreter.
            pip_command_list = [sys.executable, "-m", "pip"]
            if uninstall:
                pip_command_list.extend(["uninstall", "-y", libraryname]) # `-y` for non-interactive uninstall.
            elif update and not version: # If update=True and no specific version, then upgrade.
                pip_command_list.extend(["install", target_library_spec, "--upgrade"]) # --upgrade or -U
            else: # Standard install (could be specific version if `target_library_spec` includes `==version`).
                pip_command_list.extend(["install", target_library_spec])
            
            self.log.debug(f"Executing pip command: {' '.join(pip_command_list)}")

            # Execute the pip command and capture its output.
            process = Popen(pip_command_list, stdout=PIPE, stderr=PIPE)
            output_bytes, error_bytes = process.communicate() # Get stdout/stderr as bytes.
            return_code = process.returncode # Get exit code.

            # Decode output and error streams.
            output_str = output_bytes.decode(sys.getdefaultencoding(), errors='replace').strip() if output_bytes else ""
            error_str = error_bytes.decode(sys.getdefaultencoding(), errors='replace').strip() if error_bytes else ""

            # Check the return code from pip. Non-zero usually means an error.
            if return_code != 0:
                log_message = f"Error during pip {action_description}. Return Code: {return_code}."
                if output_str: log_message += f"\nPip stdout: {output_str}" # Include pip's stdout.
                if error_str: log_message += f"\nPip stderr: {error_str}" # Include pip's stderr.
                self.log.error(log_message)
                return False # Pip command failed.
            
            # Log stdout/stderr even on success for record-keeping, as they might contain useful info or warnings.
            if output_str: self.log.info(f"Pip {action_description} stdout:\n{output_str}")
            if error_str: self.log.info(f"Pip {action_description} stderr (RC=0, may contain warnings):\n{error_str}")

            self.log.info(f"Successfully performed pip operation: {action_description}.")
            return True # Pip command was successful.

        except subprocess.SubprocessError as spe: # Catch errors from Popen/communicate itself.
            self.LogErrorLine(f"Subprocess error during pip operation for '{libraryname}': {str(spe)}")
            return False
        except Exception as e_installlib: # Catch any other unexpected errors.
            self.LogErrorLine(f"Unexpected error in InstallLibrary for '{libraryname}': {str(e_installlib)}")
            return False

    # ---------------------------------------------------------------------------
    def ValidateConfig(self):
        """
        Validates the loaded module configurations from `CachedConfig`.

        For each enabled module, it checks:
        1. If the module script file (e.g., `genmon.py`) exists in `ModulePath` or `ModulePath/addon`.
        2. If the module's specific `.conf` files (if defined in `genloader.conf`)
           exist in `ConfigFilePath`. If a module's `.conf` file is missing in
           `ConfigFilePath` but exists in `ConfPath` (default configs), it's copied over.

        It also checks if core modules 'genmon' and 'genserv' are enabled.

        Returns:
            bool: True if all validations pass, False if any critical issue is found.
        """
        self.log.info("Validating loaded module configurations from CachedConfig...")
        any_validation_errors_found = False # Flag to track if any validation issues arise.
        if not self.CachedConfig: # Check if CachedConfig is empty (e.g., GetConfig failed critically).
            self.log.error("ValidateConfig Error: CachedConfig is empty. Cannot perform validation as no module configurations were loaded.")
            return False # Cannot validate if there's no configuration data.

        # --- Iteration through CachedConfig ---
        # Loop through each module (section_name) and its settings (dict) in the CachedConfig.
        for module_section_name, module_settings_dict in self.CachedConfig.items():
            try:
                # Only perform detailed validation if the module is marked as 'enable: True' in its config.
                # Disabled modules are not validated for script existence or their .conf files,
                # as they are not intended to be run.
                if module_settings_dict.get("enable", False): # Use .get for safe access to 'enable' key.
                    module_script_filename = module_settings_dict.get("module")
                    if not module_script_filename: # This should ideally be caught by GetConfig's defaulting.
                        self.log.error(
                            f"Validation Error for enabled module '[{module_section_name}]': 'module' (script filename) "
                            f"is not defined. Auto-disabling this module."
                        )
                        self.CachedConfig[module_section_name]["enable"] = False # Correct the config in memory.
                        any_validation_errors_found = True
                        continue # Skip further validation for this misconfigured module.

                    # --- Check for existence of module script files ---
                    # The logic searches for the module script in primary (self.ModulePath)
                    # and addon (self.ModulePath/addon) paths.
                    # GetModulePath returns the directory if found, or None if not found.
                    module_base_dir_path = self.GetModulePath(self.ModulePath, module_script_filename)
                    if module_base_dir_path is None: # GetModulePath logs details if the file is not found.
                        self.log.error(
                            f"Validation Error for enabled module '[{module_section_name}]': Module script '{module_script_filename}' "
                            f"not found in primary path ('{self.ModulePath}') or addon path ('{os.path.join(self.ModulePath, 'addon')}'). "
                            f"Auto-disabling this module."
                        )
                        self.CachedConfig[module_section_name]["enable"] = False # Correct the config in memory.
                        any_validation_errors_found = True
                        # Continue to check other modules even if one is problematic.

                # --- Process of validating associated .conf files ---
                # A module can have one or more associated `.conf` files, specified as a comma-separated
                # string in the 'conffile' setting (e.g., "genmon.conf,mycustom.conf").
                # This validation step checks if these .conf files exist in the active configuration
                # path (`self.ConfigFilePath`, e.g., /etc/genmon/).
                # If a module's .conf file is missing from `self.ConfigFilePath` but a default version
                # exists in `self.ConfPath` (the installation's default config directory),
                # it is automatically copied over to `self.ConfigFilePath`. This helps ensure
                # modules have their necessary configurations even if they were not manually set up.
                module_specific_conffiles_str = module_settings_dict.get("conffile", "")
                if module_specific_conffiles_str and len(module_specific_conffiles_str.strip()): # Check if conffile string is not empty.
                    individual_conf_filenames = module_specific_conffiles_str.split(',')
                    for conf_file_basename in individual_conf_filenames:
                        conf_file_basename = conf_file_basename.strip() # Remove whitespace.
                        if not conf_file_basename: continue # Skip if a name is empty (e.g., due to "file1,,file2").

                        # Full path to where this specific .conf file should be in the active config directory.
                        target_conf_full_path = os.path.join(self.ConfigFilePath, conf_file_basename)

                        # Check if the module's .conf file is NOT in the active config path (e.g., /etc/genmon/).
                        if not os.path.isfile(target_conf_full_path):
                            # Path to the default version of this .conf file in the installation's `conf` dir.
                            default_conf_source_full_path = os.path.join(self.ConfPath, conf_file_basename)

                            # Check if a default version of this .conf file exists.
                            if os.path.isfile(default_conf_source_full_path):
                                self.log.info(
                                    f"Validation: Config file '{conf_file_basename}' for module '[{module_section_name}]' not found in '{self.ConfigFilePath}'. "
                                    f"Attempting to copy it from default location: '{default_conf_source_full_path}'."
                                )
                                try:
                                    copyfile(default_conf_source_full_path, target_conf_full_path) # shutil.copyfile
                                    self.log.info(f"Successfully copied default config '{conf_file_basename}' to '{self.ConfigFilePath}' for module '[{module_section_name}]'.")
                                except Exception as e_copy_conf:
                                    self.log.error(f"Failed to copy default config '{conf_file_basename}' for module '[{module_section_name}]' from '{self.ConfPath}' to '{self.ConfigFilePath}': {str(e_copy_conf)}")
                                    any_validation_errors_found = True # Mark error if copy fails.
                            else:
                                # If the module is enabled, a missing .conf file (that also has no default) is an error.
                                # If the module is not enabled, it's just a warning or informational message.
                                log_method_to_use = self.log.error if module_settings_dict.get("enable", False) else self.log.warning
                                log_method_to_use(
                                    f"Validation: Config file '{conf_file_basename}' for module '[{module_section_name}]' not found in active path ('{self.ConfigFilePath}') "
                                    f"AND no default version was found in default path ('{self.ConfPath}'). This may cause issues if the module is enabled and relies on this file."
                                )
                                if module_settings_dict.get("enable", False): any_validation_errors_found = True # Error for enabled module.
            except KeyError as ke: # Catch if expected keys like 'enable' or 'module' are missing from module_settings_dict.
                self.LogErrorLine(f"Configuration validation error for module '[{module_section_name}]': Missing critical key '{str(ke)}' in its settings. This module's config might be incomplete or corrupt.")
                any_validation_errors_found = True
            except Exception as e_val_module: # Catch any other unexpected error during this specific module's validation.
                self.LogErrorLine(f"Unexpected error validating configuration for module '[{module_section_name}]': {str(e_val_module)}")
                any_validation_errors_found = True
        
        # --- Validation of essential 'genmon' and 'genserv' modules ---
        # These modules are core to the system's functionality (genmon) or user interface (genserv).
        # Their enablement status is explicitly checked.
        try:
            # Check 'genmon' (core monitoring engine). If not enabled, it's a critical error.
            if not self.CachedConfig.get("genmon", {}).get("enable", False): # Safe nested .get
                self.log.error("Critical Validation Error: Core module 'genmon' is not enabled in the configuration (genloader.conf). Genmon system cannot function correctly.")
                any_validation_errors_found = True

            # Check 'genserv' (web interface). If not enabled, it's usually informational, as genmon can run without it.
            if not self.CachedConfig.get("genserv", {}).get("enable", False):
                self.log.info("Validation Info: Web interface module 'genserv' is not enabled in genloader.conf. The Genmon web UI will be unavailable.")
                # This is not necessarily a fatal error for genloader itself, but important for the user to know.
        except KeyError as ke_core: # Should be caught by .get, but as a defensive measure.
             self.LogErrorLine(f"KeyError accessing core module ('genmon' or 'genserv') configuration during validation: {str(ke_core)}. This indicates a severely corrupted CachedConfig.")
             any_validation_errors_found = True
        except Exception as e_val_core: # Catch unexpected errors when accessing core module configs.
            self.LogErrorLine(f"Unexpected error validating core 'genmon'/'genserv' config entries: {str(e_val_core)}")
            any_validation_errors_found = True

        # Final result of validation.
        if any_validation_errors_found:
            self.log.error("Configuration validation finished with one or more errors or critical warnings. Some modules may have been auto-disabled or may not function correctly.")
        else:
            self.log.info("Configuration validation completed successfully. All checks passed for enabled modules.")
        return not any_validation_errors_found # Returns True if no errors were found, False otherwise.

    # ---------------------------------------------------------------------------
    def AddEntry(self, section=None, module=None, conffile="", args="", priority="2"):
        """
        Adds or updates a module's default configuration section in `genloader.conf`.

        If the specified `section` (typically the module's name, e.g., "genmon")
        does not already exist in `genloader.conf`, this method creates it.
        It then populates this section with default configuration values:
        - `module`: The filename of the module script (e.g., "genmon.py").
        - `enable`: Set to "False" by default, meaning the module is disabled.
        - `hardstop`: Set to "False" by default.
        - `conffile`: Comma-separated string of associated .conf file names.
        - `args`: Default command-line arguments for the module.
        - `priority`: Default load priority for the module (lower numbers can
                      mean higher priority depending on sorting logic).

        This method is primarily used by `GetConfig` to ensure that all known
        modules (defined in `valid_sections_definitions`) have at least a
        placeholder configuration in `genloader.conf`. This prevents errors if a
        new module is added to the genmon software suite but the user's
        `genloader.conf` file hasn't been manually updated to include it.
        It uses the `self.config` (a `MyConfig` instance) to write these values.

        Args:
            section (str): The name of the section to add or update in
                           `genloader.conf` (e.g., "genmon", "genserv").
                           This is mandatory.
            module (str): The filename of the module script corresponding to this
                          section (e.g., "genmon.py", "genserv.py"). This is
                          mandatory.
            conffile (str, optional): A comma-separated string of associated
                                      configuration file names for this module.
                                      Defaults to an empty string.
            args (str, optional): Default command-line arguments to be used when
                                  starting this module. Defaults to an empty string.
            priority (str, optional): Default load priority for this module.
                                      Defaults to "2". This is stored as a string
                                      but often converted to an integer later.

        Returns:
            bool: True if the configuration entry was successfully added or updated
                  in `genloader.conf`. False if `section` or `module` is None,
                  or if any other exception occurs during the write operations.
        """
        try:
            # Section and module script filename are essential for adding an entry.
            if section is None or module is None:
                self.log.error("Error in AddEntry: Both 'section' (e.g., 'genmon') and 'module' (e.g., 'genmon.py') parameters are required to add an entry to genloader.conf.")
                return False

            self.log.info(f"Adding/Updating configuration entry in genloader.conf for section '[{section}]', module script '{module}'.")

            # Use self.config (a MyConfig instance) to write values to genloader.conf.
            # MyConfig's WriteSection will create the section if it doesn't exist,
            # or set the current operating section if it does.
            self.config.WriteSection(section) 

            # Write default values for the new or existing section.
            # If the section already exists, these calls will update the values if different,
            # or add them if they are missing.
            self.config.WriteValue("module", module, section=section) # Script filename.
            self.config.WriteValue("enable", "False", section=section) # Default to disabled.
            self.config.WriteValue("hardstop", "False", section=section) # Default hardstop behavior (graceful stop).
            self.config.WriteValue("conffile", conffile, section=section) # Associated config files.
            self.config.WriteValue("args", args, section=section) # Command-line arguments.
            self.config.WriteValue("priority", str(priority), section=section) # Ensure priority is stored as a string.

            self.log.info(f"Successfully added/updated configuration entry for section '[{section}]' in genloader.conf.")
            return True
        except Exception as e_addentry: # Catch any other unexpected errors during MyConfig operations.
            self.LogErrorLine(f"Error in AddEntry while processing section '[{section}]' for genloader.conf: {str(e_addentry)}")
            return False

    # ---------------------------------------------------------------------------
    def UpdateIfNeeded(self):
        """
        Performs necessary updates to the `genloader.conf` file structure or
        specific values within it. This method is crucial for handling configuration
        migrations, ensuring backward compatibility, and setting up new installations.

        Key tasks performed:
        1.  **Ensure `conffile` for GPIO modules:** It checks if the `gengpioin`
            and `gengpio` sections in `genloader.conf` have a `conffile` entry.
            If missing, it adds the default (`gengpioin.conf` or `gengpio.conf`).
            This is important as these modules rely on their specific config files.
        2.  **Version Check and Upgrade Logic:**
            - It reads the `version` from the `[genloader]` section of `genloader.conf`.
            - If the version is missing or is "0.0.0" (an old default), it flags
              this as a new installation by setting `self.NewInstall = True`.
            - It compares this config version with the current program version
              (defined in `ProgramDefaults.GENMON_VERSION`).
            - If the config version is older than the program version, it sets
              `self.Upgrade = True`.
            - If it's a new install or an upgrade, it updates the `version` in
              `genloader.conf` to the current program version.
        3.  **Post-Install/Upgrade Tasks:** If `self.NewInstall` is True, it calls
            `self.FixPyOWMMaintIssues()` to handle potential compatibility problems
            with the `pyowm` library, which is common on fresh setups.

        This method uses `self.config` (a `MyConfig` instance) to interact with
        `genloader.conf`.

        Returns:
            bool: True if all update checks and necessary modifications were
                  processed successfully (even if no actual changes were made to
                  the file because it was already up-to-date). False if a
                  critical error occurs during file operations or version checks.
        """
        try:
            self.log.info("Performing UpdateIfNeeded checks for genloader.conf structure and version compatibility...")
            
            # --- Ensure 'conffile' for GPIO Modules ---
            # For 'gengpioin' module:
            self.config.SetSection("gengpioin") # Set MyConfig's current operating section to 'gengpioin'.
            # Check if 'conffile' option exists or if its value is empty.
            # suppress_logging_on_error=True for ReadValue prevents MyConfig from logging an error if the option is simply missing,
            # as we are checking its existence here.
            if not self.config.HasOption("conffile") or not self.config.ReadValue("conffile", default="", suppress_logging_on_error=True):
                self.config.WriteValue("conffile", "gengpioin.conf", section="gengpioin") # Write the default conffile name.
                self.log.info("Updated 'gengpioin' section in genloader.conf: set 'conffile' to 'gengpioin.conf' as it was missing or empty.")

            # For 'gengpio' module:
            self.config.SetSection("gengpio") # Switch MyConfig's section context.
            if not self.config.HasOption("conffile") or not self.config.ReadValue("conffile", default="", suppress_logging_on_error=True):
                self.config.WriteValue("conffile", "gengpio.conf", section="gengpio")
                self.log.info("Updated 'gengpio' section in genloader.conf: set 'conffile' to 'gengpio.conf' as it was missing or empty.")

            # --- Version Check and Upgrade Logic ---
            self.config.SetSection("genloader") # Operate on the [genloader] section for version info.
            # Read the current version from genloader.conf. Default to "0.0.0" if missing (helps identify new/old installs).
            current_config_version_str = self.config.ReadValue("version", default="0.0.0", suppress_logging_on_error=True)
            
            # If version is missing (ReadValue returned default "0.0.0" because key wasn't there) or explicitly "0.0.0",
            # assume it's a new installation or a very old configuration that needs full setup.
            if not current_config_version_str or current_config_version_str == "0.0.0":
                self.log.info("No version found in genloader.conf [genloader] section, or version is '0.0.0'. Assuming this is a new installation or a very old configuration.")
                self.NewInstall = True # Flag this as a new install.
                current_config_version_str = "0.0.0" # Normalize for comparison logic below.

            # Compare the version found in genloader.conf with the current program version from ProgramDefaults.
            # VersionTuple converts strings like "1.2.3" to comparable tuples (1, 2, 3).
            if self.VersionTuple(current_config_version_str) < self.VersionTuple(ProgramDefaults.GENMON_VERSION):
                self.log.info(f"Current genloader.conf version '{current_config_version_str}' is older than program version '{ProgramDefaults.GENMON_VERSION}'. Marking for upgrade.")
                self.Upgrade = True # Flag this as an upgrade.
            
            # If it's a new install or an upgrade, update the version string in genloader.conf to the current program version.
            if self.NewInstall or self.Upgrade:
                self.log.info(f"Updating 'version' entry in [genloader] section of genloader.conf to '{ProgramDefaults.GENMON_VERSION}'.")
                self.config.WriteValue("version", ProgramDefaults.GENMON_VERSION, section="genloader") # Write the new version.
            
            # --- Post-Install/Upgrade Tasks ---
            # If it's determined to be a new install, perform specific maintenance tasks, like fixing PyOWM version.
            if self.NewInstall: 
                self.log.info("New install detected (or very old config): Running one-time maintenance for PyOWM library compatibility.")
                if not self.FixPyOWMMaintIssues(): # FixPyOWMMaintIssues logs its own success/failure.
                    self.log.error("FixPyOWMMaintIssues failed during new install setup. This might affect weather-related functionality if pyowm is used.")
                    # This failure might not be fatal for genloader itself, so we log the error and continue.
                    # However, it's an important warning.

            self.version = ProgramDefaults.GENMON_VERSION # Update Loader's internal 'version' attribute to current program version.
            self.log.info("UpdateIfNeeded checks and necessary updates for genloader.conf completed.")
            return True # Indicate successful processing.
        except Exception as e_updateif: # Catch any other unexpected errors during MyConfig operations or logic.
            self.LogErrorLine(f"Unexpected error in UpdateIfNeeded while processing genloader.conf: {str(e_updateif)}")
            return False # Indicate failure.

    # ---------------------------------------------------------------------------
    def GetConfig(self):
        """
        Loads module configurations from `genloader.conf` into `self.CachedConfig`.

        This critical method performs several steps:
        1. Reads all sections from `genloader.conf`.
        2. Ensures that all known/expected modules (defined in `valid_sections_definitions`)
           have a corresponding section in the file. If a section is missing, `AddEntry`
           is called to create it with default (disabled) settings.
        3. Calls `UpdateIfNeeded` to handle version checks and necessary config updates.
        4. Re-reads sections (in case `AddEntry` or `UpdateIfNeeded` modified the file).
        5. For each section (module):
           - Reads settings like 'module' (script name), 'enable', 'hardstop',
             'conffile', 'args', 'priority', 'postloaddelay', and 'pid'.
           - Uses defaults for missing optional settings and logs errors for missing
             critical settings.
           - Populates `self.CachedConfig` with a dictionary of these settings for each module.
        
        Returns:
            bool: True if configuration is loaded and parsed successfully, False on critical error.
        """
        try:
            self.log.info("Starting to load and cache configuration from genloader.conf.")
            # --- Initial reading of sections and recovery mechanism ---
            # First, get all section names currently present in `genloader.conf`.
            # MyConfig's GetSections() method is used for this.
            current_sections = self.config.GetSections()
            if not current_sections: # This condition means genloader.conf might be empty, corrupt, or inaccessible.
                self.log.error("No sections found in genloader.conf. File might be empty, corrupt, or inaccessible by MyConfig.")
                # Attempt to recover by copying the default `genloader.conf` from the installation directory.
                # This is a critical recovery step if the primary config file is unusable.
                if not self.CopyConfFile(): # CopyConfFile logs its own errors on failure.
                    self.log.error("Attempt to copy default genloader.conf failed after finding no sections. Cannot proceed with GetConfig.")
                    return False # Fail GetConfig if recovery also fails.
                # After a successful copy, try to get sections again from the newly copied file.
                current_sections = self.config.GetSections()
                if not current_sections: # If there are still no sections, the problem is persistent and critical.
                    self.log.error("Still no sections after attempting to copy default config. GetConfig cannot proceed. The default file might also be problematic or MyConfig is failing.")
                    return False
            
            # --- valid_sections_definitions: Ensuring default entries for known modules ---
            # This dictionary defines all standard genmon modules and their default properties
            # (script name, associated config file, load priority).
            # Its purpose is to ensure that `genloader.conf` contains an entry (section) for every known module.
            # If a section for a known module is missing, `AddEntry` will be called to create it
            # with default settings (typically, `enable = False`). This prevents errors if a new
            # module is added to the genmon suite but the user's `genloader.conf` hasn't been updated yet.
            valid_sections_definitions = {
                "genmon": {"module": "genmon.py", "priority": "100", "conffile": "genmon.conf"}, # Core monitoring engine
                "genserv": {"module": "genserv.py", "priority": "90", "conffile": "genserv.conf"}, # Web server interface
                "gengpio": {"module": "gengpio.py", "conffile": "gengpio.conf"}, # General Purpose I/O (outputs)
                "gengpioin": {"module": "gengpioin.py", "conffile": "gengpioin.conf"}, # General Purpose I/O (inputs)
                "genlog": {"module": "genlog.py"}, # Logging module (often to file or syslog)
                "gensms": {"module": "gensms.py", "conffile": "gensms.conf"}, # SMS via cloud services (e.g., Twilio)
                "gensms_modem": {"module": "gensms_modem.py", "conffile": "mymodem.conf"}, # SMS via GSM modem
                "genpushover": {"module": "genpushover.py", "conffile": "genpushover.conf"}, # Pushover notifications
                "gensyslog": {"module": "gensyslog.py"}, # Forwarding to syslog
                "genmqtt": {"module": "genmqtt.py", "conffile": "genmqtt.conf"}, # MQTT publisher
                "genmqttin": {"module": "genmqttin.py", "conffile": "genmqttin.conf"}, # MQTT subscriber
                "genslack": {"module": "genslack.py", "conffile": "genslack.conf"}, # Slack notifications
                "gencallmebot": {"module": "gencallmebot.py", "conffile": "gencallmebot.conf"}, # CallMeBot notifications
                "genexercise": {"module": "genexercise.py", "conffile": "genexercise.conf"}, # Generator exercise scheduler
                "genemail2sms": {"module": "genemail2sms.py", "conffile": "genemail2sms.conf"}, # Email-to-SMS gateways
                "gentankutil": {"module": "gentankutil.py", "conffile": "gentankutil.conf"}, # Tank utility monitoring
                "gencentriconnect": {"module": "gencentriconnect.py", "conffile": "gencentriconnect.conf"}, # CentriConnect integration
                "gentankdiy": {"module": "gentankdiy.py", "conffile": "gentankdiy.conf"}, # DIY tank monitoring
                "genalexa": {"module": "genalexa.py", "conffile": "genalexa.conf"}, # Amazon Alexa integration
                "gensnmp": {"module": "gensnmp.py", "conffile": "gensnmp.conf"}, # SNMP agent/poller
                "gentemp": {"module": "gentemp.py", "conffile": "gentemp.conf"}, # Temperature sensor integration
                "gengpioledblink": {"module": "gengpioledblink.py", "conffile": "gengpioledblink.conf"}, # LED blinking via GPIO
                "gencthat": {"module": "gencthat.py", "conffile": "gencthat.conf"}, # Specific hardware hat support
                "genmopeka": {"module": "genmopeka.py", "conffile": "genmopeka.conf"}, # Mopeka tank sensors
                "gencustomgpio": {"module": "gencustomgpio.py", "conffile": "gencustomgpio.conf"}, # Custom GPIO configurations
                "gensms_voip": {"module": "gensms_voip.py", "conffile": "gensms_voip.conf"}, # SMS via VoIP providers
                "genloader": {}, # Special section for genloader's own metadata (e.g., version), not a loadable module.
            }
            
            config_was_modified_by_addentry = False # Flag to track if AddEntry modified genloader.conf.
            # Ensure all predefined valid sections exist in genloader.conf.
            for section_name, defaults_for_section in valid_sections_definitions.items():
                if section_name not in current_sections: # If a defined section is missing from the current file...
                    if section_name == "genloader": # The [genloader] section is essential for metadata.
                        self.log.info(f"Essential configuration section '[{section_name}]' is missing. Adding section header to genloader.conf.")
                        self.config.WriteSection(section_name) # MyConfig handles creation if not exists.
                        config_was_modified_by_addentry = True
                    elif defaults_for_section.get("module"): # Only add if 'module' is defined (i.e., it's a loadable module).
                        self.log.info(f"Configuration section '[{section_name}]' for module '{defaults_for_section['module']}' is missing in genloader.conf. Adding default (disabled) entry.")
                        # Call AddEntry to create the section with default values.
                        if self.AddEntry(section=section_name, module=defaults_for_section["module"],
                                         conffile=defaults_for_section.get("conffile", ""), # Use .get for optional keys.
                                         priority=defaults_for_section.get("priority", "2")): # AddEntry logs its own success/failure.
                            config_was_modified_by_addentry = True
                        else:
                             self.log.error(f"Failed to add default entry for missing section '[{section_name}]' to genloader.conf. Config may be incomplete for this module.")
            
            if config_was_modified_by_addentry: # If sections were added, the list of current sections in the file has changed.
                current_sections = self.config.GetSections() # Refresh the list.

            # --- Role of UpdateIfNeeded within configuration loading ---
            # UpdateIfNeeded performs several important tasks:
            # 1. Ensures specific modules (like gengpioin, gengpio) have their 'conffile' entries correctly set if missing.
            # 2. Checks the 'version' in the [genloader] section of `genloader.conf` against the current program version.
            #    - If the config version is older or missing, it updates the version in the file.
            #    - It sets `self.NewInstall` or `self.Upgrade` flags, which can trigger other actions (e.g., FixPyOWMMaintIssues).
            # This step is crucial for handling config migrations, updates, and ensuring compatibility.
            if not self.UpdateIfNeeded(): # UpdateIfNeeded logs its own errors if issues occur.
                self.log.error("UpdateIfNeeded reported errors during GetConfig. Configuration might be inconsistent, outdated, or fail to update correctly.")
                # Depending on the severity of errors in UpdateIfNeeded, one might consider returning False here.
                # For now, it proceeds, but the config might not be ideal.

            current_sections = self.config.GetSections() # Re-fetch sections again, as UpdateIfNeeded might also modify the config.
            temp_cached_config = {} # Temporary dictionary to build the new CachedConfig.

            # --- Process of iterating through sections to populate CachedConfig ---
            # This loop iterates through each section name found in `genloader.conf`.
            # For each section (representing a module):
            # - It reads all relevant settings: 'module' (script name), 'enable' (True/False),
            #   'hardstop', 'conffile' (associated .conf files), 'args' (command-line arguments),
            #   'priority' (for load order), 'postloaddelay', and 'pid' (process ID if running).
            # - For optional settings that might be missing from the config file, it uses default values
            #   (e.g., priority defaults to 99, postloaddelay to 0). This ensures that CachedConfig
            #   always has a complete set of keys for each module, simplifying later access.
            # - Critical settings like 'module' (the script filename) are logged with an error if missing,
            #   and a placeholder like "unknown_module.py" is used.
            # - The collected settings for each module are stored as a dictionary within `temp_cached_config`,
            #   keyed by the module's section name.
            for section_name in current_sections:
                if section_name == "genloader": 
                    continue # Skip the [genloader] section; it contains metadata, not a runnable module.
                
                settings_dict_for_module = {} # Dictionary to store settings for the current module.
                self.config.SetSection(section_name) # Set MyConfig's context to this section for subsequent reads.

                # Helper function to read configuration values with type conversion, defaults, and logging for missing critical keys.
                # This centralizes the logic for reading and defaulting module settings.
                def _read_config_value(key, expected_type=str, default_val=None, is_critical=True, suppress_log_on_missing=False):
                    if self.config.HasOption(key): # Check if the key exists in the current section.
                        try:
                            # Use MyConfig's ReadValue for robust, typed reading.
                            # suppress_logging_on_error in ReadValue handles cases where the key exists but its value is of an incorrect type.
                            if expected_type == bool: return self.config.ReadValue(key, return_type=bool, default=default_val, suppress_logging_on_error=suppress_log_on_missing)
                            if expected_type == int: return self.config.ReadValue(key, return_type=int, default=default_val, suppress_logging_on_error=suppress_log_on_missing)
                            return self.config.ReadValue(key, default=default_val, suppress_logging_on_error=suppress_log_on_missing) # Default is string.
                        except ValueError as ve: # Should ideally be caught by MyConfig's ReadValue, but as a safeguard.
                            self.log.error(f"ValueError reading key '{key}' in section '[{section_name}]' from genloader.conf: {str(ve)}. Using default value: '{default_val}'.")
                            return default_val
                    # Handle missing keys based on whether they are critical or optional.
                    elif is_critical and not suppress_log_on_missing:
                        self.log.error(f"Missing critical config key '{key}' in section '[{section_name}]' of genloader.conf. Using default value: '{default_val}'. This module might not function correctly.")
                    elif not suppress_log_on_missing: # Log at debug level for missing non-critical (optional) keys.
                        self.log.debug(f"Optional config key '{key}' not found in section '[{section_name}]' of genloader.conf. Using default value: '{default_val}'.")
                    return default_val # Return the default value if key is missing or error occurs.

                # Read all known settings for the current module using the helper.
                settings_dict_for_module["module"] = _read_config_value("module", is_critical=True, default_val="unknown_module.py")
                settings_dict_for_module["enable"] = _read_config_value("enable", expected_type=bool, default_val=False)
                settings_dict_for_module["hardstop"] = _read_config_value("hardstop", expected_type=bool, default_val=False)
                settings_dict_for_module["conffile"] = _read_config_value("conffile", default_val="", is_critical=False) # Comma-separated list of config files.
                settings_dict_for_module["args"] = _read_config_value("args", default_val="", is_critical=False) # Command-line arguments.
                settings_dict_for_module["priority"] = _read_config_value("priority", expected_type=int, default_val=99, is_critical=False) # Load order priority.
                settings_dict_for_module["postloaddelay"] = _read_config_value("postloaddelay", expected_type=int, default_val=0, is_critical=False) # Delay after loading.
                settings_dict_for_module["pid"] = _read_config_value("pid", expected_type=int, default_val=0, is_critical=False, suppress_log_on_missing=True) # PID; often not present or 0.

                # If the module script is "unknown_module.py" (meaning 'module' key was missing or invalid)
                # but the module is marked as 'enable: True', then auto-disable it to prevent errors, as it cannot be started.
                if settings_dict_for_module["module"] == "unknown_module.py" and settings_dict_for_module["enable"]:
                     self.log.warning(f"Module '{section_name}' is enabled in genloader.conf, but its 'module' (script filename) is not specified or missing. Auto-disabling this module.")
                     settings_dict_for_module["enable"] = False # Override 'enable' to False.

                temp_cached_config[section_name] = settings_dict_for_module # Add this module's settings to the cache.
            
            self.CachedConfig = temp_cached_config # Assign the fully populated temporary cache to the instance's CachedConfig.
            self.log.info(f"Successfully loaded and cached configuration for {len(self.CachedConfig)} modules from genloader.conf.")
            return True # Indicate success.

        except Exception as e_getconf: # Catch any other unexpected critical error during GetConfig.
            self.LogErrorLine(f"Unexpected critical error in GetConfig: {str(e_getconf)}")
            self.CachedConfig = {} # Clear cache on error to ensure a consistent (empty) state.
            return False # Indicate failure.

    # ---------------------------------------------------------------------------
    def ConvertToInt(self, value, default=None):
        """
        Safely converts a value to an integer.

        If the value is None, or if conversion to integer fails (e.g., the value
        is a non-numeric string), it returns the specified default value.
        It handles potential `ValueError` during the `int()` conversion.

        Args:
            value (any): The value to convert to an integer. It's first cast to
                         a string to handle various input types robustly before
                         attempting conversion to `int`.
            default (int, optional): The default value to return if the input `value`
                                     is None or if the conversion to an integer fails.
                                     Defaults to None.

        Returns:
            int or None: The converted integer if successful, otherwise the `default` value.
        """
        if value is None: # Handle None input directly.
            return default
        try:
            # First, cast the value to a string. This makes the conversion more robust
            # if `value` is not already a string or number (e.g., if it's a boolean).
            # Then, attempt to convert the string representation to an integer.
            return int(str(value))
        except ValueError:
            # If int(str(value)) raises a ValueError (e.g., value was "abc" or "1.23"),
            # it means the string could not be converted to a valid integer.
            self.log.info(f"Could not convert value '{value}' (original type: {type(value)}) to an integer. Returning default value '{default}'.")
            return default
        except Exception as e_convert: # Catch any other unexpected errors during conversion.
            self.LogErrorLine(f"Unexpected error converting value '{value}' to int: {str(e_convert)}. Returning default '{default}'.")
            return default

    # ---------------------------------------------------------------------------
    def GetLoadOrder(self):
        """
        Determines the order in which modules should be loaded (started) and
        unloaded (stopped), based on their 'priority' setting in `genloader.conf`.

        This method iterates through `self.CachedConfig` (which should be
        populated by `GetConfig` before this is called). For each module, it
        reads the 'priority' value. This priority is expected to be an integer;
        if it's missing or invalid, a default priority (99, typically low) is assigned.

        Modules are then sorted based on these priorities. The sorting logic is:
        -   **Primary Key: Priority (Descending):** Modules with a numerically
            higher 'priority' value are considered more important and will appear
            earlier in the returned list. This means they are started *last* (when
            `StartModules` reverses this list) and stopped *first* (when
            `StopModules` uses this list directly). This ensures that core modules
            (e.g., genmon with priority 100) are started after their dependencies
            (e.g., genlog with priority 2) and stopped before them.
        -   **Secondary Key: Module Name (Ascending):** If two modules have the
            same priority, they are sorted alphabetically by their section name
            (module name) for a stable and predictable order.

        The resulting sorted list of module names is stored in `self.LoadOrder`
        by the `__init__` method after calling this.

        Returns:
            list of str: A list of module names (section names from `genloader.conf`)
                         sorted according to the priority logic described above.
                         Returns an empty list if `CachedConfig` is empty or if
                         an unexpected critical error occurs during processing.
        """
        load_order_list_intermediate = [] # Will hold (module_name, priority_value) tuples.
        priority_dict_for_sorting = {} # Temporary dictionary: {module_name: priority_value}

        try:
            if not self.CachedConfig: # Check if CachedConfig has been populated.
                self.log.error("Cannot determine module load order: CachedConfig is empty. GetConfig might have failed or found no modules.")
                return [] # Return an empty list if no configuration was loaded.

            # Populate priority_dict_for_sorting from the CachedConfig.
            # For each module, extract its 'priority' setting.
            for module_name, module_settings in self.CachedConfig.items():
                try:
                    priority_str_from_config = module_settings.get("priority") # Priority from config (usually a string).

                    if priority_str_from_config is None: # Handle cases where the 'priority' key is missing.
                        # Assign a default low priority if not specified.
                        priority_numeric_value = 99
                        self.log.info(f"Module '[{module_name}]' has no 'priority' set in genloader.conf. Defaulting to priority {priority_numeric_value}.")
                    else:
                        # Convert the priority string to an integer. Use default (99) if conversion fails.
                        priority_numeric_value = self.ConvertToInt(priority_str_from_config, 99) # ConvertToInt handles logging for conversion issues.
                        # Log if ConvertToInt defaulted, but the original string was not "99", indicating a potential misconfiguration.
                        if priority_numeric_value == 99 and str(priority_str_from_config).strip() != "99":
                             self.log.info(f"Priority value '{priority_str_from_config}' for module '[{module_name}]' in genloader.conf was invalid or non-integer. Defaulted to priority {priority_numeric_value}.")
                    
                    priority_dict_for_sorting[module_name] = priority_numeric_value
                except KeyError as ke: # Should be caught by .get(), but as a defensive measure.
                    self.LogErrorLine(f"KeyError while processing priority for module '[{module_name}]': {str(ke)}. Assigning default priority 99.")
                    priority_dict_for_sorting[module_name] = 99 # Default priority on error.
                except Exception as e_module_prio: # Catch any other unexpected errors for this specific module's priority.
                    self.LogErrorLine(f"Unexpected error processing priority for module '[{module_name}]': {str(e_module_prio)}. Assigning default priority 99.")
                    priority_dict_for_sorting[module_name] = 99 # Default priority on error.
            
            # Sort the modules based on priority.
            # Primary sort key: priority value (descending, so higher numbers come first).
            #   Lambda `item: -item[1]` achieves descending sort by numeric priority.
            # Secondary sort key: module name (ascending, for stable sort if priorities are equal).
            #   Lambda `item: item[0]` provides alphabetical sort by module name.
            # This means:
            #   - genmon (priority 100) will come before genserv (priority 90).
            #   - genlog (priority 2) will come after genserv (priority 90).
            #   - If two modules have the same priority, they are sorted by name (e.g., modA before modB).
            sorted_module_tuples = sorted(
                priority_dict_for_sorting.items(), # Items are (module_name, priority_value)
                key=lambda item: (-item[1], item[0]) # Sort by priority (desc) then name (asc)
            )
            
            # Extract just the module names into the final list.
            final_load_order_list = [module_name for module_name, _ in sorted_module_tuples]

            if final_load_order_list:
                self.log.info(f"Determined module load/stop order (higher priority number = stop first / start last): {', '.join(final_load_order_list)}")
            else:
                self.log.info("No modules found in cached config to determine load order, or all had errors preventing processing.")
            return final_load_order_list

        except Exception as e_loadorder: # Catch any other unexpected critical error in GetLoadOrder.
            self.LogErrorLine(f"Unexpected critical error in GetLoadOrder: {str(e_loadorder)}")
            return [] # Return an empty list on a critical error.

    # ---------------------------------------------------------------------------
    def StopModules(self):
        """
        Stops all configured modules according to their load order.

        Iterates through `self.LoadOrder` (which is typically sorted such that
        higher priority modules are stopped last). For each module, it calls
        `UnloadModule` with appropriate parameters (PID, HardStop flag).

        Returns:
            bool: True if all modules were processed for stopping without critical
                  errors for every module, False if any module stop attempt
                  resulted in a failure logged by `UnloadModule` or other exception.
                  Note: Success here means the stop *process* was attempted for all;
                  individual modules might still fail to stop cleanly.
        """
        self.LogConsole("Attempting to stop modules...")
        if not self.LoadOrder: # Check if LoadOrder is populated.
            self.log.info("No modules found in the load order (LoadOrder is empty). Nothing to stop.")
            return True # Considered successful as there's no work to do.

        all_processing_successful = True # Flag to track if all stop operations are processed without error.
        # --- Iteration through LoadOrder for stopping modules ---
        # Modules are stopped in the order they appear in `self.LoadOrder`.
        # `self.LoadOrder` is sorted such that higher priority numbers appear earlier.
        # For example, if LoadOrder is [genmon (100), genserv (90), genlog (2)],
        # this loop will attempt to stop `genmon` first, then `genserv`, then `genlog`.
        # This means core applications (higher priority) are stopped before their dependencies or helpers (lower priority).
        for module_name_to_stop in self.LoadOrder:
            try:
                module_config = self.CachedConfig.get(module_name_to_stop)
                if not module_config: # Should not occur if config loading was successful.
                    self.log.error(f"Could not find configuration settings for module '{module_name_to_stop}' in CachedConfig during stop operation. Skipping this module.")
                    all_processing_successful = False
                    continue # Move to the next module.

                module_script_filename = module_config.get("module")
                pid_to_stop_from_conf = module_config.get("pid") # Get PID from genloader.conf (might be 0 or missing).

                # --- How effective_hard_stop is determined ---
                # The `HardStop` flag determines if a graceful stop (e.g., SIGTERM) or a forceful stop (e.g., SIGKILL) is used.
                # Priority for HardStop:
                # 1. If the module's own 'hardstop' setting in `genloader.conf` is True, that takes precedence.
                # 2. Otherwise, the global `self.HardStop` flag (set from command-line arguments like -z) is used.
                # This allows fine-grained control per module, with a global override.
                effective_hard_stop = module_config.get("hardstop", False) or self.HardStop

                if not module_script_filename: # Should be caught by GetConfig/ValidateConfig.
                    self.log.error(f"Module script filename ('module' key) not defined for '{module_name_to_stop}' in its configuration. Cannot determine what to stop. Skipping.")
                    all_processing_successful = False
                    continue
                
                self.log.info(f"Processing stop for module '{module_name_to_stop}' (Script: {module_script_filename}, PID from conf: {pid_to_stop_from_conf if pid_to_stop_from_conf else 'N/A'}, EffectiveHardStop: {effective_hard_stop}).")

                # --- Call to UnloadModule ---
                # UnloadModule handles the actual process of sending a stop signal (kill or pkill).
                # It needs the module's script name (for pkill if PID is not used/valid) and PID (if available).
                # `UsePID` is True if a valid, non-zero PID was found in the configuration.
                if not self.UnloadModule(
                    module_script_filename,   # Script name, used for pkill if PID is not effective.
                    pid=pid_to_stop_from_conf, # PID read from genloader.conf.
                    HardStop=effective_hard_stop, # Calculated hard stop flag.
                    UsePID=bool(pid_to_stop_from_conf and int(pid_to_stop_from_conf) != 0) # True if PID is present and non-zero.
                ):
                    # UnloadModule logs its own detailed errors.
                    self.log.error(f"Error occurred while trying to stop module '{module_name_to_stop}'. Check previous logs from UnloadModule for details.")
                    all_processing_successful = False # Mark that at least one module had issues stopping.
                else:
                    self.log.info(f"Successfully processed stop signal for module '{module_name_to_stop}'. PID in config will be cleared.")
            except KeyError as ke: # Safeguard if a critical key is unexpectedly missing from module_config.
                self.LogErrorLine(f"Missing critical key '{str(ke)}' in settings for module '{module_name_to_stop}' during stop operation. Skipping this module.")
                all_processing_successful = False
            except Exception as e_stopmodule: # Catch any other unexpected error during this module's stop process.
                self.LogErrorLine(f"Unexpected error occurred while stopping module '{module_name_to_stop}': {str(e_stopmodule)}")
                all_processing_successful = False
        
        # After attempting to stop all modules:
        if all_processing_successful:
            self.LogConsole("All modules have been processed for stopping successfully.")
        else:
            self.LogConsole("Finished processing modules for stopping, but one or more errors occurred, or some modules might not have stopped cleanly. Please check logs.")
        return all_processing_successful

    # ---------------------------------------------------------------------------
    def GetModulePath(self, base_module_path, module_filename):
        """
        Determines the correct directory path for a given module script file.

        This method searches for the `module_filename` in two locations:
        1.  The `base_module_path`: This is typically `self.ModulePath`, which is
            the directory where `genloader.py` and core genmon module scripts
            (like `genmon.py`, `genserv.py`) reside.
        2.  An `addon` subdirectory within `base_module_path`: This allows users
            to place custom or third-party modules in an `addon` folder, keeping
            them separate from the core scripts. For example, if `base_module_path`
            is `/opt/genmon/`, this would be `/opt/genmon/addon/`.

        If the `module_filename` is found in either of these locations, the
        method returns the directory path where it was found. If the file is
        not found in either location, or if the input arguments are invalid
        (e.g., empty `module_filename`), it returns None.

        Args:
            base_module_path (str): The primary directory to search for the module
                                    script (e.g., `self.ModulePath`).
            module_filename (str): The filename of the module script to find
                                   (e.g., "genmon.py", "my_custom_addon.py").

        Returns:
            str or None: The absolute directory path where the `module_filename`
                         was found (this will be either `base_module_path` or
                         the `addon` subdirectory within it).
                         Returns None if `module_filename` is empty, if
                         `base_module_path` is not specified, if the module
                         file is not found in either search location, or if an
                         unexpected error occurs during path operations.
        """
        try:
            # Validate input parameters.
            if not module_filename: 
                self.log.error("GetModulePath Error: module_filename parameter is empty or None. Cannot determine path.")
                return None
            if not base_module_path: # Should ideally always be provided by the caller (self.ModulePath).
                 self.log.error(f"GetModulePath Error: base_module_path parameter is not specified for module '{module_filename}'. Cannot determine path.")
                 return None

            # Search Location 1: In the base module path itself (e.g., /opt/genmon/genmon.py)
            # Construct the full path to check.
            primary_path_to_check = os.path.join(base_module_path, module_filename)
            if os.path.isfile(primary_path_to_check): # Check if a file exists at this path.
                self.log.debug(f"Module script '{module_filename}' found at primary path: '{base_module_path}'")
                return base_module_path # Return the directory path where it was found.

            # Search Location 2: In the 'addon' subdirectory within the base module path (e.g., /opt/genmon/addon/myaddon.py)
            addon_directory_path = os.path.join(base_module_path, "addon") # Path to the addon directory.
            addon_module_full_path_to_check = os.path.join(addon_directory_path, module_filename) # Full path to module in addon dir.
            if os.path.isfile(addon_module_full_path_to_check): # Check if a file exists here.
                self.log.debug(f"Module script '{module_filename}' found in addon path: '{addon_directory_path}'")
                return addon_directory_path # Return the addon directory path.

            # If the module file was not found in either location.
            self.log.info(f"Module script file '{module_filename}' was not found in the primary path ('{base_module_path}') or in the addon path ('{addon_directory_path}').")
            return None # Module not found.
        except Exception as e_getpath: # Catch any other unexpected errors (e.g., OS errors during path operations).
            self.LogErrorLine(
                f"Unexpected error in GetModulePath while searching for module '{module_filename}' with base path '{base_module_path}': {str(e_getpath)}"
            )
            return None # Indicate failure.

    # ---------------------------------------------------------------------------
    def StartModules(self):
        """
        Starts all enabled modules according to their load order.

        Iterates through `self.LoadOrder` in reverse (so higher priority modules,
        which appear earlier in `LoadOrder` due to sorting, are started last,
        which is typical for dependencies, e.g. genmon core starts after its data sources).
        For each enabled module:
        - Checks if it's already running (if `multi_instance` is False) and attempts
          to stop it if so.
        - Calls `LoadModule` to launch the module script.
        - Handles `postloaddelay` if specified.

        Args:
            multi_instance (bool): This parameter was removed from the method signature
                                   as it's now fetched from `MySupport.GetGenmonInitInfo`
                                   in the `if __name__ == "__main__"` block and used
                                   as a global or passed differently if needed.
                                   The class attribute or a direct fetch should be used.
                                   **Correction**: `multi_instance` is not a class attribute.
                                   It's fetched in `__main__`. For `StartModules` to use it,
                                   it should ideally be passed or set as an instance attribute.
                                   Assuming `MySupport.IsRunning` handles its `multi_instance`
                                   parameter if it's a static method or has access.
                                   The original code implies `multi_instance` is a global
                                   or accessible variable. For this refactor, we'll assume
                                   `MySupport.IsRunning` can access this information or
                                   it's passed to it appropriately if it's not static.
                                   The provided snippet for `IsRunning` shows it as a method
                                   that takes `multi_instance` as an argument.
                                   This means `StartModules` needs access to this value.
                                   **Re-correction**: `multi_instance` is fetched in `__main__`
                                   and NOT directly available to this method as an instance var
                                   unless passed to `__init__` or another method.
                                   The original code had `multi_instance` as a local in `__main__`
                                   and then called `MySupport.IsRunning` with it.
                                   This means `Loader.StartModules` as written in the original
                                   cannot directly use `multi_instance` unless it's made an
                                   instance variable. This refactor will assume `MySupport.IsRunning`
                                   is called with the correct `multi_instance` value if needed,
                                   or that the logic here is simplified if `multi_instance` is
                                   globally true for genloader-managed processes.
                                   **Final approach**: The `multi_instance` variable is obtained in `__main__`
                                   and then passed to `MySupport.IsRunning`. This method, `StartModules`,
                                   will call `MySupport.IsRunning` and needs that `multi_instance` flag.
                                   It should be an attribute of the `Loader` class, set from `__main__`.
                                   For now, I will add a placeholder comment.


        Returns:
            bool: True if all enabled modules were attempted to start without critical
                  errors reported by `LoadModule`. False otherwise.
        """
        self.LogConsole("Starting modules...")
        if not self.LoadOrder: # Check if there are any modules defined in the load order.
            self.log.error("Error starting modules: LoadOrder is empty. No modules to start.")
            return False # Cannot start if LoadOrder is not populated.

        any_module_start_failed = False # Flag to track if any module fails to start.

        # --- Logic for iterating through LoadOrder (reversed for starting) ---
        # Modules are started in the REVERSE of `self.LoadOrder`.
        # `self.LoadOrder` is sorted such that higher priority numbers appear earlier.
        # For example, if LoadOrder is [genmon (100), genserv (90), genlog (2)],
        # then `reversed(self.LoadOrder)` will be [genlog, genserv, genmon].
        # This means modules with lower priority numbers (dependencies, helpers) are started first,
        # and modules with higher priority numbers (core applications like genmon) are started last.
        # This is a common pattern to ensure that dependencies are running before the main applications that use them.
        for module_name_to_start in reversed(self.LoadOrder):
            try:
                module_config = self.CachedConfig.get(module_name_to_start)
                if not module_config: # Should not happen if GetConfig and GetLoadOrder are correct.
                    self.log.error(f"Cannot start module '{module_name_to_start}': Its configuration was not found in CachedConfig.")
                    any_module_start_failed = True
                    continue # Skip to next module.

                if module_config.get("enable", False): # Only attempt to start if 'enable: True'.
                    module_script_filename = module_config.get("module")
                    if not module_script_filename: # Should be caught by GetConfig/ValidateConfig.
                        self.log.error(f"Cannot start module '{module_name_to_start}': Its 'module' (script filename) is not defined in config.")
                        any_module_start_failed = True
                        continue
                    
                    # --- Process of determining the actual_module_path_dir ---
                    # GetModulePath checks for the script in the primary module directory (`self.ModulePath`)
                    # and then in the `addon` subdirectory. It returns the directory path where the script was found.
                    actual_module_path_dir = self.GetModulePath(self.ModulePath, module_script_filename)
                    if actual_module_path_dir is None: # GetModulePath logs if the script is not found.
                        self.log.error(f"Cannot start module '{module_name_to_start}': Its script '{module_script_filename}' was not found in primary or addon paths.")
                        any_module_start_failed = True
                        continue

                    # --- (Commented out or conditional) logic for checking if a module is already running ---
                    # The original code had a section here to check `if not multi_instance:` and then potentially
                    # stop an already running instance of the module.
                    # `multi_instance` is a flag usually obtained from `MySupport.GetGenmonInitInfo()` in the `__main__` block,
                    # indicating if multiple instances of genmon *modules* (not genloader itself) are allowed.
                    # For this `StartModules` method to use this `multi_instance` flag correctly with `MySupport.IsRunning()`,
                    # the flag would need to be passed to `Loader.__init__` and stored as an instance attribute (e.g., `self.multi_instance`).
                    # As of the current analysis, `multi_instance` is not an attribute of the Loader class.
                    # Therefore, this specific check is commented out here to reflect that the required state isn't directly available.
                    # If genloader is intended to manage single-instance modules by stopping existing ones,
                    # `multi_instance` needs to be properly plumbed into the Loader.
                    # Example of what the logic might look like if `self.multi_instance` was available:
                    #
                    # if not getattr(self, 'multi_instance_setting', True): # Assuming False means single instance allowed
                    #     # Check if the module (by its script name) is already running.
                    #     # MySupport.IsRunning would need the script name and the multi_instance flag.
                    #     # This path parameter for IsRunning might need to be the full script path or just name, depending on IsRunning's implementation.
                    #     if MySupport.IsRunning(os.path.join(actual_module_path_dir, module_script_filename), multi_instance=False, log=self.log):
                    #         self.log.info(f"Module '{module_script_filename}' appears to be already running. Attempting to stop it before restart as multi_instance is false for it.")
                    #         # Attempt to stop it forcefully. PID might not be known here, so pkill by name.
                    #         # The HardStop flag for this stop could be module_config.get('hardstop', False) or self.HardStop.
                    #         if not self.UnloadModule(module_script_filename, HardStop=True, UsePID=False):
                    #             self.log.error(f"Failed to stop existing instance of '{module_script_filename}'. Start may fail or lead to multiple instances.")
                    #         else:
                    #             self.log.info(f"Successfully stopped existing instance of '{module_script_filename}'.")
                    #             time.sleep(1) # Brief pause after stopping.
                    # --- End of commented out multi-instance check logic ---

                    # --- Call to LoadModule and handling of postloaddelay ---
                    # LoadModule attempts to start the module script as a subprocess.
                    # It takes the script's directory, filename, and any command-line arguments.
                    if not self.LoadModule(
                        actual_module_path_dir,   # Directory containing the module script.
                        module_script_filename,   # Filename of the module script.
                        args=module_config.get("args", ""), # Arguments from genloader.conf.
                    ):
                        self.log.error(f"Error starting module '{module_name_to_start}' (script: {module_script_filename}). Details should be logged by LoadModule.")
                        any_module_start_failed = True # Mark that this module failed to start.
                    else:
                        # If LoadModule succeeded, check for a 'postloaddelay'.
                        # This is a delay (in seconds) to wait after starting this module before proceeding
                        # to the next one. Useful if a module needs time to initialize before others start.
                        post_load_delay_sec = module_config.get("postloaddelay", 0)
                        if post_load_delay_sec and isinstance(post_load_delay_sec, int) and post_load_delay_sec > 0:
                            self.log.info(f"Post-load delay for module '{module_name_to_start}': waiting {post_load_delay_sec} seconds.")
                            time.sleep(post_load_delay_sec)
                else:
                    self.log.info(f"Module '{module_name_to_start}' is disabled in configuration (enable=False). Skipping start.")
            except KeyError as ke: # Should be caught by .get, but as a safeguard for unexpected missing keys.
                self.LogErrorLine(f"Missing critical key '{str(ke)}' in settings for module '{module_name_to_start}' during start operation. Skipping this module.")
                any_module_start_failed = True
            except Exception as e1: # Catch any other unexpected error during the start process for this specific module.
                self.LogErrorLine(
                    f"Unexpected error occurred while trying to start module '{module_name_to_start}': {str(e1)}"
                )
                any_module_start_failed = True # Mark failure and continue with other modules.
        
        # After attempting to start all modules:
        if any_module_start_failed:
            self.log.error("One or more modules failed to start correctly. Please check the logs for details.")
            return False # Indicate overall failure.
        else:
            self.log.info("All enabled modules have been processed for starting.")
            return True # Indicate overall success.

    # ---------------------------------------------------------------------------
    def LoadModuleAlt(self, modulename, args=None):
        """
        Alternative method to load (start) a module using `subprocess.Popen`.

        This method provides a simpler, more direct way to launch a module script
        as a background process compared to the primary `LoadModule` method.
        It constructs the command using `sys.executable` (the current Python
        interpreter), the provided `modulename` (expected to be a full path or
        a name findable in PATH), and any optional arguments.

        Key differences and considerations compared to `LoadModule`:
        -   **PID Tracking:** This method does NOT update the PID (Process ID)
            tracking in `genloader.conf`. This means genloader might not be able
            to stop or manage this module later using its PID-based mechanisms.
        -   **Stream Handling:** It does not explicitly redirect the subprocess's
            stdout, stderr, or stdin. The subprocess will likely inherit these
            streams from the genloader process or system defaults, which might
            lead to output appearing on genloader's console or logs, or potential
            hanging if the module expects input.
        -   **Common Arguments:** It does not automatically append common arguments
            like `-c ConfigFilePath` which `LoadModule` does.

        This method might be useful for very simple, self-contained modules that
        do not require genloader's full management capabilities or specific
        stream handling. However, for standard genmon modules, `LoadModule` is
        generally preferred.

        Args:
            modulename (str): The filename or full path of the module script to load
                              (e.g., "/opt/genmon/custom_script.py").
            args (str, optional): A string of command-line arguments to pass to
                                  the module script. These are split by spaces.
                                  Defaults to None (no arguments).

        Returns:
            bool: True if the module was launched via `subprocess.Popen` without
                  an immediate exception (e.g., `FileNotFoundError` if `modulename`
                  is invalid). False if an error occurred during the launch attempt.
                  Note: A True return value means `Popen` was called; it does not
                  guarantee that the module script itself runs successfully after launch.
        """
        try:
            self.LogConsole(f"Starting module (using alternative LoadModuleAlt method): {modulename}")
            # Base command: `python /path/to/module.py` (using current interpreter).
            command_list = [sys.executable, modulename]

            # Add arguments if provided and not just whitespace.
            if args and len(args.strip()):
                command_list.extend(args.split()) # Split space-separated arguments into a list.

            # Launch the module as a detached background process.
            # No explicit redirection of stdin, stdout, stderr is done here.
            # The subprocess will inherit streams or use system defaults.
            # `close_fds` behavior depends on Python version and platform, generally defaults to True on POSIX for Py 3.7+.
            subprocess.Popen(command_list)
            self.log.info(f"Module '{modulename}' launched via LoadModuleAlt. Note: PID not tracked in genloader.conf and streams not explicitly managed.")
            return True # Popen call was successful.

        except FileNotFoundError: # If sys.executable or modulename is not found.
             self.LogErrorLine(f"Error in LoadModuleAlt for '{modulename}': File not found. Ensure modulename is a valid path or sys.executable is correct. Command: {' '.join(command_list if 'command_list' in locals() else [sys.executable, modulename])}")
             return False
        except Exception as e1: # Catch any other unexpected errors during Popen.
            self.LogErrorLine(f"Error in LoadModuleAlt for '{modulename}': {str(e1)}")
            return False

    # ---------------------------------------------------------------------------
    def LoadModule(self, path, modulename, args=None):
        """
        Loads (starts) a specified genmon module as a background subprocess.

        This is the primary method for starting modules managed by genloader.
        It performs several key actions:
        1.  **Constructs Path:** It forms the full path to the module script using
            the provided `path` (directory) and `modulename` (script filename).
        2.  **Prepares Arguments:**
            -   It takes module-specific arguments from the `args` parameter (read
                from `genloader.conf`).
            -   Crucially, it appends a common argument `-c self.ConfigFilePath`
                to the command. This allows all genmon modules to know the location
                of the main configuration directory (e.g., `/etc/genmon/`), so they
                can find their own respective `.conf` files within that directory.
        3.  **Stream Redirection:**
            -   For most modules, `stdout` and `stderr` are redirected to
                `subprocess.PIPE`. While currently not actively read by genloader,
                this prevents them from cluttering genloader's own console output
                and allows for future capture if needed.
            -   For `genserv.py` (the web server module), `stdout` and `stderr`
                are redirected to `os.devnull` (or `subprocess.DEVNULL`). This is
                done to suppress its web server access and error logs, which can
                be very verbose and are typically managed by `genserv` itself.
            -   `stdin` is redirected from `os.devnull` to prevent the module
                from hanging if it unexpectedly tries to read from standard input.
        4.  **Launches Subprocess:** It uses `subprocess.Popen` to launch the module
            script with the current Python interpreter (`sys.executable`).
        5.  **PID Tracking:** After successfully launching the module, it retrieves
            the Process ID (PID) of the new process and calls `self.UpdatePID()`
            to write this PID into the `[module_name]` section of `genloader.conf`.
            This PID is used later by `UnloadModule` to stop the process.

        Args:
            path (str): The absolute directory path where the module script resides
                        (e.g., "/opt/genmon" or "/opt/genmon/addon").
            modulename (str): The filename of the module script to load
                              (e.g., "genmon.py", "genserv.py").
            args (str, optional): A string of command-line arguments specific to
                                  this module, as read from `genloader.conf`.
                                  These are split by spaces. Defaults to None
                                  (no module-specific arguments).

        Returns:
            bool: True if the module was launched successfully and its PID was
                  updated in `genloader.conf`. False if an error occurred during
                  path construction, argument preparation, subprocess launch
                  (e.g., `FileNotFoundError` if script is missing), or PID update.
        """
        try:
            # Construct the full, absolute path to the module script.
            full_module_path = os.path.join(path, modulename)

            # Log to console which module is being started, including its arguments if any.
            if args and len(args.strip()):
                self.LogConsole(f"Starting: {full_module_path} {args}")
            else:
                self.LogConsole(f"Starting: {full_module_path}")
            
            # Determine output stream redirection based on module name.
            # For genserv.py (web server), redirect its stdout/stderr to DEVNULL to keep genloader's console clean,
            # as web server logs can be very verbose. Genserv should handle its own logging if needed.
            # For other modules, PIPE allows potential future capture of output, though currently not actively captured by genloader.
            try:
                from subprocess import DEVNULL # Available in Python 3.3+
            except ImportError: # Fallback for older Python versions (e.g., Python 2.x, though genmon aims for Py3).
                DEVNULL = open(os.devnull, "wb") # Open /dev/null manually.

            # If the module being loaded is 'genserv.py', redirect its output to DEVNULL. Otherwise, use PIPE.
            output_stream_setting = DEVNULL if "genserv.py" in modulename else subprocess.PIPE
            
            # Prepare the command list for Popen: [python_executable, /path/to/module.py, arg1, arg2, ...]
            execution_command_list = [sys.executable, full_module_path]
            if args and len(args.strip()): # Add module-specific arguments if they exist.
                execution_command_list.extend(args.split()) # Split space-separated args string into list items.
            
            # Add common argument: -c ConfigFilePath (e.g., -c /etc/genmon).
            # This allows all genmon modules to locate their specific .conf files within the shared config directory.
            execution_command_list.extend(["-c", self.ConfigFilePath])
            
            self.log.debug(f"Executing LoadModule command: {' '.join(execution_command_list)}")

            # Launch the module as a new subprocess.
            # - stdin is redirected from DEVNULL to prevent the subprocess from hanging if it tries to read input.
            # - stdout and stderr are set according to output_stream_setting.
            # - close_fds=True (default on POSIX for Python 3.7+) is generally good practice for subprocesses
            #   to prevent unintended inheritance of file descriptors.
            process_handle = subprocess.Popen(
                execution_command_list,
                stdout=output_stream_setting,
                stderr=output_stream_setting, # Redirect stderr to the same place as stdout.
                stdin=DEVNULL,
                # close_fds=True # Consider explicitly if needed, though default behavior is often sufficient.
            )
            
            self.log.info(f"Module '{modulename}' (PID: {process_handle.pid}) launched successfully.")

            # Update genloader.conf with the new PID for this module for tracking.
            # This is crucial for being able to stop the module later.
            return self.UpdatePID(modulename, process_handle.pid)

        except FileNotFoundError: # If sys.executable or full_module_path is not found.
             self.LogErrorLine(f"Error loading module '{modulename}' from path '{path}': File not found. Command: {' '.join(execution_command_list if 'execution_command_list' in locals() else [sys.executable, full_module_path])}")
             return False
        except Exception as e1: # Catch any other unexpected errors during Popen or PID update.
            self.LogErrorLine(
                f"Error loading module '{modulename}' from path '{path}': {str(e1)}"
            )
            return False

    # ---------------------------------------------------------------------------
    def UnloadModule(self, modulename, pid=None, HardStop=False, UsePID=False):
        """
        Stops (unloads) a running genmon module.

        This method attempts to terminate a module's process using one of two strategies:
        1.  **By PID (Process ID):** If `UsePID` is True and a valid, non-zero `pid`
            is provided (typically read from `genloader.conf`), it uses the `kill`
            command to send a signal to that specific PID.
        2.  **By Process Name (`pkill`):** If `UsePID` is False or `pid` is invalid,
            it falls back to using the `pkill` command. `pkill` attempts to find
            and signal processes based on the `modulename` (script filename).
            The `pkill` command is typically restricted to processes owned by `root`
            (`-u root`) and matches against the full command line (`-f`) to be
            more specific.

        The `HardStop` flag (either module-specific from config or global `self.HardStop`)
        determines the signal sent:
        -   If `HardStop` is True, `kill -9` or `pkill -9` (SIGKILL) is used for a
            forceful, immediate termination.
        -   If `HardStop` is False, a standard termination signal (SIGTERM, default
            for `kill` and `pkill`) is used, allowing the process to shut down gracefully.

        After attempting to stop the module (regardless of success of the kill command),
        it calls `self.UpdatePID(modulename, "")` to clear the stored PID for that
        module in `genloader.conf`. This is crucial because even if the `kill` or
        `pkill` command reports an error (e.g., "process not found" if already stopped),
        the PID entry should be cleared to reflect that genloader is no longer actively
        tracking that PID as a running instance.

        Args:
            modulename (str): The filename of the module script (e.g., "genmon.py").
                              This is used by `pkill` if PID-based stopping is not used.
                              It's also used to derive the section name for `UpdatePID`.
            pid (int or str, optional): The Process ID of the module to stop.
                                        Can be an integer or a string convertible to int.
                                        Defaults to None.
            HardStop (bool, optional): If True, a forceful stop (SIGKILL) is used.
                                       Otherwise, a graceful termination signal is sent.
                                       Defaults to False.
            UsePID (bool, optional): If True and `pid` is valid and non-zero, the `kill`
                                     command with the PID is used. Otherwise, `pkill`
                                     with `modulename` is used. Defaults to False.

        Returns:
            bool: True if the stop command was issued (even if it failed, e.g.,
                  process already stopped) AND the subsequent call to `UpdatePID`
                  to clear the PID in the config was successful.
                  False if an error occurs during PID validation, command construction,
                  subprocess execution (other than typical kill/pkill failures for
                  non-existent processes), or if `UpdatePID` fails.
        """
        try:
            kill_command_args_list = [] # List to build the arguments for Popen.
            
            # Determine whether to use 'kill' with PID or 'pkill' with module name.
            # UsePID must be true, pid must be provided, not empty string, and not zero.
            pid_is_valid_for_kill = False
            if UsePID and pid is not None:
                try:
                    if str(pid).strip() and int(pid) != 0: # Ensure PID is not empty and non-zero.
                        pid_is_valid_for_kill = True
                except ValueError: # Handle if pid cannot be converted to int.
                    self.log.warning(f"PID '{pid}' for module '{modulename}' is not a valid integer. Falling back to pkill.")
                    pid_is_valid_for_kill = False # Explicitly mark as invalid.

            if pid_is_valid_for_kill:
                # Strategy 1: Use 'kill' command with the provided PID. This is more precise.
                kill_command_args_list.append("kill") # The command itself.
                if HardStop or self.HardStop: # Check module-specific 'hardstop' from config or global HardStop flag.
                    kill_command_args_list.append("-9") # SIGKILL for forceful termination.
                kill_command_args_list.append(str(pid)) # The PID to target.
                self.log.info(f"Preparing to stop module '{modulename}' using 'kill' with PID {pid} (HardStop effective: {HardStop or self.HardStop}).")
            else:
                # Strategy 2: Use 'pkill' command with the module name.
                # This is less precise if multiple instances with similar names exist from other users,
                # but `-u root -f` helps narrow it down.
                kill_command_args_list.append("pkill") # The command itself.
                if HardStop or self.HardStop: # Apply HardStop logic for pkill too.
                    kill_command_args_list.append("-9") # SIGKILL.
                # pkill options:
                #   -u root: Only target processes owned by the 'root' user.
                #   -f: Match the `modulename` against the full command line, not just process name.
                kill_command_args_list.extend(["-u", "root", "-f", modulename])
                self.log.info(f"Preparing to stop module '{modulename}' using 'pkill' (target: root's processes matching '{modulename}', HardStop effective: {HardStop or self.HardStop}). PID was not used or invalid ('{pid}').")

            self.LogConsole(f"Stopping module: {modulename} (using {'kill by PID' if pid_is_valid_for_kill else 'pkill by name'})")

            # Execute the kill or pkill command.
            # We capture stdout/stderr, but their content is often not critical for success/failure determination here,
            # as kill/pkill might return non-zero or output to stderr if the process is already gone.
            process = Popen(kill_command_args_list, stdout=PIPE, stderr=PIPE)
            output_bytes, error_bytes = process.communicate() # Wait for command to finish.
            # rc = process.returncode # Return code is not strictly checked for success here.

            # Log any output/error from the kill/pkill command for diagnostic purposes.
            output_str = output_bytes.decode(sys.getdefaultencoding(), errors='replace').strip()
            error_str = error_bytes.decode(sys.getdefaultencoding(), errors='replace').strip()
            if output_str: self.log.debug(f"Stop command stdout for '{modulename}': {output_str}")
            if error_str: self.log.debug(f"Stop command stderr for '{modulename}': {error_str}") # pkill often outputs "no process found" to stderr if already stopped.

            # After attempting to stop the module, ALWAYS clear its PID in genloader.conf.
            # This is crucial: if the process was already stopped or killed manually,
            # this ensures the config reflects that genloader is no longer tracking that PID.
            # UpdatePID returns True on success, False on failure.
            return self.UpdatePID(modulename, "") # Pass an empty string to clear the PID.

        except ValueError: # Should be caught by pid_is_valid_for_kill logic, but as a safeguard.
            self.LogErrorLine(f"Error stopping module '{modulename}': Invalid PID format '{pid}' encountered unexpectedly.")
            return False # PID was invalid. Still try to clear PID in config for safety? Current logic exits.
        except Exception as e1: # Catch any other unexpected errors.
            self.LogErrorLine(f"Unexpected error unloading module '{modulename}': {str(e1)}")
            return False

    # ---------------------------------------------------------------------------
    def UpdatePID(self, modulename, pid=""):
        """
        Updates the 'pid' entry in `genloader.conf` for a specified module.

        This method takes a module filename (e.g., "genmon.py"), derives the
        corresponding section name in `genloader.conf` (e.g., "genmon" by
        removing the ".py" extension), and then writes the provided `pid` value
        to the 'pid' key within that section.

        If the `pid` argument is an empty string, None, or 0 (after string
        conversion for consistency), it effectively clears the stored PID for
        that module in the configuration file by writing an empty string. This
        is used after a module is stopped or if its PID is found to be invalid.

        It uses `self.config` (a `MyConfig` instance) to perform the write operation.

        Args:
            modulename (str): The filename of the module (e.g., "genmon.py") whose
                              PID entry in `genloader.conf` needs to be updated.
            pid (int or str, optional): The Process ID (PID) to store for the module.
                                        If this is an empty string, None, 0, or a
                                        string evaluating to 0 as int, the PID entry
                                        in the config is cleared (set to an empty string).
                                        Defaults to an empty string, which means clearing
                                        the PID.

        Returns:
            bool: True if the PID was successfully written to (or cleared in)
                  `genloader.conf`. False if the section name cannot be derived,
                  if `MyConfig` fails to set the section, or if any other
                  exception occurs during the write operation.
        """
        try:
            # Derive the section name in genloader.conf from the module filename
            # by removing the file extension (e.g., "genmon.py" -> "genmon").
            section_name = os.path.splitext(modulename)[0]
            if not section_name: # Should not happen with valid modulename.
                self.log.error(f"Error in UpdatePID: Could not derive section name from modulename '{modulename}'.")
                return False
            
            # Set MyConfig to operate on this module's specific section in genloader.conf.
            # MyConfig.SetSection() returns False if the section doesn't exist and cannot be implicitly handled,
            # though for writing, MyConfig usually creates sections if they are missing when WriteValue is called with a section.
            # However, an explicit SetSection can be a good check or for context setting.
            if not self.config.SetSection(section_name): # SetSection logs an error if the section is invalid or cannot be set.
                self.log.error(
                    f"Error in UpdatePID: Cannot set MyConfig current section to '[{section_name}]' for module '{modulename}'. PID update failed."
                )
                return False # Cannot write PID if the section context cannot be established.
            
            # Prepare the PID value for writing.
            # If pid is None, or an empty string, or effectively zero, store an empty string to clear it.
            pid_to_write = ""
            if pid is not None and str(pid).strip(): # Check if pid is not None and not an empty/whitespace string.
                try:
                    if int(pid) != 0: # If it's a non-zero integer.
                        pid_to_write = str(pid) # Store it as a string.
                except ValueError: # If pid is not a valid integer string (e.g. "abc")
                    pid_to_write = "" # Treat as invalid, clear existing PID.
                    self.log.warning(f"UpdatePID: PID value '{pid}' for module '{modulename}' is not a valid integer. Clearing stored PID.")

            # Write the PID (or an empty string to clear it) to the 'pid' key in the current section.
            self.config.WriteValue("pid", pid_to_write, section=section_name)
            self.log.debug(f"Updated PID for module '{modulename}' (section '[{section_name}]') in genloader.conf to '{pid_to_write}'.")
            return True # PID written/cleared successfully.
        except Exception as e1: # Catch any other unexpected errors during MyConfig operations or string/int conversions.
            # Ensure section_name is defined for the error message, even if it failed early.
            current_section_name = section_name if 'section_name' in locals() and section_name else f"derived from {modulename}"
            self.LogErrorLine(f"Error writing PID for module '{modulename}' (section '[{current_section_name}]') to genloader.conf: {str(e1)}")
            return False
        # Removed redundant "return True" at end as all logical paths should explicitly return.


# ------------------main---------------------------------------------------------
if __name__ == "__main__":
    """
    Main execution block for genloader.py script.

    Handles command-line argument parsing, performs initial setup checks
    (permissions, one-time maintenance), determines operational parameters
    (start, stop, config path), and then instantiates and runs the Loader.
    """
    # Help string for command-line usage.
    HelpStr = "\npython genloader.py [-s | -r | -x] [-z] [-c configfilepath]\n"
    HelpStr += "   Example: python genloader.py -s  (Start modules)\n"
    HelpStr += "            python genloader.py -r  (Restart modules: stop then start)\n"
    HelpStr += "            python genloader.py -x  (Stop modules)\n"
    HelpStr += "\n      -s  Start Genmon modules"
    HelpStr += "\n      -r  Restart Genmon modules (equivalent to -x then -s)"
    HelpStr += "\n      -x  Stop Genmon modules"
    HelpStr += "\n      -z  Hard stop Genmon modules (use with -x or -r, e.g., -xz or -rz)"
    HelpStr += "\n      -c  Path to the configuration directory (e.g., /etc/genmon/)."
    HelpStr += "\n          This directory should contain genloader.conf."
    HelpStr += "\n \n"

    # Check for root privileges, essential for managing system services/processes.
    if not MySupport.PermissionsOK():
        print( # Direct print as logger might not be set up or accessible.
            "ERROR: You need to have root privileges to run this script.\n"
            "Please try again, using 'sudo' if necessary. Exiting."
        )
        sys.exit(2)

    # --- Argument Parsing ---
    try:
        # Default configuration path from ProgramDefaults.
        ConfigFilePath = ProgramDefaults.ConfPath
        # Parse options: h(help), s(start), r(restart), x(eXit/stop), z(hardstop), c(configpath).
        opts, args = getopt.getopt(
            sys.argv[1:], # Script arguments (excluding script name itself).
            "hsrxzc:",    # Short options. Colon indicates argument required.
            ["help", "start", "restart", "exit", "hardstop", "configpath="], # Long options.
        )
    except getopt.GetoptError as err: # Handle invalid options/arguments.
        print(f"Error: Invalid command-line argument: {err}")
        print(HelpStr)
        sys.exit(2)

    # Initialize operational flags.
    StopModules_flag = False
    StartModules_flag = False
    HardStop_flag = False

    # Process parsed command-line options.
    for opt, arg in opts:
        if opt == "-h" or opt == "--help":
            print(HelpStr)
            sys.exit()
        elif opt in ("-s", "--start"):
            StartModules_flag = True
        elif opt in ("-r", "--restart"): # Restart means stop then start.
            StopModules_flag = True
            StartModules_flag = True
        elif opt in ("-x", "--exit"): # Exit means stop.
            StopModules_flag = True
        elif opt in ("-z", "--hardstop"): # HardStop modifies stop behavior.
            HardStop_flag = True
            # HardStop usually implies a stop action. If only -z is given, it should probably imply -x.
            # If neither -x nor -r is present, make -z also trigger StopModules.
            if not StopModules_flag: StopModules_flag = True
        elif opt in ("-c", "--configpath"): # Custom config file path.
            ConfigFilePath = arg.strip() # Remove leading/trailing whitespace.

    # If no primary action (start or stop) was selected, show help and exit.
    if not StartModules_flag and not StopModules_flag:
        print("\nError: No primary action selected (start, stop, or restart).\n")
        print(HelpStr)
        sys.exit(2)

    # --- Initial Setup ---
    # Setup a temporary logger for pre-Loader tasks (OneTimeMaint, GetGenmonInitInfo).
    # Loader will instantiate its own logger later.
    # Renamed 'tmplog' to 'bootstrap_logger' for clarity.
    bootstrap_logger = SetupLogger("genloader_main_bootstrap", os.path.join(ProgramDefaults.LogPath, "genloader_main_bootstrap.log"))
    bootstrap_logger.info(f"genloader.py script started with flags: Start={StartModules_flag}, Stop={StopModules_flag}, HardStop={HardStop_flag}, ConfigPath='{ConfigFilePath}'")

    # Perform one-time maintenance (e.g., migrating old files).
    # This is a static method of Loader, called before Loader instantiation.
    if Loader.OneTimeMaint(ConfigFilePath, bootstrap_logger): # Pass ConfigFilePath and the bootstrap logger.
        bootstrap_logger.info("OneTimeMaint completed (or was not needed). Pausing briefly.")
        time.sleep(1.5) # Brief pause after maintenance, reason might be historical or for FS sync.
    else:
        bootstrap_logger.error("OneTimeMaint reported errors. Proceeding, but system might be in an inconsistent state.")

    # Get initial genmon info (port, log location, multi_instance flag) using MySupport.
    # This helps determine if another genloader instance is running, and provides log paths.
    # log=None is passed because MySupport.GetGenmonInitInfo might try to set up its own temporary log if needed.
    try:
        _, loglocation_from_support, multi_instance_setting = MySupport.GetGenmonInitInfo(
            ConfigFilePath, log=bootstrap_logger # Pass bootstrap_logger for GetGenmonInitInfo's own logging.
        )
        bootstrap_logger.info(f"Retrieved initial info: LogLocation='{loglocation_from_support}', MultiInstance={multi_instance_setting}")
    except Exception as e_getinfo:
        bootstrap_logger.error(f"Failed to get initial genmon info via MySupport.GetGenmonInitInfo: {e_getinfo}. Using defaults.")
        loglocation_from_support = ProgramDefaults.LogPath # Fallback
        multi_instance_setting = False # Fallback to safer single instance assumption.


    # Check if another instance of genloader.py is already running.
    # The `multi_instance_setting` from GetGenmonInitInfo (from genmon.conf) should ideally control this.
    # However, genloader itself is usually expected to be a singleton.
    # The original code uses `multi_instance` here, implying it might allow multiple genloaders
    # if genmon.conf's multi_instance is True. This seems unusual for a loader script.
    # Assuming `multi_instance_setting` here refers to whether *modules* can be multi-instance,
    # not genloader itself. For genloader, we typically want only one instance.
    # So, IsRunning for genloader.py itself should probably ignore `multi_instance_setting` or use False.
    if MySupport.IsRunning(os.path.basename(__file__), multi_instance=False, log=bootstrap_logger): # Force check for single instance of genloader
        bootstrap_logger.error(f"Another instance of {os.path.basename(__file__)} is already running. Exiting.")
        print(f"\nError: {os.path.basename(__file__)} is already running.")
        sys.exit(2)

    # --- Instantiate and Run Loader ---
    # Create the main Loader object with processed flags and paths.
    # loglocation_from_support is passed to ensure Loader uses the correct log path if determined from genmon.conf.
    bootstrap_logger.info("Instantiating Loader object...")
    LoaderObject = Loader(
        start=StartModules_flag,
        stop=StopModules_flag,
        hardstop=HardStop_flag,
        ConfigFilePath=ConfigFilePath,
        loglocation=loglocation_from_support, # Pass potentially updated log location
        log=None # Loader will create its own main logger or use one passed from MySupport.
        # localinit is not set from CLI here, defaults to False in Loader.__init__.
        # multi_instance_setting should be passed to Loader if its methods need it,
        # e.g., self.multi_instance = multi_instance_setting in Loader.__init__.
    )
    bootstrap_logger.info("Loader object instantiated. Main operations (start/stop modules) will now be handled by the Loader instance.")
    # The Loader's __init__ method handles the starting and stopping of modules based on the flags.
    # No further explicit calls to LoaderObject.StartModules() or StopModules() are needed here
    # as __init__ orchestrates this based on the start/stop flags passed to it.
    print("genloader operations complete. Check logs for details.")
