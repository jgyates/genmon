"""Select platform for Genmon Generator Monitor."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
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
    """Set up Genmon selects from entity definitions."""
    coordinator: GenmonCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[GenmonSelect] = []
    known_ids: set[str] = set()

    controller_type = coordinator.entities.get("controller_type")
    capabilities = coordinator.entities.get("capabilities", {})
    entity_defs = coordinator.entities.get("selects", [])
    for defn in entity_defs:
        if should_add_entity(defn, controller_type, capabilities):
            entities.append(GenmonSelect(coordinator, defn))
            known_ids.add(defn.get("entity_id", defn.get("name", "")))

    async_add_entities(entities)

    @callback
    def _add_new(new_defs: list[dict]) -> None:
        ct = coordinator.entities.get("controller_type")
        caps = coordinator.entities.get("capabilities", {})
        async_add_entities([
            GenmonSelect(coordinator, d)
            for d in new_defs
            if should_add_entity(d, ct, caps)
        ])

    coordinator.register_platform("selects", _add_new, known_ids)


class GenmonSelect(GenmonEntity, SelectEntity):
    """A Genmon select entity (e.g., exercise frequency/day)."""

    def __init__(self, coordinator: GenmonCoordinator, defn: dict[str, Any]) -> None:
        self._defn = defn
        entity_key = defn.get("entity_id", defn.get("name", ""))
        name = defn.get("name", entity_key)
        super().__init__(coordinator, entity_key, name)

        self._attr_options = defn.get("options", [])
        self._attr_icon = defn.get("icon")
        self._command_template = defn.get("command_template", "")
        self._current_option: str | None = None

    @property
    def current_option(self) -> str | None:
        """Return the current selected option from coordinator data."""
        exercise = self._get_exercise_data()
        if exercise is None:
            return self._current_option

        eid = self._defn.get("entity_id", "")
        if eid == "exercise_frequency":
            raw = exercise.get("frequency")
            return self._match_option(raw) if raw else self._current_option
        elif eid == "exercise_day_of_week":
            raw = exercise.get("day")
            return self._match_option(raw) if raw else self._current_option
        return self._current_option

    def _match_option(self, raw: str) -> str | None:
        """Case-insensitive match of a raw value against the defined options."""
        for opt in self._attr_options:
            if opt.lower() == raw.lower():
                return opt
        return raw

    async def async_select_option(self, option: str) -> None:
        """Set the selected option and send exercise command."""
        self._current_option = option
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

        if eid == "exercise_frequency":
            frequency = self._current_option or frequency
        elif eid == "exercise_day_of_week":
            day = self._current_option or day

        time_str = f"{int(hour):02d}:{int(minute):02d}"
        cmd = f"setexercise={day},{time_str},{frequency}"
        _LOGGER.debug("Sending exercise command: %s", cmd)
        await self.coordinator.api.send_command(cmd)

    def _get_exercise_data(self) -> dict[str, Any] | None:
        """Extract exercise schedule data from coordinator."""
        if self.coordinator.data is None:
            return None
        # Try path: Maintenance/Exercise
        maint = self.coordinator.data.get("Maintenance", {})
        exercise = maint.get("Exercise", {})
        if not exercise:
            return None

        # Parse "Exercise Time" string like "Weekly  Monday 12:00"
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
