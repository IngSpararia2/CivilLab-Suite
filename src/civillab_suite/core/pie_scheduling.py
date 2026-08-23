from __future__ import annotations

from datetime import date

from .pie import PieService
from .scheduling import ActivityStatus, NavigationTarget, ScheduledActivity


class PieScheduleProvider:
    module_id = "pie"
    provider_key = "core.pie"

    def __init__(self, service: PieService):
        self.service = service

    def activities_between(self, start: date, end: date) -> list[ScheduledActivity]:
        return [
            ScheduledActivity(
                module_id=item.module_ids[0] if item.module_ids else self.module_id,
                module_ids=item.module_ids,
                source_id=f"{item.plan_id}:{item.occurrence_start.isoformat()}:{item.day_number}",
                source_type="pie_occurrence",
                title=item.title,
                scheduled_date=item.scheduled_date,
                completed=item.is_completed,
                status=(
                    ActivityStatus.COMPLETED if item.is_completed else ActivityStatus.PENDING
                ),
                instructions=item.step_description,
                notes=item.notes,
                navigation=NavigationTarget(
                    module_id=None,
                    activity_type="shared_pie",
                    source_id=str(item.plan_id),
                ),
                supports_completion=True,
                supports_reopen=True,
                supports_reschedule=True,
                provider_key=self.provider_key,
                metadata=(
                    ("plan_id", str(item.plan_id)),
                    ("occurrence_start", item.occurrence_start.isoformat()),
                    ("day_number", str(item.day_number)),
                ),
            )
            for item in self.service.list_occurrences(start, end)
        ]

    def set_completed(self, activity: ScheduledActivity, completed: bool) -> None:
        values = dict(activity.metadata)
        self.service.set_occurrence_completed(
            int(values["plan_id"]),
            date.fromisoformat(values["occurrence_start"]),
            int(values["day_number"]),
            completed,
        )

    def reschedule(self, activity: ScheduledActivity, new_date: date) -> None:
        values = dict(activity.metadata)
        self.service.reschedule_occurrence(
            int(values["plan_id"]),
            date.fromisoformat(values["occurrence_start"]),
            int(values["day_number"]),
            new_date,
        )
