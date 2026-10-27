"""Config flow: MSmartHome credentials → device selection."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .cloud import CannotConnect, InvalidAuth, MSmartHomeCloud
from .const import (
    CONF_ACCOUNT,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_MODEL,
    CONF_SERIAL_NUMBER,
    CONF_SERVER,
    DEFAULT_SCAN_INTERVAL,
    DEVICE_TYPE,
    DOMAIN,
    SERVERS,
)

_LOGGER = logging.getLogger(__name__)

# Poll interval limits, in seconds. Used by setup and by the options flow.
_SCAN_INTERVAL = vol.All(int, vol.Range(min=10, max=300))

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCOUNT): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_SERVER, default=list(SERVERS.keys())[0]): vol.In(list(SERVERS.keys())),
    }
)


class WaterSoftenerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    # 2: entity unique IDs use the device ID. A minor bump, so an older release
    # can still load the entry (see async_migrate_entry).
    MINOR_VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return WaterSoftenerOptionsFlow()

    def __init__(self) -> None:
        self._account: str = ""
        self._password: str = ""
        self._server: str = ""
        self._cloud: MSmartHomeCloud | None = None
        self._appliances: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
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
    ) -> config_entries.ConfigFlowResult:
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
            appliance = next(
                (a for a in self._appliances if a["device_id"] == device_id), {}
            )

            await self.async_set_unique_id(str(device_id))
            self._abort_if_unique_id_configured()

            data = {
                CONF_ACCOUNT: self._account,
                CONF_PASSWORD: self._password,
                CONF_SERVER: self._server,
                CONF_DEVICE_ID: device_id,
                CONF_DEVICE_NAME: device_name,
                CONF_SCAN_INTERVAL: scan_interval,
            }
            # The cloud already returns these; save them when it has them.
            if appliance.get("model"):
                data[CONF_MODEL] = appliance["model"]
            if appliance.get("sn"):
                data[CONF_SERIAL_NUMBER] = appliance["sn"]
            return self.async_create_entry(title=device_name, data=data)

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): vol.In(device_options),
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): _SCAN_INTERVAL,
            }
        )

        return self.async_show_form(
            step_id="device",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> config_entries.ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask for a new password. The account and server stay as they are."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            api_url = SERVERS.get(entry.data[CONF_SERVER], list(SERVERS.values())[0])
            cloud = MSmartHomeCloud(
                async_get_clientsession(self.hass),
                entry.data[CONF_ACCOUNT],
                user_input[CONF_PASSWORD],
                api_url,
            )
            try:
                await cloud.login()
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"account": entry.data[CONF_ACCOUNT]},
            errors=errors,
        )


class WaterSoftenerOptionsFlow(config_entries.OptionsFlowWithReload):
    """Change the poll interval after setup. The entry reloads when it is saved."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Required(CONF_SCAN_INTERVAL, default=current): _SCAN_INTERVAL}
            ),
        )
