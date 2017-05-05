#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: mynotify.py
# PURPOSE:
#
#  AUTHOR: Jason G Yates
#    DATE: 25-Apr-2017
# MODIFICATIONS:
#------------------------------------------------------------
import datetime, time, sys, signal, os, threading
import myclient, mylog

#----------  GenNotify::init--- ------------------------------------------
class GenNotify:
    def __init__(self,
                host="127.0.0.1",
                port=9082,
                log = None,
                onready = None,
                onexercise = None,
                onrun = None,
                onrunmanual = None,
                onalarm = None,
                onservice = None,
                onoff = None,
                onmanual = None):

        self.ThreadList = []
        self.LastEvent = None
        self.Events = {}            # Dict for handling events

        if log != None:
            self.log = log
        else:
            # log errors in this module to a file
            self.log = mylog.SetupLogger("client", "/var/log/myclient.log")

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

        self.Generator = myclient.ClientInterface(host = host, log = log)

        # start thread to accept incoming sockets for nagios heartbeat
        self.StartThread(self.MainPollingThread, Name = "PollingThread")


    # ---------- GenNotify::StartThread------------------
    def StartThread(self, ThreadFunction, Name = None):

        ThreadObj = threading.Thread(target=ThreadFunction, name = Name)
        ThreadObj.daemon = True
        ThreadObj.start()       # start thread
        self.ThreadList.append(ThreadObj)

    # ---------- GenNotify::MainPollingThread------------------
    def MainPollingThread(self):

        while True:

            data = self.Generator.ProcessMonitorCommand("generator: getbase")

            if self.LastEvent == data:
                time.sleep(3)
                continue

            self.CallEventHandler(False)     # end last event

            self.LastEvent = data

            self.CallEventHandler(True)      # begin new event

            time.sleep(3)

    #----------  GenNotify::Close ---------------------------------
    def CallEventHandler(self, Status):

        EventCallback = self.Events.get(self.LastEvent, None)
        # Event has ended
        if EventCallback != None:
            EventCallback(Status)


    #----------  GenNotify::Close ---------------------------------
    def Close(self):

        self.Generator.Close()
        return False
