from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Iterable, Protocol


class ActivityStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class NavigationTarget:
    module_id: str | None
    activity_type: str
    source_id: str
    action: str = "open"


@dataclass(frozen=True, slots=True)
class ScheduledActivity:
    module_id: str
    source_id: str
    title: str
    scheduled_date: date
    completed: bool
    source_type: str = ""
    status: ActivityStatus = ActivityStatus.PENDING
    instructions: str = ""
    notes: str = ""
    module_ids: tuple[str, ...] = ()
    navigation: NavigationTarget | None = None
    supports_completion: bool = False
    supports_reopen: bool = False
    supports_reschedule: bool = False
    provider_key: str = ""
    metadata: tuple[tuple[str, str], ...] = ()

    @property
    def areas(self) -> tuple[str, ...]:
        return self.module_ids or (self.module_id,)

    @property
    def is_pending(self) -> bool:
        return not self.completed and self.status != ActivityStatus.CANCELLED

    def is_overdue(self, reference_date: date | None = None) -> bool:
        return self.is_pending and self.scheduled_date < (reference_date or date.today())


class ScheduleProvider(Protocol):
    """Projection boundary: specialized tables do not need a common schema."""

    module_id: str
    provider_key: str

    def activities_between(self, start: date, end: date) -> list[ScheduledActivity]: ...


class CompositeScheduleService:
    def __init__(self, providers: Iterable[ScheduleProvider]):
        self.providers = {provider.provider_key: provider for provider in providers}

    def activities_between(
        self,
        start: date,
        end: date,
        module_ids: Iterable[str] | None = None,
    ) -> list[ScheduledActivity]:
        selected = set(module_ids or ())
        activities = [
            activity
            for provider in self.providers.values()
            for activity in provider.activities_between(start, end)
            if not selected or selected.intersection(activity.areas)
        ]
        return sorted(
            activities,
            key=lambda item: (
                item.scheduled_date, item.completed, item.title.casefold(), item.source_id
            ),
        )

    def set_completed(self, activity: ScheduledActivity, completed: bool) -> None:
        provider = self._provider(activity)
        if not hasattr(provider, "set_completed"):
            raise ValueError("El origen de esta actividad no admite cambios de checklist.")
        provider.set_completed(activity, completed)

    def reschedule(self, activity: ScheduledActivity, new_date: date) -> None:
        provider = self._provider(activity)
        if not hasattr(provider, "reschedule"):
            raise ValueError("El origen de esta actividad no admite reprogramación.")
        provider.reschedule(activity, new_date)

    def _provider(self, activity: ScheduledActivity) -> ScheduleProvider:
        try:
            return self.providers[activity.provider_key]
        except KeyError as error:
            raise ValueError("El proveedor de la actividad ya no está disponible.") from error
