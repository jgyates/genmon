#!/usr/bin/env python

#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: gengpioin.py
# PURPOSE: genmon.py support program to allow amazon alexa voice commands
#
#  AUTHOR: Jason G Yates
#    DATE: 27-Jul-2019
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------
#
##############################################################################################
#### BASED ON WORK BY : https://github.com/nassir-malik/IOT-Pi3-Alexa-Automation          ####
##############################################################################################
#### To set up the Alexa Inegration, go to your Echo speaker and ask Alexa
#### to discover your device.  Say, "Discover my devices," or select Add
#### Device in the Devices section of the Alexa app.
####
#### Once Alexa has discovered your generator, you can use the Alexa app to
#### complete the setup.
####
#### To turn on your generator via the Echo speaker, say "Alexa, turn on
#### the generator".  And to off the generator again, "Alexa, turn off
#### the generator".
####
#### If you prefer to state the likes of "Alexa, start my generator"
#### or "Alexa, stop my generator" (rather than using the words ON or
#### OFF), you can set up a Routine with Alexa.


import email.utils, requests, select, socket, struct, sys, datetime, time, urllib, uuid, signal, os, threading
import atexit, getopt, json
import fcntl, re, time, locale, socket, subprocess, traceback
try:
    from genmonlib.mylog import SetupLogger
    from genmonlib.myconfig import MyConfig
    from genmonlib.myclient import ClientInterface
    from genmonlib.mysupport import MySupport
    from genmonlib.mycommon import MyCommon
    from genmonlib.program_defaults import ProgramDefaults
except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)



# This XML is the minimum needed to define one of our virtual switches
# to the Amazon Echo

SETUP_XML ="""<?xml version=1.0?>
            <root>
             <device>
                <deviceType>urn:Belkin:device:controllee:1</deviceType>
                <friendlyName>%(device_name)s</friendlyName>
                <manufacturer>Belkin International Inc.</manufacturer>
                <modelName>Socket</modelName>
                <modelNumber>3.1415</modelNumber>
                <modelDescription>Belkin Plugin Socket 1.0</modelDescription>\r\n
                <UDN>uuid:Socket-1_0-%(device_serial)s</UDN>
                <serialNumber>221517K0101767</serialNumber>
                <binaryState>0</binaryState>
                <serviceList>
                  <service>
                      <serviceType>urn:Belkin:service:basicevent:1</serviceType>
                      <serviceId>urn:Belkin:serviceId:basicevent1</serviceId>
                      <controlURL>/upnp/control/basicevent1</controlURL>
                      <eventSubURL>/upnp/event/basicevent1</eventSubURL>
                      <SCPDURL>/eventservice.xml</SCPDURL>
                  </service>
              </serviceList>
              </device>
            </root>"""

# A simple utility class to wait for incoming data to be
# ready on a socket.
#----------  poller class ------------------------------------------------------
class poller(MyCommon):
    # ---------------- poller.init ---------------------------------------------
    def __init__(self, log = None, debug = False):
        super(poller, self).__init__()
        self.log = log
        self.debug = debug
        try:
            self.poller = select.poll()
            self.targets = {}
        except Exception as e1:
            self.LogErrorLine("Error in poller init: " + str(e1))
            sys.exit(1)

    # ---------------- poller.add ----------------------------------------------
    def add(self, target, fileno = None):
        if not fileno:
            fileno = target.fileno()
        self.poller.register(fileno, select.POLLIN)
        self.targets[fileno] = target

    # ---------------- poller.remove -------------------------------------------
    def remove(self, target, fileno = None):
        if not fileno:
            fileno = target.fileno()
        self.poller.unregister(fileno)
        del(self.targets[fileno])

    # ---------------- poller.poll ---------------------------------------------
    def poll(self, timeout = 0):
        ready = self.poller.poll(timeout)
        num = len(ready)
        for one_ready in ready:
            target = self.targets.get(one_ready[0], None)
            if target:
                target.do_read(one_ready[0])
        return num


# Base class for a generic UPnP device. This is far from complete
# but it supports either specified or automatic IP address and port
# selection.
#----------  upnp_device class -------------------------------------------------
class upnp_device(MyCommon):
    this_host_ip = None

    # ---------------- upnp_device.local_ip_address ----------------------------
    @staticmethod
    def local_ip_address():
        if not upnp_device.this_host_ip:
            temp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                temp_socket.connect(('8.8.8.8', 53))
                upnp_device.this_host_ip = temp_socket.getsockname()[0]
            except:
                upnp_device.this_host_ip = '127.0.0.1'
            del(temp_socket)
        return upnp_device.this_host_ip


    # ---------------- upnp_device.init ----------------------------------------
    def __init__(self, listener, poller, port, root_url, server_version, persistent_uuid, other_headers = None, ip_address = None, log = None, debug = False):
        super(upnp_device, self).__init__()
        self.log = log
        self.debug = debug
        try:
            self.listener = listener
            self.poller = poller
            self.port = port
            self.root_url = root_url
            self.server_version = server_version
            self.persistent_uuid = persistent_uuid
            self.uuid = uuid.uuid4()
            self.other_headers = other_headers

            if ip_address:
                self.ip_address = ip_address
            else:
                self.ip_address = upnp_device.local_ip_address()

            if self.ip_address == None:
                self.LogErrorLine("Error : unable to get IP address in upnp_device init")
                sys.exit(1)

            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.ip_address, self.port))
            self.socket.listen(5)
            if self.port == 0:
                self.port = self.socket.getsockname()[1]
            self.poller.add(self)
            self.client_sockets = {}
            self.listener.add_device(self)
        except Exception as e1:
            self.LogErrorLine("Error in upnp_device init: " + str(e1))
            sys.exit(1)
    # ---------------- upnp_device.fileno --------------------------------------
    def fileno(self):
        return self.socket.fileno()

    # ---------------- upnp_device.do_read -------------------------------------
    def do_read(self, fileno):
        if fileno == self.socket.fileno():
            (client_socket, client_address) = self.socket.accept()
            self.poller.add(self, client_socket.fileno())
            self.client_sockets[client_socket.fileno()] = (client_socket, client_address)
        else:
            data, sender = self.client_sockets[fileno][0].recvfrom(4096)
            if not data:
                self.poller.remove(self, fileno)
                del(self.client_sockets[fileno])
            else:
                self.handle_request(data, sender, self.client_sockets[fileno][0], self.client_sockets[fileno][1])

    # ---------------- upnp_device.handle_request ------------------------------
    def handle_request(self, data, sender, socket, client_address):
        pass

    # ---------------- upnp_device.get_name ------------------------------------
    def get_name(self):
        return "unknown"

    # ---------------- upnp_device.respond_to_search ---------------------------
    def respond_to_search(self, destination, search_target):
        self.LogDebug("Responding to search for %s" % self.get_name())
        date_str = email.utils.formatdate(timeval=None, localtime=False, usegmt=True)
        location_url = self.root_url % {'ip_address' : self.ip_address, 'port' : self.port}
        message = ("HTTP/1.1 200 OK\r\n"
                  "CACHE-CONTROL: max-age=86400\r\n"
                  "DATE: %s\r\n"
                  "EXT:\r\n"
                  "LOCATION: %s\r\n"
                  "OPT: \"http://schemas.upnp.org/upnp/1/0/\"; ns=01\r\n"
                  "01-NLS: %s\r\n"
                  "SERVER: %s\r\n"
                  "ST: %s\r\n"
                  "USN: uuid:%s::%s\r\n" % (date_str, location_url, self.uuid, self.server_version, search_target, self.persistent_uuid, search_target))
        if self.other_headers:
            for header in self.other_headers:
                message += "%s\r\n" % header
        message += "\r\n"
        self.LogDebug(message)
        temp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        temp_socket.sendto(message.encode("UTF-8"), destination)

# This subclass does the bulk of the work to mimic a WeMo switch on the network.
#----------  fauxmo class ------------------------------------------------------
class fauxmo(upnp_device):
    # ---------------- fauxmo.make_uuid ----------------------------------------
    @staticmethod
    def make_uuid(name):
        return ''.join(["%x" % sum([ord(c) for c in name])] + ["%x" % ord(c) for c in "%sfauxmo!" % name])[:14]

    # ---------------- fauxmo.__init__ -----------------------------------------
    def __init__(self, name, listener, poller, ip_address, port, action_handler = None, log = None,  debug  = False):
        self.log = log
        self.debug = debug
        try:
            self.serial = self.make_uuid(name)
            self.name = name
            self.ip_address = ip_address
            self.generatorStatus = 0
            persistent_uuid = "Socket-1_0-" + self.serial
            other_headers = ['X-User-Agent: redsonic']
            super(fauxmo, self).__init__(listener, poller, port, "http://%(ip_address)s:%(port)s/setup.xml", "Unspecified, UPnP/1.0, Unspecified", persistent_uuid, other_headers=other_headers, ip_address=ip_address, log = log, debug = debug)
            if action_handler:
                self.action_handler = action_handler
            else:
                self.action_handler = self

            self.LogDebug("FauxMo device '%s' ready on %s:%s" % (self.name, self.ip_address, self.port))
        except Exception as e1:
            self.LogErrorLine("Error in fauxmo init: " + str(e1))
            sys.exit(1)

    # ---------------- fauxmo.get_name -----------------------------------------
    def get_name(self):
        return self.name

    # ---------------- fauxmo.handle_request -----------------------------------
    def handle_request(self, data, sender, socket, client_address):
        data = data.decode('utf-8')
        success = False

        if data.find('GET /setup.xml HTTP/1.1') == 0:

            self.LogDebug("Responding to setup.xml for %s" % self.name)
            xml = SETUP_XML % {'device_name' : self.name, 'device_serial' : self.serial}
            date_str = email.utils.formatdate(timeval=None, localtime=False, usegmt=True)
            message = ("HTTP/1.1 200 OK\r\n"
                       "CONTENT-LENGTH: %d\r\n"
                       "CONTENT-TYPE: text/xml\r\n"
                       "DATE: %s\r\n"
                       "LAST-MODIFIED: Sat, 01 Jan 2000 00:01:15 GMT\r\n"
                       "SERVER: Unspecified, UPnP/1.0, Unspecified\r\n"
                       "X-User-Agent: redsonic\r\n"
                       "CONNECTION: close\r\n"
                       "\r\n"
                       "%s" % (len(xml), date_str, xml))
            self.LogDebug(message)
            socket.send(message.encode("UTF-8"))
        elif data.find('SOAPACTION: "urn:Belkin:service:basicevent:1#SetBinaryState"') != -1:
            success = False
            if data.find('SetBinaryState') != -1:
                if data.find('<BinaryState>1</BinaryState>') != -1:
                    # on
                    self.LogDebug("Responding to ON for %s" % self.name)
                    success = self.action_handler.on()
                    if success:
                        self.generatorStatus = 1
                elif data.find('<BinaryState>0</BinaryState>') != -1:
                    # off
                    self.LogDebug("Responding to OFF for %s" % self.name)
                    success = self.action_handler.off()
                    if success:
                        self.generatorStatus = 0
                else:
                    self.LogError("Unknown Binary State request:")
                    self.LogError(data)

            if success:
                # The echo is happy with the 200 status code and doesn't
                # appear to care about the SOAP response body
                self.LogDebug("Successfully Completed Action")
                soap = ""
                date_str = email.utils.formatdate(timeval=None, localtime=False, usegmt=True)
                message = ("HTTP/1.1 200 OK\r\n"
                           "CONTENT-LENGTH: %d\r\n"
                           "CONTENT-TYPE: text/xml charset=\"utf-8\"\r\n"
                           "DATE: %s\r\n"
                           "EXT:\r\n"
                           "SERVER: Unspecified, UPnP/1.0, Unspecified\r\n"
                           "X-User-Agent: redsonic\r\n"
                           "CONNECTION: close\r\n"
                           "\r\n"
                           "%s" % (len(soap), date_str, soap))
                socket.send(message.encode("UTF-8"))
        elif data.find('GetBinaryState'):
            self.generatorStatus = self.action_handler.status(self.generatorStatus)
            self.LogDebug("Responding to provide current state: " + str(self.generatorStatus))
            soap = """<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
                <s:Body>
                    <u:GetBinaryStateResponse
                    xmlns:u="urn:Belkin:service:basicevent:1">
                    <BinaryState>"""+ str(self.generatorStatus) +"""</BinaryState>
                    </u:GetBinaryStateResponse>
                </s:Body></s:Envelope>"""
            date_str = email.utils.formatdate(timeval=None, localtime=False, usegmt=True)
            message = ("HTTP/1.1 200 OK\r\n"
                       "CONTENT-LENGTH: %d\r\n"
                       "CONTENT-TYPE: text/xml charset=\"utf-8\"\r\n"
                       "DATE: %s\r\n"
                       "EXT:\r\n"
                       "SERVER: Unspecified, UPnP/1.0, Unspecified\r\n"
                       "X-User-Agent: redsonic\r\n"
                       "CONNECTION: close\r\n"
                       "\r\n"
                       "%s" % (len(soap), date_str, soap))
            socket.send(message.encode("UTF-8"))
            self.LogDebug("SEND RESPONSE: "+str(message.replace('\n','\\n').replace('\r','\\r')))

        else:
            self.LogError("Unknown data:")
            self.LogError(str(data))
    # ---------------- fauxmo.on -----------------------------------------------
    def on(self):
        return False

    # ---------------- fauxmo.off ----------------------------------------------
    def off(self):
        return True


# Since we have a single process managing several virtual UPnP devices,
# we only need a single listener for UPnP broadcasts. When a matching
# search is received, it causes each device instance to respond.
#
# Note that this is currently hard-coded to recognize only the search
# from the Amazon Echo for WeMo devices. In particular, it does not
# support the more common root device general search. The Echo
# doesn't search for root devices.
#----------  upnp_broadcast_responder class ------------------------------------
class upnp_broadcast_responder(MyCommon):
    TIMEOUT = 0

    # ---------------- upnp_broadcast_responder.init ---------------------------
    def __init__(self, log = None, debug = False):
        super(upnp_broadcast_responder, self).__init__()
        self.log = log
        self.debug = debug
        self.devices = []

    # ---------------- upnp_broadcast_responder.init_socket --------------------
    def init_socket(self):
        ok = True
        self.ip = '239.255.255.250'
        self.port = 1900
        try:
            #This is needed to join a multicast group
            self.mreq = struct.pack("4sl",socket.inet_aton(self.ip),socket.INADDR_ANY)

            #Set up server socket
            self.ssock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM,socket.IPPROTO_UDP)
            self.ssock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)

            try:
                self.ssock.bind(('',self.port))
            except Exception as e:
                self.LogError("WARNING: Failed to bind %s:%d: %s" , (self.ip,self.port,e))
                ok = False

            try:
                self.ssock.setsockopt(socket.IPPROTO_IP,socket.IP_ADD_MEMBERSHIP,self.mreq)
            except Exception as e:
                self.LogError('WARNING: Failed to join multicast group:'+str(e))
                ok = False

        except Exception as e:
            self.LogError("Failed to initialize UPnP sockets:"+str(e))
            return False
        if ok:
            self.LogDebug("Listening for UPnP broadcasts")

    # ---------------- upnp_broadcast_responder.fileno -------------------------
    def fileno(self):
        return self.ssock.fileno()
    # ---------------- upnp_broadcast_responder.do_read ------------------------
    def do_read(self, fileno):
        data, sender = self.recvfrom(1024)
        data = data.decode('utf-8')
        if data:
            if data.find('M-SEARCH') >= 0 and data.find('urn:Belkin:device:**') >0 or data.find('n:Belkin:device:**') >0 or data.find('upnp:rootdevice') >0:
                for device in self.devices:
                    time.sleep(0.5)
                    device.respond_to_search(sender, 'urn:Belkin:device:**')
            else:
                pass
    # ---------------- upnp_broadcast_responder.recvfrom -----------------------
    #Receive network data
    def recvfrom(self,size):
        if self.TIMEOUT:
            self.ssock.setblocking(0)
            ready = select.select([self.ssock], [], [], self.TIMEOUT)[0]
        else:
            self.ssock.setblocking(1)
            ready = True

        try:
            if ready:
                return self.ssock.recvfrom(size)
            else:
                return False, False
        except Exception as e:
            self.LogError("recvfrom exception: "+str(e))
            return False, False

    def add_device(self, device):
        self.devices.append(device)
        self.LogDebug("UPnP broadcast listener: new device registered")

# This is an example handler class. The fauxmo class expects handlers to be
# instances of objects that have on() and off() methods that return True
# on success and False otherwise.
#
# This example class takes two full URLs that should be requested when an on
# and off command are invoked respectively. It ignores any return data.

class FauxmoCallback(MyCommon):
    """Use this DEBOUNCE_SECONDS to keep multiple Amazon Echo devices from reacting to
       the same voice command.
    """
    DEBOUNCE_SECONDS = 0.3
    STATUS_INTERVAL = 10
    # ---------------- FauxmoCallback.init -------------------------------------
    def __init__(self, cmd, log = None, debug = False):
        super(FauxmoCallback, self).__init__()
        self.cmd = cmd
        self.log = log
        self.debug = debug
        self.lastEcho = time.time()
        self.lastStatus = time.time()
    # ---------------- FauxmoCallback.on ---------------------------------------
    def on(self):
        if self.debounce():
            return True
        try:
              returnValue = self.cmd("generator: setremote=starttransfer")
              ## FOR TESTING ## returnValue = self.cmd("generator: setremote=start")
              ## FOR TESTING ## returnValue = self.cmd("generator: setremote=stop")
              self.LogDebug("Sent Remote Start Command. Return Value: "+returnValue)
              if returnValue != "Remote command sent successfully":
                  self.LogError("Command Failed")
                  return False
        except Exception as e1:
              LogErrorLine("Error FauxmoCallback.on: " + str(e1))
              return False
        return True
    # ---------------- FauxmoCallback.off --------------------------------------
    def off(self):
        if self.debounce():
            return True
        try:
            returnValue = self.cmd("generator: setremote=stop")

            self.LogDebug("Sent Remote Stop Command. Return Value: "+returnValue)
            if returnValue != "Remote command sent successfully":
                self.LogError("Command Failed")
                return False
        except Exception as e1:
            self.LogErrorLine("Error FauxmoCallback.off: " + str(e1))
            return False
        return True
    # ---------------- FauxmoCallback.status -----------------------------------
    def status(self, currentStatus):
        """Ensure the generators status is not checked too often if many
           Echos are present
        """
        if (time.time() - self.lastStatus) < self.STATUS_INTERVAL:
            return currentStatus

        self.lastStatus = time.time()
        try:
              returnValue = self.cmd("generator: getbase")
              self.LogDebug("Sent GETBASE Command. Return Value: "+returnValue)
              if "RUNNING" in returnValue:
                  currentStatus = 1
              else:
                  currentStatus = 0
        except Exception as e1:
              LogErrorLine("Error StopCallback: " + str(e1))
              return currentStatus
        return currentStatus

    # ---------------- FauxmoCallback.debounce ---------------------------------
    def debounce(self):
        """If multiple Echos are present, the one most likely to respond first
           is the one that can best hear the speaker... which is the closest one.
           Adding a refractory period to handlers keeps us from worrying about
           one Echo overhearing a command meant for another one.
        """
        if (time.time() - self.lastEcho) < self.DEBOUNCE_SECONDS:
            return True

        self.lastEcho = time.time()
        return False


#----------  Signal Handler ----------------------------------------------------
def signal_handler(signal, frame):

    try:
        MyClientInterface.Close()
    except Exception as e1:
        log.error("Error: signal_handler: " + str(e1))
    sys.exit(0)

#------------------- Command-line interface for gengpioin ----------------------
if __name__=='__main__':
    address=ProgramDefaults.LocalHost

    try:
        console = SetupLogger("genalexa_console", log_file = "", stream = True)

        if os.geteuid() != 0:
            console.error("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.")
            sys.exit(2)

        HelpStr = '\nsudo python genalexa.py -a <IP Address or localhost> -c <path to genmon config file>\n'
        try:
            ConfigFilePath = ProgramDefaults.ConfPath
            opts, args = getopt.getopt(sys.argv[1:],"hc:a:",["help","configpath=","address="])
        except getopt.GetoptError:
            console.error("Invalid command line argument.")
            sys.exit(2)

        for opt, arg in opts:
            if opt == '-h':
                console.error(HelpStr)
                sys.exit()
            elif opt in ("-a", "--address"):
                address = arg
            elif opt in ("-c", "--configpath"):
                ConfigFilePath = arg
                ConfigFilePath = ConfigFilePath.strip()
    except Exception as e1:
        console.error("Error in init: " + str(e1) + " : " + GetErrorLine())
        sys.exit(1)
    try:
        port, loglocation = MySupport.GetGenmonInitInfo(ConfigFilePath, log = console)
        log = SetupLogger("client", os.path.join(loglocation, "genalexa.log"))
    except Exception as e1:
        print("Error setting up log: " + str(e1))
        sys.exit(1)
    try:
        # Set the signal handler
        signal.signal(signal.SIGINT, signal_handler)

        if not os.path.isfile(os.path.join(ConfigFilePath, 'genalexa.conf')):
            console.error("Error: config file not found")
            log.error("Error: config file not found")
            sys.exit(1)
        config = MyConfig(filename = os.path.join(ConfigFilePath, 'genalexa.conf'), section = 'genalexa', log = log)
        FauxmoName = config.ReadValue('name', default = " generator")
        FauxmoPort = config.ReadValue('port', return_type = int, default = 52004)
        Debug = config.ReadValue('debug', return_type = bool, default = False)

        log.error("Key word: " + FauxmoName + "; Port: "+str(FauxmoPort) + "; " + "Debug: " + str(Debug))
        MyClientInterface = ClientInterface(host = address, port = port, log = log)


        data = MyClientInterface.ProcessMonitorCommand("generator: start_info_json")
        StartInfo = {}
        StartInfo = json.loads(data)
        remoteCommands = False
        if 'RemoteCommands' in StartInfo:
           remoteCommands = StartInfo['RemoteCommands']
        if remoteCommands == False:
           log.error("Generator does not support remote commands. So you cannot use this addon. Exiting....")
           sys.exit(1)

        FauxmoAction = FauxmoCallback(MyClientInterface.ProcessMonitorCommand, log = log, debug = Debug)

        # Set up our singleton for polling the sockets for data ready
        p = poller(log = log)

        # Set up our singleton listener for UPnP broadcasts
        u = upnp_broadcast_responder(log  = log, debug = Debug)
        u.init_socket()

        # Add the UPnP broadcast listener to the poller so we can respond
        # when a broadcast is received.
        p.add(u)

        switch = fauxmo(FauxmoName, u, p, None, FauxmoPort, action_handler = FauxmoAction, log  = log, debug = Debug)

        if Debug:
            log.info("Entering main loop")

        while True:
            try:
                # Allow time for a ctrl-c to stop the process
                p.poll(100)
                time.sleep(0.1)
            except Exception as e:
                log.error("Exception occured in main loop: "  + str(e))
                time.sleep(60)
                # break

    except Exception as e1:
        log.error("Error : " + str(e1))
        console.error("Error: " + str(e1))
