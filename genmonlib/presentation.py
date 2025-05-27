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

class UIPresenter:
    """
    Handles the presentation logic for the web UI.

    This class fetches raw data from a client interface (e.g., a generator
    monitoring process), processes it, and prepares it for rendering in
    Flask templates. It provides methods for different pages and data
    types required by the UI.
    """
    def __init__(self, client_interface):
        """
        Initializes the UIPresenter with a client interface.

        Args:
            client_interface: An object that provides a method 
                              `ProcessMonitorCommand(command_string)` 
                              to communicate with the backend data source.
        """
        self.client_interface = client_interface

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

    def handle_notify_message(self, notify_message_json_params):
        """
        Sends a notify_message command with JSON parameters.

        Args:
            notify_message_json_params (str): A JSON string containing the notification message details.

        Returns:
            str: The processed response string from the client interface, or an error message.
        """
        if not notify_message_json_params:
            return "Error: notify_message parameters not provided."
        final_command = f"generator: notify_message={notify_message_json_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_set_button_command(self, button_command_json_params):
        """
        Sends a set_button_command with JSON parameters.

        Args:
            button_command_json_params (str): A JSON string containing the button command details.

        Returns:
            str: The processed response string from the client interface, or an error message.
        """
        if not button_command_json_params:
            return "Error: set_button_command parameters not provided."
        final_command = f"generator: set_button_command={button_command_json_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_power_log_clear(self):
        """
        Sends the 'power_log_clear' command.

        Returns:
            str: The processed response string from the client interface.
        """
        final_command = "generator: power_log_clear"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_fuel_log_clear(self):
        """
        Sends the 'fuel_log_clear' command.

        Returns:
            str: The processed response string from the client interface.
        """
        final_command = "generator: fuel_log_clear"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_send_registers(self):
        """
        Sends the 'sendregisters' command.

        Returns:
            str: The processed response string from the client interface.
        """
        final_command = "generator: sendregisters"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_send_log_files(self):
        """
        Sends the 'sendlogfiles' command.

        Returns:
            str: The processed response string from the client interface.
        """
        final_command = "generator: sendlogfiles"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def get_debug_info(self): 
        """
        Fetches debug information.

        The response from the client interface might be a JSON string or plain text.
        This method attempts to parse it as JSON, and if that fails, returns it
        as a string within a dictionary.

        Returns:
            dict: A dictionary containing the debug information (parsed as JSON if possible)
                  or an error dictionary.
        """
        final_command = "generator: getdebug"
        raw_response = self.client_interface.ProcessMonitorCommand(final_command)
        processed_response = raw_response.replace("EndOfMessage", "").strip()
        try:
            json_data = json.loads(processed_response)
            return json_data 
        except json.JSONDecodeError:
            return {"debug_info": processed_response}
        except Exception as e: 
            return {"error": f"Failed to process debug_info: {str(e)}", "raw_debug_info": processed_response}

    def handle_set_exercise(self, set_exercise_params):
        """
        Constructs and sends the 'setexercise' command.

        Args:
            set_exercise_params (str): The parameter string for setting the exercise time
                                       (e.g., "Monday,13:30,Weekly").

        Returns:
            str: The processed response string from the client interface, or an error message.
        """
        if not set_exercise_params:
            return "Error: setexercise parameters not provided."
        final_command = f"generator: setexercise={set_exercise_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_set_quiet_mode(self, set_quiet_params):
        """
        Constructs and sends the 'setquiet' command.

        Args:
            set_quiet_params (str): The parameter for setting quiet mode ("on" or "off").

        Returns:
            str: The processed response string from the client interface, or an error message.
        """
        if not set_quiet_params:
            return "Error: setquiet parameters not provided."
        final_command = f"generator: setquiet={set_quiet_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_set_remote_command(self, set_remote_params):
        """
        Constructs and sends the 'setremote' command for remote start/stop.

        Args:
            set_remote_params (str): The remote command parameter (e.g., "start", "stop").

        Returns:
            str: The processed response string from the client interface, or an error message.
        """
        if not set_remote_params:
            return "Error: setremote parameters not provided."
        final_command = f"generator: setremote={set_remote_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_set_time(self):
        """
        Sends the 'settime' command to synchronize time.

        Returns:
            str: The processed response string from the client interface.
        """
        final_command = "generator: settime"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_add_maint_log(self, maint_log_json_params):
        """
        Constructs and sends the 'add_maint_log' command with JSON parameters.

        Args:
            maint_log_json_params (str): A JSON string containing the maintenance log entry.

        Returns:
            str: The processed response string from the client interface, or an error message.
        """
        if not maint_log_json_params:
            return "Error: add_maint_log parameters not provided."
        final_command = f"generator: add_maint_log={maint_log_json_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_clear_maint_log(self):
        """
        Sends the 'clear_maint_log' command.

        Returns:
            str: The processed response string from the client interface.
        """
        final_command = "generator: clear_maint_log"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_delete_row_maint_log(self, row_params):
        """
        Constructs and sends the 'delete_row_maint_log' command.

        Args:
            row_params (str): The identifier for the maintenance log row to delete.

        Returns:
            str: The processed response string from the client interface, or an error message.
        """
        if not row_params:
            return "Error: delete_row_maint_log parameters not provided."
        final_command = f"generator: delete_row_maint_log={row_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_edit_row_maint_log(self, maint_log_edit_json_params):
        """
        Constructs and sends the 'edit_row_maint_log' command with JSON parameters.

        Args:
            maint_log_edit_json_params (str): A JSON string containing the maintenance log entry to be edited.

        Returns:
            str: The processed response string from the client interface, or an error message.
        """
        if not maint_log_edit_json_params:
            return "Error: edit_row_maint_log parameters not provided."
        final_command = f"generator: edit_row_maint_log={maint_log_edit_json_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    # Note: The following handle_set_time, handle_add_maint_log, etc. methods are duplicates
    # of those defined above. They were likely added during a previous refactoring step
    # and should be removed if they are indeed identical. For this review, I will assume
    # they are unintentional duplicates based on the prompt to add docstrings to *all* methods.
    # If they were intended to be different, that would be a separate issue.

    # def handle_set_time(self):
    #     # Sends the 'settime' command.
    #     # This command does not take parameters in its current form in genserv.py
    #     final_command = "generator: settime"
    #     response = self.client_interface.ProcessMonitorCommand(final_command)
    #     return response.replace("EndOfMessage", "").strip()

    # def handle_add_maint_log(self, maint_log_json_params):
    #     # Constructs and sends the 'add_maint_log' command.
    #     # maint_log_json_params is a JSON string.
    #     if not maint_log_json_params:
    #         return "Error: add_maint_log parameters not provided."
    #     # The command expects the JSON string directly after "add_maint_log="
    #     final_command = f"generator: add_maint_log={maint_log_json_params}"
    #     response = self.client_interface.ProcessMonitorCommand(final_command)
    #     return response.replace("EndOfMessage", "").strip()

    # def handle_clear_maint_log(self):
    #     # Sends the 'clear_maint_log' command.
    #     final_command = "generator: clear_maint_log"
    #     response = self.client_interface.ProcessMonitorCommand(final_command)
    #     return response.replace("EndOfMessage", "").strip()

    # def handle_delete_row_maint_log(self, row_params):
    #     # Constructs and sends the 'delete_row_maint_log' command.
    #     # row_params is the identifier for the row to delete.
    #     if not row_params:
    #         return "Error: delete_row_maint_log parameters not provided."
    #     final_command = f"generator: delete_row_maint_log={row_params}"
    #     response = self.client_interface.ProcessMonitorCommand(final_command)
    #     return response.replace("EndOfMessage", "").strip()

    # def handle_edit_row_maint_log(self, maint_log_edit_json_params):
    #     # Constructs and sends the 'edit_row_maint_log' command.
    #     # maint_log_edit_json_params is a JSON string.
    #     if not maint_log_edit_json_params:
    #         return "Error: edit_row_maint_log parameters not provided."
    #     final_command = f"generator: edit_row_maint_log={maint_log_edit_json_params}"
    #     response = self.client_interface.ProcessMonitorCommand(final_command)
    #     return response.replace("EndOfMessage", "").strip()

    # def get_monitor_text_data(self):
    #     # Fetches data for the 'monitor' command.
    #     raw_text_data = self.client_interface.ProcessMonitorCommand("generator: monitor")
    #     processed_text = raw_text_data.replace("EndOfMessage", "").strip()
    #     return {"title": "System Monitor", "data_content": processed_text}

    # def get_outage_text_data(self):
    #     # Fetches data for the 'outage' command.
    #     raw_text_data = self.client_interface.ProcessMonitorCommand("generator: outage")
    #     processed_text = raw_text_data.replace("EndOfMessage", "").strip()
    #     return {"title": "Outage Information", "data_content": processed_text}

    # def get_help_text_data(self):
    #     # Fetches data for the 'help' command.
    #     raw_text_data = self.client_interface.ProcessMonitorCommand("generator: help")
    #     processed_text = raw_text_data.replace("EndOfMessage", "").strip()
    #     return {"title": "Help Information", "data_content": processed_text}
