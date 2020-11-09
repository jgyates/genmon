#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: mynotify.py
# PURPOSE:
#
#  AUTHOR: Jason G Yates
#    DATE: 25-Apr-2017
# MODIFICATIONS:
#-------------------------------------------------------------------------------
import datetime, time, sys, signal, os, threading, json, collections

from genmonlib.mycommon import MyCommon
from genmonlib.mylog import SetupLogger
from genmonlib.mythread import MyThread
from genmonlib.myclient import ClientInterface
from genmonlib.program_defaults import ProgramDefaults
#----------  GenNotify::init--- ------------------------------------------------
class GenNotify(MyCommon):
    def __init__(self,
                host=ProgramDefaults.LocalHost,
                port=ProgramDefaults.ServerPort,
                log = None,
                loglocation = ProgramDefaults.LogPath,
                onready = None,
                onexercise = None,
                onrun = None,
                onrunmanual = None,
                onalarm = None,
                onservice = None,
                onoff = None,
                onmanual = None,
                onutilitychange = None,
                start = True,
                console = None):

        super(GenNotify, self).__init__()

        self.AccessLock = threading.Lock()
        self.Threads = {}
        self.LastEvent = None
        self.LastOutageStatus = None
        self.Events = {}            # Dict for handling events


        self.log = log
        self.console = console
        
        try:
            # init event callbacks
            if onready != None:
                self.Events["READY"] = onready
            if onexercise != None:
                self.Events["EXERCISING"] = onexercise
            if onrun != None:
                self.Events["RUNNING"] = onrun
            if onrunmanual != None:
                self.Events["RUNNING-MANUAL"] = onrunmanual
            if onalarm != None:
                self.Events["ALARM"] = onalarm
            if onservice != None:
                self.Events["SERVICEDUE"] = onservice
            if onoff != None:
                self.Events["OFF"] = onoff
            if onmanual != None:
                self.Events["MANUAL"] = onmanual
            if onutilitychange != None:
                self.Events["OUTAGE"] = onutilitychange


            self.Generator = ClientInterface(host = host, port = port, log = log, loglocation = loglocation)

            self.Threads["PollingThread"] = MyThread(self.MainPollingThread, Name = "PollingThread", start = start)
            self.Started = start
        except Exception as e1:
            self.LogErrorLine("Error in mynotify init: "  + str(e1))

    # ---------- GenNotify::MainPollingThread-----------------------------------
    def StartPollThread(self):

        if not self.Started:
            self.Threads["PollingThread"].Start()
            self.Started = True

    # ---------- GenNotify::MainPollingThread-----------------------------------
    def MainPollingThread(self):

        while True:
            try:

                data = self.SendCommand("generator: getbase")
                OutageState = self.GetOutageState()
                if OutageState != None:
                    self.ProcessOutageState(OutageState)

                if self.LastEvent == data:
                    time.sleep(3)
                    continue
                if self.LastEvent != None:
                    self.console.info( "Last : <" + self.LastEvent + ">, New : <" + data + ">")
                self.CallEventHandler(False)     # end last event

                self.LastEvent = data

                self.CallEventHandler(True)      # begin new event

                time.sleep(3)
            except Exception as e1:
                self.LogErrorLine("Error in mynotify:MainPollingThread: " + str(e1))
                time.sleep(3)

    #----------  GenNotify::GetOutageState -------------------------------------
    def GetOutageState(self):
        OutageState = None
        outagedata = self.SendCommand("generator: outage_json")
        try:
            OutageDict = collections.OrderedDict()
            OutageDict = json.loads(outagedata)
            OutageList = OutageDict["Outage"]
            for Items in OutageList:
                for key, value in Items.items():
                    if key == "System In Outage":
                        if value.lower() == "yes":
                            return True
                        else:
                            return False
        except Exception as e1:
            # The system does no support outage tracking (i.e. H-100)
            self.LogErrorLine("Unable to get outage state: " + str(e1))
            OutageState = None
        return OutageState
    #----------  GenNotify::CallEventHandler -----------------------------------
    def CallEventHandler(self, Status):

        try:
            if self.LastEvent == None:
                return
            EventCallback = self.Events.get(self.LastEvent, None)
            # Event has ended
            if EventCallback != None:
                if callable(EventCallback):
                    EventCallback(Status)
                else:
                    self.LogError("Invalid Callback in CallEventHandler : " + str(EventCallback))
            else:
                self.LogError("Invalid Callback in CallEventHandler : None")
        except Exception as e1:
            self.LogErrorLine("Error in CallEventHandler: " + str(e1))

    #----------  GenNotify::ProcessOutageState ---------------------------------
    def ProcessOutageState(self, outagestate):

        try:
            if self.LastOutageStatus == outagestate:
                return

            self.LastOutageStatus = outagestate
            EventCallback = self.Events.get("OUTAGE", None)

            if EventCallback != None:
                if callable(EventCallback):
                    EventCallback(self.LastOutageStatus)
                else:
                    self.LogError("Invalid Callback in ProcessOutageState : " + str(EventCallback))
            else:
                self.LogError("Invalid Callback in ProcessOutageState : None")
        except Exception as e1:
            self.LogErrorLine("Error in ProcessOutageState: " + str(e1))

    #----------  GenNotify::SendCommand ----------------------------------------
    def SendCommand(self, Command):

        if len(Command) == 0:
            return "Invalid Command"

        try:
            with self.AccessLock:
                data = self.Generator.ProcessMonitorCommand(Command)
        except Exception as e1:
            self.LogErrorLine("Error calling  ProcessMonitorCommand: " + str(Command))
            data = ""

        return data

    #----------  GenNotify::Close ----------------------------------------------
    def Close(self):
        try:
            self.KillThread("PollingThread")
            self.Generator.Close()
        except Exception as e1:
            pass
        return False
