"""Switches for CloudPets."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import CloudPetsConfigEntry, CloudPetsCoordinator
from .entity import CloudPetsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CloudPetsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up CloudPets switches."""
    coordinator = entry.runtime_data
    async_add_entities(
        CloudPetsChildLockSwitch(coordinator, device_id)
        for device_id, feeder in coordinator.data.feeders.items()
        if feeder.child_lock_supported
    )


class CloudPetsChildLockSwitch(CloudPetsEntity, SwitchEntity):
    """Child lock switch."""

    _attr_icon = "mdi:lock-outline"
    _attr_translation_key = "child_lock"

    def __init__(self, coordinator: CloudPetsCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "child_lock")

    @property
    def is_on(self) -> bool:
        """Return whether the child lock is enabled."""
        return self.feeder.child_locked

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the child lock."""
        await self.coordinator.async_set_child_lock(self._device_id, True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the child lock."""
        await self.coordinator.async_set_child_lock(self._device_id, False)
