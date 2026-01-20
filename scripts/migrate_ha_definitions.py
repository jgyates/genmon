#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: migrate_ha_definitions.py
# PURPOSE: Export Home Assistant entity definitions from genhomeassistant.py to JSON
#
#  AUTHOR: Claude AI (Anthropic)
#    DATE: 2025
#
# This is a one-time migration script. After running, the JSON files will be the
# source of truth and this script can be removed.
#
# USAGE: python3 scripts/migrate_ha_definitions.py
# -------------------------------------------------------------------------------

import json
import os
import sys

# Add parent directory to path for addon imports
script_dir = os.path.dirname(os.path.realpath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, os.pardir))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "addon"))

# Import the current definitions from genhomeassistant
from genhomeassistant import (
    SENSOR_DEFINITIONS,
    BINARY_SENSOR_DEFINITIONS,
    BUTTON_DEFINITIONS,
    SWITCH_DEFINITIONS,
    SELECT_DEFINITIONS,
    NUMBER_DEFINITIONS,
)


def convert_sensor_to_json_format(entity_id, entity_def):
    """Convert a sensor definition dict to JSON schema format."""
    return {
        "entity_id": entity_id,
        "name": entity_def.get("name", entity_id),
        "path": entity_def.get("path", ""),
        "device_class": entity_def.get("device_class"),
        "unit": entity_def.get("unit"),
        "icon": entity_def.get("icon"),
        "state_class": entity_def.get("state_class"),
        "category": entity_def.get("category"),
        "enabled_default": entity_def.get("enabled_default", True),
        "controllers": entity_def.get("controllers"),
        "monitor_stats": entity_def.get("monitor_stats", False),
        "weather": entity_def.get("weather", False),
    }


def convert_binary_sensor_to_json_format(entity_id, entity_def):
    """Convert a binary sensor definition dict to JSON schema format."""
    return {
        "entity_id": entity_id,
        "name": entity_def.get("name", entity_id),
        "path": entity_def.get("path", ""),
        "device_class": entity_def.get("device_class"),
        "payload_on": entity_def.get("payload_on"),
        "payload_off": entity_def.get("payload_off"),
        "payload_on_not_empty": entity_def.get("payload_on_not_empty"),
        "payload_off_invert": entity_def.get("payload_off_invert"),
        "icon": entity_def.get("icon"),
        "category": entity_def.get("category"),
        "controllers": entity_def.get("controllers"),
    }


def convert_button_to_json_format(entity_id, entity_def):
    """Convert a button definition dict to JSON schema format."""
    return {
        "entity_id": entity_id,
        "name": entity_def.get("name", entity_id),
        "command": entity_def.get("command", ""),
        "icon": entity_def.get("icon"),
        "controllers": entity_def.get("controllers"),
    }


def convert_switch_to_json_format(entity_id, entity_def):
    """Convert a switch definition dict to JSON schema format."""
    return {
        "entity_id": entity_id,
        "name": entity_def.get("name", entity_id),
        "command_on": entity_def.get("command_on", ""),
        "command_off": entity_def.get("command_off", ""),
        "icon": entity_def.get("icon"),
        "state_path": entity_def.get("state_path"),
        "payload_on": entity_def.get("payload_on"),
        "payload_off": entity_def.get("payload_off"),
        "controllers": entity_def.get("controllers"),
    }


def convert_select_to_json_format(entity_id, entity_def):
    """Convert a select definition dict to JSON schema format."""
    return {
        "entity_id": entity_id,
        "name": entity_def.get("name", entity_id),
        "icon": entity_def.get("icon"),
        "options": entity_def.get("options", []),
        "command_template": entity_def.get("command_template"),
    }


def convert_number_to_json_format(entity_id, entity_def):
    """Convert a number definition dict to JSON schema format."""
    return {
        "entity_id": entity_id,
        "name": entity_def.get("name", entity_id),
        "icon": entity_def.get("icon"),
        "min": entity_def.get("min"),
        "max": entity_def.get("max"),
        "step": entity_def.get("step", 1),
        "unit": entity_def.get("unit"),
        "command_template": entity_def.get("command_template"),
    }


def clean_none_values(obj):
    """Remove None values from a dictionary to keep JSON clean."""
    if isinstance(obj, dict):
        return {k: clean_none_values(v) for k, v in obj.items() if v is not None}
    elif isinstance(obj, list):
        return [clean_none_values(i) for i in obj]
    return obj


def main():
    output_dir = os.path.join(project_root, "data", "homeassistant")
    os.makedirs(output_dir, exist_ok=True)

    # Convert all definitions to JSON format
    sensors = []
    for entity_id, entity_def in SENSOR_DEFINITIONS.items():
        sensors.append(convert_sensor_to_json_format(entity_id, entity_def))

    binary_sensors = []
    for entity_id, entity_def in BINARY_SENSOR_DEFINITIONS.items():
        binary_sensors.append(convert_binary_sensor_to_json_format(entity_id, entity_def))

    buttons = []
    for entity_id, entity_def in BUTTON_DEFINITIONS.items():
        buttons.append(convert_button_to_json_format(entity_id, entity_def))

    switches = []
    for entity_id, entity_def in SWITCH_DEFINITIONS.items():
        switches.append(convert_switch_to_json_format(entity_id, entity_def))

    selects = []
    for entity_id, entity_def in SELECT_DEFINITIONS.items():
        selects.append(convert_select_to_json_format(entity_id, entity_def))

    numbers = []
    for entity_id, entity_def in NUMBER_DEFINITIONS.items():
        numbers.append(convert_number_to_json_format(entity_id, entity_def))

    # Create the base.json file with all definitions
    base_config = {
        "controller_type": "base",
        "version": "1.0",
        "description": "Base Home Assistant entity definitions for all controller types",
        "sensors": [clean_none_values(s) for s in sensors],
        "binary_sensors": [clean_none_values(bs) for bs in binary_sensors],
        "buttons": [clean_none_values(b) for b in buttons],
        "switches": [clean_none_values(sw) for sw in switches],
        "selects": [clean_none_values(s) for s in selects],
        "numbers": [clean_none_values(n) for n in numbers],
    }

    base_file = os.path.join(output_dir, "base.json")
    with open(base_file, "w") as f:
        json.dump(base_config, f, indent=2)
    print(f"Created: {base_file}")
    print(f"  - {len(sensors)} sensors")
    print(f"  - {len(binary_sensors)} binary_sensors")
    print(f"  - {len(buttons)} buttons")
    print(f"  - {len(switches)} switches")
    print(f"  - {len(selects)} selects")
    print(f"  - {len(numbers)} numbers")

    # Create empty controller-specific files
    controller_configs = {
        "generac_evo_nexus.json": {
            "controller_type": "evolution",
            "version": "1.0",
            "description": "Evolution/Nexus controller-specific entity definitions (extends base)",
            "sensors": [],
            "binary_sensors": [],
            "buttons": [],
            "switches": [],
            "selects": [],
            "numbers": [],
        },
        "h_100.json": {
            "controller_type": "h-100",
            "version": "1.0",
            "description": "H-100/G-Panel controller-specific entity definitions (extends base)",
            "sensors": [],
            "binary_sensors": [],
            "buttons": [],
            "switches": [],
            "selects": [],
            "numbers": [],
        },
        "powerzone.json": {
            "controller_type": "powerzone",
            "version": "1.0",
            "description": "PowerZone controller-specific entity definitions (extends base)",
            "sensors": [],
            "binary_sensors": [],
            "buttons": [],
            "switches": [],
            "selects": [],
            "numbers": [],
        },
        "custom.json": {
            "controller_type": "custom",
            "version": "1.0",
            "description": "Custom controller-specific entity definitions (extends base)",
            "sensors": [],
            "binary_sensors": [],
            "buttons": [],
            "switches": [],
            "selects": [],
            "numbers": [],
        },
    }

    for filename, config in controller_configs.items():
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w") as f:
            json.dump(config, f, indent=2)
        print(f"Created: {filepath}")

    print("\nMigration complete!")
    print("JSON files created in data/homeassistant/")
    print("\nNext steps:")
    print("1. Update genhomeassistant.py to load definitions from JSON")
    print("2. Test the addon to verify entities are discovered correctly")
    print("3. This migration script can be deleted after verification")


if __name__ == "__main__":
    main()
