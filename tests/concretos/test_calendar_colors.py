from dataclasses import dataclass
from datetime import date, timedelta

from concrete_mix_designer.domain.pie_models import PieFrequency, PieOccurrence
from concrete_mix_designer.ui.pages.calendar_page import LaboratoryCalendarPage


@dataclass
class _Task:
    pending: bool = False
    completed: bool = False
    overdue: bool = False

    @property
    def is_pending(self) -> bool:
        return self.pending

    @property
    def is_completed(self) -> bool:
        return self.completed

    def is_overdue(self, _reference_date: date) -> bool:
        return self.overdue


def _pie(reference_date: date, completed: bool = False) -> PieOccurrence:
    return PieOccurrence(
        plan_id=1,
        plan_name="Control PIE",
        frequency=PieFrequency.DAILY,
        interval=1,
        occurrence_start=reference_date,
        scheduled_date=reference_date,
        day_number=1,
        duration_days=1,
        step_description="Revisar",
        checklist_completed=completed,
    )


def test_calendar_color_categories_follow_the_legend():
    reference = date(2026, 8, 1)

    assert LaboratoryCalendarPage._calendar_color_key([_Task(pending=True)], reference) == "pending"
    assert LaboratoryCalendarPage._calendar_color_key([_Task(completed=True)], reference) == "completed"
    assert LaboratoryCalendarPage._calendar_color_key([_pie(reference)], reference) == "pie"
    assert LaboratoryCalendarPage._calendar_color_key([_pie(reference, completed=True)], reference) == "pie"
    assert (
        LaboratoryCalendarPage._calendar_color_key(
            [_Task(pending=True), _Task(completed=True)], reference
        )
        == "mixed"
    )


def test_calendar_overdue_color_has_priority_over_other_states():
    reference = date(2026, 8, 1)
    overdue_task = _Task(pending=True, overdue=True)

    assert (
        LaboratoryCalendarPage._calendar_color_key(
            [overdue_task, _pie(reference - timedelta(days=1))], reference
        )
        == "overdue"
    )
