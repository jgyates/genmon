#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: ClientInterface.py
# PURPOSE:
#
#  AUTHOR: Jason G Yates
#    DATE: 17-Dec-2016
# MODIFICATIONS:
#------------------------------------------------------------
import datetime, time, sys, smtplib, signal, os, threading, socket, getopt

try:
    from genmonlib.mylog import SetupLogger
    from genmonlib.myclient import ClientInterface
    from genmonlib.program_defaults import ProgramDefaults
except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)



#----------  Signal Handler ------------------------------------------
def signal_handler(signal, frame):

    sys.exit(0)

#------------------- Command-line interface for monitor -----------------#
if __name__=='__main__': # usage program.py [server_address] [port]
    address=ProgramDefaults.LocalHost
    port = ProgramDefaults.ServerPort

    # log errors in this module to a file
    console = SetupLogger("client_console", log_file = "", stream = True)
    HelpStr = '\npython ClientInterface.py -a <IP Address or none for localhost> -p <port or none for default port>\n'
    try:
        opts, args = getopt.getopt(sys.argv[1:],"hp:a:",["help","port=","address="])
    except getopt.GetoptError:
        console.error("Invalid command line argument.")
        sys.exit(2)

    try:
        for opt, arg in opts:
            if opt == '-h':
                console.error(HelpStr)
                sys.exit()
            elif opt in ("-a", "--address"):
                address = arg
            elif opt in ("-p", "--port"):
                port = int(arg)
    except Exception as e1:
        console.error ("Error parsing: " + str(e1))
        sys.exit(2)

    log = SetupLogger("client", "client.log")

    # Set the signal handler
    signal.signal(signal.SIGINT, signal_handler)

    MyClientInterface = ClientInterface(host = address, port = port, log = log)

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
        console.error ("Error: " + str(e1))
    MyClientInterface.Close()
