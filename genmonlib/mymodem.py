#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: mymodem.py
# PURPOSE: module for using direct cellular comms for SMS via cellular modem
#
#  AUTHOR: Jason G Yates
#    DATE: 29-Aug-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

from __future__ import print_function       # For python 3.x compatibility with print function

import datetime, sys, collections, time, threading, re, os

from genmonlib.myserial import SerialDevice
from genmonlib.myconfig import MyConfig
from genmonlib.mysupport import MySupport
from genmonlib.mylog import SetupLogger
from genmonlib.mythread import MyThread
from genmonlib.program_defaults import ProgramDefaults

#------------ MyModem class ----------------------------------------------------
class MyModem(MySupport):
    def __init__(self,
            port = "/dev/ttyAMA0" ,
            rate = 115200,
            loglocation = ProgramDefaults.LogPath,
            log = None,
            localinit = False,
            ConfigFilePath = ProgramDefaults.ConfPath,
            recipient = None):
        super(MyModem, self).__init__()

        self.MessagesSent = 0
        self.Errors = 0
        self.SendActive = False
        self.ModemLock = threading.RLock()
        self.Sending = False
        self.SendQueue = []

        if ConfigFilePath == None:
            self.ConfigFilePath = ProgramDefaults.ConfPath
        else:
            self.ConfigFilePath = ConfigFilePath

        # log errors in this module to a file
        if localinit == True:
            self.configfile = "mymodem.conf"
        else:
            self.configfile = os.path.join(self.ConfigFilePath, "mymodem.conf")

        # log errors in this module to a file
        if log == None:
            self.log = SetupLogger("mymodem", os.path.join(loglocation, "mymodem.log"))
        else:
            self.log = log

        self.console = SetupLogger("mymodem_console", log_file = "", stream = True)

        try:
            self.config = MyConfig(filename = self.configfile, section = "MyModem", log = self.log)

            self.LogAtCommands = self.config.ReadValue('log_at_commands', return_type = bool, default = False)

            self.MessageLevel = self.config.ReadValue('message_level', default = 'error')

            self.Rate = self.config.ReadValue('rate', return_type = int, default = 115200)

            self.Port = self.config.ReadValue('port', default = "/dev/ttyAMA0")

            self.Recipient = self.config.ReadValue('recipient', default = recipient)

            self.ModemType = self.config.ReadValue('modem_type', default = "LTEPiHat")

        except Exception as e1:
            self.LogErrorLine("Error reading config file: " + str(e1))
            self.LogConsole("Error reading config file: " + str(e1))
            return

        if self.Recipient == None or not len(self.Recipient):
            self.LogErrorLine("Error invalid recipient")
            self.LogConsole("Error invalid recipient")

        if self.Port == None or not len(self.Port):
            self.LogErrorLine("Error invalid port")
            self.LogConsole("Error invalid port")
            return

        if self.Rate == None or self.Rate <= 0:
            self.LogErrorLine("Error invalid rate")
            self.LogConsole("Error invalid rate")
            return

        # rate * 10 bits then convert to MS
        self.CharacterTimeMS = (((1/ self.Rate) * 10)  *1000)

        self.InitComplete = False

        try:
            self.SerialDevice = SerialDevice(port, rate = rate, log = self.log, loglocation = loglocation)
            self.Threads = self.MergeDicts(self.Threads, self.SerialDevice.Threads)

            self.Threads["SendMessageThread"] = MyThread(self.SendMessageThread, Name = "SendMessageThread")

        except Exception as e1:
            self.LogErrorLine("Error opening serial device in MyModem: " + str(e1))

    #------------MyModem::SendMessageThread-------------------------------------
    def SendMessageThread(self):

        # once SendMessage is called messages are queued and then sent from this thread
        time.sleep(0.5)
        while True:
            try:
                self.SendActive = False
                if self.WaitForExit("SendMessageThread", 2 ):
                    return

                while self.SendQueue != []:
                    SendError = False

                    if not self.InitComplete:
                        if self.WaitForExit("SendMessageThread", 5 ):
                            return
                        else:
                            continue

                    self.SendActive = True
                    MessageItems = self.SendQueue.pop()
                    try:
                        if not (self.SendSMS(message = MessageItems[0], recipient = MessageItems[1] , msgtype = MessageItems[2])):
                            self.LogError("Error in SendMessageThread, SendSMS failed, retrying")
                            SendError = True
                    except Exception as e1:
                        # put the time back at the end of the queue
                        self.LogErrorLine("Error in SendMessageThread, retrying (2): " + str(e1))
                        SendError = True

                    if SendError:
                        self.SendQueue.insert(len(self.SendQueue),MessageItems)
                        self.SendActive = False
                        # sleep for 10 sec and try again
                        if self.WaitForExit("SendMessageThread", 10 ):
                            return
            except Exception as e1:
                self.LogErrorLine("Error in SendMessageThread: " + str(e1))

    #------------MyModem::SendMessage-------------------------------------------
    # msgtype must be one of "outage", "error", "warn", "info"
    def SendMessage(self, message = None, recipient = None, msgtype = "error"):

        try:
            self.SendQueue.insert(0,[message, recipient, msgtype])
            return True
        except Exception as e1:
            self.LogErrorLine("Error in SendMessage: " + str(e1))
            return False

    #------------------MyModem::MessagesPending---------------------------------
    def MessagesPending(self):

        return self.SendQueue != [] or self.SendActive

    #------------------MyModem::SendCommand-------------------------------------
    def SendATCommand(self, command, response = None, retries = 1, NoAddCRLF = False):

        try:

            if self.SerialDevice == None:
                self.LogError("Serial device is not open!")
                return False

            if not NoAddCRLF:
                command = str(command) + b"\r\n"
                if response != None:
                    response = str(response) + b"\r\n"
            else:
                command = str(command)
                if response != None:
                    response = str(response)
            with self.ModemLock:
                self.Sending = True
                self.SerialDevice.Flush()

                attempts = retries
                while  self.Sending and attempts >= 0:
                    self.SerialDevice.Write(command)
                    if self.LogAtCommands:
                        self.LogError("->" + command)
                    time.sleep(0.75)
                    if None != response:
                        SerialBuffer = self.SerialDevice.GetRxBufferAsString()

                        if self.LogAtCommands and len(SerialBuffer):
                            self.LogError("<-" + SerialBuffer)

                        if SerialBuffer.find("ERROR") >= 0:
                            self.Sending = False
                            self.LogError("Error returned SendATCommand: CMD: " + str(command))
                            return False

                        if SerialBuffer.find(response) >= 0:
                            self.Sending = False
                            attempts += 1

                    elif None == response:
                        self.Sending = False

                    if self.Sending:
                        time.sleep(0.5)
                        attempts = attempts - 1
                    else:
                        break

                return (attempts >= 0)

        except Exception as e1:
            self.LogErrorLine("Error in SendATCommand: " + "CMD: " + str(command) + " : "+ str(e1))
            return False

    #------------------MyModem::Send--------------------------------------------
    def SendSMS(self, message = None, recipient = None, msgtype = "error"):

        try:

            if recipient == None:
                recipient = self.Recipient

            if recipient == None or not len(recipient):
                self.LogError("Invalid recipient in SendSMS.")
                return False

            with self.ModemLock:
                # set default config
                if not self.SendATCommand("ATZ", "OK"):
                    self.LogError("Failed setting default config in MySMS:Send")
                    self.Errors += 1

                # set text message mode
                if not self.SendATCommand("AT+CMGF=1", "OK"):
                    self.LogError("Failed setting message mode in MySMS:Send")
                    self.Errors += 1
                    return False

                StartMessage = str("AT+CMGS=" + '"' + str(recipient) + '"' + "\r")
                if not self.SendATCommand(StartMessage, ">", retries = 0,  NoAddCRLF = True):
                    self.SendATCommand("\x1b" , "OK", retries = 1,  NoAddCRLF = True)
                    self.LogError("Failed sending CMGS in MySMS:Send")
                    self.Errors += 1
                    return False

                if not self.SendATCommand(str(message) + "\r" , ">", retries = 0,  NoAddCRLF = True):
                    self.SendATCommand("\x1b" , "OK", retries = 1,  NoAddCRLF = True)
                    self.LogError("Failed sending Message Body in MySMS:Send")
                    self.Errors += 1
                    return False

                if not self.SendATCommand("\x1a" , "OK", retries = 1,  NoAddCRLF = True):
                    self.SendATCommand("\x1b" , "OK", retries = 1,  NoAddCRLF = True)
                    self.LogError("Failed sending EOM in MySMS:Send")
                    self.Errors += 1
                    return False

                self.SendATCommand("AT", 'OK')
                self.MessagesSent += 1
            return True
        except Exception as e1:
            self.Errors += 1
            self.LogErrorLine("Error in MySMS:Send: " + str(e1))
            return False
    #------------------MyModem::GetQuotedString---------------------------------
    def GetQuotedString(self, InputString):

        try:
            quoted = re.compile('"[^"]*"')
            for value in quoted.findall(InputString):
                newline = "".join( c for c in value if  c not in '"' )
                return newline

            return None
        except Exception as e1:
            self.LogErrorLine("Error in GetQuotedString: " + str(InputString) + ": " + str(e1))
            return ""
    #------------------MyModem::GetNumbersFromString----------------------------
    def GetNumbersFromString(self, InputString):
        # return list of numbers
        try:
            return re.findall(r'\d+', InputString)
        except Exception as e1:
            self.LogErrorLine("Error in GetNumbersFromString: " + str(InputString) + ": " + str(e1))
            return []

    #------------------MyModem::GetItemsFromCommand-----------------------------
    def GetItemsFromCommand(self, InputString):

        try:
            ReturnString = InputString
            Index = ReturnString.find(":")
            if Index > 1 or len(ReturnString) < 2:
                ListItems = ReturnString[Index + 1 :].split(",")
                ListItems = map(str.strip, ListItems)
                return ListItems
            else:
                return [InputString.split('\r\n')[1].strip()]
        except Exception as e1:
            self.LogErrorLine("Error in GetItemsFromCommand: " + str(InputString) + ": " + str(e1))
            self.LogErrorLine("Input: " + str(InputString))
            return []

    #------------------MyModem::GetInfo-----------------------------------------
    def GetInfo(self, ReturnString = False):
        ModemInfo = collections.OrderedDict()
        try:
            with self.ModemLock:
                ModemInfo["Port"] = str(self.Port)
                ModemInfo["Rate"] = str(self.Rate)
                ModemInfo["Messages Sent"] = str(self.MessagesSent)
                ModemInfo["Errors"] = str(self.Errors)

                # get operator name
                if self.SendATCommand("AT+COPS?","OK" ):
                    Buffer = self.SerialDevice.GetRxBufferAsString()
                    ModemInfo["Carrier"] = self.GetQuotedString(Buffer.split('\r\n')[1])

                # AT+CIMI IMSI (International mobile subscriber identification)
                if self.SendATCommand("AT+CIMI","OK" ):
                    Buffer = self.SerialDevice.GetRxBufferAsString()
                    ReturnValue = self.GetItemsFromCommand(Buffer)
                    if len(ReturnValue):
                        ModemInfo["IMSI"] = ReturnValue[0]

                ## get SIM card state
                if self.SendATCommand("AT+UUICC?", "OK"):
                    Buffer = self.SerialDevice.GetRxBufferAsString()
                    ReturnValue = self.GetItemsFromCommand(Buffer)
                    if len(ReturnValue):
                        SIMType = self.GetNumbersFromString(ReturnValue[0])[0]
                        if SIMType == "0":
                            ModemInfo["SIM Type"] = "2G"
                        elif SIMType == "1":
                            ModemInfo["SIM Type"] = "3G or 4G"


                # name of manufacturer (AT+CGMI)
                if self.SendATCommand("AT+CGMI", "OK"):
                    Buffer = self.SerialDevice.GetRxBufferAsString()
                    ReturnValue = self.GetItemsFromCommand(Buffer)
                    if len(ReturnValue):
                        ModemInfo["Manufacturer"] = ReturnValue[0]

                # show module/model name
                if self.SendATCommand("AT+CGMM", "OK"):
                    Buffer = self.SerialDevice.GetRxBufferAsString()
                    ReturnValue = self.GetItemsFromCommand(Buffer)
                    if len(ReturnValue):
                        ModemInfo["Model"] = ReturnValue[0]

                # phone / modem info

                # IMEI number (International Mobile Equipment Identity) (AT+CGSN)
                if self.SendATCommand("AT+CGSN", "OK"):
                    Buffer = self.SerialDevice.GetRxBufferAsString()
                    ReturnValue = self.GetItemsFromCommand(Buffer)
                    if len(ReturnValue):
                        ModemInfo["IMEI"] = ReturnValue[0]

                # software version (AT+CGMR)
                if self.SendATCommand("AT+CGMR", "OK"):
                    Buffer = self.SerialDevice.GetRxBufferAsString()
                    ReturnValue = self.GetItemsFromCommand(Buffer)
                    if len(ReturnValue):
                        ModemInfo["Firmware Version"] = ReturnValue[0]

                ## subscriber info MSISDN (AT+CNUM)
                if self.SendATCommand("AT+CNUM", "OK"):
                    Buffer = self.SerialDevice.GetRxBufferAsString()
                    ReturnValue = self.GetItemsFromCommand(Buffer)
                    if len(ReturnValue) >= 2:
                        ModemInfo["MSISDN"] = self.GetQuotedString(ReturnValue[1])

                # mobile phone activity status (AT+CPAS),  returns "+CPAS: 0" where number is:
                #    0: ready (MT allows commands from DTE)
                #    1: unavailable (MT does not allow commands from
                #    2: unknown (MT is not guaranteed to respond to instructions)
                #    3: ringing (MT is ready for commands from DTE, but the ringer is active)
                #    4:callinprogress(MTisreadyforcommandsfromDTE,butacallisinprogress,e.g.callactive,
                #    hold, disconnecting)
                #    5:asleep(MEisunabletoprocesscommandsfromDTEbecauseitisinalowfunctionalitystate)
                if self.SendATCommand("AT+CPAS", "OK"):
                    Buffer = self.SerialDevice.GetRxBufferAsString()
                    NumberList = self.GetItemsFromCommand(Buffer)
                    if len(NumberList) >= 1:
                        Status = self.GetNumbersFromString(NumberList[0])[0]
                        if Status == "0":
                            ModemInfo["Status"] = "Ready"
                        elif Status == "1":
                            ModemInfo["Status"] = "Unavailable"
                        elif Status == "2":
                            ModemInfo["Status"] = "Unknown"
                        elif Status == "3":
                            ModemInfo["Status"] = "Ringing"
                        elif Status == "4":
                            ModemInfo["Status"] = "Call In Progress"
                        elif Status == "5":
                            ModemInfo["Status"] = "Asleep"
                        else:
                            ModemInfo["Status"] = "Unknown"

                # mobile network registration status (AT+CREG?) returns "+CREG: 0,0" or +CREG: n,stat
                #    <n>
                #    0 (default value and factory-programmed value): network registration URC disabled
                #    1: network registration URC +CREG: <stat> enabled
                #    2: network registration and location information URC +CREG: <stat>[,<lac>,<ci>[,<AcTStatus>]] enabled
                #    <stat>
                #    0: not registered, the MT is not currently searching a new operator to register to
                #    1: registered, home network
                #    2: not registered, but the MT is currently searching a new operator to register to
                #    3: registration denied
                #    4: unknown (e.g. out of GERAN/UTRAN/E-UTRAN coverage)
                #    5: registered, roaming
                #    6:registeredfor"SMSonly",homenetwork(applicableonlywhen<AcTStatus>indicates E-UTRAN)
                #    7:registeredfor"SMSonly",roaming(applicableonlywhen<AcTStatus>indicatesE-UTRAN)
                #    8: attached for emergency bearer services only
                #    9:registeredfor"CSFBnotpreferred",homenetwork(applicableonlywhen<AcTStatus> indicates E-UTRAN)
                #    10:registeredfor"CSFBnotpreferred",roaming(applicableonlywhen<AcTStatus>indicates E-UTRAN)

                ## AT+REG=2
                self.SendATCommand("AT+CREG=2", "OK")

                ## +CREG, +CEREG and +CGREG.
                if self.SendATCommand("AT+CREG?", "OK"):
                    Buffer = self.SerialDevice.GetRxBufferAsString()
                    NumberList = self.GetItemsFromCommand(Buffer)
                    if len(NumberList) >= 1:
                        if NumberList[0] == "0":
                            ModemInfo["Registration Status"] = "Disabled"
                        elif NumberList[0] == "1" or NumberList[0] == "2":
                            ModemInfo["Registration Status"] = "Enabled"
                    if len(NumberList) >= 2:
                        NetworkRegistrationLookup = {
                            "0" : "Not Registered, Not searching",
                            "1" : "Registered, Home network",
                            "2" : "Not Registered, Searching",
                            "3" : "Registration Denied",
                            "4" : "Unknown, Out of Coverage",
                            "5" : "Registered, Roaming",
                            "6" : "Registered, Home network, SMS Only",
                            "7" : "Registered, Roaming, SMS Only",
                            "8" : "Attached for Emergency Bearer Services Only",
                            "9" : "Registered, Home network, CSFB Not Preferred",
                            "10" : "Registered, Roaming, CSFB Not Preferred",
                        }

                        ModemInfo["Network Registration"] = NetworkRegistrationLookup.get(NumberList[1], "Unknown")

                    if len(NumberList) > 5:
                        NetworkTech ={
                            "0" : "GSM",                        # 2G
                            "1" : "GSM Compact",                # 2G
                            "2" : "UTRAN",                      # 3G
                            "3" : "GSM w/EGPRS",                # 2.5G
                            "4" : "UTRAN w/HSDPA",              # 3G
                            "5" : "UTRAN w/HSUPA",              # 3G
                            "6" : "UTRAN w/HSDPA and HSUPA",    # 3G
                            "7" : "E-UTRAN",                    # 4G
                            "255" : "Unknown"
                        }
                        ModemInfo["Cell Network Technology"] = NetworkTech.get(self.GetNumbersFromString(NumberList[4])[0], "Unknown")

                # radio signal strength (AT+CSQ), returns "+CSQ: 2,5"
                # first number is RSSI:
                #    The allowed range is 0-31 and 99. Remapped indication of the following parameters:
                #    the Received Signal Strength Indication (RSSI) in GSM RAT
                #    the Received Signal Code Power (RSCP) in UMTS RAT
                #    the Reference Signal Received Power (RSRP) in LTE RAT
                #    When the RF power level of the received signal is the highest possible, the value 31 is reported. When it is not known, not detectable or currently not available, 99 is returned.
                # second number is signal quality:
                #   The allowed range is 0-7 and 99. The information provided depends on the selected RAT:
                #   In 2G RAT CS dedicated and GPRS packet transfer mode indicates the BitErrorRate(BER)as
                #   specified in 3GPP TS 45.008 [148]
                #   In 2G RAT EGPRS packet transfer mode indicates the Mean BitErrorProbability(BEP) of a radio
                #   block. 3GPP TS 45.008 [148] specifies the range 0-31 for the Mean BEP which is mapped to
                #   the range 0-7 of <qual>
                #   In UMTS RAT indicates the Energy per Chip/Noise(ECN0) ratioin dB levels of the current cell.
                #   3GPP TS 25.133 [106] specifies the range 0-49 for EcN0 which is mapped to the range 0-7
                #   of <qual>
                #   In LTE RAT indicates the Reference Signal Received Quality(RSRQ). TS36.133[105] specifies
                #   the range 0-34 for RSRQ which is mapped to the range 0-7 of <qual>

                if self.SendATCommand("AT+CSQ", "OK"):
                    Buffer = self.SerialDevice.GetRxBufferAsString()
                    NumberList = self.GetItemsFromCommand(Buffer)

                    if len(NumberList) >= 2:
                        RSSIList = self.ParseRSSI(NumberList[0])
                        ModemInfo["RSSI"] = RSSIList[0] + " dBm" + ", " + RSSIList[1]
                        ModemInfo["Signal Quality"] = self.GetNumbersFromString(NumberList[1])[0]

                if self.SendATCommand("AT+CCLK?", "OK"):
                    Buffer = self.SerialDevice.GetRxBufferAsString()
                    if len(Buffer):
                        ModemInfo["Network Time"] = self.GetQuotedString(Buffer)


        except Exception as e1:
            self.LogErrorLine("Error in MyModem:GetInfo: " + str(e1))

        if ReturnString:
            return self.DictToString(ModemInfo)
        return ModemInfo
    #------------------MyModem::ParseRSSI-------------------------------------------
    def ParseRSSI(self, Value):

        RSSILookup = {
            "0" : ["-113", "Poor"],
            "1" : ["-111", "Poor"],
            "2" : ["-109", "Marginal"],
            "3" : ["-107", "Marginal"],
            "4" : ["-105", "Marginal"],
            "5" : ["-103", "Marginal"],
            "6" : ["-101", "Marginal"],
            "7" : ["-99", "Marginal"],
            "8" : ["-97", "Marginal"],
            "9" : ["-95", "Marginal"],
            "10" : ["-93", "OK"],
            "11" : ["-91", "OK"],
            "12" : ["-89", "OK"],
            "13" : ["-87", "OK"],
            "14" : ["-85", "OK"],
            "15" : ["-83", "Good"],
            "16" : ["-81", "Good"],
            "17" : ["-79", "Good"],
            "18" : ["-77", "Good"],
            "19" : ["-75", "Good"],
            "20" : ["-73", "Excellent"],
            "21" : ["-71", "Excellent"],
            "22" : ["-69", "Excellent"],
            "23" : ["-67", "Excellent"],
            "24" : ["-65", "Excellent"],
            "25" : ["-63", "Excellent"],
            "26" : ["-61", "Excellent"],
            "27" : ["-59", "Excellent"],
            "28" : ["-57", "Excellent"],
            "29" : ["-55", "Excellent"],
            "30" : ["-53", "Excellent"],
            "99" : ["Unknown", "Unknown"]
            }

        return RSSILookup.get(Value, ["Unknown", "Unknown"])

    #------------------MyModem::Close-------------------------------------------
    def Close(self):
        try:
            try:
                self.KillThread("SendMessageThread")
            except:
                pass
            try:
                self.SerialDevice.Close()
            except:
                pass
        except Exception as e1:
            self.LogErrorLine("Error Closing Modem: " + str(e1))


#---------------------------LTEPiHat class -------------------------------------
from subprocess import PIPE, Popen
try:
    import RPi.GPIO as GPIO
except Exception as e1:
    print("Unable to Import Library RPi.GPIO")
    sys.exit(1)

class LTEPiHat(MyModem):
    # https://github.com/mholling/rpirtscts is required
    #---------------------LTEPiHat::__init__------------------------------------
    def __init__(self,
        port = "/dev/ttyAMA0" ,
        rate=115200,
        loglocation = ProgramDefaults.LogPath,
        log = None,
        localinit = False,
        ConfigFilePath = ProgramDefaults.ConfPath,
        recipient = None):

        # call parent constructor
        super(LTEPiHat, self).__init__(port = port, rate = rate, loglocation = loglocation,
            log = log, localinit = localinit, ConfigFilePath = ConfigFilePath, recipient = recipient)

        if not self.InitHardware():
            self.LogError("Error starting device.")
            self.LogConsole("Error starting device.")
            return
        self.InitComplete = True

    #------------------LTEPiHat:InitHardware-------------------------------------
    def InitHardware(self):

        # NOTE: This function assumes the underlying hardware is the LTE Cat 1 Pi Hat
        # http://wiki.seeedstudio.com/LTE_Cat_1_Pi_HAT/

        try:
            self.power_pin = 29
            self.reset_pin = 31
            GPIO.setmode(GPIO.BOARD)
            GPIO.setwarnings(False)
            GPIO.setup(self.power_pin, GPIO.OUT) # Setup module power pin
            GPIO.setup(self.reset_pin, GPIO.OUT) # Setup module reset pin
            GPIO.output(self.power_pin, False)
            GPIO.output(self.reset_pin, False)

            return self.PowerUp()
        except Exception as e1:
            self.LogErrorLine("Error in LTEPiHat:InitHardware: " + str(e1))
            return False
    #------------------LTEPiHat::PowerDown-------------------------------------
    def PowerDown(self):

        self.LogConsole("Powering Down Modem...")
        GPIO.output(self.power_pin, True)
        self.DisableRTSCTS()
    #------------------LTEPiHat::TogglePower------------------------------------
    def TogglePower(self):

        GPIO.output(self.power_pin, True)
        time.sleep(1.5)
        GPIO.output(self.power_pin, False)

    #------------------LTEPiHat::PowerUp----------------------------------------
    def PowerUp(self):
        self.debug = False
        self.LogConsole( "Waking up...")
        self.TogglePower()
        if not self.EnableRTSCTS():
            self.LogConsole("Unable to Enable RTS/CTS")
            self.LogError("Unable to Enable RTS/CTS")
            return False
        count = 0
        while not self.SendATCommand("AT", 'OK'):
            count += 1
            if count > 7:
                self.LogConsole("Unable to power up Modem.")
                self.LogError("Unable to power up Modem.")
                return False
            else:
                time.sleep(1)
        return True

    #------------------LTEPiHat::EnableRTSCTS-----------------------------------
    def EnableRTSCTS(self):

        try:
            process = Popen(['rpirtscts', 'on'], stdout=PIPE)
            output, _error = process.communicate()
            if _error == None:
                return True
            else:
                self.LogError("Error running rpirtscts in EnableRTSCTS: " + str(_error) )
                return False
        except Exception as e1:
            self.LogErrorLine("Error in EnableRTSCTS: " + str(e1))
            self.LogError("Output: " + str(output))
            self.LogError("Error: " + str(_error))
            return False

    #------------------LTEPiHat::DisableRTSCTS----------------------------------
    def DisableRTSCTS(self):

        try:
            process = Popen(['rpirtscts', 'off'], stdout=PIPE)
            output, _error = process.communicate()
            if _error == None:
                return True
            else:
                self.LogError("Error running rpirtscts in DisableRTSCTS: " + str(_error) )
                return False
        except Exception as e1:
            self.LogErrorLine("Error in DisableRTSCTS: " + str(e1))
            self.LogError("Output: " + str(output))
            self.LogError("Error: " + str(_error))
            return False

    #------------------LTEPiHat::Close------------------------------------------
    def Close(self):
        try:
            try:
                super(LTEPiHat, self).Close()
            except:
                 pass
            try:
                self.PowerDown()
            except:
                pass
        except Exception as e1:
            self.LogErrorLine("Error Closing Modem: " + str(e1))
