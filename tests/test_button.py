"""Regenerate Now refreshes after a good press, and not after a failed one."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.midea_water_softener.button import RegenNowButton
from custom_components.midea_water_softener.device import WaterSoftenerDevice


def _button(reply):
    cloud = MagicMock()
    cloud.send_command = AsyncMock(return_value=reply)
    coordinator = MagicMock()
    coordinator.device = WaterSoftenerDevice(cloud, 123456, "Test softener")
    coordinator.async_request_refresh = AsyncMock()
    entry = MagicMock(entry_id="entry1", data={"device_id": 123456})
    return RegenNowButton(coordinator, entry), coordinator, cloud


async def test_a_good_press_sends_and_then_refreshes():
    button, coordinator, cloud = _button(bytearray(b"\x01"))
    await button.async_press()
    cloud.send_command.assert_awaited_once()
    coordinator.async_request_refresh.assert_awaited_once()


async def test_a_press_with_no_device_reply_still_refreshes():
    # Cloud code 1306 (delivered, no reply) comes back as empty bytes: success.
    button, coordinator, _ = _button(bytearray())
    await button.async_press()
    coordinator.async_request_refresh.assert_awaited_once()


async def test_a_failed_press_raises_and_does_not_refresh():
    button, coordinator, _ = _button(None)
    with pytest.raises(HomeAssistantError):
        await button.async_press()
    coordinator.async_request_refresh.assert_not_awaited()
