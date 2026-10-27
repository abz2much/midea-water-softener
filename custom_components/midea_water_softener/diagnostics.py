"""Diagnostics for the Midea water softener."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import (
    CONF_ACCOUNT,
    CONF_DEVICE_ID,
    CONF_KEY,
    CONF_PASSWORD,
    CONF_SERIAL_NUMBER,
    CONF_TOKEN,
    DOMAIN,
)
from .coordinator import WaterSoftenerConfigEntry

TO_REDACT = {
    CONF_ACCOUNT,
    CONF_PASSWORD,
    CONF_SERIAL_NUMBER,
    CONF_DEVICE_ID,
    CONF_TOKEN,
    CONF_KEY,
    "access_token",
    "accessToken",
    "uid",
    "randomData",
    "aes_key",
    "aes_iv",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: WaterSoftenerConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    integration = await async_get_integration(hass, DOMAIN)
    return {
        "integration_version": integration.version.string
        if integration.version
        else None,
        "poll_interval": coordinator.update_interval.total_seconds(),
        "entry": {
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": async_redact_data(entry.options, TO_REDACT),
        },
        "coordinator": {
            "data": async_redact_data(coordinator.data, TO_REDACT),
            "last_update_success": coordinator.last_update_success,
            "last_exception": str(coordinator.last_exception)
            if coordinator.last_exception
            else None,
        },
    }
