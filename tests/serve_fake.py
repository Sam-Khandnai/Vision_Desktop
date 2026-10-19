"""Starts the real backend with a scripted fake model + the fake MCP server. Used by the UI smoke test.
Usage: uv run python tests/serve_fake.py <port>
"""
from __future__ import annotations

import sys
import tempfile
import os
import threading
import time

port = int(sys.argv[1])
os.environ["VISION_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import uvicorn

from vision import providers, secrets_store

secrets_store._keyring = lambda: None
from tests.conftest import FAKE_SERVER, FakeModel  # noqa: E402

fake = FakeModel()
providers.model_for = lambda provider: fake

from vision.main import app  # noqa: E402

server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
threading.Thread(target=server.run, daemon=True).start()
for _ in range(100):
    try:
        if httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=1).status_code == 200:
            break
    except httpx.HTTPError:
        time.sleep(0.1)
c = httpx.Client(base_url=f"http://127.0.0.1:{port}")
c.post("/api/providers", json={"name": "Fake", "base_url": "http://localhost:1/v1", "model_name": "fake-1", "api_key": "sk-test"})
c.post("/api/mcp/servers", json={"name": "fake", "transport": "stdio", "command": sys.executable, "args": [FAKE_SERVER]})
print("READY", flush=True)
while True:
    time.sleep(1)
