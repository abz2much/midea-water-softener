"""Unique IDs move from the config entry ID to the device ID, in place."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.midea_water_softener.const import DOMAIN

from .conftest import LOGIN, SEND, login_ok, send_reply, status_packet
from .test_entities_end_to_end import EXPECTED, make_entry

PKG = "custom_components.midea_water_softener"

# What a v1.0.5 install had: every current entity except the new Anti-Leakage Limit.
OLD_ENTITIES = {e: v for e, v in EXPECTED.items() if not e.endswith("anti_leakage_limit")}
NEW_ONLY = "number.test_softener_anti_leakage_limit"


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations):
    """Let Home Assistant find the integration in custom_components/."""


def _old_entry() -> MockConfigEntry:
    """An entry as it was saved before this release: version 1.1."""
    return make_entry(version=1, minor_version=1)


def _register_old_entities(hass, entry):
    registry = er.async_get(hass)
    for entity_id, (_, suffix) in OLD_ENTITIES.items():
        domain, object_id = entity_id.split(".", 1)
        registry.async_get_or_create(
            domain, DOMAIN, f"{entry.entry_id}_{suffix}",
            config_entry=entry, suggested_object_id=object_id,
        )
    return registry


async def _setup(hass, make_session, entry):
    packet = status_packet({7: 80, 8: 50, 51: 0x14})
    session = make_session({LOGIN: [login_ok()], SEND: [send_reply(packet)]})
    with patch(f"{PKG}.async_get_clientsession", return_value=session):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


def _snapshot(registry, entry):
    return {
        r.entity_id: (r.unique_id, r.modified_at)
        for r in er.async_entries_for_config_entry(registry, entry.entry_id)
    }


async def test_an_old_entry_gets_device_id_unique_ids_and_keeps_its_entity_ids(
    hass, make_session
):
    entry = _old_entry()
    entry.add_to_hass(hass)
    registry = _register_old_entities(hass, entry)
    ids_before = set(registry.entities)

    await _setup(hass, make_session, entry)

    assert entry.state is ConfigEntryState.LOADED
    for entity_id, (name, suffix) in OLD_ENTITIES.items():
        reg = registry.async_get(entity_id)
        assert reg is not None, f"{entity_id} lost"
        assert reg.unique_id == f"123456_{suffix}", entity_id
        assert hass.states.get(entity_id).attributes["friendly_name"] == name
    # Only the new Anti-Leakage Limit was added: nothing duplicated, nothing renamed.
    assert set(registry.entities) - ids_before == {NEW_ONLY}
    assert not [e for e in registry.entities if e.endswith("_2")]
    assert (entry.version, entry.minor_version) == (1, 2)
    await hass.config_entries.async_unload(entry.entry_id)


async def test_every_platform_is_covered(hass, make_session):
    entry = _old_entry()
    entry.add_to_hass(hass)
    registry = _register_old_entities(hass, entry)
    await _setup(hass, make_session, entry)

    migrated_domains = {
        r.domain
        for r in er.async_entries_for_config_entry(registry, entry.entry_id)
        if r.unique_id.startswith("123456_")
    }
    assert migrated_domains == {"sensor", "binary_sensor", "switch", "number", "time", "button"}
    assert not [
        r for r in er.async_entries_for_config_entry(registry, entry.entry_id)
        if r.unique_id.startswith(entry.entry_id)
    ]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_running_it_twice_changes_nothing(hass, make_session):
    from custom_components.midea_water_softener import async_migrate_entry

    entry = _old_entry()
    entry.add_to_hass(hass)
    registry = _register_old_entities(hass, entry)
    await _setup(hass, make_session, entry)
    before = _snapshot(registry, entry)

    assert await async_migrate_entry(hass, entry)
    assert await async_migrate_entry(hass, entry)

    assert _snapshot(registry, entry) == before
    await hass.config_entries.async_unload(entry.entry_id)


async def test_entities_already_migrated_are_skipped(hass, make_session):
    from custom_components.midea_water_softener import async_migrate_entry

    entry = _old_entry()
    entry.add_to_hass(hass)
    registry = _register_old_entities(hass, entry)
    flow_rate = "sensor.test_softener_flow_rate"
    registry.async_update_entity(flow_rate, new_unique_id="123456_flow_rate")
    before = registry.async_get(flow_rate)

    assert await async_migrate_entry(hass, entry)

    assert registry.async_get(flow_rate) == before  # untouched, not rewritten
    assert registry.async_get("sensor.test_softener_days_in_use").unique_id == "123456_use_days"


async def test_a_clash_aborts_and_nothing_is_half_migrated(hass, make_session):
    entry = _old_entry()
    entry.add_to_hass(hass)
    registry = _register_old_entities(hass, entry)
    # A twin: another entity already has the unique ID the flow rate sensor would get.
    registry.async_get_or_create(
        "sensor", DOMAIN, "123456_flow_rate", suggested_object_id="stray_flow_rate"
    )
    before = _snapshot(registry, entry)

    await _setup(hass, make_session, entry)

    assert entry.state is ConfigEntryState.MIGRATION_ERROR
    assert _snapshot(registry, entry) == before
    assert entry.minor_version == 1
    assert all(u.startswith(entry.entry_id) for u, _ in before.values())


async def test_a_newer_major_version_is_refused(hass):
    from custom_components.midea_water_softener import async_migrate_entry

    entry = make_entry(version=2)
    entry.add_to_hass(hass)
    assert await async_migrate_entry(hass, entry) is False


# --- new entries ------------------------------------------------------------

async def test_a_new_entry_gets_the_new_unique_ids_straight_away(hass, make_session):
    entry = make_entry()  # default flow version 1.2, no old entities
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    await _setup(hass, make_session, entry)

    unique_ids = {r.unique_id for r in er.async_entries_for_config_entry(registry, entry.entry_id)}
    assert unique_ids == {f"123456_{s}" for _, s in EXPECTED.values()}
    await hass.config_entries.async_unload(entry.entry_id)


async def test_the_config_flow_creates_version_1_minor_2(hass, make_session):
    from .conftest import LOGIN as _L

    list_route = "/v1/appliance/user/list/get"
    appliance = {"id": "123456", "name": "Test softener", "type": "0xED", "onlineStatus": "1"}
    session = make_session(
        {_L: [login_ok()], list_route: [{"code": 0, "data": {"list": [appliance]}}]}
    )
    with patch(
        "custom_components.midea_water_softener.config_flow.async_get_clientsession",
        return_value=session,
    ), patch(f"{PKG}.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"account": "user@example.com", "password": "fake-password",
             "server": "MSmartHome (Global)"},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device_id": "123456"}
        )
        # A blank IP address: cloud only.
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": ""}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert (result["version"], result["minor_version"]) == (1, 2)
