#-------------------------------------------------------------------------------
#    FILE: genloader.py
# PURPOSE: app for loading specific moduels for genmon
#
#  AUTHOR: Jason G Yates
#    DATE: 12-Sept-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import time, sys, os, getopt, subprocess
from subprocess import PIPE, Popen, call
from shutil import copyfile

try:
    from genmonlib import mylog, mysupport, myconfig

except Excpetion as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)

#------------ Loader class -----------------------------------------------------
class Loader(mysupport.MySupport):

    def __init__(self,
        start = False,
        stop = False,
        hardstop = False,
        loglocation = "/var/log/",
        log = None,
        localinit = False,
        ConfigFilePath = None):

        self.Start = start
        self.Stop = stop
        self.HardStop = hardstop

        if ConfigFilePath == None:
            self.ConfigFilePath = "/etc/"
        else:
            self.ConfigFilePath = ConfigFilePath

        self.ConfigFileName = "genloader.conf"
        # log errors in this module to a file
        if localinit == True:
            self.configfile = self.ConfigFileName
        else:
            self.configfile = self.ConfigFilePath + self.ConfigFileName

        self.ModulePath = os.path.dirname(os.path.realpath(__file__)) + "/"

        # log errors in this module to a file
        if log == None:
            self.log = mylog.SetupLogger("genloader", loglocation + "genloader.log")
        else:
            self.log = log

        self.console = mylog.SetupLogger("genloader_console", log_file = "", stream = True)

        try:
            if self.Start:
                if not self.CheckSystem():
                    self.LogInfo("Error check system readiness. Exiting")
                    sys.exit(2)

            self.CachedConfig = {}

            # check to see if genloader.conf is present, if not copy it from genmon directory
            if not os.path.isfile(self.configfile):
                self.LogInfo("Warning: unable to find config file: " + self.configfile + " Copying file to /etc/ directory.")
                if os.path.isfile(self.ModulePath + self.ConfigFileName):
                    copyfile(self.ModulePath + self.ConfigFileName , self.configfile)
                else:
                    self.LogInfo("Unable to find config file.")
                    sys.exit(2)

            self.config = myconfig.MyConfig(filename = self.configfile, section = "genmon", log = self.log)
            if not self.GetConfig():
                self.LogInfo("Error reading config file. Exiting")
                sys.exit(2)

            if not self.ValidateConfig():
                self.LogInfo("Error validating config. Exiting")
                sys.exit(2)

            self.LoadOrder = self.GetLoadOrder()

            if self.Stop:
                self.StopModules()
                time.sleep(1)

            if self.Start:
                self.StartModules()
        except Exception as e1:
            self.LogErrorLine("Error in init: " + str(e1))

    #---------------------------------------------------------------------------
    def CheckSystem(self):

        # this function checks the system to see if the required libraries are
        # installed. If they are not then an attempt is made to install them.
        ModuleList = [
            # [import name , install name]
            ['flask','flask'],
            ['configparser','configparser'],
            ['serial','pyserial'],
            ['crcmod','crcmod'],
            ['pyowm','pyowm'],
            ['pytz','pytz']
        ]
        try:
            ErrorOccured = False
            for Module in ModuleList:
                if not self.LibraryIsInstalled(Module[0]):
                    self.LogInfo("Warning: required library " + Module[1] + " not installed. Attempting to install....")
                    self.LogConsole("Warning: required library " + Module[1] + " not installed. Attempting to install....")
                    if not self.InstallLibrary(Module[1]):
                        self.LogInfo("Error: unable to install library " + Module[1])
                        ErrorOccured = True
            return not ErrorOccured
        except Exception as e1:
            self.LogInfo("Error in CheckSystem: " + str(e1), LogLine = True)
            return False
    #---------------------------------------------------------------------------
    def LibraryIsInstalled(self, libraryname):

        try:
            import importlib
            my_module = importlib.import_module(libraryname)
            return True
        except Exception as e1:
            return False

    #---------------------------------------------------------------------------
    def InstallLibrary(self, libraryname):

        try:
            process = Popen(['pip','install', libraryname], stdout=PIPE, stderr=PIPE)
            output, _error = process.communicate()

            if _error:
                self.LogConsole("Error in InstallLibrary: " + libraryname + ": " + str(_error))
            rc = process.returncode
            return True

        except Exception as e1:
            self.LogInfo("Error installing module: " + libraryname + ": "+ str(e1), LogLine = True)
            return False
    #---------------------------------------------------------------------------
    def LogInfo(self, message, LogLine = False):
        self.LogConsole(message)
        if not LogLine:
            self.LogError(message)
        else:
            self.LogErrorLine(message)
    #---------------------------------------------------------------------------
    def ValidateConfig(self):

        ErrorOccured = False
        if not len(self.CachedConfig):
            self.LogInfo("Error: Empty configruation found.")
            return False

        for Module, Settiings in self.CachedConfig.items():
            try:
                if self.CachedConfig[Module]["enable"]:
                    if not os.path.isfile(self.ModulePath + self.CachedConfig[Module]["module"]):
                        self.LogInfo("Enable to find file " + self.ModulePath + self.CachedConfig[Module]["module"])
                        ErrorOccured = True

                # validate config file and if it is not there then copy it.
                if not self.CachedConfig[Module]["conffile"] == None and len(self.CachedConfig[Module]["conffile"]):
                    if not os.path.isfile(self.ConfigFilePath + self.CachedConfig[Module]["conffile"]):
                        if os.path.isfile(self.ModulePath + self.CachedConfig[Module]["conffile"]):
                            self.LogInfo("Copying " + self.CachedConfig[Module]["conffile"] + " to " + self.ConfigFilePath )
                            copyfile(self.ModulePath + self.CachedConfig[Module]["conffile"] , self.ConfigFilePath + self.CachedConfig[Module]["conffile"])
                        else:
                            self.LogInfo("Enable to find config file " + self.ModulePath + self.CachedConfig[Module]["conffile"])
                            ErrorOccured = True
            except Exception as e1:
                self.LogInfo("Error validating config for " + Module + " : " + str(e1), LogLine = True)
                return False

        return not ErrorOccured
    #---------------------------------------------------------------------------
    def GetConfig(self):

        try:

            Sections = self.config.GetSections()

            for SectionName in Sections:
                TempDict = {}
                self.config.SetSection(SectionName)
                if self.config.HasOption('module'):
                    TempDict['module'] = self.config.ReadValue('module')
                else:
                    TempDict['module'] = None

                if self.config.HasOption('enable'):
                    TempDict['enable'] = self.config.ReadValue('enable', return_type = bool)
                else:
                    TempDict['enable'] = False

                if self.config.HasOption('hardstop'):
                    TempDict['hardstop'] = self.config.ReadValue('hardstop', return_type = bool)
                else:
                    TempDict['hardstop'] = False

                if self.config.HasOption('conffile'):
                    TempDict['conffile'] = self.config.ReadValue('conffile')
                else:
                    TempDict['conffile'] = None

                if self.config.HasOption('args'):
                    TempDict['args'] = self.config.ReadValue('args')
                else:
                    TempDict['args'] = None

                if self.config.HasOption('priority'):
                    TempDict['priority'] = self.config.ReadValue('priority', return_type = int, default = None)
                else:
                    TempDict['priority'] = None

                if self.config.HasOption('postloaddelay'):
                    TempDict['postloaddelay'] = self.config.ReadValue('postloaddelay', return_type = int, default = 0)
                else:
                    TempDict['postloaddelay'] = 0

                self.CachedConfig[SectionName] = TempDict
            return True

        except Exception as e1:
            self.LogInfo("Error parsing config file: " + str(e1), LogLine = True)
            return False

    #---------------------------------------------------------------------------
    def ConvertToInt(self, value, default = None):

        try:
            return int(str(value))
        except:
            return default

    #---------------------------------------------------------------------------
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
                    self.LogInfo("Error reading load order (retrying): " + str(e1), LogLine = True)

            for key, value in sorted(LoadDict.iteritems(), key=lambda (k,v): (v,k)):
                LoadOrder.append(key)
        except Exception as e1:
            self.LogInfo("Error reading load order: " + str(e1), LogLine = True)

        return LoadOrder
    #---------------------------------------------------------------------------
    def StopModules(self):

        self.LogConsole("Stopping....")
        if not len(self.LoadOrder):
            self.LogInfo("Error, nothing to stop.")
            return False
        ErrorOccured = False
        for Module in reversed(self.LoadOrder):
            try:
                if not self.UnloadModule(self.CachedConfig[Module]["module"], HardStop = self.CachedConfig[Module]["hardstop"]):
                    self.LogInfo("Error stopping " + Module)
                    ErrorOccured = True
            except Exception as e1:
                self.LogInfo("Error stopping module " + Module + " : " + str(e1), LogLine = True)
                return False
        return not ErrorOccured
    #---------------------------------------------------------------------------
    def StartModules(self):

        self.LogConsole("Starting....")
        if not len(self.LoadOrder):
            self.LogInfo("Error, nothing to start.")
            return False
        ErrorOccured = False
        for Module in self.LoadOrder:
            try:
                if self.CachedConfig[Module]["enable"]:
                    if not self.LoadModule(self.ModulePath + self.CachedConfig[Module]["module"], args = self.CachedConfig[Module]["args"]):
                        self.LogInfo("Error starting " + Module)
                        ErrorOccured = True
                    if not self.CachedConfig[Module]["postloaddelay"] == None and self.CachedConfig[Module]["postloaddelay"] > 0:
                        time.sleep(self.CachedConfig[Module]["postloaddelay"])
            except Exception as e1:
                self.LogInfo("Error starting module " + Module + " : " + str(e1), LogLine = True)
                return False
        return not ErrorOccured
    #---------------------------------------------------------------------------
    def LoadModule(self, modulename, args = None):
        try:
            self.LogConsole("Starting " + modulename)
            # to load as a background process we just use os.system since Popen
            # is problematic in doing this
            CommandString = "python " + modulename
            if args != None and len(args):
                CommandString += " " + args
            CommandString += " &"
            os.system(CommandString)
            return True

        except Exception as e1:
            self.LogInfo("Error loading module: " + str(e1), LogLine = True)
            return False

    #---------------------------------------------------------------------------
    def UnloadModule(self, modulename, HardStop = False):
        try:
            self.LogConsole("Stopping " + modulename)
            LoadInfo = []
            LoadInfo.append('pkill')
            if HardStop or self.HardStop:
                LoadInfo.append('-9')
            LoadInfo.append('-u')
            LoadInfo.append('root')
            LoadInfo.append('-f')
            LoadInfo.append(modulename)

            process = Popen(LoadInfo, stdout=PIPE)
            output, _error = process.communicate()
            rc = process.returncode
            return True

        except Exception as e1:
            self.LogInfo("Error loading module: " + str(e1), LogLine = True)
            return False

#------------------main---------------------------------------------------------
if __name__ == '__main__':


    HelpStr =  "\npython genloader.py [-s -r -x -z]\n"
    HelpStr += "   Example: python genloader.py -s\n"
    HelpStr += "            python genloader.py -r\n"
    HelpStr += "\n      -s  Start Genmon modules"
    HelpStr += "\n      -r  Restart Genmon moduels"
    HelpStr += "\n      -x  Stop Genmon modules"
    HelpStr += "\n      -z  Hard stop Genmon modules"
    HelpStr += "\n \n"

    if os.geteuid() != 0:
        print("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.")
        sys.exit(2)

    try:
        opts, args = getopt.getopt(sys.argv[1:],"hsrx",["help","start","restart","exit","hardstop"])
    except getopt.GetoptError:
        print(HelpStr)
        sys.exit(2)

    StopModules = False
    StartModules = False
    HardStop = False

    for opt, arg in opts:
        if opt == '-h':
            print HelpStr
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

    if not StartModules and not StopModules:
        print("\nNo option selected.\n")
        print(HelpStr)
        sys.exit(2)

    LoaderObject = Loader(start = StartModules, stop = StopModules, hardstop = HardStop)
