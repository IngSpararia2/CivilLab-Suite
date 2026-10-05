from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCalendarWidget,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from concrete_mix_designer.data.calendar_repository import (
    CalendarRepository,
    CalendarTaskRecord,
)
from concrete_mix_designer.domain.laboratory_models import (
    SPECIMEN_TYPE_LABELS,
    SpecimenStatus,
)
from concrete_mix_designer.domain.pie_models import PieOccurrence
from concrete_mix_designer.services.app_state import AppState
from concrete_mix_designer.ui.dialogs.pie_dialog import PiePlanDialog

MONTH_NAMES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
ITEM_KIND_ROLE = int(Qt.ItemDataRole.UserRole)
SPECIMEN_ID_ROLE = ITEM_KIND_ROLE + 1
PRODUCTION_ID_ROLE = ITEM_KIND_ROLE + 2
PIE_PLAN_ID_ROLE = ITEM_KIND_ROLE + 3
PIE_START_ROLE = ITEM_KIND_ROLE + 4
PIE_DAY_ROLE = ITEM_KIND_ROLE + 5

CALENDAR_COLORS = {
    "pending": "#2563eb",
    "overdue": "#c2410c",
    "completed": "#15803d",
    "pie": "#7c3aed",
    "mixed": "#d97706",
}


class ColoredCalendarWidget(QCalendarWidget):
    """Calendar that keeps event colors visible despite table-wide styles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._day_colors: dict[QDate, QColor] = {}

    def set_day_colors(self, day_colors: dict[QDate, QColor]) -> None:
        self._day_colors = day_colors
        self.updateCells()

    def paintCell(self, painter: QPainter, rect, day: QDate) -> None:  # noqa: N802
        super().paintCell(painter, rect, day)
        background = self._day_colors.get(day)
        if background is None:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colored_rect = rect.adjusted(3, 3, -3, -3)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(colored_rect, 5, 5)

        font = QFont(painter.font())
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(colored_rect, Qt.AlignmentFlag.AlignCenter, str(day.day()))

        if day == self.selectedDate():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#102f4f"), 2))
            painter.drawRoundedRect(colored_rect, 5, 5)
        painter.restore()


WEEKDAY_NAMES = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)


class LaboratoryCalendarPage(QWidget):
    open_production_requested = Signal(int)

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.repository = CalendarRepository(state.laboratory_repository.database_path)
        self._loading = False
        self._day_tasks: list[CalendarTaskRecord] = []
        self._day_pie_occurrences: list[PieOccurrence] = []
        title = QLabel("Calendario de laboratorio")
        title.setObjectName("Title")
        self.pie_button = QPushButton("Añadir PIE")
        self.pie_button.clicked.connect(self._open_pie_dialog)
        title_row = QHBoxLayout()
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(self.pie_button)
        subtitle = QLabel(
            "Consulta muestras y actividades de los planes PIE por fecha. El checklist es "
            "operativo: marcar una tarea como realizada no crea un resultado de resistencia "
            "ni altera las estadísticas."
        )
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)

        metrics = QHBoxLayout()
        self.pending_today_value = self._metric_card("Actividades pendientes hoy")
        self.completed_today_value = self._metric_card("Actividades concluidas hoy")
        self.overdue_value = self._metric_card("Muestras vencidas")
        self.upcoming_value = self._metric_card("Actividades próximos 7 días")
        for card, _value in (
            self.pending_today_value,
            self.completed_today_value,
            self.overdue_value,
            self.upcoming_value,
        ):
            metrics.addWidget(card)

        calendar_card = QFrame()
        calendar_card.setObjectName("Card")
        calendar_layout = QVBoxLayout(calendar_card)
        calendar_title = QLabel("Programación mensual")
        calendar_title.setObjectName("SectionTitle")
        self.calendar = ColoredCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.calendar.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        self.calendar.setSelectedDate(QDate.currentDate())
        self.calendar.clicked.connect(self._date_selected)
        self.calendar.currentPageChanged.connect(self._month_changed)
        legend = QLabel(
            "<b>Leyenda:</b> "
            f"<span style='background:{CALENDAR_COLORS['pending']};color:white;padding:2px 6px;'>Pendiente</span> &nbsp;"
            f"<span style='background:{CALENDAR_COLORS['overdue']};color:white;padding:2px 6px;'>Vencido</span> &nbsp;"
            f"<span style='background:{CALENDAR_COLORS['completed']};color:white;padding:2px 6px;'>Concluido</span> &nbsp;"
            f"<span style='background:{CALENDAR_COLORS['pie']};color:white;padding:2px 6px;'>PIE</span> &nbsp;"
            f"<span style='background:{CALENDAR_COLORS['mixed']};color:white;padding:2px 6px;'>Mixto</span>"
        )
        legend.setWordWrap(True)
        calendar_layout.addWidget(calendar_title)
        calendar_layout.addWidget(self.calendar, 1)
        calendar_layout.addWidget(legend)

        detail_card = QFrame()
        detail_card.setObjectName("Card")
        detail_layout = QVBoxLayout(detail_card)
        self.date_title = QLabel()
        self.date_title.setObjectName("SectionTitle")
        self.day_summary = QLabel()
        self.day_summary.setObjectName("Subtitle")

        self.status_filter = QComboBox()
        self.status_filter.addItem("Todos los estados", "all")
        self.status_filter.addItem("Solo pendientes", "pending")
        self.status_filter.addItem("Solo concluidos", "completed")
        self.status_filter.currentIndexChanged.connect(self._populate_table)
        refresh_button = QPushButton("Actualizar")
        refresh_button.setObjectName("Secondary")
        refresh_button.clicked.connect(self.refresh)
        open_button = QPushButton("Abrir producción")
        open_button.setObjectName("Secondary")
        open_button.clicked.connect(self._open_selected_production)
        complete_button = QPushButton("Marcar seleccionados como realizados")
        complete_button.clicked.connect(lambda: self._set_selected_rows(True))
        reopen_button = QPushButton("Reabrir seleccionados")
        reopen_button.setObjectName("Secondary")
        reopen_button.clicked.connect(lambda: self._set_selected_rows(False))

        actions = QHBoxLayout()
        actions.addWidget(QLabel("Mostrar:"))
        actions.addWidget(self.status_filter)
        actions.addStretch()
        actions.addWidget(refresh_button)
        actions.addWidget(open_button)
        actions.addWidget(complete_button)
        actions.addWidget(reopen_button)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Hecho",
                "Hora",
                "Código",
                "Tipo",
                "Etapa",
                "Origen",
                "Actividad",
                "Estado",
                "Notas / paso",
            ]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self._item_changed)
        self.table.doubleClicked.connect(self._open_selected_production)
        header = self.table.horizontalHeader()
        for column in (0, 1, 2, 3, 4, 5, 7):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)

        detail_layout.addWidget(self.date_title)
        detail_layout.addWidget(self.day_summary)
        detail_layout.addLayout(actions)
        detail_layout.addWidget(self.table, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        calendar_card.setMinimumWidth(390)
        detail_card.setMinimumWidth(720)
        splitter.addWidget(calendar_card)
        splitter.addWidget(detail_card)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([440, 1050])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.addLayout(title_row)
        layout.addWidget(subtitle)
        layout.addLayout(metrics)
        layout.addWidget(splitter, 1)

        state.productions_changed.connect(self.refresh)
        self.refresh()

    @staticmethod
    def _metric_card(caption: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        label = QLabel(caption)
        label.setObjectName("Subtitle")
        value = QLabel("0")
        value.setObjectName("Metric")
        layout.addWidget(label)
        layout.addWidget(value)
        return card, value

    @staticmethod
    def _to_date(value: QDate) -> date:
        return date(value.year(), value.month(), value.day())

    @staticmethod
    def _to_qdate(value: date) -> QDate:
        return QDate(value.year, value.month, value.day)

    @staticmethod
    def _date_label(value: date) -> str:
        return (
            f"{WEEKDAY_NAMES[value.weekday()].capitalize()}, {value.day} de "
            f"{MONTH_NAMES[value.month - 1]} de {value.year}"
        )

    def refresh(self) -> None:
        self._refresh_summary()
        self._refresh_month()
        self._refresh_day()

    def _refresh_summary(self) -> None:
        today = datetime.now().astimezone().date()
        summary = self.repository.operational_summary(today)
        pie_today = self.repository.list_pie_occurrences(today, today)
        pie_upcoming = self.repository.list_pie_occurrences(
            today + timedelta(days=1), today + timedelta(days=7)
        )
        self.pending_today_value[1].setText(
            str(summary.pending_today + sum(item.is_pending for item in pie_today))
        )
        self.completed_today_value[1].setText(
            str(summary.completed_today + sum(item.is_completed for item in pie_today))
        )
        self.overdue_value[1].setText(str(summary.overdue))
        self.upcoming_value[1].setText(
            str(
                summary.upcoming_seven_days
                + sum(item.is_pending for item in pie_upcoming)
            )
        )

    def _month_changed(self, _year: int, _month: int) -> None:
        self._refresh_month()

    def _date_selected(self, _selected: QDate) -> None:
        self._refresh_day()

    def _refresh_month(self) -> None:
        year = self.calendar.yearShown()
        month = self.calendar.monthShown()
        tasks = self.repository.list_month_tasks(year, month)
        pie_occurrences = self.repository.list_month_pie_occurrences(year, month)
        grouped: dict[date, list[CalendarTaskRecord | PieOccurrence]] = defaultdict(list)
        for task in tasks:
            grouped[task.planned_test_at.date()].append(task)
        for occurrence in pie_occurrences:
            grouped[occurrence.scheduled_date].append(occurrence)

        today = datetime.now().astimezone().date()
        day_colors: dict[QDate, QColor] = {}
        for task_date, day_tasks in grouped.items():
            color_key = self._calendar_color_key(day_tasks, today)
            day_colors[self._to_qdate(task_date)] = QColor(CALENDAR_COLORS[color_key])
        self.calendar.set_day_colors(day_colors)

    @staticmethod
    def _calendar_color_key(
        day_tasks: list[CalendarTaskRecord | PieOccurrence], reference_date: date
    ) -> str:
        """Return one legend category for a date, in display-priority order."""
        pending = [task for task in day_tasks if task.is_pending]
        completed = [task for task in day_tasks if task.is_completed]
        if any(task.is_overdue(reference_date) for task in day_tasks):
            return "overdue"
        if pending and completed:
            return "mixed"
        if all(isinstance(task, PieOccurrence) for task in day_tasks):
            return "pie"
        if pending:
            return "pending"
        return "completed"

    def _refresh_day(self) -> None:
        selected = self._to_date(self.calendar.selectedDate())
        self._day_tasks = self.repository.list_tasks_for_date(selected)
        self._day_pie_occurrences = self.repository.list_pie_occurrences_for_date(selected)
        all_tasks: list[CalendarTaskRecord | PieOccurrence] = [
            *self._day_tasks,
            *self._day_pie_occurrences,
        ]
        self.date_title.setText(self._date_label(selected))
        pending = sum(task.is_pending for task in all_tasks)
        completed = sum(task.is_completed for task in all_tasks)
        cancelled = sum(
            task.specimen_status == SpecimenStatus.CANCELLED for task in self._day_tasks
        )
        overdue = sum(task.is_overdue() for task in all_tasks)
        self.day_summary.setText(
            f"{len(all_tasks)} actividades · {pending} pendientes · "
            f"{completed} concluidas · {len(self._day_pie_occurrences)} PIE"
            + (f" · {cancelled} canceladas" if cancelled else "")
            + (f" · {overdue} vencidas" if overdue else "")
        )
        self._populate_table()

    def _visible_tasks(self) -> list[CalendarTaskRecord | PieOccurrence]:
        tasks: list[CalendarTaskRecord | PieOccurrence] = [
            *self._day_tasks,
            *self._day_pie_occurrences,
        ]
        mode = self.status_filter.currentData()
        if mode == "pending":
            return [task for task in tasks if task.is_pending]
        if mode == "completed":
            return [task for task in tasks if task.is_completed]
        return tasks

    def _populate_table(self, *_args) -> None:
        tasks = self._visible_tasks()
        self._loading = True
        try:
            self.table.setRowCount(len(tasks))
            for row, task in enumerate(tasks):
                check_item = QTableWidgetItem()
                check_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                check_item.setCheckState(
                    Qt.CheckState.Checked if task.is_completed else Qt.CheckState.Unchecked
                )
                flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                if isinstance(task, PieOccurrence):
                    flags |= Qt.ItemFlag.ItemIsUserCheckable
                    check_item.setData(ITEM_KIND_ROLE, "pie")
                    check_item.setData(PIE_PLAN_ID_ROLE, task.plan_id)
                    check_item.setData(PIE_START_ROLE, task.occurrence_start.isoformat())
                    check_item.setData(PIE_DAY_ROLE, task.day_number)
                    if task.checklist_completed:
                        status = "PIE realizado"
                        background = QColor("#ecfdf5")
                    elif task.is_overdue():
                        status = "PIE vencido"
                        background = QColor("#fee2e2")
                    else:
                        status = "PIE pendiente"
                        background = QColor("#f3e8ff")
                    values = [
                        "Todo el día",
                        f"PIE-{task.plan_id}",
                        "Ensayo PIE",
                        f"Día {task.day_number}/{task.duration_days}",
                        self.repository.pie_frequency_label(task.frequency, task.interval),
                        task.plan_name,
                        status,
                        task.step_description,
                    ]
                else:
                    check_item.setData(ITEM_KIND_ROLE, "specimen")
                    check_item.setData(SPECIMEN_ID_ROLE, task.specimen_id)
                    check_item.setData(PRODUCTION_ID_ROLE, task.production_id)
                    if task.specimen_status == SpecimenStatus.PLANNED:
                        flags |= Qt.ItemFlag.ItemIsUserCheckable
                    if task.specimen_status == SpecimenStatus.TESTED:
                        status = "Resultado registrado"
                        background = QColor("#dcfce7")
                    elif task.specimen_status == SpecimenStatus.CANCELLED:
                        status = "Muestra cancelada"
                        background = QColor("#e5e7eb")
                    elif task.checklist_completed:
                        status = "Realizado · resultado pendiente"
                        background = QColor("#ecfdf5")
                    elif task.is_overdue():
                        status = "Vencido"
                        background = QColor("#fee2e2")
                    else:
                        status = "Pendiente"
                        background = QColor("#eff6ff")
                    values = [
                        task.planned_test_at.strftime("%H:%M"),
                        task.specimen_code,
                        SPECIMEN_TYPE_LABELS[task.specimen_type],
                        f"{task.target_age_days:g} d",
                        task.batch_code,
                        task.design_name,
                        status,
                        task.specimen_notes or "—",
                    ]
                check_item.setFlags(flags)
                self.table.setItem(row, 0, check_item)
                for column, value in enumerate(values, start=1):
                    item = QTableWidgetItem(value)
                    for role in (
                        ITEM_KIND_ROLE,
                        SPECIMEN_ID_ROLE,
                        PRODUCTION_ID_ROLE,
                        PIE_PLAN_ID_ROLE,
                        PIE_START_ROLE,
                        PIE_DAY_ROLE,
                    ):
                        item.setData(role, check_item.data(role))
                    item.setBackground(QBrush(background))
                    self.table.setItem(row, column, item)
                check_item.setBackground(QBrush(background))
            self.table.resizeRowsToContents()
        finally:
            self._loading = False

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or item.column() != 0:
            return
        completed = item.checkState() == Qt.CheckState.Checked
        try:
            if item.data(ITEM_KIND_ROLE) == "pie":
                self.repository.set_pie_occurrence_completed(
                    int(item.data(PIE_PLAN_ID_ROLE)),
                    date.fromisoformat(str(item.data(PIE_START_ROLE))),
                    int(item.data(PIE_DAY_ROLE)),
                    completed,
                )
            else:
                specimen_id = item.data(SPECIMEN_ID_ROLE)
                if specimen_id is None:
                    return
                self.repository.set_task_completed(int(specimen_id), completed)
            action = "marcada como realizada" if completed else "reabierta"
            self.state.message.emit(f"Actividad de laboratorio {action}.")
            self.refresh()
        except Exception as error:
            QMessageBox.critical(self, "No se pudo actualizar el checklist", str(error))
            self.refresh()

    def _selected_task_items(self) -> list[QTableWidgetItem]:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        return [item for row in rows if (item := self.table.item(row, 0)) is not None]

    def _set_selected_rows(self, completed: bool) -> None:
        items = self._selected_task_items()
        if not items:
            QMessageBox.information(
                self, "Selecciona actividades", "Selecciona una o más filas del itinerario."
            )
            return
        try:
            for item in items:
                if item.data(ITEM_KIND_ROLE) == "pie":
                    self.repository.set_pie_occurrence_completed(
                        int(item.data(PIE_PLAN_ID_ROLE)),
                        date.fromisoformat(str(item.data(PIE_START_ROLE))),
                        int(item.data(PIE_DAY_ROLE)),
                        completed,
                    )
                else:
                    specimen_id = item.data(SPECIMEN_ID_ROLE)
                    if specimen_id is not None:
                        self.repository.set_task_completed(int(specimen_id), completed)
            self.state.message.emit(
                f"Se actualizaron {len(items)} actividades del calendario."
            )
            self.refresh()
        except Exception as error:
            QMessageBox.critical(self, "No se pudo actualizar el checklist", str(error))

    def _selected_production_id(self) -> int | None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        value = item.data(PRODUCTION_ID_ROLE) if item else None
        return int(value) if value is not None else None

    def _open_selected_production(self, *_args) -> None:
        production_id = self._selected_production_id()
        if production_id is None:
            QMessageBox.information(
                self, "Selecciona una actividad", "Selecciona una muestra del itinerario."
            )
            return
        self.open_production_requested.emit(production_id)

    def _open_pie_dialog(self) -> None:
        dialog = PiePlanDialog(self.repository, self)
        dialog.plans_changed.connect(self.refresh)
        dialog.exec()
        self.refresh()
