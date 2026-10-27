"""Sensor descriptions must use device and state classes that HA accepts together."""
from __future__ import annotations

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor.const import DEVICE_CLASS_STATE_CLASSES

from custom_components.midea_water_softener.sensor import SENSOR_DESCRIPTIONS


@pytest.mark.parametrize("desc", SENSOR_DESCRIPTIONS, ids=lambda d: d.key)
def test_device_class_and_state_class_are_a_valid_pair(desc):
    if desc.device_class is None or desc.state_class is None:
        pytest.skip("needs both a device class and a state class")
    allowed = DEVICE_CLASS_STATE_CLASSES.get(desc.device_class)
    if allowed is not None:
        assert desc.state_class in allowed


def test_remaining_soft_water_keeps_its_key_and_uses_volume_storage():
    desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == "soft_water_remaining")
    assert desc.device_class == SensorDeviceClass.VOLUME_STORAGE
