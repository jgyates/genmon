#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: mymodbus.py
# PURPOSE: Base modbus protocol support
#
#  AUTHOR: Jason G Yates
#    DATE: 19-Apr-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

from __future__ import print_function       # For python 3.x compatibility with print function

import datetime, threading, crcmod, sys, time, collections

from genmonlib.modbusbase import ModbusBase
from genmonlib.myserial import SerialDevice
from genmonlib.myserialtcp import SerialTCPDevice
from genmonlib.program_defaults import ProgramDefaults

#--------------------- MODBUS specific Const defines for Generator class--------
# Packet offsets
MBUS_OFF_ADDRESS            = 0x00
MBUS_OFF_COMMAND            = 0x01
MBUS_OFF_EXCEPTION          = 0x02
MBUS_OFF_RESPONSE_LEN       = 0x02
MBUS_OFF_FILE_TYPE          = 0x04      # offset in response packet
MBUS_OFF_FILE_PAYLOAD_LEN   = 0x03
MBUS_OFF_FILE_PAYLOAD       = 0x05
MBUS_OFF_REGISTER_HI        = 0x02
MBUS_OFF_REGISTER_LOW       = 0x03
MBUS_OFF_FILE_NUM_HI        = 0x04
MBUS_OFF_FILE_NUM_LOW       = 0x05
MBUS_OFF_FILE_RECORD_HI     = 0x06
MBUS_OFF_FILE_RECORD_LOW    = 0x07
MBUS_OFF_RECORD_LENGTH_HI   = 0x08
MBUS_OFF_RECORD_LENGTH_LOW  = 0x09
MBUS_OFF_LENGTH_HI          = 0x04
MBUS_OFF_LENGTH_LOW         = 0x05
MBUS_OFF_WR_REQ_BYTE_COUNT  = 0x06

# Field Sizes
MBUS_ADDRESS_SIZE       = 0x01
MBUS_COMMAND_SIZE       = 0x01
MBUS_CRC_SIZE           = 0x02
MBUS_RES_LENGTH_SIZE    = 0x01
MBUS_FILE_TYPE_SIZE     = 0x01

# Packet lengths
MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH  = MBUS_ADDRESS_SIZE + MBUS_COMMAND_SIZE + MBUS_RES_LENGTH_SIZE + MBUS_CRC_SIZE
MBUS_FILE_READ_PAYLOAD_SIZE_MINUS_LENGTH = MBUS_ADDRESS_SIZE + MBUS_COMMAND_SIZE + MBUS_RES_LENGTH_SIZE + MBUS_CRC_SIZE
MIN_PACKET_ERR_LENGTH                   = 0x05
MIN_PACKET_RESPONSE_LENGTH              = 0x07
MIN_PACKET_MIN_WRITE_RESPONSE_LENGTH    = 0x08
MBUS_READ_FILE_REQUEST_PAYLOAD_LENGTH   = 0x07
MIN_REQ_PACKET_LENGTH                   = 0x08
MIN_WR_REQ_PACKET_LENGTH                = 0x09
MIN_FILE_READ_REQ_PACKET_LENGTH         = 0x0C
MAX_MODBUS_PACKET_SIZE                  = 0x100
# Varible limits
MAX_REGISTER                            = 0xffff
MIN_REGISTER                            = 0x0
MAX_FILE_RECORD_NUM                     = 0x270F
MIN_FILE_RECORD_NUM                     = 0x0
MAX_FILE_NUMBER                         = 0xFFFF
MIN_FILE_NUMBER                         = 0x01
# commands
MBUS_CMD_READ_REGS      = 0x03
MBUS_CMD_WRITE_REGS     = 0x10
MBUS_CMD_READ_FILE      = 0x14

# Values
MBUS_FILE_TYPE_VALUE    = 0x06
MBUS_ERROR_BIT          = 0x80

# Exceprtion codes
MBUS_EXCEP_FUNCTION     = 0x01      # Illegal Function
MBUS_EXCEP_ADDRESS      = 0x02      # Illegal Address
MBUS_EXCEP_DATA         = 0x03      # Illegal Data Value
MBUS_EXCEP_SLAVE_FAIL   = 0x04      # Slave Device Failure
MBUS_EXCEP_ACK          = 0x05      # Acknowledge
MBUS_EXCEP_BUSY         = 0x06      # Slave Device Busy
MBUS_EXCEP_NACK         = 0x07      # Negative Acknowledge
MBUS_EXCEP_MEM_PE       = 0x08      # Memory Parity Error
MBUS_EXCEP_GATEWAY      = 0x10      # Gateway Path Unavailable
MBUS_EXCEP_GATEWAY_TG   = 0x11      #Gateway Target Device Failed to Respond

#------------ ModbusProtocol class ---------------------------------------------
class ModbusProtocol(ModbusBase):
    def __init__(self,
        updatecallback,
        address = 0x9d,
        name = "/dev/serial0",
        rate=9600,
        Parity = None,
        OnePointFiveStopBits = None,
        config = None):

        super(ModbusProtocol, self).__init__(updatecallback = updatecallback, address = address, name = name, rate = rate, config = config)

        try:

            # ~3000 for 9600               bit time * 10 bits * 10 char * 2 packets + wait time(3000) (convert to ms * 1000)
            self.ModBusPacketTimoutMS = (((((1/float(rate)) * 10.0) * 10.0 * 2.0) *1000.0)  + 3000.0)     # .00208

            self.ModBusPacketTimoutMS += self.AdditionalModbusTimeout * 1000.0


            if self.UseTCP:
                self.ModBusPacketTimoutMS = self.ModBusPacketTimoutMS
            #Starting serial connection
            if self.UseTCP:
                self.Slave = SerialTCPDevice(config = self.config)
            else:
                self.Slave = SerialDevice(name = name, rate = rate, Parity = Parity, OnePointFiveStopBits = OnePointFiveStopBits, config = self.config)
            self.Threads = self.MergeDicts(self.Threads, self.Slave.Threads)


        except Exception as e1:
            self.LogErrorLine("Error opening serial device: " + str(e1))
            self.FatalError("Error opening serial device.")

        try:
            # CRCMOD library, used for CRC calculations
            self.ModbusCrc = crcmod.predefined.mkCrcFun('modbus')
            self.InitComplete = True
        except Exception as e1:
            self.FatalError("Unable to find crcmod package: " + str(e1))

    #--------------------ModbusProtocol:GetExceptionString----------------------
    def GetExceptionString(self, Code):

        try:

            LookUp = {
                MBUS_EXCEP_FUNCTION : "Illegal Function",
                MBUS_EXCEP_ADDRESS : "Illegal Address",
                MBUS_EXCEP_DATA : "Illegal Data Value",
                MBUS_EXCEP_SLAVE_FAIL : "Slave Device Failure",
                MBUS_EXCEP_ACK : "Acknowledge",
                MBUS_EXCEP_BUSY : "Slave Device Busy",
                MBUS_EXCEP_NACK : "Negative Acknowledge",
                MBUS_EXCEP_MEM_PE : "Memory Parity Error",
                MBUS_EXCEP_GATEWAY : "Gateway Path Unavailable",
                MBUS_EXCEP_GATEWAY_TG : "Gateway Target Device Failed to Respond"
             }

            ReturnString = LookUp.get(Code, "Unknown")
            ReturnString = ReturnString + (": %02x" % Code)
            return ReturnString
        except Exception as e1:
            self.LogErrorLine("Error in GetExceptionString: " + str(e1))

        return ""
    # ---------- ModbusProtocol::CheckResponseAddress---------------------------
    def CheckResponseAddress(self, Address):

        if Address == self.Address:
            return True
        if self.ResponseAddress == None:
            return False
        if Address == self.ResponseAddress:
            return True
        return False

    # ---------- ModbusProtocol::GetPacketFromSlave-----------------------------
    #  This function returns two values, the first is boolean. The seconds is
    #  a packet (list). If the return value is True and an empty packet, then
    #  keep looking because the data has not arrived yet, if return is False there
    #  is and error. If True and a non empty packet then it is valid data
    def GetPacketFromSlave(self):

        LocalErrorCount = 0
        Packet = []
        EmptyPacket = []    # empty packet
        try:
            if not len(self.Slave.Buffer):
                return True, EmptyPacket

            if not self.CheckResponseAddress(self.Slave.Buffer[MBUS_OFF_ADDRESS]):
                self.DiscardByte()
                self.Flush()
                return False, EmptyPacket

            if len(self.Slave.Buffer) < MIN_PACKET_ERR_LENGTH:
                return True, EmptyPacket   # No full packet ready

            if self.Slave.Buffer[MBUS_OFF_COMMAND] & MBUS_ERROR_BIT:
                for i in range(0, MIN_PACKET_ERR_LENGTH):
                    Packet.append(self.Slave.Buffer.pop(0))  # pop Address, Function, Excetion code, and CRC
                if self.CheckCRC(Packet):
                    self.RxPacketCount += 1
                    self.SlaveException += 1
                    self.LogError("Modbus Exception: " + self.GetExceptionString(Packet[MBUS_OFF_EXCEPTION]) + " , Modbus Command: " + ("%02x" % Packet[MBUS_OFF_COMMAND]))
                else:
                    self.CrcError += 1
                return False, Packet

            if len(self.Slave.Buffer) < MIN_PACKET_RESPONSE_LENGTH:
                return True, EmptyPacket   # No full packet ready

            if  self.Slave.Buffer[MBUS_OFF_COMMAND] in [MBUS_CMD_READ_REGS]:
                # it must be a read command response
                length = self.Slave.Buffer[MBUS_OFF_RESPONSE_LEN]   # our packet tells us the length of the payload
                # if the full length of the packet has not arrived, return and try again
                if (length + MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH) > len(self.Slave.Buffer):
                    return True, EmptyPacket

                for i in range(0, length + MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH):
                    Packet.append(self.Slave.Buffer.pop(0))  # pop Address, Function, Length, message and CRC

                if self.CheckCRC(Packet):
                    self.RxPacketCount += 1
                    return True, Packet
                else:
                    self.CrcError += 1
                    return False, Packet
            elif self.Slave.Buffer[MBUS_OFF_COMMAND] in [MBUS_CMD_WRITE_REGS]:
                # it must be a write command response
                if len(self.Slave.Buffer) < MIN_PACKET_MIN_WRITE_RESPONSE_LENGTH:
                    return True, EmptyPacket
                for i in range(0, MIN_PACKET_MIN_WRITE_RESPONSE_LENGTH):
                    Packet.append(self.Slave.Buffer.pop(0))    # address, function, address hi, address low, quantity hi, quantity low, CRC high, crc low

                if self.CheckCRC(Packet):
                    self.RxPacketCount += 1
                    return True, Packet
                else:
                    self.CrcError += 1
                    return False, Packet
            elif self.Slave.Buffer[MBUS_OFF_COMMAND] in [MBUS_CMD_READ_FILE]:
                length = self.Slave.Buffer[MBUS_OFF_RESPONSE_LEN]   # our packet tells us the length of the payload
                if self.Slave.Buffer[MBUS_OFF_FILE_TYPE] != MBUS_FILE_TYPE_VALUE:
                    self.LogError("Invalid modbus file record type")
                    self.ComValidationError += 1
                    return False, EmptyPacket
                # if the full length of the packet has not arrived, return and try again
                if (length + MBUS_FILE_READ_PAYLOAD_SIZE_MINUS_LENGTH) > len(self.Slave.Buffer):
                    return True, EmptyPacket
                for i in range(0, length + MBUS_FILE_READ_PAYLOAD_SIZE_MINUS_LENGTH):
                    Packet.append(self.Slave.Buffer.pop(0))  # pop Address, Function, Length, message and CRC

                if self.CheckCRC(Packet):
                    self.RxPacketCount += 1
                    return True, Packet
                else:
                    self.CrcError += 1
                    return False, Packet
            else:
                # received a  response to a command we do not support
                self.DiscardByte()
                self.Flush()
                return False, EmptyPacket
        except Exception as e1:
            self.LogErrorLine("Error in GetPacketFromSlave: " + str(e1))
            self.SlaveException += 1
            return False, EmptyPacket
    # ---------- GeneratorDevice::DiscardByte-----------------------------------
    def DiscardByte(self):

        discard = self.Slave.DiscardByte()
        self.LogError("Discarding byte slave: %02x" % (discard))

    #-------------ModbusProtocol::ProcessMasterSlaveWriteTransaction------------
    def ProcessMasterSlaveWriteTransaction(self, Register, Length, Data):

        try:
            MasterPacket = []

            MasterPacket = self.CreateMasterPacket(Register, length = int(Length), command = MBUS_CMD_WRITE_REGS, data = Data)

            if len(MasterPacket) == 0:
                return False

            return self.ProcessOneTransaction(MasterPacket, skipupdate = True)   # True to skip writing results to cached reg values
        except Exception as e1:
            self.LogErrorLine("Error in ProcessMasterSlaveWriteTransaction: " + str(e1))
            return False

    #-------------ModbusProtocol::ProcessMasterSlaveTransaction-----------------
    def ProcessMasterSlaveTransaction(self, Register, Length, skipupdate = False, ReturnString = False):

        MasterPacket = []

        try:
            MasterPacket = self.CreateMasterPacket(Register, length = int(Length))

            if len(MasterPacket) == 0:
                return ""

            return self.ProcessOneTransaction(MasterPacket, skipupdate = skipupdate, ReturnString = ReturnString)     # don't log

        except Exception as e1:
            self.LogErrorLine("Error in ProcessMasterSlaveTransaction: " + str(e1))
            return ""

    #-------------ModbusProtocol::ProcessMasterSlaveFileReadTransaction---------
    def ProcessMasterSlaveFileReadTransaction(self, Register, Length, skipupdate = False, file_num = 1, ReturnString = False):

        MasterPacket = []

        try:
            MasterPacket = self.CreateMasterPacket(Register, length = int(Length), command = MBUS_CMD_READ_FILE, file_num = file_num)

            if len(MasterPacket) == 0:
                return ""

            return self.ProcessOneTransaction(MasterPacket, skipupdate = skipupdate, ReturnString = ReturnString)     # don't log

        except Exception as e1:
            self.LogErrorLine("Error in ProcessMasterSlaveFileReadTransaction: " + str(e1))
            return ""

    #------------ModbusProtocol::ProcessOneTransaction--------------------------
    def ProcessOneTransaction(self, MasterPacket, skipupdate = False, ReturnString = False):

        try:
            with self.CommAccessLock:       # this lock should allow calls from multiple threads

                if len(self.Slave.Buffer):
                    self.UnexpectedData += 1
                    self.LogError("Flushing, unexpected data. Likely timeout.")
                    self.Flush()
                self.SendPacketAsMaster(MasterPacket)

                SentTime = datetime.datetime.now()
                while True:
                    # be kind to other processes, we know we are going to have to wait for the packet to arrive
                    # so let's sleep for a bit before we start polling
                    if self.SlowCPUOptimization:
                        time.sleep(0.03)
                    else:
                        time.sleep(0.01)

                    if self.IsStopping:
                        return ""
                    RetVal, SlavePacket = self.GetPacketFromSlave()

                    if RetVal == True and len(SlavePacket) != 0:    # we receive a packet
                        self.TotalElapsedPacketeTime += (self.MillisecondsElapsed(SentTime) / 1000)
                        break
                    if RetVal == False:
                        self.LogError("Error Receiving slave packet for register %04x" % (self.GetRegisterFromPacket(MasterPacket) ))
                        # Errors returned here are logged in GetPacketFromSlave
                        self.Flush()
                        return ""

                    msElapsed = self.MillisecondsElapsed(SentTime)
                    # This normally takes about 30 ms however in some instances it can take up to 950ms
                    # the theory is this is either a delay due to how python does threading, or
                    # delay caused by the generator controller.
                    # each char time is about 1 millisecond (at 9600 baud) so assuming a 10 byte packet
                    # transmitted and a 10 byte received with about 5 char times of silence
                    # in between should give us about 25ms
                    if msElapsed > self.ModBusPacketTimoutMS:
                        self.ComTimoutError += 1
                        self.LogError("Error: timeout receiving slave packet for register %04x Buffer:%d" % (self.GetRegisterFromPacket(MasterPacket), len(self.Slave.Buffer)) )
                        if len(self.Slave.Buffer):
                            self.LogError("Buffer: " + str(self.Slave.Buffer))
                        self.Flush()
                        return ""

                # update our cached register dict
                ReturnRegValue = self.UpdateRegistersFromPacket(MasterPacket, SlavePacket, SkipUpdate = skipupdate, ReturnString = ReturnString)
                if ReturnRegValue == "Error":
                    self.LogError("Master: " + str(MasterPacket))
                    self.LogError("Slave: " + str(SlavePacket))
                    self.ComValidationError += 1
                    self.Flush()
                    ReturnRegValue = ""

            return ReturnRegValue


        except Exception as e1:
            self.LogErrorLine("Error in ProcessOneTransaction: " + str(e1))
            return ""

    # ---------- ModbusProtocol::MillisecondsElapsed----------------------------
    def MillisecondsElapsed(self, ReferenceTime):

        CurrentTime = datetime.datetime.now()
        Delta = CurrentTime - ReferenceTime
        return Delta.total_seconds() * 1000

    #------------GetRegisterFromPacket -----------------------------------------
    def GetRegisterFromPacket(self, Packet):
        try:
            Register = 0
            if Packet[MBUS_OFF_COMMAND] == MBUS_CMD_READ_FILE:
                Register = Packet[MBUS_OFF_FILE_RECORD_HI] << 8 |  Packet[MBUS_OFF_FILE_RECORD_LOW] & 0x00FF
            else:
                Register = Packet[MBUS_OFF_REGISTER_HI] << 8 |  Packet[MBUS_OFF_REGISTER_LOW] & 0x00FF
            return Register
        except Exception as e1:
            self.LogErrorLine("Error in GetRegisterFromPacket: " + str(e1))
            return Register

    # ---------- ModbusProtocol::CreateMasterPacket-----------------------------
    # the length is the register length in words, as required by modbus
    # build Packet
    def CreateMasterPacket(self, register, length = 1, command = MBUS_CMD_READ_REGS, data=[], file_num = 1):

        Packet = []
        try:
            RegisterInt = int(register,16)

            if RegisterInt < MIN_REGISTER or RegisterInt > MAX_REGISTER:
                self.ComValidationError += 1
                self.LogError("Validation Error: CreateMasterPacket maximum regiseter value exceeded: " + str(register))
                return []
            if file_num < MIN_FILE_NUMBER or file_num > MAX_FILE_NUMBER:
                self.ComValidationError += 1
                self.LogError("Validation Error: CreateMasterPacket maximum file number value exceeded: " + str(file_num))
                return []

            if command == MBUS_CMD_READ_REGS:
                Packet.append(self.Address)                 # address
                Packet.append(command)                      # command
                Packet.append(RegisterInt >> 8)             # reg higy
                Packet.append(RegisterInt & 0x00FF)         # reg low
                Packet.append(length >> 8)                  # length high
                Packet.append(length & 0x00FF)              # length low
                CRCValue = self.GetCRC(Packet)
                Packet.append(CRCValue & 0x00FF)            # CRC low
                Packet.append(CRCValue >> 8)                # CRC high

            elif command == MBUS_CMD_WRITE_REGS:
                if len(data) == 0:
                    self.LogError("Validation Error: CreateMasterPacket invalid length (1) %x %x" % (len(data), length))
                    self.ComValidationError += 1
                    return []
                if len(data)/2 != length:
                    self.LogError("Validation Error: CreateMasterPacket invalid length (2) %x %x" % (len(data), length))
                    self.ComValidationError += 1
                    return []
                Packet.append(self.Address)                 # address
                Packet.append(command)                      # command
                Packet.append(RegisterInt >> 8)             # reg higy
                Packet.append(RegisterInt & 0x00FF)         # reg low
                Packet.append(length >> 8)                  # Num of Reg higy
                Packet.append(length & 0x00FF)              # Num of Reg low
                Packet.append(len(data))                    # byte count
                for b in range(0, len(data)):
                    Packet.append(data[b])                  # data
                CRCValue = self.GetCRC(Packet)
                Packet.append(CRCValue & 0x00FF)            # CRC low
                Packet.append(CRCValue >> 8)                # CRC high

            elif command == MBUS_CMD_READ_FILE:

                # Note, we only support one sub request at at time
                if RegisterInt < MIN_FILE_RECORD_NUM or RegisterInt > MAX_FILE_RECORD_NUM:
                    self.ComValidationError += 1
                    self.LogError("Validation Error: CreateMasterPacket maximum regiseter (record number) value exceeded: " + str(register))
                    return []
                Packet.append(self.Address)                 # address
                Packet.append(command)                      # command
                Packet.append(MBUS_READ_FILE_REQUEST_PAYLOAD_LENGTH)     # Byte count
                Packet.append(MBUS_FILE_TYPE_VALUE)         # always same value
                Packet.append(file_num >> 8)                # File Number hi
                Packet.append(file_num & 0x00FF)            # File Number low
                Packet.append(RegisterInt >> 8)             # register (file record number) high
                Packet.append(RegisterInt & 0x00FF)         # register (file record number) low
                Packet.append(length >> 8)                  # Length to return hi
                Packet.append(length & 0x00FF)              # Length to return lo
                CRCValue = self.GetCRC(Packet)
                Packet.append(CRCValue & 0x00FF)            # CRC low
                Packet.append(CRCValue >> 8)                # CRC high
            else:
                self.LogError("Validation Error: Invalid command in CreateMasterPacket!")
                self.ComValidationError += 1
                return []
        except Exception as e1:
            self.LogErrorLine("Error in CreateMasterPacket: " + str(e1))

        if len(Packet) > MAX_MODBUS_PACKET_SIZE:
            self.LogError("Validation Error: CreateMasterPacket: Packet size exceeds max size")
            self.ComValidationError += 1
            return []

        return Packet

    #-------------ModbusProtocol::SendPacketAsMaster----------------------------
    def SendPacketAsMaster(self, Packet):

        try:
            ByteArray = bytearray(Packet)
            self.Slave.Write(ByteArray)
            self.TxPacketCount += 1
        except Exception as e1:
            self.LogErrorLine("Error in SendPacketAsMaster: " + str(e1))
            self.LogError("Packet: " + str(Packet))

    # ---------- ModbusProtocol::UpdateRegistersFromPacket----------------------
    #    Update our internal register list based on the request/response packet
    def UpdateRegistersFromPacket(self, MasterPacket, SlavePacket, SkipUpdate = False, ReturnString = False):

        try:
            if len(MasterPacket) < MIN_PACKET_RESPONSE_LENGTH or len(SlavePacket) < MIN_PACKET_RESPONSE_LENGTH:
                self.LogError("Validation Error, length: Master" + str(len(MasterPacket)) + " Slave: " + str(len(SlavePacket)))
                return "Error"

            if MasterPacket[MBUS_OFF_ADDRESS] != self.Address:
                self.LogError("Validation Error: Invalid address in UpdateRegistersFromPacket (Master)")
                return "Error"
            if not self.CheckResponseAddress(SlavePacket[MBUS_OFF_ADDRESS]):
                self.LogError("Validation Error: Invalid address in UpdateRegistersFromPacket (Slave)")
                return "Error"
            if not SlavePacket[MBUS_OFF_COMMAND] in [MBUS_CMD_READ_REGS, MBUS_CMD_WRITE_REGS, MBUS_CMD_READ_FILE]:
                self.LogError("Validation Error: Unknown Function slave %02x %02x" %  (SlavePacket[MBUS_OFF_ADDRESS],SlavePacket[MBUS_OFF_COMMAND]))
                return "Error"
            if not MasterPacket[MBUS_OFF_COMMAND] in [MBUS_CMD_READ_REGS, MBUS_CMD_WRITE_REGS, MBUS_CMD_READ_FILE]:
                self.LogError("Validation Error: Unknown Function master %02x %02x" %  (MasterPacket[MBUS_OFF_ADDRESS],MasterPacket[MBUS_OFF_COMMAND]))
                return "Error"

            if MasterPacket[MBUS_OFF_COMMAND] != SlavePacket[MBUS_OFF_COMMAND]:
                self.LogError("Validation Error: Command Mismatch :" + str(MasterPacket[MBUS_OFF_COMMAND]) + ":" + str(SlavePacket[MBUS_OFF_COMMAND]))
                return "Error"

             # get register from master packet
            Register = "%04x" % (self.GetRegisterFromPacket(MasterPacket))
            if MasterPacket[MBUS_OFF_COMMAND] == MBUS_CMD_WRITE_REGS:
                # get register from slave packet
                SlaveRegister = "%04x" % (self.GetRegisterFromPacket(SlavePacket))
                if SlaveRegister != Register:
                    self.LogError("Validation Error: Master Slave Register Mismatch : " + Register +  ":" + SlaveRegister)
                    return "Error"

            RegisterValue = ""
            RegisterStringValue = ""
            if MasterPacket[MBUS_OFF_COMMAND] == MBUS_CMD_READ_REGS:
                # get value from slave packet
                length = SlavePacket[MBUS_OFF_RESPONSE_LEN]
                if (length + MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH) > len(SlavePacket):
                    self.LogError("Validation Error: Slave Lenght : " + length +  ":" + len(SlavePacket))
                    return "Error"

                for i in range(3, length+3):
                    RegisterValue += "%02x" % SlavePacket[i]
                    if ReturnString:
                        if SlavePacket[i]:
                            RegisterStringValue += chr(SlavePacket[i])
                # update register list
                if not SkipUpdate:
                    if not self.UpdateRegisterList == None:
                        if not ReturnString:
                            self.UpdateRegisterList(Register, RegisterValue)
                        else:
                            self.UpdateRegisterList(Register, RegisterStringValue, IsString = True)

            if MasterPacket[MBUS_OFF_COMMAND] == MBUS_CMD_READ_FILE:
                payloadLen = SlavePacket[MBUS_OFF_FILE_PAYLOAD_LEN]
                payloadLen -= 1
                for i  in range (MBUS_OFF_FILE_PAYLOAD, MBUS_OFF_FILE_PAYLOAD + payloadLen):
                    RegisterValue += "%02x" % SlavePacket[i]
                    if ReturnString:
                        if SlavePacket[i]:
                            RegisterStringValue += chr(SlavePacket[i])

                if not SkipUpdate:
                    if not ReturnString:
                        self.UpdateRegisterList(Register, RegisterValue, IsFile = True)
                    else:
                        self.UpdateRegisterList(Register, RegisterStringValue, IsString = True, IsFile = True)
                pass
            if ReturnString:
                return str(RegisterStringValue)
            return str(RegisterValue)
        except Exception as e1:
            self.LogErrorLine("Error in UpdateRegistersFromPacket: " + str(e1))
            return "Error"

     #------------ModbusProtocol::CheckCrc--------------------------------------
    def CheckCRC(self, Packet):

        try:
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
        except Exception as e1:
            self.LogErrorLine("Error in CheckCRC: " + str(e1))
            self.LogError("Packet: " + str(Packet))
            return False

     #------------ModbusProtocol::GetCRC----------------------------------------
    def GetCRC(self, Packet):
        try:
            if len(Packet) == 0:
                return False
            ByteArray = bytearray(Packet)

            if sys.version_info[0] < 3:
                results = self.ModbusCrc(str(ByteArray))
            else:   # PYTHON3
                results = self.ModbusCrc(ByteArray)

            return results
        except Exception as e1:
            self.LogErrorLine("Error in GetCRC: " + str(e1))
            self.LogError("Packet: " + str(Packet))
            return 0
    # ---------- ModbusProtocol::GetCommStats-----------------------------------
    def GetCommStats(self):
        SerialStats = []

        try:
            SerialStats.append({"Packet Count" : "M: %d, S: %d" % (self.TxPacketCount, self.RxPacketCount)})

            if self.CrcError == 0 or self.TxPacketCount == 0:
                PercentErrors = 0.0
            else:
                PercentErrors = float(self.CrcError) / float(self.TxPacketCount)

            if self.ComTimoutError == 0 or self.TxPacketCount == 0:
                PercentTimeoutErrors = 0.0
            else:
                PercentTimeoutErrors = float(self.ComTimoutError) / float(self.TxPacketCount)

            SerialStats.append({"CRC Errors" : "%d " % self.CrcError})
            SerialStats.append({"CRC Percent Errors" : ("%.2f" % (PercentErrors * 100)) + "%"})
            SerialStats.append({"Packet Timeouts" : "%d" %  self.ComTimoutError})
            SerialStats.append({"Packet Timeouts Percent Errors" : ("%.2f" % (PercentTimeoutErrors * 100)) + "%"})
            SerialStats.append({"Modbus Exceptions" : self.SlaveException})
            SerialStats.append({"Validation Errors" : self.ComValidationError})
            SerialStats.append({"Invalid Data" : self.UnexpectedData})
            # add serial stats
            SerialStats.append({"Discarded Bytes" : "%d" % self.Slave.DiscardedBytes})
            SerialStats.append({"Comm Restarts" : "%d" % self.Slave.Restarts})

            CurrentTime = datetime.datetime.now()
            #
            Delta = CurrentTime - self.ModbusStartTime        # yields a timedelta object
            PacketsPerSecond = float((self.TxPacketCount + self.RxPacketCount)) / float(Delta.total_seconds())
            SerialStats.append({"Packets Per Second" : "%.2f" % (PacketsPerSecond)})

            if self.RxPacketCount:
                AvgTransactionTime = float(self.TotalElapsedPacketeTime / self.RxPacketCount)
                SerialStats.append({"Average Transaction Time" : "%.4f sec" % (AvgTransactionTime)})
        except Exception as e1:
            self.LogErrorLine("Error in GetCommStats: " + str(e1))
        return SerialStats

    # ---------- ModbusProtocol::ResetCommStats---------------------------------
    def ResetCommStats(self):

        try:
            self.RxPacketCount = 0
            self.TxPacketCount = 0
            self.TotalElapsedPacketeTime = 0
            self.ModbusStartTime = datetime.datetime.now()     # used for com metrics
            self.Slave.ResetSerialStats()
        except Exception as e1:
            self.LogErrorLine("Error in ResetCommStats: " + str(e1))

    #------------ModbusProtocol::Flush------------------------------------------
    def Flush(self):

        self.Slave.Flush()

    #------------ModbusProtocol::Close------------------------------------------
    def Close(self):
        self.IsStopping = True
        self.Slave.Close()
