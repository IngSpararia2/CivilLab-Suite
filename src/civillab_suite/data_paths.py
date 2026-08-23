from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

from .config import LEGACY_DATA_DIR, suite_data_dir


def _is_sqlite_database(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        connection.execute("PRAGMA schema_version").fetchone()
        connection.close()
    except sqlite3.Error:
        return False
    return True


def prepare_prefabricados_data() -> Path:
    """Select a stable suite path and copy legacy data only when no target exists."""

    configured = os.getenv("PRECON_LAB_DATA_DIR")
    if configured:
        directory = Path(configured).expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        return directory / "precon_lab.db"

    target_directory = suite_data_dir() / "prefabricados"
    target_directory.mkdir(parents=True, exist_ok=True)
    target = target_directory / "precon_lab.db"

    if not target.exists():
        candidates = (
            Path.home() / "PreconLabData" / "precon_lab.db",
            LEGACY_DATA_DIR / "prefabricados" / "precon_lab.db",
        )
        source = next((item for item in candidates if _is_sqlite_database(item)), None)
        if source is not None:
            shutil.copy2(source, target)

    os.environ["PRECON_LAB_DATA_DIR"] = str(target_directory)
    return target
