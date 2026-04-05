"""DataUpdateCoordinator for Genmon Generator Monitor."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GenmonApiClient, GenmonConnectionError
from .const import (
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    CONF_USE_SSL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USE_SSL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class GenmonCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls genhalink and listens on WebSocket."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.api = GenmonApiClient(
            entry.data[CONF_HOST],
            entry.data[CONF_PORT],
            entry.data[CONF_API_KEY],
            use_ssl=entry.data.get(CONF_USE_SSL, DEFAULT_USE_SSL),
        )
        self._ws_task: asyncio.Task | None = None
        self.entities: dict[str, Any] = {}
        self.info: dict[str, Any] = {}
        self._new_entity_callbacks: dict[str, Callable] = {}
        self._known_entity_ids: dict[str, set[str]] = {}
        self._last_entity_fetch: float = 0

        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest state from genhalink."""
        try:
            status = await self.api.get_status()
        except GenmonConnectionError as err:
            raise UpdateFailed(f"Error communicating with genhalink: {err}") from err

        # Fetch entity definitions: always on first call, then re-check every 60s
        try:
            now = time.monotonic()
            if not self.entities or (now - self._last_entity_fetch >= 60):
                fresh = await self.api.get_entities()
                if fresh:
                    if self.entities and self._new_entity_callbacks:
                        self._dispatch_new_entities(fresh)
                    self.entities = fresh
                    self._last_entity_fetch = now
            if not self.info:
                self.info = await self.api.get_info()
        except GenmonConnectionError:
            _LOGGER.debug("Failed to fetch entities/info, will retry next poll")

        # The API returns {"state": {...}, "values": {...}}
        # Entities need the nested state dict for path traversal
        state = status.get("state", status)
        _LOGGER.debug(
            "Polled genmon: %d top-level keys in state",
            len(state) if isinstance(state, dict) else 0,
        )
        return state

    def register_platform(
        self,
        platform_key: str,
        add_callback: Callable[[list[dict]], None],
        known_ids: set[str],
    ) -> None:
        """Store a platform's callback for dynamic entity discovery."""
        self._new_entity_callbacks[platform_key] = add_callback
        self._known_entity_ids[platform_key] = known_ids

    @callback
    def _dispatch_new_entities(self, fresh: dict) -> None:
        """Detect new entity definitions and dispatch them to platforms."""
        for platform_key, cb in self._new_entity_callbacks.items():
            known = self._known_entity_ids.get(platform_key, set())
            new_defs = []
            for defn in fresh.get(platform_key, []):
                eid = defn.get("entity_id", "")
                if eid and eid not in known:
                    new_defs.append(defn)
                    known.add(eid)
            if new_defs:
                _LOGGER.info(
                    "Discovered %d new %s entities: %s",
                    len(new_defs),
                    platform_key,
                    [d.get("entity_id") for d in new_defs],
                )
                cb(new_defs)

    async def _async_ws_listener(self) -> None:
        """Background WebSocket listener for push updates."""
        while True:
            try:
                await self.api.listen_ws(self._handle_ws_message)
            except Exception:
                _LOGGER.debug("WebSocket disconnected, reconnecting in 5s")
            await asyncio.sleep(5)

    async def _handle_ws_message(self, data: dict) -> None:
        """Handle incoming WebSocket push data."""
        msg_type = data.get("type")
        if msg_type in ("state_update", "full_state"):
            state = data.get("state", {})
            if state:
                # Use async_set_updated_data to push new state to entities.
                # This also resets the poll timer so the next poll happens
                # update_interval seconds from now (avoids double-polling).
                self.async_set_updated_data(state)

    async def start_ws(self) -> None:
        """Start the WebSocket listener task."""
        if self._ws_task is None or self._ws_task.done():
            self._ws_task = self.hass.async_create_background_task(
                self._async_ws_listener(),
                f"{DOMAIN}_ws_listener",
            )

    async def stop_ws(self) -> None:
        """Stop the WebSocket listener and close the API session."""
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None
        await self.api.close()
