"""Anti-Leakage Limit: set the leak volume without switching protection off."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from custom_components.midea_water_softener.device import WaterSoftenerDevice


def pack_of(message: bytes) -> list[int]:
    """The 5-byte parameter pack at the end of a set message (before the checksum)."""
    return list(message[-6:-1])


def _device(reply=bytearray(b"\x01")):
    cloud = MagicMock()
    cloud.send_command = AsyncMock(return_value=reply)
    return WaterSoftenerDevice(cloud, 123456, "Test softener"), cloud


def _entity(protection_on, reply=bytearray(b"\x01"), threshold=500):
    from custom_components.midea_water_softener.number import (
        LEAK_LIMIT_DESCRIPTION,
        WaterSoftenerLeakLimitNumber,
    )

    device, cloud = _device(reply)
    coordinator = MagicMock()
    coordinator.device = device
    coordinator.data = {"anti_leakage": protection_on, "leak_threshold": threshold}
    coordinator.async_request_refresh = AsyncMock()
    entry = MagicMock(entry_id="entry1", data={"device_id": 123456})
    entry.unique_id = "123456"
    entity = WaterSoftenerLeakLimitNumber(coordinator, entry, LEAK_LIMIT_DESCRIPTION)
    return entity, coordinator, cloud


# --- the message ------------------------------------------------------------

def test_builder_puts_the_on_state_in_value_and_the_volume_in_addition():
    from custom_components.midea_water_softener.message import build_set_leak_limit

    assert pack_of(build_set_leak_limit(True, 500)) == [0x0A, 0x01, 0x01, 50, 0]


def test_builder_puts_the_off_state_in_value():
    from custom_components.midea_water_softener.message import build_set_leak_limit

    assert pack_of(build_set_leak_limit(False, 500)) == [0x0A, 0x01, 0x00, 50, 0]


def test_the_set_unit_is_one_constant(monkeypatch):
    import custom_components.midea_water_softener.message as message

    monkeypatch.setattr(message, "LEAK_LIMIT_SET_UNIT_L", 1)
    assert pack_of(message.build_set_leak_limit(True, 500)) == [0x0A, 0x01, 0x01, 500 & 0xFF, 500 >> 8]


# --- the device -------------------------------------------------------------

async def test_device_sends_the_limit_with_the_current_state():
    device, cloud = _device()
    await device.set_leak_limit(800, True)
    assert pack_of(cloud.send_command.await_args.args[1]) == [0x0A, 0x01, 0x01, 80, 0]


async def test_device_refuses_to_guess_an_unknown_protection_state():
    device, cloud = _device()
    with pytest.raises(HomeAssistantError):
        await device.set_leak_limit(800, None)
    cloud.send_command.assert_not_awaited()


# --- the entity -------------------------------------------------------------

async def test_set_while_protection_is_on_sends_value_1_and_the_volume():
    entity, coordinator, cloud = _entity(protection_on=True)
    await entity.async_set_native_value(800)
    assert pack_of(cloud.send_command.await_args.args[1]) == [0x0A, 0x01, 0x01, 80, 0]
    coordinator.async_request_refresh.assert_awaited_once()


async def test_set_while_protection_is_off_sends_value_0_and_the_volume():
    entity, coordinator, cloud = _entity(protection_on=False)
    await entity.async_set_native_value(800)
    assert pack_of(cloud.send_command.await_args.args[1]) == [0x0A, 0x01, 0x00, 80, 0]
    coordinator.async_request_refresh.assert_awaited_once()


async def test_a_failed_send_raises_and_does_not_refresh():
    entity, coordinator, _ = _entity(protection_on=True, reply=None)
    with pytest.raises(HomeAssistantError):
        await entity.async_set_native_value(800)
    coordinator.async_request_refresh.assert_not_awaited()


async def test_the_value_comes_from_the_status_in_litres():
    entity, _, _ = _entity(protection_on=True, threshold=500)
    assert entity.native_value == 500.0


def test_the_description():
    from custom_components.midea_water_softener.number import LEAK_LIMIT_DESCRIPTION as d

    assert d.key == "leak_limit"
    assert d.translation_key == "leak_limit"
    assert d.entity_category == EntityCategory.CONFIG
    assert (d.native_min_value, d.native_max_value, d.native_step) == (10, 2550, 10)
    assert d.native_unit_of_measurement == "L"


def test_the_maximum_is_what_one_status_byte_can_read_back():
    # The status carries the limit in one byte, in units of 10 L: 255 * 10 = 2550 L.
    from custom_components.midea_water_softener.number import LEAK_LIMIT_DESCRIPTION as d

    assert d.native_max_value == 255 * 10 == 2550
