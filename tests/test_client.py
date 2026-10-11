"""Tests for the Soloist WebSocket client against a fake Soloist server."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys

import aiohttp
from aiohttp import web
import pytest

# Load client.py directly so the tests don't need Home Assistant installed.
_spec = importlib.util.spec_from_file_location(
    "soloist_client",
    Path(__file__).parents[1] / "custom_components/spotify_soloist/client.py",
)
client_mod = importlib.util.module_from_spec(_spec)
sys.modules["soloist_client"] = client_mod
_spec.loader.exec_module(client_mod)

SoloistClient = client_mod.SoloistClient
SoloistError = client_mod.SoloistError

AUTH_LOGGED_OUT = {
    "type": "auth_state",
    "logged_in": False,
    "is_active": False,
    "device_name": "Test",
}
AUTH_LOGGED_IN = {**AUTH_LOGGED_OUT, "logged_in": True, "is_active": True}
PLAYBACK = {
    "type": "playback_state",
    "status": "playing",
    "item": {"uri": "spotify:track:a", "entity_type": "track", "decorations": {}},
    "volume": 65,
    "options": {"shuffle": False, "repeat": "off"},
}


class FakeSoloist:
    """Speaks the documented Soloist WebSocket protocol."""

    def __init__(self) -> None:
        self.received: list[dict] = []
        self.sockets: list[web.WebSocketResponse] = []
        self.logged_in = False

    async def handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.sockets.append(ws)
        await ws.send_json(AUTH_LOGGED_IN if self.logged_in else AUTH_LOGGED_OUT)
        if self.logged_in:
            await ws.send_json(PLAYBACK)
        async for msg in ws:
            data = json.loads(msg.data)
            self.received.append(data)
            if data.get("command") == "get_state":
                await ws.send_json(PLAYBACK)
            else:
                await ws.send_json(
                    {"type": "command_result", "command": data["command"]}
                )
        return ws

    async def broadcast(self, payload: dict) -> None:
        for ws in self.sockets:
            if not ws.closed:
                await ws.send_json(payload)


@pytest.fixture
async def server():
    fake = FakeSoloist()
    app = web.Application()
    app.router.add_get("/", fake.handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    yield fake, port
    for ws in fake.sockets:
        await ws.close()
    await runner.cleanup()


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as s:
        yield s


async def wait_for(predicate, timeout=3):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


async def test_probe_returns_auth_state(server, session):
    _, port = server
    auth = await SoloistClient(session, "127.0.0.1", port).probe()
    assert auth["device_name"] == "Test"


async def test_probe_unreachable(session):
    with pytest.raises(SoloistError):
        await SoloistClient(session, "127.0.0.1", 1).probe(timeout=2)


async def test_login_fetches_state_and_tracks_events(server, session):
    fake, port = server
    client = SoloistClient(session, "127.0.0.1", port)
    changes = []
    client.add_listener(lambda: changes.append(1))
    client.start()
    try:
        await wait_for(lambda: client.auth.get("device_name") == "Test")
        assert client.connected
        assert client.playback == {}

        # Logging in triggers a get_state for a full snapshot.
        await fake.broadcast(AUTH_LOGGED_IN)
        await wait_for(lambda: client.playback.get("status") == "playing")
        assert {"type": "command", "command": "get_state"} in fake.received

        await fake.broadcast({"type": "volume_changed", "volume": 42})
        await fake.broadcast({"type": "playback_changed", "status": "paused"})
        await fake.broadcast(
            {"type": "device_changed", "is_active": False, "device_name": "Test"}
        )
        await wait_for(lambda: client.playback.get("status") == "paused")
        await wait_for(lambda: client.auth.get("is_active") is False)
        assert client.playback["volume"] == 42
        assert changes

        await client.send("set_volume", volume=10)
        await wait_for(
            lambda: (
                {"type": "command", "command": "set_volume", "volume": 10}
                in fake.received
            )
        )

        # Logging out clears playback state.
        await fake.broadcast(AUTH_LOGGED_OUT)
        await wait_for(lambda: client.playback == {})
    finally:
        await client.stop()
    assert not client.connected


async def test_reconnects_after_server_drop(server, session, monkeypatch):
    fake, port = server
    monkeypatch.setattr(client_mod, "RECONNECT_MIN", 0.05)
    client = SoloistClient(session, "127.0.0.1", port)
    client.start()
    try:
        await wait_for(lambda: client.connected)
        await fake.sockets[0].close()
        await wait_for(lambda: len(fake.sockets) == 2 and client.connected)
    finally:
        await client.stop()


async def test_send_when_disconnected(session):
    client = SoloistClient(session, "127.0.0.1", 1)
    with pytest.raises(SoloistError):
        await client.send("play")
