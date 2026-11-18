#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_mytile.py
# PURPOSE: Tests for genmonlib/mytile.py, the gauges and graphs of the web
#          page's dashboard: the scale, labels and color zones of each gauge
#          type, the values shown (and kept within the scale), and invalid
#          gauges.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_mytile
#
# -------------------------------------------------------------------------------

import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genmonlib.mytile import MyTile  # noqa: E402

GAUGE_TYPES = ["batteryvolts", "linevolts", "current", "power", "frequency", "rpm", "fuel",
               "level", "position", "wifipercent", "loadbalance", "temperature", "pressure",
               "wifi"]


class TileTestCase(unittest.TestCase):

    def setUp(self):
        self.log = logging.getLogger("mytile_test")
        self.log.handlers, self.log.propagate = [], False
        self.errors = []

        class Collect(logging.Handler):
            def emit(handler, record):
                self.errors.append(record.getMessage())

        self.log.addHandler(Collect())

    def tile(self, type, value=None, **kwargs):
        return MyTile(self.log, title="Test", type=type, units=kwargs.pop("units", "V"),
                      callback=(lambda: value), callbackparameters=(), **kwargs)


class GaugeTests(TileTestCase):

    def test_every_type_with_defaults(self):
        for gauge in GAUGE_TYPES:
            with self.subTest(type=gauge):
                tile = self.tile(gauge)
                info = tile.GetStartInfo()
                self.assertLess(info["minimum"], info["maximum"])
                self.assertTrue(info["colorzones"])
                # the color zones cover the scale, in order
                zones = info["colorzones"]
                self.assertEqual(zones[0]["min"], info["minimum"])
                self.assertEqual(zones[-1]["max"], info["maximum"])
                for zone in zones:
                    self.assertLessEqual(zone["min"], zone["max"])
                self.assertEqual(info["type"], "gauge")
        self.assertEqual(self.errors, [])

    def test_line_volts_without_nominal(self):
        # the 240 V default (the gauge failed: the tolerances were worked out
        # before the default was set)
        tile = self.tile("linevolts")
        self.assertEqual((tile.Nominal, tile.Maximum), (240, 280))
        self.assertEqual([z["strokeStyle"] for z in tile.ColorZones],
                         [tile.RED, tile.YELLOW, tile.GREEN, tile.YELLOW, tile.RED])
        self.assertEqual(tile.ColorZones[2], {"strokeStyle": tile.GREEN, "min": 228, "max": 252})
        self.assertEqual(self.errors, [])

    def test_nominal_values(self):
        tile = self.tile("batteryvolts", nominal=24)
        self.assertEqual(tile.Maximum, 32)
        tile = self.tile("power", nominal=22)
        self.assertEqual(tile.Maximum, 26)
        self.assertEqual(tile.Labels, [0, 5, 10, 15, 20, 26])
        tile = self.tile("frequency", nominal=50)
        self.assertEqual(tile.Maximum, 60)

    def test_pressure(self):
        # zones are a percentage of nominal and stay within the scale (the top
        # zone went past the maximum); the labels end at the maximum
        tile = self.tile("pressure", units="kPa", nominal=400, maximum=700)
        self.assertEqual([(z["strokeStyle"], z["min"], z["max"]) for z in tile.ColorZones],
                         [(tile.RED, 0, 200), (tile.YELLOW, 200, 300),
                          (tile.GREEN, 300, 500), (tile.YELLOW, 500, 700)])
        self.assertEqual(tile.Labels, list(range(0, 701, 70)))
        # defaults: 1.5 x nominal
        tile = self.tile("pressure", units="psi")
        self.assertEqual((tile.Nominal, tile.Maximum), (100, 150))
        self.assertEqual(tile.Labels[-1], 150)
        # small units (bar) and a maximum below the top of the green zone
        tile = self.tile("pressure", units="bar", nominal=3, maximum=5)
        self.assertEqual([z["max"] for z in tile.ColorZones], [1.5, 2.25, 3.75, 5])
        self.assertEqual(tile.Labels, [0, 1, 2, 3, 4, 5])
        tile = self.tile("pressure", units="kPa", nominal=100, maximum=110)
        self.assertEqual([(z["strokeStyle"], z["max"]) for z in tile.ColorZones],
                         [(tile.RED, 50), (tile.YELLOW, 75), (tile.GREEN, 110)])
        self.assertEqual(self.errors, [])

    def test_graph(self):
        tile = self.tile("powergraph", nominal=20)
        self.assertEqual(tile.GetStartInfo()["type"], "graph")
        self.assertEqual(tile.Maximum, 24)

    def test_values(self):
        self.assertEqual(self.tile("batteryvolts", 13.2).GetGUIInfo()["text"], "13.2 V")
        info = self.tile("batteryvolts", 13.2).GetGUIInfo()
        self.assertEqual((info["value"], info["title"], info["subtype"]), ("13.2", "Test", "batteryvolts"))
        self.assertEqual(self.tile("power", 5, units="kW").GetGUIInfo()["text"], "5 kW")
        # text with decimals (it raised an error, the gauge had no data)
        self.assertEqual(self.tile("batteryvolts", "12.5").GetGUIInfo()["value"], "12.5")
        self.assertEqual(self.errors, [])

    def test_value_outside_the_scale(self):
        # the text shows the value, the gauge stops at its end
        info = self.tile("batteryvolts", 30.0).GetGUIInfo()
        self.assertEqual((info["text"], info["value"]), ("30 V", "16"))
        info = self.tile("wifi", -120, units="dBm").GetGUIInfo()
        self.assertEqual((info["text"], info["value"]), ("-120 dBm", "-100"))

    def test_no_value(self):
        self.assertEqual(self.tile("fuel", None, units="%").GetGUIInfo()["value"], "0")

    def test_invalid(self):
        MyTile(self.log, title=None, type="power")
        MyTile(self.log, title="T", type=None)
        MyTile(self.log, title="T", type="nothing")
        self.assertEqual(len(self.errors), 3)
        self.errors.clear()
        tile = self.tile("power", nominal=10, minimum=20, maximum=20)
        self.assertIn("invalid value", self.errors[0])
        self.assertEqual(tile.Maximum, tile.Minimum)

    def test_labels_end_at_the_maximum(self):
        # (they stopped one step short: 0..90 on a 0-100 fuel gauge)
        for gauge, kwargs, last in [("fuel", {}, 100), ("level", {}, 100), ("position", {}, 100),
                                    ("wifipercent", {}, 100), ("loadbalance", {}, 100),
                                    ("temperature", {}, 100), ("temperature", {"subtype": "coolant"}, 100),
                                    ("wifi", {}, -30), ("linevolts", {"nominal": 12}, 12),
                                    ("current", {"nominal": 20}, 24), ("frequency", {}, 70),
                                    ("pressure", {}, 150), ("batteryvolts", {}, 16)]:
            with self.subTest(type=gauge, **kwargs):
                tile = self.tile(gauge, **kwargs)
                self.assertEqual(tile.Labels[-1], last)
                self.assertEqual(tile.Labels[-1], tile.Maximum)
        # a small scale (steps of at least 1)
        self.assertEqual(self.tile("fuel", nominal=5).Labels, [0, 1, 2, 3, 4, 5])
        # a maximum between steps: added, or in place of a label too close to it
        self.assertEqual(MyTile.LabelRange(0, 24, 5), [0, 5, 10, 15, 20, 24])
        self.assertEqual(MyTile.LabelRange(0, 21, 5), [0, 5, 10, 15, 21])

    def test_labels(self):
        tile = MyTile(self.log, title="T", type="current", nominal=100)
        self.assertEqual(tile.Labels, [0, 20, 40, 60, 80, 100, 120])
        # from the values given (it used the tile's own minimum and maximum)
        self.assertEqual(tile.CreateLabels(0, 10, 12), [0, 2, 4, 6, 8, 10, 12])


if __name__ == "__main__":
    unittest.main()
