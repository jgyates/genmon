#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: modbus_evo2.py
# PURPOSE: Modbus specific fuctions for Evolution 2
#
#  AUTHOR: Jason G Yates
#    DATE: 23-08-2020
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

from __future__ import print_function       # For python 3.x compatibility with print function

import datetime, threading, crcmod, sys, time, collections

from genmonlib.modbusbase import ModbusBase
from genmonlib.mymodbus import ModbusProtocol
from genmonlib.myserial import SerialDevice
from genmonlib.myserialtcp import SerialTCPDevice
from genmonlib.program_defaults import ProgramDefaults
from genmonlib.mycrypto import MyCrypto

#------------ ModbusEvo2 class -------------------------------------------------
class ModbusEvo2(ModbusProtocol):

    MBUS_EVO2_CMD_PREFIX    = 0xF1
    MBUS_EVO2_CMD_1         = 0x01  #
    MBUS_EVO2_CMD_2         = 0x51  #
    MBUS_EVO2_CMD_3         = 0xa7  #

    def __init__(self,
        updatecallback,
        address = 0x9d,
        name = "/dev/serial0",
        rate=9600,
        Parity = None,
        OnePointFiveStopBits = None,
        config = None,
        host = None,
        port = None):

        self.ParentCallback = updatecallback
        super(ModbusEvo2, self).__init__(updatecallback = self.ParentCallback, address = address, name = name,
        rate = rate, Parity = None, OnePointFiveStopBits = None,config = config, host = host, port = port)

        self.LastUnlockTime = None
        self.LastExectpionCount = self.ExcepAck
        self.ModbusEncapsulationRegister = "ea60"
        self.KeySent = False
        self.UnlockInterval = 3
        self.MaxExceptions = 2
        try:

            if self.config != None:
                self.UnlockInterval = self.config.ReadValue('evo2_unlock_interval', return_type = int, default = 3)
                self.MaxExceptions = self.config.ReadValue('evo2_max_except', return_type = int, default = 2)
            # initilization vector
            self.iv = b'\xC0\x94\xFB\xEB\xF5\x96\x43\x7F\xA2\x2E\xFA\x84\xFC\xC5\x21\x52'

            # 16 keys
            self.key = [    b'\x4A\x2A\xA3\xE4\x7E\xE0\x42\x2C\xA4\xBC\x8D\x1D\x52\xDE\xD9\x69',
                            b'\xEE\xFA\x10\x27\x80\xE7\x4F\x03\xB7\xD0\x32\x58\xC4\xD7\xF8\xE5',
                            b'\xFD\x79\xA9\xCF\xCF\x94\x40\x1D\x9A\x65\xA4\x7C\x97\xB3\x0C\xC2',
                            b'\x55\x99\xF2\xFB\x0D\x70\x49\x1A\xBC\x85\xF4\x58\x9E\xC1\x11\x48',
                            b'\xDB\xCF\x82\x6F\x42\xE8\x41\xDE\xBD\x64\xBB\xAC\x16\xFB\xB4\xD3',
                            b'\x84\xA1\xA5\xF7\x26\xA3\x47\xFE\x8A\x0F\xB5\xF1\xC1\x9E\xA3\xCF',
                            b'\x20\x9C\xD8\xDF\xAB\x2E\x47\x3E\xA2\xBF\xFE\xEA\xC1\xD4\x87\x8E',
                            b'\xEF\xA6\x7A\xD0\x81\xBC\x42\xEB\xB4\xDE\x51\xAE\x1A\x04\x73\xA7',
                            b'\x17\x3E\x13\x55\x77\xC3\x4D\x46\xAB\x2C\x5A\xD7\x95\x25\xE7\x62',
                            b'\xCC\x8D\x8F\x2A\x3B\x1B\x44\x96\xBD\x8B\x78\x78\xF8\xB2\xAF\x43',
                            b'\xA8\x50\x14\xDD\xE5\x38\x42\xDD\xA5\xE9\xA9\xAD\xB1\xD4\x84\xAE',
                            b'\x24\x43\xCE\xF9\x55\xCC\x42\xDA\x95\x77\xF9\xED\xEA\xE4\x1A\xA1',
                            b'\x3A\xC2\x6F\x6A\xFE\x08\x40\xC1\x80\x46\x39\x95\x69\x1D\x85\x2E',
                            b'\xA2\x42\x7B\x25\x57\x05\x43\x35\xB4\x79\x0A\x64\x66\x00\x07\xF6',
                            b'\xFD\xB5\xCF\x6C\x7D\xE6\x42\xA7\x92\xB4\x3C\xC9\xC7\x7B\x92\x57',
                            b'\xC7\x39\x70\xD5\xFC\xCA\x43\x0C\x8E\xCD\xEA\x54\xAF\x88\xA3\x67']

            self.LogDebug("KeySize = " + str(len(self.key[0])))
            self.crypto = MyCrypto(log = self.log, console = self.console, key = self.key[0], iv = self.iv)

        except Exception as e1:
            self.LogErrorLine("Error in ModbusEvo2 init: " + str(e1))

    #-------------ModbusEvo2::Encapsulating-------------------------------------
    def Encapsulating(self):
        return self.ExcepAck > self.MaxExceptions
    #-------------ModbusEvo2::ProcessTransaction--------------------------------
    def ProcessTransaction(self, Register, Length, skipupdate = False, ReturnString = False):

        if self.Encapsulating():
            self.SendUnlockSequence( Register, Length, skipupdate = False, ReturnString = False)

        # check Modbus exceptions and if needed change to encapsulated modbus calls
        return self._PT(Register, Length, skipupdate, ReturnString)

    #-------------ModbusProtocol::ProcessWriteTransaction-----------------------
    def ProcessWriteTransaction(self, Register, Length, Data):
        if self.Encapsulating():
            self.SendUnlockSequence(Register, Length, Data)

        return self._PWT(Register, Length, Data)

    #-------------ModbusEvo2::SendUnlockSequence--------------------------------
    # Send unlock sequence if it has not been sent in the last 5 min
    def SendUnlockSequence(self, Register, Length, skipupdate = False, ReturnString = False):

        try:
            if not (self.ExcepAck != self.LastExectpionCount or self.LastUnlockTime == None or
                self.GetDeltaTimeMinutes(datetime.datetime.now() - self.LastUnlockTime) > self.UnlockInterval):
                 return False

            self.LastUnlockTime = datetime.datetime.now()
            self.LastExectpionCount = self.ExcepAck
            # create the orignal read registers packet
            MasterPacket = self.CreateMasterPacket(Register, length = int(Length))

            if len(MasterPacket) == 0:
                return False

            try:
                # This appears to have the first byte set the encryption key and the key
                # the byte at index 9 should be 0xe3
                sn = b'\x00\x00\x00\x05\x06\x02\x04\x04\x01\xe3\x00\x00\x00\x00\x00\x00'
                zero_buffer = b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                # convert the modbus request to bytearray
                mpBytes = self.ConvertToBytes(MasterPacket)
                # encrypt the bytes, this will return a buffer that is multiples of block size bytes
                mp_crypttext = bytearray(self.crypto.EncryptBuff(mpBytes))
                # convert the non encrypted section to bytearray
                sn_plaintext = bytearray(self.ConvertToBytes(sn))
                # append encrypted bytes to non-encrypted data
                sn_plaintext.extend(mp_crypttext)
                # scramble bytes
                Data = self.NybbleSwap(list(sn_plaintext))
                # prepend control data bytes
                # format: X Y ENCRYPTED_DATA total length is 0x22 bytes
                Data.insert(0,self.MBUS_EVO2_CMD_PREFIX)
                Data.insert(1,self.MBUS_EVO2_CMD_1)
                self._PWT(self.ModbusEncapsulationRegister, len(Data) / 2, Data)
            except Exception as e1:
                self.LogErrorLine("Error (1) SendUnlockSequence: " + str(e1))

            try:
                # pad the buffer to 2x blocksize
                if len(MasterPacket) < (self.crypto.blocksize * 2):
                    for x in range(len(MasterPacket), (self.crypto.blocksize * 2)):
                        MasterPacket.append(0)
                # encrypt buffer
                mpBytes = self.ConvertToBytes(MasterPacket)
                mp_crypttext = self.crypto.EncryptBuff(mpBytes)
                # scamble bytes
                Data = self.NybbleSwap(list(mp_crypttext))
                Data.insert(0,self.MBUS_EVO2_CMD_PREFIX)
                Data.insert(1,self.MBUS_EVO2_CMD_2)
                self._PWT(self.ModbusEncapsulationRegister, len(Data) / 2, Data)
            except Exception as e1:
                self.LogErrorLine("Error (2) SendUnlockSequence: " + str(e1))
            try:

                plaintext_1 = bytearray(self.ConvertToBytes(zero_buffer))
                plaintext_2 = bytearray(self.ConvertToBytes(zero_buffer))
                plaintext_1.extend(plaintext_2)
                Data = list(sn_plaintext)
                Data.insert(0,self.MBUS_EVO2_CMD_PREFIX)
                Data.insert(1,self.MBUS_EVO2_CMD_3)
                # we set min_response_override to 6 here as the returned packet is
                # shorter than a typical modbus packt
                self._PWT(self.ModbusEncapsulationRegister, len(Data) / 2, Data, min_response_override = 6)

            except Exception as e1:
                self.LogErrorLine("Error (3) SendUnlockSequence: " + str(e1))

            return True
        except Exception as e1:
            self.LogErrorLine("Error in SendUnlockSequence: " + str(e1))
            return False
    # ---------- ModbusProtocol::GetControlBytes--------------------------------
    def GetControlBytes(self, Packet):

        if Packet[self.MBUS_OFF_COMMAND] == self.MBUS_CMD_READ_REGS:
            return [Packet[self.MBUS_OFF_READ_REG_RES_DATA], Packet[self.MBUS_OFF_READ_REG_RES_DATA + 1]]
        elif Packet[self.MBUS_OFF_COMMAND] == self.MBUS_CMD_WRITE_REGS:
            return [Packet[self.MBUS_OFF_WRITE_REG_REQ_DATA], Packet[self.MBUS_OFF_WRITE_REG_REQ_DATA + 1]]
        else:
            self.LogError("Invalid command type in GetControlBytes")
            self.LogHexList(MasterPacket, prefix = "Error Packet")
            return [0, 0]
    # ---------- ModbusProtocol::UpdateRegistersFromPacket----------------------
    #    Update our internal register list based on the request/response packet
    def UpdateRegistersFromPacket(self, MasterPacket, SlavePacket, SkipUpdate = False, ReturnString = False):

        try:

            # Here we get the full packets sent from the master (us) and the recived packet (slave)
            MasterRegister = "%04x" % (self.GetRegisterFromPacket(MasterPacket))
            if MasterRegister == self.ModbusEncapsulationRegister:

                # Master 0xf1, 0x01  ->  Slave 0xf1, 0x23
                # Master 0xf1, 0x51  ->  Slave 0xf1, 0x65
                # Master 0xf1, 0xa7 ->
                MasterControl = self.GetControlBytes(MasterPacket)
                #self.LogHexList(MasterPacket, prefix = "Master")
                #self.LogError("Master CMD: %02x" % MasterPacket[self.MBUS_OFF_COMMAND])

                #self.LogHexList(MasterControl, prefix = "Master Control Bytes")
                #self.LogError("Master Num Data Bytes: %d" % MasterPacket[self.MBUS_OFF_WR_REQ_BYTE_COUNT])
                # This should give us a list of 2x block size
                #MasterData = self.NybbleSwap(MasterPacket[self.MBUS_OFF_WR_REQ_BYTE_COUNT + 3:-2])

                #self.LogHexList(MasterData, prefix = "Master Data Bytes (pre decrypt, post swap)")
                # decrypt master
                # only decrypt 2nd block
                #if MasterControl == [self.MBUS_EVO2_CMD_PREFIX,self.MBUS_EVO2_CMD_1]:
                #    # in this instance just decrypt the 2nd block
                #    mpBytes = self.ConvertToBytes(MasterData[self.crypto.blocksize:])
                #else:
                #    mpBytes = self.ConvertToBytes(MasterData)
                #mp_plaintext = bytearray(self.crypto.DecryptBuff(mpBytes))
                #MasterData = list(mp_plaintext)

                #self.LogHexList(MasterData, prefix = "Original Master Packet")
                #self.LogHexList(SlavePacket, prefix = "Slave")
                #self.LogError("Slave CMD: %02x" % SlavePacket[self.MBUS_OFF_COMMAND])
                #SlaveControl = self.GetControlBytes(SlavePacket)
                #self.LogHexList(SlaveControl, prefix = "Slave Control Bytes")
                #self.LogError("Slave Num Data Bytes: %d" % SlavePacket[self.MBUS_OFF_RESPONSE_LEN])
                #SlaveData = self.NybbleSwap(SlavePacket[self.MBUS_OFF_RESPONSE_LEN + 3:-2])
                # decrypt slave
                #spBytes = self.ConvertToBytes(SlaveData)
                #sp_plaintext = bytearray(self.crypto.DecryptBuff(spBytes))
                #SlaveData = list(sp_plaintext)
                #self.LogHexList(SlaveData, prefix = "Returned Slave Packet")
                if MasterControl == [self.MBUS_EVO2_CMD_PREFIX,self.MBUS_EVO2_CMD_3]:
                    self.LogDebug("Unlock Response sent/recieved")
                return ""
            else:
                return self._URFP(MasterPacket, SlavePacket, SkipUpdate, ReturnString)
        except Exception as e1:
            self.LogErrorLine("Error in UpdateRegistersFromPacket : " + str(e1))
            return "Error"
    #-------------ModbusEvo2::ConvertToBytes------------------------------------
    # convert list to bytes
    def ConvertToBytes(self, Buffer):

        try:
            if sys.version_info[0] < 3:
                byte_output = bytearray("")
                for i in range(0, len(Buffer)):
                    if isinstance(Buffer[i], str):
                        byte_output.append(ord(Buffer[i]))
                    else:
                        byte_output.append(Buffer[i])
                return byte_output
            else:
                return bytes(Buffer)
        except Exception as e1:
            self.LogErrorLine("Error in ConvertToBytes: " + str(e1))
            return Buffer
    #-------------ModbusEvo2::ConvertToInts-------------------------------------
    # convert all items in list to ints
    def ConvertToInts(self, Buffer):
        try:
            # converts items in list from str to int if needed
            for i in range(0, len(Buffer)):
                if isinstance(Buffer[i], str):
                    Buffer[i] = ord(Buffer[i])
            return Buffer
        except Exception as e1:
            self.LogErrorLine("Error in ConvertToInts: " + str(e1))
            return Buffer
    #-------------ModbusEvo2::NybbleSwap----------------------------------------
    def NybbleSwap(self, Buffer):

        try:
            Buffer = self.ConvertToInts(Buffer)
            # assumes Buffer is a list of ints
            blocksize = self.crypto.blocksize
            if len(Buffer) != (blocksize * 2):
                 self.LogError("Error in NybbleSwap: Invalid buffer length : " + str(len(Buffer)))

            for i in range(0, int((len(Buffer) / 2))):
                Temp1 = Buffer[i]
                Temp2 = Buffer[i +blocksize]

                if (i % 2) == 0:    # even
                    Buffer[i] = ((Temp2 << 4) | (Temp1 & 0xf)) & 0xff
                    Buffer[i + blocksize] = ((Temp1 >> 4) | (Temp2 & 0xf0)) & 0xff
                else:               # odd
                    Buffer[i] =((Temp2 & 0xf0) | (Temp1 & 0xf)) & 0xff
                    Buffer[i + blocksize] =((Temp1 & 0xf0) + (Temp2 & 0xf)) & 0xff

            return Buffer
        except Exception as e1:
            self.LogErrorLine("Error in NybbleSwap: " + str(e1))
            return Buffer
