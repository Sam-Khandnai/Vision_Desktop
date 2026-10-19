"""Catalog of popular MCP servers and the logic that turns one catalog entry + user input into a server config."""
from __future__ import annotations

import json
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).parent / "data" / "mcp_catalog.json"


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    return json.loads(DATA.read_text(encoding="utf-8"))


def get(entry_id: str) -> dict[str, Any] | None:
    return next((s for s in load()["servers"] if s["id"] == entry_id), None)


def runtimes() -> dict[str, bool]:
    """Which launchers exist on this machine (used to warn before adding a server that cannot start)."""
    return {"node": shutil.which("npx") is not None, "uv": shutil.which("uvx") is not None}


def loc(value: Any, lang: str = "en") -> str:
    """Catalog texts are {fa, en} dicts (plain strings are accepted too)."""
    if isinstance(value, dict):
        return value.get(lang) or value.get("en") or next(iter(value.values()), "")
    return str(value or "")


def _fill(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def build_server(entry: dict[str, Any], values: dict[str, str]) -> dict[str, Any]:
    """Return kwargs for McpHub.save_server(). Secrets only ever go to env/headers, never to args."""
    values = {k: (v or "").strip() for k, v in (values or {}).items()}
    env: dict[str, str] = dict(entry.get("env_static", {}))
    headers: dict[str, str] = {}
    for inp in entry.get("inputs", []):
        value = values.get(inp["key"]) or inp.get("default", "")
        if not value:
            if inp.get("required", True):
                raise ValueError(f"'{loc(inp['label'])}' is required.")
            continue
        values[inp["key"]] = value
        if inp["target"] == "env":
            env[inp["name"]] = value
        elif inp["target"] == "header":
            headers[inp["name"]] = inp.get("template", "{{value}}").replace("{{value}}", value)
    config: dict[str, Any]
    if entry["transport"] == "stdio":
        config = {"command": entry["command"], "args": [_fill(a, values) for a in entry.get("args", [])]}
    else:
        config = {"url": entry["url"]}
    return {
        "name": entry["name"],
        "transport": entry["transport"],
        "config": config,
        "env": env if entry["transport"] == "stdio" else None,
        "headers": headers if entry["transport"] != "stdio" else None,
        "catalog_id": entry["id"],
    }
