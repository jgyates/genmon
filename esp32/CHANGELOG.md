# Changelog

All notable changes to genmon-esp32 are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- ESP32-WROOM-32D firmware port of genmon for Generac Evolution and Nexus controllers:
  Modbus RTU polling (including the Evolution 2.0 unlock handshake), status/alarm/log/
  maintenance decoding, outage tracking, remote commands, web UI, OTA updates.
- genmon-compatible JSON reports at `/cmd/<report>`.
- Home Assistant MQTT discovery publisher compatible with upstream `genhomeassistant`
  (same topics, unique ids and entity definitions).
- Plain-topic MQTT publisher compatible with upstream `genmqtt`.
- `tools/gen_upstream_data.py` to compile upstream `data/ALARMS.txt` and
  `data/homeassistant/*.json` into the firmware.
- `sync-upstream` Claude Code skill for merging and porting upstream changes.

### Upstream baseline

- Ported from jgyates/genmon at `894ab5e` (genmon 2.0.03).
