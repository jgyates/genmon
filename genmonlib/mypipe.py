#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: mypipe.py
# PURPOSE: pipe wrapper
#
#  AUTHOR: Jason G Yates
#    DATE: 21-Apr-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import os, sys, time, json, threading

from genmonlib.mysupport import MySupport
from genmonlib.mythread import MyThread
from genmonlib.program_defaults import ProgramDefaults

#------------ MyPipe class -----------------------------------------------------
class MyPipe(MySupport):
    #------------ MyPipe::init--------------------------------------------------
    def __init__(self, name, callback = None, Reuse = False, log = None, simulation = False, nullpipe = False, ConfigFilePath = ProgramDefaults.ConfPath):
        super(MyPipe, self).__init__(simulation = simulation)
        self.log = log
        self.BasePipeName = name
        self.NullPipe = nullpipe

        if self.Simulation:
            return

        self.ThreadName = "ReadPipeThread" + self.BasePipeName
        self.Callback = callback

        self.FileAccessLock = threading.RLock()

        self.FileName = os.path.join(ConfigFilePath, self.BasePipeName + "_dat")

        try:
            if not Reuse:
                try:
                    os.remove(self.FileName)
                except:
                    pass
                with open(self.FileName, 'w') as f: # create empty file
                    f.write("")

        except Exception as e1:
            self.LogErrorLine("Error in MyPipe:__init__: " + str(e1))

        if self.NullPipe or not self.Callback == None or not self.Simulation:
            self.Threads[self.ThreadName] = MyThread(self.ReadPipeThread, Name = self.ThreadName)


    #------------ MyPipe::Write-------------------------------------------------
    def WriteFile(self, data):
        try:
            with self.FileAccessLock:
                with open(self.FileName, 'a') as f:
                    f.write(data + "\n")
                    f.flush()

        except Exception as e1:
            self.LogErrorLine("Error in Pipe WriteFile: " + str(e1))

    #------------ MyPipe::ReadLines---------------------------------------------
    def ReadLines(self):

        try:
            with self.FileAccessLock:
                with open(self.FileName, 'r') as f:
                    lines = f.readlines()
                open(self.FileName, 'w').close()
            return lines
        except Exception as e1:
            self.LogErrorLine("Error in mypipe::ReadLines: " + str(e1))
            return []

    #------------ MyPipe::ReadPipeThread----------------------------------------
    def ReadPipeThread(self):

        time.sleep(1)
        while True:
            try:
                if self.WaitForExit(self.ThreadName, 2):  #
                    return
                # since realines is blocking, check if the file is non zero before we attempt to read
                if not os.path.getsize(self.FileName):
                    continue

                ValueList = self.ReadLines()
                if len(ValueList):
                    for Value in ValueList:
                        if len(Value):
                            self.Callback(Value)
            except Exception as e1:
                self.LogErrorLine("Error in ReadPipeThread: " + str(e1))

    #----------------MyPipe::SendFeedback---------------------------------------
    def SendFeedback(self,Reason, Always = False, Message = None, FullLogs = False, NoCheck = False):

        if self.Simulation:
            return

        try:
            FeedbackDict = {}
            FeedbackDict["Reason"] = Reason
            FeedbackDict["Always"] = Always
            FeedbackDict["Message"] = Message
            FeedbackDict["FullLogs"] = FullLogs
            FeedbackDict["NoCheck"] = NoCheck

            data = json.dumps(FeedbackDict, sort_keys=False)
            self.WriteFile(data)
        except Exception as e1:
            self.LogErrorLine("Error in SendFeedback: " + str(e1))

    #----------------MyPipe::SendMessage----------------------------------------
    def SendMessage(self,subjectstr, msgstr, recipient = None, files = None, deletefile = False, msgtype = "error", onlyonce = False):

        if self.Simulation:
            return
        try:
            MessageDict = {}
            MessageDict["subjectstr"] = subjectstr
            MessageDict["msgstr"] = msgstr
            MessageDict["recipient"] = recipient
            MessageDict["files"] = files
            MessageDict["deletefile"] = deletefile
            MessageDict["msgtype"] = msgtype
            MessageDict["onlyonce"] = onlyonce

            data = json.dumps(MessageDict, sort_keys=False)
            self.WriteFile(data)
        except Exception as e1:
            self.LogErrorLine("Error in SendMessage: <" + (str(subjectstr)) + "> : "+ str(e1))

    #------------ MyPipe::Close-------------------------------------------------
    def Close(self):

        if self.Simulation:
            return

        try:
            if not self.Callback == None:
                self.KillThread(self.ThreadName)
        except Exception as e1:
            self.LogErrorLine("Error in mypipe:Close: " + str(e1))
