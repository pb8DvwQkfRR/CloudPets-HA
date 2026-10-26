"""Config flow for CloudPets."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, override

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    TimeSelector,
)

from .api import (
    CloudPetsAPI,
    CloudPetsAuthError,
    CloudPetsConnectionError,
    CloudPetsError,
)
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .services import validate_plan

DAY_LABELS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


class CloudPetsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a CloudPets config flow."""

    VERSION = 1

    async def _async_validate(
        self, account: str, password: str
    ) -> tuple[CloudPetsAPI | None, str | None]:
        api = CloudPetsAPI(async_get_clientsession(self.hass))
        try:
            await api.login(account, password)
            if not await api.async_get_devices():
                return None, "no_devices"
        except CloudPetsAuthError:
            return None, "invalid_auth"
        except CloudPetsConnectionError:
            return None, "cannot_connect"
        except CloudPetsError:
            return None, "unknown"
        return api, None

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle credentials entered by the user."""
        errors: dict[str, str] = {}
        if user_input is not None:
            account = str(user_input[CONF_USERNAME]).strip()
            password = str(user_input[CONF_PASSWORD])
            api, error = await self._async_validate(account, password)
            if error is not None:
                errors["base"] = error
            else:
                await self.async_set_unique_id(account)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=account,
                    data={
                        CONF_USERNAME: account,
                        CONF_PASSWORD: password,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_USERNAME): TextSelector(
                        TextSelectorConfig(autocomplete="username")
                    ),
                    probatio.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(
                            type=TextSelectorType.PASSWORD,
                            autocomplete="current-password",
                        )
                    ),
                }
            ),
            errors=errors,
        )

    @override
    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle an expired CloudPets session."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for new credentials after reauthentication."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            password = str(user_input[CONF_PASSWORD])
            api, error = await self._async_validate(
                str(entry.data[CONF_USERNAME]), password
            )
            if error is not None:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_PASSWORD: password},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(
                            type=TextSelectorType.PASSWORD,
                            autocomplete="current-password",
                        )
                    )
                }
            ),
            errors=errors,
            description_placeholders={
                CONF_USERNAME: str(entry.data[CONF_USERNAME])
            },
        )

    @staticmethod
    def async_get_options_flow(config_entry: Any) -> CloudPetsOptionsFlow:
        """Return the options flow."""
        return CloudPetsOptionsFlow()


class CloudPetsOptionsFlow(OptionsFlowWithReload):
    """Manage CloudPets plans and polling."""

    def __init__(self) -> None:
        self._plan_options: dict[str, tuple[str, str]] = {}
        self._selected_plan: tuple[str, str] | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["manage_plans", "settings"],
        )

    async def async_step_manage_plans(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show plan management actions."""
        menu_options = ["plan_overview", "add_plan"]
        if self._plans():
            menu_options.extend(["edit_plan_select", "delete_plan_select"])
        return self.async_show_menu(
            step_id="manage_plans",
            menu_options=menu_options,
        )

    async def async_step_plan_overview(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the current plans before choosing an action."""
        return await self.async_step_manage_plans()

    async def async_step_add_plan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a feed plan."""
        feeders = self._feeders()
        if user_input is not None:
            try:
                plan = validate_plan(user_input)
            except probatio.Invalid as err:
                return self._show_plan_form(
                    "add_plan", errors={"base": str(err)}, user_input=user_input
                )
            await self.config_entry.runtime_data.async_create_plan(
                str(user_input["device_id"]),
                name=plan["name"],
                hour=plan["hour"],
                minute=plan["minute"],
                servings=plan["servings"],
                enabled=plan["enabled"],
                days=plan["days"],
            )
            return await self.async_step_manage_plans()

        if not feeders:
            return self.async_abort(reason="no_feeders")
        return self._show_plan_form("add_plan")

    async def async_step_edit_plan_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select a plan to edit."""
        if user_input is not None:
            target = self._plan_options.get(str(user_input["plan_key"]))
            if target is None:
                return self.async_abort(reason="plan_not_found")
            self._selected_plan = target
            return await self.async_step_edit_plan()
        return self._show_plan_select("edit_plan_select")

    async def async_step_edit_plan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the selected feed plan."""
        selected = self._selected_plan
        if selected is None:
            return self.async_abort(reason="plan_not_found")
        device_id, plan_id = selected
        plan = self._find_plan(device_id, plan_id)
        if plan is None:
            return self.async_abort(reason="plan_not_found")

        if user_input is not None:
            try:
                validated = validate_plan(user_input)
            except probatio.Invalid as err:
                return self._show_plan_form(
                    "edit_plan",
                    plan=plan,
                    device_id=device_id,
                    errors={"base": str(err)},
                    user_input=user_input,
                )
            await self.config_entry.runtime_data.async_update_plan(
                device_id,
                plan_id,
                name=validated["name"],
                hour=validated["hour"],
                minute=validated["minute"],
                servings=validated["servings"],
                enabled=validated["enabled"],
                days=validated["days"],
            )
            self._selected_plan = None
            return await self.async_step_manage_plans()

        return self._show_plan_form(
            "edit_plan",
            plan=plan,
            device_id=device_id,
        )

    async def async_step_delete_plan_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select a plan to delete, then delete it after confirmation."""
        if user_input is not None:
            target = self._plan_options.get(str(user_input["plan_key"]))
            if target is None:
                return self.async_abort(reason="plan_not_found")
            device_id, plan_id = target
            await self.config_entry.runtime_data.async_delete_plan(plan_id)
            return await self.async_step_manage_plans()
        return self._show_plan_select("delete_plan_select")

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure polling."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = int(
            self.config_entry.options.get(
                CONF_SCAN_INTERVAL,
                DEFAULT_SCAN_INTERVAL.total_seconds(),
            )
        )
        return self.async_show_form(
            step_id="settings",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        CONF_SCAN_INTERVAL,
                        default=current_interval,
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=30,
                            max=3600,
                            step=30,
                            unit_of_measurement="秒",
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )

    def _show_plan_form(
        self,
        step_id: str,
        *,
        plan: Any = None,
        device_id: str | None = None,
        errors: dict[str, str] | None = None,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Render the native HA plan form."""
        values = user_input or {}
        feeders = self._feeders()
        selected_device = str(
            values.get("device_id") or device_id or feeders[0]["value"]
        )
        selected_days = values.get("days")
        if selected_days is None:
            selected_days = (
                [str(day + 1) for day in plan.days]
                if plan is not None
                else [str(day) for day in range(1, 8)]
            )
        name = values.get("name", plan.name if plan is not None else "")
        feed_time = values.get(
            "time",
            plan.time_label if plan is not None else "08:00",
        )
        servings = values.get(
            "servings",
            plan.servings if plan is not None else 1,
        )
        enabled = values.get(
            "enabled",
            plan.enabled if plan is not None else True,
        )
        return self.async_show_form(
            step_id=step_id,
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        "device_id", default=selected_device
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=feeders,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    probatio.Required("name", default=name): TextSelector(),
                    probatio.Required("time", default=feed_time): TimeSelector(),
                    probatio.Required(
                        "servings", default=servings
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0.5,
                            max=20,
                            step=0.5,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="份",
                        )
                    ),
                    probatio.Required(
                        "days", default=selected_days
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(
                                    value=str(index),
                                    label=label,
                                )
                                for index, label in enumerate(DAY_LABELS, start=1)
                            ],
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                    probatio.Required(
                        "enabled", default=enabled
                    ): selector.BooleanSelector(),
                }
            ),
            errors=errors or {},
            description_placeholders={
                "device": self._feeder_name(selected_device)
            },
        )

    def _show_plan_select(self, step_id: str) -> ConfigFlowResult:
        """Render the plan selection form."""
        self._plan_options = {}
        options: list[SelectOptionDict] = []
        for feeder_id, feeder in self._feeders_by_id().items():
            for plan in feeder.plans:
                key = str(len(options))
                options.append(
                    SelectOptionDict(
                        value=key,
                        label=(
                            f"{feeder.name} · {plan.time_label} · "
                            f"{plan.name}"
                        ),
                    )
                )
                self._plan_options[key] = (feeder_id, plan.id)
        if not options:
            return self.async_abort(reason="no_plans")
        return self.async_show_form(
            step_id=step_id,
            data_schema=probatio.Schema(
                {
                    probatio.Required("plan_key"): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    def _feeders(self) -> list[SelectOptionDict]:
        """Return feeder selector options."""
        return [
            SelectOptionDict(value=feeder_id, label=feeder.name)
            for feeder_id, feeder in self._feeders_by_id().items()
        ]

    def _feeder_name(self, device_id: str) -> str:
        feeder = self._feeders_by_id().get(device_id)
        return feeder.name if feeder is not None else device_id

    def _feeders_by_id(self):
        coordinator = self.config_entry.runtime_data
        return coordinator.data.feeders if coordinator.data else {}

    def _plans(self) -> list[Any]:
        return [
            plan
            for feeder in self._feeders_by_id().values()
            for plan in feeder.plans
        ]

    def _find_plan(self, device_id: str, plan_id: str):
        feeder = self._feeders_by_id().get(device_id)
        if feeder is None:
            return None
        return next((plan for plan in feeder.plans if plan.id == plan_id), None)
