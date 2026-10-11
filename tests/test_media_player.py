"""Tests for the Soloist media player entity."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest
from spotify_soloist.client import SoloistError
from spotify_soloist.media_player import SoloistMediaPlayer, to_spotify_uri

from homeassistant.components.media_player import (
    MediaPlayerEnqueue,
    MediaPlayerState,
    MediaType,
    RepeatMode,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

TRACK = {
    "uri": "spotify:track:2JRo0gjbX4GrCqBYdRohoo",
    "entity_type": "track",
    "decorations": {
        "identity": {"name": "My Song"},
        "visual_identity": {
            "cover": [
                {"url": "https://i.scdn.co/small", "size": "small"},
                {"url": "https://i.scdn.co/large", "size": "large"},
            ]
        },
        "parent": {
            "entity": {
                "uri": "spotify:album:x",
                "entity_type": "album",
                "decorations": {"identity": {"name": "Album Name"}},
            }
        },
        "creators": [
            {"entity": {"decorations": {"identity": {"name": "Artist A"}}}},
            {"entity": {"decorations": {"identity": {"name": "Artist B"}}}},
        ],
        "playback": {"duration_ms": 210000, "content_ratings": []},
    },
}


def make_player(**client_state):
    state = {
        "connected": True,
        "auth": {"logged_in": True, "is_active": True, "device_name": "Kitchen"},
        "playback": {
            "status": "playing",
            "item": TRACK,
            "context": {
                "uri": "spotify:playlist:p",
                "decorations": {"identity": {"name": "Hits"}},
            },
            "position": {
                "position_ms": 45000,
                "timestamp_ms": 1747654321000,
                "speed": 1.0,
            },
            "volume": 65,
            "options": {"shuffle": True, "repeat": "context"},
        },
        "queue": {
            "upcoming": [
                {
                    "item": {
                        "uri": "spotify:track:n",
                        "decorations": {"identity": {"name": "Next"}},
                    }
                }
            ]
        },
    }
    state.update(client_state)
    client = SimpleNamespace(
        **state, send=AsyncMock(), add_listener=lambda listener: lambda: None
    )
    entry = SimpleNamespace(
        runtime_data=client, unique_id="127.0.0.1:9090", entry_id="e1", title="Kitchen"
    )
    return SoloistMediaPlayer(entry), client


def test_state_and_metadata():
    player, _ = make_player()
    assert player.available
    assert player.state == MediaPlayerState.PLAYING
    assert player.media_title == "My Song"
    assert player.media_artist == "Artist A, Artist B"
    assert player.media_album_name == "Album Name"
    assert player.media_playlist == "Hits"
    assert player.media_image_url == "https://i.scdn.co/large"
    assert player.media_duration == 210
    assert player.media_position == 45
    assert player.media_position_updated_at.timestamp() == 1747654321
    assert player.volume_level == 0.65
    assert player.shuffle is True
    assert player.repeat == RepeatMode.ALL
    assert player.media_content_type == MediaType.MUSIC
    assert player.extra_state_attributes == {
        "context_uri": "spotify:playlist:p",
        "queue": [{"uri": "spotify:track:n", "name": "Next"}],
    }


@pytest.mark.parametrize(
    ("auth", "expected"),
    [
        ({"logged_in": False, "is_active": False}, MediaPlayerState.OFF),
        ({"logged_in": True, "is_active": False}, MediaPlayerState.OFF),
    ],
)
def test_off_when_not_active(auth, expected):
    player, _ = make_player(auth=auth)
    assert player.state == expected


def test_unavailable_and_empty_when_disconnected():
    player, _ = make_player(connected=False, auth={}, playback={}, queue={})
    assert not player.available
    assert player.media_title is None
    assert player.volume_level is None
    assert player.media_position is None


@pytest.mark.parametrize(
    ("status", "state"),
    [
        ("paused", MediaPlayerState.PAUSED),
        ("buffering", MediaPlayerState.BUFFERING),
        ("idle", MediaPlayerState.IDLE),
    ],
)
def test_status_mapping(status, state):
    player, client = make_player()
    client.playback["status"] = status
    assert player.state == state


@pytest.mark.parametrize(
    ("media_id", "uri"),
    [
        ("spotify:album:abc", "spotify:album:abc"),
        (
            "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=1",
            "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M",
        ),
        ("https://open.spotify.com/intl-de/track/abc123", "spotify:track:abc123"),
    ],
)
def test_to_spotify_uri(media_id, uri):
    assert to_spotify_uri(media_id) == uri


def test_to_spotify_uri_rejects_other_urls():
    with pytest.raises(ServiceValidationError):
        to_spotify_uri("https://example.com/song.mp3")


async def test_simple_commands():
    player, client = make_player()
    await player.async_media_play()
    await player.async_media_pause()
    await player.async_media_next_track()
    await player.async_media_previous_track()
    await player.async_media_seek(30.5)
    await player.async_set_volume_level(0.42)
    await player.async_set_shuffle(False)
    await player.async_turn_on()
    await player.async_turn_off()
    assert client.send.await_args_list == [
        call("play"),
        call("pause"),
        call("skip_next"),
        call("skip_prev"),
        call("seek", position_ms=30500),
        call("set_volume", volume=42),
        call("set_shuffle", enabled=False),
        call("activate"),
        call("deactivate"),
    ]


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (
            RepeatMode.OFF,
            [
                call("set_repeat_track", enabled=False),
                call("set_repeat_context", enabled=False),
            ],
        ),
        (
            RepeatMode.ALL,
            [
                call("set_repeat_track", enabled=False),
                call("set_repeat_context", enabled=True),
            ],
        ),
        (
            RepeatMode.ONE,
            [
                call("set_repeat_context", enabled=False),
                call("set_repeat_track", enabled=True),
            ],
        ),
    ],
)
async def test_repeat_sequences(mode, expected):
    player, client = make_player()
    await player.async_set_repeat(mode)
    assert client.send.await_args_list == expected


async def test_play_media_and_enqueue():
    player, client = make_player()
    await player.async_play_media(
        MediaType.PLAYLIST, "https://open.spotify.com/playlist/abc"
    )
    await player.async_play_media(
        MediaType.MUSIC, "spotify:track:t", enqueue=MediaPlayerEnqueue.ADD
    )
    assert client.send.await_args_list == [
        call("play", uri="spotify:playlist:abc"),
        call("add_to_queue", uri="spotify:track:t"),
    ]
    with pytest.raises(ServiceValidationError):
        await player.async_play_media(
            MediaType.PLAYLIST, "spotify:album:a", enqueue=MediaPlayerEnqueue.ADD
        )


async def test_send_error_becomes_ha_error():
    player, client = make_player()
    client.send.side_effect = SoloistError("Not connected to Soloist")
    with pytest.raises(HomeAssistantError):
        await player.async_media_play()
