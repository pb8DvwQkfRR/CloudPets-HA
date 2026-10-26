"""The CloudPets integration."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, PLATFORMS
from .coordinator import CloudPetsConfigEntry, CloudPetsCoordinator
from .services import async_setup_services

PLATFORM_LIST: list[Platform] = [Platform(platform) for platform in PLATFORMS]

__all__ = ["DOMAIN", "async_setup_entry", "async_unload_entry"]


async def async_setup_entry(hass: HomeAssistant, entry: CloudPetsConfigEntry) -> bool:
    """Set up CloudPets from a config entry."""
    coordinator = CloudPetsCoordinator(
        hass,
        entry,
        account=str(entry.data[CONF_USERNAME]),
        password=str(entry.data[CONF_PASSWORD]),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    _async_migrate_stale_devices(hass, entry, coordinator)
    async_setup_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORM_LIST)
    return True


@callback
def _async_migrate_stale_devices(
    hass: HomeAssistant,
    entry: CloudPetsConfigEntry,
    coordinator: CloudPetsCoordinator,
) -> None:
    """Migrate registry entries from a CloudPets device ID that no longer exists."""
    live_ids = set(coordinator.data.feeders)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    stale_devices: list[tuple[str, str, str]] = []
    live_entity_ids: set[str] = set()
    for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if any(entity.unique_id.startswith(f"{device_id}_") for device_id in live_ids):
            live_entity_ids.add(entity.unique_id)
    live_by_name: dict[str, list[str]] = {}
    for device_id, feeder in coordinator.data.feeders.items():
        live_by_name.setdefault(feeder.name, []).append(device_id)
    registered_devices = list(
        dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    )
    live_device_ids: dict[str, str] = {}
    for device in registered_devices:
        identifiers = [
            identifier
            for domain, identifier in device.identifiers
            if domain == DOMAIN
        ]
        if identifiers and identifiers[0] in live_ids:
            live_device_ids[identifiers[0]] = device.id

    for device in registered_devices:
        identifiers = [
            identifier
            for domain, identifier in device.identifiers
            if domain == DOMAIN
        ]
        if not identifiers:
            continue
        device_id = identifiers[0]
        if device_id in live_ids:
            continue
        matches = live_by_name.get(device.name or "", [])
        if len(matches) == 1:
            new_device_id = live_device_ids.get(matches[0])
            if new_device_id is not None:
                stale_devices.append((device.id, new_device_id, matches[0]))

    if not stale_devices:
        return

    for entity in list(
        er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    ):
        replacement = next(
            (
                (new_id, new_device_id)
                for stale_id, new_device_id, new_id in stale_devices
                if stale_id == entity.device_id
            ),
            None,
        )
        if replacement is None:
            continue
        new_id, new_device_id = replacement
        if "_" in entity.unique_id:
            suffix = entity.unique_id.split("_", 1)[1]
            new_unique_id = f"{new_id}_{suffix}"
            if new_unique_id in live_entity_ids:
                entity_registry.async_remove(entity.entity_id)
            else:
                entity_registry.async_update_entity(
                    entity.entity_id,
                    new_unique_id=new_unique_id,
                    device_id=new_device_id,
                )

    for device_id, _, _ in stale_devices:
        device_registry.async_remove_device(device_id)


async def async_unload_entry(hass: HomeAssistant, entry: CloudPetsConfigEntry) -> bool:
    """Unload a CloudPets config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORM_LIST)
