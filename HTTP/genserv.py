#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: genserv.py
# PURPOSE: Flask app for generator monitor web app
#
#  AUTHOR: Jason G Yates
#    DATE: 20-Dec-2016
#
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

from flask import Flask, render_template, request, jsonify
import sys, signal, os, socket, atexit, ConfigParser
import mylog


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
            RetData, data = self.Receive(noeom = True)       # Get initial status before commands are sent
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

#------------------------------------------------------------
app = Flask(__name__,static_url_path='')

# log errors in this module to a file
log = mylog.SetupLogger("genserv", "/var/log/genserv.log")

#------------------------------------------------------------
@app.route('/')
def root():
    return app.send_static_file('index.html')

#------------------------------------------------------------
@app.route("/cmd/<command>")
def command(command):

    if command in ["status", "outage", "maint", "logs", "monitor", "getbase", "getsitename", "setexercise", "setquiet", "getexercise"]:
        finalcommand = "generator: " + command
        try:
            if command == "setexercise":
                settimestr = request.args.get('settime', 0, type=str)
                finalcommand += "=" + settimestr
            if command == "setquiet":
                setquietstr = request.args.get('setquiet', 0, type=str)
                finalcommand += "=" + setquietstr
                #print finalcommand

            data = MyClientInterface.ProcessMonitorCommand(finalcommand)
        except Exception, e1:
            data = "Retry"
            log.error("Error on command function" + str(e1))
        return jsonify(data)

    else:
        return render_template('command_template.html', command = command)

#------------------------------------------------------------
if __name__ == "__main__":


    clientport = 0
    try:
        config = ConfigParser.RawConfigParser()
        # config parser reads from current directory, when running form a cron tab this is
        # not defined so we specify the full path
        config.read('/etc/genmon.conf')
        # heartbeat server port, must match value in check_generator_system.py and any calling client apps
        if config.has_option('GenMon', 'server_port'):
            clientport = config.getint('GenMon', 'server_port')
    except Exception, e1:
        log.error("Missing config file or config file entries: " + str(e1))

    MyClientInterface = ClientInterface(port=clientport)
    while True:
        try:
            app.run(host="0.0.0.0", port=8000)
        except Exception, e1:
            log.error("Error in app.run:" + str(e1))
