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

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# import subprocess # No longer directly needed in this file after moving TestUIPresenterRunBashScript
from genmonlib.presentation import UIPresenter
# from genmonlib.myclient import ClientInterface # ClientInterface is mocked, direct import not strictly needed for tests
# from genmonlib.myconfig import MyConfig # MyConfig will be mocked via patch
# from genmonlib.mysupport import MySupport # MySupport will be mocked via patch

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
        # self.mock_log.info.assert_called_with("get_favicon_path called, needs MyConfig implementation.")
        # self.assertEqual(favicon_path, "/static/favicon.ico")
        # With actual implementation:
        mock_my_config_class.assert_called_once_with(self.mock_config_file_path, log=self.mock_log)
        mock_my_config_instance.ReadValue.assert_called_with("favicon", section="SYSTEM", default="/static/favicon.ico")
        self.assertEqual(favicon_path, "custom_favicon.ico")


    @patch('genmonlib.presentation.MySupport') # Patch MySupport where it's imported in presentation.py
    def test_restart_genmon_success(self, MockMySupport):
        """
        Tests restart_genmon for successful execution.
        """
        mock_support_instance = MockMySupport.return_value # This is the mock instance UIPresenter will create
        mock_support_instance.run_bash_script.return_value = {"status": "OK", "message": "Simulated restart command executed."}
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response = presenter.restart_genmon()
        
        # project_path = "/opt/genmon" # This was a placeholder in the old _run_bash_script.
                                      # The new run_bash_script in MySupport calculates project_root internally.
                                      # The arguments passed from presenter are now simpler.
        config_file = self.mock_config_file_path
        expected_args = ["restart", "-c", config_file] # Updated expected args
        
        mock_support_instance.run_bash_script.assert_called_once_with("startgenmon.sh", expected_args, log=self.mock_log)
        self.assertEqual(response.get("status"), "OK")
        # The message "Genmon restart command issued successfully." comes from presenter, not the script output directly.
        self.assertEqual(response.get("message"), "Simulated restart command executed.") # This should be the direct message from run_bash_script


    @patch('genmonlib.presentation.MySupport')
    def test_restart_genmon_failure(self, MockMySupport):
        """
        Tests restart_genmon when the script execution fails.
        """
        mock_support_instance = MockMySupport.return_value
        mock_support_instance.run_bash_script.return_value = {"status": "error", "message": "Simulated script failure."}
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response = presenter.restart_genmon()
        
        self.assertEqual(response.get("status"), "error")
        self.assertEqual(response.get("message"), "Simulated script failure.")
        self.mock_log.error.assert_called_with("Genmon restart command failed: Simulated script failure.")

    @patch('genmonlib.presentation.MySupport')
    def test_update_software_success(self, MockMySupport):
        mock_support_instance = MockMySupport.return_value
        mock_support_instance.run_bash_script.return_value = {"status": "OK", "message": "Update script completed."}
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response = presenter.update_software()
        
        expected_args = ["-u", "-n"]
        mock_support_instance.run_bash_script.assert_called_once_with("genmonmaint.sh", expected_args, log=self.mock_log)
        self.assertEqual(response.get("status"), "OK")
        # This message comes from the presenter method itself after a successful script run
        self.assertEqual(response.get("message"), "Software update process initiated. Genmon should restart if update was successful.")

    @patch('genmonlib.presentation.MySupport')
    def test_update_software_failure(self, MockMySupport):
        mock_support_instance = MockMySupport.return_value
        mock_support_instance.run_bash_script.return_value = {"status": "error", "message": "Update script failed."}
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response = presenter.update_software()
        
        expected_args = ["-u", "-n"]
        mock_support_instance.run_bash_script.assert_called_once_with("genmonmaint.sh", expected_args, log=self.mock_log)
        self.assertEqual(response.get("status"), "error")
        self.assertEqual(response.get("message"), "Update script failed.")
        self.mock_log.error.assert_called_with("Software update script failed: Update script failed.")

    @patch('genmonlib.presentation.MySupport')
    def test_reboot_system_success(self, MockMySupport):
        mock_support_instance = MockMySupport.return_value
        mock_support_instance.run_bash_script.return_value = {"status": "OK", "message": "Reboot command sent."}
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response = presenter.reboot_system()
        
        mock_support_instance.run_bash_script.assert_called_once_with("sudo reboot now", log=self.mock_log)
        self.assertEqual(response.get("status"), "OK")
        self.assertEqual(response.get("message"), "Reboot command sent.")

    @patch('genmonlib.presentation.MySupport')
    def test_reboot_system_failure(self, MockMySupport): # Assuming run_bash_script can return failure for sudo commands too
        mock_support_instance = MockMySupport.return_value
        mock_support_instance.run_bash_script.return_value = {"status": "error", "message": "Reboot failed."}
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response = presenter.reboot_system()
        
        mock_support_instance.run_bash_script.assert_called_once_with("sudo reboot now", log=self.mock_log)
        self.assertEqual(response.get("status"), "error")
        self.assertEqual(response.get("message"), "Reboot failed.")

    @patch('genmonlib.presentation.MySupport')
    def test_shutdown_system_success(self, MockMySupport):
        mock_support_instance = MockMySupport.return_value
        mock_support_instance.run_bash_script.return_value = {"status": "OK", "message": "Shutdown command sent."}
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response = presenter.shutdown_system()
        
        mock_support_instance.run_bash_script.assert_called_once_with("sudo shutdown -h now", log=self.mock_log)
        self.assertEqual(response.get("status"), "OK")
        self.assertEqual(response.get("message"), "Shutdown command sent.")

    @patch('genmonlib.presentation.MySupport')
    def test_shutdown_system_failure(self, MockMySupport):
        mock_support_instance = MockMySupport.return_value
        mock_support_instance.run_bash_script.return_value = {"status": "error", "message": "Shutdown failed."}
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response = presenter.shutdown_system()
        
        mock_support_instance.run_bash_script.assert_called_once_with("sudo shutdown -h now", log=self.mock_log)
        self.assertEqual(response.get("status"), "error")
        self.assertEqual(response.get("message"), "Shutdown failed.")

    @patch('genmonlib.presentation.MySupport')
    def test_backup_configuration_success(self, MockMySupport):
        mock_support_instance = MockMySupport.return_value
        backup_path = "/tmp/backup.zip"
        mock_support_instance.run_bash_script.return_value = {"status": "OK", "message": f"Backup created at {backup_path}", "path": backup_path, "stdout": backup_path}
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response = presenter.backup_configuration()
        
        expected_args = ["-b", "-c", self.mock_config_file_path]
        mock_support_instance.run_bash_script.assert_called_once_with("genmonmaint.sh", expected_args, log=self.mock_log)
        self.assertEqual(response.get("status"), "OK")
        self.assertEqual(response.get("path"), backup_path)
        self.mock_log.info.assert_called_with(f"Configuration backup successful. Path: {backup_path}")

    @patch('genmonlib.presentation.MySupport')
    def test_backup_configuration_script_ok_no_path(self, MockMySupport):
        mock_support_instance = MockMySupport.return_value
        # Simulate script success but stdout didn't contain a path as expected by run_bash_script's specific logic for -b
        mock_support_instance.run_bash_script.return_value = {"status": "OK", "message": "Script ran.", "stdout": "Script ran."} 
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response = presenter.backup_configuration()
        
        expected_args = ["-b", "-c", self.mock_config_file_path]
        mock_support_instance.run_bash_script.assert_called_once_with("genmonmaint.sh", expected_args, log=self.mock_log)
        self.assertEqual(response.get("status"), "error") # Presenter should treat this as an error
        self.assertEqual(response.get("message"), "Backup script ran but did not return a path.")
        self.mock_log.warning.assert_called_with("Configuration backup script ran, but no path was returned in stdout. Output: Script ran.")

    @patch('genmonlib.presentation.MySupport')
    def test_backup_configuration_failure(self, MockMySupport):
        mock_support_instance = MockMySupport.return_value
        mock_support_instance.run_bash_script.return_value = {"status": "error", "message": "Backup script failed."}
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response = presenter.backup_configuration()
        
        expected_args = ["-b", "-c", self.mock_config_file_path]
        mock_support_instance.run_bash_script.assert_called_once_with("genmonmaint.sh", expected_args, log=self.mock_log)
        self.assertEqual(response.get("status"), "error")
        self.assertEqual(response.get("message"), "Backup script failed.")
        self.mock_log.error.assert_called_with("Configuration backup failed: Backup script failed.")

    @patch('genmonlib.presentation.MySupport')
    def test_get_log_archive_success(self, MockMySupport):
        mock_support_instance = MockMySupport.return_value
        archive_path = "/tmp/logs.zip"
        mock_support_instance.run_bash_script.return_value = {"status": "OK", "message": f"Archive created at {archive_path}", "path": archive_path, "stdout": archive_path}
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response = presenter.get_log_archive()
        
        expected_args = ["-l"]
        mock_support_instance.run_bash_script.assert_called_once_with("genmonmaint.sh", expected_args, log=self.mock_log)
        self.assertEqual(response.get("status"), "OK")
        self.assertEqual(response.get("path"), archive_path)
        self.mock_log.info.assert_called_with(f"Log archive creation successful. Path: {archive_path}")

    @patch('genmonlib.presentation.MySupport')
    def test_get_log_archive_script_ok_no_path(self, MockMySupport):
        mock_support_instance = MockMySupport.return_value
        mock_support_instance.run_bash_script.return_value = {"status": "OK", "message": "Archive script ran.", "stdout": "Archive script ran."}
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response = presenter.get_log_archive()
        
        expected_args = ["-l"]
        mock_support_instance.run_bash_script.assert_called_once_with("genmonmaint.sh", expected_args, log=self.mock_log)
        self.assertEqual(response.get("status"), "error")
        self.assertEqual(response.get("message"), "Log archive script ran but did not return a path.")
        self.mock_log.warning.assert_called_with("Log archive script ran, but no path was returned in stdout. Output: Archive script ran.")

    @patch('genmonlib.presentation.MySupport')
    def test_get_log_archive_failure(self, MockMySupport):
        mock_support_instance = MockMySupport.return_value
        mock_support_instance.run_bash_script.return_value = {"status": "error", "message": "Archive script failed."}
        
        presenter = UIPresenter(self.mock_client_interface, self.mock_config_file_path, self.mock_log)
        response = presenter.get_log_archive()
        
        expected_args = ["-l"]
        mock_support_instance.run_bash_script.assert_called_once_with("genmonmaint.sh", expected_args, log=self.mock_log)
        self.assertEqual(response.get("status"), "error")
        self.assertEqual(response.get("message"), "Archive script failed.")
        self.mock_log.error.assert_called_with("Log archive creation failed: Archive script failed.")

# TestUIPresenterRunBashScript class removed from here

if __name__ == '__main__':
    unittest.main()
