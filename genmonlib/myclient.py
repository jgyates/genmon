#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: myclient.py
# PURPOSE:
#
#  AUTHOR: Jason G Yates
#    DATE: 5-Apr-2017
# MODIFICATIONS:
#------------------------------------------------------------
import datetime, time, sys, smtplib, signal, os, threading, socket
import mylog, mycommon

#----------  ClientInterface::init--- ------------------------------------------
class ClientInterface(mycommon.MyCommon):
    def __init__(self, host="127.0.0.1", port=9082, log = None):

        if log != None:
            self.log = log
        else:
            # log errors in this module to a file
            self.log = mylog.SetupLogger("client", "/var/log/myclient.log")

        self.AccessLock = threading.RLock()
        self.EndOfMessage = "EndOfMessage"
        self.rxdatasize = 2000
        self.host = host
        self.port = port

        self.Connect()

    #----------  ClientInterface::Connect ---------------------------------
    def Connect(self):

        retries = 0
        while True:

            try:
                #create an INET, STREAMing socket
                self.Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                #now connect to the server on our port
                self.Socket.connect((self.host, self.port))
                sRetData, data = self.Receive(noeom = True)       # Get initial status before commands are sent
                #print(data)
                return
            except Exception as e1:
                retries += 1
                if retries >= 3:
                    self.FatalError("Error: Connect : " + str(e1))
                else:
                    time.sleep(1)
                    continue


    #----------  ClientInterface::SendCommand ---------------------------------
    def SendCommand(self, cmd):

        try:
            self.Socket.sendall(cmd.encode())
        except Exception as e1:
            self.LogError( "Error: TX: " + str(e1))
            self.Close()
            self.Connect()

    #----------  ClientInterface::Receive ---------------------------------
    def Receive(self, noeom = False):

        with self.AccessLock:
            RetStatus = True
            try:
                bytedata = self.Socket.recv(self.rxdatasize)
                data = bytedata.decode()
                if len(data):
                    if not self.CheckForStarupMessage(data) or not noeom:
                        while not self.EndOfMessage in data:
                            morebytes = self.Socket.recv(self.rxdatasize)
                            more = morebytes.decode()
                            if len(more):
                                if self.CheckForStarupMessage(more):
                                    data = ""
                                    RetStatus = False
                                    break
                                data += more

                        if data.endswith(self.EndOfMessage):
                            data = data[:-len(self.EndOfMessage)]
                            RetStatus = True
                else:
                    self.Connect()
                    return False, data
            except Exception as e1:
                self.LogError( "Error: RX:" + str(e1))
                self.Close()
                self.Connect()
                RetStatus = False
                data = "Retry"

            return RetStatus, data

    #----------  ClientInterface::CheckForStarupMessage ---------------------------------
    def CheckForStarupMessage(self, data):

        # check for initial status response from monitor
        if data.startswith("OK") or data.startswith("CRITICAL:") or data.startswith("WARNING:"):
            return True
        else:
            return False

    #----------  ClientInterface::Close ---------------------------------
    def Close(self):
        self.Socket.close()

    #----------  ClientInterface::ProcessMonitorCommand ---------------------------------
    def ProcessMonitorCommand(self, cmd):

        data = ""
        try:
            with self.AccessLock:
                RetStatus = False
                while RetStatus == False:
                    self.SendCommand(cmd)
                    RetStatus, data = self.Receive()
        except Exception as e1:
            self.LogError("Error in ProcessMonitorCommand:" + str(e1))
        return data
