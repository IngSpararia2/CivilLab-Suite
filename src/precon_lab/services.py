from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from .models import (
    HistoricalTest,
    InspectionPlanEntry,
    LaboratoryTest,
    MaterialType,
    Product,
    ProductionBatch,
    SampleSet,
    Specimen,
    TestApplicability,
    TestRequirement,
    TestResult,
    WorkflowTask,
)


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ProductionSummary:
    batch_id: int
    sample_set_count: int
    specimen_count: int
    task_count: int


def parse_ages(value: str | Iterable[int]) -> list[int]:
    if isinstance(value, str):
        raw = [part.strip() for part in value.replace(";", ",").split(",")]
        values = [int(part) for part in raw if part]
    else:
        values = [int(item) for item in value]
    ages = sorted(set(values))
    if not ages:
        raise ValidationError("Debes indicar al menos una edad de ensayo.")
    if any(age <= 0 for age in ages):
        raise ValidationError("Las edades deben ser números enteros mayores que cero.")
    return ages


def create_product(session: Session, name: str, code: str, category: str) -> Product:
    name = name.strip()
    code = code.strip().upper()
    category = category.strip().upper()
    if not name:
        raise ValidationError("El nombre del producto es obligatorio.")
    if category not in {"BLOCK", "FLEXURE"}:
        raise ValidationError("La categoría debe ser BLOCK o FLEXURE.")
    product = Product(name=name, code=code, category=category)
    session.add(product)
    session.flush()
    return product


def _add_specimens(sample_set: SampleSet, batch: ProductionBatch) -> None:
    product_code = batch.product.code or f"P{batch.product_id}"
    lot = batch.lot_code or batch.production_date.strftime("%Y%m%d")
    purpose_code = {"ABSORPTION": "ABS", "COMPRESSION": "CMP", "FLEXURE": "FLX"}[sample_set.purpose]
    age_code = f"{sample_set.target_age_days}D" if sample_set.target_age_days else "NA"
    for ordinal in range(1, sample_set.specimen_count + 1):
        sample_set.specimens.append(
            Specimen(
                ordinal=ordinal,
                specimen_code=f"{product_code}-{lot}-{purpose_code}-{age_code}-{ordinal}",
            )
        )


def _task(sample_set: SampleSet, task_type: str, title: str, instructions: str, day: date, sequence: int) -> None:
    sample_set.tasks.append(
        WorkflowTask(
            task_type=task_type,
            title=title,
            instructions=instructions,
            scheduled_date=day,
            original_scheduled_date=day,
            sequence=sequence,
        )
    )


def _configure_block_absorption(sample_set: SampleSet, production_date: date) -> None:
    count = sample_set.specimen_count
    _task(
        sample_set,
        "BLOCK_NATURAL_OVEN",
        "Registrar masa natural e ingresar al horno",
        f"Identificar {count} bloques, registrar masa natural y dimensiones disponibles; luego ingresar al horno.",
        production_date,
        10,
    )
    _task(
        sample_set,
        "BLOCK_DRY_TANK",
        "Registrar masa seca e ingresar al tanque",
        f"Retirar {count} bloques del horno, registrar masa seca e ingresarlos al tanque.",
        production_date + timedelta(days=1),
        20,
    )
    _task(
        sample_set,
        "BLOCK_IMMERSED_SATURATED",
        "Registrar masas inmersa y saturada",
        f"Registrar masa inmersa de {count} bloques, retirarlos, secar superficialmente, registrar masa saturada y definir disposición final.",
        production_date + timedelta(days=2),
        30,
    )


def _configure_compression(sample_set: SampleSet, test_date: date) -> None:
    _task(
        sample_set,
        "COMPRESSION_TEST",
        "Realizar ensayo de compresión",
        f"Ensayar {sample_set.specimen_count} bloques a {sample_set.target_age_days} días y registrar el promedio provisional.",
        test_date,
        100,
    )


def _configure_flexure(sample_set: SampleSet, test_date: date) -> None:
    count = sample_set.specimen_count
    _task(
        sample_set,
        "FLEXURE_OVEN",
        "Ingresar al horno y verificar dimensiones",
        f"Preparar {count} especímenes, verificar o registrar dimensiones e ingresarlos al horno.",
        test_date - timedelta(days=3),
        10,
    )
    _task(
        sample_set,
        "FLEXURE_DRY_TANK",
        "Registrar masa seca e ingresar al tanque",
        f"Retirar {count} especímenes del horno, registrar masa seca e ingresarlos al tanque.",
        test_date - timedelta(days=2),
        20,
    )
    _task(
        sample_set,
        "FLEXURE_IMMERSED_SATURATED_AIR",
        "Registrar masas inmersa y saturada; curar al aire",
        f"Registrar masa inmersa y masa saturada de {count} especímenes; luego dejarlos en curado al aire.",
        test_date - timedelta(days=1),
        30,
    )
    _task(
        sample_set,
        "FLEXURE_TEST",
        "Realizar ensayo de flexotracción",
        f"Ensayar {count} especímenes a {sample_set.target_age_days} días y registrar absorción y módulo de rotura promedio.",
        test_date,
        100,
    )


def create_production(
    session: Session,
    *,
    product_id: int,
    production_date: date,
    lot_code: str,
    ages: str | Iterable[int],
    quantity_produced: Optional[int] = None,
    notes: str = "",
    specimens_per_age: Optional[int] = None,
) -> ProductionSummary:
    product = session.get(Product, product_id)
    if product is None or not product.active:
        raise ValidationError("El producto seleccionado no existe o está inactivo.")
    parsed_ages = parse_ages(ages)
    if product.category == "FLEXURE" and min(parsed_ages) < 3:
        raise ValidationError("En este prototipo, flexotracción requiere edades de al menos 3 días.")

    batch = ProductionBatch(
        product=product,
        production_date=production_date,
        lot_code=lot_code.strip(),
        quantity_produced=quantity_produced,
        notes=notes.strip(),
    )
    session.add(batch)

    if product.category == "BLOCK":
        absorption_set = SampleSet(purpose="ABSORPTION", specimen_count=3, status="PLANNED")
        batch.sample_sets.append(absorption_set)
        _add_specimens(absorption_set, batch)
        _configure_block_absorption(absorption_set, production_date)

        count = specimens_per_age or 3
        for age in parsed_ages:
            test_date = production_date + timedelta(days=age)
            sample_set = SampleSet(
                purpose="COMPRESSION",
                target_age_days=age,
                planned_test_date=test_date,
                specimen_count=count,
                status="PLANNED",
            )
            batch.sample_sets.append(sample_set)
            _add_specimens(sample_set, batch)
            _configure_compression(sample_set, test_date)
    else:
        count = specimens_per_age or 5
        for age in parsed_ages:
            test_date = production_date + timedelta(days=age)
            sample_set = SampleSet(
                purpose="FLEXURE",
                target_age_days=age,
                planned_test_date=test_date,
                specimen_count=count,
                status="PLANNED",
            )
            batch.sample_sets.append(sample_set)
            _add_specimens(sample_set, batch)
            _configure_flexure(sample_set, test_date)

    session.flush()
    return ProductionSummary(
        batch_id=batch.id,
        sample_set_count=len(batch.sample_sets),
        specimen_count=sum(len(item.specimens) for item in batch.sample_sets),
        task_count=sum(len(item.tasks) for item in batch.sample_sets),
    )


def list_products(session: Session) -> list[Product]:
    return list(session.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.name)))


def list_tasks_for_date(session: Session, selected_date: date, include_done: bool = True) -> list[WorkflowTask]:
    stmt = (
        select(WorkflowTask)
        .options(
            joinedload(WorkflowTask.sample_set)
            .joinedload(SampleSet.batch)
            .joinedload(ProductionBatch.product)
        )
        .where(WorkflowTask.scheduled_date == selected_date)
        .order_by(WorkflowTask.status, WorkflowTask.sequence, WorkflowTask.id)
    )
    if not include_done:
        stmt = stmt.where(WorkflowTask.status != "DONE")
    return list(session.scalars(stmt).unique())


def list_overdue_tasks(session: Session, today: date) -> list[WorkflowTask]:
    stmt = (
        select(WorkflowTask)
        .options(
            joinedload(WorkflowTask.sample_set)
            .joinedload(SampleSet.batch)
            .joinedload(ProductionBatch.product)
        )
        .where(and_(WorkflowTask.scheduled_date < today, WorkflowTask.status != "DONE"))
        .order_by(WorkflowTask.scheduled_date, WorkflowTask.sequence)
    )
    return list(session.scalars(stmt).unique())


def complete_task(session: Session, task_id: int, notes: str = "") -> WorkflowTask:
    task = session.get(WorkflowTask, task_id)
    if task is None:
        raise ValidationError("La actividad no existe.")
    task.status = "DONE"
    task.completed_at = datetime.now()
    task.notes = notes.strip()
    _refresh_sample_set_status(task.sample_set)
    return task


def reopen_task(session: Session, task_id: int) -> WorkflowTask:
    task = session.get(WorkflowTask, task_id)
    if task is None:
        raise ValidationError("La actividad no existe.")
    task.status = "PENDING"
    task.completed_at = None
    _refresh_sample_set_status(task.sample_set)
    return task


def _refresh_sample_set_status(sample_set: SampleSet) -> None:
    if sample_set.result is not None:
        sample_set.status = "TESTED"
        return
    done = sum(task.status == "DONE" for task in sample_set.tasks)
    if done == 0:
        sample_set.status = "PLANNED"
    elif done == len(sample_set.tasks):
        sample_set.status = "READY"
    else:
        sample_set.status = "IN_PROGRESS"


def reprogram_sample_set(session: Session, sample_set_id: int, new_test_date: date) -> SampleSet:
    sample_set = session.scalar(
        select(SampleSet).options(joinedload(SampleSet.tasks)).where(SampleSet.id == sample_set_id)
    )
    if sample_set is None:
        raise ValidationError("El conjunto de muestras no existe.")
    if sample_set.planned_test_date is None:
        raise ValidationError("El conjunto de absorción exclusiva no usa fecha objetivo de ensayo.")
    if new_test_date <= sample_set.batch.production_date:
        raise ValidationError("La nueva fecha debe ser posterior a la fecha de producción.")
    delta = new_test_date - sample_set.planned_test_date
    for task in sample_set.tasks:
        if task.status != "DONE":
            task.scheduled_date = task.scheduled_date + delta
    sample_set.planned_test_date = new_test_date
    return sample_set


def list_result_candidates(session: Session) -> list[SampleSet]:
    stmt = (
        select(SampleSet)
        .join(SampleSet.batch)
        .options(joinedload(SampleSet.batch).joinedload(ProductionBatch.product), joinedload(SampleSet.result))
        .where(SampleSet.purpose.in_(["ABSORPTION", "COMPRESSION", "FLEXURE"]))
        .order_by(ProductionBatch.production_date.desc(), SampleSet.target_age_days)
    )
    return list(session.scalars(stmt).unique())


def save_provisional_result(
    session: Session,
    *,
    sample_set_id: int,
    test_date: date,
    absorption_avg: Optional[float] = None,
    strength_avg: Optional[float] = None,
    flexural_avg: Optional[float] = None,
    abrasion_avg: Optional[float] = None,
    notes: str = "",
) -> TestResult:
    sample_set = session.get(SampleSet, sample_set_id)
    if sample_set is None or sample_set.purpose not in {"ABSORPTION", "COMPRESSION", "FLEXURE"}:
        raise ValidationError("Selecciona un conjunto de absorción, compresión o flexotracción.")
    result = sample_set.result
    if result is None:
        result = TestResult(
            sample_set=sample_set,
            test_type=sample_set.purpose,
            test_date=test_date,
        )
        session.add(result)
    result.test_date = test_date
    result.absorption_avg = absorption_avg
    result.strength_avg = strength_avg
    result.flexural_avg = flexural_avg
    result.abrasion_avg = abrasion_avg
    result.notes = notes.strip()
    if result.imported_test_id is None:
        result.status = "PROVISIONAL"
        result.source = "MANUAL"
    sample_set.status = "TESTED"
    session.flush()
    return result


def dashboard_metrics(session: Session, today: date) -> dict[str, int]:
    pending_today = session.scalar(
        select(func.count()).select_from(WorkflowTask).where(
            and_(WorkflowTask.scheduled_date == today, WorkflowTask.status != "DONE")
        )
    ) or 0
    overdue = session.scalar(
        select(func.count()).select_from(WorkflowTask).where(
            and_(WorkflowTask.scheduled_date < today, WorkflowTask.status != "DONE")
        )
    ) or 0
    batches = session.scalar(
        select(func.count()).select_from(ProductionBatch).where(ProductionBatch.production_date == today)
    ) or 0
    provisional = session.scalar(
        select(func.count()).select_from(TestResult).where(TestResult.status == "PROVISIONAL")
    ) or 0
    historical = session.scalar(select(func.count()).select_from(HistoricalTest)) or 0
    return {
        "pending_today": pending_today,
        "overdue": overdue,
        "batches_today": batches,
        "provisional": provisional,
        "historical": historical,
    }


def list_batches(session: Session, limit: int = 500) -> list[ProductionBatch]:
    stmt = (
        select(ProductionBatch)
        .options(joinedload(ProductionBatch.product), joinedload(ProductionBatch.sample_sets))
        .order_by(ProductionBatch.production_date.desc(), ProductionBatch.id.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt).unique())


def list_results(session: Session, limit: int = 500) -> list[TestResult]:
    stmt = (
        select(TestResult)
        .options(
            joinedload(TestResult.sample_set)
            .joinedload(SampleSet.batch)
            .joinedload(ProductionBatch.product)
        )
        .order_by(TestResult.test_date.desc(), TestResult.id.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt).unique())


def list_historical_tests(session: Session, limit: int = 1000) -> list[HistoricalTest]:
    stmt = select(HistoricalTest).order_by(HistoricalTest.test_date.desc(), HistoricalTest.id.desc()).limit(limit)
    return list(session.scalars(stmt))


WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
ORDINALS = ("primer", "segundo", "tercer", "cuarto", "quinto")


def list_material_types(session: Session) -> list[MaterialType]:
    return list(
        session.scalars(
            select(MaterialType).where(MaterialType.active.is_(True)).order_by(MaterialType.name)
        )
    )


def list_applicable_tests(session: Session, material_type_id: int) -> list[TestApplicability]:
    stmt = (
        select(TestApplicability)
        .options(joinedload(TestApplicability.laboratory_test), joinedload(TestApplicability.standard))
        .where(TestApplicability.material_type_id == material_type_id)
        .join(TestApplicability.laboratory_test)
        .order_by(TestApplicability.preferred.desc(), LaboratoryTest.name)
    )
    return list(session.scalars(stmt))


def get_test_requirements(
    session: Session, material_type_id: int, laboratory_test_id: int
) -> list[TestRequirement]:
    stmt = (
        select(TestRequirement)
        .options(
            joinedload(TestRequirement.material_type),
            joinedload(TestRequirement.laboratory_test),
            joinedload(TestRequirement.standard),
        )
        .where(
            TestRequirement.material_type_id == material_type_id,
            TestRequirement.laboratory_test_id == laboratory_test_id,
        )
        .order_by(TestRequirement.condition, TestRequirement.aggregation, TestRequirement.id)
    )
    return list(session.scalars(stmt))


def list_inspection_catalog(
    session: Session,
) -> list[tuple[TestApplicability, Optional[TestRequirement]]]:
    """Devuelve el catálogo maestro con requisitos en una consulta, sin usar planes."""

    stmt = (
        select(TestApplicability, TestRequirement)
        .join(TestApplicability.material_type)
        .join(TestApplicability.laboratory_test)
        .outerjoin(
            TestRequirement,
            and_(
                TestRequirement.material_type_id == TestApplicability.material_type_id,
                TestRequirement.laboratory_test_id == TestApplicability.laboratory_test_id,
            ),
        )
        .options(
            joinedload(TestApplicability.material_type),
            joinedload(TestApplicability.laboratory_test).joinedload(LaboratoryTest.standard),
            joinedload(TestApplicability.standard),
            joinedload(TestRequirement.standard),
        )
        .order_by(
            MaterialType.name,
            LaboratoryTest.name,
            TestRequirement.grading,
            TestRequirement.condition,
            TestRequirement.aggregation,
            TestRequirement.id,
        )
    )
    return list(session.execute(stmt).all())


def validate_periodicity(
    frequency_type: str,
    *,
    weekday: Optional[int] = None,
    week_ordinal: Optional[int] = None,
    month_interval: Optional[int] = None,
    reference_date: Optional[date] = None,
) -> None:
    if frequency_type not in {"DAILY", "WEEKLY", "MONTHLY", "EVERY_X_MONTHS"}:
        raise ValidationError("Selecciona una periodicidad válida.")
    if frequency_type in {"WEEKLY", "MONTHLY", "EVERY_X_MONTHS"} and weekday not in range(7):
        raise ValidationError("Selecciona el día de la semana.")
    if frequency_type in {"MONTHLY", "EVERY_X_MONTHS"} and week_ordinal not in range(1, 6):
        raise ValidationError("Selecciona la semana ordinal del mes.")
    if frequency_type == "EVERY_X_MONTHS":
        if month_interval is None or month_interval < 2:
            raise ValidationError("El intervalo debe ser de al menos 2 meses.")
        if reference_date is None:
            raise ValidationError("Indica una fecha de referencia para el ciclo.")


def format_periodicity(
    frequency_type: str,
    *,
    weekday: Optional[int] = None,
    week_ordinal: Optional[int] = None,
    month_interval: Optional[int] = None,
) -> str:
    validate_periodicity(
        frequency_type,
        weekday=weekday,
        week_ordinal=week_ordinal,
        month_interval=month_interval,
        reference_date=date.today() if frequency_type == "EVERY_X_MONTHS" else None,
    )
    if frequency_type == "DAILY":
        return "Diario"
    day = WEEKDAYS[weekday]  # type: ignore[index]
    if frequency_type == "WEEKLY":
        return f"Cada {day}"
    ordinal = ORDINALS[week_ordinal - 1]  # type: ignore[index]
    if frequency_type == "MONTHLY":
        return f"{ordinal.capitalize()} {day} de cada mes"
    return f"{ordinal.capitalize()} {day} cada {month_interval} meses"


def create_inspection_plan_entry(
    session: Session,
    *,
    material_type_id: int,
    laboratory_test_id: int,
    responsible: str,
    frequency_type: str,
    weekday: Optional[int] = None,
    week_ordinal: Optional[int] = None,
    month_interval: Optional[int] = None,
    reference_date: Optional[date] = None,
    observations: str = "",
) -> InspectionPlanEntry:
    responsible = responsible.strip()
    if not responsible:
        raise ValidationError("El responsable es obligatorio.")
    applicability = session.scalar(
        select(TestApplicability).where(
            TestApplicability.material_type_id == material_type_id,
            TestApplicability.laboratory_test_id == laboratory_test_id,
        )
    )
    if applicability is None:
        raise ValidationError("El ensayo no aplica al material seleccionado.")
    validate_periodicity(
        frequency_type,
        weekday=weekday,
        week_ordinal=week_ordinal,
        month_interval=month_interval,
        reference_date=reference_date,
    )
    duplicate = session.scalar(
        select(InspectionPlanEntry).where(
            InspectionPlanEntry.material_type_id == material_type_id,
            InspectionPlanEntry.laboratory_test_id == laboratory_test_id,
            InspectionPlanEntry.responsible == responsible,
            InspectionPlanEntry.frequency_type == frequency_type,
            InspectionPlanEntry.weekday == weekday,
            InspectionPlanEntry.week_ordinal == week_ordinal,
            InspectionPlanEntry.month_interval == month_interval,
            InspectionPlanEntry.active.is_(True),
        )
    )
    if duplicate is not None:
        raise ValidationError("Ya existe una entrada activa idéntica en el plan.")
    entry = InspectionPlanEntry(
        material_type_id=material_type_id,
        laboratory_test_id=laboratory_test_id,
        responsible=responsible,
        frequency_type=frequency_type,
        weekday=weekday,
        week_ordinal=week_ordinal,
        month_interval=month_interval,
        reference_date=reference_date,
        observations=observations.strip(),
    )
    session.add(entry)
    session.flush()
    return entry


def list_inspection_plan_entries(session: Session) -> list[InspectionPlanEntry]:
    stmt = (
        select(InspectionPlanEntry)
        .options(
            joinedload(InspectionPlanEntry.material_type),
            joinedload(InspectionPlanEntry.laboratory_test),
        )
        .where(InspectionPlanEntry.active.is_(True))
        .order_by(InspectionPlanEntry.id.desc())
    )
    return list(session.scalars(stmt))


def seed_demo_data(session: Session, today: date) -> None:
    existing = session.scalar(select(func.count()).select_from(ProductionBatch)) or 0
    if existing:
        raise ValidationError("La base ya contiene producción. No se cargaron datos de demostración.")
    products = list_products(session)
    block = next(item for item in products if item.category == "BLOCK")
    flex = next(item for item in products if item.category == "FLEXURE")
    create_production(
        session,
        product_id=block.id,
        production_date=today,
        lot_code="DEMO-BLOQUE",
        ages=[3, 7, 14, 28],
        notes="Producción de demostración",
    )
    create_production(
        session,
        product_id=flex.id,
        production_date=today,
        lot_code="DEMO-FLEX",
        ages=[3, 7, 14, 28],
        notes="Producción de demostración",
    )
