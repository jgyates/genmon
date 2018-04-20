#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: myserial.py
# PURPOSE: Base serial comms for modbus
#
#  AUTHOR: Jason G Yates
#    DATE: 19-Apr-2018
#
# MODIFICATIONS:
#------------------------------------------------------------

from __future__ import print_function       # For python 3.x compatibility with print function

import datetime, threading, serial, sys
import mylog, mythread


#------------ SerialDevice class --------------------------------------------
class SerialDevice:
    def __init__(self, name, rate=9600, loglocation = "/var/log/"):
        self.DeviceName = name
        self.BaudRate = rate
        self.Buffer = []
        self.BufferLock = threading.Lock()

        self.RxPacketCount = 0
        self.TxPacketCount = 0
        self.ComTimoutError = 0
        self.TotalElapsedPacketeTime = 0
        self.CrcError = 0
        self.DiscardedBytes = 0
        self.Restarts = 0
        self.SerialStartTime = datetime.datetime.now()     # used for com metrics

        # log errors in this module to a file
        self.log = mylog.SetupLogger("myserial", loglocation + "myserial.log")

        #Starting serial connection
        self.SerialDevice = serial.Serial()
        self.SerialDevice.port = name
        self.SerialDevice.baudrate = rate
        self.SerialDevice.bytesize = serial.EIGHTBITS     #number of bits per bytes
        self.SerialDevice.parity = serial.PARITY_NONE     #set parity check: no parity
        self.SerialDevice.stopbits = serial.STOPBITS_ONE  #number of stop bits
        self.SerialDevice.timeout =  0.05                 # small timeout so we can check if the thread should exit
        self.SerialDevice.xonxoff = False                 #disable software flow control
        self.SerialDevice.rtscts = False                  #disable hardware (RTS/CTS) flow control
        self.SerialDevice.dsrdtr = False                  #disable hardware (DSR/DTR) flow control
        self.SerialDevice.writeTimeout = None             #timeout for write, return when packet sent

        #Check if port failed to open
        if (self.SerialDevice.isOpen() == False):
            try:
                self.SerialDevice.open()
            except Exception as e:
                self.FatalError( "Error on open serial port %s: " % self.DeviceName + str(e))
                return None
        else:
            self.FatalError( "Serial port already open: %s" % self.DeviceName)
            return None

        self.Flush()

    # ---------- SerialDevice::ResetSerialStats------------------
    def ResetSerialStats(self):
        # resets status that are time based (affected by a time change)
        self.SerialStartTime = datetime.datetime.now()     # used for com metrics
        self.RxPacketCount = 0
        self.TxPacketCount = 0
        self.TotalElapsedPacketeTime = 0
    # ---------- SerialDevice::StartReadThread------------------
    def StartReadThread(self):

        # start read thread to monitor incoming data commands
        self.Thread = mythread.MyThread(self.ReadThread, Name = "SerialReadThread")

        return self.Thread

    # ---------- SerialDevice::ReadThread------------------
    def ReadThread(self):
        while True:
            try:
                self.Flush()
                while True:
                    for c in self.Read():
                        with self.BufferLock:
                            if sys.version_info[0] < 3:
                                self.Buffer.append(ord(c))      # PYTHON2
                            else:
                                self.Buffer.append(c)           # PYTHON3
                        # first check for SignalStopped is when we are receiving
                        if self.Thread.StopSignaled():
                            return
                    # second check for SignalStopped is when we are not receiving
                    if self.Thread.StopSignaled():
                            return

            except Exception as e1:
                self.LogError( "Resetting SerialDevice:ReadThread Error: " + self.DeviceName + ":"+ str(e1))
                # if we get here then this is likely due to the following exception:
                #  "device reports readiness to read but returned no data (device disconnected?)"
                #  This is believed to be a kernel issue so let's just reset the device and hope
                #  for the best (actually this works)
                self.Restarts += 1
                self.SerialDevice.close()
                self.SerialDevice.open()

    #------------SerialDevice::DiscardByte------------
    def DiscardByte(self):

        if len(self.Buffer):
            discard = self.Buffer.pop(0)
            self.DiscardedBytes += 1
            return discard

    # ---------- SerialDevice::Close------------------
    def Close(self):
        if self.SerialDevice.isOpen():
            if self.Thread.IsAlive():
                self.Thread.Stop()
                self.Thread.WaitForThreadToEnd()
            self.SerialDevice.close()

    # ---------- SerialDevice::Flush------------------
    def Flush(self):
        try:
            self.SerialDevice.flushInput()      #flush input buffer, discarding all its contents
            self.SerialDevice.flushOutput()     #flush output buffer, aborting current output
            with self.BufferLock:               # will block if lock is already held
                del self.Buffer[:]

        except Exception as e1:
            self.FatalError( "Error in SerialDevice:Flush : " + self.DeviceName + ":" + str(e1))

    # ---------- SerialDevice::Read------------------
    def Read(self):
        return  self.SerialDevice.read()        # self.SerialDevice.inWaiting returns number of bytes ready

    # ---------- SerialDevice::Write-----------------
    def Write(self, data):
        return  self.SerialDevice.write(data)

    #---------------------SerialDevice::FatalError------------------------
    def LogError(self, Message):
        self.log.error(Message)
    #---------------------SerialDevice::FatalError------------------------
    def FatalError(self, Message):

        self.log.error(Message)
        raise Exception(Message)
