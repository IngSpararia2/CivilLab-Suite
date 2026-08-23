from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "Concretos Lab"
APP_VERSION = "0.9.1"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets" / "concretos"
APP_ICON_PATH = ASSETS_DIR / "app_icon.png"
APP_ICON_PNG_PATH = ASSETS_DIR / "app_icon.png"
SIDEBAR_LOGO_PATH = ASSETS_DIR / "sidebar_logo.png"


def user_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    # Keep the historical directory name so an update to Concretos Lab does
    # not make existing materials, designs or laboratory records disappear.
    return base / "ConcreteMixDesignerACI"


# The existing materials table and the new design/production/laboratory tables
# share one local SQLite database. Existing installations are upgraded in place.
DATABASE_PATH = user_data_dir() / "materials.sqlite3"
