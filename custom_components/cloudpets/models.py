"""Data models used by the CloudPets integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FeedPlan:
    """A feed schedule returned by CloudPets."""

    id: str
    name: str
    hour: int
    minute: int
    servings: float
    enabled: bool
    days: list[int]
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def time_label(self) -> str:
        """Return the plan time as HH:MM."""
        return f"{self.hour:02d}:{self.minute:02d}"


@dataclass(slots=True)
class DesiccantState:
    """Desiccant reminder state."""

    supported: bool = False
    remain_days: int | None = None
    cycle_days: int | None = None
    remind_time: str | None = None
    overdue: bool = False


@dataclass(slots=True)
class FeederData:
    """Current feeder state."""

    id: str
    cloud_device_id: int
    name: str
    model: str
    online: bool
    battery: int | None = None
    food_level: int | None = None
    bowl_status: str | None = None
    servings_today: float | None = None
    child_lock_supported: bool = False
    child_locked: bool = False
    desiccant: DesiccantState = field(default_factory=DesiccantState)
    plans: list[FeedPlan] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CloudPetsData:
    """All data for one CloudPets account."""

    account: str
    user_id: str | None
    feeders: dict[str, FeederData]
