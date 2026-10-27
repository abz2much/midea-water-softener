"""Local setup: fetch the token and key, test the connection, save them."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from midealocal.security import CloudSecurity
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.midea_water_softener.const import DOMAIN
from custom_components.midea_water_softener.local import LocalNoReply, LocalNotSent

from .conftest import LOGIN, login_ok, status_packet

PKG = "custom_components.midea_water_softener"
SESSION_PATCH = f"{PKG}.config_flow.async_get_clientsession"
TRANSPORT_PATCH = f"{PKG}.config_flow.LocalTransport"
LIST = "/v1/appliance/user/list/get"
GET_TOKEN = "/v1/iot/secure/getToken"

DEVICE = 123456
HOST = "192.0.2.10"
TOKEN_1, KEY_1 = "ab" * 64, "cd" * 32
TOKEN_2, KEY_2 = "ef" * 64, "01" * 32
APPLIANCE = {"id": str(DEVICE), "name": "Test softener", "type": "0xED", "onlineStatus": "1"}


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations):
    """Let Home Assistant find the integration in custom_components/."""


def token_reply(method: int, token: str, key: str) -> dict:
    """A getToken reply holding the pair for one udpid method."""
    udp_id = CloudSecurity.get_udp_id(DEVICE, method)
    return {
        "code": 0,
        "data": {"tokenlist": [{"udpId": udp_id, "token": token.upper(), "key": key.upper()}]},
    }


NO_TOKENS = {"code": 0, "data": {"tokenlist": []}}
TOKEN_ERROR = {"code": 3004, "msg": "value is illegal"}


class FakeTransport:
    """Stands in for LocalTransport. `works` lists the tokens that connect."""

    works: set[str] = set()
    made: list[tuple] = []

    def __init__(self, host, device_id, token, key, **kwargs) -> None:
        FakeTransport.made.append((host, device_id, token, key))
        self._token = token

    async def send(self, frame: bytes) -> bytes:
        if self._token not in FakeTransport.works:
            raise LocalNotSent("refused")
        return status_packet({7: 80})


@pytest.fixture
def transport():
    FakeTransport.works = set()
    FakeTransport.made = []
    with patch(TRANSPORT_PATCH, FakeTransport):
        yield FakeTransport


async def _to_local_step(hass, make_session, tokens):
    session = make_session(
        {
            LOGIN: [login_ok()],
            LIST: [{"code": 0, "data": {"list": [APPLIANCE]}}],
            GET_TOKEN: tokens,
        }
    )
    patcher = patch(SESSION_PATCH, return_value=session)
    patcher.start()
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"account": "user@example.com", "password": "fake-password",
         "server": "MSmartHome (Global)"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device_id": str(DEVICE)}
    )
    return result, session, patcher


async def _submit(hass, result, host: str):
    with patch(f"{PKG}.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": host}
        )
        await hass.async_block_till_done()
    return result


# ---------------------------------------------------------------- new setup


async def test_the_ip_step_follows_the_device_step(hass, make_session, transport):
    result, _, patcher = await _to_local_step(hass, make_session, [])
    patcher.stop()
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "local"
    assert list(result["data_schema"].schema) == ["host"]


async def test_new_setup_with_local_saves_host_token_and_key(
    hass, make_session, transport
):
    transport.works = {TOKEN_1}
    result, session, patcher = await _to_local_step(
        hass, make_session, [token_reply(1, TOKEN_1, KEY_1), NO_TOKENS]
    )
    result = await _submit(hass, result, HOST)
    patcher.stop()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == HOST
    assert result["data"]["token"] == TOKEN_1
    assert result["data"]["key"] == KEY_1
    assert transport.made[0] == (HOST, DEVICE, TOKEN_1, KEY_1)


async def test_the_second_pair_is_tried_when_the_first_fails(
    hass, make_session, transport
):
    transport.works = {TOKEN_2}
    result, _, patcher = await _to_local_step(
        hass,
        make_session,
        [token_reply(1, TOKEN_1, KEY_1), token_reply(2, TOKEN_2, KEY_2)],
    )
    result = await _submit(hass, result, HOST)
    patcher.stop()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert (result["data"]["token"], result["data"]["key"]) == (TOKEN_2, KEY_2)


async def test_token_fetch_failure_shows_an_error_then_cloud_only_works(
    hass, make_session, transport
):
    result, _, patcher = await _to_local_step(
        hass, make_session, [TOKEN_ERROR, TOKEN_ERROR]
    )
    result = await _submit(hass, result, HOST)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "token_failed"}

    result = await _submit(hass, result, "")
    patcher.stop()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert not {"host", "token", "key"} & result["data"].keys()


async def test_local_test_failure_shows_an_error_then_cloud_only_works(
    hass, make_session, transport
):
    result, _, patcher = await _to_local_step(
        hass, make_session, [token_reply(1, TOKEN_1, KEY_1), NO_TOKENS]
    )
    result = await _submit(hass, result, HOST)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "local_failed"}

    result = await _submit(hass, result, "")
    patcher.stop()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert not {"host", "token", "key"} & result["data"].keys()


async def test_a_blank_ip_skips_local(hass, make_session, transport):
    result, session, patcher = await _to_local_step(hass, make_session, [])
    result = await _submit(hass, result, "")
    patcher.stop()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert session.count(GET_TOKEN) == 0
    assert transport.made == []


# ---------------------------------------------------------------- reconfigure


def _entry(**extra) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(DEVICE),
        title="Test softener",
        data={
            "account": "user@example.com",
            "password": "fake-password",
            "server": "MSmartHome (Global)",
            "device_id": DEVICE,
            "device_name": "Test softener",
            "scan_interval": 30,
            **extra,
        },
    )


async def _reconfigure(hass, make_session, entry, host, routes):
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    first = result
    with patch(SESSION_PATCH, return_value=make_session(routes)), \
         patch(f"{PKG}.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": host}
        )
        await hass.async_block_till_done()
    return first, result


async def test_reconfigure_asks_only_for_the_ip(hass, make_session, transport):
    entry = _entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert list(result["data_schema"].schema) == ["host"]


async def test_reconfigure_adds_local_to_an_existing_entry(
    hass, make_session, transport
):
    transport.works = {TOKEN_1}
    entry = _entry()
    _, result = await _reconfigure(
        hass, make_session, entry, HOST, {GET_TOKEN: [token_reply(1, TOKEN_1, KEY_1), NO_TOKENS]}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == HOST
    assert entry.data["token"] == TOKEN_1
    assert entry.data["key"] == KEY_1
    assert entry.data["password"] == "fake-password"


async def test_reconfigure_shows_an_error_when_local_fails(
    hass, make_session, transport
):
    entry = _entry()
    _, result = await _reconfigure(
        hass, make_session, entry, HOST, {GET_TOKEN: [token_reply(1, TOKEN_1, KEY_1), NO_TOKENS]}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "local_failed"}
    assert "host" not in entry.data


async def test_reconfigure_with_a_wrong_stored_password(hass, make_session, transport):
    entry = _entry()
    _, result = await _reconfigure(
        hass, make_session, entry, HOST, {LOGIN: [{"code": 1, "msg": "bad password"}]}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reconfigure_with_a_blank_ip_removes_local(hass, make_session, transport):
    entry = _entry(host=HOST, token=TOKEN_1, key=KEY_1)
    _, result = await _reconfigure(hass, make_session, entry, "", {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert not {"host", "token", "key"} & entry.data.keys()


@pytest.mark.parametrize("error", [LocalNotSent("refused"), LocalNoReply("timeout")])
async def test_any_local_error_counts_as_a_failed_test(
    hass, make_session, transport, error
):
    class Failing(FakeTransport):
        async def send(self, frame):
            raise error

    with patch(TRANSPORT_PATCH, Failing):
        entry = _entry()
        _, result = await _reconfigure(
            hass, make_session, entry, HOST,
            {GET_TOKEN: [token_reply(1, TOKEN_1, KEY_1), NO_TOKENS]},
        )
    assert result["errors"] == {"base": "local_failed"}


# ---------------------------------------------------------------- strings


def test_every_new_form_string_is_translated():
    import json
    from pathlib import Path

    en = json.loads(
        (Path(__file__).parents[1]
         / "custom_components/midea_water_softener/translations/en.json").read_text()
    )["config"]
    for step in ("local", "reconfigure"):
        assert en["step"][step]["title"]
        assert en["step"][step]["description"]
        assert en["step"][step]["data"]["host"]
        assert en["step"][step]["data_description"]["host"]
    for error in ("token_failed", "local_failed", "local_unavailable"):
        assert en["error"][error]
    assert en["abort"]["reconfigure_successful"]


def _suggested_host(result) -> str | None:
    marker = next(iter(result["data_schema"].schema))
    return (marker.description or {}).get("suggested_value")


async def test_clearing_the_ip_field_in_reconfigure_removes_local(
    hass, make_session, transport
):
    """The frontend leaves a cleared optional field out of the submission."""
    entry = _entry(host=HOST, token=TOKEN_1, key=KEY_1)
    _, result = await _reconfigure_with(hass, make_session, entry, {}, {})
    assert result["type"] is FlowResultType.ABORT
    assert not {"host", "token", "key"} & entry.data.keys()


async def test_reconfigure_suggests_the_current_ip(hass, make_session, transport):
    entry = _entry(host=HOST, token=TOKEN_1, key=KEY_1)
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert _suggested_host(result) == HOST


async def test_the_ip_is_kept_after_an_error(hass, make_session, transport):
    result, _, patcher = await _to_local_step(
        hass, make_session, [token_reply(1, TOKEN_1, KEY_1), NO_TOKENS]
    )
    result = await _submit(hass, result, HOST)
    patcher.stop()
    assert result["errors"] == {"base": "local_failed"}
    assert _suggested_host(result) == HOST


async def _reconfigure_with(hass, make_session, entry, user_input, routes):
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    with patch(SESSION_PATCH, return_value=make_session(routes)), \
         patch(f"{PKG}.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input
        )
        await hass.async_block_till_done()
    return None, result
