#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: check_monitor_system.py
# PURPOSE: Nagios plugin for checking monitor system
#------------------------------------------------------------
import socket, sys, getopt

def main(argv):
    myhostaddress = ''

    try:
      opts, args = getopt.getopt(argv,"H:h")
    except getopt.GetoptError:
      print 'USAGE: check_monitor_system.py -H <hostaddress> '
      sys.exit(2)

    for opt, arg in opts:
      if opt == '-h':
         print 'USAGE: check_monitor_system.py -H <hostaddress>'
         sys.exit(1)
      elif opt in ("-H"):
         myhostaddress = arg

    if myhostaddress == '':
       print 'USAGE: check_monitor_system.py -H <hostaddress>'
       sys.exit(1)

    try:
        #create an INET, STREAMing socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        #now connect to the server on our port
        s.connect((myhostaddress, 9082))
        s.settimeout(8.0)   #  blok on recv
    except:
        print "CRITICAL: Monitor Program not running"
        sys.exit(2)

    try:
        # read serial data from socket
        data = s.recv(1024)
        s.shutdown(socket.SHUT_RDWR)
        s.close()
    except:
        # if not receiving then check exit
        print "CRITICAL: No Data"
        sys.exit(2)

    #print data
    if "OK" in data:           #
        print data
        sys.exit(0)
    elif "CRITICAL" in data:
        print data
        sys.exit(2)
    elif "WARNING" in data:
        print data
        sys.exit(1)
    else:
        print data
        sys.exit(1)

if __name__ == "__main__":
   main(sys.argv[1:])
