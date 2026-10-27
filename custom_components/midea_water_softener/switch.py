"""Switch entities for the Midea water softener."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_ANTI_LEAKAGE,
    ATTR_INLET,
    ATTR_SOFTEN,
    DOMAIN,
)
from .coordinator import WaterSoftenerCoordinator
from .device_info import build_device_info
from .device import WaterSoftenerDevice


@dataclass(frozen=True, kw_only=True)
class WaterSoftenerSwitchDescription(SwitchEntityDescription):
    attr_key: str = ""
    turn_on: Callable[[WaterSoftenerDevice], Coroutine] = None  # type: ignore[assignment]
    turn_off: Callable[[WaterSoftenerDevice], Coroutine] = None  # type: ignore[assignment]


SWITCH_DESCRIPTIONS: tuple[WaterSoftenerSwitchDescription, ...] = (
    WaterSoftenerSwitchDescription(
        key="soften",
        attr_key=ATTR_SOFTEN,
        name="Soft Water",
        icon="mdi:water-check",
        turn_on=lambda d: d.set_soften(True),
        turn_off=lambda d: d.set_soften(False),
    ),
    WaterSoftenerSwitchDescription(
        key="inlet",
        attr_key=ATTR_INLET,
        name="Inlet",
        icon="mdi:valve-open",
        turn_on=lambda d: d.set_inlet(True),
        turn_off=lambda d: d.set_inlet(False),
    ),
    WaterSoftenerSwitchDescription(
        key="anti_leakage",
        attr_key=ATTR_ANTI_LEAKAGE,
        name="Anti-Leakage Reminder",
        icon="mdi:water-alert",
        turn_on=lambda d: d.set_anti_leakage(True),
        turn_off=lambda d: d.set_anti_leakage(False),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: WaterSoftenerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        WaterSoftenerSwitch(coordinator, entry, desc) for desc in SWITCH_DESCRIPTIONS
    )


class WaterSoftenerSwitch(CoordinatorEntity[WaterSoftenerCoordinator], SwitchEntity):
    _attr_has_entity_name = True
    entity_description: WaterSoftenerSwitchDescription

    def __init__(
        self,
        coordinator: WaterSoftenerCoordinator,
        entry: ConfigEntry,
        description: WaterSoftenerSwitchDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = build_device_info(entry)

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get(self.entity_description.attr_key)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.entity_description.turn_on(self.coordinator.device)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.entity_description.turn_off(self.coordinator.device)
        await self.coordinator.async_request_refresh()
