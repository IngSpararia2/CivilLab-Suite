from __future__ import annotations

from pathlib import Path

from concrete_mix_designer.services.pdf_report import ensure_unique_path
from concrete_mix_designer.services.report_preferences import (
    ReportPreferences,
    ReportPreferencesStore,
)


def test_report_preferences_and_logo_are_persistent(tmp_path: Path) -> None:
    source_logo = tmp_path / "source.png"
    source_logo.write_bytes(b"not-a-real-image-but-valid-for-copy-test")

    store = ReportPreferencesStore(tmp_path / "app-data")
    copied_logo = store.import_logo(source_logo)
    saved = store.save(
        ReportPreferences(
            logo_path=copied_logo,
            letterhead_text="Empresa de concreto",
            footer_text="Código F-LAB-001",
        )
    )

    loaded = store.load()
    assert loaded == saved
    assert Path(loaded.logo_path).exists()
    assert Path(loaded.logo_path).parent == tmp_path / "app-data"

    store.remove_logo()
    store.save(ReportPreferences(letterhead_text="Empresa de concreto", footer_text="Pie"))
    assert store.load().logo_path == ""


def test_pdf_path_uses_counter_instead_of_overwriting(tmp_path: Path) -> None:
    original = tmp_path / "reporte.pdf"
    original.write_bytes(b"first")
    (tmp_path / "reporte_001.pdf").write_bytes(b"second")

    assert ensure_unique_path(original) == tmp_path / "reporte_002.pdf"
    assert ensure_unique_path(tmp_path / "nuevo") == tmp_path / "nuevo.pdf"
