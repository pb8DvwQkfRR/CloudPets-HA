"""Shared CloudPets entities."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_UNKNOWN
from .coordinator import CloudPetsCoordinator
from .models import FeederData


class CloudPetsConfigEntity(Entity):
    """Base entity that exposes the feeder's CloudPets device ID."""

    _cloudpets_device_id: str


class CloudPetsEntity(CoordinatorEntity[CloudPetsCoordinator]):
    """Base entity for a CloudPets feeder."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CloudPetsCoordinator,
        device_id: str,
        entity_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}_{entity_key}"

    @property
    def feeder(self) -> FeederData:
        """Return the current feeder data."""
        return self.coordinator.data.feeders[self._device_id]

    @property
    def available(self) -> bool:
        """Return whether the feeder is available."""
        return (
            super().available
            and self._device_id in self.coordinator.data.feeders
            and self.feeder.online
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer=MANUFACTURER,
            model=self.feeder.model or MODEL_UNKNOWN,
            name=self.feeder.name,
        )
