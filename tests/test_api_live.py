"""End-to-end tests against a real uvicorn server, a real stdio MCP server and a scripted model."""
from __future__ import annotations

import threading
import time

import httpx

from tests.conftest import SEEN_SYSTEM, FakeModel, add_fake_mcp, add_provider, read_sse


def client(live):
    return httpx.Client(base_url=live.url, timeout=30)


def new_conv(c):
    return c.post("/api/conversations").json()["id"]


def test_chat_requires_provider(live):
    with client(live) as c:
        cid = new_conv(c)
        r = c.post(f"/api/conversations/{cid}/chat", json={"message": "hi"})
        assert r.status_code == 400 and r.json()["detail"] == "no_provider"


def test_plain_chat_streams_tokens_and_persists(live):
    with client(live) as c:
        add_provider(c)
        cid = new_conv(c)
        with c.stream("POST", f"/api/conversations/{cid}/chat", json={"message": "Salam dostam"}) as r:
            events = list(read_sse(r))
        types = [e["type"] for e in events]
        assert types[0] == "start" and types[-1] == "done"
        assert "".join(e["text"] for e in events if e["type"] == "token").strip() == "Hello there"
        conv = c.get(f"/api/conversations/{cid}").json()
        assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
        assert conv["title"] == "Salam dostam"


def test_mcp_tool_call_is_streamed_and_read_only_needs_no_approval(live):
    with client(live) as c:
        add_provider(c)
        add_fake_mcp(c)
        cid = new_conv(c)
        with c.stream("POST", f"/api/conversations/{cid}/chat", json={"message": "please use echo"}) as r:
            events = list(read_sse(r))
        kinds = [e["type"] for e in events]
        assert "approval_request" not in kinds
        start = next(e for e in events if e["type"] == "tool_start")
        end = next(e for e in events if e["type"] == "tool_end")
        assert start["name"] == "echo" and end["ok"] and "echo:hi" in end["output"]
        text = "".join(e["text"] for e in events if e["type"] == "token")
        assert "Tool said:" in text and "echo:hi" in text
        saved = c.get(f"/api/conversations/{cid}").json()["messages"][-1]
        assert saved["tools"][0]["name"] == "echo"


def _run_chat_with_decision(live, approve: bool):
    events: list[dict] = []
    with client(live) as c:
        add_provider(c)
        add_fake_mcp(c)
        cid = new_conv(c)
        with c.stream("POST", f"/api/conversations/{cid}/chat", json={"message": "please use delete"}) as r:
            for ev in read_sse(r):
                events.append(ev)
                if ev["type"] == "approval_request":
                    assert ev["tool"] == "delete_note" and ev["args"] == {"name": "x"}
                    ans = c.post(f"/api/approvals/{ev['id']}", json={"approve": approve})
                    assert ans.json() == {"ok": True}
    return events


def test_destructive_tool_waits_for_approval_and_runs_when_approved(live):
    events = _run_chat_with_decision(live, True)
    end = next(e for e in events if e["type"] == "tool_end")
    assert end["ok"] and "deleted:x" in end["output"]


def test_destructive_tool_is_blocked_when_declined(live):
    events = _run_chat_with_decision(live, False)
    end = next(e for e in events if e["type"] == "tool_end")
    assert not end["ok"] and "declined" in end["output"]
    assert not any("deleted:x" in str(e) for e in events)


def test_never_mode_skips_approval(live):
    with client(live) as c:
        add_provider(c)
        add_fake_mcp(c, approval="never")
        cid = new_conv(c)
        with c.stream("POST", f"/api/conversations/{cid}/chat", json={"message": "please use delete"}) as r:
            kinds = [e["type"] for e in read_sse(r)]
        assert "approval_request" not in kinds


def test_profile_and_memories_reach_the_system_prompt_and_facts_are_learned(live):
    with client(live) as c:
        add_provider(c)
        c.put("/api/profile", json={"display_name": "Sam", "about": "AI programmer", "instructions": "Be brief"})
        c.post("/api/memories", json={"text": "User builds desktop apps with Electron"})
        cid = new_conv(c)
        # 3rd user message triggers fact extraction
        for text in ["hello", "tell me about electron apps", "ok thanks"]:
            with c.stream("POST", f"/api/conversations/{cid}/chat", json={"message": text}) as r:
                list(read_sse(r))
        prompts = SEEN_SYSTEM
        assert any("Name: Sam" in p and "AI programmer" in p and "Be brief" in p for p in prompts)
        assert any("Electron" in p for p in prompts[1:2])  # retrieved by the word "electron"
        for _ in range(50):  # extraction runs in the background after the turn
            facts = [m["text"] for m in c.get("/api/memories").json()]
            if "User is a Python developer" in facts:
                break
            time.sleep(0.1)
        assert "User is a Python developer" in facts


def test_memory_can_be_disabled(live):
    with client(live) as c:
        add_provider(c)
        c.put("/api/settings", json={"memory_enabled": False})
        c.post("/api/memories", json={"text": "User likes turquoise"})
        cid = new_conv(c)
        SEEN_SYSTEM.clear()
        with c.stream("POST", f"/api/conversations/{cid}/chat", json={"message": "turquoise colour ideas"}) as r:
            list(read_sse(r))
        assert not any("turquoise" in p for p in SEEN_SYSTEM)


def test_stopping_a_stream_keeps_the_partial_answer(live, monkeypatch):
    # the model streams slowly; the client disconnects after the first token
    async def slow(self, messages, stop=None, run_manager=None, **kw):
        import asyncio
        from langchain_core.messages import AIMessageChunk
        from langchain_core.outputs import ChatGenerationChunk
        for w in ["one", "two", "three", "four"]:
            yield ChatGenerationChunk(message=AIMessageChunk(content=w + " "))
            await asyncio.sleep(0.4)

    monkeypatch.setattr(FakeModel, "_astream", slow)
    with client(live) as c:
        add_provider(c)
        cid = new_conv(c)
        with c.stream("POST", f"/api/conversations/{cid}/chat", json={"message": "count"}) as r:
            for ev in read_sse(r):
                if ev["type"] == "token":
                    break  # leaving the with-block closes the connection
        for _ in range(40):
            msgs = c.get(f"/api/conversations/{cid}").json()["messages"]
            if len(msgs) == 2:
                break
            time.sleep(0.1)
        assert len(msgs) == 2 and msgs[1]["content"].startswith("one") and "four" not in msgs[1]["content"]


def test_local_provider_needs_no_api_key_and_can_chat(live):
    with client(live) as c:
        r = c.post("/api/providers", json={"name": "Ollama", "base_url": "http://localhost:11434/v1",
                                           "model_name": "llama3", "local": True})
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["local"] is True and p["has_key"] is False
        # the fake model is injected by the live fixture, so the turn must run without any stored key
        cid = new_conv(c)
        with c.stream("POST", f"/api/conversations/{cid}/chat", json={"message": "hello"}) as resp:
            events = list(read_sse(resp))
        assert [e["type"] for e in events][-1] == "done"
        assert any(e["type"] == "token" for e in events)


def test_remote_provider_still_requires_a_key(live):
    with client(live) as c:
        r = c.post("/api/providers", json={"name": "Remote", "base_url": "https://api.example.com/v1",
                                           "model_name": "m", "local": False})
        assert r.status_code == 200 and r.json()["has_key"] is False
        cid = new_conv(c)
        resp = c.post(f"/api/conversations/{cid}/chat", json={"message": "hello"})
        assert resp.status_code == 400 and resp.json()["detail"] == "no_provider"


def test_provider_local_flag_survives_edit(live):
    with client(live) as c:
        pid = c.post("/api/providers", json={"name": "Ollama", "base_url": "http://localhost:11434/v1",
                                             "model_name": "llama3", "local": True}).json()["id"]
        c.put(f"/api/providers/{pid}", json={"name": "Ollama", "base_url": "http://localhost:11434/v1",
                                             "model_name": "qwen2", "local": True})
        row = next(p for p in c.get("/api/providers").json() if p["id"] == pid)
        assert row["local"] is True and row["model_name"] == "qwen2"
        # switching back to a remote provider drops the flag and requires a key again
        c.put(f"/api/providers/{pid}", json={"name": "Remote", "base_url": "https://api.example.com/v1",
                                             "model_name": "m", "local": False})
        row = next(p for p in c.get("/api/providers").json() if p["id"] == pid)
        assert row["local"] is False


def test_retry_user_message_drops_the_tail_and_reruns_the_turn(live):
    with client(live) as c:
        add_provider(c)
        cid = new_conv(c)
        with c.stream("POST", f"/api/conversations/{cid}/chat", json={"message": "first question"}) as r:
            events = list(read_sse(r))
        start = next(e for e in events if e["type"] == "start")
        assert start["user_message_id"]
        with c.stream("POST", f"/api/conversations/{cid}/chat", json={"message": "second question"}) as r:
            list(read_sse(r))
        assert len(c.get(f"/api/conversations/{cid}").json()["messages"]) == 4

        with c.stream("POST", f"/api/conversations/{cid}/retry", json={"message_id": start["user_message_id"]}) as r:
            retry_events = list(read_sse(r))
        assert retry_events[0]["type"] == "start"
        msgs = c.get(f"/api/conversations/{cid}").json()["messages"]
        assert [m["content"] for m in msgs if m["role"] == "user"] == ["first question"]
        assert msgs[-1]["content"].strip() == "Hello there"


def test_retry_assistant_message_regenerates_from_its_user_message(live):
    with client(live) as c:
        add_provider(c)
        cid = new_conv(c)
        with c.stream("POST", f"/api/conversations/{cid}/chat", json={"message": "hello there"}) as r:
            events = list(read_sse(r))
        assistant_id = next(e for e in events if e["type"] == "done")["message_id"]
        with c.stream("POST", f"/api/conversations/{cid}/retry", json={"message_id": assistant_id}) as r:
            assert list(read_sse(r))[0]["type"] == "start"
        msgs = c.get(f"/api/conversations/{cid}").json()["messages"]
        assert [m["role"] for m in msgs] == ["user", "assistant"]
        assert msgs[0]["content"] == "hello there" and msgs[1]["content"].strip() == "Hello there"


def test_retry_requires_a_provider_before_deleting_anything(live):
    with client(live) as c:
        add_provider(c)
        cid = new_conv(c)
        with c.stream("POST", f"/api/conversations/{cid}/chat", json={"message": "keep me"}) as r:
            events = list(read_sse(r))
        user_id = next(e for e in events if e["type"] == "start")["user_message_id"]
        pid = c.get("/api/providers").json()[0]["id"]
        c.delete(f"/api/providers/{pid}")
        r = c.post(f"/api/conversations/{cid}/retry", json={"message_id": user_id})
        assert r.status_code == 400 and r.json()["detail"] == "no_provider"
        assert len(c.get(f"/api/conversations/{cid}").json()["messages"]) == 2  # nothing was dropped


def test_retry_rejects_unknown_message_ids(live):
    with client(live) as c:
        add_provider(c)
        cid = new_conv(c)
        assert c.post(f"/api/conversations/{cid}/retry", json={"message_id": 999}).status_code == 404
        assert c.post("/api/conversations/nope/retry", json={"message_id": 1}).status_code == 404


def test_conversation_crud_and_search(live):
    with client(live) as c:
        add_provider(c)
        cid = new_conv(c)
        with c.stream("POST", f"/api/conversations/{cid}/chat", json={"message": "quantum entanglement basics"}) as r:
            list(read_sse(r))
        assert [x["id"] for x in c.get("/api/conversations", params={"q": "entanglement"}).json()] == [cid]
        assert c.get("/api/conversations", params={"q": "zzzzzz"}).json() == []
        c.patch(f"/api/conversations/{cid}", json={"title": "Physics"})
        assert c.get("/api/conversations").json()[0]["title"] == "Physics"
        c.delete(f"/api/conversations/{cid}")
        assert c.get("/api/conversations").json() == []
        assert c.get(f"/api/conversations/{cid}").status_code == 404


def test_api_key_is_never_returned_or_stored_in_sqlite(live, tmp_path):
    with client(live) as c:
        add_provider(c)
        listed = c.get("/api/providers").json()
        assert listed[0]["has_key"] is True and "sk-test" not in str(listed)
        pid = listed[0]["id"]
        # editing without a key keeps the stored one
        c.put(f"/api/providers/{pid}", json={"name": "Renamed", "base_url": "http://localhost:1/v1", "model_name": "m2"})
        assert c.get("/api/providers").json()[0]["has_key"] is True
    import sqlite3
    raw = sqlite3.connect(tmp_path / "vision.db")
    dump = "\n".join(raw.iterdump())
    assert "sk-test" not in dump


def test_mcp_secrets_are_not_in_sqlite_and_catalog_install_works(live, tmp_path):
    with client(live) as c:
        r = c.post("/api/catalog/github/install", json={"values": {"token": "ghp_secret"}})
        assert r.status_code == 200, r.text
        server = r.json()
        assert server["header_keys"] == ["Authorization"] and "ghp_secret" not in str(server)
        assert c.post("/api/catalog/github/install", json={"values": {}}).status_code == 400
        cat = c.get("/api/catalog").json()
        assert next(s for s in cat["servers"] if s["id"] == "github")["installed"] is True
    import sqlite3
    dump = "\n".join(sqlite3.connect(tmp_path / "vision.db").iterdump())
    assert "ghp_secret" not in dump


def test_one_broken_mcp_server_does_not_block_others(live):
    with client(live) as c:
        c.post("/api/mcp/servers", json={"name": "broken", "transport": "stdio", "command": "definitely-not-a-command", "args": []})
        sid = add_fake_mcp(c)
        for _ in range(50):
            states = {s["name"]: s["status"]["state"] for s in c.get("/api/mcp/servers").json()}
            if states.get("broken") == "error":
                break
            time.sleep(0.2)
        assert states["broken"] == "error" and states["fake"] == "connected"
        msg = next(s for s in c.get("/api/mcp/servers").json() if s["name"] == "broken")["status"]["message"]
        assert "not found" in msg.lower() or "No such file" in msg or "FileNotFound" in msg or "definitely" in msg


def test_toggle_disables_tools(live):
    with client(live) as c:
        sid = add_fake_mcp(c)
        from vision.mcp_hub import hub
        assert {"echo", "delete_note"} <= set(hub.tool_names())
        c.post(f"/api/mcp/servers/{sid}/enabled", json={"enabled": False})
        assert hub.tool_names() == []


def test_token_auth_is_enforced_when_configured(live, monkeypatch):
    monkeypatch.setenv("VISION_TOKEN", "s3cret")
    with client(live) as c:
        assert c.get("/api/health").status_code == 200  # health stays open for the launcher
        assert c.get("/api/profile").status_code == 401
        assert c.get("/api/profile", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert c.get("/api/profile", headers={"Authorization": "Bearer s3cret"}).status_code == 200
