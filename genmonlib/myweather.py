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
import mysupport, mythread

try:
    import pyowm
    pyowm_installed = True
except:
    pyowm_installed = False

class MyWeather(mysupport.MySupport):
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
        self.DataAccessLock = threading.Lock()     # lock to synchronize access to WeatherData

        if not pyowm_installed:
            self.LogError("Library pyowm not installed, disabling weather support." )
            return

        self.InitOWM()

        self.Threads["WeatherThread"] = mythread.MyThread(self.WeatherThread, Name = "WeatherThread")

    #---------------------GetUnits----------------------------------------------
    def GetUnits(self, measured, Label = False):

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

    #---------------------InitOWM-----------------------------------------------
    def InitOWM(self):
        try:
            self.OWM = pyowm.OWM(self.APIKey) # You MUST provide a valid API key
        except Exception as e1:
            self.OWM = None
            self.LogErrorLine("Error in InitOWM: " + str(e1))
        try:
            if self.Location.isdigit():
                self.Observation = self.OWM.weather_at_id(int(self.Location))
            else:
                self.Observation = self.OWM.weather_at_place(self.Location)
            self.Location = self.Observation.get_location()
        except Exception as e1:
            self.Observation = None
            self.LogErrorLine("Error in InitOWM (location): " + str(e1))

    #---------------------WeatherThread-----------------------------------------
    def WeatherThread(self):

        time.sleep(1)
        while True:
            if self.OWM == None or self.Observation == None:
                self.InitOWM()
            if self.OWM == None or self.Observation == None:
                time.sleep(60)
                continue
            try:
                weatherdata = self.Observation.get_weather()
                with self.DataAccessLock:
                    self.WeatherData = weatherdata
            except Exception as e1:
                self.LogErrorLine("Error calling Observation.get_weather: " + str(e1))
                self.WeatherData = None
                time.sleep(60)
                continue

            for x in range(0, 60):
                time.sleep(10)
                if self.IsStopSignaled("WeatherThread"):
                        return

    #---------------------GetWeather--------------------------------------------
    def GetWeather(self, minimum = True, ForUI = False):

        Data = collections.OrderedDict()

        try:
            # Search for current weather in location
            if self.OWM == None or self.Observation == None:
                return Data

            if self.WeatherData == None:
                return Data

            with self.DataAccessLock:
                TempDict = self.WeatherData.get_temperature(unit = self.GetUnits("temp"))
                Data["Current Temperature"] = str(TempDict.get('temp', 0)) + " " + self.GetUnits("temp", Label = True)
                Data["Conditions"] = self.WeatherData.get_detailed_status().title()

                if not minimum:
                    Data["Maximum Current Temperature"] = str(TempDict.get('temp_max', 0)) + " " + self.GetUnits("temp", Label = True)
                    Data["Minimum Current Temperature"] = str(TempDict.get('temp_min', 0)) + " " + self.GetUnits("temp", Label = True)
                    Data["Humidity"] = str(self.WeatherData.get_humidity() ) + " %"
                    Data["Cloud Coverage"] = str(self.WeatherData.get_clouds()) + " %"
                    TempDict = self.WeatherData.get_wind(unit = self.GetUnits("speed")) # unit is meters_sec or miles_hour
                    Data["Wind"] = str(round(TempDict.get("deg", 0), 2)) + " Degrees, " + str(round(TempDict.get("speed", 0),2)) + " " +self.GetUnits("speed", Label = True)
                    TempDict = self.WeatherData.get_rain()
                    if len(TempDict):
                        Data["Rain in last 3 hours"] = str(TempDict.get("3h", 0))
                    TempDict = self.WeatherData.get_snow()
                    if len(TempDict):
                        Data["Snow in last 3 hours"] = str(TempDict.get("3h", 0))

                    TempDict = self.WeatherData.get_pressure()
                    if len(TempDict):
                        Data["Pressure"] = str(TempDict.get("press", 0)) + " " + "hpa"

                    Data["Sunrise Time"] = datetime.datetime.fromtimestamp(int(self.WeatherData.get_sunrise_time())).strftime("%A %B %-d, %Y %H:%M:%S")
                    Data["Sunset Time"] = datetime.datetime.fromtimestamp(int(self.WeatherData.get_sunset_time())).strftime("%A %B %-d, %Y %H:%M:%S")

                    UTC = datetime.datetime.fromtimestamp(int(self.WeatherData.get_reference_time()))
                    Local = self.UTC2Local(UTC)
                    Data["Reference Time"] = Local.strftime("%A %B %-d, %Y %H:%M:%S")
                if ForUI:
                    Data["code"] = self.WeatherData.get_weather_code()          # Get OWM weather condition code
                    # "http://openweathermap.org/img/w/" + iconCode + ".png";
                    Data["icon"] = self.WeatherData.get_weather_icon_name()     # Get OWM weather icon code

            return Data
        except Exception, e1:
            self.LogErrorLine("Error in GetWeather: " + str(e1))
            return Data

    #---------------------UTC2Local---------------------------------------------
    def UTC2Local(self, utc):
        epoch = time.mktime(utc.timetuple())
        offset = datetime.datetime.fromtimestamp (epoch) - datetime.datetime.utcfromtimestamp (epoch)
        return utc + offset

    #---------------------Close-------------------------------------------------
    def Close(self):

        if not self.OWM == None and not self.Observation == None:
            self.KillThread("WeatherThread")
