from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from concrete_mix_designer.domain.metadata_models import (
    APPLICATION_LABELS,
    CONSISTENCY_LABELS,
    DesignSpecification,
    StrengthBasis,
)
from concrete_mix_designer.domain.models import (
    CATEGORY_LABELS,
    ConstraintMode,
    MaterialCategory,
)
from concrete_mix_designer.services.report_preferences import ReportPreferences

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_X = 14 * mm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN_X
FOOTER_TOP = 17 * mm


CONSTRAINT_LABELS = {
    ConstraintMode.MASS_RATIO: "Relación A/B",
    ConstraintMode.PERCENT_OF_B: "A como % de B",
    ConstraintMode.PERCENT_OF_PAIR: "A como % de A+B",
    ConstraintMode.PERCENT_OF_CEMENTITIOUS: "A como % cementante",
    ConstraintMode.ML_PER_100KG_B: "mL/100 kg de B",
    ConstraintMode.ML_PER_100KG_CEMENTITIOUS: "mL/100 kg cementante",
}

CONSTRAINT_SUFFIXES = {
    ConstraintMode.MASS_RATIO: "",
    ConstraintMode.PERCENT_OF_B: " %",
    ConstraintMode.PERCENT_OF_PAIR: " %",
    ConstraintMode.PERCENT_OF_CEMENTITIOUS: " %",
    ConstraintMode.ML_PER_100KG_B: " mL/100 kg",
    ConstraintMode.ML_PER_100KG_CEMENTITIOUS: " mL/100 kg",
}


def ensure_unique_path(path: Path) -> Path:
    """Return a non-existing path by appending a three-digit counter."""

    path = Path(path)
    if path.suffix.lower() != ".pdf":
        path = path.with_suffix(".pdf")
    if not path.exists():
        return path

    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{counter:03d}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def export_mix_report(
    path: Path,
    design,
    correction_rows: list[dict],
    batch_volume_m3: float,
    *,
    preferences: ReportPreferences | None = None,
    statistics: list | None = None,
    design_name: str = "Diseño activo",
    group_name: str = "",
    description: str = "",
    specification: DesignSpecification | None = None,
) -> Path:
    """Generate a fixed two-page professional report.

    Page 1 is an internal laboratory sheet and includes physical properties,
    exact quantities, moisture correction and strength records. Page 2 is a
    client-facing technical sheet and deliberately omits internal quantities.
    """

    preferences = preferences or ReportPreferences()
    specification = specification or DesignSpecification.from_mix_design(design)
    output_path = ensure_unique_path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pdf = canvas.Canvas(str(output_path), pagesize=A4)
    pdf.setTitle("Diseño de mezcla de concreto")
    pdf.setAuthor("Ing. Samuel Parariá")
    pdf.setSubject("Diseño de mezcla y ficha técnica para cliente")

    _draw_laboratory_page(
        pdf,
        design,
        correction_rows,
        batch_volume_m3,
        preferences,
        statistics or [],
        design_name,
        group_name,
        description,
        specification,
    )
    pdf.showPage()
    _draw_client_page(
        pdf,
        design,
        preferences,
        design_name,
        group_name,
        description,
        specification,
    )
    pdf.save()
    return output_path


def _draw_laboratory_page(
    pdf: canvas.Canvas,
    design,
    correction_rows: list[dict],
    batch_volume_m3: float,
    preferences: ReportPreferences,
    statistics: list,
    design_name: str,
    group_name: str,
    description: str,
    specification: DesignSpecification,
) -> None:
    y = _draw_header(
        pdf,
        preferences,
        "Informe técnico de laboratorio",
        "Diseño de mezcla de concreto - Método de volúmenes absolutos",
        1,
    )

    y = _draw_section_title(pdf, "Identificación y parámetros del diseño", y)
    identity = f"{design_name}" + (f" / Grupo: {group_name}" if group_name else "")
    strength_text = _strength_text(specification)
    consistency_text = _consistency_text(specification)
    acceleration = (
        f"Sí · {specification.accelerated_age_days:g} días"
        if specification.accelerated and specification.accelerated_age_days is not None
        else ("Sí" if specification.accelerated else "No")
    )
    summary = [
        ["Diseño", identity, "Tipo", APPLICATION_LABELS[specification.application_type]],
        ["Resistencia esperada", strength_text, CONSISTENCY_LABELS[specification.consistency_type], consistency_text],
        [
            "Tamaño máximo nominal",
            f"{specification.nominal_max_size_mm:g} mm" if specification.nominal_max_size_mm is not None else "—",
            "Fraguado inicial",
            f"{specification.initial_set_minutes} min" if specification.initial_set_minutes is not None else "—",
        ],
        ["Acelerado", acceleration, "Exposición", specification.exposure_condition or "—"],
        [
            "Relación a/mc objetivo",
            f"{design.parameters.target_w_cm:.3f}",
            "Relación a/mc calculada",
            f"{design.actual_w_cm:.3f}",
        ],
        [
            "Volumen absoluto",
            f"{design.total_absolute_volume_l:.2f} L",
            "Volumen de amasada",
            f"{batch_volume_m3:.4f} m³",
        ],
    ]
    basis = design.parameters.strength_basis_snapshot
    if design.parameters.fcr_mpa is not None:
        summary.append(["f'c especificado", f"{design.parameters.fc_mpa:.2f} MPa",
                        "f'cr requerido", f"{design.parameters.fcr_mpa:.2f} MPa"])
        summary.append(["Base de resistencia", basis.get('mode','Sin documentar'),
                        "N / s / factor", f"{basis.get('n','—')} / {basis.get('s_mpa','—')} / {basis.get('factor','—')}"])
    y = _draw_table(
        pdf,
        summary,
        [37 * mm, 55 * mm, 40 * mm, 51 * mm],
        y,
        max_height=50 * mm,
        header_rows=0,
        font_size=7.4,
        label_columns={0, 2},
    ) - 3 * mm

    y = _draw_section_title(pdf, "Materiales, propiedades físicas y dosificación", y)
    by_uid = {str(row.get("uid")): row for row in correction_rows}
    materials = [["Material", "Categoría", "G.E.", "Abs. %", "Hum. %", "Diseño/m³", "Corregido/m³", "Amasada"]]
    for component in design.enabled_components():
        row = by_uid.get(component.uid, {})
        corrected = float(row.get("corrected_quantity", component.quantity))
        materials.append(
            [
                component.material.name,
                CATEGORY_LABELS.get(component.category, str(component.category)),
                f"{component.material.specific_gravity:.3f}",
                f"{component.material.absorption_pct:.2f}",
                f"{design.batch_moistures.get(component.uid, component.material.moisture_pct):.2f}",
                f"{component.quantity:.3f} {component.unit}",
                f"{corrected:.3f} {component.unit}",
                f"{corrected * batch_volume_m3:.3f} {component.unit}",
            ]
        )
    y = _draw_table(
        pdf,
        materials,
        [37 * mm, 27 * mm, 13 * mm, 14 * mm, 14 * mm, 24 * mm, 27 * mm, 27 * mm],
        y,
        max_height=71 * mm,
        header_rows=1,
        font_size=6.7,
    ) - 3 * mm

    enabled_constraints = [item for item in design.ratio_constraints if item.enabled]
    if enabled_constraints:
        y = _draw_section_title(pdf, "Relaciones y dosificaciones internas", y)
        relations = [["Material A", "Regla", "Base", "Objetivo"]]
        for constraint in enabled_constraints:
            numerator = design.component(constraint.numerator_uid)
            denominator = design.component(constraint.denominator_uid)
            relations.append(
                [
                    numerator.material.name if numerator else "Material no disponible",
                    CONSTRAINT_LABELS[constraint.mode],
                    denominator.material.name if denominator else "Cementante total",
                    f"{constraint.target_ratio:g}{CONSTRAINT_SUFFIXES[constraint.mode]}",
                ]
            )
        y = _draw_table(
            pdf,
            relations,
            [48 * mm, 49 * mm, 51 * mm, 35 * mm],
            y,
            max_height=38 * mm,
            header_rows=1,
            font_size=6.8,
        ) - 3 * mm

    y = _draw_section_title(pdf, "Control de mezcla de prueba", y)
    control = [
        ["Fecha", "", "Responsable", ""],
        ["Asentamiento real", "", "Temperatura", ""],
        ["Contenido de aire", "", "Masa unitaria", ""],
        ["Rendimiento", "", "Observaciones", ""],
    ]
    y = _draw_table(
        pdf,
        control,
        [33 * mm, 53 * mm, 35 * mm, 62 * mm],
        y,
        max_height=25 * mm,
        header_rows=0,
        font_size=7.1,
        label_columns={0, 2},
        minimum_row_height=5.2 * mm,
    ) - 3 * mm

    y = _draw_section_title(pdf, "Resultados de resistencia", y)
    available = max(y - FOOTER_TOP - 3 * mm, 34 * mm)
    if statistics:
        strength = [["Ensayo", "Edad", "n", "Promedio", "Mínimo", "Máximo", "Desv."]]
        for record in statistics:
            test_name = "Compresión" if str(record.specimen_type.value) == "cylinder" else "Flexión"
            strength.append(
                [
                    test_name,
                    f"{record.target_age_days:g} d",
                    str(record.result_count),
                    f"{record.average_mpa:.3f} MPa",
                    f"{record.minimum_mpa:.3f} MPa",
                    f"{record.maximum_mpa:.3f} MPa",
                    (f"{record.standard_deviation_mpa:.3f} MPa" if record.standard_deviation_mpa is not None else "No estimable (N < 2)"),
                ]
            )
        _draw_table(
            pdf,
            strength,
            [32 * mm, 21 * mm, 12 * mm, 31 * mm, 28 * mm, 28 * mm, 31 * mm],
            y,
            max_height=available,
            header_rows=1,
            font_size=6.9,
        )
    else:
        strength = [["Edad", "Identificación", "Carga", "Resultado", "Observaciones"]]
        for _ in range(5):
            strength.append(["", "", "", "", ""])
        _draw_table(
            pdf,
            strength,
            [22 * mm, 39 * mm, 28 * mm, 35 * mm, 59 * mm],
            y,
            max_height=available,
            header_rows=1,
            font_size=7.2,
            minimum_row_height=7.2 * mm,
        )

    _draw_footer(pdf, preferences, 1)


def _draw_client_page(
    pdf: canvas.Canvas,
    design,
    preferences: ReportPreferences,
    design_name: str,
    group_name: str,
    description: str,
    specification: DesignSpecification,
) -> None:
    y = _draw_header(
        pdf,
        preferences,
        "Ficha técnica de mezcla de concreto",
        "Documento de entrega al cliente",
        2,
    )

    y = _draw_section_title(pdf, "Datos de entrega", y)
    delivery = [
        ["Cliente", "", "Proyecto", ""],
        ["Elemento o uso", "", "Fecha", ""],
        ["Código / lote", "", "Responsable", ""],
    ]
    y = _draw_table(
        pdf,
        delivery,
        [29 * mm, 58 * mm, 31 * mm, 65 * mm],
        y,
        max_height=24 * mm,
        header_rows=0,
        font_size=7.4,
        label_columns={0, 2},
        minimum_row_height=6 * mm,
    ) - 5 * mm

    y = _draw_section_title(pdf, "Características objetivo", y)
    air_pct = _air_content_pct(design)
    acceleration = (
        f"Sí · {specification.accelerated_age_days:g} días"
        if specification.accelerated and specification.accelerated_age_days is not None
        else ("Sí" if specification.accelerated else "No")
    )
    performance = [
        ["Nombre del diseño", design_name, "Grupo", group_name or "Sin grupo"],
        ["Tipo de concreto", APPLICATION_LABELS[specification.application_type], "Resistencia esperada", _strength_text(specification)],
        [CONSISTENCY_LABELS[specification.consistency_type], _consistency_text(specification), "Tamaño máximo nominal", f"{specification.nominal_max_size_mm:g} mm" if specification.nominal_max_size_mm is not None else "—"],
        ["Fraguado inicial", f"{specification.initial_set_minutes} min" if specification.initial_set_minutes is not None else "—", "Acelerado", acceleration],
        ["Contenido de aire previsto", f"{air_pct:.1f} %", "Método", "Volúmenes absolutos"],
    ]
    y = _draw_table(
        pdf,
        performance,
        [38 * mm, 51 * mm, 39 * mm, 55 * mm],
        y,
        max_height=31 * mm,
        header_rows=0,
        font_size=7.5,
        label_columns={0, 2},
    ) - 5 * mm

    y = _draw_section_title(pdf, "Constitución de la mezcla", y)
    grouped: dict[MaterialCategory, list[str]] = defaultdict(list)
    for component in design.enabled_components():
        grouped[component.category].append(component.material.name)

    composition = [["Componente", "Materiales incluidos"]]
    order = [
        MaterialCategory.WATER,
        MaterialCategory.CEMENTITIOUS,
        MaterialCategory.FINE_AGGREGATE,
        MaterialCategory.COARSE_AGGREGATE,
        MaterialCategory.ADMIXTURE,
        MaterialCategory.AIR,
        MaterialCategory.OTHER,
    ]
    for category in order:
        names = grouped.get(category, [])
        if names:
            composition.append([CATEGORY_LABELS[category], ", ".join(names)])
    y = _draw_table(
        pdf,
        composition,
        [47 * mm, 136 * mm],
        y,
        max_height=68 * mm,
        header_rows=1,
        font_size=8.0,
        minimum_row_height=7 * mm,
    ) - 6 * mm

    y = _draw_section_title(pdf, "Descripción y observaciones", y)
    description_text = description.strip() or (
        "Mezcla diseñada para cumplir las características objetivo indicadas. "
        "La aplicación, colocación, compactación, acabado, curado y control deben "
        "realizarse de acuerdo con las especificaciones del proyecto."
    )
    paragraph = _paragraph(description_text, 8.5, leading=12, color="#334155")
    _, paragraph_height = paragraph.wrap(CONTENT_WIDTH, 42 * mm)
    paragraph.drawOn(pdf, MARGIN_X, y - paragraph_height)
    y -= paragraph_height + 7 * mm

    y = _draw_section_title(pdf, "Control y aceptación", y)
    controls = [
        ["Control de recepción", "Verificar asentamiento, temperatura y demás propiedades acordadas para el suministro."],
        ["Muestreo y curado", "Realizar la toma, identificación, conservación y ensayo de muestras conforme al plan de calidad aplicable."],
        ["Aceptación", "La conformidad se determina con los resultados de control, las especificaciones contractuales y los criterios técnicos del proyecto."],
    ]
    y = _draw_table(
        pdf,
        controls,
        [42 * mm, 141 * mm],
        y,
        max_height=54 * mm,
        header_rows=0,
        font_size=7.7,
        label_columns={0},
        minimum_row_height=10 * mm,
    ) - 7 * mm

    signatures = [
        ["Elaboró", "", "Revisó", ""],
        ["Firma", "", "Firma", ""],
    ]
    _draw_table(
        pdf,
        signatures,
        [25 * mm, 66 * mm, 25 * mm, 67 * mm],
        y,
        max_height=max(y - FOOTER_TOP - 3 * mm, 22 * mm),
        header_rows=0,
        font_size=7.3,
        label_columns={0, 2},
        minimum_row_height=8 * mm,
    )

    _draw_footer(pdf, preferences, 2)


def _strength_text(specification: DesignSpecification) -> str:
    parts = []
    if specification.strength_basis in {StrengthBasis.COMPRESSION, StrengthBasis.BOTH}:
        if specification.expected_compressive_strength_mpa is not None:
            parts.append(
                f"f'c {specification.expected_compressive_strength_mpa:.2f} MPa "
                f"@ {specification.compressive_strength_age_days:g} d"
            )
    if specification.strength_basis in {StrengthBasis.FLEXURAL, StrengthBasis.BOTH}:
        if specification.expected_modulus_rupture_mpa is not None:
            parts.append(
                f"MR {specification.expected_modulus_rupture_mpa:.2f} MPa "
                f"@ {specification.modulus_rupture_age_days:g} d"
            )
    return " / ".join(parts) or "—"


def _consistency_text(specification: DesignSpecification) -> str:
    value = specification.consistency_value_mm
    if value is None:
        return "—"
    if specification.consistency_type.value == "slump":
        return f"{value / 25.4:.2f} in / {value:.1f} mm"
    return f"{value:.1f} mm"


def _draw_header(
    pdf: canvas.Canvas,
    preferences: ReportPreferences,
    title: str,
    subtitle: str,
    page_number: int,
) -> float:
    top = PAGE_HEIGHT - 12 * mm
    logo_width = 0.0
    logo_path = Path(preferences.logo_path) if preferences.logo_path else None
    if logo_path and logo_path.exists():
        try:
            image = ImageReader(str(logo_path))
            image_width, image_height = image.getSize()
            max_width = 31 * mm
            max_height = 19 * mm
            scale = min(max_width / image_width, max_height / image_height)
            draw_width = image_width * scale
            draw_height = image_height * scale
            pdf.drawImage(
                image,
                MARGIN_X,
                top - draw_height,
                width=draw_width,
                height=draw_height,
                preserveAspectRatio=True,
                mask="auto",
            )
            logo_width = max_width + 4 * mm
        except Exception:
            logo_width = 0.0

    text_x = MARGIN_X + logo_width
    text_width = CONTENT_WIDTH - logo_width
    pdf.setFillColor(colors.HexColor("#12355b"))
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(text_x, top - 5 * mm, title)
    pdf.setFillColor(colors.HexColor("#526579"))
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(text_x, top - 10 * mm, subtitle)

    letterhead = preferences.letterhead_text.strip()
    if letterhead:
        paragraph, height = _fitted_paragraph(
            letterhead,
            text_width,
            9 * mm,
            base_font_size=7.5,
            minimum_font_size=5.5,
            color="#475569",
        )
        paragraph.drawOn(pdf, text_x, top - 12 * mm - height)

    line_y = top - 23 * mm
    pdf.setStrokeColor(colors.HexColor("#9fb2c5"))
    pdf.setLineWidth(0.7)
    pdf.line(MARGIN_X, line_y, PAGE_WIDTH - MARGIN_X, line_y)
    return line_y - 5 * mm


def _draw_footer(pdf: canvas.Canvas, preferences: ReportPreferences, page_number: int) -> None:
    line_y = 14 * mm
    pdf.setStrokeColor(colors.HexColor("#9fb2c5"))
    pdf.setLineWidth(0.5)
    pdf.line(MARGIN_X, line_y, PAGE_WIDTH - MARGIN_X, line_y)

    footer = preferences.footer_text.strip()
    if footer:
        paragraph, height = _fitted_paragraph(
            footer,
            CONTENT_WIDTH - 30 * mm,
            7 * mm,
            base_font_size=6.7,
            minimum_font_size=5.0,
            color="#526579",
        )
        paragraph.drawOn(pdf, MARGIN_X, 5.2 * mm)

    pdf.setFillColor(colors.HexColor("#526579"))
    pdf.setFont("Helvetica", 7)
    pdf.drawRightString(PAGE_WIDTH - MARGIN_X, 7 * mm, f"Página {page_number} de 2")


def _draw_section_title(pdf: canvas.Canvas, title: str, y: float) -> float:
    pdf.setFillColor(colors.HexColor("#12355b"))
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawString(MARGIN_X, y, title)
    pdf.setStrokeColor(colors.HexColor("#d5dee8"))
    pdf.setLineWidth(0.4)
    pdf.line(MARGIN_X, y - 1.5 * mm, PAGE_WIDTH - MARGIN_X, y - 1.5 * mm)
    return y - 4.3 * mm


def _draw_table(
    pdf: canvas.Canvas,
    data: list[list[object]],
    col_widths: list[float],
    y_top: float,
    *,
    max_height: float,
    header_rows: int,
    font_size: float,
    label_columns: set[int] | None = None,
    minimum_row_height: float | None = None,
) -> float:
    label_columns = label_columns or set()
    selected_table = None
    selected_height = 0.0

    for current_font in [font_size, font_size - 0.5, font_size - 1.0, font_size - 1.5, 5.2]:
        current_font = max(current_font, 5.2)
        leading = current_font + 1.4
        converted: list[list[object]] = []
        for row_index, row in enumerate(data):
            converted_row: list[object] = []
            for column_index, value in enumerate(row):
                is_header = row_index < header_rows
                is_label = column_index in label_columns and not is_header
                converted_row.append(
                    _paragraph(
                        str(value),
                        current_font,
                        leading=leading,
                        bold=is_header or is_label,
                        color="#ffffff" if is_header else "#1f2937",
                    )
                )
            converted.append(converted_row)

        row_heights = None
        if minimum_row_height is not None:
            row_heights = [minimum_row_height] * len(converted)
        table = Table(converted, colWidths=col_widths, rowHeights=row_heights, repeatRows=header_rows)
        style = [
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9aa9b8")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2.2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2.2),
            ("TOPPADDING", (0, 0), (-1, -1), 1.8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8),
        ]
        if header_rows:
            style.extend(
                [
                    ("BACKGROUND", (0, 0), (-1, header_rows - 1), colors.HexColor("#12355b")),
                    ("ROWBACKGROUNDS", (0, header_rows), (-1, -1), [colors.white, colors.HexColor("#f4f7fb")]),
                ]
            )
        else:
            style.append(("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]))
        if label_columns:
            for column in label_columns:
                style.append(("BACKGROUND", (column, 0), (column, -1), colors.HexColor("#eaf0f7")))
        table.setStyle(TableStyle(style))
        _, height = table.wrap(CONTENT_WIDTH, max_height)
        selected_table = table
        selected_height = height
        if height <= max_height:
            break

    assert selected_table is not None
    scale = min(1.0, max_height / selected_height) if selected_height > 0 else 1.0
    if scale < 1.0:
        pdf.saveState()
        scaled_width = sum(col_widths) * scale
        x = MARGIN_X + (CONTENT_WIDTH - scaled_width) / 2
        pdf.translate(x, y_top - selected_height * scale)
        pdf.scale(scale, scale)
        selected_table.drawOn(pdf, 0, 0)
        pdf.restoreState()
        return y_top - selected_height * scale

    selected_table.drawOn(pdf, MARGIN_X, y_top - selected_height)
    return y_top - selected_height


def _fitted_paragraph(
    text: str,
    width: float,
    max_height: float,
    *,
    base_font_size: float,
    minimum_font_size: float,
    color: str,
) -> tuple[Paragraph, float]:
    candidate_text = str(text).strip()
    font_size = base_font_size
    while font_size >= minimum_font_size:
        paragraph = _paragraph(
            candidate_text,
            font_size,
            leading=font_size + 1.4,
            color=color,
        )
        _, height = paragraph.wrap(width, max_height)
        if height <= max_height:
            return paragraph, height
        font_size -= 0.5

    while len(candidate_text) > 30:
        candidate_text = candidate_text[:-20].rstrip() + "..."
        paragraph = _paragraph(
            candidate_text,
            minimum_font_size,
            leading=minimum_font_size + 1.2,
            color=color,
        )
        _, height = paragraph.wrap(width, max_height)
        if height <= max_height:
            return paragraph, height

    paragraph = _paragraph(
        candidate_text,
        minimum_font_size,
        leading=minimum_font_size + 1.2,
        color=color,
    )
    _, height = paragraph.wrap(width, max_height)
    return paragraph, min(height, max_height)


def _paragraph(
    text: str,
    font_size: float,
    *,
    leading: float,
    bold: bool = False,
    color: str = "#1f2937",
) -> Paragraph:
    safe_text = escape(str(text)).replace("\n", "<br/>")
    if bold:
        safe_text = f"<b>{safe_text}</b>"
    style = ParagraphStyle(
        name=f"cell-{font_size}-{bold}-{color}",
        fontName="Helvetica",
        fontSize=font_size,
        leading=leading,
        textColor=colors.HexColor(color),
        spaceAfter=0,
        spaceBefore=0,
    )
    return Paragraph(safe_text or "&nbsp;", style)


def _air_content_pct(design) -> float:
    air_l = sum(
        component.absolute_volume_l
        for component in design.enabled_components()
        if component.category == MaterialCategory.AIR
    )
    target_volume = max(float(design.parameters.target_volume_l), 1e-9)
    return air_l / target_volume * 100.0
