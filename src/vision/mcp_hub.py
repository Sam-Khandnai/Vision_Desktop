"""MCP server registry + connection hub.

Adapted from the original mcp_manager.py. Differences:
  * each server connects independently, so one broken server never blocks the others;
  * per-server status is tracked for the UI;
  * env vars / HTTP headers (secrets) live in the OS keychain, not in SQLite.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from . import approvals, db, secrets_store

logger = logging.getLogger(__name__)
CONNECT_TIMEOUT = 120.0  # first `npx` run may download the package
APPROVAL_MODES = ("smart", "always", "never")


def parse_json_object(value: str, field_name: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name} must be a JSON object.")
    return parsed


def validate_config(name: str, transport: str, config: dict[str, Any], secret: dict[str, Any]) -> None:
    if not name.strip():
        raise ValueError("Every MCP server needs a name.")
    if transport == "stdio":
        command = str(config.get("command", "")).strip()
        args = config.get("args", [])
        if not command:
            raise ValueError(f"MCP server '{name}' needs a command.")
        if not isinstance(args, list) or not all(isinstance(x, str) for x in args):
            raise ValueError(f"Arguments for '{name}' must be a list of strings.")
        if not isinstance(secret.get("env", {}), dict):
            raise ValueError(f"Environment for '{name}' must be an object.")
    elif transport in ("streamable_http", "sse"):
        url = str(config.get("url", "")).strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"MCP server '{name}' needs a valid HTTP(S) URL.")
        if not isinstance(secret.get("headers", {}), dict):
            raise ValueError(f"Headers for '{name}' must be an object.")
    else:
        raise ValueError(f"Unsupported transport '{transport}'. Use stdio, streamable_http, or sse.")


def _secret_key(server_id: str) -> str:
    return f"mcp:{server_id}"


def _load_secret(server_id: str) -> dict[str, Any]:
    raw = secrets_store.get_secret(_secret_key(server_id))
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {}
    return data if isinstance(data, dict) else {}


def build_connection(row: dict[str, Any]) -> dict[str, Any]:
    config = json.loads(row["config_json"] or "{}")
    secret = _load_secret(row["id"])
    if row["transport"] == "stdio":
        conn: dict[str, Any] = {
            "transport": "stdio",
            "command": config["command"],
            "args": config.get("args", []),
        }
        env = secret.get("env") or {}
        if env:
            conn["env"] = env
        return conn
    conn = {"transport": row["transport"], "url": config["url"]}
    headers = secret.get("headers") or {}
    if headers:
        conn["headers"] = headers
    return conn


def _public(row: dict[str, Any]) -> dict[str, Any]:
    config = json.loads(row["config_json"] or "{}")
    secret = _load_secret(row["id"])
    return {
        "id": row["id"],
        "name": row["name"],
        "transport": row["transport"],
        "command": config.get("command", ""),
        "args": config.get("args", []),
        "url": config.get("url", ""),
        "enabled": bool(row["enabled"]),
        "approval": row["approval"],
        "catalog_id": row["catalog_id"],
        "env_keys": sorted((secret.get("env") or {}).keys()),
        "header_keys": sorted((secret.get("headers") or {}).keys()),
    }


class McpHub:
    def __init__(self) -> None:
        self._tools: dict[str, list[BaseTool]] = {}
        self._status: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self) -> None:
        """Remember the server's event loop: sync (threadpool) endpoints schedule connections onto it."""
        self._loop = asyncio.get_running_loop()

    # ---- registry (SQLite) ----
    def list_servers(self) -> list[dict[str, Any]]:
        with db.connect() as conn:
            rows = [dict(r) for r in conn.execute("SELECT * FROM mcp_servers ORDER BY name COLLATE NOCASE")]
        out = []
        for row in rows:
            item = _public(row)
            item["status"] = self._status.get(row["id"]) or {
                "state": "idle" if row["enabled"] else "disabled",
                "message": "",
                "tool_count": 0,
                "tools": [],
            }
            out.append(item)
        return out

    def get_row(self, server_id: str) -> dict[str, Any] | None:
        with db.connect() as conn:
            row = conn.execute("SELECT * FROM mcp_servers WHERE id=?", (server_id,)).fetchone()
        return dict(row) if row else None

    def save_server(
        self,
        *,
        server_id: str | None,
        name: str,
        transport: str,
        config: dict[str, Any],
        env: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        approval: str = "smart",
        catalog_id: str = "",
        keep_secrets: bool = False,
    ) -> dict[str, Any]:
        name = name.strip()
        if approval not in APPROVAL_MODES:
            raise ValueError(f"approval must be one of {APPROVAL_MODES}")
        existing_secret = _load_secret(server_id) if (server_id and keep_secrets) else {}
        secret = {
            "env": env if env is not None else existing_secret.get("env", {}),
            "headers": headers if headers is not None else existing_secret.get("headers", {}),
        }
        validate_config(name, transport, config, secret)
        with db.connect() as conn:
            dup = conn.execute(
                "SELECT id FROM mcp_servers WHERE name=? AND id<>?", (name, server_id or "")
            ).fetchone()
            if dup:
                raise ValueError(f"Duplicate MCP server name: {name}")
            if server_id:
                conn.execute(
                    "UPDATE mcp_servers SET name=?, transport=?, config_json=?, approval=? WHERE id=?",
                    (name, transport, json.dumps(config), approval, server_id),
                )
            else:
                server_id = db.new_id()
                conn.execute(
                    "INSERT INTO mcp_servers(id, name, transport, config_json, enabled, approval, catalog_id) "
                    "VALUES(?,?,?,?,1,?,?)",
                    (server_id, name, transport, json.dumps(config), approval, catalog_id),
                )
        secrets_store.set_secret(_secret_key(server_id), json.dumps(secret))
        self._tools.pop(server_id, None)
        self._status.pop(server_id, None)
        return _public(self.get_row(server_id))

    def delete_server(self, server_id: str) -> None:
        self.disconnect(server_id)
        with db.connect() as conn:
            conn.execute("DELETE FROM mcp_servers WHERE id=?", (server_id,))
        secrets_store.delete_secret(_secret_key(server_id))

    def set_enabled(self, server_id: str, enabled: bool) -> None:
        with db.connect() as conn:
            conn.execute("UPDATE mcp_servers SET enabled=? WHERE id=?", (1 if enabled else 0, server_id))
        if not enabled:
            self.disconnect(server_id)

    def set_approval(self, server_id: str, approval: str) -> None:
        if approval not in APPROVAL_MODES:
            raise ValueError(f"approval must be one of {APPROVAL_MODES}")
        with db.connect() as conn:
            conn.execute("UPDATE mcp_servers SET approval=? WHERE id=?", (approval, server_id))

    # ---- connections ----
    def disconnect(self, server_id: str) -> None:
        task = self._tasks.pop(server_id, None)
        if task and not task.done():
            if self._loop is not None:
                self._loop.call_soon_threadsafe(task.cancel)
            else:
                task.cancel()
        self._tools.pop(server_id, None)
        self._status.pop(server_id, None)

    async def connect(self, server_id: str) -> dict[str, Any]:
        row = self.get_row(server_id)
        if row is None:
            raise KeyError(server_id)
        if not row["enabled"]:
            self._status[server_id] = {"state": "disabled", "message": "", "tool_count": 0, "tools": []}
            return self._status[server_id]
        self._status[server_id] = {"state": "connecting", "message": "", "tool_count": 0, "tools": []}
        try:
            client = MultiServerMCPClient({row["name"]: build_connection(row)})
            tools = await asyncio.wait_for(client.get_tools(), CONNECT_TIMEOUT)
            self._tools[server_id] = list(tools)
            self._status[server_id] = {
                "state": "connected",
                "message": "",
                "tool_count": len(tools),
                "tools": [t.name for t in tools],
            }
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # ExceptionGroup from anyio TaskGroup is a BaseException subclass
            self._tools.pop(server_id, None)
            logger.warning("MCP server '%s' failed to connect", row["name"], exc_info=True)
            self._status[server_id] = {
                "state": "error",
                "message": _explain(exc),
                "tool_count": 0,
                "tools": [],
            }
        return self._status[server_id]

    def connect_in_background(self, server_id: str) -> None:
        loop = self._loop or asyncio.get_running_loop()

        def start() -> None:
            old = self._tasks.get(server_id)
            if old and not old.done():
                old.cancel()
            self._tasks[server_id] = loop.create_task(self.connect(server_id))

        loop.call_soon_threadsafe(start)

    def connect_all_in_background(self) -> None:
        for server in self.list_servers():
            if server["enabled"]:
                self.connect_in_background(server["id"])

    # ---- tools for the agent ----
    def get_tools(self) -> list[BaseTool]:
        entries: list[tuple[dict[str, Any], BaseTool]] = []
        with db.connect() as conn:
            rows = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM mcp_servers WHERE enabled=1")}
        for server_id, tools in self._tools.items():
            row = rows.get(server_id)
            if row:
                entries.extend((row, t) for t in tools)
        counts: dict[str, int] = {}
        for _, tool in entries:
            counts[tool.name] = counts.get(tool.name, 0) + 1
        wrapped: list[BaseTool] = []
        for row, tool in entries:
            name = tool.name
            if counts[name] > 1:  # keep names unique across servers
                slug = re.sub(r"[^A-Za-z0-9_-]+", "_", row["name"]).strip("_") or "server"
                name = f"{slug}__{tool.name}"[:64]
            wrapped.append(approvals.wrap_tool(tool, server=row["name"], mode=row["approval"], public_name=name))
        return wrapped

    def tool_names(self) -> list[str]:
        return [t.name for t in self.get_tools()]


def _explain(exc: BaseException) -> str:
    """Flatten (possibly nested) exception groups into one readable line."""
    if isinstance(exc, BaseExceptionGroup):
        parts = [_explain(e) for e in exc.exceptions]
        return "; ".join(dict.fromkeys(parts))
    if isinstance(exc, asyncio.TimeoutError):
        return "Timed out while connecting. If this is the first run, the package may still be downloading."
    if isinstance(exc, FileNotFoundError):
        return f"Command not found: {exc.filename or exc}. Install Node.js (npx) or uv (uvx) first."
    return f"{type(exc).__name__}: {exc}"


hub = McpHub()
