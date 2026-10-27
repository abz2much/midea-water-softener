"""The coordinator is tied to its config entry."""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.midea_water_softener.coordinator import (
    WaterSoftenerCoordinator,
)


def test_coordinator_holds_its_config_entry():
    entry = MagicMock()
    device = MagicMock()
    device.name = "Test softener"

    coordinator = WaterSoftenerCoordinator(MagicMock(), entry, device, 45)

    assert coordinator.config_entry is entry
    assert coordinator.update_interval.total_seconds() == 45
