#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: ClientInterface.py
# PURPOSE:
#
#  AUTHOR: Jason G Yates
#    DATE: 17-Dec-2016
# MODIFICATIONS:
#------------------------------------------------------------

#
# This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import datetime, time, sys, smtplib, signal, os, threading, socket
import mylog

# log errors in this module to a file
log = mylog.SetupLogger("client", "client.log")


#----------  ClientInterface::init--- ------------------------------------------
class ClientInterface:
    def __init__(self, host="127.0.0.1", port=9082):

        self.EndOfMessage = "EndOfMessage"
        self.rxdatasize = 2000
        self.host = host
        self.port = port

        self.Connect()

    #----------  ClientInterface::Connect ---------------------------------
    def Connect(self):

        try:
            #create an INET, STREAMing socket
            self.Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            #now connect to the server on our port
            self.Socket.connect((self.host, self.port))
            sRetData, data = self.Receive(noeom = True)       # Get initial status before commands are sent
            print data
        except Exception, e1:
            self.FatalError("Error: Connect" + str(e1))


    #----------  ClientInterface::SendCommand ---------------------------------
    def SendCommand(self, cmd):

        try:
            self.Socket.sendall(cmd)
        except Exception, e1:
            self.LogError( "Error: TX:" + str(e1))
            self.Close()
            self.Connect()

    #----------  ClientInterface::Receive ---------------------------------
    def Receive(self, noeom = False):

        RetStatus = True
        try:
            data = self.Socket.recv(self.rxdatasize)
            if len(data):
                if not self.CheckForStarupMessage(data) or not noeom:
                    while not self.EndOfMessage in data:
                        more = self.Socket.recv(self.rxdatasize)
                        if len(more):
                            if self.CheckForStarupMessage(more):
                                data = ""
                                RetStatus = False
                                break
                            data += more

                    if data.endswith(self.EndOfMessage):
                        data = data[:-len(self.EndOfMessage)]
                        RetStatus = True

        except Exception, e1:
            self.LogError( "Error: RX:" + str(e1))
            self.Close()
            self.Connect()
            RetStatus = False
            data = "Retry"

        return RetStatus, data

    #----------  ClientInterface::CheckForStarupMessage ---------------------------------
    def CheckForStarupMessage(self, data):

        # check for initial status response from monitor
        if data.startswith("OK") or data.startswith("CRITICAL:") or data.startswith("WARNING:"):
            return True
        else:
            return False

    #----------  ClientInterface::Close ---------------------------------
    def Close(self):
        self.Socket.close()

    #----------  ClientInterface::ProcessMonitorCommand ---------------------------------
    def ProcessMonitorCommand(self, cmd):

        data = ""
        try:
            RetStatus = False
            while RetStatus == False:
                self.SendCommand(cmd)
                RetStatus, data = self.Receive()
        except Exception, e1:
            self.LogError("Error in ProcessMonitorCommand:" + str(e1))
        return data

    #---------------------ClientInterface::FatalError------------------------
    def LogError(self, Message):
        log.error(Message)

    #----------  ClientInterface::FatalError ---------------------------------
    def FatalError(self, Message):

        log.error(Message)
        raise Exception(Message)

#----------  Signal Handler ------------------------------------------
def signal_handler(signal, frame):

    sys.exit(0)

#------------------- Command-line interface for monitor -----------------#
if __name__=='__main__': # usage program.py [server_address]
    address='192.168.11.15' if len(sys.argv)<2 else sys.argv[1]


    # Set the signal handler
    signal.signal(signal.SIGINT, signal_handler)

    MyClientInterface = ClientInterface(host = address)

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


