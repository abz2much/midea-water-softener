"""Device abstraction: wraps local and cloud comms + message protocol for one water softener."""
from __future__ import annotations

import logging

from homeassistant.exceptions import HomeAssistantError

from .cloud import MSmartHomeCloud, MSmartHomeError
from .const import (
    ATTR_ANTI_LEAKAGE,
    ATTR_DEVICE_STATUS,
    ATTR_ERROR,
    ATTR_FLOW_RATE,
    ATTR_HARDNESS,
    ATTR_INLET,
    ATTR_LEAK_DETECTED,
    ATTR_LEAK_THRESHOLD,
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
from .local import LocalNoReply, LocalNotSent, LocalTransport, LocalUnavailable
from .message import (
    DeviceStatus,
    build_query,
    build_regen_now,
    build_set_anti_leakage,
    build_set_hardness,
    build_set_inlet,
    build_set_leak_limit,
    build_set_regen_interval,
    build_set_regen_time,
    build_set_soften,
    parse_response,
)

_LOGGER = logging.getLogger(__name__)

_MODE_LOCAL = "local"
_MODE_CLOUD = "cloud"


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
        ATTR_LEAK_THRESHOLD: s.leak_threshold,
        ATTR_LEAK_DETECTED: s.leak_detected,
        ATTR_HARDNESS: s.water_hardness,
        ATTR_REGEN_INTERVAL: s.regen_interval,
        ATTR_REGEN_HOUR: s.regen_hour,
        ATTR_REGEN_MIN: s.regen_min,
        ATTR_REGENERATING: s.regenerating,
        ATTR_STANDBY: s.standby,
        ATTR_ERROR: s.error,
    }


class WaterSoftenerDevice:
    """Represents one physical water softener.

    With a local transport, every request goes over the LAN first and uses the
    cloud only when local fails. Without one, it is cloud only.
    """

    def __init__(
        self,
        cloud: MSmartHomeCloud,
        device_id: int,
        name: str,
        local: LocalTransport | None = None,
    ) -> None:
        self._cloud = cloud
        self._local = local
        self._device_id = device_id
        self.name = name
        self.available = False
        self.attributes: dict = {}
        self._mode = _MODE_LOCAL if local else _MODE_CLOUD

    def _set_mode(self, mode: str, reason: str = "") -> None:
        """Log one INFO line when the path changes, not one per request."""
        if mode == self._mode:
            return
        self._mode = mode
        if mode == _MODE_CLOUD:
            _LOGGER.info(
                "[%s] Local connection failed (%s); using the cloud", self.name, reason
            )
        else:
            _LOGGER.info("[%s] Local connection works again; using local", self.name)

    def _disable_local(self, reason: str) -> None:
        """midea-local can't be used: turn local off for good, with one WARNING."""
        self._local = None
        self._mode = _MODE_CLOUD
        _LOGGER.warning(
            "[%s] Local control is off, midea-local cannot be used (%s); using the cloud only",
            self.name,
            reason,
        )

    async def _request(self, message: bytes, *, write: bool) -> bytearray | None:
        """Send one frame: local first, then the cloud.

        A write that was sent locally but got no reply is not sent again over
        the cloud, because the softener may already have acted on it.
        """
        if self._local is not None:
            try:
                reply = await self._local.send(message)
            except LocalNotSent as exc:
                self._set_mode(_MODE_CLOUD, str(exc))
            except LocalUnavailable as exc:
                self._disable_local(str(exc))
                if write and exc.sent:
                    raise HomeAssistantError(
                        f"{self.name} did not confirm the command over the local network"
                    ) from exc
            except LocalNoReply as exc:
                self._set_mode(_MODE_CLOUD, str(exc))
                if write:
                    raise HomeAssistantError(
                        f"{self.name} did not confirm the command over the local network"
                    ) from exc
            else:
                self._set_mode(_MODE_LOCAL)
                return bytearray(reply)
            await self._cloud.ensure_logged_in()
        return await self._cloud.send_command(self._device_id, message)

    async def refresh_status(self) -> dict | None:
        """Poll the device and return updated attributes, or None on failure."""
        query = build_query()
        raw = await self._request(query, write=False)
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
                self.name, len(raw), raw.hex(),
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

    async def set_leak_limit(self, volume_l: int, protection_on: bool | None) -> None:
        # The command also carries the protection on/off state. Never guess it:
        # a wrong value would switch the protection off or on.
        if protection_on is None:
            raise HomeAssistantError(
                f"Cannot set the leak limit on {self.name} until its protection state is known"
            )
        await self._send(build_set_leak_limit(protection_on, volume_l))

    async def set_hardness(self, ppm: int) -> None:
        await self._send(build_set_hardness(ppm))

    async def set_regen_interval(self, days: int) -> None:
        await self._send(build_set_regen_interval(days))

    async def set_regen_time(self, hour: int, minute: int) -> None:
        await self._send(build_set_regen_time(hour, minute))

    async def regenerate_now(self) -> None:
        await self._send(build_regen_now())

    async def _send(self, message: bytes) -> None:
        try:
            result = await self._request(message, write=True)
        except MSmartHomeError as exc:
            raise HomeAssistantError(
                f"Could not send the command to {self.name}: {exc}"
            ) from exc
        if result is None:
            _LOGGER.warning("[%s] Command send failed or no reply", self._device_id)
            raise HomeAssistantError(f"Could not send the command to {self.name}")
