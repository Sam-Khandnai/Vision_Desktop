from vision import db, memory


def test_add_fact_dedupes_similar_text():
    assert memory.add_fact("User is a Python developer")
    assert not memory.add_fact("the user is a python developer")
    assert memory.add_fact("User prefers dark themes")
    assert len(memory.list_memories()) == 2


def test_retrieve_english_and_persian():
    memory.add_fact("User works on a FastAPI backend")
    memory.add_fact("کاربر برنامه نویس هوش مصنوعی است")
    assert memory.retrieve("how do I structure my fastapi project?") == ["User works on a FastAPI backend"]
    assert memory.retrieve("من برنامه نویس هستم")  # matches the Persian fact on shared words
    assert memory.retrieve("completely unrelated cooking question") == []


def test_delete_memory_removes_from_search():
    memory.add_fact("User likes turquoise")
    mid = memory.list_memories()[0]["id"]
    memory.delete_memory(mid)
    assert memory.retrieve("turquoise") == []


def test_parse_fact_list_is_tolerant():
    assert memory.parse_fact_list('Here: ["a fact", "another"] done') == ["a fact", "another"]
    assert memory.parse_fact_list("nothing") == []
    assert memory.parse_fact_list("[not json]") == []


def _conv_with_messages(n, size=3000):
    cid = db.new_id()
    with db.connect() as conn:
        conn.execute("INSERT INTO conversations(id, title, created_at, updated_at) VALUES(?,?,?,?)", (cid, "t", 0, 0))
        for i in range(n):
            conn.execute("INSERT INTO messages(conversation_id, role, content, created_at) VALUES(?,?,?,?)",
                         (cid, "user" if i % 2 == 0 else "assistant", f"m{i} " + "x" * size, 0))
    return cid


def test_build_context_respects_token_budget_and_starts_with_user():
    cid = _conv_with_messages(20)
    summary, msgs = memory.build_context(cid)
    assert summary == ""
    assert 0 < len(msgs) < 20
    assert msgs[0]["role"] == "user"
    assert msgs[-1]["content"].startswith("m19")


async def test_summarization_folds_old_messages():
    from tests.conftest import FakeModel

    cid = _conv_with_messages(20)
    assert await memory.maybe_summarize(FakeModel(), cid)
    summary, msgs = memory.build_context(cid)
    assert summary == "SUMMARY-OK"
    assert len(msgs) <= memory.KEEP_RECENT_MESSAGES
