"""Switch platform for Genmon Generator Monitor."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up Genmon switches from entity definitions."""
    coordinator: GenmonCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[GenmonSwitch] = []
    known_ids: set[str] = set()

    controller_type = coordinator.entities.get("controller_type")
    capabilities = coordinator.entities.get("capabilities", {})
    entity_defs = coordinator.entities.get("switches", [])
    for defn in entity_defs:
        if should_add_entity(defn, controller_type, capabilities):
            entities.append(GenmonSwitch(coordinator, defn))
            known_ids.add(defn.get("entity_id", defn.get("name", "")))

    async_add_entities(entities)

    @callback
    def _add_new(new_defs: list[dict]) -> None:
        ct = coordinator.entities.get("controller_type")
        caps = coordinator.entities.get("capabilities", {})
        async_add_entities([
            GenmonSwitch(coordinator, d)
            for d in new_defs
            if should_add_entity(d, ct, caps)
        ])

    coordinator.register_platform("switches", _add_new, known_ids)


class GenmonSwitch(GenmonEntity, SwitchEntity):
    """A Genmon switch entity (e.g., quiet mode)."""

    def __init__(self, coordinator: GenmonCoordinator, defn: dict[str, Any]) -> None:
        self._defn = defn
        entity_key = defn.get("entity_id", defn.get("name", ""))
        name = defn.get("name", entity_key)
        super().__init__(coordinator, entity_key, name)

        self._command_on = defn.get("command_on", "")
        self._command_off = defn.get("command_off", "")
        self._state_path = defn.get("state_path", "")
        self._payload_on = defn.get("payload_on", "On")
        self._payload_off = defn.get("payload_off", "Off")
        self._attr_icon = defn.get("icon")

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        parts = self._state_path.split("/") if self._state_path else []
        data = self.coordinator.data
        for part in parts:
            if isinstance(data, dict):
                data = data.get(part)
            else:
                return None
            if data is None:
                return None
        data = self._unwrap_num_json(data)
        return str(data).strip() == self._payload_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        _LOGGER.debug("Switch ON %s: %s", self.name, self._command_on)
        await self.coordinator.api.send_command(self._command_on)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        _LOGGER.debug("Switch OFF %s: %s", self.name, self._command_off)
        await self.coordinator.api.send_command(self._command_off)
        await self.coordinator.async_request_refresh()
