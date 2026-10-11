"""Media player entity for a Spotify Soloist Connect device."""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEnqueue,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    RepeatMode,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SoloistConfigEntry
from .client import SoloistClient, SoloistError
from .const import DOMAIN

STATUS_TO_STATE = {
    "playing": MediaPlayerState.PLAYING,
    "paused": MediaPlayerState.PAUSED,
    "buffering": MediaPlayerState.BUFFERING,
    "idle": MediaPlayerState.IDLE,
}

REPEAT_FROM_SOLOIST = {
    "off": RepeatMode.OFF,
    "context": RepeatMode.ALL,
    "track": RepeatMode.ONE,
}

ENTITY_TO_MEDIA_TYPE = {
    "track": MediaType.MUSIC,
    "episode": MediaType.PODCAST,
}

COVER_PREFERENCE = ("large", "xlarge", "default", "small")

OPEN_SPOTIFY_URL = re.compile(
    r"https?://open\.spotify\.com/(?:intl-[a-z-]+/)?"
    r"(track|album|playlist|artist|episode|show)/([A-Za-z0-9]+)"
)

SUPPORTED_FEATURES = (
    MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.SEEK
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.SHUFFLE_SET
    | MediaPlayerEntityFeature.REPEAT_SET
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.MEDIA_ENQUEUE
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoloistConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the Soloist media player."""
    async_add_entities([SoloistMediaPlayer(entry)])


def to_spotify_uri(media_id: str) -> str:
    """Accept spotify: URIs and open.spotify.com links."""
    if media_id.startswith("spotify:"):
        return media_id
    if match := OPEN_SPOTIFY_URL.match(media_id):
        return f"spotify:{match[1]}:{match[2]}"
    raise ServiceValidationError(
        f"Unsupported media id {media_id!r}: use a spotify: URI or open.spotify.com link"
    )


def _name(entity: dict[str, Any] | None) -> str | None:
    if not entity:
        return None
    return entity.get("decorations", {}).get("identity", {}).get("name")


class SoloistMediaPlayer(MediaPlayerEntity):
    """A Soloist device seen through its local WebSocket API.

    Soloist is a Spotify Connect receiver, so "off" means it is not the
    active Connect device: turn_on claims the session, turn_off releases it.
    """

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_supported_features = SUPPORTED_FEATURES
    _attr_volume_step = 0.05

    def __init__(self, entry: SoloistConfigEntry) -> None:
        self._client: SoloistClient = entry.runtime_data
        self._attr_unique_id = entry.unique_id or entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            name=entry.title,
            manufacturer="Spotify",
            model="Soloist",
            configuration_url="https://open.spotify.com",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._client.add_listener(self._on_change))

    @callback
    def _on_change(self) -> None:
        self.async_write_ha_state()

    # ---- state -------------------------------------------------------------

    @property
    def _pb(self) -> dict[str, Any]:
        return self._client.playback

    @property
    def _item(self) -> dict[str, Any]:
        return self._pb.get("item") or {}

    @property
    def _decorations(self) -> dict[str, Any]:
        return self._item.get("decorations") or {}

    @property
    def available(self) -> bool:
        return self._client.connected

    @property
    def state(self) -> MediaPlayerState:
        auth = self._client.auth
        if not auth.get("logged_in") or not auth.get("is_active"):
            return MediaPlayerState.OFF
        return STATUS_TO_STATE.get(self._pb.get("status"), MediaPlayerState.IDLE)

    @property
    def volume_level(self) -> float | None:
        volume = self._pb.get("volume")
        return None if volume is None else volume / 100

    @property
    def shuffle(self) -> bool | None:
        return (self._pb.get("options") or {}).get("shuffle")

    @property
    def repeat(self) -> RepeatMode | None:
        return REPEAT_FROM_SOLOIST.get((self._pb.get("options") or {}).get("repeat"))

    @property
    def media_content_id(self) -> str | None:
        return self._item.get("uri") or None

    @property
    def media_content_type(self) -> MediaType | str | None:
        return ENTITY_TO_MEDIA_TYPE.get(self._item.get("entity_type"), MediaType.MUSIC)

    @property
    def media_title(self) -> str | None:
        return _name(self._item)

    @property
    def media_artist(self) -> str | None:
        names = [
            name
            for creator in self._decorations.get("creators") or []
            if (name := _name(creator.get("entity")))
        ]
        return ", ".join(names) or None

    @property
    def media_album_name(self) -> str | None:
        return _name((self._decorations.get("parent") or {}).get("entity"))

    @property
    def media_playlist(self) -> str | None:
        return _name(self._pb.get("context"))

    @property
    def media_image_url(self) -> str | None:
        covers = (self._decorations.get("visual_identity") or {}).get("cover") or []
        by_size = {cover.get("size"): cover.get("url") for cover in covers}
        for size in COVER_PREFERENCE:
            if by_size.get(size):
                return by_size[size]
        return covers[0].get("url") if covers else None

    @property
    def media_image_remotely_accessible(self) -> bool:
        return True

    @property
    def media_duration(self) -> int | None:
        duration = (self._decorations.get("playback") or {}).get("duration_ms")
        return None if duration is None else duration // 1000

    @property
    def media_position(self) -> int | None:
        position = self._pb.get("position") or {}
        if "position_ms" not in position:
            return None
        return position["position_ms"] // 1000

    @property
    def media_position_updated_at(self) -> datetime | None:
        timestamp = (self._pb.get("position") or {}).get("timestamp_ms")
        if timestamp is None:
            return None
        return datetime.fromtimestamp(timestamp / 1000, UTC)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        context = self._pb.get("context") or {}
        upcoming = self._client.queue.get("upcoming") or []
        return {
            "context_uri": context.get("uri") or None,
            "queue": [
                {
                    "uri": entry.get("item", {}).get("uri"),
                    "name": _name(entry.get("item")),
                }
                for entry in upcoming[:10]
            ],
        }

    # ---- commands ----------------------------------------------------------

    async def _send(self, command: str, **fields: Any) -> None:
        try:
            await self._client.send(command, **fields)
        except SoloistError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_turn_on(self) -> None:
        await self._send("activate")

    async def async_turn_off(self) -> None:
        await self._send("deactivate")

    async def async_media_play(self) -> None:
        await self._send("play")

    async def async_media_pause(self) -> None:
        await self._send("pause")

    async def async_media_stop(self) -> None:
        await self._send("pause")

    async def async_media_next_track(self) -> None:
        await self._send("skip_next")

    async def async_media_previous_track(self) -> None:
        await self._send("skip_prev")

    async def async_media_seek(self, position: float) -> None:
        await self._send("seek", position_ms=int(position * 1000))

    async def async_set_volume_level(self, volume: float) -> None:
        await self._send("set_volume", volume=round(volume * 100))

    async def async_set_shuffle(self, shuffle: bool) -> None:
        await self._send("set_shuffle", enabled=shuffle)

    async def async_set_repeat(self, repeat: RepeatMode) -> None:
        # Order matters: Soloist documents these exact sequences.
        if repeat == RepeatMode.ONE:
            await self._send("set_repeat_context", enabled=False)
            await self._send("set_repeat_track", enabled=True)
        else:
            await self._send("set_repeat_track", enabled=False)
            await self._send("set_repeat_context", enabled=repeat == RepeatMode.ALL)

    async def async_play_media(
        self,
        media_type: MediaType | str,
        media_id: str,
        enqueue: MediaPlayerEnqueue | None = None,
        **kwargs: Any,
    ) -> None:
        uri = to_spotify_uri(media_id)
        if enqueue in (MediaPlayerEnqueue.ADD, MediaPlayerEnqueue.NEXT):
            if not uri.startswith("spotify:track:"):
                raise ServiceValidationError("Soloist can only queue single tracks")
            await self._send("add_to_queue", uri=uri)
            return
        await self._send("play", uri=uri)
