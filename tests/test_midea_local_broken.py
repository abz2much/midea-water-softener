"""A broken midea-local turns local control off; the cloud carries on."""
from __future__ import annotations

import logging
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.midea_water_softener import local
from custom_components.midea_water_softener.const import ATTR_SALT_REMAINING, DOMAIN
from custom_components.midea_water_softener.local import LocalUnavailable
from custom_components.midea_water_softener.message import build_query

from .conftest import SEND, send_reply
from .test_local import FakeSoftener, _transport
from .test_local_fallback import CLOUD_STATUS, FakeLocal, _device

PKG = "custom_components.midea_water_softener"
MIDEA_LOCAL_MODULES = ("midealocal", "midealocal.security", "midealocal.packet_builder")


@pytest.fixture
def broken_import():
    """midea-local is installed but cannot be imported."""
    local._lib = None
    with patch.dict(sys.modules, dict.fromkeys(MIDEA_LOCAL_MODULES)):
        yield
    local._lib = None


def _warnings(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING and r.name.startswith(PKG)
    ]


def _entry(with_local: bool = True) -> MockConfigEntry:
    data = {
        "account": "user@example.com",
        "password": "fake-password",
        "server": "MSmartHome (Global)",
        "device_id": 123456,
        "device_name": "Test softener",
        "scan_interval": 45,
    }
    if with_local:
        data |= {"host": "192.0.2.10", "token": "ab" * 64, "key": "cd" * 32}
    return MockConfigEntry(domain=DOMAIN, unique_id="123456", data=data)


# ---------------------------------------------------------------- import


@pytest.mark.usefixtures("enable_custom_integrations", "broken_import")
async def test_a_broken_import_still_loads_and_works_over_the_cloud(
    hass, make_session, caplog
):
    entry = _entry()
    entry.add_to_hass(hass)
    session = make_session({SEND: [send_reply(CLOUD_STATUS)]})
    caplog.set_level(logging.WARNING)
    with patch(f"{PKG}.async_get_clientsession", return_value=session), \
         patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.LOADED
    coordinator = entry.runtime_data
    assert coordinator.data[ATTR_SALT_REMAINING] == 40
    assert coordinator.device._local is None
    assert session.count(SEND) == 1
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "midea-local" in warnings[0]


@pytest.mark.usefixtures("enable_custom_integrations", "broken_import")
async def test_a_cloud_only_entry_does_not_warn(hass, make_session, caplog):
    entry = _entry(with_local=False)
    entry.add_to_hass(hass)
    session = make_session({SEND: [send_reply(CLOUD_STATUS)]})
    caplog.set_level(logging.WARNING)
    with patch(f"{PKG}.async_get_clientsession", return_value=session), \
         patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.LOADED
    assert _warnings(caplog) == []


@pytest.mark.usefixtures("broken_import")
def test_the_transport_reports_a_broken_import():
    assert local.unavailable_reason() is not None
    with pytest.raises(LocalUnavailable):
        local.udp_id(123456, 1)


# ---------------------------------------------------------------- changed API


@pytest.mark.usefixtures("socket_enabled")
async def test_a_changed_api_raises_unavailable_before_sending(monkeypatch):
    class OldSecurity:
        """A LocalSecurity without encode_8370."""

    real = local._midea_local()
    monkeypatch.setattr(local, "_lib", SimpleNamespace(**{**vars(real), "LocalSecurity": OldSecurity}))
    async with FakeSoftener(b"") as softener:
        with pytest.raises(LocalUnavailable) as err:
            await _transport(softener.port).send(build_query())
    assert err.value.sent is False


async def test_local_switches_off_after_one_warning(make_session, make_cloud, caplog):
    # Only one scripted result: a second local call would fail the test.
    local_fake = FakeLocal(LocalUnavailable("changed API", sent=False))
    device, session = await _device(
        make_session,
        make_cloud,
        local_fake,
        [send_reply(CLOUD_STATUS), send_reply(CLOUD_STATUS)],
    )
    caplog.set_level(logging.INFO)

    for _ in range(2):
        data = await device.refresh_status()
        assert data[ATTR_SALT_REMAINING] == 40

    assert len(local_fake.sent) == 1
    assert session.count(SEND) == 2
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "midea-local" in warnings[0]


async def test_a_sent_write_is_not_repeated_when_the_api_breaks(make_session, make_cloud):
    local_fake = FakeLocal(LocalUnavailable("changed API", sent=True))
    device, session = await _device(make_session, make_cloud, local_fake, [])
    with pytest.raises(HomeAssistantError):
        await device.regenerate_now()
    assert session.count(SEND) == 0
    assert device._local is None


# ---------------------------------------------------------------- setup form


@pytest.mark.usefixtures("enable_custom_integrations", "broken_import")
async def test_the_ip_step_says_local_is_unavailable(hass, make_session):
    from .test_config_flow_local import GET_TOKEN, _submit, _to_local_step

    result, session, patcher = await _to_local_step(hass, make_session, [])
    result = await _submit(hass, result, "192.0.2.10")
    patcher.stop()
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "local_unavailable"}
    assert session.count(GET_TOKEN) == 0
