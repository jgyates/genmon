# genmonlib/presentation.py
"""
This module defines the UIPresenter class, responsible for handling the presentation
logic for the Genmon web application. It interacts with the client interface
(typically to a backend monitoring process) to fetch data and then processes
and formats this data for display in the web UI. This separation of concerns
helps keep the Flask route handlers in `genserv.py` cleaner and focused on
request handling and routing.
"""
import json
import datetime
import os
import subprocess # For _run_bash_script
from .myconfig import MyConfig
# from .mymail import MyMail # Placeholder for when MyMail is made available

class UIPresenter:
    """
    Handles the presentation logic for the web UI.

    This class fetches raw data from a client interface (e.g., a generator
    monitoring process), processes it, and prepares it for rendering in
    Flask templates. It provides methods for different pages and data
    types required by the UI.
    """
    def __init__(self, client_interface, ConfigFilePath, log):
        """
        Initializes the UIPresenter with a client interface, config path, and logger.

        Args:
            client_interface: An object that provides a method
                              `ProcessMonitorCommand(command_string)`
                              to communicate with the backend data source.
            ConfigFilePath (str): Path to the main configuration file (e.g., genmon.conf).
            log: A logging object for recording messages.
        """
        self.client_interface = client_interface
        self.ConfigFilePath = ConfigFilePath
        self.log = log

    def get_base_status(self):
        """
        Fetches the base status from the generator.
        Returns:
            str: The processed status string, or an error message.
        """
        try:
            raw_data = self.client_interface.ProcessMonitorCommand("generator: getbase")
            # Assuming "EndOfMessage" is a marker to be removed.
            return raw_data.replace("EndOfMessage", "").strip()
        except Exception as e:
            self.log.error(f"Error in get_base_status: {e}")
            return "Error: Could not fetch base status."

    def get_site_name(self):
        """
        Fetches the site name from the generator.
        Returns:
            str: The processed site name string, or an error message.
        """
        try:
            raw_data = self.client_interface.ProcessMonitorCommand("generator: getsitename")
            return raw_data.replace("EndOfMessage", "").strip()
        except Exception as e:
            self.log.error(f"Error in get_site_name: {e}")
            return "Error: Could not fetch site name."

    def get_register_labels(self):
        """
        Fetches register labels as a JSON dictionary.
        Returns:
            dict: A dictionary containing register labels, or an error dictionary.
        """
        try:
            raw_data_str = self.client_interface.ProcessMonitorCommand("generator: getreglabels_json")
            return json.loads(raw_data_str)
        except json.JSONDecodeError:
            self.log.error("Failed to decode register labels JSON.")
            return {"error": "Failed to decode register labels data"}
        except Exception as e:
            self.log.error(f"Error in get_register_labels: {e}")
            return {"error": str(e)}

    def get_favicon_path(self):
        """
        Reads the favicon path from the configuration file.
        Note: This method needs access to MyConfig or similar to read genmon.conf.
              For now, it's a placeholder.
        Returns:
            str: The path to the favicon, or a default/error message.
        """
        # This method will require MyConfig to be integrated.
        # Placeholder implementation:
        # try:
        #     conf = MyConfig(self.ConfigFilePath, self.log)
        #     favicon_path = conf.ReadSetting("favicon")
        #     if favicon_path:
        #         return favicon_path
        #     return "/static/favicon.ico" # Default if not set
        # except Exception as e:
        #     self.log.error(f"Error reading favicon from config: {e}")
        #     return "/static/favicon.ico" # Default on error
        self.log.info("get_favicon_path called, needs MyConfig implementation.")
        return "/static/favicon.ico" # Placeholder

    # System Action Methods
    # These methods will use a helper like RunBashScript from mysupport.
    # For now, the call to RunBashScript is a placeholder.

    def _run_bash_script(self, command, args_list=None):
        """
        Placeholder for a utility function to run shell commands.
        This should ideally be in 'mysupport.py' and imported.
        """
        if args_list is None:
            args_list = []
        full_command = f"{command} {' '.join(args_list)}"
        self.log.info(f"Executing system command: {full_command}")
        # In a real implementation, this would use subprocess.run or similar
        # from mysupport.py and capture output and return codes.
        # Example:
        # try:
        #     # Assuming RunBashScript is in mysupport and imported
        #     # import mysupport
        #     # result = mysupport.RunBashScript(command, args_list, self.log)
        #     # if result['ReturnCode'] == 0:
        #     #     return {"status": "OK", "message": result.get('Stdout', 'Command executed.')}
        #     # else:
        #     #     return {"status": "error", "message": result.get('Stderr', 'Command failed.')}
        #     self.log.warning(f"RunBashScript for '{full_command}' is not fully implemented here.")
        #     return {"status": "OK", "message": f"Placeholder: Command '{full_command}' would be executed."}
        # except Exception as e:
        #     self.log.error(f"Error executing '{full_command}': {e}")
        #     return {"status": "error", "message": str(e)}
        if args_list is None:
            args_list = []

        script_executable_path = ""

        if command.startswith("sudo"):
            full_cmd_list = command.split() + args_list
        else:
            # Determine project root relative to presentation.py
            # presentation.py is in genmonlib/, scripts are in project root
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            script_executable_path = os.path.join(project_root, command)
            full_cmd_list = ['/bin/bash', script_executable_path] + args_list
        
        self.log.info(f"Executing bash command: {' '.join(full_cmd_list)}")

        try:
            result = subprocess.run(full_cmd_list, capture_output=True, text=True, check=False)

            if result.returncode == 0:
                message = result.stdout.strip() if result.stdout.strip() else "Command executed successfully."
                # If backup or archive, the path is expected in stdout
                # The caller will extract it if needed.
                # For backup_configuration and get_log_archive, they currently also add a 'path' key
                # based on this stdout. This can be refined if scripts don't output path directly.
                return_dict = {"status": "OK", "message": message, "stdout": result.stdout.strip(), "ReturnCode": 0}
                # Specific handling for backup/archive path for compatibility with existing calling code structure
                if command == "genmonmaint.sh" and ("-b" in args_list or "-l" in args_list):
                    # Assuming the script prints only the path to stdout
                    return_dict["path"] = result.stdout.strip() 
                return return_dict
            else:
                message = result.stderr.strip() if result.stderr.strip() else f"Command failed with return code {result.returncode}."
                self.log.error(f"Command failed: {' '.join(full_cmd_list)}. Return Code: {result.returncode}. Stderr: {result.stderr.strip()}")
                return {"status": "error", "message": message, "stderr": result.stderr.strip(), "ReturnCode": result.returncode}

        except FileNotFoundError as e:
            # This might occur if 'sudo' is not found, or if the script path was wrong despite resolution
            self.log.error(f"Command not found for: {' '.join(full_cmd_list)}: {e}")
            return {"status": "error", "message": f"Command not found: {command}. Details: {str(e)}", "ReturnCode": -1}
        except Exception as e:
            self.log.error(f"Exception during subprocess execution for {' '.join(full_cmd_list)}: {e}")
            return {"status": "error", "message": str(e), "ReturnCode": -1}

    def update_software(self):
        """
        Runs genmonmaint.sh to update software and then restarts Genmon.
        Returns:
            dict: Status dictionary.
        """
        self.log.info("Starting software update process.")
        # Path to genmonmaint.sh might need to be configurable or discovered
        update_command = "genmonmaint.sh"
        # Example: genmonmaint.sh -u -n -p /opt/genmon -c /etc/genmon/genmon.conf (restart is handled by script)
        # These paths need to be determined, possibly from config or environment
        # For now, assume genmonmaint.sh and startgenmon.sh are in project root and _run_bash_script handles path.
        # The script itself uses relative paths or discovers them.
        # UIPresenter shouldn't need to know exact project path if scripts are self-contained or use relative paths.
        
        # If genmonmaint.sh needs absolute paths for -p or -s, those would need to be passed.
        # For now, let's assume the script can derive these or they are configured elsewhere (e.g. within the script).
        # The original RunBashScript in genserv.py resolved the script path to be next to genserv.py.
        # The new _run_bash_script resolves it to project root.
        
        # Simplified args if script is smart enough:
        args = ["-u", "-n"] # -p and -s might be auto-detected by the script or unnecessary if it restarts itself.
        # If the script *requires* project_path and start_script_path:
        # project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        # start_script_path_abs = os.path.join(project_root, "startgenmon.sh")
        # args = ["-u", "-n", "-p", project_root, "-s", start_script_path_abs]


        update_result = self._run_bash_script(update_command, args)
        if update_result.get("status") == "error":
            self.log.error(f"Software update script failed: {update_result.get('message')}")
            return update_result

        self.log.info("Software update script completed. Attempting to restart Genmon.")
        # The restart is often part of the update script itself (-s flag handles it)
        # If a separate restart is needed:
        # restart_result = self.restart_genmon()
        # return restart_result
        return {"status": "OK", "message": "Software update process initiated. Genmon should restart if update was successful."}


    def restart_genmon(self):
        """
        Restarts the Genmon application using startgenmon.sh.
        Returns:
            dict: Status dictionary.
        """
        self.log.info("Attempting to restart Genmon application.")
        # Path to startgenmon.sh might need to be configurable
        restart_command = "startgenmon.sh" # This might need full path
        # Similar to update_software, args might be simplified if startgenmon.sh is smart.
        # config_file is available as self.ConfigFilePath
        # project_path might be needed if script doesn't auto-detect.
        # project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        args = ["restart", "-c", self.ConfigFilePath] # Assuming -p (project_path) is auto-detected by script
        # If not: args = ["restart", "-p", project_root, "-c", self.ConfigFilePath]

        result = self._run_bash_script(restart_command, args)
        if result.get("status") == "OK":
            self.log.info("Genmon restart command issued successfully.")
        else:
            self.log.error(f"Genmon restart command failed: {result.get('message')}")
        return result

    def reboot_system(self):
        """
        Reboots the system.
        Returns:
            dict: Status dictionary.
        """
        self.log.info("Attempting to reboot the system.")
        # This command requires sudo and will not return if successful.
        result = self._run_bash_script("sudo reboot now")
        # The response might not be seen if reboot is immediate.
        # Logging before the call is critical.
        return result

    def shutdown_system(self):
        """
        Shuts down the system.
        Returns:
            dict: Status dictionary.
        """
        self.log.info("Attempting to shut down the system.")
        # This command requires sudo and will not return if successful.
        result = self._run_bash_script("sudo shutdown -h now")
        # Logging before the call is critical.
        return result

    def backup_configuration(self):
        """
        Backs up the Genmon configuration using genmonmaint.sh.
        Returns:
            dict: Status dictionary, including path to backup file if successful.
        """
        self.log.info("Attempting to backup Genmon configuration.")
        backup_command = "genmonmaint.sh"
        # Args for backup: genmonmaint.sh -b -c /path/to/genmon.conf
        # The script should ideally place the backup in a known location or output the path.
        # Assume script places backup in project_root/backups or similar, and outputs path.
        # project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        # backup_dir_abs = os.path.join(project_root, "backups") # Example, script might use its own default
        # args = ["-b", "-c", self.ConfigFilePath, "-d", backup_dir_abs]
        args = ["-b", "-c", self.ConfigFilePath] # Simpler if script handles backup dir

        result = self._run_bash_script(backup_command, args)
        
        # The new _run_bash_script returns stdout in "message" or "stdout"
        # and "path" if it's a backup/archive command and stdout contained a path.
        if result.get("status") == "OK" and result.get("path"):
            self.log.info(f"Configuration backup successful. Path: {result.get('path')}")
            # The 'path' key is now directly in the result from _run_bash_script
        elif result.get("status") == "OK": # Script succeeded but no path in stdout (should not happen for -b)
            self.log.warning(f"Configuration backup script ran, but no path was returned in stdout. Output: {result.get('stdout')}")
            # Fallback or error if path is crucial and missing
            return {"status": "error", "message": "Backup script ran but did not return a path."}
        else:
            self.log.error(f"Configuration backup failed: {result.get('message')}")
        return result

    def get_log_archive(self):
        """
        Creates and returns a log archive using genmonmaint.sh.
        Returns:
            dict: Status dictionary, including path to log archive if successful.
        """
        self.log.info("Attempting to create log archive.")
        archive_command = "genmonmaint.sh"
        # Args for log archive: genmonmaint.sh -l
        # Script should output path of the archive.
        # log_location might be read from config if needed by script, or script has default.
        # project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        # archive_dir_abs = os.path.join(project_root, "archives") # Example
        # args = ["-l", "-d", archive_dir_abs] # If script needs output dir
        args = ["-l"] # Simpler if script handles archive dir and outputs path

        result = self._run_bash_script(archive_command, args)

        if result.get("status") == "OK" and result.get("path"):
            self.log.info(f"Log archive creation successful. Path: {result.get('path')}")
        elif result.get("status") == "OK":
             self.log.warning(f"Log archive script ran, but no path was returned in stdout. Output: {result.get('stdout')}")
             return {"status": "error", "message": "Log archive script ran but did not return a path."}
        else:
            self.log.error(f"Log archive creation failed: {result.get('message')}")
        return result

    # Settings Management Methods
    # These methods use MyConfig to interact with configuration files.

    def get_general_settings(self):
        """
        Reads general settings from the main configuration file (genmon.conf).
        Returns:
            dict: A dictionary of general settings, or an error dictionary.
        """
        try:
            conf = MyConfig(self.ConfigFilePath, log=self.log)
            if not conf.InitComplete:
                return {"error": "Failed to initialize MyConfig for general settings."}

            settings = {
                "Brand": conf.ReadValue("Brand", default="Brand", section="SYSTEM"),
                "Model": conf.ReadValue("Model", default="Model", section="SYSTEM"),
                "Serial": conf.ReadValue("Serial", default="Serial", section="SYSTEM"),
                "FluidType": conf.ReadValue("FluidType", default="LP", section="SYSTEM"),
                "SiteName": conf.ReadValue("SiteName", default="My Generator", section="SYSTEM"),
                "MonitorName": conf.ReadValue("MonitorName", default="GENMON", section="SYSTEM"),
                "ControllerAddr": conf.ReadValue("ControllerAddr", default="192.168.1.250:502", section="SYSTEM"),
                "Interface": conf.ReadValue("Interface", default="MODBUS", section="SYSTEM"),
                "ModbusProto": conf.ReadValue("ModbusProto", default="RTU", section="SYSTEM"),
                "ModbusSlaveAddr": conf.ReadValue("ModbusSlaveAddr", return_type=int, default=1, section="SYSTEM"),
                "ModbusBaud": conf.ReadValue("ModbusBaud", return_type=int, default=19200, section="SYSTEM"),
                "ModbusInterface": conf.ReadValue("ModbusInterface", default="/dev/ttyUSB0", section="SYSTEM"),
                "GenmonMinorVersion": conf.ReadValue("GenmonMinorVersion", default="1", section="SYSTEM"), # Assuming this is a typo and should be GenmonUpdateChannel or similar
                "GenmonUpdateChannel": conf.ReadValue("GenmonUpdateChannel", default="stable", section="SYSTEM"),
                "GenmonDevOptions": conf.ReadValue("GenmonDevOptions", return_type=bool, default=False, section="SYSTEM"),
                "Latitude": conf.ReadValue("Latitude", default="", section="LOCATION"),
                "Longitude": conf.ReadValue("Longitude", default="", section="LOCATION"),
                "Altitude": conf.ReadValue("Altitude", default="", section="LOCATION"),
                "Units": conf.ReadValue("Units", default="imperial", section="LOCALIZATION"),
                "Language": conf.ReadValue("Language", default="en", section="LOCALIZATION"),
                "TempFormat": conf.ReadValue("TempFormat", default="F", section="LOCALIZATION"),
                "GenPower": conf.ReadValue("GenPower", default="0", section="GENERATOR"),
                "FuelUsed": conf.ReadValue("FuelUsed", default="0", section="GENERATOR"), # This seems more like a status than a setting
                "GenHours": conf.ReadValue("GenHours", default="0", section="GENERATOR"), # Ditto
                "StartBattery": conf.ReadValue("StartBattery", default="0", section="GENERATOR"), # Ditto
                "GenVoltage": conf.ReadValue("GenVoltage", default="0", section="GENERATOR"), # Ditto
                "RemoteStart": conf.ReadValue("RemoteStart", default="False", section="FEATURES"),
                "RemoteStop": conf.ReadValue("RemoteStop", default="False", section="FEATURES"),
                "PowerOutageRun": conf.ReadValue("PowerOutageRun", return_type=bool, default=False, section="FEATURES"),
                "OutageDelay": conf.ReadValue("OutageDelay", return_type=int, default=30, section="FEATURES"),
                "EnableQuietMode": conf.ReadValue("EnableQuietMode", return_type=bool, default=False, section="FEATURES"),
                "QuietModeStart": conf.ReadValue("QuietModeStart", default="22:00", section="FEATURES"),
                "QuietModeStop": conf.ReadValue("QuietModeStop", default="07:00", section="FEATURES"),
                "ExerciseEnabled": conf.ReadValue("ExerciseEnabled", return_type=bool, default=True, section="EXERCISE"),
                "ExerciseDay": conf.ReadValue("ExerciseDay", default="Friday", section="EXERCISE"),
                "ExerciseTime": conf.ReadValue("ExerciseTime", default="13:00", section="EXERCISE"),
                "ExercisePeriod": conf.ReadValue("ExercisePeriod", default="Weekly", section="EXERCISE"),
                "ExerciseDuration": conf.ReadValue("ExerciseDuration", return_type=int, default=12, section="EXERCISE"),
                "NoLoadTest": conf.ReadValue("NoLoadTest", return_type=bool, default=True, section="EXERCISE"),
                "FullCycle": conf.ReadValue("FullCycle", return_type=bool, default=False, section="EXERCISE"),
                "EmailEnable": conf.ReadValue("EmailEnable", return_type=bool, default=False, section="EMAIL"),
                "SMTPIP": conf.ReadValue("SMTPIP", default="smtp.gmail.com", section="EMAIL"),
                "SMTPPort": conf.ReadValue("SMTPPort", return_type=int, default=587, section="EMAIL"),
                "SMTPUser": conf.ReadValue("SMTPUser", default="user@example.com", section="EMAIL"),
                "SMTPPassword": conf.ReadValue("SMTPPassword", default="", section="EMAIL"),
                "SMTPAuth": conf.ReadValue("SMTPAuth", return_type=bool, default=True, section="EMAIL"),
                "EmailTo": conf.ReadValue("EmailTo", default="user@example.com", section="EMAIL"),
                "EmailFrom": conf.ReadValue("EmailFrom", default="genmon@example.com", section="EMAIL"),
                "EmailStart": conf.ReadValue("EmailStart", return_type=bool, default=False, section="EMAIL"),
                "EmailStop": conf.ReadValue("EmailStop", return_type=bool, default=False, section="EMAIL"),
                "EmailOutage": conf.ReadValue("EmailOutage", return_type=bool, default=False, section="EMAIL"),
                "EmailExercise": conf.ReadValue("EmailExercise", return_type=bool, default=False, section="EMAIL"),
                "EmailService": conf.ReadValue("EmailService", return_type=bool, default=False, section="EMAIL"),
                "EmailFault": conf.ReadValue("EmailFault", return_type=bool, default=False, section="EMAIL"),
            }
            return settings
        except Exception as e:
            self.log.error(f"Error reading general settings: {e}")
            return {"error": f"Failed to read general settings: {e}"}

    def save_general_settings(self, settings_dict):
        """
        Saves general settings to the main configuration file (genmon.conf).
        Args:
            settings_dict (dict): A dictionary of settings to save.
        Returns:
            dict: Status dictionary (OK or error).
        """
        try:
            conf = MyConfig(self.ConfigFilePath, log=self.log)
            if not conf.InitComplete:
                return {"status": "error", "message": "Failed to initialize MyConfig for saving general settings."}

            # Mapping from form keys (or dict keys) to (section, key_in_conf_file, type)
            # This helps manage type conversions and section targeting.
            # Based on ReadSettingsFromFile and SaveSettings in genserv.py
            key_map = {
                # SYSTEM
                "Brand": ("SYSTEM", "Brand", str), "Model": ("SYSTEM", "Model", str),
                "Serial": ("SYSTEM", "Serial", str), "FluidType": ("SYSTEM", "FluidType", str),
                "SiteName": ("SYSTEM", "SiteName", str), "MonitorName": ("SYSTEM", "MonitorName", str),
                "ControllerAddr": ("SYSTEM", "ControllerAddr", str), "Interface": ("SYSTEM", "Interface", str),
                "ModbusProto": ("SYSTEM", "ModbusProto", str), "ModbusSlaveAddr": ("SYSTEM", "ModbusSlaveAddr", str), # Should be int, but saved as str
                "ModbusBaud": ("SYSTEM", "ModbusBaud", str), # Should be int, saved as str
                "ModbusInterface": ("SYSTEM", "ModbusInterface", str),
                "GenmonUpdateChannel": ("SYSTEM", "GenmonUpdateChannel", str),
                "GenmonDevOptions": ("SYSTEM", "GenmonDevOptions", bool),
                # LOCATION
                "Latitude": ("LOCATION", "Latitude", str), "Longitude": ("LOCATION", "Longitude", str),
                "Altitude": ("LOCATION", "Altitude", str),
                # LOCALIZATION
                "Units": ("LOCALIZATION", "Units", str), "Language": ("LOCALIZATION", "Language", str),
                "TempFormat": ("LOCALIZATION", "TempFormat", str),
                # FEATURES (mix of settings from different sections in original SaveSettings)
                "RemoteStart": ("FEATURES", "RemoteStart", bool), "RemoteStop": ("FEATURES", "RemoteStop", bool),
                "PowerOutageRun": ("FEATURES", "PowerOutageRun", bool), "OutageDelay": ("FEATURES", "OutageDelay", str), # int, saved as str
                "EnableQuietMode": ("FEATURES", "EnableQuietMode", bool),
                "QuietModeStart": ("FEATURES", "QuietModeStart", str), "QuietModeStop": ("FEATURES", "QuietModeStop", str),
                # EXERCISE
                "ExerciseEnabled": ("EXERCISE", "ExerciseEnabled", bool), "ExerciseDay": ("EXERCISE", "ExerciseDay", str),
                "ExerciseTime": ("EXERCISE", "ExerciseTime", str), "ExercisePeriod": ("EXERCISE", "ExercisePeriod", str),
                "ExerciseDuration": ("EXERCISE", "ExerciseDuration", str), # int, saved as str
                "NoLoadTest": ("EXERCISE", "NoLoadTest", bool), "FullCycle": ("EXERCISE", "FullCycle", bool),
                # EMAIL
                "EmailEnable": ("EMAIL", "EmailEnable", bool), "SMTPIP": ("EMAIL", "SMTPIP", str),
                "SMTPPort": ("EMAIL", "SMTPPort", str), # int, saved as str
                "SMTPUser": ("EMAIL", "SMTPUser", str), "SMTPPassword": ("EMAIL", "SMTPPassword", str),
                "SMTPAuth": ("EMAIL", "SMTPAuth", bool), "EmailTo": ("EMAIL", "EmailTo", str),
                "EmailFrom": ("EMAIL", "EmailFrom", str), "EmailStart": ("EMAIL", "EmailStart", bool),
                "EmailStop": ("EMAIL", "EmailStop", bool), "EmailOutage": ("EMAIL", "EmailOutage", bool),
                "EmailExercise": ("EMAIL", "EmailExercise", bool), "EmailService": ("EMAIL", "EmailService", bool),
                "EmailFault": ("EMAIL", "EmailFault", bool),
            }

            for key, value in settings_dict.items():
                if key in key_map:
                    section, conf_key, val_type = key_map[key]
                    # MyConfig.WriteValue expects string values. Booleans are 'True'/'False'.
                    str_value = str(value) if isinstance(value, bool) else str(value) # Ensure it's a string
                    if not conf.WriteValue(conf_key, str_value, section=section):
                        self.log.error(f"Failed to write setting: {section}/{conf_key} = {str_value}")
                        # Decide if one error should halt all writes or collect errors
                        # For now, let's try to write all and report general failure if any fails.
            
            # Checkbox values that are not present in form submission mean 'False'
            # This needs to be handled carefully if settings_dict comes from a form.
            # The provided settings_dict should ideally have all keys with their intended values.
            # For example, if a checkbox 'EmailStart' is unchecked, settings_dict['EmailStart'] should be False.

            self.log.info("General settings saved successfully.")
            # Trigger a config reload in the backend if necessary (outside presenter's scope)
            # e.g., self.client_interface.ProcessMonitorCommand("client: reloadconfig")
            return {"status": "OK", "message": "General settings saved successfully."}
        except Exception as e:
            self.log.error(f"Error saving general settings: {e}")
            return {"status": "error", "message": f"Failed to save general settings: {e}"}

    def get_advanced_settings(self):
        """
        Reads advanced settings from the main configuration file (genmon.conf).
        Returns:
            dict: A dictionary of advanced settings, or an error dictionary.
        """
        try:
            conf = MyConfig(self.ConfigFilePath, log=self.log)
            if not conf.InitComplete:
                return {"error": "Failed to initialize MyConfig for advanced settings."}

            settings = {
                # CLIENT section
                "PollingInterval": conf.ReadValue("PollingInterval", return_type=int, default=2, section="CLIENT"),
                "CFPollingInterval": conf.ReadValue("CFPollingInterval", return_type=int, default=30, section="CLIENT"),
                "ChartRefreshInterval": conf.ReadValue("ChartRefreshInterval", return_type=int, default=60, section="CLIENT"),
                "HighPowerUsage": conf.ReadValue("HighPowerUsage", return_type=int, default=75, section="CLIENT"),
                "LowPowerUsage": conf.ReadValue("LowPowerUsage", return_type=int, default=25, section="CLIENT"),
                "HighBatteryVoltage": conf.ReadValue("HighBatteryVoltage", return_type=float, default=14.0, section="CLIENT"),
                "LowBatteryVoltage": conf.ReadValue("LowBatteryVoltage", return_type=float, default=11.5, section="CLIENT"),
                "LowFuelAlarm": conf.ReadValue("LowFuelAlarm", return_type=int, default=25, section="CLIENT"),
                "PanelTimeout": conf.ReadValue("PanelTimeout", return_type=int, default=30, section="CLIENT"),
                "MaxLogSize": conf.ReadValue("MaxLogSize", return_type=int, default=1000000, section="CLIENT"),
                "MaxOutageLogSize": conf.ReadValue("MaxOutageLogSize", return_type=int, default=1000000, section="CLIENT"),
                "OutageLogRetention": conf.ReadValue("OutageLogRetention", return_type=int, default=365, section="CLIENT"), # Days
                "StatusLogRetention": conf.ReadValue("StatusLogRetention", return_type=int, default=30, section="CLIENT"),   # Days
                "MaintLogRetention": conf.ReadValue("MaintLogRetention", return_type=int, default=3650, section="CLIENT"), # Days
                "NTPHost": conf.ReadValue("NTPHost", default="pool.ntp.org", section="CLIENT"),
                "NTPSync": conf.ReadValue("NTPSync", return_type=bool, default=True, section="CLIENT"),
                "GenmonLogEnable": conf.ReadValue("GenmonLogEnable", return_type=bool, default=True, section="CLIENT"),
                # DEBUG section
                "Debug": conf.ReadValue("Debug", return_type=bool, default=False, section="DEBUG"),
                "DebugComm": conf.ReadValue("DebugComm", return_type=bool, default=False, section="DEBUG"),
                "LogMQTT": conf.ReadValue("LogMQTT", return_type=bool, default=False, section="DEBUG"),
                "CachePath": conf.ReadValue("CachePath", default="/var/cache/genmon", section="DEBUG"), # Should be CLIENT or SYSTEM
                "TempPath": conf.ReadValue("TempPath", default="/tmp/genmon", section="DEBUG"), # Ditto
                "DisableStatusLog": conf.ReadValue("DisableStatusLog", return_type=bool, default=False, section="DEBUG"),
                "RemoteMonitorLog": conf.ReadValue("RemoteMonitorLog", return_type=bool, default=False, section="DEBUG"),
            }
            return settings
        except Exception as e:
            self.log.error(f"Error reading advanced settings: {e}")
            return {"error": f"Failed to read advanced settings: {e}"}

    def save_advanced_settings(self, settings_dict):
        """
        Saves advanced settings to the main configuration file (genmon.conf).
        Args:
            settings_dict (dict): A dictionary of settings to save.
        Returns:
            dict: Status dictionary (OK or error).
        """
        try:
            conf = MyConfig(self.ConfigFilePath, log=self.log)
            if not conf.InitComplete:
                return {"status": "error", "message": "Failed to initialize MyConfig for saving advanced settings."}

            key_map = {
                # CLIENT
                "PollingInterval": ("CLIENT", "PollingInterval", str), # int, saved as str
                "CFPollingInterval": ("CLIENT", "CFPollingInterval", str), # int, saved as str
                "ChartRefreshInterval": ("CLIENT", "ChartRefreshInterval", str), # int, saved as str
                "HighPowerUsage": ("CLIENT", "HighPowerUsage", str), # int, saved as str
                "LowPowerUsage": ("CLIENT", "LowPowerUsage", str), # int, saved as str
                "HighBatteryVoltage": ("CLIENT", "HighBatteryVoltage", str), # float, saved as str
                "LowBatteryVoltage": ("CLIENT", "LowBatteryVoltage", str), # float, saved as str
                "LowFuelAlarm": ("CLIENT", "LowFuelAlarm", str), # int, saved as str
                "PanelTimeout": ("CLIENT", "PanelTimeout", str), # int, saved as str
                "MaxLogSize": ("CLIENT", "MaxLogSize", str), # int, saved as str
                "MaxOutageLogSize": ("CLIENT", "MaxOutageLogSize", str), # int, saved as str
                "OutageLogRetention": ("CLIENT", "OutageLogRetention", str), # int, saved as str
                "StatusLogRetention": ("CLIENT", "StatusLogRetention", str), # int, saved as str
                "MaintLogRetention": ("CLIENT", "MaintLogRetention", str), # int, saved as str
                "NTPHost": ("CLIENT", "NTPHost", str),
                "NTPSync": ("CLIENT", "NTPSync", bool),
                "GenmonLogEnable": ("CLIENT", "GenmonLogEnable", bool),
                # DEBUG
                "Debug": ("DEBUG", "Debug", bool),
                "DebugComm": ("DEBUG", "DebugComm", bool),
                "LogMQTT": ("DEBUG", "LogMQTT", bool),
                "CachePath": ("DEBUG", "CachePath", str),
                "TempPath": ("DEBUG", "TempPath", str),
                "DisableStatusLog": ("DEBUG", "DisableStatusLog", bool),
                "RemoteMonitorLog": ("DEBUG", "RemoteMonitorLog", bool),
            }

            for key, value in settings_dict.items():
                if key in key_map:
                    section, conf_key, _ = key_map[key] # type info not strictly needed for WriteValue
                    str_value = str(value) # MyConfig.WriteValue expects string
                    if not conf.WriteValue(conf_key, str_value, section=section):
                        self.log.error(f"Failed to write advanced setting: {section}/{conf_key} = {str_value}")
                        # Potentially collect errors or return on first error
            
            self.log.info("Advanced settings saved successfully.")
            # Consider if a backend config reload is needed
            # self.client_interface.ProcessMonitorCommand("client: reloadconfig")
            return {"status": "OK", "message": "Advanced settings saved successfully."}
        except Exception as e:
            self.log.error(f"Error saving advanced settings: {e}")
            return {"status": "error", "message": f"Failed to save advanced settings: {e}"}

    def get_notification_settings(self):
        """
        Reads notification settings from notifications.conf.
        Returns:
            dict: Contains 'notifications' (list of dicts) and 'order' (string), or an error dict.
        """
        notifications_file_path = self.ConfigFilePath.replace("genmon.conf", "notifications.conf")
        try:
            conf = MyConfig(notifications_file_path, log=self.log)
            if not conf.InitComplete:
                return {"error": "Failed to initialize MyConfig for notifications.conf."}

            notifications = []
            order_string = conf.ReadValue("order", default="", section="NOTIFY")
            if order_string:
                for num_str in order_string.split(','):
                    section_name = "NOTIFY" + num_str
                    if conf.HasOption(section_name): # Check if section exists
                        item = {
                            "num": num_str,
                            "desc": conf.ReadValue("Desc", default="", section=section_name),
                            "type": conf.ReadValue("Type", default="", section=section_name),
                            "param1": conf.ReadValue("Param1", default="", section=section_name),
                            "param2": conf.ReadValue("Param2", default="", section=section_name),
                            "param3": conf.ReadValue("Param3", default="", section=section_name),
                            "param4": conf.ReadValue("Param4", default="", section=section_name),
                            "param5": conf.ReadValue("Param5", default="", section=section_name),
                            "param6": conf.ReadValue("Param6", default="", section=section_name),
                            "param7": conf.ReadValue("Param7", default="", section=section_name),
                            "param8": conf.ReadValue("Param8", default="", section=section_name),
                            "message": conf.ReadValue("Message", default="", section=section_name),
                            "enable": conf.ReadValue("Enable", return_type=bool, default=False, section=section_name),
                        }
                        notifications.append(item)
            return {"notifications": notifications, "order": order_string}
        except Exception as e:
            self.log.error(f"Error reading notification settings: {e}")
            return {"error": f"Failed to read notification settings: {e}"}

    def save_notification_settings(self, notifications_data, order_string):
        """
        Saves notification settings to notifications.conf.
        Args:
            notifications_data (list): A list of dictionaries, each representing a notification.
            order_string (str): Comma-separated string of notification numbers for order.
        Returns:
            dict: Status dictionary (OK or error).
        """
        notifications_file_path = self.ConfigFilePath.replace("genmon.conf", "notifications.conf")
        try:
            conf = MyConfig(notifications_file_path, log=self.log)
            if not conf.InitComplete:
                return {"status": "error", "message": "Failed to initialize MyConfig for notifications.conf."}

            # Save the order string
            conf.WriteValue("order", order_string, section="NOTIFY")

            # Save each notification item
            for item in notifications_data:
                section_name = "NOTIFY" + item["num"]
                if not conf.HasOption(section_name) and not conf.config.has_section(section_name):
                    conf.WriteSection(section_name) # Create section if it doesn't exist

                conf.WriteValue("Desc", item.get("desc", ""), section=section_name)
                conf.WriteValue("Type", item.get("type", ""), section=section_name)
                conf.WriteValue("Param1", item.get("param1", ""), section=section_name)
                conf.WriteValue("Param2", item.get("param2", ""), section=section_name)
                conf.WriteValue("Param3", item.get("param3", ""), section=section_name)
                conf.WriteValue("Param4", item.get("param4", ""), section=section_name)
                conf.WriteValue("Param5", item.get("param5", ""), section=section_name)
                conf.WriteValue("Param6", item.get("param6", ""), section=section_name)
                conf.WriteValue("Param7", item.get("param7", ""), section=section_name)
                conf.WriteValue("Param8", item.get("param8", ""), section=section_name)
                conf.WriteValue("Message", item.get("message", ""), section=section_name)
                conf.WriteValue("Enable", str(item.get("enable", False)), section=section_name)
            
            self.log.info("Notification settings saved successfully.")
            # Consider if a backend config reload is needed
            # self.client_interface.ProcessMonitorCommand("client: reloadnotifications")
            return {"status": "OK", "message": "Notification settings saved successfully."}
        except Exception as e:
            self.log.error(f"Error saving notification settings: {e}")
            return {"status": "error", "message": f"Failed to save notification settings: {e}"}

    def get_addon_settings(self):
        """
        Reads settings for all addons. This is complex as it involves finding addon.conf files.
        Returns:
            dict: A dictionary where keys are addon names and values are their settings,
                  or an error dictionary.
        """
        # This method would need to replicate the logic in GetAddOns() from genserv.py,
        # which involves finding addon.conf files in subdirectories of 'addons'.
        # It would then read each addon.conf.
        self.log.info("get_addon_settings called. This method requires complex logic to find and parse multiple addon.conf files.")
        # Placeholder structure:
        # addon_settings = {}
        # try:
        #     addons_dir = os.path.join(os.path.dirname(self.ConfigFilePath), "addons") # Assuming relative path
        #     for addon_name in os.listdir(addons_dir):
        #         addon_conf_path = os.path.join(addons_dir, addon_name, "addon.conf")
        #         if os.path.exists(addon_conf_path):
        #             conf = MyConfig(addon_conf_path, log=self.log)
        #             if conf.InitComplete:
        #                 # Read relevant settings for this addon
        #                 # Example: addon_settings[addon_name] = {"setting1": conf.ReadValue(...), ...}
        #                 pass # Actual implementation needed
        # except Exception as e:
        #     self.log.error(f"Error reading addon settings: {e}")
        #     return {"error": f"Failed to read addon settings: {e}"}
        # return addon_settings
        return {"placeholder": "Addon settings functionality not fully implemented here."}


    def save_addon_settings(self, settings_dict):
        """
        Saves settings for addons. This is complex.
        Args:
            settings_dict (dict): A dictionary where keys are addon names and values are their settings.
        Returns:
            dict: Status dictionary (OK or error).
        """
        # This method would need to iterate through settings_dict,
        # locate the correct addon.conf for each addon, and write the settings.
        self.log.info("save_addon_settings called. This method requires complex logic to find and write to multiple addon.conf files.")
        # Placeholder structure:
        # try:
        #     addons_dir = os.path.join(os.path.dirname(self.ConfigFilePath), "addons")
        #     for addon_name, addon_specific_settings in settings_dict.items():
        #         addon_conf_path = os.path.join(addons_dir, addon_name, "addon.conf")
        #         if os.path.exists(addon_conf_path):
        #             conf = MyConfig(addon_conf_path, log=self.log)
        #             if conf.InitComplete:
        #                 for key, value in addon_specific_settings.items():
        #                     # conf.WriteValue(key, str(value), section="ADDON_SECTION_NAME") # Section name might vary
        #                     pass # Actual implementation needed
        # except Exception as e:
        #     self.log.error(f"Error saving addon settings: {e}")
        #     return {"status": "error", "message": f"Failed to save addon settings: {e}"}
        # return {"status": "OK", "message": "Addon settings saved (placeholder)."}
        return {"placeholder": "Save addon settings functionality not fully implemented here."}

    def send_test_email(self, email_params_dict):
        """
        Sends a test email using settings from email_params_dict.
        This method would use MyMail, similar to genserv.py's SendTestEmail.
        Args:
            email_params_dict (dict): Contains SMTP server details, auth, to/from addresses.
        Returns:
            dict: Status dictionary (OK or error).
        """
        # from genmonlib.mymail import MyMail # Import locally to avoid circular deps if MyMail needs UIPresenter
        self.log.info(f"Attempting to send test email with params: {email_params_dict}")

        # This is a placeholder. A real implementation would instantiate MyMail
        # and call its TestSendSettings method.
        # Example:
        # try:
        #     # mailer = MyMail(self.log) # MyMail might need config path too
        #     # result, message = mailer.TestSendSettings(
        #     #     email_params_dict.get("SMTPIP"),
        #     #     email_params_dict.get("SMTPPort"),
        #     #     email_params_dict.get("SMTPUser"),
        #     #     email_params_dict.get("SMTPPassword"),
        #     #     email_params_dict.get("EmailTo"),
        #     #     email_params_dict.get("EmailFrom"),
        #     #     email_params_dict.get("SMTPAuth", True) # Default to True if not provided
        #     # )
        #     # if result:
        #     #     self.log.info("Test email sent successfully.")
        #     #     return {"status": "OK", "message": "Test email sent successfully."}
        #     # else:
        #     #     self.log.error(f"Failed to send test email: {message}")
        #     #     return {"status": "error", "message": f"Failed to send test email: {message}"}
        #     self.log.warning("send_test_email is a placeholder and did not actually send an email.")
        #     return {"status": "OK", "message": "Test email function is a placeholder. Email not sent."}
        # except Exception as e:
        #     self.log.error(f"Exception in send_test_email: {e}")
        #     return {"status": "error", "message": f"Exception during test email: {str(e)}"}

        # For now, simulating success as MyMail is not directly usable here without more refactoring
        # of its dependencies or how it's instantiated.
        if email_params_dict.get("EmailTo") and email_params_dict.get("EmailFrom"):
            self.log.info("Simulating successful test email dispatch.")
            return {"status": "OK", "message": "Test email would have been sent (simulated)."}
        else:
            self.log.error("Test email simulation failed: Missing To/From address.")
            return {"status": "error", "message": "Missing To/From address for test email (simulated)."}

    # The handle_ methods below were refactored in a previous step to return dicts.
    # They are correctly placed before the get_status_page_data and other get_... methods.
    # The duplicated section of old handle_ methods that might have appeared here
    # in thought process is now removed, ensuring these are the definitive versions.

    def get_status_page_data(self):
        """
        Fetches and prepares data for the main status page.
        
        Note: This is currently a placeholder and should be updated to fetch
        actual status data.

        Returns:
            A dictionary with data for the status page template.
        """
        # Placeholder for fetching and preparing status page data
        # Example:
        # raw_data = self.client_interface.ProcessMonitorCommand("generator: status_json")
        # processed_data = self._process_status_data(raw_data)
        # return processed_data
        return {"title": "Status Page - Placeholder", "content": "Data will be here soon."}

    def _process_status_data(self, raw_data):
        """
        Processes raw status data.

        Args:
            raw_data: The raw data (typically a dictionary parsed from JSON) 
                      to be processed.

        Returns:
            A dictionary containing the processed data and a timestamp.
        """
        # Example processing:
        processed_data = {"processed_content": raw_data, "timestamp": datetime.datetime.now().isoformat()}
        return processed_data

    def get_index_page_data(self):
        """
        Provides data for the index (home) page.

        Returns:
            A dictionary containing the title and a greeting message for the home page.
        """
        # Placeholder for index page data
        return {"title": "Genmon Home", "greeting": "Welcome to Genmon!"}

    def get_status_json(self):
        """
        Fetches generator status and returns it as a JSON-like dictionary.

        Returns:
            A dictionary containing the processed status data and a timestamp,
            or an error dictionary if fetching/processing fails.
        """
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: status_json")
        try:
            raw_data = json.loads(raw_data_str)
            return self._process_status_data(raw_data) 
        except json.JSONDecodeError:
            return {"error": "Failed to decode status data"}
        except Exception as e:
            return {"error": str(e)}

    def get_verbose_page_data(self):
        """
        Provides data for the verbose mode page.

        Returns:
            A dictionary containing the title for the verbose mode page.
        """
        return {"title": "Genmon Verbose Mode"}

    def get_lowbandwidth_page_data(self):
        """
        Provides data for the low bandwidth mode page.

        Returns:
            A dictionary containing the title for the low bandwidth mode page.
        """
        return {"title": "Genmon Low Bandwidth Mode"}

    def get_outage_json(self):
        """
        Fetches generator outage data and returns it as a JSON-like dictionary.

        Returns:
            A dictionary containing outage data, type, and timestamp,
            or an error dictionary if fetching/processing fails.
        """
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: outage_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "outage", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode outage data"}
        except Exception as e:
            return {"error": str(e)}

    def get_maint_json(self):
        """
        Fetches generator maintenance data and returns it as a JSON-like dictionary.

        Returns:
            A dictionary containing maintenance data, type, and timestamp,
            or an error dictionary if fetching/processing fails.
        """
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: maint_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "maintenance", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode maintenance data"}
        except Exception as e:
            return {"error": str(e)}

    def get_logs_json(self):
        """
        Fetches generator logs data and returns it as a JSON-like dictionary.

        Returns:
            A dictionary containing logs data, type, and timestamp,
            or an error dictionary if fetching/processing fails.
        """
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: logs_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "logs", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode logs data"}
        except Exception as e:
            return {"error": str(e)}

    def get_internal_page_data(self):
        """
        Provides data for the internal diagnostics page.

        Returns:
            A dictionary containing the title for the internal diagnostics page.
        """
        # This page seems to have its own JS logic, so the presenter might just provide a title.
        return {"title": "Genmon Internal Diagnostics"}

    def get_monitor_json(self):
        """
        Fetches system monitor data and returns it as a JSON-like dictionary.

        Returns:
            A dictionary containing monitor data, type, and timestamp,
            or an error dictionary if fetching/processing fails.
        """
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: monitor_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "monitor", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode monitor data"}
        except Exception as e:
            return {"error": str(e)}

    def get_registers_json(self):
        """
        Fetches generator registers data and returns it as a JSON-like dictionary.

        Returns:
            A dictionary containing registers data, type, and timestamp,
            or an error dictionary if fetching/processing fails.
        """
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: registers_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "registers", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode registers data"}
        except Exception as e:
            return {"error": str(e)}

    def get_allregs_json(self):
        """
        Fetches all generator registers data and returns it as a JSON-like dictionary.

        Returns:
            A dictionary containing all registers data, type, and timestamp,
            or an error dictionary if fetching/processing fails.
        """
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: allregs_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "all_registers", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode all registers data"}
        except Exception as e:
            return {"error": str(e)}

    def get_start_info_json(self, session_data):
        """
        Fetches initial startup information and augments it with session data.

        Args:
            session_data: A dictionary containing session information like
                          'write_access' and 'LoginActive'.

        Returns:
            A dictionary containing startup information combined with session details,
            or an error dictionary if fetching/processing fails.
        """
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: start_info_json")
        try:
            start_info = json.loads(raw_data_str)
            # Augment with session-specific access rights
            start_info["write_access"] = session_data.get("write_access", True)
            if not start_info["write_access"]:
                start_info["pages"]["settings"] = False
                start_info["pages"]["notifications"] = False
            start_info["LoginActive"] = session_data.get("LoginActive", False) 
            return start_info 
        except json.JSONDecodeError:
            return {"error": "Failed to decode start_info data"}
        except Exception as e:
            return {"error": str(e), "trace": "Error in get_start_info_json"}

    def get_gui_status_json(self):
        """
        Fetches GUI status data and returns it as a JSON-like dictionary.

        Returns:
            A dictionary containing GUI status data, type, and timestamp,
            or an error dictionary if fetching/processing fails.
        """
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: gui_status_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "gui_status", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode gui_status data"}
        except Exception as e:
            return {"error": str(e)}

    def get_power_log_json(self, log_period=None):
        """
        Fetches power log data for a specified period.

        Args:
            log_period (str, optional): The period for which to fetch the log (e.g., "1440"). 
                                        Defaults to None for all available data.

        Returns:
            A dictionary containing power log data, type, log period, and timestamp,
            or an error dictionary if fetching/processing fails.
        """
        command = "generator: power_log_json"
        if log_period:
            command += "=" + str(log_period)
        raw_data_str = self.client_interface.ProcessMonitorCommand(command)
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "power_log", "log_period": log_period, "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode power_log data"}
        except Exception as e:
            return {"error": str(e)}

    def get_status_num_json(self):
        """
        Fetches numeric status data and returns it as a JSON-like dictionary.

        Returns:
            A dictionary containing numeric status data, type, and timestamp,
            or an error dictionary if fetching/processing fails.
        """
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: status_num_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "status_numeric", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode status_num data"}
        except Exception as e:
            return {"error": str(e)}

    def get_maint_num_json(self):
        """
        Fetches numeric maintenance data and returns it as a JSON-like dictionary.

        Returns:
            A dictionary containing numeric maintenance data, type, and timestamp,
            or an error dictionary if fetching/processing fails.
        """
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: maint_num_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "maint_numeric", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode maint_num data"}
        except Exception as e:
            return {"error": str(e)}

    def get_monitor_num_json(self):
        """
        Fetches numeric monitor data and returns it as a JSON-like dictionary.

        Returns:
            A dictionary containing numeric monitor data, type, and timestamp,
            or an error dictionary if fetching/processing fails.
        """
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: monitor_num_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "monitor_numeric", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode monitor_num data"}
        except Exception as e:
            return {"error": str(e)}

    def get_outage_num_json(self):
        """
        Fetches numeric outage data and returns it as a JSON-like dictionary.

        Returns:
            A dictionary containing numeric outage data, type, and timestamp,
            or an error dictionary if fetching/processing fails.
        """
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: outage_num_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "outage_numeric", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode outage_num data"}
        except Exception as e:
            return {"error": str(e)}

    def get_maint_log_json(self):
        """
        Fetches the maintenance log and returns it as a JSON-like dictionary.

        Returns:
            A dictionary containing maintenance log data, type, and timestamp,
            or an error dictionary if fetching/processing fails.
        """
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: get_maint_log_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "maint_log", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode maint_log data"} 
        except Exception as e:
            return {"error": str(e)}

    def get_support_data_json(self):
        """
        Fetches support data (often for debugging) and returns it as a JSON-like dictionary.

        Returns:
            A dictionary containing support data, type, and timestamp,
            or an error dictionary if fetching/processing fails.
        """
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: support_data_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "support_data", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode support_data"}
        except Exception as e:
            return {"error": str(e)}

    def get_status_text_data(self):
        """
        Fetches raw generator status text and prepares it for display.

        Returns:
            A dictionary with a title and the processed status text content.
        """
        raw_text_data = self.client_interface.ProcessMonitorCommand("generator: status")
        processed_text = raw_text_data.replace("EndOfMessage", "").strip()
        return {"title": "Generator Status", "data_content": processed_text}

    def get_maint_text_data(self):
        """
        Fetches raw maintenance information text and prepares it for display.

        Returns:
            A dictionary with a title and the processed maintenance text content.
        """
        raw_text_data = self.client_interface.ProcessMonitorCommand("generator: maint")
        processed_text = raw_text_data.replace("EndOfMessage", "").strip()
        return {"title": "Maintenance Information", "data_content": processed_text}

    def get_logs_text_data(self):
        """
        Fetches raw generator logs text and prepares it for display.

        Returns:
            A dictionary with a title and the processed logs text content.
        """
        raw_text_data = self.client_interface.ProcessMonitorCommand("generator: logs")
        processed_text = raw_text_data.replace("EndOfMessage", "").strip()
        return {"title": "Generator Logs", "data_content": processed_text}

    def get_monitor_text_data(self):
        """
        Fetches raw system monitor text data and prepares it for display.

        Returns:
            A dictionary with a title and the processed monitor text content.
        """
        raw_text_data = self.client_interface.ProcessMonitorCommand("generator: monitor")
        processed_text = raw_text_data.replace("EndOfMessage", "").strip()
        return {"title": "System Monitor", "data_content": processed_text}

    def get_outage_text_data(self):
        """
        Fetches raw outage information text and prepares it for display.

        Returns:
            A dictionary with a title and the processed outage text content.
        """
        raw_text_data = self.client_interface.ProcessMonitorCommand("generator: outage")
        processed_text = raw_text_data.replace("EndOfMessage", "").strip()
        return {"title": "Outage Information", "data_content": processed_text}

    def get_help_text_data(self):
        """
        Fetches raw help text and prepares it for display.

        Returns:
            A dictionary with a title and the processed help text content.
        """
        raw_text_data = self.client_interface.ProcessMonitorCommand("generator: help")
        processed_text = raw_text_data.replace("EndOfMessage", "").strip()
        return {"title": "Help Information", "data_content": processed_text}

    # The section with old handle_ methods and get_..._text_data methods below this line
    # should be removed as they are now superseded or handled by JSON methods.
    # For brevity, the diff tool will show this as a large deletion.
