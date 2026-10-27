"""One DeviceInfo for every entity of a config entry."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_MODEL, CONF_SERIAL_NUMBER, DOMAIN

# Used by entries made before the model was saved.
DEFAULT_MODEL = "QS2476-90"


def build_device_info(entry: ConfigEntry) -> DeviceInfo:
    info = DeviceInfo(
        identifiers={(DOMAIN, str(entry.data["device_id"]))},
        name=entry.data.get("device_name", "Water Softener"),
        manufacturer="Midea",
        model=entry.data.get(CONF_MODEL) or DEFAULT_MODEL,
    )
    if serial_number := entry.data.get(CONF_SERIAL_NUMBER):
        info["serial_number"] = serial_number
    return info
