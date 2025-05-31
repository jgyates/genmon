import unittest
import os
import sys
from configparser import ConfigParser

# Add genmonlib to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from genmonlib.myconfig import MyConfig

class TestMyConfig(unittest.TestCase):

    def setUp(self):
        # Create a dummy config file for testing
        self.config_file_path = "test_config.conf"
        with open(self.config_file_path, "w") as f:
            f.write("[Section1]\n")
            f.write("string_val = test_string\n")
            f.write("int_val = 123\n")
            f.write("float_val = 45.67\n")
            f.write("bool_val_true = true\n")
            f.write("bool_val_false = false\n")
            f.write("# This is a comment\n")
            f.write("val_with_comment = comment_val\n")
            f.write("[Section2]\n")
            f.write("another_val = another_string\n")

        # Initialize MyConfig with the dummy file
        self.my_config = MyConfig(filename=self.config_file_path, section="Section1")

    def tearDown(self):
        # Remove the dummy config file
        if os.path.exists(self.config_file_path):
            os.remove(self.config_file_path)

    def test_read_string_value(self):
        self.assertEqual(self.my_config.ReadValue("string_val"), "test_string")

    def test_read_int_value(self):
        self.assertEqual(self.my_config.ReadValue("int_val", return_type=int), 123)

    def test_read_float_value(self):
        self.assertEqual(self.my_config.ReadValue("float_val", return_type=float), 45.67)

    def test_read_bool_true_value(self):
        self.assertTrue(self.my_config.ReadValue("bool_val_true", return_type=bool))

    def test_read_bool_false_value(self):
        self.assertFalse(self.my_config.ReadValue("bool_val_false", return_type=bool))

    def test_read_default_value(self):
        self.assertEqual(self.my_config.ReadValue("non_existent_val", default="default_val"), "default_val")

    def test_read_value_from_another_section(self):
        self.assertEqual(self.my_config.ReadValue("another_val", section="Section2"), "another_string")

    def test_has_option(self):
        self.assertTrue(self.my_config.HasOption("string_val"))
        self.assertFalse(self.my_config.HasOption("non_existent_val"))

    def test_get_list(self):
        expected_list = [
            ("string_val", "test_string"),
            ("int_val", "123"),
            ("float_val", "45.67"),
            ("bool_val_true", "true"),
            ("bool_val_false", "false"),
            ("val_with_comment", "comment_val")
        ]
        # Order might not be guaranteed by ConfigParser, so compare as sets
        self.assertCountEqual(self.my_config.GetList(), expected_list)

    def test_get_sections(self):
        self.assertCountEqual(self.my_config.GetSections(), ["Section1", "Section2"])

    def test_set_section(self):
        self.my_config.SetSection("Section2")
        self.assertEqual(self.my_config.Section, "Section2")
        self.assertEqual(self.my_config.ReadValue("another_val"), "another_string")

    def test_write_value_new(self):
        self.my_config.WriteValue("new_val", "new_string_value")
        # Re-read the config to verify
        config_parser = ConfigParser()
        config_parser.read(self.config_file_path)
        self.assertEqual(config_parser.get("Section1", "new_val"), "new_string_value")
        # Also check with MyConfig instance
        self.assertEqual(self.my_config.ReadValue("new_val"), "new_string_value")


    def test_write_value_existing(self):
        self.my_config.WriteValue("string_val", "updated_string")
        config_parser = ConfigParser()
        config_parser.read(self.config_file_path)
        self.assertEqual(config_parser.get("Section1", "string_val"), "updated_string")
        self.assertEqual(self.my_config.ReadValue("string_val"), "updated_string")

    def test_remove_value(self):
        self.assertTrue(self.my_config.HasOption("string_val"))
        self.my_config.WriteValue("string_val", "", remove=True)
        config_parser = ConfigParser()
        config_parser.read(self.config_file_path)
        self.assertFalse(config_parser.has_option("Section1", "string_val"))
        self.assertFalse(self.my_config.HasOption("string_val"))


    def test_write_section_new(self):
        self.my_config.WriteSection("Section3")
        config_parser = ConfigParser()
        config_parser.read(self.config_file_path)
        self.assertTrue(config_parser.has_section("Section3"))
        self.assertIn("Section3", self.my_config.GetSections())


    def test_comment_preservation_on_write(self):
        # This test is tricky because preserving comments with ConfigParser is hard.
        # MyConfig.WriteValue attempts to preserve them by reading and rewriting.
        self.my_config.WriteValue("int_val", 789)

        with open(self.config_file_path, "r") as f:
            content = f.read()
            self.assertIn("# This is a comment", content)
            self.assertIn("val_with_comment = comment_val", content) # Ensure other lines are still there
            self.assertIn("int_val = 789", content)


    def test_write_value_to_different_section(self):
        self.my_config.WriteValue("new_in_section2", "val_sec2", section="Section2")
        config_parser = ConfigParser()
        config_parser.read(self.config_file_path)
        self.assertEqual(config_parser.get("Section2", "new_in_section2"), "val_sec2")
        self.assertEqual(self.my_config.ReadValue("new_in_section2", section="Section2"), "val_sec2")

    def test_read_value_non_existent_section_with_default(self):
        self.assertEqual(self.my_config.ReadValue("some_key", section="NonExistentSection", default="default_val"), "default_val")

    def test_write_value_creates_section_if_not_exists_in_alt_write(self):
        # alt_WriteValue should create the section if it doesn't exist with Python 3 ConfigParser behavior
        # For Python 2, it might require section to exist or manual creation.
        # This test specifically targets the behavior of alt_WriteValue if it's intended to create sections.
        # If MyConfig.alt_WriteValue is used and expected to create sections:
        self.my_config.alt_WriteValue("key_in_new_section", "value_new_sec", section="SectionNewAlt")
        config_parser = ConfigParser()
        config_parser.read(self.config_file_path)
        self.assertTrue(config_parser.has_section("SectionNewAlt"))
        self.assertEqual(config_parser.get("SectionNewAlt", "key_in_new_section"), "value_new_sec")
        # Check with MyConfig as well
        self.assertIn("SectionNewAlt", self.my_config.GetSections())
        self.assertEqual(self.my_config.ReadValue("key_in_new_section", section="SectionNewAlt"), "value_new_sec")


if __name__ == '__main__':
    unittest.main()
