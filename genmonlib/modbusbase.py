#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: modbusbase.py
# PURPOSE: Base modbus class support
#
#  AUTHOR: Jason G Yates
#    DATE: 19-Apr-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

from __future__ import print_function       # For python 3.x compatibility with print function

import datetime, threading, crcmod, sys, time, os

from genmonlib.mysupport import MySupport
from genmonlib.mylog import SetupLogger
from genmonlib.program_defaults import ProgramDefaults


#------------ ModbusBase class -------------------------------------------------
class ModbusBase(MySupport ):
    #--------------------- MODBUS specific Const defines for modbus class-------
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
    MBUS_OFF_READ_REG_RES_DATA  = 0x03
    MBUS_OFF_WRITE_REG_REQ_DATA = 0x07

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

    # Exception codes
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

    #-------------------------__init__------------------------------------------
    def __init__(self,
        updatecallback,
        address = 0x9d,
        name = "/dev/serial",
        rate=9600,
        config = None):

        super(ModbusBase, self).__init__()
        self.Address = address
        self.Rate = rate
        self.PortName = name
        self.config = config
        self.InitComplete = False
        self.IsStopping = False
        self.UpdateRegisterList = updatecallback
        self.RxPacketCount = 0
        self.TxPacketCount = 0
        self.ComTimoutError = 0
        self.TotalElapsedPacketeTime = 0
        self.ModbusException = 0
        self.ExcepFunction = 0
        self.ExcepAddress = 0
        self.ExcepData = 0
        self.ExcepSlave = 0
        self.ExcepAck = 0
        self.ExcepBusy = 0
        self.ExcepNack = 0
        self.ExcepMemPe = 0
        self.ExcepGateway = 0
        self.ExcepGateWayTg = 0
        self.CrcError = 0
        self.ComValidationError = 0
        self.ComSyncError = 0
        self.UnexpectedData = 0
        self.SlowCPUOptimization = False
        self.UseTCP = False
        self.AdditionalModbusTimeout = 0
        self.ModBusPacketTimoutMS = 0
        self.ResponseAddress = None         # Used if recieve packes have a different address than sent packets
        self.debug = False

        if self.config != None:
            self.debug = self.config.ReadValue('debug', return_type = bool, default = False)
            self.loglocation = self.config.ReadValue('loglocation', default = ProgramDefaults.LogPath)
            self.SlowCPUOptimization = self.config.ReadValue('optimizeforslowercpu', return_type = bool, default = False)
            self.UseTCP = self.config.ReadValue('use_serial_tcp', return_type = bool, default = False)
            try:
                self.Address = int(self.config.ReadValue('address', default = '9d'),16)         # modbus address
            except:
                self.Address = 0x9d
            self.AdditionalModbusTimeout = self.config.ReadValue('additional_modbus_timeout', return_type = float, default = 0.0)
            ResponseAddressStr = self.config.ReadValue('response_address', default = None)
            if ResponseAddressStr != None:
                try:
                    self.ResponseAddress = int(ResponseAddressStr,16)         # response modbus address
                except:
                    self.ResponseAddress = None
        else:
            self.loglocation = default = './'


        self.CommAccessLock = threading.RLock()     # lock to synchronize access to the serial port comms
        self.ModbusStartTime = datetime.datetime.now()     # used for com metrics

        # log errors in this module to a file
        self.log = SetupLogger("mymodbus", os.path.join(self.loglocation, "mymodbus.log"))
        self.console = SetupLogger("mymodbus_console", log_file = "", stream = True)

    #-------------ModbusBase::ProcessWriteTransaction---------------------------
    def ProcessWriteTransaction(self, Register, Length, Data):
        return

    #-------------ModbusBase::ProcessTransaction--------------------------------
    def ProcessTransaction(self, Register, Length, skipupdate = False, ReturnString = False):
        return

    #-------------ModbusProtocol::ProcessFileReadTransaction--------------------
    def ProcessFileReadTransaction(self, Register, Length, skipupdate = False, file_num = 1, ReturnString = False):
        return
    # ---------- ModbusBase::GetCommStats---------------------------------------
    def GetCommStats(self):
        SerialStats = []

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
        SerialStats.append({"Timeout Errors" : "%d" %  self.ComTimoutError})
        SerialStats.append({"Timeout Percent Errors" : ("%.2f" % (PercentTimeoutErrors * 100)) + "%"})
        SerialStats.append({"Modbus Exceptions" : self.ModbusException})
        SerialStats.append({"Validation Errors" : self.ComValidationError})
        SerialStats.append({"Sync Errors" : self.ComSyncError})
        SerialStats.append({"Invalid Data" : self.UnexpectedData})
        # Add serial stats here
        CurrentTime = datetime.datetime.now()

        #
        Delta = CurrentTime - self.ModbusStartTime        # yields a timedelta object
        PacketsPerSecond = float((self.TxPacketCount + self.RxPacketCount)) / float(Delta.total_seconds())
        SerialStats.append({"Packets Per Second" : "%.2f" % (PacketsPerSecond)})

        if self.ModBus.RxPacketCount:
            AvgTransactionTime = float(self.TotalElapsedPacketeTime / self.RxPacketCount)
            SerialStats.append({"Average Transaction Time" : "%.4f sec" % (AvgTransactionTime)})

        return SerialStats
    # ---------- ModbusBase::ResetCommStats-------------------------------------
    def ResetCommStats(self):
        self.RxPacketCount = 0
        self.TxPacketCount = 0
        self.CrcError = 0
        self.ComTimoutError = 0
        self.ComValidationError = 0
        self.ComSyncError = 0
        self.ModbusException = 0
        self.ExcepFunction = 0
        self.ExcepAddress = 0
        self.ExcepData = 0
        self.ExcepSlave = 0
        self.ExcepAck = 0
        self.ExcepBusy = 0
        self.ExcepNack = 0
        self.ExcepMemPe = 0
        self.ExcepGateway = 0
        self.ExcepGateWayTg = 0
        self.TotalElapsedPacketeTime = 0
        self.ModbusStartTime = datetime.datetime.now()     # used for com metrics
        pass

    #------------ModbusBase::Flush----------------------------------------------
    def Flush(self):
        pass

    #------------ModbusBase::Close----------------------------------------------
    def Close(self):
        pass
