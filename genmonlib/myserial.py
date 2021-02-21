#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: myserial.py
# PURPOSE: Base serial comms for modbus
#
#  AUTHOR: Jason G Yates
#    DATE: 19-Apr-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

from __future__ import print_function       # For python 3.x compatibility with print function

import datetime, threading, serial, sys, os

from genmonlib.mysupport import MySupport
from genmonlib.mylog import SetupLogger
from genmonlib.mythread import MyThread
from genmonlib.program_defaults import ProgramDefaults

#------------ SerialDevice class -----------------------------------------------
class SerialDevice(MySupport):
    def __init__(self,
        name = '/dev/serial0',
        rate=9600,
        log = None,
        Parity = None,
        OnePointFiveStopBits = None,
        sevendatabits = False,
        RtsCts = False,
        config = None,
        loglocation = ProgramDefaults.LogPath):

        super(SerialDevice, self).__init__()

        self.config = config
        self.DeviceName = name
        self.BaudRate = rate
        self.Buffer = []
        self.BufferLock = threading.Lock()
        self.DiscardedBytes = 0
        self.Restarts = 0
        self.SerialStartTime = datetime.datetime.now()     # used for com metrics
        self.loglocation = loglocation

        # This supports getting this info from genmon.conf
        if self.config != None:
            self.loglocation = self.config.ReadValue('loglocation', default = '/var/log/')
            self.DeviceName = self.config.ReadValue('port', default = '/dev/serial0')

        # log errors in this module to a file
        if log == None:
            self.log = SetupLogger("myserial", os.path.join(self.loglocation, "myserial.log"))
        else:
            self.log = log
        self.console = SetupLogger("myserial_console", log_file = "", stream = True)

        #Starting serial connection
        self.SerialDevice = serial.Serial()
        self.SerialDevice.port = self.DeviceName
        self.SerialDevice.baudrate = rate
        #number of bits per bytes
        if sevendatabits == True:
            self.SerialDevice.bytesize = serial.SEVENBITS
        else:
            self.SerialDevice.bytesize = serial.EIGHTBITS

        if Parity == None:
            self.SerialDevice.parity = serial.PARITY_NONE    #set parity check: no parity
        elif Parity == 1:
            self.SerialDevice.parity = serial.PARITY_ODD     #set parity check: use odd parity
        else:
            self.SerialDevice.parity = serial.PARITY_EVEN    #set parity check: use even parity

        if OnePointFiveStopBits == None:
            self.SerialDevice.stopbits = serial.STOPBITS_ONE  #number of stop bits
        elif OnePointFiveStopBits:
            self.SerialDevice.stopbits = serial.STOPBITS_ONE_POINT_FIVE  #number of stop bits
        else:
            self.SerialDevice.stopbits = serial.STOPBITS_ONE  #number of stop bits

        self.SerialDevice.timeout =  0.05                 # small timeout so we can check if the thread should exit
        self.SerialDevice.xonxoff = False                 #disable software flow control
        self.SerialDevice.rtscts = RtsCts                 #disable hardware (RTS/CTS) flow control
        self.SerialDevice.dsrdtr = False                  #disable hardware (DSR/DTR) flow control
        self.SerialDevice.writeTimeout = None             #timeout for write, return when packet sent
        self.IsOpen = False
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
        self.IsOpen = True
        self.Flush()
        self.StartReadThread()

    # ---------- SerialDevice::ResetSerialStats---------------------------------
    def ResetSerialStats(self):
        # resets status that are time based (affected by a time change)
        self.SerialStartTime = datetime.datetime.now()     # used for com metrics
    # ---------- SerialDevice::StartReadThread----------------------------------
    def StartReadThread(self):

        # start read thread to monitor incoming data commands
        self.Threads["SerialReadThread"] = MyThread(self.ReadThread, Name = "SerialReadThread")

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
                                self.Buffer.append(ord(c))      # PYTHON2
                            else:
                                self.Buffer.append(c)           # PYTHON3
                        # first check for SignalStopped is when we are receiving
                        if self.IsStopSignaled("SerialReadThread"):
                            return
                    # second check for SignalStopped is when we are not receiving
                    if self.IsStopSignaled("SerialReadThread"):
                        return

            except Exception as e1:
                self.LogErrorLine( "Resetting SerialDevice:ReadThread Error: " + self.DeviceName + ":"+ str(e1))
                # if we get here then this is likely due to the following exception:
                #  "device reports readiness to read but returned no data (device disconnected?)"
                #  This is believed to be a kernel issue so let's just reset the device and hope
                #  for the best (actually this works)
                self.Restarts += 1
                self.SerialDevice.close()
                self.SerialDevice.open()

    #------------SerialDevice::DiscardByte--------------------------------------
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
            self.SerialDevice.flushInput()      #flush input buffer, discarding all its contents
            self.SerialDevice.flushOutput()     #flush output buffer, aborting current output
            with self.BufferLock:               # will block if lock is already held
                del self.Buffer[:]

        except Exception as e1:
            self.LogErrorLine( "Error in SerialDevice:Flush : " + self.DeviceName + ":" + str(e1))

    # ---------- SerialDevice::Read---------------------------------------------
    def Read(self):
        return  self.SerialDevice.read()        # self.SerialDevice.inWaiting returns number of bytes ready

    # ---------- SerialDevice::Write--------------------------------------------
    def Write(self, data):
        return  self.SerialDevice.write(data)

    # ---------- SerialDevice::GetRxBufferAsString------------------------------
    def GetRxBufferAsString(self):

        try:
            if not len(self.Buffer):
                return ""
            with self.BufferLock:
                str1 = ''.join(chr(e) for e in self.Buffer)
            return str1
        except Exception as e1:
            self.LogErrorLine("Error in GetRxBufferAsString: " + str(e1))
            return ""
