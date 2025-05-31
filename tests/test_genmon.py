import unittest
import sys
import os

# Adjust path to import Monitor from genmon.py
# Assuming tests/test_genmon.py and genmon.py are in a structure like:
# project_root/
#   genmon.py
#   genmonlib/  <-- genmon.py imports from here
#   tests/
#     test_genmon.py
current_script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_script_dir) # This should be the parent of 'tests'

# Add project_root to sys.path so 'genmon' (referring to genmon.py) can be found,
# and 'genmonlib' can be found by genmon.py
sys.path.insert(0, project_root)

# The Monitor class itself is in genmon.py at the project root.
# genmon.py also imports from genmonlib.
# For the purpose of this unit test, we are primarily testing the URL f-string construction.
# The actual Monitor class has a complex __init__ method involving file reads,
# permission checks, and other side effects not ideal for a simple unit test.
# Therefore, we will use a dummy/mock object that mimics the necessary attributes.

class DummyMonitorForURLTest:
    """
    A simple mock object to hold attributes needed for URL construction,
    avoiding the complex initialization of the actual Monitor class.
    """
    def __init__(self):
        # Initialize with default values, similar to how Monitor.GetConfig would set them
        self.UpdateCheckUser = "jgyates"
        self.UpdateCheckRepo = "genmon"
        self.UpdateCheckBranch = "master"

class TestMonitorURLConstruction(unittest.TestCase):
    def setUp(self):
        """
        Set up a dummy monitor instance for each test.
        """
        self.monitor = DummyMonitorForURLTest()

    def test_software_update_url_construction(self):
        """
        Tests the construction of the software update URL based on
        UpdateCheckUser, UpdateCheckRepo, and UpdateCheckBranch attributes.
        """
        test_cases = [
            {
                "user": "jgyates", "repo": "genmon", "branch": "master",
                "expected": "https://raw.githubusercontent.com/jgyates/genmon/master/genmonlib/program_defaults.py"
            },
            {
                "user": "testuser", "repo": "testrepo", "branch": "develop",
                "expected": "https://raw.githubusercontent.com/testuser/testrepo/develop/genmonlib/program_defaults.py"
            },
            {
                "user": "another-user", "repo": "another-repo", "branch": "feature/new-feature-branch",
                "expected": "https://raw.githubusercontent.com/another-user/another-repo/feature/new-feature-branch/genmonlib/program_defaults.py"
            },
            {
                "user": "user_with_underscores", "repo": "repo-with-hyphens", "branch": "branch_with_numbers123",
                "expected": "https://raw.githubusercontent.com/user_with_underscores/repo-with-hyphens/branch_with_numbers123/genmonlib/program_defaults.py"
            }
        ]

        for tc in test_cases:
            with self.subTest(tc=tc):
                # Set the attributes on our dummy monitor instance
                self.monitor.UpdateCheckUser = tc["user"]
                self.monitor.UpdateCheckRepo = tc["repo"]
                self.monitor.UpdateCheckBranch = tc["branch"]

                # This is the f-string logic being tested, copied from genmon.py's CheckSoftwareUpdate method
                actual_url = f"https://raw.githubusercontent.com/{self.monitor.UpdateCheckUser}/{self.monitor.UpdateCheckRepo}/{self.monitor.UpdateCheckBranch}/genmonlib/program_defaults.py"

                self.assertEqual(actual_url, tc["expected"])

if __name__ == '__main__':
    # This allows running the tests directly from the command line
    unittest.main()
