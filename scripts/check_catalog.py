"""Checks the catalog against the real registries (needs internet):
  * the npm / PyPI package exists,
  * every environment variable and --flag we pass is mentioned in the package's README.
Run: uv run python scripts/check_catalog.py [--verbose]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import quote

import httpx

CATALOG = Path(__file__).resolve().parents[1] / "src" / "vision" / "data" / "mcp_catalog.json"


def fetch(client: httpx.Client, reg: str, pkg: str) -> tuple[bool, str, str]:
    if reg == "npm":
        r = client.get(f"https://registry.npmjs.org/{quote(pkg, safe='@')}")
        if r.status_code != 200:
            return False, "", ""
        data = r.json()
        latest = data.get("dist-tags", {}).get("latest", "")
        ver = data.get("versions", {}).get(latest, {})
        return True, (data.get("readme") or "") + (ver.get("description") or ""), data.get("description", "")
    r = client.get(f"https://pypi.org/pypi/{pkg}/json")
    if r.status_code != 200:
        return False, "", ""
    info = r.json()["info"]
    return True, (info.get("description") or "") + (info.get("summary") or ""), info.get("summary") or ""


def main() -> int:
    verbose = "--verbose" in sys.argv
    servers = json.loads(CATALOG.read_text(encoding="utf-8"))["servers"]
    missing_pkg, warnings = [], []
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for s in servers:
            reg, pkg = s.get("registry"), s.get("package")
            if not reg:
                continue
            try:
                ok, text, summary = fetch(client, reg, pkg)
            except httpx.HTTPError:
                ok, text, summary = False, "", ""
            if not ok:
                print("MISS ", s["id"], pkg)
                missing_pkg.append(s["id"])
                continue
            names = [i["name"] for i in s["inputs"] if i["target"] == "env"] + list(s.get("env_static", {}))
            flags = [a.split("=")[0] for a in s.get("args", []) if a.startswith("--") and "{{" not in a]
            lacking = [n for n in names + flags if n not in text]
            status = "OK   " if not lacking else "WARN "
            if lacking:
                warnings.append((s["id"], lacking))
            print(status, s["id"], pkg, ("-> not in README: " + ", ".join(lacking)) if lacking else "")
            if verbose:
                print("       ", summary[:110])
    print(f"\n{len(servers)} entries | packages missing: {len(missing_pkg)} | entries with unverified env/flags: {len(warnings)}")
    print("Remote servers (URL-based) cannot be checked from here.")
    return 1 if missing_pkg else 0


if __name__ == "__main__":
    sys.exit(main())
