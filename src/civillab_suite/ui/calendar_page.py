from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Callable

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCalendarWidget,
    QCheckBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from civillab_suite.core.scheduling import (
    CompositeScheduleService,
    NavigationTarget,
    ScheduledActivity,
)


class SharedCalendarPage(QWidget):
    """Reusable operational calendar over module-specific schedule providers."""

    def __init__(
        self,
        service: CompositeScheduleService,
        available_modules: dict[str, str],
        context_module_id: str | None = None,
        navigate: Callable[[NavigationTarget], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.service = service
        self.available_modules = available_modules
        self.navigate = navigate
        self._activities: list[ScheduledActivity] = []

        title = QLabel("Calendario de laboratorio")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Actividades de las áreas habilitadas, proyectadas sin modificar sus datos técnicos."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("Subtitle")

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Áreas:"))
        self.module_checks: dict[str, QCheckBox] = {}
        for module_id, name in available_modules.items():
            check = QCheckBox(name)
            check.setChecked(module_id == context_module_id or context_module_id is None)
            check.toggled.connect(self.refresh)
            self.module_checks[module_id] = check
            filters.addWidget(check)
        filters.addStretch()

        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.selectionChanged.connect(self._refresh_day)
        self.calendar.currentPageChanged.connect(lambda *_: self.refresh())

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(("Estado", "Área", "Actividad", "Origen", "Fecha"))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.doubleClicked.connect(self._open_selected)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.instructions = QTextBrowser()
        self.instructions.setMaximumHeight(115)
        self.instructions.setPlaceholderText("Selecciona una actividad para consultar instrucciones.")
        self.table.itemSelectionChanged.connect(self._show_instructions)

        complete = QPushButton("Marcar completada")
        complete.clicked.connect(lambda: self._set_selected(True))
        reopen = QPushButton("Reabrir")
        reopen.clicked.connect(lambda: self._set_selected(False))
        reschedule = QPushButton("Reprogramar")
        reschedule.clicked.connect(self._reschedule_selected)
        open_button = QPushButton("Abrir actividad")
        open_button.clicked.connect(self._open_selected)
        actions = QHBoxLayout()
        for button in (complete, reopen, reschedule, open_button):
            actions.addWidget(button)
        actions.addStretch()

        content = QHBoxLayout()
        content.addWidget(self.calendar, 2)
        right = QVBoxLayout()
        right.addWidget(self.table, 1)
        right.addWidget(self.instructions)
        right.addLayout(actions)
        content.addLayout(right, 5)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(filters)
        layout.addLayout(content, 1)
        self.refresh()

    def selected_modules(self) -> tuple[str, ...]:
        return tuple(
            module_id for module_id, check in self.module_checks.items() if check.isChecked()
        )

    def refresh(self, *_args) -> None:
        year = self.calendar.yearShown()
        month = self.calendar.monthShown()
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        try:
            self._month_activities = self.service.activities_between(
                start, end, self.selected_modules()
            )
        except Exception as error:
            self._month_activities = []
            QMessageBox.warning(self, "No se pudo actualizar el calendario", str(error))
        self._refresh_day()

    def _refresh_day(self) -> None:
        qdate = self.calendar.selectedDate()
        selected = date(qdate.year(), qdate.month(), qdate.day())
        self._activities = [
            item for item in getattr(self, "_month_activities", [])
            if item.scheduled_date == selected
        ]
        self.table.setRowCount(len(self._activities))
        for row, activity in enumerate(self._activities):
            values = (
                "Completada" if activity.completed else "Vencida" if activity.is_overdue() else "Pendiente",
                ", ".join(activity.areas),
                activity.title,
                activity.source_type or activity.provider_key,
                activity.scheduled_date.strftime("%d/%m/%Y"),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(row, column, item)
        self.table.resizeRowsToContents()
        self.instructions.clear()

    def _selected(self) -> list[ScheduledActivity]:
        rows = sorted({item.row() for item in self.table.selectedItems()})
        return [self._activities[row] for row in rows if 0 <= row < len(self._activities)]

    def _show_instructions(self) -> None:
        selected = self._selected()
        if not selected:
            self.instructions.clear()
            return
        activity = selected[0]
        self.instructions.setPlainText(activity.instructions or "Sin instrucciones registradas.")

    def _set_selected(self, completed: bool) -> None:
        selected = self._selected()
        if not selected:
            return
        try:
            for activity in selected:
                if completed and not activity.supports_completion:
                    continue
                if not completed and not activity.supports_reopen:
                    continue
                self.service.set_completed(activity, completed)
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo actualizar", str(error))
        self.refresh()

    def _reschedule_selected(self) -> None:
        selected = self._selected()
        if len(selected) != 1:
            QMessageBox.information(self, "Reprogramar", "Selecciona una sola actividad.")
            return
        activity = selected[0]
        if not activity.supports_reschedule:
            QMessageBox.information(
                self, "Reprogramar", "El origen de esta actividad no admite reprogramación."
            )
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Reprogramar actividad")
        form = QFormLayout(dialog)
        reference_text = dict(activity.metadata).get("reschedule_reference", "")
        reference_date = (
            date.fromisoformat(reference_text) if reference_text else activity.scheduled_date
        )
        field = QDateEdit(QDate(
            reference_date.year,
            reference_date.month,
            reference_date.day,
        ))
        field.setCalendarPopup(True)
        form.addRow("Nueva fecha:", field)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        value = field.date()
        try:
            self.service.reschedule(
                activity, date(value.year(), value.month(), value.day())
            )
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo reprogramar", str(error))
        self.refresh()

    def _open_selected(self, *_args) -> None:
        selected = self._selected()
        if not selected or selected[0].navigation is None:
            return
        if self.navigate is None:
            QMessageBox.information(
                self, "Destino no disponible", "Esta instalación no configuró navegación directa."
            )
            return
        self.navigate(selected[0].navigation)
