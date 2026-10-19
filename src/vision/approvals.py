"""Human-in-the-loop approvals for tool calls that may change something."""
from __future__ import annotations

import asyncio
import contextvars
import re
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from . import db

# Event sink for the chat turn that is currently running (set by the chat runner).
event_sink: contextvars.ContextVar[asyncio.Queue | None] = contextvars.ContextVar("event_sink", default=None)

_pending: dict[str, asyncio.Future] = {}
APPROVAL_TIMEOUT = 600.0

_SAFE = {
    "read", "list", "get", "search", "find", "fetch", "query", "describe", "view", "show", "check",
    "lookup", "status", "info", "tree", "stat", "resolve", "snapshot", "screenshot", "wait", "time",
    "convert", "transcript", "directory", "diff", "log", "count", "browse", "scrape", "crawl", "extract",
    "retrieve", "explain", "inspect", "peek", "head", "tail", "ls", "cat", "open", "navigate", "think",
}
_RISKY = {
    "write", "edit", "create", "delete", "remove", "rm", "move", "rename", "update", "send", "post",
    "execute", "exec", "run", "kill", "drop", "insert", "commit", "push", "merge", "install", "set",
    "add", "apply", "save", "upload", "replace", "append", "patch", "put", "truncate", "reset",
    "start", "stop", "restart", "deploy", "publish", "reply", "forward", "archive", "trash", "close",
    "click", "type", "fill", "press", "drag", "evaluate", "shell", "command", "terminal", "process",
}


def _tokens(name: str) -> set[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return {t.lower() for t in re.split(r"[^A-Za-z0-9]+", spaced) if t}


def needs_approval(tool: BaseTool, mode: str) -> bool:
    """mode: 'never' | 'always' | 'smart'. 'smart' trusts read-only hints and clear read-only names."""
    if mode == "never":
        return False
    if mode == "always":
        return True
    meta = getattr(tool, "metadata", None) or {}
    if meta.get("destructiveHint") is True:
        return True
    if meta.get("readOnlyHint") is True:
        return False
    tokens = _tokens(tool.name)
    if tokens & _RISKY:
        return True
    if tokens & _SAFE:
        return False
    return True


async def request(tool_name: str, server: str, args: dict[str, Any]) -> bool:
    """Ask the UI for approval and wait for the answer. Returns True if approved."""
    sink = event_sink.get()
    if sink is None:  # no UI attached: refuse rather than act silently
        return False
    approval_id = db.new_id()
    future: asyncio.Future = asyncio.get_running_loop().create_future()
    _pending[approval_id] = future
    await sink.put({"type": "approval_request", "id": approval_id, "tool": tool_name, "server": server, "args": args})
    try:
        return bool(await asyncio.wait_for(future, APPROVAL_TIMEOUT))
    except asyncio.TimeoutError:
        return False
    finally:
        _pending.pop(approval_id, None)


def resolve(approval_id: str, approved: bool) -> bool:
    future = _pending.get(approval_id)
    if future is None or future.done():
        return False
    future.set_result(approved)
    return True


def pending_count() -> int:
    return len(_pending)


def wrap_tool(tool: BaseTool, *, server: str, mode: str, public_name: str | None = None) -> BaseTool:
    """Return a tool that asks for approval first when the policy says so."""
    ask = needs_approval(tool, mode)
    name = public_name or tool.name

    async def run(**kwargs: Any) -> Any:
        if ask:
            if not await request(name, server, kwargs):
                return "The user declined this action. Do not retry it; ask what they would like instead."
        try:
            return await tool.ainvoke(kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # report tool failures to the model instead of crashing the turn
            return f"Tool error ({type(exc).__name__}): {exc}"

    return StructuredTool(
        name=name,
        description=tool.description or name,
        args_schema=tool.args_schema,
        coroutine=run,
        metadata={**(getattr(tool, "metadata", None) or {}), "server": server, "needs_approval": ask},
    )
