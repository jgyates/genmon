#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: genhalink.py
# PURPOSE: Native Home Assistant integration backend for genmon.
#          Exposes a REST + WebSocket API that the HA custom component connects to.
#
#  AUTHOR: jgyates
#    DATE: 03-2026
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import json
import os
import re
import secrets
import signal
import sys
import threading
import time
import uuid

try:
    from aiohttp import web
    import aiohttp
    import asyncio
except Exception as e1:
    print(
        "\n\nThis program requires the aiohttp module. "
        "Please use 'sudo pip3 install aiohttp' to install.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)

try:
    file_root = os.path.dirname(os.path.realpath(__file__))
    parent_root = os.path.abspath(os.path.join(file_root, os.pardir))
    if os.path.isdir(os.path.join(parent_root, "genmonlib")):
        sys.path.insert(1, parent_root)

    from genmonlib.myclient import ClientInterface
    from genmonlib.mycommon import MyCommon
    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.myplatform import MyPlatform
    from genmonlib.mysupport import MySupport
    from genmonlib.mythread import MyThread
    from genmonlib.program_defaults import ProgramDefaults

except Exception as e1:
    print(
        "\n\nThis program requires the modules located in the genmonlib directory.\n"
    )
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)

# Optional zeroconf support
try:
    from zeroconf import ServiceInfo, Zeroconf
    import socket
    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False


# -------------------------------------------------------------------------------
class GenHALink(MySupport):
    """REST + WebSocket API server bridging genmon to Home Assistant."""

    def __init__(
        self,
        log=None,
        loglocation=ProgramDefaults.LogPath,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        configfilepath=ProgramDefaults.ConfPath,
        console=None,
    ):
        super(GenHALink, self).__init__()

        self.log = log
        self.console = console
        self.Exiting = False
        self.MonitorAddress = host
        self.MonitorPort = port
        self.ConfigFilePath = configfilepath

        self.AccessLock = threading.Lock()
        self.LastValues = {}
        self.StartInfo = {}
        self.CurrentState = {}
        self.EntityDefinitions = {}
        self.DynamicSensors = {}
        self.WSClients = set()
        self.WSClientsLock = threading.Lock()
        self.ZeroconfInstance = None
        self.ZeroconfInfo = None
        self.LoopThread = None
        self._entities_pruned = False
        self._last_resource_check_time = 0
        self._cached_resource_info = {}
        self._skipped_paths = set()  # paths suppressed as name-duplicates

        self._load_config()
        self._ensure_api_key()

        signal.signal(signal.SIGTERM, self._signal_close)
        signal.signal(signal.SIGINT, self._signal_close)

        try:
            self.Generator = ClientInterface(
                host=self.MonitorAddress, port=self.MonitorPort, log=self.log
            )
            self._get_start_info()
            self._controller_type = self._normalize_controller_type(
                self.StartInfo.get("Controller", "")
            )
            self._load_entity_definitions()

            self.Threads["PollingThread"] = MyThread(
                self._polling_thread, Name="PollingThread", start=False
            )
            self.Threads["PollingThread"].Start()

            self.Threads["ServerThread"] = MyThread(
                self._server_thread, Name="ServerThread", start=False
            )
            self.Threads["ServerThread"].Start()

        except Exception as e1:
            self.LogErrorLine("Error in GenHALink init: " + str(e1))

    # ---------- Configuration --------------------------------------------------
    def _load_config(self):
        try:
            config = MyConfig(
                filename=os.path.join(self.ConfigFilePath, "genhalink.conf"),
                section="genhalink",
                log=self.log,
            )
            self.ServerPort = config.ReadValue("port", return_type=int, default=9083)
            self.ApiKey = config.ReadValue("api_key", return_type=str, default="")
            self.PollTime = config.ReadValue(
                "poll_interval", return_type=float, default=3.0
            )
            self.BlackList = [
                x.strip()
                for x in config.ReadValue(
                    "blacklist", return_type=str, default="Tiles"
                ).split(",")
                if x.strip()
            ]
            self.IncludeMonitorStats = config.ReadValue(
                "include_monitor_stats", return_type=bool, default=True
            )
            self.IncludeWeather = config.ReadValue(
                "include_weather", return_type=bool, default=True
            )
            self.ZeroconfEnabled = config.ReadValue(
                "zeroconf_enabled", return_type=bool, default=True
            )
            self.UseHTTPS = config.ReadValue(
                "use_https", return_type=bool, default=True
            )
            self.debug = config.ReadValue(
                "debug", return_type=bool, default=False
            )
        except Exception as e1:
            self.LogErrorLine("Error in _load_config: " + str(e1))

    def _ensure_api_key(self):
        """Auto-generate API key if empty and write back to config."""
        if self.ApiKey:
            return
        try:
            self.ApiKey = str(uuid.uuid4())
            config_path = os.path.join(self.ConfigFilePath, "genhalink.conf")
            config = MyConfig(
                filename=config_path, section="genhalink", log=self.log
            )
            config.WriteValue("api_key", self.ApiKey)
            self.LogError("Generated new API key for genhalink")
        except Exception as e1:
            self.LogErrorLine("Error generating API key: " + str(e1))

    # ---------- Genmon Communication -------------------------------------------
    def _send_command(self, command):
        try:
            data = self.Generator.ProcessMonitorCommand(command)
            return data
        except Exception as e1:
            self.LogErrorLine("Error in _send_command: " + str(e1))
            return None

    def _get_start_info(self):
        try:
            data = self._send_command("generator: start_info_json")
            if data:
                self.StartInfo = json.loads(data)
        except Exception as e1:
            self.LogErrorLine("Error in _get_start_info: " + str(e1))

    def _load_entity_definitions(self):
        """Load entity definitions from JSON files in data/homeassistant/."""
        try:
            data_dir = os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                os.pardir,
                "data",
                "homeassistant",
            )
            data_dir = os.path.abspath(data_dir)

            # Load base definitions
            base_path = os.path.join(data_dir, "base.json")
            if os.path.isfile(base_path):
                with open(base_path, "r") as f:
                    self.EntityDefinitions = json.load(f)
            else:
                self.EntityDefinitions = {}

            # Load controller-specific overlay
            controller = self.StartInfo.get("Controller", "")
            controller_file = self._get_controller_filename(controller)
            self.LogDebug("Controller detected: '%s', overlay file: %s" % (controller, controller_file))
            if controller_file:
                overlay_path = os.path.join(data_dir, controller_file)
                if os.path.isfile(overlay_path):
                    with open(overlay_path, "r") as f:
                        overlay = json.load(f)
                    self._merge_definitions(overlay)

            # Load user-defined overrides
            user_path = os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                os.pardir,
                "userdefined.json",
            )
            user_path = os.path.abspath(user_path)
            if os.path.isfile(user_path):
                with open(user_path, "r") as f:
                    user_defs = json.load(f)
                self._merge_definitions(user_defs)

            # Inject platform resource entities (memory, disk, WiFi, CPU utilization)
            self._inject_platform_entity_definitions()

            for cat in ["sensors", "binary_sensors", "buttons", "switches", "selects", "numbers"]:
                self.LogDebug("Loaded %d %s definitions" % (len(self.EntityDefinitions.get(cat, [])), cat))

        except Exception as e1:
            self.LogErrorLine("Error in _load_entity_definitions: " + str(e1))

    def _get_controller_filename(self, controller_str):
        """Map controller description to JSON filename."""
        ctrl = controller_str.lower()
        if "evolution" in ctrl or "nexus" in ctrl:
            return "generac_evo_nexus.json"
        elif "h-100" in ctrl or "g-panel" in ctrl:
            return "h_100.json"
        elif "powerzone" in ctrl:
            return "powerzone.json"
        else:
            # Check for custom controller config files.
            # Strip all non-alphanumeric chars so that e.g. "Briggs & Stratton"
            # matches the filename "Briggs_Stratton_GC-1032".
            ctrl_norm = re.sub(r'[^a-z0-9]', '', ctrl)
            for name in [
                "Briggs_Stratton_GC-1032",
                "ComAp",
                "Deepsea_controller",
                "Kohler_APM603",
                "MEBAY_DCxx",
                "Power_Zone_410",
                "SmartGen_HGM4000",
            ]:
                name_norm = re.sub(r'[^a-z0-9]', '', name.lower())
                if name_norm in ctrl_norm:
                    return name + ".json"
            return "custom.json"

    def _inject_platform_entity_definitions(self):
        """Add hardcoded entity definitions for platform resource metrics."""
        platform_sensors = [
            {
                "entity_id": "memory_utilization",
                "name": "Memory Utilization",
                "path": "Monitor/Platform Stats/Memory Utilization",
                "icon": "mdi:memory",
                "unit": "%",
                "state_class": "measurement",
                "category": "diagnostic",
                "enabled_default": True,
                "monitor_stats": True,
                "weather": False,
            },
            {
                "entity_id": "disk_utilization",
                "name": "Disk Utilization",
                "path": "Monitor/Platform Stats/Disk Utilization",
                "icon": "mdi:harddisk",
                "unit": "%",
                "state_class": "measurement",
                "category": "diagnostic",
                "enabled_default": True,
                "monitor_stats": True,
                "weather": False,
            },
            {
                "entity_id": "wlan_signal_level",
                "name": "WiFi Signal Level",
                "path": "Monitor/Platform Stats/WLAN Signal Level",
                "device_class": "signal_strength",
                "unit": "dBm",
                "icon": "mdi:wifi",
                "state_class": "measurement",
                "category": "diagnostic",
                "enabled_default": True,
                "monitor_stats": True,
                "weather": False,
            },
            {
                "entity_id": "wlan_signal_quality",
                "name": "WiFi Signal Quality",
                "path": "Monitor/Platform Stats/WLAN Signal Quality",
                "icon": "mdi:wifi",
                "category": "diagnostic",
                "enabled_default": True,
                "monitor_stats": True,
                "weather": False,
            },
            {
                "entity_id": "wlan_signal_percent",
                "name": "WiFi Signal Percent",
                "path": "Monitor/Platform Stats/WLAN Signal Percent",
                "unit": "%",
                "icon": "mdi:wifi",
                "state_class": "measurement",
                "category": "diagnostic",
                "enabled_default": True,
                "monitor_stats": True,
                "weather": False,
            },
        ]
        if "sensors" not in self.EntityDefinitions:
            self.EntityDefinitions["sensors"] = []
        existing_ids = {e.get("entity_id") for e in self.EntityDefinitions["sensors"]}
        for defn in platform_sensors:
            if defn["entity_id"] not in existing_ids:
                self.EntityDefinitions["sensors"].append(defn)

    def _merge_definitions(self, overlay):
        """Merge overlay entity definitions into base."""
        for category in ["sensors", "binary_sensors", "buttons", "switches", "selects", "numbers"]:
            if category in overlay:
                if category not in self.EntityDefinitions:
                    self.EntityDefinitions[category] = []
                existing_ids = {
                    e.get("entity_id") for e in self.EntityDefinitions.get(category, [])
                }
                for entity in overlay[category]:
                    eid = entity.get("entity_id")
                    if eid and eid in existing_ids:
                        # Replace existing
                        self.EntityDefinitions[category] = [
                            entity if e.get("entity_id") == eid else e
                            for e in self.EntityDefinitions[category]
                        ]
                    else:
                        self.EntityDefinitions[category].append(entity)

    # ---------- Controller Type Helpers ----------------------------------------
    # Standard controller types — used to distinguish known Generac controllers
    # from custom (third-party) controllers when filtering entities.
    _STANDARD_TYPES = {"evolution", "nexus", "h-100", "powerzone"}

    @staticmethod
    def _normalize_controller_type(controller_str):
        """Map a controller description string to a normalized type keyword.

        For standard Generac controllers returns a well-known keyword
        (evolution, nexus, h-100, powerzone).  For custom / third-party
        controllers returns the specific config-file stem so that overlay
        entity definitions with a matching ``controllers`` list are kept.
        """
        ctrl = controller_str.lower()
        if "evolution" in ctrl:
            return "evolution"
        if "nexus" in ctrl:
            return "nexus"
        if "h-100" in ctrl or "g-panel" in ctrl:
            return "h-100"
        if "powerzone" in ctrl:
            return "powerzone"
        # Derive specific type from known custom controller names
        ctrl_norm = re.sub(r'[^a-z0-9]', '', ctrl)
        for name in [
            "Briggs_Stratton_GC-1032",
            "ComAp",
            "Deepsea_controller",
            "Kohler_APM603",
            "MEBAY_DCxx",
            "Power_Zone_410",
            "SmartGen_HGM4000",
        ]:
            name_norm = re.sub(r'[^a-z0-9]', '', name.lower())
            if name_norm in ctrl_norm:
                return name
        return "custom"

    @staticmethod
    def _matches_controller(entity_def, controller_type):
        """Return True if this entity should be included for the given controller type.

        If the entity has no 'controllers' list it is available for all types.
        The keyword ``"custom"`` in a controllers list acts as a wildcard that
        matches any non-standard (third-party) controller type.
        """
        allowed = entity_def.get("controllers")
        if not allowed:
            return True
        if controller_type in allowed:
            return True
        # "custom" matches any controller type that isn't a standard Generac type
        if "custom" in allowed and controller_type not in GenHALink._STANDARD_TYPES:
            return True
        return False

    def _filter_entities_for_controller(self, entities_dict, controller_type, capabilities):
        """Return a filtered copy of entities_dict appropriate for the controller."""
        result = {}
        exercise_ok = capabilities.get("ExerciseControls", False)
        quiet_ok = capabilities.get("WriteQuietMode", False)
        remote_ok = capabilities.get("RemoteCommands", False)
        transfer_ok = capabilities.get("RemoteTransfer", False)
        settime_ok = capabilities.get("SetGenTime", False)

        exercise_entity_ids = {
            "exercise_time", "exercise_frequency", "exercise_day_of_week",
            "exercise_hour", "exercise_minute", "exercise_day_of_month",
        }

        for category in ["sensors", "binary_sensors", "buttons", "switches", "selects", "numbers"]:
            items = entities_dict.get(category, [])
            filtered = []
            for entity in items:
                eid = entity.get("entity_id", "")
                # Filter by controller type
                if not self._matches_controller(entity, controller_type):
                    self.LogDebug("Filtered out '%s' (controllers=%s, detected=%s)" % (
                        eid, entity.get("controllers"), controller_type))
                    continue
                # Filter exercise entities by capability
                if eid in exercise_entity_ids and not exercise_ok:
                    self.LogDebug("Filtered out '%s' (ExerciseControls=False)" % eid)
                    continue
                # Filter quiet mode by capability
                if eid == "quiet_mode" and not quiet_ok:
                    self.LogDebug("Filtered out 'quiet_mode' (WriteQuietMode=False)")
                    continue
                # Filter buttons by capabilities
                if eid in ("start", "stop") and not remote_ok:
                    self.LogDebug("Filtered out '%s' (RemoteCommands=False)" % eid)
                    continue
                if eid == "start_transfer" and not transfer_ok:
                    self.LogDebug("Filtered out 'start_transfer' (RemoteTransfer=False)")
                    continue
                if eid == "start_exercise" and not exercise_ok:
                    self.LogDebug("Filtered out 'start_exercise' (ExerciseControls=False)")
                    continue
                if eid == "set_time" and not settime_ok:
                    self.LogDebug("Filtered out 'set_time' (SetGenTime=False)")
                    continue
                filtered.append(entity)
            result[category] = filtered
        return result

    # ---------- Polling --------------------------------------------------------
    def _polling_thread(self):
        time.sleep(2)  # Let genmon settle
        while True:
            if self.WaitForExit("PollingThread", float(self.PollTime)):
                return
            try:
                self._poll_genmon()
            except Exception as e1:
                self.LogErrorLine("Error in polling thread: " + str(e1))

    def _poll_genmon(self):
        """Poll genmon for all data and detect changes."""
        commands = {
            "Status": "generator: status_num_json",
            "Maintenance": "generator: maint_num_json",
            "Outage": "generator: outage_num_json",
            "Monitor": "generator: monitor_num_json",
        }

        new_state = {}
        for key, cmd in commands.items():
            data = self._send_command(cmd)
            if data:
                try:
                    parsed = json.loads(data)
                    normalized = self._normalize_genmon_data(parsed)
                    # Unwrap top-level key — genmon wraps e.g. status_num_json
                    # in [{"Status": [...]}] so after normalization we get
                    # {"Status": {...}}. Unwrap to avoid double nesting.
                    if isinstance(normalized, dict) and key in normalized:
                        new_state[key] = normalized[key]
                    else:
                        new_state[key] = normalized
                except (json.JSONDecodeError, ValueError):
                    pass

        # GUI status for tiles / base status
        gui_data = self._send_command("generator: gui_status_json")
        if gui_data:
            try:
                new_state["gui_status"] = self._normalize_genmon_data(
                    json.loads(gui_data)
                )
            except (json.JSONDecodeError, ValueError):
                pass

        # Inject defaults for optional fields that genmon omits when inactive
        self._inject_optional_defaults(new_state)

        # Filter excluded data from state
        self._filter_state(new_state)

        # Inject CPU temperature from gui_status indicators into the
        # Tiles path that base.json expects.  This must happen AFTER
        # _filter_state so the blacklist on "Tiles" doesn't remove it.
        self._inject_cpu_temp(new_state)

        # Inject platform resource metrics (memory, disk) on Raspberry Pi
        self._inject_platform_resources(new_state)

        # Discover dynamic sensors
        self._discover_dynamic_sensors(new_state)

        # Remove paths that were suppressed as duplicates so HA never
        # receives a value for them and stale entities become unavailable.
        for _dup_path in self._skipped_paths:
            self._remove_state_path(new_state, _dup_path)

        # Detect changes and notify WebSocket clients
        changes = {}
        flat_new = self._flatten_state(new_state)
        with self.AccessLock:
            for path, value in flat_new.items():
                old_value = self.LastValues.get(path)
                if old_value != value:
                    changes[path] = value
                    self.LastValues[path] = value
            self.CurrentState = new_state

        self.LogDebug("Poll complete: %d paths, %d changes" % (len(flat_new), len(changes)))
        if changes:
            self._notify_ws_clients({"type": "state_update", "state": new_state})

        # After first poll with data, prune entity definitions that have no
        # matching data from the current controller
        if not self._entities_pruned and flat_new:
            self._prune_unsupported_entities(flat_new)
            self._entities_pruned = True

    # Paths that genmon omits entirely when inactive — provide defaults
    OPTIONAL_DEFAULTS = {
        ("Status", "Engine", "System In Alarm"): "",
    }

    def _inject_optional_defaults(self, state):
        """Ensure known optional paths exist with defaults when absent.

        Skipped for custom / third-party controllers whose status hierarchy
        differs from the standard Generac layout — injecting defaults into
        their differently-structured containers would create phantom entities.
        """
        if self._controller_type not in self._STANDARD_TYPES:
            return
        for path_parts, default in self.OPTIONAL_DEFAULTS.items():
            node = state
            for part in path_parts[:-1]:
                if isinstance(node, dict) and part in node:
                    node = node[part]
                else:
                    break
            else:
                # Only inject if the leaf key is missing
                if isinstance(node, dict) and path_parts[-1] not in node:
                    node[path_parts[-1]] = default

    def _filter_state(self, state):
        """Remove blacklisted / excluded data paths from state in-place."""
        try:
            if not self.IncludeWeather:
                self.LogDebug("Filtering weather data from state")
                for section in list(state.keys()):
                    if isinstance(state[section], dict):
                        for key in list(state[section].keys()):
                            if "weather" in key.lower():
                                del state[section][key]
                    if "weather" in section.lower():
                        del state[section]
            if not self.IncludeMonitorStats:
                self.LogDebug("Filtering monitor stats from state")
                state.pop("Monitor", None)
        except Exception as e1:
            self.LogErrorLine("Error in _filter_state: " + str(e1))

    def _inject_cpu_temp(self, state):
        """Extract CPU temperature from gui_status indicators and inject into
        the Tiles/CPU Temp/value path that the base entity definition expects."""
        try:
            gui = state.get("gui_status", {})
            indicators = gui.get("indicators", {})
            cpu_temp = indicators.get("cpuTemp")
            if cpu_temp is not None:
                # indicators.cpuTemp is always Celsius (float)
                temp_str = "%.1f °C" % float(cpu_temp)
                if "Tiles" not in state:
                    state["Tiles"] = {}
                if "CPU Temp" not in state["Tiles"]:
                    state["Tiles"]["CPU Temp"] = {}
                state["Tiles"]["CPU Temp"]["value"] = temp_str
                self.LogDebug("Injected CPU temp: " + temp_str)
        except Exception as e1:
            self.LogErrorLine("Error in _inject_cpu_temp: " + str(e1))

    def _inject_platform_resources(self, state):
        """Inject memory and disk utilization into state (Raspberry Pi only).

        Reads /proc/meminfo and os.statvfs on the Pi. If any call fails the
        metric is silently omitted. Values are cached for 60 seconds.
        """
        try:
            if not MyPlatform.IsOSLinux():
                return
            platform = MyPlatform(log=self.log)
            if not platform.IsPlatformRaspberryPi():
                return

            now = time.time()
            if (now - self._last_resource_check_time) < 60 and self._cached_resource_info:
                resources = self._cached_resource_info
            else:
                resources = {}
                # Memory utilization from /proc/meminfo
                try:
                    with open("/proc/meminfo", "r") as f:
                        meminfo = {}
                        for line in f:
                            parts = line.split(":")
                            if len(parts) == 2:
                                meminfo[parts[0].strip()] = parts[1].strip()
                    mem_total = int(meminfo.get("MemTotal", "0").split()[0])
                    mem_available = int(meminfo.get("MemAvailable", "0").split()[0])
                    if mem_total > 0:
                        mem_pct = round((1 - mem_available / mem_total) * 100, 1)
                        resources["Memory Utilization"] = str(mem_pct) + "%"
                except Exception:
                    pass

                # Disk utilization via os.statvfs
                try:
                    st = os.statvfs("/")
                    total = st.f_blocks * st.f_frsize
                    free = st.f_bavail * st.f_frsize
                    if total > 0:
                        disk_pct = round((1 - free / total) * 100, 1)
                        resources["Disk Utilization"] = str(disk_pct) + "%"
                except Exception:
                    pass

                self._cached_resource_info = resources
                self._last_resource_check_time = now

            if resources:
                monitor = state.setdefault("Monitor", {})
                pstats = monitor.setdefault("Platform Stats", {})
                pstats.update(resources)

            # Compute WiFi signal percent from dBm (same formula as web UI)
            try:
                monitor = state.get("Monitor", {})
                pstats = monitor.get("Platform Stats", {})
                raw_dbm = pstats.get("WLAN Signal Level", "")
                if raw_dbm:
                    dbm = float(str(raw_dbm).replace("dBm", "").strip())
                    pct = max(0, min(100, round((dbm + 90) / 60 * 100)))
                    pstats["WLAN Signal Percent"] = str(pct) + "%"
            except Exception:
                pass
        except Exception:
            pass

    def _prune_unsupported_entities(self, flat_state):
        """Remove entity definitions whose path has no data after the first poll.

        This ensures only entities actually supported by the current controller
        are exposed to Home Assistant.
        """
        try:
            known_paths = set(flat_state.keys())
            for category in ["sensors", "binary_sensors"]:
                original = self.EntityDefinitions.get(category, [])
                kept = []
                for entity in original:
                    path = entity.get("path", "")
                    if not path:
                        kept.append(entity)
                        continue
                    if path in known_paths:
                        kept.append(entity)
                    else:
                        self.LogDebug(
                            "Pruned entity '%s' — path '%s' not in current data"
                            % (entity.get("entity_id", "?"), path)
                        )
                self.EntityDefinitions[category] = kept
        except Exception as e1:
            self.LogErrorLine("Error in _prune_unsupported_entities: " + str(e1))

    def _normalize_genmon_data(self, data):
        """Convert genmon's array-of-single-key-dict format to nested dicts.

        genmon returns data like:
            [{"Status": [{"Engine": [{"Battery Voltage": "13.6 V"}]}]}]
        This converts it to:
            {"Status": {"Engine": {"Battery Voltage": "13.6 V"}}}

        Lists of plain values (e.g. Active Alarms: ["Alarm A", "Alarm B"])
        are joined into a comma-separated string for display.
        """
        if isinstance(data, dict):
            return {k: self._normalize_genmon_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            merged = {}
            for item in data:
                if isinstance(item, dict):
                    for k, v in item.items():
                        merged[k] = self._normalize_genmon_data(v)
                else:
                    # List contains non-dict items — join as display string
                    return ", ".join(str(v) for v in data)
            return merged if merged else data
        return data

    @staticmethod
    def _is_num_json(data):
        """Return True if data is a genmon _num_json structured dict."""
        return isinstance(data, dict) and "value" in data and (
            "type" in data or "unit" in data
        )

    def _flatten_state(self, data, prefix=""):
        """Recursively flatten nested dict/list structure to path:value pairs.

        Genmon _num_json dicts (e.g. {"unit":"V","type":"float","value":13.9})
        are treated as leaf values and stored under the parent path as a
        formatted string like "13.9 V".
        """
        result = {}
        if isinstance(data, dict):
            for key, value in data.items():
                new_prefix = f"{prefix}/{key}" if prefix else key
                if self._is_num_json(value):
                    # Treat as leaf: reconstruct display string
                    val = value.get("value", "")
                    unit = value.get("unit", "")
                    result[new_prefix] = f"{val} {unit}".strip() if unit else val
                elif isinstance(value, (dict, list)):
                    result.update(self._flatten_state(value, new_prefix))
                else:
                    result[new_prefix] = value
        elif isinstance(data, list):
            # Check if this is a list of plain values (e.g. Active Alarms)
            if data and all(not isinstance(item, dict) for item in data):
                if prefix:
                    result[prefix] = ", ".join(str(v) for v in data)
            else:
                for item in data:
                    if isinstance(item, dict):
                        for key, value in item.items():
                            new_prefix = f"{prefix}/{key}" if prefix else key
                            if self._is_num_json(value):
                                val = value.get("value", "")
                                unit = value.get("unit", "")
                                result[new_prefix] = f"{val} {unit}".strip() if unit else val
                            elif isinstance(value, (dict, list)):
                                result.update(self._flatten_state(value, new_prefix))
                            else:
                                result[new_prefix] = value
        return result

    def _discover_dynamic_sensors(self, state_data):
        """Walk the genmon data tree and discover sensors not in predefined definitions."""
        try:
            flat = self._flatten_state(state_data)
            # Also extract units from raw _num_json dicts in the state tree
            num_json_units = self._extract_num_json_units(state_data)

            known_paths = set()
            for category in ["sensors", "binary_sensors"]:
                for entity in self.EntityDefinitions.get(category, []):
                    known_paths.add(entity.get("path", ""))

            # Build set of already-registered leaf names (predefined + dynamic)
            # so that duplicate concepts (e.g. "Utility Voltage" in both
            # Status/Line and Outage) produce only a single HA sensor.
            seen_leaf_names = set()
            for category in ("sensors", "binary_sensors"):
                for entity in self.EntityDefinitions.get(category, []):
                    ename = entity.get("name", "")
                    if ename:
                        seen_leaf_names.add(ename.lower())
            for ds in self.DynamicSensors.values():
                ename = ds.get("name", "")
                if ename:
                    seen_leaf_names.add(ename.lower())

            for path, value in flat.items():
                if any(bl.lower() in path.lower() for bl in self.BlackList):
                    continue
                if path in known_paths:
                    continue
                # gui_status is internal GUI data (tiles, indicators, etc.)
                # already extracted selectively by _inject_cpu_temp et al.
                if path.startswith("gui_status/"):
                    continue
                # Skip indexed collection entries (e.g. Outage Log/0/Date)
                if any(seg.isdigit() for seg in path.split("/")):
                    continue
                if not self.IncludeMonitorStats and path.startswith("Monitor/"):
                    continue
                if not self.IncludeWeather and "Weather" in path:
                    continue

                entity_id = self._path_to_entity_id(path)
                if entity_id not in self.DynamicSensors:
                    name = self._path_to_name(path)
                    # Skip if another sensor already uses this leaf name.
                    # Genmon reports the same value (e.g. "Utility Voltage")
                    # in multiple sections (Status/Line and Outage); we keep
                    # only the first occurrence so HA shows a single entity.
                    if name.lower() in seen_leaf_names:
                        self.LogDebug("Skipping duplicate dynamic sensor: %s (path=%s)" % (name, path))
                        self._skipped_paths.add(path)
                        continue
                    seen_leaf_names.add(name.lower())
                    self.DynamicSensors[entity_id] = {
                        "entity_id": entity_id,
                        "name": name,
                        "path": path,
                        "dynamic": True,
                    }
                    # Infer device_class and unit from value
                    unit = None
                    if isinstance(value, str):
                        unit = self._extract_unit(value)
                    elif isinstance(value, (int, float)):
                        # Value came from a _num_json dict — check if
                        # the raw dict carried a unit
                        unit = num_json_units.get(path)
                        # Even without a unit, mark as numeric measurement
                        if not unit:
                            self.DynamicSensors[entity_id]["state_class"] = "measurement"

                    if unit:
                        # Normalize bare C/F to °C/°F (HA temperature class
                        # rejects unit strings without the degree symbol).
                        if unit == "C":
                            unit = "°C"
                        elif unit == "F":
                            unit = "°F"
                        self.DynamicSensors[entity_id]["unit"] = unit
                        self.DynamicSensors[entity_id]["state_class"] = "measurement"
                        dc = self._unit_to_device_class(unit)
                        if dc:
                            self.DynamicSensors[entity_id]["device_class"] = dc

                    self.LogDebug("Discovered dynamic sensor: %s (path=%s, unit=%s)" % (
                        entity_id, path, self.DynamicSensors[entity_id].get("unit", "none")))
        except Exception as e1:
            self.LogErrorLine("Error in _discover_dynamic_sensors: " + str(e1))

    def _extract_num_json_units(self, data, prefix=""):
        """Walk state tree and extract units from _num_json leaf values."""
        result = {}
        if isinstance(data, dict):
            for key, value in data.items():
                new_prefix = f"{prefix}/{key}" if prefix else key
                if self._is_num_json(value):
                    unit = value.get("unit", "")
                    if unit:
                        result[new_prefix] = unit
                elif isinstance(value, (dict, list)):
                    result.update(self._extract_num_json_units(value, new_prefix))
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    for key, value in item.items():
                        new_prefix = f"{prefix}/{key}" if prefix else key
                        if self._is_num_json(value):
                            unit = value.get("unit", "")
                            if unit:
                                result[new_prefix] = unit
                        elif isinstance(value, (dict, list)):
                            result.update(self._extract_num_json_units(value, new_prefix))
        return result

    def _remove_state_path(self, state, path):
        """Remove a '/'-separated path from the nested state dict in-place."""
        parts = path.split("/")
        node = state
        for part in parts[:-1]:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return
        if isinstance(node, dict):
            node.pop(parts[-1], None)

    def _path_to_entity_id(self, path):
        return re.sub(r"[^a-z0-9]+", "_", path.lower()).strip("_")

    def _path_to_name(self, path):
        parts = path.split("/")
        return parts[-1] if parts else path

    def _extract_unit(self, value_str):
        match = re.search(
            r"[\d.]+\s*(V|A|W|kW|kVA|Hz|°[CF]|dBm|%|RPM|gal|hours|h|C|F)\s*$",
            str(value_str),
        )
        return match.group(1) if match else None

    def _unit_to_device_class(self, unit):
        mapping = {
            "V": "voltage", "A": "current", "W": "power", "kW": "power",
            "kVA": "apparent_power",
            "Hz": "frequency",
            "°C": "temperature", "°F": "temperature",
            "C": "temperature", "F": "temperature",
            "dBm": "signal_strength",
            "%": None, "RPM": None, "gal": None,
        }
        return mapping.get(unit)

    # Default unit per HA device_class when state has not yet supplied one.
    # Required because HA validates device_class/unit at entity registration
    # time. Imperial defaults match genmon's default UseMetric=False.
    _DEFAULT_UNIT_BY_DEVICE_CLASS = {
        "temperature": "°F",
        "voltage": "V",
        "current": "A",
        "power": "kW",
        "apparent_power": "kVA",
        "energy": "kWh",
        "frequency": "Hz",
        "humidity": "%",
        "pressure": "hPa",
        "duration": "s",
        "signal_strength": "dBm",
    }

    def _lookup_path_value(self, path):
        """Walk CurrentState by '/'-separated path. Returns the leaf value
        (which may be a _num_json dict, scalar, or None)."""
        try:
            data = self.CurrentState
            for part in path.split("/"):
                if isinstance(data, dict):
                    data = data.get(part)
                else:
                    return None
                if data is None:
                    return None
            return data
        except Exception:
            return None

    def _resolve_missing_units(self, sensors):
        """For sensor defs that declare a unit-required device_class but no
        unit, try to discover the unit from the current state, otherwise
        apply a sensible default. Mutates the dicts in place."""
        # HA requires the degree symbol for temperature units; genmon often
        # emits plain "C"/"F". Normalize before assigning.
        unit_aliases = {"C": "°C", "F": "°F"}
        try:
            for defn in sensors:
                dc = defn.get("device_class")
                if not dc or dc not in self._DEFAULT_UNIT_BY_DEVICE_CLASS:
                    continue
                if defn.get("unit"):
                    continue
                unit = None
                path = defn.get("path", "")
                if path:
                    leaf = self._lookup_path_value(path)
                    if self._is_num_json(leaf):
                        unit = leaf.get("unit") or None
                    elif isinstance(leaf, str):
                        unit = self._extract_unit(leaf)
                if unit in unit_aliases:
                    unit = unit_aliases[unit]
                if not unit:
                    unit = self._DEFAULT_UNIT_BY_DEVICE_CLASS[dc]
                defn["unit"] = unit
        except Exception as e1:
            self.LogErrorLine("Error in _resolve_missing_units: " + str(e1))

    # ---------- WebSocket Notifications ----------------------------------------
    def _notify_ws_clients(self, message):
        msg_str = json.dumps(message)
        dead = set()
        with self.WSClientsLock:
            for ws in self.WSClients:
                try:
                    asyncio.run_coroutine_threadsafe(
                        ws.send_str(msg_str), self._loop
                    )
                except Exception as e1:
                    self.LogDebug("WebSocket client send failed: " + str(e1))
                    dead.add(ws)
            self.WSClients -= dead

    # ---------- Authentication -------------------------------------------------
    def _check_auth(self, request):
        """Validate Bearer token using timing-safe comparison to prevent
        side-channel attacks that could reveal the API key."""
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            if secrets.compare_digest(token, self.ApiKey):
                return True
        return False

    # ---------- REST Handlers --------------------------------------------------
    async def _handle_health(self, request):
        return web.json_response({"status": "ok", "version": "1.0.0"})

    async def _handle_info(self, request):
        if not self._check_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response(self.StartInfo)

    async def _handle_status(self, request):
        if not self._check_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        with self.AccessLock:
            state = {
                "state": self.CurrentState,
                "values": dict(self.LastValues),
            }
        return web.json_response(state)

    async def _handle_entities(self, request):
        if not self._check_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)

        # Include capabilities from StartInfo
        capabilities = {
            "RemoteCommands": self.StartInfo.get("RemoteCommands", False),
            "ExerciseControls": self.StartInfo.get("ExerciseControls", True),
            "WriteQuietMode": self.StartInfo.get("WriteQuietMode", False),
            "RemoteButtons": self.StartInfo.get("RemoteButtons", False),
            "RemoteTransfer": self.StartInfo.get("RemoteTransfer", False),
            "SetGenTime": self.StartInfo.get("SetGenTime", False),
            "EnhancedExerciseMode": self.StartInfo.get("EnhancedExerciseMode", False),
        }

        controller_str = self.StartInfo.get("Controller", "Unknown")
        controller_type = self._normalize_controller_type(controller_str)

        # Filter entity definitions by controller type and capabilities
        entities = self._filter_entities_for_controller(
            self.EntityDefinitions, controller_type, capabilities
        )

        # Merge dynamic sensors into the sensors list so the HA
        # component creates entities for them (they share the same platform)
        if self.DynamicSensors:
            existing_ids = {e.get("entity_id") for e in entities.get("sensors", [])}
            for ds in self.DynamicSensors.values():
                if ds.get("entity_id") not in existing_ids:
                    entities.setdefault("sensors", []).append(ds)

        # Resolve missing units for sensors that declare a device_class which
        # requires one (HA emits a registration warning otherwise). Tries to
        # discover the unit from current state; falls back to a sensible default.
        self._resolve_missing_units(entities.get("sensors", []))

        entities["capabilities"] = capabilities
        entities["buttons_from_controller"] = self.StartInfo.get("buttons", [])
        entities["controller"] = controller_str
        entities["controller_type"] = controller_type
        entities["model"] = self.StartInfo.get("model", self.StartInfo.get("Model", "Generator"))
        entities["serial"] = self.StartInfo.get("serial", self.StartInfo.get("SerialNumber", ""))
        entities["nominalKW"] = self.StartInfo.get("nominalKW", 0)
        entities["fueltype"] = self.StartInfo.get("fueltype", "Unknown")

        self.LogDebug("Returning entities for controller '%s' (type=%s): %s" % (
            controller_str, controller_type,
            {cat: len(entities.get(cat, [])) for cat in ["sensors", "binary_sensors", "buttons", "switches", "selects", "numbers"]}))

        return web.json_response(entities)

    async def _handle_command(self, request):
        if not self._check_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
            command = body.get("command", "")
            if not command:
                return web.json_response({"error": "missing command"}, status=400)
            response = self._send_command("generator: " + command)
            return web.json_response({"result": response})
        except json.JSONDecodeError:
            return web.json_response({"error": "invalid json"}, status=400)
        except Exception as e1:
            self.LogErrorLine("Error in _handle_command: " + str(e1))
            return web.json_response({"error": "internal error"}, status=500)  # generic; details logged server-side only

    async def _handle_ws(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        # Auth via first message: client must send {"type": "auth", "token": "..."}
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=10)
        except asyncio.TimeoutError:
            await ws.close(code=4001, message=b"auth timeout")
            return ws
        if msg.type != aiohttp.WSMsgType.TEXT:
            await ws.close(code=4001, message=b"auth required")
            return ws
        try:
            auth_data = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError):
            await ws.close(code=4001, message=b"invalid auth")
            return ws
        token = auth_data.get("token", "") if auth_data.get("type") == "auth" else ""
        if not token or not secrets.compare_digest(token, self.ApiKey):
            await ws.send_json({"type": "auth_error", "error": "unauthorized"})
            await ws.close(code=4001, message=b"unauthorized")
            return ws
        await ws.send_json({"type": "auth_ok"})

        with self.WSClientsLock:
            self.WSClients.add(ws)

        try:
            # Send full state on connect
            with self.AccessLock:
                snapshot = {
                    "type": "full_state",
                    "state": self.CurrentState,
                    "values": dict(self.LastValues),
                    "info": self.StartInfo,
                }
            await ws.send_json(snapshot)

            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        if data.get("type") == "command":
                            cmd = data.get("command", "")
                            if cmd:
                                response = self._send_command("generator: " + cmd)
                                await ws.send_json(
                                    {"type": "command_response", "result": response}
                                )
                    except json.JSONDecodeError:
                        pass
                elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                    break
        finally:
            with self.WSClientsLock:
                self.WSClients.discard(ws)

        return ws

    # ---------- TLS certificate -------------------------------------------------
    @staticmethod
    def _get_local_ips():
        """Return a set of all non-loopback IPv4 addresses on this machine."""
        import socket as _sock
        import subprocess

        ips = set()
        try:
            out = subprocess.check_output(
                ["hostname", "-I"], timeout=5, stderr=subprocess.DEVNULL
            ).decode()
            for token in out.split():
                if ":" not in token:
                    ips.add(token.strip())
        except Exception:
            pass
        try:
            hn = _sock.gethostname()
            for info in _sock.getaddrinfo(hn, None):
                addr = info[4][0]
                if addr and not addr.startswith("127.") and ":" not in addr:
                    ips.add(addr)
        except Exception:
            pass
        try:
            s = _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
            s.close()
        except Exception:
            pass
        ips.discard("127.0.0.1")
        return ips

    def _ensure_tls_cert(self):
        """Generate (or reuse) a self-signed TLS certificate for the API server.

        Returns (crt_path, key_path) or None on failure.
        """
        try:
            from OpenSSL import crypto
        except ImportError:
            self.LogError(
                "pyOpenSSL not installed — cannot generate TLS certificate. "
                "Install with: sudo pip3 install pyOpenSSL"
            )
            return None

        import socket as _sock

        key_path = os.path.join(self.ConfigFilePath, "genhalink.key")
        crt_path = os.path.join(self.ConfigFilePath, "genhalink.crt")

        # Check existing cert: reuse if present and IPs still match
        if os.path.isfile(key_path) and os.path.isfile(crt_path):
            try:
                with open(crt_path, "rb") as f:
                    existing = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
                existing_san = ""
                for i in range(existing.get_extension_count()):
                    ext = existing.get_extension(i)
                    if ext.get_short_name() == b"subjectAltName":
                        existing_san = str(ext)
                        break
                missing = False
                for addr in self._get_local_ips():
                    if addr not in existing_san:
                        missing = True
                        break
                if not missing:
                    self.LogError("TLS certificate reused: " + crt_path)
                    return (crt_path, key_path)
                self.LogError(
                    "TLS certificate SAN outdated, regenerating."
                )
            except Exception as e1:
                self.LogErrorLine("Error reading existing TLS cert: " + str(e1))

        # Generate new self-signed cert
        try:
            san_entries = set()
            san_entries.add("DNS:localhost")
            try:
                hn = _sock.gethostname()
                if hn:
                    san_entries.add("DNS:" + hn)
                    san_entries.add("DNS:" + hn + ".local")
                fqdn = _sock.getfqdn()
                if fqdn and fqdn != hn:
                    san_entries.add("DNS:" + fqdn)
            except Exception:
                pass
            for addr in self._get_local_ips():
                san_entries.add("IP:" + addr)
            san_entries.add("IP:127.0.0.1")
            san_string = ", ".join(sorted(san_entries))

            key = crypto.PKey()
            key.generate_key(crypto.TYPE_RSA, 2048)

            cert = crypto.X509()
            cert.set_version(2)
            cert.set_serial_number(int.from_bytes(os.urandom(16), "big"))
            cert.gmtime_adj_notBefore(0)
            cert.gmtime_adj_notAfter(10 * 365 * 24 * 60 * 60)  # 10 years

            subj = cert.get_subject()
            subj.CN = _sock.gethostname() if _sock.gethostname() else "genhalink"
            subj.O = "Genmon"
            cert.set_issuer(subj)
            cert.set_pubkey(key)

            cert.add_extensions([
                crypto.X509Extension(b"basicConstraints", False, b"CA:FALSE"),
                crypto.X509Extension(
                    b"keyUsage", True, b"digitalSignature, keyEncipherment"
                ),
                crypto.X509Extension(
                    b"extendedKeyUsage", False, b"serverAuth"
                ),
                crypto.X509Extension(
                    b"subjectAltName", False, san_string.encode("ascii")
                ),
            ])
            cert.sign(key, "sha256")

            with open(key_path, "wb") as f:
                f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, key))
            try:
                os.chmod(key_path, 0o600)
            except Exception:
                pass
            with open(crt_path, "wb") as f:
                f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))

            self.LogError(
                "Generated TLS certificate: " + crt_path + " SAN=" + san_string
            )
            return (crt_path, key_path)
        except Exception as e1:
            self.LogErrorLine("Error generating TLS certificate: " + str(e1))
            return None

    # ---------- HTTP Server ----------------------------------------------------
    def _server_thread(self):
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            app = web.Application()
            app.router.add_get("/api/health", self._handle_health)
            app.router.add_get("/api/info", self._handle_info)
            app.router.add_get("/api/status", self._handle_status)
            app.router.add_get("/api/entities", self._handle_entities)
            app.router.add_post("/api/command", self._handle_command)
            app.router.add_get("/ws", self._handle_ws)

            runner = web.AppRunner(app)
            self._loop.run_until_complete(runner.setup())

            ssl_ctx = None
            self.IsHTTPS = False
            if self.UseHTTPS:
                cert_paths = self._ensure_tls_cert()
                if cert_paths:
                    import ssl
                    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                    ssl_ctx.load_cert_chain(cert_paths[0], cert_paths[1])
                    self.IsHTTPS = True
                else:
                    self.LogError(
                        "TLS cert generation failed — falling back to plain HTTP"
                    )

            site = web.TCPSite(runner, "0.0.0.0", self.ServerPort, ssl_context=ssl_ctx)
            self._loop.run_until_complete(site.start())

            scheme = "HTTPS" if self.IsHTTPS else "HTTP"
            self.LogError(
                "GenHALink API server started on port "
                + str(self.ServerPort) + " (" + scheme + ")"
            )

            # Start zeroconf after server is up
            self._start_zeroconf()

            # Run until exit
            while not self.Exiting:
                self._loop.run_until_complete(asyncio.sleep(0.5))

            self._stop_zeroconf()
            self._loop.run_until_complete(runner.cleanup())
            self._loop.close()

        except Exception as e1:
            self.LogErrorLine("Error in _server_thread: " + str(e1))

    # ---------- Zeroconf -------------------------------------------------------
    def _start_zeroconf(self):
        if not self.ZeroconfEnabled:
            return
        if not ZEROCONF_AVAILABLE:
            self.LogError(
                "Zeroconf Python package not available in this environment. "
                "Install with: sudo pip3 install zeroconf "
                "(the system apt package python3-zeroconf may not be "
                "accessible if genmon runs in a virtualenv)"
            )
            return
        try:
            local_ip = self._get_local_ip()
            properties = {
                "api_version": "1",
                "https": "1" if getattr(self, "IsHTTPS", False) else "0",
                "serial": str(
                    self.StartInfo.get(
                        "serial", self.StartInfo.get("SerialNumber", "unknown")
                    )
                ),
                "model": str(
                    self.StartInfo.get(
                        "model", self.StartInfo.get("Model", "Generator")
                    )
                ),
            }
            hostname = socket.gethostname()
            self.ZeroconfInfo = ServiceInfo(
                "_genmon._tcp.local.",
                f"Genmon Generator ({hostname})._genmon._tcp.local.",
                addresses=[socket.inet_aton(local_ip)],
                port=self.ServerPort,
                properties=properties,
                server=f"{hostname}.local.",
            )
            self.ZeroconfInstance = Zeroconf()
            self.ZeroconfInstance.register_service(self.ZeroconfInfo)
            self.LogError(
                f"Zeroconf: broadcasting _genmon._tcp on {local_ip}:{self.ServerPort}"
            )
        except Exception as e1:
            self.LogErrorLine("Error starting zeroconf: " + str(e1))

    def _stop_zeroconf(self):
        try:
            if self.ZeroconfInstance and self.ZeroconfInfo:
                self.ZeroconfInstance.unregister_service(self.ZeroconfInfo)
                self.ZeroconfInstance.close()
                self.LogError("Zeroconf: service unregistered")
        except Exception as e1:
            self.LogErrorLine("Error stopping zeroconf: " + str(e1))

    def _get_local_ip(self):
        """Get the local IP address used for network communication."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e1:
            self.LogDebug("Failed to get local IP: " + str(e1))
            return "127.0.0.1"

    # ---------- Shutdown -------------------------------------------------------
    def _signal_close(self, signum, frame):
        self.Close()
        sys.exit(0)

    def Close(self):
        self.LogError("GenHALink shutting down")
        self.Exiting = True
        try:
            self.KillThread("PollingThread")
        except Exception as e1:
            self.LogDebug("Error killing polling thread: " + str(e1))
        try:
            if self.Generator:
                self.Generator.Close()
        except Exception as e1:
            self.LogDebug("Error closing generator client: " + str(e1))


# -------------------------------------------------------------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("genhalink")

    Instance = GenHALink(
        host=address,
        port=port,
        log=log,
        loglocation=loglocation,
        configfilepath=ConfigFilePath,
        console=console,
    )

    while not Instance.Exiting:
        time.sleep(0.5)

    sys.exit(0)
