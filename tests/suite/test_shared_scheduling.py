from __future__ import annotations

from datetime import date

from civillab_suite.core.scheduling import (
    CompositeScheduleService,
    ScheduledActivity,
)


class _Provider:
    def __init__(self, module_id: str):
        self.module_id = module_id
        self.provider_key = f"fake.{module_id}"
        self.completed: list[tuple[str, bool]] = []

    def activities_between(self, start, end):
        return [
            ScheduledActivity(
                module_id=self.module_id,
                source_id="1",
                title=f"Actividad {self.module_id}",
                scheduled_date=start,
                completed=False,
                module_ids=(self.module_id,),
                provider_key=self.provider_key,
                supports_completion=True,
            )
        ]

    def set_completed(self, activity, completed):
        self.completed.append((activity.source_id, completed))


def test_calendar_filters_one_many_and_all_enabled_modules():
    concrete = _Provider("concretos")
    prefabricated = _Provider("prefabricados")
    service = CompositeScheduleService((concrete, prefabricated))
    selected = date(2026, 8, 5)

    assert [item.module_id for item in service.activities_between(
        selected, selected, ("concretos",)
    )] == ["concretos"]
    assert {item.module_id for item in service.activities_between(
        selected, selected, ("concretos", "prefabricados")
    )} == {"concretos", "prefabricados"}
    assert len(service.activities_between(selected, selected)) == 2

    activity = service.activities_between(selected, selected, ("concretos",))[0]
    service.set_completed(activity, True)
    assert concrete.completed == [("1", True)]
    assert prefabricated.completed == []
