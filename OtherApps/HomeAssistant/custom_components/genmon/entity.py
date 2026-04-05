"""Base entity for Genmon Generator Monitor."""
from __future__ import annotations

import re
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, PATH_SEP, UNIT_STRIP_PATTERNS
from .coordinator import GenmonCoordinator


def should_add_entity(defn: dict, controller_type: str | None, capabilities: dict | None = None) -> bool:
    """Return True if an entity definition is appropriate for the active controller.

    Mirrors the server-side filtering done in genhalink so that any entity
    definitions still present in the payload are double-checked on the HA side.
    """
    # Controller filter
    allowed = defn.get("controllers")
    if allowed and controller_type and controller_type not in allowed:
        return False
    # Capability filter
    if capabilities:
        eid = defn.get("entity_id", "")
        exercise_ids = {
            "exercise_time", "exercise_frequency", "exercise_day_of_week",
            "exercise_hour", "exercise_minute", "exercise_day_of_month",
        }
        if eid in exercise_ids and not capabilities.get("ExerciseControls", False):
            return False
        if eid == "quiet_mode" and not capabilities.get("WriteQuietMode", False):
            return False
    return True


class GenmonEntity(CoordinatorEntity[GenmonCoordinator]):
    """Base class for all Genmon entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GenmonCoordinator,
        entity_key: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._entity_key = entity_key
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{entity_key}"

    @property
    def device_info(self) -> DeviceInfo:
        info = self.coordinator.info
        serial = info.get("serial", info.get("SerialNumber"))
        model = info.get("model", info.get("Model", "Generator"))
        controller = info.get("controller", info.get("Controller", ""))
        fw = info.get("firmware", info.get("FirmwareVersion"))

        identifiers = {(DOMAIN, self.coordinator.config_entry.entry_id)}
        if serial:
            identifiers.add((DOMAIN, str(serial)))

        return DeviceInfo(
            identifiers=identifiers,
            name=model if model else "Genmon Generator",
            manufacturer="Generac",
            model=controller if controller else model,
            sw_version=fw,
            configuration_url=(
                f"http://{self.coordinator.config_entry.data.get('host', '')}:8000"
            ),
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    def _get_raw_value(self) -> Any | None:
        """Look up this entity's value from coordinator data."""
        if self.coordinator.data is None:
            return None
        # entity_key can be a path like "Status/Engine/Battery Voltage"
        parts = self._entity_key.split(PATH_SEP)
        data = self.coordinator.data
        for part in parts:
            if isinstance(data, dict):
                data = data.get(part)
            else:
                return None
            if data is None:
                return None
        # genmon _num_json returns structured values like
        # {"unit": "V", "type": "float", "value": 13.9}
        # Extract the display value from these
        return self._unwrap_num_json(data)

    @staticmethod
    def _unwrap_num_json(data: Any) -> Any:
        """If data is a genmon _num_json structured dict, extract value+unit as string."""
        if isinstance(data, dict) and "value" in data:
            val = data["value"]
            unit = data.get("unit", "")
            if unit:
                return f"{val} {unit}"
            return val
        return data

    @staticmethod
    def extract_numeric(raw: str) -> tuple[float | None, str | None]:
        """Extract numeric value and unit from a string like '13.6 V' or '2.5 kW'."""
        if not isinstance(raw, str):
            try:
                return float(raw), None
            except (TypeError, ValueError):
                return None, None

        for suffix, unit in UNIT_STRIP_PATTERNS.items():
            if raw.endswith(suffix):
                try:
                    return float(raw[: -len(suffix)].strip().replace(",", "")), unit
                except ValueError:
                    return None, unit

        # Try generic number extraction
        match = re.match(r"^([+-]?\d[\d,]*\.?\d*)\s*(.*)$", raw.strip())
        if match:
            try:
                val = float(match.group(1).replace(",", ""))
                unit = match.group(2).strip() or None
                return val, unit
            except ValueError:
                pass
        return None, None
