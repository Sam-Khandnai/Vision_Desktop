"""Actually starts every local (stdio) catalog server with placeholder values and lists its tools.
Needs internet (downloads packages through npx/uvx) and Node.js + uv. Remote servers are skipped.
Run: uv run python scripts/probe_catalog.py [id ...]       results: probe_results.json
Each server is probed in its own process, so one crash cannot affect the others.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

from vision import catalog

TIMEOUT = 240
PARALLEL = int(os.environ.get("PROBE_PARALLEL", "5"))


def sample_values(entry: dict, tmp: Path) -> dict[str, str]:
    values = {}
    for inp in entry["inputs"]:
        if inp["type"] == "path":
            values[inp["key"]] = str(tmp / inp["key"])
            (tmp / inp["key"]).mkdir(exist_ok=True)
        else:
            values[inp["key"]] = inp.get("default") or "placeholder"
    return values


def _flatten(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(dict.fromkeys(_flatten(e) for e in exc.exceptions))
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


async def probe(entry: dict, tmp: Path) -> dict:
    kw = catalog.build_server(entry, sample_values(entry, tmp))
    conn = {"transport": "stdio", "command": kw["config"]["command"], "args": kw["config"]["args"]}
    env = dict(kw["env"] or {})
    for name in ("UV_SYSTEM_CERTS", "UV_NATIVE_TLS", "SSL_CERT_FILE", "NODE_EXTRA_CA_CERTS"):
        if os.environ.get(name):  # MCP's stdio client does not forward most variables; needed behind TLS-inspecting proxies
            env[name] = os.environ[name]
    if env:
        conn["env"] = env
    started = time.monotonic()
    try:
        client = MultiServerMCPClient({entry["id"]: conn})
        tools = await asyncio.wait_for(client.get_tools(), TIMEOUT)
        return {"id": entry["id"], "ok": True, "tools": len(tools), "secs": round(time.monotonic() - started)}
    except BaseException as exc:  # includes ExceptionGroup from anyio
        if isinstance(exc, asyncio.CancelledError):
            raise
        msg = _flatten(exc)
        return {"id": entry["id"], "ok": False, "error": msg[:300], "secs": round(time.monotonic() - started)}


async def probe_one(entry_id: str) -> None:
    entry = catalog.get(entry_id)
    tmp = Path(tempfile.mkdtemp(prefix="vision-probe-"))
    try:
        result = await probe(entry, tmp)
    except BaseException as exc:  # never let anyio task-group noise escape
        result = {"id": entry_id, "ok": False, "error": _flatten(exc)[:300], "secs": 0}
    print("RESULT " + json.dumps(result), flush=True)


async def run_child(entry_id: str) -> dict:
    proc = await asyncio.create_subprocess_exec(
        sys.executable, __file__, "--one", entry_id,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), TIMEOUT + 60)
    except asyncio.TimeoutError:
        proc.kill()
        return {"id": entry_id, "ok": False, "error": "probe timed out", "secs": TIMEOUT + 60}
    for line in out.decode(errors="replace").splitlines():
        if line.startswith("RESULT "):
            return json.loads(line[7:])
    return {"id": entry_id, "ok": False, "error": "no result (process crashed)", "secs": 0}


async def main() -> None:
    wanted = set(sys.argv[1:])
    out = Path("probe_results.json")
    results: list[dict] = []
    if out.exists() and not wanted:  # resume: keep earlier results, probe only what is missing
        results = json.loads(out.read_text())
    done = {r["id"] for r in results}
    results = [r for r in results if r["id"] not in wanted]
    ids = [e["id"] for e in catalog.load()["servers"]
           if e["transport"] == "stdio" and (e["id"] in wanted if wanted else e["id"] not in done)]
    sem = asyncio.Semaphore(PARALLEL)

    async def run(entry_id: str) -> None:
        async with sem:
            r = await run_child(entry_id)
            results.append(r)
            print(("OK   " if r["ok"] else "FAIL ") + f"{r['id']:20} {r.get('tools', '')!s:>3} tools  {r['secs']}s  {r.get('error', '')}", flush=True)
            Path("probe_results.json").write_text(json.dumps(results, indent=1))

    await asyncio.gather(*(run(i) for i in ids))
    ok = sum(r["ok"] for r in results)
    print(f"\n{ok}/{len(results)} local servers started and listed tools", flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--one":
        asyncio.run(probe_one(sys.argv[2]))
    else:
        asyncio.run(main())
