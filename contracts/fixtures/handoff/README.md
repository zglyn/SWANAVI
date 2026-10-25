# Hand-off fixtures: dashboard ⇄ gateway ⇄ AgentCore booking master

One trip (the Kyoto demo, plan id `kyoto-demo`) shown at every step, so the gateway can be built and tested without the
dashboard or AWS running.

```
dashboard sends            gateway translates to          booking master returns         gateway streams to dashboard
──────────────────         ─────────────────────          ──────────────────────         ────────────────────────────
../package_kyoto.json  ─►  trip_plan_kyoto.json      ─►  booking_response_kyoto.json ─►  dashboard_events_kyoto.json
../profile.json                                           booking_response_kyoto_disrupted.json  (same file, events 8–12)
../trip_request_kyoto.json
```

| File | What it is | How it was made |
|---|---|---|
| `../package_kyoto.json`, `../profile.json`, `../trip_request_kyoto.json` | What the dashboard has when the user clicks **Book** (snake_case, `roam_contracts` models) | existing fixtures |
| `trip_plan_kyoto.json` | The same trip in the booking master's format (`booking/contract.py` `TripPlan`, camelCase). **This is the expected output of the translator** the gateway needs. | hand-mapped from the three files above; validated with `TripPlan.model_validate` |
| `booking_response_kyoto.json` | Real booking-master output for that plan: all 6 segments booked in the sandbox | `booking.master.service.handle_payload(trip_plan_kyoto.json)` with the sandbox env (no AWS, no Amadeus) |
| `booking_response_kyoto_disrupted.json` | Real output for a disrupted day 2: Tenryū-ji **cancelled** at tick 1, Nishiki Market **ended 45 min late** at tick 2 | same call, with the clock and signal patches that `booking/master/demo.py` uses |
| `dashboard_events_kyoto.json` | **Expected output of the gateway**: the `InspectorEvent`s the dashboard should receive over `GET /api/events` for both runs | generated from the two responses |

## Mapping decisions used in `trip_plan_kyoto.json`
- `tripId` ← `plan_id`
- `travelers` ← profile `name`. The dashboard only collects a traveller **count**, so extra travellers need placeholder names ("Traveller 2").
- `destination` ← `"Kyoto, Japan"`, split into `{city: "Kyoto", country: "JP"}`
- `dates.start` ← the **outbound departure date** (2026-11-13, local SFO time), not the trip start (11-14). Otherwise the flight falls outside the trip.
- one `flights[]` entry for the round trip: `from`/`to` = outbound segment airport codes, `departDate` = outbound date, `returnDate` = return date. `segmentId` = the outbound offer id (`out-jl`).
- `hotels[]` ← each `HotelStay`. `rooms` defaults to 1, `guests` = traveller count.
- `attractions[]` ← itinerary stops of kind `attraction` / `merchant`. `segmentId` = stop id, `time` = local start time.
- **Not representable:** Swan merchant stops paid with XRPL (`quote.invoice_id`). Those go through `POST /api/checkout`, not the booking master.

## Event types in `dashboard_events_kyoto.json`
`agent.planning` and `booking.confirmed` already exist in `EVENT_TYPES`. `trip.alert` and `plan.change_applied` are
**proposed** (ticket #49) and not yet in the contracts; the dashboard shows unknown types generically until then. Also
proposed for failures: `booking.failed` and `booking.needs_user` (not exercised here, since every segment booked).

## Booking-master behaviour worth knowing (found while generating these)
1. **The loop never leaves `pre_trip` on its own.** `run_plan` passes the clock *object* to `trip_progress`, which expects
   a timestamp string, so signals don't fire. `booking/master/demo.py` patches around this; the real entry point doesn't.
2. **Day-1 stops are flagged `rebook` on every later tick** (Kinkaku-ji here), because nothing reports a stop as
   finished. The gateway should de-duplicate repeated updates (the events file shows each one once).
3. **Cancelling Tenryū-ji shifted Nishiki Market 120 min earlier, to before it opens.** The late-finish check then
   reports `starts before opening`.
4. The four failing tests in `booking/orchestrator/tests/test_orchestrator.py` are stale (they expect
   `provider_not_installed`), not a sign that booking is broken. Both runs here book everything.
