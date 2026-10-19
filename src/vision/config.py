from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Vision"


def data_dir() -> Path:
    """Where Vision keeps its local database. Everything stays on this machine."""
    override = os.environ.get("VISION_DATA_DIR")
    if override:
        path = Path(override)
    elif sys.platform == "win32":
        path = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        path = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME.lower()
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "vision.db"


def api_token() -> str:
    """Per-launch secret shared by Electron and the backend. Empty = dev mode (no auth)."""
    return os.environ.get("VISION_TOKEN", "")
