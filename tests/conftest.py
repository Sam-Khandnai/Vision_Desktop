from __future__ import annotations

import json
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

FAKE_SERVER = str(Path(__file__).parent / "fake_mcp_server.py")


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Every test gets its own data dir and never touches the real OS keychain."""
    monkeypatch.setenv("VISION_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("VISION_TOKEN", raising=False)
    from vision import secrets_store

    monkeypatch.setattr(secrets_store, "_keyring", lambda: None)
    from vision import db

    db.init_db()
    yield


SEEN_SYSTEM: list[str] = []


class FakeModel(BaseChatModel):
    """Scripted chat model: calls tools when the user message says so, answers after tool results."""

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools, **kwargs):  # tools are ignored; behaviour is scripted
        return self

    def _decide(self, messages: list[BaseMessage]) -> AIMessage:
        if messages and isinstance(messages[0], SystemMessage):
            SEEN_SYSTEM.append(messages[0].content)
        last = messages[-1]
        c = last.content
        text = c if isinstance(c, str) else "".join(b.get("text", "") for b in c if isinstance(b, dict))
        if isinstance(last, ToolMessage):
            return AIMessage(content=f"Tool said: {text}")
        if "extract durable facts" in text:
            return AIMessage(content='Sure: ["User is a Python developer"]')
        if "Update the running summary" in text:
            return AIMessage(content="SUMMARY-OK")
        if "use echo" in text:
            return AIMessage(content="", tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "c1", "type": "tool_call"}])
        if "use delete" in text:
            return AIMessage(content="", tool_calls=[{"name": "delete_note", "args": {"name": "x"}, "id": "c2", "type": "tool_call"}])
        return AIMessage(content="Hello there")

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._decide(messages))])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._decide(messages))])

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        msg = self._decide(messages)
        if msg.tool_calls:
            tc = msg.tool_calls[0]
            yield ChatGenerationChunk(message=AIMessageChunk(
                content="", tool_call_chunks=[{"name": tc["name"], "args": json.dumps(tc["args"]), "id": tc["id"], "index": 0}]))
            return
        for word in str(msg.content).split(" "):
            yield ChatGenerationChunk(message=AIMessageChunk(content=word + " "))


class LiveServer:
    def __init__(self) -> None:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        from vision.main import app

        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        self.thread.start()
        for _ in range(100):
            try:
                if httpx.get(self.url + "/api/health", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.1)
        raise RuntimeError("server did not start")

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


@pytest.fixture
def live(monkeypatch):
    from vision import providers
    from vision.mcp_hub import hub

    fake = FakeModel()
    SEEN_SYSTEM.clear()
    monkeypatch.setattr(providers, "model_for", lambda provider: fake)
    hub._tools.clear()
    hub._status.clear()
    srv = LiveServer()
    srv.start()
    yield srv
    srv.stop()
    for sid in list(hub._tasks):
        hub.disconnect(sid)


def read_sse(response: httpx.Response):
    for line in response.iter_lines():
        if line.startswith("data: "):
            yield json.loads(line[6:])


def add_provider(client: httpx.Client) -> None:
    r = client.post("/api/providers", json={"name": "Fake", "base_url": "http://localhost:1/v1",
                                            "model_name": "fake-1", "api_key": "sk-test"})
    assert r.status_code == 200, r.text


def add_fake_mcp(client: httpx.Client, approval: str = "smart") -> str:
    r = client.post("/api/mcp/servers", json={"name": "fake", "transport": "stdio", "command": sys.executable,
                                              "args": [FAKE_SERVER], "approval": approval})
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    for _ in range(100):
        servers = client.get("/api/mcp/servers").json()
        st = next(s for s in servers if s["id"] == sid)["status"]
        if st["state"] == "connected":
            return sid
        if st["state"] == "error":
            raise AssertionError(st["message"])
        time.sleep(0.2)
    raise AssertionError("MCP server never connected")
