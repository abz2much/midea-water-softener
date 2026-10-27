"""Bug 1: the cloud session recovers from expiry and reports errors clearly."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import aiohttp
import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from custom_components.midea_water_softener import async_setup_entry
from custom_components.midea_water_softener.cloud import (
    CannotConnect,
    InvalidAuth,
    SessionExpired,
)
from custom_components.midea_water_softener.const import (
    CONF_ACCOUNT,
    CONF_DEVICE_ID,
    CONF_SERVER,
    DOMAIN,
    SERVERS,
)

from .conftest import (
    EXPIRED,
    LOGIN,
    LOGIN_ID,
    ROUTER,
    SEND,
    login_ok,
    send_reply,
)

DEVICE = 123456


async def test_expired_session_logs_in_again_and_retries(make_session, make_cloud):
    session = make_session(
        {LOGIN: [login_ok("one"), login_ok("two")], SEND: [EXPIRED, send_reply(b"\x07")]}
    )
    cloud = make_cloud(session)
    await cloud.login()

    reply = await cloud.send_command(DEVICE, b"\x01")

    assert reply == bytearray(b"\x07")
    assert session.count(SEND) == 2
    assert session.count(LOGIN) == 2


async def test_second_expiry_gives_up_without_looping(make_session, make_cloud):
    session = make_session(
        {LOGIN: [login_ok("one"), login_ok("two")], SEND: [EXPIRED, EXPIRED]}
    )
    cloud = make_cloud(session)
    await cloud.login()

    with pytest.raises(SessionExpired):
        await cloud.send_command(DEVICE, b"\x01")

    assert session.count(SEND) == 2
    assert session.count(LOGIN) == 2


async def test_bad_password_raises_invalid_auth(make_session, make_cloud):
    session = make_session({LOGIN: [{"code": 1, "msg": "invalid password"}]})
    with pytest.raises(InvalidAuth):
        await make_cloud(session).login()


async def test_network_failure_raises_cannot_connect(make_session, make_cloud):
    session = make_session({ROUTER: [aiohttp.ClientConnectionError("down")]})
    with pytest.raises(CannotConnect):
        await make_cloud(session).login()


def _entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.data = {
        CONF_ACCOUNT: "user@example.com",
        "password": "fake-password",
        CONF_SERVER: list(SERVERS)[0],
        CONF_DEVICE_ID: DEVICE,
    }
    return entry


async def _setup(session):
    hass = MagicMock()
    hass.data = {}
    with patch(
        "custom_components.midea_water_softener.async_get_clientsession",
        return_value=session,
    ):
        return await async_setup_entry(hass, _entry())


async def test_setup_bad_password_raises_auth_failed(make_session):
    session = make_session({LOGIN: [{"code": 1, "msg": "invalid password"}]})
    with pytest.raises(ConfigEntryAuthFailed):
        await _setup(session)


async def test_setup_network_failure_raises_not_ready(make_session):
    session = make_session({ROUTER: [aiohttp.ClientConnectionError("down")]})
    with pytest.raises(ConfigEntryNotReady):
        await _setup(session)
