from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "CivilLab Suite"
APP_VERSION = "0.1.0"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets"
SUITE_ASSETS_DIR = ASSETS_DIR / "suite"
LEGACY_DATA_DIR = PROJECT_ROOT / "data" / "legacy"


def suite_data_dir() -> Path:
    configured = os.getenv("CIVILLAB_SUITE_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "CivilLabSuite"


def core_database_path() -> Path:
    return suite_data_dir() / "core.sqlite3"
