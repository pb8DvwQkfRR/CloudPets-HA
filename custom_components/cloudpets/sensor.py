"""Sensors for CloudPets."""

from __future__ import annotations

from datetime import date, timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import CloudPetsConfigEntry, CloudPetsCoordinator
from .entity import CloudPetsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CloudPetsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up CloudPets sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []
    for device_id, feeder in coordinator.data.feeders.items():
        entities.extend(
            [
                CloudPetsBatterySensor(coordinator, device_id),
                CloudPetsFoodLevelSensor(coordinator, device_id),
                CloudPetsServingsTodaySensor(coordinator, device_id),
                CloudPetsStatusSensor(coordinator, device_id),
            ]
        )
        if feeder.desiccant.supported:
            entities.extend(
                [
                    CloudPetsDesiccantRemainingSensor(coordinator, device_id),
                    CloudPetsDesiccantDueSensor(coordinator, device_id),
                ]
            )
    async_add_entities(entities)


class CloudPetsBatterySensor(CloudPetsEntity, SensorEntity):
    """Battery percentage."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "battery"

    def __init__(self, coordinator: CloudPetsCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "battery")

    @property
    def native_value(self) -> int | None:
        """Return battery percentage."""
        return self.feeder.battery


class CloudPetsFoodLevelSensor(CloudPetsEntity, SensorEntity):
    """Food bin percentage."""

    _attr_icon = "mdi:food-variant"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "food_level"

    def __init__(self, coordinator: CloudPetsCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "food_level")

    @property
    def native_value(self) -> int | None:
        """Return food bin percentage."""
        return self.feeder.food_level


class CloudPetsServingsTodaySensor(CloudPetsEntity, SensorEntity):
    """Servings dispensed today."""

    _attr_icon = "mdi:utensils"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_translation_key = "servings_today"

    def __init__(self, coordinator: CloudPetsCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "servings_today")

    @property
    def native_value(self) -> float | None:
        """Return servings dispensed today."""
        return self.feeder.servings_today


class CloudPetsStatusSensor(CloudPetsEntity, SensorEntity):
    """Feeder bowl status."""

    _attr_icon = "mdi:information-outline"
    _attr_translation_key = "status"

    def __init__(self, coordinator: CloudPetsCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "status")

    @property
    def native_value(self) -> str:
        """Return feeder status."""
        return self.feeder.bowl_status or "unknown"


class CloudPetsDesiccantRemainingSensor(CloudPetsEntity, SensorEntity):
    """Days left before replacing the desiccant."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:water-percent"
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "desiccant_remaining"

    def __init__(self, coordinator: CloudPetsCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "desiccant_remaining")

    @property
    def native_value(self) -> int | None:
        """Return remaining days."""
        return self.feeder.desiccant.remain_days


class CloudPetsDesiccantDueSensor(CloudPetsEntity, SensorEntity):
    """Calculated date on which the desiccant is due."""

    _attr_device_class = SensorDeviceClass.DATE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "desiccant_due"

    def __init__(self, coordinator: CloudPetsCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "desiccant_due")

    @property
    def native_value(self) -> date | None:
        """Return the due date."""
        remaining = self.feeder.desiccant.remain_days
        if remaining is None:
            return None
        return dt_util.now().date() + timedelta(days=remaining)
