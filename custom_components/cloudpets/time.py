"""Time entities for CloudPets."""

from __future__ import annotations

from datetime import time as dt_time
from typing import override

from homeassistant.components.time import TimeEntity
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
    """Set up CloudPets time entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        CloudPetsDesiccantReminderTime(coordinator, device_id)
        for device_id, feeder in coordinator.data.feeders.items()
        if feeder.desiccant.supported
    )


class CloudPetsDesiccantReminderTime(CloudPetsEntity, TimeEntity):
    """Desiccant reminder time."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:clock-outline"
    _attr_translation_key = "desiccant_reminder_time"

    def __init__(self, coordinator: CloudPetsCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "desiccant_reminder_time")

    @property
    def native_value(self) -> dt_time | None:
        """Return the reminder time."""
        value = self.feeder.desiccant.remind_time
        if not value:
            return None
        try:
            hour, minute = value.split(":")[:2]
            return dt_time(hour=int(hour), minute=int(minute))
        except (TypeError, ValueError):
            return None

    @override
    async def async_set_value(self, value: dt_time) -> None:
        """Update the reminder time."""
        await self.coordinator.async_set_desiccant(
            self._device_id,
            cycle_days=self.feeder.desiccant.cycle_days or 30,
            remind_time=value.strftime("%H:%M"),
        )
