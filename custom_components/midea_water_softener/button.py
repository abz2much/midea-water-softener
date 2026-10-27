"""Button entity: trigger immediate regeneration."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import WaterSoftenerConfigEntry, WaterSoftenerCoordinator
from .device_info import build_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WaterSoftenerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([RegenNowButton(coordinator, entry)])


class RegenNowButton(CoordinatorEntity[WaterSoftenerCoordinator], ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Regenerate Now"
    _attr_icon = "mdi:refresh"

    def __init__(
        self,
        coordinator: WaterSoftenerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_regenerate_now"
        self._attr_device_info = build_device_info(entry)

    async def async_press(self) -> None:
        await self.coordinator.device.regenerate_now()
