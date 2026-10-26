"""Buttons for CloudPets."""

from __future__ import annotations

from typing import override

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import CloudPetsConfigEntry, CloudPetsCoordinator
from .entity import CloudPetsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CloudPetsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up CloudPets buttons."""
    coordinator = entry.runtime_data
    entities: list[ButtonEntity] = []
    for device_id, feeder in coordinator.data.feeders.items():
        entities.append(CloudPetsFeedNowButton(coordinator, device_id))
        if feeder.desiccant.supported:
            entities.append(CloudPetsDesiccantResetButton(coordinator, device_id))
    async_add_entities(entities)


class CloudPetsFeedNowButton(CloudPetsEntity, ButtonEntity):
    """Dispense the configured number of servings."""

    _attr_icon = "mdi:food-drumstick"
    _attr_translation_key = "feed_now"

    def __init__(self, coordinator: CloudPetsCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "feed_now")

    @override
    async def async_press(self) -> None:
        """Dispense food."""
        servings = await self._async_get_servings()
        await self.coordinator.async_feed(self._device_id, servings)

    async def _async_get_servings(self) -> int:
        entity_id = self._servings_entity_id()
        if entity_id is None:
            return 1
        state = self.hass.states.get(entity_id)
        if state is None:
            return 1
        try:
            servings = int(round(float(state.state)))
        except ValueError:
            return 1
        return min(20, max(1, servings))

    def _servings_entity_id(self) -> str | None:
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(self.hass)
        for entry in registry.entities.values():
            if (
                entry.platform == DOMAIN
                and entry.unique_id == f"{self._device_id}_manual_feed_servings"
            ):
                return entry.entity_id
        return None


class CloudPetsDesiccantResetButton(CloudPetsEntity, ButtonEntity):
    """Mark the desiccant as replaced."""

    _attr_icon = "mdi:restart"
    _attr_translation_key = "desiccant_reset"

    def __init__(self, coordinator: CloudPetsCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "desiccant_reset")

    @override
    async def async_press(self) -> None:
        """Reset the desiccant reminder."""
        await self.coordinator.async_reset_desiccant(self._device_id)
