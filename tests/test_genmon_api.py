#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: test_genmon_api.py
# PURPOSE:
#
#  AUTHOR: Jason G Yates
#    DATE: 25-Apr-2018
# MODIFICATIONS:
#------------------------------------------------------------
import datetime, time, sys, smtplib, signal, os, threading, socket, requests, json, collections, getopt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from genmonlib.mylog import SetupLogger
    from genmonlib.myclient import ClientInterface
    from genmonlib.mycommon import MyCommon
    from genmonlib.program_defaults import ProgramDefaults
except:
    print("\n\nThis program is used for the testing of genmon.py and genserv.py.")
    print("\n\nThis program requires the modules that to reside in the genmonlib directory.\n")
    sys.exit(2)



#----------  Signal Handler ------------------------------------------
def signal_handler(signal, frame):

    sys.exit(0)
#------------ MyTest class -----------------------------------------------------
class MyTest(MyCommon):
    def __init__(self, address, serverport = ProgramDefaults.ServerPort, webport = "8000"):
        super(MyTest, self).__init__()

        self.Address = address
        self.WebPort = webport
        self.ServerPort = serverport

        # log errors in this module to a file
        self.log = SetupLogger("test_genmon_api", "test_genmon_api.log")
        self.console = SetupLogger("test_genmon_api_stderr", log_file = "", stream = True)


        # Set the signal handler
        signal.signal(signal.SIGINT, signal_handler)

        self.CommandDict = collections.OrderedDict()

        self.CommandDict["registers"] = [None, False]
        self.CommandDict["allregs"] = [None, False]
        self.CommandDict["logs"] = [None, False]
        self.CommandDict["status"] = [None, False]
        self.CommandDict["maint"] = [None, False]
        self.CommandDict["monitor"] = [None, False]
        self.CommandDict["outage"] = [None, False]
        self.CommandDict["settime"] = [None, False]
        #self.CommandDict["setexercise"] = ["=Monday,13:30,Weekly", False]
        #self.CommandDict["setquiet"] = ["setquiet=off", False]
        self.CommandDict["help"] = [None, False]
        #self.CommandDict["setremote"] = ["=stop", False]
        ## These commands are used by the web / socket interface only
        self.CommandDict["power_log_json"] = [None, False]
        #self.CommandDict["power_log_clear"] = [None, False]
        self.CommandDict["start_info_json"] = [None, False]
        self.CommandDict["registers_json"] = [None, False]
        self.CommandDict["allregs_json"] = [None, False]
        self.CommandDict["logs_json"] = [None, False]
        self.CommandDict["status_json"] = [None, False]
        self.CommandDict["maint_json"] = [None, False]
        self.CommandDict["monitor_json"] = [None, False]
        self.CommandDict["weather_json"] = [None, False]
        self.CommandDict["outage_json"] = [None, False]
        self.CommandDict["gui_status_json"] = [None, False]
        self.CommandDict["getsitename"] = [None, False]
        self.CommandDict["getbase"] = [None, False]
        self.CommandDict["gethealth"] = [None, False]
        self.CommandDict["getregvalue"] = ["=0000", False]
        self.CommandDict["readregvalue"] = ["=0000", False]
        self.CommandDict["getdebug"] = [None, False]
        self.CommandDict["sendregisters"] = [None, False]
        self.CommandDict["sendlogfiles"] = [None, False]

        self.ServerCmdDict = collections.OrderedDict()

        self.ServerCmdDict["status"] = [None, False]
        self.ServerCmdDict["status_json"] = [None, True]
        self.ServerCmdDict["outage"] = [None, False]
        self.ServerCmdDict["outage_json"] = [None, True]
        self.ServerCmdDict["maint"] = [None, False]
        self.ServerCmdDict["maint_json"] = [None, True]
        self.ServerCmdDict["logs"] = [None, False]
        self.ServerCmdDict["logs_json"] = [None, True]
        self.ServerCmdDict["monitor"] = [None, False]
        self.ServerCmdDict["monitor_json"] = [None, True]
        self.ServerCmdDict["registers_json"] = [None, True]
        self.ServerCmdDict["allregs_json"] = [None, True]
        self.ServerCmdDict["start_info_json"] = [None, True]
        self.ServerCmdDict["gui_status_json"] = [None, True]
        self.ServerCmdDict["power_log_json"] = [None, True]
        #self.ServerCmdDict["power_log_clear"] = [None, False]
        self.ServerCmdDict["getbase"] = [None, False]
        self.ServerCmdDict["getsitename"] = [None, False]
        #self.ServerCmdDict["setexercise"] = [None, False]
        #self.ServerCmdDict["setquiet"] = [None, False]
        #self.ServerCmdDict["setremote"] = [None, False]
        #self.ServerCmdDict["settime"] = [None, False]
        self.ServerCmdDict["getdebug"] = [None, False]
        #self.ServerCmdDict["updatesoftware"] = [None, False]
        self.ServerCmdDict["getfavicon"] = [None, False]
        self.ServerCmdDict["notifications" ] = [None, True]
        self.ServerCmdDict["settings"] = [None, True]
        #self.ServerCmdDict["setnotifications"] = [None, False]
        #self.ServerCmdDict["setsettings"] = [None, False]
        self.ServerCmdDict["getreglabels"] = [None, True]
        self.ServerCmdDict["get_add_on_settings"] = [None, True]
        #self.ServerCmdDict["set_add_on_settings"] = [None, True]
        #self.ServerCmdDict["restart"] = [None, False]
        #self.ServerCmdDict["stop"] = [None, False]
        self.ServerCmdDict["sendregisters"] = [None, False]
        self.ServerCmdDict["sendlogfiles"] = [None, False]


    #---------------------------------------------------------------------------
    def TestGenServ(self):
        try:
            for Key, CmdList in self.ServerCmdDict.items():
                ReturnValue = None
                CommandString = Key
                if len(CmdList) and CmdList[0] != None and len(CmdList[0]):
                    CommandString += CmdList[0]
                self.PrintResults("TESTING GENSERV: " + CommandString)

                ReturnValue = self.URLCommand(CommandString, params = CmdList[0], parsejson = CmdList[1])

                if isinstance(ReturnValue, str):
                    self.PrintResults(ReturnValue)
                elif sys.version_info[0] < 3 and isinstance(ReturnValue, unicode):
                    self.PrintResults(ReturnValue)
                elif isinstance(ReturnValue, dict):
                    self.PrintResults(self.DictToString(ReturnValue))
                elif isinstance(ReturnValue, list):
                    self.PrintResults(str(ReturnValue))
                else:
                    self.LogError("ERROR: Unknown type: " + Key + ":" + str(type(ReturnValue)))
        except Exception as e1:
            self.LogErrorLine("Error in genmon.py test: " + str(e1))

    #---------------------------------------------------------------------------
    def TestGenMon(self):

        MyClientInterface = ClientInterface(host = self.Address, port = self.ServerPort, log = self.log)

        try:

            for Key, CmdList in self.CommandDict.items():
                ReturnValue = None
                CommandString = "generator: " + Key
                if len(CmdList) and CmdList[0] != None and len(CmdList[0]):
                    CommandString += CmdList[0]
                self.PrintResults("TESTING GENMON: " + CommandString)

                ReturnValue = MyClientInterface.ProcessMonitorCommand(CommandString)
                if CmdList[1]:
                    self.PrintResults(self.DictToString(json.loads(ReturnValue)))
                else:
                    self.PrintResults(ReturnValue)

        except Exception as e1:
            self.LogErrorLine("Error in genmon.py test: " + str(e1))
        MyClientInterface.Close()

    #---------------------------------------------------------------------------
    def URLCommand(self,command, params = None, parsejson = False):

        try:
            if not len(command) or command == None:
                return

            URL = "http://" + self.Address + ":" + self.WebPort + "/cmd/" + command

            response = requests.get(URL, params = params)

            if parsejson:
                return response.json()
            else:
                #return response
                return response.json()

        except Exception as e1:
            self.LogErrorLine("Error in URLCommand: " + str(e1))

    #---------------------------------------------------------------------------
    def PrintResults(self, Message):

        try:
            if self.console != None:
                self.console.info(Message)
        except Exception as e1:
            self.LogErrorLine("Error in PrintResults: " + str(e1))
#-------------------------------------------------------------------------------
if __name__=='__main__':


    address='localhost'
    serverport = ProgramDefaults.ServerPort
    webport = "8000"

    HelpStr =  '\npython test_genmon_api.py -a <IP Address or none for localhost> -p <port or none for default port> -w <web port or none>\n'
    HelpStr += '\n'
    HelpStr += '      -a    address\n'
    HelpStr += '      -p    port of server\n'
    HelpStr += '      -w    web server port\n'
    HelpStr += '      -h    help\n'
    try:
        opts, args = getopt.getopt(sys.argv[1:],"hp:a:w:",["help","port=","address=","webport="])
    except getopt.GetoptError:
        print("Invalid command line argument.")
        sys.exit(2)

    try:
        for opt, arg in opts:
            if opt == '-h':
                print(HelpStr)
                sys.exit()
            elif opt in ("-a", "--address"):
                address = arg
            elif opt in ("-p", "--port"):
                serverport = int(arg)
            elif opt in ("-w", "--webport"):
                webport = arg
    except Exception as e1:
        print ("Error parsing: " + str(e1))
        sys.exit(2)

    Test = MyTest(address = address, serverport = serverport, webport = webport)

    Test.TestGenMon()
    Test.TestGenServ()
