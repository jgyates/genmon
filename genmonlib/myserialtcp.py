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

import datetime, threading, sys, socket, time, os

from genmonlib.mysupport import MySupport
from genmonlib.mylog import SetupLogger
from genmonlib.mythread import MyThread
from genmonlib.program_defaults import ProgramDefaults

#------------ SerialTCPDevice class --------------------------------------------
class SerialTCPDevice(MySupport):
    def __init__(self,
        log = None,
        host = ProgramDefaults.LocalHost,
        port = 8899,
        config = None):

        super(SerialTCPDevice, self).__init__()
        self.DeviceName = "serialTCP"
        self.config = config
        self.Buffer = []
        self.BufferLock = threading.Lock()
        self.DiscardedBytes = 0
        self.Restarts = 0
        self.SerialStartTime = datetime.datetime.now()     # used for com metrics
        self.rxdatasize = 2000
        self.SocketTimeout = 1

        self.host = host
        self.port = port

        if self.config != None:
            self.loglocation = self.config.ReadValue('loglocation', default = '/var/log/')
            self.host = self.config.ReadValue('serial_tcp_address', return_type = str, default = None)
            self.port = self.config.ReadValue('serial_tcp_port', return_type = int, default = None, NoLog = True)
        else:
            self.loglocation = default = './'

        # log errors in this module to a file
        self.console = SetupLogger("myserialtcp_console", log_file = "", stream = True)
        if log == None:
            self.log = SetupLogger("myserialtcp", os.path.join(self.loglocation, "myserialtcp.log"))
        else:
            self.log = log

        if self.host == None or self.port == None:
            self.LogError("Invalid setting for host or port in myserialtcp")
        #Starting tcp connection
        self.Connect()

        self.IsOpen = True
        self.StartReadThread()

    #----------  SerialTCPDevice::Connect --------------------------------------
    def Connect(self):

        try:
            #create an INET, STREAMing socket
            self.Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.Socket.settimeout(self.SocketTimeout)
            #now connect to the server on our port
            self.Socket.connect((self.host, self.port))
            self.Flush()
            return True
        except Exception as e1:
            self.LogError("Error: Connect : " + str(e1))
            self.console.error("Unable to make TCP connection.")
            self.Socket = None
            return False

    # ---------- SerialTCPDevice::ResetSerialStats------------------------------
    def ResetSerialStats(self):
        # resets status that are time based (affected by a time change)
        self.SerialStartTime = datetime.datetime.now()     # used for com metrics
    # ---------- SerialTCPDevice::StartReadThread-------------------------------
    def StartReadThread(self):

        # start read thread to monitor incoming data commands
        self.Threads["SerialTCPReadThread"] = MyThread(self.ReadThread, Name = "SerialTCPReadThread")

        return self.Threads["SerialTCPReadThread"]

    # ---------- SerialTCPDevice::ReadThread------------------------------------
    def ReadThread(self):
        while True:
            try:
                self.Flush()
                while True:

                    if self.Socket == None:
                        self.Restarts += 1
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
                if self.Socket != None:
                    self.Socket.close()
                    self.Socket = None
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
                    self.Socket = None
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
            if data == None:
                return ""
            return  data
        except socket.timeout as err:
            return ""
        except socket.error as err:
            self.LogErrorLine( "Error in SerialTCPDevice:Read socket error: " + str(err))
            if self.Socket != None:
                self.Socket.close()
                self.Socket = None
        except Exception as e1:
            self.LogErrorLine( "Error in SerialTCPDevice:Read : " + str(e1))
            if self.Socket != None:
                self.Socket.close()
                self.Socket = None
            return ""

    # ---------- SerialTCPDevice::Write-----------------------------------------
    def Write(self, data):

        try:
            if self.Socket == None:
                return None
            return self.Socket.sendall(data)
        except Exception as e1:
            if self.Socket != None:
                self.Socket.close()
                self.Socket = None
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
