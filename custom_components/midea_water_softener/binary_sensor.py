"""Binary sensor for the Midea water softener."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_LEAK_DETECTED
from .coordinator import WaterSoftenerConfigEntry, WaterSoftenerCoordinator
from .device_info import build_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WaterSoftenerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([WaterSoftenerLeakSensor(coordinator, entry)])


class WaterSoftenerLeakSensor(
    CoordinatorEntity[WaterSoftenerCoordinator], BinarySensorEntity
):
    _attr_has_entity_name = True
    _attr_translation_key = "leak_detected"
    _attr_device_class = BinarySensorDeviceClass.MOISTURE

    def __init__(
        self,
        coordinator: WaterSoftenerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_leak_detected"
        self._attr_device_info = build_device_info(entry)

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get(ATTR_LEAK_DETECTED)
