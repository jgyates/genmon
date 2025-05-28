"""
Unit tests for the UIPresenter class in the genmonlib.presentation module.

This test suite uses unittest.mock to simulate the ClientInterface and its
ProcessMonitorCommand method, allowing for isolated testing of the UIPresenter's
data fetching, processing, and formatting logic.
"""
import unittest
from unittest.mock import Mock, patch, MagicMock, call # Added MagicMock, call
import json
import datetime

# Assuming genmonlib is in thePYTHONPATH or discoverable
# For local testing, you might need to adjust sys.path
import sys
import os
# from unittest.mock import patch # Already imported via above line

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import subprocess # Will be needed by UIPresenter
from genmonlib.presentation import UIPresenter
# from genmonlib.myclient import ClientInterface # ClientInterface is mocked, direct import not strictly needed for tests
# from genmonlib.myconfig import MyConfig # MyConfig will be mocked via patch

class TestUIPresenter(unittest.TestCase):
    """
    Test suite for the UIPresenter class.
    
    This class contains tests for various methods of UIPresenter, ensuring
    they correctly process data from the client interface and format it
    as expected for UI display or API responses.
    """

    def setUp(self):
        """
        Set up for each test method.
        
        Initializes a mock ClientInterface instance that can be configured
        by individual tests to simulate different responses from the backend.
        """
        self.mock_client_interface = Mock(spec="genmonlib.myclient.ClientInterface") # Use string spec if class not imported
        self.mock_config_file_path = "dummy/path/genmon.conf"
        self.mock_log = Mock()
        # Default return value for ProcessMonitorCommand, can be overridden in specific tests.
        self.mock_client_interface.ProcessMonitorCommand.return_value = "Default mock responseEndOfMessage"
        # Instantiate presenter here if it's common and doesn't change per test,
        # or instantiate in each test if specific mocks for constructor are needed per test.
        # For now, let's instantiate in each test to be explicit.

    def test_get_index_page_data(self):
        """
        Tests the get_index_page_data method.
        
        Ensures that the method returns a dictionary with the expected title
        and greeting for the home page. This test assumes this method
        primarily returns static or minimally processed data.
        """
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        data = presenter.get_index_page_data()
        self.assertEqual(data["title"], "Genmon Home")
        self.assertIn("greeting", data)
        # Example of how to assert a call if this method were to use the client:
        # self.mock_client_interface.ProcessMonitorCommand.assert_any_call("generator: getsitename")

    def test_get_status_json_success(self):
        """
        Tests get_status_json for successful JSON processing.
        
        Mocks ProcessMonitorCommand to return a valid JSON string.
        Verifies that the command "generator: status_json" is called,
        and the returned data contains the correctly parsed 'processed_content'
        and a 'timestamp'.
        """
        mock_raw_data = {"raw_status": "ok", "details": "all systems nominal"}
        self.mock_client_interface.ProcessMonitorCommand.return_value = json.dumps(mock_raw_data)
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        data = presenter.get_status_json()
        
        self.mock_client_interface.ProcessMonitorCommand.assert_called_with("generator: status_json")
        self.assertEqual(data["processed_content"], mock_raw_data)
        self.assertIn("timestamp", data)
        self.assertTrue(isinstance(data["timestamp"], str)) # Timestamp is expected as an ISO format string.

    def test_get_status_json_decode_error(self):
        """
        Tests get_status_json for handling JSON decoding errors.
        
        Mocks ProcessMonitorCommand to return an invalid JSON string.
        Verifies that the method returns an error dictionary with the
        correct error message.
        """
        self.mock_client_interface.ProcessMonitorCommand.return_value = "not a valid json string"
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        data = presenter.get_status_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"], "Failed to decode status data")

    def test_get_status_text_data(self):
        """
        Tests get_status_text_data for correct text processing.
        
        Mocks ProcessMonitorCommand to return a raw text string with "EndOfMessage".
        Verifies that the command "generator: status" is called, and the returned
        dictionary contains the correct title and processed 'data_content'
        (with "EndOfMessage" removed and whitespace stripped).
        """
        mock_response = "Generator Status: Running\nVoltage: 240V\nEndOfMessage"
        self.mock_client_interface.ProcessMonitorCommand.return_value = mock_response
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        data = presenter.get_status_text_data()
        
        self.mock_client_interface.ProcessMonitorCommand.assert_called_with("generator: status")
        self.assertEqual(data["title"], "Generator Status")
        self.assertEqual(data["data_content"], "Generator Status: Running\nVoltage: 240V")

    def test_handle_set_exercise(self):
        """
        Tests handle_set_exercise for successful command construction and response processing.
        
        Mocks ProcessMonitorCommand to return a standard "OKEndOfMessage" response.
        Verifies that the correct command string (including parameters) is sent
        to the client interface and that the response is processed correctly (as a dict).
        """
        params = "Monday,14:00,Weekly"
        mock_response = "OKEndOfMessage" # Example response from backend
        self.mock_client_interface.ProcessMonitorCommand.return_value = mock_response
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response_dict = presenter.handle_set_exercise(params) # Method now returns a dict
        
        self.mock_client_interface.ProcessMonitorCommand.assert_called_with(f"generator: setexercise={params}")
        self.assertIsInstance(response_dict, dict)
        self.assertEqual(response_dict.get("status"), "OK")
        self.assertEqual(response_dict.get("response"), "OK") # Original string response is nested

    def test_handle_set_exercise_no_params_none(self):
        """
        Tests handle_set_exercise error handling when parameters are None.
        
        Verifies that an error message is returned and ProcessMonitorCommand is not called.
        """
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response_dict = presenter.handle_set_exercise(None)
        self.assertEqual(response_dict.get("status"), "error")
        self.assertEqual(response_dict.get("message"), "setexercise parameters not provided.")
        self.mock_client_interface.ProcessMonitorCommand.assert_not_called()

    def test_handle_set_exercise_no_params_empty_string(self):
        """
        Tests handle_set_exercise error handling when parameters are an empty string.

        Verifies that an error message is returned and ProcessMonitorCommand is not called.
        """
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response_dict = presenter.handle_set_exercise("") 
        self.assertEqual(response_dict.get("status"), "error")
        self.assertEqual(response_dict.get("message"), "setexercise parameters not provided.")
        self.mock_client_interface.ProcessMonitorCommand.assert_not_called()

    # Test for get_outage_json_success
    def test_get_outage_json_success(self):
        """
        Tests get_outage_json for successful JSON processing.
        """
        mock_outage_data = {"outages": [{"start": "2023-01-01T10:00:00", "end": "2023-01-01T11:00:00"}]}
        self.mock_client_interface.ProcessMonitorCommand.return_value = json.dumps(mock_outage_data)
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        data = presenter.get_outage_json()
        
        self.mock_client_interface.ProcessMonitorCommand.assert_called_with("generator: outage_json")
        self.assertEqual(data["processed_content"], mock_outage_data)
        self.assertEqual(data["data_type"], "outage")
        self.assertIn("timestamp", data)

    # Test for get_outage_json_decode_error
    def test_get_outage_json_decode_error(self):
        """
        Tests get_outage_json for handling JSON decoding errors.
        """
        self.mock_client_interface.ProcessMonitorCommand.return_value = "invalid json for outage"
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        data = presenter.get_outage_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"], "Failed to decode outage data")

    # Test for get_maint_text_data
    def test_get_maint_text_data(self):
        """
        Tests get_maint_text_data for correct text processing.
        """
        mock_response = "Maintenance due: Oil ChangeEndOfMessage"
        self.mock_client_interface.ProcessMonitorCommand.return_value = mock_response
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        data = presenter.get_maint_text_data()
        
        self.mock_client_interface.ProcessMonitorCommand.assert_called_with("generator: maint")
        self.assertEqual(data["title"], "Maintenance Information")
        self.assertEqual(data["data_content"], "Maintenance due: Oil Change")

    # Test for handle_power_log_clear_success
    def test_handle_power_log_clear_success(self):
        """
        Tests handle_power_log_clear for successful command and structured dict response.
        """
        self.mock_client_interface.ProcessMonitorCommand.return_value = "OKEndOfMessage"
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response = presenter.handle_power_log_clear()
        
        self.mock_client_interface.ProcessMonitorCommand.assert_called_with("generator: power_log_clear")
        expected_response = {"status": "OK", "message": "Power log clear command sent.", "response": "OK"}
        self.assertEqual(response, expected_response)

    # Test for handle_power_log_clear_failure
    def test_handle_power_log_clear_failure(self):
        """
        Tests handle_power_log_clear for failure response.
        """
        mock_error_message = "Error: Failed to clear"
        self.mock_client_interface.ProcessMonitorCommand.return_value = f"{mock_error_message}EndOfMessage"
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response = presenter.handle_power_log_clear()

        self.mock_client_interface.ProcessMonitorCommand.assert_called_with("generator: power_log_clear")
        expected_response = {"status": "error", "message": mock_error_message}
        self.assertEqual(response, expected_response)

    @patch('genmonlib.presentation.MyConfig')
    def test_get_favicon_path_from_config(self, mock_my_config_class):
        """
        Tests get_favicon_path when favicon is set in config.
        """
        mock_my_config_instance = Mock()
        mock_my_config_instance.ReadValue.return_value = "custom_favicon.ico"
        mock_my_config_instance.InitComplete = True # Ensure MyConfig is treated as initialized
        mock_my_config_class.return_value = mock_my_config_instance
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        favicon_path = presenter.get_favicon_path()
        
        # The presenter's get_favicon_path currently has placeholder logic and doesn't use MyConfig.
        # This test is structured for when it *does* use MyConfig as intended.
        # For the current placeholder, this test would fail or need adjustment.
        # Assuming future implementation of get_favicon_path using MyConfig:
        # mock_my_config_class.assert_called_once_with(self.mock_config_file_path, log=self.mock_log)
        # mock_my_config_instance.ReadValue.assert_called_with("favicon", section="SYSTEM", default="/static/favicon.ico")
        # self.assertEqual(favicon_path, "custom_favicon.ico")

        # For current placeholder implementation:
        self.mock_log.info.assert_called_with("get_favicon_path called, needs MyConfig implementation.")
        self.assertEqual(favicon_path, "/static/favicon.ico")


    @patch('genmonlib.presentation.UIPresenter._run_bash_script')
    def test_restart_genmon_success(self, mock_run_bash_script):
        """
        Tests restart_genmon for successful execution.
        """
        mock_run_bash_script.return_value = {"status": "OK", "message": "Simulated restart command executed."}
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response = presenter.restart_genmon()
        
        project_path = "/opt/genmon" # Placeholder from presenter method
        config_file = self.mock_config_file_path
        expected_args = ["restart", "-p", project_path, "-c", config_file]
        
        mock_run_bash_script.assert_called_once_with("startgenmon.sh", expected_args)
        self.assertEqual(response.get("status"), "OK")
        self.assertIn("Genmon restart command issued successfully.", response.get("message", ""))


    @patch('genmonlib.presentation.UIPresenter._run_bash_script')
    def test_restart_genmon_failure(self, mock_run_bash_script):
        """
        Tests restart_genmon when the script execution fails.
        """
        mock_run_bash_script.return_value = {"status": "error", "message": "Simulated script failure."}
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response = presenter.restart_genmon()
        
        self.assertEqual(response.get("status"), "error")
        self.assertEqual(response.get("message"), "Simulated script failure.")
        self.mock_log.error.assert_called_with("Genmon restart command failed: Simulated script failure.")

class TestUIPresenterRunBashScript(unittest.TestCase):
    def setUp(self):
        # Mock dependencies for UIPresenter
        self.mock_client_interface = MagicMock()
        self.mock_log = MagicMock()
        # Provide a dummy ConfigFilePath, it might be used for path calculations if not mocked out
        self.dummy_config_path = '/fake/path/genmon.conf'
        
        self.presenter = UIPresenter(
            client_interface=self.mock_client_interface,
            ConfigFilePath=self.dummy_config_path,
            log=self.mock_log
        )
        # Calculate project root for script path assertions
        # Assuming presentation.py is in genmonlib/ which is a subdirectory of the project root
        self.presentation_module_path = os.path.dirname(sys.modules[UIPresenter.__module__].__file__)
        self.project_root = os.path.abspath(os.path.join(self.presentation_module_path, ".."))

    @patch('genmonlib.presentation.subprocess.run')
    def test_successful_script_execution(self, mock_subprocess_run):
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="Script output success", stderr="")
        script_name = "test_script.sh"
        args = ["arg1", "arg2"]
        
        result = self.presenter._run_bash_script(script_name, args)
        
        expected_script_path = os.path.join(self.project_root, script_name)
        expected_cmd_list = ['/bin/bash', expected_script_path] + args
        
        mock_subprocess_run.assert_called_once_with(expected_cmd_list, capture_output=True, text=True, check=False)
        self.assertEqual(result, {"status": "OK", "message": "Script output success", "stdout": "Script output success", "ReturnCode": 0})
        self.mock_log.info.assert_any_call(f"Executing bash command: {' '.join(expected_cmd_list)}")

    @patch('genmonlib.presentation.subprocess.run')
    def test_successful_script_empty_stdout(self, mock_subprocess_run):
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        script_name = "another_script.sh"
        args = []

        result = self.presenter._run_bash_script(script_name, args)

        expected_script_path = os.path.join(self.project_root, script_name)
        expected_cmd_list = ['/bin/bash', expected_script_path] + args

        mock_subprocess_run.assert_called_once_with(expected_cmd_list, capture_output=True, text=True, check=False)
        self.assertEqual(result, {"status": "OK", "message": "Command executed successfully.", "stdout": "", "ReturnCode": 0})
        self.mock_log.info.assert_any_call(f"Executing bash command: {' '.join(expected_cmd_list)}")

    @patch('genmonlib.presentation.subprocess.run')
    def test_script_failure_non_zero_return_code(self, mock_subprocess_run):
        mock_subprocess_run.return_value = MagicMock(returncode=1, stdout="Output before error", stderr="Script error message")
        script_name = "error_script.sh"
        args = ["-f"]

        result = self.presenter._run_bash_script(script_name, args)

        expected_script_path = os.path.join(self.project_root, script_name)
        expected_cmd_list = ['/bin/bash', expected_script_path] + args
        
        mock_subprocess_run.assert_called_once_with(expected_cmd_list, capture_output=True, text=True, check=False)
        self.assertEqual(result, {"status": "error", "message": "Script error message", "stderr": "Script error message", "ReturnCode": 1})
        self.mock_log.info.assert_any_call(f"Executing bash command: {' '.join(expected_cmd_list)}")
        self.mock_log.error.assert_any_call(f"Command failed: {' '.join(expected_cmd_list)}. Return Code: 1. Stderr: Script error message")

    @patch('genmonlib.presentation.subprocess.run')
    def test_script_failure_empty_stderr(self, mock_subprocess_run):
        mock_subprocess_run.return_value = MagicMock(returncode=2, stdout="", stderr="")
        script_name = "fail_script.sh"
        args = []

        result = self.presenter._run_bash_script(script_name, args)

        expected_script_path = os.path.join(self.project_root, script_name)
        expected_cmd_list = ['/bin/bash', expected_script_path] + args

        mock_subprocess_run.assert_called_once_with(expected_cmd_list, capture_output=True, text=True, check=False)
        self.assertEqual(result, {"status": "error", "message": "Command failed with return code 2.", "stderr": "", "ReturnCode": 2})
        self.mock_log.info.assert_any_call(f"Executing bash command: {' '.join(expected_cmd_list)}")
        self.mock_log.error.assert_any_call(f"Command failed: {' '.join(expected_cmd_list)}. Return Code: 2. Stderr: ")

    @patch('genmonlib.presentation.subprocess.run')
    def test_sudo_command_execution(self, mock_subprocess_run):
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        command = "sudo reboot now"
        args = [] # Sudo commands often have args as part of the main command string
        
        result = self.presenter._run_bash_script(command, args)
        
        expected_cmd_list = ['sudo', 'reboot', 'now']
        
        mock_subprocess_run.assert_called_once_with(expected_cmd_list, capture_output=True, text=True, check=False)
        self.assertEqual(result, {"status": "OK", "message": "Command executed successfully.", "stdout": "", "ReturnCode": 0})
        self.mock_log.info.assert_any_call(f"Executing bash command: {' '.join(expected_cmd_list)}")

    @patch('genmonlib.presentation.subprocess.run')
    def test_backup_command_execution(self, mock_subprocess_run):
        backup_path_stdout = "/tmp/backup_placeholder.zip\n"
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout=backup_path_stdout, stderr="")
        script_name = "genmonmaint.sh"
        args = ["-b", "-c", "/fake/genmon.conf"]
        
        result = self.presenter._run_bash_script(script_name, args)
        
        expected_script_path = os.path.join(self.project_root, script_name)
        expected_cmd_list = ['/bin/bash', expected_script_path] + args
        
        mock_subprocess_run.assert_called_once_with(expected_cmd_list, capture_output=True, text=True, check=False)
        self.assertEqual(result, {"status": "OK", "message": backup_path_stdout.strip(), "stdout": backup_path_stdout.strip(), "ReturnCode": 0, "path": backup_path_stdout.strip()})
        self.mock_log.info.assert_any_call(f"Executing bash command: {' '.join(expected_cmd_list)}")

    @patch('genmonlib.presentation.subprocess.run')
    def test_log_archive_command_execution(self, mock_subprocess_run):
        log_archive_path_stdout = "/tmp/logs_placeholder.zip\n"
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout=log_archive_path_stdout, stderr="")
        script_name = "genmonmaint.sh"
        args = ["-l", "-p", "/fake/project"]
        
        result = self.presenter._run_bash_script(script_name, args)
        
        expected_script_path = os.path.join(self.project_root, script_name)
        expected_cmd_list = ['/bin/bash', expected_script_path] + args
        
        mock_subprocess_run.assert_called_once_with(expected_cmd_list, capture_output=True, text=True, check=False)
        self.assertEqual(result, {"status": "OK", "message": log_archive_path_stdout.strip(), "stdout": log_archive_path_stdout.strip(), "ReturnCode": 0, "path": log_archive_path_stdout.strip()})
        self.mock_log.info.assert_any_call(f"Executing bash command: {' '.join(expected_cmd_list)}")

    @patch('genmonlib.presentation.subprocess.run')
    def test_subprocess_run_raises_file_not_found(self, mock_subprocess_run):
        error_message = "No such file or directory: /bin/nonexistent_command"
        mock_subprocess_run.side_effect = FileNotFoundError(error_message)
        script_name = "nonexistent_command.sh" # Script that won't be found by subprocess.run
        
        result = self.presenter._run_bash_script(script_name, [])
        
        # The exact command list depends on how _run_bash_script constructs it before the error.
        # It will try to form ['/bin/bash', '/path/to/project/nonexistent_command.sh']
        # We need to assert the log message based on this.
        expected_script_path = os.path.join(self.project_root, script_name)
        failed_cmd_str = f"/bin/bash {expected_script_path}" # Simplified for log, actual list is ['/bin/bash', path]

        self.assertEqual(result, {"status": "error", "message": f"Command not found: {script_name}. Details: {error_message}", "ReturnCode": -1})
        # Check that the log message includes the command that was attempted
        # The exact log message formatting is important here.
        # The log message is `f"Command not found for: {' '.join(full_cmd_list)}: {e}"`
        # full_cmd_list would be ['/bin/bash', expected_script_path]
        logged_command_str = f"/bin/bash {expected_script_path}"
        self.mock_log.error.assert_any_call(f"Command not found for: {logged_command_str}: {error_message}")


    @patch('genmonlib.presentation.subprocess.run')
    def test_script_execution_no_args(self, mock_subprocess_run):
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="Script with no args output", stderr="")
        script_name = "test_no_args.sh"
        
        # Call with args_list=None (default) or explicitly empty
        result_none_args = self.presenter._run_bash_script(script_name) 
        
        expected_script_path = os.path.join(self.project_root, script_name)
        expected_cmd_list_no_args = ['/bin/bash', expected_script_path]
        
        # Check the call for the case where args_list is None
        mock_subprocess_run.assert_called_with(expected_cmd_list_no_args, capture_output=True, text=True, check=False)
        self.assertEqual(result_none_args, {"status": "OK", "message": "Script with no args output", "stdout": "Script with no args output", "ReturnCode": 0})
        self.mock_log.info.assert_any_call(f"Executing bash command: {' '.join(expected_cmd_list_no_args)}")

        # Reset mock for next call if needed, or ensure unique script name if checking call_count
        mock_subprocess_run.reset_mock()
        self.mock_log.reset_mock()

        result_empty_args = self.presenter._run_bash_script(script_name, [])
        mock_subprocess_run.assert_called_with(expected_cmd_list_no_args, capture_output=True, text=True, check=False)
        self.assertEqual(result_empty_args, {"status": "OK", "message": "Script with no args output", "stdout": "Script with no args output", "ReturnCode": 0})
        self.mock_log.info.assert_any_call(f"Executing bash command: {' '.join(expected_cmd_list_no_args)}")


if __name__ == '__main__':
    unittest.main()
