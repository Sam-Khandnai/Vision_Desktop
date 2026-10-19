"""OpenAI-compatible provider helpers (adapted from the original provider_manager.py)."""
from __future__ import annotations

from typing import Any

import httpx
from langchain_openai import ChatOpenAI

from . import db, secrets_store


def normalize_base_url(base_url: str) -> str:
    value = (base_url or "").strip().rstrip("/")
    if not value:
        raise ValueError("Base URL cannot be empty.")
    if not value.startswith(("http://", "https://")):
        raise ValueError("Base URL must start with http:// or https://.")
    return value


def create_chat_model(
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    temperature: float = 0.2,
    timeout: float = 120.0,
) -> ChatOpenAI:
    if not (api_key or "").strip():
        raise ValueError("API key cannot be empty.")
    if not (model_name or "").strip():
        raise ValueError("Model name cannot be empty.")
    return ChatOpenAI(
        model=model_name.strip(),
        api_key=api_key.strip(),
        base_url=normalize_base_url(base_url),
        temperature=temperature,
        timeout=timeout,
        max_retries=2,
    )


async def list_models(*, base_url: str, api_key: str, timeout: float = 20.0) -> list[dict[str, Any]]:
    url = normalize_base_url(base_url)
    if not (api_key or "").strip():
        raise ValueError("API key cannot be empty.")
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(f"{url}/models", headers={"Authorization": f"Bearer {api_key.strip()}"})
        response.raise_for_status()
        payload = response.json()
    data = payload.get("data", [])
    if not isinstance(data, list):
        raise ValueError("Unexpected /models response: expected a 'data' list.")
    models = [
        {"id": str(item["id"]), "object": item.get("object", "model")}
        for item in data
        if isinstance(item, dict) and item.get("id")
    ]
    return sorted(models, key=lambda m: m["id"].lower())


async def test_model(model: Any) -> str:
    result = await model.ainvoke("Reply with exactly: connection successful")
    content = result.content
    return content if isinstance(content, str) else str(content)


# ---- stored providers ----

def _secret_key(provider_id: str) -> str:
    return f"provider:{provider_id}"


def public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "base_url": row["base_url"],
        "model_name": row["model_name"],
        "is_default": bool(row["is_default"]),
        "has_key": bool(secrets_store.get_secret(_secret_key(row["id"]))),
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
    *, provider_id: str | None, name: str, base_url: str, model_name: str, api_key: str | None
) -> dict[str, Any]:
    base_url = normalize_base_url(base_url)
    name = (name or "").strip() or base_url
    with db.connect() as conn:
        if provider_id:
            conn.execute(
                "UPDATE providers SET name=?, base_url=?, model_name=? WHERE id=?",
                (name, base_url, (model_name or "").strip(), provider_id),
            )
        else:
            provider_id = db.new_id()
            first = conn.execute("SELECT COUNT(*) FROM providers").fetchone()[0] == 0
            conn.execute(
                "INSERT INTO providers(id, name, base_url, model_name, is_default) VALUES(?,?,?,?,?)",
                (provider_id, name, base_url, (model_name or "").strip(), 1 if first else 0),
            )
    if api_key:  # empty/None keeps the stored key
        secrets_store.set_secret(_secret_key(provider_id), api_key.strip())
    return public(get_provider(provider_id))


def delete_provider(provider_id: str) -> None:
    with db.connect() as conn:
        was_default = conn.execute("SELECT is_default FROM providers WHERE id=?", (provider_id,)).fetchone()
        conn.execute("DELETE FROM providers WHERE id=?", (provider_id,))
        if was_default and was_default[0]:
            conn.execute("UPDATE providers SET is_default=1 WHERE id=(SELECT id FROM providers LIMIT 1)")
    secrets_store.delete_secret(_secret_key(provider_id))


def set_default(provider_id: str) -> None:
    with db.connect() as conn:
        conn.execute("UPDATE providers SET is_default=0")
        conn.execute("UPDATE providers SET is_default=1 WHERE id=?", (provider_id,))


def model_for(provider: dict[str, Any]):
    """Build a chat model from a stored provider row (API key comes from the keychain)."""
    return create_chat_model(
        base_url=provider["base_url"],
        api_key=secrets_store.get_secret(_secret_key(provider["id"])),
        model_name=provider["model_name"],
    )


def key_for(provider_id: str) -> str:
    return secrets_store.get_secret(_secret_key(provider_id))
