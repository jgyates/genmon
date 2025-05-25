import unittest
from unittest.mock import Mock
import json
import datetime

# Assuming genmonlib is in thePYTHONPATH or discoverable
# For local testing, you might need to adjust sys.path
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from genmonlib.presentation import UIPresenter
from genmonlib.myclient import ClientInterface # Needed for type hinting if used, and for mock target if specific

class TestUIPresenter(unittest.TestCase):

    def setUp(self):
        # Create a mock ClientInterface instance
        # We mock the class ClientInterface itself, then its instance methods.
        # Or, if ClientInterface is simple and we only mock ProcessMonitorCommand,
        # we can create a more generic Mock object.
        self.mock_client_interface = Mock(spec=ClientInterface)
        # Default return value for ProcessMonitorCommand if not overridden by a specific test
        self.mock_client_interface.ProcessMonitorCommand.return_value = "Default mock responseEndOfMessage"

    def test_get_index_page_data(self):
        presenter = UIPresenter(self.mock_client_interface)
        data = presenter.get_index_page_data()
        self.assertEqual(data["title"], "Genmon Home")
        self.assertIn("greeting", data)
        # We can also check if the correct command was sent if get_index_page_data made a client call
        # For now, assuming it's mostly static data or data derived without client calls.
        # If it does make calls, e.g. to get site name:
        # self.mock_client_interface.ProcessMonitorCommand.assert_any_call("generator: getsitename")

    def test_get_status_json_success(self):
        mock_raw_data = {"raw_status": "ok", "details": "all systems nominal"}
        # Simulate ProcessMonitorCommand returning a JSON string
        self.mock_client_interface.ProcessMonitorCommand.return_value = json.dumps(mock_raw_data)
        
        presenter = UIPresenter(self.mock_client_interface)
        data = presenter.get_status_json() # This calls _process_status_data internally
        
        self.mock_client_interface.ProcessMonitorCommand.assert_called_with("generator: status_json")
        self.assertEqual(data["processed_content"], mock_raw_data)
        self.assertIn("timestamp", data)
        # Ensure timestamp is a recent datetime object (or string representation)
        self.assertTrue(isinstance(data["timestamp"], str)) # Assuming ISO format string

    def test_get_status_json_decode_error(self):
        self.mock_client_interface.ProcessMonitorCommand.return_value = "not a valid json string"
        presenter = UIPresenter(self.mock_client_interface)
        data = presenter.get_status_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"], "Failed to decode status data")

    def test_get_status_text_data(self):
        mock_response = "Generator Status: Running\nVoltage: 240V\nEndOfMessage"
        self.mock_client_interface.ProcessMonitorCommand.return_value = mock_response
        
        presenter = UIPresenter(self.mock_client_interface)
        data = presenter.get_status_text_data()
        
        self.mock_client_interface.ProcessMonitorCommand.assert_called_with("generator: status")
        self.assertEqual(data["title"], "Generator Status")
        self.assertEqual(data["data_content"], "Generator Status: Running\nVoltage: 240V")

    def test_handle_set_exercise(self):
        params = "Monday,14:00,Weekly"
        mock_response = "OKEndOfMessage"
        self.mock_client_interface.ProcessMonitorCommand.return_value = mock_response
        
        presenter = UIPresenter(self.mock_client_interface)
        response = presenter.handle_set_exercise(params)
        
        self.mock_client_interface.ProcessMonitorCommand.assert_called_with(f"generator: setexercise={params}")
        self.assertEqual(response, "OK")

    def test_handle_set_exercise_no_params_none(self):
        presenter = UIPresenter(self.mock_client_interface)
        response = presenter.handle_set_exercise(None)
        self.assertEqual(response, "Error: setexercise parameters not provided.")
        self.mock_client_interface.ProcessMonitorCommand.assert_not_called()

    def test_handle_set_exercise_no_params_empty_string(self):
        presenter = UIPresenter(self.mock_client_interface)
        response = presenter.handle_set_exercise("") 
        self.assertEqual(response, "Error: setexercise parameters not provided.")
        self.mock_client_interface.ProcessMonitorCommand.assert_not_called()

if __name__ == '__main__':
    unittest.main()
