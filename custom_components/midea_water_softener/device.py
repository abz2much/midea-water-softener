"""Device abstraction: wraps cloud comms + message protocol for one water softener."""
from __future__ import annotations

import logging

from homeassistant.exceptions import HomeAssistantError

from .cloud import MSmartHomeCloud
from .const import (
    ATTR_ANTI_LEAKAGE,
    ATTR_DEVICE_STATUS,
    ATTR_ERROR,
    ATTR_FLOW_RATE,
    ATTR_HARDNESS,
    ATTR_INLET,
    ATTR_REGEN_HOUR,
    ATTR_REGEN_INTERVAL,
    ATTR_REGEN_MIN,
    ATTR_REGEN_SECONDS_REMAINING,
    ATTR_REGENERATING,
    ATTR_SALT_REMAINING,
    ATTR_SOFT_WATER_REMAINING,
    ATTR_SOFTEN,
    ATTR_STANDBY,
    ATTR_USE_DAYS,
    ATTR_WATER_CONSUMPTION_TOTAL,
    STATUS_NORMAL,
    STATUS_REGENERATING,
    STATUS_STANDBY,
)
from .message import (
    DeviceStatus,
    build_query,
    build_regen_now,
    build_set_anti_leakage,
    build_set_hardness,
    build_set_inlet,
    build_set_regen_interval,
    build_set_regen_time,
    build_set_soften,
    parse_response,
)

_LOGGER = logging.getLogger(__name__)


def _status_to_dict(s: DeviceStatus) -> dict:
    """Flatten a DeviceStatus into the coordinator data dict."""
    if s.regenerating:
        status_str = STATUS_REGENERATING
    elif s.standby:
        status_str = STATUS_STANDBY
    else:
        status_str = STATUS_NORMAL

    return {
        ATTR_SOFT_WATER_REMAINING: s.soft_water_remaining,
        ATTR_FLOW_RATE: s.flow_rate,
        ATTR_SALT_REMAINING: s.salt_remaining,
        ATTR_DEVICE_STATUS: status_str,
        ATTR_WATER_CONSUMPTION_TOTAL: s.water_consumption_total,
        ATTR_USE_DAYS: s.use_days,
        ATTR_REGEN_SECONDS_REMAINING: s.regen_seconds_remaining,
        ATTR_SOFTEN: s.soften,
        ATTR_INLET: s.inlet,
        ATTR_ANTI_LEAKAGE: s.anti_leakage,
        ATTR_HARDNESS: s.water_hardness,
        ATTR_REGEN_INTERVAL: s.regen_interval,
        ATTR_REGEN_HOUR: s.regen_hour,
        ATTR_REGEN_MIN: s.regen_min,
        ATTR_REGENERATING: s.regenerating,
        ATTR_STANDBY: s.standby,
        ATTR_ERROR: s.error,
    }


class WaterSoftenerDevice:
    """Represents one physical water softener on the Midea cloud."""

    def __init__(
        self,
        cloud: MSmartHomeCloud,
        device_id: int,
        name: str,
    ) -> None:
        self._cloud = cloud
        self._device_id = device_id
        self.name = name
        self.available = False
        self.attributes: dict = {}

    async def refresh_status(self) -> dict | None:
        """Poll the device and return updated attributes, or None on failure."""
        query = build_query()
        raw = await self._cloud.send_command(self._device_id, query)
        if raw is None:
            _LOGGER.warning(
                "[%s] send_command returned None for id=%s — check AES keys and cloud API logs",
                self.name, self._device_id,
            )
            self.available = False
            return None

        status = parse_response(raw)
        if status is None:
            _LOGGER.warning(
                "[%s] Could not parse status response (len=%d, hex=%s)",
                self._device_id, len(raw), raw.hex(),
            )
            self.available = False
            return None

        self.available = True
        self.attributes = _status_to_dict(status)
        return self.attributes

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    async def set_soften(self, on: bool) -> None:
        await self._send(build_set_soften(on))

    async def set_inlet(self, on: bool) -> None:
        await self._send(build_set_inlet(on))

    async def set_anti_leakage(self, on: bool) -> None:
        await self._send(build_set_anti_leakage(on))

    async def set_hardness(self, ppm: int) -> None:
        await self._send(build_set_hardness(ppm))

    async def set_regen_interval(self, days: int) -> None:
        await self._send(build_set_regen_interval(days))

    async def set_regen_time(self, hour: int, minute: int) -> None:
        await self._send(build_set_regen_time(hour, minute))

    async def regenerate_now(self) -> None:
        await self._send(build_regen_now())

    async def _send(self, message: bytes) -> None:
        result = await self._cloud.send_command(self._device_id, message)
        if result is None:
            _LOGGER.warning("[%s] Command send failed or no reply", self._device_id)
            raise HomeAssistantError(f"Could not send the command to {self.name}")
