"""Entity names and icons come from translations/en.json and icons.json."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.midea_water_softener.binary_sensor import WaterSoftenerLeakSensor
from custom_components.midea_water_softener.button import RegenNowButton
from custom_components.midea_water_softener.number import NUMBER_DESCRIPTIONS, WaterSoftenerNumber
from custom_components.midea_water_softener.sensor import SENSOR_DESCRIPTIONS, WaterSoftenerSensor
from custom_components.midea_water_softener.switch import SWITCH_DESCRIPTIONS, WaterSoftenerSwitch
from custom_components.midea_water_softener.time import RegenTimeEntity

COMPONENT = Path(__file__).parent.parent / "custom_components" / "midea_water_softener"
TRANSLATIONS = json.loads((COMPONENT / "translations" / "en.json").read_text())
try:
    ICONS = json.loads((COMPONENT / "icons.json").read_text())
except FileNotFoundError:
    ICONS = {}

# domain -> translation key -> (visible name, icon). Recorded from the code
# before names and icons moved into translation files.
EXPECTED = {
    "sensor": {
        "soft_water_remaining": ("Remaining Soft Water", "mdi:water-outline"),
        "flow_rate": ("Flow Rate", "mdi:water-pump"),
        "salt_remaining": ("Remaining Salt", "mdi:shaker-outline"),
        "device_status": ("Device Status", "mdi:water-check"),
        "water_consumption_total": ("Total Water Consumption", "mdi:water-boiler"),
        "use_days": ("Days in Use", "mdi:counter"),
        "regen_seconds_remaining": ("Regeneration Time Remaining", "mdi:timer-outline"),
        "leak_threshold": ("Anti-Leakage Threshold", "mdi:water-alert-outline"),
    },
    "switch": {
        "soften": ("Soft Water", "mdi:water-check"),
        "inlet": ("Inlet", "mdi:valve-open"),
        "anti_leakage": ("Anti-Leakage Reminder", "mdi:water-alert"),
    },
    "number": {
        "hardness": ("Hardness Setting", "mdi:water-minus"),
        "regen_interval": ("Regeneration Interval", "mdi:calendar-refresh"),
    },
    "time": {"regen_time": ("Regeneration Time", "mdi:clock-outline")},
    "button": {"regenerate_now": ("Regenerate Now", "mdi:refresh")},
    "binary_sensor": {"leak_detected": ("Leak Detected", None)},
}


def _entities() -> list[tuple[str, object]]:
    coordinator = MagicMock()
    entry = MagicMock(entry_id="entry1", data={"device_id": 123456})
    entities = [("sensor", WaterSoftenerSensor(coordinator, entry, d)) for d in SENSOR_DESCRIPTIONS]
    entities += [("switch", WaterSoftenerSwitch(coordinator, entry, d)) for d in SWITCH_DESCRIPTIONS]
    entities += [("number", WaterSoftenerNumber(coordinator, entry, d)) for d in NUMBER_DESCRIPTIONS]
    entities += [
        ("time", RegenTimeEntity(coordinator, entry)),
        ("button", RegenNowButton(coordinator, entry)),
        ("binary_sensor", WaterSoftenerLeakSensor(coordinator, entry)),
    ]
    return entities


ENTITIES = _entities()


@pytest.mark.parametrize(("domain", "entity"), ENTITIES, ids=lambda v: v if isinstance(v, str) else "")
def test_every_entity_has_a_translated_name_equal_to_todays(domain, entity):
    key = entity.translation_key
    assert key, f"{type(entity).__name__} has no translation_key"
    name = TRANSLATIONS["entity"][domain][key]["name"]
    assert name == EXPECTED[domain][key][0]


@pytest.mark.parametrize(("domain", "entity"), ENTITIES, ids=lambda v: v if isinstance(v, str) else "")
def test_every_entity_with_an_icon_has_an_icons_json_entry(domain, entity):
    key = entity.translation_key
    icon = EXPECTED[domain][key][1]
    if icon is None:
        return
    assert ICONS["entity"][domain][key]["default"] == icon


@pytest.mark.parametrize(("domain", "entity"), ENTITIES, ids=lambda v: v if isinstance(v, str) else "")
def test_no_name_or_icon_is_left_in_the_code(domain, entity):
    description = getattr(entity, "entity_description", None)
    if description is not None:
        assert not isinstance(description.name, str), "name still in the description"
        assert description.icon is None
    assert getattr(entity, "_attr_icon", None) is None
    assert getattr(entity, "_attr_name", None) in (None, "")


def test_translations_have_no_unused_entity_keys():
    used = {(d, e.translation_key) for d, e in ENTITIES}
    listed = {(d, k) for d, keys in TRANSLATIONS["entity"].items() for k in keys}
    assert listed == used


async def test_home_assistant_loads_the_names_and_icons(hass, enable_custom_integrations):
    from homeassistant.helpers.icon import async_get_icons
    from homeassistant.helpers.translation import async_get_translations

    from custom_components.midea_water_softener.const import DOMAIN

    names = await async_get_translations(hass, "en", "entity", [DOMAIN])
    icons = await async_get_icons(hass, "entity", [DOMAIN])

    for domain, keys in EXPECTED.items():
        for key, (name, icon) in keys.items():
            assert names[f"component.{DOMAIN}.entity.{domain}.{key}.name"] == name
            if icon:
                assert icons[DOMAIN][domain][key]["default"] == icon
