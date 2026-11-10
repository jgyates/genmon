#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: myconfig.py
# PURPOSE: Configuration file Abstraction
#
#  AUTHOR: Jason G Yates
#    DATE: 22-May-2018
#
# MODIFICATIONS:
#
# -------------------------------------------------------------------------------

import threading

from configparser import ConfigParser

from genmonlib.mycommon import MyCommon
from genmonlib.myfileutil import AtomicWrite, FileLock

# Fix Python 2.x. unicode type
unicode = str


class MyConfig(MyCommon):
    # ---------------------MyConfig::__init__------------------------------------
    def __init__(self, filename=None, section=None, simulation=False, log=None):

        super(MyConfig, self).__init__()
        self.log = log
        self.FileName = filename
        self.Section = section
        self.Simulation = simulation
        self.CriticalLock = threading.Lock()  # Critical Lock (writing conf file)
        self.InitComplete = False
        try:
            self.config = ConfigParser(interpolation=None)
            self.config.read(self.FileName)

            if self.Section == None:
                SectionList = self.GetSections()
                if len(SectionList):
                    self.Section = SectionList[0]

        except Exception as e1:
            self.LogErrorLine("Error in MyConfig:init: " + str(e1))
            return
        self.InitComplete = True

    # ---------------------MyConfig::HasOption-----------------------------------
    def HasOption(self, Entry):

        return self.config.has_option(self.Section, Entry)

    # ---------------------MyConfig::GetList-------------------------------------
    def GetList(self):
        try:
            return self.config.items(self.Section)

        except Exception as e1:
            self.LogErrorLine(
                "Error in MyConfig:GetList: " + self.Section + ": " + str(e1)
            )
            return None

    # ---------------------MyConfig::GetSections---------------------------------
    def GetSections(self):

        return self.config.sections()

    # ---------------------MyConfig::SetSection----------------------------------
    def SetSection(self, section):

        if self.Simulation:
            return True
        if not (isinstance(section, str) or isinstance(section, unicode)) or not len(
            section
        ):
            self.LogError(
                "Error in MyConfig:ReadValue: invalid section: " + str(section)
            )
            return False
        self.Section = section
        return True

    # ---------------------MyConfig::ReadValue-----------------------------------
    def ReadValue(
        self, Entry, return_type=str, default=None, section=None, NoLog=False
    ):

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
                    self.LogErrorLine(
                        "Warning in MyConfig:ReadValue: invalid type or missing value, using default :"
                        + str(return_type)
                    )
                    return default
            else:
                return default
        except Exception as e1:
            if not NoLog:
                self.LogErrorLine(
                    "Error in MyConfig:ReadValue: "
                    + self.Section
                    + ": "
                    + Entry
                    + ": "
                    + str(e1)
                )
            return default

    # ---------------------MyConfig::WriteSection--------------------------------
    def WriteSection(self, SectionName):

        if self.Simulation:
            return True

        if not self.InitComplete:
            return False
        SectionList = self.GetSections()

        if SectionName in SectionList:
            self.LogError("Error in WriteSection: Section already exist.")
            return True
        if self.HasLineBreak(SectionName):
            self.LogError("Error in WriteSection: invalid section name: " + repr(SectionName))
            return False
        try:
            with self.CriticalLock, FileLock(self.FileName):
                with open(self.FileName, "r") as ConfigFile:
                    FileString = ConfigFile.read()
                if len(FileString) and not FileString.endswith("\n"):
                    FileString += "\n"
                FileString += "[" + SectionName + "]\n"
                AtomicWrite(self.FileName, FileString)
                # update the read data that is cached
                self.config.read(self.FileName)
            return True
        except Exception as e1:
            self.LogErrorLine("Error in WriteSection: " + str(e1))
            return False

    # ---------------------MyConfig::HasLineBreak--------------------------------
    def HasLineBreak(self, Value):
        # a line break in a key or value would inject extra lines into the file
        return "\n" in Value or "\r" in Value

    # ---------------------MyConfig::WriteValue----------------------------------
    def WriteValue(self, Entry, Value, remove=False, section=None):

        if self.Simulation:
            return

        if not self.InitComplete:
            return False

        if section != None:
            self.SetSection(section)

        try:
            if self.HasLineBreak(Entry) or (not remove and self.HasLineBreak(Value)):
                self.LogError(
                    "Error in WriteValue: line break not allowed in " + repr(Entry)
                )
                return False
        except TypeError:
            self.LogError("Error in WriteValue: non-string entry or value for " + repr(Entry))
            return False

        SectionFound = False
        try:
            with self.CriticalLock, FileLock(self.FileName):
                Found = False
                with open(self.FileName, "r") as ConfigFile:
                    FileString = ConfigFile.read()

                # build the new file in memory, then replace the old one in a
                # single step so a crash can never leave a partial config
                Output = []
                for line in FileString.splitlines():
                    if not line.isspace():  # blank lines
                        newLine = line.strip()  # strip leading spaces
                        if len(newLine):
                            if not newLine[0] == "#":  # not a comment
                                if not SectionFound and not self.LineIsSection(newLine):
                                    Output.append(line + "\n")
                                    continue

                                if (
                                    self.LineIsSection(newLine)
                                    and self.Section.lower()
                                    != self.GetSectionName(newLine).lower()
                                ):
                                    if (
                                        SectionFound and not Found and not remove
                                    ):  # we reached the end of the section
                                        Output.append(Entry + " = " + Value + "\n")
                                        Found = True
                                    SectionFound = False
                                    Output.append(line + "\n")
                                    continue
                                if (
                                    self.LineIsSection(newLine)
                                    and self.Section.lower()
                                    == self.GetSectionName(newLine).lower()
                                ):
                                    SectionFound = True
                                    Output.append(line + "\n")
                                    continue

                                if not SectionFound:
                                    Output.append(line + "\n")
                                    continue
                                items = newLine.split(
                                    "="
                                )  # split items in line by spaces
                                if len(items) >= 2:
                                    items[0] = items[0].strip()
                                    if items[0] == Entry:
                                        if not remove:
                                            Output.append(
                                                Entry + " = " + Value + "\n"
                                            )
                                        Found = True
                                        continue

                    Output.append(line + "\n")
                # if this is a new entry, then write it to the file, unless we are removing it
                # this check is if there is not section below the one we are working in,
                # it will be added to the end of the file
                if not Found and not remove:
                    Output.append(Entry + " = " + Value + "\n")
                AtomicWrite(self.FileName, "".join(Output))
                # update the read data that is cached
                self.config.read(self.FileName)
            return True

        except Exception as e1:
            self.LogErrorLine("Error in WriteValue: " + str(e1))
            return False

    # ---------------------MyConfig::GetSectionName------------------------------
    def GetSectionName(self, Line):

        if self.Simulation:
            return ""
        Line = Line.strip()
        if Line.startswith("[") and Line.endswith("]") and len(Line) >= 3:
            Line = Line.replace("[", "")
            Line = Line.replace("]", "")
            return Line
        return ""

    # ---------------------MyConfig::LineIsSection-------------------------------
    def LineIsSection(self, Line):

        if self.Simulation:
            return False
        Line = Line.strip()
        if Line.startswith("[") and Line.endswith("]") and len(Line) >= 3:
            return True
        return False
