"""Three layers of memory.

1. Short-term   - the most recent messages of the conversation (token-budgeted).
2. Rolling summary - older messages of a long conversation are compressed into a summary.
3. Long-term    - durable facts about the user, extracted every few turns and retrieved with FTS5.

Everything lives in the local SQLite file; nothing leaves the machine except the model calls themselves.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from . import db

logger = logging.getLogger(__name__)

HISTORY_TOKEN_BUDGET = 6000      # raw history handed to the model
SUMMARY_TRIGGER_TOKENS = 8000    # when un-summarised history exceeds this, compress it
KEEP_RECENT_MESSAGES = 6         # never summarise the last N messages
EXTRACT_EVERY_N_USER_MESSAGES = 3
MAX_FACTS_PER_EXTRACTION = 5
MEMORY_LIMIT = 300

_REMEMBER_TRIGGER = re.compile(r"(remember|don'?t forget|یادت باشه|یادت\s*باشد|به\s*خاطر\s*بسپار|فراموش\s*نکن|یادداشت\s*کن)", re.I)


def est_tokens(text: str) -> int:
    return max(1, len(text) // 3)


# ---------- long-term facts ----------

def _norm_tokens(text: str) -> set[str]:
    return set(re.findall(r"\w{2,}", text.lower()))


def _similar(a: str, b: str) -> bool:
    ta, tb = _norm_tokens(a), _norm_tokens(b)
    if not ta or not tb:
        return a.strip().lower() == b.strip().lower()
    return len(ta & tb) / len(ta | tb) >= 0.7


def list_memories() -> list[dict[str, Any]]:
    with db.connect() as conn:
        return [dict(r) for r in conn.execute("SELECT id, text, created_at FROM memories ORDER BY id DESC")]


def add_fact(text: str, conversation_id: str = "") -> bool:
    text = " ".join((text or "").split())[:400]
    if len(text) < 4:
        return False
    with db.connect() as conn:
        existing = [r["text"] for r in conn.execute("SELECT text FROM memories")]
        if any(_similar(text, e) for e in existing):
            return False
        if len(existing) >= MEMORY_LIMIT:
            conn.execute("DELETE FROM memories WHERE id=(SELECT MIN(id) FROM memories)")
        conn.execute(
            "INSERT INTO memories(text, source_conversation, created_at) VALUES(?,?,?)",
            (text, conversation_id, db.now()),
        )
    return True


def delete_memory(memory_id: int) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))


def clear_memories() -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM memories")


def _fts_query(text: str) -> str:
    words = sorted(set(re.findall(r"\w{2,}", text.lower())), key=len, reverse=True)[:8]
    return " OR ".join(f'"{w}"' for w in words)


def retrieve(query: str, limit: int = 6) -> list[str]:
    q = _fts_query(query)
    if not q:
        return []
    with db.connect() as conn:
        try:
            rows = conn.execute(
                "SELECT m.text FROM memories_fts f JOIN memories m ON m.id=f.rowid "
                "WHERE memories_fts MATCH ? ORDER BY bm25(memories_fts) LIMIT ?",
                (q, limit),
            ).fetchall()
        except Exception:
            logger.warning("Memory search failed", exc_info=True)
            return []
    return [r["text"] for r in rows]


# ---------- conversation context ----------

def build_context(conversation_id: str, budget: int | None = None) -> tuple[str, list[dict[str, str]]]:
    """Return (summary, recent messages) for a conversation, trimmed to the token budget."""
    with db.connect() as conn:
        conv = conn.execute("SELECT summary, summary_upto FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        rows = conn.execute(
            "SELECT id, role, content FROM messages WHERE conversation_id=? AND id>? AND role IN ('user','assistant') "
            "AND content<>'' ORDER BY id",
            (conversation_id, conv["summary_upto"] if conv else 0),
        ).fetchall()
    messages = [{"role": r["role"], "content": r["content"]} for r in rows]
    total = 0
    kept: list[dict[str, str]] = []
    for msg in reversed(messages):
        total += est_tokens(msg["content"])
        if total > (budget or HISTORY_TOKEN_BUDGET) and kept:
            break
        kept.append(msg)
    kept.reverse()
    while kept and kept[0]["role"] != "user":  # providers dislike a leading assistant turn
        kept.pop(0)
    return (conv["summary"] if conv else ""), kept


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return str(content)


async def maybe_summarize(model: Any, conversation_id: str, trigger: int | None = None) -> bool:
    with db.connect() as conn:
        conv = conn.execute("SELECT summary, summary_upto FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        if not conv:
            return False
        rows = conn.execute(
            "SELECT id, role, content FROM messages WHERE conversation_id=? AND id>? AND role IN ('user','assistant') "
            "ORDER BY id",
            (conversation_id, conv["summary_upto"]),
        ).fetchall()
    if len(rows) <= KEEP_RECENT_MESSAGES:
        return False
    if sum(est_tokens(r["content"]) for r in rows) < (trigger or SUMMARY_TRIGGER_TOKENS):
        return False
    old = rows[:-KEEP_RECENT_MESSAGES]
    transcript = "\n".join(f"{r['role']}: {r['content'][:2000]}" for r in old)
    prompt = (
        "Update the running summary of a conversation between a user and an AI assistant.\n"
        "Keep decisions, facts, file names, code identifiers, open tasks and the user's goals. "
        "Write compactly in the language the conversation uses (max ~250 words).\n\n"
        f"Current summary:\n{conv['summary'] or '(none)'}\n\nNew messages to fold in:\n{transcript}\n\nUpdated summary:"
    )
    result = await model.ainvoke(prompt)
    summary = _content_text(result.content).strip()
    if not summary:
        return False
    with db.connect() as conn:
        conn.execute(
            "UPDATE conversations SET summary=?, summary_upto=? WHERE id=?",
            (summary, old[-1]["id"], conversation_id),
        )
    return True


# ---------- fact extraction ----------

def should_extract(conversation_id: str, last_user_text: str) -> bool:
    if _REMEMBER_TRIGGER.search(last_user_text or ""):
        return True
    with db.connect() as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id=? AND role='user'", (conversation_id,)
        ).fetchone()[0]
    return n > 0 and n % EXTRACT_EVERY_N_USER_MESSAGES == 0


def parse_fact_list(text: str) -> list[str]:
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    return [str(x) for x in data if isinstance(x, (str, int, float)) and str(x).strip()]


async def extract_facts(model: Any, conversation_id: str) -> int:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id=? AND role IN ('user','assistant') "
            "ORDER BY id DESC LIMIT 6",
            (conversation_id,),
        ).fetchall()
    if not rows:
        return 0
    transcript = "\n".join(f"{r['role']}: {r['content'][:1500]}" for r in reversed(rows))
    prompt = (
        "From the conversation below, extract durable facts about the USER that would help an assistant in "
        "future conversations: their name, job, projects, tools and languages they use, preferences, goals, "
        "constraints.\n"
        "Rules: ignore passwords, API keys, tokens and other secrets; ignore one-off requests and anything "
        "about the assistant; do not store sensitive details (health, finances, identity documents) unless "
        "the user explicitly asked to be remembered; each fact is one short sentence written in the user's "
        f"language; at most {MAX_FACTS_PER_EXTRACTION} facts.\n"
        "Reply with ONLY a JSON array of strings, or [] if there is nothing worth keeping.\n\n"
        f"Conversation:\n{transcript}"
    )
    result = await model.ainvoke(prompt)
    added = 0
    for fact in parse_fact_list(_content_text(result.content))[:MAX_FACTS_PER_EXTRACTION]:
        if add_fact(fact, conversation_id):
            added += 1
    return added
