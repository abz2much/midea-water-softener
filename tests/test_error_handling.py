"""Cloud errors are handled above cloud.py: in the device and the coordinator."""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import aiohttp
import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.midea_water_softener.coordinator import (
    WaterSoftenerCoordinator,
)
from custom_components.midea_water_softener.device import WaterSoftenerDevice

from .conftest import EXPIRED, LOGIN, SEND, login_ok

DEVICE = 123456

# The cloud goes down after we are logged in.
DOWN = aiohttp.ClientConnectionError("down")


async def _device(make_session, make_cloud, routes):
    session = make_session(routes)
    cloud = make_cloud(session)
    await cloud.login()
    return WaterSoftenerDevice(cloud, DEVICE, "Test softener")


def _coordinator(device) -> WaterSoftenerCoordinator:
    # HA reports a coordinator built without a config entry; that needs a
    # running frame helper, which these tests do not have.
    with patch("homeassistant.helpers.frame.report_usage"):
        return WaterSoftenerCoordinator(MagicMock(), device)


async def test_command_with_cloud_down_raises_home_assistant_error(
    make_session, make_cloud
):
    device = await _device(make_session, make_cloud, {SEND: [DOWN]})
    with pytest.raises(HomeAssistantError):
        await device.set_inlet(True)


async def test_poll_with_cloud_down_raises_update_failed_without_traceback(
    make_session, make_cloud, caplog
):
    device = await _device(make_session, make_cloud, {SEND: [DOWN]})
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(UpdateFailed):
            await _coordinator(device)._async_update_data()

    assert not [r for r in caplog.records if r.exc_info]
    assert "Traceback" not in caplog.text


async def test_poll_with_bad_password_raises_auth_failed(make_session, make_cloud):
    # The session expires, then the new login is rejected.
    device = await _device(
        make_session,
        make_cloud,
        {
            SEND: [EXPIRED],
            LOGIN: [login_ok(), {"code": 1, "msg": "invalid password"}],
        },
    )
    with pytest.raises(ConfigEntryAuthFailed):
        await _coordinator(device)._async_update_data()
