# genmonlib/presentation.py
import json
import datetime

class UIPresenter:
    def __init__(self, client_interface):
        self.client_interface = client_interface

    def get_status_page_data(self):
        # Placeholder for fetching and preparing status page data
        # Example:
        # raw_data = self.client_interface.ProcessMonitorCommand("generator: status_json")
        # processed_data = self._process_status_data(raw_data)
        # return processed_data
        return {"title": "Status Page - Placeholder", "content": "Data will be here soon."}

    def _process_status_data(self, raw_data):
        # Example processing:
        processed_data = {"processed_content": raw_data, "timestamp": datetime.datetime.now().isoformat()}
        return processed_data

    def get_index_page_data(self):
        # Placeholder for index page data
        return {"title": "Genmon Home", "greeting": "Welcome to Genmon!"}

    def get_status_json(self):
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: status_json")
        try:
            # Assuming raw_data_str is a JSON string
            raw_data = json.loads(raw_data_str)
            return self._process_status_data(raw_data) # Use existing helper if suitable
        except json.JSONDecodeError:
            # Handle error if data is not valid JSON
            return {"error": "Failed to decode status data"}
        except Exception as e:
            # Handle other potential errors
            return {"error": str(e)}

    # Add more methods for other pages as needed, e.g.:
    # def get_outage_page_data(self):
    #     ...
    # def get_maintenance_page_data(self):
    #     ...

    def get_verbose_page_data(self):
        # Placeholder for verbose page data
        return {"title": "Genmon Verbose Mode"}

    def get_lowbandwidth_page_data(self):
        # Placeholder for low bandwidth page data
        return {"title": "Genmon Low Bandwidth Mode"}

    def get_outage_json(self):
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: outage_json")
        try:
            raw_data = json.loads(raw_data_str)
            # Add any specific processing for outage data if needed
            return {"processed_content": raw_data, "data_type": "outage", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode outage data"}
        except Exception as e:
            return {"error": str(e)}

    def get_maint_json(self):
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: maint_json")
        try:
            raw_data = json.loads(raw_data_str)
            # Add any specific processing for maintenance data if needed
            return {"processed_content": raw_data, "data_type": "maintenance", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode maintenance data"}
        except Exception as e:
            return {"error": str(e)}

    def get_logs_json(self):
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: logs_json")
        try:
            raw_data = json.loads(raw_data_str)
            # Add any specific processing for logs data if needed
            return {"processed_content": raw_data, "data_type": "logs", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode logs data"}
        except Exception as e:
            return {"error": str(e)}

    def get_internal_page_data(self):
        # Placeholder for internal page data
        # This page seems to have its own JS logic, so the presenter might just provide a title
        # and the template will handle the rest via static JS.
        return {"title": "Genmon Internal Diagnostics"}

    def get_monitor_json(self):
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: monitor_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "monitor", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode monitor data"}
        except Exception as e:
            return {"error": str(e)}

    def get_registers_json(self):
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: registers_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "registers", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode registers data"}
        except Exception as e:
            return {"error": str(e)}

    def get_allregs_json(self):
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: allregs_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "all_registers", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode all registers data"}
        except Exception as e:
            return {"error": str(e)}

    def get_start_info_json(self, session_data): # Pass session data for write_access and LoginActive
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: start_info_json")
        try:
            start_info = json.loads(raw_data_str)
            # Logic previously in genserv.py command route
            start_info["write_access"] = session_data.get("write_access", True)
            if not start_info["write_access"]:
                start_info["pages"]["settings"] = False
                start_info["pages"]["notifications"] = False
            start_info["LoginActive"] = session_data.get("LoginActive", False) # Need to determine how to get LoginActive status here
            return start_info # Return the modified dictionary directly
        except json.JSONDecodeError:
            return {"error": "Failed to decode start_info data"}
        except Exception as e:
            return {"error": str(e), "trace": "Error in get_start_info_json"}

    def get_gui_status_json(self):
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: gui_status_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "gui_status", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode gui_status data"}
        except Exception as e:
            return {"error": str(e)}

    def get_power_log_json(self, log_period=None):
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
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: status_num_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "status_numeric", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode status_num data"}
        except Exception as e:
            return {"error": str(e)}

    def get_maint_num_json(self):
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: maint_num_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "maint_numeric", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode maint_num data"}
        except Exception as e:
            return {"error": str(e)}

    def get_monitor_num_json(self):
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: monitor_num_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "monitor_numeric", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode monitor_num data"}
        except Exception as e:
            return {"error": str(e)}

    def get_outage_num_json(self):
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: outage_num_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "outage_numeric", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode outage_num data"}
        except Exception as e:
            return {"error": str(e)}

    def get_maint_log_json(self): # Method name in presenter get_maint_log_json for consistency
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: get_maint_log_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "maint_log", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode maint_log data"} # Corrected error message
        except Exception as e:
            return {"error": str(e)}

    def get_support_data_json(self):
        raw_data_str = self.client_interface.ProcessMonitorCommand("generator: support_data_json")
        try:
            raw_data = json.loads(raw_data_str)
            return {"processed_content": raw_data, "data_type": "support_data", "timestamp": datetime.datetime.now().isoformat()}
        except json.JSONDecodeError:
            return {"error": "Failed to decode support_data"}
        except Exception as e:
            return {"error": str(e)}

    def get_status_text_data(self):
        raw_text_data = self.client_interface.ProcessMonitorCommand("generator: status")
        processed_text = raw_text_data.replace("EndOfMessage", "").strip()
        return {"title": "Generator Status", "data_content": processed_text}

    def get_maint_text_data(self):
        raw_text_data = self.client_interface.ProcessMonitorCommand("generator: maint")
        processed_text = raw_text_data.replace("EndOfMessage", "").strip()
        return {"title": "Maintenance Information", "data_content": processed_text}

    def get_logs_text_data(self):
        raw_text_data = self.client_interface.ProcessMonitorCommand("generator: logs")
        processed_text = raw_text_data.replace("EndOfMessage", "").strip()
        return {"title": "Generator Logs", "data_content": processed_text}

    def get_monitor_text_data(self):
        # Fetches data for the 'monitor' command.
        raw_text_data = self.client_interface.ProcessMonitorCommand("generator: monitor")
        processed_text = raw_text_data.replace("EndOfMessage", "").strip()
        return {"title": "System Monitor", "data_content": processed_text}

    def get_outage_text_data(self):
        # Fetches data for the 'outage' command.
        raw_text_data = self.client_interface.ProcessMonitorCommand("generator: outage")
        processed_text = raw_text_data.replace("EndOfMessage", "").strip()
        return {"title": "Outage Information", "data_content": processed_text}

    def get_help_text_data(self):
        # Fetches data for the 'help' command.
        raw_text_data = self.client_interface.ProcessMonitorCommand("generator: help")
        processed_text = raw_text_data.replace("EndOfMessage", "").strip()
        return {"title": "Help Information", "data_content": processed_text}

    def handle_notify_message(self, notify_message_json_params):
        if not notify_message_json_params:
            return "Error: notify_message parameters not provided."
        final_command = f"generator: notify_message={notify_message_json_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_set_button_command(self, button_command_json_params):
        if not button_command_json_params:
            return "Error: set_button_command parameters not provided."
        final_command = f"generator: set_button_command={button_command_json_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_power_log_clear(self):
        final_command = "generator: power_log_clear"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_fuel_log_clear(self):
        final_command = "generator: fuel_log_clear"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_send_registers(self):
        final_command = "generator: sendregisters"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_send_log_files(self):
        final_command = "generator: sendlogfiles"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def get_debug_info(self): 
        final_command = "generator: getdebug"
        raw_response = self.client_interface.ProcessMonitorCommand(final_command)
        # Remove EndOfMessage which might be appended by the client interface or the remote process
        processed_response = raw_response.replace("EndOfMessage", "").strip()
        try:
            # Attempt to parse as JSON, in case it's a JSON string
            json_data = json.loads(processed_response)
            return json_data 
        except json.JSONDecodeError:
            # If not JSON, return as a string field in a dict, suitable for jsonify
            return {"debug_info": processed_response}
        except Exception as e: # Catch any other parsing errors or issues
            return {"error": f"Failed to process debug_info: {str(e)}", "raw_debug_info": processed_response}

    def handle_set_exercise(self, set_exercise_params):
        # Constructs and sends the 'setexercise' command.
        # set_exercise_params is the string like "Monday,13:30,Weekly"
        if not set_exercise_params:
            return "Error: setexercise parameters not provided."
        final_command = f"generator: setexercise={set_exercise_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_set_quiet_mode(self, set_quiet_params):
        # Constructs and sends the 'setquiet' command.
        # set_quiet_params is "on" or "off"
        if not set_quiet_params:
            return "Error: setquiet parameters not provided."
        final_command = f"generator: setquiet={set_quiet_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_set_remote_command(self, set_remote_params):
        # Constructs and sends the 'setremote' command.
        # set_remote_params is "start", "stop", etc.
        if not set_remote_params:
            return "Error: setremote parameters not provided."
        final_command = f"generator: setremote={set_remote_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_set_time(self):
        # Sends the 'settime' command.
        final_command = "generator: settime"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_add_maint_log(self, maint_log_json_params):
        # Constructs and sends the 'add_maint_log' command.
        # maint_log_json_params is a JSON string.
        if not maint_log_json_params:
            return "Error: add_maint_log parameters not provided."
        # The command expects the JSON string directly after "add_maint_log="
        final_command = f"generator: add_maint_log={maint_log_json_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_clear_maint_log(self):
        # Sends the 'clear_maint_log' command.
        final_command = "generator: clear_maint_log"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_delete_row_maint_log(self, row_params):
        # Constructs and sends the 'delete_row_maint_log' command.
        # row_params is the identifier for the row to delete.
        if not row_params:
            return "Error: delete_row_maint_log parameters not provided."
        final_command = f"generator: delete_row_maint_log={row_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_edit_row_maint_log(self, maint_log_edit_json_params):
        # Constructs and sends the 'edit_row_maint_log' command.
        # maint_log_edit_json_params is a JSON string.
        if not maint_log_edit_json_params:
            return "Error: edit_row_maint_log parameters not provided."
        final_command = f"generator: edit_row_maint_log={maint_log_edit_json_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_set_time(self):
        # Sends the 'settime' command.
        # This command does not take parameters in its current form in genserv.py
        final_command = "generator: settime"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_add_maint_log(self, maint_log_json_params):
        # Constructs and sends the 'add_maint_log' command.
        # maint_log_json_params is a JSON string.
        if not maint_log_json_params:
            return "Error: add_maint_log parameters not provided."
        # The command expects the JSON string directly after "add_maint_log="
        final_command = f"generator: add_maint_log={maint_log_json_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_clear_maint_log(self):
        # Sends the 'clear_maint_log' command.
        final_command = "generator: clear_maint_log"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_delete_row_maint_log(self, row_params):
        # Constructs and sends the 'delete_row_maint_log' command.
        # row_params is the identifier for the row to delete.
        if not row_params:
            return "Error: delete_row_maint_log parameters not provided."
        final_command = f"generator: delete_row_maint_log={row_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def handle_edit_row_maint_log(self, maint_log_edit_json_params):
        # Constructs and sends the 'edit_row_maint_log' command.
        # maint_log_edit_json_params is a JSON string.
        if not maint_log_edit_json_params:
            return "Error: edit_row_maint_log parameters not provided."
        final_command = f"generator: edit_row_maint_log={maint_log_edit_json_params}"
        response = self.client_interface.ProcessMonitorCommand(final_command)
        return response.replace("EndOfMessage", "").strip()

    def get_monitor_text_data(self):
        # Fetches data for the 'monitor' command.
        raw_text_data = self.client_interface.ProcessMonitorCommand("generator: monitor")
        processed_text = raw_text_data.replace("EndOfMessage", "").strip()
        return {"title": "System Monitor", "data_content": processed_text}

    def get_outage_text_data(self):
        # Fetches data for the 'outage' command.
        raw_text_data = self.client_interface.ProcessMonitorCommand("generator: outage")
        processed_text = raw_text_data.replace("EndOfMessage", "").strip()
        return {"title": "Outage Information", "data_content": processed_text}

    def get_help_text_data(self):
        # Fetches data for the 'help' command.
        raw_text_data = self.client_interface.ProcessMonitorCommand("generator: help")
        processed_text = raw_text_data.replace("EndOfMessage", "").strip()
        return {"title": "Help Information", "data_content": processed_text}
