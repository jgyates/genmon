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

#------------ MyCommon class -----------------------------------------------------
class MyCommon(object):
    def __init__(self):
        self.log = None
        self.console = None
        self.Threads = {}       # Dict of mythread objects
        self.MaintainerAddress = "generatormonitor.software@gmail.com"
        pass
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
            if not char.isalpha():
                answer += char
        return answer
    #------------ MyCommon::MergeDicts -----------------------------------------
    def MergeDicts(self, x, y):
        #Given two dicts, merge them into a new dict as a shallow copy.
        z = x.copy()
        z.update(y)
        return z

    #---------------------------------------------------------------------------
    def LogInfo(self, message, LogLine = False):

        if not LogLine:
            self.LogError(message)
        else:
            self.LogErrorLine(message)
        self.LogConsole(message)
    #---------------------MyCommon::LogConsole------------------------------------
    def LogConsole(self, Message):
        if not self.console == None:
            self.console.error(Message)

    #---------------------MyCommon::LogError------------------------------------
    def LogError(self, Message):
        if not self.log == None:
            self.log.error(Message)
    #---------------------MyCommon::FatalError----------------------------------
    def FatalError(self, Message):
        if not self.log == None:
            self.log.error(Message)
        raise Exception(Message)
    #---------------------MyCommon::LogErrorLine--------------------------------
    def LogErrorLine(self, Message):
        if not self.log == None:
            self.log.error(Message + " : " + self.GetErrorLine())

    #---------------------MyCommon::GetErrorLine--------------------------------
    def GetErrorLine(self):
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        lineno = exc_tb.tb_lineno
        return fname + ":" + str(lineno)
