#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: gensnmp.py
# PURPOSE: gensnmp.py add SNMP support to genmon
#
#  AUTHOR: jgyates
#    DATE: 09-12-2019
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------


import json
import os
import signal
import sys
import threading
import time

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

try:

    import bisect
    import time

    from pyasn1.codec.ber import decoder, encoder
    from pysnmp.carrier.asyncore.dgram import udp, udp6, unix
    from pysnmp.carrier.asyncore.dispatch import AsyncoreDispatcher
    from pysnmp.proto import api
    from pysnmp.proto.rfc1902 import ObjectIdentifier, TimeTicks
    from pysnmp.proto.rfc1902 import *
except Exception as e1:
    print("Error loading pysnmp! :" + str(e1))
    sys.exit(2)

# requires:
#    sudo pip install pysnmp
#
# ------------ MyOID class ------------------------------------------------------
class MyOID(MySupport):
    def __init__(
        self,
        name,
        return_type=None,
        description=None,
        default=None,
        keywords=[],
        log=None,
    ):
        self.log = log
        self.name = name
        self.description = description
        self.return_type = return_type
        self.value = default
        self.keywords = keywords
        self.birthday = time.time()
        if return_type == str:
            pass
        elif return_type == int:
            pass
        else:
            pass

    def __eq__(self, other):
        return self.name == other

    def __ne__(self, other):
        return self.name != other

    def __lt__(self, other):
        return self.name < other

    def __le__(self, other):
        return self.name <= other

    def __gt__(self, other):
        return self.name > other

    def __ge__(self, other):
        return self.name >= other

    def __call__(self, protoVer):

        try:
            if self.return_type == str:
                return api.protoModules[protoVer].OctetString(self.value)
            elif self.return_type == int:
                return api.protoModules[protoVer].Integer(self.value)
            elif self.return_type == ObjectIdentifier:
                return api.protoModules[protoVer].ObjectIdentifier(self.value)
            elif self.return_type == TimeTicks:
                return api.protoModules[protoVer].TimeTicks(
                    (time.time() - self.birthday) * 100
                )
            else:
                self.LogError("Invalid type in MyOID: " + str(self.return_type))
                return api.protoModules[protoVer].Integer(self.value)
        except Exception as e1:
            self.LogError("Error: " + str(self.keywords) + ": " + str(self.value))
            self.LogErrorLine("Error in MyOid __call__: " + str(e1))
            return None


# ------------ GenSNMP class ----------------------------------------------------
class GenSNMP(MySupport):

    # ------------ GenSNMP::init-------------------------------------------------
    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath=MyCommon.DefaultConfPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        console=None,
    ):

        super(GenSNMP, self).__init__()

        self.AccessLock = threading.Lock()

        self.log = log
        self.console = console

        self.IPv6 = True
        self.mibData = []
        self.LastValues = {}
        self.transportDispatcher = None

        self.UseNumeric = False
        self.MonitorAddress = host
        self.debug = False
        self.PollTime = 1
        self.BlackList = []  # ["Monitor","Outage"]
        configfile = os.path.join(ConfigFilePath, "gensnmp.conf")
        try:
            if not os.path.isfile(configfile):
                self.LogConsole("Missing config file : " + configfile)
                self.LogError("Missing config file : " + configfile)
                sys.exit(1)

            self.genmon_config = MyConfig(
                filename=os.path.join(ConfigFilePath, "genmon.conf"),
                section="GenMon",
                log=self.log,
            )
            self.ControllerSelected = self.genmon_config.ReadValue("controllertype", default="generac_evo_nexus")

            if self.ControllerSelected.strip() == "":
                self.ControllerSelected = "generac_evo_nexus"

            self.CustomControllerConfigFile = self.genmon_config.ReadValue("import_config_file", default=None)

            self.config = MyConfig(filename=configfile, section="gensnmp", log=self.log)

            self.UseNumeric = self.config.ReadValue("use_numeric", return_type=bool, default=False)
            self.UseIntegerValues = self.config.ReadValue("use_integer", return_type=bool, default=False)
            self.PollTime = self.config.ReadValue("poll_frequency", return_type=float, default=1)
            self.debug = self.config.ReadValue("debug", return_type=bool, default=False)
            self.community = self.config.ReadValue("community", default="public")
            self.enterpriseID = self.config.ReadValue("enterpriseid", return_type=int, default=58399)
            self.baseOID = (1, 3, 6, 1, 4, 1, self.enterpriseID)
            self.snmpport = self.config.ReadValue("snmpport", return_type=int, default=161)
            # this is the snmp id used to populate user defined data in the snmp schema 
            # the value after the enterprise ID is the externaldata ID
            # if the file userdefined.json is in the ./genmon/data/mib folder, user defined 
            # data on the Monitor page of the UI will be assigned SNMP data per the json file 
            # in the mib folder
            self.externaldataID = self.config.ReadValue("externaldataid", return_type=int, default=99)

            if self.UseIntegerValues:
                self.UseNumeric = True

            if self.MonitorAddress != None:
                self.MonitorAddress = self.MonitorAddress.strip()

            if self.MonitorAddress == None or not len(self.MonitorAddress):
                self.MonitorAddress = ProgramDefaults.LocalHost

        except Exception as e1:
            self.LogErrorLine("Error reading " + configfile + ": " + str(e1))
            self.LogConsole("Error reading " + configfile + ": " + str(e1))
            sys.exit(1)

        try:

            self.Generator = ClientInterface(host=self.MonitorAddress, port=port, log=self.log)

            self.GetGeneratorStartInfo()

            # start thread monitor time for exercise
            self.Threads["SNMPThread"] = MyThread(self.SNMPThread, Name="SNMPThread", start=False)
            self.Threads["SNMPThread"].Start()

            signal.signal(signal.SIGTERM, self.SignalClose)
            signal.signal(signal.SIGINT, self.SignalClose)

            self.SetupSNMP()  # Must be last since we do not return from this call

        except Exception as e1:
            self.LogErrorLine("Error in GenSNMP init: " + str(e1))
            self.LogConsole("Error in GenSNMP init: " + str(e1))
            sys.exit(1)

    # ----------  GenSNMP::ControllerIsEvolutionNexus --------------------------------
    def ControllerIsEvolutionNexus(self):
        try:
            if (
                "evolution" in self.StartInfo["Controller"].lower()
                or "nexus" in self.StartInfo["Controller"].lower()
            ):
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in ControllerIsEvolutionNexus: " + str(e1))
            return False

    # ----------  GenSNMP::ControllerIsGeneracH100 ------------------------------
    def ControllerIsGeneracH100(self):
        try:
            if (
                "h-100" in self.StartInfo["Controller"].lower()
                or "g-panel" in self.StartInfo["Controller"].lower()
            ):
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in ControllerIsGeneracH100: " + str(e1))
            return False

    # ----------  GenSNMP::ControllerIsGeneracPowerZone -------------------------
    def ControllerIsGeneracPowerZone(self):
        try:
            if "powerzone" in self.StartInfo["Controller"].lower():
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in ControllerIsPowerZone: " + str(e1))
            return False
    # ----------  GenSNMP::ControllerIsCustom ----------------------------------
    def ControllerIsCustom(self):
        try:
            if "custom" in self.StartInfo["Controller"].lower():
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in ControllerIsCustom: " + str(e1))
            return False

    # ----------  GenSNMP::GetGeneratorStartInfo --------------------------------
    def GetGeneratorStartInfo(self):

        try:
            data = self.SendCommand("generator: start_info_json")
            self.StartInfo = {}
            self.StartInfo = json.loads(data)

            return True
        except Exception as e1:
            self.LogErrorLine("Error in GetGeneratorStartInfo: " + str(e1))
            return False

    # ----------  GenSNMP::UpdateSNMPData ----------------------------------------
    def UpdateSNMPData(self, Path, Value):

        try:
            if self.transportDispatcher == None:
                return
            oid = self.GetOID(Path)
            if oid == None:
                return
            self.LogDebug(Path + " : " + str(Value) + ", type= " + str(self.mibDataIdx[oid].return_type))
            if self.mibDataIdx[oid].return_type == str:
                self.mibDataIdx[oid].value = str(Value)
            elif self.mibDataIdx[oid].return_type == int:
                if isinstance(Value, int):
                    self.mibDataIdx[oid].value = Value
                else:
                    try:
                        # this will convert a float string to an int
                        Value = float(self.removeAlpha(Value))
                        self.mibDataIdx[oid].value = int(Value)
                    except:
                        self.mibDataIdx[oid].value = int(self.removeAlpha(Value))
            else:
                self.LogError(
                    "Invalid type in UpdateSNMPData: "
                    + str(self.mibDataIdx[oid].return_type)
                )
                self.mibDataIdx[oid].value = Value
        except Exception as e1:
            self.LogError("Error: " + Path + " : " + str(Value) + ", type= " + str(self.mibDataIdx[oid].return_type))
            self.LogErrorLine("Error in UpdateSNMPData: " + str(e1))

    # ----------  GenSNMP::GetOID -----------------------------------------------
    def GetOID(self, path):
        try:
            if not len(path):
                return None

            for mib in self.mibData:
                if len(mib.keywords):
                    if all(x in path for x in mib.keywords):
                        self.LogDebug(str(mib.name))
                        return mib.name
            return None

        except Exception as e1:
            self.LogErrorLine("Error in GetOID: " + str(e1))

    # ----------  GenSNMP::GetData ----------------------------------------------
    def GetData(self, namelist):

        try:
            if not len(namelist):
                return None

            for key in self.LastValues.keys():
                if all(x in key for x in namelist):
                    return self.LastValues[key]
            return None
        except Exception as e1:
            self.LogErrorLine("Error in GetData: " + str(e1))

    # ----------  GenSNMP::AddOID -----------------------------------------------
    def AddOID(self, id, return_type, description, default, keywords):

        self.mibData.append(
            MyOID(
                self.baseOID + id,
                return_type,
                description,
                default,
                keywords,
                log=self.log,
            )
        )

    # -------------CustomController:ReadJSONConfig------------------------------
    def ReadJSONConfig(self, FileName):

        if os.path.isfile(FileName):
            try:
                with open(FileName) as infile:
                    return json.load(infile)
            except Exception as e1:
                self.LogErrorLine("Error in ReadJSONConfig: Error in GetConfig reading config import file: " + str(e1) + ": " + str(FileName))
                return None
        else:
            self.LogError("Error reading config import file in ReadJSONConfig: " + str(FileName))
            return None

    # ----------  GenSNMP::SetupSNMP -------------------------------------------
    def SetupSNMP(self):

        try:
            if (self.ControllerIsEvolutionNexus() or self.ControllerSelected == "generac_evo_nexus"):
                self.ControllerSelected = "generac_evo_nexus"
                CtlID = 1
            elif self.ControllerIsGeneracH100() or self.ControllerSelected == "h_100":
                self.ControllerSelected = "h_100"
                CtlID = 2
            elif (self.ControllerIsGeneracPowerZone() or self.ControllerSelected == "powerzone"):
                self.ControllerSelected = "powerzone"
                CtlID = 3
            elif (self.ControllerIsCustom() or self.ControllerSelected == "custom"):
                self.ControllerSelected = "custom"
                CtlID = 4
            else:
                ## TODO add custom controller check and file name here
                self.LogError("Error: Invalid controller type")
                self.LogError(str(self.ControllerSelected))
                return

            # Base OIDs required for core functionality
            self.mibData.append(
                MyOID(
                    (1, 3, 6, 1, 2, 1, 1, 1, 0),
                    return_type=str,
                    description="SysDescr",
                    default="Genmon Generator Monitor",
                    log=self.log,
                )
            )
            self.mibData.append(
                MyOID(
                    (1, 3, 6, 1, 2, 1, 1, 2, 0),
                    return_type=ObjectIdentifier,
                    description="OID",
                    default=".1.3.6.1.4.1." + str(self.enterpriseID),
                    log=self.log,
                )
            )
            self.mibData.append(
                MyOID(
                    (1, 3, 6, 1, 2, 1, 1, 3, 0),
                    return_type=TimeTicks,
                    description="Uptime",
                    log=self.log,
                )
            )
            # assumed to be ~/genmon/data/mib
            self.GenmonSNMPConfigFileName = os.path.join(
                os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
                "data",
                "mib",
                "genmon.json",
            )

            self.LogDebug(self.GenmonSNMPConfigFileName)

            self.GenmonSNMP = self.ReadJSONConfig(self.GenmonSNMPConfigFileName)
            if self.GenmonSNMP == None:
                self.LogError("Fatal Error: Unable to get base SNMP config data from " + self.GenmonSNMPConfigFileName)
                return 
            
            if "genmon" != self.GenmonSNMP["controller_type"]:
                self.LogError("Fatal Error: Invalid data (genmon) in " + self.GenmonSNMPConfigFileName)
                return 
        
            ## custom controller check and file name here
            if (self.ControllerIsCustom() or self.ControllerSelected == "custom"):
                ControllerFileName = self.CustomControllerConfigFile
            else:
                ControllerFileName = self.ControllerSelected + ".json"

            self.ControllerSNMPConfigFileName = os.path.join(
                os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
                "data",
                "mib",
                ControllerFileName,
            )
            self.LogDebug(self.ControllerSNMPConfigFileName)
            self.ControllerSNMP = self.ReadJSONConfig(self.ControllerSNMPConfigFileName)
            if self.ControllerSNMP == None:
                self.LogError("Fatal Error: Unable to get base controller SNMP config data from " + self.ControllerSNMPConfigFileName)
                return 

            ## TODO add custom controller check and file name here
            if self.ControllerSelected != self.ControllerSNMP["controller_type"]:
                self.LogError("Fatal Error: Invalid data (controller) in " + self.ControllerSNMPConfigFileName)
                return 

            # setup OIDs for genmon specific entries (not controller specific entries)
            if not self.SetSNMPData(self.GenmonSNMP, "genmon"):
                self.LogError("Error parsing genmon SNMP data, exiting ")
                return 
            
            if not self.SetSNMPData(self.ControllerSNMP, "controller", ControllerID = CtlID):
                self.LogError("Error parsing controller SNMP data, exiting")
                return 
        
            
                        # assumed to be ~/genmon/data/mib
            self.UserDefinedSNMPConfigFileName = os.path.join(
                os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
                "data",
                "mib",
                "userdefined.json",
            )
            # is there a userdefined.json file in ./genmon/data/mib ?
            if os.path.isfile(self.UserDefinedSNMPConfigFileName):
                self.LogDebug(self.UserDefinedSNMPConfigFileName)
                self.UserDefinedSNMP = self.ReadJSONConfig(self.UserDefinedSNMPConfigFileName)
                if self.UserDefinedSNMP == None:
                    self.LogError("Fatal Error: Unable to get base controller SNMP config data from " + self.ControllerSNMPConfigFileName)
                    return 
                if not self.SetSNMPData(self.UserDefinedSNMP, "user defined", ControllerID = self.externaldataID):
                    self.LogError("Error parsing user defined SNMP data, exiting")
                    return

            self.mibDataIdx = {}
            for mibVar in self.mibData:
                self.mibDataIdx[mibVar.name] = mibVar

            self.transportDispatcher = AsyncoreDispatcher()
            self.transportDispatcher.registerRecvCbFun(self.SnmpCallbackFunction)

            # UDP/IPv4
            self.transportDispatcher.registerTransport(
                udp.domainName,
                udp.UdpSocketTransport().openServerMode(("0.0.0.0", self.snmpport)),
            )

            # UDP/IPv6
            try:
                self.transportDispatcher.registerTransport(
                    udp6.domainName,
                    udp6.Udp6SocketTransport().openServerMode(("::", self.snmpport)),
                )
            except:
                self.LogError("Warning IPv6 is disabled")
                self.IPv6 = False

            ## Local domain socket
            # self.transportDispatcher.registerTransport(
            #    unix.domainName, unix.UnixSocketTransport().openServerMode('/tmp/snmp-agent')
            # )

            self.transportDispatcher.jobStarted(1)

            try:
                # Dispatcher will never finish as job#1 never reaches zero
                if self.transportDispatcher != None:
                    self.transportDispatcher.runDispatcher()
            except Exception as e1:
                self.SnmpClose()
                if self.transportDispatcher != None:
                    self.LogErrorLine("Fatal Error in SetupSNMP: " + str(e1))
                else:
                    # we are exiting
                    self.LogDebug("Exit Snmp Engine")

        except Exception as e1:
            self.LogErrorLine("Error in SetupSNMP: " + str(e1))
            self.SnmpClose()

    # ----------  GenSNMP::SetSNMPData -----------------------------------------
    def SetSNMPData(self, config_dict, name, ControllerID = None):

        try:
            self.LogDebug(name + ": " + str(len(config_dict["snmp"])))
            for entry in config_dict["snmp"]:
                return_type = str
                if entry["return_type"].lower() == "str":
                    return_type = str
                elif entry["return_type"].lower() == "int":
                    return_type = int
                else:
                    self.LogError(f"Error: invalid return type in {name} config")
                    return_type = str
                if self.UseIntegerValues and "integer" in entry and entry["integer"] == True:
                    self.LogDebug("Int set for " + str(entry["keywords"]))
                    return_type = int
                    default = 0
                else:
                    default = entry["default"]
                OID = list(eval(entry["oid"]))
                if ControllerID != None:
                    OID.insert(0,ControllerID)
                self.AddOID(tuple(OID), return_type, entry["description"], default,entry["keywords"])
            return True
        except Exception as e1:
            self.LogErrorLine(f"Error parsing {name} SNMP data: " + str(e1))
            return False
        
    # ----------  GenSNMP::SnmpClose -------------------------------------------
    def SnmpClose(self):

        try:
            if self.transportDispatcher != None:
                self.transportDispatcher.jobFinished(1)
                self.transportDispatcher.unregisterRecvCbFun(recvId=None)
                self.transportDispatcher.unregisterTransport(udp.domainName)
                if self.IPv6:
                    self.transportDispatcher.unregisterTransport(udp6.domainName)
                self.transportDispatcher.closeDispatcher()
                self.LogDebug("Dispatcher Closed")
                self.transportDispatcher = None
        except Exception as e1:
            self.LogErrorLine("Error in SnmpClose: " + str(e1))

    # ----------  GenSNMP::SnmpCallbackFunction ---------------------------------
    def SnmpCallbackFunction(
        self, transportDispatcher, transportDomain, transportAddress, wholeMsg
    ):
        while wholeMsg:
            try:
                msgVer = api.decodeMessageVersion(wholeMsg)
                if msgVer in api.protoModules:
                    pMod = api.protoModules[msgVer]
                else:
                    self.LogError("Unsupported SNMP version %s" % msgVer)
                    return
                reqMsg, wholeMsg = decoder.decode(
                    wholeMsg,
                    asn1Spec=pMod.Message(),
                )
                rspMsg = pMod.apiMessage.getResponse(reqMsg)
                rspPDU = pMod.apiMessage.getPDU(rspMsg)
                reqPDU = pMod.apiMessage.getPDU(reqMsg)
                Community = pMod.apiMessage.getCommunity(reqMsg)
                if Community != OctetString(self.community.strip()):
                    self.LogError(
                        "Invalid community string: <"
                        + Community
                        + ">, expected: <"
                        + self.community
                        + ">"
                    )
                    return wholeMsg
                self.LogDebug("Community: " + Community)
                varBinds = []
                pendingErrors = []
                errorIndex = 0
                # GETNEXT PDU
                if reqPDU.isSameTypeWith(pMod.GetNextRequestPDU()):
                    # Produce response var-binds
                    for oid, val in pMod.apiPDU.getVarBinds(reqPDU):
                        errorIndex = errorIndex + 1
                        # Search next OID to report
                        nextIdx = bisect.bisect(self.mibData, oid)
                        if nextIdx == len(self.mibData):
                            # Out of MIB
                            varBinds.append((oid, val))
                            pendingErrors.append(
                                (pMod.apiPDU.setEndOfMibError, errorIndex)
                            )
                        else:
                            # Report value if OID is found
                            varBinds.append(
                                (
                                    self.mibData[nextIdx].name,
                                    self.mibData[nextIdx](msgVer),
                                )
                            )
                elif reqPDU.isSameTypeWith(pMod.GetRequestPDU()):
                    for oid, val in pMod.apiPDU.getVarBinds(reqPDU):
                        # print("Oid: " + str(oid))
                        if oid in self.mibDataIdx:
                            varBinds.append(
                                (oid, self.mibDataIdx[oid](msgVer))
                            )  # call the __call__  function
                        else:
                            # No such instance
                            varBinds.append((oid, val))
                            pendingErrors.append(
                                (pMod.apiPDU.setNoSuchInstanceError, errorIndex)
                            )
                            break
                else:
                    # Report unsupported request type
                    pMod.apiPDU.setErrorStatus(rspPDU, "genErr")
                pMod.apiPDU.setVarBinds(rspPDU, varBinds)
                # Commit possible error indices to response PDU
                for f, i in pendingErrors:
                    f(rspPDU, i)
                transportDispatcher.sendMessage(
                    encoder.encode(rspMsg), transportDomain, transportAddress
                )
            except Exception as e1:
                self.LogErrorLine("Error in SnmpCallbackFunction: " + str(e1))
        return wholeMsg

    # ----------  GenSNMP::SendCommand ------------------------------------------
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

    # ---------- GenSNMP::SNMPThread--------------------------------------------
    def SNMPThread(self):

        time.sleep(1)

        while True:
            try:
                if not self.UseNumeric:
                    statusdata = self.SendCommand("generator: status_json")
                    maintdata = self.SendCommand("generator: maint_json")
                    outagedata = self.SendCommand("generator: outage_json")
                    monitordata = self.SendCommand("generator: monitor_json")
                else:
                    statusdata = self.SendCommand("generator: status_num_json")
                    outagedata = self.SendCommand("generator: outage_num_json")
                    monitordata = self.SendCommand("generator: monitor_num_json")
                    maintdata = self.SendCommand("generator: maint_num_json")
                try:
                    GenmonDict = {}
                    TempDict = {}
                    TempDict = json.loads(statusdata)
                    GenmonDict["Status"] = TempDict["Status"]
                    TempDict = json.loads(maintdata)
                    GenmonDict["Maintenance"] = TempDict["Maintenance"]
                    TempDict = json.loads(outagedata)
                    GenmonDict["Outage"] = TempDict["Outage"]
                    TempDict = json.loads(monitordata)
                    GenmonDict["Monitor"] = TempDict["Monitor"]
                    self.CheckDictForChanges(GenmonDict, "home")

                    if self.WaitForExit("SNMPThread", float(self.PollTime)):
                        self.SnmpClose()
                        return
                except Exception as e1:
                    self.LogErrorLine("Error in SNMPThread: (parse) : " + str(e1))
            except Exception as e1:
                self.LogErrorLine("Error in SNMPThread: " + str(e1))
                if self.WaitForExit("SNMPThread", float(self.PollTime * 60)):
                    self.SnmpClose()
                    return

    # ------------ GenSNMP::DictIsNumeric ---------------------------------------
    def DictIsNumeric(self, node):

        try:
            if not self.UseNumeric:
                return False
            if (
                isinstance(node, dict)
                and "type" in node
                and "value" in node
                and "unit" in node
            ):
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in DictIsNumeric: " + str(e1))
            return False

    # ------------ GenSNMP::CheckDictForChanges ---------------------------------
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
                    if not self.DictIsNumeric(item):
                        CurrentPath = PathPrefix + "/" + str(key)
                        self.CheckDictForChanges(item, CurrentPath)
                    else:
                        CurrentPath = PathPrefix + "/" + str(key)
                        self.CheckForChanges(CurrentPath, str(item["value"]))
                elif isinstance(item, list):
                    CurrentPath = PathPrefix + "/" + str(key)
                    if self.ListIsStrings(item):
                        # if this is a list of strings, the join the list to one comma separated string
                        self.CheckForChanges(CurrentPath, ", ".join(item))
                    else:
                        for listitem in item:
                            if isinstance(listitem, dict):
                                if not self.DictIsNumeric(item):
                                    self.CheckDictForChanges(listitem, CurrentPath)
                                else:
                                    CurrentPath = PathPrefix + "/" + str(key)
                                    self.CheckForChanges(
                                        CurrentPath, str(item["value"])
                                    )
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

    # ---------- GenSNMP::ListIsStrings-----------------------------------------
    # return true if every element of list is a string
    def ListIsStrings(self, listinput):

        try:
            if not isinstance(listinput, list):
                return False
            for item in listinput:
                if sys.version_info[0] < 3:
                    if not (isinstance(item, str) or isinstance(item, unicode)):
                        return False
                else:
                    if not (isinstance(item, str) or isinstance(item, bytes)):
                        return False
            return True
        except Exception as e1:
            self.LogErrorLine("Error in ListIsStrings: " + str(e1))
            return False

    # ---------- GenSNMP::CheckForChanges-------------------------------------
    def CheckForChanges(self, Path, Value):

        try:

            if self.BlackList != None:
                for BlackItem in self.BlackList:
                    if BlackItem.lower() in Path.lower():
                        return
            LastValue = self.LastValues.get(str(Path), None)

            if LastValue == None or LastValue != Value:
                self.LastValues[str(Path)] = Value
                self.UpdateSNMPData(Path, Value)

        except Exception as e1:
            self.LogErrorLine("Error in mygenpush:CheckForChanges: " + str(e1))

    # ----------GenSNMP::SignalClose--------------------------------------------
    def SignalClose(self, signum, frame):

        try:
            self.Close()
        except Exception as e1:
            self.LogErrorLine("Error in SignalClose: " + str(e1))
        sys.exit(1)

    # ----------GenSNMP::Close----------------------------------------------
    def Close(self):

        try:
            self.LogDebug("GenSNMP Exit")
            self.KillThread("SNMPThread")
            self.SnmpClose()
            self.Generator.Close()
        except Exception as e1:
            self.LogErrorLine("Error in Close: " + str(e1))


# -------------------------------------------------------------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("gensnmp")

    GenSNMPInstance = GenSNMP(
        log=log,
        loglocation=loglocation,
        ConfigFilePath=ConfigFilePath,
        host=address,
        port=port,
        console=console,
    )

    sys.exit(1)
