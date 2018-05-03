#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: modbusbase.py
# PURPOSE: Base modbus class support
#
#  AUTHOR: Jason G Yates
#    DATE: 19-Apr-2018
#
# MODIFICATIONS:
#------------------------------------------------------------

from __future__ import print_function       # For python 3.x compatibility with print function

import datetime, threading, crcmod, sys, time
import mylog, mythread, mysupport

#------------ ModbusBase class --------------------------------------------
class ModbusBase(mysupport.MySupport ):
    def __init__(self, updatecallback, address = 0x9d, name = "/dev/serial", rate=9600, loglocation = "/var/log/"):
        super(ModbusBase, self).__init__()
        self.Address = address
        self.Rate = rate
        self.PortName = name
        self.InitComplete = False
        self.UpdateRegisterList = updatecallback
        self.RxPacketCount = 0
        self.TxPacketCount = 0
        self.ComTimoutError = 0
        self.TotalElapsedPacketeTime = 0
        self.ComTimoutError = 0
        self.CrcError = 0
        self.ModbusStartTime = datetime.datetime.now()     # used for com metrics

        # log errors in this module to a file
        self.log = mylog.SetupLogger("mymodbus", loglocation + "mymodbus.log")
        self.CommAccessLock = threading.RLock()     # lock to synchronize access to the serial port comms
        self.UpdateRegisterList = updatecallback

    #-------------ModbusBase::ProcessMasterSlaveWriteTransaction--------------------
    def ProcessMasterSlaveWriteTransaction(self, Register, Length, Data):
        return

    #-------------ModbusBase::ProcessMasterSlaveTransaction--------------------
    def ProcessMasterSlaveTransaction(self, Register, Length, ReturnValue = False):
        return

    # ---------- ModbusBase::GetCommStats---------------------------------------
    def GetCommStats(self):
        SerialStats = collections.OrderedDict()

        SerialStats["Packet Count"] = "M: %d, S: %d" % (self.TxPacketCount, self.RxPacketCount)

        if self.CrcError == 0 or self.RxPacketCount == 0:
            PercentErrors = 0.0
        else:
            PercentErrors = float(self.CrcError) / float(self.RxPacketCount)

        SerialStats["CRC Errors"] = "%d " % self.CrcError
        SerialStats["CRC Percent Errors"] = "%.2f" % PercentErrors
        SerialStats["Packet Timeouts"] = "%d" %  self.ComTimoutError
        # Add serial stats here

        CurrentTime = datetime.datetime.now()

        #
        Delta = CurrentTime - self.ModbusStartTime        # yields a timedelta object
        PacketsPerSecond = float((self.TxPacketCount + self.RxPacketCount)) / float(Delta.total_seconds())
        SerialStats["Packets Per Second"] = "%.2f" % (PacketsPerSecond)

        if self.ModBus.RxPacketCount:
            AvgTransactionTime = float(self.TotalElapsedPacketeTime / self.RxPacketCount)
            SerialStats["Average Transaction Time"] = "%.4f sec" % (AvgTransactionTime)

        return SerialStats
    # ---------- ModbusBase::ResetCommStats-------------------------------------
    def ResetCommStats(self):
        self.RxPacketCount = 0
        self.TxPacketCount = 0
        self.TotalElapsedPacketeTime = 0
        self.ModbusStartTime = datetime.datetime.now()     # used for com metrics
        pass

    #------------ModbusBase::Flush-----------------------
    def Flush(self):
        pass

    #------------ModbusBase::Close-----------------------
    def Close(self):

        pass
