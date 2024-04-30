#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: genmqttin.py
# PURPOSE: genmqttin.py is a genmon add on program that will listen for MQTT
# broker changes and import them into genmon as sensor data
#
#  AUTHOR: jgyates
#    DATE: 03-10-2024
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------


import json
import os
import signal
import ssl
import sys
import threading
import time

# The following is need to install the mqtt module: pip3 install paho-mqtt

try:
    import paho.mqtt.client as mqtt
except Exception as e1:
    print(
        "\n\nThe program requies the paho-mqtt module to be installed. Please use 'sudo pip install paho-mqtt' to install.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)
try:
    # this will add the parent of the genmonlib folder to the path
    # if we are one level below the genmonlib parent (e.g. in the addon folder)
    file_root = os.path.dirname(os.path.realpath(__file__))
    parent_root = os.path.abspath(os.path.join(file_root, os.pardir))
    if os.path.isdir(os.path.join(parent_root, "genmonlib")):
        sys.path.insert(1, parent_root)

    from genmonlib.myclient import ClientInterface
    from genmonlib.mycommon import MyCommon
    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.mysupport import MySupport
    from genmonlib.mythread import MyThread
    from genmonlib.program_defaults import ProgramDefaults

except Exception as e1:
    print(
        "\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n"
    )
    print(
        "Please see the project documentation at https://github.com/jgyates/genmon.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)

# ------------ MyMQTT class -----------------------------------------------------
class MyMQTT(MyCommon):

    # ------------ MyMQTT::init--------------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        configfilepath=ProgramDefaults.ConfPath,
        console=None,
    ):

        super(MyMQTT, self).__init__()

        self.log = log
        self.console = console

        self.Exiting = False
        self.Username = None
        self.Password = None

        self.MQTTAddress = None
        self.MonitorAddress = host
        self.MQTTPort = 1883
        self.TopicRoot = None
        self.AccessLock = threading.Lock()
        self.debug = False
        self.MaxTopicsSupported = 4
        self.LastValues = {}

        try:
            config = MyConfig(
                filename=os.path.join(configfilepath, "genmqttin.conf"),
                section="genmqttin",
                log=log,
            )

            self.Username = config.ReadValue("username")
            self.Password = config.ReadValue("password")
            self.ClientID = config.ReadValue("client_id", default="genmon")
            self.MQTTAddress = config.ReadValue("mqtt_address")

            if self.MQTTAddress == None or not len(self.MQTTAddress):
                self.LogError("Error: invalid MQTT server address")
                sys.exit(1)

            self.MonitorAddress = config.ReadValue("monitor_address", default=self.MonitorAddress)

            if self.MonitorAddress != None:
                self.MonitorAddress = self.MonitorAddress.strip()

            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost

            self.MQTTPort = config.ReadValue("mqtt_port", return_type=int, default=1883)
            self.TopicRoot = config.ReadValue("root_topic")

            if self.TopicRoot != None:
                self.TopicRoot = self.TopicRoot.strip()
                self.LogDebug("Root Topic : " + self.TopicRoot)

            if self.TopicRoot == None or not len(self.TopicRoot):
                self.TopicRoot = None

            # http://www.steves-internet-guide.com/mosquitto-tls/
            self.CertificateAuthorityPath = config.ReadValue("cert_authority_path", default="")
            self.TLSVersion = config.ReadValue("tls_version", return_type=str, default="1.0")
            self.CertReqs = config.ReadValue("cert_reqs", return_type=str, default="Required")
            self.ClientCertificatePath = config.ReadValue("client_cert_path", default="")
            self.ClientKeyPath = config.ReadValue("client_key_path", default="")

            self.strict = config.ReadValue("strict", return_type=bool, default=False)
            self.use_for_power_fuel = config.ReadValue("use_for_power_fuel", return_type=bool, default=False)
            self.topics = self.ParseStringToList(config.ReadValue("topics", default=""))
            self.types = self.ParseStringToList(config.ReadValue("types", default=""))
            self.units = self.ParseStringToList(config.ReadValue("units", default=""))
            self.labels = self.ParseStringToList(config.ReadValue("labels", default=""))
            self.exclude_gauge = self.ParseStringToList(config.ReadValue("exclude_gauge",default=""))
            self.nominal_values = self.ParseStringToList(config.ReadValue("nominal_values", default=None))
            self.max_values = self.ParseStringToList(config.ReadValue("maximum_values", default=None))
            self.powerfactor = config.ReadValue("powerfactor", return_type=float, default=1.0)

            self.debug = config.ReadValue("debug", return_type=bool, default=False)

        except Exception as e1:
            self.LogErrorLine(
                "Error reading "
                + os.path.join(configfilepath, "genmqttin.conf")
                + " : "
                + str(e1)
            )
            sys.exit(1)

        try:
            if self.topics == None or len(self.topics) == 0:
                self.LogError("Error validating topics: no topics found")
                sys.exit(1)
            self.NumTopics = len(self.topics)
            self.LogDebug("Found " + str(self.NumTopics) +" topics.")
            for type in self.types:
                if not type.lower() in ["fuel","temperature","power","current","voltage","pressure","ct1","ct2","ctpower1","ctpower2","voltageleg1","voltageleg2"]:
                    self.LogError("Error: invalid type found: " + str(type))
                    sys.exit(1)
            if self.exclude_gauge != None and len(self.exclude_gauge):
                for exclude in self.exclude_gauge:
                    if not exclude.lower() in self.labels:
                        self.LogError("Invalid gague in exclude gauge list: " + str(exclude))
            if len(self.topics) != len(self.types):
                self.LogError("Number of topics does not equal the number of types. " + str(len(self.topics)) +", " + str(len(self.types)))
                sys.exit(1)
            if len(self.topics) != len(self.labels):
                self.LogError("Number of topics does not equal the number of labels. " + str(len(self.topics)) +", " + str(len(self.labels)))
                sys.exit(1)
            if len(self.topics) != len(self.units):
                self.LogError("Number of topics does not equal the number of units. " + str(len(self.topics)) +", " + str(len(self.units)))
                sys.exit(1)
            if len(self.topics) != len(self.nominal_values):
                self.LogError("Number of topics does not equal the number of nominal values. " + str(len(self.topics)) +", " + str(len(self.nominal_values)))
                sys.exit(1)
            if len(self.topics) != len(self.max_values):
                self.LogError("Number of topics does not equal the number of max values. " + str(len(self.topics)) +", " + str(len(self.max_values)))
                sys.exit(1)
            
            self.UseCT1CT2 = False
            self.UseP1P2 = False
            self.UseVoltageLegs = False
            if "ct1" in self.types and "ct2" in self.types:
                self.LogDebug("Using ct1 and ct2")
                self.UseCT1CT2 = True
            if "ctpower1" in self.types and "ctpower2" in self.types:
                self.LogDebug("Using ctpower1 and ctpower2")
                self.UseP1P2 = True
            if "voltageleg1" in self.types and "voltagelegs2" in self.types:
                self.LogDebug("Using voltageleg1 and voltagelegs2")
                self.UseVoltageLegs = True

            # build dict
            self.Sensors = {}
            index = 0
            self.GaugeData = []
            for topic in self.topics:
                if index >= self.MaxTopicsSupported:
                    self.LogError("WARNING: Only importing data from the first %d topics. Ignoring the other topics." % self.MaxTopicsSupported)
                    break
                if self.exclude_gauge == None:
                    exclude_gauge = False
                else:
                    exclude_gauge = self.labels[index] in self.exclude_gauge

                sensor_type = self.types[index]
                self.Sensors[topic] = {"title": self.labels[index], 
                                       "type": sensor_type, 
                                       "units": self.units[index], 
                                       "nominal": self.ConvertToNumber(self.nominal_values[index]),
                                       "max": self.ConvertToNumber(self.max_values[index]),
                                       "exclude_gauge": exclude_gauge,
                                       "from": "genmqttin",
                                       "strict": self.strict}
                GaugeDict = self.Sensors[topic].copy()
                if GaugeDict['type'] in ['ct1','ct2']:
                    GaugeDict['type'] = 'current'
                elif GaugeDict['type'] in ['ctpower1','ctpower2']:
                    GaugeDict['type'] = 'power'
                elif GaugeDict['type'] in ['voltageleg1','voltageleg1']:
                    GaugeDict['type'] = 'voltage'
                self.GaugeData.append(GaugeDict)
                index += 1
        except Exception as e1:
            self.LogErrorLine("Error: parameter validatation failed : " + str(e1))
            sys.exit(1)
        try:
            self.Generator = ClientInterface(host=self.MonitorAddress, port=port, log=log)
            self.GetGeneratorStartInfo()
        except Exception as e1:
            self.LogErrorLine("Error: Can't communicate with genmon: " + str(e1))
            sys.exit(1)
        try:
            # Setup gauges
            if len(self.GaugeData):
                self.SendCommand("generator: set_external_gauge_data=" + json.dumps(self.GaugeData))
        except Exception as e1:
            self.LogErrorLine("Error: Can't setup gauges with genmon: " + str(e1))
            sys.exit(1)
        try:
            self.MQTTclient = mqtt.Client(client_id=self.ClientID)
            if self.Username != None and len(self.Username) and self.Password != None:
                self.MQTTclient.username_pw_set(self.Username, password=self.Password)

            self.MQTTclient.on_connect = self.on_connect
            self.MQTTclient.on_message = self.on_message
            self.MQTTclient.on_disconnect = self.on_disconnect
            self.MQTTclient.on_subscribe = self.on_subscribe

            if len(self.CertificateAuthorityPath):
                if os.path.isfile(self.CertificateAuthorityPath):
                    cert_reqs = ssl.CERT_REQUIRED
                    if self.CertReqs.lower() == "required":
                        cert_reqs = ssl.CERT_REQUIRED
                    elif self.CertReqs.lower() == "optional":
                        cert_reqs = ssl.CERT_REQUIRED
                    elif self.CertReqs.lower() == "none":
                        cert_reqs = ssl.CERT_NONE
                    else:
                        self.LogError(
                            "Error: invalid cert required specified, defaulting to required: "
                            + self.CertReq
                        )

                    use_tls = ssl.PROTOCOL_TLSv1
                    if self.TLSVersion == "1.0" or self.TLSVersion == "1":
                        use_tls = ssl.PROTOCOL_TLSv1
                    elif self.TLSVersion == "1.1":
                        use_tls = ssl.PROTOCOL_TLSv1_1
                    elif self.TLSVersion == "1.2":
                        use_tls = ssl.PROTOCOL_TLSv1_2
                    else:
                        self.LogError(
                            "Error: invalid TLS version specified, defaulting to 1.0: "
                            + self.TLSVersion
                        )
                    certfile = None
                    keyfile = None
                    # strip off any whitespace
                    self.ClientCertificatePath = self.ClientCertificatePath.strip()
                    self.ClientKeyPath = self.ClientKeyPath.strip()
                    # if nothing is there then use None
                    if len(self.ClientCertificatePath):
                        certfile = self.ClientCertificatePath
                    if len(self.ClientKeyPath):
                        keyfile = self.ClientKeyPath

                    self.MQTTclient.tls_set(
                        ca_certs=self.CertificateAuthorityPath,
                        certfile=certfile,
                        keyfile=keyfile,
                        cert_reqs=cert_reqs,
                        tls_version=use_tls,
                    )
                    self.MQTTPort = 8883  # port for SSL
                else:
                    self.LogError("Error: Unable to  find CA cert file: " + self.CertificateAuthorityPath)

            # setup last will and testament
            self.LastWillTopic = self.AppendRoot("generator/client_input_status")
            self.MQTTclient.will_set(self.LastWillTopic, payload="Offline", qos=0, retain=True)
            # connect
            self.LogDebug("Connecting to " + self.MQTTAddress + ":" + str(self.MQTTPort))
            self.MQTTclient.connect(self.MQTTAddress, self.MQTTPort, 60)

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

            self.MQTTclient.loop_start()
        except Exception as e1:
            self.LogErrorLine("Error in MyMQTT init: " + str(e1))
            sys.exit(1)

    # ----------  MyMQTT::ParseStringToList ------------------------------------
    def ParseStringToList(self, input_string):
        try:
        
            if input_string != None and isinstance(input_string, str) and len(input_string):
                InputList = input_string.strip().split(",")
                if len(InputList):
                    ReturnList = []
                    for Items in InputList:
                        ReturnList.append(Items.strip())
                    return ReturnList
                else:
                    self.LogDebug("ParseStringToList: invalid input (1): " + str(input_string))
            else:
                self.LogDebug("ParseStringToList: invalid input: " + str(input_string))
        except Exception as e1:
            self.LogErrorLine("Error in ParseStringToList:" + str(e1) + " : " + input_string)
        return None
    # ----------  MyMQTT::GetGeneratorStartInfo --------------------------------
    def GetGeneratorStartInfo(self):

        try:
            data = self.SendCommand("generator: start_info_json")
            self.StartInfo = {}
            self.StartInfo = json.loads(data)

            return True
        except Exception as e1:
            self.LogErrorLine("Error in GetGeneratorStartInfo: " + str(e1))
            return False

    # ----------  MyGenPush::SendCommand ----------------------------------------
    def SendCommand(self, Command):

        if len(Command) == 0:
            return "Invalid Command"

        try:
            with self.AccessLock:
                data = self.Generator.ProcessMonitorCommand(Command)
        except Exception as e1:
            self.LogErrorLine("Error calling  ProcessMonitorCommand: " + str(Command))
            data = ""

        return data

    # ------------ MyMQTT::AppendRoot-------------------------------------------
    def AppendRoot(self, name):

        if self.TopicRoot != None and len(self.TopicRoot):
            ReturnPath = self.TopicRoot + "/" + str(name)
        else:
            ReturnPath = str(name)
        return ReturnPath

    # ------------ MyMQTT::on_disconnect-----------------------------------------
    def on_disconnect(self, client, userdata, rc=0):

        self.LogInfo("Disconnected from " + self.MQTTAddress + " result code: " + str(rc))
        self.MQTTclient.publish(self.LastWillTopic, payload="Offline", retain=True)

    # ------------ MyMQTT::on_connect--------------------------------------------
    # The callback for when the client receives a CONNACK response from the server.
    def on_connect(self, client, userdata, flags, rc):

        try:
            if rc != 0:
                self.LogError("Error connecting to MQTT server: return code: " + str(rc))
            self.LogInfo("Connected to " + self.MQTTAddress + " result code: " + str(rc))

            # Subscribing in on_connect() means that if we lose the connection and
            # reconnect then subscriptions will be renewed.
            for topic in self.topics:
                self.MQTTclient.subscribe(topic)

            # Setup Last Will value
            self.MQTTclient.publish(self.LastWillTopic, payload="Online", retain=True)

        except Exception as e1:
            self.LogErrorLine("Error in MyMQTT:on_connect: " + str(e1))

    # ------------ MyMQTT::on_message--------------------------------------------
    # The callback for when a PUBLISH message is received from the server.
    def on_message(self, client, userdata, message):

        try:
            value = self.ConvertToNumber(str(message.payload))
            self.LogDebug("on_message: " + message.topic + ": " + str(value))

            topic_data = self.Sensors.get(message.topic, None)
            if topic_data == None:
                self.LogDebug("No topic data found for " + str(message.topic))
            else:
                self.SendData(message.topic, topic_data, value)
            # send data to genmon
            
        except Exception as e1:
            self.LogErrorLine("Error in MyMQTT:on_message: " + str(e1))

    # ------------ MyMQTT::on_subscribe-----------------------------------------
    def on_subscribe(self, client, userdata, mid, qos, properties=None):
        try:
            self.LogDebug("on_subscribe: " + str(client))
        except Exception as e1:
            self.LogErrorLine("Error in MyMQTT:on_subscribe: " + str(e1))

    # ------------ MyMQTT::SendData---------------------------------------------
    def SendData(self, topic, topic_data, value):

        try:
            # Send data to genmon
            self.LastValues[topic] = {"value": value, "topic_data": topic_data}

            if topic_data["type"] in ["ct1","ct2","ctpower1","ctpower2"]:
                JSON_string = self.GetMatchingValue(topic, topic_data, value)
                if JSON_string == None:
                    self.LogDebug("No matching value to send.")
                    return
            else:
                # data should look like this [{label: value units}]
                JSON_string = json.dumps([{topic_data["title"]: "%s %s" % (str(value), topic_data["units"])}])

            self.SendCommand("generator: set_sensor_data=" + JSON_string)
            self.SendPowerData(topic, topic_data, value)
            self.SendTankData(topic, topic_data, value)
            
        except Exception as e1:
            self.LogErrorLine("Error in SendData: " + str(e1) + ": " + str(topic))

    # ------------ MyMQTT::SendTankData-----------------------------------------
    def SendTankData(self, topic, topic_data, value):

        try:
            valid_types = ["fuel"]
            if not self.use_for_power_fuel or not topic_data["type"] in valid_types:
                return
            
            if value > 100 or value < 0:
                self.LogDebug("WARNING in SendTankData: tank percentage is out of range: " + str(value))
            data = {}
            data["Tank Name"] = topic_data["title"]
            data["Percentage"] = value

            self.SendCommand("generator: set_tank_data=" + json.dumps(data))
        except Exception as e1:
            self.LogErrorLine("Error in SendTankData: " + str(e1) + ": " + str(topic))

    # ------------ MyMQTT::SendPowerData----------------------------------------
    def SendPowerData(self, topic, topic_data, value):
        try:
            
            valid_types = ["ct1","ct2","ctpower1","ctpower2","voltageleg1","voltageleg2","current","voltage","power"]
            if not self.use_for_power_fuel or not topic_data["type"] in valid_types:
                # no need to do anything
                return
            
            data = {}
            data['strict'] = self.strict
            data['from'] = "genmqttin"
            data["powerfactor"] = self.powerfactor

            
            if self.UseCT1CT2:
                CT1 = self.GetLastValueFromTopic(self.GetLastMatchingTopic("ct1"))
                CT2 = self.GetLastValueFromTopic(self.GetLastMatchingTopic("ct2"))
                if CT1 != None and CT2 != None:
                    data['ctdata'] = []
                    data['ctdata'].append(int(CT1))
                    data['ctdata'].append(int(CT2))
                    data['current'] = int(CT1 + CT2)
            if self.UseP1P2:
                cttopic = self.GetLastMatchingTopic("ctpower1")
                CTPOWER1 = self.GetLastValueFromTopic(cttopic)
                if CTPOWER1 != None:
                    if self.LastValues[cttopic]['topic_data']['units'].lower() ==  "w":
                        CTPOWER1 = round(float(CTPOWER1) / 1000,3)
                cttopic = self.GetLastMatchingTopic("ctpower2")
                CTPOWER2 = self.GetLastValueFromTopic(cttopic)
                if CTPOWER2 != None:
                    if self.LastValues[cttopic]['topic_data']['units'].lower() ==  "w":
                        CTPOWER2 = round(float(CTPOWER2) / 1000,3)
                if CTPOWER2 != None and CTPOWER2 != None:
                    data['ctpower'] = []
                    data['ctpower'].append(round(float(CTPOWER1),3))
                    data['ctpower'].append(round(float(CTPOWER2),3))
                    data['power'] = round(float(CTPOWER1 + CTPOWER1),3)

            if topic_data['type'] == 'power' and not 'power' in data.keys():
                if topic_data['units'].lower() == 'w':
                    data['power'] = round(float(value) / 1000.0,3)
                else:
                    data['power'] = value

            elif topic_data['type'] == 'current' and not 'current' in data.keys():
                data['current'] = value
            
            if self.UseVoltageLegs:
                VL1 = self.GetLastValueFromTopic(self.GetLastMatchingTopic("voltageleg1"))
                VL2 = self.GetLastValueFromTopic(self.GetLastMatchingTopic("voltageleg2"))
                data['voltagelegs'] = []
                data['voltagelegs'].append(int(VL1))
                data['voltagelegs'].append(int(VL2))
                data['voltage'] = int(VL1 + VL2)

            if topic_data['type'] == 'voltage' and 'voltage' not in data.keys():
                data['voltage'] = value
            
            self.LogDebug(str(data))
            JSON_string = json.dumps(data)
            self.SendCommand("generator: set_power_data=" + JSON_string)
        except Exception as e1:
            self.LogErrorLine("Error in SendPowerData: " + str(e1) + ": " + str(topic))
            
    # ----------MyMQTT::GetMatchingValue----------------------------------------
    def GetMatchingValue(self, topic, topic_data, value):

        try:
            if not topic_data["type"] in ["ct1","ct2","ctpower1","ctpower2"]:
                self.LogDebug("Invalid parameter in GetMatchingValue: " + str(topic))
                return None
            if topic_data["type"] == "ct1":
                matching_type = "ct2"
                matching_topic = self.GetLastMatchingTopic(matching_type)
            elif topic_data["type"] == "ct2":
                matching_type = "ct1"
                matching_topic = self.GetLastMatchingTopic(matching_type)
            elif topic_data["type"] == "ctpower1":
                matching_type = "ctpower2"
                matching_topic = self.GetLastMatchingTopic(matching_type)
            elif topic_data["type"] == "ctpower2":
                matching_type = "ctpower1"
                matching_topic = self.GetLastMatchingTopic(matching_type)
            
            if matching_topic == None:
                return None
            return_list = []
            return_list.append({topic_data["title"]: "%s %s" % (str(value), topic_data["units"])})
            matching_units = self.LastValues[matching_topic]["topic_data"]["units"]
            matching_label = self.LastValues[matching_topic]["topic_data"]["title"]
            matching_value = self.LastValues[matching_topic]["value"]
            return_list.append({matching_label: "%s %s" % (str(matching_value), matching_units)})
            return json.dumps(return_list)
        except Exception as e1:
            self.LogErrorLine("Error in GetMatchingValue: " + str(e1) + ": " + str(topic))
            return None

    # ----------MyMQTT::GetLastValueFromTopic-----------------------------------
    def GetLastValueFromTopic(self, topic):
        try:
            if topic == None:
                return None
            topic_info = self.LastValues.get(topic, None)
            if topic_info == None:
                return None
            return topic_info['value']
        except Exception as e1:
            self.LogErrorLine("Error in GetLastValueFromTopic: " + str(e1) + ": " + str(topic))
            return None

    # ----------MyMQTT::GetLastMatchingTopic------------------------------------
    def GetLastMatchingTopic(self, type_value):
        try:
            # self.LastValues[topic] = {"value": value, "topic_data": topic_data}
            for topic, data in self.LastValues.items():
                if data["topic_data"]["type"] == type_value:
                    return topic
            return None
        except Exception as e1:
            self.LogErrorLine("Error in GetLastMatchingTopic: " + str(e1) + ": " + str(type_value))
            return None
    # ----------MyMQTT::SignalClose---------------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(1)

    # ---------- MyMQTT::Close--------------------------------------------------
    def Close(self):
        self.LogDebug("Exiting MyMQTT")
        self.Exiting = True
        self.Generator.Close()
        self.MQTTclient.loop_stop(force=True)


# -------------------------------------------------------------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("genmqttin")

    InstanceMQTT = MyMQTT(
        host=address,
        port=port,
        log=log,
        loglocation=loglocation,
        configfilepath=ConfigFilePath,
        console=console,
    )

    while not InstanceMQTT.Exiting:
        time.sleep(0.5)

    sys.exit(1)
