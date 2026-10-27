"""Config flow: MSmartHome credentials → device selection → local IP address."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .cloud import CannotConnect, InvalidAuth, MSmartHomeCloud, MSmartHomeError
from .const import (
    CONF_ACCOUNT,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_HOST,
    CONF_KEY,
    CONF_MODEL,
    CONF_SERIAL_NUMBER,
    CONF_SERVER,
    CONF_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DEVICE_TYPE,
    DOMAIN,
    SERVERS,
)
from .local import LocalError, LocalTransport
from .message import build_query, parse_response

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

_LOCAL_KEYS = (CONF_HOST, CONF_TOKEN, CONF_KEY)


def _local_schema(host: str = "") -> vol.Schema:
    """The softener's IP address. Blank means cloud only.

    A suggested value, not a default: the frontend leaves a cleared field out
    of the submission, and a default would fill the old address back in.
    """
    return vol.Schema(
        {vol.Optional(CONF_HOST, description={"suggested_value": host}): str}
    )


async def _async_find_local(
    cloud: MSmartHomeCloud, device_id: int, host: str
) -> tuple[dict[str, str], str | None]:
    """Fetch the token and key from the cloud and test them on the softener.

    Returns the entry data to save, or an error key for the form.
    """
    try:
        keys = await cloud.get_keys(device_id)
    except MSmartHomeError:
        return {}, "token_failed"
    if not keys:
        return {}, "token_failed"

    # The cloud may hold more than one pair; only the device knows which works.
    for pair in keys:
        transport = LocalTransport(host, device_id, pair["token"], pair["key"])
        try:
            reply = await transport.send(build_query())
        except LocalError as exc:
            _LOGGER.debug("Local test failed: %s", exc)
            continue
        if parse_response(reply) is not None:
            return {CONF_HOST: host, CONF_TOKEN: pair["token"], CONF_KEY: pair["key"]}, None
    return {}, "local_failed"


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
        self._entry_data: dict[str, Any] = {}

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
            self._entry_data = data
            return await self.async_step_local()

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

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask for the softener's IP address. Blank means cloud only."""
        errors: dict[str, str] = {}
        title = self._entry_data[CONF_DEVICE_NAME]
        host = ""

        if user_input is not None:
            host = user_input.get(CONF_HOST, "").strip()
            if not host:
                return self.async_create_entry(title=title, data=self._entry_data)
            local_data, error = await _async_find_local(
                self._cloud, self._entry_data[CONF_DEVICE_ID], host
            )
            if error is None:
                return self.async_create_entry(
                    title=title, data={**self._entry_data, **local_data}
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="local",
            data_schema=_local_schema(host),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Add, change or remove the softener's IP address.

        Uses the account and password already in the entry. Blank means cloud only.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input.get(CONF_HOST, "").strip()
            if not host:
                data = {k: v for k, v in entry.data.items() if k not in _LOCAL_KEYS}
                return self.async_update_reload_and_abort(entry, data=data)

            api_url = SERVERS.get(entry.data[CONF_SERVER], list(SERVERS.values())[0])
            cloud = MSmartHomeCloud(
                async_get_clientsession(self.hass),
                entry.data[CONF_ACCOUNT],
                entry.data[CONF_PASSWORD],
                api_url,
            )
            try:
                await cloud.login()
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                local_data, error = await _async_find_local(
                    cloud, entry.data[CONF_DEVICE_ID], host
                )
                if error is None:
                    return self.async_update_reload_and_abort(
                        entry, data_updates=local_data
                    )
                errors["base"] = error

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_local_schema(entry.data.get(CONF_HOST, "")),
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
