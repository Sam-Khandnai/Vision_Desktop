"""Secret storage: OS keychain first (Windows Credential Manager / macOS Keychain / Secret Service).

If no keychain backend exists, fall back to a user-only file in the data directory.
API keys and MCP credentials never go into the SQLite database.
"""
from __future__ import annotations

import json
import logging
import os
import threading

from . import config

logger = logging.getLogger(__name__)
SERVICE = "Vision"
_lock = threading.Lock()


def _keyring():
    try:
        import keyring
        from keyring.backends import fail

        backend = keyring.get_keyring()
        if isinstance(backend, fail.Keyring):
            return None
        return keyring
    except Exception:  # pragma: no cover - defensive
        return None


def _file_path():
    return config.data_dir() / "secrets.json"


def _read_file() -> dict[str, str]:
    path = _file_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_file(data: dict[str, str]) -> None:
    path = _file_path()
    path.write_text(json.dumps(data), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def backend_name() -> str:
    kr = _keyring()
    return "os-keychain" if kr else "local-file"


def set_secret(key: str, value: str) -> None:
    with _lock:
        kr = _keyring()
        if kr:
            try:
                kr.set_password(SERVICE, key, value)
                return
            except Exception:
                logger.warning("Keychain write failed; using local file fallback", exc_info=True)
        data = _read_file()
        data[key] = value
        _write_file(data)


def get_secret(key: str) -> str:
    with _lock:
        kr = _keyring()
        if kr:
            try:
                value = kr.get_password(SERVICE, key)
                if value is not None:
                    return value
            except Exception:
                logger.warning("Keychain read failed; trying local file", exc_info=True)
        return _read_file().get(key, "")


def delete_secret(key: str) -> None:
    with _lock:
        kr = _keyring()
        if kr:
            try:
                kr.delete_password(SERVICE, key)
            except Exception:
                pass
        data = _read_file()
        if key in data:
            del data[key]
            _write_file(data)
