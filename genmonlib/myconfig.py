#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: myconfig.py
# PURPOSE: Configuration file Abstraction
#
#  AUTHOR: Jason G Yates
#    DATE: 22-May-2018
#
# MODIFICATIONS:
#
# USAGE: This is the base class of used to abstract gauges and graphs, etc
# LogError or FatalError should be used to log errors or fatal errors.
#
#-------------------------------------------------------------------------------

import threading
try:
    from ConfigParser import RawConfigParser
except ImportError as e:
    from configparser import RawConfigParser

from genmonlib.mycommon import MyCommon
from genmonlib.program_defaults import ProgramDefaults

class MyConfig (MyCommon):
    #---------------------MyConfig::__init__------------------------------------
    def __init__(self, filename = None, section = None, simulation = False, log = None):

        super(MyConfig, self).__init__()
        self.log = log
        self.FileName = filename
        self.Section = section
        self.Simulation = simulation
        self.CriticalLock = threading.Lock()        # Critical Lock (writing conf file)
        self.InitComplete = False
        try:
            self.config = RawConfigParser()
            self.config.read(self.FileName)

            if self.Section == None:
                SectionList = self.GetSections()
                if len(SectionList):
                    self.Section = SectionList[0]

        except Exception as e1:
            self.LogErrorLine("Error in MyConfig:init: " + str(e1))
            return
        self.InitComplete = True
    #---------------------MyConfig::HasOption-----------------------------------
    def HasOption(self, Entry):

        return self.config.has_option(self.Section, Entry)

    #---------------------MyConfig::GetList-------------------------------------
    def GetList(self):

        return self.config.items(self.Section)

    #---------------------MyConfig::GetSections---------------------------------
    def GetSections(self):

        return self.config.sections()

    #---------------------MyConfig::SetSection----------------------------------
    def SetSection(self, section):

        if self.Simulation:
            return True
        if not (isinstance(section, str) or isinstance(section, unicode)) or not len(section):
            self.LogError("Error in MyConfig:ReadValue: invalid section: " + str(section))
            return False
        self.Section = section
        return True
    #---------------------MyConfig::ReadValue-----------------------------------
    def ReadValue(self, Entry, return_type = str, default = None, section = None, NoLog = False):

        try:

            if section != None:
                self.SetSection(section)

            if self.config.has_option(self.Section, Entry):
                if return_type == str:
                    return self.config.get(self.Section, Entry)
                elif return_type == bool:
                    return self.config.getboolean(self.Section, Entry)
                elif return_type == float:
                    return self.config.getfloat(self.Section, Entry)
                elif return_type == int:
                    return self.config.getint(self.Section, Entry)
                else:
                    self.LogErrorLine("Error in MyConfig:ReadValue: invalid type:" + str(return_type))
                    return default
            else:
                return default
        except Exception as e1:
            if not NoLog:
                self.LogErrorLine("Error in MyConfig:ReadValue: " + Entry + ": " + str(e1))
            return default


    #---------------------MyConfig::WriteSection--------------------------------
    def WriteSection(self, SectionName):

        if self.Simulation:
            return True

        SectionList = self.GetSections()

        if SectionName in SectionList:
            self.LogError("Error in WriteSection: Section already exist.")
            return True
        try:
            with self.CriticalLock:
                with open(self.FileName, "a") as ConfigFile:
                    ConfigFile.write("[" + SectionName + "]")
                    ConfigFile.flush()
                    ConfigFile.close()
                    # update the read data that is cached
                    self.config.read(self.FileName)
            return True
        except Exception as e1:
            self.LogErrorLine("Error in WriteSection: " + str(e1))
            return False

    #---------------------MyConfig::WriteValue----------------------------------
    def WriteValue(self, Entry, Value, remove = False, section = None):

        if self.Simulation:
            return

        if section != None:
            self.SetSection(section)

        SectionFound = False
        try:
            with self.CriticalLock:
                Found = False
                ConfigFile = open(self.FileName,'r')
                FileString = ConfigFile.read()
                ConfigFile.close()

                ConfigFile = open(self.FileName,'w')
                for line in FileString.splitlines():
                    if not line.isspace():                  # blank lines
                        newLine = line.strip()              # strip leading spaces
                        if len(newLine):
                            if not newLine[0] == "#":           # not a comment
                                if not SectionFound and not self.LineIsSection(newLine):
                                    ConfigFile.write(line+"\n")
                                    continue

                                if self.LineIsSection(newLine) and self.Section.lower() != self.GetSectionName(newLine).lower():
                                    if SectionFound and not Found and not remove:  # we reached the end of the section
                                        ConfigFile.write(Entry + " = " + Value + "\n")
                                        Found = True
                                    SectionFound = False
                                    ConfigFile.write(line+"\n")
                                    continue
                                if self.LineIsSection(newLine) and self.Section.lower() == self.GetSectionName(newLine).lower():
                                    SectionFound = True
                                    ConfigFile.write(line+"\n")
                                    continue

                                if not SectionFound:
                                    ConfigFile.write(line+"\n")
                                    continue
                                items = newLine.split('=')      # split items in line by spaces
                                if len(items) >= 2:
                                    items[0] = items[0].strip()
                                    if items[0] == Entry:
                                        if not remove:
                                            ConfigFile.write(Entry + " = " + Value + "\n")
                                        Found = True
                                        continue

                    ConfigFile.write(line+"\n")
                # if this is a new entry, then write it to the file, unless we are removing it
                # this check is if there is not section below the one we are working in,
                # it will be added to the end of the file
                if not Found and not remove:
                    ConfigFile.write(Entry + " = " + Value + "\n")
                ConfigFile.flush()
                ConfigFile.close()
                # update the read data that is cached
                self.config.read(self.FileName)
            return True

        except Exception as e1:
            self.LogError("Error in WriteValue: " + str(e1))
            return False

    #---------------------MyConfig::GetSectionName------------------------------
    def GetSectionName(self, Line):

        if self.Simulation:
            return ""
        Line = Line.strip()
        if Line.startswith("[") and Line.endswith("]") and len(Line) >=3 :
            Line = Line.replace("[", "")
            Line = Line.replace("]", "")
            return Line
        return ""
    #---------------------MyConfig::LineIsSection-------------------------------
    def LineIsSection(self, Line):

        if self.Simulation:
            return False
        Line = Line.strip()
        if Line.startswith("[") and Line.endswith("]") and len(Line) >=3 :
            return True
        return False
