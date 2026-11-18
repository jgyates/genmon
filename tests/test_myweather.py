#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_myweather.py
# PURPOSE: Tests for genmonlib/myweather.py, the weather shown on the web page
#          (OpenWeatherMap, the pyowm library): finding the location (city,
#          US zip code, city ID), the values shown in imperial and metric units
#          (temperature, conditions, wind, rain, snow, pressure, sun rise and
#          set, location), the old pyowm interface, and errors.
#
#          pyowm is a fake: nothing is sent to OpenWeatherMap.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_myweather
#
# -------------------------------------------------------------------------------

import datetime
import logging
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genmonlib import myweather  # noqa: E402

SUNRISE = int(datetime.datetime(2026, 11, 2, 6, 30).timestamp())


class FakeWeather(object):
    """pyowm 3 Weather."""

    def __init__(self):
        self.units = []
        self.detailed_status = "light rain"
        self.humidity = 81
        self.clouds = 75
        self.rain = {"1h": 0.5}
        self.snow = {}
        self.pressure = {"press": 1012, "sea_level": None}
        self.weather_code = 500
        self.weather_icon_name = "10d"

    def temperature(self, unit):
        self.units.append(unit)
        return {"temp": 61.5 if unit == "fahrenheit" else 16.4, "temp_max": 63.0, "temp_min": 59.0}

    def wind(self, unit):
        self.units.append(unit)
        return {"speed": 7.25, "deg": 225}

    def sunrise_time(self):
        return SUNRISE

    def sunset_time(self):
        return SUNRISE + 10 * 3600

    def reference_time(self):
        return SUNRISE + 3600


class FakeOldWeather(object):
    """pyowm 2 Weather (get_ methods)."""

    def __init__(self):
        self.new = FakeWeather()

    def get_temperature(self, unit):
        return self.new.temperature(unit)

    def get_detailed_status(self):
        return "clear sky"

    def get_humidity(self):
        return 40

    def get_clouds(self):
        return 0

    def get_wind(self, unit):
        return self.new.wind(unit)

    def get_rain(self):
        return {}

    def get_snow(self):
        return {"3h": 2}

    def get_pressure(self):
        return {"press": 1020}

    def get_sunrise_time(self):
        return SUNRISE

    def get_sunset_time(self):
        return SUNRISE

    def get_reference_time(self):
        return SUNRISE

    def get_weather_code(self):
        return 800

    def get_weather_icon_name(self):
        return "01d"


def fake_pyowm(old_api=False, fail=None):
    """pyowm with an OWM whose weather manager records the lookups."""
    calls = []
    location = types.SimpleNamespace(name="Springfield", lat=39.8, lon=-89.6, id=4250542)

    class Manager(object):
        def lookup(self, kind, *args):
            calls.append((kind,) + args)
            if fail:
                raise fail
            weather = FakeOldWeather() if old_api else FakeWeather()
            observation = types.SimpleNamespace(weather=weather, location=location)
            observation.get_weather = lambda: weather
            observation.get_location = lambda: types.SimpleNamespace(
                get_name=lambda: "Springfield", get_lat=lambda: 39.8, get_lon=lambda: -89.6,
                get_ID=lambda: 4250542)
            return observation

        def weather_at_place(self, place):
            return self.lookup("place", place)

        def weather_at_zip_code(self, zipcode, country):
            return self.lookup("zip", zipcode, country)

        def weather_at_id(self, city_id):
            return self.lookup("id", city_id)

    class OWM(Manager):
        def __init__(self, apikey):
            calls.append(("key", apikey))
            if not old_api:
                self.version = (3, 3, 0)

        def __getattribute__(self, name):
            if name == "version" and old_api:
                raise AttributeError(name)
            return object.__getattribute__(self, name)

        def weather_manager(self):
            return Manager()

    return types.SimpleNamespace(OWM=OWM), calls


class WeatherTestCase(unittest.TestCase):

    def weather(self, location="Springfield, IL", unit="imperial", apikey="key123", **fake):
        pyowm, self.calls = fake_pyowm(**fake)
        log = logging.getLogger("myweather_test")
        log.handlers, log.propagate = [], False
        self.errors = []

        class Collect(logging.Handler):
            def emit(handler, record):
                self.errors.append(record.getMessage())

        log.addHandler(Collect())
        patches = [mock.patch.object(myweather, "pyowm", pyowm, create=True),
                   mock.patch.object(myweather, "pyowm_installed", True),
                   mock.patch.object(myweather, "MyThread")]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        weather = myweather.MyWeather(apikey, location, log=log, unit=unit)
        return weather

    def poll(self, weather):
        """One pass of the weather thread."""
        with mock.patch.object(weather, "WaitForExit", return_value=True), \
                mock.patch.object(myweather.time, "sleep"):
            weather.WeatherThread()

    def values(self, weather, **kwargs):
        data = weather.GetWeather(**kwargs)
        return {key: value for item in data for key, value in item.items()}


# -------------------------------------------------------------------------------
class WeatherTests(WeatherTestCase):

    def test_location(self):
        for location, expected in [("Springfield, IL", ("place", "Springfield, IL")),
                                   (" 62701 ", ("zip", "62701", "us")),
                                   ("4250542", ("id", 4250542))]:
            with self.subTest(location=location):
                weather = self.weather(location)
                self.poll(weather)
                self.assertEqual(self.calls[-1], expected)
        self.assertEqual(self.calls[0], ("key", "key123"))

    def test_imperial(self):
        weather = self.weather()
        self.poll(weather)
        values = self.values(weather, minimum=False)
        self.assertEqual(values["Current Temperature"], "61.5 F")
        self.assertEqual(values["Conditions"], "light rain")
        self.assertEqual(values["Maximum Current Temperature"], "63.0 F")
        self.assertEqual(values["Humidity"], "81 %")
        self.assertEqual(values["Cloud Coverage"], "75 %")
        self.assertEqual(values["Rain in last hour"], "0.5 mm")
        self.assertNotIn("Snow in last hour", values)
        self.assertEqual(values["Pressure"], "1012 hPa")
        self.assertEqual(values["Sunrise Time"], "Monday November 02, 2026 06:30:00")
        self.assertEqual(values["Location"][0], {"City Name": "Springfield"})
        self.assertIn("fahrenheit", weather.WeatherData.units)

    def test_wind(self):
        # from the wind data (it was always "N (0 Degrees), 0 mph")
        weather = self.weather()
        self.poll(weather)
        self.assertEqual(self.values(weather, minimum=False)["Wind"], "SW (225 Degrees), 7.25 mph")

    def test_metric(self):
        weather = self.weather(unit="metric")
        self.poll(weather)
        values = self.values(weather, minimum=False)
        self.assertEqual(values["Current Temperature"], "16.4 C")
        self.assertTrue(values["Wind"].endswith("m/s"))
        self.assertEqual(weather.WeatherData.units[:2], ["celsius", "meters_sec"])

    def test_minimum_and_web_page(self):
        weather = self.weather()
        self.poll(weather)
        self.assertEqual(list(self.values(weather)), ["Current Temperature", "Conditions"])
        values = self.values(weather, ForUI=True)
        self.assertEqual((values["code"], values["icon"]), (500, "10d"))

    def test_old_pyowm(self):
        weather = self.weather(old_api=True)
        self.poll(weather)
        self.assertFalse(weather.NewAPI)
        values = self.values(weather, minimum=False, ForUI=True)
        self.assertEqual(values["Conditions"], "Clear Sky")
        self.assertEqual(values["Snow in last 3 hours"], "2 mm")
        self.assertEqual(values["Location"][0], {"City Name": "Springfield"})
        self.assertEqual(values["code"], 800)

    def test_no_data_yet(self):
        weather = self.weather()
        self.assertEqual(weather.GetWeather(), [])

    def test_lookup_fails(self):
        weather = self.weather(fail=ValueError("not found"))
        self.poll(weather)
        self.assertIsNone(weather.Observation)
        self.assertEqual(weather.GetWeather(), [])
        self.assertTrue(any("not found" in e for e in self.errors))

    def test_no_key_or_location(self):
        for apikey, location in [("", "Springfield"), ("key", " "), (None, "Springfield")]:
            with self.subTest(apikey=apikey, location=location):
                weather = self.weather(location, apikey=apikey)
                self.assertIsNone(weather.OWM)
                self.assertEqual(weather.GetWeather(), [])

    def test_pyowm_not_installed(self):
        with mock.patch.object(myweather, "pyowm_installed", False):
            log = logging.getLogger("myweather_test_missing")
            log.handlers, log.propagate = [logging.NullHandler()], False
            weather = myweather.MyWeather("key", "Springfield", log=log)
        self.assertIsNone(weather.OWM)

    def test_cardinal(self):
        weather = self.weather()
        for degrees, expected in [(0, "N"), (44, "NE"), (90, "E"), (190, "S"), (350, "N")]:
            self.assertEqual(weather._DegreesToCardinal(degrees), expected)


if __name__ == "__main__":
    unittest.main()
