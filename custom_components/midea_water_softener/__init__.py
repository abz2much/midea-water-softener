"""Midea Water Softener integration."""
from __future__ import annotations

import logging

from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .cloud import CannotConnect, InvalidAuth, MSmartHomeCloud
from .const import (
    CONF_ACCOUNT,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_HOST,
    CONF_KEY,
    CONF_SERVER,
    CONF_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SERVERS,
)
from .coordinator import WaterSoftenerConfigEntry, WaterSoftenerCoordinator
from .device import WaterSoftenerDevice
from .local import LocalTransport, unavailable_reason
from .migration import async_migrate_unique_ids

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.TIME,
    Platform.BUTTON,
]

# The coordinator is in entry.runtime_data. hass.data[DOMAIN] only keeps
#   entry.entry_id + ".cloud" → MSmartHomeCloud (persists across setup retries)
_CLOUD_SUFFIX = ".cloud"


async def async_migrate_entry(hass: HomeAssistant, entry: WaterSoftenerConfigEntry) -> bool:
    """Bring an older entry up to date.

    Minor 2: entity unique IDs use the device ID. Only the minor version is
    bumped, so an older release still loads the entry (it will make its own
    entities, though; see the release notes).
    """
    if entry.version > 1:
        return False  # saved by a newer major version
    if entry.minor_version < 2:
        await async_migrate_unique_ids(hass, entry)
        hass.config_entries.async_update_entry(entry, minor_version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: WaterSoftenerConfigEntry) -> bool:
    account = entry.data[CONF_ACCOUNT]
    password = entry.data[CONF_PASSWORD]
    server = entry.data[CONF_SERVER]
    device_id = entry.data[CONF_DEVICE_ID]
    device_name = entry.data.get(CONF_DEVICE_NAME, "Water Softener")
    # An option set after setup wins over the value saved at setup.
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )

    # Local control needs all three; without them the integration is cloud only.
    local: LocalTransport | None = None
    if all(entry.data.get(k) for k in (CONF_HOST, CONF_TOKEN, CONF_KEY)):
        # The first import of midea-local reads from disk: keep it off the loop.
        reason = await hass.async_add_executor_job(unavailable_reason)
        if reason:
            _LOGGER.warning(
                "Local control for %s is off (%s); using the cloud only",
                device_name,
                reason,
            )
        else:
            local = LocalTransport(
                entry.data[CONF_HOST],
                device_id,
                entry.data[CONF_TOKEN],
                entry.data[CONF_KEY],
            )

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
            if local is None:
                raise ConfigEntryNotReady("Cannot reach the Midea cloud") from exc
            # Start on local. The device logs in when it first needs the cloud.
            _LOGGER.info(
                "Cannot reach the Midea cloud; starting %s on the local connection",
                device_name,
            )
        else:
            _LOGGER.debug("New cloud session established for %s", device_name)
        domain_data[cloud_key] = cloud

    device = WaterSoftenerDevice(cloud, device_id, device_name, local=local)
    coordinator = WaterSoftenerCoordinator(hass, entry, device, scan_interval)

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        # Do not keep a session made with a password that no longer works, or a
        # reload after the reauth form would reuse it instead of logging in.
        domain_data.pop(cloud_key, None)
        raise

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WaterSoftenerConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        domain_data = hass.data.get(DOMAIN, {})
        domain_data.pop(entry.entry_id + _CLOUD_SUFFIX, None)
    return unloaded
