from __future__ import annotations

from datetime import date

from civillab_suite.core.scheduling import (
    ActivityStatus,
    NavigationTarget,
    ScheduledActivity,
)


class ConcretosScheduleProvider:
    module_id = "concretos"
    provider_key = "concretos.specimens"

    def __init__(self, repository):
        self.repository = repository

    def activities_between(self, start: date, end: date) -> list[ScheduledActivity]:
        return [self._activity(item) for item in self.repository.list_tasks(start, end)]

    def set_completed(self, activity: ScheduledActivity, completed: bool) -> None:
        self.repository.set_task_completed(int(activity.source_id), completed)

    def _activity(self, item) -> ScheduledActivity:
        completed = bool(item.is_completed)
        return ScheduledActivity(
            module_id=self.module_id,
            module_ids=(self.module_id,),
            source_id=str(item.specimen_id),
            source_type="specimen",
            title=f"{item.specimen_code} · {item.design_name}",
            scheduled_date=item.planned_test_at.date(),
            completed=completed,
            status=ActivityStatus.COMPLETED if completed else ActivityStatus.PENDING,
            instructions=item.specimen_notes or (
                "Ejecutar el ensayo programado y registrar el resultado técnico en Producción."
            ),
            notes=item.specimen_notes,
            navigation=NavigationTarget(
                module_id=self.module_id,
                activity_type="production",
                source_id=str(item.production_id),
            ),
            supports_completion=True,
            supports_reopen=True,
            provider_key=self.provider_key,
            metadata=(("production_id", str(item.production_id)),),
        )
