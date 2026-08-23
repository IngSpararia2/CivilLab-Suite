from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Prefabricados Lab"
APP_VERSION = "0.1.0"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets" / "prefabricados"
APP_ICON_PATH = ASSETS_DIR / "app_icon.png"
APP_ICON_PNG_PATH = ASSETS_DIR / "app_icon.png"
BRAND_SOURCE_PATH = ASSETS_DIR / "brand_source.png"


def data_dir() -> Path:
    configured = os.getenv("PRECON_LAB_DATA_DIR")
    path = Path(configured).expanduser() if configured else Path.home() / "PreconLabData"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return data_dir() / "precon_lab.db"


def database_url() -> str:
    return f"sqlite:///{database_path().as_posix()}"
