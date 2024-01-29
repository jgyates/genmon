#!/usr/bin/env python
# ------------------------------------------------------------
#    FILE: modbusdump.py
# PURPOSE:
#
#  AUTHOR: Jason G Yates
#    DATE: 23-Apr-2018
# Free software. Use at your own risk.
# MODIFICATIONS:
# ------------------------------------------------------------


import getopt
import os
import sys

# Adds higher directory to python modules path.
sys.path.append(os.path.dirname(sys.path[0]))  

try:
    from genmonlib.mymodbus import ModbusProtocol
except Exception as e1:
    print("\n\nThis program is used for the testing of modbus registers.")

    managedfile = "/usr/lib/python" + str(sys.version_info.major) + "." + str(sys.version_info.minor) + "/EXTERNALLY-MANAGED"
    if os.path.isfile(managedfile):
        print("\n\nYou appear to be running in a managed python environemnt. To run this program see this page: ")
        print("\n\n  https://github.com/jgyates/genmon/wiki/Appendix-S---Working-in-a-Managed-Python-Environment\n")
    else:
        print("\nThe required python libraries are not installed. You must run the setup script first.\n")
        print("\n\n   https://github.com/jgyates/genmon/wiki/3.3--Setup-genmon-software")
    
    print("\n\nError: " + str(e1))
    sys.exit(2)

# ------------ RegisterResults --------------------------------------------------
def RegisterResults(Register, Value, IsCoil = False, IsInput = False):

    print(Register + ":" + Value)
    return True


# ------------ TestAllAddresses -------------------------------------------------
def TestAllAddresses():

    try:
        if not useTCP:
            modbus = ModbusProtocol(
                updatecallback=RegisterResults,
                address=0,
                name=device,
                rate=baudrate,
                Parity=parity,
                OnePointFiveStopBits=OnePointFiveStopBits,
            )
        else:
            modbus = ModbusProtocol(
                updatecallback=RegisterResults,
                address=modbusaddress,
                host=hostIP,
                port=TCPport,
                modbustcp=ModbusTCP,
            )
    except Exception as e1:
        print("Test all: Error opening serial device...: " + str(e1))
        return False

    try:
        for Address in range(0, 0x100):
            modbus.Address = Address
            print("Testing modbus address %02x" % Address)
            for Reg in range(startregister, endregister):
                RegStr = "%04x" % Reg
                modbus.ProcessTransaction(RegStr, 1)

        DisplayComErrors(modbus)
    except Exception as e1:
        print("Error reading device: " + str(e1))
        return False

    return True


# ----------------ModbusWrite----------------------------------------------------
def ModbusWrite():
    try:
        try:
            if not useTCP:
                modbus = ModbusProtocol(
                    updatecallback=RegisterResults,
                    address=modbusaddress,
                    name=device,
                    rate=baudrate,
                    Parity=parity,
                    OnePointFiveStopBits=OnePointFiveStopBits,
                )
            else:
                modbus = ModbusProtocol(
                    updatecallback=RegisterResults,
                    address=modbusaddress,
                    host=hostIP,
                    port=TCPport,
                    modbustcp=ModbusTCP,
                )
        except Exception as e1:
            print("Test all: Error opening serial device...: " + str(e1))
            return False

        LowByte = writevalue & 0x00FF
        HighByte = writevalue >> 8
        Data = []
        Data.append(HighByte)  # Value for register (High byte)
        Data.append(LowByte)  # Value for register (Low byte)

        RegStr = "%04x" % startregister
        modbus.ProcessMasterSlaveWriteTransaction(RegStr, len(Data) / 2, Data)
        DisplayComErrors(modbus)
    except Exception as e1:
        print("Error write device: " + str(e1))
        return False
    return True


# ----------------DisplayComErrors-----------------------------------------------
def DisplayComErrors(modbusdevice):

    try:
        print("\n")
        if modbusdevice.ModbusException != 0:
            print("Modbus Exception(s) detected: %d" % modbusdevice.ModbusException)
            if modbusdevice.ExcepFunction != 0:
                print("   Function: %d" % modbusdevice.ExcepFunction)
            if modbusdevice.ExcepAddress != 0:
                print("   Address: %d" % modbusdevice.ExcepAddress)
            if modbusdevice.ExcepData != 0:
                print("   Data: %d" % modbusdevice.ExcepData)
            if modbusdevice.ExcepSlave != 0:
                print("   Slave: %d" % modbusdevice.ExcepSlave)
            if modbusdevice.ExcepAck != 0:
                print("   ACK: %d" % modbusdevice.ExcepAck)
            if modbusdevice.ExcepBusy != 0:
                print("   Busy: %d" % modbusdevice.ExcepBusy)
            if modbusdevice.ExcepNack != 0:
                print("   NACK: %d" % modbusdevice.ExcepNack)
            if modbusdevice.ExcepMemPe != 0:
                print("   Mem PE: %d" % modbusdevice.ExcepMemPe)
            if modbusdevice.ExcepGateway != 0:
                print("   Gateway: %d" % modbusdevice.ExcepGateway)
            if modbusdevice.ExcepGateWayTg != 0:
                print("   GatewayTE: %d" % modbusdevice.ExcepGateWayTg)
        if modbusdevice.CrcError:
            print("Modbus CRC Error(s) detected: %d" % modbusdevice.CrcError)
        if modbusdevice.ComTimoutError:
            print("Modbus Timeout Error(s) detected: %d" % modbusdevice.ComTimoutError)
        if modbusdevice.ComValidationError:
            print(
                "Modbus Validation Error(s) detected: %d"
                % modbusdevice.ComValidationError
            )

    except Exception as e1:
        print("Error in  DisplayComErrors: " + str(e1))


# ------------------- Command-line interface for monitor -----------------------#
if __name__ == "__main__":  #

    device = None
    baudrate = None
    startregister = None
    endregister = None
    modbusaddress = None
    parity = None
    stopbits = None
    writevalue = None
    useTCP = False
    hostIP = None
    TCPport = None
    ModbusTCP = False
    UseFC4 = False
    UseCoils = False

    HelpStr = "\npython3 mobusdump.py -r <Baud Rate> -p <serial port> -a <modbus address to query> -s <start modbus register>  -e <end modbus register>\n"
    HelpStr += "\n   Example: python3 modbusdump.py -r 9600 -p /dev/serial0 -a 9d -s 5 -e 100 \n"
    HelpStr += "\n   Example: python3 modbusdump.py -i 192.168.1.10 -t 9988 -a 9d -s 5 -e 100 \n"
    HelpStr += "\n"
    HelpStr += "\n      -r  Baud rate of serial port (9600, 115300, etc)"
    HelpStr += "\n      -p  Operating System device name of the serail port (/dev/serial0)"
    HelpStr += "\n      -a  Modbus address to query in hexidecimal, 0 - ff (e.g. 9d, 10, ff) or 'all' to probe all addresses"
    HelpStr += "\n      -s  Starting modbus register to read (decimal number)"
    HelpStr += "\n      -e  Ending modbus register to read (decimal number, must be greater than start register)"
    HelpStr += "\n      -b  Stop bits. If omitted 1 stop bit, if present use 1.5 stop bits"
    HelpStr += "\n      -x  Omit for no parity. -x 1 for odd parity, -x 2 for even parity"
    HelpStr += "\n      -w  write this value to register instead of read. Start register is used as register"
    HelpStr += "\n      -c  read coils (bits) instead of holding register"
    HelpStr += "\n      -i  IP address if modbus over TCP is used"
    HelpStr += "\n      -t  TCP port if modbus over TCP is used"
    HelpStr += "\n      -m  Use Modbus TCP, if omitted and IP and port provided then use Modbus RTU over TCP"
    HelpStr += "\n      -f  use modbus function 4 instead of function 3 to read input registers instead of holding registers"
    HelpStr += "\n \n"

    try:
        opts, args = getopt.getopt(
            sys.argv[1:],
            "cfmbhr:p:s:e:a:x:w:i:t:",
            [
                "rate=",
                "port=",
                "start=",
                "end=",
                "address=",
                "parity=",
                "write=",
                "ip=",
                "tcpport=",
            ],
        )
    except getopt.GetoptError:
        print(HelpStr)
        sys.exit(2)

    try:
        for opt, arg in opts:
            if opt == "-h":
                print(HelpStr)
                sys.exit()
            elif opt in ("-a", "--address"):
                try:
                    modbusaddress = int(arg, 16)
                    print("Address is : %x" % modbusaddress)
                except:
                    try:
                        if arg.lower() == "all":
                            modbusaddress = "all"
                            print("Address is : %s" % arg)
                        else:
                            print("Error parsing modbus address: %s" % modbusaddress)
                    except:
                        print("Error parsing modbus address: %s" % modbusaddress)
            elif opt in ("-p", "--port"):
                device = arg
                print("Port is : %s" % device)
            elif opt in ("-r", "--rate"):
                baudrate = int(arg)
                print("Baud Rate : " + str(baudrate))
            elif opt in ("-s", "--start"):
                startregister = int(arg)
                print("Start Register : " + str(startregister))
            elif opt in ("-e", "--end"):
                endregister = int(arg)
                print("End Register : " + str(endregister))
            elif opt in ("-x", "--parity"):
                parity = int(arg)
                print("Parity : " + str(parity))
            elif opt in ("-b", "--stopbits"):
                stopbits = True
                print("1.5 Stop Bits : " + str(stopbits))
            elif opt in ("-w", "--write"):
                writevalue = int(arg, 16)
            elif opt in ("-i", "--ip"):
                hostIP = arg
                print("IP Address : " + hostIP)
            elif opt in ("-t", "--tcpport"):
                TCPport = int(arg)
                print("TCP Port : %d" % TCPport)
            elif opt in ("-m", "--modbustcp"):
                ModbusTCP = True
                print("Use Modbus TCP protocol")
            elif opt in ("-f", "--function4"):
                UseFC4 = True
                print("Use Modbus Function 4 instead of 3")
            elif opt in ("-c", "--coil"):
                UseCoils = True
                print("Reading Coil Values")

    except Exception as e1:
        print("\nError parsing command line: " + str(e1) + "\n")
        print(HelpStr)
        sys.exit(2)

    if TCPport != None and hostIP != None:
        useTCP = True
        print("Using serial over TCP.")
    elif (
        device == None
        or baudrate == None
        or startregister == None
        or modbusaddress == None
    ):
        print(HelpStr)
        sys.exit(2)
    if writevalue == None:
        if endregister == None or startregister > endregister:
            print(HelpStr)
            sys.exit(2)
    elif UseCoils:
        print("\nCoil reading and writing flags are not compatible.\n")
        print(HelpStr)
        sys.exit(2)

    if isinstance(modbusaddress, str) and modbusaddress.lower() != "all":
        print("Invalid modbus address parameter: %s" % modbusaddress)
        print(HelpStr)
        sys.exit(2)

    if isinstance(modbusaddress, int) and (modbusaddress > 255 or modbusaddress < 0):
        print("Invalid modbus address: %02x" % modbusaddress)
        print(HelpStr)
        sys.exit(2)
    

    if not stopbits == None:
        OnePointFiveStopBits = True
    else:
        OnePointFiveStopBits = False

    if not parity == None:
        if not parity == 1 and not parity == 2:
            print(HelpStr)
            sys.exit(2)

    try:
        modbus = None

        if writevalue != None and modbusaddress != "all":
            if not ModbusWrite():
                sys.exit(2)

        elif modbusaddress != "all":

            try:
                if not useTCP:
                    modbus = ModbusProtocol(
                        updatecallback=RegisterResults,
                        address=modbusaddress,
                        name=device,
                        rate=baudrate,
                        Parity=parity,
                        OnePointFiveStopBits=OnePointFiveStopBits
                    )
                else:
                    modbus = ModbusProtocol(
                        updatecallback=RegisterResults,
                        address=modbusaddress,
                        host=hostIP,
                        port=TCPport,
                        modbustcp=ModbusTCP
                    )
            except Exception as e1:
                print("Error opening serial device...: " + str(e1))
                sys.exit(2)
            try:
                for Reg in range(startregister, endregister):
                    RegStr = "%04x" % Reg
                    modbus.ProcessTransaction(RegStr, 1, IsCoil = UseCoils, IsInput = UseFC4)
            except Exception as e1:
                print("Error reading device: " + str(e1))
                sys.exit(2)

            DisplayComErrors(modbus)
        else:
            if not TestAllAddresses():
                sys.exit(2)

    except Exception as e1:
        print("Error in main program: " + str(e1))
    print("Program Complete")
    sys.exit(1)
