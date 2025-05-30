# -------------------------------------------------------------------------------
#    FILE: genloader.py
# PURPOSE: app for loading specific moduels for genmon
#
#  AUTHOR: Jason G Yates
#    DATE: 12-Sept-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import getopt
import os
import subprocess
import sys
import time
from shutil import copyfile, move
from subprocess import PIPE, Popen

try:
    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.mysupport import MySupport
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

# ------------ Loader class -----------------------------------------------------
class Loader(MySupport):
    def __init__(
        self,
        start=False,
        stop=False,
        hardstop=False,
        loglocation=ProgramDefaults.LogPath,
        log=None,
        localinit=False,
        ConfigFilePath=ProgramDefaults.ConfPath,
    ):

        self.Start = start
        self.Stop = stop
        self.HardStop = hardstop
        self.PipChecked = False
        self.AptUpdated = False
        self.NewInstall = False
        self.Upgrade = False
        self.version = None

        if sys.version_info[0] < 3:
            self.pipProgram = "pip2"
        else:
            self.pipProgram = "pip3"

        self.ConfigFilePath = ConfigFilePath

        self.ConfigFileName = "genloader.conf"
        # log errors in this module to a file
        if localinit == True:
            self.configfile = self.ConfigFileName
        else:
            self.configfile = os.path.join(self.ConfigFilePath, self.ConfigFileName)

        self.ModulePath = os.path.dirname(os.path.realpath(__file__))
        self.ConfPath = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "conf"
        )

        # log errors in this module to a file
        if log == None:
            self.log = SetupLogger(
                "genloader", os.path.join(loglocation, "genloader.log")
            )
        else:
            self.log = log

        self.console = SetupLogger("genloader_console", log_file="", stream=True)

        try:
            if self.Start:
                if not self.CheckSystem():
                    self.LogInfo("Error check system readiness. Exiting")
                    sys.exit(2)

            self.CachedConfig = {}

            if not os.path.isdir(self.ConfigFilePath):
                try:
                    os.mkdir(self.ConfigFilePath)
                except Exception as e1:
                    self.LogInfo(
                        "Error creating target config directory: " + str(e1),
                        LogLine=True,
                    )

            # check to see if genloader.conf is present, if not copy it from genmon directory
            if not os.path.isfile(self.configfile):
                self.LogInfo(
                    "Warning: unable to find config file: "
                    + self.configfile
                    + " Copying file to "
                    + self.ConfigFilePath
                    + " directory."
                )
                if not self.CopyConfFile():
                    sys.exit(2)

            self.config = MyConfig(
                filename=self.configfile, section="genmon", log=self.log
            )

            if not self.GetConfig():
                self.CopyConfFile()
                self.LogInfo("Error validating config. Retrying..")
                self.config = MyConfig(
                    filename=self.configfile, section="genmon", log=self.log
                )
                if not self.GetConfig():
                    self.LogInfo("Error reading config file, 2nd attempt (1), Exiting")
                    sys.exit(2)

            if not self.ValidateConfig():
                self.CopyConfFile()
                self.LogInfo("Error validating config. Retrying..")
                self.config = MyConfig(
                    filename=self.configfile, section="genmon", log=self.log
                )
                if not self.GetConfig():
                    self.LogInfo("Error reading config file, 2nd attempt (2), Exiting")
                    sys.exit(2)
                if not self.ValidateConfig():
                    self.LogInfo("Error validating config file, Exiting")
                    sys.exit(2)

            self.LoadOrder = self.GetLoadOrder()

            if self.Stop:
                self.StopModules()
                time.sleep(2)

            if self.Start:
                self.StartModules()
        except Exception as e1:
            self.LogErrorLine("Error in init: " + str(e1))

    # ---------------------------------------------------------------------------
    def CopyConfFile(self):

        if os.path.isfile(os.path.join(self.ConfPath, self.ConfigFileName)):
            copyfile(os.path.join(self.ConfPath, self.ConfigFileName), self.configfile)
            return True
        else:
            self.LogInfo("Unable to find config file.")
            return False
            sys.exit(2)

    # ---------------------------------------------------------------------------
    def CheckSystem(self):

        # this function checks the system to see if the required libraries are
        # installed. If they are not then an attempt is made to install them.
        ModuleList = [
            # [import name , install name, required version]
            ["flask", "flask", None],  # Web server
            # we will not use the check for configparser as this look like it is in backports on 2.7
            # and our myconfig modules uses the default so this generates an error that is not warranted
            # ['configparser','configparser',None],   # reading config files
            ["serial", "pyserial", None],  # Serial
            ["crcmod", "crcmod", None],  # Modbus CRC
            ["pyowm", "pyowm", "2.10.0"],  # Open Weather API
            ["pytz", "pytz", None],  # Time zone support
            ["pysnmp", "pysnmp", None],  # SNMP
            ["ldap3", "ldap3", None],  # LDAP
            ["smbus", "smbus", None],  # SMBus reading of temp sensors
            ["pyotp", "pyotp", "2.3.0"],  # 2FA support
            ["psutil", "psutil", None],  # process utilities
            ["chump", "chump", None],  # for genpushover
            ["twilio", "twilio", None],  # for gensms
            ["paho.mqtt.client", "paho-mqtt", "1.6.1"],  # for genmqtt
            ["OpenSSL", "pyopenssl", None],  # SSL
            ["spidev", "spidev", None],  # spidev
            ["voipms", "voipms", "0.2.5"]      # voipms for gensms_voip
            # ['fluids', 'fluids', None]              # fluids for genmopeka
        ]
        try:
            ErrorOccured = False

            self.CheckToolsNeeded()

            for Module in ModuleList:
                # fluids is only for Python 3.6 and higher
                if (Module[0] == "fluids") and sys.version_info < (3, 6):
                    continue
                if not self.LibraryIsInstalled(Module[0]):
                    self.LogInfo(
                        "Warning: required library "
                        + Module[1]
                        + " not installed. Attempting to install...."
                    )
                    if not self.InstallLibrary(Module[1], version=Module[2]):
                        self.LogInfo("Error: unable to install library " + Module[1])
                        ErrorOccured = True
                    if Module[0] == "ldap3":
                        # This will correct and issue with the ldap3 modbule not being recogonized in LibrayIsInstalled
                        self.InstallLibrary("pyasn1", update=True)

            return not ErrorOccured
        except Exception as e1:
            self.LogInfo("Error in CheckSystem: " + str(e1), LogLine=True)
            return False

    # ---------------------------------------------------------------------------
    def ExecuteCommandList(self, execute_list, env=None):

        try:
            process = Popen(execute_list, stdout=PIPE, stderr=PIPE, env=env)
            output, _error = process.communicate()

            if _error:
                self.LogInfo("Error in ExecuteCommandList  : " + str(_error))
                return False
            rc = process.returncode
            return True
        except:
            return False

    # ---------------------------------------------------------------------------
    # check for other tools that are needed by pip libaries
    def CheckToolsNeeded(self):
        try:

            command_list = ["cmake", "--version"]
            if not self.ExecuteCommandList(command_list):
                if not self.AptUpdated:
                    command_list = ["sudo", "apt-get", "-yqq", "--allow-releaseinfo-change","update"]
                    if not self.ExecuteCommandList(command_list):
                        self.LogInfo("Error: Unable to run apt-get update. Retrying...")
                        command_list = ["sudo", "apt-get", "-yqq", "update"]
                        if not self.ExecuteCommandList(command_list):
                            self.LogInfo("Error: Unable to run apt-get update. ")
                    self.AptUpdated = True
                self.LogInfo("Installing cmake...")
                command_list = [
                    "sudo",
                    "DEBIAN_FRONTEND=noninteractive",
                    "apt-get",
                    "-yqq",
                    "install",
                    "cmake",
                ]
                if not self.ExecuteCommandList(command_list):
                    self.LogInfo("Error: Unable to install cmake.")

            return True
        except Exception as e1:
            self.LogInfo("Error in CheckToolsNeeded: " + str(e1), LogLine=True)
            return False

    # ---------------------------------------------------------------------------
    def CheckBaseSoftware(self):

        try:
            if self.PipChecked:
                return True

            command_list = [sys.executable, "-m", "pip", "-V"]
            #command_list = [self.pipProgram, "-V"]
            if not self.ExecuteCommandList(command_list):
                self.InstallBaseSoftware()

            self.PipChecked = True
            return True
        except Exception as e1:
            self.LogInfo("Error in CheckBaseSoftware: " + str(e1), LogLine=True)
            self.InstallBaseSoftware()
            return False

    # ---------------------------------------------------------------------------
    def InstallBaseSoftware(self):

        try:
            if sys.version_info[0] < 3:
                pipInstallProgram = "python-pip"
            else:
                pipInstallProgram = "python3-pip"

            self.LogInfo("Installing " + pipInstallProgram)

            if not self.AptUpdated:
                command_list = ["sudo", "apt-get", "-yqq", "--allow-releaseinfo-change", "update"]
                if not self.ExecuteCommandList(command_list):
                    self.LogInfo("Error: Unable to run apt-get update. Retrying..")
                    command_list = ["sudo", "apt-get", "-yqq", "update"]
                    if not self.ExecuteCommandList(command_list):
                        self.LogInfo("Error: Unable to run apt-get update. Retrying..")
                self.AptUpdated = True
            command_list = ["sudo", "apt-get", "-yqq", "install", pipInstallProgram]
            if not self.ExecuteCommandList(command_list):
                self.LogInfo("Error: Unable to install " + pipInstallProgram)

            return True
        except Exception as e1:
            self.LogInfo("Error in InstallBaseSoftware: " + str(e1), LogLine=True)
            return False

    # ---------------------------------------------------------------------------
    @staticmethod
    def OneTimeMaint(ConfigFilePath, log):

        FileList = {
            "feedback.json": os.path.dirname(os.path.realpath(__file__)) + "/",
            "outage.txt": os.path.dirname(os.path.realpath(__file__)) + "/",
            "kwlog.txt": os.path.dirname(os.path.realpath(__file__)) + "/",
            "maintlog.json": os.path.dirname(os.path.realpath(__file__)) + "/",
            "Feedback_dat": os.path.dirname(os.path.realpath(__file__)) + "/genmonlib/",
            "Message_dat": os.path.dirname(os.path.realpath(__file__)) + "/genmonlib/",
            "genmon.conf": "/etc/",
            "genserv.conf": "/etc/",
            "gengpio.conf": "/etc/",
            "gengpioin.conf": "/etc/",
            "genlog.conf": "/etc/",
            "gensms.conf": "/etc/",
            "gensms_modem.conf": "/etc/",
            "genpushover.conf": "/etc/",
            "gensyslog.conf": "/etc/",
            "genmqtt.conf": "/etc/",
            "genmqttin.conf": "/etc/",
            "genslack.conf": "/etc/",
            "gencallmebot.conf": "/etc/",
            "genexercise.conf": "/etc/",
            "genemail2sms.conf": "/etc/",
            "genloader.conf": "/etc/",
            "mymail.conf": "/etc/",
            "mymodem.conf": "/etc/",
        }
        try:
            # Check to see if we have done this already by checking files in the genmon source directory
            if (
                not os.path.isfile(
                    os.path.dirname(os.path.realpath(__file__))
                    + "/genmonlib/Message_dat"
                )
                and not os.path.isfile(
                    os.path.dirname(os.path.realpath(__file__)) + "/maintlog.json"
                )
                and not os.path.isfile(
                    os.path.dirname(os.path.realpath(__file__)) + "/outage.txt"
                )
                and not os.path.isfile(
                    os.path.dirname(os.path.realpath(__file__)) + "/kwlog.txt"
                )
                and not os.path.isfile("/etc/genmon.conf")
            ):
                return False
            # validate target directory
            if not os.path.isdir(ConfigFilePath):
                try:
                    os.mkdir(ConfigFilePath)
                    if not os.access(ConfigFilePath + File, os.R_OK):
                        pass
                except Exception as e1:
                    log.error(
                        "Error validating target directory: " + str(e1), LogLine=True
                    )

            # move files
            for File, Path in FileList.items():
                try:
                    SourceFile = Path + File
                    if os.path.isfile(SourceFile):
                        log.error("Moving " + SourceFile + " to " + ConfigFilePath)
                        if not MySupport.CopyFile(
                            SourceFile, ConfigFilePath + File, move=True, log=log
                        ):
                            log.error("Error: using alternate move method")
                            move(SourceFile, ConfigFilePath + File)
                        if not os.access(ConfigFilePath + File, os.R_OK):
                            pass
                except Exception as e1:
                    log.error("Error moving " + SourceFile)
        except Exception as e1:
            log.error("Error moving files: " + str(e1), LogLine=True)
        return True

    # ---------------------------------------------------------------------------
    def FixPyOWMMaintIssues(self):
        try:
            # check version of pyowm
            import pyowm

            if sys.version_info[0] < 3:
                required_version = "2.9.0"
            else:
                required_version = "2.10.0"

            if not self.LibraryIsInstalled("pyowm"):
                self.LogError("Error in FixPyOWMMaintIssues: pyowm not installed")
                return False

            installed_version = self.GetLibararyVersion("pyowm")

            if installed_version == None:
                self.LogError("Error in FixPyOWMMaintIssues: pyowm version not found")
                return None

            if self.VersionTuple(installed_version) <= self.VersionTuple(
                required_version
            ):
                return True

            self.LogInfo(
                "Found wrong version of pyowm, uninstalling and installing the correct version."
            )

            self.InstallLibrary("pyowm", uninstall=True)

            self.InstallLibrary("pyowm", version=required_version)

            return True
        except Exception as e1:
            self.LogErrorLine("Error in FixPyOWMMaintIssues: " + str(e1))
            return False

    # ---------------------------------------------------------------------------
    def GetLibararyVersion(self, libraryname, importonly=False):

        try:

            try:
                import importlib

                my_module = importlib.import_module(libraryname)
                return my_module.__version__
            except:

                if importonly:
                    return None
                # if we get here then the libarary does not support a __version__ attribute
                # lets use pip to get the version
                try:
                    # This will check if pip is installed
                    if "linux" in sys.platform:
                        self.CheckBaseSoftware()

                    install_list = [sys.executable, "-m", "pip", "freeze", libraryname]

                    process = Popen(install_list, stdout=PIPE, stderr=PIPE)
                    output, _error = process.communicate()

                    if _error:
                        self.LogInfo(
                            "Error in GetLibararyVersion using pip : "
                            + libraryname
                            + ": "
                            + str(_error)
                        )
                    rc = process.returncode

                    # process output of pip freeze
                    lines = output.splitlines()

                    for line in lines:
                        line = line.decode("utf-8")
                        line = line.strip()
                        if line.startswith(libraryname):
                            items = line.split("==")
                            if len(items) <= 2:
                                return items[1]
                    return None

                except Exception as e1:
                    self.LogInfo(
                        "Error getting version of module: "
                        + libraryname
                        + ": "
                        + str(e1),
                        LogLine=True,
                    )
                    return None
        except Exception as e1:
            self.LogErrorLine("Error in GetLibararyVersion: " + str(e1))
            return None

    # ---------------------------------------------------------------------------
    def LibraryIsInstalled(self, libraryname):

        try:
            import importlib

            my_module = importlib.import_module(libraryname)
            return True
        except Exception as e1:
            return False

    # ---------------------------------------------------------------------------
    def InstallLibrary(self, libraryname, update=False, version=None, uninstall=False):

        try:
            if version != None and uninstall == False:
                libraryname = libraryname + "==" + version

            # This will check if pip is installed
            if "linux" in sys.platform:
                self.CheckBaseSoftware()

            if update:
                install_list = [sys.executable, "-m", "pip", "install", libraryname, "-U"]
            elif uninstall:
                install_list = [sys.executable, "-m", "pip", "uninstall", "-y", libraryname]
            else:
                install_list = [sys.executable, "-m", "pip", "install", libraryname]

            process = Popen(install_list, stdout=PIPE, stderr=PIPE)
            output, _error = process.communicate()

            if _error:
                self.LogInfo(
                    "Error in InstallLibrary using pip : "
                    + str(install_list)
                    + ": "
                    + str(_error)
                )
            rc = process.returncode
            return True

        except Exception as e1:
            self.LogInfo(
                "Error installing module: "
                + str(install_list)
                + ": "
                + str(e1),
                LogLine=True,
            )
            return False

    # ---------------------------------------------------------------------------
    def ValidateConfig(self):

        ErrorOccured = False
        if not len(self.CachedConfig):
            self.LogInfo("Error: Empty configruation found.")
            return False

        for Module, Settiings in self.CachedConfig.items():
            try:
                if self.CachedConfig[Module]["enable"]:
                    modulepath = self.GetModulePath(
                        self.ModulePath, self.CachedConfig[Module]["module"]
                    )
                    if modulepath == None:
                        self.LogInfo(
                            "Enable to find file " + self.CachedConfig[Module]["module"]
                        )
                        ErrorOccured = True

                # validate config file and if it is not there then copy it.
                if not self.CachedConfig[Module]["conffile"] == None and len(
                    self.CachedConfig[Module]["conffile"]
                ):
                    ConfFileList = self.CachedConfig[Module]["conffile"].split(",")
                    for ConfigFile in ConfFileList:
                        ConfigFile = ConfigFile.strip()
                        if not os.path.isfile(
                            os.path.join(self.ConfigFilePath, ConfigFile)
                        ):
                            if os.path.isfile(os.path.join(self.ConfPath, ConfigFile)):
                                self.LogInfo(
                                    "Copying "
                                    + ConfigFile
                                    + " to "
                                    + self.ConfigFilePath
                                )
                                copyfile(
                                    os.path.join(self.ConfPath, ConfigFile),
                                    os.path.join(self.ConfigFilePath, ConfigFile),
                                )
                            else:
                                self.LogInfo(
                                    "Enable to find config file "
                                    + os.path.join(self.ConfPath, ConfigFile)
                                )
                                ErrorOccured = True
            except Exception as e1:
                self.LogInfo(
                    "Error validating config for " + Module + " : " + str(e1),
                    LogLine=True,
                )
                return False

        try:
            if not self.CachedConfig["genmon"]["enable"]:
                self.LogError("Warning: Genmon is not enabled, assume corrupt file.")
                ErrorOccured = True
            if not self.CachedConfig["genserv"]["enable"]:
                self.LogError("Warning: Genserv is not enabled")

        except Exception as e1:
            self.LogErrorLine(
                "Error in ValidateConfig, possible corrupt file. " + str(e1)
            )
            ErrorOccured = True
        return not ErrorOccured

    # ---------------------------------------------------------------------------
    def AddEntry(self, section=None, module=None, conffile="", args="", priority="2"):

        try:
            if section == None or module == None:
                return
            self.config.WriteSection(section)
            self.config.WriteValue("module", module, section=section)
            self.config.WriteValue("enable", "False", section=section)
            self.config.WriteValue("hardstop", "False", section=section)
            self.config.WriteValue("conffile", conffile, section=section)
            self.config.WriteValue("args", args, section=section)
            self.config.WriteValue("priority", priority, section=section)
        except Exception as e1:
            self.LogInfo("Error in AddEntry: " + str(e1), LogLine=True)
        return

    # ---------------------------------------------------------------------------
    def UpdateIfNeeded(self):

        try:
            self.config.SetSection("gengpioin")
            if not self.config.HasOption("conffile"):
                self.config.WriteValue(
                    "conffile", "gengpioin.conf", section="gengpioin"
                )
                self.LogError("Updated entry gengpioin.conf")
            else:
                defValue = self.config.ReadValue("conffile", default="")
                if not len(defValue):
                    self.config.WriteValue(
                        "conffile", "gengpioin.conf", section="gengpioin"
                    )
                    self.LogError("Updated entry gengpioin.conf")

            self.config.SetSection("gengpio")
            if not self.config.HasOption("conffile"):
                self.config.WriteValue("conffile", "gengpio.conf", section="gengpio")
                self.LogError("Updated entry gengpio.conf")
            else:
                defValue = self.config.ReadValue("conffile", default="")
                if not len(defValue):
                    self.config.WriteValue(
                        "conffile", "gengpio.conf", section="gengpio"
                    )
                    self.LogError("Updated entry gengpio.conf")

            # check version info
            self.config.SetSection("genloader")
            self.version = self.config.ReadValue("version", default="0.0.0")
            if self.version == "0.0.0" or not len(self.version):
                self.version = "0.0.0"
                self.NewInstall = True

            if self.VersionTuple(self.version) < self.VersionTuple(
                ProgramDefaults.GENMON_VERSION
            ):
                self.Upgrade = True

            if self.NewInstall or self.Upgrade:
                self.config.WriteValue(
                    "version", ProgramDefaults.GENMON_VERSION, section="genloader"
                )
            if self.NewInstall:
                self.LogInfo("Running one time maintenance check")
                self.FixPyOWMMaintIssues()

            # TODO other version checks can be added here

            self.version = ProgramDefaults.GENMON_VERSION

        except Exception as e1:
            self.LogInfo("Error in UpdateIfNeeded: " + str(e1), LogLine=True)

    # ---------------------------------------------------------------------------
    def GetConfig(self):

        try:

            Sections = self.config.GetSections()
            ValidSections = [
                "genmon",
                "genserv",
                "gengpio",
                "gengpioin",
                "genlog",
                "gensms",
                "gensms_modem",
                "genpushover",
                "gensyslog",
                "genmqtt",
                "genmqttin",
                "genslack",
                "gencallmebot",
                "genexercise",
                "genemail2sms",
                "gentankutil",
                "gencentriconnect",
                "gentankdiy",
                "genalexa",
                "gensnmp",
                "gentemp",
                "gengpioledblink",
                "gencthat",
                "genmopeka",
                "gencustomgpio",
                "gensms_voip",
                "genloader",
            ]
            for entry in ValidSections:
                if not entry in Sections:
                    if entry == "genmon" or entry == "genserv":
                        self.LogError(
                            "Warning: Missing entry: " + entry + " , file corruption. "
                        )
                        return False
                    if entry == "genslack":
                        self.LogError(
                            "Warning: Missing entry: " + entry + " , adding entry"
                        )
                        self.AddEntry(
                            section=entry,
                            module="genslack.py",
                            conffile="genslack.conf",
                        )
                    if entry == "gencallmebot":
                        self.LogError(
                            "Warning: Missing entry: " + entry + " , adding entry"
                        )
                        self.AddEntry(
                            section=entry,
                            module="gencallmebot.py",
                            conffile="gencallmebot.conf",
                        )
                    if entry == "genexercise":
                        self.LogError(
                            "Warning: Missing entry: " + entry + " , adding entry"
                        )
                        self.AddEntry(
                            section=entry,
                            module="genexercise.py",
                            conffile="genexercise.conf",
                        )
                    if entry == "genemail2sms":
                        self.LogError(
                            "Warning: Missing entry: " + entry + " , adding entry"
                        )
                        self.AddEntry(
                            section=entry,
                            module="genemail2sms.py",
                            conffile="genemail2sms.conf",
                        )
                    if entry == "gencentriconnect":
                        self.LogError(
                            "Warning: Missing entry: " + entry + " , adding entry"
                        )
                        self.AddEntry(
                            section=entry,
                            module="gencentriconnect.py",
                            conffile="gencentriconnect.conf",
                        )
                    if entry == "gentankutil":
                        self.LogError(
                            "Warning: Missing entry: " + entry + " , adding entry"
                        )
                        self.AddEntry(
                            section=entry,
                            module="gentankutil.py",
                            conffile="gentankutil.conf",
                        )
                    if entry == "genalexa":
                        self.LogError(
                            "Warning: Missing entry: " + entry + " , adding entry"
                        )
                        self.AddEntry(
                            section=entry,
                            module="genalexa.py",
                            conffile="genalexa.conf",
                        )
                    if entry == "gensnmp":
                        self.LogError(
                            "Warning: Missing entry: " + entry + " , adding entry"
                        )
                        self.AddEntry(
                            section=entry, module="gensnmp.py", conffile="gensnmp.conf"
                        )
                    if entry == "gentemp":
                        self.LogError(
                            "Warning: Missing entry: " + entry + " , adding entry"
                        )
                        self.AddEntry(
                            section=entry, module="gentemp.py", conffile="gentemp.conf"
                        )
                    if entry == "gentankdiy":
                        self.LogError(
                            "Warning: Missing entry: " + entry + " , adding entry"
                        )
                        self.AddEntry(
                            section=entry,
                            module="gentankdiy.py",
                            conffile="gentankdiy.conf",
                        )
                    if entry == "gengpioledblink":
                        self.LogError(
                            "Warning: Missing entry: " + entry + " , adding entry"
                        )
                        self.AddEntry(
                            section=entry,
                            module="gengpioledblink.py",
                            conffile="gengpioledblink.conf",
                        )
                    if entry == "gencthat":
                        self.LogError(
                            "Warning: Missing entry: " + entry + " , adding entry"
                        )
                        self.AddEntry(
                            section=entry,
                            module="gencthat.py",
                            conffile="gencthat.conf",
                        )
                    if entry == "genmopeka":
                        self.LogError(
                            "Warning: Missing entry: " + entry + " , adding entry"
                        )
                        self.AddEntry(
                            section=entry,
                            module="genmopeka.py",
                            conffile="genmopeka.conf",
                        )
                    if entry == "gensms_voip":
                        self.LogError(
                            "Warning: Missing entry: " + entry + " , adding entry"
                        )
                        self.AddEntry(
                            section=entry,
                            module="gensms_voip.py",
                            conffile="gensms_voip.conf",
                        )
                    if entry == "genmqttin":
                        self.LogError(
                            "Warning: Missing entry: " + entry + " , adding entry"
                        )
                        self.AddEntry(
                            section=entry,
                            module="genmqttin.py",
                            conffile="genmqttin.conf",
                        )
                    if entry == "gencustomgpio":
                        self.LogError(
                            "Warning: Missing entry: " + entry + " , adding entry"
                        )
                        self.AddEntry(
                            section=entry,
                            module="gencustomgpio.py",
                            conffile="gencustomgpio.conf",
                        )
                    if entry == "genloader":
                        self.LogError("Adding entry: " + entry)
                        self.config.WriteSection(entry)
                    else:
                        self.LogError("Warning: Missing entry: " + entry)

            self.UpdateIfNeeded()

            Sections = self.config.GetSections()
            for SectionName in Sections:
                if SectionName == "genloader":
                    continue
                TempDict = {}
                self.config.SetSection(SectionName)
                if self.config.HasOption("module"):
                    TempDict["module"] = self.config.ReadValue("module")
                else:
                    self.LogError(
                        "Error in GetConfig: expcting module in section "
                        + str(SectionName)
                    )
                    TempDict["module"] = None

                if self.config.HasOption("enable"):
                    TempDict["enable"] = self.config.ReadValue(
                        "enable", return_type=bool
                    )
                else:
                    self.LogError(
                        "Error in GetConfig: expcting enable in section "
                        + str(SectionName)
                    )
                    TempDict["enable"] = False

                if self.config.HasOption("hardstop"):
                    TempDict["hardstop"] = self.config.ReadValue(
                        "hardstop", return_type=bool
                    )
                else:
                    self.LogError(
                        "Error in GetConfig: expcting hardstop in section "
                        + str(SectionName)
                    )
                    TempDict["hardstop"] = False

                if self.config.HasOption("conffile"):
                    TempDict["conffile"] = self.config.ReadValue("conffile")
                else:
                    self.LogError(
                        "Error in GetConfig: expcting confile in section "
                        + str(SectionName)
                    )
                    TempDict["conffile"] = None

                if self.config.HasOption("args"):
                    TempDict["args"] = self.config.ReadValue("args")
                else:
                    self.LogError(
                        "Error in GetConfig: expcting args in section "
                        + str(SectionName)
                    )
                    TempDict["args"] = None

                if self.config.HasOption("priority"):
                    TempDict["priority"] = self.config.ReadValue(
                        "priority", return_type=int, default=None
                    )
                else:
                    self.LogError(
                        "Error in GetConfig: expcting priority in section "
                        + str(SectionName)
                    )
                    TempDict["priority"] = None

                if self.config.HasOption("postloaddelay"):
                    TempDict["postloaddelay"] = self.config.ReadValue(
                        "postloaddelay", return_type=int, default=0
                    )
                else:
                    TempDict["postloaddelay"] = 0

                if self.config.HasOption("pid"):
                    TempDict["pid"] = self.config.ReadValue(
                        "pid", return_type=int, default=0, NoLog=True
                    )
                else:
                    TempDict["pid"] = 0

                self.CachedConfig[SectionName] = TempDict
            return True

        except Exception as e1:
            self.LogInfo("Error parsing config file: " + str(e1), LogLine=True)
            return False
        return True

    # ---------------------------------------------------------------------------
    def ConvertToInt(self, value, default=None):

        try:
            return int(str(value))
        except:
            return default

    # ---------------------------------------------------------------------------
    def GetLoadOrder(self):

        LoadOrder = []
        LoadDict = {}
        try:
            for Module, Settiings in self.CachedConfig.items():
                # get the load order of all modules, even if they are disabled
                # since we need to stop all modules (even disabled ones) if the
                # conf file changed
                try:
                    if self.CachedConfig[Module]["priority"] == None:
                        LoadDict[Module] = 99
                    elif self.CachedConfig[Module]["priority"] >= 0:
                        LoadDict[Module] = self.CachedConfig[Module]["priority"]
                    else:
                        LoadDict[Module] = 99
                except Exception as e1:
                    self.LogInfo(
                        "Error reading load order (retrying): " + str(e1), LogLine=True
                    )
            # lambda kv: (-kv[1], kv[0])
            for key, value in sorted(LoadDict.items(), key=lambda kv: (-kv[1], kv[0])):
                # for key, value in sorted(LoadDict.iteritems(), key=lambda (k,v): (v,k)):
                LoadOrder.append(key)
        except Exception as e1:
            self.LogInfo("Error reading load order: " + str(e1), LogLine=True)

        return LoadOrder

    # ---------------------------------------------------------------------------
    def StopModules(self):

        self.LogConsole("Stopping....")
        if not len(self.LoadOrder):
            self.LogInfo("Error, nothing to stop.")
            return False
        ErrorOccured = False
        for Module in self.LoadOrder:
            try:
                if not self.UnloadModule(
                    self.CachedConfig[Module]["module"],
                    pid=self.CachedConfig[Module]["pid"],
                    HardStop=self.CachedConfig[Module]["hardstop"],
                    UsePID=True,
                ):
                    self.LogInfo("Error stopping " + Module)
                    ErrorOccured = True
            except Exception as e1:
                self.LogInfo(
                    "Error stopping module " + Module + " : " + str(e1), LogLine=True
                )
                return False
        return not ErrorOccured

    # ---------------------------------------------------------------------------
    def GetModulePath(self, modulepath, modulename):
        try:
            fullpath = os.path.join(modulepath, modulename)

            if os.path.isfile(fullpath):
                return modulepath

            fullpath = os.path.join(modulepath, "addon", modulename)

            if os.path.isfile(fullpath):
                return os.path.join(modulepath, "addon")

            return None
        except Exception as e1:
            self.LogInfo(
                "Error in GetModulePath :" + modulename + " : " + str(e1), LogLine=True
            )
            return None

    # ---------------------------------------------------------------------------
    def StartModules(self):

        self.LogConsole("Starting....")

        if not len(self.LoadOrder):
            self.LogInfo("Error, nothing to start.")
            return False
        ErrorOccured = False
        for Module in reversed(self.LoadOrder):
            try:
                if self.CachedConfig[Module]["enable"]:
                    modulepath = self.GetModulePath(
                        self.ModulePath, self.CachedConfig[Module]["module"]
                    )
                    if modulepath == None:
                        continue

                    if not multi_instance:
                        # check that module is not loaded already, if it is then force it (hard) to unload
                        attempts = 0
                        while True:
                            if MySupport.IsRunning(
                                prog_name=self.CachedConfig[Module]["module"],
                                log=self.log,
                                multi_instance=multi_instance,
                            ):
                                # if loaded then kill it
                                if attempts >= 4:
                                    # kill it
                                    if not self.UnloadModule(
                                        self.CachedConfig[Module]["module"],
                                        pid=None,
                                        HardStop=True,
                                        UsePID=False,
                                    ):
                                        self.LogInfo(
                                            "Error killing "
                                            + self.CachedConfig[Module]["module"]
                                        )
                                else:
                                    attempts += 1
                                    time.sleep(1)
                            else:
                                break

                    if not self.LoadModule(
                        modulepath,
                        self.CachedConfig[Module]["module"],
                        args=self.CachedConfig[Module]["args"],
                    ):
                        self.LogInfo("Error starting " + Module)
                        ErrorOccured = True
                    if (
                        not self.CachedConfig[Module]["postloaddelay"] == None
                        and self.CachedConfig[Module]["postloaddelay"] > 0
                    ):
                        time.sleep(self.CachedConfig[Module]["postloaddelay"])
            except Exception as e1:
                self.LogInfo(
                    "Error starting module " + Module + " : " + str(e1), LogLine=True
                )
                return False
        return not ErrorOccured

    # ---------------------------------------------------------------------------
    def LoadModuleAlt(self, modulename, args=None):
        try:
            self.LogConsole("Starting " + modulename)
            # to load as a background process we just use os.system since Popen
            # is problematic in doing this
            CommandString = sys.executable + " " + modulename
            if args != None and len(args):
                CommandString += " " + args
            CommandString += " &"
            os.system(CommandString)
            return True

        except Exception as e1:
            self.LogInfo("Error loading module: " + str(e1), LogLine=True)
            return False

    # ---------------------------------------------------------------------------
    def LoadModule(self, path, modulename, args=None):
        try:
            try:
                import os

                fullmodulename = os.path.join(path, modulename)
            except Exception as e1:
                fullmodulename = path + "/" + modulename

            if args != None:
                self.LogConsole("Starting " + fullmodulename + " " + args)
            else:
                self.LogConsole("Starting " + fullmodulename)
            try:
                from subprocess import DEVNULL  # py3k
            except ImportError:
                import os

                DEVNULL = open(os.devnull, "wb")

            if not len(args):
                args = None

            if "genserv.py" in modulename:
                OutputStream = DEVNULL
            else:
                OutputStream = subprocess.PIPE

            executelist = [sys.executable, fullmodulename]
            if args != None:
                executelist.extend(args.split(" "))
            # This will make all the programs use the same config files
            executelist.extend(["-c", self.ConfigFilePath])
            # close_fds=True
            pid = subprocess.Popen(
                executelist,
                stdout=OutputStream,
                stderr=OutputStream,
                stdin=OutputStream,
            )
            return self.UpdatePID(modulename, pid.pid)

        except Exception as e1:
            self.LogInfo(
                "Error loading module " + path + ": " + modulename + ": " + str(e1),
                LogLine=True,
            )
            return False

    # ---------------------------------------------------------------------------
    def UnloadModule(self, modulename, pid=None, HardStop=False, UsePID=False):
        try:
            LoadInfo = []
            if UsePID:
                if pid == None or pid == "" or pid == 0:
                    return True
                LoadInfo.append("kill")
                if HardStop or self.HardStop:
                    LoadInfo.append("-9")
                LoadInfo.append(str(pid))
            else:
                LoadInfo.append("pkill")
                if HardStop or self.HardStop:
                    LoadInfo.append("-9")
                LoadInfo.append("-u")
                LoadInfo.append("root")
                LoadInfo.append("-f")
                LoadInfo.append(modulename)

            self.LogConsole("Stopping " + modulename)
            process = Popen(LoadInfo, stdout=PIPE)
            output, _error = process.communicate()
            rc = process.returncode
            return self.UpdatePID(modulename, "")

        except Exception as e1:
            self.LogInfo("Error loading module: " + str(e1), LogLine=True)
            return False

    # ---------------------------------------------------------------------------
    def UpdatePID(self, modulename, pid=None):

        try:
            filename = os.path.splitext(modulename)[0]  # remove extension
            if not self.config.SetSection(filename):
                self.LogError(
                    "Error settting section name in UpdatePID: " + str(filename)
                )
                return False
            self.config.WriteValue("pid", str(pid))
            return True
        except Exception as e1:
            self.LogInfo("Error writing PID for " + modulename + " : " + str(e1))
            return False
        return True


# ------------------main---------------------------------------------------------
if __name__ == "__main__":

    HelpStr = "\npython genloader.py [-s -r -x -z -c configfilepath]\n"
    HelpStr += "   Example: python genloader.py -s\n"
    HelpStr += "            python genloader.py -r\n"
    HelpStr += "\n      -s  Start Genmon modules"
    HelpStr += "\n      -r  Restart Genmon moduels"
    HelpStr += "\n      -x  Stop Genmon modules"
    HelpStr += "\n      -z  Hard stop Genmon modules"
    HelpStr += "\n      -c  Path of genmon.conf file i.e. /etc/"
    HelpStr += "\n \n"

    if not MySupport.PermissionsOK():
        print(
            "You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting."
        )
        sys.exit(2)

    try:
        ConfigFilePath = ProgramDefaults.ConfPath
        opts, args = getopt.getopt(
            sys.argv[1:],
            "hsrxzc:",
            ["help", "start", "restart", "exit", "hardstop", "configpath="],
        )
    except getopt.GetoptError:
        print(HelpStr)
        sys.exit(2)

    StopModules = False
    StartModules = False
    HardStop = False

    for opt, arg in opts:
        if opt == "-h":
            print(HelpStr)
            sys.exit()
        elif opt in ("-s", "--start"):
            StartModules = True
        elif opt in ("-r", "--restart"):
            StopModules = True
            StartModules = True
        elif opt in ("-x", "--exit"):
            StopModules = True
        elif opt in ("-z", "--hardstop"):
            HardStop = True
            StopModules = True
        elif opt in ("-c", "--configpath"):
            ConfigFilePath = arg
            ConfigFilePath = ConfigFilePath.strip()

    if not StartModules and not StopModules:
        print("\nNo option selected.\n")
        print(HelpStr)
        sys.exit(2)

    tmplog = SetupLogger("genloader", "/var/log/" + "genloader.log")
    if Loader.OneTimeMaint(ConfigFilePath, tmplog):
        time.sleep(1.5)
    port, loglocation, multi_instance = MySupport.GetGenmonInitInfo(
        ConfigFilePath, log=None
    )

    if MySupport.IsRunning(os.path.basename(__file__), multi_instance=multi_instance):
        print("\ngenloader already running.")
        sys.exit(2)

    LoaderObject = Loader(
        start=StartModules,
        stop=StopModules,
        hardstop=HardStop,
        ConfigFilePath=ConfigFilePath,
        loglocation=loglocation,
    )
