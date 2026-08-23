from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from civillab_suite.core.catalog import CatalogAssay, CatalogService


class AssayCatalogPage(QWidget):
    """One read-only catalog implementation embeddable by every suite area."""

    def __init__(self, service: CatalogService, module_id: str | None = None, parent=None):
        super().__init__(parent)
        self.service = service
        self.module_id = module_id
        self._rows: list[CatalogAssay] = []

        title = QLabel("Catálogo de Ensayos")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Catálogo canónico suministrado por CivilLab. La edición se realiza "
            "exclusivamente mediante actualizaciones versionadas de la aplicación."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("Subtitle")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar ensayo, norma, método o material…")
        self.search.textChanged.connect(self._filter)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Buscar:"))
        filters.addWidget(self.search, 1)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            (
                "Ensayo canónico", "Métodos", "Normas", "Materiales", "Áreas",
                "Periodicidad", "Requisitos",
            )
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._show_details)
        self.details = QTextBrowser()
        self.details.setMaximumHeight(170)
        self.details.setPlaceholderText(
            "Selecciona un ensayo para consultar equipo, procedimiento y requisitos."
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(filters)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.details)
        self.refresh()

    def refresh(self) -> None:
        self._rows = self.service.list_assays(self.module_id)
        self._filter()

    def _filter(self, *_args) -> None:
        needle = self.search.text().strip().casefold()
        visible = [
            row for row in self._rows
            if not needle or needle in " ".join(
                (
                    row.name, *row.method_names, *row.standards, *row.materials,
                    *row.modules, row.normative_frequency, *row.requirements,
                )
            ).casefold()
        ]
        self._visible_rows = visible
        self.table.setRowCount(len(visible))
        for row_index, assay in enumerate(visible):
            values = (
                assay.name,
                "\n".join(assay.method_names) or "—",
                "\n".join(assay.standards) or "—",
                ", ".join(assay.materials) or "No aplica / sin clasificar",
                ", ".join(assay.modules),
                assay.normative_frequency or "—",
                f"{len(assay.requirements)} requisito(s)" if assay.requirements else "—",
            )
            for column, value in enumerate(values):
                self.table.setItem(row_index, column, QTableWidgetItem(value))
        self.table.resizeRowsToContents()
        self.details.clear()

    def _show_details(self) -> None:
        row = self.table.currentRow()
        if not 0 <= row < len(getattr(self, "_visible_rows", [])):
            self.details.clear()
            return
        assay = self._visible_rows[row]
        requirements = "\n".join(f"• {item}" for item in assay.requirements)
        parts = [
            f"ENSAYO\n{assay.name}",
            f"EQUIPO\n{assay.equipment or 'No especificado'}",
            f"PROCEDIMIENTO\n{assay.procedure or 'No especificado'}",
            f"REQUISITOS\n{requirements or 'Sin requisitos registrados'}",
        ]
        self.details.setPlainText("\n\n".join(parts))
