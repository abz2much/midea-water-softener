"""device.py: local first, the cloud as the fallback; and setup with local."""
from __future__ import annotations

import logging
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.midea_water_softener.const import ATTR_SALT_REMAINING, DOMAIN
from custom_components.midea_water_softener.coordinator import (
    WaterSoftenerCoordinator,
)
from custom_components.midea_water_softener.device import WaterSoftenerDevice
from custom_components.midea_water_softener.local import (
    LocalNoReply,
    LocalNotSent,
    LocalTransport,
)
from custom_components.midea_water_softener.message import (
    build_query,
    build_regen_now,
    build_set_inlet,
)

from .conftest import LOGIN, ROUTER, SEND, login_ok, send_reply, status_packet

PKG = "custom_components.midea_water_softener"
DEVICE = 123456
DOWN = aiohttp.ClientConnectionError("down")
LOCAL_STATUS = status_packet({7: 80})  # salt 80 %
CLOUD_STATUS = status_packet({7: 40})  # salt 40 %


class FakeLocal:
    """Stands in for LocalTransport. Each send takes the next scripted result."""

    def __init__(self, *results) -> None:
        self._results = deque(results)
        self.sent: list[bytes] = []

    async def send(self, frame: bytes) -> bytes:
        self.sent.append(frame)
        result = self._results.popleft()
        if isinstance(result, Exception):
            raise result
        return result


async def _device(make_session, make_cloud, local, sends, *, logged_in=True):
    session = make_session({SEND: sends})
    cloud = make_cloud(session)
    if logged_in:
        await cloud.login()
    return WaterSoftenerDevice(cloud, DEVICE, "Test softener", local=local), session


# ---------------------------------------------------------------- reads


async def test_local_is_used_when_configured(make_session, make_cloud):
    local = FakeLocal(LOCAL_STATUS)
    device, session = await _device(make_session, make_cloud, local, [])
    data = await device.refresh_status()
    assert data[ATTR_SALT_REMAINING] == 80
    assert local.sent == [build_query()]
    assert session.count(SEND) == 0


@pytest.mark.parametrize("error", [LocalNotSent("refused"), LocalNoReply("timeout")])
async def test_a_read_uses_the_cloud_when_local_fails(make_session, make_cloud, error):
    local = FakeLocal(error)
    device, session = await _device(
        make_session, make_cloud, local, [send_reply(CLOUD_STATUS)]
    )
    data = await device.refresh_status()
    assert data[ATTR_SALT_REMAINING] == 40
    assert session.count(SEND) == 1


async def test_cloud_only_when_local_is_not_configured(make_session, make_cloud):
    device, session = await _device(
        make_session, make_cloud, None, [send_reply(CLOUD_STATUS)]
    )
    data = await device.refresh_status()
    assert data[ATTR_SALT_REMAINING] == 40
    assert session.count(SEND) == 1


async def test_a_poll_fails_when_both_fail(make_session, make_cloud):
    local = FakeLocal(LocalNotSent("refused"))
    device, _ = await _device(make_session, make_cloud, local, [DOWN])
    coordinator = WaterSoftenerCoordinator(MagicMock(), MagicMock(), device)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_the_cloud_logs_in_when_first_needed(make_session, make_cloud):
    """Setup may skip the cloud login when only local works."""
    local = FakeLocal(LocalNotSent("refused"))
    device, session = await _device(
        make_session, make_cloud, local, [send_reply(CLOUD_STATUS)], logged_in=False
    )
    data = await device.refresh_status()
    assert data[ATTR_SALT_REMAINING] == 40
    assert session.count(LOGIN) == 1


# ---------------------------------------------------------------- writes


async def test_a_write_goes_local(make_session, make_cloud):
    local = FakeLocal(b"\xaa")
    device, session = await _device(make_session, make_cloud, local, [])
    await device.set_inlet(True)
    assert local.sent == [build_set_inlet(True)]
    assert session.count(SEND) == 0


async def test_an_unsent_write_uses_the_cloud(make_session, make_cloud):
    local = FakeLocal(LocalNotSent("refused"))
    device, session = await _device(make_session, make_cloud, local, [send_reply()])
    await device.regenerate_now()
    assert local.sent == [build_regen_now()]
    assert session.count(SEND) == 1


async def test_a_sent_write_with_no_reply_is_not_sent_again(make_session, make_cloud):
    """The softener may have acted already, so the cloud must not repeat it."""
    local = FakeLocal(LocalNoReply("timeout"))
    device, session = await _device(make_session, make_cloud, local, [])
    with pytest.raises(HomeAssistantError):
        await device.regenerate_now()
    assert session.count(SEND) == 0


async def test_a_write_fails_when_both_fail(make_session, make_cloud):
    local = FakeLocal(LocalNotSent("refused"))
    device, _ = await _device(make_session, make_cloud, local, [DOWN])
    with pytest.raises(HomeAssistantError):
        await device.set_inlet(True)


# ---------------------------------------------------------------- logging


def _mode_lines(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.INFO and r.name == f"{PKG}.device"
    ]


async def test_one_info_line_per_mode_switch(make_session, make_cloud, caplog):
    local = FakeLocal(
        LocalNotSent("refused"), LocalNotSent("refused"), LOCAL_STATUS, LOCAL_STATUS
    )
    device, _ = await _device(
        make_session,
        make_cloud,
        local,
        [send_reply(CLOUD_STATUS), send_reply(CLOUD_STATUS)],
    )
    caplog.set_level(logging.INFO)

    for _ in range(4):
        await device.refresh_status()

    lines = _mode_lines(caplog)
    assert len(lines) == 2
    assert "cloud" in lines[0]
    assert "local" in lines[1]


async def test_no_mode_line_while_local_keeps_working(make_session, make_cloud, caplog):
    local = FakeLocal(LOCAL_STATUS, LOCAL_STATUS)
    device, _ = await _device(make_session, make_cloud, local, [])
    caplog.set_level(logging.INFO)
    await device.refresh_status()
    await device.refresh_status()
    assert _mode_lines(caplog) == []


# ---------------------------------------------------------------- setup


def _entry(local: bool) -> MockConfigEntry:
    data = {
        "account": "user@example.com",
        "password": "fake-password",
        "server": "MSmartHome (Global)",
        "device_id": DEVICE,
        "device_name": "Test softener",
        "scan_interval": 45,
    }
    if local:
        data |= {"host": "192.0.2.10", "token": "ab" * 64, "key": "cd" * 32}
    return MockConfigEntry(domain=DOMAIN, unique_id=str(DEVICE), data=data)


@pytest.fixture
def _custom(enable_custom_integrations):
    """Let Home Assistant find the integration in custom_components/."""


def _coordinator_cls():
    cls = MagicMock()
    cls.return_value.async_config_entry_first_refresh = AsyncMock()
    return cls


@pytest.mark.usefixtures("_custom")
async def test_setup_gives_the_device_a_local_transport(hass, make_session):
    entry = _entry(local=True)
    entry.add_to_hass(hass)
    with patch(f"{PKG}.async_get_clientsession", return_value=make_session()), \
         patch(f"{PKG}.WaterSoftenerCoordinator", _coordinator_cls()) as cls, \
         patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
    device = cls.call_args.args[2]
    assert isinstance(device._local, LocalTransport)
    assert device._local.host == "192.0.2.10"
    assert device._local.port == 6444


@pytest.mark.usefixtures("_custom")
async def test_setup_without_local_has_no_local_transport(hass, make_session):
    entry = _entry(local=False)
    entry.add_to_hass(hass)
    with patch(f"{PKG}.async_get_clientsession", return_value=make_session()), \
         patch(f"{PKG}.WaterSoftenerCoordinator", _coordinator_cls()) as cls, \
         patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
    assert cls.call_args.args[2]._local is None


@pytest.mark.usefixtures("_custom")
async def test_setup_with_the_cloud_down_loads_on_local(hass, make_session):
    entry = _entry(local=True)
    entry.add_to_hass(hass)
    session = make_session({ROUTER: [DOWN]})
    with patch(f"{PKG}.async_get_clientsession", return_value=session), \
         patch(f"{PKG}.WaterSoftenerCoordinator", _coordinator_cls()), \
         patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.LOADED


@pytest.mark.usefixtures("_custom")
async def test_setup_with_the_cloud_down_and_no_local_retries(hass, make_session):
    entry = _entry(local=False)
    entry.add_to_hass(hass)
    session = make_session({ROUTER: [DOWN]})
    with patch(f"{PKG}.async_get_clientsession", return_value=session), \
         patch(f"{PKG}.WaterSoftenerCoordinator", _coordinator_cls()), \
         patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.usefixtures("_custom")
async def test_a_wrong_password_still_asks_to_sign_in_with_local(hass, make_session):
    entry = _entry(local=True)
    entry.add_to_hass(hass)
    session = make_session({LOGIN: [{"code": 1, "msg": "bad password"}]})
    with patch(f"{PKG}.async_get_clientsession", return_value=session), \
         patch(f"{PKG}.WaterSoftenerCoordinator", _coordinator_cls()), \
         patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
