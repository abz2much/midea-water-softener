"""The coordinator lives in entry.runtime_data; the cloud session survives retries."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.midea_water_softener import binary_sensor, button, number, sensor, switch
from custom_components.midea_water_softener import time as time_platform
from custom_components.midea_water_softener.const import DOMAIN

from .conftest import LOGIN, login_ok

PKG = "custom_components.midea_water_softener"


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations):
    """Let Home Assistant find the integration in custom_components/."""


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="123456",
        title="Test softener",
        data={
            "account": "user@example.com",
            "password": "fake-password",
            "server": "MSmartHome (Global)",
            "device_id": 123456,
            "device_name": "Test softener",
            "scan_interval": 45,
        },
    )


def _coordinator_cls(first_refresh):
    cls = MagicMock()
    cls.return_value.async_config_entry_first_refresh = first_refresh
    return cls


@pytest.mark.parametrize(
    "platform", [sensor, switch, number, time_platform, button, binary_sensor]
)
async def test_platforms_read_the_coordinator_from_runtime_data(hass, platform):
    entry = MagicMock(entry_id="entry1", data={"device_id": 123456})
    entry.runtime_data = MagicMock()
    add = MagicMock()
    await platform.async_setup_entry(hass, entry, add)
    add.assert_called_once()


async def test_setup_stores_the_coordinator_in_runtime_data(hass, make_session):
    entry = _entry()
    entry.add_to_hass(hass)
    cls = _coordinator_cls(AsyncMock())
    with patch(f"{PKG}.async_get_clientsession", return_value=make_session({LOGIN: [login_ok()]})), \
         patch(f"{PKG}.WaterSoftenerCoordinator", cls), \
         patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data is cls.return_value
    assert entry.entry_id not in hass.data[DOMAIN]


async def test_a_setup_retry_does_not_log_in_again(hass, make_session):
    entry = _entry()
    entry.add_to_hass(hass)
    session = make_session({LOGIN: [login_ok()]})
    first_refresh = AsyncMock(side_effect=[ConfigEntryNotReady("device offline"), None])
    with patch(f"{PKG}.async_get_clientsession", return_value=session), \
         patch(f"{PKG}.WaterSoftenerCoordinator", _coordinator_cls(first_refresh)), \
         patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        assert entry.state is ConfigEntryState.SETUP_RETRY

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=15))
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert session.count(LOGIN) == 1


async def test_unload_cleans_everything_up(hass, make_session):
    entry = _entry()
    entry.add_to_hass(hass)
    with patch(f"{PKG}.async_get_clientsession", return_value=make_session({LOGIN: [login_ok()]})), \
         patch(f"{PKG}.WaterSoftenerCoordinator", _coordinator_cls(AsyncMock())), \
         patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()), \
         patch.object(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        assert f"{entry.entry_id}.cloud" in hass.data[DOMAIN]

        assert await hass.config_entries.async_unload(entry.entry_id)

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert not hasattr(entry, "runtime_data")
    assert hass.data[DOMAIN] == {}
