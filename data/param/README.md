# Liquid cooled model parameters

Read by `GetLiquidCooledParams` in `genmonlib/generac_evolution.py` to find the
kW, voltage, frequency, phase, engine and fuel of an Evolution or Nexus liquid
cooled generator.

| File | Controller |
| --- | --- |
| `EvoLCParam.csv` | Evolution liquid cooled |
| `NexusLCParam.csv` | Nexus liquid cooled |

A unit is matched on **Parameter Group** and **Voltage Code**, the dealer menu
settings read from registers 020a and 020b. The first row that matches is used.

## Columns

| Column | Meaning |
| --- | --- |
| kW | Rated kW |
| Volts | Nominal line voltage |
| Frequency | 50 or 60 (Hz) |
| Phase | 1 or 3 |
| Parameter Group | Dealer menu Parameter Group |
| Voltage Code | Dealer menu Voltage Code. Bit 15 (0x8000) is set on emissions units |
| Emissions | Y for emissions units, otherwise N |
| Unit Voltage Code | Letter code, see below |
| Engine | Engine displacement, for example `2.4 L` |
| Fuel | `Diesel` or `NG/LPV` (Evolution only) |

## Unit Voltage Codes

| Code | Voltage |
| --- | --- |
| A | 120/240 1 phase |
| G | 120/208 3 phase |
| J | 120/240 3 phase |
| K | 277/480 3 phase |
| M | 110/220 1 phase, 50 Hz |
| R | 231/400 3 phase |

The files are plain CSV with a header row, read with Python's `csv.DictReader`.
Columns are found by header name, so keep the names unchanged. Comment lines are
not allowed. `tests/test_data_files.py` checks the files.
