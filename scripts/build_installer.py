"""Build the Vision installer for the OS you are running on.

    uv run python scripts/build_installer.py            # full installer  -> desktop/release/
    uv run python scripts/build_installer.py --dir      # unpacked app only (quick test, no installer)
    uv run python scripts/build_installer.py --no-node  # do not bundle Node.js (smaller installer)
    uv run python scripts/build_installer.py --backend-only   # only freeze + self-test the engine

Steps: 1) freeze the Python engine with PyInstaller  2) self-test the frozen engine
       3) copy uv (and Node.js on Windows) next to it  4) build the UI  5) electron-builder.
Windows installers must be built on Windows, macOS ones on a Mac, Linux ones on Linux.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"
STAGE = ROOT / "build" / "stage"
WIN = sys.platform == "win32"
EXE = "vision-server.exe" if WIN else "vision-server"


def run(cmd: list[str], cwd: Path = ROOT, env: dict | None = None) -> None:
    print("\n>", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=cwd, check=True, env={**os.environ, **(env or {})})


def need(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        sys.exit(f"'{tool}' was not found on PATH. Install it first, then run this script again.")
    return path


def freeze_backend() -> None:
    uv = need("uv")
    sep = os.pathsep
    collect = ["langchain", "langchain_core", "langchain_openai", "langchain_mcp_adapters", "langgraph",
               "uvicorn", "keyring", "anyio", "tiktoken_ext", "vision"]
    cmd = [uv, "run", "--with", "pyinstaller", "pyinstaller", "scripts/server_entry.py",
           "--name", "vision-server", "--onedir", "--noconfirm", "--clean",
           "--distpath", str(STAGE), "--workpath", str(ROOT / "build" / "pyi"), "--specpath", str(ROOT / "build"),
           "--paths", "src", "--add-data", f"{ROOT / 'src' / 'vision' / 'data'}{sep}vision/data",
           "--copy-metadata", "keyring", "--hidden-import", "tiktoken_ext.openai_public",
           "--hidden-import", "mcp.client.stdio", "--hidden-import", "mcp.client.sse",
           "--hidden-import", "mcp.client.streamable_http", "--exclude-module", "mcp.cli"]
    for pkg in collect:
        cmd += ["--collect-submodules", pkg]
    for pkg in ("langchain", "langchain_core", "langgraph"):  # these also read data files at runtime
        cmd += ["--collect-data", pkg]
    if WIN:
        cmd += ["--collect-submodules", "win32ctypes"]
    run(cmd)


def selftest_backend() -> None:
    exe = STAGE / "vision-server" / EXE
    if not exe.exists():
        sys.exit(f"Freezing failed: {exe} not found.")
    out = subprocess.run([str(exe), "--check"], capture_output=True, text=True, timeout=180)
    lines = [l for l in out.stdout.splitlines() if l.startswith("{")]
    if out.returncode != 0 or not lines:
        sys.exit(f"Self-test of the frozen engine crashed:\n{out.stdout}\n{out.stderr[-3000:]}")
    info = json.loads(lines[-1])
    print("self-test:", info)
    problems = []
    if info.get("agent") != "ok":
        problems.append(f"agent: {info.get('agent')}")
    if info.get("catalog", 0) < 90:
        problems.append("MCP catalog data file is missing from the build")
    if sys.platform in ("win32", "darwin") and info.get("secrets") != "os-keychain":
        problems.append(f"API keys would NOT go to the system credential store (backend: {info.get('secrets')})")
    if problems:
        sys.exit("Self-test failed:\n  - " + "\n  - ".join(problems))
    print("frozen engine OK")


def copy_tools(with_node: bool) -> None:
    tools = STAGE / "tools"
    shutil.rmtree(tools, ignore_errors=True)
    tools.mkdir(parents=True)
    uv_dir = tools / "uv"
    uv_dir.mkdir()
    for name in ("uv", "uvx"):
        src = shutil.which(name)
        if src:
            shutil.copy2(src, uv_dir / Path(src).name)
        else:
            print(f"warning: {name} not found, uvx-based MCP servers will need uv installed by the user")
    if with_node and WIN:
        node = shutil.which("node")
        if node:
            src_dir = Path(node).parent
            if (src_dir / "node_modules" / "npm").exists():
                print("bundling Node.js from", src_dir)
                shutil.copytree(src_dir, tools / "node", ignore=shutil.ignore_patterns("*.log", "uninstall*", "*.md", "LICENSE"))
            else:
                print("warning: npm folder not found next to node.exe, not bundling Node.js")
        else:
            print("warning: node not found, not bundling Node.js")
    elif with_node:
        print("note: Node.js is only bundled on Windows; on this OS npx servers use the user's own Node.js")


def build_app(unpacked: bool, publish: bool = False) -> None:
    npm = need("npm")
    if not (DESKTOP / "node_modules").exists():
        run([npm, "install"], cwd=DESKTOP)
    run([npm, "run", "build"], cwd=DESKTOP)
    cmd = [need("npx"), "electron-builder"] + (["--dir"] if unpacked else [])
    cmd += ["--publish", "always"] if publish else ["--publish", "never"]
    run(cmd, cwd=DESKTOP, env={"CSC_IDENTITY_AUTO_DISCOVERY": "false"})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", action="store_true", help="unpacked app only, no installer")
    ap.add_argument("--no-node", action="store_true", help="do not bundle Node.js")
    ap.add_argument("--backend-only", action="store_true")
    ap.add_argument("--publish", action="store_true", help="upload the installer to GitHub Releases (needs GH_TOKEN)")
    a = ap.parse_args()
    STAGE.mkdir(parents=True, exist_ok=True)
    freeze_backend()
    selftest_backend()
    if a.backend_only:
        return
    copy_tools(with_node=not a.no_node)
    build_app(unpacked=a.dir, publish=a.publish)
    print("\nDone. Output:", DESKTOP / "release")


if __name__ == "__main__":
    main()
