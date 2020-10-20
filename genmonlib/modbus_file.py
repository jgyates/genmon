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

import datetime, threading, crcmod, sys, time, os, collections, json

from genmonlib.modbusbase import ModbusBase
from genmonlib.mythread import MyThread
from genmonlib.program_defaults import ProgramDefaults

#------------ ModbusBase class -------------------------------------------------
class ModbusFile(ModbusBase):
    def __init__(self,
        updatecallback,
        address = 0x9d,
        name = "/dev/serial",
        rate=9600,
        config = None,
        inputfile = None):

        super(ModbusFile, self).__init__(updatecallback = updatecallback, address = address, name = name, rate = rate, config = config)

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
        self.Strings = {}
        self.FileData = {}

        if self.InputFile == None:
            self.InputFile = os.path.join(os.path.dirname(os.path.realpath(__file__)), "modbusregs.txt")

        if not os.path.isfile(self.InputFile):
            self.LogError("Error: File not present: " + self.InputFile)
        self.CommAccessLock = threading.RLock()     # lock to synchronize access to the serial port comms
        self.UpdateRegisterList = updatecallback

        if not self.ReadInputFile(self.InputFile):
            self.LogError("ModusFile Init(): Error loading input file: " + self.InputFile)
        else:
            if not self.AdjustInputData():
                self.LogInfo("Error parsing input data")

            self.Threads["ReadInputFileThread"] = MyThread(self.ReadInputFileThread, Name = "ReadInputFileThread", start = False)
            self.Threads["ReadInputFileThread"].Start()
        self.InitComplete = False

    #-------------ModbusBase::ReadInputFileThread-------------------------------
    def ReadInputFileThread(self):

        while True:
            if self.IsStopSignaled("ReadInputFileThread"):
                break
            self.ReadInputFile(self.InputFile)
            if not self.AdjustInputData():
                self.LogInfo("Error parsing input data")
            time.sleep(5)

    #-------------ModbusBase::ProcessWriteTransaction---------------------------
    def ProcessWriteTransaction(self, Register, Length, Data):
        return

    #-------------ModbusBase::ProcessTransaction--------------------------------
    def ProcessTransaction(self, Register, Length, skipupdate = False, ReturnString = False):

        # TODO need more validation

        if ReturnString:
            RegValue = self.Strings.get(Register, "")
        else:
            RegValue = self.Strings.get(Register, None)

            if  RegValue == None :
                RegValue = self.Registers.get(Register, "")

                if len(RegValue):
                    while (len(RegValue) != Length * 4):

                        if len(RegValue) < Length * 4:
                            RegValue = "0" + RegValue
                        elif len(RegValue) > Length * 4:
                            RegValue = RegValue[1:]

        self.TxPacketCount += 1
        self.RxPacketCount += 1
        if self.SimulateTime:
            time.sleep(.02)

        if not skipupdate:
            if not self.UpdateRegisterList == None:
                self.UpdateRegisterList(Register, RegValue, IsFile = False, IsString = ReturnString)

        return RegValue

    #-------------ModbusProtocol::ProcessFileReadTransaction---------
    def ProcessFileReadTransaction(self, Register, Length, skipupdate = False, file_num = 1, ReturnString = False):

        RegValue = self.FileData.get(Register, "")

        self.TxPacketCount += 1
        self.RxPacketCount += 1
        if self.SimulateTime:
            time.sleep(.02)

        RegValue = self.FileData.get(Register, "")
        if not skipupdate:
            if not self.UpdateRegisterList == None:
                self.UpdateRegisterList(Register, RegValue, IsFile = True, IsString = ReturnString)

        return RegValue
    #----------  AdjustInputData  ----------------------------------------------
    def AdjustInputData(self):

        if not len(self.Registers):
            self.LogError("Error in AdjustInputData, no data.")
            return False
        #  No need to adjust data for registers, move on to strings and File data
        for Reg, Value in self.Strings.items():
            RegInt = int(Reg,16)
            if not len(Value):
                self.Registers["%04x" % (RegInt)] = "0000"
                continue
            if self.StringIsHex(Value):
                # Not a string, just hex data in a string format
                for i in range( 0, len(Value), 4):
                    self.Registers["%04x" % (RegInt + int(i / 4))] = Value[i:i+4]
            else:
                for i in range(0, len(Value), 2):
                    HiByte = ord(Value[i])
                    if i + 1 >= len(Value):
                        LowByte = 0
                    else:
                        LowByte = ord(Value[i+1])
                    self.Registers["%04x" % (RegInt + int(i / 2))] = "%02x%02x" % (HiByte, LowByte)
        return True

    #----------  ReadJSONFile  -------------------------------------------------
    def ReadJSONFile(self, FileName):

        if not len(FileName):
            self.LogError("Error in  ReadJSONFile: No Input File")
            return False
        try:
            with open(FileName) as f:
                data = json.load(f,object_pairs_hook=collections.OrderedDict)
                self.Registers = data["Registers"]
                self.Strings = data["Strings"]
                self.FileData = data["FileData"]
            return True
        except Exception as e1:
            #self.LogErrorLine("Error in ReadJSONFile: " + str(e1))
            return False

    #----------  GeneratorDevice:ReadInputFile  --------------------------------
    def ReadInputFile(self, FileName):

        REGISTERS = 0
        STRINGS = 1
        FILE_DATA = 2

        Section  = REGISTERS
        if not len(FileName):
            self.LogError("Error in  ReadInputFile: No Input File")
            return False

        if self.ReadJSONFile(FileName):
            return True

        try:

            with open(FileName,"r") as InputFile:   #opens file

                for line in InputFile:
                    line = line.strip()             # remove beginning and ending whitespace

                    if not len(line):
                        continue
                    if line[0] == "#":              # comment?
                        continue
                    if "Strings :"in line:
                        Section = STRINGS
                    elif "FileData :" in line:
                        Section = FILE_DATA
                    if Section == REGISTERS:
                        line = line.replace('\t', ' ')
                        line = line.replace(' : ', ':')
                        Items = line.split(" ")
                        for entry in Items:
                            RegEntry = entry.split(":")
                            if len(RegEntry) == 2:
                                if len(RegEntry[0])  and len(RegEntry[1]):
                                    try:
                                        if Section == REGISTERS:
                                            HexVal = int(RegEntry[0], 16)
                                            HexVal = int(RegEntry[1], 16)
                                            #self.LogError("REGISTER: <" + RegEntry[0] + ": " + RegEntry[1] + ">")
                                            self.Registers[RegEntry[0]] = RegEntry[1]

                                    except:
                                        continue
                    elif Section == STRINGS:
                        Items = line.split(" : ")
                        if len(Items) == 2:
                            #self.LogError("STRINGS: <" + Items[0] + ": " + Items[1] + ">")
                            self.Strings[Items[0]] = Items[1]
                        else:
                            pass
                            #self.LogError("Error in STRINGS: " + str(Items))
                    elif Section == FILE_DATA:
                        Items = line.split(" : ")
                        if len(Items) == 2:
                            #self.LogError("FILEDATA: <" + Items[0] + ": " + Items[1] + ">")
                            self.FileData[Items[0]] = Items[1]
                        else:
                            pass
                            #self.LogError("Error in FILEDATA: " + str(Items))

            return True

        except Exception as e1:
            self.LogErrorLine("Error in  ReadInputFile: " + str(e1))
            return False

    # ---------- ModbusBase::GetCommStats---------------------------------------
    def GetCommStats(self):
        SerialStats = []

        SerialStats.append({"Packet Count" : "M: %d, S: %d" % (self.TxPacketCount, self.RxPacketCount)})

        if self.CrcError == 0 or self.RxPacketCount == 0:
            PercentErrors = 0.0
        else:
            PercentErrors = float(self.CrcError) / float(self.RxPacketCount)

        SerialStats.append({"CRC Errors" : "%d " % self.CrcError})
        SerialStats.append({"CRC Percent Errors" : "%.2f" % PercentErrors})
        SerialStats.append({"Timeouts Errors" : "%d" %  self.ComTimoutError})
        # Add serial stats here

        CurrentTime = datetime.datetime.now()

        #
        Delta = CurrentTime - self.ModbusStartTime        # yields a timedelta object
        PacketsPerSecond = float((self.TxPacketCount + self.RxPacketCount)) / float(Delta.total_seconds())
        SerialStats.append({"Packets Per Second" : "%.2f" % (PacketsPerSecond)})

        if self.RxPacketCount:
            AvgTransactionTime = float(self.TotalElapsedPacketeTime / self.RxPacketCount)
            SerialStats.append({"Average Transaction Time" : "%.4f sec" % (AvgTransactionTime)})

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
