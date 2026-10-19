"""Vision backend: FastAPI app bound to 127.0.0.1, started and supervised by the Electron shell."""
from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import __version__, approvals, catalog, chat, config, db, memory, providers, secrets_store
from .mcp_hub import hub

logger = logging.getLogger("vision")
_background: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    hub.bind_loop()
    hub.connect_all_in_background()
    yield
    for server in hub.list_servers():
        hub.disconnect(server["id"])


app = FastAPI(title="Vision", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["null", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def require_token(request: Request) -> None:
    token = config.api_token()
    if not token:  # dev mode only; Electron always sets a per-launch token
        return
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, token):
        raise HTTPException(status_code=401, detail="Unauthorized")


api = Depends(require_token)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "version": __version__}


@app.get("/api/system", dependencies=[api])
def system_info() -> dict[str, Any]:
    return {"version": __version__, "secrets": secrets_store.backend_name(), "runtimes": catalog.runtimes(),
            "data_dir": str(config.data_dir())}


# ---------------- profile & settings ----------------
PROFILE_KEYS = ("display_name", "about", "instructions")


class ProfileIn(BaseModel):
    display_name: str = Field("", max_length=80)
    about: str = Field("", max_length=2000)
    instructions: str = Field("", max_length=2000)


@app.get("/api/profile", dependencies=[api])
def get_profile() -> dict[str, Any]:
    data = db.kv_get_all("profile")
    settings = db.kv_get_all("settings")
    return {**{k: data.get(k, "") for k in PROFILE_KEYS}, "memory_enabled": settings.get("memory_enabled", "1") == "1"}


@app.put("/api/profile", dependencies=[api])
def put_profile(body: ProfileIn) -> dict[str, Any]:
    for key in PROFILE_KEYS:
        db.kv_set("profile", key, getattr(body, key).strip())
    return get_profile()


class SettingsIn(BaseModel):
    memory_enabled: bool


@app.put("/api/settings", dependencies=[api])
def put_settings(body: SettingsIn) -> dict[str, Any]:
    db.kv_set("settings", "memory_enabled", "1" if body.memory_enabled else "0")
    return get_profile()


# ---------------- memories ----------------
@app.get("/api/memories", dependencies=[api])
def get_memories() -> list[dict[str, Any]]:
    return memory.list_memories()


class MemoryIn(BaseModel):
    text: str = Field(..., min_length=2, max_length=400)


@app.post("/api/memories", dependencies=[api])
def post_memory(body: MemoryIn) -> dict[str, Any]:
    return {"added": memory.add_fact(body.text)}


@app.delete("/api/memories/{memory_id}", dependencies=[api])
def del_memory(memory_id: int) -> dict[str, bool]:
    memory.delete_memory(memory_id)
    return {"ok": True}


@app.delete("/api/memories", dependencies=[api])
def del_all_memories() -> dict[str, bool]:
    memory.clear_memories()
    return {"ok": True}


# ---------------- providers ----------------
class ProviderIn(BaseModel):
    name: str = ""
    base_url: str
    model_name: str = ""
    api_key: str | None = None  # None/"" keeps the stored key


class ModelsIn(BaseModel):
    base_url: str
    api_key: str | None = None
    provider_id: str | None = None  # use the stored key of this provider when api_key is empty


class TestIn(ModelsIn):
    model_name: str


def _resolve_key(api_key: str | None, provider_id: str | None) -> str:
    if api_key and api_key.strip():
        return api_key
    return providers.key_for(provider_id) if provider_id else ""


@app.get("/api/providers", dependencies=[api])
def get_providers() -> list[dict[str, Any]]:
    return providers.list_providers()


@app.post("/api/providers", dependencies=[api])
def post_provider(body: ProviderIn) -> dict[str, Any]:
    try:
        return providers.save_provider(provider_id=None, name=body.name, base_url=body.base_url,
                                       model_name=body.model_name, api_key=body.api_key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.put("/api/providers/{provider_id}", dependencies=[api])
def put_provider(provider_id: str, body: ProviderIn) -> dict[str, Any]:
    if providers.get_provider(provider_id) is None:
        raise HTTPException(404, "Provider not found")
    try:
        return providers.save_provider(provider_id=provider_id, name=body.name, base_url=body.base_url,
                                       model_name=body.model_name, api_key=body.api_key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/api/providers/{provider_id}", dependencies=[api])
def del_provider(provider_id: str) -> dict[str, bool]:
    providers.delete_provider(provider_id)
    return {"ok": True}


@app.post("/api/providers/{provider_id}/default", dependencies=[api])
def default_provider(provider_id: str) -> dict[str, bool]:
    providers.set_default(provider_id)
    return {"ok": True}


@app.post("/api/providers/models", dependencies=[api])
async def post_models(body: ModelsIn) -> dict[str, Any]:
    try:
        models = await providers.list_models(base_url=body.base_url, api_key=_resolve_key(body.api_key, body.provider_id))
        return {"models": [m["id"] for m in models]}
    except Exception as exc:
        raise HTTPException(400, f"{type(exc).__name__}: {exc}") from exc


@app.post("/api/providers/test", dependencies=[api])
async def post_test(body: TestIn) -> dict[str, Any]:
    try:
        model = providers.create_chat_model(base_url=body.base_url, api_key=_resolve_key(body.api_key, body.provider_id),
                                            model_name=body.model_name)
        return {"reply": await providers.test_model(model)}
    except Exception as exc:
        raise HTTPException(400, f"{type(exc).__name__}: {exc}") from exc


# ---------------- MCP servers ----------------
class McpIn(BaseModel):
    name: str
    transport: str
    command: str = ""
    args: list[str] = []
    url: str = ""
    env: dict[str, str] | None = None
    headers: dict[str, str] | None = None
    approval: str = "smart"


def _server_kwargs(body: McpIn) -> dict[str, Any]:
    cfg = {"command": body.command.strip(), "args": body.args} if body.transport == "stdio" else {"url": body.url.strip()}
    return {"name": body.name, "transport": body.transport, "config": cfg, "env": body.env,
            "headers": body.headers, "approval": body.approval}


@app.get("/api/mcp/servers", dependencies=[api])
def get_servers() -> list[dict[str, Any]]:
    return hub.list_servers()


@app.post("/api/mcp/servers", dependencies=[api])
def post_server(body: McpIn) -> dict[str, Any]:
    try:
        saved = hub.save_server(server_id=None, **_server_kwargs(body))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    hub.connect_in_background(saved["id"])
    return saved


@app.put("/api/mcp/servers/{server_id}", dependencies=[api])
def put_server(server_id: str, body: McpIn) -> dict[str, Any]:
    if hub.get_row(server_id) is None:
        raise HTTPException(404, "Server not found")
    try:
        saved = hub.save_server(server_id=server_id, keep_secrets=True, **_server_kwargs(body))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    hub.connect_in_background(server_id)
    return saved


@app.delete("/api/mcp/servers/{server_id}", dependencies=[api])
def del_server(server_id: str) -> dict[str, bool]:
    hub.delete_server(server_id)
    return {"ok": True}


class ToggleIn(BaseModel):
    enabled: bool


@app.post("/api/mcp/servers/{server_id}/enabled", dependencies=[api])
def toggle_server(server_id: str, body: ToggleIn) -> dict[str, bool]:
    if hub.get_row(server_id) is None:
        raise HTTPException(404, "Server not found")
    hub.set_enabled(server_id, body.enabled)
    if body.enabled:
        hub.connect_in_background(server_id)
    return {"ok": True}


class ApprovalModeIn(BaseModel):
    approval: str


@app.post("/api/mcp/servers/{server_id}/approval", dependencies=[api])
def set_server_approval(server_id: str, body: ApprovalModeIn) -> dict[str, bool]:
    try:
        hub.set_approval(server_id, body.approval)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@app.post("/api/mcp/servers/{server_id}/connect", dependencies=[api])
def reconnect_server(server_id: str) -> dict[str, bool]:
    if hub.get_row(server_id) is None:
        raise HTTPException(404, "Server not found")
    hub.connect_in_background(server_id)
    return {"ok": True}


# ---------------- catalog ----------------
@app.get("/api/catalog", dependencies=[api])
def get_catalog() -> dict[str, Any]:
    installed = {s["catalog_id"] for s in hub.list_servers() if s["catalog_id"]}
    data = catalog.load()
    return {
        "categories": data["categories"],
        "runtimes": catalog.runtimes(),
        "servers": [{**s, "installed": s["id"] in installed} for s in data["servers"]],
    }


class CatalogInstallIn(BaseModel):
    values: dict[str, str] = {}
    approval: str = "smart"


@app.post("/api/catalog/{entry_id}/install", dependencies=[api])
def install_catalog_entry(entry_id: str, body: CatalogInstallIn) -> dict[str, Any]:
    entry = catalog.get(entry_id)
    if entry is None:
        raise HTTPException(404, "Unknown catalog entry")
    try:
        kwargs = catalog.build_server(entry, body.values)
        name, n = kwargs["name"], 2
        existing = {s["name"] for s in hub.list_servers()}
        while kwargs["name"] in existing:
            kwargs["name"] = f"{name} {n}"
            n += 1
        saved = hub.save_server(server_id=None, approval=body.approval, **kwargs)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    hub.connect_in_background(saved["id"])
    return saved


# ---------------- approvals ----------------
class ApprovalIn(BaseModel):
    approve: bool


@app.post("/api/approvals/{approval_id}", dependencies=[api])
def answer_approval(approval_id: str, body: ApprovalIn) -> dict[str, bool]:
    return {"ok": approvals.resolve(approval_id, body.approve)}


# ---------------- conversations ----------------
class ConversationPatch(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


@app.get("/api/conversations", dependencies=[api])
def list_conversations(q: str = "") -> list[dict[str, Any]]:
    with db.connect() as conn:
        if q.strip():
            fts = memory._fts_query(q)
            ids: set[str] = set()
            if fts:
                try:
                    ids = {r[0] for r in conn.execute(
                        "SELECT DISTINCT m.conversation_id FROM messages_fts f JOIN messages m ON m.id=f.rowid "
                        "WHERE messages_fts MATCH ? LIMIT 100", (fts,))}
                except Exception:
                    ids = set()
            rows = conn.execute("SELECT id, title, updated_at FROM conversations ORDER BY updated_at DESC").fetchall()
            rows = [r for r in rows if r["id"] in ids or q.strip().lower() in (r["title"] or "").lower()]
        else:
            rows = conn.execute("SELECT id, title, updated_at FROM conversations ORDER BY updated_at DESC LIMIT 300").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/conversations", dependencies=[api])
def create_conversation() -> dict[str, Any]:
    cid, ts = db.new_id(), db.now()
    with db.connect() as conn:
        conn.execute("INSERT INTO conversations(id, title, created_at, updated_at) VALUES(?,?,?,?)", (cid, "", ts, ts))
    return {"id": cid, "title": "", "updated_at": ts}


@app.get("/api/conversations/{cid}", dependencies=[api])
def get_conversation(cid: str) -> dict[str, Any]:
    with db.connect() as conn:
        conv = conn.execute("SELECT id, title, updated_at FROM conversations WHERE id=?", (cid,)).fetchone()
        if conv is None:
            raise HTTPException(404, "Conversation not found")
        rows = conn.execute(
            "SELECT id, role, content, tool_json, created_at FROM messages WHERE conversation_id=? ORDER BY id", (cid,)
        ).fetchall()
    messages = [{**dict(r), "tools": json.loads(r["tool_json"] or "[]")} for r in rows]
    for m in messages:
        m.pop("tool_json", None)
    return {**dict(conv), "messages": messages}


@app.patch("/api/conversations/{cid}", dependencies=[api])
def rename_conversation(cid: str, body: ConversationPatch) -> dict[str, bool]:
    with db.connect() as conn:
        conn.execute("UPDATE conversations SET title=? WHERE id=?", (body.title.strip(), cid))
    return {"ok": True}


@app.delete("/api/conversations/{cid}", dependencies=[api])
def delete_conversation(cid: str) -> dict[str, bool]:
    with db.connect() as conn:
        conn.execute("DELETE FROM conversations WHERE id=?", (cid,))
    return {"ok": True}


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=60000)


def _sse(event: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n".encode("utf-8")


def _title_from(text: str) -> str:
    line = " ".join(text.split())
    return line if len(line) <= 48 else line[:47].rstrip() + "…"


async def _after_turn(model: Any, cid: str, user_text: str, memory_on: bool) -> None:
    try:
        await memory.maybe_summarize(model, cid)
        if memory_on and memory.should_extract(cid, user_text):
            await memory.extract_facts(model, cid)
    except Exception:
        logger.warning("Post-turn memory work failed", exc_info=True)


@app.post("/api/conversations/{cid}/chat", dependencies=[api])
async def chat_endpoint(cid: str, body: ChatIn) -> StreamingResponse:
    with db.connect() as conn:
        conv = conn.execute("SELECT id, title FROM conversations WHERE id=?", (cid,)).fetchone()
    if conv is None:
        raise HTTPException(404, "Conversation not found")
    provider = providers.get_default_provider()
    if provider is None or not provider["model_name"] or not providers.key_for(provider["id"]):
        raise HTTPException(400, "no_provider")
    try:
        model = providers.model_for(provider)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    # history must be read BEFORE the new user message is stored
    summary, history = memory.build_context(cid)
    title = conv["title"] or _title_from(body.message)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO messages(conversation_id, role, content, created_at) VALUES(?,?,?,?)",
            (cid, "user", body.message, db.now()),
        )
        conn.execute("UPDATE conversations SET title=?, updated_at=? WHERE id=?", (title, db.now(), cid))

    profile = db.kv_get_all("profile")
    memory_on = db.setting_bool("memory_enabled", True)
    facts = memory.retrieve(body.message) if memory_on else []
    tools = hub.get_tools()
    system_prompt = chat.build_system_prompt(profile=profile, memories=facts, summary=summary,
                                             tool_names=[t.name for t in tools])

    queue: asyncio.Queue = asyncio.Queue()
    state = chat.TurnState()

    async def producer() -> None:
        approvals.event_sink.set(queue)
        try:
            await chat.run_turn(model=model, tools=tools, system_prompt=system_prompt, history=history,
                                user_text=body.message, sink=queue, state=state)
            message_id = chat.persist_assistant(cid, state)
            await queue.put({"type": "done", "message_id": message_id, "title": title})
            _spawn(_after_turn(model, cid, body.message, memory_on))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Chat turn failed", exc_info=True)
            chat.persist_assistant(cid, state)
            await queue.put({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            await queue.put(None)

    task = asyncio.create_task(producer())

    async def stream():
        try:
            yield _sse({"type": "start", "title": title, "tools": [t.name for t in tools]})
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield _sse(event)
        finally:  # client pressed Stop / closed the window: keep what was generated so far
            if not task.done():
                task.cancel()
            chat.persist_assistant(cid, state)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def self_check() -> dict[str, Any]:
    """`vision-server --check`: proves a packaged build really contains everything it needs."""
    import sys

    result: dict[str, Any] = {
        "version": __version__,
        "frozen": bool(getattr(sys, "frozen", False)),
        "secrets": secrets_store.backend_name(),
        "catalog": len(catalog.load()["servers"]),
        "runtimes": catalog.runtimes(),
    }
    try:  # build and run one tiny agent turn: loads LangChain/LangGraph for real
        from langchain.agents import create_agent
        from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
        from langchain_core.messages import AIMessage

        model = GenericFakeChatModel(messages=iter([AIMessage(content="ok")]))
        out = create_agent(model=model, tools=[], system_prompt="test").invoke({"messages": [("user", "hi")]})
        result["agent"] = "ok" if out["messages"][-1].content == "ok" else "unexpected reply"
    except Exception as exc:
        result["agent"] = f"{type(exc).__name__}: {exc}"
    return result


def run() -> None:
    parser = argparse.ArgumentParser(prog="vision-server")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--check", action="store_true", help="print a self-check as JSON and exit")
    args = parser.parse_args()
    if args.check:
        print(json.dumps(self_check()))
        return
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    run()
