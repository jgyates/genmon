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

import os, sys, time

#------------ MyCommon class -----------------------------------------------------
class MyCommon(object):
    def __init__(self):
        self.log = None
        pass

    #------------ MyCommon::BitIsEqual -----------------------------------------
    def BitIsEqual(self, value, mask, bits):

        newval = value & mask
        if (newval == bits):
            return True
        else:
            return False

    #------------ MyCommon::printToString --------------------------------------------
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

    #----------  MyCommon::removeAlpha--------------------------
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

    #---------------------MyCommon::LogError------------------------
    def LogError(self, Message):
        self.log.error(Message)
    #---------------------MyCommon::FatalError------------------------
    def FatalError(self, Message):

        self.log.error(Message)
        raise Exception(Message)

    #---------------------MyCommon::GetErrorLine------------------------
    def GetErrorLine(self):
        return sys.exc_info()[-1].tb_lineno
