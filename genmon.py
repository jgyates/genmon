#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: genmon.py
# PURPOSE: Monitor for MODBUS port on Generac Generator
#
#  AUTHOR: Jason G Yates
#    DATE: 05-Oct-2016
#
# MODIFICATIONS:
#------------------------------------------------------------


## Notes:
#   Pin 8 (white) appears to be TX from Controller
#   Pin 7 (black) appears to be TX from mobile link

# http://modbus.rapidscada.net/

import datetime, time, sys, smtplib, signal, os, threading, socket, serial
import crcmod.predefined, crcmod, mymail, atexit, ConfigParser
import mymail, mylog

#------------ SerialDevice class --------------------------------------------
class SerialDevice:
    def __init__(self, name, rate=9600):
        self.DeviceName = name
        self.BaudRate = rate
        self.Buffer = []
        self.BufferLock = threading.Lock()

        self.RxPacketCount = 0
        self.TxPacketCount = 0
        self.CrcError = 0
        self.DiscardedBytes = 0
        self.Restarts = 0

        # log errors in this module to a file
        self.log = mylog.SetupLogger("myserial", "/var/log/myserial.log")

        #Starting serial connection
        self.SerialDevice = serial.Serial()
        self.SerialDevice.port = name
        self.SerialDevice.baudrate = rate
        self.SerialDevice.bytesize = serial.EIGHTBITS     #number of bits per bytes
        self.SerialDevice.parity = serial.PARITY_NONE     #set parity check: no parity
        self.SerialDevice.stopbits = serial.STOPBITS_ONE  #number of stop bits
        self.SerialDevice.timeout = None                  # should be blocking to help with CPU load
        self.SerialDevice.xonxoff = False                 #disable software flow control
        self.SerialDevice.rtscts = False                  #disable hardware (RTS/CTS) flow control
        self.SerialDevice.dsrdtr = False                  #disable hardware (DSR/DTR) flow control
        self.SerialDevice.writeTimeout = None             #timeout for write, return when packet sent

        #Check if port failed to open
        if (self.SerialDevice.isOpen() == False):
            try:
                self.SerialDevice.open()
            except Exception, e:
                self.FatalError( "Error on open serial port %s: " % self.DeviceName + str(e))
                return None
        else:
            self.FatalError( "Serial port already open: %s" % self.DeviceName)
            return None

        self.Flush()

    # ---------- SerialDevice::StartReadThread------------------
    def StartReadThread(self):

         # start read thread to monitor incoming data commands
        self.ReadThreadObj = threading.Thread(target=self.ReadThread, name = "SerialReadThread")
        self.ReadThreadObj.daemon = True
        self.ReadThreadObj.start()       # start Read thread

        return self.ReadThreadObj

    # ---------- SerialDevice::ReadThread------------------
    def ReadThread(self):
        while True:
            try:
                self.Flush()
                while True:
                    for c in self.Read():
                        with self.BufferLock:
                            self.Buffer.append(ord(c))

            except Exception, e1:
                self.LogError( "Resetting SerialDevice:ReadThread Error: " + self.DeviceName + ":"+ str(e1))
                # if we get here then this is likely due to the following exception:
                #  "device reports readiness to read but returned no data (device disconnected?)"
                #  This is believed to be a kernel issue so let's just reset the device and hope
                #  for the best (actually this works)
                self.Restarts += 1
                self.SerialDevice.close()
                self.SerialDevice.open()

    #------------SerialDevice::DiscardByte------------
    def DiscardByte(self):

        if len(self.Buffer):
            discard = self.Buffer.pop(0)
            self.DiscardedBytes += 1
            return discard

    # ---------- SerialDevice::Close------------------
    def Close(self):

        self.SerialDevice.close()
    # ---------- SerialDevice::Flush------------------
    def Flush(self):
        try:
            self.SerialDevice.flushInput()      #flush input buffer, discarding all its contents
            self.SerialDevice.flushOutput()     #flush output buffer, aborting current output
            with self.BufferLock:               # will block if lock is already held
                del self.Buffer[:]

        except Exception, e1:
            self.FatalError( "Error in SerialDevice:Flush : " + self.DeviceName + ":" + str(e1))

    # ---------- SerialDevice::Read------------------
    def Read(self):
        return  self.SerialDevice.read()

    # ---------- SerialDevice::Write-----------------
    def Write(self, data):
        return  self.SerialDevice.write(data)

    #---------------------SerialDevice::FatalError------------------------
    def LogError(self, Message):
        self.log.error(Message)
    #---------------------SerialDevice::FatalError------------------------
    def FatalError(self, Message):

        self.log.error(Message)
        raise Exception(Message)


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

#-------------------Generator specific const defines for Generator class
LOG_DEPTH               = 50
START_LOG_STARTING_REG  = 0x012c    # the most current start log entry should be at this register
START_LOG_STRIDE        = 4
START_LOG_END_REG       = ((START_LOG_STARTING_REG + (START_LOG_STRIDE * LOG_DEPTH)) - START_LOG_STRIDE)
ALARM_LOG_STARTING_REG  = 0x03e8    # the most current alarm log entry should be at this register
ALARM_LOG_STRIDE        = 5
ALARM_LOG_END_REG       = ((ALARM_LOG_STARTING_REG + (ALARM_LOG_STRIDE * LOG_DEPTH)) - ALARM_LOG_STRIDE)
SERVICE_LOG_STARTING_REG= 0x04e2    # the most current service log entry should be at this register
SERVICE_LOG_STRIDE      = 4
SERVICE_LOG_END_REG     = ((SERVICE_LOG_STARTING_REG + (SERVICE_LOG_STRIDE * LOG_DEPTH)) - SERVICE_LOG_STRIDE)
# Register for Model number
MODEL_REG               = 0x01f4
MODEL_REG_LENGTH        = 5

DEFAULT_THRESHOLD_VOLTAGE = 143
DEFAULT_PICKUP_VOLTAGE = 215
#------------ GeneratorDevice class --------------------------------------------
class GeneratorDevice:

    def __init__(self):
        self.ProgramName = "Generator Monitor"
        self.BaudRate = 9600        # data rate of the serial port (default 9600)
        self.Registers = {}         # dict for registers and values
        self.RegistersUnderTest = {}# dict for registers we are testing
        self.RegistersUnderTestData = ""
        self.NotChanged = 0         # stats for registers
        self.Changed = 0            # stats for registers
        self.TotalChanged = 0.0     # ratio of changed ragisters
        self.LastAlarmValue = 0xFF  # Last Value of the Alarm Register
        self.ConnectionList = []    # list of incoming connections for heartbeat
        self.ServerSocket = 0       # server socket for nagios heartbeat and command/status
        self.ThreadList = []     # list of thread objects
        self.GeneratorInAlarm = False       # Flag to let the heartbeat thread know there is a problem
        self.SystemInOutage = False         # Flag to signal utility power is out
        self.TransferActive = False         # Flag to signal transfer switch is allowing gen supply power
        self.CommunicationsActive = False   # Flag to let the heartbeat thread know we are communicating
        self.CommAccessLock = threading.RLock()  # lock to synchronize access to the serial port comms
        self.UtilityVoltsMin = 0    # Minimum reported utility voltage above threshold
        self.UtilityVoltsMax = 0    # Maximum reported utility voltage above pickup
        self.MailInit = False       # set to true once mail is init
        self.SerialInit = False     # set to true once serial is init

        self.DaysOfWeek = { 0: "Sunday",    # decode for register values with day of week
                            1: "Monday",
                            2: "Tuesday",
                            3: "Wednesday",
                            4: "Thursday",
                            5: "Friday",
                            6: "Saturday"}
        self.MonthsOfYear = { 1: "January",     # decode for register values with month
                              2: "February",
                              3: "March",
                              4: "April",
                              5: "May",
                              6: "June",
                              7: "July",
                              8: "August",
                              9: "September",
                              10: "October",
                              11: "November",
                              12: "December"}

        # base registers and their length in bytes
        # note: the lengths are in bytes. The request packet should be in words
        # and due to the magic of python, we often deal with the response in string values
        #   dict format  Register: [ Length in bytes: monitor change 0 - no, 1 = yes]
        self.BaseRegisters = {                  # base registers read by master
                                "0000" : [2, 0],     # Number of hours exercise
                                "0005" : [2, 0],     # Exercise Time Hi Byte = Hour, Lo Byte = Min (Read Only)
                                "0006" : [2, 0],     # Exercise Time Hi Byte = Day of Week 00=Sunday 01=Monday, Low Byte = 00=quiet=no, 01=yes
                                "0007" : [2, 0],     # Engine RPM
                                "0008" : [2, 0],     # Freq - value includes Hz to the tenths place i.e. 59.9 Hz
                                "000a" : [2, 0],     # battery voltage Volts to  tenths place i.e. 13.9V
                                "000c" : [2, 0],     # engine run time hours
                                "000e" : [2, 0],     # Read / Write: Generator Time Hi byte = hours, Lo byte = min
                                "000f" : [2, 0],     # Read / Write: Generator Time Hi byte = month, Lo byte = day of the month
                                "0010" : [2, 0],     # Read / Write: Generator Time = Hi byte Day of Week 00=Sunday 01=Monday, Lo byte = last 2 digits of year
                                "0011" : [2, 0],     # Utility Threshold, ML Does not read this
                                "0012" : [2, 0],     # Gen output voltage
                                "001a" : [2, 0],     # Hours until next service
                                "002a" : [2, 0],     # hardware (high byte) (Hardware V1.04 = 0x68) and firmware version (low byte) (Firmware V1.33 = 0x85)
                                "003c" : [2, 0],     # Unknown sensor 1 ramps up to 300 (30.0 ?)
                                "0058" : [2, 0],     # Unknown sensor 2, once engine starts ramps up to 1600 decimal (160.0?)
                                "005d" : [2, 0],     # Unknown sensor 3, Moves between 0x55 - 0x58 continuously even when engine off
                                "05ed" : [2, 0],     # Unknown sensor 4, changes between 35, 37, 39
                                "0059" : [2, 0],     # Set Voltage from Dealer Menu (not currently used)
                                "023b" : [2, 0],     # Pick Up Voltage
                                "023e" : [2, 0]}     # Exercise time duration


        # registers that need updating more frequently than others to make things more responsive
        self.PrimeRegisters = {
                                "0001" : [4, 1],     # Alarm and status register
                                "0053" : [2, 0],     # Output relay status register (battery charging, transfer switch, Change at startup and stop
                                "0057" : [2, 0],     # Input status registes
                                "0009" : [2, 0],     # Utility voltage
                                "05f1" : [2, 0]}     # Last Alarm Code

        self.WriteRegisters = {  # 0003 and 0004 are index registers, used to write exercise time and other unknown stuff (remote start, stop and transfer)
                                "002c" : 2,     # Read / Write: Exercise Time HH:MM
                                "002e" : 2,     # Read / Write: Exercise Day Sunday =0, Monday=1
                                "002f" : 2}     # Read / Write: Exercise Quite Mode=1 Not Quiet Mode = 0

        self.REGLEN = 0
        self.REGMONITOR = 1

        try:
            # read config file
            config = ConfigParser.RawConfigParser()
            # config parser reads from current directory, when running form a cron tab this is
            # not defined so we specify the full path
            config.read('/etc/genmon.conf')

            # set defaults for optional parameters
            self.bDisplayOutput = False
            self.bDisplayMonitor = False
            self.bDisplayRegisters = False
            self.bDisplayStatus = False
            self.EnableDebug = False
            self.bDisplayUnknownSensors = False
            self.bDisplayMaintenance = False
            self.bUseLegacyWrite = False

            # getfloat() raises an exception if the value is not a float
            # getint() and getboolean() also do this for their respective types
            self.SiteName = config.get('GenMon', 'sitename')
            self.SerialPort = config.get('GenMon', 'port')
            self.IncomingEmailFolder = config.get('GenMon', 'incoming_mail_folder')     # imap folder for incoming mail
            self.ProcessedEmailFolder = config.get('GenMon', 'processed_mail_folder')   # imap folder for processed mail
            # heartbeat server port, must match value in check_monitor_system.py and any calling client apps
            self.ServerSocketPort = config.getint('GenMon', 'server_port')
            self.Address = int(config.get('GenMon', 'address'),16)                      # modbus address
            self.LogLocation = config.get('GenMon', 'loglocation')
            self.AlarmFile = config.get('GenMon', 'alarmfile')
            self.LiquidCooled = config.getboolean('GenMon', 'liquidcooled')
            self.EvolutionController = config.getboolean('GenMon', 'evolutioncontroller')

            # optional config parameters
            if config.has_option('GenMon', 'displayoutput'):
                self.bDisplayOutput = config.getboolean('GenMon', 'displayoutput')
            if config.has_option('GenMon', 'displaymonitor'):
                self.bDisplayMonitor = config.getboolean('GenMon', 'displaymonitor')
            if config.has_option('GenMon', 'displayregisters'):
                self.bDisplayRegisters = config.getboolean('GenMon', 'displayregisters')
            if config.has_option('GenMon', 'displaystatus'):
                self.bDisplayStatus = config.getboolean('GenMon', 'displaystatus')
            if config.has_option('GenMon', 'displaymaintenance'):
                self.bDisplayMaintenance = config.getboolean('GenMon', 'displaymaintenance')
            if config.has_option('GenMon', 'enabledebug'):
                self.EnableDebug = config.getboolean('GenMon', 'enabledebug')
            if config.has_option('GenMon', 'displayunknown'):
                self.bDisplayUnknownSensors = config.getboolean('GenMon', 'displayunknown')
            if config.has_option('GenMon', 'uselegacysetexercise'):
                self.bUseLegacyWrite = config.getboolean('GenMon', 'uselegacysetexercise')
        except Exception, e1:
            raise Exception("Missing config file or config file entries: " + str(e1))
            return None

        if not self.EvolutionController:        # if we are using a Nexus Controller, force legacy writes
            self.bUseLegacyWrite = True

                        # log errors in this module to a file
        self.log = mylog.SetupLogger("genmon", self.LogLocation + "genmon.log")

        self.ProgramStartTime = datetime.datetime.now()     # used for com metrics

        self.OutageStartTime = self.ProgramStartTime    # if these two are the same, no outage has occured
        self.LastOutageDuration = self.OutageStartTime - self.OutageStartTime

        atexit.register(self.Close)

        try:
            #Starting serial connection
            self.Slave = SerialDevice(self.SerialPort, self.BaudRate)
            self.SerialInit = True
            self.ThreadList.append(self.Slave.StartReadThread())

        except Exception, e1:
            self.FatalError("Error opening serial device: " + str(e1))
            return None

        # init mail, start processing incoming email
        self.mail = mymail.MyMail(monitor=True, incoming_folder = self.IncomingEmailFolder, processed_folder =self.ProcessedEmailFolder,incoming_callback = self.ProcessCommand)
        self.MailInit = True

        # send mail to tell we are starting
        self.mail.sendEmail("Generator Monitor Starting at " + self.SiteName, "Generator Monitor Starting at " + self.SiteName )

        # check for ALARM.txt file present
        try:
            with open(self.AlarmFile,"r") as AlarmFile:     #
                self.printToScreen("Validated alarm file present")
        except Exception, e1:
            self.FatalError("Unable to open alarm file: " + str(e1))

        self.ThreadList.append(self.mail.GetSendEmailThreadObject())
        self.ThreadList.append(self.mail.GetEmailMonitorThreadObject())

        try:
            # CRCMOD library, used for CRC calculations
            self.ModbusCrc = crcmod.predefined.mkCrcFun('modbus')
        except Exception, e1:
            self.FatalError("Unable to find crcmod package: " + str(e1))

        # start read thread to process incoming data commands
        self.StartThread(self.ProcessThread, Name = "ProcessThread")

        # start read thread to monitor registers as they change
        self.StartThread(self.MonitorThread, Name = "MonitorThread")

        # start thread to accept incoming sockets for nagios heartbeat and command / status clients
        self.StartThread(self.InterfaceServerThread, Name = "InterfaceServerThread")

        # start thread to accept incoming sockets for nagios heartbeat
        self.StartThread(self.ComWatchDog, Name = "ComWatchDog")

        if self.EnableDebug:
            self.StartThread(self.DebugThread, Name = "DebugThread")      # for debugging registers

    # ---------- GeneratorDevice::StartThread------------------
    def StartThread(self, ThreadFunction, Name = None):

        ThreadObj = threading.Thread(target=ThreadFunction, name = Name)
        ThreadObj.daemon = True
        ThreadObj.start()       # start monitor thread
        self.ThreadList.append(ThreadObj)

    # ---------- GeneratorDevice::ProcessThread------------------
    #  remove items from Buffer, form packets
    #  all read and writes to serial port(s) should occur in this thread so we can
    #  serialize access to the ports
    def ProcessThread(self):

        try:
            self.Flush()
            self.InitDevice()
            while True:
                try:
                    self.MasterEmulation()
                    if self.EnableDebug:
                        self.DebugRegisters()
                except Exception, e1:
                    self.LogError("Error in GeneratorDevice:ProcessThread, contiue: " + str(e1))
        except Exception, e1:
            self.FatalError("Exiting GeneratorDevice:ProcessThread " + str(e1))

    # ---------- GeneratorDevice::MonitorThread------------------
    # This thread will analyze the cached registers. It should not write to the serial port(s)
    def MonitorThread(self):

        while True:
            try:
                time.sleep(5)
                if self.bDisplayMonitor:
                    self.DisplayMonitor()       # display communication stats
                if self.bDisplayRegisters:
                    self.DisplayRegisters()     # display registers
                if self.bDisplayStatus:
                    self.DisplayStatus()        # display generator engine status
                if self.bDisplayMaintenance:
                    self.DisplayMaintenance()   # display Maintenance
            except Exception, e1:
                self.LogError("Error in GeneratorDevice:MonitorThread " + str(e1))

    #------------GeneratorDevice::Flush-----------------------
    def Flush(self):

        self.Slave.Flush()

    # ---------- GeneratorDevice::GetPacketFromSlave------------------
    def GetPacketFromSlave(self):

        LocalErrorCount = 0
        Packet = []
        EmptyPacket = []    # empty packet

        if len(self.Slave.Buffer) < MIN_PACKET_LENGTH_RES:
            return True, EmptyPacket

        while len(self.Slave.Buffer) >= MIN_PACKET_LENGTH_RES:
            if self.Slave.Buffer[MBUS_ADDRESS] == self.Address and self.Slave.Buffer[MBUS_COMMAND] in [0x01, 0x02, MBUS_CMD_READ_REGS, 0x04]:
                length = self.Slave.Buffer[MBUS_RESPONSE_LEN]
                if (length + MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH) > len(self.Slave.Buffer):
                    continue

                for i in range(0, length + MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH):
                    Packet.append(self.Slave.Buffer.pop(0))  # pop Address, Function, Length, message and CRC

                if self.CheckCRC(Packet):
                    self.Slave.RxPacketCount += 1
                    return True, Packet
                else:
                    self.Slave.CrcError += 1
                    return False, EmptyPacket
            elif self.Slave.Buffer[MBUS_ADDRESS] == self.Address and self.Slave.Buffer[MBUS_COMMAND] in [MBUS_CMD_WRITE_REGS]:
                if len(self.Slave.Buffer) < MIN_PACKET_LENGTH_WR_RES:
                    continue
                for i in range(0, MIN_PACKET_LENGTH_WR_RES):
                    Packet.append(self.Slave.Buffer.pop(0))    # address, function, address hi, address low, quantity hi, quantity low, CRC high, crc low

                if self.CheckCRC(Packet):
                    self.Slave.RxPacketCount += 1
                    return True,Packet
                else:
                    self.Slave.CrcError += 1
                    return False, EmptyPacket
            else:
                LocalErrorCount += 1
                self.DiscardByte()
                if LocalErrorCount >= MIN_PACKET_LENGTH_RES:
                    self.LogError("Validation Error: simulated CRC error (Slave)")
                    # if we get here then there was a bit dropped in the address field and
                    #  we never assemble the packet to check the CRC
                    self.Slave.CrcError += 1
                    return False, EmptyPacket

        return True, EmptyPacket   # technically not a CRC error, we really should never get here

    #-------------GeneratorDevice::InitDevice------------------------------------
    # One time reads, and read all registers once
    def InitDevice(self):

        self.ProcessMasterSlaveTransaction("%04x" % MODEL_REG, MODEL_REG_LENGTH)

        if self.EvolutionController:
            self.ProcessMasterSlaveTransaction("%04x" % ALARM_LOG_STARTING_REG, ALARM_LOG_STRIDE)

        self.ProcessMasterSlaveTransaction("%04x" % START_LOG_STARTING_REG, START_LOG_STRIDE)

        if self.EvolutionController:
            self.ProcessMasterSlaveTransaction("%04x" % SERVICE_LOG_STARTING_REG, SERVICE_LOG_STRIDE)

        for PrimeReg, PrimeInfo in self.PrimeRegisters.items():
            self.ProcessMasterSlaveTransaction(PrimeReg, PrimeInfo[self.REGLEN] / 2)

        for Reg, Info in self.BaseRegisters.items():

            #The divide by 2 is due to the diference in the values in our dict are bytes
            # but modbus makes register request in word increments so the request needs to
            # in word multiples, not bytes
            self.ProcessMasterSlaveTransaction(Reg, Info[self.REGLEN] / 2)

        self.CheckForAlarms()   # check for unknown events (i.e. events we are not decoded) and send an email if they occur

    #-------------GeneratorDevice::DebugRegisters------------------------------------
    def DebugRegisters(self):

        # reg 200 - -3e7 and 4af - 4e2 and 5af - 600 (already got 5f1 5f4 and 5f5?
        for Reg in range(0x05 , 0x600):
            RegStr = "%04x" % Reg
            if not self.RegisterIsKnown(RegStr):
                self.ProcessMasterSlaveTransaction(RegStr, 1)

    #-------------GeneratorDevice::MasterEmulation------------------------------------
    def MasterEmulation(self):

        counter = 0
        for Reg, Info in self.BaseRegisters.items():

            if counter % 6 == 0:
                for PrimeReg, PrimeInfo in self.PrimeRegisters.items():
                    self.ProcessMasterSlaveTransaction(PrimeReg, PrimeInfo[self.REGLEN] / 2)
                self.CheckForAlarms()   # check for unknown events (i.e. events we are not decoded) and send an email if they occur

            #The divide by 2 is due to the diference in the values in our dict are bytes
            # but modbus makes register request in word increments so the request needs to
            # in word multiples, not bytes
            self.ProcessMasterSlaveTransaction(Reg, Info[self.REGLEN] / 2)
            counter += 1

    #-------------GeneratorDevice::ProcessMasterSlaveTransaction--------------------
    def ProcessMasterSlaveWriteTransaction(self, Register, Length, Data):

        MasterPacket = []

        MasterPacket = self.CreateMasterPacket(Register, Length, MBUS_CMD_WRITE_REGS, Data)

        if len(MasterPacket) == 0:
            return

        return self.ProcessOneTransaction(MasterPacket, True)   # True to skip writing results to cached reg values

    #-------------GeneratorDevice::ProcessMasterSlaveTransaction--------------------
    def ProcessMasterSlaveTransaction(self, Register, Length):

        MasterPacket = []

        MasterPacket = self.CreateMasterPacket(Register, Length)

        if len(MasterPacket) == 0:
            return

        return self.ProcessOneTransaction(MasterPacket)

    #------------GeneratorDevice::ProcessOneTransaction
    def ProcessOneTransaction(self, MasterPacket, skiplog = False):

        with self.CommAccessLock:       # this lock should allow calls from multiple threads

            self.SendPacketAsMaster(MasterPacket)

            SentTime = datetime.datetime.now()
            while True:
                # be kind to other processes, we know we are going to have to wait for the packet to arrive
                # so let's sleep for a bit before we start polling
                time.sleep(0.01)
                RetVal, SlavePacket = self.GetPacketFromSlave()

                if RetVal == True and len(SlavePacket) != 0:    # we receive a packet
                    break
                if RetVal == False:
                    self.LogError("Error Receiving slave packet for register %x%x" % (MasterPacket[2],MasterPacket[3]) )
                    return False
                msElapsed = self.MillisecondsElapsed(SentTime)
                # todo test this, it should probably be lower, like 25 or 30 (depending on the response from the controller)
                # each char time is about 1 millisecond so assuming a 10 byte packet transmitted
                # and a 10 byte received with about 5 char times of silence in between should give
                # us about 25ms
                if msElapsed > 1000:
                    self.LogError("Error: timeout receiving slave packet for register %x%x Buffer:%d" % (MasterPacket[2],MasterPacket[3], len(self.Slave.Buffer)) )
                    return False

        # update our cached register dict
        if not skiplog:
            self.UpdateRegistersFromPacket(MasterPacket, SlavePacket)

        return True

    # ---------- GeneratorDevice::CreateMasterPacket------------------
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

    #-------------GeneratorDevice::SendPacketAsMaster---------------------------------
    def SendPacketAsMaster(self, Packet):

        ByteArray = bytearray(Packet)
        self.Slave.Write(ByteArray)
        self.Slave.TxPacketCount += 1

     #-------------GeneratorDevice::UpdateLogRegistersAsMaster
    def UpdateLogRegistersAsMaster(self):

        # Start / Stop Log
        for Register in self.LogRange(START_LOG_STARTING_REG , LOG_DEPTH,START_LOG_STRIDE):
            RegStr = "%04x" % Register
            if not self.ProcessMasterSlaveTransaction(RegStr, START_LOG_STRIDE):
                break

        if self.EvolutionController:
            # Service Log
            for Register in self.LogRange(SERVICE_LOG_STARTING_REG , LOG_DEPTH, SERVICE_LOG_STRIDE):
                RegStr = "%04x" % Register
                if not self.ProcessMasterSlaveTransaction(RegStr, SERVICE_LOG_STRIDE):
                    break

            # Alarm Log
            for Register in self.LogRange(ALARM_LOG_STARTING_REG , LOG_DEPTH, ALARM_LOG_STRIDE):
                RegStr = "%04x" % Register
                if not self.ProcessMasterSlaveTransaction(RegStr, ALARM_LOG_STRIDE):
                    break

    # ---------- GeneratorDevice::MillisecondsElapsed------------------
    def MillisecondsElapsed(self, ReferenceTime):

        CurrentTime = datetime.datetime.now()
        Delta = CurrentTime - ReferenceTime
        return Delta.microseconds / 1000

     #----------  GeneratorDevice::SetGeneratorRemoteStartStop-------------------------------
    def SetGeneratorRemoteStartStop(self, CmdString):

        # WARNING: THIS IS HIGHLY EXPERIMENTAL, writing zero or x0203 to indexed register 0001
        # will remote start the generator. Apparently register index 0002 register controls the transfer
        # switch in some way

        # extract quiet mode setting from Command String
        # format is setquiet=yes or setquiet=no
        msgbody = "Invalid command syntax for command setremote (1)"
        try:
            #Format we are looking for is "setremote=RemoteStart"
            marker0 = CmdString.lower().find("setremote")
            marker1 = CmdString.find("=", marker0)
            marker2 = CmdString.find(" ",marker1+1)

            if -1 in [marker0, marker1]:
                self.LogError("Validation Error: Error parsing command string in SetGeneratorRemoteStartStop (parse): " + CmdString)
                return msgbody

            if marker2 == -1:       # was this the last char in the string or now space given?
                Command = CmdString[marker1+1:]
            else:
                Command = CmdString[marker1+1:marker2]

        except Exception, e1:
            self.LogError("Validation Error: Error parsing command string in SetGeneratorRemoteStartStop: " + CmdString)
            self.LogError( str(e1))
            return msgbody

        # Index register 0001 controls remote start (data written 0001 to start,I believe ).
        # Index register 0002 controls remote transfer switch (Not sure of the data here )
        Register = 0
        Value = 0

        if Command == "RemoteStart":
            Register = 0x0001
            Value = 0x0000          # Unverified
        elif Command == "RemoteStop":
            Register = 0x0001       # Unverified
            Value = 0x0001          # Unverified
        elif Command == "TransferGenerator":
            Register = 0x0002       # Unverified
            Value = 0x0000          # Unverified
        elif Command == "TransferUtility":
            Register = 0x0002       # Unverified
            Value = 0x0001          # Unverified
        else:
            return "Invalid command syntax for command setremote (2)"

        with self.CommAccessLock:
            #
            LowByte = Value & 0x00FF
            HighByte = Value >> 8
            Data= []
            Data.append(HighByte)           # Value for indexed register (High byte)
            Data.append(LowByte)            # Value for indexed register (Low byte)

            self.ProcessMasterSlaveWriteTransaction("0004", len(Data) / 2, Data)

            LowByte = Register & 0x00FF
            HighByte = Register >> 8
            Data= []
            Data.append(HighByte)           # indexed register to be written (High byte)
            Data.append(LowByte)            # indexed register to be written (Low byte)

            self.ProcessMasterSlaveWriteTransaction("0003", len(Data) / 2, Data)

        return "Remote command sent successfully"

    #-------------MonitorUnknownRegisters--------------------------------------------------------
    def MonitorUnknownRegisters(self,Register, FromValue, ToValue):

        msgbody = ""
        if self.RegisterIsKnown(Register):
            if not self.MonitorRegister(Register):
                return

            msgbody = "%s changed from %s to %s" % (Register, FromValue, ToValue)
            msgbody += "\n"
            msgbody += self.DisplayRegisters(True)
            msgbody += "\n"
            msgbody += self.DisplayStatus(True)

            self.mail.sendEmail("Monitor Register Alert: " + Register, msgbody)
        else:
            # bulk register monitoring goes here and an email is sent out in a batch
            if self.EnableDebug:
                self.RegistersUnderTestData += "Register %s changed from %s to %s\n" % (Register, FromValue, ToValue)

    #----------  GeneratorDevice::CalculateExerciseTime-------------------------------
    # helper routine for AltSetGeneratorExerciseTime
    def CalculateExerciseTime(self,MinutesFromNow):

        ReturnedValue = 0x00
        Remainder = MinutesFromNow
        # convert minutes from now to weighted bit value
        if Remainder >= 8738:
            ReturnedValue |= 0x1000
            Remainder -=  8738
        if Remainder >= 4369:
            ReturnedValue |= 0x0800
            Remainder -=  4369
        if Remainder >= 2184:
            ReturnedValue |= 0x0400
            Remainder -=  2185
        if Remainder >= 1092:
            ReturnedValue |= 0x0200
            Remainder -=  1092
        if Remainder >= 546:
            ReturnedValue |= 0x0100
            Remainder -=  546
        if Remainder >= 273:
            ReturnedValue |= 0x0080
            Remainder -=  273
        if Remainder >= 136:
            ReturnedValue |= 0x0040
            Remainder -=  137
        if Remainder >= 68:
            ReturnedValue |= 0x0020
            Remainder -=  68
        if Remainder >= 34:
            ReturnedValue |= 0x0010
            Remainder -=  34
        if Remainder >= 17:
            ReturnedValue |= 0x0008
            Remainder -=  17
        if Remainder >= 8:
            ReturnedValue |= 0x0004
            Remainder -=  8
        if Remainder >= 4:
            ReturnedValue |= 0x0002
            Remainder -=  4
        if Remainder >= 2:
            ReturnedValue |= 0x0001
            Remainder -=  2

        return ReturnedValue

    #----------  GeneratorDevice::AltSetGeneratorExerciseTime-------------------------------
    # Note: This method is a bit odd but it is how ML does it. It can result in being off by
    # a min or two
    def AltSetGeneratorExerciseTime(self, CmdString):

        # extract time of day and day of week from command string
        # format is day:hour:min  Monday:15:00
        msgsubject = "Generator Command Notice at " + self.SiteName
        msgbody = "Invalid command syntax for command setexercise"
        try:
            #Format we are looking for is "setexercise=Monday,12:20"
            marker0 = CmdString.lower().find("setexercise")
            marker1 = CmdString.find("=", marker0)
            marker2 = CmdString.find(",",marker1)
            marker3 = CmdString.find(":",marker2+1)
            marker4 = CmdString.find(" ",marker3+1)

            if -1 in [marker0, marker1, marker2, marker3]:
                self.LogError("Validation Error: Error parsing command string in AltSetGeneratorExerciseTime (parse): " + CmdString)
                self.mail.sendEmail(msgsubject, msgbody)
                return

            DayStr = CmdString[marker1+1:marker2]
            HourStr = CmdString[marker2+1:marker3]
            if marker4 == -1:       # was this the last char in the string or now space given?
                MinuteStr = CmdString[marker3+1:]
            else:
                MinuteStr = CmdString[marker3+1:marker4]

            Minute = int(MinuteStr)
            Hour = int(HourStr)

            DayOfWeek =  {  "monday": 0,        # decode for register values with day of week
                            "tuesday": 1,       # NOTE: This decodes for datetime i.e. Monday=0
                            "wednesday": 2,     # the generator firmware programs Sunday = 0, but
                            "thursday": 3,      # this is OK since we are calculating delta minutes
                            "friday": 4,        # since time of day to set exercise time
                            "saturday": 5,
                            "sunday": 6}

            Day = DayOfWeek.get(DayStr.lower(), -1)
            if Day == -1:
                self.LogError("Validation Error: Error parsing command string in AltSetGeneratorExerciseTime (day of week): " + CmdString)
                self.mail.sendEmail(msgsubject, msgbody)
                return

        except Exception, e1:
            self.LogError("Validation Error: Error parsing command string in AltSetGeneratorExerciseTime: " + CmdString)
            self.LogError( str(e1))
            self.mail.sendEmail(msgsubject, msgbody)
            return


        if Minute >59 or Hour > 23 or Day > 6:     # validate minute
            self.LogError("Validation Error: Error parsing command string in AltSetGeneratorExerciseTime (v1): " + CmdString)
            self.mail.sendEmail(msgsubject, msgbody)
            return

        # Get System time and create a new datatime item with the target exercise time
        GeneratorTime = datetime.datetime.strptime(self.GetDateTime(), "%A %B %d, %Y %H:%M")
        # fix hours and min in gen time to the requested exercise time
        TargetExerciseTime = GeneratorTime.replace(hour = Hour, minute = Minute, day = GeneratorTime.day)
        # now change day of week
        while TargetExerciseTime.weekday() != Day:
            TargetExerciseTime += datetime.timedelta(1)

        # convert total minutes between two datetime objects
        DeltaTime =  TargetExerciseTime - GeneratorTime

        days, seconds = DeltaTime.days, DeltaTime.seconds
        delta_hours = days * 24 + seconds // 3600
        delta_minutes = (seconds % 3600) // 60

        total_delta_min = (delta_hours * 60 + delta_minutes)

        WriteValue = self.CalculateExerciseTime(total_delta_min)

        with self.CommAccessLock:
            #  have seen the following values 0cf6,0f8c,0f5e
            Last = WriteValue & 0x00FF
            First = WriteValue >> 8
            Data= []
            Data.append(First)             # Hour 0 - 23
            Data.append(Last)             # Min 0 - 59

            self.ProcessMasterSlaveWriteTransaction("0004", len(Data) / 2, Data)

            #
            Data= []
            Data.append(0)                  # The value for reg 0003 is always 0006. This appears
            Data.append(6)                  # to be an indexed register

            self.ProcessMasterSlaveWriteTransaction("0003", len(Data) / 2, Data)
        return  "Set Exercise Time Command sent (using legacy write)"

    #----------  GeneratorDevice::SetGeneratorExerciseTime-------------------------------
    def SetGeneratorExerciseTime(self, CmdString):

        # use older style write to set exercise time if this flag is set
        if self.bUseLegacyWrite:
            return self.AltSetGeneratorExerciseTime(CmdString)

        # extract time of day and day of week from command string
        # format is day:hour:min  Monday:15:00
        msgbody = "Invalid command syntax for command setexercise"
        try:
            #Format we are looking for is "setexercise=Monday,12:20"
            marker0 = CmdString.lower().find("setexercise")
            marker1 = CmdString.find("=", marker0)
            marker2 = CmdString.find(",",marker1)
            marker3 = CmdString.find(":",marker2+1)
            marker4 = CmdString.find(" ",marker3+1)

            if -1 in [marker0, marker1, marker2, marker3]:
                self.LogError("Validation Error: Error parsing command string in SetGeneratorExerciseTime (parse): " + CmdString)
                return msgbody

            DayStr = CmdString[marker1+1:marker2]
            HourStr = CmdString[marker2+1:marker3]
            if marker4 == -1:       # was this the last char in the string or now space given?
                MinuteStr = CmdString[marker3+1:]
            else:
                MinuteStr = CmdString[marker3+1:marker4]

            Minute = int(MinuteStr)
            Hour = int(HourStr)

            DayOfWeek =  {  "sunday": 0,
                            "monday": 1,        # decode for register values with day of week
                            "tuesday": 2,       # NOTE: This decodes for datetime i.e. Sunday = 0, Monday=1
                            "wednesday": 3,     #
                            "thursday": 4,      #
                            "friday": 5,        #
                            "saturday": 6,
                            }

            Day = DayOfWeek.get(DayStr.lower(), -1)
            if Day == -1:
                self.LogError("Validation Error: Error parsing command string in SetGeneratorExerciseTime (day of week): " + CmdString)
                return msgbody

        except Exception, e1:
            self.LogError("Validation Error: Error parsing command string in SetGeneratorExerciseTime: " + CmdString)
            self.LogError( str(e1))
            return msgbody


        if Minute >59 or Hour > 23 or Day > 6:     # validate minute
            self.LogError("Validation Error: Error parsing command string in SetGeneratorExerciseTime (v1): " + CmdString)
            return msgbody

        with self.CommAccessLock:
            Data= []
            Data.append(0x00)               #
            Data.append(Day)                # Day

            self.ProcessMasterSlaveWriteTransaction("002e", len(Data) / 2, Data)

            #
            Data= []
            Data.append(Hour)                  #
            Data.append(Minute)                #

            self.ProcessMasterSlaveWriteTransaction("002c", len(Data) / 2, Data)

        return  "Set Exercise Time Command sent"

     #----------  GeneratorDevice::SetGeneratorTimeDate-------------------------------
    def SetGeneratorQuietMode(self, CmdString):

        # extract quiet mode setting from Command String
        # format is setquiet=yes or setquiet=no
        msgbody = "Invalid command syntax for command setquiet"
        try:
            #Format we are looking for is "setexercise=Monday,12:20"
            marker0 = CmdString.lower().find("setquiet")
            marker1 = CmdString.find("=", marker0)
            marker2 = CmdString.find(" ",marker1+1)

            if -1 in [marker0, marker1]:
                self.LogError("Validation Error: Error parsing command string in SetGeneratorQuietMode (parse): " + CmdString)
                return msgbody

            if marker2 == -1:       # was this the last char in the string or now space given?
                Mode = CmdString[marker1+1:]
            else:
                Mode = CmdString[marker1+1:marker2]

            if "on" in Mode.lower():
                ModeValue = 0x01
            elif "off" in Mode.lower():
                ModeValue = 0x00
            else:
                self.LogError("Validation Error: Error parsing command string in SetGeneratorQuietMode (value): " + CmdString)
                return msgbody

        except Exception, e1:
            self.LogError("Validation Error: Error parsing command string in SetGeneratorQuietMode: " + CmdString)
            self.LogError( str(e1))
            return msgbody

        Data= []
        Data.append(0x00)
        Data.append(ModeValue)
        with self.CommAccessLock:
            self.ProcessMasterSlaveWriteTransaction("002f", len(Data) / 2, Data)

        return "Set Quiet Mode Command sent"

    #----------  GeneratorDevice::SetGeneratorTimeDate-------------------------------
    def SetGeneratorTimeDate(self):


        # get system time
        d = datetime.datetime.now()

        # attempt to make the seconds zero when we set the generator time so it will
        # be very close to the system time
        # Testing has show that this is not really achieving the seconds synced up, but
        # it does make the time offset consistant
        while d.second != 0:
            time.sleep(60 - d.second)       # sleep until seconds are zero
            d = datetime.datetime.now()

        # We will write three registers at once: 000e - 0010.
        Data= []
        Data.append(d.hour)             #000e
        Data.append(d.minute)
        Data.append(d.month)            #000f
        Data.append(d.day)
        # Note: Day of week should always be zero when setting time
        Data.append(0)                  #0010
        Data.append(d.year - 2000)

        self.ProcessMasterSlaveWriteTransaction("000e", len(Data) / 2, Data)

    # ---------- GeneratorDevice::DiscardByte------------------
    def DiscardByte(self):

            discard = self.Slave.DiscardByte()
            self.LogError("Discarding byte slave: %02x" % (discard))

   # ---------- GeneratorDevice::UpdateRegistersFromPacket------------------
   #    Update our internal register list based on the request/response packet
    def UpdateRegistersFromPacket(self, MasterPacket, SlavePacket):

        if len(MasterPacket) < MIN_PACKET_LENGTH_RES or len(SlavePacket) < MIN_PACKET_LENGTH_RES:
            return

        if MasterPacket[MBUS_ADDRESS] != self.Address:
            self.LogError("Validation Error:: Invalid address in UpdateRegistersFromPacket (Master)")

        if SlavePacket[MBUS_ADDRESS] != self.Address:
            self.LogError("Validation Error:: Invalid address in UpdateRegistersFromPacket (Slave)")

        if not SlavePacket[MBUS_COMMAND] in [MBUS_CMD_READ_REGS]:
            self.LogError("UpdateRegistersFromPacket: Unknown Function slave %02x %02x" %  (SlavePacket[0],SlavePacket[1]))

        if not MasterPacket[MBUS_COMMAND] in [MBUS_CMD_READ_REGS]:
            self.LogError("UpdateRegistersFromPacket: Unknown Function master %02x %02x" %  (MasterPacket[0],MasterPacket[1]))

        # get register from master packet
        Register = "%02x%02x" % (MasterPacket[2],MasterPacket[3])
        # get value from slave packet
        length = SlavePacket[MBUS_RESPONSE_LEN]
        if (length + MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH) > len(SlavePacket):
                return False
        RegisterValue = ""
        for i in range(3, length+3):
            RegisterValue += "%02x" % SlavePacket[i]
        # update register list
        self.UpdateRegisterList(Register, RegisterValue)

    #------------GeneratorDevice::CheckCrc---------------------
    def CheckCRC(self, Packet):

        if len(Packet) == 0:
            return False
        ByteArray = bytearray(Packet[:len(Packet)-2])
        results = self.ModbusCrc(str(ByteArray))
        CRCValue = ( ( Packet[-1] & 0xFF ) << 8 ) | ( Packet[ -2] & 0xFF )
        if results != CRCValue:
            self.LogError("Data Error: CRC check failed: %04x  %04x" % (results, CRCValue))
            return False
        return True

    #------------GeneratorDevice::GetCRC---------------------
    def GetCRC(self, Packet):

        if len(Packet) == 0:
            return False
        ByteArray = bytearray(Packet)
        results = self.ModbusCrc(str(ByteArray))

        return results

    #------------ GeneratorDevice::GetRegisterLength --------------------------------------------
    def GetRegisterLength(self, Register):

        RegInfoReg = self.BaseRegisters.get(Register, [0,0])

        RegLength = RegInfoReg[self.REGLEN]

        if RegLength == 0:
            RegInfoReg = self.PrimeRegisters.get(Register, [0,0])
            RegLength = RegInfoReg[self.REGLEN]

        return RegLength

    #------------ GeneratorDevice::MonitorRegister --------------------------------------------
    # return true if we are monitoring this register
    def MonitorRegister(self, Register):

        RegInfoReg = self.BaseRegisters.get(Register, [0,-1])

        MonitorReg = RegInfoReg[self.REGMONITOR]

        if MonitorReg == -1:
            RegInfoReg = self.PrimeRegisters.get(Register, [0,-1])
            MonitorReg = RegInfoReg[self.REGMONITOR]

        if MonitorReg == 1:
            return True
        return False

    #------------ GeneratorDevice::ValidateRegister --------------------------------------------
    def ValidateRegister(self, Register, Value):

        ValidationOK = True
        # validate the length of the data against the size of the register
        RegLength = self.GetRegisterLength(Register)
        if(RegLength):      # if this is a base register
            if RegLength != (len(Value) / 2):  # note: the divide here compensates between the len of hex values vs string data
                self.LogError("Validation Error: Invalid register length (base) %s:%s %d %d" % (Register, Value, RegLength, len(Value) /2 ))
                ValidationOK = False
        # appears to be Start/Stop Log or service log
        elif int(Register,16) >=  SERVICE_LOG_STARTING_REG and int(Register,16) <= SERVICE_LOG_END_REG:
            if len(Value) != 16:
                self.LogError("Validation Error: Invalid register length (Service) %s %s" % (Register, Value))
                ValidationOK = False
        elif int(Register,16) >=  START_LOG_STARTING_REG and int(Register,16) <= START_LOG_END_REG:
            if len(Value) != 16:
                self.LogError("Validation Error: Invalid register length (Start) %s %s" % (Register, Value))
                ValidationOK = False
        elif int(Register,16) >=  ALARM_LOG_STARTING_REG and int(Register,16) <= ALARM_LOG_END_REG:
            if len(Value) != 20:      # length appears to indicate this is an alarm log register
                self.LogError("Validation Error: Invalid register length (Alarm) %s %s" % (Register, Value))
                ValidationOK = False
        elif int(Register,16) == MODEL_REG:
            if len(Value) != 20:
                self.LogError("Validation Error: Invalid register length (Model) %s %s" % (Register, Value))
                ValidationOK = False
        else:
            self.LogError("Validation Error: Invalid register or length (Unkown) %s %s" % (Register, Value))
            ValidationOK = False

        return ValidationOK


    #------------ GeneratorDevice::RegisterIsLog --------------------------------------------
    def RegisterIsLog(self, Register):

        ## Is this a log register
        if int(Register,16) >=  SERVICE_LOG_STARTING_REG and int(Register,16) <= SERVICE_LOG_END_REG:
            return True
        elif int(Register,16) >=  START_LOG_STARTING_REG and int(Register,16) <= START_LOG_END_REG:
            return True
        elif int(Register,16) >=  ALARM_LOG_STARTING_REG and int(Register,16) <= ALARM_LOG_END_REG:
            return True
        elif int(Register,16) == MODEL_REG:
            return True
        return False

    #------------ GeneratorDevice::UpdateRegisterList --------------------------------------------
    def UpdateRegisterList(self, Register, Value):

        # Validate Register by length
        if len(Register) != 4 or len(Value) < 4:
            self.LogError("Validation Error: Invalid data in UpdateRegisterList: %s %s" % (Register, Value))

        if self.RegisterIsKnown(Register):
            if not self.ValidateRegister(Register, Value):
                return
            RegValue = self.Registers.get(Register, "")

            if RegValue == "":
                self.Registers[Register] = Value        # first time seeing this register so add it to the list
            elif RegValue != Value:
                # don't print values of registers we have validated the purpose
                if not self.RegisterIsLog(Register):
                    self.MonitorUnknownRegisters(Register,RegValue, Value)
                self.Registers[Register] = Value
                self.Changed += 1
            else:
                self.NotChanged += 1
        else:   # Register Under Test
            RegValue = self.RegistersUnderTest.get(Register, "")
            if RegValue == "":
                self.RegistersUnderTest[Register] = Value        # first time seeing this register so add it to the list
            elif RegValue != Value:
                self.MonitorUnknownRegisters(Register,RegValue, Value)
                self.RegistersUnderTest[Register] = Value        # update the value

    #------------ GeneratorDevice::RegisterIsKnown ------------------------------------
    def RegisterIsKnown(self, Register):

        RegLength = self.GetRegisterLength(Register)

        if RegLength != 0:
            return True

        return self.RegisterIsLog(Register)

    #------------ GeneratorDevice::GetRegisterValueFromList ------------------------------------
    def GetRegisterValueFromList(self,Register):

        return self.Registers.get(Register, "")

    #------------ GeneratorDevice::RegRegValue ------------------------------------
    def GetRegValue(self, CmdString):

        # extract quiet mode setting from Command String
        # format is setquiet=yes or setquiet=no
        msgbody = "Invalid command syntax for command getregvalue"
        try:
            #Format we are looking for is "getregvalue=01f4"
            marker0 = CmdString.lower().find("getregvalue")
            marker1 = CmdString.find("=", marker0)
            marker2 = CmdString.find(" ",marker1+1)

            if -1 in [marker0, marker1]:
                self.LogError("Validation Error: Error parsing command string in GetRegValue (parse): " + CmdString)
                return msgbody

            if marker2 == -1:       # was this the last char in the string or now space given?
                Register = CmdString[marker1+1:]
            else:
                Register = CmdString[marker1+1:marker2]

            RegValue = self.GetRegisterValueFromList(Register)

            if RegValue == "":
                self.LogError("Validation Error: Register  not known:" + Register)
                msgbody = "Unknown Register: " + Register
                return msgbody

            msgbody = RegValue

        except Exception, e1:
            self.LogError("Validation Error: Error parsing command string in GetRegValue: " + CmdString)
            self.LogError( str(e1))
            return msgbody

        return msgbody

    #------------ GeneratorDevice::DisplayRegisters --------------------------------------------
    def DisplayRegisters(self, ToString = False):

        outstring = ""
        outstring += self.printToScreen("Num Regs: %d " % len(self.Registers), ToString)
        if self.NotChanged == 0:
            self.TotalChanged = 0.0
        else:
            self.TotalChanged =  float(self.Changed)/float(self.NotChanged)
        outstring += self.printToScreen("Not Changed: %d Changed %d Total Changed %.2f" % (self.NotChanged, self.Changed, self.TotalChanged), ToString)

        # print all the registers
        count = 0
        for Register, Value in self.Registers.items():

            # do not display log registers or model register
            if int(Register,16) >=  SERVICE_LOG_STARTING_REG and int(Register,16) <= SERVICE_LOG_END_REG:
                continue
            elif int(Register,16) >=  START_LOG_STARTING_REG and int(Register,16) <= START_LOG_END_REG:
                continue
            elif int(Register,16) >=  ALARM_LOG_STARTING_REG and int(Register,16) <= ALARM_LOG_END_REG:
                continue
            elif int(Register,16) == MODEL_REG:
                continue
            ##
            if count & 0x01:
                outstring += self.printToScreen("%s:%s\n" % (Register, Value), ToString, nonewline = True)
            else:
                outstring += self.printToScreen("%s:%s\t\t\t" % (Register, Value), ToString, nonewline = True)
            count += 1
        if count & 0x01:
            outstring += self.printToScreen("\n", ToString, nonewline = True)

        return outstring

     #---------- process command from email and socket -------------------------------
    def ProcessCommand(self, command, fromsocket = False):

        if(len(command)) == 0:
            return ""

        if(not command.lower().startswith( 'generator:' )):
            self.printToScreen("Invalid GENERATOR command")
            return ""

        CommandList = command.split(" ")

        msgsubject = "Generator Command Response at " + self.SiteName
        if not fromsocket:
            msgbody = "\n"
        else:
            msgbody = ""


        for item in CommandList:
            item = item.lstrip()
            item = item.rstrip()
            if "generator:" in item.lower():
                continue
            if "registers" in item.lower():         # display registers
                self.printToScreen("GET REGISTERS")
                msgbody += "Registers:\n"
                msgbody += self.DisplayRegisters(True)
                continue
            if "logs" in item.lower():
                self.printToScreen("GET LOGS")           # display all logs
                msgbody += "Logs:\n"
                msgbody += self.DisplayLogs(AllLogs = True, PrintToString = True)
                continue
            if "status" in item.lower():            # display decoded generator info
                self.printToScreen("STATUS")
                msgbody += "Status:\n"
                msgbody += self.DisplayStatus(True)
                continue
            if "maint" in item.lower():
                self.printToScreen("MAINT")
                msgbody += "Maintenance:\n"
                msgbody += self.DisplayMaintenance(True)
                continue
            if "monitor" in item.lower():
                self.printToScreen("MONITOR")
                msgbody += "Monitor:\n"
                msgbody += self.DisplayMonitor(True)
                continue
            if "settime" in item.lower():           # set time and date
                self.printToScreen("SETTIME")
                # This is done is a separate thread as not to block any return email processing
                # since we attempt to sync with generator time
                SetTimeThread = threading.Thread(target=self.SetGeneratorTimeDate, name = "SetTimeThread")
                SetTimeThread.daemon = True
                SetTimeThread.start()               # start settime thread
                msgbody += "Time Set: Command Sent\n"
                continue
            if "setexercise" in item.lower():
                self.printToScreen("SETEXERCISE")
                msgbody += self.SetGeneratorExerciseTime( command.lower())
                continue
            if "setquiet" in item.lower():
                self.printToScreen("SETQUIET")
                msgbody += self.SetGeneratorQuietMode( command.lower())
                continue
            if "help" in item.lower():              # display help screen
                self.printToScreen("HELP")
                msgbody += "Help:\n"
                msgbody += self.DisplayHelp(True)
                continue
            if "outage" in item.lower():              # display help screen
                self.printToScreen("OUTAGE")
                msgbody += "Outage:\n"
                msgbody += self.DisplayOutage(True)
                continue
            ## These commands are used by the web / socket interface only
            if fromsocket:
                if "getsitename" in item.lower():
                    msgbody += self.SiteName
                    continue
                if "getbase" in item.lower():       # base status
                    msgbody += self.GetBaseStatus()
                    continue
                if "getexercise" in item.lower():
                    msgbody += self.GetParsedExerciseTime()
                    continue
                if "getregvalue" in item.lower():
                    msgbody += self.GetRegValue(command.lower())
                    continue
                if "getdebug" in item.lower():
                    msgbody += self.GetDeadThreadName()
                    continue
                if "setremote" in item.lower():
                    msgbody += self.SetGeneratorRemoteStartStop(command.lower())
                    continue
            if not fromsocket:
                msgbody += "\n\n"

        if not fromsocket:
            self.mail.sendEmail(msgsubject, msgbody)
            return ""       # ignored by email module
        else:
            msgbody += "EndOfMessage"
            return msgbody

    #------------ GeneratorDevice::CheckForOutage ----------------------------------------
    # also update min and max utility voltage
    def CheckForOutage(self):

        # get utility Voltage
        Value = self.GetRegisterValueFromList("0009")
        if len(Value) != 4:
            return ""           # we don't have a value for this register yet
        UtilityVolts = int(Value, 16)
        # Get threshold voltage
        Value = self.GetRegisterValueFromList("0011")
        if len(Value) != 4:
            return ""           # we don't have a value for this register yet
        ThresholdVoltage = int(Value, 16)
        # get pickup voltage
        Value = self.GetRegisterValueFromList("023b")
        if len(Value) != 4:
            return ""           # we don't have a value for this register yet
        PickupVoltage = int(Value, 16)

        # if something is wrong then we use some sensible values here
        if PickupVoltage == 0:
            PickupVoltage = DEFAULT_PICKUP_VOLTAGE
        if ThresholdVoltage == 0:
            ThresholdVoltage = DEFAULT_THRESHOLD_VOLTAGE

        # first time thru set the values to the same voltage level
        if self.UtilityVoltsMin == 0 and self.UtilityVoltsMax == 0:
            self.UtilityVoltsMin = UtilityVolts
            self.UtilityVoltsMax = UtilityVolts

        if UtilityVolts > self.UtilityVoltsMax:
            if UtilityVolts > PickupVoltage:
                self.UtilityVoltsMax = UtilityVolts

        if UtilityVolts < self.UtilityVoltsMin:
            if UtilityVolts > ThresholdVoltage:
                self.UtilityVoltsMin = UtilityVolts

        TransferStatus = self.GetTransferStatus()

        if len(TransferStatus):
            if self.TransferActive:
                if TransferStatus == "Utility":
                    self.TransferActive = False
                    msgbody = "\nPower is being supplied by the utility line. "
                    self.mail.sendEmail("Transfer Switch Changed State Notice at " + self.SiteName, msgbody)
            else:
                if TransferStatus == "Generator":
                    self.TransferActive = True
                    msgbody = "\nPower is being supplied by the generator. "
                    self.mail.sendEmail("Transfer Switch Changed State Notice at " + self.SiteName, msgbody)

        # Check for outage
        # are we in an outage now
        # NOTE: for now we are just comparing these numbers, the generator has a programmable delay
        # that must be met once the voltage passes the threshold. This may cause some "switch bounce"
        # testing needed
        if self.SystemInOutage:
            if UtilityVolts > PickupVoltage:
                self.SystemInOutage = False
                self.LastOutageDuration = datetime.datetime.now() - self.OutageStartTime
                OutageStr = str(self.LastOutageDuration).split(".")[0]  # remove microseconds from string
                msgbody = "\nUtility Power Restored. Duration of outage " + OutageStr
                self.mail.sendEmail("Outage Recovery Notice at " + self.SiteName, msgbody)
        else:
            if UtilityVolts < ThresholdVoltage:
                self.SystemInOutage = True
                self.OutageStartTime = datetime.datetime.now()
                msgbody = "\nUtility Power Out at " + self.OutageStartTime.strftime("%Y-%m-%d %H:%M:%S")
                self.mail.sendEmail("Outage Notice at " + self.SiteName, msgbody)

    #------------ GeneratorDevice::CheckForAlarms ----------------------------------------
    # Note this must be called from the Process thread since it queries the log registers
    # when in master emulation mode
    def CheckForAlarms(self):

        # update outage time, update utility low voltage and high voltage
        self.CheckForOutage()

        # now check to see if there is an alarm
        Value = self.GetRegisterValueFromList("0001")
        if len(Value) != 8:
            return ""           # we don't have a value for this register yet
        RegVal = int(Value, 16)

        if RegVal == self.LastAlarmValue:
            return      # nothing new to report, return

        # if we get past this point there is something to report, either first time through
        # or there is an alarm that has been set or reset
        self.LastAlarmValue = RegVal    # update the stored alarm

        self.UpdateLogRegistersAsMaster()       # Update all log registers

        # Create notice email strings
        msgsubject = ""
        msgbody = "\n\n"
        msgbody += self.printToScreen("Notice from Generator: \n", True)

         # get switch state
        Value = self.GetSwitchState()
        if len(Value):
            msgbody += self.printToScreen("Switch State: " + Value, True)
        #get Engine state
        # This reports on the state read at the beginning of the routine which fixes a
        # race condition when switching from starting to running
        Value = self.GetEngineState(RegVal)
        if len(Value):                          #
            msgbody += self.printToScreen("Engine State: " + Value, True)

        if self.EvolutionController:
            msgbody += self.printToScreen("Active Relays: " + self.GetDigitalOutputs(), True)

        msgsubject += "Generator Alert at " + self.SiteName + ": "

        AlarmState = self.GetAlarmState()

        if len(AlarmState) or (not self.BitIsEqual(RegVal,   0xFFF0FFF0, 0x00000000)):
            self.GeneratorInAlarm = True
            # check specific alarm bits in Reg 0001
            # if we get here we do not know the alarm bit
            if self.BitIsEqual(RegVal,   0xFFF0FFF0, 0x00000010):
                msgsubject += "WARNING "
                msgbody += self.printToScreen("\nWARNING: Check Maintenance and Alarm Log", True)
            else:
                msgsubject += "CRITICAL "
                if len(AlarmState):
                    msgbody += self.printToScreen("\nCurrent Alarm: " + AlarmState, True)
                # if in alarm get Last Error Code
                if self.EvolutoinController:
                    Value = self.GetRegisterValueFromList("05f1")
                    if len(Value) == 4:
                        msgbody += self.printToScreen("Last Alarm Code: \n%s" % self.GetAlarmInfo(Value), True)

                if not self.BitIsEqual(RegVal,   0xFFF0FFE0, 0x00000000):
                    msgbody += self.printToScreen("\nUnhandled Alert: Register 0001:%08x" % RegVal, True)

        # set this flag to let the heartbeat thread notify Nagios
        elif len(AlarmState) == 0:
            self.GeneratorInAlarm = False

            # Reg 0001 is now zero again
            msgsubject = "Generator Notice: " + self.SiteName
            msgbody += self.printToScreen("\nNo Alarms: 0001:%08x" % RegVal, True)


        # send email notice
        msgbody += self.printToScreen("\nLast Log Entries:", True)

        # display last log entries
        msgbody += self.DisplayLogs(AllLogs = False, PrintToString = True)     # if false don't display full logs

        if self.GeneratorInAlarm:
            msgbody += self.printToScreen("To clear the Alarm/Warning message, press OFF on the control panel keypad followed by the ENTER key.", True)

        self.mail.sendEmail(msgsubject , msgbody)

    #------------ GeneratorDevice::DisplayHelp ----------------------------------------
    def DisplayHelp(self, ToString = False):

        outstring = self.printToScreen("\nCommands:", ToString)
        outstring += self.printToScreen("   status      - display engine and line information", ToString)
        outstring += self.printToScreen("   maint       - display maintenance and service information", ToString)
        outstring += self.printToScreen("   outage      - display current and last outage (since program launched) info, also shows utility min and max values", ToString)
        outstring += self.printToScreen("   monitor     - display communication statistics and monitor health", ToString)
        outstring += self.printToScreen("   logs        - display all alarm, on/off, and maintenance logs", ToString)
        outstring += self.printToScreen("   registers   - display contents of registers being monitored", ToString)
        outstring += self.printToScreen("   settime     - set generator time to system time", ToString)
        outstring += self.printToScreen("   setexercise - set the exercise time of the generator. i.e. setexercise=Monday,13:30", ToString)
        outstring += self.printToScreen("   setquiet    - enable or disable exercise quiet mode, i.e.  setquiet=on or setquiet=off", ToString)
        outstring += self.printToScreen("\n", ToString)

        outstring += self.printToScreen("To clear the Alarm/Warning message, press OFF on the control panel keypad followed by the ENTER key.\n", ToString)
        outstring += self.printToScreen("To access Dealer Menu on the controller, from the top menu selection (SYSTEM, DATE/TIME, BATTERY, SUB-MENUS)", ToString)
        outstring += self.printToScreen("enter UP UP ESC DOWN UP ESC UP, then navigate to the dealer menu and press enter.", ToString)
        outstring += self.printToScreen("For liquid cooled models a level 2 dealer code can be entered, ESC UP UP DOWN DOWN ESC ESC, then naviagte to ", ToString)
        outstring += self.printToScreen("the dealer menu and press enter.", ToString)

        outstring += self.printToScreen("\n", ToString)

        return outstring

     #------------ GeneratorDevice::DisplayMaintenance ----------------------------------------
    def DisplayMaintenance (self, ToString = False):

        outstring = "\n"

        outstring += self.printToScreen("Exercise:", ToString)
        # exercise time
        Value = self.GetExerciseTime()
        if len(Value):
            outstring += self.printToScreen("Exercise Time: " + Value, ToString, spacer = True)
        if self.EvolutionController:
            # get exercise duration
            Value = self.GetExerciseDuration()
            if len(Value):
                outstring += self.printToScreen("Exercise Duration: " + Value, ToString, spacer = True)

        outstring += self.printToScreen("\nService:", ToString)
        # get next schedule service if available
        Value = self.GetServiceInfo()
        if len(Value):
            outstring += self.printToScreen("Service Scheduled: " + Value, ToString, spacer = True)
        # get run times if available
        Value = self.GetRunTimes()
        if len(Value):
            outstring += self.printToScreen(Value, ToString, spacer = True)

        # HW and Firmware versions
        Value = self.GetVersions()
        if len(Value):
            outstring += self.printToScreen(Value, ToString, spacer = True)

        return outstring

    #------------------- GeneratorDevice::DisplayOutage -----------------
    def DisplayOutage(self, ToString = False):

        outstr = "\n"
        if self.SystemInOutage:
            outstr += self.printToScreen("System in outage since %s" % self.OutageStartTime.strftime("%Y-%m-%d %H:%M:%S"), ToString, spacer = True)
        else:
            if self.ProgramStartTime != self.OutageStartTime:
                OutageStr = str(self.LastOutageDuration).split(".")[0]  # remove microseconds from string
                outstr += self.printToScreen("Last outage occurred at %s and lasted %s." % (self.OutageStartTime.strftime("%Y-%m-%d %H:%M:%S"), OutageStr), ToString, spacer = True)
            else:
                outstr += self.printToScreen("No outage has occurred since program launched.", ToString, spacer = True)

         # get utility voltage
        Value = self.GetUtilityVoltage()
        if len(Value):
            outstr += self.printToScreen("Utility Voltage : " + Value, ToString, spacer = True)
            outstr += self.printToScreen("Utility Voltage Minimum : %dV " % (self.UtilityVoltsMin), ToString, spacer = True)
            outstr += self.printToScreen("Utility Voltage Maximum : %dV " % (self.UtilityVoltsMax), ToString, spacer = True)

        return outstr

    #------------ GeneratorDevice::DisplayMonitor --------------------------------------------
    def DisplayMonitor(self, ToString = False):

        outstring = "\n"
        outstring += self.printToScreen("Monitor Health: " + self.GetSystemHealth(), ToString, spacer = True)

        GeneratorType = ""
        if self.EvolutionController:
            GeneratorType += "Evolution Controller, "
        else:
            GeneratorType += "Nexus Controller, "

        if self.LiquidCooled:
            GeneratorType += "Liquid Cooled"
        else:
            GeneratorType += "Air Cooled"

        outstring += self.printToScreen("Generator Type Selected : " + GeneratorType, ToString, spacer = True)

        outstring += self.printToScreen("PacketCount M:%d: S:%d Buffer Count:%d" % (self.Slave.TxPacketCount, self.Slave.RxPacketCount, len(self.Slave.Buffer)), ToString, spacer = True)

        if self.Slave.CrcError == 0:
            PercentErrors = 0.0
        else:
            PercentErrors = float(self.Slave.CrcError) / float(self.Slave.RxPacketCount)

        outstring += self.printToScreen("CRC Errors :%d  Percent :%.2f" % (self.Slave.CrcError, PercentErrors), ToString, spacer = True)
        outstring += self.printToScreen("Discarded  :%d  Restarts:%s" %  (self.Slave.DiscardedBytes,self.Slave.Restarts), ToString, spacer = True)

        CurrentTime = datetime.datetime.now()

        Delta = CurrentTime - self.ProgramStartTime        # yields a timedelta object
        PacketsPerSecond = float((self.Slave.TxPacketCount + self.Slave.RxPacketCount)) / float(Delta.total_seconds())
        outstring += self.printToScreen("Packets per second:%.2f" % (PacketsPerSecond), ToString, spacer = True)

        ProgramRunTime = datetime.datetime.now() - self.ProgramStartTime
        outstr = str(ProgramRunTime).split(".")[0]  # remove microseconds from string
        outstring += self.printToScreen(self.ProgramName + " running for " + outstr + ".", ToString, spacer = True)

        return outstring
    #------------ GeneratorDevice::DisplayStatus ----------------------------------------
    def DisplayStatus(self, ToString = False):

        outstring = "\n"

        outstring += self.printToScreen("Engine State:", ToString)
        # get switch state
        Value = self.GetSwitchState()
        if len(Value):
            outstring += self.printToScreen("Switch State: " + Value, ToString, spacer = True)
        #get Engine state
        Value = self.GetEngineState()
        if len(Value):
            outstring += self.printToScreen("Engine State: " + Value, ToString, spacer = True)

        if self.EvolutionController:
            Value = self.GetDigitalOutputs()
            if len(Value):
                outstring += self.printToScreen("Active Relays: " + Value, True, spacer= True)

            Value = self.GetAlarmState()
            if len(Value):
                outstring += self.printToScreen("Current Alarm(s): " + Value, True, spacer= True)

        # get battery voltage
        Value = self.GetBatteryVoltage()
        if len(Value):
            outstring += self.printToScreen("Battery Voltage: " + Value + ", Status: " + self.GetBatteryStatus(), ToString, spacer = True)
        # Get the RPM
        Value = self.GetRPM()
        if len(Value):
            outstring += self.printToScreen("RPM: " + Value, ToString, spacer = True)
        # get the frequency
        Value = self.GetFrequency()
        if len(Value):
            outstring += self.printToScreen("Frequency: " + Value, ToString, spacer = True)
        # get the generator output voltage, don't display if zero
        Value = self.GetVoltageOutput()
        if len(Value):
            outstring += self.printToScreen("Output Voltage: " + Value, ToString, spacer = True)
        if self.bDisplayUnknownSensors:
            # get UKS
            Value = self.GetUnknownSensor1()
            if len(Value):
                outstring += self.printToScreen("Unknown Sensor 1: " + Value, ToString, spacer = True)
            # get UKS
            Value = self.GetUnknownSensor2()
            if len(Value):
                outstring += self.printToScreen("Unknown Sensor 2: " + Value, ToString, spacer = True)
            # get UKS
            Value = self.GetUnknownSensor3()
            if len(Value):
                outstring += self.printToScreen("Unknown Sensor 3: " + Value, ToString, spacer = True)
             # get UKS
            Value = self.GetUnknownSensor4()
            if len(Value):
                outstring += self.printToScreen("Unknown Sensor 4: " + Value, ToString, spacer = True)

        outstring += self.printToScreen("\nLine State:", ToString)
        if self.EvolutionController:
            # get transfer switch status
            Value = self.GetTransferStatus()
            if len(Value):
                outstring += self.printToScreen("Transfer Switch Status: " + Value, ToString, spacer = True)
        # get utility voltage
        Value = self.GetUtilityVoltage()
        if len(Value):
            MinMax = ", Min: %dV, Max: %dV" % (self.UtilityVoltsMin, self.UtilityVoltsMax)
            outstring += self.printToScreen("Utility Voltage: " + Value + MinMax, ToString, spacer = True)
        # get Utility Threshold Voltage
        Value = self.GetThresholdVoltage()
        if len(Value):
            outstring += self.printToScreen("Utility Threshold Voltage: " + Value, ToString, spacer = True)

        outstring += self.printToScreen("\nLast Log Entries:", ToString)

        # display last log entries
        outstring += self.DisplayLogs(AllLogs = False, PrintToString = ToString)     # if false don't display full logs

        outstring += self.printToScreen("\nGeneral:", ToString)
        # display info decoded from the registers
        outstring += self.printToScreen("Monitor Time:   " + datetime.datetime.now().strftime("%A %B %-d, %Y %H:%M:%S"), ToString, spacer = True)
        # Generator time
        Value = self.GetDateTime()
        if len(Value):
            outstring += self.printToScreen("Generator Time: " + Value, ToString, spacer = True)

        return outstring

    #------------ GeneratorDevice::LogRange --------------------------------------------
    # used for iterating log registers
    def LogRange(self, start, count, step):
        Counter = 0
        while Counter < count:
            yield start
            start += step
            Counter += 1

    #------------ GeneratorDevice::DisplayLogs --------------------------------------------
    def DisplayLogs(self, AllLogs = False, PrintToString = False):

        if AllLogs == False:
            outstring = ""
        else:
            outstring = "\n"

        if AllLogs:
            outstring += self.printToScreen("Start Stop Log:", PrintToString)
            for Register in self.LogRange(START_LOG_STARTING_REG , LOG_DEPTH,START_LOG_STRIDE):
                RegStr = "%04x" % Register
                Value = self.GetRegisterValueFromList(RegStr)
                if len(Value) == 0:
                    break
                LogStr = self.ParseLogEntry(Value)
                if len(LogStr):             # if the register is there but no log entry exist
                    outstring += self.printToScreen(LogStr, PrintToString, spacer = True)

            if self.EvolutionController:
                outstring += self.printToScreen("Service Log:   ", PrintToString)
                for Register in self.LogRange(SERVICE_LOG_STARTING_REG , LOG_DEPTH, SERVICE_LOG_STRIDE):
                    RegStr = "%04x" % Register
                    Value = self.GetRegisterValueFromList(RegStr)
                    if len(Value) == 0:
                        break
                    LogStr = self.ParseLogEntry(Value)
                    if len(LogStr):             # if the register is there but no log entry exist
                        outstring += self.printToScreen(LogStr, PrintToString, spacer = True)

                outstring += self.printToScreen("Alarm Log:     ", PrintToString)
                for Register in self.LogRange(ALARM_LOG_STARTING_REG , LOG_DEPTH, ALARM_LOG_STRIDE):
                    RegStr = "%04x" % Register
                    Value = self.GetRegisterValueFromList(RegStr)
                    if len(Value) == 0:
                        break
                    LogStr = self.ParseLogEntry(Value)
                    if len(LogStr):             # if the register is there but no log entry exist
                        outstring += self.printToScreen(LogStr, PrintToString, spacer = True)

        else:   # only print last entry in log
            RegStr = "%04x" % START_LOG_STARTING_REG
            Value = self.GetRegisterValueFromList(RegStr)
            if len(Value):
                outstring += self.printToScreen("Start Stop Log: " + self.ParseLogEntry(Value), PrintToString, spacer = True)

            if self.EvolutionController:
                RegStr = "%04x" % SERVICE_LOG_STARTING_REG
                Value = self.GetRegisterValueFromList(RegStr)
                if len(Value):
                    outstring += self.printToScreen("Service Log:    " + self.ParseLogEntry(Value), PrintToString, spacer = True)

                RegStr = "%04x" % ALARM_LOG_STARTING_REG
                Value = self.GetRegisterValueFromList(RegStr)
                if len(Value):
                    outstring += self.printToScreen("Alarm Log:      " + self.ParseLogEntry(Value), PrintToString, spacer = True)

        # Get Last Error Code
        if self.EvolutionController:
            Value = self.GetRegisterValueFromList("05f1")
            if len(Value) == 4:
                outstring += "\nLast Alarm Code: %s" % self.GetAlarmInfo(Value)

        return outstring


    #----------  GeneratorDevice::ParseLogEntry-------------------------------
    #  Log Entries are in one of two formats, 16 (On off Log, Service Log) or
    #   20 chars (Alarm Log)
    #     AABBCCDDEEFFGGHHIIJJ
    #       AA = Log Code - Unique Value for displayable string
    #       BB = log entry number
    #       CC = minutes
    #       DD = hours
    #       EE = Month
    #       FF = Date
    #       GG = year
    #       HH = Unknown
    #       IIJJ = Alarm Code for Alarm Log only
    #---------------------------------------------------------------------------
    def ParseLogEntry(self, Value):

        LogDecoder = {
        0x28: "Switched Off",               # Start / Stop Log
        0x29: "Running - Manual",           # Start / Stop Log
        0x2A: "Stopped - Auto",             # Start / Stop Log
        0x2B: "Running - Utility Loss",     # Start / Stop Log
        0x2D: "Running - Radio Start",      # Start / Stop Log
        0x2E: "Running - Exercise",         # Start / Stop Log
        0x3D: "Stopped - Warning",          # Start / Stop Log
        # Running 2 Wire Start
        # Running Remote Start
        # Stopped Alarm
        0x17: "Service Schedule A",         # Maint
        0x3D: "Schedule A Serviced",        # Maint
        # Maintenance Reset
        0x06: "Low Coolant Level",          # 2720  Alarm
        0x47: "Low Fuel Level",             # 2700A Alarm
        0x1B: "Low Fuel Level",             # 2680W Alarm
        0x49: "Hall Calibration Error"      # 2810  Alarm
        }

        # other known log entries that we do not know the codes for:
        ### Maint Log
        # *Schedule Service A
        # Schedule Service B
        # Schedule Service C
        # *Schedule A Serviced
        # Schedule B Serviced
        # Schedule C Serviced
        # Inspect Battery
        # Maintenance Reset
        # Battery Maintained

        ### Start / Stop Log
        # Running - Remote Start
        # Running - Two Wire Start
        # Stopped - Alarm


        ### Alarm Log
        # Low Oil Pressure
        # High Engine Temperature
        # Overcrank
        # Overspeed
        # RPM Sensor Loss
        # Underspeed
        # Underfrequency
        # Wiring Error
        # Undervoltage
        # Overvoltage
        # Internal Fault
        # Firmware Error
        # Stepper Overcurrent
        # Fuse Problem
        # Ruptured Basin
        # Canbus Error

        ####Warning Displays
        # Low Battery
        # Maintenance Periods
        # Exercise Error
        # Battery Problem
        # Charger Warning
        # Charger Missing AC
        # Overload Cooldown
        # USB Warning
        # Download Failure
        # FIRMWARE ERROR-9

        # Service Schedule log and Start/Stop Log are 16 chars long
        # error log is 20 chars log
        if len(Value) < 16:
            return ""

        if len(Value) > 20:
            return ""

        TempVal = Value[4:6]
        Min = int(TempVal, 16)
        if Min >59:                     # validate minute
            return ""

        TempVal = Value[6:8]
        Hour = int(TempVal, 16)
        if Hour > 23:                   # validate hour
            return ""

        TempVal = Value[8:10]
        Month = int(TempVal, 16)
        if Month == 0 or Month > 12:    # validate month
            return ""

        TempVal = Value[14:16]
        Day = int(TempVal, 16)
        if Day == 0 or Day > 31:        # validate day
            return ""

        TempVal = Value[12:14]
        Year = int(TempVal, 16)         # year

        TempVal = Value[0:2]
        LogCode = int(TempVal, 16)

        # Get the readable string, if we have one
        LogStr = LogDecoder.get(LogCode, "Unknown 0x%02X" % LogCode)

        # This is a numeric value that increments for each new log entry
        TempVal = Value[2:4]
        EntryNumber = int(TempVal, 16)

        # Unknown Value, likely internal housekeeping of controller
        TempVal = Value[10:12]
        LastVal = int(TempVal, 16)

        RetStr = "%02d/%02d/%02d %02d:%02d %s " % (Month,Day,Year,Hour,Min, LogStr)
        if len(Value) > 16:
            TempVal = Value[16:20]
            AlarmCode = int(TempVal,16)
            RetStr += ": Alarm Code: %04d" % AlarmCode
        return RetStr

    #------------------- GeneratorDevice::GetAlarmInfo -----------------
    # Read file alarm file and get more info on alarm if we have it
    # passes ErrorCode as string of hex values
    def GetAlarmInfo(self, ErrorCode):

        try:
            with open(self.AlarmFile,"r") as AlarmFile:     #opens file

                for line in AlarmFile:
                    line = line.rstrip()                   # remove newline at end and trailing whitespace
                    line = line.lstrip()                   # remove any leading whitespace
                    if not len(line):
                        continue
                    if line[0] == "#":              # comment?
                        continue
                    Items = line.split("!")
                    if len(Items) != 5:
                        continue
                    if Items[0] == str(int(ErrorCode,16)):
                        outstr =  Items[2] + ", Error Code: " + Items[0] + "\n" + "    Description: " + Items[3] + "\n" + "    Additional Info: " + Items[4] + "\n"
                        return outstr

        except Exception, e1:
            self.LogError("Error in  GetAlarmInfo " + str(e1))

        return "Error Code Unknown: " + ErrorCode + "\n"

    #------------ GeneratorDevice::GetVersions --------------------------------------
    def GetVersions(self):

        Value = self.GetRegisterValueFromList("002a")
        if len(Value) != 4:
            return ""
        RegVal = int(Value, 16)

        IntTemp = RegVal & 0xff         # low byte is firmware version
        FloatTemp = IntTemp / 100.0
        FirmwareVersion = "V%2.2f" % FloatTemp     #

        IntTemp = RegVal >> 8           # high byte is firmware version
        FloatTemp = IntTemp / 100.0
        HardwareVersion = "V%2.2f" % FloatTemp     #

        return "Firmware : %s, Hardware : %s" % (FirmwareVersion, HardwareVersion)

     #------------ GeneratorDevice::GetTransferStatus --------------------------------------
    def GetTransferStatus(self):

        if not self.EvolutionController:
            Register = "UNK"        # Nexus
        else:
            Register = "0053"       # Evolution

        Value = self.GetRegisterValueFromList(Register)
        if len(Value) != 4:
            return "Unknown"
        RegVal = int(Value, 16)

        if self.BitIsEqual(RegVal, 0x01, 0x01):
            return "Generator"
        else:
            return "Utility"

    ##------------ GeneratorDevice::GetAlarmState --------------------------------------
    def GetAlarmState(self):

        DigitalInputs_LC = {    #0x01: "Manual",
                                #0x02: "Auto",
                                #0x04: "Two Wire Start",
                                0x08: "Wiring Error",
                                0x10: "Low Fuel Pressure",
                                0x20: "Low Coolant Level",
                                0x40: "Not Used",
                                0x80: "Low Oil Pressure"}
        # Air cooled
        DigitalInputs_AC = {    #0x01: "Manual",
                                #0x02: "Auto",
                                0x04: "No Used",
                                0x08: "Wiring Error",
                                0x10: "Not Used",
                                0x20: "High Temprature",
                                0x40: "Low Oil Pressure",
                                0x80: "Not Used"}

        if not self.EvolutionController:
            Register = "UNK"        # Nexus
        else:
            Register = "0057"       # Evolution

        # get the inputs registes
        Value = self.GetRegisterValueFromList("Register")
        if len(Value) != 4:
            return ""

        RegVal = int(Value, 16)

        if self.LiquidCooled:
            Lookup = DigitalInputs_LC
        else:
            Lookup = DigitalInputs_AC

        outvalue = ""
        counter = 0x01

        while counter <= 0x80:
            Name = Lookup.get(counter, "")
            if len(Name) and Name != "Not Used":
                if self.BitIsEqual(RegVal, counter, counter):
                    outvalue += Name + ", "
            counter = counter << 1

        # take of the last comma
        ret = outvalue.rsplit(",", 1)
        return ret[0]
    ##------------ GeneratorDevice::GetTwoWireStartState --------------------------------------
    def GetTwoWireStartState(self):

        if not self.LiquidCooled:
            return ""

        # get the inputs registes
        Value = self.GetRegisterValueFromList("0057")
        if len(Value) != 4:
            return ""

        RegVal = int(Value, 16)

        if self.BitIsEqual(RegVal, 0x04,0x04):
            return "Two Wire Start Active "
        else:
            return ""

    #------------ GeneratorDevice::GetDigitalValues --------------------------------------
    def GetDigitalValues(self, RegVal, LookUp):

        outvalue = ""
        counter = 0x01

        while counter <= 0x80:
            Name = LookUp.get(counter, "")
            if len(Name) and Name != "Not Used":
                if self.BitIsEqual(RegVal, counter, counter):
                    outvalue += "%s, " % Name
            counter = counter << 1

        # take of the last comma
        ret = outvalue.rsplit(",", 1)
        return ret[0]


    #------------ GeneratorDevice::GetDigitalOutputs --------------------------------------
    def GetDigitalOutputs(self):

        if not self.EvolutionController:
            Register = "UNK"        # Nexus
        else:
            Register = "0053"       # Evolution

        # Liquid cooled
        DigitalOutputs_LC = {   0x01: "Transfer Switch Activated",
                                0x02: "Cold Start",
                                0x04: "Starter On",
                                0x08: "Fuel Relay On",
                                0x10: "Battery Charger On",
                                0x20: "Alarm Active",
                                0x40: "Bosch Governor On",
                                0x80: "Air/Fuel Relay On"}
        # Air cooled
        DigitalOutputs_AC = {   0x01: "Transfer Switch Activated",
                                0x02: "Ignition On",
                                0x04: "Starter On",
                                0x08: "Fuel Relay On",
                                0x10: "Battery Charger On",
                                0x20: "Not Used",
                                0x40: "Not Used",
                                0x80: "Not Used"}

        Value = self.GetRegisterValueFromList(Register)
        if len(Value) != 4:
            return ""
        RegVal = int(Value, 16)

        if self.LiquidCooled:
            return self.GetDigitalValues(RegVal, DigitalOutputs_LC)
        else:
            return self.GetDigitalValues(RegVal, DigitalOutputs_AC)

    #------------ GeneratorDevice::GetEngineState --------------------------------------
    def GetEngineState(self, Reg0001Value = None):

        if Reg0001Value is None:
            Value = self.GetRegisterValueFromList("0001")
            if len(Value) != 8:
                return ""
            RegVal = int(Value, 16)
        else:
            RegVal = Reg0001Value

        # other values that are possible:
        # Running in Warning
        # Running in Alarm
        # Running Remote Start
        # Running Two Wire Start
        # Stopped Alarm
        # Stopped Warning
        # Cranking
        # Cranking Warning
        # Cranking Alarm
        if self.BitIsEqual(RegVal,   0x000F0000, 0x00040000):
            return "Exercising"
        elif self.BitIsEqual(RegVal, 0x000F0000, 0x00090000):
            return "Stopped"
        elif self.BitIsEqual(RegVal, 0x000F0000, 0x00020000):
            return "Starting"
        elif self.BitIsEqual(RegVal, 0x000F0000, 0x00050000):
            return "Cooling Down"
        elif self.BitIsEqual(RegVal, 0x000F0000, 0x00030000):
            return "Running"
        elif self.BitIsEqual(RegVal, 0x000F0000, 0x00080000):
            return "Stopped in Alarm"
        elif self.BitIsEqual(RegVal, 0x000F0000, 0x00000000):
            return "Off - Ready"
        else:
            return "UNKNOWN: %08x" % RegVal

     #------------ GeneratorDevice::GetSwitchState --------------------------------------
    def GetSwitchState(self):

        Value = self.GetRegisterValueFromList("0001")
        if len(Value) != 8:
            return ""
        RegVal = int(Value, 16)

        if self.BitIsEqual(RegVal, 0x0F, 0x00):
            return "Auto"
        elif self.BitIsEqual(RegVal, 0x0F, 0x7):
            return "Off"
        elif self.BitIsEqual(RegVal, 0x0F, 0x06):
            return "Manual"
        elif self.BitIsEqual(RegVal, 0x0F, 0x0F):
            return "Stopped Warning"
        elif self.BitIsEqual(RegVal, 0x0F, 0x08):
            return "Stopped Alarm"
        else:
            return "UNKNOWN %08x" % RegVal

    #------------ GeneratorDevice::GetDateTime -----------------------------------------
    def GetDateTime(self):

        #Generator Time Hi byte = hours, Lo byte = min
        Value = self.GetRegisterValueFromList("000e")
        if len(Value) != 4:
            return ""
        Hour = Value[:2]
        if int(Hour,16) > 23:
            return ""
        Minute = Value[2:]
        if int(Minute,16) >= 60:
            return ""
        # Hi byte = month, Lo byte = day of the month
        Value = self.GetRegisterValueFromList("000f")
        if len(Value) != 4:
            return ""
        Month = Value[:2]
        if int(Month,16) == 0 or int(Month,16) > 12:            # 1 - 12
            return ""
        DayOfMonth = Value[2:]
        if int(DayOfMonth,16) > 31 or int(DayOfMonth,16) == 0:  # 1 - 31
            return ""
        # Hi byte Day of Week 00=Sunday 01=Monday, Lo byte = last 2 digits of year
        Value = self.GetRegisterValueFromList("0010")
        if len(Value) != 4:
            return ""
        DayOfWeek = Value[:2]
        if int(DayOfWeek,16) > 7:
            return ""
        Year = Value[2:]
        if int(Year,16) < 16:
            return ""

        FullDate =self.DaysOfWeek.get(int(DayOfWeek,16),"INVALID") + " " + self.MonthsOfYear.get(int(Month,16),"INVALID")
        FullDate += " " + str(int(DayOfMonth,16)) + ", " + "20" + str(int(Year,16)) + " "
        FullDate += "%02d:%02d" %  (int(Hour,16), int(Minute,16))

        return FullDate

    #------------ GeneratorDevice::GetExerciseDuration --------------------------------------------
    def GetExerciseDuration(self):

        # get exercise time of day
        Value = self.GetRegisterValueFromList("023e")
        if len(Value) != 4:
            return ""
        return "%d min" % int(Value,16)
    #------------ GeneratorDevice::GetExerciseTime --------------------------------------------
    def GetParsedExerciseTime(self):

        retstr = self.GetExerciseTime()
        if not len(retstr):
            return ""
        #should return this format: "Saturday 13:30 Quite Mode On"
        Items = retstr.split(" ")
        Time = Items[1]
        HoursMin = Items[1].split(":")
        retstr = Items[0] + "!" + HoursMin[0] + "!" + HoursMin[1] + "!" + Items[4]
        return retstr
    #------------ GeneratorDevice::GetExerciseTime --------------------------------------------
    def GetExerciseTime(self):

        # get exercise time of day
        Value = self.GetRegisterValueFromList("0005")
        if len(Value) != 4:
            return ""
        Hour = Value[:2]
        if int(Hour,16) > 23:
            return ""
        Minute = Value[2:]
        if int(Minute,16) >= 60:
            return ""
        # Get exercise day of week
        Value = self.GetRegisterValueFromList("0006")
        if len(Value) != 4:
            return ""
        DayOfWeek = Value[:2]       # Mon = 1
        if int(DayOfWeek,16) > 7:
            return ""

        Type = Value[2:]    # Quite Mode 00=no 01=yes This value may be weekly, bi weekly or monthly 01=weekly

        ExerciseTime =  self.DaysOfWeek.get(int(DayOfWeek,16),"") + " "
        ExerciseTime += "%02d:%02d" %  (int(Hour,16), int(Minute,16))
        if Type == "00":
            ExerciseTime += " Quite Mode Off"
        elif Type == "01":
            ExerciseTime += " Quite Mode On"
        else:
            ExerciseTime += " Quite Mode Unknown"

        return ExerciseTime

    #------------ GeneratorDevice::GetUnknownSensor2-------------------------------------
    # Note: this value only appears to update if the engine is running
    def GetUnknownSensor2(self):

        EngineState = self.GetEngineState()
        # report null if engine is not running
        if "Stopped" in EngineState or "Off" in EngineState:
            return ""

        # get value
        Value = self.GetRegisterValueFromList("0058")
        if len(Value) != 4:
            return ""

        IntTemp = int(Value,16)
        FloatTemp = IntTemp / 10.0
        SensorValue = "%3.1f F" % FloatTemp     #don't know the weighted value so may need to remove the decimal place

        return SensorValue

    #------------ GeneratorDevice::GetUnknownSensor1-------------------------------------
    def GetUnknownSensor1(self):

        # get value
        Value = self.GetRegisterValueFromList("003c")
        if len(Value) != 4:
            return ""

        IntTemp = int(Value,16)
        FloatTemp = IntTemp / 10.0
        SensorValue = "%2.1f" % FloatTemp   # don't know the weighted value so may need to remove the decimal place

        return SensorValue

    #------------ GeneratorDevice::GetUnknownSensor3-------------------------------------
    def GetUnknownSensor3(self):

        # get value
        Value = self.GetRegisterValueFromList("005d")
        if len(Value) != 4:
            return ""

        IntTemp = int(Value,16)
        SensorValue = "%d" % IntTemp   #

        return SensorValue

    #------------ GeneratorDevice::GetUnknownSensor4-------------------------------------
    def GetUnknownSensor4(self):

        # get value
        Value = self.GetRegisterValueFromList("05ed")
        if len(Value) != 4:
            return ""

        IntTemp = int(Value,16)
        SensorValue = "%d" % IntTemp   #

        return SensorValue

    #------------ GeneratorDevice::GetRPM --------------------------------------------
    def GetRPM(self):

        # get RPM
        Value = self.GetRegisterValueFromList("0007")
        if len(Value) != 4:
            return ""

        RPMValue = "%5d" % int(Value,16)
        return RPMValue

    #------------ GeneratorDevice::GetFrequency ---------------------------------------
    def GetFrequency(self):

        # get Frequency
        Value = self.GetRegisterValueFromList("0008")
        if len(Value) != 4:
            return ""

        IntTemp = int(Value,16)
        if self.EvolutionController:
            FloatTemp = IntTemp / 10.0      # Evolution
        else:
            FloatTemp = IntTemp / 1.0       # Nexus
        FreqValue = "%2.1f Hz" % FloatTemp

        return FreqValue

    #------------ GeneratorDevice::GetVoltageOutput --------------------------
    def GetVoltageOutput(self):

        # get Battery Charging Voltage
        Value = self.GetRegisterValueFromList("0012")
        if len(Value) != 4:
            return ""

        VolatageValue = "%dV" % int(Value,16)

        return VolatageValue

    #------------ GeneratorDevice::GetThresholdVoltage --------------------------
    def GetThresholdVoltage(self):

        # get Utility Voltage Threshold
        Value = self.GetRegisterValueFromList("0011")
        if len(Value) != 4:
            return ""
        ThresholdVoltage = int(Value,16)

        # get Utility Voltage Pickup Voltage
        Value = self.GetRegisterValueFromList("023b")
        if len(Value) != 4:
            return ""
        PickupVoltage = int(Value,16)

        # Note: we do not put a default value here because we want to know if
        # we are reading zeros for either of these values and this returns
        # a string to the user interface
        return "Low Voltage: %dV, Pickup Voltage: %dV" % (ThresholdVoltage, PickupVoltage)

    #------------ GeneratorDevice::GetUtilityVoltage --------------------------
    def GetUtilityVoltage(self):

        # get Battery Charging Voltage
        Value = self.GetRegisterValueFromList("0009")
        if len(Value) != 4:
            return ""

        VolatageValue = "%dV" % int(Value,16)

        return VolatageValue

    #------------ GeneratorDevice::GetBatteryVoltage -------------------------
    def GetBatteryVoltage(self):

        # get Battery Charging Voltage
        Value = self.GetRegisterValueFromList("000a")
        if len(Value) != 4:
            return ""

        IntTemp = int(Value,16)
        FloatTemp = IntTemp / 10.0
        VoltageValue = "%2.1fV" % FloatTemp

        return VoltageValue

    #------------ GeneratorDevice::GetBatteryStatus -------------------------
    def GetBatteryStatus(self):

        if not self.EvolutionController:
            Register = "UNK"        # Nexus
        else:
            Register = "0053"       # Evolution

        # get Battery Charging Voltage
        Value = self.GetRegisterValueFromList(Register)
        if len(Value) != 4:
            return "Unknown"

        Outputs = int(Value,16)

        if self.BitIsEqual(Outputs, 0x10, 0x10):
            return "Charging"
        else:
            return "Not Charging"

    #------------ GeneratorDevice::GetBaseStatus ------------------------------------
    def GetBaseStatus(self):

        if self.GeneratorInAlarm:
            return "ALARM"

        Value = self.GetEngineState()
        if "Exercising" in Value:
            return "EXERCISING"
        elif "Running" in Value:
            return "RUNNING"
        else:
            return "READY"

    #------------ GeneratorDevice::GetServiceInfo ------------------------------------
    def GetServiceInfo(self):

        # get Hours until next service
        Value = self.GetRegisterValueFromList("001a")
        if len(Value) != 4:
            return ""
        ServiceValue = "Next service in %d hours" % int(Value,16)
        return ServiceValue

    #------------ GeneratorDevice::GetRunTimes ----------------------------------------
    def GetRunTimes(self):

        # get total hours running
        Value = self.GetRegisterValueFromList("000c")
        if len(Value) != 4:
            return ""

        TotalRunTime = int(Value,16)

        # removed since this does not appear to be accurate
        # get total exercise hours
        #Value = self.GetRegisterValueFromList("0000")
        #if len(Value) != 4:
        #    return ""

        #ExerciseTime = int(Value,16)


        #BackUpHours = TotalRunTime - ExerciseTime

        #RunTimes = "Total Run Hours: %d, Backup: %d, Exercise: %d " % (TotalRunTime, BackUpHours,  ExerciseTime)
        RunTimes = "Total Run Hours: %d " % (TotalRunTime)

        return RunTimes

   #-------------GeneratorDevice::GetSystemHealth--------------------------------
    #   returns the health of the monitor program
    def GetSystemHealth(self):

        outstr = ""
        if not self.AreThreadsAlive():
            outstr += " Threads are dead. "
        if  not self.CommunicationsActive:
            outstr += "Not receiving data. "

        if len(outstr) == 0:
            outstr = "OK"
        return outstr

    #----------  GeneratorDevice::DebugThread-------------------------------------
    def DebugThread(self):

        if not self.EnableDebug:
            return
        msgbody = "\n"
        while True:
            if len(self.RegistersUnderTestData):
                msgbody = self.RegistersUnderTestData
                self.RegistersUnderTestData = ""
            else:
                msgbody += "Nothing Changed"
            msgbody += "\n\n"
            count = 0
            for Register, Value in self.RegistersUnderTest.items():
                msgbody += self.printToScreen("%s:%s" % (Register, Value), True)

            self.mail.sendEmail("Register Under Test", msgbody)
            msgbody = ""

            time.sleep(60*10)

    #----------  GeneratorDevice::ComWatchDog-------------------------------------
    #----------  monitors receive data status to make sure we are still communicating
    def ComWatchDog(self):

        self.CommunicationsActive = False
        LastRxPacketCount = self.Slave.RxPacketCount
        while True:

            if LastRxPacketCount == self.Slave.RxPacketCount:
                self.CommunicationsActive = False
            else:
                self.CommunicationsActive = True
                LastRxPacketCount = self.Slave.RxPacketCount
            time.sleep(5)

    #---------- GeneratorDevice:: AreThreadsAlive----------------------------------
    # ret true if all threads are alive
    def AreThreadsAlive(self):

        for t in self.ThreadList:
            if not t.is_alive():
                return False
        return True

     #---------- GeneratorDevice::GetDeadThreadName----------------------------------
    # ret true if all threads are alive
    def GetDeadThreadName(self):

        RetStr = ""
        for t in self.ThreadList:
            if not t.is_alive():
                RetStr += t.name + " "

        if RetStr == "":
            RetStr = "None"

        return RetStr

    #----------  GeneratorDevice::SocketWorkThread-------------------------------------
    #  This thread spawns for each connection established by a client
    #  in InterfaceServerThread
    def SocketWorkThread(self, conn):

        try:

            conn.settimeout(2)   # only blok on recv for a small amount of time

            statusstr = ""
            if self.GeneratorInAlarm:
                statusstr += "CRITICAL: System in alarm! "
            HealthStr = self.GetSystemHealth()
            if HealthStr != "OK":
                statusstr += "WARNING: " + HealthStr
            if statusstr == "":
                statusstr = "OK "

            conn.sendall(statusstr + ": "+ self.GetSwitchState() + ", " + self.GetEngineState())

            while True:
                try:
                    data = conn.recv(1024)

                    if(data.lower().startswith( 'generator:' )):
                        outstr = self.ProcessCommand(data, True)
                        conn.sendall(outstr)
                    else:
                        self.ConnectionList.remove(conn)
                        conn.close()
                        break
                except socket.timeout:
                    continue
                except socket.error as msg:
                    self.ConnectionList.remove(conn)
                    conn.close()
                    break

        except socket.error as msg:
            self.ConnectionList.remove(conn)
            conn.close()

        # end SocketWorkThread

    #----------  interface for heartbeat server thread -------------
    def InterfaceServerThread(self):

        #create an INET, STREAMing socket
        self.ServerSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # set some socket options so we can resuse the port
        self.ServerSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        #bind the socket to a host, and a port
        self.ServerSocket.bind(('', self.ServerSocketPort))
        #become a server socket
        self.ServerSocket.listen(5)

        #wait to accept a connection - blocking call
        while True:
            try:
                conn, addr = self.ServerSocket.accept()
                #self.printToScreen( 'Connected with ' + addr[0] + ':' + str(addr[1]))
                conn.settimeout(0.5)
                self.ConnectionList.append(conn)
                SocketThread = threading.Thread(target=self.SocketWorkThread, args = (conn,), name = "SocketWorkThread")
                SocketThread.daemon = True
                SocketThread.start()       # start server thread
            except Exception, e1:
                self.LogError("Excpetion in InterfaceServerThread" + str(e1))
                time.sleep(0.5)
                continue

        self.ServerSocket.close()
        #
    #---------------------GeneratorDevice::FatalError------------------------
    def LogError(self, Message):
        self.log.error(Message)
    #---------------------GeneratorDevice::FatalError------------------------
    def FatalError(self, Message):

        self.log.error(Message)
        raise Exception(Message)

    #---------------------GeneratorDevice::Close------------------------
    def Close(self):

        if self.MailInit:
            self.mail.sendEmail("Generator Monitor Stopping at " + self.SiteName, "Generator Monitor Stopping at " + self.SiteName )

        for item in self.ConnectionList:
            try:
                item.close()
            except:
                continue
            self.ConnectionList.remove(item)

        if(self.ServerSocket):
            self.ServerSocket.shutdown(socket.SHUT_RDWR)
            self.ServerSocket.close()

        if self.SerialInit:
            self.Slave.Close()

    #------------ GeneratorDevice::BitIsEqual -----------------------------------------
    def BitIsEqual(self, value, mask, bits):

        newval = value & mask
        if (newval == bits):
            return True
        else:
            return False

    #------------ GeneratorDevice::printToScreen --------------------------------------------
    def printToScreen(self, msgstr, outstr = False, nonewline = False, spacer = False):

        if spacer:
            MessageStr = "    {0}"
        else:
            MessageStr = "{0}"

        if not nonewline:
            MessageStr += "\n"

        if outstr == False:
            if self.bDisplayOutput:
                print MessageStr.format(msgstr),
            return ""
        else:
            newtpl = MessageStr.format(msgstr),
            return newtpl[0]

        # end printToScreen

#----------  Signal Handler ------------------------------------------
def signal_handler(signal, frame):


    sys.exit(0)

    # end signal_handler

#----------  print hex values  ---------------------------------------------
def printHexValues( buffer, separator1, separator2):

    # print in hex
    if(len(buffer) == 0):   # don't print if there is no data to print
        return

    new_str =  separator1
    for i in buffer:
        new_str += "%02x " % i

    new_str += separator2
    self.printToScreen (new_str)

#------------------- Command-line interface for monitor -----------------#
if __name__=='__main__': # usage SerialTest.py [baud_rate]


    # Set the signal handler
    signal.signal(signal.SIGINT, signal_handler)


    #Starting serial connection
    MyGen = GeneratorDevice()

    while True:
        time.sleep(1)


