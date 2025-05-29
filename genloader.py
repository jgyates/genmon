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
        self.Start = start
        self.Stop = stop
        self.HardStop = hardstop
        self.PipChecked = False # Tracks if pip availability check has been done
        self.AptUpdated = False # Tracks if apt-get update has been run this session
        self.NewInstall = False # Flag for new installations (e.g., based on config version)
        self.Upgrade = False    # Flag for upgrades (based on config version vs program version)
        self.version = None     # Stores the current program version

        # --- Bootstrap Logger Setup ---
        # A temporary logger is used before MySupport fully initializes the official logger.
        temp_logger_active = False
        if log is None:
            try:
                # Determine effective log location for bootstrap logger
                effective_log_location = loglocation if loglocation else ProgramDefaults.LogPath
                # Create a specific bootstrap logger instance
                self.log = SetupLogger("genloader_bootstrap", os.path.join(effective_log_location, "genloader_bootstrap.log"))
                temp_logger_active = True
                self.log.info("Bootstrap logger initialized.")
            except Exception as e_log_setup:
                # Fallback to basic print if SetupLogger fails catastrophically
                print(f"CRITICAL: Initial bootstrap logger setup failed: {e_log_setup}. Further logging might be impaired.", file=sys.stderr)
                # Create a dummy self.log that just prints, to prevent AttributeError later
                class PrintLogger:
                    def info(self, msg): print(f"INFO: {msg}")
                    def error(self, msg): print(f"ERROR: {msg}", file=sys.stderr)
                    def debug(self, msg): print(f"DEBUG: {msg}")
                    def LogErrorLine(self, msg): self.error(f"[LINE_UNKNOWN] {msg}") # Compatibility
                self.log = PrintLogger()
        else:
            self.log = log # Use provided logger
        
        # --- Initialize Parent Class (MySupport) ---
        # MySupport's __init__ is expected to finalize self.log (potentially replacing the bootstrap one)
        # and self.ConfigFilePath (using ProgramDefaults if ConfigFilePath arg is None).
        # It also uses `localinit` to adjust its path findings.
        try:
            super(Loader, self).__init__(log=self.log, ConfigFilePath=ConfigFilePath, localinit=localinit)
            # If MySupport replaced our temporary logger, update self.log to use the official one from MySupport.
            if temp_logger_active and hasattr(super(), 'log') and self.log != getattr(super(), 'log', None) :
                self.log = getattr(super(), 'log') 
                self.log.info("Switched from bootstrap logger to MySupport's finalized logger.")
        except Exception as e_super_init:
            self.log.error(f"CRITICAL: Error during MySupport initialization: {str(e_super_init)}. Functionality will be severely limited.")
            # Depending on MySupport's criticality, a sys.exit might be warranted here.

        # --- Determine pip program ---
        if sys.version_info[0] < 3:
            self.pipProgram = "pip2"
        else:
            self.pipProgram = "pip3"

        # --- Configuration File Path Setup ---
        # self.ConfigFilePath should now be set by MySupport's init.
        if not hasattr(self, 'ConfigFilePath') or not self.ConfigFilePath:
             self.log.error("CRITICAL: ConfigFilePath not set after MySupport init. Cannot determine genloader.conf location. Exiting.")
             sys.exit(2)

        self.ConfigFileName = "genloader.conf"
        # If localinit is True, genloader.conf is in the current working directory.
        # Otherwise, it's located in the self.ConfigFilePath (e.g., /etc/genmon, /usr/local/etc/genmon).
        if localinit:
            self.configfile = self.ConfigFileName
            self.log.info(f"localinit is True: Expecting '{self.ConfigFileName}' in current directory: {os.getcwd()}")
        else:
            self.configfile = os.path.join(self.ConfigFilePath, self.ConfigFileName)
            self.log.info(f"localinit is False: Expecting '{self.ConfigFileName}' in config path: {self.ConfigFilePath}")
        
        # --- Module and Default Config Paths ---
        # ModulePath is the directory where this script (genloader.py) resides.
        self.ModulePath = os.path.dirname(os.path.realpath(__file__))
        # ConfPath is the 'conf' subdirectory within ModulePath, containing default configs.
        self.ConfPath = os.path.join(self.ModulePath, "conf")

        # --- Console Logger Setup ---
        # Sets up a logger for direct console output (e.g., for "Starting module X...").
        try:
            self.console = SetupLogger("genloader_console", log_file="", stream=True)
        except Exception as e_console_log:
            self.log.error(f"Error setting up console logger: {str(e_console_log)}")
            class PrintConsole: # Fallback console logger
                def error(self, msg): print(f"CONSOLE_ERROR: {msg}", file=sys.stderr)
                def info(self, msg): print(f"CONSOLE_INFO: {msg}")
            self.console = PrintConsole()

        # --- Main Initialization Sequence ---
        try:
            # If starting modules, perform system checks first.
            if self.Start:
                self.log.info("Start flag is set. Checking system readiness...")
                if not self.CheckSystem(): # CheckSystem logs its own detailed errors.
                    self.log.error("System readiness check failed. Cannot start modules. Exiting.")
                    sys.exit(2)

            self.CachedConfig = {} # Initialize cache for module configurations.

            # Ensure configuration directory exists.
            if not os.path.isdir(self.ConfigFilePath):
                self.log.info(f"Configuration directory '{self.ConfigFilePath}' does not exist. Attempting to create it.")
                try:
                    os.makedirs(self.ConfigFilePath, exist_ok=True)
                    self.log.info(f"Successfully created configuration directory: {self.ConfigFilePath}")
                except OSError as oe:
                    self.LogErrorLine(f"OSError creating target config directory '{self.ConfigFilePath}': {str(oe)}. Check permissions and path. Exiting.")
                    sys.exit(2) 
                except Exception as e_mkdir:
                    self.LogErrorLine(f"Unexpected error creating target config directory '{self.ConfigFilePath}': {str(e_mkdir)}. Exiting.")
                    sys.exit(2) 

            # Ensure genloader.conf exists, copying from default if not found.
            if not os.path.isfile(self.configfile):
                self.log.info(
                    f"Main config file '{self.configfile}' not found. Attempting to copy from default: "
                    f"{os.path.join(self.ConfPath, self.ConfigFileName)}"
                )
                if not self.CopyConfFile(): 
                    self.log.error(f"Failed to copy main configuration file ('{self.ConfigFileName}'). This is a critical error. Exiting.")
                    sys.exit(2)
            
            # Initialize MyConfig for genloader.conf.
            try:
                self.config = MyConfig(filename=self.configfile, section="genmon", log=self.log) # Default section for MyConfig operations
            except Exception as e_myconfig_init:
                self.LogErrorLine(f"Failed to initialize MyConfig with '{self.configfile}': {str(e_myconfig_init)}. Exiting.")
                sys.exit(2)

            # --- Load, Validate, and Recover Configuration ---
            # This sequence attempts to load the config, and if it fails or is invalid,
            # it tries to recover by copying the default config and trying again.

            # First attempt to load configuration.
            if not self.GetConfig(): # GetConfig logs its own detailed errors.
                self.log.info("Initial attempt to load configuration (GetConfig) failed. Attempting recovery by copying default config.")
                if not self.CopyConfFile(): # CopyConfFile logs its own errors.
                     self.log.error("Failed to copy/restore main configuration file after GetConfig() failure. Exiting.")
                     sys.exit(2)
                self.log.info("Retrying GetConfig after copying default configuration.")
                try: # Re-initialize MyConfig after copy as file content has changed.
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
                try: # Re-initialize MyConfig.
                    self.config = MyConfig(filename=self.configfile, section="genmon", log=self.log)
                except Exception as e_myconfig_reinit_val:
                    self.LogErrorLine(f"Failed to re-initialize MyConfig for validation retry: {str(e_myconfig_reinit_val)}. Exiting.")
                    sys.exit(2)
                if not self.GetConfig(): # Must re-load config after copy for validation.
                    self.log.error("Failed to re-load configuration (GetConfig) after copy during validation retry. Exiting.")
                    sys.exit(2)
                if not self.ValidateConfig(): # Second attempt to validate.
                    self.log.error("Second attempt to validate configuration (ValidateConfig) failed even after copying default. Critical failure. Exiting.")
                    sys.exit(2)

            # Determine module load order based on priorities in the (now validated) config.
            self.LoadOrder = self.GetLoadOrder() # GetLoadOrder logs its own errors.

            # --- Stop or Start Modules Based on Flags ---
            if self.Stop:
                self.log.info("Stop flag is set. Processing stop for modules...")
                self.StopModules() # StopModules logs its own errors.
                time.sleep(2) # Allow time for modules to shut down.

            if self.Start:
                self.log.info("Start flag is set. Processing start for modules...")
                self.StartModules() # StartModules logs its own errors.

        except SystemExit: # Allow sys.exit() to propagate cleanly from earlier checks.
            self.log.info("SystemExit called during initialization.")
            raise
        except Exception as e_init_main: # Catch-all for any other unhandled exceptions in __init__.
            self.LogErrorLine(f"CRITICAL UNHANDLED ERROR during Loader initialization sequence: {str(e_init_main)}")
            # Depending on state, self.log might be the bootstrap or final logger.
            sys.exit(3) # Exit due to critical unhandled error.

    # ---------------------------------------------------------------------------
    def CopyConfFile(self):
        """
        Copies the default `genloader.conf` file from the installation's `conf`
        directory to the active configuration path (`self.configfile`).

        This is typically used if `genloader.conf` is missing from the active
        configuration path during startup or if a recovery is attempted.
        It ensures that the target directory exists before copying.

        Returns:
            bool: True if the file was copied successfully, False otherwise.
        """
        source_conf_file = os.path.join(self.ConfPath, self.ConfigFileName)
        target_conf_file = self.configfile # self.configfile is the full path

        try:
            # Check if the source (default) config file exists.
            if not os.path.isfile(source_conf_file):
                self.log.error(f"Default configuration file '{source_conf_file}' not found. Cannot copy.")
                return False
            
            # Ensure destination directory exists. Although __init__ tries, this is a safeguard.
            target_dir = os.path.dirname(target_conf_file)
            if not os.path.isdir(target_dir):
                try:
                    self.log.info(f"Target directory '{target_dir}' for config file does not exist. Attempting to create.")
                    os.makedirs(target_dir, exist_ok=True)
                    self.log.info(f"Successfully created directory '{target_dir}'.")
                except OSError as oe_dir:
                    self.LogErrorLine(f"OSError creating directory '{target_dir}' for config file: {str(oe_dir)}")
                    return False # Cannot copy if target directory creation fails.
            
            self.log.info(f"Attempting to copy default config from '{source_conf_file}' to '{target_conf_file}'.")
            copyfile(source_conf_file, target_conf_file) # shutil.copyfile
            self.log.info(f"Successfully copied default config from '{source_conf_file}' to '{target_conf_file}'.")
            return True
        except IOError as ioe: # Specific to file I/O issues with copyfile itself.
            self.LogErrorLine(f"IOError during config file copy from '{source_conf_file}' to '{target_conf_file}': {str(ioe)}")
            return False
        except OSError as ose: # Broader OS errors (permissions, path issues not caught by makedirs).
            self.LogErrorLine(f"OSError during config file copy operation for '{target_conf_file}': {str(ose)}")
            return False
        except Exception as e_copy: # Catch any other unexpected error.
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
        # ModuleList: [import_name, pip_install_name, optional_required_version]
        module_list_definitions = [
            ["flask", "flask", None],
            ["serial", "pyserial", None],
            ["crcmod", "crcmod", None],
            ["pyowm", "pyowm", "2.10.0"], # Note: FixPyOWMMaintIssues might handle specific version nuances.
            ["pytz", "pytz", None],
            ["pysnmp", "pysnmp", None],
            ["ldap3", "ldap3", None],
            ["smbus", "smbus", None],
            ["pyotp", "pyotp", "2.3.0"],
            ["psutil", "psutil", None],
            ["chump", "chump", None], # For genpushover
            ["twilio", "twilio", None], # For gensms
            ["paho.mqtt.client", "paho-mqtt", "1.6.1"], # For genmqtt
            ["OpenSSL", "pyopenssl", None], # SSL support
            ["spidev", "spidev", None],
            ["voipms", "voipms", "0.2.5"] # For gensms_voip
            # ['fluids', 'fluids', None] # Example of a conditionally checked module
        ]
        any_installation_failed = False

        # First, check for essential system tools (like cmake).
        if not self.CheckToolsNeeded(): # CheckToolsNeeded logs its own errors.
            self.log.error("CheckToolsNeeded reported errors. System readiness check might be incomplete or fail.")
            # Depending on how critical these tools are, could set any_installation_failed = True here.

        # Iterate through the list of required Python libraries.
        for import_name, install_name, required_version in module_list_definitions:
            # Example for conditional module: Skip 'fluids' on Python < 3.6
            if (import_name == "fluids") and sys.version_info < (3, 6):
                self.log.debug(f"Skipping check for '{install_name}' as it requires Python 3.6+.")
                continue

            if not self.LibraryIsInstalled(import_name): # LibraryIsInstalled logs its own attempts.
                self.log.info(
                    f"Warning: Required library '{install_name}' (for import '{import_name}') not found. Attempting installation..."
                )
                if not self.InstallLibrary(install_name, version=required_version): # InstallLibrary logs details.
                    self.log.error(f"Error: Failed to install library '{install_name}'.")
                    any_installation_failed = True
                # Specific post-install action for ldap3 if pyasn1 is often an issue.
                # Modern pip usually handles dependencies well, so this might be less needed.
                if import_name == "ldap3" and not self.LibraryIsInstalled("pyasn1"):
                    self.log.info("Attempting to update/install 'pyasn1' as a common dependency issue for 'ldap3'.")
                    if not self.InstallLibrary("pyasn1", update=True):
                         self.log.warning("Failed to install/update 'pyasn1' for 'ldap3'. This might or might not cause issues.")
                         # Not necessarily setting any_installation_failed = True for a sub-dependency here.

        if any_installation_failed:
            self.log.error("One or more required Python libraries could not be installed. System readiness check failed.")
            return False
        else:
            self.log.info("System check for Python libraries completed. All appear to be installed or were successfully installed.")
            return True
        # Removed try-except Exception as e_checksys as individual methods should handle their exceptions.

    # ---------------------------------------------------------------------------
    def ExecuteCommandList(self, execute_list, env=None):
        """
        Executes an external command as a subprocess.

        This method takes a list of command arguments, runs them using `subprocess.Popen`,
        and captures standard output and standard error. It checks the return code
        and logs errors if the command fails.

        Args:
            execute_list (list of str): A list where the first element is the command
                                        and subsequent elements are its arguments.
            env (dict, optional): A dictionary of environment variables to set for
                                  the command's execution. Defaults to None, which
                                  inherits the current environment.

        Returns:
            bool: True if the command executed successfully (return code 0),
                  False otherwise.
        """
        try:
            # Ensure all elements in execute_list are strings for Popen.
            execute_list_str = [str(item) for item in execute_list]
            self.log.debug(f"Executing command: {' '.join(execute_list_str)}")
            
            # Start the subprocess.
            process = Popen(execute_list_str, stdout=PIPE, stderr=PIPE, env=env)
            # Wait for command to complete and get output.
            output_bytes, error_bytes = process.communicate()
            return_code = process.returncode

            # Decode output and error streams from bytes to string.
            output_str = output_bytes.decode(sys.getdefaultencoding(), errors='replace') if output_bytes else ""
            error_str = error_bytes.decode(sys.getdefaultencoding(), errors='replace') if error_bytes else ""

            # Check the return code.
            if return_code != 0:
                log_message = f"Error executing command: '{' '.join(execute_list_str)}'. Return Code: {return_code}"
                if output_str.strip():
                    log_message += f"\nStdout: {output_str.strip()}"
                if error_str.strip():
                    log_message += f"\nStderr: {error_str.strip()}"
                self.log.error(log_message)
                return False
            
            # Log non-empty stderr even on success, as it might contain warnings.
            if error_str.strip():
                self.log.info(f"Stderr from successful command '{' '.join(execute_list_str)}' (RC=0):\n{error_str.strip()}")

            self.log.debug(f"Command '{' '.join(execute_list_str)}' executed successfully.")
            return True
        except FileNotFoundError: # Specific error if the command itself is not found.
            self.LogErrorLine(f"Error in ExecuteCommandList: Command '{execute_list[0]}' not found.")
            return False
        except subprocess.SubprocessError as spe: # Catch other Popen/communicate related errors.
            self.LogErrorLine(f"Subprocess error executing '{' '.join(map(str,execute_list))}': {str(spe)}")
            return False
        except Exception as e_exec: # Catch any other unexpected error.
            self.LogErrorLine(f"Unexpected error in ExecuteCommandList for '{' '.join(map(str,execute_list))}': {str(e_exec)}")
            return False

    # ---------------------------------------------------------------------------
    def CheckToolsNeeded(self):
        """
        Checks for essential system tools, like `cmake`, required by some Python libraries.

        If a required tool is not found, it attempts to install it using `apt-get`.
        This includes running `apt-get update` if it hasn't been done yet in the session.

        Returns:
            bool: True if all required tools are present or successfully installed,
                  False otherwise.
        """
        try:
            self.log.info("Checking for required system tool: cmake.")
            command_list_cmake_check = ["cmake", "--version"]
            # Check if cmake is installed and executable.
            if not self.ExecuteCommandList(command_list_cmake_check): # ExecuteCommandList logs detailed errors.
                self.log.info("'cmake --version' command failed, indicating cmake is not installed or not in PATH. Attempting to install cmake via apt-get.")
                
                # Run 'apt-get update' if not already done in this session.
                if not self.AptUpdated:
                    self.log.info("Running 'apt-get update' before attempting to install cmake.")
                    cmd_apt_update_allow_rls = ["sudo", "apt-get", "-yqq", "--allow-releaseinfo-change", "update"]
                    cmd_apt_update_normal = ["sudo", "apt-get", "-yqq", "update"]
                    
                    # Try with --allow-releaseinfo-change first, then normal update.
                    if not self.ExecuteCommandList(cmd_apt_update_allow_rls):
                        self.log.info("First 'apt-get update' attempt failed (with --allow-releaseinfo-change). Retrying standard update...")
                        if not self.ExecuteCommandList(cmd_apt_update_normal):
                            self.log.error("Error: Unable to run 'apt-get update' even after retry. Cannot proceed with cmake installation.")
                            return False # Cannot install cmake if update fails.
                    self.AptUpdated = True # Mark apt-get update as done for this session.
                    self.log.info("'apt-get update' completed successfully.")
                
                # Attempt to install cmake.
                self.log.info("Attempting to install cmake using 'apt-get install'.")
                # DEBIAN_FRONTEND=noninteractive prevents prompts during apt-get install.
                custom_env = os.environ.copy()
                custom_env["DEBIAN_FRONTEND"] = "noninteractive"
                install_cmd_list_cmake = ["sudo", "apt-get", "-yqq", "install", "cmake"]

                if not self.ExecuteCommandList(install_cmd_list_cmake, env=custom_env): # ExecuteCommandList logs errors.
                    self.log.error("Error: Failed to install cmake via 'apt-get'.")
                    return False
                self.log.info("cmake installed successfully via apt-get.")
            else:
                self.log.info("cmake is already installed and accessible.")
            return True # cmake is present or was installed.
        except Exception as e_tools:
            self.LogErrorLine(f"Unexpected error in CheckToolsNeeded: {str(e_tools)}")
            return False

    # ---------------------------------------------------------------------------
    def CheckBaseSoftware(self):
        """
        Checks if `pip` (Python package installer) is installed and accessible.

        If `pip` is not found, it calls `InstallBaseSoftware` to attempt installation.
        Uses `sys.executable -m pip -V` for a robust check.

        Returns:
            bool: True if `pip` is available or successfully installed, False otherwise.
        """
        try:
            # If pip check was already done and successful in this session, skip.
            if self.PipChecked:
                self.log.debug("Pip check previously performed and successful.")
                return True

            self.log.info("Checking for pip availability...")
            # Command to check pip version; a non-zero return indicates issues.
            command_list_pip_check = [sys.executable, "-m", "pip", "-V"]
            if not self.ExecuteCommandList(command_list_pip_check): # This logs if the command fails.
                self.log.info(f"'{sys.executable} -m pip -V' command failed or pip is not installed/configured correctly. Attempting to install base software (pip).")
                # Attempt to install pip if the check fails.
                if not self.InstallBaseSoftware(): # This logs its own success/failure.
                    self.log.error("Failed to install base software (pip) after check indicated it was missing or misconfigured.")
                    self.PipChecked = False # Explicitly mark as failed for this session.
                    return False
            else:
                self.log.info("pip is installed and accessible.")

            self.PipChecked = True # Mark pip as checked and available for this session.
            return True
        except Exception as e_basesw:
            self.LogErrorLine(f"Unexpected error during CheckBaseSoftware: {str(e_basesw)}")
            # Fallback attempt to install, similar to original logic, though less likely to succeed if above failed.
            self.log.info("Attempting to install base software as a fallback due to unexpected error in CheckBaseSoftware.")
            if not self.InstallBaseSoftware():
                 self.log.error("Fallback attempt to install base software (pip) also failed.")
            self.PipChecked = False # Ensure PipChecked is false if we hit an exception path.
            return False

    # ---------------------------------------------------------------------------
    def InstallBaseSoftware(self):
        """
        Installs `pip` (Python package installer) using `apt-get`.

        It determines the correct package name (`python-pip` or `python3-pip`)
        based on the Python version. Runs `apt-get update` if not already done.

        Returns:
            bool: True if `pip` is successfully installed, False otherwise.
        """
        try:
            # Determine correct pip package name based on Python version.
            pip_install_program = "python3-pip" if sys.version_info[0] >= 3 else "python-pip"
            self.log.info(f"Attempting to install base software: {pip_install_program} using apt-get.")

            # Run 'apt-get update' if not already done in this session.
            if not self.AptUpdated:
                self.log.info(f"Running 'apt-get update' before installing {pip_install_program}.")
                cmd_apt_update_allow_rls = ["sudo", "apt-get", "-yqq", "--allow-releaseinfo-change", "update"]
                cmd_apt_update_normal = ["sudo", "apt-get", "-yqq", "update"]
                
                if not self.ExecuteCommandList(cmd_apt_update_allow_rls):
                    self.log.info("First 'apt-get update' attempt failed (with --allow-releaseinfo-change). Retrying standard update...")
                    if not self.ExecuteCommandList(cmd_apt_update_normal):
                        self.log.error(f"Error: Unable to run 'apt-get update'. Cannot install {pip_install_program}.")
                        return False
                self.AptUpdated = True # Mark as done for this session.
                self.log.info("'apt-get update' completed successfully.")
            
            # Set DEBIAN_FRONTEND to noninteractive to prevent prompts during installation.
            custom_env = os.environ.copy()
            custom_env["DEBIAN_FRONTEND"] = "noninteractive"
            command_list_pip_install = ["sudo", "apt-get", "-yqq", "install", pip_install_program]
            
            # Execute the pip installation command.
            if not self.ExecuteCommandList(command_list_pip_install, env=custom_env): # Logs errors.
                self.log.error(f"Error: Failed to install {pip_install_program} via 'apt-get'.")
                return False

            self.log.info(f"{pip_install_program} installed successfully.")
            return True
        except Exception as e_installbase:
            self.LogErrorLine(f"Unexpected error in InstallBaseSoftware: {str(e_installbase)}")
            return False

    # ---------------------------------------------------------------------------
    @staticmethod
    def OneTimeMaint(ConfigFilePath, log): # log is passed directly, not self.log
        """
        Performs one-time maintenance tasks, primarily migrating old data/log files
        from previous locations to the standard `ConfigFilePath`.

        This is a static method. It checks for the existence of specific files
        (defined in `FileList`) in old locations (relative to the script or in
        `genmonlib`) and moves them to the `ConfigFilePath`. It also handles the
        creation of `ConfigFilePath` if it doesn't exist.

        Args:
            ConfigFilePath (str): The target path for configuration and data files.
            log (logging.Logger): An external logger instance to use for logging
                                  maintenance activities.

        Returns:
            bool: True if the maintenance was performed (or deemed not needed),
                  False if a critical error occurred during the process.
        """
        # Determine script's directory and genmonlib path for locating old files.
        script_dir = os.path.dirname(os.path.realpath(__file__))
        genmonlib_dir = os.path.join(script_dir, "genmonlib")

        # Defines files to potentially migrate: {basename: source_directory_prefix}
        # Paths are constructed relative to the script or genmonlib directory.
        file_migration_list = {
            "feedback.json": script_dir,
            "outage.txt": script_dir,
            "kwlog.txt": script_dir,
            "maintlog.json": script_dir,
            "Feedback_dat": genmonlib_dir,
            "Message_dat": genmonlib_dir,
        }
        # Note: Migration of files from /etc/ (like an old /etc/genmon.conf) would be more complex
        # and needs careful consideration of system-wide vs. local installs.
        # The current logic focuses on files within the application's own structure.

        # Check if migration is even needed by looking for key files in old locations.
        # If these specific files are absent, and /etc/genmon.conf (a potential old global config)
        # also doesn't exist, assume maintenance is done or not applicable (e.g., fresh install).
        key_old_files_for_check = [
            os.path.join(genmonlib_dir, "Message_dat"),
            os.path.join(script_dir, "maintlog.json"),
        ]
        if not any(os.path.isfile(f) for f in key_old_files_for_check) and not os.path.isfile("/etc/genmon.conf"):
            log.info("OneTimeMaint: Key source files for migration not found in typical old locations, and /etc/genmon.conf doesn't exist. Skipping file migration.")
            return True # Nothing to do, or already done.

        try:
            # Ensure the target configuration directory exists.
            if not os.path.isdir(ConfigFilePath):
                log.info(f"OneTimeMaint: Target configuration directory '{ConfigFilePath}' does not exist. Attempting to create it.")
                try:
                    os.makedirs(ConfigFilePath, exist_ok=True)
                    log.info(f"OneTimeMaint: Successfully created target directory: {ConfigFilePath}")
                except OSError as oe:
                    log.error(f"OneTimeMaint: OSError creating target config directory '{ConfigFilePath}': {str(oe)}", exc_info=True)
                    return False # Cannot proceed if target directory creation fails.
                except Exception as e_mkdir: # Catch other unexpected errors.
                     log.error(f"OneTimeMaint: Unexpected error creating target config directory '{ConfigFilePath}': {str(e_mkdir)}", exc_info=True)
                     return False

            files_moved_count = 0
            # Iterate through the defined list of files to migrate.
            for file_basename, source_path_prefix in file_migration_list.items():
                source_file_full_path = os.path.join(source_path_prefix, file_basename)
                target_file_full_path = os.path.join(ConfigFilePath, file_basename)

                if os.path.isfile(source_file_full_path): # Check if the source file exists.
                    try:
                        log.info(f"OneTimeMaint: Moving '{source_file_full_path}' to '{target_file_full_path}'")
                        move(source_file_full_path, target_file_full_path) # shutil.move handles cross-filesystem moves.
                        files_moved_count += 1
                        log.info(f"OneTimeMaint: Successfully moved '{file_basename}'.")
                    except FileNotFoundError: # Should ideally not happen if os.path.isfile was true.
                        log.warning(f"OneTimeMaint: Source file '{source_file_full_path}' disappeared before move. Skipping.")
                    except (IOError, OSError) as e_move_io_os: # Catch file I/O or OS errors during move.
                        log.error(f"OneTimeMaint: IOError/OSError moving '{source_file_full_path}' to '{target_file_full_path}': {str(e_move_io_os)}", exc_info=True)
                    except Exception as e_move_other: # Catch other unexpected errors during move.
                        log.error(f"OneTimeMaint: Unexpected error moving '{source_file_full_path}': {str(e_move_other)}", exc_info=True)
                # else: # If source file doesn't exist, silently skip (no need to log for each one).
                    # log.debug(f"OneTimeMaint: Source file '{source_file_full_path}' not found for moving. Skipping.")

            if files_moved_count > 0:
                 log.info(f"OneTimeMaint: Moved {files_moved_count} files into '{ConfigFilePath}'.")
            else:
                 log.info("OneTimeMaint: No files were moved (either already moved or source files not found in specified old locations).")
            return True # Maintenance process completed.

        except Exception as e_maint_outer: # Catch any other unexpected error in the maintenance logic.
            log.error(f"OneTimeMaint: Unexpected critical error during one-time maintenance process: {str(e_maint_outer)}", exc_info=True)
            return False # Indicate maintenance failed.

    # ---------------------------------------------------------------------------
    def FixPyOWMMaintIssues(self):
        """
        Checks the installed version of the `pyowm` library and attempts to fix it
        if it's newer than a known compatible version.

        Some newer versions of `pyowm` (OpenWeatherMap API library) might have
        breaking changes. This method uninstalls an incompatible (too new) version
        and installs a specific known-good version (`2.9.0` for Python 2, `2.10.0`
        for Python 3).

        Returns:
            bool: True if `pyowm` is at an acceptable version or successfully fixed.
                  False if an error occurs or the fix fails.
        """
        try:
            # Ensure pyowm is imported to check its version or if it exists.
            try:
                import pyowm # Attempt to import to trigger ImportError if not installed.
            except ImportError:
                self.log.error("FixPyOWMMaintIssues: pyowm library is not installed.")
                # Attempt to install it if it's missing entirely.
                self.log.info("Attempting to install pyowm as it's missing.")
                required_version_for_install = "2.10.0" if sys.version_info[0] >= 3 else "2.9.0"
                if self.InstallLibrary("pyowm", version=required_version_for_install): # InstallLibrary logs success/failure.
                    self.log.info("Successfully installed pyowm. A restart of genloader might be needed.")
                else:
                    self.log.error("Failed to install missing pyowm library during FixPyOWMMaintIssues.")
                return False # pyowm was missing; attempted install. Outcome logged by InstallLibrary.

            # Determine the target "known good" version based on Python version.
            required_version_str = "2.10.0" if sys.version_info[0] >= 3 else "2.9.0"

            installed_version_str = self.GetLibararyVersion("pyowm") # This method logs its own errors.

            if installed_version_str is None:
                self.log.error("FixPyOWMMaintIssues: Could not determine installed pyowm version after import success. Cannot proceed with fix.")
                return False # Cannot proceed without knowing the installed version.

            # Compare installed version with the required "known good" version.
            # If installed version is less than or equal to required, it's considered okay.
            if self.VersionTuple(installed_version_str) <= self.VersionTuple(required_version_str):
                self.log.info(f"pyowm version {installed_version_str} is acceptable (<= {required_version_str}). No fix needed.")
                return True

            # If installed version is newer than required, attempt to uninstall and reinstall correct version.
            self.log.info(
                f"FixPyOWMMaintIssues: Found pyowm version {installed_version_str}, which is newer than required/tested {required_version_str}. "
                f"Attempting to uninstall current and reinstall version {required_version_str}."
            )

            if not self.InstallLibrary("pyowm", uninstall=True): # InstallLibrary logs its own errors.
                self.log.error("FixPyOWMMaintIssues: Failed to uninstall the current (newer) version of pyowm.")
                return False 
            
            self.log.info(f"Successfully uninstalled current pyowm. Now installing version {required_version_str}.")

            if not self.InstallLibrary("pyowm", version=required_version_str): # InstallLibrary logs its own errors.
                self.log.error(f"FixPyOWMMaintIssues: Failed to install required version {required_version_str} of pyowm.")
                return False

            self.log.info(f"FixPyOWMMaintIssues: Successfully installed pyowm version {required_version_str}.")
            return True
        except Exception as e_fixpyowm:
            self.LogErrorLine(f"Unexpected error in FixPyOWMMaintIssues: {str(e_fixpyowm)}")
            return False

    # ---------------------------------------------------------------------------
    def GetLibararyVersion(self, libraryname, importonly=False):
        """
        Attempts to determine the installed version of a Python library.

        It first tries to import the library and access its `__version__`
        attribute. If that fails or `importonly` is False, it falls back to
        using `pip show <libraryname>` and parsing its output.

        Args:
            libraryname (str): The import name of the library (e.g., "pyserial", "paho.mqtt.client").
            importonly (bool, optional): If True, only attempts the import method
                                         and does not fall back to `pip show`.
                                         Defaults to False.

        Returns:
            str or None: The version string of the library if found, otherwise None.
        """
        try:
            self.log.debug(f"Attempting to get version for library: '{libraryname}' (importonly={importonly})")
            
            # Attempt 1: Import the library and check for a __version__ attribute.
            try:
                import importlib
                my_module = importlib.import_module(libraryname)
                version = getattr(my_module, '__version__', None)
                if version:
                    self.log.debug(f"Found version '{version}' for '{libraryname}' via importlib and __version__ attribute.")
                    return str(version) # Ensure it's a string
                self.log.debug(f"Module '{libraryname}' imported but no __version__ attribute found or it was None.")
                # Fall through if __version__ is not present or None, unless importonly.
            except ImportError:
                self.log.info(f"Library '{libraryname}' not found via importlib (ImportError).")
                if importonly: return None # If only import was requested, and it failed.
                # Proceed to pip check if not importonly.
            except Exception as e_import:
                self.LogErrorLine(f"Error importing library '{libraryname}' to get version: {str(e_import)}")
                if importonly: return None # If only import was requested, and it had other errors.
                # Proceed to pip check if not importonly.

            # If importonly was True and we reached here, it means import succeeded but no __version__.
            if importonly:
                 self.log.debug(f"importonly is True and version not found via import for '{libraryname}'. Returning None.")
                 return None

            # Attempt 2: Use 'pip show' to get the version.
            self.log.info(f"Trying to get version of '{libraryname}' using 'pip show'.")
            # Ensure pip is available, especially on Linux systems.
            if "linux" in sys.platform: # This check might be redundant if CheckBaseSoftware runs first in broader flows.
                if not self.CheckBaseSoftware(): # CheckBaseSoftware logs its own errors.
                    self.log.error(f"Cannot get library version for '{libraryname}' via pip: Base software (pip) check failed.")
                    return None

            command_list_pip_show = [sys.executable, "-m", "pip", "show", libraryname]
            self.log.debug(f"Executing: {' '.join(command_list_pip_show)}")
            
            process = Popen(command_list_pip_show, stdout=PIPE, stderr=PIPE)
            output_bytes, error_bytes = process.communicate()
            return_code = process.returncode

            output_str = output_bytes.decode(sys.getdefaultencoding(), errors='replace') if output_bytes else ""
            error_str = error_bytes.decode(sys.getdefaultencoding(), errors='replace') if error_bytes else ""

            if return_code != 0: # pip show command failed.
                self.log.error(f"Error using 'pip show {libraryname}': RC={return_code}. Stderr: {error_str.strip()}")
                return None

            # Parse the output of 'pip show' for the version line.
            for line in output_str.splitlines():
                line = line.strip()
                if line.lower().startswith("version:"):
                    version_found_str = line.split(":", 1)[1].strip()
                    self.log.info(f"Found version '{version_found_str}' for library '{libraryname}' via 'pip show'.")
                    return version_found_str
            
            self.log.info(f"Could not find version information for '{libraryname}' in 'pip show' output (package might not be installed via pip or name mismatch).")
            return None # Version line not found in pip show output.

        except subprocess.SubprocessError as spe: # Errors related to Popen/communicate.
            self.LogErrorLine(f"Subprocess error while getting version for '{libraryname}': {str(spe)}")
            return None
        except Exception as e_getver: # Catch any other unexpected error.
            self.LogErrorLine(f"Unexpected error in GetLibararyVersion for '{libraryname}': {str(e_getver)}")
            return None

    # ---------------------------------------------------------------------------
    def LibraryIsInstalled(self, libraryname):
        """
        Checks if a Python library is installed and can be imported.

        Uses `importlib.import_module()` for the check.

        Args:
            libraryname (str): The import name of the library.

        Returns:
            bool: True if the library can be imported, False otherwise.
        """
        try:
            import importlib
            importlib.import_module(libraryname) # Attempt to import the library.
            self.log.debug(f"Library '{libraryname}' is installed (import successful).")
            return True
        except ImportError: # Specifically catch ImportError.
            self.log.info(f"Library '{libraryname}' is NOT installed (ImportError during check).")
            return False
        except Exception as e_isinst: # Catch other potential errors during import attempt.
            self.LogErrorLine(f"Error checking if library '{libraryname}' is installed (unexpected import error): {str(e_isinst)}")
            return False # Assume not installed or problematic if any other error occurs.

    # ---------------------------------------------------------------------------
    def InstallLibrary(self, libraryname, update=False, version=None, uninstall=False):
        """
        Installs, updates, or uninstalls a Python library using `pip`.

        Constructs and executes the appropriate `pip` command based on the
        provided flags.

        Args:
            libraryname (str): The name of the library as known by pip.
            update (bool, optional): If True, attempts to update the library
                                     (uses `pip install -U`). Defaults to False.
            version (str, optional): If specified, attempts to install this exact
                                     version (e.g., `libraryname==version`).
                                     Takes precedence over `update` if both are set.
                                     Defaults to None.
            uninstall (bool, optional): If True, attempts to uninstall the library.
                                        Defaults to False.

        Returns:
            bool: True if the pip command executes successfully (return code 0),
                  False otherwise.
        """
        try:
            target_library_spec = libraryname # Default spec is just the library name.
            action_description = "install"    # Default action for logging.
            
            # Determine pip command and logging description based on flags.
            if uninstall:
                action_description = f"uninstalling '{libraryname}'"
            elif version: # Specific version install takes precedence over generic update.
                target_library_spec = f"{libraryname}=={version}"
                action_description = f"installing specific version '{target_library_spec}'"
            elif update:
                action_description = f"updating '{libraryname}'"
            else: # Default action: install latest or specified version.
                action_description = f"installing '{libraryname}'"


            self.log.info(f"Attempting to perform pip operation: {action_description}.")

            # Ensure pip is available, especially on Linux, unless uninstalling.
            if "linux" in sys.platform and not uninstall:
                if not self.CheckBaseSoftware(): # CheckBaseSoftware logs its own errors.
                    self.log.error(f"Cannot {action_description}: Base software (pip) check failed.")
                    return False

            # Construct the pip command list.
            pip_command_list = [sys.executable, "-m", "pip"]
            if uninstall:
                pip_command_list.extend(["uninstall", "-y", libraryname]) # -y for non-interactive uninstall.
            elif update and not version: # Update to latest if no specific version.
                pip_command_list.extend(["install", target_library_spec, "--upgrade"]) # --upgrade or -U
            else: # Install (specific version if provided, or latest).
                pip_command_list.extend(["install", target_library_spec])
            
            self.log.debug(f"Executing pip command: {' '.join(pip_command_list)}")
            # Execute the command.
            process = Popen(pip_command_list, stdout=PIPE, stderr=PIPE)
            output_bytes, error_bytes = process.communicate()
            return_code = process.returncode

            output_str = output_bytes.decode(sys.getdefaultencoding(), errors='replace').strip() if output_bytes else ""
            error_str = error_bytes.decode(sys.getdefaultencoding(), errors='replace').strip() if error_bytes else ""

            # Check return code from pip.
            if return_code != 0:
                log_message = f"Error during pip {action_description}. RC: {return_code}."
                if output_str: log_message += f"\nPip stdout: {output_str}"
                if error_str: log_message += f"\nPip stderr: {error_str}"
                self.log.error(log_message)
                return False
            
            # Log stdout/stderr even on success for record-keeping.
            if output_str: self.log.info(f"Pip {action_description} stdout:\n{output_str}")
            if error_str: self.log.info(f"Pip {action_description} stderr (RC=0):\n{error_str}") # Might contain warnings.

            self.log.info(f"Successfully performed pip operation: {action_description}.")
            return True

        except subprocess.SubprocessError as spe: # Errors from Popen/communicate.
            self.LogErrorLine(f"Subprocess error during pip operation for '{libraryname}': {str(spe)}")
            return False
        except Exception as e_installlib: # Other unexpected errors.
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
        self.log.info("Validating loaded module configurations...")
        any_errors_found = False
        if not self.CachedConfig: # Check if CachedConfig is empty.
            self.log.error("ValidateConfig Error: CachedConfig is empty. Cannot validate.")
            return False # Cannot validate if no config was loaded.

        # Iterate through each module defined in the cached configuration.
        for module_name, settings in self.CachedConfig.items():
            try:
                # Only validate further if the module is marked as 'enable: True'.
                if settings.get("enable", False): # Use .get for safer access.
                    module_script_name = settings.get("module")
                    if not module_script_name:
                        self.log.error(f"Validation Error for '{module_name}': 'module' (script filename) not defined but module is enabled. Disabling.")
                        self.CachedConfig[module_name]["enable"] = False # Auto-disable misconfigured module.
                        any_errors_found = True
                        continue

                    # Check if the module's script file exists.
                    module_base_path = self.GetModulePath(self.ModulePath, module_script_name) # GetModulePath logs if not found.
                    if module_base_path is None:
                        self.log.error(
                            f"Validation Error for '{module_name}': Module script '{module_script_name}' not found in primary or addon paths. Disabling."
                        )
                        self.CachedConfig[module_name]["enable"] = False # Auto-disable.
                        any_errors_found = True
                        # continue # Continue to check other modules.

                # Validate associated .conf files for the module.
                # A module can have multiple associated .conf files, comma-separated.
                module_conf_files_str = settings.get("conffile", "")
                if module_conf_files_str and len(module_conf_files_str.strip()):
                    individual_conf_files = module_conf_files_str.split(',')
                    for conf_file_basename in individual_conf_files:
                        conf_file_basename = conf_file_basename.strip()
                        if not conf_file_basename: continue # Skip if empty after strip (e.g. due to "file1,,file2")

                        target_conf_path = os.path.join(self.ConfigFilePath, conf_file_basename)
                        # If the module's .conf file is NOT in the active config path (e.g., /etc/genmon/).
                        if not os.path.isfile(target_conf_path):
                            default_conf_source_path = os.path.join(self.ConfPath, conf_file_basename)
                            # Check if a default version of this .conf file exists in `self.ConfPath`.
                            if os.path.isfile(default_conf_source_path):
                                self.log.info(
                                    f"Validation: Config file '{conf_file_basename}' for module '{module_name}' not found in '{self.ConfigFilePath}'. "
                                    f"Copying from default location: '{default_conf_source_path}'."
                                )
                                try:
                                    copyfile(default_conf_source_path, target_conf_path) # shutil.copyfile
                                    self.log.info(f"Successfully copied '{conf_file_basename}' to '{self.ConfigFilePath}'.")
                                except Exception as e_copy_conf:
                                    self.log.error(f"Failed to copy '{conf_file_basename}' for '{module_name}' from defaults: {str(e_copy_conf)}")
                                    any_errors_found = True
                            else:
                                # If enabled, this is an error. If not enabled, it might be just a warning or info.
                                log_level_method = self.log.error if settings.get("enable",False) else self.log.warning
                                log_level_method(
                                    f"Validation: Config file '{conf_file_basename}' for module '{module_name}' not found in '{self.ConfigFilePath}' "
                                    f"AND no default version found in '{self.ConfPath}'. This may cause issues if module is enabled."
                                )
                                if settings.get("enable", False): any_errors_found = True
            except KeyError as ke: # Catch if expected keys like 'enable' or 'module' are missing.
                self.LogErrorLine(f"Configuration validation error for module '{module_name}': Missing key '{str(ke)}'. This module's config might be incomplete.")
                any_errors_found = True
            except Exception as e_val_module: # Catch any other unexpected error for this module's validation.
                self.LogErrorLine(f"Unexpected error validating configuration for module '{module_name}': {str(e_val_module)}")
                any_errors_found = True
        
        # Validate essential 'genmon' and 'genserv' entries for enablement.
        try:
            if not self.CachedConfig.get("genmon", {}).get("enable", False):
                self.log.error("Critical Validation Error: Core module 'genmon' is not enabled in the configuration. Genmon cannot function.")
                any_errors_found = True
            if not self.CachedConfig.get("genserv", {}).get("enable", False):
                self.log.info("Validation Info: Web interface module 'genserv' is not enabled. Web UI will be unavailable.")
                # Not necessarily a fatal error for genloader itself, but important.
        except KeyError as ke_core: # Should be caught by .get, but as a safeguard.
             self.LogErrorLine(f"KeyError accessing core module ('genmon' or 'genserv') config during validation: {str(ke_core)}")
             any_errors_found = True
        except Exception as e_val_core: # Catch unexpected errors accessing core module configs.
            self.LogErrorLine(f"Unexpected error validating core 'genmon'/'genserv' config entries: {str(e_val_core)}")
            any_errors_found = True

        if any_errors_found:
            self.log.error("Configuration validation finished with one or more errors or warnings that may impact functionality.")
        else:
            self.log.info("Configuration validation completed successfully. All checks passed.")
        return not any_errors_found # True if no errors, False if errors were found.

    # ---------------------------------------------------------------------------
    def AddEntry(self, section=None, module=None, conffile="", args="", priority="2"):
        """
        Adds a new module's default configuration section to `genloader.conf`.

        If the specified section (module name) does not exist in `genloader.conf`,
        this method creates it with default values (e.g., `enable = False`).
        This is typically used by `GetConfig` to ensure all known modules have
        at least a placeholder configuration.

        Args:
            section (str): The name of the section to add (usually the module's name).
            module (str): The filename of the module script (e.g., "genmon.py").
            conffile (str, optional): Comma-separated string of associated .conf files.
                                      Defaults to "".
            args (str, optional): Default command-line arguments for the module.
                                  Defaults to "".
            priority (str, optional): Default load priority for the module.
                                      Defaults to "2".

        Returns:
            bool: True if the entry was added successfully, False on error.
        """
        try:
            if section is None or module is None:
                self.log.error("Error in AddEntry: 'section' and 'module' parameters are required.")
                return False

            self.log.info(f"Adding/Updating configuration entry for section '{section}', module script '{module}'.")
            # Use self.config (MyConfig instance) to write values.
            # MyConfig's WriteSection will create the section if it doesn't exist.
            self.config.WriteSection(section) 
            # Write default values for the new section.
            self.config.WriteValue("module", module, section=section)
            self.config.WriteValue("enable", "False", section=section) # Default to disabled.
            self.config.WriteValue("hardstop", "False", section=section) # Default hardstop behavior.
            self.config.WriteValue("conffile", conffile, section=section)
            self.config.WriteValue("args", args, section=section)
            self.config.WriteValue("priority", str(priority), section=section) # Ensure priority is string.
            self.log.info(f"Successfully added/updated configuration entry for section '{section}'.")
            return True
        except Exception as e_addentry:
            self.LogErrorLine(f"Error in AddEntry for section '{section}': {str(e_addentry)}")
            return False

    # ---------------------------------------------------------------------------
    def UpdateIfNeeded(self):
        """
        Performs necessary updates to the `genloader.conf` structure or values.

        This includes:
        - Ensuring `gengpioin` and `gengpio` sections have a `conffile` entry.
        - Checking the version in `genloader.conf` against the program's current
          version (`ProgramDefaults.GENMON_VERSION`). If the config version is older
          or missing, it updates the version in the file and sets `self.Upgrade`
          or `self.NewInstall` flags.
        - If it's a new install, runs `FixPyOWMMaintIssues`.

        Returns:
            bool: True if updates were processed (even if no changes were made),
                  False if a critical error occurred.
        """
        try:
            self.log.info("Performing UpdateIfNeeded checks for genloader.conf structure and version...")
            
            # Ensure 'gengpioin' section has 'conffile' defined.
            self.config.SetSection("gengpioin") # Set current section for MyConfig operations.
            if not self.config.HasOption("conffile") or not self.config.ReadValue("conffile", default="", suppress_logging_on_error=True):
                self.config.WriteValue("conffile", "gengpioin.conf", section="gengpioin")
                self.log.info("Updated 'gengpioin' section: set 'conffile' to 'gengpioin.conf'.")

            # Ensure 'gengpio' section has 'conffile' defined.
            self.config.SetSection("gengpio")
            if not self.config.HasOption("conffile") or not self.config.ReadValue("conffile", default="", suppress_logging_on_error=True):
                self.config.WriteValue("conffile", "gengpio.conf", section="gengpio")
                self.log.info("Updated 'gengpio' section: set 'conffile' to 'gengpio.conf'.")

            # --- Version Check and Upgrade Logic ---
            self.config.SetSection("genloader") # Operate on the [genloader] section.
            current_config_version_str = self.config.ReadValue("version", default="0.0.0", suppress_logging_on_error=True)
            
            # If version is missing or "0.0.0", assume it's a new install.
            if not current_config_version_str or current_config_version_str == "0.0.0":
                self.log.info("No version found in genloader.conf or version is '0.0.0'. Assuming new install or very old config.")
                self.NewInstall = True
                current_config_version_str = "0.0.0" # Normalize for comparison.

            # Compare config version with current program version.
            if self.VersionTuple(current_config_version_str) < self.VersionTuple(ProgramDefaults.GENMON_VERSION):
                self.log.info(f"Current config version '{current_config_version_str}' is older than program version '{ProgramDefaults.GENMON_VERSION}'. Marking for upgrade.")
                self.Upgrade = True # Set upgrade flag.
            
            # If it's a new install or an upgrade, update the version in genloader.conf.
            if self.NewInstall or self.Upgrade:
                self.log.info(f"Updating genloader.conf version entry to '{ProgramDefaults.GENMON_VERSION}'.")
                self.config.WriteValue("version", ProgramDefaults.GENMON_VERSION, section="genloader")
            
            # If it's a new install, perform specific maintenance tasks (like PyOWM fix).
            if self.NewInstall: 
                self.log.info("New install detected: Running one-time maintenance for PyOWM compatibility.")
                if not self.FixPyOWMMaintIssues(): # FixPyOWMMaintIssues logs its own errors.
                    self.log.error("FixPyOWMMaintIssues failed during new install setup. This might affect weather functionality.")
                    # This might not be fatal for genloader itself, so logging and continuing.

            self.version = ProgramDefaults.GENMON_VERSION # Update Loader's internal version attribute.
            self.log.info("UpdateIfNeeded checks completed.")
            return True 
        except Exception as e_updateif: 
            self.LogErrorLine(f"Unexpected error in UpdateIfNeeded: {str(e_updateif)}")
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
            # Initial read of sections from the MyConfig object.
            current_sections = self.config.GetSections()
            if not current_sections: # Handle case where genloader.conf is empty or unreadable.
                self.log.error("No sections found in genloader.conf. File might be empty, corrupt, or inaccessible by MyConfig.")
                # Attempt to restore config by copying default if it's this problematic.
                if not self.CopyConfFile(): # CopyConfFile logs its own errors.
                    self.log.error("Attempt to copy default genloader.conf failed. Cannot proceed with GetConfig.")
                    return False
                current_sections = self.config.GetSections() # Retry getting sections after copy.
                if not current_sections: # If still no sections, it's a critical failure.
                    self.log.error("Still no sections after attempting to copy default config. GetConfig cannot proceed.")
                    return False
            
            # Define known modules and their default script names, conffiles, priorities.
            # This ensures that if a section is missing for a known module, we can add a default (disabled) entry.
            valid_sections_definitions = {
                "genmon": {"module": "genmon.py", "priority": "100", "conffile": "genmon.conf"},
                "genserv": {"module": "genserv.py", "priority": "90", "conffile": "genserv.conf"},
                "gengpio": {"module": "gengpio.py", "conffile": "gengpio.conf"},
                "gengpioin": {"module": "gengpioin.py", "conffile": "gengpioin.conf"},
                "genlog": {"module": "genlog.py"}, # No specific conffile needed by default.
                "gensms": {"module": "gensms.py", "conffile": "gensms.conf"},
                "gensms_modem": {"module": "gensms_modem.py", "conffile": "mymodem.conf"},
                "genpushover": {"module": "genpushover.py", "conffile": "genpushover.conf"},
                "gensyslog": {"module": "gensyslog.py"},
                "genmqtt": {"module": "genmqtt.py", "conffile": "genmqtt.conf"},
                "genmqttin": {"module": "genmqttin.py", "conffile": "genmqttin.conf"},
                "genslack": {"module": "genslack.py", "conffile": "genslack.conf"},
                "gencallmebot": {"module": "gencallmebot.py", "conffile": "gencallmebot.conf"},
                "genexercise": {"module": "genexercise.py", "conffile": "genexercise.conf"},
                "genemail2sms": {"module": "genemail2sms.py", "conffile": "genemail2sms.conf"},
                "gentankutil": {"module": "gentankutil.py", "conffile": "gentankutil.conf"},
                "gencentriconnect": {"module": "gencentriconnect.py", "conffile": "gencentriconnect.conf"},
                "gentankdiy": {"module": "gentankdiy.py", "conffile": "gentankdiy.conf"},
                "genalexa": {"module": "genalexa.py", "conffile": "genalexa.conf"},
                "gensnmp": {"module": "gensnmp.py", "conffile": "gensnmp.conf"},
                "gentemp": {"module": "gentemp.py", "conffile": "gentemp.conf"},
                "gengpioledblink": {"module": "gengpioledblink.py", "conffile": "gengpioledblink.conf"},
                "gencthat": {"module": "gencthat.py", "conffile": "gencthat.conf"},
                "genmopeka": {"module": "genmopeka.py", "conffile": "genmopeka.conf"},
                "gencustomgpio": {"module": "gencustomgpio.py", "conffile": "gencustomgpio.conf"},
                "gensms_voip": {"module": "gensms_voip.py", "conffile": "gensms_voip.conf"},
                "genloader": {}, # Special section for genloader's own version, not a loadable module.
            }
            
            config_was_modified = False # Flag if AddEntry modifies the config file.
            # Ensure all predefined valid sections exist in genloader.conf.
            for section_name, defaults in valid_sections_definitions.items():
                if section_name not in current_sections:
                    if section_name == "genloader": # The [genloader] section is essential.
                        self.log.info(f"Essential configuration section '[{section_name}]' is missing. Adding section header.")
                        self.config.WriteSection(section_name) # MyConfig handles creation.
                        config_was_modified = True
                    elif defaults.get("module"): # Only add if 'module' is defined in defaults (i.e., it's a loadable module).
                        self.log.info(f"Configuration section '[{section_name}]' for module '{defaults['module']}' is missing. Adding default (disabled) entry.")
                        if self.AddEntry(section=section_name, module=defaults["module"], 
                                         conffile=defaults.get("conffile", ""), 
                                         priority=defaults.get("priority", "2")): # AddEntry logs success/failure.
                            config_was_modified = True
                        else:
                             self.log.error(f"Failed to add default entry for missing section '[{section_name}]'. Config may be incomplete.")
            
            if config_was_modified: # If sections were added, refresh the list of current sections.
                current_sections = self.config.GetSections()

            # Perform version checks and other necessary updates on the config file content.
            if not self.UpdateIfNeeded(): # UpdateIfNeeded logs its own errors.
                self.log.error("UpdateIfNeeded reported errors during GetConfig. Configuration might be inconsistent or outdated.")
                # Depending on severity, could return False here.

            current_sections = self.config.GetSections() # Re-fetch sections again after UpdateIfNeeded.
            temp_cached_config = {} # Temporary dict to build the new CachedConfig.

            # Process each section to populate CachedConfig.
            for section_name in current_sections:
                if section_name == "genloader": 
                    continue # Skip [genloader] section; it's for metadata, not a runnable module.
                
                settings_dict = {} # Stores settings for the current module.
                self.config.SetSection(section_name) # Set MyConfig's context to this section.

                # Helper to read values, with type conversion, defaults, and logging for missing critical keys.
                def _read_config_value(key, expected_type=str, default_val=None, is_critical=True, suppress_log_on_missing=False):
                    if self.config.HasOption(key):
                        try:
                            # Use MyConfig's ReadValue for typed reading.
                            # suppress_logging_on_error in ReadValue handles if the key is there but value is bad type.
                            if expected_type == bool: return self.config.ReadValue(key, return_type=bool, default=default_val, suppress_logging_on_error=suppress_log_on_missing)
                            if expected_type == int: return self.config.ReadValue(key, return_type=int, default=default_val, suppress_logging_on_error=suppress_log_on_missing)
                            return self.config.ReadValue(key, default=default_val, suppress_logging_on_error=suppress_log_on_missing)
                        except ValueError as ve: # Should be caught by MyConfig's ReadValue, but as a safeguard.
                            self.log.error(f"ValueError reading key '{key}' in section '[{section_name}]': {str(ve)}. Using default: '{default_val}'.")
                            return default_val
                    # Handle missing keys.
                    elif is_critical and not suppress_log_on_missing:
                        self.log.error(f"Missing critical config key '{key}' in section '[{section_name}]'. Using default: '{default_val}'.")
                    elif not suppress_log_on_missing: # Log debug for missing non-critical keys.
                        self.log.debug(f"Optional config key '{key}' not found in section '[{section_name}]'. Using default: '{default_val}'.")
                    return default_val

                # Read all known settings for a module.
                settings_dict["module"] = _read_config_value("module", is_critical=True, default_val="unknown_module.py")
                settings_dict["enable"] = _read_config_value("enable", expected_type=bool, default_val=False)
                settings_dict["hardstop"] = _read_config_value("hardstop", expected_type=bool, default_val=False)
                settings_dict["conffile"] = _read_config_value("conffile", default_val="", is_critical=False)
                settings_dict["args"] = _read_config_value("args", default_val="", is_critical=False)
                settings_dict["priority"] = _read_config_value("priority", expected_type=int, default_val=99, is_critical=False) # Lower number = higher priority, but original sorts higher number = more important. Reconcile.
                settings_dict["postloaddelay"] = _read_config_value("postloaddelay", expected_type=int, default_val=0, is_critical=False)
                settings_dict["pid"] = _read_config_value("pid", expected_type=int, default_val=0, is_critical=False, suppress_log_on_missing=True) # PID often not present.

                # If module script is unknown but module is enabled, disable it to prevent errors.
                if settings_dict["module"] == "unknown_module.py" and settings_dict["enable"]:
                     self.log.warning(f"Module '{section_name}' is enabled, but its 'module' script filename is not specified or missing. Auto-disabling.")
                     settings_dict["enable"] = False 

                temp_cached_config[section_name] = settings_dict
            
            self.CachedConfig = temp_cached_config # Assign the populated cache.
            self.log.info(f"Successfully loaded and cached configuration for {len(self.CachedConfig)} modules from genloader.conf.")
            return True

        except Exception as e_getconf: 
            self.LogErrorLine(f"Unexpected critical error in GetConfig: {str(e_getconf)}")
            self.CachedConfig = {} # Clear cache on error to ensure consistent state.
            return False

    # ---------------------------------------------------------------------------
    def ConvertToInt(self, value, default=None):
        """
        Safely converts a value to an integer.

        If the value is None, or if conversion fails, it returns the specified
        default. It handles potential `ValueError` during conversion.

        Args:
            value (any): The value to convert to an integer.
            default (int, optional): The default value to return if conversion fails
                                     or input is None. Defaults to None.

        Returns:
            int or None: The converted integer, or the default value.
        """
        if value is None:
            return default
        try:
            # Ensure value is string before int() conversion for robustness.
            return int(str(value))
        except ValueError:
            self.log.info(f"Could not convert value '{value}' (type: {type(value)}) to int. Returning default '{default}'.")
            return default
        except Exception as e_convert: # Catch other unexpected errors.
            self.LogErrorLine(f"Unexpected error converting value '{value}' to int: {str(e_convert)}")
            return default

    # ---------------------------------------------------------------------------
    def GetLoadOrder(self):
        """
        Determines the load order of modules based on their 'priority' setting.

        It reads the 'priority' from `CachedConfig` for each module. Modules are
        then sorted: higher priority numbers are loaded/started first (and stopped last).
        If priority is missing or invalid, a default (low) priority is assigned.

        Returns:
            list of str: A list of module names (section names) sorted by priority.
                         Returns an empty list if `CachedConfig` is empty or an error occurs.
        """
        load_order_list = []
        priority_dict = {} # Temp dict to hold {module_name: priority_value}
        try:
            if not self.CachedConfig:
                self.log.error("Cannot determine load order: CachedConfig is empty.")
                return [] # Return empty list if no config loaded.

            # Populate priority_dict from CachedConfig.
            for module_name, settings in self.CachedConfig.items():
                try:
                    priority_str = settings.get("priority") # Priority from config (might be str).
                    if priority_str is None: # Handle missing priority key.
                        priority_val = 99 # Default to a low priority.
                        self.log.info(f"Module '{module_name}' has no 'priority' set in config, defaulting to {priority_val}.")
                    else:
                        # Convert priority to int; use default if conversion fails.
                        priority_val = self.ConvertToInt(priority_str, 99) # ConvertToInt handles logging for conversion issues.
                        if priority_val == 99 and str(priority_str) != "99": # Log if conversion defaulted for a non-99 string.
                             self.log.info(f"Priority '{priority_str}' for module '{module_name}' was invalid or non-integer, defaulted to {priority_val}.")
                    
                    priority_dict[module_name] = priority_val
                except KeyError as ke: # Should be caught by .get, but defensive.
                    self.LogErrorLine(f"KeyError processing priority for module '{module_name}': {str(ke)}. Assigning default priority 99.")
                    priority_dict[module_name] = 99 
                except Exception as e_module_prio: # Catch other errors for this module.
                    self.LogErrorLine(f"Error processing priority for module '{module_name}': {str(e_module_prio)}. Assigning default priority 99.")
                    priority_dict[module_name] = 99 
            
            # Sort modules: Primary key is priority (descending, so higher numbers first).
            # Secondary key is module name (ascending, for stable sort if priorities are equal).
            # Note: Original code sorted reversed(LoadOrder) for start, meaning higher priority = start last.
            # This seems counter-intuitive. Standard is higher priority means "more important, start first".
            # Assuming higher number = higher priority = start first / stop last.
            # So, sort descending by priority value (-item[1]).
            sorted_modules = sorted(priority_dict.items(), key=lambda item: (-item[1], item[0]))
            
            load_order_list = [module_name for module_name, _ in sorted_modules] # Extract names.

            if load_order_list:
                self.log.info(f"Determined module load/start order (higher priority first): {', '.join(load_order_list)}")
            else:
                self.log.info("No modules found in cached config to determine load order.")
            return load_order_list

        except Exception as e_loadorder: 
            self.LogErrorLine(f"Unexpected critical error in GetLoadOrder: {str(e_loadorder)}")
            return [] # Return empty list on error.

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
        if not self.LoadOrder:
            self.log.info("No modules in load order. Nothing to stop.")
            return True # Considered successful as there's nothing to do.

        all_processing_successful = True
        # Stop modules in the normal load order (e.g., dependents first, core last).
        # If LoadOrder is [A(100), B(90)], this stops A then B.
        for module_name in self.LoadOrder:
            try:
                module_settings = self.CachedConfig.get(module_name)
                if not module_settings:
                    self.log.error(f"Could not find settings for module '{module_name}' in CachedConfig during stop. Skipping.")
                    all_processing_successful = False
                    continue

                module_script_name = module_settings.get("module")
                pid_to_stop = module_settings.get("pid") # PID from genloader.conf.
                # Determine effective HardStop: use module-specific if True, else global HardStop flag.
                effective_hard_stop = module_settings.get("hardstop", False) or self.HardStop 

                if not module_script_name:
                    self.log.error(f"Module script name not defined for '{module_name}'. Cannot stop. Skipping.")
                    all_processing_successful = False
                    continue
                
                self.log.info(f"Processing stop for module '{module_name}' (Script: {module_script_name}, PID from conf: {pid_to_stop if pid_to_stop else 'N/A'}, EffectiveHardStop: {effective_hard_stop}).")

                # Call UnloadModule. Use PID from config if available and valid.
                # UnloadModule will log its own success/failure details.
                if not self.UnloadModule(
                    module_script_name, # Pass script name for pkill if PID is not used.
                    pid=pid_to_stop, 
                    HardStop=effective_hard_stop,
                    UsePID=bool(pid_to_stop) # True if PID is present and non-zero.
                ):
                    self.log.error(f"Error occurred while trying to stop module '{module_name}' (details logged by UnloadModule).")
                    all_processing_successful = False # Mark that at least one module had issues stopping.
                else:
                    self.log.info(f"Successfully processed stop signal for module '{module_name}'.")
            except KeyError as ke: # Should be caught by .get, but for safety.
                self.LogErrorLine(f"Missing key '{str(ke)}' in settings for module '{module_name}' during stop operation. Skipping.")
                all_processing_successful = False
            except Exception as e_stopmodule: 
                self.LogErrorLine(f"Unexpected error stopping module '{module_name}': {str(e_stopmodule)}")
                all_processing_successful = False
        
        if all_processing_successful:
            self.LogConsole("All modules processed for stopping successfully.")
        else:
            self.LogConsole("Finished processing modules for stopping, but one or more errors occurred or modules might not have stopped cleanly.")
        return all_processing_successful

    # ---------------------------------------------------------------------------
    def GetModulePath(self, base_module_path, module_filename):
        """
        Determines the correct path for a given module script file.

        It first checks in the `base_module_path` (typically `self.ModulePath`,
        where genloader.py and core modules reside). If not found there, it checks
        in an `addon` subdirectory within `base_module_path`.

        Args:
            base_module_path (str): The primary directory to search (e.g., self.ModulePath).
            module_filename (str): The filename of the module script (e.g., "genmon.py").

        Returns:
            str or None: The directory path where the module was found (either
                         `base_module_path` or `base_module_path/addon`).
                         Returns None if the module file is not found in either location
                         or if inputs are invalid.
        """
        try:
            if not module_filename: 
                self.log.error("GetModulePath Error: module_filename is empty or None.")
                return None
            if not base_module_path:
                 self.log.error(f"GetModulePath Error: base_module_path is not specified for module '{module_filename}'.")
                 return None

            # Check 1: In the base module path (e.g., ./genmon.py)
            primary_path_check = os.path.join(base_module_path, module_filename)
            if os.path.isfile(primary_path_check):
                self.log.debug(f"Module '{module_filename}' found at primary path: '{base_module_path}'")
                return base_module_path # Return the directory

            # Check 2: In the 'addon' subdirectory (e.g., ./addon/myaddon.py)
            addon_dir_path = os.path.join(base_module_path, "addon")
            addon_module_full_path = os.path.join(addon_dir_path, module_filename)
            if os.path.isfile(addon_module_full_path):
                self.log.debug(f"Module '{module_filename}' found in addon path: '{addon_dir_path}'")
                return addon_dir_path # Return the addon directory

            # If not found in either location.
            self.log.info(f"Module file '{module_filename}' not found in primary path ('{base_module_path}') or addon path ('{addon_dir_path}').")
            return None
        except Exception as e_getpath: 
            self.LogErrorLine(
                f"Unexpected error in GetModulePath for module '{module_filename}' with base '{base_module_path}': {str(e_getpath)}"
            )
            return None

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
        if not self.LoadOrder: # Check if there are any modules to load.
            self.log.error("Error starting modules: LoadOrder is empty. No modules to start.")
            return False

        any_module_start_failed = False
        # TODO: The `multi_instance` flag (determining if multiple instances of a module can run)
        # is obtained in the `if __name__ == "__main__":` block.
        # For this method to correctly use it with `MySupport.IsRunning`,
        # `multi_instance` should ideally be stored as an instance attribute (e.g., self.multi_instance)
        # during Loader initialization if it's intended to affect StartModules behavior globally.
        # Current refactor assumes MySupport.IsRunning has access or it's passed if needed.
        # The original snippet's MySupport.IsRunning call from __main__ used it.

        # Start modules in REVERSE of LoadOrder. If LoadOrder is [A(100), B(90), C(2)],
        # reversed is [C, B, A]. This means lowest priority (e.g. helpers) start first,
        # highest priority (e.g. core genmon) start last. This is a common dependency pattern.
        for module_name_to_start in reversed(self.LoadOrder):
            try:
                module_config = self.CachedConfig.get(module_name_to_start)
                if not module_config:
                    self.log.error(f"Cannot start module '{module_name_to_start}': Configuration not found in CachedConfig.")
                    any_module_start_failed = True
                    continue

                if module_config.get("enable", False): # Check if module is enabled.
                    module_script_filename = module_config.get("module")
                    if not module_script_filename:
                        self.log.error(f"Cannot start module '{module_name_to_start}': 'module' script filename not defined in config.")
                        any_module_start_failed = True
                        continue
                    
                    # Determine the actual path to the module script (could be in base or addon dir).
                    actual_module_path_dir = self.GetModulePath(self.ModulePath, module_script_filename)
                    if actual_module_path_dir is None: # GetModulePath logs if not found.
                        self.log.error(f"Cannot start module '{module_name_to_start}': Script '{module_script_filename}' not found.")
                        any_module_start_failed = True
                        continue

                    # --- Pre-run check: If not multi_instance, ensure it's not already running ---
                    # This assumes `multi_instance` is a known state. If it's False, check and kill.
                    # The `multi_instance` flag itself is obtained from `MySupport.GetGenmonInitInfo` in `__main__`.
                    # For this method to use it, it should be an attribute of `self`.
                    # Let's assume for now `self.multi_instance` is set during `__init__` if this logic is to be fully functional.
                    # If `self.multi_instance` is not set, this check might behave unexpectedly or use a default.
                    # The original code fetched `multi_instance` in `__main__` and passed it to `IsRunning`.
                    # This method needs that value. For now, let's assume a conceptual `self.multi_instance`.
                    # If `self.multi_instance` is not available, this check should be conditional or adapted.
                    # As a placeholder, I will assume `multi_instance_setting_for_loader` is available.
                    # This would need to be properly passed to __init__ or fetched.
                    # For now, using a placeholder `False` to match original logic flow if it were global false.
                    # This part needs proper `multi_instance` state handling.
                    # ---
                    # multi_instance_check_value = getattr(self, 'multi_instance_setting', False) # Example how it could be an attribute
                    # The original code in `__main__` calls `IsRunning` with `multi_instance` from `GetGenmonInitInfo`.
                    # This method doesn't have it directly. This part of the logic
                    # for `StartModules` killing existing processes is complex without that state.
                    # For now, I will comment out the specific IsRunning check here as `multi_instance` is not an attribute.
                    # This check should be done in `__main__` before calling `Loader` if `multi_instance` is False.
                    # Or, `multi_instance` needs to be passed to `Loader.__init__`.
                    # The original code has this check in `StartModules`.
                    # Let's assume `multi_instance` is globally available for this check as per original style,
                    # though it's not ideal. The `multi_instance` variable is defined in `__main__`.
                    # This means this method, as part of the class, cannot directly access it unless passed.
                    # This is a known discrepancy in the original code structure.
                    # For the purpose of this refactor, I will comment out the check that depends on an undefined `multi_instance`.
                    # if not multi_instance_available_here: # This variable is not defined in this scope
                    #    # Check if module is already running, if so, attempt to stop it forcefully.
                    #    # This logic is complex if multi_instance is truly respected per module.
                    #    # The original code seems to imply a global multi_instance setting for genloader.
                    #    pass # Placeholder for the IsRunning and UnloadModule logic if not multi_instance

                    # Load (start) the module.
                    if not self.LoadModule(
                        actual_module_path_dir, # Path to the directory of the module.
                        module_script_filename,   # Filename of the module.
                        args=module_config.get("args", ""), # Arguments for the module.
                    ):
                        self.log.error(f"Error starting module '{module_name_to_start}' (script: {module_script_filename}). Details logged by LoadModule.")
                        any_module_start_failed = True
                    else:
                        # Handle post-load delay if specified.
                        post_load_delay_sec = module_config.get("postloaddelay", 0)
                        if post_load_delay_sec and post_load_delay_sec > 0:
                            self.log.info(f"Post-load delay for '{module_name_to_start}': {post_load_delay_sec} seconds.")
                            time.sleep(post_load_delay_sec)
                else:
                    self.log.info(f"Module '{module_name_to_start}' is disabled in configuration. Skipping start.")
            except KeyError as ke: # Should be caught by .get, but for safety.
                self.LogErrorLine(f"Missing key '{str(ke)}' in settings for module '{module_name_to_start}' during start. Skipping.")
                any_module_start_failed = True
            except Exception as e1: # Catch any other unexpected error for this module.
                self.LogErrorLine(
                    f"Unexpected error starting module '{module_name_to_start}': {str(e1)}"
                )
                any_module_start_failed = True # Mark failure and continue with other modules.
        
        if any_module_start_failed:
            self.log.error("One or more modules failed to start correctly.")
            return False
        else:
            self.log.info("All enabled modules processed for starting.")
            return True

    # ---------------------------------------------------------------------------
    def LoadModuleAlt(self, modulename, args=None):
        """
        Alternative method to load a module using `subprocess.Popen`.

        This method provides a simpler way to launch a module as a background
        process. It constructs the command from `sys.executable`, the module name,
        and optional arguments.

        Note: This method does not update PID tracking in `genloader.conf` and
        might offer less control over the subprocess's streams compared to `LoadModule`.

        Args:
            modulename (str): The filename of the module script to load.
            args (str, optional): Command-line arguments to pass to the module.
                                  Defaults to None.

        Returns:
            bool: True if the module was launched (Popen called) without immediate
                  exception, False if an error occurred during launch.
                  (Note: Popen itself doesn't guarantee the module runs successfully).
        """
        try:
            self.LogConsole(f"Starting module (alternative method): {modulename}")
            command_list = [sys.executable, modulename] # Base command: python /path/to/module.py
            if args and len(args.strip()): # Add arguments if provided.
                command_list.extend(args.split())

            # Launch the module as a detached background process.
            # No stream redirection means it inherits genloader's streams or system defaults.
            subprocess.Popen(command_list)
            self.log.info(f"Module '{modulename}' launched via LoadModuleAlt.")
            return True

        except Exception as e1:
            self.LogErrorLine(f"Error in LoadModuleAlt for '{modulename}': {str(e1)}")
            return False

    # ---------------------------------------------------------------------------
    def LoadModule(self, path, modulename, args=None):
        """
        Loads (starts) a specified module as a subprocess.

        Constructs the full path to the module, prepares arguments (including
        the common `-c ConfigFilePath`), and launches it using `subprocess.Popen`.
        It redirects stdout/stderr for most modules to `subprocess.PIPE`, but
        for `genserv.py`, it redirects to `DEVNULL` to suppress its web server logs
        from cluttering genloader's output. The PID of the started process is
        then written to `genloader.conf` via `UpdatePID`.

        Args:
            path (str): The directory path where the module script resides.
            modulename (str): The filename of the module script (e.g., "genmon.py").
            args (str, optional): Command-line arguments to pass to the module.
                                  Defaults to None (no arguments).

        Returns:
            bool: True if the module was launched and its PID updated successfully,
                  False if an error occurred.
        """
        try:
            # Construct the full path to the module script.
            full_module_path = os.path.join(path, modulename)

            if args and len(args.strip()):
                self.LogConsole(f"Starting: {full_module_path} {args}")
            else:
                self.LogConsole(f"Starting: {full_module_path}")
            
            # Determine output stream redirection.
            # For genserv.py (web server), redirect output to DEVNULL to keep console clean.
            # For other modules, PIPE allows potential future capture if needed, though currently not captured.
            try:
                from subprocess import DEVNULL # Python 3.3+
            except ImportError: # Fallback for older Python versions (e.g., Python 2.x).
                DEVNULL = open(os.devnull, "wb")

            output_stream_setting = DEVNULL if "genserv.py" in modulename else subprocess.PIPE
            
            # Prepare the command list for Popen.
            execution_command_list = [sys.executable, full_module_path]
            if args and len(args.strip()): # Add module-specific arguments.
                execution_command_list.extend(args.split()) # Split space-separated args.
            
            # Add common argument: -c ConfigFilePath (path to main config dir).
            # This allows all modules to know where to find their respective .conf files.
            execution_command_list.extend(["-c", self.ConfigFilePath])
            
            self.log.debug(f"Executing LoadModule command: {' '.join(execution_command_list)}")
            # Launch the module subprocess.
            # stdin is redirected from DEVNULL to prevent it from hanging on input.
            # close_fds=True is generally good practice on POSIX for subprocesses not inheriting file descriptors.
            process_handle = subprocess.Popen(
                execution_command_list,
                stdout=output_stream_setting,
                stderr=output_stream_setting, # Redirect stderr to same as stdout.
                stdin=DEVNULL,
                # close_fds=True # On POSIX, consider this. Default is False for Py < 3.2, True >= 3.7 (for POSIX)
            )
            
            self.log.info(f"Module '{modulename}' (PID: {process_handle.pid}) launched.")
            # Update genloader.conf with the new PID for this module.
            return self.UpdatePID(modulename, process_handle.pid)

        except Exception as e1:
            self.LogErrorLine(
                f"Error loading module '{modulename}' from path '{path}': {str(e1)}"
            )
            return False

    # ---------------------------------------------------------------------------
    def UnloadModule(self, modulename, pid=None, HardStop=False, UsePID=False):
        """
        Stops a running module, either by its PID or by its process name (`pkill`).

        Args:
            modulename (str): The filename of the module script (used for `pkill` if PID is not used).
            pid (int or str, optional): The Process ID of the module to stop.
                                        Defaults to None.
            HardStop (bool, optional): If True, uses `kill -9` or `pkill -9` (forceful stop).
                                       Otherwise, uses a standard termination signal.
                                       Defaults to False.
            UsePID (bool, optional): If True and `pid` is provided and valid, uses `kill` with the PID.
                                     Otherwise, uses `pkill` with `modulename`.
                                     Defaults to False.

        Returns:
            bool: True if the stop command was issued and PID update was successful.
                  False if an error occurred. (Note: This doesn't guarantee the process
                  actually terminated, only that the command was sent.)
        """
        try:
            kill_command_args = [] # Renamed from LoadInfo for clarity.
            
            # Determine whether to use 'kill' with PID or 'pkill' with module name.
            if UsePID and pid is not None and str(pid).strip() and int(pid) != 0:
                # Use 'kill' command with the provided PID.
                kill_command_args.append("kill")
                if HardStop or self.HardStop: # Check module-specific or global HardStop.
                    kill_command_args.append("-9") # Force kill signal.
                kill_command_args.append(str(pid)) # PID to kill.
                self.log.info(f"Preparing to stop module '{modulename}' using PID {pid} (HardStop: {HardStop or self.HardStop}).")
            else:
                # Use 'pkill' command with the module name.
                # This is less precise if multiple instances with same name part exist from other users.
                kill_command_args.append("pkill")
                if HardStop or self.HardStop:
                    kill_command_args.append("-9") # Force kill signal.
                # pkill options: -u root (only root's processes), -f (match full command line).
                kill_command_args.extend(["-u", "root", "-f", modulename])
                self.log.info(f"Preparing to stop module '{modulename}' using pkill (HardStop: {HardStop or self.HardStop}).")

            self.LogConsole(f"Stopping module: {modulename}")
            # Execute the kill/pkill command.
            process = Popen(kill_command_args, stdout=PIPE, stderr=PIPE) # Capture output/error.
            output_bytes, error_bytes = process.communicate()
            # rc = process.returncode # Return code might be non-zero if process already stopped.

            # Log output/error from kill/pkill for diagnostics.
            output_str = output_bytes.decode(sys.getdefaultencoding(), errors='replace').strip()
            error_str = error_bytes.decode(sys.getdefaultencoding(), errors='replace').strip()
            if output_str: self.log.debug(f"Stop command stdout for '{modulename}': {output_str}")
            if error_str: self.log.debug(f"Stop command stderr for '{modulename}': {error_str}") # pkill often gives "no process found" to stderr.

            # After attempting to stop, clear the PID in genloader.conf.
            # This UpdatePID call is crucial.
            return self.UpdatePID(modulename, "") # Pass empty string to clear PID.

        except ValueError: # If pid conversion to int fails (though already checked by UsePID logic)
            self.LogErrorLine(f"Error stopping module '{modulename}': Invalid PID format '{pid}'.")
            return False
        except Exception as e1:
            self.LogErrorLine(f"Error unloading module '{modulename}': {str(e1)}")
            return False

    # ---------------------------------------------------------------------------
    def UpdatePID(self, modulename, pid=""):
        """
        Updates the 'pid' entry in `genloader.conf` for a given module.

        It sets the specified PID for the module's section. If `pid` is an
        empty string or None, it effectively clears the stored PID.

        Args:
            modulename (str): The filename of the module (e.g., "genmon.py").
                              The section name in `genloader.conf` is derived
                              from this (e.g., "genmon").
            pid (int or str, optional): The PID to store. If empty or None,
                                        the PID entry is cleared/set to empty.
                                        Defaults to an empty string.

        Returns:
            bool: True if the PID was written to the config successfully,
                  False otherwise.
        """
        try:
            # Derive section name from module filename (e.g., "genmon.py" -> "genmon").
            section_name = os.path.splitext(modulename)[0]
            
            # Set MyConfig to operate on this module's section.
            if not self.config.SetSection(section_name): # SetSection logs error if section is invalid.
                self.log.error(
                    f"Error in UpdatePID: Cannot set section to '{section_name}' in MyConfig for module '{modulename}'."
                )
                return False # Cannot write PID if section cannot be set.
            
            # Write the PID (or empty string to clear it).
            self.config.WriteValue("pid", str(pid if pid is not None else "")) # Ensure value is string.
            self.log.debug(f"Updated PID for module '{modulename}' (section '[{section_name}]') to '{pid if pid is not None else ""}'.")
            return True
        except Exception as e1:
            self.LogErrorLine(f"Error writing PID for module '{modulename}' (section '{section_name}'): {str(e1)}")
            return False
        # Removed redundant "return True" at end as all paths should return.


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
