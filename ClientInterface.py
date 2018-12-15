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

try:
    from genmonlib.mylog import SetupLogger
    from genmonlib.myclient import ClientInterface
except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)



#----------  Signal Handler ------------------------------------------
def signal_handler(signal, frame):

    sys.exit(0)

#------------------- Command-line interface for monitor -----------------#
if __name__=='__main__': # usage program.py [server_address]
    address='localhost' if len(sys.argv)<2 else sys.argv[1]

    # log errors in this module to a file
    console = SetupLogger("client_console", log_file = "", stream = True)
    log = SetupLogger("client", "client.log")

    # Set the signal handler
    signal.signal(signal.SIGINT, signal_handler)

    startcount = 0
    while startcount <= 2:
        try:
            MyClientInterface = ClientInterface(host = address, log = log)
            break
        except Exception as e1:
            startcount += 1
            if startcount >= 2:
                console.error("Error: genmon not loaded.")
                sys.exit(1)
            time.sleep(1)
            continue


    try:

        while True:
            try:
                line = raw_input(">")
            except NameError:
                pass
                line = input(">")


            if line.lower() == "exit":
                break
            if len(line):
                data = MyClientInterface.ProcessMonitorCommand(line)
                print(data)

    except Exception as e1:
        print ("Error: " + str(e1))
    MyClientInterface.Close()
