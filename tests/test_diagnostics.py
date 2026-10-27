"""Diagnostics: useful state, no secrets."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.midea_water_softener.const import DOMAIN

ACCOUNT = "sample.user@example.com"
PASSWORD = "sample-password-123"
TOKEN = "sample-access-token-abc"
UID = "sample-uid-999"
SERIAL = "SAMPLE-SERIAL-001"
DEVICE_ID = 424242


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations):
    """Let Home Assistant find the integration in custom_components/."""


def _entry(**extra) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test softener",
        data={
            "account": ACCOUNT,
            "password": PASSWORD,
            "server": "MSmartHome (Global)",
            "device_id": DEVICE_ID,
            "device_name": "Test softener",
            "scan_interval": 45,
            "serial_number": SERIAL,
            # Not stored today, but must be redacted if it ever is.
            "access_token": TOKEN,
            "uid": UID,
        },
        **extra,
    )


def _coordinator(data=None, exception=None):
    coordinator = MagicMock()
    coordinator.data = data if data is not None else {"device_status": "normal", "salt_remaining": 80}
    coordinator.last_update_success = exception is None
    coordinator.last_exception = exception
    coordinator.update_interval.total_seconds.return_value = 45
    return coordinator


async def _diagnostics(hass, entry, coordinator):
    from custom_components.midea_water_softener.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    entry.add_to_hass(hass)
    entry.runtime_data = coordinator
    return await async_get_config_entry_diagnostics(hass, entry)


async def test_no_secret_or_identifier_is_in_the_output(hass):
    result = await _diagnostics(hass, _entry(), _coordinator())
    text = json.dumps(result, default=str)
    for secret in (ACCOUNT, PASSWORD, TOKEN, UID, SERIAL, str(DEVICE_ID)):
        assert secret not in text


async def test_output_has_the_useful_state(hass):
    result = await _diagnostics(hass, _entry(), _coordinator())
    assert result["coordinator"]["data"] == {"device_status": "normal", "salt_remaining": 80}
    assert result["coordinator"]["last_update_success"] is True
    assert result["poll_interval"] == 45
    assert result["integration_version"]
    assert result["entry"]["data"]["server"] == "MSmartHome (Global)"


async def test_poll_interval_follows_the_option(hass):
    entry = _entry(options={"scan_interval": 120})
    coordinator = _coordinator()
    coordinator.update_interval.total_seconds.return_value = 120
    result = await _diagnostics(hass, entry, coordinator)
    assert result["poll_interval"] == 120
    assert result["entry"]["options"] == {"scan_interval": 120}


async def test_last_failure_is_reported(hass):
    result = await _diagnostics(
        hass, _entry(), _coordinator(exception=RuntimeError("cloud down"))
    )
    assert result["coordinator"]["last_update_success"] is False
    assert "cloud down" in result["coordinator"]["last_exception"]


async def test_the_local_token_and_key_are_redacted(hass):
    local_token = "ab" * 64
    local_key = "cd" * 32
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test softener",
        data={
            "account": ACCOUNT,
            "password": PASSWORD,
            "server": "MSmartHome (Global)",
            "device_id": DEVICE_ID,
            "device_name": "Test softener",
            "host": "192.0.2.10",
            "token": local_token,
            "key": local_key,
        },
    )
    result = await _diagnostics(hass, entry, _coordinator())
    text = json.dumps(result, default=str)
    assert local_token not in text
    assert local_key not in text
    assert result["entry"]["data"]["token"] == "**REDACTED**"
    assert result["entry"]["data"]["key"] == "**REDACTED**"
