from __future__ import annotations

import re
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Iterable

_DATE_SUFFIX_PATTERNS = (
    re.compile(r"(?:-|^)(\d{8})$"),
    re.compile(r"(?:-|^)(\d{6})$"),
    re.compile(r"(?:-|^)(\d{4})$"),
)
_AGE_SUFFIX_RE = re.compile(r"(?:-|^)(\d{1,3})D$", re.IGNORECASE)


def normalize_code(value: object) -> str:
    """Normalize a code without changing its semantic tokens."""
    if value is None:
        return ""

    text = str(value).strip().upper()
    if not text:
        return ""

    text = Path(text).name
    text = re.sub(r"\.(XLSX|XLSM|XLS)$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\([^)]*\)$", "", text).strip()

    text = unicodedata.normalize("NFKD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = re.sub(r"[\s_/]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def _strip_trailing_date(code: str) -> str:
    for pattern in _DATE_SUFFIX_PATTERNS:
        match = pattern.search(code)
        if match:
            return code[: match.start(1)].rstrip("-")
    return code


def product_candidate(value: object, specimen_ordinal: int | None = None) -> str:
    """
    Remove suffixes that represent specimen number, date and test age.

    Examples:
    - M12L-DIV-0105 -> M12L-DIV
    - M12L-DIV-14D-0120 -> M12L-DIV
    - M12L-DIV-14D-16042026 -> M12L-DIV
    - 20260416 style dates are also removed when they are the final token.
    """
    code = normalize_code(value)
    if not code:
        return ""

    if specimen_ordinal is not None:
        code = re.sub(rf"-{specimen_ordinal}$", "", code)

    code = _strip_trailing_date(code)
    code = _AGE_SUFFIX_RE.sub("", code).rstrip("-")
    code = _strip_trailing_date(code)
    return code.strip("-")


def derive_product_code(
    specimen_codes: Iterable[tuple[int, object]],
    *,
    source_test_code: object = "",
    product_name: object = "",
    source_file: object = "",
) -> str:
    """Return the most reliable normalized product code available."""
    candidates: list[str] = []

    for ordinal, value in specimen_codes:
        candidate = product_candidate(value, ordinal)
        if candidate:
            candidates.append(candidate)

    if candidates:
        counts = Counter(candidates)
        return max(counts, key=lambda item: (counts[item], len(item)))

    for value in (source_test_code, source_file, product_name):
        candidate = product_candidate(value)
        if candidate:
            return candidate

    return "SIN-CODIGO"


def build_production_code(product_code: str, production_date: date | None) -> str:
    normalized = normalize_code(product_code) or "SIN-CODIGO"
    if production_date is None:
        return f"{normalized}-SIN-FECHA"
    return f"{normalized}-{production_date:%d%m%Y}"


def build_test_code(
    product_code: str,
    target_age_days: int | None,
    test_date: date | None,
) -> str:
    normalized = normalize_code(product_code) or "SIN-CODIGO"
    age_text = f"{target_age_days}D" if target_age_days is not None else "SIN-EDAD"
    date_text = f"{test_date:%d%m%Y}" if test_date is not None else "SIN-FECHA"
    return f"{normalized}-{age_text}-{date_text}"
