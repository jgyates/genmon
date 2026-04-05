"""Number platform for Genmon Generator Monitor."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GenmonCoordinator
from .entity import GenmonEntity, should_add_entity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Genmon numbers from entity definitions."""
    coordinator: GenmonCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[GenmonNumber] = []
    known_ids: set[str] = set()

    controller_type = coordinator.entities.get("controller_type")
    capabilities = coordinator.entities.get("capabilities", {})
    entity_defs = coordinator.entities.get("numbers", [])
    for defn in entity_defs:
        if should_add_entity(defn, controller_type, capabilities):
            entities.append(GenmonNumber(coordinator, defn))
            known_ids.add(defn.get("entity_id", defn.get("name", "")))

    async_add_entities(entities)

    @callback
    def _add_new(new_defs: list[dict]) -> None:
        ct = coordinator.entities.get("controller_type")
        caps = coordinator.entities.get("capabilities", {})
        async_add_entities([
            GenmonNumber(coordinator, d)
            for d in new_defs
            if should_add_entity(d, ct, caps)
        ])

    coordinator.register_platform("numbers", _add_new, known_ids)


class GenmonNumber(GenmonEntity, NumberEntity):
    """A Genmon number entity (e.g., exercise hour/minute/day)."""

    def __init__(self, coordinator: GenmonCoordinator, defn: dict[str, Any]) -> None:
        self._defn = defn
        entity_key = defn.get("entity_id", defn.get("name", ""))
        name = defn.get("name", entity_key)
        super().__init__(coordinator, entity_key, name)

        self._attr_native_min_value = float(defn.get("min", 0))
        self._attr_native_max_value = float(defn.get("max", 100))
        self._attr_native_step = float(defn.get("step", 1))
        self._attr_mode = NumberMode.BOX
        self._attr_icon = defn.get("icon")
        self._command_template = defn.get("command_template", "")
        self._stored_value: float | None = None

    @property
    def native_value(self) -> float | None:
        """Return the current value from coordinator exercise data."""
        exercise = self._get_exercise_data()
        if exercise is None:
            return self._stored_value

        eid = self._defn.get("entity_id", "")
        if eid == "exercise_day_of_month":
            val = exercise.get("day_of_month")
            if val is not None:
                return float(val)
        elif eid == "exercise_hour":
            val = exercise.get("hour")
            if val is not None:
                return float(val)
        elif eid == "exercise_minute":
            val = exercise.get("minute")
            if val is not None:
                return float(val)
        return self._stored_value

    async def async_set_native_value(self, value: float) -> None:
        """Set the value and send exercise command."""
        self._stored_value = value
        await self._send_exercise_command()
        await self.coordinator.async_request_refresh()

    async def _send_exercise_command(self) -> None:
        """Build and send the setexercise command from current values."""
        exercise = self._get_exercise_data() or {}
        eid = self._defn.get("entity_id", "")

        frequency = exercise.get("frequency", "Weekly")
        day = exercise.get("day", "Monday")
        hour = exercise.get("hour", 12)
        minute = exercise.get("minute", 0)

        if eid == "exercise_hour" and self._stored_value is not None:
            hour = int(self._stored_value)
        elif eid == "exercise_minute" and self._stored_value is not None:
            minute = int(self._stored_value)

        time_str = f"{int(hour):02d}:{int(minute):02d}"
        cmd = f"setexercise={day},{time_str},{frequency}"
        _LOGGER.debug("Sending exercise command: %s", cmd)
        await self.coordinator.api.send_command(cmd)

    def _get_exercise_data(self) -> dict[str, Any] | None:
        """Extract exercise schedule data from coordinator."""
        if self.coordinator.data is None:
            return None
        maint = self.coordinator.data.get("Maintenance", {})
        exercise = maint.get("Exercise", {})
        if not exercise:
            return None

        exercise_time = exercise.get("Exercise Time", "")
        if isinstance(exercise_time, str) and exercise_time:
            return self._parse_exercise_time(exercise_time)
        return None

    @staticmethod
    def _parse_exercise_time(raw: str) -> dict[str, Any]:
        """Parse exercise time string into components."""
        parts = raw.split()
        result: dict[str, Any] = {}
        if len(parts) >= 1:
            result["frequency"] = parts[0]
        if len(parts) >= 2:
            result["day"] = parts[1]
        if len(parts) >= 3 and ":" in parts[2]:
            time_parts = parts[2].split(":")
            try:
                result["hour"] = int(time_parts[0])
                result["minute"] = int(time_parts[1]) if len(time_parts) > 1 else 0
            except ValueError:
                pass
        return result
