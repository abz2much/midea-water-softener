"""Set the integration up for real and check what Home Assistant creates.

This is the guard for renames and migrations: entity IDs and visible names
must not change.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.midea_water_softener.const import DOMAIN

from .conftest import LOGIN, SEND, login_ok, send_reply, status_packet

PKG = "custom_components.midea_water_softener"


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations):
    """Let Home Assistant find the integration in custom_components/."""


def make_entry(**extra) -> MockConfigEntry:
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
        **extra,
    )


async def setup_entry(hass, make_session, entry):
    """Set the entry up with one good status reply, then return the registry."""
    entry.add_to_hass(hass)
    packet = status_packet({7: 80, 8: 50, 51: 0x14})
    session = make_session({LOGIN: [login_ok()], SEND: [send_reply(packet)]})
    with patch(f"{PKG}.async_get_clientsession", return_value=session):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return er.async_get(hass)


# entity_id -> (visible name, unique ID suffix). Recorded before the polish batch.
EXPECTED = {
    "binary_sensor.test_softener_leak_detected": ("Test softener Leak Detected", "leak_detected"),
    "button.test_softener_regenerate_now": ("Test softener Regenerate Now", "regenerate_now"),
    "number.test_softener_anti_leakage_limit": ("Test softener Anti-Leakage Limit", "leak_limit"),
    "number.test_softener_hardness_setting": ("Test softener Hardness Setting", "hardness"),
    "number.test_softener_regeneration_interval": ("Test softener Regeneration Interval", "regen_interval"),
    "sensor.test_softener_anti_leakage_threshold": ("Test softener Anti-Leakage Threshold", "leak_threshold"),
    "sensor.test_softener_days_in_use": ("Test softener Days in Use", "use_days"),
    "sensor.test_softener_device_status": ("Test softener Device Status", "device_status"),
    "sensor.test_softener_flow_rate": ("Test softener Flow Rate", "flow_rate"),
    "sensor.test_softener_regeneration_time_remaining": ("Test softener Regeneration Time Remaining", "regen_seconds_remaining"),
    "sensor.test_softener_remaining_salt": ("Test softener Remaining Salt", "salt_remaining"),
    "sensor.test_softener_remaining_soft_water": ("Test softener Remaining Soft Water", "soft_water_remaining"),
    "sensor.test_softener_total_water_consumption": ("Test softener Total Water Consumption", "water_consumption_total"),
    "switch.test_softener_anti_leakage_reminder": ("Test softener Anti-Leakage Reminder", "anti_leakage"),
    "switch.test_softener_inlet": ("Test softener Inlet", "inlet"),
    "switch.test_softener_soft_water": ("Test softener Soft Water", "soften"),
    "time.test_softener_regeneration_time": ("Test softener Regeneration Time", "regen_time"),
}


async def test_entity_ids_names_and_unique_ids(hass, make_session):
    entry = make_entry()
    registry = await setup_entry(hass, make_session, entry)

    found = {}
    for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
        state = hass.states.get(reg.entity_id)
        found[reg.entity_id] = (state.attributes["friendly_name"], reg.unique_id)

    assert set(found) == set(EXPECTED)
    for entity_id, (name, suffix) in EXPECTED.items():
        assert found[entity_id][0] == name, entity_id
        assert found[entity_id][1] == f"{entry.entry_id}_{suffix}", entity_id

    await hass.config_entries.async_unload(entry.entry_id)
