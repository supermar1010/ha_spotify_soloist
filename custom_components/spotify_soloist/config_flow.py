"""Config flow for Spotify Soloist."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import SoloistClient, SoloistError
from .const import DEFAULT_HOST, DEFAULT_PORT, DOMAIN


class SoloistConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for the Soloist WebSocket endpoint and verify it answers."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host, port = user_input[CONF_HOST], user_input[CONF_PORT]
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()
            client = SoloistClient(async_get_clientsession(self.hass), host, port)
            try:
                auth = await client.probe()
            except SoloistError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=auth.get("device_name") or "Spotify Soloist",
                    data={CONF_HOST: host, CONF_PORT: port},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )
