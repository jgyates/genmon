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
from shutil import move

try:
    from genmonlib.mysupport import MySupport
    from genmonlib.mylog import SetupLogger
    from genmonlib.myconfig import MyConfig
    from genmonlib.program_defaults import ProgramDefaults

except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)

#------------ Loader class -----------------------------------------------------
class Loader(MySupport):

    def __init__(self,
        start = False,
        stop = False,
        hardstop = False,
        loglocation = ProgramDefaults.LogPath,
        log = None,
        localinit = False,
        ConfigFilePath = ProgramDefaults.ConfPath):

        self.Start = start
        self.Stop = stop
        self.HardStop = hardstop


        self.ConfigFilePath = ConfigFilePath

        self.ConfigFileName = "genloader.conf"
        # log errors in this module to a file
        if localinit == True:
            self.configfile = self.ConfigFileName
        else:
            self.configfile = self.ConfigFilePath + self.ConfigFileName

        self.ModulePath = os.path.dirname(os.path.realpath(__file__)) + "/"
        self.ConfPath = os.path.dirname(os.path.realpath(__file__)) + "/conf/"


        # log errors in this module to a file
        if log == None:
            self.log = SetupLogger("genloader", loglocation + "genloader.log")
        else:
            self.log = log

        self.console = SetupLogger("genloader_console", log_file = "", stream = True)

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
                    self.LogInfo("Error creating target config directory: " + str(e1), LogLine = True)

            # check to see if genloader.conf is present, if not copy it from genmon directory
            if not os.path.isfile(self.configfile):
                self.LogInfo("Warning: unable to find config file: " + self.configfile + " Copying file to " + self.ConfigFilePath +  " directory.")
                if os.path.isfile(self.ConfPath + self.ConfigFileName):
                    copyfile(self.ConfPath + self.ConfigFileName , self.configfile)
                else:
                    self.LogInfo("Unable to find config file.")
                    sys.exit(2)

            self.config = MyConfig(filename = self.configfile, section = "genmon", log = self.log)
            if not self.GetConfig():
                self.LogInfo("Error reading config file. Exiting")
                sys.exit(2)

            if not self.ValidateConfig():
                self.LogInfo("Error validating config. Exiting")
                sys.exit(2)

            self.LoadOrder = self.GetLoadOrder()

            if self.Stop:
                self.StopModules()
                time.sleep(2)

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
                    if not self.InstallLibrary(Module[1]):
                        self.LogInfo("Error: unable to install library " + Module[1])
                        ErrorOccured = True
            return not ErrorOccured
        except Exception as e1:
            self.LogInfo("Error in CheckSystem: " + str(e1), LogLine = True)
            return False

    #---------------------------------------------------------------------------
    @staticmethod
    def OneTimeMaint(ConfigFilePath, log):

        FileList = {
              "feedback.json" : os.path.dirname(os.path.realpath(__file__)) + "/",
              "outage.txt" : os.path.dirname(os.path.realpath(__file__)) + "/",
              "kwlog.txt" : os.path.dirname(os.path.realpath(__file__)) + "/",
              "maintlog.json" : os.path.dirname(os.path.realpath(__file__)) + "/",
              "Feedback_dat" : os.path.dirname(os.path.realpath(__file__)) + "/genmonlib/",
              "Message_dat" : os.path.dirname(os.path.realpath(__file__)) + "/genmonlib/",
              'genmon.conf' : "/etc/",
              'genserv.conf': "/etc/",
              'gengpio.conf' : "/etc/",
              'gengpioin.conf': "/etc/",
              'genlog.conf' : "/etc/",
              'gensms.conf' : "/etc/",
              'gensms_modem.conf': "/etc/",
              'genpushover.conf': "/etc/",
              'gensyslog.conf' : "/etc/",
              'genmqtt.conf' : "/etc/",
              'genslack.conf': "/etc/",
              'genexercise.conf' : "/etc/",
              'genemail2sms.conf' :  "/etc/",
              'genloader.conf' :  "/etc/",
              'mymail.conf' : "/etc/",
              'mymodem.conf' : "/etc/"
        }
        try:
            # Check to see if we have done this already by checking files in the genmon source directory
            if (not os.path.isfile(os.path.dirname(os.path.realpath(__file__)) + "/genmonlib/Message_dat") and
            not os.path.isfile(os.path.dirname(os.path.realpath(__file__)) + "/maintlog.json") and
            not os.path.isfile(os.path.dirname(os.path.realpath(__file__)) + "/outage.txt") and
            not os.path.isfile(os.path.dirname(os.path.realpath(__file__)) + "/kwlog.txt") and
            not os.path.isfile("/etc/genmon.conf")):
                return False
            # validate target directory
            if not os.path.isdir(ConfigFilePath):
                try:
                    os.mkdir(ConfigFilePath)
                    if not os.access(ConfigFilePath + File, os.R_OK):
                        pass
                except Exception as e1:
                    log.error("Error validating target directory: " + str(e1), LogLine = True)

            # move files
            for File, Path in FileList.items():
                try:
                    SourceFile = Path + File
                    if os.path.isfile(SourceFile):
                        log.error("Moving " + SourceFile + " to " + ConfigFilePath )
                        if not MySupport.CopyFile(SourceFile, ConfigFilePath + File, move = True, log = log):
                            log.error("Error: using alternate move method")
                            move(SourceFile , ConfigFilePath + File)
                        if not os.access(ConfigFilePath + File, os.R_OK):
                            pass
                except Exception as e1:
                    log.error("Error moving " + SourceFile)
        except Exception as e1:
            log.error("Error moving files: " + str(e1), LogLine = True)
        return True

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
                self.LogInfo("Error in InstallLibrary using pip : " + libraryname + " : " + str(_error))
            rc = process.returncode
            return True

        except Exception as e1:
            self.LogInfo("Error installing module: " + libraryname + ": "+ str(e1), LogLine = True)
            return False
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
                    ConfFileList = self.CachedConfig[Module]["conffile"].split(",")
                    for ConfigFile in ConfFileList:
                        ConfigFile = ConfigFile.strip()
                        if not os.path.isfile(self.ConfigFilePath + ConfigFile):
                            if os.path.isfile(self.ConfPath + ConfigFile):
                                self.LogInfo("Copying " + ConfigFile + " to " + self.ConfigFilePath )
                                copyfile(self.ConfPath + ConfigFile , self.ConfigFilePath + ConfigFile)
                            else:
                                self.LogInfo("Enable to find config file " + self.ConfPath + ConfigFile)
                                ErrorOccured = True
            except Exception as e1:
                self.LogInfo("Error validating config for " + Module + " : " + str(e1), LogLine = True)
                return False

        return not ErrorOccured

    #---------------------------------------------------------------------------
    def AddEntry(self, section = None, module = None, conffile = "", args = "", priority = '2'):

        try:
            if section == None or module == None:
                return
            self.config.WriteSection(section)
            self.config.WriteValue('module', module, section = section)
            self.config.WriteValue('enable', 'False', section = section)
            self.config.WriteValue('hardstop', 'False', section = section)
            self.config.WriteValue('conffile', conffile, section = section)
            self.config.WriteValue('args', args, section = section)
            self.config.WriteValue('priority', priority, section = section)
        except Exception as e1:
            self.LogInfo("Error in AddEntry: " + str(e1), LogLine = True)
        return

    #---------------------------------------------------------------------------
    def UpdateIfNeeded(self):

        try:
            self.config.SetSection("gengpioin")
            if not self.config.HasOption('conffile'):
                self.config.WriteValue('conffile', "gengpioin.conf", section = "gengpioin")
                self.LogError("Updated entry gengpioin.conf")
            else:
                defValue = self.config.ReadValue('conffile', default = "")
                if not len(defValue):
                    self.config.WriteValue('conffile', "gengpioin.conf", section = "gengpioin")
                    self.LogError("Updated entry gengpioin.conf")

        except Exception as e1:
            self.LogInfo("Error in UpdateIfNeeded: " + str(e1), LogLine = True)

    #---------------------------------------------------------------------------
    def GetConfig(self):

        try:

            Sections = self.config.GetSections()
            ValidSections = ['genmon', 'genserv', 'gengpio', 'gengpioin', 'genlog', 'gensms', 'gensms_modem', 'genpushover', 'gensyslog', 'genmqtt', 'genslack', 'genexercise', 'genemail2sms', 'gentankutil', 'genalexa']
            for entry in ValidSections:
                if not entry in Sections:
                    if entry == 'genslack':
                        self.LogError("Warning: Missing entry: " + entry + " , adding entry")
                        self.AddEntry(section = entry, module = 'genslack.py', conffile = 'genslack.conf')
                    if entry == 'genexercise':
                        self.LogError("Warning: Missing entry: " + entry + " , adding entry")
                        self.AddEntry(section = entry, module = 'genexercise.py', conffile = 'genexercise.conf')
                    if entry == 'genemail2sms':
                        self.LogError("Warning: Missing entry: " + entry + " , adding entry")
                        self.AddEntry(section = entry, module = 'genemail2sms.py', conffile = 'genemail2sms.conf')
                    if entry == 'gentankutil':
                        self.LogError("Warning: Missing entry: " + entry + " , adding entry")
                        self.AddEntry(section = entry, module = 'gentankutil.py', conffile = 'gentankutil.conf')
                    if entry == 'genalexa':
                        self.LogError("Warning: Missing entry: " + entry + " , adding entry")
                        self.AddEntry(section = entry, module = 'genalexa.py', conffile = 'genalexa.conf')
                    else:
                        self.LogError("Warning: Missing entry: " + entry)

            self.UpdateIfNeeded()

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

                if self.config.HasOption('pid'):
                    TempDict['pid'] = self.config.ReadValue('pid', return_type = int, default = 0, NoLog = True)
                else:
                    TempDict['pid'] = 0

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
            #lambda kv: (-kv[1], kv[0])
            for key, value in sorted(LoadDict.items(), key=lambda kv: (-kv[1], kv[0])):
            #for key, value in sorted(LoadDict.iteritems(), key=lambda (k,v): (v,k)):
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
        for Module in self.LoadOrder:
            try:
                if not self.UnloadModule(self.ModulePath, self.CachedConfig[Module]["module"], pid = self.CachedConfig[Module]["pid"],HardStop = self.CachedConfig[Module]["hardstop"], UsePID = True):
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
        for Module in reversed(self.LoadOrder):
            try:
                if self.CachedConfig[Module]["enable"]:
                    if not self.LoadModule(self.ModulePath, self.CachedConfig[Module]["module"], args = self.CachedConfig[Module]["args"]):
                        self.LogInfo("Error starting " + Module)
                        ErrorOccured = True
                    if not self.CachedConfig[Module]["postloaddelay"] == None and self.CachedConfig[Module]["postloaddelay"] > 0:
                        time.sleep(self.CachedConfig[Module]["postloaddelay"])
            except Exception as e1:
                self.LogInfo("Error starting module " + Module + " : " + str(e1), LogLine = True)
                return False
        return not ErrorOccured
    #---------------------------------------------------------------------------
    def LoadModuleAlt(self, modulename, args = None):
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
            self.LogInfo("Error loading module: " + str(e1), LogLine = True)
            return False

    #---------------------------------------------------------------------------
    def LoadModule(self, path, modulename, args = None):
        try:
            fullmodulename = path + modulename
            if args != None:
                self.LogConsole("Starting " + fullmodulename + " " + args)
            else:
                self.LogConsole("Starting " + fullmodulename)
            try:
                from subprocess import DEVNULL # py3k
            except ImportError:
                import os
                DEVNULL = open(os.devnull, 'wb')

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
            pid = subprocess.Popen(executelist, stdout=OutputStream, stderr=OutputStream, stdin=OutputStream)
            self.UpdatePID(modulename, pid.pid)
            return True

        except Exception as e1:
            self.LogInfo("Error loading module " + modulename + ": " + str(e1), LogLine = True)
            return False
    #---------------------------------------------------------------------------
    def UnloadModule(self, path, modulename, pid = None, HardStop = False, UsePID = False):
        try:
            LoadInfo = []
            if UsePID:
                if pid == None or pid == "" or pid == 0:
                    return True
                LoadInfo.append("kill")
                if HardStop or self.HardStop:
                    LoadInfo.append('-9')
                LoadInfo.append(str(pid))
            else:
                LoadInfo.append('pkill')
                if HardStop or self.HardStop:
                    LoadInfo.append('-9')
                LoadInfo.append('-u')
                LoadInfo.append('root')
                LoadInfo.append('-f')
                LoadInfo.append(modulename)

            self.LogConsole("Stopping " + modulename)
            process = Popen(LoadInfo, stdout=PIPE)
            output, _error = process.communicate()
            rc = process.returncode
            self.UpdatePID(modulename, "")
            return True

        except Exception as e1:
            self.LogInfo("Error loading module: " + str(e1), LogLine = True)
            return False
    #---------------------------------------------------------------------------
    def UpdatePID(self, modulename, pid = None):

        try:
            filename = os.path.splitext(modulename)[0]    # remove extension
            self.config.SetSection(filename)
            self.config.WriteValue("pid", str(pid))
        except Exception as e1:
            self.LogInfo("Error writing PID for " + modulename + " : " + str(e1))

#------------------main---------------------------------------------------------
if __name__ == '__main__':


    HelpStr =  "\npython genloader.py [-s -r -x -z -c configfilepath]\n"
    HelpStr += "   Example: python genloader.py -s\n"
    HelpStr += "            python genloader.py -r\n"
    HelpStr += "\n      -s  Start Genmon modules"
    HelpStr += "\n      -r  Restart Genmon moduels"
    HelpStr += "\n      -x  Stop Genmon modules"
    HelpStr += "\n      -z  Hard stop Genmon modules"
    HelpStr += "\n      -c  Path of genmon.conf file i.e. /etc/"
    HelpStr += "\n \n"

    if os.geteuid() != 0:
        print("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.")
        sys.exit(2)

    try:
        ConfigFilePath = ProgramDefaults.ConfPath
        opts, args = getopt.getopt(sys.argv[1:],"hsrxzc:",["help","start","restart","exit","hardstop","configpath="])
    except getopt.GetoptError:
        print(HelpStr)
        sys.exit(2)

    StopModules = False
    StartModules = False
    HardStop = False

    for opt, arg in opts:
        if opt == '-h':
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
    if (Loader.OneTimeMaint(ConfigFilePath, tmplog)):
        time.sleep(1.5)
    port, loglocation = MySupport.GetGenmonInitInfo(ConfigFilePath, log = None)
    LoaderObject = Loader(start = StartModules, stop = StopModules, hardstop = HardStop, ConfigFilePath = ConfigFilePath, loglocation = loglocation)
