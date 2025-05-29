#!/usr/bin/env python
"""
This module provides the MyConfig class, an abstraction layer over Python's
standard `ConfigParser` (or `configparser` in Python 3). It is designed for
managing `.conf` style configuration files. A key feature of this class is its
attempt to preserve comments and overall structure in the configuration file
when writing values, which is not a standard behavior of `ConfigParser`.
"""
# -------------------------------------------------------------------------------
#    FILE: myconfig.py
# PURPOSE: Configuration file Abstraction
#
#  AUTHOR: Jason G Yates
#    DATE: 22-May-2018
#
# MODIFICATIONS:
#
# -------------------------------------------------------------------------------

import sys
import threading

if sys.version_info[0] < 3:
    from ConfigParser import ConfigParser
else:
    from configparser import ConfigParser

from genmonlib.mycommon import MyCommon

# Fix Python 2.x. unicode type
if sys.version_info[0] >= 3:  # PYTHON 3
    unicode = str


class MyConfig(MyCommon):
    """
    Manages application configuration files (`.conf` or `.ini` style).

    This class provides methods to read, write, and manage configuration
    settings. It wraps Python's `ConfigParser` but adds functionality,
    notably an attempt to preserve comments and file structure when modifying
    values (see `WriteValue` method). It also includes thread safety for
    write operations using a `threading.Lock`.

    Attributes:
        FileName (str): The path to the configuration file.
        Section (str): The current default section being operated upon.
                       This can be changed using `SetSection()`.
        Simulation (bool): If True, file write operations are skipped,
                           allowing for "dry runs" or use in simulation modes.
                           Defaults to False.
        CriticalLock (threading.Lock): A lock used to ensure that file write
                                       operations are thread-safe.
        config (ConfigParser): The underlying `ConfigParser` instance used to
                               parse and manage configuration data.
        InitComplete (bool): A flag indicating if the initialization of the
                             config object (including file reading) was successful.
        log: Inherited from `MyCommon`. Logger object for logging messages.
    """
    # ---------------------MyConfig::__init__------------------------------------
    def __init__(self, filename=None, section=None, simulation=False, log=None):
        """
        Initializes the MyConfig object.

        This constructor sets up the configuration parser, loads the specified
        configuration file, and sets the initial default section.

        Args:
            filename (str, optional): The path to the configuration file.
                                      Defaults to None.
            section (str, optional): The default section to use for operations.
                                     If None, the first section in the file
                                     will be used as the default. Defaults to None.
            simulation (bool, optional): If True, write operations to the file
                                         will be skipped. Defaults to False.
            log (logging.Logger, optional): An external logger instance to use.
                                            If None, logging might be handled by
                                            MyCommon's default or be uninitialized.
                                            Defaults to None.
        """
        super(MyConfig, self).__init__()
        self.log = log
        self.FileName = filename
        self.Section = section
        self.Simulation = simulation
        # CriticalLock ensures thread safety for file write operations.
        self.CriticalLock = threading.Lock()
        self.InitComplete = False
        try:
            if sys.version_info[0] < 3:
                self.config = ConfigParser()
            else:
                # interpolation=None prevents errors if percent signs (%) exist in values
                self.config = ConfigParser(interpolation=None)

            if self.FileName: # Ensure filename is provided before reading
                self.config.read(self.FileName)
            else:
                if self.log:
                    self.log.warning("MyConfig initialized without a filename.")


            # If no specific section is provided, use the first section found in the file.
            if self.Section is None:
                SectionList = self.GetSections()
                if SectionList and len(SectionList):
                    self.Section = SectionList[0]
                # If still no section (e.g. empty file), Section remains None.

        except Exception as e1:
            self.LogErrorLine("Error in MyConfig:init: " + str(e1))
            return # InitComplete remains False
        self.InitComplete = True

    # ---------------------MyConfig::HasOption-----------------------------------
    def HasOption(self, Entry):
        """
        Checks if an option exists in the current default section.

        Args:
            Entry (str): The name of the option (key) to check for.

        Returns:
            bool: True if the option exists in the current section, False otherwise.
                  Returns False if `InitComplete` is False or `Section` is None.
        """
        if not self.InitComplete or not self.Section:
            return False
        return self.config.has_option(self.Section, Entry)

    # ---------------------MyConfig::GetList-------------------------------------
    def GetList(self):
        """
        Retrieves all key-value pairs from the current default section.

        Returns:
            list of tuple: A list of (key, value) tuples for all options in the
                           current section. Returns None if an error occurs or
                           if `InitComplete` is False or `Section` is None.
        """
        if not self.InitComplete or not self.Section:
            return None
        try:
            return self.config.items(self.Section)
        except Exception as e1:
            self.LogErrorLine(
                "Error in MyConfig:GetList: " + self.Section + ": " + str(e1)
            )
            return None

    # ---------------------MyConfig::GetSections---------------------------------
    def GetSections(self):
        """
        Retrieves a list of all section names in the configuration file.

        Returns:
            list of str: A list of section names. Returns an empty list if
                         `InitComplete` is False or no sections exist.
        """
        if not self.InitComplete:
            return []
        return self.config.sections()

    # ---------------------MyConfig::SetSection----------------------------------
    def SetSection(self, section):
        """
        Sets the current default section for subsequent operations.

        Args:
            section (str): The name of the section to set as the default.
                           Must be a non-empty string.

        Returns:
            bool: True if the section was successfully set (or if in simulation mode).
                  False if the provided section name is invalid.
        """
        if self.Simulation:
            return True
        # Validate section name type and content
        if not (isinstance(section, str) or isinstance(section, unicode)) or not len(
            section
        ):
            self.LogError(
                "Error in MyConfig:SetSection: invalid section name: " + str(section)
            )
            return False
        self.Section = section
        return True

    # ---------------------MyConfig::ReadValue-----------------------------------
    def ReadValue(
        self, Entry, return_type=str, default=None, section=None, suppress_logging_on_error=False
    ):
        """
        Reads a value from the configuration file for a given entry and section.

        Args:
            Entry (str): The name of the option (key) to read.
            return_type (type, optional): The expected type of the value
                                          (str, bool, float, int).
                                          Defaults to str.
            default (any, optional): The default value to return if the entry
                                     is not found or an error occurs.
                                     Defaults to None.
            section (str, optional): The section to read from. If None, the
                                     current default section (`self.Section`) is used.
                                     Defaults to None.
            suppress_logging_on_error (bool, optional): If True, errors during reading
                                            (e.g., entry not found, type conversion error)
                                            will not be logged. Defaults to False.

        Returns:
            any: The value read from the configuration, cast to `return_type`.
                 Returns `default` if the entry is not found, if `InitComplete`
                 is False, or if an error occurs during processing.
        """
        if not self.InitComplete:
            return default

        try:
            current_section = self.Section
            if section is not None:
                # Temporarily set section for this read, then revert if it was different
                if not self.SetSection(section): # handles validation
                    if not suppress_logging_on_error:
                        self.LogErrorLine(f"Error in MyConfig:ReadValue: Invalid section '{section}' specified.")
                    return default
                # self.Section is now the specified section

            if not self.Section: # If no default section and no section specified
                 if not suppress_logging_on_error:
                    self.LogErrorLine(f"Error in MyConfig:ReadValue: No section specified or set for entry '{Entry}'.")
                 if section is not None: self.Section = current_section # Revert if changed
                 return default


            value = default
            if self.config.has_option(self.Section, Entry):
                if return_type == str:
                    value = self.config.get(self.Section, Entry)
                elif return_type == bool:
                    value = self.config.getboolean(self.Section, Entry)
                elif return_type == float:
                    value = self.config.getfloat(self.Section, Entry)
                elif return_type == int:
                    value = self.config.getint(self.Section, Entry)
                else:
                    if not suppress_logging_on_error:
                        self.LogErrorLine(
                            f"Warning in MyConfig:ReadValue ({self.Section}/{Entry}): invalid return_type '{return_type}', using default."
                        )
                    value = default # Ensure default is returned if type is unknown
            # else: value remains default if option not found

            if section is not None:
                self.Section = current_section # Revert to original section if it was changed

            return value

        except Exception as e1:
            if not suppress_logging_on_error:
                self.LogErrorLine(
                    f"Error in MyConfig:ReadValue ({self.Section}/{Entry}): {str(e1)}"
                )
            if section is not None:
                 self.Section = current_section # Revert on error too
            return default

    # ---------------------MyConfig::WriteSection--------------------------------
    def alt_WriteSection(self, SectionName):
        """
        Adds a new section to the configuration file using `ConfigParser.write()`.

        NOTE: This method will typically remove all comments and reformat the
        entire configuration file because it uses `self.config.write()`.

        Args:
            SectionName (str): The name of the section to add.

        Returns:
            bool: True if the section was added and written successfully (or if
                  in simulation mode or section already exists).
                  False if an error occurs or if `InitComplete` is False.
        """
        if self.Simulation:
            return True

        if not self.InitComplete:
            return False
        SectionList = self.GetSections()

        if SectionName in SectionList:
            self.LogError(f"Error in alt_WriteSection: Section '{SectionName}' already exists.")
            return True # Or False, depending on desired behavior for existing section. Original was True.

        try:
            # Acquire lock for thread-safe file writing
            with self.CriticalLock:
                # Add section to the ConfigParser object
                if sys.version_info.major < 3:
                    self.config.add_section(SectionName)
                else:
                    self.config[SectionName] = {} # Python 3 style section addition

                # Write the entire configuration back to the file
                with open(self.FileName, "w") as ConfigFile:
                    self.config.write(ConfigFile)
            return True
        except Exception as e1:
            self.LogErrorLine(f"Error in alt_WriteSection writing section '{SectionName}': {str(e1)}")
            return False

    # ---------------------MyConfig::WriteSection--------------------------------
    def WriteSection(self, SectionName):
        """
        Appends a new section header to the configuration file.

        This method attempts to add a new section by directly appending its
        header (e.g., `[SectionName]`) to the end of the file. It then re-reads
        the configuration to update the internal `ConfigParser` object.
        This approach is less destructive to comments than `alt_WriteSection`.

        Args:
            SectionName (str): The name of the section to add.

        Returns:
            bool: True if the section was appended and the config re-read
                  successfully (or if in simulation mode or section already exists).
                  False if an error occurs or `InitComplete` is False.
        """
        if self.Simulation:
            return True

        if not self.InitComplete:
            return False
        SectionList = self.GetSections()

        if SectionName in SectionList:
            self.LogError(f"Error in WriteSection: Section '{SectionName}' already exists.")
            return True # Original behavior

        try:
            # Acquire lock for thread-safe file writing
            with self.CriticalLock:
                # Append the new section header to the file
                with open(self.FileName, "a") as ConfigFile:
                    ConfigFile.write("\n[" + SectionName + "]\n") # Add newlines for separation
                    ConfigFile.flush()
                # Re-read the configuration file to update the internal parser state
                self.config.read(self.FileName)
            return True
        except Exception as e1:
            self.LogErrorLine(f"Error in WriteSection adding section '{SectionName}': {str(e1)}")
            return False

    # ---------------------MyConfig::WriteValue----------------------------------
    def alt_WriteValue(self, Entry, Value, remove=False, section=None):
        """
        Writes or removes a value in the configuration file using `ConfigParser.set()`
        or `ConfigParser.remove_option()` and then `ConfigParser.write()`.

        NOTE: This method will typically remove all comments and reformat the
        entire configuration file because it uses `self.config.write()`.

        Args:
            Entry (str): The name of the option (key) to write or remove.
            Value (str): The value to set for the option. Ignored if `remove` is True.
            remove (bool, optional): If True, the option will be removed.
                                     Defaults to False.
            section (str, optional): The section to write to. If None, the
                                     current default section (`self.Section`) is used.
                                     Defaults to None.
        Returns:
            bool: True if the value was written/removed successfully (or if in
                  simulation mode). False if an error occurs or `InitComplete` is False.
        """
        if self.Simulation:
            return True # Simulation mode, do nothing to file

        if not self.InitComplete:
            return False

        original_section = self.Section
        if section is not None:
            if not self.SetSection(section): # This validates the section
                return False
        
        if not self.Section:
             self.LogErrorLine(f"Error in alt_WriteValue: No section specified or set for entry '{Entry}'.")
             if section is not None: self.Section = original_section # Revert
             return False


        try:
            # Acquire lock for thread-safe file writing
            with self.CriticalLock:
                if remove:
                    if self.config.has_option(self.Section, Entry):
                        self.config.remove_option(self.Section, Entry)
                    else:
                        # Option doesn't exist, consider it a success for removal
                        if section is not None: self.Section = original_section # Revert
                        return True
                else:
                    # Set the value in the ConfigParser object
                    if sys.version_info.major < 3:
                        self.config.set(self.Section, Entry, str(Value))
                    else:
                        # Ensure section exists in Py3 before assignment
                        if not self.config.has_section(self.Section):
                            self.config.add_section(self.Section)
                        self.config[self.Section][Entry] = str(Value)

                # Write the entire configuration back to the file
                with open(self.FileName, "w") as ConfigFile:
                    self.config.write(ConfigFile)
            
            if section is not None:
                self.Section = original_section # Revert to original section
            return True

        except Exception as e1:
            self.LogErrorLine(f"Error in alt_WriteValue ({self.Section}/{Entry}): {str(e1)}")
            if section is not None:
                self.Section = original_section # Revert on error
            return False

    # ---------------------MyConfig::WriteValue----------------------------------
    def WriteValue(self, Entry, Value, remove=False, section=None):
        """
        Writes or removes a value in the configuration file while attempting to
        preserve comments and existing file structure.

        This method reads the entire configuration file line by line, modifies
        the target entry if found (or adds it if not found and not removing),
        and then rewrites the entire file. This process is more complex than
        using `ConfigParser.write()` directly but is necessary for comment
        preservation.

        Args:
            Entry (str): The name of the option (key) to write or remove.
            Value (str): The value to set for the option. Should be convertible to
                         a string. Ignored if `remove` is True.
            remove (bool, optional): If True, the option will be removed from the
                                     section. Defaults to False.
            section (str, optional): The section to write to. If None, the
                                     current default section (`self.Section`) is used.
                                     Defaults to None.
        Returns:
            bool: True if the value was written/removed successfully and the file
                  rewritten (or if in simulation mode).
                  False if an error occurs, `InitComplete` is False, or section is invalid.
        """
        if self.Simulation:
            return True # Simulation mode, do nothing

        if not self.InitComplete:
            return False

        original_current_section_attr = self.Section # Save the original self.Section
        target_section_name = section if section is not None else self.Section

        if target_section_name is None:
            self.LogErrorLine(f"Error in WriteValue: No section specified or set for entry '{Entry}'.")
            return False
        
        # Temporarily set self.Section for utility methods if a specific section is passed
        if section is not None:
            if not self.SetSection(section): # Validates and sets self.Section
                 # self.SetSection logs error, so just return
                return False
        # Now self.Section is guaranteed to be target_section_name (if valid)

        value_found_in_section = False # Flag to track if the Entry was found in the target section
        current_processing_section_matches_target = False # Flag if current line is within the target section

        try:
            # Acquire lock for thread-safe file writing
            with self.CriticalLock:
                # Read all lines from the file first
                try:
                    with open(self.FileName, "r") open_read_file:
                        original_lines = open_read_file.read().splitlines()
                except IOError as e:
                    self.LogErrorLine(f"Error reading config file {self.FileName} in WriteValue: {e}")
                    if section is not None: self.Section = original_current_section_attr # Revert
                    return False

                new_file_lines = [] # Store lines for the new file content

                # Iterate through each line of the original file content
                for line_number, current_line_text in enumerate(original_lines):
                    stripped_line = current_line_text.strip()

                    # Check if the current line defines a section header
                    if self.LineIsSection(stripped_line):
                        current_section_name_from_line = self.GetSectionName(stripped_line)
                        # Are we entering or leaving the target section?
                        if current_section_name_from_line.lower() == target_section_name.lower():
                            current_processing_section_matches_target = True
                            new_file_lines.append(current_line_text) # Add section header
                        else:
                            # If we were in the target section and now encountered a new section,
                            # and the entry was not found, this is the place to add it (if not removing).
                            if current_processing_section_matches_target and not value_found_in_section and not remove:
                                new_file_lines.append(f"{Entry} = {str(Value)}")
                                value_found_in_section = True # Mark as added/found
                            current_processing_section_matches_target = False
                            new_file_lines.append(current_line_text) # Add this other section header
                        continue # Move to next line

                    # If inside the target section, look for the entry
                    if current_processing_section_matches_target:
                        # Skip comments and blank lines within the section for key-value matching
                        if not stripped_line or stripped_line.startswith('#') or stripped_line.startswith(';'):
                            new_file_lines.append(current_line_text)
                            continue

                        # Attempt to split the line into key/value
                        # Be careful with lines that might not have '=' or have multiple '='
                        parts = stripped_line.split('=', 1)
                        if len(parts) == 2:
                            key_from_line = parts[0].strip()
                            # value_from_line = parts[1].strip() # Not used directly here

                            if key_from_line == Entry:
                                value_found_in_section = True
                                if not remove: # If modifying or ensuring it exists
                                    new_file_lines.append(f"{Entry} = {str(Value)}")
                                # If removing, this line is skipped (not added to new_file_lines)
                                continue # Entry processed, move to next line
                        # This line was in the section but not the entry we're looking for
                        new_file_lines.append(current_line_text)
                    else:
                        # Line is not a section header and not in the target section, keep as is
                        new_file_lines.append(current_line_text)

                # After processing all lines, if the target section was found (or implicitly is the only section)
                # and the value was NOT found within it, and we are NOT removing, then append the new entry.
                # This handles adding to the end of the relevant section if it's the last one in the file,
                # or if the file was empty/had no sections before (though target_section_name should exist).
                if current_processing_section_matches_target and not value_found_in_section and not remove:
                    new_file_lines.append(f"{Entry} = {str(Value)}")
                    value_found_in_section = True # Mark as added

                # If the target section itself was never found (e.g. new section for a new key)
                # and we are not removing, we need to add the section header and then the key-value pair.
                # This case needs careful handling; the original code implies sections should pre-exist for WriteValue.
                # For simplicity matching original logic, we assume section exists if we reach here and
                # `current_processing_section_matches_target` might be true if it was the last one.
                # The more robust way is to check if `target_section_name` is in `self.GetSections()`
                # before this whole process, or handle adding it here.
                # The original code doesn't explicitly add a new section in WriteValue if it's missing.
                # It seems to rely on the section already existing or being the current one.

                # Rewrite the file with the modified lines
                with open(self.FileName, "w") as ConfigFile:
                    for line in new_file_lines:
                        ConfigFile.write(line + "\n")
                    ConfigFile.flush()

                # Update the internal ConfigParser cache
                self.config.read(self.FileName)

            if section is not None:
                self.Section = original_current_section_attr # Restore original self.Section

            return True

        except Exception as e1:
            self.LogErrorLine(f"Error in WriteValue ({target_section_name}/{Entry}): {str(e1)}")
            if section is not None:
                self.Section = original_current_section_attr # Restore on error
            return False

    # ---------------------MyConfig::GetSectionName------------------------------
    def GetSectionName(self, Line):
        """
        Extracts the section name from a line if it's a valid section header.

        A valid section header is like `[SectionName]`.

        Args:
            Line (str): The line to check.

        Returns:
            str: The extracted section name if the line is a valid section header.
                 An empty string otherwise, or if in simulation mode.
        """
        if self.Simulation: # In simulation, this might not be meaningful
            return ""
        Line = Line.strip()
        if Line.startswith("[") and Line.endswith("]") and len(Line) >= 3:
            # Extract name from between '[' and ']'
            return Line[1:-1]
        return ""

    # ---------------------MyConfig::LineIsSection-------------------------------
    def LineIsSection(self, Line):
        """
        Checks if a line is a valid section header.

        Args:
            Line (str): The line to check.

        Returns:
            bool: True if the line is a valid section header (e.g., `[SectionName]`),
                  False otherwise, or if in simulation mode.
        """
        if self.Simulation: # In simulation, this might not be meaningful
            return False
        Line = Line.strip()
        # A section header must start with '[', end with ']', and have content in between.
        if Line.startswith("[") and Line.endswith("]") and len(Line) >= 3:
            return True
        return False
