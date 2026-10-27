"""One DeviceInfo for every entity; new entries also save the model and serial."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.midea_water_softener.binary_sensor import WaterSoftenerLeakSensor
from custom_components.midea_water_softener.button import RegenNowButton
from custom_components.midea_water_softener.number import NUMBER_DESCRIPTIONS, WaterSoftenerNumber
from custom_components.midea_water_softener.sensor import SENSOR_DESCRIPTIONS, WaterSoftenerSensor
from custom_components.midea_water_softener.switch import SWITCH_DESCRIPTIONS, WaterSoftenerSwitch
from custom_components.midea_water_softener.time import RegenTimeEntity

from .conftest import LOGIN, login_ok

# What every entity reported before the helper existed (old-style entry, no model).
OLD_DEVICE_INFO = {
    "identifiers": {("midea_water_softener", "123456")},
    "name": "Test softener",
    "manufacturer": "Midea",
    "model": "QS2476-90",
}

OLD_DATA = {"device_id": 123456, "device_name": "Test softener"}


def _entry(data):
    return MagicMock(entry_id="entry1", data=data)


def _entities(entry):
    coordinator = MagicMock()
    return [
        WaterSoftenerSensor(coordinator, entry, SENSOR_DESCRIPTIONS[0]),
        WaterSoftenerSwitch(coordinator, entry, SWITCH_DESCRIPTIONS[0]),
        WaterSoftenerNumber(coordinator, entry, NUMBER_DESCRIPTIONS[0]),
        RegenTimeEntity(coordinator, entry),
        RegenNowButton(coordinator, entry),
        WaterSoftenerLeakSensor(coordinator, entry),
    ]


def test_old_style_entry_gives_the_same_device_info_on_every_entity():
    for entity in _entities(_entry(OLD_DATA)):
        assert dict(entity.device_info) == OLD_DEVICE_INFO, type(entity).__name__


def test_helper_for_an_old_style_entry():
    from custom_components.midea_water_softener.device_info import build_device_info

    assert dict(build_device_info(_entry(OLD_DATA))) == OLD_DEVICE_INFO


def test_helper_uses_the_saved_model_and_serial_number():
    from custom_components.midea_water_softener.device_info import build_device_info

    info = build_device_info(
        _entry({**OLD_DATA, "model": "MODEL-X", "serial_number": "SN0001"})
    )
    assert info["model"] == "MODEL-X"
    assert info["serial_number"] == "SN0001"
    assert info["identifiers"] == OLD_DEVICE_INFO["identifiers"]
    assert info["name"] == "Test softener"
    assert info["manufacturer"] == "Midea"


def test_helper_ignores_an_empty_saved_model():
    from custom_components.midea_water_softener.device_info import build_device_info

    info = build_device_info(_entry({**OLD_DATA, "model": "", "serial_number": ""}))
    assert dict(info) == OLD_DEVICE_INFO


# --- config flow saves the model and serial number -------------------------

LIST = "/v1/appliance/user/list/get"
SESSION_PATCH = "custom_components.midea_water_softener.config_flow.async_get_clientsession"


@pytest.fixture
def _custom_integrations(enable_custom_integrations):
    """Let Home Assistant find the integration in custom_components/."""


def _appliance(**extra):
    return {"id": "123456", "name": "Test softener", "type": "0xED",
            "onlineStatus": "1", **extra}


async def _run_flow(hass, make_session, appliance):
    session = make_session(
        {LOGIN: [login_ok()], LIST: [{"code": 0, "data": {"list": [appliance]}}]}
    )
    with patch(SESSION_PATCH, return_value=session), patch(
        "custom_components.midea_water_softener.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_init(
            "midea_water_softener", context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"account": "user@example.com", "password": "fake-password",
             "server": "MSmartHome (Global)"},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device_id": "123456"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    return result["data"]


async def test_new_entry_saves_the_model_and_serial_number(
    hass, make_session, _custom_integrations
):
    data = await _run_flow(
        hass, make_session, _appliance(productModel="MODEL-X", sn="SN0001")
    )
    assert data["model"] == "MODEL-X"
    assert data["serial_number"] == "SN0001"
    assert data["device_id"] == 123456


async def test_new_entry_without_a_model_saves_neither_key(
    hass, make_session, _custom_integrations
):
    data = await _run_flow(hass, make_session, _appliance(productModel="", sn=""))
    assert "model" not in data
    assert "serial_number" not in data
