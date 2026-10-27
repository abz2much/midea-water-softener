"""Bug 2: a failed command raises an error instead of only logging."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.midea_water_softener.device import WaterSoftenerDevice
from custom_components.midea_water_softener.switch import (
    SWITCH_DESCRIPTIONS,
    WaterSoftenerSwitch,
)

from .conftest import SEND, send_reply

DEVICE = 123456
INLET = next(d for d in SWITCH_DESCRIPTIONS if d.key == "inlet")


async def _device(make_session, make_cloud, send_replies):
    session = make_session({SEND: send_replies})
    cloud = make_cloud(session)
    await cloud.login()
    return WaterSoftenerDevice(cloud, DEVICE, "Test softener")


async def test_failed_send_raises_home_assistant_error(make_session, make_cloud):
    device = await _device(make_session, make_cloud, [{"code": 9999, "msg": "bad"}])
    with pytest.raises(HomeAssistantError):
        await device.set_inlet(True)


async def test_no_async_reply_1306_counts_as_success(make_session, make_cloud):
    device = await _device(
        make_session,
        make_cloud,
        [{"code": 1306, "msg": "The async reply does not exist"}],
    )
    await device.set_inlet(False)


async def test_good_send_still_works(make_session, make_cloud):
    device = await _device(make_session, make_cloud, [send_reply()])
    await device.set_inlet(True)


async def test_failed_command_does_not_refresh_coordinator(make_session, make_cloud):
    device = await _device(make_session, make_cloud, [{"code": 9999, "msg": "bad"}])
    coordinator = MagicMock()
    coordinator.device = device
    coordinator.async_request_refresh = AsyncMock()
    entry = MagicMock(entry_id="entry1", data={"device_id": DEVICE})
    switch = WaterSoftenerSwitch(coordinator, entry, INLET)

    with pytest.raises(HomeAssistantError):
        await switch.async_turn_on()

    coordinator.async_request_refresh.assert_not_awaited()
