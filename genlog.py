#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: genlog.py
# PURPOSE: genmon.py support program to allow logging of generator
# run time
#
#  AUTHOR: Jason G Yates
#    DATE: 19-Apr-2016
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import datetime, time, sys, signal, os, threading, socket
from datetime import datetime
import atexit, getopt

try:
    from genmonlib.mylog import SetupLogger
    from genmonlib.myclient import ClientInterface
    from genmonlib.mysupport import MySupport
    from genmonlib.program_defaults import ProgramDefaults
except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)


#----------  Signal Handler ----------------------------------------------------
def signal_handler(signal, frame):

    MyClientInterface.Close()
    sys.exit(0)

#------------------- excel_date ------------------------------------------------
def excel_date(date1):
    temp = datetime(1899, 12, 30)    # Note, not 31st Dec but 30th!
    delta = date1 - temp
    return str(float(delta.days) + (float(delta.seconds) / 86400))

#------------------- Command-line interface for genlog -------------------------
def LogDataToFile(fileName, time, Event):


    with open(fileName,"a") as LogFile:     #opens file
        if os.stat(fileName).st_size == 0:
            LogFile.write("Time,Event\n")

        LogFile.write(excel_date(time) + ","+ Event +"\n")
        LogFile.flush()

#------------------- Command-line interface for genlog -------------------------
if __name__=='__main__':


    address = ProgramDefaults.LocalHost
    fileName = ""

    HelpStr = '\npython genlog.py -a <IP Address or localhost> -f <outputfile> -c <config file path>\n'

    try:
        ConfigFilePath = ProgramDefaults.ConfPath
        console = SetupLogger("genlog_console", log_file = "", stream = True)

        port, loglocation, multi_instance = MySupport.GetGenmonInitInfo(ConfigFilePath, log = console)

        if not MySupport.PermissionsOK():
            console.error("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.")
            sys.exit(2)

        if MySupport.IsRunning(os.path.basename(__file__), multi_instance = multi_instance):
            console.error("The program %s is already loaded" % os.path.basename(__file__))
            sys.exit(2)

        opts, args = getopt.getopt(sys.argv[1:],"ha:f:c:",["help","address=","filename=", "configpath="])
    except getopt.GetoptError:
        console.error(HelpStr)
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            console.error(HelpStr)
            sys.exit()
        elif opt in ("-a", "--address"):
            address = arg
        elif opt in ("-f", "--filename"):
            fileName = arg
            fileName = fileName.strip()
        elif opt in ("-c", "--configpath"):
            ConfigFilePath = arg
            ConfigFilePath = ConfigFilePath.strip()

    console.error('Address is ' + address)
    console.error('Output file is ' + fileName)
    console.error("Config File Path is " + ConfigFilePath)


    if not len(fileName):
        console.error(HelpStr)
        sys.exit(2)


    log = SetupLogger("client", os.path.join(loglocation, "genlog.log"))

    try:
        # Set the signal handler
        signal.signal(signal.SIGINT, signal_handler)

        MyClientInterface = ClientInterface(host = address, port = port, log = log)

        LastEvent = ""

        while True:

            data = MyClientInterface.ProcessMonitorCommand("generator: getbase")

            if LastEvent != data:
                LastEvent = data
                LogDataToFile(fileName, datetime.now(), data)

            time.sleep(3)

    except Exception as e1:
        log.error("Error: " + str(e1))
        console.error("Error: " + str(e1))
