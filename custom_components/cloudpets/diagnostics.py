"""Diagnostics support for CloudPets."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .coordinator import CloudPetsConfigEntry

TO_REDACT = {CONF_PASSWORD, "accessToken", "access_token", "token"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CloudPetsConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with credentials and raw identifiers redacted."""
    coordinator = entry.runtime_data
    data = coordinator.data
    diagnostics = {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "account": {
            "account": data.account,
            "user_id": data.user_id,
        },
        "feeders": {
            device_id: asdict(feeder)
            for device_id, feeder in data.feeders.items()
        },
    }
    return async_redact_data(diagnostics, TO_REDACT)
