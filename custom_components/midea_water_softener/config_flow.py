"""Config flow: MSmartHome credentials → device selection."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .cloud import CannotConnect, InvalidAuth, MSmartHomeCloud
from .const import (
    CONF_ACCOUNT,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_SERVER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SERVERS,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCOUNT): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_SERVER, default=list(SERVERS.keys())[0]): vol.In(list(SERVERS.keys())),
    }
)


class WaterSoftenerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._account: str = ""
        self._password: str = ""
        self._server: str = ""
        self._cloud: MSmartHomeCloud | None = None
        self._appliances: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._account = user_input[CONF_ACCOUNT]
            self._password = user_input[CONF_PASSWORD]
            self._server = user_input[CONF_SERVER]

            api_url = SERVERS[self._server]
            session = async_get_clientsession(self.hass)
            cloud = MSmartHomeCloud(session, self._account, self._password, api_url)

            try:
                await cloud.login()
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                from .const import DEVICE_TYPE
                all_appliances = await cloud.list_appliances()
                self._appliances = [a for a in all_appliances if a["type"] == DEVICE_TYPE]
                self._cloud = cloud

                if not self._appliances:
                    errors["base"] = "no_devices"
                else:
                    return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        device_options = {
            str(a["device_id"]): f"{a['name']} ({a['device_id']})"
            for a in self._appliances
        }

        if user_input is not None:
            device_id = int(user_input[CONF_DEVICE_ID])
            device_name = next(
                (a["name"] for a in self._appliances if a["device_id"] == device_id),
                "Water Softener",
            )
            scan_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

            await self.async_set_unique_id(str(device_id))
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=device_name,
                data={
                    CONF_ACCOUNT: self._account,
                    CONF_PASSWORD: self._password,
                    CONF_SERVER: self._server,
                    CONF_DEVICE_ID: device_id,
                    CONF_DEVICE_NAME: device_name,
                    CONF_SCAN_INTERVAL: scan_interval,
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): vol.In(device_options),
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                    int, vol.Range(min=10, max=300)
                ),
            }
        )

        return self.async_show_form(
            step_id="device",
            data_schema=schema,
            errors=errors,
        )
