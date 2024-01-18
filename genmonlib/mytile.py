#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: mytile.py
# PURPOSE: Tile Abstraction
#
#  AUTHOR: Jason G Yates
#    DATE: 22-May-2018
#
# MODIFICATIONS:
#
# USAGE: This is the base class of used to abstract gauges and graphs, etc
# LogError or FatalError should be used to log errors or fatal errors.
#
# -------------------------------------------------------------------------------

from genmonlib.mycommon import MyCommon


# See http://bernii.github.io/gauge.js/ for gauage paraeters
class MyTile(MyCommon):
    # ---------------------MyTile::__init__--------------------------------------
    def __init__(
        self,
        log,
        title=None,
        units=None,
        type=None,
        subtype=None,
        nominal=None,
        minimum=None,
        maximum=None,
        divisions=None,
        subdivisions=None,
        callback=None,
        callbackparameters=None,
        labels=None,
        colors=None,
        defaultsize=None,
        values=None,
    ):

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
        self.SubType = subtype
        self.DefaultSize = defaultsize
        """
        1.) Text (eg "5 kW")
        2.) Value (eg 5)
        3.) gauge min Value (usually 0)
        4.) gauge maximum value (eg 260)
        5.) Divisions (the large line, (eg 50, 100, 150, 200, 250)
        6.) sub divisions (eg every 10, ie the samll lines)
        7.) labels... (eg put labels at 100 & 200)
        8.) color zones
        """
        self.RED = "#F03E3E"
        self.YELLOW = "#FFDD00"
        self.GREEN = "#30B32D"

        if self.Title == None:
            self.LogError("Error in MyGauge:init: invalid title: " + str(self.Title))
            return
        if self.Type == None:
            self.LogError("Error in MyGauge:init: invalid type: " + str(self.Type))
            return

        try:
            if self.Type.lower() == "batteryvolts":
                self.Nominal = self.SetDefault(self.Nominal, 12)
                self.Minimum = self.SetDefault(
                    self.Minimum,
                    0,
                )  # self.Nominal/12*10)
                self.Maximum = self.SetDefault(self.Maximum, self.Nominal / 12 * 16)
                self.Divisions = self.SetDefault(self.Divisions, 6)
                self.SubDivisions = self.SetDefault(self.SubDivisions, 10)
                self.Labels = self.SetDefault(
                    self.Labels,
                    list(
                        range(
                            int(self.Minimum),
                            int(self.Maximum + 1),
                            int(self.Maximum / 4),
                        )
                    ),
                )
                if values == None:
                    values = [
                        self.Minimum,
                        self.Nominal / 12 * 11.5,
                        self.Nominal / 12 * 12.5,
                        self.Nominal / 12 * 15,
                        self.Nominal / 12 * 15.5,
                        self.Maximum,
                    ]
                colors = [self.RED, self.YELLOW, self.GREEN, self.YELLOW, self.RED]
                self.ColorZones = self.SetDefault(
                    self.ColorZones, self.CreateColorZoneList(values, colors)
                )
                self.DefaultSize = self.SetDefault(self.DefaultSize, 2)
                self.TileType = "gauge"

            elif self.Type.lower() == "linevolts":
                ToleranceTen = round(self.Nominal * 0.1)
                ToleranceFive = round(self.Nominal * 0.05)
                self.Nominal = self.SetDefault(self.Nominal, 240)
                self.Minimum = self.SetDefault(self.Minimum, 0)
                # self.Maximum = self.SetDefault(self.Maximum, self.Nominal + 20)
                self.Maximum = self.SetDefault(
                    self.Maximum, self.Nominal + self.myround(self.Nominal * 0.15, 10)
                )
                self.Divisions = self.SetDefault(
                    self.Divisions, 10
                )  # int(self.Maximum / 10))
                self.SubDivisions = self.SetDefault(self.SubDivisions, 0)
                self.Labels = self.SetDefault(
                    self.Labels,
                    self.CreateLabels(self.Minimum, self.Nominal, self.Maximum),
                )
                values = [
                    self.Minimum,
                    self.Nominal - ToleranceTen,
                    self.Nominal - ToleranceFive,
                    self.Nominal + ToleranceFive,
                    self.Nominal + ToleranceTen,
                    self.Maximum,
                ]
                colors = [self.RED, self.YELLOW, self.GREEN, self.YELLOW, self.RED]
                self.ColorZones = self.SetDefault(
                    self.ColorZones, self.CreateColorZoneList(values, colors)
                )
                self.DefaultSize = self.SetDefault(self.DefaultSize, 2)
                self.TileType = "gauge"

            elif self.Type.lower() == "current":
                self.Nominal = self.SetDefault(self.Nominal, 100)
                self.Minimum = self.SetDefault(self.Minimum, 0)
                self.Maximum = self.SetDefault(self.Maximum, int(self.Nominal * 1.2))

                self.Divisions = self.SetDefault(self.Divisions, 12)
                self.SubDivisions = self.SetDefault(self.SubDivisions, 5)
                self.Labels = self.SetDefault(
                    self.Labels,
                    self.CreateLabels(self.Minimum, self.Nominal, self.Maximum),
                )

                values = [
                    self.Minimum,
                    int(self.Nominal * 0.8),
                    int(self.Nominal * 0.95),
                    int(self.Nominal * 1.2),
                ]
                colors = [self.GREEN, self.YELLOW, self.RED]
                self.ColorZones = self.SetDefault(
                    self.ColorZones, self.CreateColorZoneList(values, colors)
                )
                self.TileType = "gauge"

            elif self.Type.lower() == "power":
                self.Nominal = self.SetDefault(self.Nominal, 60)
                self.Minimum = self.SetDefault(self.Minimum, 0)
                self.Maximum = self.SetDefault(self.Maximum, int(self.Nominal * 1.2))
                self.Divisions = self.SetDefault(self.Divisions, 12)
                self.SubDivisions = self.SetDefault(self.SubDivisions, 5)
                self.Labels = self.SetDefault(
                    self.Labels,
                    self.CreateLabels(self.Minimum, self.Nominal, self.Maximum),
                )
                values = [
                    self.Minimum,
                    int(self.Nominal * 0.8),
                    int(self.Nominal * 0.95),
                    int(self.Nominal * 1.2),
                ]
                colors = [self.GREEN, self.YELLOW, self.RED]
                self.ColorZones = self.SetDefault(
                    self.ColorZones, self.CreateColorZoneList(values, colors)
                )
                self.DefaultSize = self.SetDefault(self.DefaultSize, 2)
                self.TileType = "gauge"

            elif self.Type.lower() == "frequency":
                self.Nominal = self.SetDefault(self.Nominal, 60)
                self.Minimum = self.SetDefault(self.Minimum, 0)
                self.Maximum = self.SetDefault(self.Maximum, self.Nominal + 10)
                self.Divisions = self.SetDefault(self.Divisions, int(self.Maximum / 10))
                self.SubDivisions = self.SetDefault(self.SubDivisions, 10)
                self.Labels = self.SetDefault(
                    self.Labels,
                    list(
                        range(int(self.Minimum + 10), int(self.Maximum + 10), int(10))
                    ),
                )
                values = [
                    self.Minimum,
                    self.Nominal - 6,
                    self.Nominal - 3,
                    self.Nominal + 3,
                    self.Nominal + 6,
                    self.Maximum,
                ]
                colors = [self.RED, self.YELLOW, self.GREEN, self.YELLOW, self.RED]
                self.ColorZones = self.SetDefault(
                    self.ColorZones, self.CreateColorZoneList(values, colors)
                )
                self.DefaultSize = self.SetDefault(self.DefaultSize, 2)
                self.TileType = "gauge"

            elif self.Type.lower() == "rpm":
                self.Nominal = self.SetDefault(self.Nominal, 3600)
                self.Minimum = self.SetDefault(self.Minimum, 0)
                # self.Maximum = self.SetDefault(self.Maximum, self.Nominal + 100)
                self.Maximum = self.SetDefault(
                    self.Maximum, self.Nominal + self.myround(self.Nominal * 0.05, 10)
                )
                self.Divisions = self.SetDefault(self.Divisions, 4)
                self.SubDivisions = self.SetDefault(self.SubDivisions, 10)
                self.Labels = self.SetDefault(
                    self.Labels,
                    list(
                        range(
                            int(self.Minimum), int(self.Maximum), int(self.Nominal / 4)
                        )
                    ),
                )
                values = [
                    self.Minimum,
                    self.Nominal - 75,
                    self.Nominal - 50,
                    self.Nominal + 50,
                    self.Nominal + 75,
                    self.Maximum,
                ]
                colors = [self.RED, self.YELLOW, self.GREEN, self.YELLOW, self.RED]
                self.ColorZones = self.SetDefault(
                    self.ColorZones, self.CreateColorZoneList(values, colors)
                )
                self.DefaultSize = self.SetDefault(self.DefaultSize, 2)
                self.TileType = "gauge"

            elif (
                self.Type.lower() == "fuel"
                or self.Type.lower() == "level"
                or self.Type.lower() == "position"
            ):
                self.Nominal = self.SetDefault(self.Nominal, 100)
                self.Minimum = self.SetDefault(self.Minimum, 0)
                self.Maximum = self.SetDefault(self.Maximum, self.Nominal)
                self.Divisions = self.SetDefault(self.Divisions, int(self.Maximum / 10))
                self.SubDivisions = self.SetDefault(self.SubDivisions, 10)
                self.Labels = self.SetDefault(
                    self.Labels,
                    list(
                        range(int(self.Minimum), int(self.Maximum), int(self.Divisions))
                    ),
                )
                values = [
                    self.Minimum,
                    int(self.Nominal * 0.10),
                    int(self.Nominal * 0.25),
                    int(self.Nominal),
                ]
                colors = [self.RED, self.YELLOW, self.GREEN]
                self.ColorZones = self.SetDefault(
                    self.ColorZones, self.CreateColorZoneList(values, colors)
                )
                self.DefaultSize = self.SetDefault(self.DefaultSize, 2)
                self.TileType = "gauge"

            elif self.Type.lower() == "temperature":
                self.Nominal = self.SetDefault(self.Nominal, 100)
                self.Minimum = self.SetDefault(self.Minimum, 0)
                self.Maximum = self.SetDefault(self.Maximum, self.Nominal)
                self.Divisions = self.SetDefault(self.Divisions, int(self.Maximum / 10))
                self.SubDivisions = self.SetDefault(self.SubDivisions, 10)
                if self.SubType != None and (self.SubType.lower() == "coolant" or self.SubType.lower() == "external"):
                    self.Labels = self.SetDefault(
                        self.Labels,
                        list(
                            range(
                                int(self.Minimum),
                                int(self.Maximum),
                                int(self.Divisions),
                            )
                        ),
                    )
                    values = [
                        self.Minimum,
                        self.Nominal + 20,
                        self.Nominal + 40,
                        self.Maximum,
                    ]
                else:
                    self.Labels = self.SetDefault(
                        self.Labels,
                        list(
                            range(
                                int(self.Minimum),
                                int(self.Maximum),
                                int(self.Divisions),
                            )
                        ),
                    )
                    values = [
                        self.Minimum,
                        self.Nominal,
                        self.Nominal + int((self.Maximum - self.Nominal) / 2),
                        self.Maximum,
                    ]
                colors = [self.GREEN, self.YELLOW, self.RED]
                self.ColorZones = self.SetDefault(
                    self.ColorZones, self.CreateColorZoneList(values, colors)
                )
                self.TileType = "gauge"

            elif self.Type.lower() == "pressure":
                self.Nominal = self.SetDefault(self.Nominal, 100)
                self.Minimum = self.SetDefault(self.Minimum, 0)
                self.Maximum = self.SetDefault(self.Maximum, self.Nominal + 10)
                self.Divisions = self.SetDefault(self.Divisions, int(self.Maximum / 10))
                self.SubDivisions = self.SetDefault(self.SubDivisions, 10)
                self.Labels = self.SetDefault(
                    self.Labels,
                    list(
                        range(int(self.Minimum), int(self.Maximum), int(self.Divisions))
                    ),
                )
                # TODO
                values = [
                    self.Minimum,
                    self.Nominal - 15,
                    self.Nominal - 5,
                    self.Nominal + 5,
                    self.Nominal + 15,
                    self.Maximum,
                ]
                colors = [self.RED, self.YELLOW, self.GREEN, self.YELLOW, self.RED]
                self.ColorZones = self.SetDefault(
                    self.ColorZones, self.CreateColorZoneList(values, colors)
                )
                self.DefaultSize = self.SetDefault(self.DefaultSize, 2)
                self.TileType = "gauge"

            elif self.Type.lower() == "powergraph":
                self.Nominal = self.SetDefault(self.Nominal, 100)
                self.Minimum = self.SetDefault(self.Minimum, 0)
                self.Maximum = self.SetDefault(
                    self.Maximum, self.Nominal + int(self.Nominal * 0.20)
                )
                self.DefaultSize = self.SetDefault(self.DefaultSize, 2)
                self.TileType = "graph"

            elif self.Type.lower() == "wifi":
                # https://www.screenbeam.com/wifihelp/wifibooster/wi-fi-signal-strength-what-is-a-good-signal/
                # -30 dBm: This is the maximum signal strength. If you have this measurement, you are likely standing right next to the access point.
                # -50 dBm: This is considered an excellent signal strength.
                # -60 dBm: This is a good signal strength.
                # -67 dBm: This is a reliable signal strength. This is the minimum for any online services that require a reliable connection and Wi-Fi signal strength.
                # -70 dBm: This is not a strong signal strength. You may be able to check your email.
                # -80 dBm: This is an unreliable signal strength. You may be able to connect to your network, but you will not support most online activity.
                # -90 dBm: This is a bad signal strength. You are not likely to connect to internet at this level.
                self.Nominal = self.SetDefault(self.Nominal, -60)
                self.Minimum = self.SetDefault(self.Minimum, -100)
                self.Maximum = self.SetDefault(self.Maximum, -30)
                self.Divisions = self.SetDefault(self.Divisions, 10)
                self.SubDivisions = self.SetDefault(self.SubDivisions, 10)
                self.Labels = self.SetDefault(
                    self.Labels,
                    list(
                        range(int(self.Minimum), int(self.Maximum), int(self.Divisions))
                    ),
                )
                values = [
                    self.Minimum,
                    int(self.Nominal - 10),
                    self.Nominal - 5,
                    self.Maximum,
                ]
                colors = [self.RED, self.YELLOW, self.GREEN]
                self.ColorZones = self.SetDefault(
                    self.ColorZones, self.CreateColorZoneList(values, colors)
                )
                self.DefaultSize = self.SetDefault(self.DefaultSize, 2)
                self.TileType = "gauge"
            else:
                self.LogError("Error in MyGauge:init: invalid type: " + str(type))
                return

            if self.Minimum >= self.Maximum:
                self.LogError(
                    "Error in MyGauge:init: invalid value, %s: min: %d max:%d"
                    % (self.Title, int(self.Minimum), int(self.Maximum))
                )
                self.Maximum = self.Minimum
                return
        except Exception as e1:
            self.LogErrorLine("Error in MyTile init: " + str(e1) + " :" + str(title))

    # -------------MyTile:myround--------------------------------------
    def myround(self, x, base=5):
        return int(base * round(float(x) / base))

    # -------------MyTile:CreateLabels--------------------------------------
    def CreateLabels(self, Minimum, Nominal, Maximum):

        if Maximum - Minimum < 15:
            return list(range(int(self.Minimum), int(self.Maximum), 2))
        elif Maximum - Minimum < 30:
            return list(range(int(self.Minimum), int(self.Maximum), 5))
        elif Maximum - Minimum < 45:
            return list(range(int(self.Minimum), int(self.Maximum), 10))
        else:
            RoundTo = 5
        ReturnList = []
        Range = Nominal
        ReturnList.append(int(round(Minimum, 1)))
        ReturnList.append(Minimum + int(self.myround(Range * 0.2, RoundTo)))
        ReturnList.append(Minimum + int(self.myround(Range * 0.4, RoundTo)))
        ReturnList.append(Minimum + int(self.myround(Range * 0.6, RoundTo)))
        ReturnList.append(Minimum + int(self.myround(Range * 0.8, RoundTo)))
        ReturnList.append(int(self.myround(Nominal, RoundTo)))
        ReturnList.append(int(Maximum))

        return ReturnList

    # -------------MyTile:CreateColorZoneList------------------------------------
    def CreateColorZoneList(self, ZoneValueList, ZoneColorList):

        if not len(ZoneValueList) == len(ZoneColorList) + 1:
            self.LogError(
                "Error in CreateColorZoneList, invalid length: "
                + str(len(ZoneValueList))
                + ":"
                + str(len(ZoneColorList))
            )
            return
        ReturnList = []
        for x in range(0, len(ZoneColorList)):
            ReturnList.append(
                self.CreateColorZone(
                    ZoneColorList[x], ZoneValueList[x], ZoneValueList[x + 1]
                )
            )

        return ReturnList

    # -------------MyTile:CreateColorZone----------------------------------------
    def CreateColorZone(self, color, min, max):

        ColorZone = {"strokeStyle": color, "min": min, "max": max}

        return ColorZone

    # -------------MyTile:SetDefault---------------------------------------------
    def SetDefault(sefl, Value, Default):

        if Value == None:
            return Default
        else:
            return Value

    # -------------MyTile:GetGUIInfo---------------------------------------------
    def GetGUIInfo(self):

        GUIInfo = {}
        try:
            if not self.Callback == None:
                Value = self.Callback(*self.CallbackParameters)
                if Value == None:
                    Value = self.Minimum
            else:
                Value = self.Minimum

            # integer or float value converted to string
            if isinstance(Value, float):
                ValueStr = "%g" % Value
            else:
                ValueStr = str(Value)

            # Displayed value in text
            if self.Units == None:
                GUIInfo["text"] = "%s" % str(ValueStr)
            else:
                GUIInfo["text"] = "%s %s" % (str(ValueStr), self.Units)

            # this check makes the gauge not display distored if the value is out of range,
            # but the above "text" will show the value that is out of range as text
            if Value < self.Minimum or  Value > self.Maximum:
                if Value < self.Minimum:
                    Value = self.Minimum
                elif Value > self.Maximum:
                    Value = self.Maximum
                # integer or float value converted to string
                if isinstance(Value, float):
                    ValueStr = "%g" % Value
                else:
                    ValueStr = str(Value)

            GUIInfo["value"] = ValueStr
            GUIInfo["title"] = self.Title
            GUIInfo["type"] = self.TileType
            GUIInfo["subtype"] = self.Type
        except Exception as e1:
            self.LogErrorLine("Error in GetGUIInfo: (" + self.Title + ") : " + str(e1))
        return GUIInfo

    # -------------MyTile:GetStartInfo-------------------------------------------
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
        StartInfo["subtype"] = self.Type
        StartInfo["default-size"] = self.DefaultSize
        if self.Units == None:
            StartInfo["units"] = ""
        else:
            StartInfo["units"] = self.Units
        return StartInfo
