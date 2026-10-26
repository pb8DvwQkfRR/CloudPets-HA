"""Binary sensors for CloudPets."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import CloudPetsConfigEntry, CloudPetsCoordinator
from .entity import CloudPetsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CloudPetsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up CloudPets binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for device_id in coordinator.data.feeders:
        entities.extend(
            [
                CloudPetsOnlineBinarySensor(coordinator, device_id),
                CloudPetsDesiccantOverdueBinarySensor(coordinator, device_id),
            ]
        )
    async_add_entities(entities)


class CloudPetsOnlineBinarySensor(CloudPetsEntity, BinarySensorEntity):
    """Online state of a feeder."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "online"

    def __init__(self, coordinator: CloudPetsCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "online")

    @property
    def is_on(self) -> bool:
        """Return whether the feeder is online."""
        return self.feeder.online

    @property
    def available(self) -> bool:
        """Online sensors must remain readable while offline."""
        return self.coordinator.last_update_success and self._device_id in (
            self.coordinator.data.feeders
        )


class CloudPetsDesiccantOverdueBinarySensor(CloudPetsEntity, BinarySensorEntity):
    """Whether the desiccant is overdue."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "desiccant_overdue"

    def __init__(self, coordinator: CloudPetsCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "desiccant_overdue")

    @property
    def is_on(self) -> bool:
        """Return whether the desiccant is overdue."""
        return self.feeder.desiccant.overdue

    @property
    def available(self) -> bool:
        """Keep the diagnostic readable while the feeder is offline."""
        return (
            self.coordinator.last_update_success
            and self._device_id in self.coordinator.data.feeders
            and self.feeder.desiccant.supported
        )
