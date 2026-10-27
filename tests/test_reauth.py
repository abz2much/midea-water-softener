"""Reauth: ask for the password only, check it, save it and reload."""
from __future__ import annotations

from unittest.mock import patch

import aiohttp
import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.midea_water_softener.const import (
    CONF_ACCOUNT,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_SERVER,
    DOMAIN,
    SERVERS,
)

from .conftest import LOGIN, ROUTER, login_ok

SESSION_PATCH = "custom_components.midea_water_softener.config_flow.async_get_clientsession"
SETUP_PATCH = "custom_components.midea_water_softener.async_setup_entry"


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations):
    """Let Home Assistant find the integration in custom_components/."""


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="123456",
        title="Test softener",
        data={
            CONF_ACCOUNT: "user@example.com",
            "password": "old-password",
            CONF_SERVER: list(SERVERS)[0],
            CONF_DEVICE_ID: 123456,
            CONF_DEVICE_NAME: "Test softener",
            "scan_interval": 30,
        },
    )


async def _start_reauth(hass, entry):
    entry.add_to_hass(hass)
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )


async def test_reauth_asks_for_the_password_only(hass, make_session):
    result = await _start_reauth(hass, _entry())
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert list(result["data_schema"].schema) == ["password"]


async def test_wrong_password_shows_invalid_auth(hass, make_session):
    result = await _start_reauth(hass, _entry())
    session = make_session({LOGIN: [{"code": 1, "msg": "invalid password"}]})
    with patch(SESSION_PATCH, return_value=session):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "wrong"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_network_failure_shows_cannot_connect(hass, make_session):
    result = await _start_reauth(hass, _entry())
    session = make_session({ROUTER: [aiohttp.ClientConnectionError("down")]})
    with patch(SESSION_PATCH, return_value=session):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "anything"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_right_password_updates_the_entry_and_reloads_it(hass, make_session):
    entry = _entry()
    result = await _start_reauth(hass, entry)
    before = dict(entry.data)
    session = make_session({LOGIN: [login_ok()]})
    with patch(SESSION_PATCH, return_value=session), patch(
        SETUP_PATCH, return_value=True
    ) as setup:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "new-password"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == {**before, "password": "new-password"}
    assert entry.unique_id == "123456"
    setup.assert_called_once()


async def test_setup_with_a_bad_password_starts_reauth(hass, make_session):
    entry = _entry()
    entry.add_to_hass(hass)
    session = make_session({LOGIN: [{"code": 1, "msg": "invalid password"}]})
    with patch(
        "custom_components.midea_water_softener.async_get_clientsession",
        return_value=session,
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is config_entries.ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == [config_entries.SOURCE_REAUTH]
