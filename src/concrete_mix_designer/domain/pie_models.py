from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class PieFrequency(StrEnum):
    """Supported recurrence rules for a PIE laboratory inspection."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM_DAYS = "custom_days"
    CUSTOM_MONTHS = "custom_months"


@dataclass(slots=True)
class PieInspectionPlan:
    name: str
    frequency: PieFrequency
    interval: int
    start_date: date
    duration_days: int
    steps: list[str] = field(default_factory=list)
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PieOccurrence:
    """One visible day of a recurring PIE inspection.

    Occurrences are projections of a plan and are intentionally not persisted.
    Only a checked occurrence produces a sparse row in the checklist table.
    """

    plan_id: int
    plan_name: str
    frequency: PieFrequency
    interval: int
    occurrence_start: date
    scheduled_date: date
    day_number: int
    duration_days: int
    step_description: str
    checklist_completed: bool = False
    checklist_completed_at: datetime | None = None

    @property
    def is_completed(self) -> bool:
        return self.checklist_completed

    @property
    def is_pending(self) -> bool:
        return not self.checklist_completed

    def is_overdue(self, reference_date: date | None = None) -> bool:
        return self.is_pending and self.scheduled_date < (reference_date or date.today())
