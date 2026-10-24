"""Invoke the AgentCore runtime locally and print per-segment booking results.

SDK local mode: this starts the same ``BedrockAgentCoreApp`` as
``python -m booking.orchestrator.main`` and posts the sample plan to
``/invocations``. It does not import provider packages and it does not call AWS.

From the repository root:

    python3 -m pip install -r booking/orchestrator/requirements.txt
    PYTHONPATH=. python3 -m booking.orchestrator.demo
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_plan.json"
_MEMORY_ENV = ("AGENTCORE_MEMORY_ID", "MEMORY_BOOKINGMEMORY_ID")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_ready(port: int, timeout_s: float = 10) -> None:
    deadline = time.monotonic() + timeout_s
    url = f"http://127.0.0.1:{port}/ping"
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
            time.sleep(0.05)
    raise RuntimeError(f"AgentCore local runtime did not become ready: {last_error}")


def invoke_runtime(payload: dict) -> dict:
    """POST ``payload`` to the running Bedrock AgentCore app and return JSON."""

    import uvicorn

    from booking.orchestrator.main import app

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="agentcore-sdk-local", daemon=True)
    thread.start()
    try:
        _wait_until_ready(port)
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/invocations",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()
            raise RuntimeError(body or f"HTTP {exc.code}") from exc
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def main() -> int:
    saved = {name: os.environ.pop(name) for name in _MEMORY_ENV if name in os.environ}
    try:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        result = invoke_runtime(payload)
    finally:
        os.environ.update(saved)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
