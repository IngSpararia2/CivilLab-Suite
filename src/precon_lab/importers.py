from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .historical_codes import build_production_code, build_test_code, derive_product_code
from .models import (
    HistoricalSpecimen,
    HistoricalTest,
    ImportBatch,
    ProductionBatch,
    SampleSet,
    TestResult,
)


class ImportValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ImportReport:
    test_type: str
    total_rows: int
    imported_rows: int
    duplicate_rows: int
    reconciled_rows: int
    conflict_rows: int
    duplicate_file: bool = False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_summary_type(columns: list[str]) -> str:
    names = set(columns)
    if "f'c Promedio" in names and "Bloque 1 Id. Muestra" in names:
        return "COMPRESSION"
    if "Modulo de Rotura Promedio" in names and "Muestra 1 - Id. Muestra" in names:
        return "FLEXURE"
    raise ImportValidationError(
        "No se reconoció el formato. Se esperaba un resumen de compresión o flexotracción generado por el extractor."
    )


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        missing = pd.isna(value)
        if isinstance(missing, bool):
            return missing
    except (TypeError, ValueError):
        pass
    return False


def _text(value: Any) -> str:
    if _is_empty(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _float(value: Any) -> Optional[float]:
    if _is_empty(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        text = str(value).strip().replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return None


def _date(value: Any) -> Optional[date]:
    if _is_empty(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if 1 <= number <= 100000:
            try:
                return (datetime(1899, 12, 30) + timedelta(days=number)).date()
            except (OverflowError, ValueError):
                return None
    parsed = pd.to_datetime(str(value).strip(), errors="coerce", dayfirst=False)
    if pd.isna(parsed):
        parsed = pd.to_datetime(str(value).strip(), errors="coerce", dayfirst=True)
    return None if pd.isna(parsed) else parsed.date()


def _age(value: Any) -> Optional[int]:
    if _is_empty(value):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return None
    match = re.search(r"(?<!\d)(\d{1,3})\s*[dD]?\b", str(value))
    return int(match.group(1)) if match else None


def _normalized_name(value: str) -> str:
    return " ".join(value.casefold().replace("-", " ").split())


def _json_value(value: Any) -> Any:
    if _is_empty(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return str(value) if not isinstance(value, (str, int, float, bool)) else value


def _row_hash(test_type: str, row: pd.Series) -> str:
    payload = {str(key): _json_value(value) for key, value in sorted(row.items(), key=lambda item: str(item[0]))}
    raw = json.dumps({"type": test_type, "row": payload}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _first_date(row: pd.Series, keys: list[str]) -> Optional[date]:
    for key in keys:
        value = _date(row.get(key))
        if value is not None:
            return value
    return None


def _first_age(row: pd.Series, keys: list[str]) -> Optional[int]:
    for key in keys:
        value = _age(row.get(key))
        if value is not None:
            return value
    return None

def _first_text(row: pd.Series, keys: list[str]) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return ""

def _build_compression(row: pd.Series, row_hash: str, import_batch: ImportBatch) -> HistoricalTest:
    test_date = _date(row.get("fecha de ensayo"))
    production_date = _first_date(
        row,
        [
            "bloque 1 fecha de elaboracion",
            "bloque 2 fecha de elaboracion",
            "bloque 3 fecha de elaboracion",
        ],
    )
    age = _first_age(
        row,
        [
            "bloque 1 edad calculada",
            "bloque 1 edad",
            "bloque 2 edad calculada",
            "bloque 2 edad",
            "bloque 3 edad calculada",
            "bloque 3 edad",
        ],
    )

    # Recupera la fecha de fabricación cuando el Excel solo conserva
    # fecha de ensayo + edad.
    if production_date is None and test_date is not None and age is not None:
        production_date = test_date - timedelta(days=age)

    product_name = _text(row.get("material"))
    source_file = _text(row.get("Nombre del Archivo"))
    source_test_code = _first_text(
        row,
        [
            "Bloque 1 Codigo Item",
            "Bloque 2 Codigo Item",
            "Bloque 3 Codigo Item",
        ],
    )
    specimen_codes = [
        (ordinal, row.get(f"Bloque {ordinal} Id. Muestra"))
        for ordinal in range(1, 4)
    ]
    product_code = derive_product_code(
        specimen_codes,
        source_test_code=source_test_code,
        product_name=product_name,
        source_file=source_file,
    )

    hist = HistoricalTest(
        import_batch=import_batch,
        row_hash=row_hash,
        test_type="COMPRESSION",
        product_code=product_code,
        production_code=build_production_code(product_code, production_date),
        test_code=build_test_code(product_code, age, test_date),
        product_name=product_name,
        production_date=production_date,
        test_date=test_date,
        target_age_days=age,
        report_number=_text(row.get("Numero de Informe")),
        absorption_avg=_float(row.get("Absorcion Promedio")),
        strength_avg=_float(row.get("f'c Promedio")),
        source_file=source_file,
        relative_path=_text(row.get("Ruta relativa")),
        reading_status=_text(row.get("Estado de lectura")),
        incidents=_text(row.get("Incidencias")),
    )

    for ordinal in range(1, 4):
        lower = f"bloque {ordinal}"
        upper = f"Bloque {ordinal}"
        sample_code = _text(row.get(f"{upper} Id. Muestra"))
        material = _text(row.get(f"{upper} Material"))
        strength = _float(row.get(f"{upper} f'c Neta"))
        max_load = _float(row.get(f"{upper} Carga Maxima"))
        if not any([sample_code, material, strength is not None, max_load is not None]):
            continue
        hist.specimens.append(
            HistoricalSpecimen(
                ordinal=ordinal,
                specimen_code=sample_code,
                material=material,
                production_date=_date(row.get(f"{lower} fecha de elaboracion")) or production_date,
                age_days=_age(row.get(f"{lower} edad calculada"))
                or _age(row.get(f"{lower} edad"))
                or age,
                natural_mass=_float(row.get(f"{upper} Masa Natural")),
                dry_mass=_float(row.get(f"{upper} Masa Seca")),
                immersed_mass=_float(row.get(f"{upper} Masa Inmersa")),
                saturated_mass=_float(row.get(f"{upper} Masa Saturada")),
                density=_float(row.get(f"{upper} Densidad")),
                absorption=_float(row.get(f"{upper} Absorcion")),
                maximum_load=max_load,
                strength=strength,
                length=_float(row.get(f"{upper} Longitud")),
                height=_float(row.get(f"{upper} Altura")),
                thickness=_float(row.get(f"{upper} Espesor")),
            )
        )
    return hist


def _build_flexure(row: pd.Series, row_hash: str, import_batch: ImportBatch) -> HistoricalTest:
    test_date = _date(row.get("Fecha de Ensayo"))
    production_date = _first_date(
        row,
        [f"Muestra {ordinal} - Fecha de Elaboracion" for ordinal in range(1, 6)],
    )
    age = _first_age(
        row,
        [f"Muestra {ordinal} - Edad" for ordinal in range(1, 6)],
    )

    if production_date is None and test_date is not None and age is not None:
        production_date = test_date - timedelta(days=age)

    product_name = _text(row.get("Material"))
    source_file = _text(row.get("Nombre del Archivo"))
    source_test_code = _first_text(
        row,
        [f"Muestra {ordinal} - Item 1" for ordinal in range(1, 6)],
    )
    specimen_codes = [
        (ordinal, row.get(f"Muestra {ordinal} - Id. Muestra"))
        for ordinal in range(1, 6)
    ]
    product_code = derive_product_code(
        specimen_codes,
        source_test_code=source_test_code,
        product_name=product_name,
        source_file=source_file,
    )

    hist = HistoricalTest(
        import_batch=import_batch,
        row_hash=row_hash,
        test_type="FLEXURE",
        product_code=product_code,
        production_code=build_production_code(product_code, production_date),
        test_code=build_test_code(product_code, age, test_date),
        product_name=product_name,
        production_date=production_date,
        test_date=test_date,
        target_age_days=age,
        report_number=_first_text(
            row,
            [f"Muestra {ordinal} - No. de Ensayo" for ordinal in range(1, 6)],
        ),
        absorption_avg=_float(row.get("Absorcion Promedio")),
        flexural_avg=_float(row.get("Modulo de Rotura Promedio")),
        source_file=source_file,
        relative_path=_text(row.get("Ruta relativa")),
        reading_status=_text(row.get("Estado de lectura")),
        incidents=_text(row.get("Incidencias")),
    )

    for ordinal in range(1, 6):
        prefix = f"Muestra {ordinal} - "
        sample_code = _text(row.get(prefix + "Id. Muestra"))
        material = _text(row.get(prefix + "Material"))
        modulus = _float(row.get(prefix + "Módulo de rotura máximo"))
        force = _float(row.get(prefix + "Fuerza Máxima"))
        if not any([sample_code, material, modulus is not None, force is not None]):
            continue
        hist.specimens.append(
            HistoricalSpecimen(
                ordinal=ordinal,
                specimen_code=sample_code,
                material=material,
                production_date=_date(row.get(prefix + "Fecha de Elaboracion")) or production_date,
                age_days=_age(row.get(prefix + "Edad")) or age,
                dry_mass=_float(row.get(prefix + "Masa Seca")),
                immersed_mass=_float(row.get(prefix + "Masa Inmersa")),
                saturated_mass=_float(row.get(prefix + "Masa Saturada")),
                density=_float(row.get(prefix + "Densidad")),
                absorption=_float(row.get(prefix + "Absorcion")),
                maximum_load=force,
                flexural_modulus=modulus,
                width=_float(row.get(prefix + "Ancho real del especímen")),
                thickness=_float(row.get(prefix + "Espesor del especímen")),
                length=_float(row.get(prefix + "Longitud rectángulo inscrito")),
            )
        )
    return hist


def _value_conflicts(manual: Optional[float], imported: Optional[float], tolerance: float = 0.05) -> bool:
    return manual is not None and imported is not None and abs(manual - imported) > tolerance


def _try_reconcile(session: Session, hist: HistoricalTest) -> str | None:
    if hist.production_date is None or hist.target_age_days is None:
        return None
    stmt = (
        select(TestResult)
        .join(TestResult.sample_set)
        .join(SampleSet.batch)
        .join(ProductionBatch.product)
        .options(
            joinedload(TestResult.sample_set)
            .joinedload(SampleSet.batch)
            .joinedload(ProductionBatch.product)
        )
        .where(
            TestResult.test_type == hist.test_type,
            ProductionBatch.production_date == hist.production_date,
            SampleSet.target_age_days == hist.target_age_days,
            TestResult.imported_test_id.is_(None),
        )
    )
    candidates = list(session.scalars(stmt).unique())
    hist_name = _normalized_name(hist.product_name)
    if hist_name:
        candidates = [
            item
            for item in candidates
            if hist_name
            in {
                _normalized_name(item.sample_set.batch.product.name),
                _normalized_name(item.sample_set.batch.product.code),
            }
        ]
    if len(candidates) != 1:
        return None
    result = candidates[0]
    conflict = False
    conflict |= _value_conflicts(result.absorption_avg, hist.absorption_avg)
    if hist.test_type == "COMPRESSION":
        conflict |= _value_conflicts(result.strength_avg, hist.strength_avg)
    else:
        conflict |= _value_conflicts(result.flexural_avg, hist.flexural_avg)

    if result.absorption_avg is None:
        result.absorption_avg = hist.absorption_avg
    if result.strength_avg is None:
        result.strength_avg = hist.strength_avg
    if result.flexural_avg is None:
        result.flexural_avg = hist.flexural_avg
    if result.test_date is None and hist.test_date is not None:
        result.test_date = hist.test_date
    result.imported_test = hist
    result.source = "MANUAL+IMPORT"
    result.status = "CONFLICT" if conflict else "CONCILIATED"
    return result.status


def import_summary_file(session: Session, file_path: str | Path) -> ImportReport:
    path = Path(file_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise ImportValidationError("El archivo seleccionado no existe.")
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ImportValidationError("El prototipo admite archivos .xlsx o .xlsm.")

    file_hash = sha256_file(path)
    existing = session.scalar(select(ImportBatch).where(ImportBatch.file_hash == file_hash))
    if existing is not None:
        return ImportReport(
            test_type=existing.test_type,
            total_rows=existing.row_count,
            imported_rows=existing.imported_count,
            duplicate_rows=existing.duplicate_count,
            reconciled_rows=existing.reconciled_count,
            conflict_rows=0,
            duplicate_file=True,
        )

    dataframe = pd.read_excel(path, sheet_name="Resumen")
    test_type = detect_summary_type([str(column) for column in dataframe.columns])
    import_batch = ImportBatch(
        file_hash=file_hash,
        file_name=path.name,
        file_path=str(path),
        test_type=test_type,
        row_count=len(dataframe),
    )
    session.add(import_batch)
    session.flush()

    imported = duplicates = reconciled = conflicts = 0
    builder = _build_compression if test_type == "COMPRESSION" else _build_flexure
    for _, row in dataframe.iterrows():
        row_hash = _row_hash(test_type, row)
        if session.scalar(select(HistoricalTest.id).where(HistoricalTest.row_hash == row_hash)) is not None:
            duplicates += 1
            continue
        hist = builder(row, row_hash, import_batch)
        session.add(hist)
        session.flush()
        imported += 1
        status = _try_reconcile(session, hist)
        if status == "CONCILIATED":
            reconciled += 1
        elif status == "CONFLICT":
            reconciled += 1
            conflicts += 1

    import_batch.imported_count = imported
    import_batch.duplicate_count = duplicates
    import_batch.reconciled_count = reconciled
    import_batch.status = "COMPLETED"
    session.flush()
    return ImportReport(
        test_type=test_type,
        total_rows=len(dataframe),
        imported_rows=imported,
        duplicate_rows=duplicates,
        reconciled_rows=reconciled,
        conflict_rows=conflicts,
    )
