"""Rewrite entity unique IDs from the config entry ID to the device ID."""
from __future__ import annotations

import logging

from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import entity_registry as er

from .coordinator import WaterSoftenerConfigEntry
from .device_info import unique_id_prefix

_LOGGER = logging.getLogger(__name__)


async def async_migrate_unique_ids(hass, entry: WaterSoftenerConfigEntry) -> None:
    """Change unique IDs from "<entry_id>_<key>" to "<device_id>_<key>", in place.

    Entity IDs, history and automations are kept, because the registry rows are
    updated, not replaced. Safe to run twice: IDs that do not start with the
    config entry ID are left alone. Every clash is found before anything is
    changed, so a clash leaves the registry as it was.
    """
    registry = er.async_get(hass)
    old_prefix = f"{entry.entry_id}_"
    new_prefix = f"{unique_id_prefix(entry)}_"

    new_ids: dict[str, str] = {}  # entity_id -> new unique ID
    for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg.unique_id.startswith(old_prefix):
            new_ids[reg.entity_id] = new_prefix + reg.unique_id[len(old_prefix):]
    if not new_ids:
        return

    taken: dict[tuple[str, str, str], str] = {}
    for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg.entity_id in new_ids:
            key = (reg.domain, reg.platform, new_ids[reg.entity_id])
            if key in taken:
                raise ConfigEntryError(
                    f"Cannot migrate unique IDs: {reg.entity_id} and {taken[key]} "
                    f"would both become {key[2]}"
                )
            taken[key] = reg.entity_id
            owner = registry.async_get_entity_id(*key)
            if owner is not None:
                raise ConfigEntryError(
                    f"Cannot migrate unique IDs: {reg.entity_id} would become "
                    f"{key[2]}, which {owner} already has. Nothing was changed."
                )

    _LOGGER.info("Migrating %d entity unique IDs to the device ID", len(new_ids))
    await er.async_migrate_entries(
        hass,
        entry.entry_id,
        lambda reg: (
            {"new_unique_id": new_ids[reg.entity_id]} if reg.entity_id in new_ids else None
        ),
    )
