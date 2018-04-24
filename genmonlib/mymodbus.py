#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: mymodbus.py
# PURPOSE: Base modbus protocol support
#
#  AUTHOR: Jason G Yates
#    DATE: 19-Apr-2018
#
# MODIFICATIONS:
#------------------------------------------------------------

from __future__ import print_function       # For python 3.x compatibility with print function

import datetime, threading, crcmod, sys, time
import mylog, mythread, myserial, mycommon

#--------------------- MODBUS specific Const defines for Generator class
MBUS_ADDRESS            = 0x00
MBUS_ADDRESS_SIZE       = 0x01
MBUS_COMMAND            = 0x01
MBUS_COMMAND_SIZE       = 0x01
MBUS_WR_REQ_BYTE_COUNT  = 0x06
MBUS_CRC_SIZE           = 0x02
MBUS_RES_LENGTH_SIZE    = 0x01
MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH  = MBUS_ADDRESS_SIZE + MBUS_COMMAND_SIZE + MBUS_RES_LENGTH_SIZE + MBUS_CRC_SIZE
MBUS_RESPONSE_LEN       = 0x02
MIN_PACKET_LENGTH_REQ   = 0x08
MIN_PACKET_LENGTH_WR_REQ= 0x09
MIN_PACKET_LENGTH_RES   = 0x07
MIN_PACKET_LENGTH_WR_RES= 0x08
MBUS_CMD_READ_REGS      = 0x03
MBUS_CMD_WRITE_REGS     = 0x10

#------------ ModbusProtocol class --------------------------------------------
class ModbusProtocol(mycommon.MyCommon):
    def __init__(self, updatecallback, address = 0x9d, name = "/dev/serial", rate=9600, loglocation = "/var/log/"):

        self.Address = address
        self.Threads = {}                           # Dict of mythread objects
        self.DeviceInit = False
        self.CommAccessLock = threading.RLock()     # lock to synchronize access to the serial port comms
        self.UpdateRegisterList = updatecallback
        # log errors in this module to a file
        self.log = mylog.SetupLogger("mymodbus", loglocation + "mymodbus.log")

        try:
            #Starting serial connection
            self.Slave = myserial.SerialDevice(name, rate, loglocation)
            self.DeviceInit = True

        except Exception as e1:
            self.FatalError("Error opening serial device: " + str(e1))
            return None

        try:
            # CRCMOD library, used for CRC calculations
            self.ModbusCrc = crcmod.predefined.mkCrcFun('modbus')
        except Exception as e1:
            self.FatalError("Unable to find crcmod package: " + str(e1))

    # ---------- ModbusProtocol::GetPacketFromSlave------------------
    #  This function returns two values, the first is boolean. The seconds is
    #  a packet (list). If the return value is True and an empty packet, then
    #  keep looking because the data has not arrived yet, if return is False there
    #  is and error. If True and a non empty packet then it is valid data
    def GetPacketFromSlave(self):

        LocalErrorCount = 0
        Packet = []
        EmptyPacket = []    # empty packet

        if len(self.Slave.Buffer) < MIN_PACKET_LENGTH_RES:
            return True, EmptyPacket

        if len(self.Slave.Buffer) >= MIN_PACKET_LENGTH_RES:
            if self.Slave.Buffer[MBUS_ADDRESS] == self.Address and self.Slave.Buffer[MBUS_COMMAND] in [MBUS_CMD_READ_REGS]:
                # it must be a read command response
                length = self.Slave.Buffer[MBUS_RESPONSE_LEN]   # our packet tells us the length of the payload
                # if the full length of the packet has not arrived, return and try again
                if (length + MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH) > len(self.Slave.Buffer):
                    return True, EmptyPacket

                for i in range(0, length + MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH):
                    Packet.append(self.Slave.Buffer.pop(0))  # pop Address, Function, Length, message and CRC

                if self.CheckCRC(Packet):
                    self.Slave.RxPacketCount += 1
                    return True, Packet
                else:
                    self.Slave.CrcError += 1
                    return False, EmptyPacket
            elif self.Slave.Buffer[MBUS_ADDRESS] == self.Address and self.Slave.Buffer[MBUS_COMMAND] in [MBUS_CMD_WRITE_REGS]:
                # it must be a write command response
                if len(self.Slave.Buffer) < MIN_PACKET_LENGTH_WR_RES:
                    return True, EmptyPacket
                for i in range(0, MIN_PACKET_LENGTH_WR_RES):
                    Packet.append(self.Slave.Buffer.pop(0))    # address, function, address hi, address low, quantity hi, quantity low, CRC high, crc low

                if self.CheckCRC(Packet):
                    self.Slave.RxPacketCount += 1
                    return True,Packet
                else:
                    self.Slave.CrcError += 1
                    return False, EmptyPacket
            else:
                self.DiscardByte()
                self.Flush()
                return False, EmptyPacket

        return True, EmptyPacket   # technically not a CRC error, we really should never get here


    # ---------- GeneratorDevice::DiscardByte------------------
    def DiscardByte(self):

        discard = self.Slave.DiscardByte()
        self.LogError("Discarding byte slave: %02x" % (discard))

    #-------------ModbusProtocol::ProcessMasterSlaveWriteTransaction--------------------
    def ProcessMasterSlaveWriteTransaction(self, Register, Length, Data):

        MasterPacket = []

        MasterPacket = self.CreateMasterPacket(Register, Length, MBUS_CMD_WRITE_REGS, Data)

        if len(MasterPacket) == 0:
            return

        return self.ProcessOneTransaction(MasterPacket, skiplog = True)   # True to skip writing results to cached reg values

    #-------------ModbusProtocol::ProcessMasterSlaveTransaction--------------------
    def ProcessMasterSlaveTransaction(self, Register, Length, ReturnValue = False):

        MasterPacket = []

        MasterPacket = self.CreateMasterPacket(Register, Length)

        if len(MasterPacket) == 0:
            return

        if ReturnValue:
            return self.ProcessOneTransaction(MasterPacket, skiplog = True, ReturnValue = True)     # don't log

        return self.ProcessOneTransaction(MasterPacket)

    #------------ModbusProtocol::ProcessOneTransaction
    def ProcessOneTransaction(self, MasterPacket, skiplog = False, ReturnValue = False):

        with self.CommAccessLock:       # this lock should allow calls from multiple threads

            self.SendPacketAsMaster(MasterPacket)

            SentTime = datetime.datetime.now()
            while True:
                # be kind to other processes, we know we are going to have to wait for the packet to arrive
                # so let's sleep for a bit before we start polling
                time.sleep(0.01)

                RetVal, SlavePacket = self.GetPacketFromSlave()

                if RetVal == True and len(SlavePacket) != 0:    # we receive a packet
                    self.Slave.TotalElapsedPacketeTime += (self.MillisecondsElapsed(SentTime) / 1000)
                    break
                if RetVal == False:
                    self.LogError("Error Receiving slave packet for register %x%x" % (MasterPacket[2],MasterPacket[3]) )
                    # Errors returned here are logged in GetPacketFromSlave
                    self.Flush()
                    return False
                msElapsed = self.MillisecondsElapsed(SentTime)
                # This normally takes about 30 ms however in some instances it can take up to 950ms
                # the theory is this is either a delay due to how python does threading, or
                # delay caused by the generator controller.
                # each char time is about 1 millisecond so assuming a 10 byte packet transmitted
                # and a 10 byte received with about 5 char times of silence in between should give
                # us about 25ms
                if msElapsed > 3000:
                    self.Slave.ComTimoutError += 1
                    self.LogError("Error: timeout receiving slave packet for register %x%x Buffer:%d" % (MasterPacket[2],MasterPacket[3], len(self.Slave.Buffer)) )
                    return False

        # update our cached register dict
        ReturnRegValue = self.UpdateRegistersFromPacket(MasterPacket, SlavePacket, SkipUpdate = skiplog)
        if ReturnValue:
            return ReturnRegValue

        return True

    # ---------- GeneratorDevice::MillisecondsElapsed------------------
    def MillisecondsElapsed(self, ReferenceTime):

        CurrentTime = datetime.datetime.now()
        Delta = CurrentTime - ReferenceTime
        return Delta.total_seconds() * 1000

    # ---------- ModbusProtocol::CreateMasterPacket------------------
    # the length is the register length in words, as required by modbus
    # build Packet
    def CreateMasterPacket(self, Register, Length, command = MBUS_CMD_READ_REGS, Data=[]):

        Packet = []
        if command == MBUS_CMD_READ_REGS:
            Packet.append(self.Address)                 # address
            Packet.append(command)                      # command
            Packet.append(int(Register,16) >> 8)        # reg hi
            Packet.append(int(Register,16) & 0x00FF)    # reg low
            Packet.append(Length >> 8)                  # length hi
            Packet.append(Length & 0x00FF)              # length low
            CRCValue = self.GetCRC(Packet)
            Packet.append(CRCValue & 0x00FF)            # CRC low
            Packet.append(CRCValue >> 8)                # CRC high
        elif command == MBUS_CMD_WRITE_REGS:
            if len(Data) == 0:
                self.LogError("Validation Error: CreateMasterPacket invalid length (1) %x %x" % (len(Data), Length))
                return Packet
            if len(Data)/2 != Length:
                self.LogError("Validation Error: CreateMasterPacket invalid length (2) %x %x" % (len(Data), Length))
                return Packet
            Packet.append(self.Address)                 # address
            Packet.append(command)                      # command
            Packet.append(int(Register,16) >> 8)        # reg hi
            Packet.append(int(Register,16) & 0x00FF)    # reg low
            Packet.append(Length >> 8)                  # Num of Reg hi
            Packet.append(Length & 0x00FF)              # Num of Reg low
            Packet.append(len(Data))                    # byte count
            for b in range(0, len(Data)):
                Packet.append(Data[b])                  # data
            CRCValue = self.GetCRC(Packet)
            Packet.append(CRCValue & 0x00FF)            # CRC low
            Packet.append(CRCValue >> 8)                # CRC high
        else:
            self.LogError("Validation Error: Invalid command in CreateMasterPacket!")
        return Packet

    #-------------ModbusProtocol::SendPacketAsMaster---------------------------------
    def SendPacketAsMaster(self, Packet):

        ByteArray = bytearray(Packet)
        self.Slave.Write(ByteArray)
        self.Slave.TxPacketCount += 1

    # ---------- ModbusProtocol::UpdateRegistersFromPacket------------------
    #    Update our internal register list based on the request/response packet
    def UpdateRegistersFromPacket(self, MasterPacket, SlavePacket, SkipUpdate = False):

        if len(MasterPacket) < MIN_PACKET_LENGTH_RES or len(SlavePacket) < MIN_PACKET_LENGTH_RES:
            return ""

        if MasterPacket[MBUS_ADDRESS] != self.Address:
            self.LogError("Validation Error:: Invalid address in UpdateRegistersFromPacket (Master)")

        if SlavePacket[MBUS_ADDRESS] != self.Address:
            self.LogError("Validation Error:: Invalid address in UpdateRegistersFromPacket (Slave)")

        if not SlavePacket[MBUS_COMMAND] in [MBUS_CMD_READ_REGS, MBUS_CMD_WRITE_REGS]:
            self.LogError("UpdateRegistersFromPacket: Unknown Function slave %02x %02x" %  (SlavePacket[0],SlavePacket[1]))

        if not MasterPacket[MBUS_COMMAND] in [MBUS_CMD_READ_REGS, MBUS_CMD_WRITE_REGS]:
            self.LogError("UpdateRegistersFromPacket: Unknown Function master %02x %02x" %  (MasterPacket[0],MasterPacket[1]))

         # get register from master packet
        Register = "%02x%02x" % (MasterPacket[2],MasterPacket[3])
        # get value from slave packet
        length = SlavePacket[MBUS_RESPONSE_LEN]
        if (length + MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH) > len(SlavePacket):
             return ""

        RegisterValue = ""
        for i in range(3, length+3):
            RegisterValue += "%02x" % SlavePacket[i]
        # update register list
        if not SkipUpdate:
            self.UpdateRegisterList(Register, RegisterValue)

        return RegisterValue

     #------------ModbusProtocol::CheckCrc---------------------
    def CheckCRC(self, Packet):

        if len(Packet) == 0:
            return False
        ByteArray = bytearray(Packet[:len(Packet)-2])

        if sys.version_info[0] < 3:
            results = self.ModbusCrc(str(ByteArray))
        else:   # PYTHON3
            results = self.ModbusCrc(ByteArray)

        CRCValue = ( ( Packet[-1] & 0xFF ) << 8 ) | ( Packet[ -2] & 0xFF )
        if results != CRCValue:
            self.LogError("Data Error: CRC check failed: %04x  %04x" % (results, CRCValue))
            return False
        return True

     #------------ModbusProtocol::GetCRC---------------------
    def GetCRC(self, Packet):

        if len(Packet) == 0:
            return False
        ByteArray = bytearray(Packet)

        if sys.version_info[0] < 3:
            results = self.ModbusCrc(str(ByteArray))
        else:   # PYTHON3
            results = self.ModbusCrc(ByteArray)

        return results

    #------------ModbusProtocol::Flush-----------------------
    def Flush(self):

        self.Slave.Flush()

    #------------ModbusProtocol::Close-----------------------
    def Close(self):

        self.Slave.Close()
