"""Leak Detected binary sensor: status flag bit 0x08 in body[51]."""
from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import Platform

import custom_components.midea_water_softener as integration
from custom_components.midea_water_softener.device import _status_to_dict
from custom_components.midea_water_softener.message import parse_response

from .conftest import status_packet


def test_flag_bit_gives_leak_detected_on():
    data = _status_to_dict(parse_response(status_packet({51: 0x08})))
    assert data["leak_detected"] is True


def test_clear_flag_gives_leak_detected_off():
    data = _status_to_dict(parse_response(status_packet({51: 0x00})))
    assert data["leak_detected"] is False


def test_other_flags_do_not_trigger_leak_detected():
    data = _status_to_dict(parse_response(status_packet({51: 0xF7})))
    assert data["leak_detected"] is False


def test_binary_sensor_platform_is_loaded():
    assert Platform.BINARY_SENSOR in integration.PLATFORMS


def _entity(leak_detected):
    from custom_components.midea_water_softener.binary_sensor import (
        WaterSoftenerLeakSensor,
    )

    coordinator = MagicMock()
    coordinator.data = {"leak_detected": leak_detected}
    entry = MagicMock(entry_id="entry1", data={"device_id": 123456})
    entry.unique_id = "123456"
    return WaterSoftenerLeakSensor(coordinator, entry)


def test_binary_sensor_identity_and_class():
    entity = _entity(False)
    assert entity.translation_key == "leak_detected"
    assert entity.device_class == BinarySensorDeviceClass.MOISTURE
    assert entity.unique_id == "123456_leak_detected"
    assert ("midea_water_softener", "123456") in entity.device_info["identifiers"]


def test_binary_sensor_state_follows_the_data():
    assert _entity(True).is_on is True
    assert _entity(False).is_on is False
