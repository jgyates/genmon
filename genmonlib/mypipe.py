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

import os, sys, time, json, multiprocessing
import mythread, mycommon


#------------ MyPipe class -----------------------------------------------------
class MyPipe(mycommon.MyCommon):
    #------------ MyPipe::init--------------------------------------------------
    def __init__(self, name, callback = None, Reuse = False, log = None, simulation = False):
        self.log = log
        self.BasePipeName = name
        self.Simulation = simulation

        if self.Simulation:
            return
        self.PipeName = os.path.dirname(os.path.realpath(__file__)) + "/" + name
        self.ThreadName = "ReadPipeThread" + self.BasePipeName
        self.Callback = callback
        self.PipeLock = multiprocessing.Lock()
        if not Reuse:
            try:
                os.remove(self.PipeName)
            except:
                pass
            os.mkfifo(self.PipeName)
        self.PipeIn = os.open(self.PipeName, os.O_RDONLY | os.O_NONBLOCK)
        self.PipeInDes = os.fdopen(self.PipeIn, "r")
        self.PipeOut = os.open(self.PipeName, os.O_WRONLY | os.O_NONBLOCK)
        self.PipeOutDes = os.fdopen(self.PipeOut, "w")
        self.Threads = {}

        if not self.Callback == None:
            self.Threads[self.ThreadName] = mythread.MyThread(self.ReadPipeThread, Name = self.ThreadName)

    #------------ MyPipe::Write-------------------------------------------------
    def Write(self, data):
        try:
            self.PipeLock.acquire()
            self.PipeOutDes.write( data + "\n")
            self.PipeLock.release()
            self.PipeOutDes.flush()
        except Exception as e1:
            self.LogErrorLine("Error in Pipe Write: " + str(e1))

    #------------ MyPipe::Read--------------------------------------------------
    def Read(self):

        try:
            return self.PipeInDes.readline()[:-1]
        except:
            return ""

    #------------ MyPipe::ReadPipeThread----------------------------------------
    def ReadPipeThread(self):

        while True:
            time.sleep(0.5)
            if self.Threads[self.ThreadName].StopSignaled():
                return

            Value = self.Read()
            if len(Value):
                self.Callback(Value)
    #----------------MyPipe::SendFeedback---------------------------------------
    def SendFeedback(self,Reason, Always = False, Message = None, FullLogs = False):

        if self.Simulation:
            return

        try:
            FeedbackDict = {}
            FeedbackDict["Reason"] = Reason
            FeedbackDict["Always"] = Always
            FeedbackDict["Message"] = Message
            FeedbackDict["FullLogs"] = FullLogs

            data = json.dumps(FeedbackDict, sort_keys=False)
            self.Write(data)
        except Exception as e1:
            self.LogErrorLine("Error in SendFeedback: " + str(e1))

    #----------------MyPipe::SendMessage----------------------------------------
    def SendMessage(self,subjectstr, msgstr, recipient = None, files = None, deletefile = False, msgtype = "error"):

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

            data = json.dumps(MessageDict, sort_keys=False)
            self.Write(data)
        except Exception as e1:
            self.LogErrorLine("Error in SendMessage: " + str(e1))

    #------------ MyPipe::Close-------------------------------------------------
    def Close(self):

        if self.Simulation:
            return

        if not self.Callback == None:
            if self.Threads[self.ThreadName].IsAlive():
                self.Threads[self.ThreadName].Stop()
                self.Threads[self.ThreadName].WaitForThreadToEnd()
                del self.Threads[self.ThreadName]

        os.close(self.PipeIn)
        os.close(self.PipeOut)
