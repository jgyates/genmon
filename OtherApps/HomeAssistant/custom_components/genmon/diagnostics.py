"""Diagnostics support for Genmon Generator Monitor."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, DOMAIN
from .coordinator import GenmonCoordinator

REDACT_KEYS = {
    CONF_API_KEY,
    "api_key",
    "serial",
    "SerialNumber",
    "Generator Serial Number",
    "password",
    "Password",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: GenmonCoordinator = hass.data[DOMAIN][entry.entry_id]

    return {
        "config_entry": async_redact_data(dict(entry.data), REDACT_KEYS),
        "options": dict(entry.options),
        "info": async_redact_data(coordinator.info, REDACT_KEYS),
        "entity_definitions": {
            "sensors": len(coordinator.entities.get("sensors", [])),
            "binary_sensors": len(coordinator.entities.get("binary_sensors", [])),
            "buttons": len(coordinator.entities.get("buttons", [])),
            "switches": len(coordinator.entities.get("switches", [])),
            "selects": len(coordinator.entities.get("selects", [])),
            "numbers": len(coordinator.entities.get("numbers", [])),
        },
        "state": async_redact_data(coordinator.data or {}, REDACT_KEYS),
    }
