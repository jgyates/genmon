#-------------------------------------------------------------------------------
#    FILE: myweather.py
# PURPOSE: app to interface to open weather map api
#
#  AUTHOR: Jason G Yates
#    DATE: 26-May-2018
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import datetime, time, threading, collections

from genmonlib.mysupport import MySupport
from genmonlib.mythread import MyThread

try:
    import pyowm
    pyowm_installed = True
except:
    pyowm_installed = False

class MyWeather(MySupport):
    #---------------------__init__----------------------------------------------
    def __init__(self, apikey, location, log = None, unit = 'imperial'):
        super(MyWeather, self).__init__()
        self.APIKey = apikey
        self.log = log
        self.Location = location
        self.OWM = None
        self.Observation = None
        self.WeatherUnit = unit
        self.WeatherData = None
        self.ObservationLocation = None
        self.DataAccessLock = threading.Lock()     # lock to synchronize access to WeatherData

        if not pyowm_installed:
            self.LogError("Library pyowm not installed, disabling weather support." )
            return
        try:
            if self.APIKey != None:
                self.APIKey = self.APIKey.strip()
            if self.Location != None:
                self.Location = self.Location.strip()

            if self.APIKey == None or not len(self.APIKey) or self.Location == None or not len(self.Location):
                self.LogError("Weather API key invalid or Weather Location invalid")
                return

            self.InitOWM()
            self.Threads["WeatherThread"] = MyThread(self.WeatherThread, Name = "WeatherThread")
        except Exception as e1:
            self.LogErrorLine("Error on MyWeather:init: " + str(e1))


    #---------------------GetUnits----------------------------------------------
    def GetUnits(self, measured, Label = False):

        try:
            LookUp = {
                    "temp" : [["fahrenheit","F"],["celsius", "C"]],
                    "speed": [["miles_hour", "mph"], ["meters_sec", "m/s"]]
            }

            ReturnList = LookUp.get(measured, None)

            if ReturnList == None:
                self.LogError("Error in GetUnits: Unknown measured value: " + str(measured))
                return ""

            if self.WeatherUnit.lower() == 'metric':
                Index = 1
            else:
                Index = 0

            if Label:
                return ReturnList[Index][1]
            else:
                return ReturnList[Index][0]
        except Exception as e1:
            self.LogErrorLine("Error in GetUnits: " + str(e1))

    #---------------------InitOWM-----------------------------------------------
    def InitOWM(self):
        try:
            self.OWM = pyowm.OWM(self.APIKey) # You MUST provide a valid API key
            return True
        except Exception as e1:
            self.OWM = None
            self.LogErrorLine("Error in InitOWM: " + str(e1))
            return False


    #---------------------WeatherThread-----------------------------------------
    def GetObservation(self):

        if self.OWM == None:
            self.Observation = None
            self.ObservationLocation = None
            return
        try:
            if self.Location.isdigit():
                self.Observation = self.OWM.weather_at_id(int(self.Location))
            else:
                self.Observation = self.OWM.weather_at_place(self.Location)
            self.ObservationLocation = self.Observation.get_location()
        except Exception as e1:
            self.Observation = None
            self.ObservationLocation = None
            self.LogErrorLine("Error in GetObservation: " + str(e1))

    #---------------------WeatherThread-----------------------------------------
    def WeatherThread(self):

        time.sleep(1)
        while True:
            if self.OWM == None:
                if not self.InitOWM():
                    if self.WaitForExit("WeatherThread", 60 ):  # 60 sec
                        return
                    continue
            try:
                self.GetObservation()
                if self.Observation == None:
                    self.OWM = None
                    if self.WaitForExit("WeatherThread", 60 ):  # 60 sec
                        return
                    continue
                weatherdata = self.Observation.get_weather()
                with self.DataAccessLock:
                    self.WeatherData = weatherdata
            except Exception as e1:
                self.LogErrorLine("Error calling Observation.get_weather: " + str(e1))
                self.WeatherData = None
                if self.WaitForExit("WeatherThread", 60 ):  # 60 sec
                    return
                continue

            if self.WaitForExit("WeatherThread", 60 * 10):  # ten min
                return

    #---------------------GetLocation-------------------------------------------
    def GetLocation(self):

        Data = []
        try:
            if self.ObservationLocation == None:
                return None

            Data.append({"City Name" : self.ObservationLocation.get_name()})
            Data.append({"Latitude" : self.ObservationLocation.get_lat()})
            Data.append({"Longitude" : self.ObservationLocation.get_lon()})
            Data.append({"City ID" : self.ObservationLocation.get_ID()})
        except Exception as e1:
            self.LogErrorLine("Error in GetLocation: " + str(e1))

        return Data
    #---------------------GetWeather--------------------------------------------
    def GetWeather(self, minimum = True, ForUI = False):

        Data = []

        try:
            # Search for current weather in location
            if self.OWM == None or self.Observation == None:
                return Data

            if self.WeatherData == None:
                return Data

            with self.DataAccessLock:
                TempDict = self.WeatherData.get_temperature(unit = self.GetUnits("temp"))
                Data.append({"Current Temperature" : str(TempDict.get('temp', 0)) + " " + self.GetUnits("temp", Label = True)})
                Data.append({"Conditions" : self.WeatherData.get_detailed_status().title()})

                if not minimum:
                    Data.append({"Maximum Current Temperature" : str(TempDict.get('temp_max', 0)) + " " + self.GetUnits("temp", Label = True)})
                    Data.append({"Minimum Current Temperature" : str(TempDict.get('temp_min', 0)) + " " + self.GetUnits("temp", Label = True)})
                    Data.append({"Humidity" : str(self.WeatherData.get_humidity() ) + " %"})
                    Data.append({"Cloud Coverage" : str(self.WeatherData.get_clouds()) + " %"})
                    TempDict = self.WeatherData.get_wind(unit = self.GetUnits("speed")) # unit is meters_sec or miles_hour
                    Degrees = round(TempDict.get("deg", 0), 2)
                    Cardinal = self.DegreesToCardinal(Degrees)
                    if len(Cardinal):
                        WindString = Cardinal + " (" + str(Degrees) + " Degrees), "
                    else:
                        WindString = str(Degrees) + " Degrees, "
                    Data.append({"Wind" : WindString + str(round(TempDict.get("speed", 0),2)) + " " +self.GetUnits("speed", Label = True)})
                    TempDict = self.WeatherData.get_rain()
                    if len(TempDict):
                        Data.append({"Rain in last 3 hours" : str(TempDict.get("3h", 0))})
                    TempDict = self.WeatherData.get_snow()
                    if len(TempDict):
                        Data.append({"Snow in last 3 hours" : str(TempDict.get("3h", 0))})

                    TempDict = self.WeatherData.get_pressure()
                    if len(TempDict):
                        Data.append({"Pressure" : str(TempDict.get("press", 0)) + " " + "hpa"})

                    Data.append({"Sunrise Time" : datetime.datetime.fromtimestamp(int(self.WeatherData.get_sunrise_time())).strftime("%A %B %-d, %Y %H:%M:%S")})
                    Data.append({"Sunset Time" : datetime.datetime.fromtimestamp(int(self.WeatherData.get_sunset_time())).strftime("%A %B %-d, %Y %H:%M:%S")})

                    ReferenceTime = datetime.datetime.fromtimestamp(int(self.WeatherData.get_reference_time()))
                    Data.append({"Reference Time" : ReferenceTime.strftime("%A %B %-d, %Y %H:%M:%S")})
                    LocationData = self.GetLocation()
                    if LocationData != None and len(LocationData):
                        Data.append({"Location" : LocationData})
                if ForUI:
                    Data.append({"code" : self.WeatherData.get_weather_code()})          # Get OWM weather condition code
                    # "http://openweathermap.org/img/w/" + iconCode + ".png";
                    Data.append({"icon" : self.WeatherData.get_weather_icon_name()})     # Get OWM weather icon code

            return Data
        except Exception as e1:
            self.LogErrorLine("Error in GetWeather: " + str(e1))
            return Data

    #---------------------DegreesToCardinal-------------------------------------
    def DegreesToCardinal(self, Degrees):

        try:
            Value = int((Degrees / 22.5) + .5)
            CardinalDirections = ["N","NNE","NE","ENE","E","ESE", "SE", "SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
            return CardinalDirections[(Value % 16)]
        except:
            return ""

    #---------------------Close-------------------------------------------------
    def Close(self):

        if self.APIKey != None and len(self.APIKey) and self.Location != None and len(self.Location):
            try:
                self.KillThread("WeatherThread")
            except:
                pass
