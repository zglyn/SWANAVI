# Master booking agent

The planner calls this runtime and no other booking entry. The master manages the trip by calling capability agents. Flight booking, hotel booking, attraction booking, confirmation-email verification, and trip progress each live in their own package. This folder does not implement those capabilities, and it does not replan the itinerary.

The runtime is one [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) app: `BedrockAgentCoreApp` in `booking/master/main.py`. A finished trip plan is posted to that runtime. The entrypoint books every segment, checks the sandbox provider email for each booked segment, then runs a control loop of at most five ticks.

Nothing in this folder has been deployed to AWS. The local demo needs no AWS credentials and no Amadeus keys.

## What the master calls

| When | Tool on this runtime | Capability package | Function it calls |
| --- | --- | --- | --- |
| Each flight segment | `book_flight` | `booking.providers.flights` | `book(segment, travelers, trip_id)` |
| Each hotel segment | `book_hotel` | `booking.providers.hotels` | `book(segment, travelers, trip_id)` |
| Each attraction segment | `book_attraction` | `booking.providers.attractions` | `book_attraction(segment, travelers, trip_id)` or `book(...)` |
| Booked flight | `verify_flight_email` | `booking.verify.flights` | `sample_email(...)`, then `verify(...)` |
| Booked hotel | `verify_hotel_email` | `booking.verify.hotels` | `sample_email(...)`, then `verify(...)` |
| Booked attraction | `verify_attraction_email` | `booking.verify.attractions` | `sample_email(...)`, then `verify(...)` |
| Each loop tick | `trip_progress` | `booking.progress` | `trip_progress(plan, results, clock)` |

Provider tool input is the segment object from the plan (`from` stays `from` on flights), the traveler list `[{id, name}, ...]`, and `tripId`.

### Sandbox email

Sandbox does not read a real inbox. For a segment whose booking status is `booked`, the master asks that verifier for `sample_email(segment, confirmation_code, travelers, trip_id)` and treats the returned message as the email the traveler received. It then calls `verify(email, segment, confirmation_code, travelers)`.

`email` is `{from, to, subject, body, receivedAt}`. `verify` returns `{segmentId, kind, verified, reason}`.

The master accepts a segment only when `status` is `booked` and `verified` is true (`emailVerified` on the master result). `segment_accepted` in `booking/master/service.py` is that rule.

When `booking.verify.flights`, `booking.verify.hotels`, or `booking.verify.attractions` cannot be imported, or does not export both `sample_email` and `verify`, that segment stays `emailVerified: false` with `reason: "verifier_not_installed"`. The other segments still run.

### Control loop

After that first pass, the master starts a simulated clock at 08:00Z on `dates.start` and advances it three hours per tick. The clock is not the wall clock. Each tick calls:

```python
trip_progress(plan, results, clock) -> {
    "phase": str,
    "onTrack": bool,
    "updates": [
        {"segmentId": str, "kind": str, "issue": str, "action": "none" | "rebook" | "verify_email"}
    ],
}
```

`plan` is the planner's trip plan. The master does not add, drop, or rewrite segments. `results` are the current per-segment results. `clock` is `{"tick": <n>, "now": "<YYYY-MM-DDTHH:MM:SSZ>"}`.

| `action` | What the master does |
| --- | --- |
| `none` | Records the update. |
| `rebook` | Calls that segment's `book_*` tool again with the original segment. |
| `verify_email` | Calls that segment's `verify_*_email` tool (sandbox `sample_email`, then `verify`). |

The loop stops at five ticks. It also stops when `onTrack` is true and the tick has no `rebook` or `verify_email` action. When `booking.progress` is missing, or it has no `trip_progress` callable, the master records one update with `issue: "progress_not_installed"` and `action: "none"`, then ends the loop. A progress exception is recorded and ends the loop the same way. The process keeps going.

A segment that is rebooked during the loop is not accepted until a later `verify_email` action returns `verified: true`. Its `reason` is `rebooked` until then.

## Per-segment result

| Field | Values |
| --- | --- |
| `segmentId` | From the plan |
| `kind` | `flight`, `hotel`, or `attraction` |
| `status` | `booked`, `failed`, or `needs_user` from the booking tool |
| `confirmationCode` | Sandbox code from the booking tool, or `null` |
| `emailVerified` | `true` only when `verify` returned `verified: true` |
| `reason` | Verifier reason, `verifier_not_installed`, `rebooked`, or the booking error |

The runtime returns:

```json
{
  "tripId": "sample-kyoto",
  "results": [],
  "ticks": [],
  "maxTicks": 5,
  "loopStopped": "progress_not_installed",
  "error": null
}
```

`error` is `invalid_plan` when the payload is not a trip plan. `results` and `ticks` are then empty. `loopStopped` is `progress_not_installed`, `on_track`, `max_ticks`, `progress_error`, or `invalid_plan`.

Each tick is `{tick, clock, phase, onTrack, updates}`.

## Local demo (AgentCore SDK local mode, no AWS)

From the repository root:

```bash
python3 -m pip install -r booking/master/requirements.txt
PYTHONPATH=. python3 -m booking.master.demo
```

That command starts the Bedrock AgentCore app (the same server as `python3 -m booking.master.main`) and posts `booking/master/fixtures/sample_plan.json` to `POST /invocations`. Stderr prints each tick and each recorded update. Stdout is the JSON result. The demo clears memory ids and `ROAM_*_PROVIDER` for the process so it stays on the local sandbox and does not call AWS. No Amadeus credentials are required.

With the email verifiers and `booking.progress` absent, booked segments have `emailVerified: false` and `reason: "verifier_not_installed"`, and the loop records one `progress_not_installed` update and stops. That is the expected sandbox result.

To hold the server open (default port 8080):

```bash
PYTHONPATH=. python3 -m booking.master.main
```

In another shell:

```bash
curl -s http://localhost:8080/ping
curl -s -X POST http://localhost:8080/invocations \
  -H 'Content-Type: application/json' \
  --data @booking/master/fixtures/sample_plan.json
```

Tests:

```bash
PYTHONPATH=. python3 -m unittest booking.master.tests.test_master
```

The tests cover a missing verifier (`emailVerified` false, process still returns) and a missing progress agent (one recorded update, loop ends, at most five ticks).
