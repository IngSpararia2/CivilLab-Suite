from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from civillab_suite.core.scheduling import (
    ActivityStatus,
    NavigationTarget,
    ScheduledActivity,
)


class PrefabricadosScheduleProvider:
    module_id = "prefabricados"
    provider_key = "prefabricados.workflow"

    def activities_between(self, start: date, end: date) -> list[ScheduledActivity]:
        from precon_lab.database import session_scope
        from precon_lab.models import ProductionBatch, SampleSet, WorkflowTask

        with session_scope() as session:
            rows = list(
                session.scalars(
                    select(WorkflowTask)
                    .options(
                        joinedload(WorkflowTask.sample_set)
                        .joinedload(SampleSet.batch)
                        .joinedload(ProductionBatch.product)
                    )
                    .where(WorkflowTask.scheduled_date.between(start, end))
                    .order_by(WorkflowTask.scheduled_date, WorkflowTask.sequence, WorkflowTask.id)
                ).unique()
            )
            return [self._activity(item) for item in rows]

    def set_completed(self, activity: ScheduledActivity, completed: bool) -> None:
        from precon_lab.database import session_scope
        from precon_lab.services import complete_task, reopen_task

        with session_scope() as session:
            if completed:
                complete_task(session, int(activity.source_id))
            else:
                reopen_task(session, int(activity.source_id))

    def reschedule(self, activity: ScheduledActivity, new_date: date) -> None:
        from precon_lab.database import session_scope
        from precon_lab.services import reprogram_sample_set

        sample_set_id = int(dict(activity.metadata)["sample_set_id"])
        with session_scope() as session:
            reprogram_sample_set(session, sample_set_id, new_date)

    def _activity(self, item) -> ScheduledActivity:
        completed = item.status == "DONE"
        sample_set = item.sample_set
        product = sample_set.batch.product
        return ScheduledActivity(
            module_id=self.module_id,
            module_ids=(self.module_id,),
            source_id=str(item.id),
            source_type="workflow_task",
            title=f"{item.title} · {product.display_name}",
            scheduled_date=item.scheduled_date,
            completed=completed,
            status=ActivityStatus.COMPLETED if completed else ActivityStatus.PENDING,
            instructions=item.instructions,
            notes=item.notes,
            navigation=NavigationTarget(
                module_id=self.module_id,
                activity_type="sample_set",
                source_id=str(sample_set.id),
            ),
            supports_completion=True,
            supports_reopen=True,
            supports_reschedule=sample_set.planned_test_date is not None,
            provider_key=self.provider_key,
            metadata=(
                ("sample_set_id", str(sample_set.id)),
                (
                    "reschedule_reference",
                    sample_set.planned_test_date.isoformat()
                    if sample_set.planned_test_date else "",
                ),
            ),
        )
