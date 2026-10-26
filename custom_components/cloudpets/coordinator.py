"""Data coordinator for CloudPets."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    CloudPetsAPI,
    CloudPetsAPIError,
    CloudPetsAuthError,
    CloudPetsConnectionError,
    CloudPetsError,
    parse_device,
    parse_feeder,
    parse_plan,
)
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .models import CloudPetsData, DesiccantState, FeederData, FeedPlan

_LOGGER = logging.getLogger(__name__)

type CloudPetsConfigEntry = ConfigEntry[CloudPetsCoordinator]


class CloudPetsCoordinator(DataUpdateCoordinator[CloudPetsData]):
    """Fetch and cache CloudPets account data."""

    config_entry: CloudPetsConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: CloudPetsConfigEntry,
        *,
        account: str,
        password: str,
    ) -> None:
        self.account = account
        self.password = password
        self.api = CloudPetsAPI(async_get_clientsession(hass))
        scan_interval = config_entry.options.get(CONF_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN} {account}",
            update_interval=(
                DEFAULT_SCAN_INTERVAL
                if scan_interval is None
                else timedelta(seconds=scan_interval)
            ),
            always_update=False,
        )
        self.user_id: str | None = None

    async def async_login(self) -> None:
        """Authenticate with CloudPets."""
        try:
            result = await self.api.login(self.account, self.password)
        except CloudPetsAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except CloudPetsConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except CloudPetsError as err:
            raise UpdateFailed(str(err)) from err
        self.user_id = result.user_id

    async def _async_update_data(self) -> CloudPetsData:
        """Fetch all account data."""
        if self.api.token is None:
            await self.async_login()

        try:
            raw_devices = await self.api.async_get_devices()
            devices = [
                parsed
                for raw in raw_devices
                if (parsed := parse_device(raw)).get("id")
            ]
            feeders = await asyncio.gather(
                *(self._async_fetch_feeder(device) for device in devices)
            )
        except asyncio.CancelledError:
            raise
        except CloudPetsAuthError as err:
            # An expired token should trigger reauth, not an endless retry loop.
            raise ConfigEntryAuthFailed(str(err)) from err
        except CloudPetsConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except CloudPetsAPIError as err:
            raise UpdateFailed(str(err)) from err
        except CloudPetsError as err:
            raise UpdateFailed(str(err)) from err

        return CloudPetsData(
            account=self.account,
            user_id=self.user_id,
            feeders={feeder.id: feeder for feeder in feeders},
        )

    async def _async_fetch_feeder(self, device: dict[str, Any]) -> FeederData:
        home, battery, status, reminder = await self.api.async_get_feeder_snapshot(
            device["cloud_id"],
        )
        try:
            raw_plans = await self.api.async_get_plans(device["cloud_id"])
        except CloudPetsAuthError:
            raise
        except CloudPetsError:
            raw_plans = []
        plans = [
            parse_plan(raw_plan, index)
            for index, raw_plan in enumerate(raw_plans)
        ]
        payload = parse_feeder(
            device,
            home,
            battery,
            status,
            reminder,
            plans,
        )
        return _to_feeder(payload)

    async def async_feed(self, device_id: str, servings: int) -> None:
        """Dispense a manual feed."""
        await self._async_call(
            self.api.async_manual_feed(self._cloud_device_id(device_id), servings)
        )

    async def async_set_child_lock(self, device_id: str, locked: bool) -> None:
        """Set the child lock."""
        await self._async_call(
            self.api.async_set_child_lock(self._cloud_device_id(device_id), locked)
        )

    async def async_rename(self, device_id: str, name: str) -> None:
        """Rename a feeder."""
        await self._async_call(
            self.api.async_rename_device(self._cloud_device_id(device_id), name)
        )

    async def async_create_plan(
        self,
        device_id: str,
        *,
        name: str,
        hour: int,
        minute: int,
        servings: float,
        enabled: bool,
        days: list[int],
    ) -> None:
        """Create a feed plan."""
        await self._async_call(
            self.api.async_create_plan(
                self._cloud_device_id(device_id),
                name=name,
                hour=hour,
                minute=minute,
                servings=servings,
                enabled=enabled,
                days=days,
            )
        )

    async def async_update_plan(
        self,
        device_id: str,
        plan_id: str,
        *,
        name: str,
        hour: int,
        minute: int,
        servings: float,
        enabled: bool,
        days: list[int],
    ) -> None:
        """Update a feed plan."""
        await self._async_call(
            self.api.async_update_plan(
                self._cloud_device_id(device_id),
                plan_id,
                name=name,
                hour=hour,
                minute=minute,
                servings=servings,
                enabled=enabled,
                days=days,
            )
        )

    async def async_delete_plan(self, plan_id: str) -> None:
        """Delete a feed plan."""
        await self._async_call(self.api.async_delete_plan(plan_id))

    async def async_set_desiccant(
        self, device_id: str, *, cycle_days: int, remind_time: str
    ) -> None:
        """Set the desiccant cycle and reminder time."""
        await self._async_call(
            self.api.async_set_desiccant(
                self._cloud_device_id(device_id),
                cycle_days=cycle_days,
                remind_time=remind_time,
            )
        )

    async def async_reset_desiccant(self, device_id: str) -> None:
        """Reset the desiccant reminder."""
        await self._async_call(
            self.api.async_reset_desiccant(self._cloud_device_id(device_id))
        )

    def _cloud_device_id(self, device_id: str) -> int:
        """Return the numeric ID CloudPets expects in request payloads."""
        return self.data.feeders[device_id].cloud_device_id

    async def _async_call(self, awaitable: Any) -> None:
        try:
            await awaitable
        except CloudPetsAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except CloudPetsAPIError as err:
            raise HomeAssistantError(str(err)) from err
        except CloudPetsConnectionError as err:
            raise HomeAssistantError(str(err)) from err
        await self.async_request_refresh()


def _to_feeder(payload: dict[str, Any]) -> FeederData:
    raw_desiccant = payload.get("desiccant", {})
    desiccant = DesiccantState(
        supported=bool(raw_desiccant.get("supported")),
        remain_days=raw_desiccant.get("remain_days"),
        cycle_days=raw_desiccant.get("cycle_days"),
        remind_time=raw_desiccant.get("remind_time"),
        overdue=bool(raw_desiccant.get("overdue")),
    )
    plans = [
        FeedPlan(
            id=plan["id"],
            name=plan["name"],
            hour=plan["hour"],
            minute=plan["minute"],
            servings=plan["servings"],
            enabled=plan["enabled"],
            days=plan["days"],
            raw=plan["raw"],
        )
        for plan in payload.get("plans", [])
    ]
    return FeederData(
        id=payload["id"],
        cloud_device_id=payload["cloud_device_id"],
        name=payload["name"],
        model=payload.get("model") or "",
        online=bool(payload.get("online")),
        battery=payload.get("battery"),
        food_level=payload.get("food_level"),
        bowl_status=payload.get("bowl_status"),
        servings_today=payload.get("servings_today"),
        child_lock_supported=bool(payload.get("child_lock_supported")),
        child_locked=bool(payload.get("child_locked")),
        desiccant=desiccant,
        plans=plans,
        raw=payload.get("raw", {}),
    )
