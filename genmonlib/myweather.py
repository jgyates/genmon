# -------------------------------------------------------------------------------
#    FILE: myweather.py
# PURPOSE: app to interface to open weather map api
#
#  AUTHOR: Jason G Yates
#    DATE: 26-May-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import collections
import datetime
import threading
import time

from genmonlib.mysupport import MySupport
from genmonlib.mythread import MyThread

try:
    import pyowm

    pyowm_installed = True
except:
    pyowm_installed = False

# https://pyowm.readthedocs.io/en/latest/pyowm.html
# https://pyowm.readthedocs.io/en/latest/v3/code-recipes.html
class MyWeather(MySupport):
    # ---------------------__init__----------------------------------------------
    def __init__(self, apikey, location, log=None, unit="imperial", debug=False):
        super(MyWeather, self).__init__()
        self.APIKey = apikey
        self.log = log
        self.Location = location
        self.OWM = None
        self.Observation = None
        self.WeatherUnit = unit
        self.WeatherData = None
        self.ObservationLocation = None
        self.DataAccessLock = (
            threading.Lock()
        )  # lock to synchronize access to WeatherData

        self.debug = debug

        if not pyowm_installed:
            self.LogError("Library pyowm not installed, disabling weather support.")
            return
        try:
            if self.APIKey != None:
                self.APIKey = self.APIKey.strip()
            if self.Location != None:
                self.Location = self.Location.strip()

            if (
                self.APIKey == None
                or not len(self.APIKey)
                or self.Location == None
                or not len(self.Location)
            ):
                self.LogError("Weather API key invalid or Weather Location invalid")
                return

            self._InitOWM()
            self.Threads["WeatherThread"] = MyThread(
                self.WeatherThread, Name="WeatherThread"
            )
        except Exception as e1:
            self.LogErrorLine("Error on MyWeather:init: " + str(e1))

    # ---------------------_GetUnits--------------------------------------------
    def _GetUnits(self, measured, Label=False):

        try:
            LookUp = {
                "temp": [["fahrenheit", "F"], ["celsius", "C"]],
                "speed": [["miles_hour", "mph"], ["meters_sec", "m/s"]],
            }

            ReturnList = LookUp.get(measured, None)

            if ReturnList == None:
                self.LogError(
                    "Error in _GetUnits: Unknown measured value: " + str(measured)
                )
                return ""

            if self.WeatherUnit.lower() == "metric":
                Index = 1
            else:
                Index = 0

            if Label:
                return ReturnList[Index][1]
            else:
                return ReturnList[Index][0]
        except Exception as e1:
            self.LogErrorLine("Error in _GetUnits: " + str(e1))

    # ---------------------_InitOWM---------------------------------------------
    def _InitOWM(self):
        try:
            self.OWM = pyowm.OWM(self.APIKey)  # You MUST provide a valid API key
            self.mgr = None
            try:
                self.Version = "Unknown"
                self.Version = self.OWM.version         # tuple
                self.NewAPI = True
                self.LogDebug("New API version: " + str(self.Version))
                self.mgr = self.OWM.weather_manager()
            except:
                self.NewAPI = False
                self.LogDebug("Old API version: " + str(self.Version))
            return True
        except Exception as e1:
            self.OWM = None
            self.LogErrorLine("Error in _InitOWM: " + str(e1))
            return False

    # ---------------------_GetObservation--------------------------------------
    def _GetObservation(self):

        if self.OWM == None:
            self.Observation = None
            self.ObservationLocation = None
            return
        
            
        try:
            if self.NewAPI:
                mgr = self.mgr
            else:
                mgr = self.OWM

            if self.Location.isdigit():
                if len(self.Location.strip()) == 5:  # Assume this is a zip code
                    self.Observation = mgr.weather_at_zip_code(self.Location, "us")
                else:
                    self.Observation = mgr.weather_at_id(int(self.Location))
            else:
                self.Observation = mgr.weather_at_place(self.Location)

            if not self.NewAPI:
                self.ObservationLocation = self.Observation.get_location()
        except Exception as e1:
            self.Observation = None
            self.ObservationLocation = None
            self.LogErrorLine(
                "Error in _GetObservation: "
                + "("
                + str(self.Location)
                + ") : "
                + str(e1)
            )

    # ---------------------WeatherThread-----------------------------------------
    def WeatherThread(self):

        time.sleep(1)
        while True:
            try:
                if self.OWM == None:
                    if not self._InitOWM():
                        if self.WaitForExit("WeatherThread", 60 * 3):  # 3 min
                            return
                        continue
                try:
                    self._GetObservation()
                    if self.Observation == None:
                        self.OWM = None
                        if self.WaitForExit("WeatherThread", 60 * 3):  # 3 min
                            return
                        continue
                    if self.NewAPI:
                        weatherdata = self.Observation.weather
                    else:
                        weatherdata = self.Observation.get_weather()
                    with self.DataAccessLock:
                        self.WeatherData = weatherdata
                except Exception as e1:
                    self.LogErrorLine("Error calling Observation.get_weather: " + str(e1))
                    self.WeatherData = None
                    if self.WaitForExit("WeatherThread", 60 * 3):  # 3 min
                        return
                    continue

                if self.WaitForExit("WeatherThread", 60 * 10):  # ten min
                    return
            except Exception as e1:
                self.LogErrorLine("Erron in WeatherThread: " + str(e1))
                if self.WaitForExit("WeatherThread", 60 * 10):  # ten min
                    return
                

    # ---------------------_GetLocation-----------------------------------------
    def _GetLocation(self):

        Data = []
        try:
            if self.NewAPI:
                if self.Observation == None:
                    return None
                Data.append({"City Name": self.Observation.location.name})
                Data.append({"Latitude": self.Observation.location.lat})
                Data.append({"Longitude": self.Observation.location.lon})
                Data.append({"City ID": self.Observation.location.id})

                self.LogDebug("Location: " + str(self.Observation.location.name))
            else:
                if self.ObservationLocation == None:
                    return None

                Data.append({"City Name": self.ObservationLocation.get_name()})
                Data.append({"Latitude": self.ObservationLocation.get_lat()})
                Data.append({"Longitude": self.ObservationLocation.get_lon()})
                Data.append({"City ID": self.ObservationLocation.get_ID()})
        except Exception as e1:
            self.LogErrorLine("Error in _GetLocation: " + str(e1))

        return Data

    # ---------------------GetWeather--------------------------------------------
    def GetWeather(self, minimum=True, ForUI=False, JSONNum=False):

        Data = []

        try:
            # Search for current weather in location
            if self.OWM == None or self.Observation == None:
                return Data

            if self.WeatherData == None:
                return Data

            with self.DataAccessLock:
                if self.NewAPI:
                    TempDict = self.WeatherData.temperature(unit=self._GetUnits("temp"))
                else:
                    TempDict = self.WeatherData.get_temperature(unit=self._GetUnits("temp"))

                Data.append(
                    {
                        "Current Temperature": str(TempDict.get("temp", 0))
                        + " "
                        + self._GetUnits("temp", Label=True)
                    }
                )
                if self.NewAPI:
                    detailed_status = self.WeatherData.detailed_status
                else:
                    detailed_status = self.WeatherData.get_detailed_status().title()
                Data.append(
                    {"Conditions": detailed_status}
                )

                if not minimum:
                    Data.append(
                        {
                            "Maximum Current Temperature": str(
                                TempDict.get("temp_max", 0)
                            )
                            + " "
                            + self._GetUnits("temp", Label=True)
                        }
                    )
                    Data.append(
                        {
                            "Minimum Current Temperature": str(
                                TempDict.get("temp_min", 0)
                            )
                            + " "
                            + self._GetUnits("temp", Label=True)
                        }
                    )

                    if self.NewAPI:
                        humidity = self.WeatherData.humidity
                    else:
                        humidity = self.WeatherData.get_humidity()
                    Data.append({"Humidity": str(humidity) + " %"})

                    if self.NewAPI:
                        clouds = self.WeatherData.clouds
                    else:
                        clouds = self.WeatherData.get_clouds()
                    Data.append({"Cloud Coverage": str(clouds) + " %"})

                    if self.NewAPI:
                        wind = self.WeatherData.wind(unit=self._GetUnits("speed"))
                    else:
                        wind = self.WeatherData.get_wind(unit=self._GetUnits("speed"))

                    Degrees = round(TempDict.get("deg", 0), 2)
                    Cardinal = self._DegreesToCardinal(Degrees)
                    
                    if len(Cardinal):
                        WindString = Cardinal + " (" + str(Degrees) + " Degrees), "
                    else:
                        WindString = str(Degrees) + " Degrees, "
                    Data.append(
                        {
                            "Wind": WindString
                            + str(round(TempDict.get("speed", 0), 2))
                            + " "
                            + self._GetUnits("speed", Label=True)
                        }
                    )

                    if self.NewAPI:
                        TempDict = self.WeatherData.rain
                    else:
                        TempDict = self.WeatherData.get_rain()
                    
                    if len(TempDict):
                        amount = TempDict.get("3h", None)
                        if amount is not None:
                            Data.append({"Rain in last 3 hours": str(amount) + " mm"})
                        amount = TempDict.get("1h", None)
                        if amount is not None:
                            Data.append({"Rain in last hour": str(amount) + " mm"})
                    
                    if self.NewAPI:
                        TempDict = self.WeatherData.snow
                    else:
                        TempDict = self.WeatherData.get_snow()

                    if len(TempDict):
                        amount = TempDict.get("3h", None)
                        if amount is not None:
                            Data.append({"Snow in last 3 hours": str(amount) + " mm"})
                        amount = TempDict.get("1h", None)
                        if amount is not None:
                            Data.append({"Snow in last hour": str(amount) + " mm"})

                    if self.NewAPI:
                        TempDict = self.WeatherData.pressure
                    else:
                        TempDict = self.WeatherData.get_pressure()

                    if len(TempDict):
                        Data.append(
                            {"Pressure": str(TempDict.get("press", 0)) + " " + "hPa"}
                        )

                    if self.NewAPI:
                        sunrise_time = self.WeatherData.sunrise_time()
                    else:
                        sunrise_time = self.WeatherData.get_sunrise_time()

                    Data.append(
                        {
                            "Sunrise Time": datetime.datetime.fromtimestamp(
                                int(sunrise_time)
                            ).strftime("%A %B %d, %Y %H:%M:%S")
                        }
                    )
                    if self.NewAPI:
                        sunset_time = self.WeatherData.sunset_time()
                    else:
                        sunset_time = self.WeatherData.get_sunset_time()
                    Data.append(
                        {
                            "Sunset Time": datetime.datetime.fromtimestamp(
                                int(sunset_time)
                            ).strftime("%A %B %d, %Y %H:%M:%S")
                        }
                    )

                    if self.NewAPI:
                        reference_time = self.WeatherData.reference_time()
                    else:
                        reference_time = self.WeatherData.get_reference_time()

                    ReferenceTime = datetime.datetime.fromtimestamp(
                        int(reference_time)
                    )
                    Data.append(
                        {
                            "Reference Time": ReferenceTime.strftime(
                                "%A %B %d, %Y %H:%M:%S"
                            )
                        }
                    )
                    LocationData = self._GetLocation()
                    if LocationData != None and len(LocationData):
                        Data.append({"Location": LocationData})
                if ForUI:
                    if self.NewAPI:
                        weather_code = self.WeatherData.weather_code
                        icon = self.WeatherData.weather_icon_name
                    else:
                        weather_code = self.WeatherData.get_weather_code()
                        icon = self.WeatherData.get_weather_icon_name()
                    Data.append(
                        {"code": weather_code}
                    )  # Get OWM weather condition code
                    # "http://openweathermap.org/img/w/" + iconCode + ".png";
                    Data.append(
                        {"icon": icon}
                    )  # Get OWM weather icon code

            return Data
        except Exception as e1:
            self.LogErrorLine("Error in GetWeather: " + str(e1))
            return Data

    # ---------------------_DegreesToCardinal-------------------------------------
    def _DegreesToCardinal(self, Degrees):

        try:
            Value = int((Degrees / 22.5) + 0.5)
            CardinalDirections = [
                "N",
                "NNE",
                "NE",
                "ENE",
                "E",
                "ESE",
                "SE",
                "SSE",
                "S",
                "SSW",
                "SW",
                "WSW",
                "W",
                "WNW",
                "NW",
                "NNW",
            ]
            return CardinalDirections[(Value % 16)]
        except:
            return ""

    # ---------------------Close-------------------------------------------------
    def Close(self):

        if (
            self.APIKey != None
            and len(self.APIKey)
            and self.Location != None
            and len(self.Location)
        ):
            try:
                self.KillThread("WeatherThread")
            except:
                pass
