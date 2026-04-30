"""Number entities for the Midea water softener."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Coroutine

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_HARDNESS, ATTR_REGEN_INTERVAL, DOMAIN
from .coordinator import WaterSoftenerCoordinator
from .device import WaterSoftenerDevice


@dataclass(frozen=True, kw_only=True)
class WaterSoftenerNumberDescription(NumberEntityDescription):
    attr_key: str = ""
    set_value: Callable[[WaterSoftenerDevice, float], Coroutine] = None  # type: ignore[assignment]


NUMBER_DESCRIPTIONS: tuple[WaterSoftenerNumberDescription, ...] = (
    WaterSoftenerNumberDescription(
        key="hardness",
        attr_key=ATTR_HARDNESS,
        name="Hardness Setting",
        icon="mdi:water-minus",
        native_min_value=0,
        native_max_value=2000,
        native_step=5,
        native_unit_of_measurement="ppm",
        mode=NumberMode.BOX,
        set_value=lambda d, v: d.set_hardness(int(v)),
    ),
    WaterSoftenerNumberDescription(
        key="regen_interval",
        attr_key=ATTR_REGEN_INTERVAL,
        name="Regeneration Interval",
        icon="mdi:calendar-refresh",
        native_min_value=1,
        native_max_value=99,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.DAYS,
        mode=NumberMode.BOX,
        set_value=lambda d, v: d.set_regen_interval(int(v)),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: WaterSoftenerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        WaterSoftenerNumber(coordinator, entry, desc) for desc in NUMBER_DESCRIPTIONS
    )


class WaterSoftenerNumber(CoordinatorEntity[WaterSoftenerCoordinator], NumberEntity):
    _attr_has_entity_name = True
    entity_description: WaterSoftenerNumberDescription

    def __init__(
        self,
        coordinator: WaterSoftenerCoordinator,
        entry: ConfigEntry,
        description: WaterSoftenerNumberDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.data["device_id"]))},
            name=entry.data.get("device_name", "Water Softener"),
            manufacturer="Midea",
            model="QS2476-90",
        )

    @property
    def native_value(self) -> float | None:
        val = self.coordinator.data.get(self.entity_description.attr_key)
        return float(val) if val is not None else None

    async def async_set_native_value(self, value: float) -> None:
        await self.entity_description.set_value(self.coordinator.device, value)
        await self.coordinator.async_request_refresh()
