import asyncio

from langchain_core.tools import StructuredTool

from vision import approvals


def make(name, meta=None):
    async def f(**kw):
        return f"ran:{name}"
    return StructuredTool(name=name, description="d", coroutine=f, args_schema={"type": "object", "properties": {}},
                          metadata=meta)


def test_policy_smart_mode():
    assert not approvals.needs_approval(make("read_file"), "smart")
    assert not approvals.needs_approval(make("list_directory"), "smart")
    assert not approvals.needs_approval(make("searchWeb"), "smart")
    assert approvals.needs_approval(make("write_file"), "smart")
    assert approvals.needs_approval(make("delete_note"), "smart")
    assert approvals.needs_approval(make("browser_click"), "smart")
    assert approvals.needs_approval(make("mystery_tool"), "smart")  # unknown = ask
    assert not approvals.needs_approval(make("mystery_tool", {"readOnlyHint": True}), "smart")
    assert approvals.needs_approval(make("get_thing", {"destructiveHint": True}), "smart")


def test_policy_always_and_never():
    assert approvals.needs_approval(make("read_file"), "always")
    assert not approvals.needs_approval(make("delete_all"), "never")


async def test_declined_action_is_not_executed():
    queue: asyncio.Queue = asyncio.Queue()
    approvals.event_sink.set(queue)
    tool = approvals.wrap_tool(make("delete_note"), server="s", mode="smart")
    run = asyncio.create_task(tool.ainvoke({}))
    ev = await queue.get()
    assert ev["type"] == "approval_request" and ev["tool"] == "delete_note"
    assert approvals.resolve(ev["id"], False)
    assert "declined" in await run


async def test_approved_action_runs():
    queue: asyncio.Queue = asyncio.Queue()
    approvals.event_sink.set(queue)
    tool = approvals.wrap_tool(make("delete_note"), server="s", mode="smart")
    run = asyncio.create_task(tool.ainvoke({}))
    ev = await queue.get()
    approvals.resolve(ev["id"], True)
    assert await run == "ran:delete_note"


async def test_no_ui_attached_means_refuse():
    approvals.event_sink.set(None)
    tool = approvals.wrap_tool(make("delete_note"), server="s", mode="smart")
    assert "declined" in await tool.ainvoke({})


async def test_read_only_tool_needs_no_approval():
    approvals.event_sink.set(None)
    tool = approvals.wrap_tool(make("read_file"), server="s", mode="smart")
    assert await tool.ainvoke({}) == "ran:read_file"
