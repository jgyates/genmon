#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: mycommon.py
# PURPOSE: common functions in all classes
#
#  AUTHOR: Jason G Yates
#    DATE: 21-Apr-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import os, sys, time, json

from genmonlib.program_defaults import ProgramDefaults

#------------ MyCommon class -----------------------------------------------------
class MyCommon(object):
    DefaultConfPath = ProgramDefaults.ConfPath
    def __init__(self):
        self.log = None
        self.console = None
        self.Threads = {}       # Dict of mythread objects
        self.debug = False
        self.MaintainerAddress = "generatormonitor.software@gmail.com"

    #------------ MyCommon::StringIsInt ----------------------------------------
    def StringIsInt(self, value):

        try:
            temp = int(value)
            return True
        except:
            return False

    #------------ MyCommon::ConvertCelsiusToFahrenheit -------------------------
    def ConvertCelsiusToFahrenheit(self, Celsius):

        return ((Celsius * 9.0/5.0) + 32.0)

    #------------ MyCommon::ConvertFahrenheitToCelsius -------------------------
    def ConvertFahrenheitToCelsius(self, Fahrenheit):

        return ((Fahrenheit - 32.0) * 5.0/9.0)

    #------------ MyCommon::StripJson ------------------------------------------
    def StripJson(self, InputString):
        for char in '{}[]"':
            InputString = InputString.replace(char,'')
        return InputString

    #------------ MyCommon::DictToString ---------------------------------------
    def DictToString(self, InputDict, ExtraStrip = False):

        if InputDict == None:
            return ""
        ReturnString = json.dumps(InputDict,sort_keys=False, indent = 4, separators=(' ', ': '))
        if ExtraStrip:
            ReturnString = ReturnString.replace("} \n","")
        return self.StripJson(ReturnString)

    #------------ MyCommon::BitIsEqual -----------------------------------------
    def BitIsEqual(self, value, mask, bits):

        newval = value & mask
        if (newval == bits):
            return True
        else:
            return False

    #------------ MyCommon::printToString --------------------------------------
    def printToString(self, msgstr, nonewline = False, spacer = False):

        if spacer:
            MessageStr = "    {0}"
        else:
            MessageStr = "{0}"

        if not nonewline:
            MessageStr += "\n"

        #print (MessageStr.format(msgstr), end='')
        newtpl = MessageStr.format(msgstr),
        return newtpl[0]

        # end printToString

    #---------- MyCommon:FindDictValueInListByKey ------------------------------
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
    #----------  MyCommon::removeAlpha------------------------------------------
    # used to remove alpha characters from string so the string contains a
    # float value (leaves all special characters)
    def removeAlpha(self, inputStr):
        answer = ""
        for char in inputStr:
            if not char.isalpha() and char != ' ':
                answer += char
        return answer.strip()
    #------------ MyCommon::MergeDicts -----------------------------------------
    def MergeDicts(self, x, y):
        #Given two dicts, merge them into a new dict as a shallow copy.
        z = x.copy()
        z.update(y)
        return z

    #---------------------MyCommon:urljoin--------------------------------------
    def urljoin(self, *parts):
        # first strip extra forward slashes (except http:// and the likes) and
        # create list
        part_list = []
        for part in parts:
            p = str(part)
            if p.endswith('//'):
                p = p[0:-1]
            else:
                p = p.strip('/')
            part_list.append(p)
        # join everything together
        url = '/'.join(part_list)
        return url

    #-------------MyCommon::LogHexList------------------------------------------
    def LogHexList(self, listname, prefix = None):

        try:
            if prefix != None:
                self.LogError(prefix + " = [" + ",".join("0x{:02x}".format(num) for num in listname) + "]")
            else:
                self.LogError("[" + ",".join("0x{:02x}".format(num) for num in listname) + "]")
        except Exception as e1:
            self.LogErrorLine("Error in LogHexList: " + str(e1))

    #---------------------------------------------------------------------------
    def LogInfo(self, message, LogLine = False):

        if not LogLine:
            self.LogError(message)
        else:
            self.LogErrorLine(message)
        self.LogConsole(message)
    #---------------------MyCommon::LogConsole------------------------------------
    def LogConsole(self, Message, Error = None):
        if not self.console == None:
            self.console.error(Message)

    #---------------------MyCommon::LogError------------------------------------
    def LogError(self, Message, Error = None):
        if not self.log == None:
            if Error != None:
                Message = Message + " : " + self.GetErrorString(Error)
            self.log.error(Message)
    #---------------------MyCommon::FatalError----------------------------------
    def FatalError(self, Message, Error = None):
        if Error != None:
            Message = Message + " : " + self.GetErrorString(Error)
        if not self.log == None:
            self.log.error(Message)
        if not self.console == None:
            self.console.error(Message)
        raise Exception(Message)
    #---------------------MyCommon::LogErrorLine--------------------------------
    def LogErrorLine(self, Message, Error = None):
        if not self.log == None:
            if Error != None:
                Message = Message + " : " + self.GetErrorString(Error)
            self.log.error(Message + " : " + self.GetErrorLine())

    # ---------- MyCommon::LogDebug---------------------------------------------
    def LogDebug(self, Message, Error = None):

        if self.debug:
            self.LogError(Message, Error)
    #---------------------MyCommon::GetErrorLine--------------------------------
    def GetErrorLine(self):
        exc_type, exc_obj, exc_tb = sys.exc_info()
        if exc_tb == None:
            return ""
        else:
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            lineno = exc_tb.tb_lineno
            return fname + ":" + str(lineno)

    #---------------------MyCommon::GetErrorString------------------------------
    def GetErrorString(self, Error):

        try:
            return str(Error)
        except:
            return Error
