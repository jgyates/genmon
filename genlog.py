#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: genlog.py
# PURPOSE: genmon.py support program to allow logging of generator
# run time
#
#  AUTHOR: Jason G Yates
#    DATE: 19-Apr-2016
#
# MODIFICATIONS:
#------------------------------------------------------------

import datetime, time, sys, signal, os, threading, socket
from datetime import datetime
import atexit, getopt
import myclient, mylog


#----------  Signal Handler ------------------------------------------
def signal_handler(signal, frame):

    MyClientInterface.Close()
    sys.exit(0)

#------------------- excel_date -----------------#
def excel_date(date1):
    temp = datetime(1899, 12, 30)    # Note, not 31st Dec but 30th!
    delta = date1 - temp
    return str(float(delta.days) + (float(delta.seconds) / 86400))

#------------------- Command-line interface for genlog -----------------#
def LogDataToFile(fileName, time, Event):


    with open(fileName,"a") as LogFile:     #opens file
        if os.stat(fileName).st_size == 0:
            LogFile.write("Time,Event\n")

        LogFile.write(excel_date(time) + ","+ Event +"\n")
        LogFile.flush()

#------------------- Command-line interface for genlog -----------------#
if __name__=='__main__':


    address = '127.0.0.1'
    fileName = ""

    HelpStr = '\npython genlog.py -a <IP Address or localhost> -o <outputfile>\n'

    try:
        opts, args = getopt.getopt(sys.argv[1:],"ha:f:",["address=","filename="])
    except getopt.GetoptError:
        print HelpStr
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print HelpStr
            sys.exit()
        elif opt in ("-a", "--address"):
            address = arg
        elif opt in ("-f", "--filename"):
            fileName = arg

    print 'Address is "', address
    print 'Output file is "', fileName
    if not len(fileName):
        print HelpStr
        sys.exit(2)

    try:
        log = mylog.SetupLogger("client", "genlog.log")
        # Set the signal handler
        signal.signal(signal.SIGINT, signal_handler)

        MyClientInterface = myclient.ClientInterface(host = address, log = log)

        LastEvent = ""

        while True:

            data = MyClientInterface.ProcessMonitorCommand("generator: getbase")

            if LastEvent != data:
                LastEvent = data
                LogDataToFile(fileName, datetime.now(), data)

            time.sleep(3)

    except Exception, e1:
        log.error("Error: " + str(e1))
        print "Error: " + str(e1)








