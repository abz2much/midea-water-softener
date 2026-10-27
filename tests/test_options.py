"""Options: change the poll interval after setup."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.midea_water_softener.const import (
    CONF_ACCOUNT,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_SERVER,
    DOMAIN,
    SERVERS,
)

from .conftest import LOGIN, login_ok

PKG = "custom_components.midea_water_softener"


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations):
    """Let Home Assistant find the integration in custom_components/."""


def _entry(**extra) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="123456",
        title="Test softener",
        data={
            CONF_ACCOUNT: "user@example.com",
            "password": "fake-password",
            CONF_SERVER: list(SERVERS)[0],
            CONF_DEVICE_ID: 123456,
            CONF_DEVICE_NAME: "Test softener",
            "scan_interval": 45,
        },
        **extra,
    )


async def _scan_interval_used(hass, make_session, entry) -> int:
    """Set the entry up with a stand-in coordinator; return the interval it got."""
    entry.add_to_hass(hass)
    coordinator_cls = MagicMock()
    coordinator_cls.return_value.async_config_entry_first_refresh = AsyncMock()
    with patch(f"{PKG}.async_get_clientsession", return_value=make_session({LOGIN: [login_ok()]})), \
         patch(f"{PKG}.WaterSoftenerCoordinator", coordinator_cls), \
         patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
    return coordinator_cls.call_args.args[3]


async def test_no_option_uses_the_setup_value(hass, make_session):
    assert await _scan_interval_used(hass, make_session, _entry()) == 45


async def test_an_option_overrides_the_setup_value(hass, make_session):
    entry = _entry(options={"scan_interval": 120})
    assert await _scan_interval_used(hass, make_session, entry) == 120


async def test_options_form_starts_with_the_current_value(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    assert list(result["data_schema"].schema) == ["scan_interval"]
    assert result["data_schema"]({}) == {"scan_interval": 45}


@pytest.mark.parametrize("value", [9, 301, 0, -5])
async def test_out_of_range_is_refused(hass, value):
    entry = _entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {"scan_interval": value}
        )
    assert entry.options == {}


@pytest.mark.parametrize("value", [10, 300])
async def test_the_limits_are_accepted(hass, value):
    entry = _entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": value}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"scan_interval": value}


async def test_changing_the_option_reloads_the_entry(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    with patch(f"{PKG}.async_setup_entry", return_value=True) as setup, \
         patch(f"{PKG}.async_unload_entry", return_value=True):
        assert await hass.config_entries.async_setup(entry.entry_id)
        result = await hass.config_entries.options.async_init(entry.entry_id)
        await hass.config_entries.options.async_configure(
            result["flow_id"], {"scan_interval": 60}
        )
        await hass.async_block_till_done()
    assert setup.call_count == 2
    assert entry.data["scan_interval"] == 45  # stored data is untouched
