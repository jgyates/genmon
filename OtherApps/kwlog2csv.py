#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: kwlog2csv.py
# PURPOSE: kwlog2csv.py support program to allow testing of generator
# run time
#
#  AUTHOR: Jason G Yates
#    DATE: 17-Mar-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------


import getopt, os, sys, json

sys.path.append("..") # Adds higher directory to python modules path.

try:
    from genmonlib.program_defaults import ProgramDefaults
    from genmonlib.mylog import SetupLogger
except:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    sys.exit(2)


#------------ GeneratorDevice::LogToFile----------------------------------------
def LogToFile( File, TimeDate, Value):

    if not len(File):
        print("Error in LogToFile: invalid filename")

    try:
        with open(File,"a") as LogFile:     #opens file
            LogFile.write(TimeDate + "," + Value + "\n")
            LogFile.flush()
    except Exception as e1:
        print("Error in  LogToFile : File: %s: %s " % (File,str(e1)))

#------------------- Command-line interface for program ------------------------
if __name__=='__main__':


    address = ProgramDefaults.LocalHost
    port = ProgramDefaults.ServerPort
    fileName = ""


    HelpStr = '\npython kwlog2csv.py -a <IP Address or localhost> -f <outputfile>\n'
    HelpStr += "\n   Example: python kwlog2csv.py -a 192.168.1.100 -f Output.csv \n"
    HelpStr += "\n"
    HelpStr += "\n      -a  Address of system with genmon (omit for localhost)"
    HelpStr += "\n      -f  Filename to output the kW log in CSV format"
    HelpStr += "\n \n"

    try:
        opts, args = getopt.getopt(sys.argv[1:],"ha:f:p:",["address=","filename=","port="])
    except getopt.GetoptError:
        print("Help")
        sys.exit(2)

    try:
        for opt, arg in opts:
            if opt == '-h':
                print (HelpStr)
                sys.exit()
            elif opt in ("-a", "--address"):
                address = arg
                print ('Address is : %s' % address)
            elif opt in ("-p", "--port"):
                port = int(arg)
                print ('Port is : %s' % address)
            elif opt in ("-f", "--filename"):
                fileName = arg
                print ('Output file is : %s' % fileName)
    except Exception as e1:
        print ("Error : " + str(e1))
        sys.exit(2)

    if not len(address):
        print ("Address is : localhost")
        address = ProgramDefaults.LocalHost

    if not len(fileName):
        print (HelpStr)
        sys.exit(2)

    try:
        log = SetupLogger("client", "kwlog2csv.log")

        MyClientInterface = myclient.ClientInterface(host = address, port = port, log = log)

        data = MyClientInterface.ProcessMonitorCommand("generator: power_log_json")

        data = json.loads(data)

        for Time, Value in reversed(data):
            LogToFile(fileName, Time, Value)

    except Exception as e1:
        print ("Error (1): " + str(e1))
