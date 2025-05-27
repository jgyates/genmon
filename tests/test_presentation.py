"""
Unit tests for the UIPresenter class in the genmonlib.presentation module.

This test suite uses unittest.mock to simulate the ClientInterface and its
ProcessMonitorCommand method, allowing for isolated testing of the UIPresenter's
data fetching, processing, and formatting logic.
"""
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
from genmonlib.myclient import ClientInterface 

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
        self.mock_client_interface = Mock(spec=ClientInterface)
        # Default return value for ProcessMonitorCommand, can be overridden in specific tests.
        self.mock_client_interface.ProcessMonitorCommand.return_value = "Default mock responseEndOfMessage"

    def test_get_index_page_data(self):
        """
        Tests the get_index_page_data method.
        
        Ensures that the method returns a dictionary with the expected title
        and greeting for the home page. This test assumes this method
        primarily returns static or minimally processed data.
        """
        presenter = UIPresenter(self.mock_client_interface)
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
        
        presenter = UIPresenter(self.mock_client_interface)
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
        presenter = UIPresenter(self.mock_client_interface)
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
        
        presenter = UIPresenter(self.mock_client_interface)
        data = presenter.get_status_text_data()
        
        self.mock_client_interface.ProcessMonitorCommand.assert_called_with("generator: status")
        self.assertEqual(data["title"], "Generator Status")
        self.assertEqual(data["data_content"], "Generator Status: Running\nVoltage: 240V")

    def test_handle_set_exercise(self):
        """
        Tests handle_set_exercise for successful command construction and response processing.
        
        Mocks ProcessMonitorCommand to return a standard "OKEndOfMessage" response.
        Verifies that the correct command string (including parameters) is sent
        to the client interface and that the response is processed correctly ("OK").
        """
        params = "Monday,14:00,Weekly"
        mock_response = "OKEndOfMessage"
        self.mock_client_interface.ProcessMonitorCommand.return_value = mock_response
        
        presenter = UIPresenter(self.mock_client_interface)
        response = presenter.handle_set_exercise(params)
        
        self.mock_client_interface.ProcessMonitorCommand.assert_called_with(f"generator: setexercise={params}")
        self.assertEqual(response, "OK")

    def test_handle_set_exercise_no_params_none(self):
        """
        Tests handle_set_exercise error handling when parameters are None.
        
        Verifies that an error message is returned and ProcessMonitorCommand is not called.
        """
        presenter = UIPresenter(self.mock_client_interface)
        response = presenter.handle_set_exercise(None)
        self.assertEqual(response, "Error: setexercise parameters not provided.")
        self.mock_client_interface.ProcessMonitorCommand.assert_not_called()

    def test_handle_set_exercise_no_params_empty_string(self):
        """
        Tests handle_set_exercise error handling when parameters are an empty string.

        Verifies that an error message is returned and ProcessMonitorCommand is not called.
        """
        presenter = UIPresenter(self.mock_client_interface)
        response = presenter.handle_set_exercise("") 
        self.assertEqual(response, "Error: setexercise parameters not provided.")
        self.mock_client_interface.ProcessMonitorCommand.assert_not_called()

if __name__ == '__main__':
    unittest.main()
