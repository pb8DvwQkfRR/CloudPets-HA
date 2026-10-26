"""CloudPets services for complete feed plan editing."""

from __future__ import annotations

from typing import Any

import probatio
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.service import async_get_device_and_config_entry

from .const import (
    ATTR_DAYS,
    ATTR_ENABLED,
    ATTR_NAME,
    ATTR_PLAN_ID,
    ATTR_SERVINGS,
    ATTR_TIME,
    DOMAIN,
    SERVICE_CREATE_FEED_PLAN,
    SERVICE_DELETE_FEED_PLAN,
    SERVICE_UPDATE_FEED_PLAN,
)
from .coordinator import CloudPetsCoordinator


def validate_plan(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a plan payload."""
    name = str(data.get(ATTR_NAME) or "").strip()
    if not name:
        raise probatio.Invalid("计划名称不能为空")

    raw_time = str(data.get(ATTR_TIME) or "")
    try:
        parsed_time = cv.time(raw_time)
    except probatio.Invalid as err:
        raise probatio.Invalid("time 应为 HH:MM") from err
    hour, minute = parsed_time.hour, parsed_time.minute

    servings = float(data[ATTR_SERVINGS])
    raw_days = data.get(ATTR_DAYS)
    values = raw_days.split(",") if isinstance(raw_days, str) else raw_days
    if not isinstance(values, list) or not values:
        raise probatio.Invalid("至少选择一个星期")

    days: set[int] = set()
    for raw in values:
        try:
            day = int(raw)
        except (TypeError, ValueError) as err:
            raise probatio.Invalid("days 使用 1–7，1 表示周一") from err
        if not 1 <= day <= 7:
            raise probatio.Invalid("days 使用 1–7，1 表示周一")
        days.add(day - 1)

    valid_servings = 0.5 <= servings <= 20 and abs(
        servings * 2 - round(servings * 2)
    ) < 1e-9
    if not valid_servings:
        raise probatio.Invalid("份量应为 0.5–20，步长 0.5")

    return {
        ATTR_NAME: name,
        "hour": hour,
        "minute": minute,
        ATTR_SERVINGS: servings,
        ATTR_ENABLED: bool(data.get(ATTR_ENABLED, True)),
        ATTR_DAYS: sorted(days),
    }


PLAN_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_DEVICE_ID): cv.string,
        probatio.Required(ATTR_NAME): cv.string,
        probatio.Required(ATTR_TIME): cv.string,
        probatio.Required(ATTR_SERVINGS): probatio.Coerce(float),
        probatio.Optional(ATTR_DAYS, default="1,2,3,4,5,6,7"): probatio.Any(
            cv.string,
            [probatio.Coerce(int)],
        ),
        probatio.Optional(ATTR_ENABLED, default=True): cv.boolean,
    }
)

UPDATE_PLAN_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_DEVICE_ID): cv.string,
        probatio.Required(ATTR_PLAN_ID): cv.string,
        probatio.Required(ATTR_NAME): cv.string,
        probatio.Required(ATTR_TIME): cv.string,
        probatio.Required(ATTR_SERVINGS): probatio.Coerce(float),
        probatio.Required(ATTR_DAYS): probatio.Any(
            cv.string,
            [probatio.Coerce(int)],
        ),
        probatio.Required(ATTR_ENABLED): cv.boolean,
    }
)

DELETE_PLAN_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_DEVICE_ID): cv.string,
        probatio.Required(ATTR_PLAN_ID): cv.string,
    }
)


def _coordinator_for_call(
    call: ServiceCall,
) -> tuple[dr.DeviceEntry, CloudPetsCoordinator]:
    device, entry = async_get_device_and_config_entry(
        call.hass,
        DOMAIN,
        str(call.data[ATTR_DEVICE_ID]),
        include_child_devices=False,
        include_main_devices=True,
    )
    return device, entry.runtime_data


async def _async_create_feed_plan(call: ServiceCall) -> None:
    """Create a feed plan."""
    device, coordinator = _coordinator_for_call(call)
    data = validate_plan(dict(call.data))
    await coordinator.async_create_plan(
        _cloudpets_device_id(device),
        name=data[ATTR_NAME],
        hour=data["hour"],
        minute=data["minute"],
        servings=data[ATTR_SERVINGS],
        enabled=data[ATTR_ENABLED],
        days=data[ATTR_DAYS],
    )


async def _async_update_feed_plan(call: ServiceCall) -> None:
    """Update a feed plan."""
    device, coordinator = _coordinator_for_call(call)
    data = validate_plan(dict(call.data))
    await coordinator.async_update_plan(
        _cloudpets_device_id(device),
        str(call.data[ATTR_PLAN_ID]),
        name=data[ATTR_NAME],
        hour=data["hour"],
        minute=data["minute"],
        servings=data[ATTR_SERVINGS],
        enabled=data[ATTR_ENABLED],
        days=data[ATTR_DAYS],
    )


async def _async_delete_feed_plan(call: ServiceCall) -> None:
    """Delete a feed plan."""
    _, coordinator = _coordinator_for_call(call)
    await coordinator.async_delete_plan(str(call.data[ATTR_PLAN_ID]))


def _cloudpets_device_id(device: dr.DeviceEntry) -> str:
    for domain, identifier in device.identifiers:
        if domain == DOMAIN:
            return identifier
    raise ServiceValidationError("CloudPets 设备标识缺失")


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register CloudPets plan services once."""
    if hass.services.has_service(DOMAIN, SERVICE_CREATE_FEED_PLAN):
        return
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_FEED_PLAN,
        _async_create_feed_plan,
        schema=PLAN_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_FEED_PLAN,
        _async_update_feed_plan,
        schema=UPDATE_PLAN_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_FEED_PLAN,
        _async_delete_feed_plan,
        schema=DELETE_PLAN_SCHEMA,
    )
