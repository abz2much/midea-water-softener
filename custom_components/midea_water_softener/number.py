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
from homeassistant.const import EntityCategory, UnitOfTime, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_ANTI_LEAKAGE,
    ATTR_HARDNESS,
    ATTR_LEAK_THRESHOLD,
    ATTR_REGEN_INTERVAL,
    LEAK_LIMIT_MAX_L,
    LEAK_LIMIT_MIN_L,
    LEAK_LIMIT_STEP_L,
)
from .coordinator import WaterSoftenerConfigEntry, WaterSoftenerCoordinator
from .device_info import build_device_info
from .device import WaterSoftenerDevice


@dataclass(frozen=True, kw_only=True)
class WaterSoftenerNumberDescription(NumberEntityDescription):
    attr_key: str = ""
    set_value: Callable[[WaterSoftenerDevice, float], Coroutine] = None  # type: ignore[assignment]


NUMBER_DESCRIPTIONS: tuple[WaterSoftenerNumberDescription, ...] = (
    WaterSoftenerNumberDescription(
        key="hardness",
        attr_key=ATTR_HARDNESS,
        translation_key="hardness",
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
        translation_key="regen_interval",
        native_min_value=1,
        native_max_value=99,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.DAYS,
        mode=NumberMode.BOX,
        set_value=lambda d, v: d.set_regen_interval(int(v)),
    ),
)

# Reads the same status byte as the Anti-Leakage Threshold sensor. It has no
# set_value: WaterSoftenerLeakLimitNumber also needs the protection state.
LEAK_LIMIT_DESCRIPTION = WaterSoftenerNumberDescription(
    key="leak_limit",
    attr_key=ATTR_LEAK_THRESHOLD,
    translation_key="leak_limit",
    device_class=NumberDeviceClass.VOLUME,
    entity_category=EntityCategory.CONFIG,
    native_min_value=LEAK_LIMIT_MIN_L,
    native_max_value=LEAK_LIMIT_MAX_L,
    native_step=LEAK_LIMIT_STEP_L,
    native_unit_of_measurement=UnitOfVolume.LITERS,
    mode=NumberMode.BOX,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WaterSoftenerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            *(WaterSoftenerNumber(coordinator, entry, desc) for desc in NUMBER_DESCRIPTIONS),
            WaterSoftenerLeakLimitNumber(coordinator, entry, LEAK_LIMIT_DESCRIPTION),
        ]
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
        self._attr_device_info = build_device_info(entry)

    @property
    def native_value(self) -> float | None:
        val = self.coordinator.data.get(self.entity_description.attr_key)
        return float(val) if val is not None else None

    async def async_set_native_value(self, value: float) -> None:
        await self.entity_description.set_value(self.coordinator.device, value)
        await self.coordinator.async_request_refresh()


class WaterSoftenerLeakLimitNumber(WaterSoftenerNumber):
    """Set the leak volume, keeping the protection on or off as it is now."""

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.device.set_leak_limit(
            int(value), self.coordinator.data.get(ATTR_ANTI_LEAKAGE)
        )
        await self.coordinator.async_request_refresh()
