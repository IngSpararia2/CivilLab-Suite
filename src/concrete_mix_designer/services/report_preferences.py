from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from concrete_mix_designer.config import user_data_dir

SUPPORTED_LOGO_SUFFIXES = {".png", ".jpg", ".jpeg"}


@dataclass(slots=True)
class ReportPreferences:
    logo_path: str = ""
    letterhead_text: str = ""
    footer_text: str = (
        "Aplicación desarrollada por Ing. Samuel Parariá - Derechos reservados."
    )


class ReportPreferencesStore:
    """Persist report branding outside the source tree.

    A selected logo is copied into the application's local data directory so
    the PDF configuration remains valid even if the original image is moved.
    """

    def __init__(self, data_directory: Path | None = None):
        self.data_directory = Path(data_directory or user_data_dir())
        self.preferences_path = self.data_directory / "report_preferences.json"

    def load(self) -> ReportPreferences:
        if not self.preferences_path.exists():
            return ReportPreferences()
        try:
            payload = json.loads(self.preferences_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return ReportPreferences()
        if not isinstance(payload, dict):
            return ReportPreferences()

        preferences = ReportPreferences(
            logo_path=str(payload.get("logo_path", "") or ""),
            letterhead_text=str(payload.get("letterhead_text", "") or ""),
            footer_text=str(
                payload.get("footer_text", ReportPreferences().footer_text) or ""
            ),
        )
        if preferences.logo_path and not Path(preferences.logo_path).exists():
            preferences.logo_path = ""
        return preferences

    def save(self, preferences: ReportPreferences) -> ReportPreferences:
        self.data_directory.mkdir(parents=True, exist_ok=True)
        normalized = ReportPreferences(
            logo_path=str(preferences.logo_path or "").strip(),
            letterhead_text=str(preferences.letterhead_text or "").strip(),
            footer_text=str(preferences.footer_text or "").strip(),
        )
        self.preferences_path.write_text(
            json.dumps(asdict(normalized), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return normalized

    def import_logo(self, source_path: Path) -> str:
        source_path = Path(source_path)
        suffix = source_path.suffix.lower()
        if suffix not in SUPPORTED_LOGO_SUFFIXES:
            raise ValueError("El logo debe estar en formato PNG, JPG o JPEG.")
        if not source_path.is_file():
            raise ValueError("No se encontró el archivo de logo seleccionado.")

        self.data_directory.mkdir(parents=True, exist_ok=True)
        for existing in self.data_directory.glob("report_logo.*"):
            try:
                existing.unlink()
            except OSError:
                pass

        destination = self.data_directory / f"report_logo{suffix}"
        shutil.copy2(source_path, destination)
        return str(destination)

    def remove_logo(self) -> None:
        for existing in self.data_directory.glob("report_logo.*"):
            try:
                existing.unlink()
            except OSError:
                pass
