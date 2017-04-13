#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: serialtest.py
# PURPOSE:
#
#  AUTHOR: Jason G Yates
#    DATE: 12-Apr-2017
# Free software. Use at your own risk.
# MODIFICATIONS:
#------------------------------------------------------------


import sys, time, serial


#------------ printToScreen --------------------------------------------
def printToScreen( msgstr):

    print "{0}\n".format(msgstr),
    no_op = 0
    # end printToScreen(msgstr):


#------------------- Open Serial Port -----------------#
def OpenSerialPort(name, rate):

    #Starting serial connection
    NewSerialPort = serial.Serial()
    NewSerialPort.port = name
    NewSerialPort.baudrate = rate
    NewSerialPort.bytesize = serial.EIGHTBITS     #number of bits per bytes
    NewSerialPort.parity = serial.PARITY_NONE     #set parity check: no parity
    NewSerialPort.stopbits = serial.STOPBITS_ONE  #number of stop bits
    NewSerialPort.timeout = 4                     #non-block read
    NewSerialPort.xonxoff = False                 #disable software flow control
    NewSerialPort.rtscts = False                  #disable hardware (RTS/CTS) flow control
    NewSerialPort.dsrdtr = False                  #disable hardware (DSR/DTR) flow control
    NewSerialPort.writeTimeout = 2                #timeout for write

    #Check if port failed to open
    if (NewSerialPort.isOpen() == False):
        try:
            NewSerialPort.open()
            printToScreen( "Serial port opened")
        except Exception, e:
            printToScreen( "error open serial port: " + str(e))
            return 0
    else:
        printToScreen( "Serial port already open???")
        return 0

    NewSerialPort.flushInput() #flush input buffer, discarding all its contents
    NewSerialPort.flushOutput()#flush output buffer, aborting current output

    return NewSerialPort

#------------------- Command-line interface for monitor -----------------#
if __name__=='__main__': # usage SerialTest.py [baud_rate]

    device='/dev/serial0' if len(sys.argv)<2 else sys.argv[1]

    baudrate=9600

    print "\nLoopback testing for serial port " + device + "...\n"

    try:

        #Starting serial connection
        serialPort = OpenSerialPort(device, baudrate)

        if (serialPort == 0):
            print "Error opening Serial Port " + device
            sys.exit(1)

        TestString = "Testing 1 2 3\n"

        printToScreen("write data: sent test string")
        serialPort.write(TestString)
        time.sleep(.05)
        printToScreen("waiting to received data....")
        ReceivedString = serialPort.readline()

        if TestString != ReceivedString:
            printToScreen("FAILED: Sent data does not match receive. Received %d bytes" % len(ReceivedString))
        else:
            printToScreen("PASSED! Loopback successful")
        serialPort.close()

    except Exception, e1:
        printToScreen( "error communicating...: " + str(e1))


    sys.exit(1)


