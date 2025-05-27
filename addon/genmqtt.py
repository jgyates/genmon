#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: genmqtt.py
# PURPOSE: genmqtt.py is a client interface for a MQTT server / broker
#
#  AUTHOR: jgyates
#    DATE: 08-10-2018
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

# The following is need to install the mqtt module: pip install paho-mqtt

try:
    import paho.mqtt.client as mqtt
except ImportError as e_imp:
    # This is a critical failure if paho-mqtt is missing.
    # Logger might not be available yet, so print to stderr.
    sys.stderr.write(
        "\n\nFATAL ERROR: The paho-mqtt module is required but not installed.\n"
        "Please install it using a command like 'sudo pip install paho-mqtt' or 'pip install paho-mqtt'.\n"
    )
    sys.stderr.write(f"Specific import error: {e_imp}\n")
    sys.exit(2) # Exit if critical dependency is missing.
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

except ImportError as e_imp_genmon:
    # Critical failure if genmonlib components are missing.
    sys.stderr.write(
        "\n\nFATAL ERROR: This program requires the genmonlib modules.\n"
        "These modules should be located in the 'genmonlib' directory, typically one level above the 'addon' directory.\n"
        "Please ensure the genmonlib directory and its contents are correctly placed and accessible.\n"
        "Consult the project documentation at https://github.com/jgyates/genmon for installation details.\n"
    )
    sys.stderr.write(f"Specific import error: {e_imp_genmon}\n")
    sys.exit(2) # Exit if core components are missing.

# ------------ MyGenPush class --------------------------------------------------
class MyGenPush(MySupport):

    # ------------ MyGenPush::init-----------------------------------------------
    def __init__(
        self,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        log=None,
        callback=None,
        polltime=None,
        blacklist=None,
        flush_interval=float("inf"),
        use_numeric=False,
        use_numeric_object=False,
        strlist_json = False,
        debug=False,
        loglocation=ProgramDefaults.LogPath,
        console=None,
    ):

        super(MyGenPush, self).__init__()
        self.Callback = callback

        self.UseNumeric = use_numeric
        self.UseNumericObject = use_numeric_object
        self.StrListJson = strlist_json
        self.debug = debug
        self.Exiting = False

        if polltime == None:
            self.PollTime = 3
        else:
            self.PollTime = float(polltime)

        if log != None:
            self.log = log
        else:
            # log errors in this module to a file
            self.log = SetupLogger("client", os.path.join(loglocation, "mygenpush.log"))

        self.console = console

        self.AccessLock = threading.Lock()
        self.BlackList = blacklist
        self.LastValues = {}
        self.FlushInterval = flush_interval
        self.LastChange = {}

        try:
            self.Generator = ClientInterface(host=host, port=port, log=log)

            self.GetGeneratorStartInfo()
            # start thread to accept incoming sockets for nagios heartbeat
            self.Threads["MainPollingThread"] = MyThread(
                self.MainPollingThread, Name="MainPollingThread", start=False
            )
            self.Threads["MainPollingThread"].Start()

        except (socket.error, ConnectionRefusedError) as e_sock: # More specific for network issues
            self.LogErrorLine(f"MyGenPush.__init__: Socket error connecting to ClientInterface: {e_sock}")
            # Depending on design, might re-raise or set a failed state.
        except Exception as e_init_push: # Catch other unexpected errors
            self.LogErrorLine(f"MyGenPush.__init__: Unexpected error: {e_init_push}")

    # ----------  MyGenPush::ControllerIsEvolution2 -----------------------------
    def ControllerIsEvolution2(self):
        try:
            return "evolution 2.0" in self.StartInfo["Controller"].lower()
        except KeyError:
            self.LogErrorLine("ControllerIsEvolution2: 'Controller' key not found in StartInfo.")
            return False
        except Exception as e_ctrl:
            self.LogErrorLine(f"ControllerIsEvolution2: Unexpected error: {e_ctrl}")
            return False

    # ----------  MyGenPush::ControllerIsEvolutionNexus -------------------------
    def ControllerIsEvolutionNexus(self):
        try:
            # Assuming ControllerIsEvolution and ControllerIsNexus handle their own exceptions
            return self.ControllerIsEvolution() or self.ControllerIsNexus()
        except Exception as e_ctrl_nexus: # Catch if the boolean logic itself fails for some reason
            self.LogErrorLine(f"ControllerIsEvolutionNexus: Unexpected error: {e_ctrl_nexus}")
            return False

    # ----------  MyGenPush::ControllerIsEvolution ------------------------------
    def ControllerIsEvolution(self):
        try:
            return "evolution" in self.StartInfo["Controller"].lower()
        except KeyError:
            self.LogErrorLine("ControllerIsEvolution: 'Controller' key not found in StartInfo.")
            return False
        except Exception as e_ctrl_evo:
            self.LogErrorLine(f"ControllerIsEvolution: Unexpected error: {e_ctrl_evo}")
            return False

    # ----------  MyGenPush::ControllerIsNexius ---------------------------------
    def ControllerIsNexius(self): # Typo: Should be ControllerIsNexus
        try:
            return "nexus" in self.StartInfo["Controller"].lower()
        except KeyError:
            self.LogErrorLine("ControllerIsNexus (was ControllerIsNexius): 'Controller' key not found in StartInfo.")
            return False
        except Exception as e_ctrl_nexus_typo: # Typo in original method name
            self.LogErrorLine(f"ControllerIsNexus (was ControllerIsNexius): Unexpected error: {e_ctrl_nexus_typo}")
            return False

    # ----------  MyGenPush::ControllerIsGeneracH100 ----------------------------
    def ControllerIsGeneracH100(self):
        try:
            controller_name = self.StartInfo["Controller"].lower()
            return "h-100" in controller_name or "g-panel" in controller_name
        except KeyError:
            self.LogErrorLine("ControllerIsGeneracH100: 'Controller' key not found in StartInfo.")
            return False
        except Exception as e_ctrl_h100:
            self.LogErrorLine(f"ControllerIsGeneracH100: Unexpected error: {e_ctrl_h100}")
            return False

    # ----------  MyGenPush::ControllerIsGeneracPowerZone -----------------------
    def ControllerIsGeneracPowerZone(self):
        try:
            return "powerzone" in self.StartInfo["Controller"].lower()
        except KeyError:
            self.LogErrorLine("ControllerIsGeneracPowerZone: 'Controller' key not found in StartInfo.")
            return False
        except Exception as e_ctrl_pz:
            self.LogErrorLine(f"ControllerIsGeneracPowerZone: Unexpected error: {e_ctrl_pz}")
            return False

    # ----------  MyGenPush::GetGeneratorStartInfo ------------------------------
    def GetGeneratorStartInfo(self):
        try:
            data = self.SendCommand("generator: start_info_json")
            if not data: # Check if SendCommand returned empty (indicating an error there)
                self.LogError("GetGeneratorStartInfo: Received no data from SendCommand.")
                return False
            self.StartInfo = json.loads(data) # Removed self.StartInfo = {} before this
            return True
        except json.JSONDecodeError as e_json:
            self.LogErrorLine(f"GetGeneratorStartInfo: Error decoding JSON from genmon: {e_json}. Data: '{data[:100]}...'") # Log part of the data
            return False
        except Exception as e_get_info:
            self.LogErrorLine(f"GetGeneratorStartInfo: Unexpected error: {e_get_info}")
            return False

    # ----------  MyGenPush::SendCommand ----------------------------------------
    def SendCommand(self, Command):
        if not Command: # Check for empty or None command
            self.log.error("SendCommand: Received an invalid (empty) command.")
            return "" # Return empty string for error, consistent with original on exception

        try:
            with self.AccessLock:
                data = self.Generator.ProcessMonitorCommand(Command)
            return data
        except (socket.error, ConnectionRefusedError) as e_sock: # Specific network errors
            self.LogErrorLine(f"SendCommand: Socket error for command '{Command}': {e_sock}")
            return ""
        except Exception as e_send_cmd: # Other errors from ClientInterface
            self.LogErrorLine(f"SendCommand: Unexpected error for command '{Command}': {e_send_cmd}")
            return ""


    # ---------- MyGenPush::MainPollingThread-----------------------------------
    def MainPollingThread(self):

        while True:
            try:

                if not self.UseNumeric and not self.UseNumericObject:
                    statusdata = self.SendCommand("generator: status_json")
                    maintdata = self.SendCommand("generator: maint_json")
                    outagedata = self.SendCommand("generator: outage_json")
                    monitordata = self.SendCommand("generator: monitor_json")
                else:
                    statusdata = self.SendCommand("generator: status_num_json")
                    maintdata = self.SendCommand("generator: maint_num_json")
                    outagedata = self.SendCommand("generator: outage_num_json")
                    monitordata = self.SendCommand("generator: monitor_num_json")

                try:
                    GenmonDict = {}
                    # Helper to load JSON and update GenmonDict, handling potential errors
                    def load_and_assign(key, json_data_str, target_dict):
                        try:
                            if not json_data_str:
                                self.log.warning(f"MainPollingThread: Empty JSON data for '{key}'. Skipping.")
                                return False
                            temp_dict = json.loads(json_data_str)
                            target_dict[key] = temp_dict.get(key, {}) # Use .get for safer access to inner key
                            return True
                        except json.JSONDecodeError as e_json_poll:
                            self.LogErrorLine(f"MainPollingThread: Error decoding JSON for '{key}': {e_json_poll}. Data: '{json_data_str[:100]}...'")
                            return False
                        except KeyError: # If the 'key' itself is not in temp_dict after load
                            self.LogErrorLine(f"MainPollingThread: Expected key '{key}' not found in parsed JSON data. Data: '{json_data_str[:100]}...'")
                            return False


                    load_and_assign("Status", statusdata, GenmonDict)
                    load_and_assign("Maintenance", maintdata, GenmonDict)
                    load_and_assign("Outage", outagedata, GenmonDict)
                    load_and_assign("Monitor", monitordata, GenmonDict)
                    
                    if GenmonDict: # Only proceed if we have some data
                        self.CheckDictForChanges(GenmonDict, "generator")
                    else:
                        self.log.warning("MainPollingThread: GenmonDict is empty after attempting to load all data points. No changes to check.")

                except Exception as e_poll_processing: # Catch-all for the processing block
                    self.LogErrorLine(f"MainPollingThread: Error processing data from genmon: {e_poll_processing}")

                if self.WaitForExit("MainPollingThread", float(self.PollTime)):
                    self.log.info("MainPollingThread: Exit signal received, shutting down.")
                    return
            except Exception as e_outer_poll: # Catch-all for the entire while loop iteration
                self.LogErrorLine(f"MainPollingThread: Unhandled error in polling loop: {e_outer_poll}")
                # Implement a backoff strategy or more robust error handling if this becomes frequent
                if self.WaitForExit("MainPollingThread", float(self.PollTime) * 2): # Longer wait on error
                    self.log.info("MainPollingThread: Exit signal received during error handling, shutting down.")
                    return

    # ------------ MyGenPush::CheckDictForChanges -------------------------------
    # This function is recursive, it will turn a nested dict into a flat dict keys
    # that have a directory structure with corrposonding values and determine if
    # anyting changed. If it has then call our callback function
    def CheckDictForChanges(self, node, PathPrefix):

        CurrentPath = PathPrefix
        if not isinstance(PathPrefix, str):
            return ""

        if isinstance(node, dict):
            for key, item in node.items():
                if isinstance(item, dict):
                    CurrentPath = PathPrefix + "/" + str(key)
                    if self.UseNumericObject and self.DictIsTopicJSON(item):
                        self.CheckForChanges(CurrentPath, json.dumps(item, sort_keys=False))
                    else:
                        self.CheckDictForChanges(item, CurrentPath)
                elif isinstance(item, list):
                    CurrentPath = PathPrefix + "/" + str(key)
                    if self.ListIsStrings(item):
                        if self.StrListJson:
                            self.CheckForChanges(CurrentPath, json.dumps(item, sort_keys=False))
                        else:
                            # if this is a list of strings, the join the list to one comma separated string
                            self.CheckForChanges(CurrentPath, ", ".join(item))
                    else:
                        for listitem in item:
                            if isinstance(listitem, dict):
                                if self.UseNumericObject and self.DictIsTopicJSON(item):
                                    self.CheckForChanges(CurrentPath, json.dumps(item, sort_keys=False))
                                else:
                                    self.CheckDictForChanges(listitem, CurrentPath)
                            else:
                                self.LogError(
                                    "Invalid type in CheckDictForChanges: %s %s (2)"
                                    % (key, str(type(listitem)))
                                )
                else:
                    CurrentPath = PathPrefix + "/" + str(key)
                    self.CheckForChanges(CurrentPath, item)
        else:
            self.LogError("Invalid type in CheckDictForChanges %s " % str(type(node)))

    # ---------- MyGenPush::DictIsTopicJSON-------------------------------------
    def DictIsTopicJSON(self, entry):
        try:
            if not isinstance(entry, dict):
                return False
            if "type" in entry.keys() and "value" in entry.keys() and "unit" in entry.keys():
                return True
            return False
        except Exception as e_dict_topic_json: # More specific exception variable name
            self.LogErrorLine(f"DictIsTopicJSON: Unexpected error: {e_dict_topic_json}")
            return False

    # ---------- MyGenPush::ListIsStrings---------------------------------------
    # return true if every element of list is a string
    def ListIsStrings(self, listinput):
        try:
            if not isinstance(listinput, list):
                return False
            for item in listinput:
                # Simplified check for Python 3, assuming genmon aims for Py3
                if not isinstance(item, (str, bytes)): # bytes for Py3 if applicable, str for unicode
                    return False
            return True
        except Exception as e_list_is_strings: # More specific exception variable name
            self.LogErrorLine(f"ListIsStrings: Unexpected error: {e_list_is_strings}")
            return False

    # ---------- MyGenPush::CheckForChanges-------------------------------------
    def CheckForChanges(self, Path, Value):
        try:
            if self.BlackList is not None: # Use 'is not None' for clarity
                for BlackItem in self.BlackList:
                    if BlackItem.lower() in Path.lower():
                        return # Item is in blacklist, do not process further

            path_str = str(Path) # Ensure Path is a string for dictionary key
            LastValue = self.LastValues.get(path_str) # Simpler .get, defaults to None
            LastChange = self.LastChange.get(path_str, 0) # Default to 0 if not found

            current_time = time.time()
            value_changed = (LastValue is None or LastValue != Value)
            flush_interval_exceeded = (current_time - LastChange) >= self.FlushInterval # Use >= for flush

            if value_changed or flush_interval_exceeded:
                self.LastValues[path_str] = Value
                self.LastChange[path_str] = current_time # Update timestamp
                if self.Callback is not None:
                    try:
                        self.Callback(path_str, Value)
                    except Exception as e_callback: # Catch errors within the callback itself
                        self.LogErrorLine(f"CheckForChanges: Error executing callback for path '{path_str}': {e_callback}")
        except Exception as e_check_changes: # Catch any other unexpected error in this method
            self.LogErrorLine(f"CheckForChanges: Unexpected error for path '{Path}': {e_check_changes}")

    # ---------- MyGenPush::Close-----------------------------------------------
    def Close(self):
        self.Exiting = True
        self.KillThread("MainPollingThread")
        self.Generator.Close()


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
        self.BlackList = None
        self.UseNumeric = False
        self.StringListJson = False
        self.RemoveSpaces = False
        self.Retain = False
        self.PollTime = 2
        self.FlushInterval = float(
            "inf"
        )  # default to inifite flush interval (e.g., never)
        self.debug = False
        config_file_path = os.path.join(configfilepath, "genmqtt.conf")

        try:
            config = MyConfig(
                filename=config_file_path,
                section="genmqtt",
                log=self.log, # Pass own logger
            )

            self.Username = config.ReadValue("username", default=None) # Default to None if not present
            self.Password = config.ReadValue("password", default=None) # Default to None
            self.ClientID = config.ReadValue("client_id", default="genmon")
            self.MQTTAddress = config.ReadValue("mqtt_address", default=None)

            if not self.MQTTAddress: # Check if None or empty
                err_msg = "MyMQTT.__init__: Critical error: MQTT server address (mqtt_address) not configured in genmqtt.conf."
                self.log.error(err_msg)
                if self.console: self.console.error(err_msg)
                sys.exit(1) # Critical: cannot function without MQTT address

            self.MonitorAddress = config.ReadValue("monitor_address", default=host) # Use passed host as default
            if self.MonitorAddress: self.MonitorAddress = self.MonitorAddress.strip()
            if not self.MonitorAddress: self.MonitorAddress = ProgramDefaults.LocalHost # Final fallback

            self.MQTTPort = config.ReadValue("mqtt_port", return_type=int, default=1883)
            self.PollTime = config.ReadValue("poll_interval", return_type=float, default=2.0)
            self.UseNumeric = config.ReadValue("numeric_json", return_type=bool, default=False)
            self.UseNumericObject = config.ReadValue("numeric_json_object", return_type=bool, default=False)
            self.StringListJson = config.ReadValue("strlist_json", return_type=bool, default=False)
            self.RemoveSpaces = config.ReadValue("remove_spaces", return_type=bool, default=False)
            self.TopicRoot = config.ReadValue("root_topic", default=None)
            self.Retain = config.ReadValue("retain", return_type=bool, default=False)

            if self.TopicRoot:
                self.TopicRoot = self.TopicRoot.strip()
                if not self.TopicRoot: self.TopicRoot = None # Set to None if empty after strip
                else: self.LogDebug(f"Root Topic set to: {self.TopicRoot}")
            
            self.CertificateAuthorityPath = config.ReadValue("cert_authority_path", default="").strip()
            self.TLSVersion = config.ReadValue("tls_version", return_type=str, default="1.2") # Default to modern TLS
            self.CertReqs = config.ReadValue("cert_reqs", return_type=str, default="CERT_REQUIRED") # Match ssl const
            self.ClientCertificatePath = config.ReadValue("client_cert_path", default="").strip()
            self.ClientKeyPath = config.ReadValue("client_key_path", default="").strip()
            
            BlackList_str = config.ReadValue("blacklist", default="")
            if BlackList_str:
                self.BlackList = [item.strip() for item in BlackList_str.split(",") if item.strip()]
            else:
                self.BlackList = None

            self.debug = config.ReadValue("debug", return_type=bool, default=False)
            self.FlushInterval = config.ReadValue("flush_interval", return_type=float, default=0.0)
            if self.FlushInterval <= 0: # 0 or negative means effectively infinite
                self.FlushInterval = float("inf")

        except FileNotFoundError:
            err_msg = f"MyMQTT.__init__: Configuration file '{config_file_path}' not found. Cannot proceed."
            self.log.error(err_msg)
            if self.console: self.console.error(err_msg)
            sys.exit(1)
        except (KeyError, ValueError) as e_conf: # Catch issues from MyConfig reading or type conversion
            err_msg = f"MyMQTT.__init__: Error reading configuration from '{config_file_path}': {e_conf}"
            self.LogErrorLine(err_msg) # Use LogErrorLine if available for more detail
            if self.console: self.console.error(err_msg)
            sys.exit(1)
        except Exception as e_conf_generic: # Catch-all for other config errors
            err_msg = f"MyMQTT.__init__: Unexpected error processing configuration file '{config_file_path}': {e_conf_generic}"
            self.LogErrorLine(err_msg)
            if self.console: self.console.error(err_msg)
            sys.exit(1)

        try:
            self.MQTTclient = mqtt.Client(client_id=self.ClientID)
            if self.Username and self.Password: # Ensure both are not None or empty
                self.MQTTclient.username_pw_set(self.Username, password=self.Password)

            self.MQTTclient.on_connect = self.on_connect
            self.MQTTclient.on_message = self.on_message
            self.MQTTclient.on_disconnect = self.on_disconnect

            if self.CertificateAuthorityPath:
                if os.path.isfile(self.CertificateAuthorityPath):
                    cert_req_map = {
                        "CERT_REQUIRED": ssl.CERT_REQUIRED,
                        "CERT_OPTIONAL": ssl.CERT_OPTIONAL,
                        "CERT_NONE": ssl.CERT_NONE,
                    }
                    cert_reqs_val = cert_req_map.get(self.CertReqs.upper(), ssl.CERT_REQUIRED)
                    if self.CertReqs.upper() not in cert_req_map:
                        self.log.warning(f"Invalid cert_reqs value '{self.CertReqs}', defaulting to CERT_REQUIRED.")

                    tls_version_map = {
                        "1.0": ssl.PROTOCOL_TLSv1, # Note: TLSv1 and v1.1 are deprecated by many brokers
                        "1.1": ssl.PROTOCOL_TLSv1_1,
                        "1.2": ssl.PROTOCOL_TLSv1_2,
                        # "auto": ssl.PROTOCOL_TLS_CLIENT # Python 3.6+ for auto-negotiation
                    }
                    # Prefer PROTOCOL_TLS_CLIENT if available (Python 3.6+) for auto-negotiation
                    use_tls_protocol = tls_version_map.get(self.TLSVersion, ssl.PROTOCOL_TLSv1_2) # Default to 1.2
                    if self.TLSVersion.lower() == "auto" and hasattr(ssl, "PROTOCOL_TLS_CLIENT"):
                        use_tls_protocol = ssl.PROTOCOL_TLS_CLIENT
                    elif self.TLSVersion.lower() not in tls_version_map and self.TLSVersion.lower() != "auto":
                         self.log.warning(f"Invalid TLS version '{self.TLSVersion}', defaulting to TLSv1.2.")
                    
                    effective_certfile = self.ClientCertificatePath if self.ClientCertificatePath else None
                    effective_keyfile = self.ClientKeyPath if self.ClientKeyPath else None

                    self.MQTTclient.tls_set(
                        ca_certs=self.CertificateAuthorityPath,
                        certfile=effective_certfile,
                        keyfile=effective_keyfile,
                        cert_reqs=cert_reqs_val,
                        tls_version=use_tls_protocol,
                    )
                    self.MQTTPort = 8883 # Typically SSL uses port 8883
                    self.log.info(f"TLS configured for MQTT connection using CA: {self.CertificateAuthorityPath}")
                else:
                    self.log.error(f"MyMQTT.__init__: TLS CA certificate file not found: '{self.CertificateAuthorityPath}'. TLS will not be used.")
            
            # Last Will and Testament
            self.LastWillTopic = self.AppendRoot("generator/client_status")
            self.MQTTclient.will_set(self.LastWillTopic, payload="Offline", qos=1, retain=True) # QoS 1 for LWT

            self.log.info(f"Attempting to connect to MQTT broker at {self.MQTTAddress}:{self.MQTTPort} with client ID '{self.ClientID}'")
            self.MQTTclient.connect(self.MQTTAddress, self.MQTTPort, keepalive=60)

            self.Push = MyGenPush( # Assuming MyGenPush is already refactored
                host=self.MonitorAddress, log=self.log, callback=self.PublishCallback,
                polltime=self.PollTime, blacklist=self.BlackList, flush_interval=self.FlushInterval,
                use_numeric=self.UseNumeric, use_numeric_object=self.UseNumericObject,
                strlist_json=self.StringListJson, debug=self.debug, port=port, # port was from __main__
                loglocation=loglocation, console=self.console
            )

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

            self.MQTTclient.loop_start() # Start network loop
            self.log.info("MyMQTT initialization complete and MQTT loop started.")

        except mqtt.MQTTException as e_mqtt: # paho-mqtt specific exceptions
            err_msg = f"MyMQTT.__init__: MQTT client error: {e_mqtt}"
            self.LogErrorLine(err_msg)
            if self.console: self.console.error(err_msg)
            sys.exit(1)
        except (socket.error, ConnectionRefusedError, TimeoutError) as e_sock: # Network related errors
            err_msg = f"MyMQTT.__init__: Network error during MQTT setup/connect: {e_sock}"
            self.LogErrorLine(err_msg)
            if self.console: self.console.error(err_msg)
            sys.exit(1)
        except Exception as e_init_main: # Catch-all for other unexpected errors during init
            err_msg = f"MyMQTT.__init__: Unexpected critical error during initialization: {e_init_main}"
            self.LogErrorLine(err_msg)
            if self.console: self.console.error(err_msg)
            sys.exit(1)

    # ------------ MyMQTT::AppendRoot---------------------------------------
    def AppendRoot(self, name):

        if self.TopicRoot != None and len(self.TopicRoot):
            ReturnPath = self.TopicRoot + "/" + str(name)
        else:
            ReturnPath = str(name)
        return ReturnPath

    # ------------ MyMQTT::PublishCallback---------------------------------------
    # Callback to publish data via MQTT
    def PublishCallback(self, name, value):

        try:
            FullPath = self.AppendRoot(name)

            if self.RemoveSpaces:
                FullPath = FullPath.replace(" ", "_")

            if self.debug:
                self.LogDebug(
                    "Publish: " + FullPath + ": " + str(value) + " (Type: " + str(type(value)) + ")"
                )

            # publish() can raise ValueError for invalid topic/payload, or MQTTException for disconnections
            self.MQTTclient.publish(FullPath, value, retain=self.Retain)
        except mqtt.MQTTException as e_mqtt_pub:
            self.LogErrorLine(f"MyMQTT.PublishCallback: MQTT error publishing to '{FullPath}': {e_mqtt_pub}")
            # Optionally, attempt to reconnect or queue message if applicable
        except ValueError as ve_pub:
            self.LogErrorLine(f"MyMQTT.PublishCallback: ValueError publishing to '{FullPath}' (likely invalid topic/payload): {ve_pub}")
        except Exception as e_pub_generic:
            self.LogErrorLine(f"MyMQTT.PublishCallback: Unexpected error publishing to '{FullPath}': {e_pub_generic}")

    # ------------ MyMQTT::on_disconnect-----------------------------------------
    def on_disconnect(self, client, userdata, rc=0):
        # rc is usually 0 for planned disconnect, non-zero for unplanned.
        if rc == 0:
            self.log.info(f"MyMQTT.on_disconnect: Gracefully disconnected from {self.MQTTAddress}.")
        else:
            self.log.warning(f"MyMQTT.on_disconnect: Unexpectedly disconnected from {self.MQTTAddress}. Result code: {rc}. Will attempt to reconnect.")
        # The LWT should be handled by the broker. Re-publishing here might not be standard.
        # However, if explicit state update is desired upon reconnect, it's done in on_connect.
        # self.MQTTclient.publish(self.LastWillTopic, payload="Offline", retain=True) # Broker handles LWT

    # ------------ MyMQTT::on_connect--------------------------------------------
    # The callback for when the client receives a CONNACK response from the server.
    def on_connect(self, client, userdata, flags, rc):
        try:
            # Connection return codes (rc) defined by Paho MQTT:
            # 0: Connection successful
            # 1: Connection refused - incorrect protocol version
            # 2: Connection refused - invalid client identifier
            # 3: Connection refused - server unavailable
            # 4: Connection refused - bad username or password
            # 5: Connection refused - not authorised
            # 6-255: Currently unused.
            connack_messages = {
                0: "Connection successful",
                1: "Connection refused - incorrect protocol version",
                2: "Connection refused - invalid client identifier",
                3: "Connection refused - server unavailable",
                4: "Connection refused - bad username or password",
                5: "Connection refused - not authorised",
            }
            log_msg = connack_messages.get(rc, f"Connection attempt returned unknown code: {rc}")

            if rc == 0:
                self.log.info(f"MyMQTT.on_connect: Successfully connected to MQTT broker at {self.MQTTAddress}. {log_msg}")
                
                # Subscribe to command topic
                command_topic_suffix = "generator/command"
                full_command_topic = self.AppendRoot(command_topic_suffix)
                try:
                    # Using QoS 1 for command subscription for some reliability
                    (result, mid) = self.MQTTclient.subscribe(full_command_topic + "/#", qos=1) 
                    if result == mqtt.MQTT_ERR_SUCCESS:
                        self.log.info(f"MyMQTT.on_connect: Successfully subscribed to command topic '{full_command_topic}/#'. MID: {mid}")
                    else:
                        self.log.error(f"MyMQTT.on_connect: Failed to subscribe to command topic '{full_command_topic}/#'. Result code: {result}")
                except mqtt.MQTTException as e_sub:
                    self.LogErrorLine(f"MyMQTT.on_connect: MQTT error during subscription to '{full_command_topic}/#': {e_sub}")
                
                # Publish online status (retained)
                try:
                    self.MQTTclient.publish(self.LastWillTopic, payload="Online", qos=1, retain=True)
                    self.log.info(f"MyMQTT.on_connect: Published 'Online' status to LWT topic '{self.LastWillTopic}'.")
                except mqtt.MQTTException as e_pub_online:
                     self.LogErrorLine(f"MyMQTT.on_connect: MQTT error publishing 'Online' status: {e_pub_online}")
            else:
                self.log.error(f"MyMQTT.on_connect: Failed to connect to MQTT broker at {self.MQTTAddress}. {log_msg}")
                # Consider if a retry mechanism or exit is needed here depending on rc for persistent failures

        except Exception as e_on_connect_generic: # Catch any other unexpected error
            self.LogErrorLine(f"MyMQTT.on_connect: Unexpected error: {e_on_connect_generic}")

    # ------------ MyMQTT::on_message--------------------------------------------
    # The callback for when a PUBLISH message is received from the server.
    def on_message(self, client, userdata, message):
        try:
            payload_str = ""
            try:
                payload_str = message.payload.decode("utf-8")
            except UnicodeDecodeError as ude:
                self.LogErrorLine(f"MyMQTT.on_message: Could not decode payload from topic '{message.topic}' as UTF-8: {ude}. Payload (raw): {message.payload[:50]}...")
                return # Cannot process if payload is not valid UTF-8

            if self.debug:
                self.LogDebug(f"MyMQTT.on_message: Received message on topic '{message.topic}': '{payload_str}'")
            
            command_topic_suffix = "generator/command"
            full_command_topic_base = self.AppendRoot(command_topic_suffix)

            # Check if the message topic matches the expected command topic structure
            # (e.g., root/generator/command or root/generator/command/specific_command)
            if not message.topic.lower().startswith(full_command_topic_base.lower()):
                if self.debug:
                    self.LogDebug(f"MyMQTT.on_message: Message on topic '{message.topic}' is not a command topic. Ignoring.")
                return

            # Extract the command part from the payload
            command = payload_str.strip()
            if command: # Ensure command is not empty after stripping
                self.log.info(f"MyMQTT.on_message: Received command '{command}' on topic '{message.topic}'. Forwarding to genmon.")
                # Assuming self.Push.SendCommand handles its own errors robustly
                self.Push.SendCommand(f"generator: {command}") 
                # self.LogDebug(f"Command '{command}' sent to genmon via SendCommand.") # Already logged by SendCommand potentially
            else:
                self.log.warning(f"MyMQTT.on_message: Received empty command payload on topic '{message.topic}'. Ignoring.")
        
        except Exception as e_on_msg_generic: # Catch any other unexpected error
            self.LogErrorLine(f"MyMQTT.on_message: Unexpected error processing message from topic '{message.topic if message else 'N/A'}': {e_on_msg_generic}")

    # ----------MyMQTT::SignalClose---------------------------------------------
    def SignalClose(self, signum, frame):

        self.Close()
        sys.exit(1)

    # ---------- MyMQTT::Close--------------------------------------------------
    def Close(self):
        self.LogDebug("Exiting MyMQTT")
        self.Exiting = True
        self.Push.Close()
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
    ) = MySupport.SetupAddOnProgram("genmqtt")

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
