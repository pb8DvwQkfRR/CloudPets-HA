"""Small async client for the CloudPets mobile API."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from aiohttp import ClientError, ClientSession

from .const import API_BASE


class CloudPetsError(Exception):
    """Base error from the CloudPets API."""


class CloudPetsAuthError(CloudPetsError):
    """CloudPets rejected the credentials or session."""


class CloudPetsConnectionError(CloudPetsError):
    """CloudPets could not be reached."""


class CloudPetsAPIError(CloudPetsError):
    """CloudPets returned an API error."""

    def __init__(self, message: str, code: int | None = None) -> None:
        """Initialize the API error."""
        super().__init__(message)
        self.code = code


@dataclass(slots=True)
class LoginResult:
    """Result of a login request."""

    token: str
    user_id: str | None
    nickname: str | None


class CloudPetsAPI:
    """CloudPets API client.

    The upstream API returns HTTP 200 with an application-level ``code``.
    A non-200 application code is treated as an API error.
    """

    def __init__(
        self,
        session: ClientSession,
        *,
        base_url: str = API_BASE,
        timeout: float = 15,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self.token: str | None = None

    async def login(self, account: str, password: str) -> LoginResult:
        """Log in and store the access token."""
        try:
            payload, headers = await self._request(
                "POST",
                "/terminal/user/login",
                form={
                    "account": account,
                    "pwd": password,
                    "jpushId": "",
                    "userType": "2",
                },
            )
        except CloudPetsAPIError as err:
            if err.code in (400, 401, 403):
                raise CloudPetsAuthError("账号或密码不正确") from err
            raise
        token = self._extract_token(payload, headers)
        if not token:
            raise CloudPetsAuthError("登录响应中没有访问令牌")
        self.token = token
        result = _record(payload.get("result"))
        token_pair = _record(payload.get("tokenPair"))
        user = _record(result.get("userInfo") or result.get("user") or result)
        user_id = _string(
            user.get("userId")
            or user.get("userID")
            or user.get("id")
            or token_pair.get("userId")
            or token_pair.get("uid")
            or None
        )
        nickname = _string(
            user.get("nickname") or user.get("nickName") or user.get("userName") or None
        )
        return LoginResult(token=token, user_id=user_id or None, nickname=nickname or None)

    async def async_get_devices(self) -> list[dict[str, Any]]:
        """Return the account's devices."""
        payload = await self._request_json("GET", "/terminal/device/userDevices")
        result = payload.get("result")
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        result_record = _record(result)
        for key in ("devices", "list", "userDevices"):
            value = result_record.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    async def async_get_feeder_snapshot(
        self, cloud_device_id: int
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Fetch home, battery, status and reminder data in parallel.

        Optional telemetry failures do not make the whole feeder unavailable.
        Authentication failures are always propagated.
        """
        responses = await asyncio.gather(
            self._request_json(
                "GET",
                "/terminal/feeder/home",
                params={"deviceId": str(cloud_device_id)},
            ),
            self._request_json(
                "POST",
                "/terminal/feeder/battery",
                form={"deviceId": cloud_device_id},
            ),
            self._request_json(
                "POST",
                "/terminal/feeder/status",
                form={"deviceId": cloud_device_id},
            ),
            self._request_json(
                "GET",
                "/terminal/device/remind/config",
                params={"deviceId": str(cloud_device_id), "type": "1"},
            ),
            return_exceptions=True,
        )
        for response in responses:
            if isinstance(response, CloudPetsAuthError):
                raise response
        return tuple(
            _payload_result(response) if isinstance(response, dict) else {}
            for response in responses
        )

    async def async_get_plans(self, cloud_device_id: int) -> list[dict[str, Any]]:
        """Return feed plans for a feeder."""
        payload = await self._request_json(
            "GET",
            f"/terminal/feeder/planList/{quote(str(cloud_device_id), safe='')}",
            params={"pageSize": "1000"},
        )
        result = payload.get("result")
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        result_record = _record(result)
        for key in ("plans", "list", "feedPlans"):
            value = result_record.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    async def async_manual_feed(self, cloud_device_id: int, servings: int) -> None:
        """Dispense food immediately."""
        await self._request_json(
            "POST",
            "/terminal/feeder/manualFeed",
            form={"deviceId": cloud_device_id, "unit": servings},
        )

    async def async_set_child_lock(self, cloud_device_id: int, locked: bool) -> None:
        """Set the child lock."""
        await self._request_json(
            "POST",
            "/terminal/event/device/device_child_lock",
            json={
                "deviceId": cloud_device_id,
                "value": {"enable": locked},
            },
        )

    async def async_rename_device(self, cloud_device_id: int, name: str) -> None:
        """Rename a device."""
        await self._request_json(
            "POST",
            "/terminal/device/updateName",
            form={"deviceId": cloud_device_id, "deviceName": name},
        )

    async def async_create_plan(
        self,
        cloud_device_id: int,
        *,
        name: str,
        hour: int,
        minute: int,
        servings: float,
        enabled: bool,
        days: list[int],
    ) -> str | None:
        """Create a feed plan."""
        payload = await self._request_json(
            "POST",
            "/terminal/feeder/feedPlan",
            form=_plan_form(
                cloud_device_id,
                name=name,
                hour=hour,
                minute=minute,
                servings=servings,
                enabled=enabled,
                days=days,
            ),
        )
        result = _record(payload.get("result"))
        return (
            _string(
                result.get("id")
                or result.get("planId")
                or payload.get("id")
                or payload.get("planId")
            )
            or None
        )

    async def async_update_plan(
        self,
        cloud_device_id: int,
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
        await self._request_json(
            "PUT",
            "/terminal/feeder/feedPlan",
            form=_plan_form(
                cloud_device_id,
                name=name,
                hour=hour,
                minute=minute,
                servings=servings,
                enabled=enabled,
                days=days,
                plan_id=plan_id,
            ),
        )

    async def async_delete_plan(self, plan_id: str) -> None:
        """Delete a feed plan."""
        await self._request_json(
            "DELETE", f"/terminal/feeder/plan/{quote(str(plan_id), safe='')}"
        )

    async def async_set_desiccant(
        self,
        cloud_device_id: int,
        *,
        cycle_days: int,
        remind_time: str,
    ) -> None:
        """Update the desiccant reminder."""
        await self._request_json(
            "PUT",
            "/terminal/device/remind",
            json={
                "enable": True,
                "deviceId": cloud_device_id,
                "type": 1,
                "cycleDays": cycle_days,
                "remindTime": remind_time,
            },
        )

    async def async_reset_desiccant(self, cloud_device_id: int) -> None:
        """Mark the desiccant as replaced."""
        await self._request_json(
            "POST",
            "/terminal/device/remind/reset",
            json={"deviceId": cloud_device_id, "type": 1},
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json: dict[str, Any] | None = None,
        form: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload, _ = await self._request(
            method, path, params=params, json=json, form=form
        )
        return payload

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json: dict[str, Any] | None = None,
        form: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], Mapping[str, str]]:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "CloudPets-HomeAssistant/0.1",
        }
        if self.token:
            headers["Authorization"] = self.token
        if form is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"

        kwargs: dict[str, Any] = {"headers": headers}
        if params is not None:
            kwargs["params"] = params
        if json is not None:
            kwargs["json"] = json
        if form is not None:
            kwargs["data"] = {
                key: _bool_string(value) for key, value in form.items()
            }

        try:
            async with self._session.request(
                method,
                f"{self._base_url}{path}",
                timeout=self._timeout,
                **kwargs,
            ) as response:
                text = await response.text()
                if response.status in (401, 403):
                    raise CloudPetsAuthError(f"CloudPets 登录已失效（HTTP {response.status}）")
                if response.status >= 400:
                    raise CloudPetsAPIError(
                        f"CloudPets 请求失败（HTTP {response.status}）"
                    )
                payload = _json_object(text)
                if payload is None:
                    raise CloudPetsAPIError("CloudPets 返回了非 JSON 响应")
                code = _int(payload.get("code"), default=200)
                if code != 200:
                    message = _string(payload.get("message") or payload.get("msg"))
                    if code in (401, 403):
                        raise CloudPetsAuthError(message or "CloudPets 登录已失效")
                    raise CloudPetsAPIError(
                        message or f"CloudPets 请求失败（{code}）",
                        code,
                    )
                return payload, response.headers
        except CloudPetsError:
            raise
        except TimeoutError as err:
            raise CloudPetsConnectionError("CloudPets 请求超时") from err
        except (ClientError, OSError) as err:
            raise CloudPetsConnectionError(f"CloudPets 服务不可达：{err}") from err

    @staticmethod
    def _extract_token(
        payload: Mapping[str, Any], headers: Mapping[str, str]
    ) -> str | None:
        token_pair = _record(payload.get("tokenPair"))
        result = _record(payload.get("result"))
        return (
            _string(
                token_pair.get("accessToken")
                or token_pair.get("access_token")
                or result.get("token")
                or result.get("accessToken")
                or result.get("access_token")
                or payload.get("token")
                or payload.get("accessToken")
            )
            or _bearer_token(headers.get("Authorization"))
            or None
        )


def _plan_form(
    cloud_device_id: int,
    *,
    name: str,
    hour: int,
    minute: int,
    servings: float,
    enabled: bool,
    days: list[int],
    plan_id: str | None = None,
) -> dict[str, Any]:
    form: dict[str, Any] = {
        "deviceId": cloud_device_id,
        "remark": name,
        "hour": hour,
        "minute": minute,
        "serving": _number(servings),
        "enable": enabled,
        "daysOfWeek": ",".join(str(day + 1) for day in sorted(days)),
    }
    if plan_id is not None:
        form["id"] = plan_id
    return form


def _payload_result(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    return _record(result) if result is not None else dict(payload)


def _json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return {}
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def _int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _bool_string(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    """Return the first value that is present and not None."""
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def _bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    token = value.strip()
    if token.lower().startswith("bearer "):
        return token[7:].strip()
    return token


def _parse_days(value: Any) -> list[int]:
    """Parse the API's 1-based weekday list into Python weekdays."""
    if isinstance(value, str):
        raw_days = value.split(",")
    elif isinstance(value, (int, float)):
        raw_days = [value]
    elif isinstance(value, (list, tuple)):
        raw_days = list(value)
    else:
        raw_days = []

    days: set[int] = set()
    for raw_day in raw_days:
        try:
            day = int(raw_day)
        except (TypeError, ValueError):
            continue
        if 1 <= day <= 7:
            days.add(day - 1)
    return sorted(days)


def parse_plan(item: Mapping[str, Any], index: int = 0) -> dict[str, Any]:
    """Parse one plan item returned by the CloudPets API."""
    hour = _int(item.get("hour"), default=-1)
    minute = _int(item.get("minute"), default=0)
    feed_time = _string(item.get("feedtime") or item.get("feedTime") or item.get("time"))
    if hour < 0 and ":" in feed_time:
        try:
            hour, minute = (int(part) for part in feed_time.split(":")[:2])
        except ValueError:
            hour = 8
    elif hour < 0:
        hour = 8
    servings = _float(
        item.get("serving", item.get("feedweight", item.get("weight", 1))),
        default=1,
    )
    return {
        "id": _string(item.get("id") or item.get("planId") or index),
        "name": _string(
            item.get("remark") or item.get("planName") or item.get("name")
        )
        or f"计划 {index + 1}",
        "hour": hour,
        "minute": minute,
        "servings": servings,
        "enabled": _bool(
            item.get("enable", item.get("enabled", item.get("status", True))),
            default=True,
        ),
        "days": _parse_days(
            item.get(
                "daysOfWeek",
                item.get("repeat", item.get("weekDays", item.get("weekdays"))),
            )
        ),
        "raw": dict(item),
    }


def parse_device(item: Mapping[str, Any]) -> dict[str, Any]:
    """Parse one device item returned by the CloudPets API."""
    return {
        "id": _string(item.get("id") or item.get("deviceId") or item.get("deviceID")),
        "cloud_id": _int(item.get("id"), default=0),
        "name": _string(item.get("name") or item.get("deviceName")),
        "model": _string(item.get("model") or item.get("deviceModel")),
        "online": _bool(_first(item, "connect", "online", "onlineStatus")),
        "battery": _int(_first(item, "battery", "batteryPercentage"), default=0)
        if _first(item, "battery", "batteryPercentage") is not None
        else None,
        "raw": dict(item),
    }


def parse_feeder(
    device: Mapping[str, Any],
    home: Mapping[str, Any],
    battery: Mapping[str, Any],
    status: Mapping[str, Any],
    reminder: Mapping[str, Any],
    plans: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge the CloudPets feeder responses into a normalized payload."""
    merged = {
        **device.get("raw", {}),
        **home,
        **battery,
        **status,
        **reminder,
    }
    config = _record(merged.get("deviceConfig") or merged.get("config"))

    remain_days_raw = _first(
        merged,
        "drierRemainDays",
        "drierLeftDays",
        "desiccantRemainDays",
        "desiccantDays",
        "leftDays",
    )
    cycle_days_raw = _first(
        merged,
        "currentDays",
        "filter_days",
        "filterDays",
    )
    if cycle_days_raw is None:
        cycle_days_raw = config.get("filterDays")
    remind_time = _string(merged.get("remindTime") or config.get("remindTime"))
    percent_state = merged.get("percentState")
    battery_level = _first(
        merged,
        "batteryLevel",
        "batteryPercentage",
        "battery",
        "electricity",
    )
    servings_raw = _first(
        merged,
        "servingsToday",
        "todayFeedCount",
        "feedCount",
        "feed_count",
    )
    if servings_raw is None:
        servings_raw = _record(merged.get("feedingStatistics")).get("today")
    child_lock_value = _first(merged, "isSupportChildLock", "supportChildLock")
    if child_lock_value is None:
        child_lock_value = config.get("isSupportChildLock")
    # The child lock endpoint is available even when home omits a support flag.
    child_lock_supported = _bool(child_lock_value, default=True)
    child_locked_value = _first(
        merged,
        "childLock",
        "child_lock",
        "isChildLock",
    )
    desiccant_support_value = _first(
        merged,
        "isSupportDesiccant",
        "desiccant",
        "supportDesiccant",
    )
    online_value = _first(merged, "connect", "online", "onlineStatus")

    return {
        "id": _string(merged.get("id") or device.get("id")),
        "cloud_device_id": device.get("cloud_id", 0),
        "name": _string(merged.get("deviceName") or merged.get("name")) or "喂食器",
        "model": _string(merged.get("model") or device.get("model")),
        "online": _bool(
            online_value if online_value is not None else device.get("online")
        ),
        "battery": _int(battery_level, default=0)
        if battery_level is not None
        else None,
        "food_level": _int(percent_state, default=0)
        if percent_state is not None
        else None,
        "bowl_status": _string(
            merged.get("feedState") or merged.get("bowlStatus") or merged.get("statusText")
        )
        or None,
        "servings_today": _float(servings_raw, default=0)
        if servings_raw is not None
        else None,
        "child_lock_supported": child_lock_supported,
        "child_locked": _bool(
            child_locked_value
            if child_locked_value is not None
            else config.get("childLock")
        ),
        "desiccant": {
            "supported": remain_days_raw is not None
            or _bool(
                desiccant_support_value
                if desiccant_support_value is not None
                else config.get("isSupportDesiccant")
            ),
            "remain_days": _int(remain_days_raw, default=0)
            if remain_days_raw is not None
            else None,
            "cycle_days": _int(cycle_days_raw, default=0)
            if cycle_days_raw is not None
            else None,
            "remind_time": remind_time or None,
            "overdue": _bool(
                merged.get("desiccantExhausted"),
                default=_int(remain_days_raw, default=0) < 0,
            ),
        },
        "plans": plans,
        "raw": merged,
    }
