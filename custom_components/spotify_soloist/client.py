"""Async client for the Spotify Soloist local WebSocket API."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

RECONNECT_MIN = 1
RECONNECT_MAX = 60


class SoloistError(Exception):
    """Raised when Soloist cannot be reached or rejects a command."""


class SoloistClient:
    """Keeps a WebSocket connection to Soloist and mirrors its state.

    State is held as the raw event payloads from Soloist. Listeners are called
    with no arguments whenever anything changes, including connection state.
    """

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int) -> None:
        self._session = session
        self._url = f"ws://{host}:{port}"
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._task: asyncio.Task | None = None
        self._listeners: list[Callable[[], None]] = []

        self.connected = False
        self.auth: dict[str, Any] = {}
        self.playback: dict[str, Any] = {}
        self.queue: dict[str, Any] = {}

    @property
    def url(self) -> str:
        return self._url

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a change listener. Returns a function that removes it."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    async def probe(self, timeout: float = 10) -> dict[str, Any]:
        """Connect once, return the first auth_state, then disconnect."""
        try:
            async with asyncio.timeout(timeout):
                async with self._session.ws_connect(self._url) as ws:
                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            break
                        data = msg.json()
                        if data.get("type") == "auth_state":
                            return data
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            raise SoloistError(f"Cannot connect to {self._url}: {err}") from err
        raise SoloistError(f"No auth_state received from {self._url}")

    def start(self) -> None:
        """Start the background connection loop."""
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="spotify_soloist_ws")

    async def stop(self) -> None:
        """Stop the connection loop and close the socket."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._set_connected(False)

    async def send(self, command: str, **fields: Any) -> None:
        """Send a command. Soloist answers asynchronously with events."""
        if self._ws is None or self._ws.closed:
            raise SoloistError("Not connected to Soloist")
        await self._ws.send_json({"type": "command", "command": command, **fields})

    async def _run(self) -> None:
        delay = RECONNECT_MIN
        while True:
            try:
                async with self._session.ws_connect(self._url, heartbeat=30) as ws:
                    self._ws = ws
                    self._set_connected(True)
                    delay = RECONNECT_MIN
                    _LOGGER.debug("Connected to %s", self._url)
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            self._handle(msg.json())
                        elif msg.type in (
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.ERROR,
                        ):
                            break
            except (aiohttp.ClientError, OSError, ValueError) as err:
                _LOGGER.debug("Soloist connection to %s failed: %s", self._url, err)
            finally:
                self._ws = None
                self._set_connected(False)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX)

    def _set_connected(self, connected: bool) -> None:
        if self.connected == connected:
            return
        self.connected = connected
        if not connected:
            self.auth = {}
            self.playback = {}
            self.queue = {}
        self._notify()

    def _handle(self, data: dict[str, Any]) -> None:
        kind = data.get("type")
        pb = self.playback

        if kind == "auth_state":
            was_logged_in = self.auth.get("logged_in")
            self.auth = data
            if not data.get("logged_in"):
                self.playback = {}
                self.queue = {}
            elif not was_logged_in:
                # Fresh login: ask for a full snapshot.
                asyncio.create_task(self._safe_send("get_state"))
        elif kind == "playback_state":
            self.playback = data
        elif kind == "track_changed":
            pb["item"] = data.get("item")
        elif kind == "playback_changed":
            pb["status"] = data.get("status")
        elif kind == "volume_changed":
            pb["volume"] = data.get("volume")
        elif kind == "device_changed":
            pb["is_active"] = data.get("is_active")
            self.auth["is_active"] = data.get("is_active")
            if "device_name" in data:
                self.auth["device_name"] = data["device_name"]
        elif kind == "context_changed":
            pb["context"] = data.get("context")
        elif kind == "options_changed":
            pb["options"] = data.get("options")
        elif kind == "position_sync":
            pb["position"] = data.get("position")
        elif kind == "queue_changed":
            self.queue = data
        elif kind == "error":
            _LOGGER.warning("Soloist error: %s", data.get("message"))
            return
        else:
            # command_result and unknown events carry no state.
            return
        self._notify()

    async def _safe_send(self, command: str, **fields: Any) -> None:
        with contextlib.suppress(SoloistError, aiohttp.ClientError):
            await self.send(command, **fields)

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()
