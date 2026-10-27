"""Anti-Leakage Threshold: status byte body[8], in units of 10 L."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfVolume

from custom_components.midea_water_softener.device import _status_to_dict
from custom_components.midea_water_softener.message import parse_response
from custom_components.midea_water_softener.sensor import SENSOR_DESCRIPTIONS

from .conftest import status_packet


def test_threshold_byte_is_read_in_litres():
    status = parse_response(status_packet({8: 50}))
    assert status.leak_threshold == 500


def test_short_packet_is_still_rejected():
    # parse_response needs 21 body bytes, so body[8] is never read out of range.
    assert parse_response(status_packet(body_len=20)) is None


def test_shortest_accepted_packet_has_the_threshold():
    status = parse_response(status_packet({8: 7}, body_len=21))
    assert status.leak_threshold == 70


def test_threshold_is_in_the_status_dict():
    data = _status_to_dict(parse_response(status_packet({8: 50})))
    assert data["leak_threshold"] == 500


def test_threshold_sensor_description():
    desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == "leak_threshold")
    assert desc.attr_key == "leak_threshold"
    assert desc.translation_key == "leak_threshold"
    assert desc.native_unit_of_measurement == UnitOfVolume.LITERS
    assert desc.device_class == SensorDeviceClass.VOLUME
    assert desc.state_class is None
