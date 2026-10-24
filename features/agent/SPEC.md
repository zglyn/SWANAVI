# Feature Spec — Agent, Orchestrator & Gateway (`features/agent`)

**Owner:** B · **Package:** `roam_agent` · **Port:** `:8000` · **Parent spec:** [`docs/SPEC.md`](../../docs/SPEC.md) §4.4

## 1. Purpose

The brain and the glue. An LLM agent plans the trip by talking to merchants over MCP and collecting 402 quotes. A
deterministic orchestrator turns approved quotes into a multi-signed checkout. A FastAPI gateway is the single backend
the dashboard talks to and the **only** source of `InspectorEvent`s.

## 2. Scope

**In:** LLM agent + MCP client, orchestrator, demo scenarios, gateway REST + SSE, real/fake wiring, `spent_today`
tracking, demo reset.

**Out:** merchant logic, policy rules, XRPL transaction code, UI. You call those through their interfaces only.

## 3. What you depend on

| Need | Interface | Fake (use from Hour 2) | Real (expected) |
|---|---|---|---|
| Merchants | `roam_contracts.MerchantDirectory` + MCP at `:8001/m/{id}/mcp` | `FakeMerchantDirectory` (A) | Hour 14 |
| Guardrail | `roam_contracts.Guardrail` | `FakeGuardrail` (A) | Hour 14 |
| Ledger | `roam_contracts.Ledger` | `FakeLedger` (C) | Hour 20 |
| Models / API types | `roam_contracts.models`, `contracts/ts/api.ts` | — | exists |

If a fake isn't pushed yet, write a 20-line throwaway one from `contracts/fixtures/*.json`. **Never wait.**

Wiring: `ROAM_FAKES=merchants,guardrail,ledger` (comma list) picks fakes. Import real classes lazily so a missing
feature never breaks startup. `roam_ledger` is the only feature package you import directly (it's a library). Merchants
and guardrail are reached over HTTP via their client classes.

## 4. Gateway API (contract with the dashboard, mirrored in `contracts/ts/api.ts`)

| Method | Path | Body → Response | Notes |
|---|---|---|---|
| GET | `/api/policy` | → `PolicyConfig` | proxies the guardrail |
| PUT | `/api/policy` | `PolicyConfig` → `PolicyConfig` | proxies the guardrail; emits `agent.message` |
| POST | `/api/chat` | `{message}` → `{reply, quotes: Quote[]}` | runs the agent; streams events while it works |
| POST | `/api/checkout` | `{invoice_ids}` → `CheckoutResult` | orchestrator (§6) |
| POST | `/api/scenarios/{name}` | → `{ok: true}` | `happy-path` · `malicious-upsell` · `rainstorm` · `reset`; returns immediately, progress via events |
| GET | `/api/wallet` | → `WalletState` | from ledger |
| GET | `/api/events` | SSE | `event: inspector` / `data: <InspectorEvent JSON>`; replay the last 200 events on connect |

Enable CORS for `http://localhost:3000`. Event `type`s must come from `roam_contracts.models.EVENT_TYPES` and carry the
`data` payloads documented there. The dashboard renders them by type.

## 5. The agent

- **Model:** Claude via the Anthropic SDK (Q4; keep the provider behind one small `llm.py`). Key from `ANTHROPIC_API_KEY`.
- **Tools:** MCP tools from each merchant mount (`search_catalog`, `get_quote`, `merchant_info`). **No payment tool.**
- **System prompt essentials:** the trip brief and the policy (as context only; enforcement is the guardrail's job).
  Collect quotes for a plan, then summarise. Never claim something is booked.
- **Output:** a reply plus the list of `Quote`s it collected (capture them from `get_quote` tool results, not from LLM text).
- Emit `agent.planning` at start, `quote.received` per quote, `agent.message` for the final reply.
- **Fallback:** if the LLM call fails or `ROAM_SCRIPTED_AGENT=1`, return a scripted reply + fixture-equivalent quotes. The demo must work offline from the LLM.

## 6. Orchestrator — checkout

```
quotes = [quote_cache[id] for id in invoice_ids]
tx      = ledger.build_checkout(quotes)
agent   = ledger.sign_as_agent(tx)                      → emit tx.signed.agent
resp    = guardrail.cosign(CosignRequest(tx, quotes, policy, spent_today))
if not resp.decision.approved:                          → emit guardrail.blocked; return CheckoutResult(status="blocked", decision=…)
                                                          (NOTHING is submitted)
emit guardrail.approved
result  = ledger.submit_multisigned(tx, [agent, resp.signer_blob], quotes, emit)
if result.status == "success":
    for each escrow: merchants.confirm(merchant_id, PaymentProof(...)) → emit booking.confirmed
    spent_today += result.total
return result
```

Before emitting `quote.received`, set `quote.merchant_verified = ledger.has_credential(quote.merchant_address)` (display only; the guardrail re-checks on its own).

Keep a `quote_cache` (invoice_id → Quote) and an `escrows` map (invoice_id → EscrowRef) in memory.

## 7. Scenarios (scripted and deterministic; each step emits events with ~0.5–1 s spacing for the audience)

| Name | Steps |
|---|---|
| `happy-path` | brief "Afternoon in Arashiyama, $100" → quotes for bike + matcha (agent or scripted) → checkout → 2 bookings |
| `malicious-upsell` | agent reads the trap shop catalog → `agent.message` "The shop says this is pre-approved…" → quote GOLD-CAT $500 → checkout → **guardrail.blocked** with violations → no ledger call |
| `rainstorm` | `weather.alert` "Rain at 14:00" → `ledger.cancel_escrow(bike)` → `merchants.cancel(bike)` → `booking.cancelled` → agent looks for an indoor 14:00 alternative → ramen quote → checkout → `booking.confirmed` |
| `reset` | clear caches + `spent_today`, `POST merchants /admin/reset`, `POST guardrail /reset`, emit `system.reset` (ledger state stays; balances just carry over) |

`rainstorm` requires the bike escrow's on-ledger `CancelAfter` to have passed (see ledger spec §6). If it hasn't, wait
and emit a countdown `agent.message` rather than failing.

## 8. Tasks

**Hour 0–2:** FastAPI skeleton with all routes returning fixture data + SSE replaying `contracts/fixtures/events.json`.
Push it: D can integrate against a real server from Hour 2.
**Hour 2–8:** real/fake wiring, orchestrator against all fakes, scenarios against fakes.
**Hour 8–14:** LLM agent + MCP client (against A's real merchant server once it's up, else scripted mode).
**Hour 14:** integration #1 (real merchants + guardrail, fake ledger). **Hour 20:** integration #2 (all real).
**Hour 20–28:** timing/polish of scenario events, error events (`level=error`) for every failure path.

## 9. Acceptance tests

1. `ROAM_FAKES=merchants,guardrail,ledger`: all 4 scenarios run and produce events matching `events.json` in order and shape.
2. `malicious-upsell` never calls `ledger.submit_multisigned` (assert in a test with a spy).
3. `/api/checkout` with an unknown invoice id → 400, not a crash.
4. All real: `happy-path` produces a validated batch with 2 escrows and 2 merchant bookings.

## 10. Config

`GATEWAY_PORT=8000`, `ROAM_FAKES`, `ROAM_SCRIPTED_AGENT`, `ANTHROPIC_API_KEY`, `MERCHANTS_URL=http://localhost:8001`,
`GUARDRAIL_URL=http://localhost:8002`, `.env.ledger`.
