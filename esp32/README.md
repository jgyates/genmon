# genmon-esp32

Monitor a Generac Evolution or Nexus generator with nothing but an **ESP32-WROOM-32D DevKitC**,
an RS-232 level shifter and a 12 V → 5 V converter. This is a C++ port of the
[genmon](https://github.com/jgyates/genmon) Raspberry Pi project's core: it speaks the same
Modbus protocol to the controller, decodes the same registers, and publishes the same JSON
reports, Home Assistant entities and MQTT topics. Existing Home Assistant dashboards and
MQTT consumers carry over unchanged.

The upstream Python project stays, unmodified, in the repository root; this firmware lives
entirely in `esp32/`. See [Keeping up with upstream](#keeping-up-with-upstream).

## Contents

- [What it does](#what-it-does)
- [Supported controllers](#supported-controllers)
- [Hardware](#hardware)
- [Wiring](#wiring)
- [Build and flash](#build-and-flash)
- [First-time setup](#first-time-setup)
- [Moving from genmon on a Raspberry Pi](#moving-from-genmon-on-a-raspberry-pi)
- [Home Assistant and MQTT](#home-assistant-and-mqtt)
- [HTTP API](#http-api)
- [Security notes](#security-notes)
- [Development](#development)
- [Keeping up with upstream](#keeping-up-with-upstream)
- [Differences from genmon](#differences-from-genmon)

## What it does

- Polls the controller over Modbus RTU (9600 8N1, address `0x9D`) using genmon's register
  map and polling pattern, including the Evolution 2.0 encrypted "unlock" handshake.
- Decodes switch and engine state, alarms (with the full `ALARMS.txt` code table),
  battery, RPM, frequency, voltages, current and power (Evolution), transfer switch and
  relay/sensor state (Evolution liquid cooled), service schedules, exercise schedule,
  run hours, and the alarm, service and run logs.
- Detects utility outages using the controller's own threshold / pickup voltages and keeps
  an outage history in flash, in genmon's `outage.txt` format.
- Serves a web UI and genmon-compatible JSON at `/cmd/status_json` and friends.
- Sends remote commands: start, stop, start-and-transfer, exercise, panel buttons
  (Auto/Manual/Off), alarm reset, quiet mode, exercise schedule and controller clock.
- Publishes to Home Assistant via MQTT discovery exactly as upstream's `genhomeassistant`
  add-on, and/or plain per-value topics exactly as upstream's `genmqtt` add-on.
- Over-the-air firmware updates from the web page.

## Supported controllers

| Product code | Controller | Status |
|---|---|---|
| 0x03-0x05 | Nexus, air cooled | Supported |
| 0x06-0x08 | Nexus, liquid cooled | Supported |
| 0x09, 0x0B | Evolution, air cooled | Supported |
| 0x0A | Synergy Evolution | Supported |
| 0x0C | Evolution, liquid cooled | Supported |
| 0x12-0x14 | Power Pact Evolution | Supported |
| 0x15 | Evolution 2.0, air cooled | Supported (including the unlock handshake) |
| 0x16 | Evolution 4.5L, liquid cooled | Supported |
| 0x02 | Pre-Nexus | Status only; its older log format is not decoded |
| 0x19 | Power Zone 200 | Not supported (115200 baud, separate register set) |

H-100 / G-Panel, PowerZone Pro and the "custom" controllers genmon supports over RS-485 or
Modbus TCP are out of scope. Unvalidated product codes are guessed the same way genmon
guesses them, and the event log says so.

## Hardware

| Part | Notes |
|---|---|
| ESP32-WROOM-32D DevKitC | Any ESP32 DevKitC works; the 32D is what this was written for |
| MAX3232 RS-232 ↔ TTL module | Must be **MAX3232** (3.3 V capable), not MAX232 (5 V only) |
| 12 V → 5 V buck converter, ≥ 1 A | Powers the ESP32 from the generator's starting battery |
| Cable to the controller's serial port | The same cable used for a genmon Raspberry Pi install |
| Enclosure, preferably with an external antenna | The generator housing is a metal box |

The controller's serial port uses **RS-232 voltages (up to ±12 V)**. Never connect it
directly to ESP32 pins; the level shifter is mandatory.

## Wiring

This is the same circuit as genmon's
[`Diagrams/wiring_schematic.png`](../Diagrams/wiring_schematic.png), with the ESP32 in place
of the Raspberry Pi. Connector pin numbering is in [`Diagrams/Molex_Pinout.png`](../Diagrams/Molex_Pinout.png);
see genmon's wiki for where the port is on your controller.

```
 Generator controller            MAX3232 module                ESP32 DevKitC
 8-pin serial port               RS-232 side | TTL side
 ─────────────────               ──────────────────────        ─────────────
 pin 8  (controller TX) ───────► RX           |  TX  ◄──────── GPIO17 (TX2)
 pin 7  (controller RX) ◄─────── TX           |  RX  ────────► GPIO16 (RX2)
                                              |  VCC ◄──────── 3V3
                                              |  GND ───────┬─ GND
                                                            │
 Generator 12 V battery (+) ──► buck IN+   buck OUT+ 5 V ───┼─► 5V pin
 Generator 12 V battery (−) ──► buck IN−   buck OUT− ───────┴─► GND
```

- RS-232 is crossed (controller TX → module RX), exactly as in genmon's diagram. TTL pin
  labels vary between modules: if the monitor reports "Not receiving data", swap the two
  TTL wires at the ESP32. Both swaps are harmless.
- All grounds (battery negative, buck output, MAX3232, ESP32) must be common.
- GPIO 16/17 are the defaults; any other usable pins can be set in Settings → Controller.
- Don't power the DevKitC from USB and the 5V pin at the same time unless your board has a
  protection diode on 5V. Unplug the buck converter while flashing over USB.
- Factory reset (for example after a lost admin password): press **EN** (reset), release it,
  then within 3 seconds press and hold **BOOT** for 5 seconds. (Holding BOOT *while*
  pressing EN starts the ESP32's flash loader instead, which is harmless; just reset again.)

## Build and flash

Install [PlatformIO](https://platformio.org/) (VS Code extension or `pip install platformio`), then from `esp32/`:

```bash
pio run -e esp32dev -t upload
```

```bash
pio device monitor
```

The serial console (115200 baud) logs detection, events and the device's address.
Later updates can be installed from the web page (Control → Firmware) using
`esp32/.pio/build/esp32dev/firmware.bin`.

## First-time setup

1. Power the ESP32. With no Wi-Fi configured it opens an access point named
   `genmon-setup-XXXX`, password `genmon-setup`.
2. Join it and browse to `http://192.168.4.1/`.
3. Under **Settings**, set at least `wifi_ssid`, `wifi_password`, `admin_password`,
   `timezone` (a [POSIX TZ string](https://github.com/nayarsystems/posix_tz_db/blob/master/zones.csv)),
   `sitename` and, for current and power readings on Evolution, `nominalkw`. Then
   **Save and restart**.
4. The monitor joins your network as `http://genmon.local/` (or its DHCP address, printed on
   the serial console). If it cannot reach the network within 30 s, the setup access
   point comes back so you can fix the settings.

Until an admin password is set, settings and commands can only be changed from the setup
access point. After that, they need HTTP basic auth as user `admin`.

## Moving from genmon on a Raspberry Pi

Setting names match the upstream `.conf` files, so values can be copied across:

| Upstream file | Option(s) | ESP32 setting group |
|---|---|---|
| `genmon.conf` | `sitename`, `address`, `nominallinevolts`, `evolutioncontroller`, `liquidcooled`, `enhancedexercise`, `uselegacysetexercise`, `currentdivider`, `currentoffset`, `additionalrunhours`, `serialnumberifmissing`, `disableoutagecheck`, `synctime` | Generator / Controller |
| `genmon.conf` (written by genmon) | `model`, `fueltype`, `nominalkw`, `nominalrpm`, `nominalfrequency` | Generator. genmon looked these up from Generac's website; enter them by hand |
| `genhomeassistant.conf` | `mqtt_address`, `mqtt_port`, `username`, `password`, `client_id`, `discovery_prefix`, `base_topic`, `device_id`, `device_name`, `blacklist`, `include_monitor_stats`, `poll_interval`, `discovery_interval` | MQTT broker / Home Assistant |
| `genmqtt.conf` | `root_topic`, `numeric_json`, `retain`, `remove_spaces`, `blacklist` (→ `genmqtt_blacklist`), `poll_interval` (→ `genmqtt_poll_interval`) | Plain MQTT topics |

To keep the same Home Assistant device and entities, use the **same `device_id`,
`base_topic` and `discovery_prefix`** as the Pi, then shut the Pi's genmon down before the
ESP32 connects. Dynamically discovered entities the ESP32 no longer reports (for example
the Pi's "Platform Stats" sensors) are removed from Home Assistant automatically, as upstream
does when its entity list changes. Predefined entities with no ESP32 data (CPU usage,
weather, fuel-tank estimates) keep their last value; delete them in Home Assistant if you
don't want them. Outage history can be carried over by placing the Pi's
`outage.txt` lines in `/outage.txt` on the ESP32 file system (`pio run -t uploadfs` from a `data/` folder).

## Home Assistant and MQTT

Both publishers share one broker connection and can run together.

**Home Assistant discovery** (`ha_enabled`, default on) is a port of upstream's
`addon/genhomeassistant.py`:

- Entities are defined by upstream's `data/homeassistant/base.json` and
  `generac_evo_nexus.json` (plus `userdefined.json` if present), compiled in.
- Discovery: `<discovery_prefix>/<kind>/<device_id>/<entity_id>/config`;
  state: `<base_topic>/<kind>/<entity_id>/state`; availability: `<base_topic>/status`.
- Unique ids are `genmon_<device_id>_<entity_id>`; dynamic sensors use upstream's
  path-derived ids (for example `status_engine_battery_charger_current`).
- Buttons, the quiet-mode switch and the exercise selects/numbers send the same genmon
  commands.

**Plain topics** (`genmqtt_enabled`, default off) is a port of upstream's `addon/genmqtt.py`:
every report value on `[root_topic/]generator/<Section>/<...>/<Name>`, published on change,
and commands accepted on `[root_topic/]generator/command` (for example `setremote=start`).
Set `genmqtt_allow_commands` to false to make it read-only.

MQTT allows one last-will message per connection, so it goes to the Home Assistant
availability topic when that publisher is on, otherwise to `generator/client_status`.

## HTTP API

| Method | Path | Notes |
|---|---|---|
| GET | `/` | Web UI |
| GET | `/cmd/status_json`, `/cmd/status_num_json` | Same structure as genmon; also `maint_`, `outage_`, `monitor_`, `logs_` and `start_info_json` |
| GET | `/api/registers` | Raw register cache (`{"Registers": {"0001": "00030000", ...}}`) |
| GET | `/api/events` | Recent monitor events (state changes, alarms, outages, comms) |
| GET | `/api/info` | Network, MQTT and firmware summary |
| GET / POST | `/api/settings` | Read / update settings (JSON); saving restarts the device. **Auth** |
| POST | `/api/command` | Body is a genmon command: `setremote=start`, `setexercise=Saturday,13:30,weekly`, `setquiet=on`, `settime`. **Auth** |
| POST | `/api/update` | Multipart `firmware.bin` upload. **Auth** |
| POST | `/api/reboot` | **Auth** |

## Security notes

- Remote start, stop and transfer commands start a real engine. Use a strong admin password,
  keep the monitor on a trusted network, and secure your MQTT broker. Anyone who can publish
  to the command topics can run those commands, just as with upstream's add-ons.
- HTTP is unencrypted; credentials cross the network in clear text. Don't expose the
  device to the internet; use a VPN for remote access.
- The setup access point password is fixed and published here. It only opens while
  no Wi-Fi is configured or the configured network is unreachable.

## Development

```
esp32/
├── platformio.ini            esp32dev firmware + native test environments
├── src/
│   ├── main.cpp              wiring of the services (entry point)
│   ├── core/                 portable logic, no Arduino dependencies, unit tested
│   │   ├── modbus_frame.*        RTU framing and CRC
│   │   ├── evo2_unlock.*         Evolution 2.0 unlock payloads
│   │   ├── register_map.*        register addresses and polling lists
│   │   ├── controller_info.*     product-code detection
│   │   ├── status_decoder.*      switch / engine / alarm / base status
│   │   ├── maintenance_decoder.* clock, exercise, service, versions, run hours
│   │   ├── log_parser.*          alarm / service / run logs
│   │   ├── state_builder.*       registers → GeneratorState
│   │   ├── outage_tracker.*      outage detection and voltage statistics
│   │   ├── command.*             command parsing and register-write planning
│   │   ├── report_builder.*      genmon-format JSON reports
│   │   ├── ha_catalog.* ha_values.* ha_discovery.*   genhomeassistant port
│   │   ├── mqtt_flatten.*        genmqtt port
│   │   └── *.inc                 generated from upstream data files (do not edit)
│   └── esp/                  ESP32 services: UART, NVS settings, Wi-Fi, web, MQTT
├── tests/                    Unity tests for src/core (pio test -e native)
└── tools/gen_upstream_data.py  regenerates the *.inc files from ../data/
```

- Run the tests with `pio test -e native` (needs a host gcc or clang with C++17).
- C++ follows the [Google C++ Style Guide](https://google.github.io/styleguide/cppguide.html)
  naming, with the repository's coding standards on top: aligned columns, section banners,
  comments that explain *why*. `.clang-format` is configured to preserve alignment.
- On Windows, a `CreateProcess: No such file or directory` build error means a path is
  over 260 characters. Move or `subst` the PlatformIO directory to a short path.

## Keeping up with upstream

The fork never edits upstream's files, so `git merge upstream/master` doesn't conflict.
After merging:

1. `python esp32/tools/gen_upstream_data.py` picks up new alarm codes and Home Assistant
   entity definitions automatically (`--check` verifies nothing is stale).
2. Changes to `genmonlib/generac_evolution.py`, the Modbus modules, or the
   `genhomeassistant` / `genmqtt` add-ons are ported by hand. The mapping from each Python
   function to its C++ counterpart is in `.claude/skills/sync-upstream/SKILL.md`.

With Claude Code, ask to "sync upstream" (or run `/sync-upstream`) and it follows that
procedure: fetch, merge, classify every changed file, regenerate, port, test, and record
the result in `esp32/CHANGELOG.md`.

## Differences from genmon

- No email/SMS notifications, weather, fuel-tank estimates, power-log history or Generac
  serial-number lookup; Home Assistant or another MQTT consumer can cover these.
- The Home Assistant "Software Update" entity reports the firmware version; updates are
  installed from the web page, not from Home Assistant.
- With numeric JSON, upstream's `transfer_to_generator` binary sensor compares the text form
  of the `{unit, type, value}` object and therefore never turns on; the ESP32 compares the
  number inside, so it reports correctly. Entity ids and topics are unchanged.

## License

GPL-2.0, the same as genmon (see [`../LICENSE`](../LICENSE)). Register decoding, alarm data
and integration behaviour come from genmon by Jason G. Yates and contributors.
