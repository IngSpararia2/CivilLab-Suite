from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ScheduledActivity:
    module_id: str
    source_id: str
    title: str
    scheduled_date: date
    completed: bool


class ScheduleProvider(Protocol):
    """Boundary for a future shared calendar without changing module semantics."""

    module_id: str

    def activities_between(self, start: date, end: date) -> list[ScheduledActivity]: ...


# Concretos projects bounded recurring PIE occurrences, while Prefabricados persists
# material/test inspection rules and operational workflow tasks.  They deliberately
# remain separate behind this boundary until their recurrence semantics are aligned.
