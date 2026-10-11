"""Spotify Soloist integration: control a local Soloist Connect player."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import SoloistClient

PLATFORMS = [Platform.MEDIA_PLAYER]

type SoloistConfigEntry = ConfigEntry[SoloistClient]


async def async_setup_entry(hass: HomeAssistant, entry: SoloistConfigEntry) -> bool:
    """Set up Soloist from a config entry."""
    client = SoloistClient(
        async_get_clientsession(hass), entry.data[CONF_HOST], entry.data[CONF_PORT]
    )
    client.start()
    entry.runtime_data = client
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SoloistConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.stop()
    return unloaded
