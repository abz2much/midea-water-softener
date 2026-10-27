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
    STATUS_NORMAL,
    STATUS_REGENERATING,
    STATUS_STANDBY,
)
from .coordinator import WaterSoftenerConfigEntry, WaterSoftenerCoordinator
from .device_info import build_device_info


@dataclass(frozen=True, kw_only=True)
class WaterSoftenerSensorDescription(SensorEntityDescription):
    attr_key: str = ""


SENSOR_DESCRIPTIONS: tuple[WaterSoftenerSensorDescription, ...] = (
    WaterSoftenerSensorDescription(
        key="soft_water_remaining",
        attr_key=ATTR_SOFT_WATER_REMAINING,
        translation_key="soft_water_remaining",
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.LITERS,
    ),
    WaterSoftenerSensorDescription(
        key="flow_rate",
        attr_key=ATTR_FLOW_RATE,
        translation_key="flow_rate",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
    ),
    WaterSoftenerSensorDescription(
        key="salt_remaining",
        attr_key=ATTR_SALT_REMAINING,
        translation_key="salt_remaining",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    WaterSoftenerSensorDescription(
        key="device_status",
        attr_key=ATTR_DEVICE_STATUS,
        translation_key="device_status",
        device_class=SensorDeviceClass.ENUM,
        options=[STATUS_NORMAL, STATUS_STANDBY, STATUS_REGENERATING],
    ),
    WaterSoftenerSensorDescription(
        key="water_consumption_total",
        attr_key=ATTR_WATER_CONSUMPTION_TOTAL,
        translation_key="water_consumption_total",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.LITERS,
    ),
    WaterSoftenerSensorDescription(
        key="use_days",
        attr_key=ATTR_USE_DAYS,
        translation_key="use_days",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.DAYS,
    ),
    WaterSoftenerSensorDescription(
        key="regen_seconds_remaining",
        attr_key=ATTR_REGEN_SECONDS_REMAINING,
        translation_key="regen_seconds_remaining",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
    ),
    WaterSoftenerSensorDescription(
        key="leak_threshold",
        attr_key=ATTR_LEAK_THRESHOLD,
        translation_key="leak_threshold",
        device_class=SensorDeviceClass.VOLUME,
        native_unit_of_measurement=UnitOfVolume.LITERS,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WaterSoftenerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
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
        self._attr_device_info = build_device_info(entry)

    @property
    def native_value(self) -> Any:
        return self.coordinator.data.get(self.entity_description.attr_key)
