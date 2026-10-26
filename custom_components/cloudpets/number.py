"""Number entities for CloudPets."""

from __future__ import annotations

from typing import override

from homeassistant.components.number import (
    NumberEntity,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import CloudPetsConfigEntry, CloudPetsCoordinator
from .entity import CloudPetsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CloudPetsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up CloudPets number entities."""
    coordinator = entry.runtime_data
    entities: list[NumberEntity] = []
    for device_id, feeder in coordinator.data.feeders.items():
        entities.append(CloudPetsFeedServingsNumber(coordinator, device_id))
        if feeder.desiccant.supported:
            entities.append(CloudPetsDesiccantCycleNumber(coordinator, device_id))
    async_add_entities(entities)


class CloudPetsFeedServingsNumber(CloudPetsEntity, RestoreNumber):
    """Amount used by the manual feed button."""

    _attr_icon = "mdi:utensils"
    _attr_mode = NumberMode.BOX
    _attr_native_max_value = 20
    _attr_native_min_value = 1
    _attr_native_step = 1
    _attr_native_value = 1
    _attr_translation_key = "manual_feed_servings"

    def __init__(self, coordinator: CloudPetsCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "manual_feed_servings")

    @override
    async def async_added_to_hass(self) -> None:
        """Restore the selected serving amount."""
        await super().async_added_to_hass()
        if (last_data := await self.async_get_last_number_data()) is not None:
            self._attr_native_value = last_data.native_value

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Store the selected serving amount locally."""
        self._attr_native_value = int(round(value))
        self.async_write_ha_state()


class CloudPetsDesiccantCycleNumber(CloudPetsEntity, NumberEntity):
    """Desiccant replacement cycle."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:refresh-circle"
    _attr_mode = NumberMode.BOX
    _attr_native_max_value = 90
    _attr_native_min_value = 1
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_translation_key = "desiccant_cycle"

    def __init__(self, coordinator: CloudPetsCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "desiccant_cycle")

    @property
    def native_value(self) -> float | None:
        """Return the configured cycle."""
        cycle_days = self.feeder.desiccant.cycle_days
        return float(cycle_days) if cycle_days is not None else None

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Update the desiccant cycle."""
        remind_time = self.feeder.desiccant.remind_time or "08:00"
        await self.coordinator.async_set_desiccant(
            self._device_id,
            cycle_days=int(round(value)),
            remind_time=remind_time,
        )
