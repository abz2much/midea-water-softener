"""Midea Water Softener integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
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
from .coordinator import WaterSoftenerCoordinator
from .device import WaterSoftenerDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.TIME,
    Platform.BUTTON,
]

# hass.data[DOMAIN] stores two keys per entry:
#   entry.entry_id        → WaterSoftenerCoordinator
#   entry.entry_id + ".cloud" → MSmartHomeCloud (persists across setup retries)
_CLOUD_SUFFIX = ".cloud"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    account = entry.data[CONF_ACCOUNT]
    password = entry.data[CONF_PASSWORD]
    server = entry.data[CONF_SERVER]
    device_id = entry.data[CONF_DEVICE_ID]
    device_name = entry.data.get(CONF_DEVICE_NAME, "Water Softener")
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    domain_data = hass.data.setdefault(DOMAIN, {})
    cloud_key = entry.entry_id + _CLOUD_SUFFIX

    # Reuse an existing authenticated cloud session so that setup retries
    # (triggered by ConfigEntryNotReady from a failed first_refresh) do not
    # call login() again and replace the session AES key mid-flight.
    cloud: MSmartHomeCloud | None = domain_data.get(cloud_key)
    if cloud is not None and cloud.is_logged_in:
        _LOGGER.debug("Reusing existing cloud session for %s", device_name)
    else:
        api_url = SERVERS.get(server, list(SERVERS.values())[0])
        session = async_get_clientsession(hass)
        cloud = MSmartHomeCloud(session, account, password, api_url)
        try:
            await cloud.login()
        except InvalidAuth as exc:
            raise ConfigEntryAuthFailed("Midea login failed: check your password") from exc
        except CannotConnect as exc:
            raise ConfigEntryNotReady("Cannot reach the Midea cloud") from exc
        domain_data[cloud_key] = cloud
        _LOGGER.debug("New cloud session established for %s", device_name)

    device = WaterSoftenerDevice(cloud, device_id, device_name)
    coordinator = WaterSoftenerCoordinator(hass, device, scan_interval)

    await coordinator.async_config_entry_first_refresh()

    domain_data[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        domain_data = hass.data.get(DOMAIN, {})
        domain_data.pop(entry.entry_id, None)
        domain_data.pop(entry.entry_id + _CLOUD_SUFFIX, None)
    return unloaded
