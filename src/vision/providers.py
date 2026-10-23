"""Model providers.

Two kinds, both spoken to through the OpenAI-compatible API:
  * cloud  - OpenAI, OpenRouter, Groq, DeepSeek ...   (API key required, kept in the OS credential store)
  * local  - Ollama, LM Studio, llama.cpp, vLLM, Jan   (no key needed, nothing leaves your machine)
"""
from __future__ import annotations

import asyncio
import ipaddress
import time
from typing import Any
from urllib.parse import urlsplit

import httpx
from langchain_openai import ChatOpenAI

from . import db, secrets_store

KINDS = ("cloud", "local")
NO_KEY = "ollama"               # ChatOpenAI insists on a key; local servers ignore whatever we send
LOCAL_DEFAULT_CONTEXT = 4096     # what Ollama and most local servers load unless told otherwise

# Servers we look for on this machine (name, port). Tests replace this list.
LOCAL_CANDIDATES: list[tuple[str, int]] = [
    ("Ollama", 11434),
    ("LM Studio", 1234),
    ("llama.cpp", 8080),
    ("vLLM", 8000),
    ("Jan", 1337),
]


def is_local_host(host: str) -> bool:
    host = (host or "").strip("[]").lower()
    if host in ("localhost", "::1") or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def normalize_base_url(base_url: str, local: bool = False) -> str:
    value = (base_url or "").strip().rstrip("/")
    if not value:
        raise ValueError("Base URL cannot be empty.")
    if "://" not in value:  # "localhost:11434" -> http://..., "api.example.com/v1" -> https://...
        host = urlsplit("//" + value).hostname or ""
        value = ("http://" if is_local_host(host) else "https://") + value
    if not value.startswith(("http://", "https://")):
        raise ValueError("Base URL must start with http:// or https://.")
    if local and not urlsplit(value).path.strip("/"):  # Ollama and friends serve the API under /v1
        value += "/v1"
    return value


def create_chat_model(
    *,
    base_url: str,
    api_key: str = "",
    model_name: str,
    temperature: float = 0.2,
    timeout: float | None = None,
    local: bool = False,
) -> ChatOpenAI:
    key = (api_key or "").strip()
    if not key and not local:
        raise ValueError("API key cannot be empty.")
    if not (model_name or "").strip():
        raise ValueError("Model name cannot be empty.")
    return ChatOpenAI(
        model=model_name.strip(),
        api_key=key or NO_KEY,
        base_url=normalize_base_url(base_url, local),
        temperature=temperature,
        # a local model can take minutes to load into memory on its first request
        timeout=timeout if timeout is not None else (600.0 if local else 120.0),
        max_retries=1 if local else 2,
    )


async def list_models(*, base_url: str, api_key: str = "", local: bool = False, timeout: float = 20.0) -> list[dict[str, Any]]:
    url = normalize_base_url(base_url, local)
    if not (api_key or "").strip() and not local:
        raise ValueError("API key cannot be empty.")
    headers = {"Authorization": f"Bearer {api_key.strip()}"} if (api_key or "").strip() else {}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{url}/models", headers=headers)
            response.raise_for_status()
            payload = response.json()
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise ConnectionError(f"Cannot reach {url}. Is the server running?") from exc
    data = payload.get("data", [])
    if data == [] and isinstance(payload.get("models"), list):  # Ollama's /api/tags shape: [{"name": ...}]
        data = payload["models"]
    if not isinstance(data, list):
        raise ValueError("Unexpected /models response: expected a 'data' list.")
    models = [
        {"id": str(item.get("id") or item.get("name")), "object": item.get("object", "model")}
        for item in data
        if isinstance(item, dict) and (item.get("id") or item.get("name"))
    ]
    return sorted(models, key=lambda m: m["id"].lower())


async def test_model(model: Any) -> str:
    result = await model.ainvoke("Reply with exactly: connection successful")
    content = result.content
    return content if isinstance(content, str) else str(content)


async def detect_local(timeout: float = 0.8) -> list[dict[str, Any]]:
    """Look for local model servers on their usual ports and list the models each one offers."""

    async def probe(client: httpx.AsyncClient, name: str, port: int) -> dict[str, Any] | None:
        url = f"http://127.0.0.1:{port}/v1"
        try:
            response = await client.get(f"{url}/models")
            data = response.json().get("data", []) if response.status_code == 200 else None
        except (httpx.HTTPError, ValueError, AttributeError):
            return None
        if not isinstance(data, list):
            return None
        return {"name": name, "base_url": url, "models": sorted(str(m["id"]) for m in data if isinstance(m, dict) and m.get("id"))}

    async with httpx.AsyncClient(timeout=timeout) as client:
        found = await asyncio.gather(*(probe(client, n, p) for n, p in LOCAL_CANDIDATES))
    return [f for f in found if f]


# ---- the model picker: every model of every provider ------------------------

CHOICES_TTL = 60.0
_CHOICES: dict[str, tuple[float, dict[str, Any]]] = {}


def clear_choices_cache() -> None:
    _CHOICES.clear()


async def ollama_details(base_url: str, timeout: float = 3.0) -> dict[str, dict[str, Any]]:
    """Ollama also offers /api/tags with size, parameter count and quantization of every model."""
    parts = urlsplit(base_url)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{parts.scheme}://{parts.netloc}/api/tags")
            items = response.json().get("models", []) if response.status_code == 200 else []
    except (httpx.HTTPError, ValueError, AttributeError):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        d = item.get("details") or {}
        name = item.get("name") or item.get("model")
        info = {"size": item.get("size"), "params": d.get("parameter_size"), "quant": d.get("quantization_level"),
                "family": d.get("family")}
        if name:
            out[str(name)] = {k: v for k, v in info.items() if v}
    return out


async def _choices_for(row: dict[str, Any]) -> dict[str, Any]:
    local = is_local(row)
    key = secrets_store.get_secret(_secret_key(row["id"]))
    base = {"provider_id": row["id"], "name": row["name"], "kind": row.get("kind", "cloud"), "base_url": row["base_url"],
            "selected": row["model_name"], "is_default": bool(row["is_default"]), "has_key": bool(key)}
    ids: list[str] = []
    details: dict[str, dict[str, Any]] = {}
    error = None
    if not local and not key:
        error = "API key missing"
    else:
        try:
            ids = [m["id"] for m in await list_models(base_url=row["base_url"], api_key=key, local=local, timeout=5)]
            if local:
                details = await ollama_details(row["base_url"])
        except Exception as exc:  # an unreachable provider must not break the picker
            error = f"{type(exc).__name__}: {exc}"
    if row["model_name"] and row["model_name"] not in ids:  # the saved model stays selectable when the list is unavailable
        ids.insert(0, row["model_name"])
    return {**base, "error": error, "models": [{"id": m, **({"details": details[m]} if m in details else {})} for m in ids]}


async def model_choices(refresh: bool = False) -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM providers ORDER BY name COLLATE NOCASE")]

    async def one(row: dict[str, Any]) -> dict[str, Any]:
        hit = _CHOICES.get(row["id"])
        if hit and not refresh and time.monotonic() - hit[0] < CHOICES_TTL:
            return hit[1]
        data = await _choices_for(row)
        _CHOICES[row["id"]] = (time.monotonic(), data)
        return data

    return list(await asyncio.gather(*(one(r) for r in rows)))


# ---- stored providers -------------------------------------------------------

def _secret_key(provider_id: str) -> str:
    return f"provider:{provider_id}"


def is_local(row: dict[str, Any]) -> bool:
    return row.get("kind", "cloud") == "local"


def is_ready(row: dict[str, Any] | None) -> bool:
    """Can this provider be used for chatting right now?"""
    if not row or not (row.get("model_name") or "").strip():
        return False
    return is_local(row) or bool(secrets_store.get_secret(_secret_key(row["id"])))


def history_budget(row: dict[str, Any] | None) -> int | None:
    """How many tokens of chat history to send. Local servers load small context windows, so send less."""
    if row is None:
        return None
    ctx = int(row.get("context_tokens") or 0) or (LOCAL_DEFAULT_CONTEXT if is_local(row) else 0)
    return max(600, int(ctx * 0.4)) if ctx else None


def public(row: dict[str, Any]) -> dict[str, Any]:
    has_key = bool(secrets_store.get_secret(_secret_key(row["id"])))
    return {
        "id": row["id"],
        "name": row["name"],
        "base_url": row["base_url"],
        "model_name": row["model_name"],
        "is_default": bool(row["is_default"]),
        "kind": row.get("kind", "cloud"),
        "local": is_local(row),
        "context_tokens": int(row.get("context_tokens") or 0),
        "has_key": has_key,
        "ready": bool((row["model_name"] or "").strip()) and (is_local(row) or has_key),
    }


def list_providers() -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM providers ORDER BY name COLLATE NOCASE")]
    return [public(r) for r in rows]


def get_provider(provider_id: str) -> dict[str, Any] | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM providers WHERE id=?", (provider_id,)).fetchone()
    return dict(row) if row else None


def get_default_provider() -> dict[str, Any] | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM providers WHERE is_default=1 LIMIT 1").fetchone()
        if row is None:
            row = conn.execute("SELECT * FROM providers ORDER BY name LIMIT 1").fetchone()
    return dict(row) if row else None


def save_provider(
    *,
    provider_id: str | None,
    name: str,
    base_url: str,
    model_name: str,
    api_key: str | None,
    kind: str = "cloud",
    context_tokens: int = 0,
) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    context_tokens = int(context_tokens or 0)
    if context_tokens and not 512 <= context_tokens <= 4_000_000:
        raise ValueError("Context window must be between 512 and 4,000,000 tokens (or empty).")
    base_url = normalize_base_url(base_url, local=kind == "local")
    name = (name or "").strip() or base_url
    with db.connect() as conn:
        if provider_id:
            conn.execute(
                "UPDATE providers SET name=?, base_url=?, model_name=?, kind=?, context_tokens=? WHERE id=?",
                (name, base_url, (model_name or "").strip(), kind, context_tokens, provider_id),
            )
        else:
            provider_id = db.new_id()
            first = conn.execute("SELECT COUNT(*) FROM providers").fetchone()[0] == 0
            conn.execute(
                "INSERT INTO providers(id, name, base_url, model_name, is_default, kind, context_tokens) VALUES(?,?,?,?,?,?,?)",
                (provider_id, name, base_url, (model_name or "").strip(), 1 if first else 0, kind, context_tokens),
            )
    if api_key:  # empty/None keeps the stored key
        secrets_store.set_secret(_secret_key(provider_id), api_key.strip())
    clear_choices_cache()
    return public(get_provider(provider_id))


def delete_provider(provider_id: str) -> None:
    with db.connect() as conn:
        was_default = conn.execute("SELECT is_default FROM providers WHERE id=?", (provider_id,)).fetchone()
        conn.execute("DELETE FROM providers WHERE id=?", (provider_id,))
        if was_default and was_default[0]:
            conn.execute("UPDATE providers SET is_default=1 WHERE id=(SELECT id FROM providers LIMIT 1)")
    secrets_store.delete_secret(_secret_key(provider_id))
    clear_choices_cache()


def set_default(provider_id: str) -> None:
    with db.connect() as conn:
        conn.execute("UPDATE providers SET is_default=0")
        conn.execute("UPDATE providers SET is_default=1 WHERE id=?", (provider_id,))
    clear_choices_cache()


def model_for(provider: dict[str, Any]):
    """Build a chat model from a stored provider row (API key comes from the keychain)."""
    return create_chat_model(
        base_url=provider["base_url"],
        api_key=secrets_store.get_secret(_secret_key(provider["id"])),
        model_name=provider["model_name"],
        local=is_local(provider),
    )


def key_for(provider_id: str) -> str:
    return secrets_store.get_secret(_secret_key(provider_id))
