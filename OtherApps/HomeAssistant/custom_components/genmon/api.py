"""Async API client for communicating with the genhalink addon."""
from __future__ import annotations

import asyncio
import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)


class GenmonConnectionError(Exception):
    """Error connecting to genhalink."""


class GenmonAuthError(Exception):
    """Authentication error with genhalink."""


class GenmonApiClient:
    """Async client for the genhalink REST + WebSocket API."""

    def __init__(
        self,
        host: str,
        port: int,
        api_key: str,
        session: aiohttp.ClientSession | None = None,
        use_ssl: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._api_key = api_key
        self._session = session
        self._use_ssl = use_ssl
        http_scheme = "https" if use_ssl else "http"
        self._base_url = f"{http_scheme}://{host}:{port}"
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        # When using a self-signed cert we still want encryption but cannot
        # verify the certificate authority, so disable verification.
        self._ssl_context: bool | None = False if use_ssl else None

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        session = await self._ensure_session()
        url = f"{self._base_url}{path}"
        try:
            async with session.request(
                method, url, headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=10),
                ssl=self._ssl_context, **kwargs
            ) as resp:
                if resp.status == 401:
                    raise GenmonAuthError("Invalid API key")
                if resp.status != 200:
                    raise GenmonConnectionError(
                        f"HTTP {resp.status} from {path}"
                    )
                return await resp.json()
        except aiohttp.ClientError as err:
            raise GenmonConnectionError(f"Cannot connect to {url}: {err}") from err
        except asyncio.TimeoutError as err:
            raise GenmonConnectionError(f"Timeout connecting to {url}") from err

    async def get_health(self) -> dict:
        """Check health (unauthenticated)."""
        session = await self._ensure_session()
        url = f"{self._base_url}/api/health"
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=5),
                ssl=self._ssl_context,
            ) as resp:
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise GenmonConnectionError(f"Cannot connect: {err}") from err

    async def get_info(self) -> dict:
        """Get generator start info (controller type, capabilities, model)."""
        return await self._request("GET", "/api/info")

    async def get_status(self) -> dict:
        """Get full state snapshot."""
        return await self._request("GET", "/api/status")

    async def get_entities(self) -> dict:
        """Get entity definitions (predefined + dynamic)."""
        return await self._request("GET", "/api/entities")

    async def send_command(self, command: str) -> dict:
        """Send a command to genmon."""
        return await self._request(
            "POST", "/api/command", json={"command": command}
        )

    async def validate_connection(self) -> dict:
        """Validate connection: check health then auth.

        If use_ssl is True and the HTTPS probe fails, automatically retries
        over plain HTTP so auto-detection works for older genhalink instances.
        """
        try:
            await self.get_health()
        except GenmonConnectionError:
            if self._use_ssl:
                # Transparently fall back to HTTP
                self._use_ssl = False
                self._ssl_context = None
                self._base_url = f"http://{self._host}:{self._port}"
                await self.get_health()
            else:
                raise
        return await self.get_info()

    async def listen_ws(self, callback) -> None:
        """Connect to WebSocket and call callback on each message."""
        session = await self._ensure_session()
        ws_scheme = "wss" if self._use_ssl else "ws"
        url = f"{ws_scheme}://{self._host}:{self._port}/ws"
        try:
            async with session.ws_connect(url, ssl=self._ssl_context) as ws:
                # Authenticate via first message
                await ws.send_json({"type": "auth", "token": self._api_key})
                auth_resp = await ws.receive_json()
                if auth_resp.get("type") != "auth_ok":
                    _LOGGER.error("WebSocket auth failed: %s", auth_resp)
                    return
                self._ws = ws
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = msg.json()
                        except Exception:
                            _LOGGER.debug("Failed to parse WS message")
                            continue
                        await callback(data)
                    elif msg.type in (
                        aiohttp.WSMsgType.ERROR,
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                    ):
                        break
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("WebSocket connection error: %s", err)
        finally:
            self._ws = None

    async def close(self) -> None:
        """Close the session."""
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
