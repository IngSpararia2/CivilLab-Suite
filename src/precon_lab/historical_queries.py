from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session, joinedload

from .historical_codes import build_production_code, build_test_code, derive_product_code
from .models import HistoricalSpecimen, HistoricalTest


@dataclass(frozen=True)
class HistoricalFilters:
    date_field: str = "production"  # production | test
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    product_text: str = ""
    material_text: str = ""
    file_text: str = ""
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    reading_status: str = ""
    incidents_mode: str = "ALL"  # ALL | WITH | WITHOUT


@dataclass(frozen=True)
class HistoricalProductionSummary:
    product_code: str
    production_code: str
    product_name: str
    production_date: Optional[date]
    file_summary: str
    reading_summary: str
    incident_count: int
    test_count: int


@dataclass(frozen=True)
class HistoricalTestSummary:
    id: int
    test_type: str
    product_code: str
    production_code: str
    test_code: str
    product_name: str
    production_date: Optional[date]
    test_date: Optional[date]
    target_age_days: Optional[int]
    source_file: str
    reading_status: str
    incidents: str
    natural_mass_avg: Optional[float]
    dry_mass_avg: Optional[float]
    immersed_mass_avg: Optional[float]
    saturated_mass_avg: Optional[float]
    density_avg: Optional[float]
    maximum_load_avg: Optional[float]
    absorption_avg: Optional[float]
    strength_avg: Optional[float]
    flexural_avg: Optional[float]
    thickness_avg: Optional[float]


@dataclass(frozen=True)
class HistoricalSpecimenView:
    ordinal: int
    specimen_code: str
    material: str
    production_date: Optional[date]
    age_days: Optional[int]
    natural_mass: Optional[float]
    dry_mass: Optional[float]
    immersed_mass: Optional[float]
    saturated_mass: Optional[float]
    density: Optional[float]
    absorption: Optional[float]
    maximum_load: Optional[float]
    strength: Optional[float]
    flexural_modulus: Optional[float]
    thickness: Optional[float]


# Compatibilidad con las pruebas y con cualquier código que todavía utilice
# query_historical_groups(). La nueva interfaz no usa esta ruta pesada.
@dataclass(frozen=True)
class HistoricalTestView(HistoricalTestSummary):
    specimens: tuple[HistoricalSpecimenView, ...]


@dataclass(frozen=True)
class HistoricalProductionGroup:
    product_code: str
    production_code: str
    product_name: str
    production_date: Optional[date]
    file_summary: str
    reading_summary: str
    incident_count: int
    tests: tuple[HistoricalTestView, ...]


def _average(values: Iterable[Optional[float]]) -> Optional[float]:
    valid = [float(value) for value in values if value is not None]
    return sum(valid) / len(valid) if valid else None


def _most_common_text(values: Iterable[str]) -> str:
    cleaned = [value.strip() for value in values if value and value.strip()]
    if not cleaned:
        return ""
    counts = Counter(cleaned)
    return max(counts, key=lambda item: (counts[item], len(item)))


def _apply_filters(
    statement: Select,
    *,
    test_type: str,
    filters: HistoricalFilters,
) -> Select:
    if test_type not in {"COMPRESSION", "FLEXURE"}:
        raise ValueError("test_type debe ser COMPRESSION o FLEXURE")

    statement = statement.where(HistoricalTest.test_type == test_type)

    date_column = (
        HistoricalTest.production_date
        if filters.date_field == "production"
        else HistoricalTest.test_date
    )
    if filters.date_from is not None:
        statement = statement.where(date_column >= filters.date_from)
    if filters.date_to is not None:
        statement = statement.where(date_column <= filters.date_to)

    product_text = filters.product_text.strip()
    if product_text:
        like = f"%{product_text}%"
        statement = statement.where(
            or_(
                HistoricalTest.product_code.ilike(like),
                HistoricalTest.production_code.ilike(like),
                HistoricalTest.test_code.ilike(like),
            )
        )

    material_text = filters.material_text.strip()
    if material_text:
        statement = statement.where(
            HistoricalTest.product_name.ilike(f"%{material_text}%")
        )

    file_text = filters.file_text.strip()
    if file_text:
        statement = statement.where(
            HistoricalTest.source_file.ilike(f"%{file_text}%")
        )

    if filters.age_min is not None:
        statement = statement.where(
            HistoricalTest.target_age_days >= filters.age_min
        )
    if filters.age_max is not None:
        statement = statement.where(
            HistoricalTest.target_age_days <= filters.age_max
        )

    if filters.reading_status:
        statement = statement.where(
            HistoricalTest.reading_status == filters.reading_status
        )

    if filters.incidents_mode == "WITH":
        statement = statement.where(HistoricalTest.incidents != "")
    elif filters.incidents_mode == "WITHOUT":
        statement = statement.where(HistoricalTest.incidents == "")

    return statement


def _resolved_product_code(
    *,
    product_code: str,
    product_name: str,
    source_file: str,
) -> str:
    cleaned = product_code.strip() if product_code else ""
    if cleaned:
        return cleaned
    return derive_product_code(
        (),
        product_name=product_name,
        source_file=source_file,
    )


def list_reading_statuses(session: Session, test_type: str) -> list[str]:
    statement = (
        select(HistoricalTest.reading_status)
        .where(
            HistoricalTest.test_type == test_type,
            HistoricalTest.reading_status != "",
        )
        .distinct()
        .order_by(HistoricalTest.reading_status)
    )
    return list(session.scalars(statement))


def _production_group_subquery(
    *,
    test_type: str,
    filters: HistoricalFilters,
):
    # database.py ya completa product_code en la base existente. COALESCE evita
    # que registros antiguos incompletos desaparezcan del explorador.
    resolved_code = func.coalesce(
        func.nullif(HistoricalTest.product_code, ""),
        func.nullif(HistoricalTest.product_name, ""),
        "SIN-CODIGO",
    )

    statement = select(
        resolved_code.label("product_code"),
        HistoricalTest.production_date.label("production_date"),
        func.max(HistoricalTest.production_code).label("production_code"),
        func.max(HistoricalTest.product_name).label("product_name"),
        func.count(HistoricalTest.id).label("test_count"),
        func.count(
            func.distinct(func.nullif(HistoricalTest.source_file, ""))
        ).label("file_count"),
        func.min(func.nullif(HistoricalTest.source_file, "")).label("first_file"),
        func.count(
            func.distinct(func.nullif(HistoricalTest.reading_status, ""))
        ).label("reading_count"),
        func.min(func.nullif(HistoricalTest.reading_status, "")).label("first_reading"),
        func.sum(
            case((HistoricalTest.incidents != "", 1), else_=0)
        ).label("incident_count"),
    )
    statement = _apply_filters(
        statement,
        test_type=test_type,
        filters=filters,
    )
    return statement.group_by(
        resolved_code,
        HistoricalTest.production_date,
    ).subquery()


def count_historical_productions(
    session: Session,
    *,
    test_type: str,
    filters: HistoricalFilters,
) -> int:
    grouped = _production_group_subquery(
        test_type=test_type,
        filters=filters,
    )
    return int(
        session.scalar(select(func.count()).select_from(grouped)) or 0
    )


def query_historical_production_page(
    session: Session,
    *,
    test_type: str,
    filters: HistoricalFilters,
    limit: int = 25,
    offset: int = 0,
    sort_field: str = "date",
    descending: bool = True,
) -> list[HistoricalProductionSummary]:
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    grouped = _production_group_subquery(
        test_type=test_type,
        filters=filters,
    )
    statement = select(grouped)

    sort_map = {
        "date": grouped.c.production_date,
        "product": grouped.c.product_code,
        "tests": grouped.c.test_count,
        "reading": grouped.c.first_reading,
    }
    sort_column = sort_map.get(sort_field, grouped.c.production_date)
    order_expression = sort_column.desc() if descending else sort_column.asc()
    statement = statement.order_by(
        order_expression,
        grouped.c.product_code.asc(),
        grouped.c.production_date.desc(),
    ).limit(limit).offset(offset)

    result: list[HistoricalProductionSummary] = []
    for row in session.execute(statement):
        product_code = row.product_code or "SIN-CODIGO"
        production_code = row.production_code or build_production_code(
            product_code,
            row.production_date,
        )
        file_count = int(row.file_count or 0)
        reading_count = int(row.reading_count or 0)
        file_summary = (
            row.first_file
            if file_count == 1
            else (f"{file_count} archivos" if file_count else "")
        )
        reading_summary = (
            row.first_reading
            if reading_count == 1
            else (f"Mixta ({reading_count})" if reading_count else "")
        )
        result.append(
            HistoricalProductionSummary(
                product_code=product_code,
                production_code=production_code,
                product_name=row.product_name or "",
                production_date=row.production_date,
                file_summary=file_summary,
                reading_summary=reading_summary,
                incident_count=int(row.incident_count or 0),
                test_count=int(row.test_count or 0),
            )
        )
    return result


def query_historical_productions(
    session: Session,
    *,
    test_type: str,
    filters: HistoricalFilters,
) -> list[HistoricalProductionSummary]:
    """Compatibilidad con la interfaz anterior: devuelve todas las producciones."""
    total = count_historical_productions(
        session,
        test_type=test_type,
        filters=filters,
    )
    if total == 0:
        return []

    result: list[HistoricalProductionSummary] = []
    offset = 0
    while offset < total:
        result.extend(
            query_historical_production_page(
                session,
                test_type=test_type,
                filters=filters,
                limit=200,
                offset=offset,
                sort_field="date",
                descending=True,
            )
        )
        offset += 200
    return result


def _aggregate_specimens(
    session: Session,
    test_ids: list[int],
) -> dict[int, dict[str, Optional[float]]]:
    if not test_ids:
        return {}

    statement = (
        select(
            HistoricalSpecimen.historical_test_id,
            func.avg(HistoricalSpecimen.natural_mass).label("natural_mass_avg"),
            func.avg(HistoricalSpecimen.dry_mass).label("dry_mass_avg"),
            func.avg(HistoricalSpecimen.immersed_mass).label("immersed_mass_avg"),
            func.avg(HistoricalSpecimen.saturated_mass).label("saturated_mass_avg"),
            func.avg(HistoricalSpecimen.density).label("density_avg"),
            func.avg(HistoricalSpecimen.absorption).label("absorption_avg"),
            func.avg(HistoricalSpecimen.maximum_load).label("maximum_load_avg"),
            func.avg(HistoricalSpecimen.strength).label("strength_avg"),
            func.avg(HistoricalSpecimen.flexural_modulus).label("flexural_avg"),
            func.avg(HistoricalSpecimen.thickness).label("thickness_avg"),
        )
        .where(HistoricalSpecimen.historical_test_id.in_(test_ids))
        .group_by(HistoricalSpecimen.historical_test_id)
    )

    result: dict[int, dict[str, Optional[float]]] = {}
    for row in session.execute(statement):
        result[int(row.historical_test_id)] = {
            "natural_mass_avg": row.natural_mass_avg,
            "dry_mass_avg": row.dry_mass_avg,
            "immersed_mass_avg": row.immersed_mass_avg,
            "saturated_mass_avg": row.saturated_mass_avg,
            "density_avg": row.density_avg,
            "absorption_avg": row.absorption_avg,
            "maximum_load_avg": row.maximum_load_avg,
            "strength_avg": row.strength_avg,
            "flexural_avg": row.flexural_avg,
            "thickness_avg": row.thickness_avg,
        }
    return result


def query_historical_tests_for_production(
    session: Session,
    *,
    test_type: str,
    product_code: str,
    production_date: Optional[date],
    filters: HistoricalFilters,
) -> list[HistoricalTestSummary]:
    statement = select(
        HistoricalTest.id,
        HistoricalTest.test_type,
        HistoricalTest.product_code,
        HistoricalTest.production_code,
        HistoricalTest.test_code,
        HistoricalTest.product_name,
        HistoricalTest.production_date,
        HistoricalTest.test_date,
        HistoricalTest.target_age_days,
        HistoricalTest.source_file,
        HistoricalTest.reading_status,
        HistoricalTest.incidents,
        HistoricalTest.absorption_avg,
        HistoricalTest.strength_avg,
        HistoricalTest.flexural_avg,
    )
    statement = _apply_filters(
        statement,
        test_type=test_type,
        filters=filters,
    ).where(HistoricalTest.product_code == product_code)

    if production_date is None:
        statement = statement.where(HistoricalTest.production_date.is_(None))
    else:
        statement = statement.where(
            HistoricalTest.production_date == production_date
        )

    statement = statement.order_by(
        HistoricalTest.target_age_days,
        HistoricalTest.test_date,
        HistoricalTest.id,
    )
    rows = session.execute(statement).all()
    aggregates = _aggregate_specimens(
        session,
        [int(row.id) for row in rows],
    )

    result: list[HistoricalTestSummary] = []
    for row in rows:
        avg = aggregates.get(int(row.id), {})
        resolved_code = _resolved_product_code(
            product_code=row.product_code,
            product_name=row.product_name,
            source_file=row.source_file,
        )
        result.append(
            HistoricalTestSummary(
                id=int(row.id),
                test_type=row.test_type,
                product_code=resolved_code,
                production_code=(
                    row.production_code
                    or build_production_code(
                        resolved_code,
                        row.production_date,
                    )
                ),
                test_code=(
                    row.test_code
                    or build_test_code(
                        resolved_code,
                        row.target_age_days,
                        row.test_date,
                    )
                ),
                product_name=row.product_name,
                production_date=row.production_date,
                test_date=row.test_date,
                target_age_days=row.target_age_days,
                source_file=row.source_file,
                reading_status=row.reading_status,
                incidents=row.incidents,
                natural_mass_avg=avg.get("natural_mass_avg"),
                dry_mass_avg=avg.get("dry_mass_avg"),
                immersed_mass_avg=avg.get("immersed_mass_avg"),
                saturated_mass_avg=avg.get("saturated_mass_avg"),
                density_avg=avg.get("density_avg"),
                maximum_load_avg=avg.get("maximum_load_avg"),
                absorption_avg=(
                    row.absorption_avg
                    if row.absorption_avg is not None
                    else avg.get("absorption_avg")
                ),
                strength_avg=(
                    row.strength_avg
                    if row.strength_avg is not None
                    else avg.get("strength_avg")
                ),
                flexural_avg=(
                    row.flexural_avg
                    if row.flexural_avg is not None
                    else avg.get("flexural_avg")
                ),
                thickness_avg=avg.get("thickness_avg"),
            )
        )
    return result


def query_historical_specimens(
    session: Session,
    *,
    historical_test_id: int,
) -> list[HistoricalSpecimenView]:
    statement = (
        select(HistoricalSpecimen)
        .where(
            HistoricalSpecimen.historical_test_id == historical_test_id
        )
        .order_by(HistoricalSpecimen.ordinal)
    )
    return [
        HistoricalSpecimenView(
            ordinal=item.ordinal,
            specimen_code=item.specimen_code,
            material=item.material,
            production_date=item.production_date,
            age_days=item.age_days,
            natural_mass=item.natural_mass,
            dry_mass=item.dry_mass,
            immersed_mass=item.immersed_mass,
            saturated_mass=item.saturated_mass,
            density=item.density,
            absorption=item.absorption,
            maximum_load=item.maximum_load,
            strength=item.strength,
            flexural_modulus=item.flexural_modulus,
            thickness=item.thickness,
        )
        for item in session.scalars(statement)
    ]


def query_historical_groups(
    session: Session,
    *,
    test_type: str,
    filters: HistoricalFilters,
) -> list[HistoricalProductionGroup]:
    """Ruta de compatibilidad para pruebas existentes.

    La nueva interfaz usa paginación y consultas por nivel. Esta función conserva
    el contrato anterior para no romper las pruebas ni código auxiliar existente.
    """
    productions = query_historical_productions(
        session,
        test_type=test_type,
        filters=filters,
    )
    groups: list[HistoricalProductionGroup] = []
    for production in productions:
        summaries = query_historical_tests_for_production(
            session,
            test_type=test_type,
            product_code=production.product_code,
            production_date=production.production_date,
            filters=filters,
        )
        test_views: list[HistoricalTestView] = []
        for summary in summaries:
            specimens = tuple(
                query_historical_specimens(
                    session,
                    historical_test_id=summary.id,
                )
            )
            test_views.append(
                HistoricalTestView(
                    **summary.__dict__,
                    specimens=specimens,
                )
            )
        groups.append(
            HistoricalProductionGroup(
                product_code=production.product_code,
                production_code=production.production_code,
                product_name=production.product_name,
                production_date=production.production_date,
                file_summary=production.file_summary,
                reading_summary=production.reading_summary,
                incident_count=production.incident_count,
                tests=tuple(test_views),
            )
        )
    return groups
