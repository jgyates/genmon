# Fuel consumption

Read by `GetFuelParamsFromFile` in `genmonlib/generac_evolution.py` to estimate
fuel use of Evolution generators.

| File | Generators | Matched on |
| --- | --- | --- |
| `EvoAC_Fuel.csv` | Evolution air cooled | Reg0019 (model ID) and Fuel |
| `EvoAC2_Fuel.csv` | Evolution 2 air cooled | Reg0019 (model ID) and Fuel |
| `EvoLC_Fuel.csv` | Evolution liquid cooled | kW and Fuel |
| `EvoLC45_Fuel.csv` | Evolution liquid cooled, 4.5 L engine | kW and Fuel |

Each row gives the fuel used per hour at a load: for example `50%` is the load
(0.5) and `Rate 50%` the rate at that load, in `Units` (`gal` or `cubic feet`)
per hour. Fuel is `Propane`, `Natural Gas` or `Diesel`. The `Notes` column in
`EvoAC2_Fuel.csv` is not read by genmon.

The files are plain CSV with a header row, read with Python's `csv.DictReader`.
Columns are found by header name, so keep the names unchanged. Comment lines are
not allowed. `tests/test_data_files.py` checks the files.
