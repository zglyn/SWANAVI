# Master booking agent

The planner calls this runtime and no other booking entry. The master manages the trip by calling capability agents. Flight booking, hotel booking, attraction booking, confirmation-email verification, trip progress, replanning, and the guard tools each live in their own package. This folder does not implement those capabilities. The master calls one replan agent per event: cancellation, an early finish, or a late finish. It calls `check_budget`, `authorize_spend`, `refund_booking`, `check_conflicts`, and `trip_notice` when those packages import.

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
| Update `event` `cancelled` | `replan_cancel` | `booking.replan.cancel` | `replan_cancel(trip_id, now, plan, disruption)` |
| Update `event` `ended_early` | `replan_early` | `booking.replan.early` | `replan_early(trip_id, now, plan, disruption)` |
| Update `event` `ended_late` | `replan_late` | `booking.replan.late` | `replan_late(trip_id, now, plan, disruption)` |
| Before accepting a booked segment | `check_budget` | `booking.guard.budget` | `check_budget(trip_id, segment, price)` |
| Scripted demo charge | `authorize_spend` | `booking.guard.spend` | `authorize_spend(10, 12, "USD")` |
| Segment `event` `cancelled` | `refund_booking` | `booking.refund` | `refund_booking(trip_id, segment_id, confirmation_code)` |
| Replan returned `changed: true` | `check_conflicts` | `booking.guard.conflicts` | `check_conflicts(trip_id, plan)` |
| After a replan, or an over-capture rejection | `trip_notice` | `booking.notify` | `trip_notice(trip_id, event)` |

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
        {
            "segmentId": str,
            "kind": str,
            "issue": str,
            "action": "none" | "rebook" | "verify_email" | "replan",
            "event": "cancelled" | "ended_early" | "ended_late",
            "deltaMinutes": int | None,
        }
    ],
}
```

`plan` is the plan the master is currently running. `results` are the current per-segment results. `clock` is `{"tick": <n>, "now": "<YYYY-MM-DDTHH:MM:SSZ>"}`. `event` and `deltaMinutes` are read only when `action` is `replan`.

| `action` | What the master does |
| --- | --- |
| `none` | Records the update. |
| `rebook` | Calls that segment's `book_*` tool again. Rebook does not edit the plan. |
| `verify_email` | Calls that segment's `verify_*_email` tool (sandbox `sample_email`, then `verify`). |
| `replan` | Calls one replan agent for that `event`. |

The master calls one replan agent per event. It does not decide the new schedule.

| `event` | Tool | Arguments |
| --- | --- | --- |
| `cancelled` | `replan_cancel` | `trip_id`, `now`, the current plan, `disruption` |
| `ended_early` | `replan_early` | `trip_id`, `now`, the current plan, `disruption` |
| `ended_late` | `replan_late` | `trip_id`, `now`, the current plan, `disruption` |

`now` is the clock's timestamp string. `disruption` is `{segmentId, kind, event, deltaMinutes}`.

When `booking.replan.cancel`, `booking.replan.early`, or `booking.replan.late` cannot be imported, or does not export its tool, that update records `replan: "replan_not_installed"` and the loop continues. The other updates on the tick still run. The cap stays five ticks.

When the tool returns `changed: true` and a `plan` object, the master replaces its working plan with that plan and records `notes` on the update (`replan: "changed"`). `notes` may be a string or a list of strings. Later ticks, including `trip_progress` and a later `rebook`, see the replaced plan. The master does not invent the replacement.

The loop stops at five ticks. It also stops when `onTrack` is true and the tick has no `rebook` or `verify_email` action. A `replan` action does not by itself keep the loop open, and a missing replan package does not end it. When `booking.progress` is missing, or it has no `trip_progress` callable, the master records one update with `issue: "progress_not_installed"` and `action: "none"`, then ends the loop. A progress exception is recorded and ends the loop the same way. The process keeps going.

### Guard tools

The master calls each guard when that package imports. When the import fails, or the package does not export the function, the master records `<tool>_not_installed` and continues. The cap stays five ticks. Book, email verify, progress, and replan behavior stay as they are.

| Tool | When | Missing package | Installed result |
| --- | --- | --- | --- |
| `check_budget` | After a segment is `booked` and `emailVerified` is true, before that segment is accepted | Segment result `budget` is `check_budget_not_installed`. The segment stays accepted. | `check_budget(trip_id, segment, price)`. `price` is the booking price `{amount, currency}` or `null`. When the result has `allowed: false`, the master sets `status` to `needs_user` and does not treat the segment as accepted. |
| `authorize_spend` | Once per plan, for the scripted demo charge | Envelope `spend.reason` is `authorize_spend_not_installed` and `spend.payAmount` is `null`. | `authorize_spend(10, 12, "USD")` — `authorizedAmount` 10, `requestedAmount` 12, `currency` `"USD"`. The master records the tool's `payAmount` and `reason` on `spend`. The spend guard's over-capture result is `payAmount` 10 and `reason` `over_capture_rejected`. |
| `refund_booking` | A replan update has `event` `cancelled` | Update `refund` is `refund_booking_not_installed`. | `refund_booking(trip_id, segment_id, confirmation_code)`. The return value is stored on `refund`. |
| `check_conflicts` | A replan returned `changed: true` and replaced the plan | Update `conflicts` is `check_conflicts_not_installed`. | `check_conflicts(trip_id, plan)` on the replaced plan. The return value is stored on `conflicts`. |
| `trip_notice` | After a handled replan, and when `authorize_spend` records `reason` `over_capture_rejected` | Tick `notice` is `trip_notice_not_installed`. | `trip_notice(trip_id, event)`. The return value is kept on that tick as `notice`. Two notices on one tick are a list. |

`event` for a replan is `{type: "replan", segmentId, kind, event, replan, notes}`. `event` for an over-capture rejection is `{type: "over_capture_rejected", authorizedAmount, requestedAmount, currency, payAmount}`.

`spend` on a finished run is `{authorizedAmount, requestedAmount, currency, payAmount, reason}` plus any other fields the spend tool returned.

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
| `budget` | Present once the segment is booked and email-verified: the `check_budget` result, or `check_budget_not_installed` |

The runtime returns:

```json
{
  "tripId": "sample-kyoto",
  "results": [],
  "ticks": [],
  "maxTicks": 5,
  "loopStopped": "progress_not_installed",
  "error": null,
  "spend": {
    "authorizedAmount": 10,
    "requestedAmount": 12,
    "currency": "USD",
    "payAmount": null,
    "reason": "authorize_spend_not_installed"
  }
}
```

`error` is `invalid_plan` when the payload is not a trip plan. `results` and `ticks` are then empty, and `spend` is omitted. `loopStopped` is `progress_not_installed`, `on_track`, `max_ticks`, `progress_error`, or `invalid_plan`.

Each tick is `{tick, clock, phase, onTrack, updates}`. A tick that notified the traveler also has `notice`.

## Local demo (AgentCore SDK local mode, no AWS)

From the repository root:

```bash
python3 -m pip install -r booking/master/requirements.txt
PYTHONPATH=. python3 -m booking.master.demo
```

That command starts the Bedrock AgentCore app (the same server as `python3 -m booking.master.main`) and posts `booking/master/fixtures/sample_plan.json` to `POST /invocations`. Stderr prints each segment, each tick, and each recorded update. Stdout is the JSON result. The demo clears memory ids and `ROAM_*_PROVIDER` for the process so it stays on the local sandbox and does not call AWS. No Amadeus credentials are required.

With the verifiers and `booking.progress` installed, the sample segments come back `booked` with `emailVerified` true. The service clock starts at 08:00Z on the trip start date and stops on track before any segment has ended, so it never asks for a rebook. The demo posts the sample plan plus three visits that give the scripted replans a later same-day segment: a morning briefing at 10:00Z on the start date, a garden walk at 13:00Z the next day, and a farewell tea at 12:00Z on checkout day. Tick 1 is `2026-11-02T13:00:00Z` (past the briefing by more than the 45-minute grace, and before the hotel's 15:00Z start). Tick 1 rebooks the briefing. Ticks 2 and 3 stay on that morning (`10:30Z`, then `10:40Z`) so the loop verifies the rebook and then stops on track. The cap stays five ticks.

The demo also appends one scripted replan signal per tick for the first three ticks, on top of those progress updates. Tick 1 is `cancelled` for `flight-1`, which marks that flight removed and pulls the hotel forward. Tick 2 is `ended_early` for `hotel-1` with `deltaMinutes` 60, which pulls the farewell tea earlier. Tick 3 is `ended_late` for `attraction-1` with `deltaMinutes` 45, which pushes the garden walk later. The master calls one replan agent per event. When that package is missing, the demo still finishes and stderr shows `replan=replan_not_installed` on that update.

The same run calls `authorize_spend(10, 12, "USD")`. With `booking.guard.spend` installed, stderr shows `payAmount=10` and `reason=over_capture_rejected`, and the over-capture `trip_notice` stays on tick 1. With the guard packages absent, the demo still finishes: `spend.reason` is `authorize_spend_not_installed`, accepted segments record `budget` `check_budget_not_installed`, a cancellation records `refund` `refund_booking_not_installed`, a changed replan records `conflicts` `check_conflicts_not_installed`, and each replan tick keeps `notice` `trip_notice_not_installed`.

With the email verifiers and `booking.progress` absent, booked segments have `emailVerified: false` and `reason: "verifier_not_installed"`, and the loop records one `progress_not_installed` update and stops. The scripted spend record is still on the result.

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

The tests cover a missing verifier (`emailVerified` false, process still returns), a missing progress agent (one recorded update, loop ends, at most five ticks), a missing replan package (`replan_not_installed` recorded, loop continues, cap still five), a fake replan tool that shifts a segment (`changed: true` replaces the plan and the notes are recorded), missing guard packages (the loop still returns and records each `<tool>_not_installed`), and a fake `authorize_spend` result (`payAmount` 10 and `reason` `over_capture_rejected` recorded on `spend`, with the notice kept on the tick).
