# Feature Spec — Dashboard (`features/dashboard`)

**Owner:** D · **Stack:** Next.js (App Router) + TypeScript + Tailwind · **Port:** `:3000` · **Parent spec:** [`docs/SPEC.md`](../../docs/SPEC.md) §4.5

## 1. Purpose

The thing the judges see. A split screen: the traveller's experience on the left, and on the right "what's happening on the
ledger and why", where the guardrail block and atomic settlement become visible and dramatic.

## 2. Scope

**In:** the single demo page, all UI states, mock mode, the API client, SSE handling, demo buttons.

**Out:** auth, multiple pages, mobile polish beyond "doesn't break", any business logic (the backend decides everything).

## 3. What you depend on

| Need | Source | Until it exists |
|---|---|---|
| Types + routes | `contracts/ts/api.ts` (path alias `@contracts/*` → `../../contracts/ts/*`) | — (exists) |
| Data | gateway `:8000` (B) | **mock mode** with `contracts/fixtures/*.json` |

Ship mock mode first and you're never blocked. B has fixture-backed routes from about Hour 2 if you want a real server earlier.

## 4. Layout

```
┌───────────────────────────── Header: Roam402 · wallet balance · total saved vs Viator · network badge ──────────────┐
├──────────────── LEFT (traveller) ─────────────────┬──────────────── RIGHT (inspector) ───────────────────────────┤
│ Policy card                                        │ Signer status for the current tx:                            │
│   Max daily budget  [====|----] 100 RLUSD          │   🤖 Agent key ✅    🛡 Guardrail key ✅/❌   quorum 2/2     │
│   Max per item      [==|------]  45 RLUSD          │                                                              │
│   Verified merchants only  [on]                    │ Event timeline (newest on top, animated in)                  │
│ Chat with agent                                    │   ● quote.received  Bike rental 15 RLUSD                     │
│   …messages…                                       │   ✅ guardrail.approved  co-signed 2/2                        │
│ Quote cards: name · title · time · price           │   ⛓ batch.validated  2 escrows  [explorer ↗]                 │
│   struck-through Viator price · savings · ✔ badge  │   ⛔ guardrail.blocked  4 violations (expanded, red)          │
│   [ ] select       → [Book itinerary]              │                                                              │
├────────────────────────────────────────────────────┴──────────────────────────────────────────────────────────────┤
│ Demo bar:  [Simulate Malicious Upsell]   [Simulate Rainstorm at 2 PM]   [Reset]                                   │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## 5. Behaviour

| Element | Behaviour |
|---|---|
| Policy sliders | Load `GET /api/policy`; debounce 300 ms then `PUT /api/policy`. Show the saved state, not the optimistic one. |
| Chat | `POST /api/chat`; show a "thinking" state while events stream; render returned quotes as cards. |
| Quote card | Merchant, title, slot time, `amount`, struck-through `viator_price`, savings %, verified badge (unverified = amber "Unverified" chip). Checkbox to include in checkout. |
| Book itinerary | `POST /api/checkout {invoice_ids}`. `success` → cards flip to "Booked · in escrow" with confirmation codes. `blocked` → shake + red banner listing the violations. |
| Inspector timeline | Subscribe `GET /api/events` (EventSource, listen to `inspector`). Icon/colour by `level`: info grey, success green, warning amber, **blocked = full-width red card with each `Violation` (rule, expected vs actual)**, error red outline. `tx_hash` → explorer link. |
| Signer status | Derive from events: `tx.signed.agent` → Agent ✅. `guardrail.approved` → Guardrail ✅. `guardrail.blocked` → Guardrail ❌ + "transaction never reached the ledger". Reset on the next `agent.planning`/`system.reset`. |
| Header | `GET /api/wallet` on load and on every `wallet.updated` event: balance, locked in escrow; total saved = Σ `checkout.savings` from `batch.validated` events. |
| Demo buttons | `POST /api/scenarios/{malicious-upsell|rainstorm|reset}`; disable all buttons while a scenario runs (until a terminal event: `guardrail.blocked`, `batch.validated`, `batch.failed`, `system.reset`). |
| Rainstorm | On `escrow.cancelled`, the bike card shows "Refunded" with the amount. On the new `booking.confirmed`, a ramen card slides in. |

Event payloads by type are documented in `roam_contracts.models.EVENT_TYPES` and exemplified in `contracts/fixtures/events.json`.

## 6. Mock mode (default; `NEXT_PUBLIC_USE_MOCKS=0` switches to the real gateway)

One `api.ts` client with two implementations behind the same functions:
- `real`: fetch/EventSource to `NEXT_PUBLIC_GATEWAY_URL` (default `http://localhost:8000`).
- `mock`: returns `contracts/fixtures/*.json`. The event stream replays `events.json` with ~1.2 s spacing. Scenario buttons
  replay the relevant slice: upsell = events 7–8, rainstorm = 9–13, happy path = 1–6.

## 7. Tasks

**Hour 0–2:** `create-next-app`, path alias, layout shell, mock client.
**Hour 2–10:** policy card, chat, quote cards, inspector timeline + violation card, signer status, demo bar, all in mock mode.
**Hour 10–20:** switch to the real gateway (B's fixture-backed server works from Hour 2), handle loading/error/empty states.
**Hour 20–28:** demo polish: animations, big readable fonts (projector!), explorer links, savings counter animation.

## 8. Acceptance tests

1. Mock mode: the whole demo (happy path, upsell, rainstorm, reset) can be clicked through with no backend running.
2. A blocked event is unmissable from the back of a room (test on a projector or at 50% zoom).
3. Real mode: refreshing the page mid-demo restores the timeline (gateway replays events on connect).
4. No hard-coded amounts or merchant names; everything comes from data.

## 9. Config

`NEXT_PUBLIC_USE_MOCKS`, `NEXT_PUBLIC_GATEWAY_URL`, `NEXT_PUBLIC_EXPLORER_BASE` (default `https://devnet.xrpl.org/transactions/`).
