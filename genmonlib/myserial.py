#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: myserial.py
# PURPOSE: Base serial comms for modbus
#
#  AUTHOR: Jason G Yates
#    DATE: 19-Apr-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------
# For python 3.x compatibility with print function
from __future__ import print_function

import datetime
import os
import sys
import threading

import serial

from genmonlib.mylog import SetupLogger
from genmonlib.mysupport import MySupport
from genmonlib.mythread import MyThread
from genmonlib.program_defaults import ProgramDefaults


# ------------ SerialDevice class -----------------------------------------------
class SerialDevice(MySupport):
    def __init__(
        self,
        name="/dev/serial0",
        rate=9600,
        log=None,
        Parity=None,
        OnePointFiveStopBits=None,
        sevendatabits=False,
        RtsCts=False,
        config=None,
        loglocation=ProgramDefaults.LogPath,
    ):

        super(SerialDevice, self).__init__()

        self.config = config
        self.DeviceName = name
        self.BaudRate = rate
        self.Buffer = []
        self.BufferLock = threading.Lock()
        self.DiscardedBytes = 0
        self.Restarts = 0
        self.SerialStartTime = datetime.datetime.now()  # used for com metrics
        self.loglocation = loglocation

        # This supports getting this info from genmon.conf
        if self.config != None:
            self.loglocation = self.config.ReadValue("loglocation", default="/var/log/")
            self.DeviceName = self.config.ReadValue("port", default="/dev/serial0")
            self.ForceSerialUse = self.config.ReadValue("forceserialuse", default=False)

        # log errors in this module to a file
        if log == None:
            self.log = SetupLogger(
                "myserial", os.path.join(self.loglocation, "myserial.log")
            )
        else:
            self.log = log
        self.console = SetupLogger("myserial_console", log_file="", stream=True)

        try:
            # Starting serial connection
            if self.VersionTuple(serial.__version__) < self.VersionTuple("3.3"):
                self.SerialDevice = serial.Serial()
            else:
                self.SerialDevice = serial.Serial(exclusive=True)

                self.SerialDevice = serial.Serial()
            self.SerialDevice.port = self.DeviceName
            self.SerialDevice.baudrate = rate
            # number of bits per bytes
            if sevendatabits == True:
                self.SerialDevice.bytesize = serial.SEVENBITS
            else:
                self.SerialDevice.bytesize = serial.EIGHTBITS

            if Parity == None or Parity == 0 or Parity.lower() == "none":
                # set parity check: no parity
                self.SerialDevice.parity = (serial.PARITY_NONE)  
            elif Parity == 1 or Parity.lower() == "odd":
                # set parity check: use odd parity
                self.SerialDevice.parity = (serial.PARITY_ODD)  
                self.LogError("Serial: Setting ODD parity")
            else:
                # set parity check: use even parity
                self.SerialDevice.parity = (serial.PARITY_EVEN)  
                self.LogError("Serial: Setting EVEN parity")

            if OnePointFiveStopBits == None:
                self.SerialDevice.stopbits = serial.STOPBITS_ONE  # number of stop bits
            elif OnePointFiveStopBits:
                # number of stop bits
                self.SerialDevice.stopbits = (serial.STOPBITS_ONE_POINT_FIVE)  
            else:
                self.SerialDevice.stopbits = serial.STOPBITS_ONE  # number of stop bits
            # small timeout so we can check if the thread should exit
            self.SerialDevice.timeout = 0.05
            self.SerialDevice.xonxoff = False  # disable software flow control
            self.SerialDevice.rtscts = RtsCts  # disable hardware (RTS/CTS) flow control
            self.SerialDevice.dsrdtr = False  # disable hardware (DSR/DTR) flow control
            # timeout for write, return when packet sent
            self.SerialDevice.writeTimeout = None
            self.IsOpen = False
            # Check if port failed to open
            if self.SerialDevice.isOpen() == False:
                try:
                    self.SerialDevice.open()
                except Exception as e:
                    if not self.ForceSerialUse:
                        self.FatalError("Error on open serial port %s: " % self.DeviceName + str(e))
                        return None
                    else:
                        self.LogErrorLine("Error on open serial port %s: " % self.DeviceName + str(e))
            else:
                if not self.ForceSerialUse:
                    self.FatalError("Serial port already open: %s" % self.DeviceName)
                return None
            self.IsOpen = True
            self.Flush()
            self.StartReadThread()
        except Exception as e1:
            self.LogErrorLine("Error in init: " + str(e1))
            if not self.ForceSerialUse:
                self.FatalError("Error on serial port init!")

    # ---------- SerialDevice::ResetSerialStats---------------------------------
    def ResetSerialStats(self):
        # resets status that are time based (affected by a time change)
        self.SerialStartTime = datetime.datetime.now()  # used for com metrics

    # ---------- SerialDevice::StartReadThread----------------------------------
    def StartReadThread(self):

        # start read thread to monitor incoming data commands
        self.Threads["SerialReadThread"] = MyThread(self.ReadThread, Name="SerialReadThread")

        return self.Threads["SerialReadThread"]

    # ---------- SerialDevice::ReadThread---------------------------------------
    def ReadThread(self):
        while True:
            try:
                self.Flush()
                while True:
                    for c in self.Read():
                        with self.BufferLock:
                            if sys.version_info[0] < 3:
                                self.Buffer.append(ord(c))  # PYTHON2
                            else:
                                self.Buffer.append(c)  # PYTHON3
                        # first check for SignalStopped is when we are receiving
                        if self.IsStopSignaled("SerialReadThread"):
                            return
                    # second check for SignalStopped is when we are not receiving
                    if self.IsStopSignaled("SerialReadThread"):
                        return

            except Exception as e1:
                self.LogErrorLine("Resetting SerialDevice:ReadThread Error: " + self.DeviceName+ ":"+ str(e1))
                # if we get here then this is likely due to the following exception:
                #  "device reports readiness to read but returned no data (device disconnected?)"
                #  This is believed to be a kernel issue so let's just reset the device and hope
                #  for the best (actually this works)
                self.RestartSerial()

    # ------------SerialDevice::RestartSerial------------------------------------
    def RestartSerial(self):
        try:
            self.Restarts += 1
            try:
                self.SerialDevice.close()
            except Exception as e1:
                self.LogErrorLine("Error closing in RestartSerial:" + str(e1))
            try:
                self.SerialDevice.open()
            except Exception as e1:
                self.LogErrorLine("Error opening in RestartSerial:" + str(e1))
        except Exception as e1:
            self.LogErrorLine("Error in RestartSerial: " + str(e1))

    # ------------SerialDevice::DiscardByte--------------------------------------
    def DiscardByte(self):

        if len(self.Buffer):
            discard = self.Buffer.pop(0)
            self.DiscardedBytes += 1
            return discard

    # ---------- SerialDevice::Close--------------------------------------------
    def Close(self):

        try:
            if self.SerialDevice.isOpen():
                self.KillThread("SerialReadThread")
                self.SerialDevice.close()
                self.IsOpen = False
        except Exception as e1:
            self.LogErrorLine("Error in Close: " + str(e1))

    # ---------- SerialDevice::Flush--------------------------------------------
    def Flush(self):
        try:
            self.SerialDevice.flushInput()  # flush input buffer, discarding all its contents
            self.SerialDevice.flushOutput()  # flush output buffer, aborting current output
            with self.BufferLock:  # will block if lock is already held
                del self.Buffer[:]

        except Exception as e1:
            self.LogErrorLine("Error in SerialDevice:Flush : " + self.DeviceName + ":" + str(e1))
            self.RestartSerial()

    # ---------- SerialDevice::Read---------------------------------------------
    def Read(self):
        # self.SerialDevice.inWaiting returns number of bytes ready
        return (self.SerialDevice.read())  

    # ---------- SerialDevice::Write--------------------------------------------
    def Write(self, data):

        try:
            return self.SerialDevice.write(data)
        except Exception as e1:
            self.LogErrorLine("Error in SerialDevice:Write : " + self.DeviceName + ":" + str(e1))
            self.RestartSerial()
            return False

    # ---------- SerialDevice::GetRxBufferAsString------------------------------
    def GetRxBufferAsString(self):

        try:
            if not len(self.Buffer):
                return ""
            with self.BufferLock:
                str1 = "".join(chr(e) for e in self.Buffer)
            return str1
        except Exception as e1:
            self.LogErrorLine("Error in GetRxBufferAsString: " + str(e1))
            return ""
