#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: ClientInterface.py
# PURPOSE:
#
#  AUTHOR: Jason G Yates
#    DATE: 17-Dec-2016
# MODIFICATIONS:
#------------------------------------------------------------
import datetime, time, sys, smtplib, signal, os, threading, socket
import mylog, myclient


#----------  Signal Handler ------------------------------------------
def signal_handler(signal, frame):

    sys.exit(0)

#------------------- Command-line interface for monitor -----------------#
if __name__=='__main__': # usage program.py [server_address]
    address='192.168.11.15' if len(sys.argv)<2 else sys.argv[1]

    # log errors in this module to a file
    log = mylog.SetupLogger("client", "client.log")

    # Set the signal handler
    signal.signal(signal.SIGINT, signal_handler)

    MyClientInterface = myclient.ClientInterface(host = address, log = log)

    try:

        while True:
            line = raw_input(">")
            #print line
            if line.lower() == "exit":
                break
            data = MyClientInterface.ProcessMonitorCommand(line)

            print data

    except Exception, e1:
        print "Error: " + str(e1)
    MyClientInterface.Close()


