"""Sensor entities for the Midea water softener."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_DEVICE_STATUS,
    ATTR_FLOW_RATE,
    ATTR_LEAK_THRESHOLD,
    ATTR_REGEN_SECONDS_REMAINING,
    ATTR_SALT_REMAINING,
    ATTR_SOFT_WATER_REMAINING,
    ATTR_USE_DAYS,
    ATTR_WATER_CONSUMPTION_TOTAL,
    DOMAIN,
)
from .coordinator import WaterSoftenerCoordinator


@dataclass(frozen=True, kw_only=True)
class WaterSoftenerSensorDescription(SensorEntityDescription):
    attr_key: str = ""


SENSOR_DESCRIPTIONS: tuple[WaterSoftenerSensorDescription, ...] = (
    WaterSoftenerSensorDescription(
        key="soft_water_remaining",
        attr_key=ATTR_SOFT_WATER_REMAINING,
        name="Remaining Soft Water",
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        icon="mdi:water-outline",
    ),
    WaterSoftenerSensorDescription(
        key="flow_rate",
        attr_key=ATTR_FLOW_RATE,
        name="Flow Rate",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
        icon="mdi:water-pump",
    ),
    WaterSoftenerSensorDescription(
        key="salt_remaining",
        attr_key=ATTR_SALT_REMAINING,
        name="Remaining Salt",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:shaker-outline",
    ),
    WaterSoftenerSensorDescription(
        key="device_status",
        attr_key=ATTR_DEVICE_STATUS,
        name="Device Status",
        icon="mdi:water-check",
    ),
    WaterSoftenerSensorDescription(
        key="water_consumption_total",
        attr_key=ATTR_WATER_CONSUMPTION_TOTAL,
        name="Total Water Consumption",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        icon="mdi:water-boiler",
    ),
    WaterSoftenerSensorDescription(
        key="use_days",
        attr_key=ATTR_USE_DAYS,
        name="Days in Use",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.DAYS,
        icon="mdi:counter",
    ),
    WaterSoftenerSensorDescription(
        key="regen_seconds_remaining",
        attr_key=ATTR_REGEN_SECONDS_REMAINING,
        name="Regeneration Time Remaining",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        icon="mdi:timer-outline",
    ),
    WaterSoftenerSensorDescription(
        key="leak_threshold",
        attr_key=ATTR_LEAK_THRESHOLD,
        name="Anti-Leakage Threshold",
        device_class=SensorDeviceClass.VOLUME,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        icon="mdi:water-alert-outline",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: WaterSoftenerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        WaterSoftenerSensor(coordinator, entry, desc) for desc in SENSOR_DESCRIPTIONS
    )


class WaterSoftenerSensor(CoordinatorEntity[WaterSoftenerCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: WaterSoftenerSensorDescription

    def __init__(
        self,
        coordinator: WaterSoftenerCoordinator,
        entry: ConfigEntry,
        description: WaterSoftenerSensorDescription,
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
    def native_value(self) -> Any:
        return self.coordinator.data.get(self.entity_description.attr_key)
