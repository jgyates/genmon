# -------------------------------------------------------------------------------
#    FILE: genloader.py
# PURPOSE: app for loading specific moduels for genmon
#
#  AUTHOR: Jason G Yates
#    DATE: 12-Sept-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import collections
import configparser
import getopt
import importlib
import json
import importlib.util
import os
import re
import subprocess
import sys
import time
from shutil import copyfile, move
from subprocess import PIPE, Popen

try:
    from importlib import metadata
except ImportError:  # Python 3.7, which genmon no longer supports (see PythonSupported)
    metadata = None

try:
    from genmonlib.myconfig import MyConfig
    from genmonlib.myfileutil import AtomicWrite
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

    # pyasn1 for pysnmp (gensnmp) and ldap3: the version of requirements.txt
    # (0.6.4 and 0.6.5 are security fixes)
    PYASN1_VERSION = "0.6.5"

    def __init__(
        self,
        start=False,
        stop=False,
        hardstop=False,
        loglocation=ProgramDefaults.LogPath,
        log=None,
        localinit=False,
        ConfigFilePath=ProgramDefaults.ConfPath,
        multi_instance=False,
    ):

        self.Start = start
        # True if more than one copy of genmon may run (multi_instance in genmon.conf)
        self.MultiInstance = multi_instance
        self.Stop = stop
        self.HardStop = hardstop
        self.PipChecked = False
        self.AptUpdated = False
        self.NewInstall = False
        self.Upgrade = False
        self.version = None

        self.ConfigFilePath = ConfigFilePath
        # PIDs of the started modules, see ReadPIDs
        self.PIDFile = os.path.join(self.ConfigFilePath, "genloader.pids")

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

        self.bSystemIsNotLinux = False
        if not "linux" in sys.platform:
            self.bSystemIsNotLinux = True
        self.bSystemIsWindows = self.IsWindows()

        # log errors in this module to a file
        if log == None:
            self.log = SetupLogger(
                "genloader", os.path.join(loglocation, "genloader.log")
            )
        else:
            self.log = log

        self.console = SetupLogger("genloader_console", log_file="", stream=True)

        try:
            if self.Start and not self.PythonSupported():
                # stopping still works, so a restart leaves nothing half running
                self.Start = False

            self.pipProgram = "pip3"
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

            if self.Start:
                if not self.CheckSystem():
                    # start anyway: the add-ons that need a missing library log it
                    self.LogInfo("Warning: one or more required libraries could not be installed")

            self.LoadOrder = self.GetLoadOrder()

            if self.Stop:
                self.StopModules()
                time.sleep(2)

            self.Maintenance()

            if self.Start:
                self.StartModules()
        except Exception as e1:
            self.LogErrorLine("Error in init: " + str(e1))

    # ---------------------------------------------------------------------------
    # genmon 2.0 and later need Python 3.9 or later (see README.md)
    MIN_PYTHON = (3, 9)

    def PythonSupported(self):

        if sys.version_info >= self.MIN_PYTHON:
            return True
        Message = (
            "ERROR: genmon needs Python %d.%d or higher, this is Python %d.%d. "
            "The genmon modules were not started." % (self.MIN_PYTHON + tuple(sys.version_info[:2]))
        )
        self.LogError(Message)
        self.LogConsole(Message)
        return False

    # ---------------------------------------------------------------------------
    # sys.platform is "win32" on Windows ("darwin", macOS, also has "win" in it)
    @staticmethod
    def IsWindows():

        return sys.platform.startswith("win")

    # ---------------------------------------------------------------------------
    # Copy the default genloader.conf from the genmon conf folder. An existing
    # file is saved first (genloader.conf.bak-<date-time>), since the default
    # has every add-on disabled.
    def CopyConfFile(self):

        DefaultFile = os.path.join(self.ConfPath, self.ConfigFileName)
        if not os.path.isfile(DefaultFile):
            self.LogInfo("Unable to find config file.")
            return False
        if os.path.isfile(self.configfile):
            Backup = self.configfile + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
            try:
                copyfile(self.configfile, Backup)
                self.LogInfo(
                    "Replacing " + self.configfile + " with the default file. "
                    "The old file was saved as " + Backup
                )
            except Exception as e1:
                self.LogInfo("Error saving " + self.configfile + ": " + str(e1))
        copyfile(DefaultFile, self.configfile)
        return True

    # ---------------------------------------------------------------------------
    def IsModuleEnabled(self, ModuleList):

        try:
            if ModuleList == None or not len(ModuleList):
                return True
            for Module in ModuleList:
                if Module in self.CachedConfig and self.CachedConfig[Module]["enable"]:
                    return True
            return False
        except Exception as e1:
            self.LogInfo("Error in IsModuleEnabled: " + str(e1), LogLine=True)
            return False

    # ---------------------------------------------------------------------------
    def IsConfigOptionEnabled(self, ConfigFile, Section, Option, default=False):

        try:
            ConfigPath = os.path.join(self.ConfigFilePath, ConfigFile)
            if not os.path.isfile(ConfigPath):
                ConfigPath = os.path.join(self.ConfPath, ConfigFile)
            if not os.path.isfile(ConfigPath):
                return default
            config = MyConfig(filename=ConfigPath, section=Section, log=self.log)
            return config.ReadValue(Option, return_type=bool, default=default)
        except Exception as e1:
            self.LogInfo("Error in IsConfigOptionEnabled: " + str(e1), LogLine=True)
            return default

    # ---------------------------------------------------------------------------
    def LibraryDependency(
        self,
        ImportName,
        InstallName=None,
        Version=None,
        LinuxOnly=False,
        MinPython=None,
        TestImport=False,
    ):

        # ImportName is the module name used by importlib. InstallName is the
        # package name used by pip, which can differ (e.g. serial -> pyserial).
        # Version is the minimum version (pip installs exactly that version if
        # the installed one is older). TestImport imports the library to check
        # it, instead of only finding it, for a library that can be installed
        # but fail to import.
        return {
            "import": ImportName,
            "install": InstallName if InstallName != None else ImportName,
            "version": Version,
            "linuxonly": LinuxOnly,
            "minpython": MinPython,
            "testimport": TestImport,
        }

    # ---------------------------------------------------------------------------
    def GetDependencyRegistry(self):

        # Dependency groups:
        #   base     - always required for normal genmon/genserv startup
        #   addons   - required only when at least one listed add-on is enabled
        #   features - required only when a config option is enabled; a feature
        #              may also list modules when both an add-on and an option
        #              must be enabled before installing the dependency.
        #
        # Keep optional or unusually large packages out of base. For example,
        # fluids is only needed by genmopeka, and zeroconf is only needed when
        # genhalink mDNS discovery is enabled.
        return {
            "base": [
                self.LibraryDependency("flask"),  # Web server
                self.LibraryDependency("serial", "pyserial"),  # Serial
                self.LibraryDependency("crcmod"),  # Modbus CRC
                self.LibraryDependency("pyowm"),  # Open Weather API
                self.LibraryDependency("pyotp", Version="2.3.0"),  # 2FA support
                self.LibraryDependency("psutil"),  # process utilities
                self.LibraryDependency("OpenSSL", "pyopenssl"),  # SSL
                # ldap3 fails to import with some pyasn1 versions, see CheckSystem
                self.LibraryDependency("ldap3", TestImport=True),  # LDAP
            ],
            "addons": [
                {
                    "modules": ["gensnmp"],
                    "dependencies": [
                        self.LibraryDependency("pysnmp", Version="7.1.21"),
                        self.LibraryDependency("pyasn1", Version=self.PYASN1_VERSION)
                    ],
                },
                {
                    "modules": ["gentankdiy"],
                    "dependencies": [
                        self.LibraryDependency("smbus", LinuxOnly=True),
                    ],
                },
                {
                    "modules": ["genpushover"],
                    "dependencies": [
                        self.LibraryDependency("chump"),
                    ],
                },
                {
                    "modules": ["gensms"],
                    "dependencies": [
                        self.LibraryDependency("twilio"),
                    ],
                },
                {
                    "modules": ["genmqtt", "genmqttin", "genhomeassistant"],
                    "dependencies": [
                        self.LibraryDependency(
                            "paho.mqtt.client", "paho-mqtt", Version="1.6.1"
                        ),
                    ],
                },
                {
                    "modules": ["gencthat"],
                    "dependencies": [
                        self.LibraryDependency("spidev", LinuxOnly=True),
                    ],
                },
                {
                    "modules": ["genhalink"],
                    "dependencies": [
                        self.LibraryDependency("aiohttp"),
                    ],
                },
                {
                    "modules": ["gensms_voip"],
                    "dependencies": [
                        self.LibraryDependency("voipms", Version="0.2.5"),
                    ],
                },
                {
                    "modules": ["genmopeka"],
                    "dependencies": [
                        self.LibraryDependency("fluids"),
                        self.LibraryDependency(
                            "bleson", "bleson @ git+https://github.com/TheCellule/python-bleson"
                        ),
                    ],
                },
                {
                    "modules": ["genotodata"],
                    "dependencies": [
                        self.LibraryDependency("bleak"),
                    ],
                },
                {
                    "modules": ["genhubitat"],
                    "dependencies": [
                        self.LibraryDependency("aiohttp"),
                    ],
                },
            ],
            "features": [
                {
                    # zeroconf is optional within genhalink. Do not install it
                    # unless the add-on is enabled and mDNS discovery is on.
                    "modules": ["genhalink"],
                    "config": {
                        "file": "genhalink.conf",
                        "section": "genhalink",
                        "option": "zeroconf_enabled",
                        "default": True,
                    },
                    "dependencies": [
                        self.LibraryDependency("zeroconf"),
                    ],
                },
                {
                    # zeroconf is optional within genhubitat. Do not install it
                    # unless the add-on is enabled and mDNS discovery is on.
                    "modules": ["genhubitat"],
                    "config": {
                        "file": "genhubitat.conf",
                        "section": "genhubitat",
                        "option": "zeroconf_enabled",
                        "default": True,
                    },
                    "dependencies": [
                        self.LibraryDependency("zeroconf"),
                    ],
                },
                {
                    # mopeka_pro_check is only used by genmopeka's old library
                    # option
                    "modules": ["genmopeka"],
                    "config": {
                        "file": "genmopeka.conf",
                        "section": "genmopeka",
                        "option": "use_old_lib",
                        "default": False,
                    },
                    "dependencies": [
                        self.LibraryDependency("mopeka_pro_check"),
                    ],
                },
                {
                    # webauthn is used for passkeys, which are only available
                    # when MFA is enabled.
                    "config": {
                        "file": "genmon.conf",
                        "section": "GenMon",
                        "option": "usemfa",
                        "default": False,
                    },
                    "dependencies": [
                        self.LibraryDependency("webauthn", Version="2.7.0"),
                    ],
                },
            ],
        }

    # ---------------------------------------------------------------------------
    def GetModuleList(self):

        ModuleList = []
        Seen = set()
        DependencyRegistry = self.GetDependencyRegistry()

        try:
            # Start with the unconditional core dependencies.
            for Module in DependencyRegistry["base"]:
                ModuleList.append(Module)

            # Add dependencies for enabled add-ons only. This keeps disabled
            # add-ons from triggering pip installs during every genloader start.
            for AddOn in DependencyRegistry["addons"]:
                if not self.IsModuleEnabled(AddOn["modules"]):
                    continue
                for Module in AddOn["dependencies"]:
                    Module = Module.copy()
                    Module["modules"] = AddOn["modules"]
                    ModuleList.append(Module)

            # Add dependencies for enabled feature flags. Some features also
            # have an add-on owner, so both gates must pass before inclusion.
            for Feature in DependencyRegistry["features"]:
                if "modules" in Feature:
                    if not self.IsModuleEnabled(Feature["modules"]):
                        continue
                if not self.IsConfigOptionEnabled(
                    Feature["config"]["file"],
                    Feature["config"]["section"],
                    Feature["config"]["option"],
                    default=Feature["config"].get("default", False),
                ):
                    continue
                for Module in Feature["dependencies"]:
                    Module = Module.copy()
                    if "modules" in Feature:
                        Module["modules"] = Feature["modules"]
                    Module["config"] = Feature["config"]
                    ModuleList.append(Module)

            # A package can be required through more than one path. Check it
            # once so shared dependencies do not produce duplicate log/install
            # attempts.
            DedupedList = []
            for Module in ModuleList:
                Key = (Module["import"], Module["install"], Module["version"])
                if Key in Seen:
                    continue
                Seen.add(Key)
                DedupedList.append(Module)
            return DedupedList
        except Exception as e1:
            self.LogInfo("Error in GetModuleList: " + str(e1), LogLine=True)
            return ModuleList

    # ---------------------------------------------------------------------------
    def ShouldCheckLibrary(self, Module):

        try:
            # Final platform/version/config guard before importing or installing.
            # GetModuleList already filters add-ons and features, but keeping
            # this here preserves one validation path for any direct callers.
            if "linuxonly" in Module and self.bSystemIsNotLinux and Module["linuxonly"]:
                return False
            if "minpython" in Module and Module["minpython"] != None:
                if sys.version_info < Module["minpython"]:
                    return False
            if not self.IsModuleEnabled(Module.get("modules", None)):
                return False
            if "config" in Module:
                Config = Module["config"]
                return self.IsConfigOptionEnabled(
                    Config["file"],
                    Config["section"],
                    Config["option"],
                    default=Config.get("default", False),
                )
            return True
        except Exception as e1:
            self.LogInfo("Error in ShouldCheckLibrary: " + str(e1), LogLine=True)
            return True

    # ---------------------------------------------------------------------------
    def CheckSystem(self):

        # this function checks the system to see if the required libraries are
        # installed. If they are not then an attempt is made to install them.

        ModuleList = self.GetModuleList()
        try:
            ErrorOccured = False

            for Module in ModuleList:

                if not self.ShouldCheckLibrary(Module):
                    continue
                if not self.LibraryIsInstalled(
                    Module["import"],
                    Module["version"],
                    installname=Module["install"],
                    testimport=Module.get("testimport", False),
                ):
                    self.LogInfo(
                        "Warning: required library "
                        + Module["install"]
                        + " not installed. Attempting to install...."
                    )
                    if not self.bSystemIsNotLinux:
                        self.CheckToolsNeeded()
                    if not self.InstallLibrary(Module["install"], version=Module["version"]):
                        self.LogInfo("Error: unable to install library " + Module["install"])
                        ErrorOccured = True
                    if Module["import"] == "ldap3":
                        # This will correct and issue with the ldap3 modbule not being recogonized in LibrayIsInstalled
                        self.InstallLibrary("pyasn1", version=self.PYASN1_VERSION, update=True)

            return not ErrorOccured
        except Exception as e1:
            self.LogInfo("Error in CheckSystem: " + str(e1), LogLine=True)
            return False

    # ---------------------------------------------------------------------------
    def ExecuteCommandList(self, execute_list, env=None):

        try:
            process = Popen(execute_list, stdout=PIPE, stderr=PIPE, env=env)
            output, _error = process.communicate()

            # many tools write warnings to stderr, so only the return code is used
            if process.returncode != 0:
                self.LogInfo(
                    "Error in ExecuteCommandList: " + str(execute_list) + ": " + str(_error)
                )
                return False
            return True
        except Exception:
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
                    if not os.access(ConfigFilePath, os.R_OK):
                        pass
                except Exception as e1:
                    log.error("Error validating target directory: " + str(e1))

            # move files
            for File, Path in FileList.items():
                try:
                    SourceFile = Path + File
                    if os.path.isfile(SourceFile):
                        log.error("Moving " + SourceFile + " to " + ConfigFilePath)
                        if not MySupport.CopyFile(
                            SourceFile, os.path.join(ConfigFilePath, File), move=True, log=log
                        ):
                            log.error("Error: using alternate move method")
                            move(SourceFile, os.path.join(ConfigFilePath, File))
                        if not os.access(os.path.join(ConfigFilePath, File), os.R_OK):
                            pass
                except Exception as e1:
                    log.error("Error moving " + SourceFile + ": " + str(e1))
        except Exception as e1:
            log.error("Error moving files: " + str(e1))
        return True

    # ---------------------------------------------------------------------------
    # The leading numbers of a version, e.g. "2.0.0rc1" -> (2, 0, 0)
    @staticmethod
    def ParseVersion(value):

        Match = re.match(r"\d+(\.\d+)*", str(value).strip())
        if Match is None:
            return None
        return tuple(int(x) for x in Match.group(0).split("."))

    # ---------------------------------------------------------------------------
    # The installed version of a pip package, from the package information (the
    # library is not imported). None if it can not be found.
    @staticmethod
    def InstalledVersion(installname):

        if metadata is None:
            return None
        # "bleson @ git+https://..." -> "bleson"
        Name = re.split(r"[\s@=<>\[]", installname.strip())[0]
        try:
            return metadata.version(Name)
        except metadata.PackageNotFoundError:
            pass
        except Exception:
            return None
        # older Pythons do not match "pyopenssl" to "pyOpenSSL" or "-" to "_"
        Wanted = re.sub(r"[-_.]+", "-", Name).lower()
        try:
            for Dist in metadata.distributions():
                DistName = Dist.metadata["Name"] or ""
                if re.sub(r"[-_.]+", "-", DistName).lower() == Wanted:
                    return Dist.version
        except Exception:
            pass
        return None

    # ---------------------------------------------------------------------------
    # True if the library is installed (and at least version, if given). The
    # library is only found, not imported, unless testimport: importing every
    # library on each start is slow on a Pi.
    def LibraryIsInstalled(self, libraryname, version=None, installname=None, testimport=False):

        try:
            if testimport:
                importlib.import_module(libraryname)
            elif importlib.util.find_spec(libraryname) is None:
                return False
        except Exception:
            return False

        if version == None:
            return True
        Installed = self.InstalledVersion(installname or libraryname)
        if Installed is None:
            # e.g. installed by the OS package manager without package
            # information, so the version is not known
            return True
        InstalledTuple = self.ParseVersion(Installed)
        NeededTuple = self.ParseVersion(version)
        if InstalledTuple is None or NeededTuple is None:
            return True
        if InstalledTuple < NeededTuple:
            self.LogError("Need update on %s from %s to %s" % (libraryname, Installed, version))
            return False
        return True

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

            # pip writes warnings to stderr, so only the return code is used
            if process.returncode != 0:
                self.LogInfo(
                    "Error in InstallLibrary using pip : "
                    + str(install_list)
                    + ": "
                    + str(_error)
                )
                return False
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

        for Module, Settings in self.CachedConfig.items():
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
    # The default genloader.conf in the genmon conf folder:
    # {section: {option: value}}, in file order. Empty if it can not be read.
    def ReadTemplate(self):

        Template = collections.OrderedDict()
        try:
            parser = configparser.RawConfigParser(strict=False)
            if not parser.read(os.path.join(self.ConfPath, self.ConfigFileName)):
                self.LogError("Unable to read the default " + self.ConfigFileName)
                return Template
            for section in parser.sections():
                Template[section] = collections.OrderedDict(parser.items(section))
        except Exception as e1:
            self.LogInfo("Error in ReadTemplate: " + str(e1), LogLine=True)
        return Template

    # ---------------------------------------------------------------------------
    # Bring genloader.conf up to date with the default file: add the sections of
    # modules added since it was made, and options missing from a section.
    def UpdateFromTemplate(self, Sections):

        try:
            Template = self.ReadTemplate()
            for section, options in Template.items():
                if section == "genloader":
                    continue
                if section not in Sections:
                    self.LogError("Warning: Missing entry: " + section + ", adding entry")
                    self.config.WriteSection(section)
                    for option, value in options.items():
                        self.config.WriteValue(option, value, section=section)
                    continue
                self.config.SetSection(section)
                for option, value in options.items():
                    if not self.config.HasOption(option):
                        self.LogError("Adding " + option + " to " + section)
                        self.config.WriteValue(option, value, section=section)
                    elif option == "conffile" and len(value):
                        # an old genloader.conf may have an empty conffile
                        if not len(self.config.ReadValue("conffile", default="")):
                            self.LogError("Updated entry " + value)
                            self.config.WriteValue(option, value, section=section)
        except Exception as e1:
            self.LogInfo("Error in UpdateFromTemplate: " + str(e1), LogLine=True)

    # ---------------------------------------------------------------------------
    # Older versions gave genlog.py its file name on the command line, as
    # "args = -f <file>" in genloader.conf. Move it to genlog.conf (once).
    def MoveGenLogArgs(self):

        try:
            if not "genlog" in self.config.GetSections():
                return
            self.config.SetSection("genlog")
            Args = self.config.ReadValue("args", default="").split()
            if len(Args) != 2 or Args[0] not in ("-f", "--filename"):
                return
            GenLogConf = os.path.join(self.ConfigFilePath, "genlog.conf")
            if not os.path.isfile(GenLogConf):
                Default = os.path.join(self.ConfPath, "genlog.conf")
                if os.path.isfile(Default):
                    copyfile(Default, GenLogConf)
                else:
                    with open(GenLogConf, "w") as f:
                        f.write("[genlog]\n")
            if not MyConfig(filename=GenLogConf, section="genlog", log=self.log).WriteValue(
                "filename", Args[1]
            ):
                self.LogError("Error writing the genlog file name to " + GenLogConf)
                return  # keep args, try again next time
            self.config.WriteValue("args", "", section="genlog")
            self.LogError("Moved the genlog file name (" + Args[1] + ") from genloader.conf to " + GenLogConf)
        except Exception as e1:
            self.LogInfo("Error in MoveGenLogArgs: " + str(e1), LogLine=True)

    # ---------------------------------------------------------------------------
    def UpdateIfNeeded(self):

        try:
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
                pass
                #self.LogInfo("Running one time maintenance check")

            # TODO other version checks can be added here

            self.version = ProgramDefaults.GENMON_VERSION

        except Exception as e1:
            self.LogInfo("Error in UpdateIfNeeded: " + str(e1), LogLine=True)

    # ---------------------------------------------------------------------------
    # Misc maint to perform when genmon is stopped
    def Maintenance(self):

        # rename templogs folder to sensordata
        self.OldSensorLogPath = os.path.join(self.ConfigFilePath, "templogs")
        if os.path.isdir(self.OldSensorLogPath):
            self.NewSensorLogPath = os.path.join(self.ConfigFilePath, "sensordata")
            os.rename(self.OldSensorLogPath, self.NewSensorLogPath)
            try:
                from pathlib import Path
                directory = Path(self.NewSensorLogPath)

                # 2. Use wildcard to find files and rename them in a loop
                old_prefix = "templog"
                new_prefix = "sensor"
                for file_path in directory.glob(f"{old_prefix}*"):
                    if file_path.is_file():
                        new_name = file_path.name.removeprefix(old_prefix)
                        new_file_path = file_path.with_name(f"{new_prefix}{new_name}")
                        
                        # Rename the file
                        file_path.rename(new_file_path)
                        self.LogError(f"Renamed: {file_path.name} -> {new_file_path.name}")

            except Exception as e1:
                self.LogError("Error renaming sensor data files: " + str(e1))

    # ---------------------------------------------------------------------------
    def GetConfig(self):

        # start over, this is also called again after the file is replaced
        self.CachedConfig = {}
        try:

            Sections = self.config.GetSections()
            for entry in ["genmon", "genserv"]:
                if not entry in Sections:
                    self.LogError(
                        "Warning: Missing entry: " + entry + " , file corruption. "
                    )
                    return False
            if not "genloader" in Sections:
                self.LogError("Adding entry: genloader")
                self.config.WriteSection("genloader")

            # sections in the default genloader.conf are the known modules
            self.UpdateFromTemplate(Sections)
            self.MoveGenLogArgs()
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

                TempDict["pid"] = 0
                self.CachedConfig[SectionName] = TempDict

            # the PIDs of the running modules
            PIDs = self.MovePIDsFromConfig(self.ReadPIDs())
            for SectionName, PID in PIDs.items():
                if SectionName in self.CachedConfig:
                    self.CachedConfig[SectionName]["pid"] = PID
            return True

        except Exception as e1:
            self.LogInfo("Error parsing config file: " + str(e1), LogLine=True)
            return False
        return True

    # ---------------------------------------------------------------------------
    def GetLoadOrder(self):

        LoadOrder = []
        LoadDict = {}
        try:
            for Module, Settings in self.CachedConfig.items():
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
                ErrorOccured = True
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

                    if not self.MultiInstance:
                        # check that module is not loaded already, if it is then force it (hard) to unload
                        attempts = 0
                        while True:
                            if MySupport.IsRunning(
                                prog_name=self.CachedConfig[Module]["module"],
                                log=self.log,
                                multi_instance=self.MultiInstance,
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
    def LoadModule(self, path, modulename, args=None):
        try:
            fullmodulename = os.path.join(path, modulename)

            # args is None if the section in genloader.conf has no args entry
            if args != None and not len(args.strip()):
                args = None

            if args != None:
                self.LogConsole("Starting " + fullmodulename + " " + args)
            else:
                self.LogConsole("Starting " + fullmodulename)

            # genloader exits after starting the modules, so nothing would read a
            # pipe; a module writing to a closed pipe gets BrokenPipeError
            OutputStream = subprocess.DEVNULL

            executelist = [sys.executable, fullmodulename]
            if args != None:
                executelist.extend(args.split())
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
                if not self.PIDIsModule(pid, modulename):
                    # the module is not running, and the PID may now belong
                    # to another program
                    self.LogInfo(
                        "Not stopping PID " + str(pid) + ", it is not " + modulename
                    )
                    return self.UpdatePID(modulename, "")
                if self.bSystemIsNotLinux:
                    if self.bSystemIsWindows:
                        LoadInfo.append("taskkill")
                        LoadInfo.append("/PID")
                        LoadInfo.append(str(pid))
                        LoadInfo.append("/T")
                        LoadInfo.append("/F")
                    else:
                        self.LogError("ERROR in UnloadModule: This OS is not support at this time")
                        return False
                else:
                    LoadInfo.append("kill")
                    if HardStop or self.HardStop:
                        LoadInfo.append("-9")
                    LoadInfo.append(str(pid))
            else:
                if self.bSystemIsNotLinux:
                    self.LogError("HARDKILL is not support under non linux platforms at this time")
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
            process.communicate()
            return self.UpdatePID(modulename, "")

        except Exception as e1:
            self.LogInfo("Error unoading module: (" + str(modulename) +"): " + str(e1), LogLine=True)
            self.LogInfo(f"Module: {modulename} PID: {pid}, UsePID: {UsePID} Hardstop: {HardStop}")
            return False

    # ---------------------------------------------------------------------------
    # True if process pid is running modulename. The PID saved in genloader.conf
    # is old if the module stopped or crashed, and the system may have given the
    # PID to another program since.
    def PIDIsModule(self, pid, modulename):

        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return False
        try:
            import psutil

            try:
                CommandLine = psutil.Process(pid).cmdline()
            except psutil.NoSuchProcess:  # also a zombie process
                return False
            except psutil.AccessDenied:
                return True  # can not tell, stop it as before
        except ImportError:
            ProcFile = "/proc/%d/cmdline" % pid
            if not os.path.isdir("/proc"):
                return True  # can not tell, stop it as before
            if not os.path.isfile(ProcFile):
                return False
            try:
                with open(ProcFile, "rb") as f:
                    CommandLine = [
                        a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a
                    ]
            except Exception:
                return True  # can not tell, stop it as before
        except Exception as e1:
            self.LogInfo("Error in PIDIsModule: " + str(e1), LogLine=True)
            return True
        # e.g. python3 /home/pi/genmon/addon/genlog.py -c /etc/genmon/
        return any(os.path.basename(arg) == modulename for arg in CommandLine)

    # ---------------------------------------------------------------------------
    # The PIDs of the started modules are kept in genloader.pids in the config
    # folder ({"genmon": 1234, ...}), not in genloader.conf, so genloader.conf
    # only changes when its settings do. Returns None if the file does not exist.
    def ReadPIDs(self):

        if not os.path.isfile(self.PIDFile):
            return None
        try:
            with open(self.PIDFile) as f:
                Data = json.load(f)
            PIDs = {}
            for Section, PID in Data.items():
                try:
                    PIDs[str(Section)] = int(PID)
                except (TypeError, ValueError):
                    pass
            return PIDs
        except Exception as e1:
            self.LogError("Error reading " + self.PIDFile + ": " + str(e1))
            return {}

    # ---------------------------------------------------------------------------
    def WritePIDs(self, PIDs):

        try:
            AtomicWrite(self.PIDFile, json.dumps(PIDs, indent=1, sort_keys=True) + "\n")
            return True
        except Exception as e1:
            self.LogError("Error writing " + self.PIDFile + ": " + str(e1))
            return False

    # ---------------------------------------------------------------------------
    # Older versions kept each module's PID as "pid" in genloader.conf. If
    # genloader.pids does not exist yet, they are moved there; otherwise (e.g.
    # an old genloader.conf was restored) the old entries are only removed.
    # Returns the PIDs to use.
    def MovePIDsFromConfig(self, PIDs):

        try:
            OldPIDs = {}
            for Section in self.config.GetSections():
                self.config.SetSection(Section)
                if self.config.HasOption("pid"):
                    OldPIDs[Section] = self.config.ReadValue(
                        "pid", return_type=int, default=0, NoLog=True
                    )
            if PIDs is None:
                PIDs = {Section: PID for Section, PID in OldPIDs.items() if PID}
                if not self.WritePIDs(PIDs):
                    return PIDs  # keep the old entries, try again next time
                if len(OldPIDs):
                    self.LogError("Moved the module PIDs from genloader.conf to " + self.PIDFile)
            elif len(OldPIDs):
                self.LogError("Removed old PID entries from genloader.conf")
            for Section in OldPIDs:
                self.config.WriteValue("pid", "", remove=True, section=Section)
            return PIDs
        except Exception as e1:
            self.LogInfo("Error in MovePIDsFromConfig: " + str(e1), LogLine=True)
            return PIDs or {}

    # ---------------------------------------------------------------------------
    # Save (or with pid "" forget) the PID of a module
    def UpdatePID(self, modulename, pid=None):

        try:
            Section = os.path.splitext(modulename)[0]  # remove extension
            PIDs = self.ReadPIDs() or {}
            if pid in (None, "", 0):
                PIDs.pop(Section, None)
            else:
                PIDs[Section] = int(pid)
            return self.WritePIDs(PIDs)
        except Exception as e1:
            self.LogInfo("Error writing PID for " + modulename + " : " + str(e1))
            return False


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

    if not Loader.IsWindows():
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
        multi_instance=multi_instance,
    )
