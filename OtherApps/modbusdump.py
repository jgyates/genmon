#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: modbusdump.py
# PURPOSE:
#
#  AUTHOR: Jason G Yates
#    DATE: 23-Apr-2018
# Free software. Use at your own risk.
# MODIFICATIONS:
#------------------------------------------------------------


import sys, time, getopt, os

sys.path.append(os.path.dirname(sys.path[0]))   # Adds higher directory to python modules path.

try:
    from genmonlib.mymodbus import ModbusProtocol
except Exception as e1:
    print ("\n\nThis program is used for the testing of modbus registers.")
    print ("\n\nThis program requires the modules mymodbus.py and myserial.py to reside in the genmonlib directory.\n")
    print("\n\nError: " + str(e1))
    sys.exit(2)

#------------ RegisterResults --------------------------------------------------
def RegisterResults(Register, Value):

    print(Register + ":" + Value)

#------------------- Command-line interface for monitor -----------------------#
if __name__=='__main__': #

    device = None
    baudrate = None
    startregister = None
    endregister = None
    modbusaddress = None
    parity = None
    stopbits = None

    HelpStr = '\npython mobusdump.py -r <Baud Rate> -p <serial port> -a <modbus address to query> -s <start modbus register>  -e <end modbus register>\n'
    HelpStr += "\n   Example: python mobusdump.py -r 9600 -p /dev/serial0 -a 9d -s 5 -e 100 \n"
    HelpStr += "\n"
    HelpStr += "\n      -r  Baud rate of serial port (9600, 115300, etc)"
    HelpStr += "\n      -p  Operating System device name of the serail port (/dev/serial0)"
    HelpStr += "\n      -a  Modbus address to query in hexidecimal, 0 - ff. (e.g. 9d, 10, ff)"
    HelpStr += "\n      -s  Starting modbus register to read (decimal number)"
    HelpStr += "\n      -e  Ending modbus register to read (decimal number, must be greater than start register)"
    HelpStr += "\n      -b  Stop bits. If omitted 1 stop bit, if present use 1.5 stop bits"
    HelpStr += "\n      -x  Omit for no parity. -x 1 for odd parity, -x 2 for even parity"
    HelpStr += "\n \n"

    try:
        opts, args = getopt.getopt(sys.argv[1:],"bhr:p:s:e:a:x:",["rate=","port=","start=","end=","address=", "parity="])
    except getopt.GetoptError:
        print(HelpStr)
        sys.exit(2)

    try:
        for opt, arg in opts:
            if opt == '-h':
                print (HelpStr)
                sys.exit()
            elif opt in ("-a", "--address"):
                modbusaddress = int(arg,16)
                print ('Address is : %x' % modbusaddress)
            elif opt in ("-p", "--port"):
                device = arg
                print ('Port is : %s' % device)
            elif opt in ("-r", "--rate"):
                baudrate = int(arg)
                print ('Baud Rate : ' + str(baudrate))
            elif opt in ("-s", "--start"):
                startregister =  int(arg)
                print ('Start Register : ' + str(startregister))
            elif opt in ("-e", "--end"):
                endregister =  int(arg)
                print ('End Register : ' + str(endregister))
            elif opt in ("-x", "--parity"):
                parity =  int(arg)
                print ('Parity : ' + str(parity))
            elif opt in ("-b", "--stopbits"):
                stopbits =  True
                print ('1.5 Stop Bits : ' + str(stopbits))

    except Exception as e1:
        print (HelpStr)
        sys.exit(2)

    if device == None or baudrate == None or startregister == None or endregister == None or modbusaddress == None or startregister > endregister or modbusaddress > 255:
        print (HelpStr)
        sys.exit(2)

    if not stopbits == None:
        OnePointFiveStopBits = True
    else:
        OnePointFiveStopBits = False

    if not parity == None:
        if not parity == 1 and not parity == 2:
            print (HelpStr)
            sys.exit(2)


    modbus = None
    try:
        modbus = ModbusProtocol(updatecallback = RegisterResults, address = modbusaddress, name = device,
            rate = baudrate, Parity = parity, OnePointFiveStopBits = OnePointFiveStopBits)
        pass
    except Exception as e1:
        print( "Error opening serial device...: " + str(e1))
        sys.exit(2)
    try:
        for Reg in range(startregister , endregister):
            RegStr = "%04x" % Reg
            modbus.ProcessMasterSlaveTransaction(RegStr, 1)
    except Exception as e1:
        print("Error reading device: " + str(e1))
        sys.exit(2)

    print("Program Complete")
    sys.exit(1)
