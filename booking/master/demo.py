"""Run the master AgentCore runtime locally and print the control loop.

SDK local mode: this starts the same BedrockAgentCoreApp as
``python -m booking.master.main`` and posts the sample plan to ``/invocations``.
No AWS credentials and no Amadeus keys.

From the repository root:

    python3 -m pip install -r booking/master/requirements.txt
    PYTHONPATH=. python3 -m booking.master.demo
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
_SANDBOX_ENV = (
    "AGENTCORE_MEMORY_ID",
    "MEMORY_BOOKINGMEMORY_ID",
    "ROAM_FLIGHT_PROVIDER",
    "ROAM_HOTEL_PROVIDER",
    "ROAM_ATTRACTION_PROVIDER",
)
# The sample attraction ends at 09:00Z on 2026-11-03. The service clock starts at
# 08:00Z on the trip start date and stops while on track, so it never reaches a
# segment end. This demo keeps that clock, then moves tick 1 to 60 minutes after
# the attraction end (more than the 45-minute grace) and passes that timestamp
# as ``now``. Later ticks stay on the service clock. The cap stays five ticks.
_DEMO_LATE_TICK = 1
_DEMO_LATE_NOW = "2026-11-03T10:00:00Z"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_ready(port: int, timeout_s: float = 15) -> None:
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


def _demo_clock(original):
    """Service clock, except one tick is after a sample segment end."""

    def clock(plan: dict, tick: int) -> dict:
        reported = original(plan, tick)
        if tick == _DEMO_LATE_TICK:
            return {"tick": reported.get("tick", tick), "now": _DEMO_LATE_NOW}
        return reported

    return clock


def _demo_progress(original):
    """Forward the clock's ``now`` string. ``trip_progress`` does not read a clock object."""

    def progress(plan: dict, results: list, clock: dict):
        now = clock.get("now") if isinstance(clock, dict) else clock
        return original(plan, results, now)

    return progress


def invoke_runtime(payload: dict) -> dict:
    """POST ``payload`` to the running Bedrock AgentCore app and return JSON."""

    import uvicorn

    from booking.master import service as master_service
    from booking.master.main import app

    original_clock = master_service._clock
    original_progress = master_service.trip_progress
    master_service._clock = _demo_clock(original_clock)
    master_service.trip_progress = _demo_progress(original_progress)
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="agentcore-master-local", daemon=True)
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
                body = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()
            raise RuntimeError(detail or f"HTTP {exc.code}") from exc
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        master_service._clock = original_clock
        master_service.trip_progress = original_progress
    if not isinstance(body, dict):
        raise RuntimeError("AgentCore runtime returned a non-object response")
    return body


def write_trace(result: dict, stream: object | None = None) -> None:
    """Print one line per tick and one line per recorded update."""

    out = stream or sys.stderr
    stopped = result.get("loopStopped")
    ticks = result.get("ticks") if isinstance(result.get("ticks"), list) else []
    results = result.get("results") if isinstance(result.get("results"), list) else []
    for item in results:
        if not isinstance(item, dict):
            continue
        print(
            f"segment {item.get('segmentId')} status={item.get('status')} emailVerified={item.get('emailVerified')}",
            file=out,
        )
    print(f"master loop stopped={stopped} ticks={len(ticks)} maxTicks={result.get('maxTicks')}", file=out)
    for tick in ticks:
        if not isinstance(tick, dict):
            continue
        clock = tick.get("clock") if isinstance(tick.get("clock"), dict) else {}
        updates = tick.get("updates") if isinstance(tick.get("updates"), list) else []
        print(
            f"tick {tick.get('tick')} now={clock.get('now')} phase={tick.get('phase')} onTrack={tick.get('onTrack')} updates={len(updates)}",
            file=out,
        )
        for update in updates:
            if not isinstance(update, dict):
                continue
            print(
                "  update "
                f"segmentId={update.get('segmentId')} kind={update.get('kind')} "
                f"issue={update.get('issue')} action={update.get('action')}",
                file=out,
            )


def main() -> int:
    saved = {name: os.environ.pop(name) for name in _SANDBOX_ENV if name in os.environ}
    try:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        result = invoke_runtime(payload)
    finally:
        os.environ.update(saved)
    write_trace(result)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
