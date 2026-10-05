from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "prefabricados_products"
    __table_args__ = (UniqueConstraint("name", "code", name="uq_product_name_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(30), nullable=False)  # BLOCK / FLEXURE
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    batches: Mapped[list["ProductionBatch"]] = relationship(back_populates="product")

    @property
    def display_name(self) -> str:
        return f"{self.code} — {self.name}" if self.code else self.name


class ProductionBatch(Base):
    __tablename__ = "prefabricados_production_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("prefabricados_products.id"), nullable=False)
    production_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    lot_code: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    quantity_produced: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    product: Mapped[Product] = relationship(back_populates="batches")
    sample_sets: Mapped[list["SampleSet"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class SampleSet(Base):
    __tablename__ = "prefabricados_sample_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("prefabricados_production_batches.id"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)  # ABSORPTION / COMPRESSION / FLEXURE
    target_age_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    planned_test_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    specimen_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PLANNED")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    batch: Mapped[ProductionBatch] = relationship(back_populates="sample_sets")
    specimens: Mapped[list["Specimen"]] = relationship(
        back_populates="sample_set", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["WorkflowTask"]] = relationship(
        back_populates="sample_set", cascade="all, delete-orphan"
    )
    result: Mapped[Optional["TestResult"]] = relationship(
        back_populates="sample_set", cascade="all, delete-orphan", uselist=False
    )

    @property
    def label(self) -> str:
        age = f" — {self.target_age_days} días" if self.target_age_days is not None else ""
        return f"{self.purpose}{age} ({self.specimen_count} unidades)"


class Specimen(Base):
    __tablename__ = "prefabricados_specimens"
    __table_args__ = (UniqueConstraint("sample_set_id", "ordinal", name="uq_specimen_ordinal"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sample_set_id: Mapped[int] = mapped_column(ForeignKey("prefabricados_sample_sets.id"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    specimen_code: Mapped[str] = mapped_column(String(120), nullable=False)
    current_state: Mapped[str] = mapped_column(String(40), nullable=False, default="REGISTERED")
    disposition: Mapped[str] = mapped_column(String(40), nullable=False, default="PENDING")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    sample_set: Mapped[SampleSet] = relationship(back_populates="specimens")


class WorkflowTask(Base):
    __tablename__ = "prefabricados_workflow_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    sample_set_id: Mapped[int] = mapped_column(ForeignKey("prefabricados_sample_sets.id"), nullable=False)
    task_type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(260), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    original_scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    sample_set: Mapped[SampleSet] = relationship(back_populates="tasks")


class ImportBatch(Base):
    __tablename__ = "prefabricados_import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    test_type: Mapped[str] = mapped_column(String(30), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reconciled_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="STARTED")
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    historical_tests: Mapped[list["HistoricalTest"]] = relationship(
        back_populates="import_batch", cascade="all, delete-orphan"
    )


class HistoricalTest(Base):
    __tablename__ = "prefabricados_historical_tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("prefabricados_import_batches.id"), nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    test_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    product_code: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
        default="",
        index=True,
    )

    production_code: Mapped[str] = mapped_column(
        String(220),
        nullable=False,
        default="",
        index=True,
    )

    test_code: Mapped[str] = mapped_column(
        String(220),
        nullable=False,
        default="",
        index=True,
    )

    product_name: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
        default="",
    )
    production_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    test_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    target_age_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    report_number: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    absorption_avg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    strength_avg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    flexural_avg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    abrasion_avg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    relative_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reading_status: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    incidents: Mapped[str] = mapped_column(Text, nullable=False, default="")

    import_batch: Mapped[ImportBatch] = relationship(back_populates="historical_tests")
    specimens: Mapped[list["HistoricalSpecimen"]] = relationship(
        back_populates="historical_test", cascade="all, delete-orphan"
    )
    linked_result: Mapped[Optional["TestResult"]] = relationship(back_populates="imported_test")


class HistoricalSpecimen(Base):
    __tablename__ = "prefabricados_historical_specimens"
    __table_args__ = (UniqueConstraint("historical_test_id", "ordinal", name="uq_hist_spec_ordinal"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    historical_test_id: Mapped[int] = mapped_column(ForeignKey("prefabricados_historical_tests.id"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    specimen_code: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    material: Mapped[str] = mapped_column(String(180), nullable=False, default="")
    production_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    age_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    natural_mass: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dry_mass: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    immersed_mass: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    saturated_mass: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    density: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    absorption: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    maximum_load: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    strength: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    flexural_modulus: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    length: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    width: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    height: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    thickness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    historical_test: Mapped[HistoricalTest] = relationship(back_populates="specimens")


class TestResult(Base):
    __tablename__ = "prefabricados_test_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    sample_set_id: Mapped[int] = mapped_column(ForeignKey("prefabricados_sample_sets.id"), nullable=False, unique=True)
    imported_test_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("prefabricados_historical_tests.id"), nullable=True, unique=True
    )
    test_type: Mapped[str] = mapped_column(String(30), nullable=False)
    test_date: Mapped[date] = mapped_column(Date, nullable=False)
    absorption_avg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    strength_avg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    flexural_avg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    abrasion_avg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PROVISIONAL")
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="MANUAL")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    sample_set: Mapped[SampleSet] = relationship(back_populates="result")
    imported_test: Mapped[Optional[HistoricalTest]] = relationship(back_populates="linked_result")


class MaterialType(Base):
    __tablename__ = "prefabricados_material_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)

    test_applicabilities: Mapped[list["TestApplicability"]] = relationship(
        back_populates="material_type", cascade="all, delete-orphan"
    )
    inspection_plan_entries: Mapped[list["InspectionPlanEntry"]] = relationship(
        back_populates="material_type"
    )


class StandardReference(Base):
    __tablename__ = "prefabricados_standard_references"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    issuer: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    edition: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    source_reference: Mapped[str] = mapped_column(Text, nullable=False, default="")
    location_reference: Mapped[str] = mapped_column(String(180), nullable=False, default="")
    verification_status: Mapped[str] = mapped_column(String(40), nullable=False)


class LaboratoryTest(Base):
    __tablename__ = "prefabricados_laboratory_tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(220), nullable=False)
    standard_id: Mapped[Optional[int]] = mapped_column(ForeignKey("prefabricados_standard_references.id"), nullable=True)
    equipment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    procedure_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    active: Mapped[bool] = mapped_column(default=True, nullable=False)

    standard: Mapped[Optional[StandardReference]] = relationship()
    applicabilities: Mapped[list["TestApplicability"]] = relationship(
        back_populates="laboratory_test", cascade="all, delete-orphan"
    )
    requirements: Mapped[list["TestRequirement"]] = relationship(
        back_populates="laboratory_test", cascade="all, delete-orphan"
    )
    inspection_plan_entries: Mapped[list["InspectionPlanEntry"]] = relationship(
        back_populates="laboratory_test"
    )


class TestApplicability(Base):
    __tablename__ = "prefabricados_test_applicabilities"
    __table_args__ = (
        UniqueConstraint("material_type_id", "laboratory_test_id", name="uq_test_applicability"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    material_type_id: Mapped[int] = mapped_column(ForeignKey("prefabricados_material_types.id"), nullable=False)
    laboratory_test_id: Mapped[int] = mapped_column(ForeignKey("prefabricados_laboratory_tests.id"), nullable=False)
    standard_id: Mapped[Optional[int]] = mapped_column(ForeignKey("prefabricados_standard_references.id"), nullable=True)
    normative_frequency: Mapped[str] = mapped_column(String(180), nullable=False, default="")
    procedure_detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    preferred: Mapped[bool] = mapped_column(default=False, nullable=False)

    material_type: Mapped[MaterialType] = relationship(back_populates="test_applicabilities")
    laboratory_test: Mapped[LaboratoryTest] = relationship(back_populates="applicabilities")
    standard: Mapped[Optional[StandardReference]] = relationship()


class TestRequirement(Base):
    __tablename__ = "prefabricados_test_requirements"
    __table_args__ = (UniqueConstraint("seed_key", name="uq_test_requirement_seed_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    seed_key: Mapped[str] = mapped_column(String(180), nullable=False)
    material_type_id: Mapped[int] = mapped_column(ForeignKey("prefabricados_material_types.id"), nullable=False)
    laboratory_test_id: Mapped[int] = mapped_column(ForeignKey("prefabricados_laboratory_tests.id"), nullable=False)
    standard_id: Mapped[Optional[int]] = mapped_column(ForeignKey("prefabricados_standard_references.id"), nullable=True)
    minimum: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    maximum: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    operator: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    condition: Mapped[str] = mapped_column(String(260), nullable=False, default="")
    aggregation: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    age_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    grading: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    source_detail: Mapped[str] = mapped_column(String(220), nullable=False, default="")
    verification_status: Mapped[str] = mapped_column(String(40), nullable=False)

    material_type: Mapped[MaterialType] = relationship()
    laboratory_test: Mapped[LaboratoryTest] = relationship(back_populates="requirements")
    standard: Mapped[Optional[StandardReference]] = relationship()


class InspectionPlanEntry(Base):
    __tablename__ = "prefabricados_inspection_plan_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    material_type_id: Mapped[int] = mapped_column(ForeignKey("prefabricados_material_types.id"), nullable=False)
    laboratory_test_id: Mapped[int] = mapped_column(ForeignKey("prefabricados_laboratory_tests.id"), nullable=False)
    responsible: Mapped[str] = mapped_column(String(180), nullable=False)
    frequency_type: Mapped[str] = mapped_column(String(30), nullable=False)
    weekday: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    week_ordinal: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    month_interval: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reference_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    observations: Mapped[str] = mapped_column(Text, nullable=False, default="")
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    material_type: Mapped[MaterialType] = relationship(back_populates="inspection_plan_entries")
    laboratory_test: Mapped[LaboratoryTest] = relationship(back_populates="inspection_plan_entries")
