import unittest
from unittest.mock import Mock, patch, MagicMock, call
import os
import sys
import subprocess # Needed for comparison with actual subprocess calls

# Add project root to sys.path to allow importing genmonlib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from genmonlib.mysupport import MySupport

class TestMySupportRunBashScript(unittest.TestCase):
    def setUp(self):
        self.mock_log = MagicMock()
        self.support = MySupport() # MySupport's __init__ doesn't require log, but it has self.log
        self.support.log = self.mock_log # Assign the mock log to the instance

        # Calculate project root for script path assertions
        # This test file is in tests/, mysupport.py is in genmonlib/
        # run_bash_script calculates project_root relative to mysupport.py
        # So, this self.project_root is for verifying the *expected* paths
        # that run_bash_script should construct.
        # The project root is one level up from the 'tests' directory.
        self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    @patch('genmonlib.mysupport.subprocess.run')
    def test_successful_script_execution(self, mock_subprocess_run):
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="Script output success", stderr="")
        script_name = "test_script.sh"
        args = ["arg1", "arg2"]
        
        result = self.support.run_bash_script(script_name, args, log=self.mock_log)
        
        expected_script_path = os.path.join(self.project_root, script_name)
        expected_cmd_list = ['/bin/bash', expected_script_path] + args
        
        mock_subprocess_run.assert_called_once_with(expected_cmd_list, capture_output=True, text=True, check=False)
        self.assertEqual(result, {"status": "OK", "message": "Script output success", "stdout": "Script output success", "ReturnCode": 0})
        self.mock_log.info.assert_any_call(f"Executing bash command: {' '.join(expected_cmd_list)}")

    @patch('genmonlib.mysupport.subprocess.run')
    def test_successful_script_empty_stdout(self, mock_subprocess_run):
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        script_name = "another_script.sh"
        args = []

        result = self.support.run_bash_script(script_name, args, log=self.mock_log)

        expected_script_path = os.path.join(self.project_root, script_name)
        expected_cmd_list = ['/bin/bash', expected_script_path] + args

        mock_subprocess_run.assert_called_once_with(expected_cmd_list, capture_output=True, text=True, check=False)
        self.assertEqual(result, {"status": "OK", "message": "Command executed successfully.", "stdout": "", "ReturnCode": 0})
        self.mock_log.info.assert_any_call(f"Executing bash command: {' '.join(expected_cmd_list)}")

    @patch('genmonlib.mysupport.subprocess.run')
    def test_script_failure_non_zero_return_code(self, mock_subprocess_run):
        mock_subprocess_run.return_value = MagicMock(returncode=1, stdout="Output before error", stderr="Script error message")
        script_name = "error_script.sh"
        args = ["-f"]

        result = self.support.run_bash_script(script_name, args, log=self.mock_log)

        expected_script_path = os.path.join(self.project_root, script_name)
        expected_cmd_list = ['/bin/bash', expected_script_path] + args
        
        mock_subprocess_run.assert_called_once_with(expected_cmd_list, capture_output=True, text=True, check=False)
        self.assertEqual(result, {"status": "error", "message": "Script error message", "stderr": "Script error message", "ReturnCode": 1})
        self.mock_log.info.assert_any_call(f"Executing bash command: {' '.join(expected_cmd_list)}")
        self.mock_log.error.assert_any_call(f"Command failed: {' '.join(expected_cmd_list)}. Return Code: 1. Stderr: Script error message")

    @patch('genmonlib.mysupport.subprocess.run')
    def test_script_failure_empty_stderr(self, mock_subprocess_run):
        mock_subprocess_run.return_value = MagicMock(returncode=2, stdout="", stderr="")
        script_name = "fail_script.sh"
        args = []

        result = self.support.run_bash_script(script_name, args, log=self.mock_log)

        expected_script_path = os.path.join(self.project_root, script_name)
        expected_cmd_list = ['/bin/bash', expected_script_path] + args

        mock_subprocess_run.assert_called_once_with(expected_cmd_list, capture_output=True, text=True, check=False)
        self.assertEqual(result, {"status": "error", "message": "Command failed with return code 2.", "stderr": "", "ReturnCode": 2})
        self.mock_log.info.assert_any_call(f"Executing bash command: {' '.join(expected_cmd_list)}")
        self.mock_log.error.assert_any_call(f"Command failed: {' '.join(expected_cmd_list)}. Return Code: 2. Stderr: ")

    @patch('genmonlib.mysupport.subprocess.run')
    def test_sudo_command_execution(self, mock_subprocess_run):
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        command = "sudo reboot now"
        args = [] # Sudo commands often have args as part of the main command string
        
        result = self.support.run_bash_script(command, args, log=self.mock_log)
        
        expected_cmd_list = ['sudo', 'reboot', 'now']
        
        mock_subprocess_run.assert_called_once_with(expected_cmd_list, capture_output=True, text=True, check=False)
        self.assertEqual(result, {"status": "OK", "message": "Command executed successfully.", "stdout": "", "ReturnCode": 0})
        self.mock_log.info.assert_any_call(f"Executing bash command: {' '.join(expected_cmd_list)}")

    @patch('genmonlib.mysupport.subprocess.run')
    def test_backup_command_execution(self, mock_subprocess_run):
        backup_path_stdout = "/tmp/backup_placeholder.zip\n"
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout=backup_path_stdout, stderr="")
        script_name = "genmonmaint.sh"
        args = ["-b", "-c", "/fake/genmon.conf"]
        
        result = self.support.run_bash_script(script_name, args, log=self.mock_log)
        
        expected_script_path = os.path.join(self.project_root, script_name)
        expected_cmd_list = ['/bin/bash', expected_script_path] + args
        
        mock_subprocess_run.assert_called_once_with(expected_cmd_list, capture_output=True, text=True, check=False)
        self.assertEqual(result, {"status": "OK", "message": backup_path_stdout.strip(), "stdout": backup_path_stdout.strip(), "ReturnCode": 0, "path": backup_path_stdout.strip()})
        self.mock_log.info.assert_any_call(f"Executing bash command: {' '.join(expected_cmd_list)}")

    @patch('genmonlib.mysupport.subprocess.run')
    def test_log_archive_command_execution(self, mock_subprocess_run):
        log_archive_path_stdout = "/tmp/logs_placeholder.zip\n"
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout=log_archive_path_stdout, stderr="")
        script_name = "genmonmaint.sh"
        args = ["-l", "-p", "/fake/project"] # Example args
        
        result = self.support.run_bash_script(script_name, args, log=self.mock_log)
        
        expected_script_path = os.path.join(self.project_root, script_name)
        expected_cmd_list = ['/bin/bash', expected_script_path] + args
        
        mock_subprocess_run.assert_called_once_with(expected_cmd_list, capture_output=True, text=True, check=False)
        self.assertEqual(result, {"status": "OK", "message": log_archive_path_stdout.strip(), "stdout": log_archive_path_stdout.strip(), "ReturnCode": 0, "path": log_archive_path_stdout.strip()})
        self.mock_log.info.assert_any_call(f"Executing bash command: {' '.join(expected_cmd_list)}")

    @patch('genmonlib.mysupport.subprocess.run')
    def test_subprocess_run_raises_file_not_found(self, mock_subprocess_run):
        error_message = "No such file or directory: /bin/nonexistent_command"
        mock_subprocess_run.side_effect = FileNotFoundError(error_message)
        script_name = "nonexistent_command.sh"
        
        result = self.support.run_bash_script(script_name, [], log=self.mock_log)
        
        expected_script_path = os.path.join(self.project_root, script_name)
        failed_cmd_str = f"/bin/bash {expected_script_path}" 

        self.assertEqual(result, {"status": "error", "message": f"Command not found: {script_name}. Details: {error_message}", "ReturnCode": -1})
        logged_command_str = f"/bin/bash {expected_script_path}"
        self.mock_log.error.assert_any_call(f"Command not found for: {logged_command_str}: {error_message}")

    @patch('genmonlib.mysupport.subprocess.run')
    def test_script_execution_no_args(self, mock_subprocess_run):
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="Script with no args output", stderr="")
        script_name = "test_no_args.sh"
        
        result_none_args = self.support.run_bash_script(script_name, log=self.mock_log) 
        
        expected_script_path = os.path.join(self.project_root, script_name)
        expected_cmd_list_no_args = ['/bin/bash', expected_script_path]
        
        mock_subprocess_run.assert_called_with(expected_cmd_list_no_args, capture_output=True, text=True, check=False)
        self.assertEqual(result_none_args, {"status": "OK", "message": "Script with no args output", "stdout": "Script with no args output", "ReturnCode": 0})
        self.mock_log.info.assert_any_call(f"Executing bash command: {' '.join(expected_cmd_list_no_args)}")

        mock_subprocess_run.reset_mock()
        self.mock_log.reset_mock()

        result_empty_args = self.support.run_bash_script(script_name, [], log=self.mock_log)
        mock_subprocess_run.assert_called_with(expected_cmd_list_no_args, capture_output=True, text=True, check=False)
        self.assertEqual(result_empty_args, {"status": "OK", "message": "Script with no args output", "stdout": "Script with no args output", "ReturnCode": 0})
        self.mock_log.info.assert_any_call(f"Executing bash command: {' '.join(expected_cmd_list_no_args)}")

if __name__ == '__main__':
    unittest.main()
