# Task brief: connect the gateway to the AgentCore booking master

**Audience:** the AI coding agent working on the AWS AgentCore features. Read this whole file before starting.
**Repo:** `zglyn/SWANAVI` · **Base branch:** `dev` (until PR #105 merges, branch from `claude/integrate-into-dev`)

---

## 1. Goal (one paragraph)
When the traveller clicks **Book** on the trip overview, the gateway must turn the dashboard's trip package into the
booking master's input format, run the booking master, and stream the results back to the dashboard as live events.
Today none of that path exists. The dashboard, the gateway and the booking master each work alone. You are building the
bridge **inside the gateway**.

```
Dashboard ──POST /api/plans/{id}/book──► Gateway ──TripPlan──► Booking master (AgentCore runtime)
    ▲                                        │                         │
    └──── GET /api/events (live stream) ◄────┴──── events ◄──── {tripId, results, ticks, …}
```

## 2. What already exists (verified on `claude/integrate-into-dev` @ `63ec94c`)
| Piece | Where | Notes |
|---|---|---|
| Gateway app (FastAPI, port 8000) | `features/agent/roam_agent/app.py` | Planner routes; event bus: `publish(event: InspectorEvent)` appends to a 500-event replay buffer and pushes to every `GET /api/events` subscriber (SSE event name `inspector`). Replays the buffer on connect. |
| Swan trip routes | `features/agent/roam_agent/swan_http.py` (router included by `app.py`) | `_user(authorization)` resolves the `Bearer` token to a `user_id`; trips live in the module-level dict `trips: dict[str, SwanTrip]`; `trips[plan_id].package` is the `TravelPackage` the user sees on the overview; `profiles.get(user_id)` gives the `UserProfile`. `_publish(trip)` shows how to emit an event. |
| Booking master | `booking/master/main.py` (AgentCore `@app.entrypoint` → `booking.master.service.handle_payload(payload)`) | Input: `TripPlan` from `booking/contract.py` (camelCase, strict; invalid input returns `error: "invalid_plan"`). Output: `{tripId, results[], ticks[], maxTicks, loopStopped, error, …assist keys}`. Runs locally without AWS when these env vars are **unset**: `AGENTCORE_MEMORY_ID`, `MEMORY_BOOKINGMEMORY_ID`, `ROAM_FLIGHT_PROVIDER`, `ROAM_HOTEL_PROVIDER`, `ROAM_ATTRACTION_PROVIDER`. |
| Shared models | `contracts/python/roam_contracts/models.py` (+ TS mirror `contracts/ts/api.ts`) | `TravelPackage`, `UserProfile`, `TripRequest`, `InspectorEvent`, `EVENT_TYPES`. |
| **Hand-off fixtures** | `contracts/fixtures/handoff/` (read its `README.md`) | One Kyoto trip at every step. Your tests are built on these. |

### The fixtures you'll use
| File | Role in your tests |
|---|---|
| `contracts/fixtures/package_kyoto.json`, `profile.json`, `trip_request_kyoto.json` | **Input** to the translator |
| `contracts/fixtures/handoff/trip_plan_kyoto.json` | **Expected output** of the translator (already passes `TripPlan.model_validate`) |
| `contracts/fixtures/handoff/booking_response_kyoto.json` | Real booking-master output, normal day (6/6 booked) |
| `contracts/fixtures/handoff/booking_response_kyoto_disrupted.json` | Real output, disrupted day 2 (one cancellation, one late finish) |
| `contracts/fixtures/handoff/dashboard_events_kyoto.json` | **Expected events** your converter should emit for the two responses |

## 3. What to build
Put new code in **new modules** under `features/agent/roam_agent/` and add one route. Suggested layout:

### 3.1 `booking_bridge.py`: the translator (pure function, no I/O)
`package_to_trip_plan(package: TravelPackage, profile: UserProfile, request: TripRequest) -> dict`

Return a dict that passes `booking.contract.TripPlan.model_validate`. Follow the mapping documented in
`contracts/fixtures/handoff/README.md` ("Mapping decisions"), in short:
- `tripId` ← `package.plan_id`
- `travelers` ← `[{id: "t1", name: profile.name}]`, then `"Traveller 2"`, … up to `request.travellers`
- `destination` ← split `request.destination` (`"Kyoto, Japan"`) → `{city: "Kyoto", country: "JP"}`. Use a small country-name→ISO-2 map; `"JP"` is what the fixture uses.
- `dates.start` ← **outbound departure date** (local date of `package.outbound.segments[0].depart_at`), `dates.end` ← return date
- `flights` ← one round-trip entry: `from`/`to` = outbound first/last segment airport codes (`from_place.code`, `to_place.code`), `departDate`, `returnDate`, `cabin`, `segmentId` = outbound offer `id`, `travelerIds` = all traveller ids
- `hotels` ← each `package.hotels[]` (`HotelStay`): `segmentId` = `"hotel-" + slug(offer.name)`, `city`, `checkIn`, `checkOut`, `rooms: 1`, `guests` = traveller count
- `attractions` ← itinerary stops with `kind` in `{"attraction", "merchant"}` **that have no `quote`**: `segmentId` = stop `id`, `name` = stop title, `date` and `time` from the stop's local `start`, `partySize` = traveller count
- **Skip stops that carry a `quote`.** Those are Swan merchant items paid with XRPL through `POST /api/checkout`, which is a different team member's work.

**Test:** `package_to_trip_plan(<fixtures>) == json.load(trip_plan_kyoto.json)`.

### 3.2 `booking_client.py`: run the booking master
`run_booking(trip_plan: dict, session_id: str) -> dict`, behind one switch `ROAM_BOOKING_MODE`:
- `local` (default): `from booking.master.service import handle_payload` and call it directly. Make sure the five sandbox env vars above are unset for this call, so it never touches AWS.
- `agentcore`: call the deployed runtime with boto3's `bedrock-agentcore` client (`invoke_agent_runtime`), with the runtime ARN from `BOOKING_RUNTIME_ARN`, the region from `AWS_REGION`, and `session_id = plan_id`. Check the current boto3 docs for the exact parameter names and response streaming before writing this; the service is new.
- Both modes return the same dict shape as `booking_response_kyoto.json`.

### 3.3 `booking_events.py`: turn the response into dashboard events
`booking_events(plan_id: str, response: dict, names: dict[str, str]) -> list[InspectorEvent]`
- one `agent.planning` event ("Booking N items for your … trip")
- per `results[]` item:
  - `booked` → `booking.confirmed` (level `success`); `data.booking` = `{invoice_id: segmentId, merchant_id: kind, sku: segmentId, status: "confirmed", confirmation_code}` plus `data.segment` = the raw result
  - `failed` → `booking.failed` (level `error`)
  - `needs_user` → `booking.needs_user` (level `warning`, message = `reason`, so the UI can ask the user)
- per `ticks[].updates[]`, **de-duplicated by `(segmentId, event or action)` across ticks**:
  - `cancelled` → `trip.alert`, plus `plan.change_applied` when `replan == "changed"` (message = the `notes` joined)
  - `ended_late` / `ended_early` → `trip.alert` (append `hours.reason` when `hours.ok` is false)
  - `rebook` → `trip.alert`
  - `verify_email` → `trip.alert` (level `info`)
- Ids must be unique and stable per plan (e.g. `f"{plan_id}-book-{n:03d}"`), so the dashboard's replay de-duplication works.

**Test:** for both fixture responses, the emitted events match `dashboard_events_kyoto.json` on `type`, `level`,
`message` and `data` keys. Ignore `id`/`ts` differences, or generate them the same way.

### 3.4 Route: `POST /api/plans/{plan_id}/book` (in `swan_http.py`'s router)
1. `user_id = _user(authorization)`. 404 if `plan_id` isn't in `trips`, 403 if `trips[plan_id].user_id != user_id`, 409 if `trip.package` is `None`.
2. Build the `TripPlan` with `package_to_trip_plan(trip.package, trip.profile, trip.request)`. `SwanTrip` (in `autopilot.py`) has `plan_id`, `user_id`, `request`, `profile`, `phase` and `package`.
3. Return `{"ok": true, "trip_id": plan_id}` **immediately**, and run the booking in a FastAPI `BackgroundTasks` job: `run_booking` → `booking_events` → `publish(...)` each event, with a short delay (~300 ms) between events so the UI animates.
4. On any exception, publish one `booking.failed` event with level `error` and the message, and never crash the gateway.
5. Store the response on the trip (e.g. `trip.booking = response`) so a page refresh can show the final state.

### 3.5 Contract additions (small, additive, in their own commit)
- `contracts/ts/api.ts`: add `book: (id: string) => \`/api/plans/${id}/book\`` to `API`.
- `contracts/python/roam_contracts/models.py` `EVENT_TYPES` **and** `contracts/ts/api.ts` `EventType`: add `booking.failed`, `booking.needs_user`, `trip.alert`, `plan.change_applied`.
- Add only; never rename or remove fields. Mention these additions in your PR description so the UI agent (Cursor) can wire the **Book** button to `API.book`.

## 4. Known booking-master bugs (found while making the fixtures)
These are in `booking/`. **Coordinate before editing**: that folder belongs to the booking-line owner. Fix #1 only if you own it or get the go-ahead, since live trip tracking depends on it.
1. **The loop never leaves `pre_trip`.** `booking/master/service.py` line 247 calls `trip_progress(plan, results, clock)` with the clock **dict**; `trip_progress` expects the timestamp string. Verified: dict → `phase: pre_trip`, string → `in_progress`. Fix: pass `clock["now"]`. `booking/master/demo.py` patches around this, which is why the demo works.
2. Day-1 stops are flagged `rebook` on every later tick, because nothing reports a stop as finished. Your de-duplication hides the noise; a real fix needs a "completed" signal.
3. A cancellation shifted a stop to before its opening time (`hours.ok: false`).
4. The 4 failing tests in `booking/orchestrator/tests/test_orchestrator.py` are stale (they expect `provider_not_installed`) and pre-date this work.

## 5. Boundaries: do not edit
| Path | Owner |
|---|---|
| `features/dashboard/**` | Cursor (UI). It will add the Book button wiring using `API.book`. |
| `features/ledger/**` | Ledger teammate |
| `features/guardrail/**`, `features/merchants/**`, `POST /api/checkout`, `/api/policy`, `/api/chat`, `/api/scenarios/*`, `/api/wallet` | Claude (XRPL payment path and demo routes) |
| `booking/**` | Booking-line owner; see §4 |

Keep secrets out of the repo. AWS credentials, `BOOKING_RUNTIME_ARN` and API keys come from env only. Never send
loyalty numbers or the full home address to an LLM or to the booking master. The `TripPlan` above contains neither.

## 6. How to run and test
```bash
uv sync                                   # repo root
uv run pytest                             # planner/tools/merchants (currently 43 passing); add your tests under features/agent/tests/
# booking line (45 modules; 4 known stale failures):
PYTHONPATH=. uv run --with bedrock-agentcore python -m unittest $(find booking -name "test_*.py" | sed 's#\.py$##; s#/#.#g')
# gateway locally:
uv run uvicorn roam_agent.app:app --port 8000 --app-dir features/agent
# dashboard against it (separate terminal):
cd features/dashboard && pnpm install && NEXT_PUBLIC_USE_MOCKS=0 pnpm dev
```

## 7. Done when
- [ ] `package_to_trip_plan` reproduces `trip_plan_kyoto.json` exactly (unit test)
- [ ] `booking_events` reproduces `dashboard_events_kyoto.json` for both fixture responses (unit test)
- [ ] Integration test with FastAPI's `TestClient` and `ROAM_BOOKING_MODE=local`:
  - `POST /api/auth/demo` → token
  - `POST /api/trips/request` with `trip_request_kyoto.json` (all autonomy = Swan decides) → `plan_id`, with `trips[plan_id].package` set
  - `POST /api/plans/{plan_id}/book` returns immediately
  - the published events then include `agent.planning` + one `booking.confirmed` per booked segment
- [ ] Wrong user → 403, unknown plan → 404, no package yet → 409; a booking-master exception produces one `booking.failed` event, not a crash
- [ ] `ROAM_BOOKING_MODE=agentcore` works against a deployed runtime, or is clearly marked untested in the PR if no runtime exists yet
- [ ] Existing tests still pass (43 + booking suite with only the 4 known failures)
- [ ] One PR into `dev`, branched from `dev`. The description lists the contract additions and `Closes #N` for its ticket, if one exists.
