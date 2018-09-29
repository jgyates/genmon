#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: myserialtcp.py
# PURPOSE: Base serial over TCP comms for modbus
#
#  AUTHOR: Jason G Yates
#    DATE: 19-Apr-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

from __future__ import print_function       # For python 3.x compatibility with print function

import datetime, threading, sys, socket, time
import mylog, mythread, mysupport


#------------ SerialTCPDevice class --------------------------------------------
class SerialTCPDevice(mysupport.MySupport):
    def __init__(self, loglocation = "/var/log/", log = None, host="127.0.0.1", port=8899):
        super(SerialTCPDevice, self).__init__()
        self.DeviceName = "serialTCP"
        self.Buffer = []
        self.BufferLock = threading.Lock()
        self.DiscardedBytes = 0
        self.Restarts = 0
        self.SerialStartTime = datetime.datetime.now()     # used for com metrics
        self.rxdatasize = 2000
        self.host = host
        self.port = port

        # log errors in this module to a file
        self.console = mylog.SetupLogger("myserialtcp_console", log_file = "", stream = True)
        if log == None:
            self.log = mylog.SetupLogger("myserialtcp", loglocation + "myserialtcp.log")
        else:
            self.log = log

        #Starting serial connection
        self.Connect()

        self.IsOpen = True
        self.StartReadThread()

    #----------  SerialTCPDevice::Connect --------------------------------------
    def Connect(self):

        #retries = 0
        #while True:

        try:
            #create an INET, STREAMing socket
            self.Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.Socket.settimeout(1)
            #now connect to the server on our port
            self.Socket.connect((self.host, self.port))
            self.Flush()
            return True
        except Exception as e1:
            #retries += 1
            #if retries >= 3:
            self.LogError("Error: Connect : " + str(e1))
            self.console.error("Unable to make TCP connection.")
            self.Socket = None
            return False
                #else:
            #        time.sleep(1)
            #        continue
    # ---------- SerialTCPDevice::ResetSerialStats------------------------------
    def ResetSerialStats(self):
        # resets status that are time based (affected by a time change)
        self.SerialStartTime = datetime.datetime.now()     # used for com metrics
    # ---------- SerialTCPDevice::StartReadThread-------------------------------
    def StartReadThread(self):

        # start read thread to monitor incoming data commands
        self.Threads["SerialTCPReadThread"] = mythread.MyThread(self.ReadThread, Name = "SerialTCPReadThread")

        return self.Threads["SerialTCPReadThread"]

    # ---------- SerialTCPDevice::ReadThread------------------------------------
    def ReadThread(self):
        while True:
            try:
                self.Flush()
                while True:

                    if self.Socket == None:
                        if not self.Connect():
                            if self.WaitForExit("SerialTCPReadThread", 10):  # 10 seconds
                                return
                            continue
                    for c in self.Read():
                        with self.BufferLock:
                            if sys.version_info[0] < 3:
                                self.Buffer.append(ord(c))      # PYTHON2
                            else:
                                self.Buffer.append(c)           # PYTHON3
                        # first check for SignalStopped is when we are receiving
                        if self.IsStopSignaled("SerialTCPReadThread"):
                            return
                    # second check for SignalStopped is when we are not receiving
                    if self.IsStopSignaled("SerialTCPReadThread"):
                        return

            except Exception as e1:
                self.LogErrorLine( "Resetting SerialTCPDevice:ReadThread Error: " + self.DeviceName + ":"+ str(e1))
                # if we get here then this is likely due to the following exception:
                #  "device reports readiness to read but returned no data (device disconnected?)"
                #  This is believed to be a kernel issue so let's just reset the device and hope
                #  for the best (actually this works)
                self.Restarts += 1
                self.Close()
                self.Connect()

    #------------SerialTCPDevice::DiscardByte-----------------------------------
    def DiscardByte(self):

        if len(self.Buffer):
            discard = self.Buffer.pop(0)
            self.DiscardedBytes += 1
            return discard

    # ---------- SerialTCPDevice::Close-----------------------------------------
    def Close(self):
        try:
            if self.IsOpen:
                self.KillThread("SerialTCPReadThread")
                # close socket
                if self.Socket != None:
                    self.Socket.close()
                self.IsOpen = False
        except Exception as e1:
            self.LogErrorLine( "Error in SerialTCPDevice:Close : " + str(e1))

    # ---------- SerialTCPDevice::Flush-----------------------------------------
    def Flush(self):
        try:
            # Flush socket
            with self.BufferLock:               # will block if lock is already held
                del self.Buffer[:]

        except Exception as e1:
            self.LogErrorLine( "Error in SerialTCPDevice:Flush : " + str(e1))

    # ---------- SerialTCPDevice::Read------------------------------------------
    def Read(self):
        try:
            if self.Socket == None:
                return ""
            data = self.Socket.recv(self.rxdatasize)
            return  data
        except socket.timeout as err:
            return ""
        except Exception as e1:
            self.LogErrorLine( "Error in SerialTCPDevice:Read : " + str(e1))
            return ""

    # ---------- SerialTCPDevice::Write-----------------------------------------
    def Write(self, data):

        try:
            if self.Socket == None:
                return None
            return self.Socket.sendall(data)
        except Exception as e1:
            self.LogErrorLine( "Error in SerialTCPDevice:Write : " + str(e1))
            return 0

    # ---------- SerialTCPDevice::GetRxBufferAsString---------------------------
    def GetRxBufferAsString(self):

        try:
            if not len(self.Buffer):
                return ""
            with self.BufferLock:
                str1 = ''.join(chr(e) for e in self.Buffer)
            return str1
        except Exception as e1:
            self.LogErrorLine("Error in SerialTCPDevice:GetRxBufferAsString: " + str(e1))
            return ""
