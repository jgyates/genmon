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
                onsoftwareupdate = None,
                onsystemhealth = None,
                onfuelstate = None,
                start = True,
                console = None):

        super(GenNotify, self).__init__()

        self.AccessLock = threading.Lock()
        self.Threads = {}
        self.LastEvent = None
        self.LastOutageStatus = None
        self.LastSoftwareUpdateStatus = None
        self.LastSystemHealth = None
        self.LastFuelWarningStatus = True
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
            if onsoftwareupdate != None:
                self.Events["SOFTWAREUPDATE"] = onsoftwareupdate
            if onsystemhealth != None:
                self.Events["SYSTEMHEALTH"] = onsystemhealth
            if onfuelstate != None:
                self.Events["FUELWARNING"] = onfuelstate


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

                OutageState = self.GetOutageState()
                self.GetMonitorState()
                self.GetMaintState()
                data = self.SendCommand("generator: getbase")

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
                    if key == "Status" and value == "Not Supported":
                        return None
                    if key == "System In Outage":
                        if value.lower() == "yes":
                            OutageState = True
                        else:
                            OutageState = False
        except Exception as e1:
            # The system does no support outage tracking (i.e. H-100)
            self.LogErrorLine("Unable to get outage state: " + str(e1))
            OutageState = None

        if OutageState != None:
            self.ProcessEventData("OUTAGE", OutageState, self.LastOutageStatus)
            self.LastOutageStatus = OutageState

        return OutageState
    #----------  GenNotify::GetMonitorState ------------------------------------
    def GetMonitorState(self):
        UpdateAvailable = None

        try:
            monitordata = self.SendCommand("generator: monitor_json")
            GenDict = collections.OrderedDict()
            GenDict = json.loads(monitordata)
            GenList = GenDict["Monitor"][0]["Generator Monitor Stats"]
            for Items in GenList:
                for key, value in Items.items():
                    if key == "Update Available":
                        if value.lower() == "yes":
                            UpdateAvailable = True
                        else:
                            UpdateAvailable = False
                        self.ProcessEventData("SOFTWAREUPDATE", UpdateAvailable, self.LastSoftwareUpdateStatus)
                        self.LastSoftwareUpdateStatus = UpdateAvailable
                    if key == "Monitor Health":
                        self.ProcessEventData("SYSTEMHEALTH", value, self.LastSystemHealth)
                        self.LastSystemHealth = value
        except Exception as e1:
            # The system does no support outage tracking (i.e. H-100)
            self.LogErrorLine("Unable to get moniotr state: " + str(e1))
            UpdateAvailable = None
        return UpdateAvailable

    #----------  GenNotify::GetMaintState --------------------------------------
    def GetMaintState(self):
        FuelOK = None

        try:
            maintdata = self.SendCommand("generator: maint_json")
            GenDict = collections.OrderedDict()
            GenDict = json.loads(maintdata)
            GenList = GenDict["Maintenance"]
            for Items in GenList:
                for key, value in Items.items():
                    if key == "Fuel Level State":
                        if value.lower() == "ok":
                            FuelOK = True
                        else:
                            FuelOK = False
                        self.ProcessEventData("FUELWARNING", FuelOK, self.LastFuelWarningStatus)
                        self.LastFuelWarningStatus = FuelOK

        except Exception as e1:
            # The system does no support outage tracking (i.e. H-100)
            self.LogErrorLine("Unable to get maint state: " + str(e1))
            FuelOK = None
        return FuelOK
    #----------  GenNotify::ProcessEventData --------------------------------
    def ProcessEventData(self, name, eventdata, lastvalue):

        try:
            if eventdata == None:
                return
            if lastvalue == eventdata:
                return

            lastvalue = eventdata
            EventCallback = self.Events.get(name, None)

            if EventCallback != None:
                if callable(EventCallback):
                    EventCallback(lastvalue)
                else:
                    self.LogError("Invalid Callback in ProcessEventData : " + name + ": " + str(EventCallback))
            else:
                self.LogError("Invalid Callback in ProcessEventData : None : "  + name)
        except Exception as e1:
            self.LogErrorLine("Error in ProcessEventData: "  + name + ": " + str(e1))

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
