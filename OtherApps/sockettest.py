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


import sys, time, getopt, socket


#------------ printToScreen --------------------------------------------
def printToScreen( msgstr):

    print "{0}\n".format(msgstr),
    no_op = 0
    # end printToScreen(msgstr):


#-------------------------------------------------------------------------------
def OpenPort(host, port):

    try:
        #create an INET, STREAMing socket
        newSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        newSocket.settimeout(3)
        #now connect to the server on our port
        newSocket.connect((host, port))
        return newSocket
    except Exception as e1:
        printToScreen("Error opening socket: " + str(e1))
        return None

#-------------------------------------------------------------------------------
if __name__=='__main__':

    HelpStr = '\npython sockettest.py  -a <ip address>  -p <port>\n'
    HelpStr += '\n       -a <ip address>\n'
    HelpStr +=   '       -p <port>\n'


    try:
        opts, args = getopt.getopt(sys.argv[1:],"ha:p:",["address=","port="])
    except getopt.GetoptError:
        print (HelpStr)
        sys.exit(2)

    host = None
    port = None
    for opt, arg in opts:
        if opt == '-h':
            print (HelpStr)
            sys.exit()
        elif opt in ("-a", "--address"):
            host = arg
        elif opt in ("-p", "--port"):
            port = arg

    if host == None or port == None:
        print (HelpStr)
        sys.exit(2)

    print "\nLoopback testing for TCP serial port at " + host + ":" + str(port) + "...\n"

    try:

        #Starting serial connection
        Socket = OpenPort(host, int(port))
        if Socket == None:
            print("Error creating socket")
            sys.exit(1)


        TestString = "Testing 1 2 3\n"

        printToScreen("write data: sent test string")
        Socket.sendall(TestString.encode())
        printToScreen("waiting to received data....")
        time.sleep(.05)
        ReceivedString = Socket.recv(200)

        Socket.close()

        if TestString != ReceivedString:
            printToScreen("FAILED: Sent data does not match receive. Received %d bytes" % len(ReceivedString))
        else:
            printToScreen("PASSED! Loopback successful")
        Socket.close()

    except Exception as e1:
        printToScreen( "error communicating...: " + str(e1))


    sys.exit(1)
