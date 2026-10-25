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
# The service clock starts at 08:00Z on the trip start date and stops while on
# track, so it never reaches a segment end. Progress treats an attraction time
# as that segment's end. Tick 1 is 13:00Z on the start date: after the morning
# briefing (10:00Z, past the 45-minute grace, so the loop rebooks and stays
# open) and before the hotel's 15:00Z start, so a cancellation can still pull
# that hotel forward. Ticks 2 and 3 stay on that morning. The service clock
# would jump past the briefing and rebook it again, and the loop would stop
# before the early and late signals. The cap stays five ticks.
_DEMO_NOW = {
    1: "2026-11-02T13:00:00Z",
    2: "2026-11-02T10:30:00Z",
    3: "2026-11-02T10:40:00Z",
}
# One scripted replan signal per tick, on top of whatever trip_progress reports.
# ended_early is 60 minutes. ended_late is 45 minutes. A missing replan package
# is recorded as replan_not_installed and the demo still finishes.
# The loop also calls check_budget, authorize_spend(10, 12, USD),
# refund_booking, check_conflicts, and trip_notice. A missing guard package
# is recorded as <tool>_not_installed and the demo still finishes.
# Assist tools run the same way: a missing package is <tool>_not_installed
# and the demo still finishes. watch_trip is polled at the start of every tick.
# The sample flight, hotel, and temple are not one same-day chain. The demo
# adds a morning briefing (keeps the loop open), an afternoon garden after the
# temple, and a farewell tea after hotel checkout. Those are the later segments
# the three replan agents move.
_REPLAN_SIGNALS = {
    1: {
        "segmentId": "flight-1",
        "kind": "flight",
        "issue": "segment cancelled",
        "action": "replan",
        "event": "cancelled",
        "deltaMinutes": None,
    },
    2: {
        "segmentId": "hotel-1",
        "kind": "hotel",
        "issue": "segment ended early",
        "action": "replan",
        "event": "ended_early",
        "deltaMinutes": 60,
    },
    3: {
        "segmentId": "attraction-1",
        "kind": "attraction",
        "issue": "segment ended late",
        "action": "replan",
        "event": "ended_late",
        "deltaMinutes": 45,
    },
}


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
    """Service clock, except the scripted ticks use ``_DEMO_NOW``."""

    def clock(plan: dict, tick: int) -> dict:
        reported = original(plan, tick)
        now = _DEMO_NOW.get(tick)
        if now is not None:
            return {"tick": reported.get("tick", tick), "now": now}
        return reported

    return clock


def _with_later_segments(payload: dict) -> dict:
    """Add the later same-day visits the scripted replans move.

    Cancellation pulls the hotel, which starts later the same day as the flight.
    The farewell tea starts after hotel checkout, so an early finish can pull it
    forward. The garden walk starts after the temple, so a late finish can push
    it back.     The morning briefing is what progress rebooks on tick 1.
    Tick 1 is 13:00Z, so the riverside pause ends within 20 minutes and the
    night market is a later stop that same day. watch_trip warns, and the
    master requests that ride in the same tick.
    """

    plan = json.loads(json.dumps(payload))
    flights = plan.get("flights")
    if isinstance(flights, list):
        for flight in flights:
            if isinstance(flight, dict) and not isinstance(flight.get("international"), bool):
                flight["international"] = True
        # A later departure the sample tests do not pin. Tick clocks on
        # 2026-11-02 sit inside its 24 hour check-in window. The delayed
        # feed is only for this segment, so flight-1 stays booked.
        flights.append(
            {
                "segmentId": "flight-2",
                "kind": "flight",
                "from": "KIX",
                "to": "NRT",
                "departDate": "2026-11-03",
                "cabin": "economy",
                "travelerIds": ["t1"],
                "international": True,
            }
        )
    plan["flightFeeds"] = [
        {"tick": 1, "segmentId": "flight-2", "event": "delayed", "delayMinutes": 40},
    ]
    attractions = plan.get("attractions")
    if not isinstance(attractions, list):
        attractions = []
        plan["attractions"] = attractions
    attractions.extend(
        [
            {
                "segmentId": "attraction-2",
                "kind": "attraction",
                "name": "Sample morning briefing",
                "city": "Kyoto",
                "date": "2026-11-02",
                "partySize": 1,
                "time": "10:00",
            },
            {
                "segmentId": "attraction-3",
                "kind": "attraction",
                "name": "Sample garden walk",
                "city": "Kyoto",
                "date": "2026-11-03",
                "partySize": 1,
                "time": "13:00",
                "outdoor": True,
            },
            {
                "segmentId": "attraction-4",
                "kind": "attraction",
                "name": "Sample farewell tea",
                "city": "Kyoto",
                "date": "2026-11-06",
                "partySize": 1,
                "time": "12:00",
                "meal": True,
                "reservationAt": "2026-11-06T11:00:00Z",
                "arriveAt": "2026-11-06T12:00:00Z",
            },
            {
                "segmentId": "attraction-5",
                "kind": "attraction",
                "name": "Sample riverside pause",
                "city": "Kyoto",
                "date": "2026-11-02",
                "partySize": 1,
                "time": "13:00",
                "start": "2026-11-02T12:55:00Z",
                "end": "2026-11-02T13:10:00Z",
            },
            {
                "segmentId": "attraction-6",
                "kind": "attraction",
                "name": "Sample night market",
                "city": "Kyoto",
                "date": "2026-11-02",
                "partySize": 1,
                "time": "18:00",
                "start": "2026-11-02T18:00:00Z",
                "end": "2026-11-02T19:00:00Z",
            },
        ]
    )
    return plan


def _with_replan_signal(report: object, tick: object) -> object:
    """Append the scripted replan update for this tick. Leave any other report alone."""

    if not isinstance(report, dict) or not isinstance(tick, int):
        return report
    signal = _REPLAN_SIGNALS.get(tick)
    if signal is None:
        return report
    updates = report.get("updates")
    merged = dict(report)
    merged["updates"] = [*(updates if isinstance(updates, list) else []), dict(signal)]
    return merged


def _demo_signals(plan: dict, clock: dict) -> list:
    """The scripted replan signal for this tick, passed through to watch_trip."""

    del plan
    tick = clock.get("tick") if isinstance(clock, dict) else None
    signal = _REPLAN_SIGNALS.get(tick)
    if signal is None:
        return []
    return [dict(signal)]


def _demo_progress(original):
    """Forward the clock's ``now`` string, then add this tick's scripted replan signal.

    ``trip_progress`` does not read a clock object.
    """

    def progress(plan: dict, results: list, clock: dict):
        now = clock.get("now") if isinstance(clock, dict) else clock
        tick = clock.get("tick") if isinstance(clock, dict) else None
        return _with_replan_signal(original(plan, results, now), tick)

    return progress


def invoke_runtime(payload: dict) -> dict:
    """POST ``payload`` to the running Bedrock AgentCore app and return JSON."""

    import uvicorn

    from booking.master import service as master_service
    from booking.master.main import app

    original_clock = master_service._clock
    original_progress = master_service.trip_progress
    original_signals = master_service._signals
    master_service._clock = _demo_clock(original_clock)
    master_service.trip_progress = _demo_progress(original_progress)
    master_service._signals = _demo_signals
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
        master_service._signals = original_signals
    if not isinstance(body, dict):
        raise RuntimeError("AgentCore runtime returned a non-object response")
    return body


def _proof_lines(tick: dict) -> list[str]:
    """One readable line per concierge result recorded on this tick."""

    lines: list[str] = []
    for item in _as_list(tick.get("flightStatus")):
        if not isinstance(item, dict):
            lines.append(f"flightStatus={item}")
            continue
        lines.append(
            "flightStatus "
            f"segmentId={item.get('segmentId')} event={item.get('event')} "
            f"delayMinutes={item.get('delayMinutes')} action={item.get('action')}"
        )
    for item in _as_list(tick.get("checkIn")):
        if not isinstance(item, dict):
            lines.append(f"checkIn={item}")
            continue
        if isinstance(item.get("boardingPass"), str):
            lines.append(
                f"checkIn segmentId={item.get('segmentId')} status={item.get('status')} "
                f"boardingPass={item.get('boardingPass')}"
            )
    dcc = tick.get("dcc")
    if isinstance(dcc, dict):
        lines.append(
            f"dcc refused={dcc.get('refused')} payAmount={dcc.get('payAmount')} "
            f"payCurrency={dcc.get('payCurrency')} reason={dcc.get('reason')}"
        )
    card = tick.get("card")
    if isinstance(card, dict):
        lines.append(
            f"card cardId={card.get('cardId')} feeAmount={card.get('feeAmount')} "
            f"reason={card.get('reason')}"
        )
    cash = tick.get("cash")
    if isinstance(cash, dict):
        amount = cash.get("tripAmount")
        shown = f"{amount:.2f}" if isinstance(amount, (int, float)) and not isinstance(amount, bool) else amount
        lines.append(
            f"cash action={cash.get('action')} tripAmount={shown} {cash.get('tripCurrency')}"
        )
    for item in _as_list(tick.get("holiday")):
        if isinstance(item, dict) and item.get("holiday") == "Culture Day":
            lines.append(
                f"holiday segmentId={item.get('segmentId')} closed={item.get('closed')} "
                f"holiday={item.get('holiday')} action={item.get('action')}"
            )
    layover = tick.get("layover")
    if isinstance(layover, dict):
        lines.append(
            f"layover action={layover.get('action')} shortfallMinutes={layover.get('shortfallMinutes')}"
        )
    etiquette = tick.get("etiquette")
    if isinstance(etiquette, dict):
        lines.append(f"etiquette phrase={etiquette.get('phrase')}")
    tax = tick.get("taxRefund")
    if isinstance(tax, dict):
        lines.append(
            f"taxRefund refundAmount={tax.get('refundAmount')} {tax.get('refundCurrency')} "
            "quote=not_tax_advice"
        )
    for item in _as_list(tick.get("segmentRebook")):
        if not isinstance(item, dict):
            lines.append(f"segmentRebook={item}")
            continue
        replacement = item.get("replacement") if isinstance(item.get("replacement"), dict) else {}
        lines.append(
            f"segmentRebook segmentId={item.get('segmentId')} "
            f"confirmationCode={replacement.get('confirmationCode')} "
            f"kind={replacement.get('kind')} departDate={replacement.get('departDate')} "
            f"date={replacement.get('date')}"
        )
    hold = tick.get("hold")
    if isinstance(hold, dict):
        lines.append(
            f"hold releaseAmount={hold.get('releaseAmount')} reason={hold.get('reason')} charged=false"
        )
    over = tick.get("holdOver")
    if isinstance(over, dict):
        lines.append(
            f"holdOver payAmount={over.get('payAmount')} reason={over.get('reason')} charged=false"
        )
    for item in _as_list(tick.get("landing")):
        if not isinstance(item, dict):
            lines.append(f"landing={item}")
            continue
        lines.append(f"landing planCode={item.get('planCode')} action={item.get('action')}")
    return lines


def _as_list(value: object) -> list:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


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
    spend = result.get("spend") if isinstance(result.get("spend"), dict) else None
    if spend is not None:
        print(
            f"spend payAmount={spend.get('payAmount')} reason={spend.get('reason')}",
            file=out,
        )
    for label in ("entry", "fx", "tip", "emergency", "weather", "transfer", "luggage", "table", "checkout"):
        if label in result:
            print(f"{label}={result.get(label)}", file=out)
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
        if "notice" in tick:
            print(f"  notice={tick.get('notice')}", file=out)
        if "watch" in tick:
            print(f"  watch={tick.get('watch')}", file=out)
        if "airport" in tick:
            print(f"  airport={tick.get('airport')}", file=out)
        if "afterDark" in tick:
            print(f"  afterDark={tick.get('afterDark')}", file=out)
        if "phrase" in tick:
            print(f"  phrase={tick.get('phrase')}", file=out)
        if "rides" in tick:
            print(f"  rides={tick.get('rides')}", file=out)
        if "wallet" in tick:
            print(f"  wallet={tick.get('wallet')}", file=out)
        for line in _proof_lines(tick):
            print(f"  {line}", file=out)
        if tick.get("warnings"):
            print(f"  warnings={tick.get('warnings')}", file=out)
        for update in updates:
            if not isinstance(update, dict):
                continue
            suffix = ""
            if update.get("action") == "replan" or "replan" in update:
                suffix = (
                    f" event={update.get('event')} deltaMinutes={update.get('deltaMinutes')}"
                    f" replan={update.get('replan')}"
                )
                if "notes" in update:
                    suffix += f" notes={update.get('notes')}"
            print(
                "  update "
                f"segmentId={update.get('segmentId')} kind={update.get('kind')} "
                f"issue={update.get('issue')} action={update.get('action')}{suffix}",
                file=out,
            )


def main() -> int:
    saved = {name: os.environ.pop(name) for name in _SANDBOX_ENV if name in os.environ}
    try:
        payload = _with_later_segments(json.loads(FIXTURE.read_text(encoding="utf-8")))
        result = invoke_runtime(payload)
    finally:
        os.environ.update(saved)
    write_trace(result)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
