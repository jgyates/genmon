#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: mysupport.py
# PURPOSE: support functions in major classes
#
#  AUTHOR: Jason G Yates
#    DATE: 21-Apr-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import os, sys, time, collections, threading

from genmonlib import mycommon

#------------ MySupport class -----------------------------------------------------
class MySupport(mycommon.MyCommon):
    def __init__(self, simulation = False):
        super(MySupport, self).__init__()
        self.Simulation = simulation
        self.CriticalLock = threading.Lock()        # Critical Lock (writing conf file)

    #------------ MySupport::LogToFile-------------------------
    def LogToFile(self, File, TimeDate, Value):
        if self.Simulation:
            return
        if not len(File):
            return ""

        try:
            with open(File,"a") as LogFile:     #opens file
                LogFile.write(TimeDate + "," + Value + "\n")
                LogFile.flush()
        except Exception as e1:
            self.LogError("Error in  LogToFile : File: %s: %s " % (File,str(e1)))

    # ---------- MySupport::KillThread------------------
    def KillThread(self, Name, CleanupSelf = False):

        try:
            MyThreadObj = self.Threads.get(Name, None)
            if MyThreadObj == None:
                self.LogError("Error getting thread name in KillThread: " + Name)
                return False

            if not CleanupSelf:
                MyThreadObj.Stop()
                MyThreadObj.WaitForThreadToEnd()
        except Exception as e1:
            self.LogError("Error in KillThread ( " + Name  + "): " + str(e1))
            return

    # ---------- MySupport::IsStopSignaled------------------
    def IsStopSignaled(self, Name):

        Thread = self.Threads.get(Name, None)
        if Thread == None:
            self.LogError("Error getting thread name in IsStopSignaled: " + Name)
            return False

        return Thread.StopSignaled()

    # ---------- MySupport::WaitForExit-----------------------------------------
    def WaitForExit(self, Name, timeout = None):

        Thread = self.Threads.get(Name, None)
        if Thread == None:
            self.LogError("Error getting thread name in WaitForExit: " + Name)
            return False

        return Thread.Wait(timeout)
    #---------------------MySupport::AddItemToConfFile------------------------
    # Add or update config item
    def AddItemToConfFile(self, Entry, Value):

        if self.Simulation:
            return
        FileName = "/etc/genmon.conf"
        try:
            with self.CriticalLock:
                Found = False
                ConfigFile = open(FileName,'r')
                FileString = ConfigFile.read()
                ConfigFile.close()

                ConfigFile = open(FileName,'w')
                for line in FileString.splitlines():
                    if not line.isspace():                  # blank lines
                        newLine = line.strip()              # strip leading spaces
                        if len(newLine):
                            if not newLine[0] == "#":           # not a comment
                                items = newLine.split(' ')      # split items in line by spaces
                                for strings in items:           # loop thru items
                                    strings = strings.strip()   # strip any whitespace
                                    if Entry == strings or strings.lower().startswith(Entry+"="):        # is this our value?
                                        line = Entry + " = " + Value    # replace it
                                        Found = True
                                        break

                    ConfigFile.write(line+"\n")
                if not Found:
                    ConfigFile.write(Entry + " = " + Value + "\n")
                ConfigFile.close()
            return True

        except Exception as e1:
            self.LogError("Error in AddItemToConfFile: " + str(e1))
            return False

    #------------ MySupport::GetDispatchItem ------------------------------------
    def GetDispatchItem(self, item):

        if isinstance(item, str):
            return item
        if isinstance(item, unicode):
            return str(item)
        elif callable(item):
            return item()
        elif isinstance(item, (int, long)):
            return str(item)
        else:
            self.LogError("Unable to convert type %s in GetDispatchItem" % type(item))
            self.LogError("Item: " + str(item))
            return ""

    #------------ MySupport::ProcessDispatch ------------------------------------
    # This function is recursive, it will turn a dict with callable functions into
    # all of the callable functions resolved to stings (by calling the functions).
    # If string output is needed instead of a dict output, ProcessDispatchToString
    # is called
    def ProcessDispatch(self, node, InputBuffer, indent=0):

        if isinstance(InputBuffer, str):
            return self.ProcessDispatchToString(node, InputBuffer, indent)

        if isinstance(node, dict):
            for key, item in node.items():
                if isinstance(item, dict):
                    NewDict = collections.OrderedDict()
                    InputBuffer[key] = self.ProcessDispatch(item, NewDict)
                elif isinstance(item, list):
                    InputBuffer[key] = []
                    for listitem in item:
                        if isinstance(listitem, dict):
                            NewDict2 = collections.OrderedDict()
                            InputBuffer[key].append(self.ProcessDispatch(listitem, NewDict2))
                        else:
                            self.LogError("Invalid type in ProcessDispatch %s " % type(node))
                else:
                    InputBuffer[key] = self.GetDispatchItem(item)
        else:
            self.LogError("Invalid type in ProcessDispatch %s " % type(node))

        return InputBuffer

     #------------ MySupport::ProcessDispatchToString ---------------------------
     # This function is recursive, it will turn a dict with callable functions into
     # a printable string with indentation and formatting
    def ProcessDispatchToString(self, node, InputBuffer, indent = 0):

        if not isinstance(InputBuffer, str):
            return ""

        if isinstance(node, dict):
            for key, item in node.items():
                if isinstance(item, dict):
                    InputBuffer += "\n" + ("    " * indent) + str(key) + " : \n"
                    InputBuffer = self.ProcessDispatchToString(item, InputBuffer, indent + 1)
                elif isinstance(item, list):
                    InputBuffer += "\n" + ("    " * indent) + str(key) + " : \n"
                    for listitem in item:
                        if isinstance(listitem, dict):
                            InputBuffer = self.ProcessDispatchToString(listitem, InputBuffer, indent + 1)
                        elif isinstance(listitem, str):
                            InputBuffer += (("    " * (indent +1)) +  self.GetDispatchItem(listitem) + "\n")
                        else:
                            self.LogError("Invalid type in ProcessDispatchToString %s %s (2)" % (key, type(listitem)))
                else:
                    InputBuffer += (("    " * indent) + str(key) + " : " +  self.GetDispatchItem(item) + "\n")
        else:
            self.LogError("Invalid type in ProcessDispatchToString %s " % type(node))
        return InputBuffer

    #----------  Controller::GetNumBitsChanged-------------------------------
    def GetNumBitsChanged(self, FromValue, ToValue):

        MaskBitsChanged = int(FromValue, 16) ^ int(ToValue, 16)
        NumBitsChanged = MaskBitsChanged
        count = 0
        while (NumBitsChanged):
            count += NumBitsChanged & 1
            NumBitsChanged >>= 1

        return count, MaskBitsChanged

    #----------  MySupport::GetDeltaTimeMinutes-------------------------------
    def GetDeltaTimeMinutes(self, DeltaTime):

        days, seconds = DeltaTime.days, DeltaTime.seconds
        delta_hours = days * 24 + seconds // 3600
        delta_minutes = (seconds % 3600) // 60

        return (delta_hours * 60 + delta_minutes)
