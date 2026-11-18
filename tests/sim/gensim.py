#!/usr/bin/env python3
#-------------------------------------------------------------------------------
#    FILE: gensim.py
# PURPOSE: Simulator for Generator Monitor: answers genmon's Modbus requests
#          from a register file (a genmon register dump) over TCP, as a
#          generator controller would over the serial port. genmon connects to
#          it with use_serial_tcp. Writes are logged, not applied.
#
#          Used by tests/test_genmon_sim.py. To run it by hand:
#              python3 tests/sim/gensim.py <folder with gensim.conf>/
#          (see tests/sim/gensim.conf for the settings)
#
#  AUTHOR: Jason G Yates
#    DATE: 11-Oct-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import datetime, time, sys, signal, os, threading, socket, collections, json, math
import subprocess, platform, ipaddress

try:
    import crcmod
except Exception:
    print("crcmod library is not installed!")
    sys.exit(1)

# genmonlib is two folders up (tests/sim/gensim.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from genmonlib.mysupport import MySupport
    from genmonlib.mylog import SetupLogger
    from genmonlib.mythread import MyThread
    from genmonlib.myconfig import MyConfig
except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)

#--------------------- MODBUS specific Const defines for Generator class--------
# Packet offsets
MBUS_OFF_ADDRESS = 0x00
MBUS_OFF_COMMAND = 0x01
MBUS_OFF_EXCEPTION = 0x02
MBUS_OFF_RESPONSE_LEN = 0x02
MBUS_OFF_FILE_TYPE = 0x04  # offset in response packet (file read)
MBUS_OFF_WRITE_FILE_TYPE = 0x03  # offset in response packet
MBUS_OFF_FILE_PAYLOAD_LEN = 0x03
MBUS_OFF_FILE_PAYLOAD = 0x05
MBUS_OFF_REGISTER_HI = 0x02
MBUS_OFF_REGISTER_LOW = 0x03
MBUS_OFF_SINGLE_WRITE_VALUE_HI = 0x04
MBUS_OFF_SINGLE_WRITE_VALUE_LOW = 0x05
MBUS_OFF_FILE_NUM_HI = 0x04
MBUS_OFF_FILE_NUM_LOW = 0x05
MBUS_OFF_FILE_RECORD_HI = 0x06
MBUS_OFF_FILE_RECORD_LOW = 0x07
MBUS_OFF_RECORD_LENGTH_HI = 0x08
MBUS_OFF_RECORD_LENGTH_LOW = 0x09
MBUS_OFF_LENGTH_HI = 0x04
MBUS_OFF_LENGTH_LOW = 0x05
MBUS_OFF_WR_REQ_BYTE_COUNT = 0x06
MBUS_OFF_READ_REG_RES_DATA = 0x03
MBUS_OFF_WRITE_REG_REQ_DATA = 0x07

# Field Sizes
MBUS_ADDRESS_SIZE = 0x01
MBUS_COMMAND_SIZE = 0x01
MBUS_CRC_SIZE = 0x02
MBUS_RES_LENGTH_SIZE = 0x01
MBUS_FILE_TYPE_SIZE = 0x01
MBUS_FILE_NUN_SIZE = 0x02
MBUS_RECORD_NUM_SIZE = 0x02
MBUS_RECORD_LENGTH_SIZE = 0x02
MBUS_REG_SIZE = 0x02
MBUS_VALUE_SIZE = 0x02

# Packet lengths
MODBUS_TCP_HEADER_SIZE = 0x06
MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH = (
    MBUS_ADDRESS_SIZE + MBUS_COMMAND_SIZE + MBUS_RES_LENGTH_SIZE + MBUS_CRC_SIZE
)
MBUS_FILE_READ_PAYLOAD_SIZE_MINUS_LENGTH = (
    MBUS_ADDRESS_SIZE + MBUS_COMMAND_SIZE + MBUS_RES_LENGTH_SIZE + MBUS_CRC_SIZE
)  # include bytes not in count

MBUS_SINGLE_WRITE_RES_LENGTH = (MBUS_ADDRESS_SIZE + MBUS_COMMAND_SIZE + MBUS_REG_SIZE + MBUS_VALUE_SIZE + MBUS_CRC_SIZE)

MBUS_SINGLE_WRITE_REQ_LENGTH = MBUS_SINGLE_WRITE_RES_LENGTH

MBUS_FILE_WRITE_REQ_SIZE_MINUS_LENGTH = (
    MBUS_FILE_TYPE_SIZE
    + MBUS_FILE_NUN_SIZE
    + MBUS_RECORD_NUM_SIZE
    + MBUS_RECORD_LENGTH_SIZE
)
MIN_PACKET_ERR_LENGTH = 0x05
MIN_PACKET_RESPONSE_LENGTH = 0x06           # change from 7 to 6 to accomiadate coil reads
MIN_PACKET_MIN_WRITE_RESPONSE_LENGTH = 0x08
MBUS_READ_FILE_REQUEST_PAYLOAD_LENGTH = 0x07
MIN_REQ_PACKET_LENGTH = 0x08
MIN_WR_REQ_PACKET_LENGTH = 0x09
MIN_FILE_READ_REQ_PACKET_LENGTH = 0x0C
MAX_MODBUS_PACKET_SIZE = 0x100
# Varible limits
MAX_REGISTER = 0xFFFF
MIN_REGISTER = 0x0
MAX_FILE_RECORD_NUM = 0x270F  # 9999 decimal
MIN_FILE_RECORD_NUM = 0x0
MAX_FILE_NUMBER = 0xFFFF
MIN_FILE_NUMBER = 0x01
# commands
MBUS_CMD_READ_COILS = 0x01          # Read multiple coils
MBUS_CMD_READ_DISCRETE_INPUTS = 0x02    # read multiple discrete inputs (bits)
MBUS_CMD_READ_HOLDING_REGS = 0x03       # Read Multiple Holding Registers
MBUS_CMD_READ_INPUT_REGS = 0x04     # Read multiple Inputs Registers
MBUS_CMD_WRITE_COIL = 0x05          # write single coil
MBUS_CMD_WRITE_REG = 0x06           # write single register
MBUS_CMD_WRITE_COILS = 0x0f         # Write multiple coils
MBUS_CMD_WRITE_REGS = 0x10          # Write multiple holding regs
MBUS_CMD_READ_FILE = 0x14
MBUS_CMD_WRITE_FILE = 0x15

# Values
MBUS_FILE_TYPE_VALUE = 0x06
MBUS_ERROR_BIT = 0x80

# Exception codes
MBUS_EXCEP_FUNCTION = 0x01  # Illegal Function
MBUS_EXCEP_ADDRESS = 0x02  # Illegal Address
MBUS_EXCEP_DATA = 0x03  # Illegal Data Value
MBUS_EXCEP_SLAVE_FAIL = 0x04  # Slave Device Failure
MBUS_EXCEP_ACK = 0x05  # Acknowledge
MBUS_EXCEP_BUSY = 0x06  # Slave Device Busy
MBUS_EXCEP_NACK = 0x07  # Negative Acknowledge
MBUS_EXCEP_MEM_PE = 0x08  # Memory Parity Error
MBUS_EXCEP_GATEWAY = 0x0a  # Gateway Path Unavailable
MBUS_EXCEP_GATEWAY_TG = 0x0b  # Gateway Target Device Failed to Respond

#------------ GenSim class -----------------------------------------------------
class GenSim(MySupport):
    #-------------------------__init__------------------------------------------
    def __init__(self, ConfigFilePath = "./"):
        super(GenSim, self).__init__()

        self.ProgramComplete = True
        self.IsStopping = False
        self.ConnectionList = []    # list of incoming connections for server
        self.Holding = {}
        self.Strings = {}
        self.FileData = {}
        self.Coils = {}
        self.Inputs = {}
        self.CRCErrors = 0
        self.SlaveException = 0
        self.ComTimoutError = 0
        self.ComValidationError = 0
        self.DiscardedBytes = 0
        self.TxPacketCount = 0
        self.RxPacketCount = 0
        self.RegisterFileLock = threading.Lock()        # lock for user data
        self.console = SetupLogger("gensim_console", log_file = "", stream = True)
        self.log = None

        self.config = MyConfig(filename = os.path.join(ConfigFilePath, 'gensim.conf'), section = "gensim", log = self.console)

        if not self.config.InitComplete:
            self.LogConsole("ERROR reading config file.")
            sys.exit(1)

        # log errors in this module to a file
        self.LogLocation = self.config.ReadValue("log_location", default = "./")
        self.log = SetupLogger("gensim", os.path.join(self.LogLocation, "gensim.log"))
        self.config.log = self.log
        # "" listens on every network interface, 127.0.0.1 only on this computer
        self.BindAddress = self.config.ReadValue("bind_address", default = "")

        self.Address = self.config.ReadValue("address", default = "9d")
        try:
            self.Address = int(self.Address, 16)
        except Exception:
            self.LogInfo("Error: invalid address: " + str(self.Address))

        self.debug = self.config.ReadValue("debug", return_type = bool, default = False)
        self.ServerSocketPort = self.config.ReadValue("server_socket", return_type = int, default = 9989)

        if self.IsLoaded():
            self.LogInfo("ERROR: gensim.py is already loaded (port %d is in use)." % self.ServerSocketPort)
            sys.exit(1)
        self.SimulationFile = self.config.ReadValue("register_file")

        if self.SimulationFile == None:
            self.LogInfo("ERROR: no register file specified.")
            sys.exit(1)

        self.LogConsole("Register File: " + self.SimulationFile)
        if not self.ReadInputFile(self.SimulationFile):
            self.LogInfo("ERROR reading register file.")
            sys.exit(1)

        if not self.AdjustInputData():
            self.LogInfo("Error parsing input data")
            sys.exit(1)

        try:
            # CRCMOD library, used for CRC calculations
            self.ModbusCrc = crcmod.predefined.mkCrcFun('modbus')
            self.InitComplete = True
        except Exception as e1:
            self.LogInfo("Unable to find crcmod package: " + str(e1))
            sys.exit(1)

        self.ProgramStartTime = datetime.datetime.now()     # used for com metrics
        self.LastUpdateTime = self.ProgramStartTime

        #atexit.register(self.Close)
        signal.signal(signal.SIGTERM, self.SignalClose)
        signal.signal(signal.SIGINT, self.SignalClose)

        try:
            self.HostName = socket.gethostname()
            self.HostIP = self.GetNetworkIp()
            self.LogConsole("Starting Simulation Server on " + self.HostName + " at " + self.HostIP + " on port " + str(self.ServerSocketPort))
        except Exception as e1:
            self.LogConsole("Unable to get Hostname and IP : " + str(e1))
            sys.exit(1)

        # start thread to accept incoming sockets for nagios heartbeat and command / status clients
        self.Threads["InterfaceServerThread"] = MyThread(self.InterfaceServerThread, Name = "InterfaceServerThread", start = False)
        self.Threads["InterfaceServerThread"].Start()
        self.Threads["RegisterFileMonitorThread"] = MyThread(self.RegisterFileMonitorThread, Name = "RegisterFileMonitorThread", start = False)
        self.Threads["RegisterFileMonitorThread"].Start()
        self.ProgramStartTime = datetime.datetime.now()     # used for com metrics

        self.ProgramComplete = False

    #----------  RegisterFileMonitorThread  ----------------------------------------------
    def RegisterFileMonitorThread(self):

        ModifiedTime =  os.stat(self.SimulationFile).st_mtime

        while True:
            try:
                if self.WaitForExit("RegisterFileMonitorThread", 2):  #
                    return

                NewTime =  os.stat(self.SimulationFile).st_mtime
                if NewTime == ModifiedTime:
                    continue

                ModifiedTime = NewTime

                with self.RegisterFileLock:
                    if not self.ReadInputFile(self.SimulationFile):
                        self.LogInfo("ERROR reading register file in RegisterFileMonitorThread.")

                    if not self.AdjustInputData():
                        self.LogInfo("Error parsing input data in RegisterFileMonitorThread")

            except Exception as e1:
                self.LogErrorLine("Error in  RegisterFileMonitorThread: " + str(e1))

    #----------  AdjustInputData  ----------------------------------------------
    def AdjustInputData(self):

        if not len(self.Holding) and not len(self.Inputs) and not len(self.Coils):
            self.LogError("Error in AdjustInputData, no data.")
            return False

        # lookups use lower case, zero padded 4 digit keys ("%04x")
        self.Holding = self.NormalizeKeys(self.Holding, "Holding")
        self.Inputs = self.NormalizeKeys(self.Inputs, "Inputs")
        self.Coils = self.NormalizeKeys(self.Coils, "Coils")
        self.Strings = self.NormalizeKeys(self.Strings, "Strings")
        self.FileData = self.NormalizeKeys(self.FileData, "FileData")

        self.SplitMultiWordRegisters(self.Holding)
        self.SplitMultiWordRegisters(self.Inputs)

        for Reg, Value in self.Strings.items():
            RegInt = int(Reg,16)
            if not len(Value):
                self.Holding["%04x" % (RegInt)] = "0000"
                continue
            if self.StringIsHex(Value):
                # Not a string, just hex data in a string format
                for i in range( 0, len(Value), 4):
                    self.Holding["%04x" % (RegInt + int(i / 4))] = Value[i:i+4]
            else:
                for i in range(0, len(Value), 2):
                    HiByte = ord(Value[i])
                    if i + 1 >= len(Value):
                        LowByte = 0
                    else:
                        LowByte = ord(Value[i+1])
                    self.Holding["%04x" % (RegInt + int(i / 2))] = "%02x%02x" % (HiByte, LowByte)


        return True

    #----------  NormalizeKeys  ------------------------------------------------
    def NormalizeKeys(self, Registers, Name):

        Result = collections.OrderedDict()
        for Reg, Value in Registers.items():
            try:
                Result["%04x" % int(Reg, 16)] = Value
            except (ValueError, TypeError):
                self.LogError("Invalid " + Name + " register in register file: " + str(Reg))
        return Result

    #----------  SplitMultiWordRegisters  --------------------------------------
    # values longer than one register are split into consecutive 16 bit registers
    def SplitMultiWordRegisters(self, Registers):

        TempRegisters = collections.OrderedDict()
        for Reg, Value in Registers.items():
            if len(Value) <= 4:
                continue
            RegInt = int(Reg, 16)
            for i in range(0, len(Value), 4):
                TempRegisters["%04x" % (RegInt + i // 4)] = Value[i:i+4]

        Registers.update(TempRegisters)

    #----------  ReadJSONFile  -------------------------------------------------
    def ReadJSONFile(self, FileName):

        if not len(FileName):
            self.LogError("Error in  ReadJSONFile: No Input File")
            return False

        try:
            with open(FileName) as f:
                data = json.load(f,object_pairs_hook=collections.OrderedDict)
                if "Holding" in data.keys():
                    self.Holding = data["Holding"]
                else:
                    self.Holding = data["Registers"]
                self.Strings = data["Strings"]
                self.FileData = data["FileData"]
                if "Coils" in data:
                    self.Coils = data["Coils"]
                else:
                    self.Coils = {}
                if "Inputs" in data:
                    self.Inputs = data["Inputs"]
                else:
                    self.Inputs = {}
            return True
        except Exception as e1:
            self.LogErrorLine("Error in ReadJSONFile: " + str(e1))
            return False

    #----------  ReadInputFile  ------------------------------------------------
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
                                            int(RegEntry[0], 16)  # both must be hex
                                            int(RegEntry[1], 16)
                                            self.Holding[RegEntry[0]] = RegEntry[1]

                                    except:
                                        continue
                    elif Section == STRINGS:
                        Items = line.split(" : ")
                        if len(Items) == 2:
                            self.Strings[Items[0]] = Items[1]
                        else:
                            pass
                            #self.LogError("Error in STRINGS: " + str(Items))
                    elif Section == FILE_DATA:
                        Items = line.split(" : ")
                        if len(Items) == 2:
                            self.FileData[Items[0]] = Items[1]
                        else:
                            pass
                            #self.LogError("Error in FILEDATA: " + str(Items))

            return True

        except Exception as e1:
            self.LogErrorLine("Error in  ReadInputFile: " + str(e1))
            return False

    #------------ModbusProtocol::CheckCrc---------------------------------------
    def CheckCRC(self, Packet):

       try:
           if len(Packet) == 0:
               return False
           ByteArray = bytearray(Packet[:len(Packet)-2])
           results = self.ModbusCrc(ByteArray)

           CRCValue = ( ( Packet[-1] & 0xFF ) << 8 ) | ( Packet[ -2] & 0xFF )
           if results != CRCValue:
               self.LogError("Data Error: CRC check failed: %04x  %04x" % (results, CRCValue))
               return False
           return True
       except Exception as e1:
           self.LogErrorLine("Error in CheckCRC: " + str(e1))
           self.LogInfo("Packet: " + str(Packet))
           return False

    #------------GetCRC---------------------------------------------------------
    def GetCRC(self, Packet):
       try:
           if len(Packet) == 0:
               return False
           ByteArray = bytearray(Packet)
           results = self.ModbusCrc(ByteArray)

           return results
       except Exception as e1:
           self.LogErrorLine("Error in GetCRC: " + str(e1))
           self.LogInfo("Packet: " + str(Packet))
           return 0
    #------------CreateExceptionPacket------------------------------------------
    def CreateExceptionPacket(self, MasterPacket, ExceptionCode):
        Packet = []

        try:
            Packet.append(self.Address)
            Packet.append(MasterPacket[MBUS_OFF_COMMAND] | MBUS_ERROR_BIT)
            Packet.append(ExceptionCode)
            CRCValue = self.GetCRC(Packet)
            Packet.append(CRCValue & 0x00FF)            # CRC low
            Packet.append(CRCValue >> 8)                # CRC high

            if not len(Packet) == MIN_PACKET_ERR_LENGTH:
                self.ComValidationError += 1
                self.LogError("Validation Error: CreateExceptionPacket lenght incorrect: " + str(len(Packet)))
            return Packet
        except Exception as e1:
            self.LogErrorLine("Error in CreateExceptionPacket: " + str(e1))
            return []

    #------------DiscardByte----------------------------------------------------
    def DiscardByte(self, Buffer):

        if len(Buffer):
            discard = Buffer.pop(0)
            self.DiscardedBytes += 1
            return discard

    #------------GetFileNumberFromPacket ---------------------------------------
    def GetFileNumberFromPacket(self, Packet):
        try:
            if Packet[MBUS_OFF_COMMAND] == MBUS_CMD_READ_FILE:
                return Packet[MBUS_OFF_FILE_NUM_HI] << 8 | Packet[MBUS_OFF_FILE_NUM_LOW] & 0x00FF
            else:
                return None
        except Exception as e1:
            self.LogErrorLine("Error in GetFileNumberFromPacket: " + str(e1))
            return None

    #------------GetLengthFromPacket -------------------------------------------
    def GetLengthFromPacket(self, Packet):
        try:
            if Packet[MBUS_OFF_COMMAND] == MBUS_CMD_READ_FILE:
                return Packet[MBUS_OFF_RECORD_LENGTH_HI] << 8 | Packet[MBUS_OFF_RECORD_LENGTH_LOW] & 0x00FF
            else:
                return Packet[MBUS_OFF_LENGTH_HI] << 8 |  Packet[MBUS_OFF_LENGTH_LOW] & 0x00FF
        except Exception as e1:
            self.LogErrorLine("Error in GetLengthFromPacket: " + str(e1))
            return None

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

    #------------GetReadFileMasterPacket ---------------------------------------
    def GetReadFileMasterPacket(self,Buffer):
        EmptyPacket = []
        ReturnPacket = []
        if Buffer[MBUS_OFF_COMMAND] != MBUS_CMD_READ_FILE:
            return False, EmptyPacket

        if len(Buffer) < MIN_FILE_READ_REQ_PACKET_LENGTH:
            return False, EmptyPacket   # wait for the rest of the packet

        for Count in range(MIN_FILE_READ_REQ_PACKET_LENGTH):
            ReturnPacket.append(Buffer.pop(0))

        return True, ReturnPacket
    #------------GetReadMasterPacket -------------------------------------------
    def GetReadMasterPacket(self, Buffer):
        EmptyPacket = []
        ReturnPacket = []
        if (Buffer[MBUS_OFF_COMMAND] != MBUS_CMD_READ_HOLDING_REGS and 
            Buffer[MBUS_OFF_COMMAND] != MBUS_CMD_READ_INPUT_REGS and 
            Buffer[MBUS_OFF_COMMAND] != MBUS_CMD_READ_COILS):
            return False, EmptyPacket

        if len(Buffer) < MIN_REQ_PACKET_LENGTH:
            return False, EmptyPacket   # wait for the rest of the packet

        for Count in range(MIN_REQ_PACKET_LENGTH):
            ReturnPacket.append(Buffer.pop(0))

        return True, ReturnPacket
    #------------GetWriteMasterPacket ------------------------------------------
    def GetWriteMasterPacket(self, Buffer):
        EmptyPacket = []
        ReturnPacket = []
        if not Buffer[MBUS_OFF_COMMAND] in [MBUS_CMD_WRITE_REGS, MBUS_CMD_WRITE_COILS, MBUS_CMD_WRITE_REG, MBUS_CMD_WRITE_COIL]:
            return False, EmptyPacket

        if Buffer[MBUS_OFF_COMMAND] in [MBUS_CMD_WRITE_REGS, MBUS_CMD_WRITE_COILS]:
            if len(Buffer) < MIN_WR_REQ_PACKET_LENGTH:
                return False, EmptyPacket

            AdditionalBytes = Buffer[MBUS_OFF_WR_REQ_BYTE_COUNT]

            if len(Buffer) < MIN_WR_REQ_PACKET_LENGTH + AdditionalBytes:
                return False, EmptyPacket

            for Count in range(MIN_WR_REQ_PACKET_LENGTH + AdditionalBytes):
                ReturnPacket.append(Buffer.pop(0))

        elif Buffer[MBUS_OFF_COMMAND] in [MBUS_CMD_WRITE_REG, MBUS_CMD_WRITE_COIL]:
            if len(Buffer) < MBUS_SINGLE_WRITE_REQ_LENGTH:
                return False, EmptyPacket
            for Count in range(MBUS_SINGLE_WRITE_REQ_LENGTH):
                ReturnPacket.append(Buffer.pop(0))

        return True, ReturnPacket

    #------------ProcessFileReadRequest ----------------------------------------
    def ProcessFileReadRequest(self, Buffer):
        EmptyPacket  = []
        ReturnPacket = []

        try:
            if Buffer[MBUS_OFF_COMMAND] != MBUS_CMD_READ_FILE:
                return False, EmptyPacket

            if len(Buffer) < MIN_FILE_READ_REQ_PACKET_LENGTH:
                return False, EmptyPacket

            self.RxPacketCount += 1

            if not self.CheckCRC(Buffer):
                self.CRCErrors += 1
                self.LogError("CRC Error (Read): " + str(Buffer))
                return True, EmptyPacket

            Register = self.GetRegisterFromPacket(Buffer)
            Length = self.GetLengthFromPacket(Buffer)   # Length requested in words
            FileNumber = self.GetFileNumberFromPacket(Buffer)

            if FileNumber < MIN_FILE_NUMBER or FileNumber > MAX_FILE_NUMBER:
                self.ComValidationError += 1
                self.LogError("Validation Error: ProcessFileReadRequest maximum file number value exceeded: " + str(FileNumber))
                return True, self.CreateExceptionPacket(Buffer, MBUS_EXCEP_SLAVE_FAIL)

            if Register < MIN_FILE_RECORD_NUM or Register > MAX_FILE_RECORD_NUM:
                self.ComValidationError += 1
                self.LogError("Validation Error: ProcessFileReadRequest maximum regiseter (file record) value exceeded: " + str(Register))
                return True, self.CreateExceptionPacket(Buffer, MBUS_EXCEP_SLAVE_FAIL)

            if Length == 0:
                self.LogError("ERROR: Length is zero (file read)!!")
                self.ComValidationError += 1
            ReturnPacket.append(self.Address)
            ReturnPacket.append(MBUS_CMD_READ_FILE)
            ReturnPacket.append(((Length * 2) + 2 & 0x00FF)) # Response length in bytes
            ReturnPacket.append(((Length * 2) + 1 & 0x00FF)) # Sub Response length in bytes
            ReturnPacket.append(MBUS_FILE_TYPE_VALUE)        # Sub Request Reference Type (always 6)
            RegStr = "%04x" % Register
            with self.RegisterFileLock:
                Value = self.FileData.get(RegStr, None)
            if Value == None:
                Value = ""
            if self.StringIsHex(Value):
                try:
                    ByteArray = bytearray.fromhex(Value)
                except Exception:
                    self.LogErrorLine("Error decoding hex string: " + RegStr + ": <" + Value + ">")
                    ByteArray = bytearray()     # served as zeros below
            else:
                ByteArray = bytearray(Value, 'ascii')
            for i in range(0, Length * 2):      # multiply by 2 to get bytes from words
                #  fill the rest with zero if no data present
                if i >= len(ByteArray):
                    ByteValue = 0
                else:
                    ByteValue = ByteArray[i]
                ReturnPacket.append(ByteValue)

            CRCValue = self.GetCRC(ReturnPacket)
            ReturnPacket.append(CRCValue & 0x00FF)            # CRC low
            ReturnPacket.append(CRCValue >> 8)                # CRC high

            return True, ReturnPacket
        except Exception as e1:
            self.LogErrorLine("Error in ProcessFileReadRequest: " + str(e1))
            return True, EmptyPacket

    #------------ProcessReadRequest --------------------------------------------
    def ProcessReadRequest(self, Buffer):

        try:
            EmptyPacket  = []
            ReturnPacket = []
            IsCoils = IsInputs = False
            if (Buffer[MBUS_OFF_COMMAND] != MBUS_CMD_READ_HOLDING_REGS and 
                Buffer[MBUS_OFF_COMMAND] != MBUS_CMD_READ_INPUT_REGS and
                Buffer[MBUS_OFF_COMMAND] != MBUS_CMD_READ_COILS):
                return False, EmptyPacket

            if Buffer[MBUS_OFF_COMMAND] == MBUS_CMD_READ_COILS:
                IsCoils = True
            elif Buffer[MBUS_OFF_COMMAND] == MBUS_CMD_READ_INPUT_REGS:
                IsInputs = True
            
            if len(Buffer) < MIN_REQ_PACKET_LENGTH:
                return False, EmptyPacket

            self.RxPacketCount += 1

            if not self.CheckCRC(Buffer):
                self.CRCErrors += 1
                self.LogError("CRC Error (Read): " + str(Buffer))
                return True, EmptyPacket

            Register = self.GetRegisterFromPacket(Buffer)
            Length = self.GetLengthFromPacket(Buffer)

            if Register < MIN_REGISTER or Register > MAX_REGISTER:
                self.ComValidationError += 1
                self.LogError("Validation Error: ProcessReadRequest maximum regiseter value exceeded: " + str(Register))
                return True, self.CreateExceptionPacket(Buffer, MBUS_EXCEP_SLAVE_FAIL)

            if Length == 0:
                self.LogError("ERROR: Length is zero (read)!!")
                self.ComValidationError += 1

            if IsCoils:
                ByteCount = math.ceil(Length/8)     # convert number of bits to bytes
                if ByteCount < 1:
                    ByteCount = 1
            else:
                ByteCount = Length * 2
            ReturnPacket.append(self.Address)
            ReturnPacket.append(Buffer[MBUS_OFF_COMMAND])
            ReturnPacket.append((ByteCount) & 0x00FF)
            
            for Reg in range(Register, Register + Length):
                RegStr = "%04x" % Reg
                with self.RegisterFileLock:
                    if IsCoils:
                        Value = self.Coils.get(RegStr, None)
                    elif IsInputs:
                        Value = self.Inputs.get(RegStr, None)
                    else:
                        Value = self.Holding.get(RegStr, None)
                # fill regs we don't have with zero
                if Value == None:
                    Value = "0000"
                    self.LogDebug("ProcessReadRequest: No Data for register. Filling zero. Reg: " + RegStr)
                ValueInt = int(Value,16)
                if not IsCoils and ByteCount > 1:
                    ReturnPacket.append(ValueInt >> 8)
                ReturnPacket.append(ValueInt & 0x00FF)

            CRCValue = self.GetCRC(ReturnPacket)
            ReturnPacket.append(CRCValue & 0x00FF)            # CRC low
            ReturnPacket.append(CRCValue >> 8)                # CRC high

            if self.debug:
                self.LogHexList(Buffer, prefix="Master")
                self.LogHexList(ReturnPacket, prefix="Slave")
            return True, ReturnPacket
        except Exception as e1:
            self.LogErrorLine("Error in ProcessReadRequest: " + str(e1))
            return True, EmptyPacket

    #------------ProcessWriteRequest -------------------------------------------
    def ProcessWriteRequest(self, Buffer):
        EmptyPacket  = []
        ReturnPacket = []

        if not Buffer[MBUS_OFF_COMMAND] in [MBUS_CMD_WRITE_REGS, MBUS_CMD_WRITE_COILS,MBUS_CMD_WRITE_COIL,MBUS_CMD_WRITE_REG]:
            return False, EmptyPacket

        if len(Buffer) < MIN_REQ_PACKET_LENGTH:
            return False, EmptyPacket

        self.RxPacketCount += 1

        if not self.CheckCRC(Buffer):
            self.CRCErrors += 1
            self.LogError("CRC Error (Write): " + str(Buffer))
            return True, EmptyPacket

        Register = self.GetRegisterFromPacket(Buffer)

        if Buffer[MBUS_OFF_COMMAND] in [MBUS_CMD_WRITE_COIL,MBUS_CMD_WRITE_REG]:
            # for single reg writes, just send back the same thing
            ReturnPacket = Buffer[:]
            Value = (Buffer[MBUS_OFF_SINGLE_WRITE_VALUE_HI] << 8) | Buffer[MBUS_OFF_SINGLE_WRITE_VALUE_LOW]
            self.LogError("Writing (%02x) %04x:%04x" % (Buffer[MBUS_OFF_COMMAND], Register, Value))
            return True, ReturnPacket

        Length = self.GetLengthFromPacket(Buffer)   # registers (0x10) or coils (0x0f)

        if Register < MIN_REGISTER or Register > MAX_REGISTER:
            self.ComValidationError += 1
            self.LogError("Validation Error: ProcessWriteRequest maximum regiseter value exceeded: " + str(Register))
            return True, self.CreateExceptionPacket(Buffer, MBUS_EXCEP_SLAVE_FAIL)

        if Length == 0:
            self.LogError("ERROR: Length is zero (write)!!")
            self.ComValidationError += 1

        IsCoils = Buffer[MBUS_OFF_COMMAND] == MBUS_CMD_WRITE_COILS
        if IsCoils:
            ExpectedBytes = (Length + 7) // 8       # coils are packed 8 per byte
        else:
            ExpectedBytes = Length * 2
        if Buffer[MBUS_OFF_WR_REQ_BYTE_COUNT] < ExpectedBytes:
            self.ComValidationError += 1
            self.LogError("Validation Error: ProcessWriteRequest byte count %d too small for length %d" % (Buffer[MBUS_OFF_WR_REQ_BYTE_COUNT], Length))
            return True, self.CreateExceptionPacket(Buffer, MBUS_EXCEP_DATA)

        # Print what we write
        for Count in range(Length):
            if IsCoils:
                Value = (Buffer[MBUS_OFF_WRITE_REG_REQ_DATA + (Count // 8)] >> (Count % 8)) & 0x01
            else:
                Value = Buffer[MBUS_OFF_WRITE_REG_REQ_DATA + (Count*2)] << 8 | Buffer[MBUS_OFF_WRITE_REG_REQ_DATA + (Count*2) +  1] & 0x00FF
            self.LogError("Writing (%02x) %04x:%04x" % (Buffer[MBUS_OFF_COMMAND], Register + Count, Value))


        ReturnPacket.append(self.Address)
        ReturnPacket.append(Buffer[MBUS_OFF_COMMAND])
        ReturnPacket.append(Register >> 8)
        ReturnPacket.append(Register & 0x00FF)
        ReturnPacket.append(Length >> 8)
        ReturnPacket.append(Length & 0x00FF)
        CRCValue = self.GetCRC(ReturnPacket)
        ReturnPacket.append(CRCValue & 0x00FF)            # CRC low
        ReturnPacket.append(CRCValue >> 8)                # CRC high
        return True, ReturnPacket

    #------------ProcessData ---------------------------------------------------
    def ProcessData(self, Buffer):
        EmptyPacket = []
        try:
            if not len(Buffer):
                return False, EmptyPacket

            if Buffer[MBUS_OFF_ADDRESS] != self.Address:
                self.LogConsole(str(Buffer))
                self.LogError("Invalid Modbus Address")
                self.ComValidationError += 1
                del Buffer[:]
                return False, EmptyPacket

            if len(Buffer) < MIN_REQ_PACKET_LENGTH:
                return False, EmptyPacket

            # Each Get*MasterPacket removes one complete packet from the front of
            # Buffer, leaving any following bytes for the next call. A return of
            # False means more bytes are needed.
            Command = Buffer[MBUS_OFF_COMMAND]
            if Command in [MBUS_CMD_READ_HOLDING_REGS, MBUS_CMD_READ_INPUT_REGS, MBUS_CMD_READ_COILS]:
                ReturnValue, Packet = self.GetReadMasterPacket(Buffer)
                if ReturnValue:
                    return self.ProcessReadRequest(Packet)
            elif Command in [MBUS_CMD_WRITE_REGS, MBUS_CMD_WRITE_COILS, MBUS_CMD_WRITE_REG, MBUS_CMD_WRITE_COIL]:
                ReturnValue, Packet = self.GetWriteMasterPacket(Buffer)
                if ReturnValue:
                    return self.ProcessWriteRequest(Packet)
            elif Command == MBUS_CMD_READ_FILE:
                ReturnValue, Packet = self.GetReadFileMasterPacket(Buffer)
                if ReturnValue:
                    return self.ProcessFileReadRequest(Packet)
            else:
                # the packet length of an unsupported command is unknown, so drop the buffer
                self.LogError("Unsupported function code: %02x" % Command)
                self.ComValidationError += 1
                Packet = self.CreateExceptionPacket(Buffer, MBUS_EXCEP_FUNCTION)
                del Buffer[:]
                return True, Packet

            return False, EmptyPacket

        except Exception as e1:
            self.LogErrorLine("Error in ProcessData: " + str(e1))
            del Buffer[:]
            return False, EmptyPacket

    #----------  SocketWorkThread-----------------------------------------------
    #  This thread spawns for each connection established by a client
    #  in InterfaceServerThread
    def SocketWorkThread(self, conn, addr):

        self.LogConsole("Connected with " + addr[0] + ":" + str(addr[1]))
        Buffer = []
        try:
            #conn.settimeout(2)   # only blok on recv for a small amount of time

            while True:
                try:
                    data = conn.recv(4096)
                    if self.IsStopping:
                        self.ConnectionList.remove(conn)
                        conn.close()
                        break
                    #self.LogConsole("Socket : " + str(len(data)))
                    if len(data):
                        Buffer.extend(data)
                        # the buffer may hold more than one request, process all complete ones
                        while len(Buffer):
                            ReturnValue, Packet = self.ProcessData(Buffer)
                            if not ReturnValue:
                                break       # incomplete packet, wait for more data
                            if len(Packet):
                                if len(Packet) > MAX_MODBUS_PACKET_SIZE:
                                    self.LogError("Error in SocketWorkThread: Packet size exceeds 256: " + str(len(Packet)))
                                    self.ComValidationError += 1
                                    Packet = self.CreateExceptionPacket(Packet, MBUS_EXCEP_SLAVE_FAIL)
                                if len(Packet):
                                    ByteArray = bytearray(Packet)
                                    self.TxPacketCount += 1
                                    conn.sendall(ByteArray)
                    else:
                        self.ConnectionList.remove(conn)
                        conn.close()
                        break
                except socket.timeout:

                    if len(self.BindAddress):
                        # listening on one address, a network change does not matter
                        continue
                    TestHostIP = self.GetNetworkIp()
                    #self.LogConsole("Testing IP: " + self.HostIP + ": " + TestHostIP)
                    if TestHostIP != self.HostIP:
                        self.LogInfo("Host IP Changed from " + self.HostIP + " to " + TestHostIP +  "!")
                        self.HostIP = TestHostIP
                        self.CloseServerSocket()
                        self.SetupServerSocket()
                        break

                    if self.IsStopping:
                        continue
                except socket.error as msg:
                    self.LogConsole("Socket Err: " + str(msg))
                    try:
                        self.ConnectionList.remove(conn)
                        conn.close()
                    except:
                        pass
                    break
                except Exception as e1:
                    # bad register data etc. Drop this request but keep the connection.
                    self.LogErrorLine("Error in SocketWorkThread: " + str(e1))
                    del Buffer[:]

        except socket.error:
            pass
        try:
            self.ConnectionList.remove(conn)
            conn.close()
        except:
            pass
        self.LogConsole("Exit Socket Worker Thread: " + addr[0] + ":" + str(addr[1]))
        # end SocketWorkThread

    #----------  SetupServerSocket ---------------------------------------------
    def SetupServerSocket(self):
        #create an INET, STREAMing socket
        self.ServerSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # set some socket options so we can resuse the port
        self.ServerSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.ServerSocket.settimeout(.5)
        #bind the socket to a host, and a port
        self.ServerSocket.bind((self.BindAddress, self.ServerSocketPort))
        #become a server socket
        self.ServerSocket.listen(5)

        self.HostIP = self.GetNetworkIp()

    #----------  CloseServerSocket ---------------------------------------------
    def CloseServerSocket(self):

        if self.ServerSocket != None:
            if len(self.ConnectionList):
                try:
                    self.ServerSocket.shutdown(socket.SHUT_RDWR)
                except:
                    pass
            self.ServerSocket.close()
            self.ServerSocket = None

    #----------  interface for server thread -----------------------------------
    def InterfaceServerThread(self):

        self.SetupServerSocket()

        #wait to accept a connection - blocking call
        while True:
            try:
                conn, addr = self.ServerSocket.accept()
                conn.settimeout(1)
                self.ConnectionList.append(conn)
                SocketThread = threading.Thread(target=self.SocketWorkThread, args = (conn, addr), name = "SocketWorkThread")
                SocketThread.daemon = True
                SocketThread.start()       # start server thread
            except socket.timeout:
                if self.IsStopping:
                    break
                continue
            except Exception as e1:
                if self.IsStopping:
                    break
                self.LogErrorLine("Exception in InterfaceServerThread" + str(e1))
                if self.WaitForExit("InterfaceServerThread", 0.5 ):
                    break
                continue

        self.CloseServerSocket()

    #-------------------------------------------------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(1)
    #-------------------------Close---------------------------------------------
    def Close(self):

        self.IsStopping = True

        self.LogConsole("\nStopping Simulation Server.")
        try:
            for item in list(self.ConnectionList):     # copy, items are removed in the loop
                try:
                    item.close()
                except:
                    pass
                try:
                    self.ConnectionList.remove(item)
                except ValueError:
                    pass    # already removed by its SocketWorkThread
        except:
            pass
        try:
            if(self.ServerSocket != None):
                self.ServerSocket.shutdown(socket.SHUT_RDWR)
                self.ServerSocket.close()
            self.KillThread("InterfaceServerThread")

            self.KillThread("RegisterFileMonitorThread")
        except:
            pass
        self.ProgramComplete = True
        sys.exit(1)

    #-------------------------GetNetworkIp--------------------------------------
    def GetNetworkIp2(self):
        try:

            host_name = socket.gethostname()
            host_ip = socket.gethostbyname(host_name)
            return host_ip
        except Exception as e1:
            print("Error in GetNetworkIp: " + str(e1))
            return "Unknown"


    def GetNetworkIp(self):
        try:
            return(str((([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")] or [[(s.connect(("8.8.8.8", 53)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) + ["no IP found"])[0]))
        except:
            return self.get_local_ipv4()
    #-------------------------run_shell_command---------------------------------
    def run_shell_command(self, command, capture_output = False):
        print(f"$ {command}")
        # 'shell=True' => Use built-in shell, '/bin/sh' on Linux and Mac, 'cmd.exe' on Windows.
        return subprocess.run(command, shell=True, capture_output=capture_output, text=capture_output) 

    #-------------------------get_local_ipv4---------------------------------
    def get_local_ipv4(self):
        local_ipv4 = None

        operating_system_kind = platform.system()
        if operating_system_kind == 'Darwin':
            local_ipv4 = self.run_shell_command('ipconfig getifaddr en0', True).stdout.strip()
        elif operating_system_kind == 'Windows':
            for line in self.run_shell_command('netsh ip show address | findstr "IP Address"', True).stdout.split(os.linesep):
                local_ipv4_or_empty = line.removeprefix('IP Address:').strip()
                if local_ipv4_or_empty:
                    local_ipv4 = local_ipv4_or_empty
                    break
        else: # Linux
            local_ipv4 = self.run_shell_command("hostname -I | awk '{print $1}'", True).stdout.strip()

        try:
            ipaddress.IPv4Address(local_ipv4)
        except ipaddress.AddressValueError:
            self.LogErrorLine("Could not get the local network IPv4 address")
            return "Unknown"

        if local_ipv4.startswith("127.0."):
            self.LogErrorLine(f"Could not get the correct local network IPv4 address, got {local_ipv4}")

        return local_ipv4

    #-------------------------DisplayStats--------------------------------------
    def DisplayStats(self):

        try:
            Interval = datetime.datetime.now() - self.LastUpdateTime
            if Interval.total_seconds() >= 5:
                self.LastUpdateTime = datetime.datetime.now()
                self.LogConsole("---------Stats----------")
                self.LogConsole("Tx Packet Count : " + str(self.TxPacketCount))
                self.LogConsole("Rx Packet Count : " + str(self.RxPacketCount))
                self.LogConsole("CRC Errors: " + str(self.CRCErrors))
                self.LogConsole("Slave Exceptions: " + str(self.SlaveException))
                self.LogConsole("Timerout Errors: " + str(self.ComTimoutError))
                self.LogConsole("Validation Errors: " + str(self.ComValidationError))
                self.LogConsole("Discarded Bytes: " + str(self.DiscardedBytes))
                self.LogConsole("Host IP: " + str(self.HostIP))
                self.LogConsole("Holding: " + str(len(self.Holding)))
                try:
                    self.LogConsole("Inputs: " + str(len(self.Inputs)))
                    self.LogConsole("Coils: " + str(len(self.Coils)))
                    self.LogConsole("Strings: " + str(len(self.Strings)))
                    self.LogConsole("File Data: " + str(len(self.FileData)))
                except:
                    pass
                self.LogConsole("Input File: " + self.SimulationFile)

                ProgramRunTime = datetime.datetime.now() - self.ProgramStartTime
                outstr = str(ProgramRunTime).split(".")[0]  # remove microseconds from string
                self.LogConsole("Running for " + outstr + ".")
        except Exception as e1:
            self.LogErrorLine("Error in DisplayStats: " + str(e1))

#------------------- Command-line interface for monitor ------------------------
if __name__=='__main__': #
    ConfigFilePath = None if len(sys.argv)<2 else sys.argv[1]

    #Start things up
    if ConfigFilePath == None:
        MyGenSim = GenSim()
    else:
        MyGenSim = GenSim(ConfigFilePath = ConfigFilePath)

    try:
        while not MyGenSim.ProgramComplete:
            MyGenSim.DisplayStats()
            time.sleep(0.01)
        sys.exit(0)
    except Exception as e1:
        print("Error in main: " + str(e1))
        sys.exit(1)
