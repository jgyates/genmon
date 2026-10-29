---
name: sync-upstream
description: Merge new commits from jgyates/genmon (upstream) into this genmon-esp32 fork and port the relevant changes into the ESP32 firmware under esp32/. Use when the user asks to sync, update from upstream, pull in upstream changes, or check what changed in genmon.
---

# Sync upstream genmon into genmon-esp32

This fork keeps upstream's Python project **untouched** at the repository root and adds the
ESP32 firmware in `esp32/` (plus this skill in `.claude/`). Because the fork never edits
upstream files, merging `upstream/master` is conflict-free; the real work is deciding which
upstream changes the firmware must mirror, and porting them.

Remotes: `origin` = the fork (github.com/slevin22/genmon-esp32), `upstream` = github.com/jgyates/genmon.

## 1. Preconditions

1. `git status --porcelain` must be empty (ask the user to commit or stash otherwise).
2. Check remotes with `git remote -v`. If `upstream` is missing:
   `git remote add upstream https://github.com/jgyates/genmon`
3. `git fetch upstream` and `git fetch origin`.
4. Work on a branch: `git switch -c sync/upstream-YYYY-MM-DD origin/master` (today's date).

## 2. Find what changed

The last upstream commit already merged is the merge base, so no bookkeeping file is needed:

```bash
BASE=$(git merge-base HEAD upstream/master)
git log --oneline "$BASE"..upstream/master
git diff --stat "$BASE"..upstream/master
```

If the log is empty, report "already up to date" and stop.

## 3. Merge

```bash
git merge --no-ff upstream/master -m "chore: merge upstream genmon <short-sha>"
```

A conflict means a fork commit touched an upstream file. Resolve in upstream's favour
(`git checkout --theirs <file>`) unless the user says otherwise, then move any needed
fork-specific behaviour into `esp32/`.

## 4. Triage each changed upstream file

Classify every file from the `--stat` list with this table. Report the classification to
the user before porting anything that is not automatic.

| Upstream path | Firmware counterpart | Action |
|---|---|---|
| `data/ALARMS.txt` | `esp32/src/core/alarm_codes_table.inc` | **Automatic**: regenerate (step 5) |
| `data/homeassistant/base.json`, `generac_evo_nexus.json`, `userdefined.json` | `esp32/src/core/ha_definitions.inc` | **Automatic**: regenerate (step 5) |
| `genmonlib/generac_evolution.py` | see function map below | **Port** |
| `genmonlib/mymodbus.py`, `modbusbase.py` | `core/modbus_frame.*`, `esp/modbus_port.*` | Port protocol / timing changes |
| `genmonlib/modbus_evo2.py`, `mycrypto.py` | `core/evo2_unlock.*`, `esp/modbus_port.cpp` | Port unlock changes |
| `genmonlib/controller.py` | `core/outage_tracker.*` (CheckForOutageCommon), `core/report_builder.*` (Display*Common, DisplayOutageHistory) | Port if those functions changed |
| `genmon.py` | `core/report_builder.cpp` (DisplayMonitor, GetStartInfo) | Port report key changes only |
| `addon/genhomeassistant.py` | `core/ha_catalog.*`, `core/ha_values.*`, `core/ha_discovery.*`, `esp/ha_publisher.*` | **Port**: entity compatibility depends on it |
| `addon/genmqtt.py` | `core/mqtt_flatten.*`, `esp/genmqtt_publisher.*` | Port topic / payload changes |
| `conf/genmon.conf`, `conf/genhomeassistant.conf`, `conf/genmqtt.conf` | `esp/settings.*` (field table in `visitFields`) and the web page groups in `esp/web_page.h` | Add options that affect Evolution/Nexus or the two MQTT add-ons |
| `genmonlib/generac_HPanel.py`, `generac_powerzone_pro.py`, `custom_controller.py`, `data/controller/*`, other `data/homeassistant/*.json` | none | Not applicable (controllers the firmware does not support) |
| `genserv.py`, `static/`, `templates/`, other `addon/*`, `OtherApps/`, `*.sh`, `requirements.txt` | none | Not applicable (Raspberry Pi platform) |

Function map for `genmonlib/generac_evolution.py`:

| Python | C++ |
|---|---|
| `BaseRegisters`, `PrimeRegisters`, log constants | `core/register_map.*` |
| `DetectController`, `GetController` | `core/controller_info.*` |
| `GetSwitchState`, `GetEngineState`, `GetAlarmState`, `FilterReg0001`, `Reg0001IsValid`, `ServiceIsDue`, `GetBaseStatus`, `GetLedState` | `core/status_decoder.*` |
| `ParseLogEntry`, `GetAlarmInfo` | `core/log_parser.*`, `core/alarm_codes.*` |
| `GetExerciseTime`, `GetServiceDue`, `GetServiceDueDate`, `GetRunHours`, `GetSerialNumber`, `GetDateTime`, versions | `core/maintenance_decoder.*` |
| `GetCurrentOutput`, `GetPowerOutput`, `GetFrequency`, `GetRPM`, voltages, `GetDigitalOutputs`, `GetSensorInputs`, `DisplayMaintenance` settings | `core/state_builder.*` |
| `DisplayStatus`, `DisplayMaintenance`, `DisplayOutage`, `GetStartInfo` (key names / order) | `core/report_builder.*` |
| `SetGeneratorRemoteCommand`, `WriteIndexedRegister`, `SetGeneratorExerciseTime`, `AltSetGeneratorExerciseTime`, `SetGeneratorQuietMode`, `SetGeneratorTimeDate` | `core/command.*` |
| `MasterEmulation`, `UpdateLogRegistersAsMaster`, `CheckForAlarms` | `esp/generator_service.*` |
| PowerZone 200 branches | not ported (unsupported controller) |

For each file to port, read the upstream diff hunk by hunk
(`git diff "$BASE"..upstream/master -- <file>`), make the equivalent C++ change, and add or
update a test in `esp32/tests/` that pins the new behaviour to the value the Python produces.
Report keys, entity ids and topic strings must stay byte-identical to upstream; that is what
keeps existing Home Assistant entities and MQTT consumers working.

## 5. Regenerate compiled-in upstream data

```bash
python esp32/tools/gen_upstream_data.py
python esp32/tools/gen_upstream_data.py --check   # must exit 0
```

## 6. Verify

Run from `esp32/`:

```bash
pio test -e native
pio run -e esp32dev
```

Both must pass. `pio test -e native` needs a host C++17 compiler (gcc/clang). On Windows
without one, say so in the summary instead of skipping silently. If the build fails with
`CreateProcess: No such file or directory`, the path is too long for Windows; map the
PlatformIO directory to a short drive with `subst` and set `PLATFORMIO_CORE_DIR`.

## 7. Record and hand off

1. Add an entry to `esp32/CHANGELOG.md` under `## [Unreleased]` listing the upstream range
   (`<base>..<upstream sha>`) and what was ported, regenerated, or judged not applicable.
2. Commit the port separately from the merge commit, using Conventional Commits, e.g.
   `feat(esp32): port upstream alarm decoding for Evolution 2.0 code 0x74`.
3. Ask the user before pushing; then `git push -u origin <branch>` and offer to open a pull
   request into the fork's `master`.

Never edit upstream files to make the firmware build; never rewrite published history.
