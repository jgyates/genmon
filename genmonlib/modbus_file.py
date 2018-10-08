#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: modbus_file.py
# PURPOSE: simulate modbus, registers backed by text file
#
#  AUTHOR: Jason G Yates
#    DATE: 19-Apr-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

from __future__ import print_function       # For python 3.x compatibility with print function

import datetime, threading, crcmod, sys, time, os, collections
import mylog, mythread, mycommon, modbusbase

#------------ ModbusBase class -------------------------------------------------
class ModbusFile(modbusbase.ModbusBase):
    def __init__(self, updatecallback, address = 0x9d, name = "/dev/serial", rate=9600, loglocation = "/var/log/", inputfile = None):
        super(ModbusFile, self).__init__(updatecallback = updatecallback, address = address, name = name, rate = rate, loglocation = loglocation)
        self.Address = address
        self.Rate = rate
        self.PortName = name
        self.InputFile = inputfile
        self.InitComplete = False
        self.UpdateRegisterList = updatecallback
        self.RxPacketCount = 0
        self.TxPacketCount = 0
        self.ComTimoutError = 0
        self.TotalElapsedPacketeTime = 0
        self.ComTimoutError = 0
        self.CrcError = 0
        self.SimulateTime = True

        self.ModbusStartTime = datetime.datetime.now()     # used for com metrics
        self.Registers = {}

        if self.InputFile == None:
            self.InputFile = os.path.dirname(os.path.realpath(__file__)) + "/modbusregs.txt"

        # log errors in this module to a file
        self.log = mylog.SetupLogger("mymodbus", loglocation + "mymodbus.log")

        if not os.path.isfile(self.InputFile):
            self.LogError("Error: File not present: " + self.InputFile)
        self.CommAccessLock = threading.RLock()     # lock to synchronize access to the serial port comms
        self.UpdateRegisterList = updatecallback

        self.ReadInputFile(self.InputFile)
        self.Threads["ReadInputFileThread"] = mythread.MyThread(self.ReadInputFileThread, Name = "ReadInputFileThread")


    #-------------ModbusBase::ReadInputFileThread-------------------------------
    def ReadInputFileThread(self):

        time.sleep(0.01)
        while True:
            if self.IsStopSignaled("ReadInputFileThread"):
                break
            self.ReadInputFile(self.InputFile)
            time.sleep(5)

    #-------------ModbusBase::ProcessMasterSlaveWriteTransaction----------------
    def ProcessMasterSlaveWriteTransaction(self, Register, Length, Data):
        return

    #-------------ModbusBase::ProcessMasterSlaveTransaction--------------------
    def ProcessMasterSlaveTransaction(self, Register, Length, ReturnValue = False):

        # TODO need more validation
        RegValue = self.Registers.get(Register, "")
        if len(RegValue):
            if ReturnValue:
                return RegValue
            else:
                if not self.UpdateRegisterList == None:
                    self.UpdateRegisterList(Register, RegValue)
                self.TxPacketCount += 1
                self.RxPacketCount += 1
                if self.SimulateTime:
                    time.sleep(.02)
        return

    #----------  GeneratorDevice:ReadInputFile  --------------------------------
    def ReadInputFile(self, FileName):

        if not len(FileName):
            self.LogError("Error in  ReadInputFile: No Input File")
            return False

        try:

            with open(FileName,"r") as InputFile:   #opens file

                for line in InputFile:
                    line = line.strip()             # remove beginning and ending whitespace

                    if not len(line):
                        continue
                    if line[0] == "#":              # comment?
                        continue
                    line = line.replace('\t', ' ')
                    line = line.replace(' : ', ':')
                    Items = line.split(" ")

                    for entry in Items:
                        RegEntry = entry.split(":")
                        if len(RegEntry) == 2:
                            if len(RegEntry[0])  and len(RegEntry[1]):
                                try:
                                    HexVal = int(RegEntry[0], 16)
                                    HexVal = int(RegEntry[1], 16)
                                    self.Registers[RegEntry[0]] = RegEntry[1]
                                except:
                                    continue

            return True

        except Exception as e1:
            self.LogErrorLine("Error in  ReadInputFile: " + str(e1))
            return False

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

        if self.RxPacketCount:
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

    #------------ModbusBase::Flush----------------------------------------------
    def Flush(self):
        pass

    #------------ModbusBase::Close----------------------------------------------
    def Close(self):

        pass
