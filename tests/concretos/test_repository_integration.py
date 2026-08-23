from pathlib import Path

from concrete_mix_designer.config import APP_NAME, APP_VERSION


ROOT = Path(__file__).resolve().parents[2]


def test_active_files_expose_current_brand_and_navigation():
    main = (ROOT / "src/concrete_mix_designer/ui/main_window.py").read_text(
        encoding="utf-8"
    )
    library = (
        ROOT / "src/concrete_mix_designer/ui/pages/design_library_page.py"
    ).read_text(encoding="utf-8")

    version = tuple(int(part) for part in APP_VERSION.split("."))
    assert version >= (0, 9, 1)
    assert APP_NAME == "Concretos Lab"
    assert "LaboratoryCalendarPage" in main
    assert '(self.calendar_page, "Calendario", "6 · Calendario de laboratorio")' in main
    assert "library_splitter = QSplitter" in library
    assert "QTableWidget(0, 5)" in library


def test_repository_package_has_no_legacy_update_artifacts():
    assert not list(ROOT.glob(".patch-backup-v*"))
    assert not (ROOT / "patch_runtime.py").exists()
    assert not (ROOT / "test-results.txt").exists()
