"""Button entity: trigger immediate regeneration."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import WaterSoftenerConfigEntry, WaterSoftenerCoordinator
from .device_info import build_device_info, unique_id_prefix


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WaterSoftenerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([RegenNowButton(coordinator, entry)])


class RegenNowButton(CoordinatorEntity[WaterSoftenerCoordinator], ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "regenerate_now"

    def __init__(
        self,
        coordinator: WaterSoftenerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{unique_id_prefix(entry)}_regenerate_now"
        self._attr_device_info = build_device_info(entry)

    async def async_press(self) -> None:
        await self.coordinator.device.regenerate_now()
        await self.coordinator.async_request_refresh()
