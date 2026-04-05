"""Binary sensor platform for Genmon Generator Monitor."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GenmonCoordinator
from .entity import GenmonEntity, should_add_entity

_LOGGER = logging.getLogger(__name__)
_UNSET = object()  # sentinel distinct from any real is_on value

DEVICE_CLASS_MAP = {
    "power": BinarySensorDeviceClass.POWER,
    "problem": BinarySensorDeviceClass.PROBLEM,
    "running": BinarySensorDeviceClass.RUNNING,
    "update": BinarySensorDeviceClass.UPDATE,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Genmon binary sensors from entity definitions."""
    coordinator: GenmonCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[GenmonBinarySensor] = []
    known_ids: set[str] = set()

    controller_type = coordinator.entities.get("controller_type")
    capabilities = coordinator.entities.get("capabilities", {})
    entity_defs = coordinator.entities.get("binary_sensors", [])
    for defn in entity_defs:
        if should_add_entity(defn, controller_type, capabilities):
            entities.append(GenmonBinarySensor(coordinator, defn))
            known_ids.add(defn.get("entity_id", defn.get("path", "")))

    async_add_entities(entities)

    @callback
    def _add_new(new_defs: list[dict]) -> None:
        ct = coordinator.entities.get("controller_type")
        caps = coordinator.entities.get("capabilities", {})
        async_add_entities([
            GenmonBinarySensor(coordinator, d)
            for d in new_defs
            if should_add_entity(d, ct, caps)
        ])

    coordinator.register_platform("binary_sensors", _add_new, known_ids)


class GenmonBinarySensor(GenmonEntity, BinarySensorEntity):
    """A Genmon binary sensor entity."""

    def __init__(self, coordinator: GenmonCoordinator, defn: dict[str, Any]) -> None:
        self._defn = defn
        entity_key = defn.get("entity_id", defn.get("path", ""))
        name = defn.get("name", entity_key)
        super().__init__(coordinator, entity_key, name)

        self._path = defn.get("path", "")
        self._attr_icon = defn.get("icon")

        if defn.get("device_class") in DEVICE_CLASS_MAP:
            self._attr_device_class = DEVICE_CLASS_MAP[defn["device_class"]]

        if defn.get("category") == "diagnostic":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

        # Matching logic configuration
        self._payload_on = defn.get("payload_on")
        self._payload_off = defn.get("payload_off")
        self._payload_on_not_empty = defn.get("payload_on_not_empty", False)
        self._payload_on_gt = defn.get("payload_on_gt")
        self._payload_off_invert = defn.get("payload_off_invert", False)
        self._prev_is_on = _UNSET

    @callback
    def _handle_coordinator_update(self) -> None:
        """Write HA state only when is_on actually changes."""
        new_val = self.is_on
        if self._prev_is_on is not _UNSET and new_val == self._prev_is_on:
            return
        self._prev_is_on = new_val
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        raw = self._get_raw_value()
        if raw is None:
            # For payload_on_not_empty sensors, missing path means OFF
            # (e.g. "System In Alarm" only exists when alarm is active)
            if self._payload_on_not_empty:
                return False
            return None

        raw_str = str(raw).strip()

        # payload_on_not_empty: ON when the value is non-empty
        if self._payload_on_not_empty:
            return bool(raw_str)

        # payload_on_gt: ON when numeric value exceeds threshold
        if self._payload_on_gt is not None:
            numeric, _ = self.extract_numeric(raw)
            if numeric is not None:
                return numeric > self._payload_on_gt
            return False

        # payload_on as list: ON if value matches any in the list
        if isinstance(self._payload_on, list):
            return raw_str in self._payload_on

        # payload_on as string: exact match
        if isinstance(self._payload_on, str):
            if self._payload_off_invert:
                # ON = matches payload_on, OFF = everything else
                return raw_str == self._payload_on
            return raw_str == self._payload_on

        # If payload_off_invert is set with list payload_on
        if self._payload_off_invert and isinstance(self._payload_on, list):
            return raw_str in self._payload_on

        return None

    def _get_raw_value(self) -> Any | None:
        if self.coordinator.data is None:
            return None
        parts = self._path.split("/") if self._path else []
        data = self.coordinator.data
        for part in parts:
            if isinstance(data, dict):
                data = data.get(part)
            else:
                return None
            if data is None:
                return None
        return self._unwrap_num_json(data)
