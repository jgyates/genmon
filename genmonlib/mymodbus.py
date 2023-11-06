#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: mymodbus.py
# PURPOSE: Base modbus protocol support
#
#  AUTHOR: Jason G Yates
#    DATE: 19-Apr-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

from __future__ import (  # For python 3.x compatibility with print function
    print_function,
)

import datetime
import sys
import time
import crcmod

from genmonlib.modbusbase import ModbusBase
from genmonlib.myserial import SerialDevice
from genmonlib.myserialtcp import SerialTCPDevice


# ------------ ModbusProtocol class ---------------------------------------------
class ModbusProtocol(ModbusBase):
    def __init__(
        self,
        updatecallback,
        address=0x9D,
        name="/dev/serial0",
        rate=9600,
        Parity=None,
        OnePointFiveStopBits=None,
        config=None,
        host=None,
        port=None,
        modbustcp=False,  # True of Modbus TCP, else if TCP then assume serial over TCP (Modbus RTU over serial)
        use_fc4=False,
    ):

        super(ModbusProtocol, self).__init__(
            updatecallback=updatecallback,
            address=address,
            name=name,
            rate=rate,
            config=config,
            use_fc4=use_fc4,
        )

        try:
            if config == None:
                self.ModbusTCP = modbustcp
                self.Host = host
                self.Port = port
                self.Parity = Parity
                self.Rate = rate
            self.TransactionID = 0
            self.AlternateFileProtocol = False

            if host != None and port != None and self.config == None:
                # in this instance we do not use a config file, but config comes from command line
                self.UseTCP = True

            # ~3000 for 9600               bit time * 10 bits * 10 char * 2 packets + wait time(3000) (convert to ms * 1000)
            self.ModBusPacketTimoutMS = (
                (((1 / float(self.Rate)) * 10.0) * 10.0 * 2.0) * 1000.0
            ) + 3000.0  # .00208

            self.ModBusPacketTimoutMS += self.AdditionalModbusTimeout * 1000.0

            if self.ModbusTCP:
                self.MIN_PACKET_RESPONSE_LENGTH -= 2
                self.MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH -= 2
                self.MBUS_FILE_READ_PAYLOAD_SIZE_MINUS_LENGTH -= 2
                self.MBUS_CRC_SIZE = 0
                self.MIN_PACKET_ERR_LENGTH -= 2

            if self.UseTCP:
                self.ModBusPacketTimoutMS = self.ModBusPacketTimoutMS + 2000
            # Starting serial connection
            if self.UseTCP:
                self.Slave = SerialTCPDevice(config=self.config, host=host, port=port)
            else:
                self.Slave = SerialDevice(
                    name=name,
                    rate=self.Rate,
                    Parity=self.Parity,
                    OnePointFiveStopBits=OnePointFiveStopBits,
                    config=self.config,
                )
            self.Threads = self.MergeDicts(self.Threads, self.Slave.Threads)

        except Exception as e1:
            self.LogErrorLine("Error opening modbus device: " + str(e1))
            self.FatalError("Error opening modbus device.")

        try:
            # CRCMOD library, used for CRC calculations
            self.ModbusCrc = crcmod.predefined.mkCrcFun("modbus")
            self.InitComplete = True
        except Exception as e1:
            self.FatalError("Unable to find crcmod package: " + str(e1))

    # --------------------ModbusProtocol:GetExceptionString----------------------
    def GetExceptionString(self, Code):

        try:

            LookUp = {
                self.MBUS_EXCEP_FUNCTION: "Illegal Function",
                self.MBUS_EXCEP_ADDRESS: "Illegal Address",
                self.MBUS_EXCEP_DATA: "Illegal Data Value",
                self.MBUS_EXCEP_SLAVE_FAIL: "Slave Device Failure",
                self.MBUS_EXCEP_ACK: "Acknowledge",
                self.MBUS_EXCEP_BUSY: "Slave Device Busy",
                self.MBUS_EXCEP_NACK: "Negative Acknowledge",
                self.MBUS_EXCEP_MEM_PE: "Memory Parity Error",
                self.MBUS_EXCEP_GATEWAY: "Gateway Path Unavailable",
                self.MBUS_EXCEP_GATEWAY_TG: "Gateway Target Device Failed to Respond",
            }

            if Code == self.MBUS_EXCEP_FUNCTION:
                self.ExcepFunction += 1
            elif Code == self.MBUS_EXCEP_ADDRESS:
                self.ExcepAddress += 1
            elif Code == self.MBUS_EXCEP_DATA:
                self.ExcepData += 1
            elif Code == self.MBUS_EXCEP_SLAVE_FAIL:
                self.ExcepSlave += 1
            elif Code == self.MBUS_EXCEP_ACK:
                self.ExcepAck += 1
            elif Code == self.MBUS_EXCEP_BUSY:
                self.ExcepBusy += 1
            elif Code == self.MBUS_EXCEP_NACK:
                self.ExcepNack += 1
            elif Code == self.MBUS_EXCEP_MEM_PE:
                self.ExcepMemPe += 1
            elif Code == self.MBUS_EXCEP_GATEWAY:
                self.ExcepGateway += 1
            elif Code == self.MBUS_EXCEP_GATEWAY_TG:
                self.ExcepGateWayTg += 1

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
    def GetPacketFromSlave(self, min_response_override=None):

        LocalErrorCount = 0
        Packet = []
        EmptyPacket = []  # empty packet
        try:
            if not len(self.Slave.Buffer):
                return True, EmptyPacket

            if self.ModbusTCP:
                # byte 0:   transaction identifier - copied by server - usually 0
                # byte 1:   transaction identifier - copied by server - usually 0
                # byte 2:   protocol identifier = 0
                # byte 3:   protocol identifier = 0
                # byte 4:   length field (upper byte) = 0 (since all messages are smaller than 256)
                # byte 5:   length field (lower byte) = number of bytes following
                # byte 6:   unit identifier (previously 'slave address')
                # byte 7:   MODBUS function code
                # byte 8 on:    data as needed

                if len(self.Slave.Buffer) < (
                    self.MIN_PACKET_ERR_LENGTH + self.MODBUS_TCP_HEADER_SIZE
                ):
                    return True, EmptyPacket

                # transaction ID must match
                rxID = (self.Slave.Buffer[0] << 8) | (self.Slave.Buffer[1] & 0xFF)
                if self.CurrentTransactionID != rxID:
                    self.LogError(
                        "ModbusTCP transaction ID mismatch: %x %x"
                        % (self.CurrentTransactionID, rxID)
                    )
                    self.DiscardByte(reason="Transaction ID")
                    self.Flush()
                    return False, EmptyPacket
                # protocol ID is zero
                if self.Slave.Buffer[2] != 0 or self.Slave.Buffer[3] != 0:
                    self.LogError(
                        "ModbusTCP protocool ID non zero: %x %x"
                        % (self.Slave.Buffer[2], self.Slave.Buffer[3])
                    )
                    self.DiscardByte(reason="protocol error")
                    self.Flush()
                    return False, EmptyPacket
                # Modbus TCP payload length
                ModbusTCPLength = (self.Slave.Buffer[4] << 8) | (
                    self.Slave.Buffer[5] & 0xFF
                )
                if len(self.Slave.Buffer[6:]) != ModbusTCPLength:
                    # more data is needed
                    return True, EmptyPacket

                # remove modbud TCP header
                for i in range(0, self.MODBUS_TCP_HEADER_SIZE):
                    self.Slave.Buffer.pop(0)

            if not self.CheckResponseAddress(self.Slave.Buffer[self.MBUS_OFF_ADDRESS]):
                self.DiscardByte(reason="Response Address")
                self.Flush()
                return False, EmptyPacket

            if len(self.Slave.Buffer) < self.MIN_PACKET_ERR_LENGTH:
                return True, EmptyPacket  # No full packet ready

            if self.Slave.Buffer[self.MBUS_OFF_COMMAND] & self.MBUS_ERROR_BIT:
                for i in range(0, self.MIN_PACKET_ERR_LENGTH):
                    Packet.append(
                        self.Slave.Buffer.pop(0)
                    )  # pop Address, Function, Exception code, and CRC
                if self.CheckCRC(Packet):
                    self.RxPacketCount += 1
                    self.ModbusException += 1
                    self.LogError(
                        "Modbus Exception: "
                        + self.GetExceptionString(Packet[self.MBUS_OFF_EXCEPTION])
                        + " , Modbus Command: "
                        + ("%02x" % Packet[self.MBUS_OFF_COMMAND])
                        + " , Sequence: "
                        + str(self.TxPacketCount)
                    )

                else:
                    self.CrcError += 1
                return False, Packet

            if min_response_override != None:
                if len(self.Slave.Buffer) < min_response_override:
                    return True, EmptyPacket  # No full packet ready
            else:
                if len(self.Slave.Buffer) < self.MIN_PACKET_RESPONSE_LENGTH:
                    return True, EmptyPacket  # No full packet ready

            if self.Slave.Buffer[self.MBUS_OFF_COMMAND] in [self.MBUS_CMD_READ_REGS, self.MBUS_CMD_READ_INPUT_REGS, self.MBUS_CMD_READ_COILS]:
                # it must be a read command response
                length = self.Slave.Buffer[
                    self.MBUS_OFF_RESPONSE_LEN
                ]  # our packet tells us the length of the payload
                # if the full length of the packet has not arrived, return and try again
                if (length + self.MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH) > len(
                    self.Slave.Buffer
                ):
                    return True, EmptyPacket

                for i in range(0, length + self.MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH):
                    Packet.append(
                        self.Slave.Buffer.pop(0)
                    )  # pop Address, Function, Length, message and CRC

                if self.CheckCRC(Packet):
                    self.RxPacketCount += 1
                    return True, Packet
                else:
                    self.CrcError += 1
                    return False, Packet
            elif self.Slave.Buffer[self.MBUS_OFF_COMMAND] in [self.MBUS_CMD_WRITE_REGS]:
                # it must be a write command response
                if len(self.Slave.Buffer) < self.MIN_PACKET_MIN_WRITE_RESPONSE_LENGTH:
                    return True, EmptyPacket
                for i in range(0, self.MIN_PACKET_MIN_WRITE_RESPONSE_LENGTH):
                    Packet.append(
                        self.Slave.Buffer.pop(0)
                    )  # address, function, address hi, address low, quantity hi, quantity low, CRC high, crc low

                if self.CheckCRC(Packet):
                    self.RxPacketCount += 1
                    return True, Packet
                else:
                    self.CrcError += 1
                    return False, Packet
            elif self.Slave.Buffer[self.MBUS_OFF_COMMAND] in [self.MBUS_CMD_READ_FILE]:
                length = self.Slave.Buffer[
                    self.MBUS_OFF_RESPONSE_LEN
                ]  # our packet tells us the length of the payload
                if (
                    self.Slave.Buffer[self.MBUS_OFF_FILE_TYPE]
                    != self.MBUS_FILE_TYPE_VALUE
                ):
                    self.LogError("Invalid modbus file record type")
                    self.ComValidationError += 1
                    return False, EmptyPacket
                # if the full length of the packet has not arrived, return and try again
                if (length + self.MBUS_FILE_READ_PAYLOAD_SIZE_MINUS_LENGTH) > len(
                    self.Slave.Buffer
                ):
                    return True, EmptyPacket
                # we will copy the entire buffer, this will be validated at a later time
                for i in range(0, len(self.Slave.Buffer)):
                    Packet.append(
                        self.Slave.Buffer.pop(0)
                    )  # pop Address, Function, Length, message and CRC

                if len(self.Slave.Buffer):
                    self.LogHexList(self.Slave.Buffer, prefix="Left Over")

                if self.CheckCRC(Packet):
                    self.RxPacketCount += 1
                    return True, Packet
                else:
                    self.CrcError += 1
                    return False, Packet
            elif self.Slave.Buffer[self.MBUS_OFF_COMMAND] in [self.MBUS_CMD_WRITE_FILE]:
                length = self.Slave.Buffer[
                    self.MBUS_OFF_RESPONSE_LEN
                ]  # our packet tells us the length of the payload
                if (
                    self.Slave.Buffer[self.MBUS_OFF_WRITE_FILE_TYPE]
                    != self.MBUS_FILE_TYPE_VALUE
                ):
                    self.LogError("Invalid modbus write file record type")
                    self.ComValidationError += 1
                    return False, EmptyPacket
                # if the full length of the packet has not arrived, return and try again
                if (length + self.MBUS_FILE_READ_PAYLOAD_SIZE_MINUS_LENGTH) > len(
                    self.Slave.Buffer
                ):
                    return True, EmptyPacket
                # we will copy the entire buffer, this will be validated at a later time
                for i in range(0, len(self.Slave.Buffer)):
                    Packet.append(
                        self.Slave.Buffer.pop(0)
                    )  # pop Address, Function, Length, message and CRC

                if len(self.Slave.Buffer):
                    self.LogHexList(self.Slave.Buffer, prefix="Left Over")

                if self.CheckCRC(Packet):
                    self.RxPacketCount += 1
                    return True, Packet
                else:
                    self.CrcError += 1
                    return False, Packet
            else:
                # received a  response to a command we do not support
                self.DiscardByte(reason="Invalid Modbus command")
                self.Flush()
                return False, EmptyPacket
        except Exception as e1:
            self.LogErrorLine("Error in GetPacketFromSlave: " + str(e1))
            self.ComValidationError += 1
            return False, EmptyPacket

    # ---------- GeneratorDevice::DiscardByte-----------------------------------
    def DiscardByte(self, reason=None):

        discard = self.Slave.DiscardByte()
        if reason == None:
            reason = "Unknown"
        self.LogError("Discarding byte slave: %02x : %s " % (discard, str(reason)))

    # -------------ModbusProtocol::PWT-------------------------------------------
    # called from derived calls to get to overridded function ProcessWriteTransaction
    def _PWT(self, Register, Length, Data, min_response_override=None):

        try:
            with self.CommAccessLock:
                MasterPacket = []

                MasterPacket = self.CreateMasterPacket(
                    Register,
                    length=int(Length),
                    command=self.MBUS_CMD_WRITE_REGS,
                    data=Data,
                )

                if len(MasterPacket) == 0:
                    return False

                # skipupdate=True to skip writing results to cached reg values
                return self.ProcessOneTransaction(
                    MasterPacket,
                    skipupdate=True,
                    min_response_override=min_response_override,
                )
        except Exception as e1:
            self.LogErrorLine("Error in ProcessWriteTransaction: " + str(e1))
            return False

    # -------------ModbusProtocol::ProcessWriteTransaction-----------------------
    def ProcessWriteTransaction(self, Register, Length, Data):
        return self._PWT(Register, Length, Data)

    # -------------ModbusProtocol::PT--------------------------------------------
    # called from derived calls to get to overridded function ProcessTransaction
    def _PT(self, Register, Length, skipupdate=False, ReturnString=False, IsCoil = False, IsInput = False):

        MasterPacket = []

        try:
            min_response_override = None # use the default minimum response packet size
            with self.CommAccessLock:
                if IsCoil:
                    packet_type = self.MBUS_CMD_READ_COILS
                elif IsInput:
                    packet_type = self.MBUS_CMD_READ_INPUT_REGS
                else:
                    packet_type = self.MBUS_CMD_READ_REGS
                MasterPacket = self.CreateMasterPacket(
                    Register, command=packet_type, length=int(Length)
                )

                if len(MasterPacket) == 0:
                    return ""

                return self.ProcessOneTransaction(
                    MasterPacket, skipupdate=skipupdate, ReturnString=ReturnString, min_response_override = min_response_override
                )  # don't log

        except Exception as e1:
            self.LogErrorLine("Error in ProcessTransaction: " + str(e1))
            return ""

    # -------------ModbusProtocol::ProcessTransaction----------------------------
    def ProcessTransaction(
        self, Register, Length, skipupdate=False, ReturnString=False, IsCoil = False, IsInput = False
    ):
        return self._PT(Register, Length, skipupdate = skipupdate, ReturnString = ReturnString, IsCoil = IsCoil, IsInput = IsInput)

    # -------------ModbusProtocol::ProcessFileReadTransaction--------------------
    def ProcessFileReadTransaction(
        self, Register, Length, skipupdate=False, file_num=1, ReturnString=False
    ):

        MasterPacket = []

        try:
            with self.CommAccessLock:
                MasterPacket = self.CreateMasterPacket(
                    Register,
                    length=int(Length),
                    command=self.MBUS_CMD_READ_FILE,
                    file_num=file_num,
                )

                if len(MasterPacket) == 0:
                    return ""

                return self.ProcessOneTransaction(
                    MasterPacket, skipupdate=skipupdate, ReturnString=ReturnString
                )  # don't log

        except Exception as e1:
            self.LogErrorLine("Error in ProcessFileReadTransaction: " + str(e1))
            return ""

    # -------------ModbusProtocol::ProcessFileWriteTransaction-------------------
    def ProcessFileWriteTransaction(
        self, Register, Length, Data, file_num=1, min_response_override=None
    ):

        MasterPacket = []

        try:
            with self.CommAccessLock:
                MasterPacket = self.CreateMasterPacket(
                    Register,
                    length=int(Length),
                    command=self.MBUS_CMD_WRITE_FILE,
                    file_num=file_num,
                    data=Data,
                )

                if len(MasterPacket) == 0:
                    return ""

                # skipupdate=True to skip writing results to cached reg values
                return self.ProcessOneTransaction(
                    MasterPacket,
                    skipupdate=True,
                    min_response_override=min_response_override,
                )

        except Exception as e1:
            self.LogErrorLine("Error in ProcessFileWriteTransaction: " + str(e1))
            return ""

    # ------------ModbusProtocol::ProcessOneTransaction--------------------------
    def ProcessOneTransaction(
        self,
        MasterPacket,
        skipupdate=False,
        ReturnString=False,
        min_response_override=None,
    ):

        try:
            if self.ModbusTCP:
                PacketOffset = self.MODBUS_TCP_HEADER_SIZE
            else:
                PacketOffset = 0

            with self.CommAccessLock:  # this lock should allow calls from multiple threads

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
                    RetVal, SlavePacket = self.GetPacketFromSlave(
                        min_response_override=min_response_override
                    )

                    if RetVal == True and len(SlavePacket) != 0:  # we receive a packet
                        self.TotalElapsedPacketeTime += (
                            self.MillisecondsElapsed(SentTime) / 1000
                        )
                        break
                    if RetVal == False:
                        self.LogError(
                            "Error Receiving slave packet for register %04x"
                            % (
                                self.GetRegisterFromPacket(
                                    MasterPacket, offset=PacketOffset
                                )
                            )
                        )
                        # Errors returned here are logged in GetPacketFromSlave
                        time.sleep(1)
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
                        self.LogError(
                            "Error: timeout receiving slave packet for register %04x Buffer: %d, sequence %d"
                            % (
                                self.GetRegisterFromPacket(
                                    MasterPacket, offset=PacketOffset
                                ),
                                len(self.Slave.Buffer),
                                self.TxPacketCount,
                            )
                        )
                        if len(self.Slave.Buffer):
                            self.LogHexList(self.Slave.Buffer, prefix="Buffer")
                        self.Flush()
                        return ""

                # update our cached register dict
                ReturnRegValue = self.UpdateRegistersFromPacket(
                    MasterPacket,
                    SlavePacket,
                    SkipUpdate=skipupdate,
                    ReturnString=ReturnString,
                )
                if ReturnRegValue == "Error":
                    self.LogHexList(MasterPacket, prefix="Master")
                    self.LogHexList(SlavePacket, prefix="Slave")
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

    # ------------GetRegisterFromPacket -----------------------------------------
    def GetRegisterFromPacket(self, Packet, offset=0):
        try:
            Register = 0

            if Packet[self.MBUS_OFF_COMMAND + offset] in [
                self.MBUS_CMD_READ_FILE,
                self.MBUS_CMD_WRITE_FILE,
            ]:
                Register = (
                    Packet[self.MBUS_OFF_FILE_RECORD_HI + offset] << 8
                    | Packet[self.MBUS_OFF_FILE_RECORD_LOW + offset] & 0x00FF
                )
            else:
                Register = (
                    Packet[self.MBUS_OFF_REGISTER_HI + offset] << 8
                    | Packet[self.MBUS_OFF_REGISTER_LOW + offset] & 0x00FF
                )
            return Register
        except Exception as e1:
            self.LogErrorLine("Error in GetRegisterFromPacket: " + str(e1))
            return Register

    # ---------- ModbusProtocol::CreateMasterPacket-----------------------------
    # the length is the register length in words, as required by modbus
    # build Packet
    def CreateMasterPacket(self, register, length=1, command=None, data=[], file_num=1):

        Packet = []
        try:
            if command == None:
                command = self.MBUS_CMD_READ_REGS

            RegisterInt = int(register, 16)

            if RegisterInt < self.MIN_REGISTER or RegisterInt > self.MAX_REGISTER:
                self.ComValidationError += 1
                self.LogError(
                    "Validation Error: CreateMasterPacket maximum regiseter value exceeded: "
                    + str(register)
                )
                return []
            if file_num < self.MIN_FILE_NUMBER or file_num > self.MAX_FILE_NUMBER:
                self.ComValidationError += 1
                self.LogError(
                    "Validation Error: CreateMasterPacket maximum file number value exceeded: "
                    + str(file_num)
                )
                return []

            if command == self.MBUS_CMD_READ_REGS or command == self.MBUS_CMD_READ_COILS or command == self.MBUS_CMD_READ_INPUT_REGS:
                Packet.append(self.Address)  # address
                Packet.append(command)  # command
                Packet.append(RegisterInt >> 8)  # reg high
                Packet.append(RegisterInt & 0x00FF)  # reg low
                Packet.append(length >> 8)  # length / num coils high 
                Packet.append(length & 0x00FF)  # length / num coils low
                CRCValue = self.GetCRC(Packet)
                if CRCValue != None:
                    Packet.append(CRCValue & 0x00FF)  # CRC low
                    Packet.append(CRCValue >> 8)  # CRC high

            elif command == self.MBUS_CMD_WRITE_REGS:
                if len(data) == 0:
                    self.LogError(
                        "Validation Error: CreateMasterPacket invalid length (1) %x %x"
                        % (len(data), length)
                    )
                    self.ComValidationError += 1
                    return []
                if len(data) / 2 != length:
                    self.LogError(
                        "Validation Error: CreateMasterPacket invalid length (2) %x %x"
                        % (len(data), length)
                    )
                    self.ComValidationError += 1
                    return []
                Packet.append(self.Address)  # address
                Packet.append(command)  # command
                Packet.append(RegisterInt >> 8)  # reg higy
                Packet.append(RegisterInt & 0x00FF)  # reg low
                Packet.append(length >> 8)  # Num of Reg higy
                Packet.append(length & 0x00FF)  # Num of Reg low
                Packet.append(len(data))  # byte count
                for b in range(0, len(data)):
                    Packet.append(data[b])  # data
                CRCValue = self.GetCRC(Packet)
                if CRCValue != None:
                    Packet.append(CRCValue & 0x00FF)  # CRC low
                    Packet.append(CRCValue >> 8)  # CRC high

            elif command == self.MBUS_CMD_READ_FILE:

                # Note, we only support one sub request at at time
                if (
                    RegisterInt < self.MIN_FILE_RECORD_NUM
                    or RegisterInt > self.MAX_FILE_RECORD_NUM
                ):
                    self.ComValidationError += 1
                    self.LogError(
                        "Validation Error: CreateMasterPacket maximum regiseter (record number) value exceeded: "
                        + str(register)
                    )
                    return []
                Packet.append(self.Address)  # address
                Packet.append(command)  # command
                Packet.append(self.MBUS_READ_FILE_REQUEST_PAYLOAD_LENGTH)  # Byte count
                Packet.append(self.MBUS_FILE_TYPE_VALUE)  # always same value
                Packet.append(file_num >> 8)  # File Number hi
                Packet.append(file_num & 0x00FF)  # File Number low
                Packet.append(RegisterInt >> 8)  # register (file record number) high
                Packet.append(RegisterInt & 0x00FF)  # register (file record number) low
                Packet.append(length >> 8)  # Length to return hi
                Packet.append(length & 0x00FF)  # Length to return lo
                CRCValue = self.GetCRC(Packet)
                if CRCValue != None:
                    Packet.append(CRCValue & 0x00FF)  # CRC low
                    Packet.append(CRCValue >> 8)  # CRC high
            elif command == self.MBUS_CMD_WRITE_FILE:
                # Note, we only support one sub request at at time
                if (
                    RegisterInt < self.MIN_FILE_RECORD_NUM
                    or RegisterInt > self.MAX_FILE_RECORD_NUM
                ):
                    self.ComValidationError += 1
                    self.LogError(
                        "Validation Error: CreateMasterPacket maximum regiseter (write record number) value exceeded: "
                        + str(register)
                    )
                    return []
                if len(data) / 2 != length:
                    self.LogError(
                        "Validation Error: CreateMasterPacket invalid length (3) %x %x"
                        % (len(data), length)
                    )
                    self.ComValidationError += 1
                    return []
                Packet.append(self.Address)  # address
                Packet.append(command)  # command
                Packet.append(
                    length * 2 + self.MBUS_FILE_WRITE_REQ_SIZE_MINUS_LENGTH
                )  # packet payload size from here
                Packet.append(self.MBUS_FILE_TYPE_VALUE)  # always same value
                Packet.append(file_num >> 8)  # File Number hi
                Packet.append(file_num & 0x00FF)  # File Number low
                Packet.append(RegisterInt >> 8)  # register (file record number) high
                Packet.append(RegisterInt & 0x00FF)  # register (file record number) low
                Packet.append(length >> 8)  # Length to return hi
                Packet.append(length & 0x00FF)  # Length to return lo
                for b in range(0, len(data)):
                    Packet.append(data[b])  # data
                CRCValue = self.GetCRC(Packet)
                if CRCValue != None:
                    Packet.append(CRCValue & 0x00FF)  # CRC low
                    Packet.append(CRCValue >> 8)  # CRC high

            else:
                self.LogError(
                    "Validation Error: Invalid command in CreateMasterPacket!"
                )
                self.ComValidationError += 1
                return []
        except Exception as e1:
            self.LogErrorLine("Error in CreateMasterPacket: " + str(e1))

        if len(Packet) > self.MAX_MODBUS_PACKET_SIZE:
            self.LogError(
                "Validation Error: CreateMasterPacket: Packet size exceeds max size"
            )
            self.ComValidationError += 1
            return []

        if self.ModbusTCP:
            return self.ConvertToModbusModbusTCP(Packet)
        return Packet

    # -------------ModbusProtocol::GetTransactionID------------------------------
    def GetTransactionID(self):

        ID = self.TransactionID
        self.CurrentTransactionID = ID
        self.TransactionID += 1
        if self.TransactionID > 0xFFFF:
            self.TransactionID = 0

        return ID

    # -------------ModbusProtocol::ConvertToModbusModbusTCP----------------------
    def ConvertToModbusModbusTCP(self, Packet):

        # byte 0:   transaction identifier - copied by server - usually 0
        # byte 1:   transaction identifier - copied by server - usually 0
        # byte 2:   protocol identifier = 0
        # byte 3:   protocol identifier = 0
        # byte 4:   length field (upper byte) = 0 (since all messages are smaller than 256)
        # byte 5:   length field (lower byte) = number of bytes following
        # byte 6:   unit identifier (previously 'slave address')
        # byte 7:   MODBUS function code
        # byte 8 on:    data as needed
        try:
            if not self.ModbusTCP:
                return Packet
            # remove last two bytes of CRC
            Packet.pop()
            Packet.pop()
            length = len(Packet)
            # byte 6 (slave address) is already provided in the Packet argument
            Packet.insert(
                0, length & 0xFF
            )  # byte 5:   length field (lower byte) = number of bytes following
            Packet.insert(
                0, length & 0xFF00
            )  # byte 4:   length field (upper byte) = 0 (since all messages are smaller than 256)
            Packet.insert(0, 0)  # byte 3:   protocol identifier = 0
            Packet.insert(0, 0)  # byte 2:   protocol identifier = 0
            TransactionID = self.GetTransactionID()
            Packet.insert(
                0, TransactionID & 0xFF
            )  # byte 1:   transaction identifier (low)- copied by server - usually 0
            Packet.insert(
                0, (TransactionID & 0xFF00) >> 8
            )  # byte 0:   transaction identifier (high)- copied by server - usually 0
            return Packet
        except Exception as e1:
            self.LogErrorLine("Error in CreateModbusTCPHeader: " + str(e1))
            return []

    # -------------ModbusProtocol::SendPacketAsMaster----------------------------
    def SendPacketAsMaster(self, Packet):

        try:
            ByteArray = bytearray(Packet)
            self.TxPacketCount += 1
            self.Slave.Write(ByteArray)
        except Exception as e1:
            self.LogErrorLine("Error in SendPacketAsMaster: " + str(e1))
            self.LogHexList(Packet, prefix="Packet")

    # ---------- ModbusProtocol::UpdateRegistersFromPacket----------------------
    #    Update our internal register list based on the request/response packet
    def UpdateRegistersFromPacket(
        self, MasterPacket, SlavePacket, SkipUpdate=False, ReturnString=False
    ):
        return self._URFP(MasterPacket, SlavePacket, SkipUpdate, ReturnString)

    # ---------- ModbusProtocol::URFP-------------------------------------------
    #    Called from UpdateRegistersFromPacket
    def _URFP(self, MasterPacket, SlavePacket, SkipUpdate=False, ReturnString=False):

        try:

            if (
                len(MasterPacket) < self.MIN_PACKET_RESPONSE_LENGTH
                or len(SlavePacket) < self.MIN_PACKET_RESPONSE_LENGTH
            ):
                self.LogError(
                    "Validation Error, length: Master "
                    + str(len(MasterPacket))
                    + " Slave: "
                    + str(len(SlavePacket))
                )
                return "Error"

            if self.ModbusTCP:
                PacketOffset = self.MODBUS_TCP_HEADER_SIZE
            else:
                PacketOffset = 0
            if MasterPacket[self.MBUS_OFF_ADDRESS + PacketOffset] != self.Address:
                self.LogError(
                    "Validation Error: Invalid address in UpdateRegistersFromPacket (Master)"
                )
                return "Error"
            if not self.CheckResponseAddress(SlavePacket[self.MBUS_OFF_ADDRESS]):
                self.LogError(
                    "Validation Error: Invalid address in UpdateRegistersFromPacket (Slave)"
                )
                return "Error"
            if not SlavePacket[self.MBUS_OFF_COMMAND] in [
                self.MBUS_CMD_READ_COILS,
                self.MBUS_CMD_READ_INPUT_REGS,
                self.MBUS_CMD_READ_REGS,
                self.MBUS_CMD_WRITE_REGS,
                self.MBUS_CMD_READ_FILE,
                self.MBUS_CMD_WRITE_FILE,
            ]:
                self.LogError(
                    "Validation Error: Unknown Function slave %02x %02x"
                    % (
                        SlavePacket[self.MBUS_OFF_ADDRESS],
                        SlavePacket[self.MBUS_OFF_COMMAND],
                    )
                )
                return "Error"
            if not MasterPacket[self.MBUS_OFF_COMMAND + PacketOffset] in [
                self.MBUS_CMD_READ_COILS,
                self.MBUS_CMD_READ_INPUT_REGS,
                self.MBUS_CMD_READ_REGS,
                self.MBUS_CMD_WRITE_REGS,
                self.MBUS_CMD_READ_FILE,
                self.MBUS_CMD_WRITE_FILE,
            ]:
                self.LogError(
                    "Validation Error: Unknown Function master %02x %02x"
                    % (
                        MasterPacket[self.MBUS_OFF_ADDRESS],
                        MasterPacket[self.MBUS_OFF_COMMAND],
                    )
                )
                return "Error"

            if (
                MasterPacket[self.MBUS_OFF_COMMAND + PacketOffset]
                != SlavePacket[self.MBUS_OFF_COMMAND]
            ):
                self.LogError(
                    "Validation Error: Command Mismatch :"
                    + str(MasterPacket[self.MBUS_OFF_COMMAND])
                    + ":"
                    + str(SlavePacket[self.MBUS_OFF_COMMAND])
                )
                return "Error"

            # get register from master packet
            Register = "%04x" % (
                self.GetRegisterFromPacket(MasterPacket, offset=PacketOffset)
            )

            if MasterPacket[self.MBUS_OFF_COMMAND + PacketOffset] in [
                self.MBUS_CMD_WRITE_REGS,
                self.MBUS_CMD_WRITE_FILE,
            ]:
                # get register from slave packet
                SlaveRegister = "%04x" % (self.GetRegisterFromPacket(SlavePacket))
                if SlaveRegister != Register:
                    self.LogError(
                        "Validation Error: Master Slave Register Mismatch : "
                        + Register
                        + ":"
                        + SlaveRegister
                    )
                    return "Error"

            RegisterValue = ""
            RegisterStringValue = ""
            if (MasterPacket[self.MBUS_OFF_COMMAND + PacketOffset] == self.MBUS_CMD_READ_REGS or
                MasterPacket[self.MBUS_OFF_COMMAND + PacketOffset] == self.MBUS_CMD_READ_INPUT_REGS or
                MasterPacket[self.MBUS_OFF_COMMAND + PacketOffset] == self.MBUS_CMD_READ_COILS
            ):
                IsCoil = False      # Mobus funciton 01
                IsInput = False     # Modubs function 04
                # get value from slave packet
                length = SlavePacket[self.MBUS_OFF_RESPONSE_LEN]
                if MasterPacket[self.MBUS_OFF_COMMAND + PacketOffset] == self.MBUS_CMD_READ_COILS:
                    IsCoil = True
                elif MasterPacket[self.MBUS_OFF_COMMAND + PacketOffset] == self.MBUS_CMD_READ_INPUT_REGS:
                    IsInput = True
                if (length + self.MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH) > len(
                    SlavePacket
                ):
                    self.LogError(
                        "Validation Error: Slave Length : "
                        + length
                        + ":"
                        + len(SlavePacket)
                    )
                    return "Error"

                for i in range(3, length + 3):
                    RegisterValue += "%02x" % SlavePacket[i]
                    if ReturnString:
                        if SlavePacket[i]:
                            RegisterStringValue += chr(SlavePacket[i])
                # update register list
                if not SkipUpdate:
                    if not self.UpdateRegisterList == None:
                        if not ReturnString:
                            if not self.UpdateRegisterList(Register, RegisterValue, IsCoil = IsCoil, IsInput = IsInput):
                                self.ComSyncError += 1
                                return "Error"
                        else:
                            if not self.UpdateRegisterList(Register, RegisterStringValue, IsString=True, IsCoil = IsCoil, IsInput = IsInput):
                                self.ComSyncError += 1
                                return "Error"

            if (
                MasterPacket[self.MBUS_OFF_COMMAND + PacketOffset]
                == self.MBUS_CMD_READ_FILE
            ):
                payloadLen = SlavePacket[self.MBUS_OFF_FILE_PAYLOAD_LEN]
                if not self.AlternateFileProtocol:
                    # TODO This is emperical
                    payloadLen -= 1
                for i in range(
                    self.MBUS_OFF_FILE_PAYLOAD,
                    (self.MBUS_OFF_FILE_PAYLOAD + payloadLen),
                ):
                    RegisterValue += "%02x" % SlavePacket[i]
                    if ReturnString:
                        if SlavePacket[i]:
                            RegisterStringValue += chr(SlavePacket[i])

                if not SkipUpdate:
                    if not ReturnString:
                        if not self.UpdateRegisterList(
                            Register, RegisterValue, IsFile=True
                        ):
                            self.ComSyncError += 1
                            return "Error"
                    else:
                        if not self.UpdateRegisterList(
                            Register, RegisterStringValue, IsString=True, IsFile=True
                        ):
                            self.ComSyncError += 1
                            return "Error"

            if ReturnString:
                return str(RegisterStringValue)
            return str(RegisterValue)
        except Exception as e1:
            self.LogErrorLine("Error in UpdateRegistersFromPacket: " + str(e1))
            return "Error"

    # ------------ModbusProtocol::CheckCrc--------------------------------------
    def CheckCRC(self, Packet):

        try:
            if self.ModbusTCP:
                return True

            if len(Packet) == 0:
                return False
            ByteArray = bytearray(Packet[: len(Packet) - 2])

            if sys.version_info[0] < 3:
                results = self.ModbusCrc(str(ByteArray))
            else:  # PYTHON3
                results = self.ModbusCrc(ByteArray)

            CRCValue = ((Packet[-1] & 0xFF) << 8) | (Packet[-2] & 0xFF)
            if results != CRCValue:
                self.LogError(
                    "Data Error: CRC check failed: %04x  %04x" % (results, CRCValue)
                )
                return False
            return True
        except Exception as e1:
            self.LogErrorLine("Error in CheckCRC: " + str(e1))
            self.LogHexList(Packet, prefix="Packet")
            return False

    # ------------ModbusProtocol::GetCRC----------------------------------------
    def GetCRC(self, Packet):
        try:
            if len(Packet) == 0:
                return None
            ByteArray = bytearray(Packet)

            if sys.version_info[0] < 3:
                results = self.ModbusCrc(str(ByteArray))
            else:  # PYTHON3
                results = self.ModbusCrc(ByteArray)

            return results
        except Exception as e1:
            self.LogErrorLine("Error in GetCRC: " + str(e1))
            self.LogHexList(Packet, prefix="Packet")
            return None

    # ---------- ModbusProtocol::GetCommStats-----------------------------------
    def GetCommStats(self):
        SerialStats = []

        try:
            SerialStats.append(
                {
                    "Packet Count": "M: %d, S: %d"
                    % (self.TxPacketCount, self.RxPacketCount)
                }
            )

            if self.CrcError == 0 or self.TxPacketCount == 0:
                PercentErrors = 0.0
            else:
                PercentErrors = float(self.CrcError) / float(self.TxPacketCount)

            if self.ComTimoutError == 0 or self.TxPacketCount == 0:
                PercentTimeoutErrors = 0.0
            else:
                PercentTimeoutErrors = float(self.ComTimoutError) / float(
                    self.TxPacketCount
                )

            SerialStats.append({"CRC Errors": "%d " % self.CrcError})
            SerialStats.append(
                {"CRC Percent Errors": ("%.2f" % (PercentErrors * 100)) + "%"}
            )
            SerialStats.append({"Timeout Errors": "%d" % self.ComTimoutError})
            SerialStats.append(
                {
                    "Timeout Percent Errors": ("%.2f" % (PercentTimeoutErrors * 100))
                    + "%"
                }
            )
            SerialStats.append({"Modbus Exceptions": self.ModbusException})
            SerialStats.append({"Validation Errors": self.ComValidationError})
            SerialStats.append({"Sync Errors": self.ComSyncError})
            SerialStats.append({"Invalid Data": self.UnexpectedData})
            # add serial stats
            SerialStats.append({"Discarded Bytes": "%d" % self.Slave.DiscardedBytes})
            SerialStats.append({"Comm Restarts": "%d" % self.Slave.Restarts})

            CurrentTime = datetime.datetime.now()
            #
            Delta = CurrentTime - self.ModbusStartTime  # yields a timedelta object
            PacketsPerSecond = float((self.TxPacketCount + self.RxPacketCount)) / float(
                Delta.total_seconds()
            )
            SerialStats.append({"Packets Per Second": "%.2f" % (PacketsPerSecond)})

            if self.RxPacketCount:
                AvgTransactionTime = float(
                    self.TotalElapsedPacketeTime / self.RxPacketCount
                )
                SerialStats.append(
                    {"Average Transaction Time": "%.4f sec" % (AvgTransactionTime)}
                )
            if not self.UseTCP:
                SerialStats.append({"Modbus Transport": "Serial"})
                SerialStats.append({"Serial Data Rate": "%d" % (self.Slave.BaudRate)})
            else:
                SerialStats.append({"Modbus Transport": "TCP"})
        except Exception as e1:
            self.LogErrorLine("Error in GetCommStats: " + str(e1))
        return SerialStats

    # ---------- ModbusProtocol::ResetCommStats---------------------------------
    def ResetCommStats(self):

        try:
            self.RxPacketCount = 0
            self.TxPacketCount = 0
            self.TotalElapsedPacketeTime = 0
            self.ModbusStartTime = datetime.datetime.now()  # used for com metrics
            self.Slave.ResetSerialStats()
        except Exception as e1:
            self.LogErrorLine("Error in ResetCommStats: " + str(e1))

    # ------------ModbusProtocol::Flush------------------------------------------
    def Flush(self):

        with self.CommAccessLock:
            self.Slave.Flush()

    # ------------ModbusProtocol::Close------------------------------------------
    def Close(self):
        self.IsStopping = True
        with self.CommAccessLock:
            self.Slave.Close()
