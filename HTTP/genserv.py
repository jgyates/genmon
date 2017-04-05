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

from flask import Flask, render_template, request, jsonify
import sys, signal, os, socket, atexit, ConfigParser
import mylog, myclient

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

    if command in ["status", "outage", "maint", "logs", "monitor", "getbase", "getsitename", "setexercise", "setquiet", "getexercise","setremote"]:
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

    MyClientInterface = myclient.ClientInterface(port=clientport, log = log)
    while True:
        try:
            app.run(host="0.0.0.0", port=8000)
        except Exception, e1:
            log.error("Error in app.run:" + str(e1))
