"""Time entity for regeneration scheduling."""
from __future__ import annotations

import datetime

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_REGEN_HOUR, ATTR_REGEN_MIN, DOMAIN
from .coordinator import WaterSoftenerCoordinator
from .device_info import build_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: WaterSoftenerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RegenTimeEntity(coordinator, entry)])


class RegenTimeEntity(CoordinatorEntity[WaterSoftenerCoordinator], TimeEntity):
    _attr_has_entity_name = True
    _attr_name = "Regeneration Time"
    _attr_icon = "mdi:clock-outline"

    def __init__(
        self,
        coordinator: WaterSoftenerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_regen_time"
        self._attr_device_info = build_device_info(entry)

    @property
    def native_value(self) -> datetime.time | None:
        hour = self.coordinator.data.get(ATTR_REGEN_HOUR)
        minute = self.coordinator.data.get(ATTR_REGEN_MIN)
        if hour is None or minute is None:
            return None
        return datetime.time(hour % 24, minute % 60)

    async def async_set_value(self, value: datetime.time) -> None:
        await self.coordinator.device.set_regen_time(value.hour, value.minute)
        await self.coordinator.async_request_refresh()
