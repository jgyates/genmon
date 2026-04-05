"""The Genmon Generator Monitor integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, PLATFORMS
from .coordinator import GenmonCoordinator
from .entity import should_add_entity

_LOGGER = logging.getLogger(__name__)

type GenmonConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: GenmonConfigEntry) -> bool:
    """Set up Genmon from a config entry."""
    coordinator = GenmonCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()
    await coordinator.start_ws()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_cleanup_stale_entities(hass, entry, coordinator)

    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    return True


def _build_valid_unique_ids(
    entry_id: str, entities: dict[str, Any]
) -> set[str]:
    """Build the set of unique_ids that the API currently defines.

    The entity_key logic here must mirror each platform's __init__.
    """
    valid: set[str] = set()
    controller_type = entities.get("controller_type")
    capabilities = entities.get("capabilities", {})

    # Map platform keys → entity_key extraction (mirrors each platform class)
    # sensor.py: super().__init__(..., defn.get("entity_id", entity_key), ...)
    #   so entity_id wins over path for the unique_id in ALL platforms.
    key_builders: dict[str, Any] = {
        "sensors": lambda d: d.get("entity_id", d.get("path", "")),
        "binary_sensors": lambda d: d.get("entity_id", d.get("path", "")),
        "buttons": lambda d: d.get("entity_id", d.get("name", "")),
        "switches": lambda d: d.get("entity_id", d.get("name", "")),
        "selects": lambda d: d.get("entity_id", d.get("name", "")),
        "numbers": lambda d: d.get("entity_id", d.get("name", "")),
    }

    for platform_key, get_key in key_builders.items():
        for defn in entities.get(platform_key, []):
            if should_add_entity(defn, controller_type, capabilities):
                entity_key = get_key(defn)
                if entity_key:
                    valid.add(f"{entry_id}_{entity_key}")

    # Controller buttons use a special key format
    for btn in entities.get("buttons_from_controller", []):
        owc = btn.get("onewordcommand", "")
        if owc:
            valid.add(f"{entry_id}_ctrl_{owc.lower().replace(' ', '_')}")

    return valid


@callback
def _async_cleanup_stale_entities(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: GenmonCoordinator
) -> None:
    """Remove entities from the HA registry that the API no longer defines."""
    if not coordinator.entities:
        return

    valid_ids = _build_valid_unique_ids(entry.entry_id, coordinator.entities)
    if not valid_ids:
        return  # Safety: don't nuke everything if definitions failed to load

    registry = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.unique_id not in valid_ids:
            _LOGGER.info(
                "Removing stale entity %s (%s)",
                reg_entry.entity_id,
                reg_entry.unique_id,
            )
            registry.async_remove(reg_entry.entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: GenmonConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: GenmonCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.stop_ws()
    return unload_ok


async def _async_update_options(hass: HomeAssistant, entry: GenmonConfigEntry) -> None:
    """Handle options update — reload the integration."""
    await hass.config_entries.async_reload(entry.entry_id)
