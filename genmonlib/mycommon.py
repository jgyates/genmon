#!/usr/bin/env python
"""
This module provides the MyCommon class, a base class intended to be inherited by
other classes within the genmon system. It offers a collection of common utility
functions and initializes shared attributes that are frequently used across different
parts of the application. These utilities include type checking, string manipulation,
data conversion, logging helpers, and more.
"""
# -------------------------------------------------------------------------------
#    FILE: mycommon.py
# PURPOSE: common functions in all classes
#
#  AUTHOR: Jason G Yates
#    DATE: 21-Apr-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import json
import os
import sys
import re

from genmonlib.program_defaults import ProgramDefaults


# ------------ MyCommon class -----------------------------------------------------
class MyCommon(object):
    """
    Base class providing common utility functions and attributes.

    This class is intended to be inherited by other classes in the genmon system.
    It initializes common attributes like loggers and debug flags, and provides
    a suite of helper methods for various tasks such as type checking, string
    manipulation, data conversion, and logging.

    Attributes:
        DefaultConfPath (str): The default path to the configuration file,
                               obtained from ProgramDefaults.
        log: Logger object for general logging. Expected to be initialized by
             a subclass or an external entity.
        console: Logger object for console-specific logging. Expected to be
                 initialized by a subclass or an external entity.
        Threads (dict): A dictionary to store and manage thread objects.
                        The keys are thread names or identifiers, and values
                        are the thread objects themselves.
        debug (bool): A flag indicating whether debug mode is enabled.
                      Defaults to False.
        MaintainerAddress (str): Email address for the software maintainer.
    """
    DefaultConfPath = ProgramDefaults.ConfPath

    def __init__(self):
        """
        Initializes common attributes for the MyCommon class.
        """
        self.log = None
        self.console = None
        self.Threads = {}  # Dict of mythread objects
        self.debug = False
        self.MaintainerAddress = "generatormonitor.software@gmail.com"

    # ------------ MyCommon::InVirtualEnvironment -------------------------------
    def InVirtualEnvironment(self):
        """
        Checks if the code is running inside a Python virtual environment.

        Returns:
            bool: True if running in a virtual environment, False otherwise.
                  Returns False if an exception occurs during the check.
        """
        try:
            # Check for attributes commonly present in virtual environments
            return (hasattr(sys, 'real_prefix') or
                (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix))
        except:
            return False  # Fallback in case of unexpected errors
    # ------------ MyCommon::InManagedLibaries ----------------------------------
    def ManagedLibariesEnabled(self):
        """
        Checks if the Python installation uses externally managed libraries.

        This is relevant for newer Python versions (e.g., 3.11+) on systems
        that use OS package managers to handle Python packages, which might
        place an "EXTERNALLY-MANAGED" file in the standard library path.

        Returns:
            bool: True if the EXTERNALLY-MANAGED file exists, False otherwise.
                  Returns False if an exception occurs during the check.
        """
        try:
            # Construct the path to the EXTERNALLY-MANAGED file
            # e.g., /usr/lib/python3.11/EXTERNALLY-MANAGED
            # Using string concatenation for compatibility with older Python versions
            # that might not support f-strings as used in the original commented-out code.
            managedfile = "/usr/lib/python" + str(sys.version_info.major) + "." + str(sys.version_info.minor) + "/EXTERNALLY-MANAGED"
            #managedfile = f"/usr/lib/python{sys.version_info.major:d}.{sys.version_info.minor:d}/EXTERNALLY-MANAGED" # Original f-string version
            if os.path.isfile(managedfile):
                return True
            else:
                return False
        except:
            return False # Fallback in case of unexpected errors
    # ------------ MyCommon::VersionTuple ---------------------------------------
    def VersionTuple(self, value):
        """
        Converts a version string (e.g., "1.2.3a") into a tuple of integers.

        It first removes any alphabetic characters from the string.

        Args:
            value (str): The version string to convert.

        Returns:
            tuple: A tuple of integers representing the version numbers.
                   For example, "1.2.3a" becomes (1, 2, 3).
        """
        value = self.removeAlpha(value) # Remove non-numeric parts
        return tuple(map(int, (value.split("."))))

    # ------------ MyCommon::StringIsInt ----------------------------------------
    def StringIsInt(self, value):
        """
        Checks if a given string can be converted to an integer.

        Args:
            value (str): The string to check.

        Returns:
            bool: True if the string can be converted to an integer, False otherwise.
        """
        try:
            temp = int(value) # Attempt conversion
            return True
        except:
            return False # Conversion failed

    # ------------ MyCommon::StringIsFloat --------------------------------------
    def StringIsFloat(self, value):
        """
        Checks if a given string can be converted to a float.

        Args:
            value (str): The string to check.

        Returns:
            bool: True if the string can be converted to a float, False otherwise.
        """
        try:
            temp = float(value) # Attempt conversion
            return True
        except:
            return False # Conversion failed

    # ------------ MyCommon::ConvertCelsiusToFahrenheit -------------------------
    def ConvertCelsiusToFahrenheit(self, Celsius):
        """
        Converts a temperature from Celsius to Fahrenheit.

        Args:
            Celsius (float or int): The temperature in Celsius.

        Returns:
            float: The temperature converted to Fahrenheit.
        """
        return (Celsius * 9.0 / 5.0) + 32.0

    # ------------ MyCommon::ConvertFahrenheitToCelsius -------------------------
    def ConvertFahrenheitToCelsius(self, Fahrenheit):
        """
        Converts a temperature from Fahrenheit to Celsius.

        Args:
            Fahrenheit (float or int): The temperature in Fahrenheit.

        Returns:
            float: The temperature converted to Celsius.
        """
        return (Fahrenheit - 32.0) * 5.0 / 9.0

    # ------------ MyCommon::StripJson ------------------------------------------
    def StripJson(self, InputString):
        """
        Removes JSON-specific characters ('{}[]"') from a string.

        Args:
            InputString (str): The string from which to strip characters.

        Returns:
            str: The string with JSON characters removed.
        """
        for char in '{}[]"': # Iterate over characters to remove
            InputString = InputString.replace(char, "")
        return InputString

    # ------------ MyCommon::DictToString ---------------------------------------
    def DictToString(self, InputDict, ExtraStrip=False):
        """
        Converts a dictionary to a formatted JSON string, with an option for
        additional stripping of characters.

        Args:
            InputDict (dict): The dictionary to convert.
            ExtraStrip (bool, optional): If True, removes "} \n" from the end
                                         of the JSON string. Defaults to False.

        Returns:
            str: The formatted string representation of the dictionary.
                 Returns an empty string if InputDict is None.
        """
        if InputDict == None:
            return ""
        # Convert dict to a pretty-printed JSON string
        ReturnString = json.dumps(
            InputDict, sort_keys=False, indent=4, separators=(" ", ": ")
        )
        if ExtraStrip:
            ReturnString = ReturnString.replace("} \n", "") # Optional extra stripping
        return self.StripJson(ReturnString) # Final stripping of JSON chars

    # ------------ MyCommon::BitIsEqual -----------------------------------------
    def BitIsEqual(self, value, mask, bits):
        """
        Checks if specific bits in a value are equal to a given bit pattern
        after applying a mask.

        Args:
            value (int): The integer value to check.
            mask (int): The bitmask to apply to the value (e.g., 0xFF).
            bits (int): The expected bit pattern to compare against after masking.

        Returns:
            bool: True if (value & mask) is equal to bits, False otherwise.
        """
        newval = value & mask # Apply mask
        if newval == bits: # Compare with expected bits
            return True
        else:
            return False

    # ------------ MyCommon::printToString --------------------------------------
    def printToString(self, msgstr, nonewline=False, spacer=False):
        """
        Formats a message string, optionally adding a newline or leading spaces.

        This method essentially prepares a string as if it were to be printed,
        but returns the string instead.

        Args:
            msgstr (str): The message string to format.
            nonewline (bool, optional): If True, no newline character is appended.
                                        Defaults to False.
            spacer (bool, optional): If True, four leading spaces are added to
                                     the message. Defaults to False.

        Returns:
            str: The formatted message string.
        """
        if spacer:
            MessageStr = "    {0}" # Add leading spaces
        else:
            MessageStr = "{0}"

        if not nonewline:
            MessageStr += "\n" # Append newline by default

        # The original code had a commented-out print statement.
        # This method returns the formatted string, not prints it.
        # print (MessageStr.format(msgstr), end='')
        formatted_message_tuple = (MessageStr.format(msgstr),) # Store in a tuple (original logic)
        return formatted_message_tuple[0] # Return the first element

        # end printToString

    # ---------- MyCommon:FindDictValueInListByKey ------------------------------
    def FindDictValueInListByKey(self, key, listname):
        """
        Finds the value associated with a specific key within a list of dictionaries.

        It iterates through the list, and for each dictionary, it checks if the
        (case-insensitive) key exists. Returns the first value found.

        Args:
            key (str): The key to search for (case-insensitive).
            listname (list): A list, potentially containing dictionaries.

        Returns:
            any: The value associated with the key if found, otherwise None.
                 Logs an error if an exception occurs during processing.
        """
        try:
            for item in listname:
                if isinstance(item, dict): # Process only dictionary items
                    for dictkey, value in item.items():
                        if dictkey.lower() == key.lower(): # Case-insensitive key comparison
                            return value
        except Exception as e1:
            # Log the error with details
            self.LogErrorLine("Error in FindDictInList: " + str(e1))
        return None # Key not found or an error occurred

    # ----------  MyCommon::removeNonPrintable-----------------------------------
    def removeNonPrintable(self, inputStr):
        """
        Removes non-printable ASCII characters from a string.

        Uses a regular expression to keep only characters in the range
        ASCII 32 (space) to 127 (~).

        Args:
            inputStr (str): The string to process.

        Returns:
            str: The string with non-printable characters removed.
                 Returns the original string if an exception occurs.
        """
        try:
            import re # Import locally as it's only used here

            # Regular expression to match any character not in the range \x20 (space) to \x7f (~)
            inputStr = re.sub(r"[^\x20-\x7f]", r"", inputStr)
            return inputStr
        except:
            return inputStr # Return original string on error

    # ----------  MyCommon::removeAlpha------------------------------------------
    def removeAlpha(self, input_string):
        """
        Removes alphabetic characters, spaces, and percent signs from a string.

        This method is typically used to sanitize strings that are expected to
        represent numerical or version values but may include unwanted characters
        (e.g., units like "100%", or alpha tags in versions like "1.2.3a").
        It preserves digits, periods (.), and other special characters not
        explicitly targeted for removal.

        Args:
            input_string (str): The string to process.

        Returns:
            str: The string with specified characters removed, then stripped of
                 leading/trailing whitespace.
        """
        processed_string = ""
        for char in input_string:
            # Keep characters that are not alphabetic, not a space, and not a percent sign
            if not char.isalpha() and char != " " and char != "%":
                processed_string += char

        return processed_string.strip() # Remove leading/trailing whitespace

    # ------------ MyCommon::ConvertToNumber------------------------------------
    def ConvertToNumber(self, value_str):
        """
        Converts a string to an integer or float after removing non-numeric characters.

        This method first removes any characters that are not digits, a period (.),
        or a hyphen/minus sign (-). It then attempts to convert the cleaned string
        first to an integer. If this conversion fails (e.g., the string contains a
        decimal point), it attempts to convert it to a float.

        Args:
            value_str (str): The string to convert.

        Returns:
            int or float: The converted number. Returns 0 if conversion fails
                          or an error occurs, and logs the error.
        """
        try:
            # Remove characters that are not digits, '.', or '-'
            # Remove characters that are not digits, '.', or '-'
            cleaned_string = re.sub('[^0-9.\-]','',value_str)
            try:
                numeric_value = int(cleaned_string) # Try converting to int
            except ValueError: # More specific exception handling
                numeric_value = float(cleaned_string) # If int conversion fails, try float
            return numeric_value
        except Exception as e1:
             # Log error with specific details, including the original value string
             self.LogErrorLine("Error in MyCommon:ConvertToNumber: " + str(e1) + ": " + str(value_str))
             return 0 # Default return value on error
    # ------------ MyCommon::MergeDicts -----------------------------------------
    def MergeDicts(self, dict1, dict2):
        """
        Merges two dictionaries into a new dictionary.

        This performs a shallow copy. If keys overlap, values from the second
        dictionary (`dict2`) will overwrite those from the first (`dict1`).

        Args:
            dict1 (dict): The first dictionary.
            dict2 (dict): The second dictionary, whose items will be merged into
                          and potentially overwrite items from `dict1`.

        Returns:
            dict: A new dictionary containing merged key-value pairs from `dict1` and `dict2`.
        """
        merged_dict = dict1.copy() # Start with a shallow copy of the first dict
        merged_dict.update(dict2)  # Update with key-value pairs from the second dict
        return merged_dict

    # ---------------------MyCommon:urljoin--------------------------------------
    def urljoin(self, *parts):
        """
        Joins multiple parts of a URL into a single string.

        It strips extra forward slashes from the parts to prevent issues like
        "http:///example.com//path". It's careful not to remove the double slash
        in "http://" or similar protocol indicators.

        Args:
            *parts (str): Variable number of string arguments representing
                          parts of a URL.

        Returns:
            str: The combined URL string.
        """
        part_list = []
        for part in parts:
            p = str(part) # Ensure part is a string
            # Handle cases like "http://" to avoid stripping the essential slashes
            if p.endswith("//"):
                p = p[0:-1] # Remove one trailing slash if two are present
            else:
                p = p.strip("/") # Strip leading/trailing slashes from other parts
            part_list.append(p)
        # Join all parts with a single slash
        url = "/".join(part_list)
        return url

    # -------------MyCommon::LogHexList------------------------------------------
    def LogHexList(self, listname, prefix=None, suppress_logging = False):
        """
        Formats a list of numbers as a hex string and optionally logs it.

        Each number in the list is formatted as "0xNN".

        Args:
            listname (list of int): The list of numbers to format.
            prefix (str, optional): A string to prepend to the hex list string
                                    (e.g., "Data: "). Defaults to None.
            suppress_logging (bool, optional): If False (default), the formatted string
                                     is logged using self.LogError.
                                     If True, logging is skipped.

        Returns:
            str: The formatted hex string (e.g., "[0x0a,0x1f,0x00]").
                 Logs an error if an exception occurs during formatting.
        """
        try:
            outstr = ""
            # Format each number as a two-digit hex value, prefixed with "0x"
            outstr = "[" + ",".join("0x{:02x}".format(num) for num in listname) + "]"
            if prefix != None:
                outstr = prefix + " = " + outstr # Prepend prefix if provided

            if suppress_logging == False: # Log if not suppressed
                self.LogError(outstr)
            return outstr
        except Exception as e1:
            self.LogErrorLine("Error in LogHexList: " + str(e1))
            return outstr # Return whatever was formatted before the error

    # ---------------------------------------------------------------------------
    def LogInfo(self, message, LogLine=False):
        """
        Logs an informational message to both the general log and the console log.

        This method uses `self.LogError` for the general log and
        `self.LogConsole` for the console log. Note that despite the name
        `LogError`, it's used here for informational messages as per existing
        pattern in this class. The console logging also goes to `self.console.error`.

        Args:
            message (str): The message to log.
            LogLine (bool, optional): If True, logs the message with file name
                                      and line number using `self.LogErrorLine`.
                                      If False (default), logs the message as is
                                      using `self.LogError`.
        """
        if not LogLine:
            self.LogError(message) # Logs to self.log.error
        else:
            self.LogErrorLine(message) # Logs to self.log.error with line info
        self.LogConsole(message) # Logs to self.console.error

    # ---------------------MyCommon::LogConsole------------------------------------
    def LogConsole(self, message):
        """
        Logs a message to the console logger, specifically using `self.console.error`.

        Note: This method uses `self.console.error` for output, which might imply
        an error by name, but it's used in this class for general console visibility.

        Args:
            message (str): The message to log to the console.
        """
        if self.console is not None:
            self.console.error(message) # Log to console via its error method

    # ---------------------MyCommon::LogError------------------------------------
    def LogError(self, message, error_obj=None):
        """
        Logs an error message to the general log (`self.log.error`).

        If an error object (exception) is provided, its string representation is
        appended to the message.

        Args:
            message (str): The error message to log.
            error_obj (Exception, optional): An exception object associated with the
                                           error. Defaults to None.
        """
        if self.log is not None:
            if error_obj is not None:
                message = message + " : " + self.GetErrorString(error_obj)
            self.log.error(message)

    # ---------------------MyCommon::FatalError----------------------------------
    def FatalError(self, message, error_obj=None):
        """
        Logs a fatal error message and then raises an Exception.

        The message is logged to both the general log (`self.log.error`) and
        the console log (`self.console.error`).

        Args:
            message (str): The fatal error message.
            error_obj (Exception, optional): An exception object associated with the
                                           error. Defaults to None.

        Raises:
            Exception: Always raises an exception with the provided message
                       (and error string if `error_obj` is not None).
        """
        if error_obj is not None:
            message = message + " : " + self.GetErrorString(error_obj)
        if self.log is not None:
            self.log.error(message) # Log to general log
        if self.console is not None:
            self.console.error(message) # Log to console
        raise Exception(message) # Raise an exception to halt execution

    # ---------------------MyCommon::LogErrorLine--------------------------------
    def LogErrorLine(self, message, error_obj=None):
        """
        Logs an error message to the general log, including the file name and
        line number where the logging call was made (or from exception context).

        Uses `self.log.error`. If an error object is provided, its string
        representation is appended.

        Args:
            message (str): The error message to log.
            error_obj (Exception, optional): An exception object associated with the
                                           error. Defaults to None.
        """
        if self.log is not None:
            if error_obj is not None:
                message = message + " : " + self.GetErrorString(error_obj)
            # Append file name and line number to the message
            self.log.error(message + " : " + self.GetErrorLine())

    # ---------- MyCommon::LogDebug---------------------------------------------
    def LogDebug(self, message, error_obj=None):
        """
        Logs a debug message if the debug flag (`self.debug`) is True.

        The message is logged using `self.LogError` (which in turn uses `self.log.error`).

        Args:
            message (str): The debug message to log.
            error_obj (Exception, optional): An exception object associated with the
                                           debug information. Defaults to None.
        """
        if self.debug: # Only log if debug mode is enabled
            self.LogError(message, error_obj)

    # ---------------------MyCommon::GetErrorLine--------------------------------
    def GetErrorLine(self):
        """
        Retrieves the file name and line number from the current exception's traceback.

        This method should be called from within an except block to access
        valid exception information via `sys.exc_info()`.

        Returns:
            str: A string in the format "filename:lineno", or an empty string
                 if no exception traceback information is available (e.g., called
                 outside of an `except` block).
        """
        exc_type, exc_obj, exc_tb = sys.exc_info() # Get current exception info
        if exc_tb is None: # Check if traceback object exists
            return "" # No traceback available
        else:
            filename = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1] # Get filename
            line_number = exc_tb.tb_lineno # Get line number
            return f"{filename}:{line_number}" # Use f-string for cleaner formatting

    # ---------------------MyCommon::GetErrorString------------------------------
    def GetErrorString(self, error_obj):
        """
        Converts an error object (typically an Exception instance) to its string representation.

        Args:
            error_obj (Exception or any): The error object.

        Returns:
            str: The string representation of the `error_obj`. Returns the `error_obj`
                 itself if conversion to string fails (though this is unlikely
                 for standard exception types like `Exception`).
        """
        try:
            return str(error_obj)
        except:
            # Fallback, though str() on exceptions should generally not fail.
            return error_obj # Should be error_obj, not Error
    # ---------------------MyCommon::getSignedNumber-----------------------------
    def getSignedNumber(self, unsigned_number, bit_length):
        """
        Converts an unsigned integer to a signed integer using two's complement
        representation, based on its bit length.

        This is useful for interpreting values read from hardware registers or
        communication protocols where numbers are represented with a fixed number
        of bits and might be signed.

        Args:
            unsigned_number (int): The unsigned integer value to convert.
            bit_length (int): The number of bits used to represent the number
                              (e.g., 8 for byte, 16 for short).

        Returns:
            int: The signed integer value. Returns the original number if inputs
                 are not integers or if an error occurs, and logs the error.
        """
        try:
            if isinstance(unsigned_number, int) and isinstance(bit_length, int):
                mask = (1 << bit_length) - 1 # Mask to get the number within bit_length bits
                # Check if the sign bit (the most significant bit for the given bit_length) is set
                if unsigned_number & (1 << (bit_length - 1)):
                    # Negative number: apply two's complement.
                    # This is done by taking (number - 2^bit_length)
                    # or (number | ~mask) if you want to ensure sign extension
                    # for potentially larger Python integers.
                    # (unsigned_number | ~mask) correctly sign-extends.
                    return unsigned_number | ~mask
                else:
                    # Positive number: just ensure it's within the mask,
                    # though for positive standard integers, it already would be.
                    return unsigned_number & mask
            else:
                # Input types are incorrect; log an error and return the original number.
                self.LogErrorLine(f"Error in getSignedNumber: Invalid input types. number: {type(unsigned_number)}, bitLength: {type(bit_length)}")
                return unsigned_number
        except Exception as e1:
            self.LogErrorLine("Error in getSignedNumber: " + str(e1))
            return unsigned_number # Return original number on other unforeseen errors
