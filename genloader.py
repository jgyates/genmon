# -------------------------------------------------------------------------------
#    FILE: genloader.py
# PURPOSE: app for loading specific moduels for genmon
#
#  AUTHOR: Jason G Yates
#    DATE: 12-Sept-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

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

        self.Start = start
        self.Stop = stop
        self.HardStop = hardstop
        self.PipChecked = False
        self.AptUpdated = False
        self.NewInstall = False
        self.Upgrade = False
        self.version = None

        # Temporary logger for pre-super-init phase
        temp_logger_active = False
        if log is None:
            try:
                # Use a specific name for this temporary logger
                # Ensure loglocation is sensible; default if not provided before ProgramDefaults is confirmed.
                effective_log_location = loglocation if loglocation else ProgramDefaults.LogPath
                self.log = SetupLogger("genloader_bootstrap", os.path.join(effective_log_location, "genloader_bootstrap.log"))
                temp_logger_active = True
            except Exception as e_log_setup:
                # Fallback to basic print if SetupLogger fails catastrophically
                print(f"CRITICAL: Initial logger setup failed: {e_log_setup}. Further logging might be impaired.", file=sys.stderr)
                # Create a dummy self.log that just prints, to prevent AttributeError
                class PrintLogger:
                    def info(self, msg): print(f"INFO: {msg}")
                    def error(self, msg): print(f"ERROR: {msg}", file=sys.stderr)
                    def debug(self, msg): print(f"DEBUG: {msg}")
                    # Add other methods like LogErrorLine if MySupport expects them before its own init.
                    def LogErrorLine(self, msg): self.error(f"[LINE_UNKNOWN] {msg}")

                self.log = PrintLogger()
        else:
            self.log = log
        
        # Initialize parent class (MySupport)
        # MySupport's __init__ is expected to finalize self.log and self.ConfigFilePath
        try:
            # Pass ConfigFilePath to parent, MySupport will use ProgramDefaults if it's None
            super(Loader, self).__init__(log=self.log, ConfigFilePath=ConfigFilePath, localinit=localinit)
            if temp_logger_active and hasattr(super(), 'log') and self.log != getattr(super(), 'log', None) :
                # If MySupport.__init__ replaced our temporary logger, update self.log to use the official one.
                self.log = getattr(super(), 'log') 
        except Exception as e_super_init:
            self.log.error(f"CRITICAL: Error during MySupport initialization: {str(e_super_init)}. Functionality will be severely limited.")
            # Depending on MySupport's criticality, a sys.exit might be warranted here.
            # For now, assume we might be able to proceed with limited functionality or it handles its own exit.

        # Now self.log should be the logger from MySupport or the one passed in.
        # And self.ConfigFilePath should be set by MySupport.

        if sys.version_info[0] < 3:
            self.pipProgram = "pip2"
        else:
            self.pipProgram = "pip3"

        # self.ConfigFilePath should now be set by MySupport's init
        # self.ConfigFileName = "genloader.conf" # This is fine
        # self.configfile path construction depends on self.ConfigFilePath
        if not hasattr(self, 'ConfigFilePath') or not self.ConfigFilePath:
             self.log.error("CRITICAL: ConfigFilePath not set after MySupport init. Cannot proceed.")
             sys.exit(2)

        self.ConfigFileName = "genloader.conf"
        if localinit: # localinit means config file is in current dir, not ConfigFilePath
            self.configfile = self.ConfigFileName
        else:
            self.configfile = os.path.join(self.ConfigFilePath, self.ConfigFileName)
        
        self.ModulePath = os.path.dirname(os.path.realpath(__file__))
        self.ConfPath = os.path.join(os.path.dirname(os.path.realpath(__file__)), "conf")

        # self.console setup remains, assuming SetupLogger is now reliable via MySupport or genmonlib
        try:
            self.console = SetupLogger("genloader_console", log_file="", stream=True) # Use the potentially updated SetupLogger
        except Exception as e_console_log:
            self.log.error(f"Error setting up console logger: {str(e_console_log)}")
            # Fallback for console if needed, or ensure self.console has a safe dummy.
            class PrintConsole:
                def error(self, msg): print(f"CONSOLE: {msg}", file=sys.stderr) # Typically console logs to stdout for info
                def info(self, msg): print(f"CONSOLE: {msg}")
            self.console = PrintConsole()


        try:
            if self.Start:
                self.log.info("Start flag is set. Checking system readiness...")
                if not self.CheckSystem(): # CheckSystem should log its own errors
                    self.log.error("System readiness check failed. Exiting.")
                    sys.exit(2)

            self.CachedConfig = {}

            if not os.path.isdir(self.ConfigFilePath):
                self.log.info(f"Configuration directory '{self.ConfigFilePath}' does not exist. Attempting to create it.")
                try:
                    os.makedirs(self.ConfigFilePath, exist_ok=True)
                    self.log.info(f"Successfully created configuration directory: {self.ConfigFilePath}")
                except OSError as oe:
                    self.LogErrorLine(f"OSError creating target config directory '{self.ConfigFilePath}': {str(oe)}. Check permissions and path.")
                    sys.exit(2) 
                except Exception as e_mkdir: # Catch any other unexpected error
                    self.LogErrorLine(f"Unexpected error creating target config directory '{self.ConfigFilePath}': {str(e_mkdir)}")
                    sys.exit(2) 

            if not os.path.isfile(self.configfile):
                self.log.info( # Changed from LogInfo to log.info for consistency if LogInfo is a class method with specific formatting.
                    f"Main config file '{self.configfile}' not found. Attempting to copy from default location: "
                    f"{os.path.join(self.ConfPath, self.ConfigFileName)}"
                )
                if not self.CopyConfFile(): 
                    self.log.error("Failed to copy main configuration file (genloader.conf). This is a critical error. Exiting.")
                    sys.exit(2)
            
            # Initialize MyConfig for genloader.conf
            try:
                self.config = MyConfig(filename=self.configfile, section="genmon", log=self.log)
            except Exception as e_myconfig_init:
                self.LogErrorLine(f"Failed to initialize MyConfig with '{self.configfile}': {str(e_myconfig_init)}. Exiting.")
                sys.exit(2)


            # Config loading and validation sequence
            if not self.GetConfig(): # GetConfig logs its own detailed errors
                self.log.info("Initial attempt to load configuration (GetConfig) failed. Attempting recovery by copying default config.")
                if not self.CopyConfFile():
                     self.log.error("Failed to copy/restore main configuration file after GetConfig() failure. Exiting.")
                     sys.exit(2)
                self.log.info("Retrying GetConfig after copying default configuration.")
                try: # Re-initialize MyConfig after copy
                    self.config = MyConfig(filename=self.configfile, section="genmon", log=self.log)
                except Exception as e_myconfig_reinit:
                    self.LogErrorLine(f"Failed to re-initialize MyConfig after copy: {str(e_myconfig_reinit)}. Exiting.")
                    sys.exit(2)

                if not self.GetConfig():
                    self.log.error("Second attempt to load configuration (GetConfig) failed even after copying default. This is a critical failure. Exiting.")
                    sys.exit(2)

            if not self.ValidateConfig(): # ValidateConfig logs its own detailed errors
                self.log.info("Initial configuration validation (ValidateConfig) failed. Attempting recovery by copying default config.")
                if not self.CopyConfFile():
                     self.log.error("Failed to copy/restore main configuration file after ValidateConfig() failure. Exiting.")
                     sys.exit(2)
                self.log.info("Retrying configuration load and validation after copying default configuration.")
                try: # Re-initialize MyConfig
                    self.config = MyConfig(filename=self.configfile, section="genmon", log=self.log)
                except Exception as e_myconfig_reinit_val:
                    self.LogErrorLine(f"Failed to re-initialize MyConfig for validation retry: {str(e_myconfig_reinit_val)}. Exiting.")
                    sys.exit(2)
                
                if not self.GetConfig(): # Must re-load config after copy
                    self.log.error("Failed to re-load configuration (GetConfig) after copy during validation retry. Exiting.")
                    sys.exit(2)
                if not self.ValidateConfig():
                    self.log.error("Second attempt to validate configuration (ValidateConfig) failed even after copying default. This is a critical failure. Exiting.")
                    sys.exit(2)

            self.LoadOrder = self.GetLoadOrder() # GetLoadOrder logs its own errors

            if self.Stop:
                self.log.info("Stop flag is set. Stopping modules...")
                self.StopModules() # StopModules logs its own errors
                time.sleep(2) # Consider if this sleep is always necessary

            if self.Start:
                self.log.info("Start flag is set. Starting modules...")
                self.StartModules() # StartModules logs its own errors

        except SystemExit: # Allow sys.exit() to propagate cleanly
            raise
        except Exception as e_init_main: # Catch-all for any other unhandled exceptions in __init__
            self.LogErrorLine(f"Critical error during Loader initialization sequence: {str(e_init_main)}")
            # Consider if a sys.exit is needed here if the object is in an unusable state.
            # For now, it logs and completes __init__, but might be unstable.
            # If self.log isn't fully set up, this might print to a fallback.

    # ---------------------------------------------------------------------------
    def CopyConfFile(self):
        source_conf_file = os.path.join(self.ConfPath, self.ConfigFileName)
        target_conf_file = self.configfile

        try:
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
                    return False
            
            self.log.info(f"Attempting to copy default config from '{source_conf_file}' to '{target_conf_file}'.")
            copyfile(source_conf_file, target_conf_file)
            self.log.info(f"Successfully copied default config from '{source_conf_file}' to '{target_conf_file}'.")
            return True
        except IOError as ioe: # Specific to file I/O issues with copyfile
            self.LogErrorLine(f"IOError during config file copy from '{source_conf_file}' to '{target_conf_file}': {str(ioe)}")
            return False
        except OSError as ose: # Broader OS errors (permissions, path issues not caught by makedirs)
            self.LogErrorLine(f"OSError during config file copy operation for '{target_conf_file}': {str(ose)}")
            return False
        except Exception as e_copy: # Catch any other unexpected error
            self.LogErrorLine(f"Unexpected error copying config file from '{source_conf_file}' to '{target_conf_file}': {str(e_copy)}")
            return False

    # ---------------------------------------------------------------------------
    def CheckSystem(self):

        # this function checks the system to see if the required libraries are
        # installed. If they are not then an attempt is made to install them.
        ModuleList = [
            # [import name , install name, required version]
            ["flask", "flask", None],  # Web server
            # we will not use the check for configparser as this look like it is in backports on 2.7
            # and our myconfig modules uses the default so this generates an error that is not warranted
            # ['configparser','configparser',None],   # reading config files
            ["serial", "pyserial", None],  # Serial
            ["crcmod", "crcmod", None],  # Modbus CRC
            ["pyowm", "pyowm", "2.10.0"],  # Open Weather API
            ["pytz", "pytz", None],  # Time zone support
            ["pysnmp", "pysnmp", None],  # SNMP
            ["ldap3", "ldap3", None],  # LDAP
            ["smbus", "smbus", None],  # SMBus reading of temp sensors
            ["pyotp", "pyotp", "2.3.0"],  # 2FA support
            ["psutil", "psutil", None],  # process utilities
            ["chump", "chump", None],  # for genpushover
            ["twilio", "twilio", None],  # for gensms
            ["paho.mqtt.client", "paho-mqtt", "1.6.1"],  # for genmqtt
            ["OpenSSL", "pyopenssl", None],  # SSL
            ["spidev", "spidev", None],  # spidev
            ["voipms", "voipms", "0.2.5"]      # voipms for gensms_voip
            # ['fluids', 'fluids', None]              # fluids for genmopeka
        ]
        try:
            ErrorOccured = False

            self.CheckToolsNeeded()

            for Module in ModuleList:
                # fluids is only for Python 3.6 and higher
                if (Module[0] == "fluids") and sys.version_info < (3, 6):
                    continue
                if not self.LibraryIsInstalled(Module[0]):
                    self.LogInfo(
                        "Warning: required library "
                        + Module[1]
                        + " not installed. Attempting to install...."
                    )
                    if not self.InstallLibrary(Module[1], version=Module[2]):
                        self.LogInfo("Error: unable to install library " + Module[1])
                        ErrorOccured = True
                    if Module[0] == "ldap3":
                        # This will correct and issue with the ldap3 modbule not being recogonized in LibrayIsInstalled
                        self.InstallLibrary("pyasn1", update=True)

            ErrorOccured = False # Tracks if any installation failed

            if not self.CheckToolsNeeded(): # CheckToolsNeeded now logs its own errors
                self.LogError("CheckToolsNeeded reported errors. System check might be incomplete.")
                # Decide if this is fatal. For now, continue to check other libraries.
                # ErrorOccured = True # Could set this if CheckToolsNeeded is critical

            for module_import_name, module_install_name, required_version in ModuleList:
                if (module_import_name == "fluids") and sys.version_info < (3, 6):
                    continue # Skip fluids for older Python versions

                if not self.LibraryIsInstalled(module_import_name):
                    self.LogInfo(
                        f"Warning: required library '{module_install_name}' (for '{module_import_name}') not installed. Attempting to install...."
                    )
                    if not self.InstallLibrary(module_install_name, version=required_version):
                        self.LogError(f"Error: unable to install library '{module_install_name}'.")
                        ErrorOccured = True # Mark that an error occurred
                    # Special handling for ldap3's dependency, if still needed after InstallLibrary improvements
                    if module_import_name == "ldap3" and not self.LibraryIsInstalled("pyasn1"):
                        self.LogInfo("Attempting to update/install 'pyasn1' as a dependency for 'ldap3'.")
                        if not self.InstallLibrary("pyasn1", update=True):
                             self.LogError("Failed to install/update 'pyasn1' for 'ldap3'.")
                             # ErrorOccured = True # ldap3 might still work, or InstallLibrary for ldap3 handled it.

            if ErrorOccured:
                self.LogError("One or more required libraries could not be installed. System readiness check failed.")
                return False
            else:
                self.LogInfo("System check completed successfully. All required libraries appear to be installed.")
                return True
        except Exception as e_checksys: # Catch any unexpected error in CheckSystem logic
            self.LogErrorLine(f"Unexpected error in CheckSystem: {str(e_checksys)}")
            return False

    # ---------------------------------------------------------------------------
    def ExecuteCommandList(self, execute_list, env=None):
        try:
            # Ensure all elements in execute_list are strings
            execute_list_str = [str(item) for item in execute_list]
            self.log.debug(f"Executing command: {' '.join(execute_list_str)}") # Log the command being run
            process = Popen(execute_list_str, stdout=PIPE, stderr=PIPE, env=env)
            output, error_output = process.communicate()
            rc = process.returncode

            # Decode output and error_output if they are bytes
            if isinstance(output, bytes):
                output = output.decode(sys.getdefaultencoding(), errors='replace')
            if isinstance(error_output, bytes):
                error_output = error_output.decode(sys.getdefaultencoding(), errors='replace')

            if rc != 0: # Check return code for errors
                log_message = f"Error in ExecuteCommandList for command '{' '.join(execute_list_str)}'. RC: {rc}"
                if output and output.strip(): # Only add if there's content
                    log_message += f"\nStdout: {output.strip()}"
                if error_output and error_output.strip(): # Only add if there's content
                    log_message += f"\nStderr: {error_output.strip()}"
                self.LogError(log_message)
                return False
            
            # Log non-empty stderr even if rc is 0, as it might contain warnings
            if error_output and error_output.strip():
                self.LogInfo(f"Stderr from command '{' '.join(execute_list_str)}' (RC=0): {error_output.strip()}")

            self.log.debug(f"Command '{' '.join(execute_list_str)}' executed successfully.")
            return True
        except FileNotFoundError as fnfe:
            self.LogErrorLine(f"Error in ExecuteCommandList: Command '{execute_list[0]}' not found: {str(fnfe)}")
            return False
        except subprocess.SubprocessError as spe: # More specific than general Exception for Popen/communicate issues
            self.LogErrorLine(f"Subprocess error in ExecuteCommandList for '{' '.join(map(str,execute_list))}': {str(spe)}")
            return False
        except Exception as e_exec: # Catch any other unexpected error
            self.LogErrorLine(f"Unexpected error in ExecuteCommandList for '{' '.join(map(str,execute_list))}': {str(e_exec)}")
            return False


    # ---------------------------------------------------------------------------
    # check for other tools that are needed by pip libaries
    def CheckToolsNeeded(self):
        try:
            self.log.info("Checking for required system tools (e.g., cmake)...")
            command_list_cmake_check = ["cmake", "--version"]
            if not self.ExecuteCommandList(command_list_cmake_check):
                self.LogInfo("'cmake --version' command failed or cmake is not installed. Attempting to install cmake.")
                
                if not self.AptUpdated:
                    self.log.info("Running apt-get update before installing cmake.")
                    # --allow-releaseinfo-change might be needed for older distros
                    cmd_apt_update_allow_rls = ["sudo", "apt-get", "-yqq", "--allow-releaseinfo-change", "update"]
                    cmd_apt_update_normal = ["sudo", "apt-get", "-yqq", "update"]
                    
                    if not self.ExecuteCommandList(cmd_apt_update_allow_rls):
                        self.LogInfo("First attempt to run apt-get update failed (with --allow-releaseinfo-change). Retrying without it...")
                        if not self.ExecuteCommandList(cmd_apt_update_normal):
                            self.LogError("Error: Unable to run apt-get update even after retry. Cannot install cmake.")
                            return False # Cannot proceed if apt-get update fails
                    self.AptUpdated = True
                    self.log.info("apt-get update completed successfully.")
                
                self.log.info("Attempting to install cmake...")
                # DEBIAN_FRONTEND=noninteractive to prevent prompts.
                # This should be passed as an environment variable to Popen.
                custom_env = os.environ.copy()
                custom_env["DEBIAN_FRONTEND"] = "noninteractive"
                install_cmd_list_cmake = ["sudo", "apt-get", "-yqq", "install", "cmake"]

                if not self.ExecuteCommandList(install_cmd_list_cmake, env=custom_env):
                    self.LogError("Error: Unable to install cmake via apt-get.")
                    return False
                self.log.info("cmake installed successfully.")
            else:
                self.log.info("cmake is already installed.")
            return True
        except Exception as e_tools: # Catch any unexpected error in CheckToolsNeeded logic
            self.LogErrorLine(f"Unexpected error in CheckToolsNeeded: {str(e_tools)}")
            return False

    # ---------------------------------------------------------------------------
    def CheckBaseSoftware(self):

        try:
            if self.PipChecked:
                return True

            command_list = [sys.executable, "-m", "pip", "-V"]
            #command_list = [self.pipProgram, "-V"]
            if not self.ExecuteCommandList(command_list):
                self.InstallBaseSoftware()

            self.PipChecked = True
            return True
        except Exception as e1:
            self.LogInfo("Error in CheckBaseSoftware: " + str(e1), LogLine=True)
            self.log.info("Pip check already performed.")
            return True

        command_list_pip_check = [sys.executable, "-m", "pip", "-V"]
        if not self.ExecuteCommandList(command_list_pip_check): # ExecuteCommandList logs its own errors
            self.LogInfo(f"'{sys.executable} -m pip -V' command failed or pip is not installed correctly. Attempting to install/reinstall base software (pip).")
            if not self.InstallBaseSoftware(): # InstallBaseSoftware logs its own errors
                self.LogError("Failed to install base software (pip) after check failed.")
                self.PipChecked = False 
                return False
        else:
            self.log.info("pip is installed and accessible.")

        self.PipChecked = True
        return True
    except Exception as e_basesw: # Catch any unexpected error in CheckBaseSoftware logic
        self.LogErrorLine(f"Unexpected error in CheckBaseSoftware: {str(e_basesw)}")
        # Attempt to install base software as a fallback, as original logic did
        self.LogInfo("Attempting to install base software as a fallback due to unexpected error in CheckBaseSoftware.")
        if not self.InstallBaseSoftware():
             self.LogError("Fallback attempt to install base software also failed.")
        self.PipChecked = False # Mark as failed if we reached here due to an exception
        return False

    # ---------------------------------------------------------------------------
    def InstallBaseSoftware(self):
        try:
            pip_install_program = "python3-pip" if sys.version_info[0] >= 3 else "python-pip"
            self.log.info(f"Attempting to install {pip_install_program}.")

            if not self.AptUpdated:
                self.log.info(f"Running apt-get update before installing {pip_install_program}.")
                cmd_apt_update_allow_rls = ["sudo", "apt-get", "-yqq", "--allow-releaseinfo-change", "update"]
                cmd_apt_update_normal = ["sudo", "apt-get", "-yqq", "update"]
                
                if not self.ExecuteCommandList(cmd_apt_update_allow_rls):
                    self.LogInfo("First attempt to run apt-get update failed (with --allow-releaseinfo-change). Retrying without it...")
                    if not self.ExecuteCommandList(cmd_apt_update_normal):
                        self.LogError(f"Error: Unable to run apt-get update. Cannot install {pip_install_program}.")
                        return False
                self.AptUpdated = True
                self.log.info("apt-get update completed successfully.")
            
            custom_env = os.environ.copy()
            custom_env["DEBIAN_FRONTEND"] = "noninteractive"
            command_list_pip_install = ["sudo", "apt-get", "-yqq", "install", pip_install_program]
            
            if not self.ExecuteCommandList(command_list_pip_install, env=custom_env):
                self.LogError(f"Error: Unable to install {pip_install_program} via apt-get.")
                return False

            self.log.info(f"{pip_install_program} installed successfully.")
            return True
        except Exception as e_installbase: # Catch any unexpected error
            self.LogErrorLine(f"Unexpected error in InstallBaseSoftware: {str(e_installbase)}")
            return False

    # ---------------------------------------------------------------------------
    @staticmethod
    def OneTimeMaint(ConfigFilePath, log): # log is passed directly, not self.log
        # Corrected paths to be relative to the script's directory for genmon-specific files
        # /etc/ paths are system-level and their existence implies a different state.
        script_dir = os.path.dirname(os.path.realpath(__file__))
        genmonlib_dir = os.path.join(script_dir, "genmonlib")

        FileList = {
            "feedback.json": script_dir + "/", # Assuming these are directly in script_dir
            "outage.txt": script_dir + "/",
            "kwlog.txt": script_dir + "/",
            "maintlog.json": script_dir + "/",
            "Feedback_dat": genmonlib_dir + "/", # These are in genmonlib subdir
            "Message_dat": genmonlib_dir + "/",
            # For /etc/ files, the source path is literally /etc/ if they are being migrated *from* there.
            # If they are default configs *copied to* /etc/, then source is local.
            # The original logic seems to imply moving files *from* old locations (some local, some /etc/) *to* ConfigFilePath.
            # This is complex. Let's assume for now the main goal is moving files from within the app structure to ConfigFilePath.
            # And if /etc/genmon.conf exists, it might mean an old system-wide install.
            # The logic for /etc/ files might need more context if they are truly being *moved* from /etc/
            # For now, focusing on files within the application's own structure.
        }
        # Add /etc/ files separately if the intent is to check them as sources for migration
        # This part of the original logic is a bit ambiguous. If /etc/ files are *sources*,
        # then they should be listed with "/etc/" as their path.
        # If they are *examples* of what *might* be in ConfigFilePath, that's different.
        # Given the "move" operation, it implies they are sources.

        critical_files_to_check_in_source = [
            os.path.join(genmonlib_dir, "Message_dat"),
            os.path.join(script_dir, "maintlog.json"),
        ]
        # If key files that would be migrated are *not* present in their old locations,
        # assume this maintenance was done or is not applicable (e.g., new install).
        if not any(os.path.isfile(f) for f in critical_files_to_check_in_source) and not os.path.isfile("/etc/genmon.conf"):
            log.info("OneTimeMaint: Key source files for migration not found in typical old locations, and /etc/genmon.conf doesn't exist. Skipping file migration.")
            return True # True means "nothing to do" or "already done"

        try:
            if not os.path.isdir(ConfigFilePath):
                log.info(f"OneTimeMaint: Target configuration directory '{ConfigFilePath}' does not exist. Attempting to create it.")
                try:
                    os.makedirs(ConfigFilePath, exist_ok=True)
                    log.info(f"OneTimeMaint: Successfully created target directory: {ConfigFilePath}")
                except OSError as oe:
                    # Use exc_info=True for stack trace in log for OS errors
                    log.error(f"OneTimeMaint: OSError creating target config directory '{ConfigFilePath}': {str(oe)}", exc_info=True)
                    return False # Cannot proceed if target dir cannot be created
                except Exception as e_mkdir:
                     log.error(f"OneTimeMaint: Unexpected error creating target config directory '{ConfigFilePath}': {str(e_mkdir)}", exc_info=True)
                     return False


            files_moved_count = 0
            for file_basename, source_path_prefix in FileList.items():
                source_file_full_path = os.path.join(source_path_prefix, file_basename)
                target_file_full_path = os.path.join(ConfigFilePath, file_basename)

                if os.path.isfile(source_file_full_path):
                    try:
                        log.info(f"OneTimeMaint: Moving '{source_file_full_path}' to '{target_file_full_path}'")
                        # Ensure parent directory of target_file_path exists (ConfigFilePath should be created already)
                        move(source_file_full_path, target_file_full_path) # shutil.move
                        files_moved_count += 1
                        log.info(f"OneTimeMaint: Successfully moved '{source_file_full_path}'.")
                    except FileNotFoundError: # Should not happen if os.path.isfile was true, but defensive.
                        log.warning(f"OneTimeMaint: Source file '{source_file_full_path}' disappeared before move. Skipping.")
                    except (IOError, OSError) as e_move_io_os:
                        log.error(f"OneTimeMaint: IOError/OSError moving '{source_file_full_path}' to '{target_file_full_path}': {str(e_move_io_os)}", exc_info=True)
                    except Exception as e_move_other:
                        log.error(f"OneTimeMaint: Unexpected error moving '{source_file_full_path}': {str(e_move_other)}", exc_info=True)
                # else: # No need to log if source file doesn't exist for these locally defined files, initial check handles broader condition.
                    # log.debug(f"OneTimeMaint: Source file '{source_file_full_path}' not found for moving. Skipping.")

            if files_moved_count > 0:
                 log.info(f"OneTimeMaint: Moved {files_moved_count} files into '{ConfigFilePath}'.")
            else:
                 log.info("OneTimeMaint: No files were moved (either already moved or source files not found).")
            return True # Indicate maintenance process completed (even if no files moved)

        except Exception as e_maint_outer: # Catch any other unexpected error in the maintenance logic
            log.error(f"OneTimeMaint: Unexpected critical error during one-time maintenance process: {str(e_maint_outer)}", exc_info=True)
            return False # Indicate maintenance failed or had critical issues

    # ---------------------------------------------------------------------------
    def FixPyOWMMaintIssues(self):
        try:
            # check version of pyowm
            import pyowm

            if sys.version_info[0] < 3:
                required_version = "2.9.0"
            else:
                required_version = "2.10.0"

            if not self.LibraryIsInstalled("pyowm"):
                self.LogError("Error in FixPyOWMMaintIssues: pyowm not installed")
                return False

            installed_version = self.GetLibararyVersion("pyowm")

            if installed_version == None:
                self.LogError("Error in FixPyOWMMaintIssues: pyowm version not found")
                return None

            if self.VersionTuple(installed_version) <= self.VersionTuple(
                required_version
            ):
                return True

            self.LogInfo(
                "Found wrong version of pyowm, uninstalling and installing the correct version."
            )

            self.InstallLibrary("pyowm", uninstall=True)

            self.InstallLibrary("pyowm", version=required_version)

            # Ensure pyowm is imported to check its version or if it exists
            try:
                import pyowm
            except ImportError:
                self.LogError("Error in FixPyOWMMaintIssues: pyowm library is not installed at all.")
                # Attempt to install it if it's missing entirely
                self.LogInfo("Attempting to install pyowm as it's missing.")
                required_version_for_install = "2.10.0" if sys.version_info[0] >= 3 else "2.9.0"
                if self.InstallLibrary("pyowm", version=required_version_for_install):
                    self.LogInfo("Successfully installed pyowm. Please restart genloader for changes to take effect.")
                else:
                    self.LogError("Failed to install missing pyowm library.")
                return False # pyowm was missing, attempted install, outcome logged.

            required_version = "2.10.0" if sys.version_info[0] >= 3 else "2.9.0"

            installed_version_str = self.GetLibararyVersion("pyowm") # This method logs its own errors

            if installed_version_str is None:
                self.LogError("Error in FixPyOWMMaintIssues: Could not determine installed pyowm version.")
                return False # Cannot proceed without knowing the installed version

            # Use VersionTuple for robust comparison (assuming it handles version strings correctly)
            if self.VersionTuple(installed_version_str) <= self.VersionTuple(required_version):
                self.log.info(f"pyowm version {installed_version_str} is acceptable (<= {required_version}). No fix needed.")
                return True

            self.LogInfo(
                f"Found pyowm version {installed_version_str}, which is newer than required {required_version}. "
                f"Attempting to uninstall and reinstall the correct version."
            )

            if not self.InstallLibrary("pyowm", uninstall=True): # InstallLibrary logs its own errors
                self.LogError("Failed to uninstall the current version of pyowm.")
                return False 
            
            self.log.info(f"Successfully uninstalled pyowm. Now installing version {required_version}.")

            if not self.InstallLibrary("pyowm", version=required_version): # InstallLibrary logs its own errors
                self.LogError(f"Failed to install required version {required_version} of pyowm.")
                return False

            self.log.info(f"Successfully installed pyowm version {required_version}.")
            return True
        except Exception as e_fixpyowm: # Catch any other unexpected error
            self.LogErrorLine(f"Unexpected error in FixPyOWMMaintIssues: {str(e_fixpyowm)}")
            return False

    # ---------------------------------------------------------------------------
    def GetLibararyVersion(self, libraryname, importonly=False):
        try:
            self.log.debug(f"Attempting to get version for library: {libraryname} (importonly={importonly})")
            try:
                import importlib
                my_module = importlib.import_module(libraryname)
                version = getattr(my_module, '__version__', None)
                if version:
                    self.log.debug(f"Found version '{version}' for '{libraryname}' via importlib and __version__ attribute.")
                    return version
                self.log.debug(f"'{libraryname}' module imported but no __version__ attribute found.")
                # Fall through if __version__ is not present or None
            except ImportError: # Library not found by importlib
                self.log.info(f"Library '{libraryname}' not found via importlib (ImportError).")
                if importonly: return None
                # Proceed to pip check
            except Exception as e_import: # Other import related errors
                self.LogErrorLine(f"Error importing library '{libraryname}' to get version: {str(e_import)}")
                if importonly: return None
                # Proceed to pip check

            # If import failed or __version__ was not found, try pip (unless importonly)
            if importonly: # Should have returned by now if importonly was True and import failed/no version
                 self.log.debug(f"Importonly is True and version not found via import for '{libraryname}'. Returning None.")
                 return None

            self.log.info(f"Trying to get version of '{libraryname}' using pip.")
            if "linux" in sys.platform: # Ensure pip is available on Linux
                if not self.CheckBaseSoftware(): # Logs its own errors
                    self.LogError(f"Cannot get library version for '{libraryname}' via pip: Base software (pip) check failed.")
                    return None

            # Using 'pip show' is generally more reliable for getting a specific package's version.
            command_list_pip_show = [sys.executable, "-m", "pip", "show", libraryname]
            self.log.debug(f"Executing: {' '.join(command_list_pip_show)}")
            
            process = Popen(command_list_pip_show, stdout=PIPE, stderr=PIPE)
            output_bytes, error_bytes = process.communicate()
            rc = process.returncode

            output = output_bytes.decode(sys.getdefaultencoding(), errors='replace') if output_bytes else ""
            error_output = error_bytes.decode(sys.getdefaultencoding(), errors='replace') if error_bytes else ""

            if rc != 0:
                self.LogError(f"Error using 'pip show {libraryname}': RC={rc}. Stderr: {error_output.strip()}")
                return None # pip command failed

            for line in output.splitlines():
                line = line.strip()
                if line.lower().startswith("version:"):
                    version_str = line.split(":", 1)[1].strip()
                    self.log.info(f"Found version '{version_str}' for library '{libraryname}' via pip show.")
                    return version_str
            
            self.LogInfo(f"Could not find version information for '{libraryname}' in 'pip show' output.")
            return None

        except subprocess.SubprocessError as spe:
            self.LogErrorLine(f"Subprocess error while getting version for '{libraryname}': {str(spe)}")
            return None
        except Exception as e_getver: # Catch any other unexpected error
            self.LogErrorLine(f"Unexpected error in GetLibararyVersion for '{libraryname}': {str(e_getver)}")
            return None

    # ---------------------------------------------------------------------------
    def LibraryIsInstalled(self, libraryname):
        try:
            import importlib
            importlib.import_module(libraryname)
            self.log.debug(f"Library '{libraryname}' is installed (import successful).")
            return True
        except ImportError:
            self.log.info(f"Library '{libraryname}' is NOT installed (ImportError).")
            return False
        except Exception as e_isinst: # Catch other potential import errors
            self.LogErrorLine(f"Error checking if library '{libraryname}' is installed: {str(e_isinst)}")
            return False # Assume not installed or problematic

    # ---------------------------------------------------------------------------
    def InstallLibrary(self, libraryname, update=False, version=None, uninstall=False):
        try:
            target_library_spec = libraryname
            action = "install"
            log_action_description = f"installing '{libraryname}'"
            
            if uninstall:
                action = "uninstall"
                log_action_description = f"uninstalling '{libraryname}'"
            elif version:
                target_library_spec = f"{libraryname}=={version}"
                action = "install specific version"
                log_action_description = f"installing '{target_library_spec}'"
            elif update:
                action = "update"
                log_action_description = f"updating '{libraryname}'"

            self.log.info(f"Attempting to {log_action_description} using pip.")

            if "linux" in sys.platform and not uninstall: # Ensure pip is available on Linux for install/update
                if not self.CheckBaseSoftware(): # Logs its own errors
                    self.LogError(f"Cannot {action} library '{target_library_spec}': Base software (pip) check failed.")
                    return False

            pip_command_list = [sys.executable, "-m", "pip"]
            if uninstall:
                pip_command_list.extend(["uninstall", "-y", libraryname])
            elif update:
                pip_command_list.extend(["install", target_library_spec, "-U"]) # -U for upgrade
            else: # Install (specific version or latest)
                pip_command_list.extend(["install", target_library_spec])
            
            self.log.debug(f"Executing pip command: {' '.join(pip_command_list)}")
            process = Popen(pip_command_list, stdout=PIPE, stderr=PIPE)
            output_bytes, error_bytes = process.communicate()
            rc = process.returncode

            output = output_bytes.decode(sys.getdefaultencoding(), errors='replace').strip() if output_bytes else ""
            error_output = error_bytes.decode(sys.getdefaultencoding(), errors='replace').strip() if error_bytes else ""

            if rc != 0:
                log_message = f"Error during pip {action} for '{target_library_spec}'. RC: {rc}."
                if output: log_message += f"\nPip stdout: {output}"
                if error_output: log_message += f"\nPip stderr: {error_output}"
                self.LogError(log_message)
                return False
            
            # Log stdout/stderr even on success as they might contain useful info or warnings
            if output: self.log.info(f"Pip {action} stdout for '{target_library_spec}':\n{output}")
            if error_output: self.log.info(f"Pip {action} stderr for '{target_library_spec}':\n{error_output}")

            self.log.info(f"Successfully performed pip {action} for '{target_library_spec}'.")
            return True

        except subprocess.SubprocessError as spe:
            self.LogErrorLine(f"Subprocess error during pip operation for '{libraryname}': {str(spe)}")
            return False
        except Exception as e_installlib: # Catch any other unexpected error
            self.LogErrorLine(f"Unexpected error in InstallLibrary for '{libraryname}': {str(e_installlib)}")
            return False

    # ---------------------------------------------------------------------------
    def ValidateConfig(self):

        ErrorOccured = False
        if not len(self.CachedConfig):
            self.LogInfo("Error: Empty configruation found.")
            return False

        for Module, Settiings in self.CachedConfig.items():
            try:
                if self.CachedConfig[Module]["enable"]:
                    modulepath = self.GetModulePath(
                        self.ModulePath, self.CachedConfig[Module]["module"]
                    )
                    if modulepath == None:
                        self.LogInfo(
                            "Enable to find file " + self.CachedConfig[Module]["module"]
                        )
                        ErrorOccured = True

                # validate config file and if it is not there then copy it.
                if not self.CachedConfig[Module]["conffile"] == None and len(
                    self.CachedConfig[Module]["conffile"]
                ):
                    ConfFileList = self.CachedConfig[Module]["conffile"].split(",")
                    for ConfigFile in ConfFileList:
                        ConfigFile = ConfigFile.strip()
                        if not os.path.isfile(
                            os.path.join(self.ConfigFilePath, ConfigFile)
                        ):
                            if os.path.isfile(os.path.join(self.ConfPath, ConfigFile)):
                                self.LogInfo(
                                    "Copying "
                                    + ConfigFile
                                    + " to "
                                    + self.ConfigFilePath
                                )
                                copyfile(
                                    os.path.join(self.ConfPath, ConfigFile),
                                    os.path.join(self.ConfigFilePath, ConfigFile),
                                )
                            else:
                                self.LogInfo(
                                    "Enable to find config file "
                                    + os.path.join(self.ConfPath, ConfigFile)
                                )
                                ErrorOccured = True
            except Exception as e1:
                self.LogInfo(
                    "Error validating config for " + Module + " : " + str(e1),
                    LogLine=True, # Assuming LogInfo is from MySupport and handles LogLine
                )
                ErrorOccured = True # Mark that an error occurred for this module
                # Continue to validate other modules instead of returning False immediately
            except KeyError as ke:
                self.LogErrorLine(f"Configuration key error for module '{Module}': {str(ke)}. This module's config might be incomplete.")
                ErrorOccured = True
            except Exception as e_val_module: # Catch any other unexpected error for this module's validation
                self.LogErrorLine(f"Unexpected error validating configuration for module '{Module}': {str(e_val_module)}")
                ErrorOccured = True
        
        # Validate essential genmon and genserv entries
        try:
            if not self.CachedConfig.get("genmon", {}).get("enable", False): # Use .get for safer access
                self.LogError("Critical: Genmon core module ('genmon') is not enabled in the configuration.")
                ErrorOccured = True
            if not self.CachedConfig.get("genserv", {}).get("enable", False):
                self.LogInfo("Warning: Genserv web interface module ('genserv') is not enabled. Web UI will be unavailable.")
                # Not necessarily a fatal error for genloader itself.
        except KeyError as ke_core: # Should be caught by .get, but as a safeguard
             self.LogErrorLine(f"KeyError accessing core module ('genmon' or 'genserv') config: {str(ke_core)}")
             ErrorOccured = True
        except Exception as e_val_core: # Catch unexpected errors accessing core module configs
            self.LogErrorLine(f"Unexpected error validating core genmon/genserv config entries: {str(e_val_core)}")
            ErrorOccured = True

        if ErrorOccured:
            self.LogError("Configuration validation failed with one or more errors.")
        else:
            self.LogInfo("Configuration validation completed successfully.")
        return not ErrorOccured

    # ---------------------------------------------------------------------------
    def AddEntry(self, section=None, module=None, conffile="", args="", priority="2"):
        try:
            if section is None or module is None:
                self.LogError("Error in AddEntry: 'section' and 'module' parameters are required.")
                return False # Indicate failure

            self.log.info(f"Adding/Updating configuration entry for section '{section}', module '{module}'.")
            self.config.WriteSection(section) 
            self.config.WriteValue("module", module, section=section)
            self.config.WriteValue("enable", "False", section=section) # Default to False
            self.config.WriteValue("hardstop", "False", section=section)
            self.config.WriteValue("conffile", conffile, section=section)
            self.config.WriteValue("args", args, section=section)
            self.config.WriteValue("priority", str(priority), section=section) 
            self.log.info(f"Successfully added/updated configuration entry for section '{section}'.")
            return True
        except Exception as e_addentry: # Catch any error from MyConfig or other issues
            self.LogErrorLine(f"Error in AddEntry for section '{section}': {str(e_addentry)}")
            return False

    # ---------------------------------------------------------------------------
    def UpdateIfNeeded(self):
        try:
            self.log.info("Performing UpdateIfNeeded checks for config file structure and version...")
            # gengpioin conffile update
            self.config.SetSection("gengpioin")
            if not self.config.HasOption("conffile") or not self.config.ReadValue("conffile", default=""):
                self.config.WriteValue("conffile", "gengpioin.conf", section="gengpioin")
                self.log.info("Updated 'gengpioin' section: set 'conffile' to 'gengpioin.conf'.")

            # gengpio conffile update
            self.config.SetSection("gengpio")
            if not self.config.HasOption("conffile") or not self.config.ReadValue("conffile", default=""):
                self.config.WriteValue("conffile", "gengpio.conf", section="gengpio")
                self.log.info("Updated 'gengpio' section: set 'conffile' to 'gengpio.conf'.")

            # Version check and upgrade logic
            self.config.SetSection("genloader")
            current_config_version_str = self.config.ReadValue("version", default="0.0.0")
            if not current_config_version_str or current_config_version_str == "0.0.0":
                self.log.info("No version found in genloader.conf or version is '0.0.0'. Assuming new install.")
                self.NewInstall = True
                current_config_version_str = "0.0.0" # Normalize for comparison

            if self.VersionTuple(current_config_version_str) < self.VersionTuple(ProgramDefaults.GENMON_VERSION):
                self.log.info(f"Current config version '{current_config_version_str}' is older than program version '{ProgramDefaults.GENMON_VERSION}'. Marking for upgrade.")
                self.Upgrade = True
            
            if self.NewInstall or self.Upgrade:
                self.log.info(f"Updating genloader.conf version to '{ProgramDefaults.GENMON_VERSION}'.")
                self.config.WriteValue("version", ProgramDefaults.GENMON_VERSION, section="genloader")
            
            if self.NewInstall: 
                self.log.info("New install detected: Running one-time maintenance for PyOWM.")
                if not self.FixPyOWMMaintIssues(): # Logs its own errors
                    self.LogError("FixPyOWMMaintIssues failed during new install setup.")
                    # This might not be fatal for genloader itself, so logging and continuing.

            self.version = ProgramDefaults.GENMON_VERSION # Update internal version attribute
            self.log.info("UpdateIfNeeded checks completed.")
            return True 
        except Exception as e_updateif: 
            self.LogErrorLine(f"Unexpected error in UpdateIfNeeded: {str(e_updateif)}")
            return False

    # ---------------------------------------------------------------------------
    def GetConfig(self):
        try:
            self.log.info("Starting to load and cache configuration from genloader.conf.")
            current_sections = self.config.GetSections()
            if not current_sections: # Check if GetSections returned None or empty list
                self.log.error("No sections found in genloader.conf. The file might be empty, corrupt, or inaccessible by MyConfig.")
                # Attempt to restore config if it's this bad early on.
                if not self.CopyConfFile():
                    self.log.error("Attempt to copy default config failed. Cannot proceed with GetConfig.")
                    return False
                current_sections = self.config.GetSections() # Try again after copy
                if not current_sections:
                    self.log.error("Still no sections after attempting to copy default config. GetConfig cannot proceed.")
                    return False
            
            valid_sections_definitions = {
                "genmon": {"module": "genmon.py", "priority": "100", "conffile": "genmon.conf"},
                "genserv": {"module": "genserv.py", "priority": "90", "conffile": "genserv.conf"},
                "gengpio": {"module": "gengpio.py", "conffile": "gengpio.conf"},
                "gengpioin": {"module": "gengpioin.py", "conffile": "gengpioin.conf"},
                "genlog": {"module": "genlog.py"}, # No specific conffile by default for genlog
                "gensms": {"module": "gensms.py", "conffile": "gensms.conf"},
                "gensms_modem": {"module": "gensms_modem.py", "conffile": "mymodem.conf"}, # Note: mymodem.conf
                "genpushover": {"module": "genpushover.py", "conffile": "genpushover.conf"},
                "gensyslog": {"module": "gensyslog.py"}, # No specific conffile by default
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
                "genloader": {}, # genloader is special, no module/conffile in this context
            }
            
            config_changed_by_addentry = False
            for section_name, defaults in valid_sections_definitions.items():
                if section_name not in current_sections:
                    if section_name == "genloader": # genloader section is critical but simple
                        self.log.info(f"Critical configuration section '{section_name}' is missing. Adding section header.")
                        self.config.WriteSection(section_name) 
                        config_changed_by_addentry = True
                    elif defaults: # For other modules with defined defaults
                        self.log.info(f"Configuration section '{section_name}' is missing. Adding default entry (disabled).")
                        if self.AddEntry(section=section_name, module=defaults["module"], 
                                         conffile=defaults.get("conffile", ""), 
                                         priority=defaults.get("priority", "2")):
                            config_changed_by_addentry = True
                        else:
                             self.log.error(f"Failed to add default entry for missing section '{section_name}'.")
            
            if config_changed_by_addentry: # If we added sections, re-fetch them
                current_sections = self.config.GetSections()

            if not self.UpdateIfNeeded(): 
                self.log.error("UpdateIfNeeded reported errors during GetConfig. Configuration might be inconsistent.")

            current_sections = self.config.GetSections() # Re-fetch again after UpdateIfNeeded
            temp_cached_config = {}

            for section_name in current_sections:
                if section_name == "genloader": 
                    continue # genloader section managed separately for version, not as a loadable module here
                
                settings_dict = {}
                self.config.SetSection(section_name) 

                def _read_config_value(key, expected_type=str, default_val=None, is_critical=True, no_log_missing=False):
                    if self.config.HasOption(key):
                        try:
                            if expected_type == bool: return self.config.ReadValue(key, return_type=bool, default=default_val, NoLog=no_log_missing)
                            if expected_type == int: return self.config.ReadValue(key, return_type=int, default=default_val, NoLog=no_log_missing)
                            return self.config.ReadValue(key, default=default_val, NoLog=no_log_missing)
                        except ValueError as ve: # MyConfig might raise ValueError on type conversion
                            self.log.error(f"ValueError reading key '{key}' in section '{section_name}': {str(ve)}. Using default '{default_val}'.")
                            return default_val
                    elif is_critical and not no_log_missing:
                        self.log.error(f"Missing critical config key '{key}' in section '{section_name}'. Using default '{default_val}'.")
                    elif not no_log_missing:
                        self.log.debug(f"Optional config key '{key}' not found in section '{section_name}'. Using default '{default_val}'.")
                    return default_val

                settings_dict["module"] = _read_config_value("module", is_critical=True, default_val="unknown.py")
                settings_dict["enable"] = _read_config_value("enable", expected_type=bool, default_val=False)
                settings_dict["hardstop"] = _read_config_value("hardstop", expected_type=bool, default_val=False)
                settings_dict["conffile"] = _read_config_value("conffile", default_val="", is_critical=False)
                settings_dict["args"] = _read_config_value("args", default_val="", is_critical=False)
                settings_dict["priority"] = _read_config_value("priority", expected_type=int, default_val=99, is_critical=False)
                settings_dict["postloaddelay"] = _read_config_value("postloaddelay", expected_type=int, default_val=0, is_critical=False)
                settings_dict["pid"] = _read_config_value("pid", expected_type=int, default_val=0, is_critical=False, no_log_missing=True)

                if settings_dict["module"] == "unknown.py" and settings_dict["enable"]:
                     self.log.warning(f"Module '{section_name}' is enabled but 'module' filename is not specified or missing. Disabling.")
                     settings_dict["enable"] = False 

                temp_cached_config[section_name] = settings_dict
            
            self.CachedConfig = temp_cached_config 
            self.log.info(f"Successfully loaded and cached configuration for {len(self.CachedConfig)} modules.")
            return True

        except Exception as e_getconf: 
            self.LogErrorLine(f"Unexpected critical error in GetConfig: {str(e_getconf)}")
            self.CachedConfig = {} 
            return False
        # Removed final "return True" as all paths should explicitly return.

    # ---------------------------------------------------------------------------
    def ConvertToInt(self, value, default=None):
        if value is None:
            return default
        try:
            return int(str(value)) # str(value) handles cases where value might be non-string/non-numeric directly
        except ValueError:
            self.log.info(f"Could not convert value '{value}' to int. Returning default '{default}'.")
            return default
        except Exception as e_convert: # Other unexpected errors
            self.LogErrorLine(f"Unexpected error converting value '{value}' to int: {str(e_convert)}")
            return default

    # ---------------------------------------------------------------------------
    def GetLoadOrder(self):
        load_order_list = []
        priority_dict = {}
        try:
            if not self.CachedConfig:
                self.log.error("Cannot determine load order: CachedConfig is empty.")
                return []

            for module_name, settings in self.CachedConfig.items():
                try:
                    # Use .get for safer access, default to a high number (low priority) if 'priority' is missing
                    priority = settings.get("priority")
                    if priority is None: # Explicit check for None, as 0 is a valid priority
                        priority_val = 99 # Default for missing or None priority
                        self.log.info(f"Module '{module_name}' has no priority set, defaulting to {priority_val}.")
                    elif not isinstance(priority, int):
                        priority_val = self.ConvertToInt(priority, 99) # ConvertToInt logs its own issues
                        if priority_val == 99 and str(priority) != "99": # Log if conversion defaulted
                             self.log.info(f"Priority '{priority}' for module '{module_name}' was invalid, defaulted to {priority_val}.")
                    else:
                        priority_val = priority
                    
                    priority_dict[module_name] = priority_val
                except KeyError as ke: # Should be caught by .get, but defensive
                    self.LogErrorLine(f"KeyError accessing priority for module '{module_name}': {str(ke)}. Assigning default priority 99.")
                    priority_dict[module_name] = 99
                except Exception as e_module_prio: 
                    self.LogErrorLine(f"Error processing priority for module '{module_name}': {str(e_module_prio)}. Assigning default priority 99.")
                    priority_dict[module_name] = 99 
            
            # Sort by priority value (higher numbers first = more important), then by module name
            sorted_modules = sorted(priority_dict.items(), key=lambda item: (-item[1], item[0]))
            
            load_order_list = [module_name for module_name, prio in sorted_modules]

            if load_order_list:
                self.log.info(f"Determined module load order: {', '.join(load_order_list)}")
            else:
                self.log.info("No modules found in cached config to determine load order.")
            return load_order_list

        except Exception as e_loadorder: 
            self.LogErrorLine(f"Unexpected critical error in GetLoadOrder: {str(e_loadorder)}")
            return [] # Return empty list on error

    # ---------------------------------------------------------------------------
    def StopModules(self):
        self.LogConsole("Attempting to stop modules...")
        if not self.LoadOrder: # Check if LoadOrder is empty
            self.log.info("No modules in load order. Nothing to stop.")
            return True # Successfully did nothing

        all_stopped_successfully = True
        for module_name in self.LoadOrder:
            try:
                module_settings = self.CachedConfig.get(module_name)
                if not module_settings:
                    self.log.error(f"Could not find settings for module '{module_name}' in CachedConfig during stop. Skipping.")
                    all_stopped_successfully = False
                    continue

                module_file = module_settings.get("module")
                pid = module_settings.get("pid")
                # Use global HardStop if module-specific is False or missing
                hard_stop = module_settings.get("hardstop", False) or self.HardStop 

                if not module_file:
                    self.log.error(f"Module name (filename) not defined for '{module_name}'. Cannot stop. Skipping.")
                    all_stopped_successfully = False
                    continue
                
                self.log.info(f"Processing stop for module '{module_name}' (File: {module_file}, PID: {pid if pid else 'N/A'}, EffectiveHardStop: {hard_stop}).")

                if not self.UnloadModule(
                    module_file,
                    pid=pid, 
                    HardStop=hard_stop,
                    UsePID=bool(pid) # Use PID if it's present and non-zero/non-empty
                ):
                    self.log.error(f"Error occurred while trying to stop module '{module_name}' (logged by UnloadModule).")
                    all_stopped_successfully = False
                else:
                    self.log.info(f"Successfully signaled stop for module '{module_name}'.")
            except KeyError as ke:
                self.LogErrorLine(f"Missing key '{str(ke)}' in settings for module '{module_name}' during stop operation. Skipping.")
                all_stopped_successfully = False
            except Exception as e_stopmodule: 
                self.LogErrorLine(f"Unexpected error stopping module '{module_name}': {str(e_stopmodule)}")
                all_stopped_successfully = False
        
        if all_stopped_successfully:
            self.LogConsole("All modules processed for stopping successfully.")
        else:
            self.LogConsole("Finished processing modules for stopping, but one or more errors occurred.")
        return all_stopped_successfully

    # ---------------------------------------------------------------------------
    def GetModulePath(self, base_module_path, module_filename):
        try:
            if not module_filename: 
                self.log.error("GetModulePath: module_filename is empty or None.")
                return None
            if not base_module_path: # base_module_path is typically self.ModulePath
                 self.log.error(f"GetModulePath: base_module_path is not specified for module '{module_filename}'.")
                 return None


            primary_path_check = os.path.join(base_module_path, module_filename)
            if os.path.isfile(primary_path_check):
                self.log.debug(f"Module '{module_filename}' found at primary path: '{base_module_path}'")
                return base_module_path 

            addon_dir_check = os.path.join(base_module_path, "addon")
            addon_path_full_check = os.path.join(addon_dir_check, module_filename)
            if os.path.isfile(addon_path_full_check):
                self.log.debug(f"Module '{module_filename}' found in addon path: '{addon_dir_check}'")
                return addon_dir_check 

            self.log.info(f"Module file '{module_filename}' not found in primary path '{base_module_path}' or addon path '{addon_dir_check}'.")
            return None
        except Exception as e_getpath: 
            self.LogErrorLine(
                f"Unexpected error in GetModulePath for module '{module_filename}' with base '{base_module_path}': {str(e_getpath)}"
            )
            return None

    # ---------------------------------------------------------------------------
    def StartModules(self):

        self.LogConsole("Starting....")

        if not len(self.LoadOrder):
            self.LogInfo("Error, nothing to start.")
            return False
        ErrorOccured = False
        for Module in reversed(self.LoadOrder):
            try:
                if self.CachedConfig[Module]["enable"]:
                    modulepath = self.GetModulePath(
                        self.ModulePath, self.CachedConfig[Module]["module"]
                    )
                    if modulepath == None:
                        continue

                    if not multi_instance:
                        # check that module is not loaded already, if it is then force it (hard) to unload
                        attempts = 0
                        while True:
                            if MySupport.IsRunning(
                                prog_name=self.CachedConfig[Module]["module"],
                                log=self.log,
                                multi_instance=multi_instance,
                            ):
                                # if loaded then kill it
                                if attempts >= 4:
                                    # kill it
                                    if not self.UnloadModule(
                                        self.CachedConfig[Module]["module"],
                                        pid=None,
                                        HardStop=True,
                                        UsePID=False,
                                    ):
                                        self.LogInfo(
                                            "Error killing "
                                            + self.CachedConfig[Module]["module"]
                                        )
                                else:
                                    attempts += 1
                                    time.sleep(1)
                            else:
                                break

                    if not self.LoadModule(
                        modulepath,
                        self.CachedConfig[Module]["module"],
                        args=self.CachedConfig[Module]["args"],
                    ):
                        self.LogInfo("Error starting " + Module)
                        ErrorOccured = True
                    if (
                        not self.CachedConfig[Module]["postloaddelay"] == None
                        and self.CachedConfig[Module]["postloaddelay"] > 0
                    ):
                        time.sleep(self.CachedConfig[Module]["postloaddelay"])
            except Exception as e1:
                self.LogInfo(
                    "Error starting module " + Module + " : " + str(e1), LogLine=True
                )
                return False
        return not ErrorOccured

    # ---------------------------------------------------------------------------
    def LoadModuleAlt(self, modulename, args=None):
        try:
            self.LogConsole("Starting " + modulename)
            # Using subprocess.Popen to load as a background process
            command_list = [sys.executable, modulename]
            if args is not None and len(args):
                command_list.extend(args.split())

            subprocess.Popen(command_list)
            return True

        except Exception as e1:
            self.LogInfo("Error loading module: " + str(e1), LogLine=True)
            return False

    # ---------------------------------------------------------------------------
    def LoadModule(self, path, modulename, args=None):
        try:
            try:
                import os

                fullmodulename = os.path.join(path, modulename)
            except Exception as e1:
                fullmodulename = path + "/" + modulename

            if args != None:
                self.LogConsole("Starting " + fullmodulename + " " + args)
            else:
                self.LogConsole("Starting " + fullmodulename)
            try:
                from subprocess import DEVNULL  # py3k
            except ImportError:
                import os

                DEVNULL = open(os.devnull, "wb")

            if not len(args):
                args = None

            if "genserv.py" in modulename:
                OutputStream = DEVNULL
            else:
                OutputStream = subprocess.PIPE

            executelist = [sys.executable, fullmodulename]
            if args != None:
                executelist.extend(args.split(" "))
            # This will make all the programs use the same config files
            executelist.extend(["-c", self.ConfigFilePath])
            # close_fds=True
            pid = subprocess.Popen(
                executelist,
                stdout=OutputStream,
                stderr=OutputStream,
                stdin=OutputStream,
            )
            return self.UpdatePID(modulename, pid.pid)

        except Exception as e1:
            self.LogInfo(
                "Error loading module " + path + ": " + modulename + ": " + str(e1),
                LogLine=True,
            )
            return False

    # ---------------------------------------------------------------------------
    def UnloadModule(self, modulename, pid=None, HardStop=False, UsePID=False):
        try:
            LoadInfo = []
            if UsePID:
                if pid == None or pid == "" or pid == 0:
                    return True
                LoadInfo.append("kill")
                if HardStop or self.HardStop:
                    LoadInfo.append("-9")
                LoadInfo.append(str(pid))
            else:
                LoadInfo.append("pkill")
                if HardStop or self.HardStop:
                    LoadInfo.append("-9")
                LoadInfo.append("-u")
                LoadInfo.append("root")
                LoadInfo.append("-f")
                LoadInfo.append(modulename)

            self.LogConsole("Stopping " + modulename)
            process = Popen(LoadInfo, stdout=PIPE)
            output, _error = process.communicate()
            rc = process.returncode
            return self.UpdatePID(modulename, "")

        except Exception as e1:
            self.LogInfo("Error loading module: " + str(e1), LogLine=True)
            return False

    # ---------------------------------------------------------------------------
    def UpdatePID(self, modulename, pid=None):

        try:
            filename = os.path.splitext(modulename)[0]  # remove extension
            if not self.config.SetSection(filename):
                self.LogError(
                    "Error settting section name in UpdatePID: " + str(filename)
                )
                return False
            self.config.WriteValue("pid", str(pid))
            return True
        except Exception as e1:
            self.LogInfo("Error writing PID for " + modulename + " : " + str(e1))
            return False
        return True


# ------------------main---------------------------------------------------------
if __name__ == "__main__":

    HelpStr = "\npython genloader.py [-s -r -x -z -c configfilepath]\n"
    HelpStr += "   Example: python genloader.py -s\n"
    HelpStr += "            python genloader.py -r\n"
    HelpStr += "\n      -s  Start Genmon modules"
    HelpStr += "\n      -r  Restart Genmon moduels"
    HelpStr += "\n      -x  Stop Genmon modules"
    HelpStr += "\n      -z  Hard stop Genmon modules"
    HelpStr += "\n      -c  Path of genmon.conf file i.e. /etc/"
    HelpStr += "\n \n"

    if not MySupport.PermissionsOK():
        print(
            "You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting."
        )
        sys.exit(2)

    try:
        ConfigFilePath = ProgramDefaults.ConfPath
        opts, args = getopt.getopt(
            sys.argv[1:],
            "hsrxzc:",
            ["help", "start", "restart", "exit", "hardstop", "configpath="],
        )
    except getopt.GetoptError:
        print(HelpStr)
        sys.exit(2)

    StopModules = False
    StartModules = False
    HardStop = False

    for opt, arg in opts:
        if opt == "-h":
            print(HelpStr)
            sys.exit()
        elif opt in ("-s", "--start"):
            StartModules = True
        elif opt in ("-r", "--restart"):
            StopModules = True
            StartModules = True
        elif opt in ("-x", "--exit"):
            StopModules = True
        elif opt in ("-z", "--hardstop"):
            HardStop = True
            StopModules = True
        elif opt in ("-c", "--configpath"):
            ConfigFilePath = arg
            ConfigFilePath = ConfigFilePath.strip()

    if not StartModules and not StopModules:
        print("\nNo option selected.\n")
        print(HelpStr)
        sys.exit(2)

    tmplog = SetupLogger("genloader", "/var/log/" + "genloader.log")
    if Loader.OneTimeMaint(ConfigFilePath, tmplog):
        time.sleep(1.5)
    port, loglocation, multi_instance = MySupport.GetGenmonInitInfo(
        ConfigFilePath, log=None
    )

    if MySupport.IsRunning(os.path.basename(__file__), multi_instance=multi_instance):
        print("\ngenloader already running.")
        sys.exit(2)

    LoaderObject = Loader(
        start=StartModules,
        stop=StopModules,
        hardstop=HardStop,
        ConfigFilePath=ConfigFilePath,
        loglocation=loglocation,
    )
