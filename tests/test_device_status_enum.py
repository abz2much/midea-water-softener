"""Device Status is an ENUM sensor; the state strings stay exactly as they are."""
from __future__ import annotations

import pytest
from homeassistant.components.sensor import SensorDeviceClass

from custom_components.midea_water_softener.device import _status_to_dict
from custom_components.midea_water_softener.message import parse_response
from custom_components.midea_water_softener.sensor import SENSOR_DESCRIPTIONS

from .conftest import status_packet

DESC = next(d for d in SENSOR_DESCRIPTIONS if d.key == "device_status")


def test_device_status_is_an_enum_with_the_same_key():
    assert DESC.device_class == SensorDeviceClass.ENUM
    assert DESC.key == "device_status"
    assert DESC.state_class is None
    assert DESC.native_unit_of_measurement is None


def test_the_options_are_exactly_the_automation_strings():
    assert DESC.options == ["normal", "standby", "regenerating"]


@pytest.mark.parametrize(
    ("flags", "expected"),
    [(0x00, "normal"), (0x20, "standby"), (0x80, "regenerating"), (0xA0, "regenerating")],
)
def test_every_value_the_device_produces_is_an_option(flags, expected):
    data = _status_to_dict(parse_response(status_packet({51: flags})))
    assert data["device_status"] == expected
    assert data["device_status"] in DESC.options


def test_a_short_packet_without_flags_is_still_an_option():
    # Flags are only read when the body has 52+ bytes.
    data = _status_to_dict(parse_response(status_packet(body_len=30)))
    assert data["device_status"] in DESC.options
