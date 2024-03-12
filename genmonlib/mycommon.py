#!/usr/bin/env python
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
    DefaultConfPath = ProgramDefaults.ConfPath

    def __init__(self):
        self.log = None
        self.console = None
        self.Threads = {}  # Dict of mythread objects
        self.debug = False
        self.MaintainerAddress = "generatormonitor.software@gmail.com"

    # ------------ MyCommon::InVirtualEnvironment -------------------------------
    def InVirtualEnvironment(self):
        try:
            return (hasattr(sys, 'real_prefix') or
                (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix))
        except:
            return False
    # ------------ MyCommon::InManagedLibaries ----------------------------------
    def ManagedLibariesEnabled(self):
        try:
            #  /usr/lib/python3.11/EXTERNALLY-MANAGED
            # to support python 3.5 not use formatted strings
            managedfile = "/usr/lib/python" + str(sys.version_info.major) + "." + str(sys.version_info.minor) + "/EXTERNALLY-MANAGED"
            #managedfile = f"/usr/lib/python{sys.version_info.major:d}.{sys.version_info.minor:d}/EXTERNALLY-MANAGED"
            if os.path.isfile(managedfile):
                return True
            else:
                return False
        except:
            return False
    # ------------ MyCommon::VersionTuple ---------------------------------------
    def VersionTuple(self, value):

        value = self.removeAlpha(value)
        return tuple(map(int, (value.split("."))))

    # ------------ MyCommon::StringIsInt ----------------------------------------
    def StringIsInt(self, value):

        try:
            temp = int(value)
            return True
        except:
            return False

    # ------------ MyCommon::StringIsFloat --------------------------------------
    def StringIsFloat(self, value):

        try:
            temp = float(value)
            return True
        except:
            return False

    # ------------ MyCommon::ConvertCelsiusToFahrenheit -------------------------
    def ConvertCelsiusToFahrenheit(self, Celsius):

        return (Celsius * 9.0 / 5.0) + 32.0

    # ------------ MyCommon::ConvertFahrenheitToCelsius -------------------------
    def ConvertFahrenheitToCelsius(self, Fahrenheit):

        return (Fahrenheit - 32.0) * 5.0 / 9.0

    # ------------ MyCommon::StripJson ------------------------------------------
    def StripJson(self, InputString):
        for char in '{}[]"':
            InputString = InputString.replace(char, "")
        return InputString

    # ------------ MyCommon::DictToString ---------------------------------------
    def DictToString(self, InputDict, ExtraStrip=False):

        if InputDict == None:
            return ""
        ReturnString = json.dumps(
            InputDict, sort_keys=False, indent=4, separators=(" ", ": ")
        )
        if ExtraStrip:
            ReturnString = ReturnString.replace("} \n", "")
        return self.StripJson(ReturnString)

    # ------------ MyCommon::BitIsEqual -----------------------------------------
    def BitIsEqual(self, value, mask, bits):

        newval = value & mask
        if newval == bits:
            return True
        else:
            return False

    # ------------ MyCommon::printToString --------------------------------------
    def printToString(self, msgstr, nonewline=False, spacer=False):

        if spacer:
            MessageStr = "    {0}"
        else:
            MessageStr = "{0}"

        if not nonewline:
            MessageStr += "\n"

        # print (MessageStr.format(msgstr), end='')
        newtpl = (MessageStr.format(msgstr),)
        return newtpl[0]

        # end printToString

    # ---------- MyCommon:FindDictValueInListByKey ------------------------------
    def FindDictValueInListByKey(self, key, listname):

        try:
            for item in listname:
                if isinstance(item, dict):
                    for dictkey, value in item.items():
                        if dictkey.lower() == key.lower():
                            return value
        except Exception as e1:
            self.LogErrorLine("Error in FindDictInList: " + str(e1))
        return None

    # ----------  MyCommon::removeNonPrintable-----------------------------------
    def removeNonPrintable(self, inputStr):

        try:
            import re

            # remove any non printable chars
            inputStr = re.sub(r"[^\x20-\x7f]", r"", inputStr)
            return inputStr
        except:
            return inputStr

    # ----------  MyCommon::removeAlpha------------------------------------------
    # used to remove alpha characters from string so the string contains a
    # float value (leaves all special characters)
    def removeAlpha(self, inputStr):
        answer = ""
        for char in inputStr:
            if not char.isalpha() and char != " " and char != "%":
                answer += char

        return answer.strip()

    # ------------ MyCommon::ConvertToNumber------------------------------------
    # convert a string to an int or float, removes non string characters
    def ConvertToNumber(self, value):
        try:
            return_value = re.sub('[^0-9.\-]','',value)
            try:
                return_value = int(return_value)
            except:
                return_value = float(return_value)
            return return_value
        except Exception as e1:
             self.LogErrorLine("Error in MyMQTT:ConvertToNumber: " + str(e1) + ": " + str(value))
             return 0
    # ------------ MyCommon::MergeDicts -----------------------------------------
    def MergeDicts(self, x, y):
        # Given two dicts, merge them into a new dict as a shallow copy.
        z = x.copy()
        z.update(y)
        return z

    # ---------------------MyCommon:urljoin--------------------------------------
    def urljoin(self, *parts):
        # first strip extra forward slashes (except http:// and the likes) and
        # create list
        part_list = []
        for part in parts:
            p = str(part)
            if p.endswith("//"):
                p = p[0:-1]
            else:
                p = p.strip("/")
            part_list.append(p)
        # join everything together
        url = "/".join(part_list)
        return url

    # -------------MyCommon::LogHexList------------------------------------------
    def LogHexList(self, listname, prefix=None, nolog = False):

        try:
            outstr = ""
            outstr = "[" + ",".join("0x{:02x}".format(num) for num in listname) + "]"
            if prefix != None:
                outstr = prefix + " = " + outstr

            if nolog == False:
                self.LogError(outstr)
            return outstr
        except Exception as e1:
            self.LogErrorLine("Error in LogHexList: " + str(e1))
            return outstr

    # ---------------------------------------------------------------------------
    def LogInfo(self, message, LogLine=False):

        if not LogLine:
            self.LogError(message)
        else:
            self.LogErrorLine(message)
        self.LogConsole(message)

    # ---------------------MyCommon::LogConsole------------------------------------
    def LogConsole(self, Message, Error=None):
        if not self.console == None:
            self.console.error(Message)

    # ---------------------MyCommon::LogError------------------------------------
    def LogError(self, Message, Error=None):
        if not self.log == None:
            if Error != None:
                Message = Message + " : " + self.GetErrorString(Error)
            self.log.error(Message)

    # ---------------------MyCommon::FatalError----------------------------------
    def FatalError(self, Message, Error=None):
        if Error != None:
            Message = Message + " : " + self.GetErrorString(Error)
        if not self.log == None:
            self.log.error(Message)
        if not self.console == None:
            self.console.error(Message)
        raise Exception(Message)

    # ---------------------MyCommon::LogErrorLine--------------------------------
    def LogErrorLine(self, Message, Error=None):
        if not self.log == None:
            if Error != None:
                Message = Message + " : " + self.GetErrorString(Error)
            self.log.error(Message + " : " + self.GetErrorLine())

    # ---------- MyCommon::LogDebug---------------------------------------------
    def LogDebug(self, Message, Error=None):

        if self.debug:
            self.LogError(Message, Error)

    # ---------------------MyCommon::GetErrorLine--------------------------------
    def GetErrorLine(self):
        exc_type, exc_obj, exc_tb = sys.exc_info()
        if exc_tb == None:
            return ""
        else:
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            lineno = exc_tb.tb_lineno
            return fname + ":" + str(lineno)

    # ---------------------MyCommon::GetErrorString------------------------------
    def GetErrorString(self, Error):

        try:
            return str(Error)
        except:
            return Error
    # ---------------------MyCommon::getSignedNumber-----------------------------
    def getSignedNumber(self, number, bitLength):

        try:
            if isinstance(number, int) and isinstance(bitLength, int):
                mask = (2 ** bitLength) - 1
                if number & (1 << (bitLength - 1)):
                    return number | ~mask
                else:
                    return number & mask
            else:
                return number
        except Exception as e1:
            self.LogErrorLine("Error in getSignedNumber: " + str(e1))
            return number
