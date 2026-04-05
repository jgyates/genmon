"""Button platform for Genmon Generator Monitor."""
from __future__ import annotations

import copy
import json
import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_BUTTON_PASSCODE, DOMAIN
from .coordinator import GenmonCoordinator
from .entity import GenmonEntity, should_add_entity

_LOGGER = logging.getLogger(__name__)

# Icon mapping for common controller button onewordcommand values
_ICON_MAP = {
    "start": "mdi:play",
    "startcmd": "mdi:play",
    "stop": "mdi:stop",
    "stopcmd": "mdi:stop",
    "auto": "mdi:autorenew",
    "manual": "mdi:hand-back-right",
    "mute": "mdi:volume-off",
    "reset": "mdi:restart",
    "faultreset": "mdi:restart-alert",
    "test": "mdi:test-tube",
    "startexercise": "mdi:test-tube",
    "transfer": "mdi:transfer",
    "off": "mdi:power-off",
    "on": "mdi:power",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Genmon buttons from entity definitions."""
    coordinator: GenmonCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[ButtonEntity] = []

    # Static button definitions from JSON files
    controller_type = coordinator.entities.get("controller_type")
    capabilities = coordinator.entities.get("capabilities", {})
    known_ids: set[str] = set()
    entity_defs = coordinator.entities.get("buttons", [])
    for defn in entity_defs:
        if should_add_entity(defn, controller_type, capabilities):
            entities.append(GenmonButton(coordinator, defn))
            known_ids.add(defn.get("entity_id", defn.get("name", "")))

    # Dynamic buttons from controller StartInfo
    controller_buttons = coordinator.entities.get("buttons_from_controller", [])
    passcode = entry.options.get(CONF_BUTTON_PASSCODE, "")
    for button in controller_buttons:
        entities.append(GenmonControllerButton(coordinator, button, passcode))

    async_add_entities(entities)

    @callback
    def _add_new(new_defs: list[dict]) -> None:
        ct = coordinator.entities.get("controller_type")
        caps = coordinator.entities.get("capabilities", {})
        async_add_entities([
            GenmonButton(coordinator, d)
            for d in new_defs
            if should_add_entity(d, ct, caps)
        ])

    coordinator.register_platform("buttons", _add_new, known_ids)


class GenmonButton(GenmonEntity, ButtonEntity):
    """A Genmon button entity for sending commands."""

    def __init__(self, coordinator: GenmonCoordinator, defn: dict[str, Any]) -> None:
        self._defn = defn
        entity_key = defn.get("entity_id", defn.get("name", ""))
        name = defn.get("name", entity_key)
        super().__init__(coordinator, entity_key, name)

        self._command = defn.get("command", "")
        self._attr_icon = defn.get("icon")

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.debug("Pressing button %s: %s", self.name, self._command)
        await self.coordinator.api.send_command(self._command)
        await self.coordinator.async_request_refresh()


class GenmonControllerButton(GenmonEntity, ButtonEntity):
    """A button entity sourced from the controller's StartInfo buttons.

    Uses the set_button_command API. For command_sequence entries that have
    an input_title but no value, the configured button_passcode is injected.
    """

    def __init__(
        self,
        coordinator: GenmonCoordinator,
        button: dict[str, Any],
        passcode: str,
    ) -> None:
        onewordcommand = button.get("onewordcommand", "")
        title = button.get("title", onewordcommand)
        entity_key = f"ctrl_{onewordcommand.lower().replace(' ', '_')}"
        super().__init__(coordinator, entity_key, title)

        self._onewordcommand = onewordcommand
        self._command_sequence = button.get("command_sequence", [])
        self._passcode = passcode
        self._attr_icon = _ICON_MAP.get(onewordcommand.lower(), "mdi:button-pointer")

    async def async_press(self) -> None:
        """Handle the button press via set_button_command."""
        cmd_seq = copy.deepcopy(self._command_sequence)
        for cmd in cmd_seq:
            if "input_title" in cmd and "value" not in cmd:
                cmd["value"] = self._passcode

        payload = json.dumps([{
            "onewordcommand": self._onewordcommand,
            "command_sequence": cmd_seq,
        }])
        _LOGGER.debug("Pressing controller button %s", self._onewordcommand)
        await self.coordinator.api.send_command(f"set_button_command={payload}")
        await self.coordinator.async_request_refresh()
