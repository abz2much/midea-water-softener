"""DataUpdateCoordinator for the water softener."""
from __future__ import annotations

import logging
import traceback
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .device import WaterSoftenerDevice

_LOGGER = logging.getLogger(__name__)


class WaterSoftenerCoordinator(DataUpdateCoordinator[dict]):
    def __init__(
        self,
        hass: HomeAssistant,
        device: WaterSoftenerDevice,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{device.name}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.device = device

    async def _async_update_data(self) -> dict:
        _LOGGER.debug(
            "[%s] Polling device (id=%s)", self.device.name, self.device._device_id
        )
        try:
            data = await self.device.refresh_status()
        except Exception:
            _LOGGER.error(
                "[%s] Unexpected exception during refresh_status:\n%s",
                self.device.name,
                traceback.format_exc(),
            )
            raise UpdateFailed("Unexpected error polling device") from None

        _LOGGER.debug("[%s] refresh_status returned: %s", self.device.name, data)

        if data is None:
            _LOGGER.warning(
                "[%s] Device id=%s did not respond (refresh_status returned None). "
                "Check cloud connectivity and device online status.",
                self.device.name,
                self.device._device_id,
            )
            raise UpdateFailed(
                f"Device '{self.device.name}' (id={self.device._device_id}) did not respond"
            )

        return data
