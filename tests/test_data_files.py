#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_data_files.py
# PURPOSE: Checks of the CSV data files genmon reads by column name
#          (MySupport.ReadCSVFile, csv.DictReader):
#
#          - data/fuel/*.csv: fuel use of Evolution generators
#            (Evolution.GetFuelParamsFromFile, see data/fuel/README.md)
#          - data/param/*.csv: liquid cooled models
#            (Evolution.GetLiquidCooledParams, see data/param/README.md)
#          - data/ALARMS.csv: Evolution / Nexus alarm code names
#            (Evolution.GetAlarmInfo)
#
#          Each file must have the header the code expects, the same number of
#          values on every row, no comment lines, values of the right kind
#          (Volts and Phase agree with the Unit Voltage Code), and one row per
#          lookup key (only the first match is used).
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_data_files
#
# -------------------------------------------------------------------------------

import collections
import csv
import glob
import os
import re
import unittest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUEL_DIR = os.path.join(REPO_DIR, "data", "fuel")
PARAM_DIR = os.path.join(REPO_DIR, "data", "param")

AC_FUEL = ["Reg0019", "kW", "Fuel", "Hz", "50%", "Rate 50%", "100%", "Rate 100%", "Units"]
LC_FUEL = ["kW", "Fuel", "25%", "Rate 25%", "50%", "Rate 50%", "75%", "Rate 75%", "100%", "Rate 100%", "Units"]
PARAM = ["kW", "Volts", "Frequency", "Phase", "Parameter Group", "Voltage Code", "Emissions",
         "Unit Voltage Code", "Engine"]

# file: (header, lookup key columns)
FILES = {
    "fuel/EvoAC_Fuel.csv": (AC_FUEL, ["Reg0019", "Fuel"]),
    "fuel/EvoAC2_Fuel.csv": (AC_FUEL + ["Notes"], ["Reg0019", "Fuel"]),
    "fuel/EvoLC_Fuel.csv": (LC_FUEL, ["kW", "Fuel"]),
    "fuel/EvoLC45_Fuel.csv": (LC_FUEL, ["kW", "Fuel"]),
    "param/EvoLCParam.csv": (PARAM + ["Fuel"], ["Parameter Group", "Voltage Code"]),
    "param/NexusLCParam.csv": (PARAM, ["Parameter Group", "Voltage Code"]),
    "ALARMS.csv": (["Code", "Name"], ["Code"]),
}

# known problems in NexusLCParam.csv, kept so that new ones are found. The
# first row of a duplicate key is the one used.
NEXUS_DUPLICATE_KEYS = {
    ("2", "16"), ("2", "2064"), ("3", "4112"), ("6", "16"), ("6", "2064"), ("6", "4112"),
    ("6", "6160"), ("15", "16"), ("15", "2064"), ("19", "16"), ("19", "32784"),
    ("19", "2071"), ("19", "4113"), ("19", "6144"),
}
# (kW, Parameter Group, Voltage Code): Emissions is Y but bit 15 of the
# Voltage Code is not set
NEXUS_EMISSIONS_MISMATCH = {("45", "2", "16"), ("45", "19", "2071")}

# Unit Voltage Code: (Volts, Phase)
VOLTAGE_CODES = {"A": ("240", "1"), "G": ("208", "3"), "J": ("240", "3"), "K": ("480", "3"),
                 "M": ("220", "1"), "R": ("400", "3")}


def read(name):
    """The header and the rows (lists) of data/<name>."""
    with open(os.path.join(REPO_DIR, "data", name), newline="") as f:
        rows = list(csv.reader(f))
    return rows[0], [r for r in rows[1:] if r]


def read_dicts(name):
    with open(os.path.join(REPO_DIR, "data", name), newline="") as f:
        return list(csv.DictReader(f))


def is_number(value):
    try:
        float(value)
        return True
    except ValueError:
        return False


class DataFileTests(unittest.TestCase):

    def test_all_files_listed(self):
        # a new CSV file in data, data/fuel or data/param needs checks here
        found = {os.path.relpath(p, os.path.join(REPO_DIR, "data")).replace(os.sep, "/")
                 for folder in [os.path.join(REPO_DIR, "data"), FUEL_DIR, PARAM_DIR]
                 for p in glob.glob(os.path.join(folder, "*.csv"))}
        self.assertEqual(found, set(FILES))

    def test_format(self):
        for name, (header, key) in FILES.items():
            with self.subTest(file=name):
                found, rows = read(name)
                self.assertEqual(found, header)
                for number, row in enumerate(rows, 2):
                    self.assertFalse(row[0].startswith("#"), "line %d is a comment" % number)
                    self.assertEqual(len(row), len(header), "line %d: %s" % (number, row))
                    self.assertEqual([v.strip() for v in row], row, "line %d has spaces" % number)

    def test_unique_keys(self):
        for name, (header, key) in FILES.items():
            with self.subTest(file=name):
                count = collections.Counter(tuple(r[k] for k in key) for r in read_dicts(name))
                duplicates = {k for k, n in count.items() if n > 1}
                if name == "param/NexusLCParam.csv":
                    self.assertEqual(duplicates, NEXUS_DUPLICATE_KEYS)
                else:
                    self.assertEqual(duplicates, set())

    def test_fuel_values(self):
        for name in [n for n in FILES if n.startswith("fuel/")]:
            with self.subTest(file=name):
                for row in read_dicts(name):
                    self.assertIn(row["Fuel"], ["Propane", "Natural Gas", "Diesel"], row)
                    self.assertEqual(row["Units"], "cubic feet" if row["Fuel"] == "Natural Gas" else "gal", row)
                    loads = [c for c in row if c.endswith("%") and not c.startswith("Rate")]
                    for load in loads:
                        self.assertEqual(float(row[load]), float(load[:-1]) / 100, row)
                        self.assertTrue(is_number(row["Rate " + load]), row)
                    if "Reg0019" in row:
                        self.assertTrue(row["Reg0019"].isdigit(), row)
                        self.assertIn(row["Hz"], ["50", "60"], row)
                    else:
                        self.assertTrue(is_number(row["kW"]), row)

    def test_param_values(self):
        for name in [n for n in FILES if n.startswith("param/")]:
            with self.subTest(file=name):
                for row in read_dicts(name):
                    model = (row["kW"], row["Parameter Group"], row["Voltage Code"])
                    for column in ["kW", "Volts", "Phase", "Parameter Group", "Voltage Code"]:
                        self.assertTrue(row[column].isdigit(), row)
                    self.assertIn(row["Frequency"], ["50", "60"], row)
                    self.assertIn(row["Unit Voltage Code"], VOLTAGE_CODES, row)
                    self.assertEqual((row["Volts"], row["Phase"]), VOLTAGE_CODES[row["Unit Voltage Code"]], row)
                    self.assertRegex(row["Engine"], re.compile(r"^\d\.\d L$"))
                    self.assertIn(row["Emissions"], ["Y", "N"], row)
                    if model not in NEXUS_EMISSIONS_MISMATCH:
                        self.assertEqual(bool(int(row["Voltage Code"]) & 0x8000), row["Emissions"] == "Y", row)
                    if "Fuel" in row:
                        self.assertIn(row["Fuel"], ["Diesel", "NG/LPV"], row)

    def test_alarm_values(self):
        # codes are decimal (the controller reports them as a 16 bit register
        # value in hex, GetAlarmInfo converts), names are shown to the user
        for row in read_dicts("ALARMS.csv"):
            self.assertTrue(row["Code"].isdigit(), row)
            self.assertTrue(0 < int(row["Code"]) <= 0xFFFF, row)
            self.assertTrue(row["Name"], row)

    def test_known_problems_still_present(self):
        # when a known Nexus problem is fixed, remove it from the lists above
        rows = {(r["kW"], r["Parameter Group"], r["Voltage Code"]): r for r in read_dicts("param/NexusLCParam.csv")}
        for model in NEXUS_EMISSIONS_MISMATCH:
            self.assertIn(model, rows)
            self.assertNotEqual(bool(int(model[2]) & 0x8000), rows[model]["Emissions"] == "Y")


if __name__ == "__main__":
    unittest.main()
