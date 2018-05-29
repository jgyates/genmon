#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: mygauge.py
# PURPOSE: Gauage Abstraction
#
#  AUTHOR: Jason G Yates
#    DATE: 22-May-2018
#
# MODIFICATIONS:
#
# USAGE: This is the base class of generator controllers. LogError or FatalError
#   should be used to log errors or fatal errors.
#
#-------------------------------------------------------------------------------

import mycommon

# See http://bernii.github.io/gauge.js/ for gauage paraeters
class MyGauge (mycommon.MyCommon):
    #---------------------Gauge::__init__---------------------------------------
    def __init__(self, log, title = None, units = None, type = None, nominal = None,
        minimum = None, maximum = None, divisions = None, subdivisions = None,
        callback = None, callbackparameters = None, labels = None, colors = None):

        self.log = log
        self.Title = title
        self.Units = units
        self.Type = type
        self.Minimum = minimum
        self.Maximum = maximum
        self.Nominal = nominal
        self.Divisions = divisions
        self.SubDivisions = subdivisions
        self.Callback = callback
        self.CallbackParameters = callbackparameters
        self.Labels = labels
        self.ColorZones = colors
        self.TileType = "gauge"
        self.DefaultSize = 2
        '''
        1.) Text (eg "5 kW")
        2.) Value (eg 5)
        3.) gauge min Value (usually 0)
        4.) gauge maximum value (eg 260)
        5.) Divisions (the large line, (eg 50, 100, 150, 200, 250)
        6.) sub divisions (eg every 10, ie the samll lines)
        7.) labels... (eg put labels at 100 & 200)
        8.) color zones
        '''
        self.RED = "#F03E3E"
        self.YELLOW = "#FFDD00"
        self.GREEN = "#30B32D"

        if self.Title == None:
            self.LogError("Error in MyGauge:init: invalid title: " + str(self.Title))
            return
        if self.Type == None:
            self.LogError("Error in MyGauge:init: invalid type: " + str(self.Type))
            return

        if self.Type.lower() == "batteryvolts":
            self.Nominal = self.SetDefault(self.Nominal, 12)
            self.Minimum = self.SetDefault(self.Minimum, self.Nominal/12*10)
            self.Maximum = self.SetDefault(self.Maximum, self.Nominal/12*16)
            self.Divisions = self.SetDefault(self.Divisions, 6)
            self.SubDivisions = self.SetDefault(self.SubDivisions, 10)
            self.Labels = self.SetDefault( self.Labels, range(self.Minimum, self.Maximum + 1, 1))
            values = [self.Minimum, self.Nominal/12*11.5, self.Nominal/12*12.5, self.Nominal/12*15, self.Nominal/12*15.5, self.Maximum]
            colors = [self.RED, self.YELLOW, self.GREEN, self.YELLOW, self.RED]
            self.ColorZones = self.SetDefault(self.ColorZones, self.CreateColorZoneList(values, colors))

        elif self.Type.lower() == "linevolts":
            self.Nominal = self.SetDefault(self.Nominal, 240)
            self.Minimum = self.SetDefault(self.Minimum, 0)
            self.Maximum = self.SetDefault(self.Maximum, self.Nominal + 20)
            self.Divisions = self.SetDefault(self.Divisions, int(self.Maximum / 10))
            self.SubDivisions = self.SetDefault(self.SubDivisions, 0)
            # This does not scale
            self.Labels = self.SetDefault( self.Labels, [self.Minimum, 100, 156, 220, self.Nominal, self.Maximum])
            # This may not scale
            values = [self.Minimum, self.Nominal - 10, self.Nominal - 5, self.Nominal + 5, self.Nominal + 15, self.Maximum]
            colors = [self.RED, self.YELLOW, self.GREEN, self.YELLOW, self.RED]
            self.ColorZones = self.SetDefault(self.ColorZones, self.CreateColorZoneList(values, colors))

        elif self.Type.lower() == "current":
            self.Nominal = self.SetDefault(self.Nominal, 100)
            self.Minimum = self.SetDefault(self.Minimum, 0)
            self.Maximum = self.SetDefault(self.Maximum, int(self.Nominal * 1.2))
            self.Divisions = self.SetDefault(self.Divisions, 12)
            self.SubDivisions = self.SetDefault(self.SubDivisions, 5)
            self.Labels = self.SetDefault( self.Labels, range(self.Minimum, self.Maximum, int(self.Nominal / 10)))
            values = [self.Minimum, int(self.Nominal * 0.8), int(self.Nominal * 0.95), int(self.Nominal * 1.2)]
            colors = [self.GREEN, self.YELLOW, self.RED]
            self.ColorZones = self.SetDefault(self.ColorZones, self.CreateColorZoneList(values, colors))
        elif self.Type.lower() == "power":
            self.Nominal = self.SetDefault(self.Nominal, 60)
            self.Minimum = self.SetDefault(self.Minimum, 0)
            self.Maximum = self.SetDefault(self.Maximum, int(self.Nominal * 1.2))
            self.Divisions = self.SetDefault(self.Divisions, 12)
            self.SubDivisions = self.SetDefault(self.SubDivisions, 5)
            self.Labels = self.SetDefault( self.Labels, self.CreatePowerLabels(self.Minimum, self.Nominal , self.Maximum))
            values = [self.Minimum, int(self.Nominal * 0.8), int(self.Nominal * 0.95), int(self.Nominal * 1.2)]
            colors = [self.GREEN, self.YELLOW, self.RED]
            self.ColorZones = self.SetDefault(self.ColorZones, self.CreateColorZoneList(values, colors))

        elif self.Type.lower() == "frequency":
            self.Nominal = self.SetDefault(self.Nominal, 60)
            self.Minimum = self.SetDefault(self.Minimum, 0)
            self.Maximum = self.SetDefault(self.Maximum, self.Nominal + 10)
            self.Divisions = self.SetDefault(self.Divisions, int(self.Maximum / 10))
            self.SubDivisions = self.SetDefault(self.SubDivisions, 10)
            self.Labels = self.SetDefault( self.Labels, range(self.Minimum + 10, self.Maximum + 10, 10))
            values = [self.Minimum, self.Nominal - 6, self.Nominal - 3, self.Nominal + 3, self.Nominal + 6, self.Maximum]
            colors = [self.RED, self.YELLOW, self.GREEN, self.YELLOW, self.RED]
            self.ColorZones = self.SetDefault(self.ColorZones, self.CreateColorZoneList(values, colors))
        elif self.Type.lower() == "rpm":
            self.Nominal = self.SetDefault(self.Nominal, 3600)
            self.Minimum = self.SetDefault(self.Minimum, 0)
            self.Maximum = self.SetDefault(self.Maximum, self.Nominal + 100)
            self.Divisions = self.SetDefault(self.Divisions, 4)
            self.SubDivisions = self.SetDefault(self.SubDivisions, 10)
            self.Labels = self.SetDefault( self.Labels, range(self.Minimum, self.Maximum, self.Nominal / 4))
            values = [self.Minimum, self.Nominal - 75, self.Nominal - 50, self.Nominal + 50, self.Nominal + 75, self.Maximum]
            colors = [self.RED, self.YELLOW, self.GREEN, self.YELLOW, self.RED]
            self.ColorZones = self.SetDefault(self.ColorZones, self.CreateColorZoneList(values, colors))

        elif self.Type.lower() == "fuel" or self.Type.lower() == "level" or self.Type.lower() == "position":
            self.Nominal = self.SetDefault(self.Nominal, 100)
            self.Minimum = self.SetDefault(self.Minimum, 0)
            self.Maximum = self.SetDefault(self.Maximum, self.Nominal)
            self.Divisions = self.SetDefault(self.Divisions, int(self.Maximum / 10))
            self.SubDivisions = self.SetDefault(self.SubDivisions, 10)
            self.Labels = self.SetDefault( self.Labels, range(self.Minimum, self.Maximum, self.Divisions))
            values = [self.Minimum, int(self.Nominal * 0.10), int(self.Nominal * 0.25), int(self.Nominal)]
            colors = [self.RED, self.YELLOW, self.GREEN]
            self.ColorZones = self.SetDefault(self.ColorZones, self.CreateColorZoneList(values, colors))

        elif self.Type.lower() == "temperature":
            self.Nominal = self.SetDefault(self.Nominal, 100)
            self.Minimum = self.SetDefault(self.Minimum, 0)
            self.Maximum = self.SetDefault(self.Maximum, self.Nominal)
            self.Divisions = self.SetDefault(self.Divisions, int(self.Maximum / 10))
            self.SubDivisions = self.SetDefault(self.SubDivisions, 10)
            self.Labels = self.SetDefault( self.Labels, range(self.Minimum, self.Maximum, self.Divisions))
            values = [self.Minimum, self.Nominal, self.Nominal + int((self.Maximum - self.Nominal) / 2), self.Maximum]
            colors = [self.GREEN, self.YELLOW, self.RED]
            self.ColorZones = self.SetDefault(self.ColorZones, self.CreateColorZoneList(values, colors))

        elif self.Type.lower() == "pressure":
            self.Nominal = self.SetDefault(self.Nominal, 100)
            self.Minimum = self.SetDefault(self.Minimum, 0)
            self.Maximum = self.SetDefault(self.Maximum, self.Nominal + 10)
            self.Divisions = self.SetDefault(self.Divisions, int(self.Maximum / 10))
            self.SubDivisions = self.SetDefault(self.SubDivisions, 10)
            self.Labels = self.SetDefault( self.Labels, range(self.Minimum, self.Maximum, self.Divisions))
            # TODO
            values = [self.Minimum, self.Nominal - 15, self.Nominal - 5, self.Nominal + 5, self.Nominal + 15, self.Maximum]
            colors = [self.RED, self.YELLOW, self.GREEN, self.YELLOW, self.RED]
            self.ColorZones = self.SetDefault(self.ColorZones, self.CreateColorZoneList(values, colors))

        else:
            self.LogError("Error in MyGauge:init: invalid type: " + str(type))
            return

        if self.Minimum >= self.Maximum:
            self.LogError("Error in MyGauge:init: invalid value, min: %d max:%d" % (self.Minimum,str.Maximum))
            return
    #-------------Gauge:CreatePowerLabels-------------------------------------
    def CreatePowerLabels(self, Minimum, Nominal, Maximum):

        ReturnList = []
        Range = Nominal
        ReturnList.append(Minimum)
        ReturnList.append(Minimum + int(round(Range * .2)))
        ReturnList.append(Minimum + int(round(Range * .4)))
        ReturnList.append(Minimum + int(round(Range * .6)))
        ReturnList.append(Minimum + int(round(Range * .8)))
        ReturnList.append(Nominal)
        ReturnList.append(Maximum)

        return ReturnList

    #-------------Gauge:CreateColorZoneList-------------------------------------
    def CreateColorZoneList(self, ZoneValueList, ZoneColorList):

        if not len(ZoneValueList) == len(ZoneColorList) + 1:
            self.LogError("Error in CreateColorZoneList, invalid length: " + str(len(ZoneValueList)) + ":" + str(len(ZoneColorList)))
            return
        ReturnList = []
        for x in range(0, len(ZoneColorList)):
            ReturnList.append(self.CreateColorZone(ZoneColorList[x], ZoneValueList[x], ZoneValueList[x+1]))

        return ReturnList
    #-------------Gauge:CreateColorZone-----------------------------------------
    def CreateColorZone(self, color, min, max):

        ColorZone = {"strokeStyle": color, "min": min, "max": max}

        return ColorZone

    #-------------Gauge:SetDefault----------------------------------------------
    def SetDefault(sefl, Value, Default):

        if Value == None:
            return Default
        else:
            return Value

    #-------------Gauge:GetGUIInfo----------------------------------------------
    def GetGUIInfo(self):

        GUIInfo = {}
        try:
            if not self.Callback == None:
                Value = self.Callback( *self.CallbackParameters)
            else:
                Value = self.Minimum

            if isinstance(Value, float):
                ValueStr = "%.2f" % Value
            else:
                ValueStr = str(Value)

            if self.Units == None:
                GUIInfo["text"] = "%s" % str(ValueStr)
            else:
                GUIInfo["text"] = "%s %s" % (str(ValueStr), self.Units)

            if Value < self.Minimum:
                Value = self.Minimum
            elif Value > self.Maximum:
                Value = self.Maximum

            GUIInfo["value"] = ValueStr
            GUIInfo["title"] = self.Title
        except Exception as e1:
            self.LogErrorLine("Error in GetGUIInfo: " + str(e1))
        return GUIInfo
    #-------------Gauge:GetStartInfo--------------------------------------------
    def GetStartInfo(self):

        StartInfo = {}

        StartInfo["title"] = self.Title
        StartInfo["minimum"] = self.Minimum
        StartInfo["maximum"] = self.Maximum
        StartInfo["divisions"] = self.Divisions
        StartInfo["subdivisions"] = self.SubDivisions
        StartInfo["labels"] = self.Labels
        StartInfo["colorzones"] = self.ColorZones
        StartInfo["type"] = self.TileType
        StartInfo["default-size"] = self.DefaultSize
        return StartInfo
