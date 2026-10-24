# Roam402 — Hackathon MVP Spec

> Status: **Draft v0.1** — open questions at the bottom must be answered before the contracts freeze (Hour 2).
>
> User flow: [`docs/USER_FLOW.md`](USER_FLOW.md)

## 1. Goal of the demo

One flawless, live, end-to-end run that shows:

1. An AI agent **discovering** three local Kyoto merchants over MCP and collecting signed `402` quotes (no money moves).
2. The **Policy Co-Signer refusing** to co-sign a malicious $500 upsell from an unverified merchant. The transaction never reaches the ledger.
3. An **atomic `Batch`** that escrows payment to two verified merchants ($15 bike + $30 matcha) in one all-or-nothing transaction, showing the ~15% "Direct-to-Wallet" savings vs. Viator.
4. A **rainstorm pivot** that cancels the bike escrow, recovers the funds and rebooks an indoor Ramen Tasting within budget.

Everything else (real onboarding, NFC check-in, real merchants) is a stretch goal or slideware.

## 2. Team & ownership

Four owners, five feature folders. **Nobody imports another feature's code.** Features talk only through
`contracts/` (shared models + interfaces) and HTTP. Every feature ships a **fake** of itself in its first two hours, so
everyone else can build against the fake until the real one lands.

| Owner | Feature folder(s) | One-line responsibility |
|---|---|---|
| **A** | `features/merchants`, `features/guardrail` | Who you may pay (merchant MCP + 402 quotes) and what you may buy (policy co-signer) |
| **B** | `features/agent` | The brain + orchestrator: LLM agent, MCP client, demo scenarios, the HTTP gateway the dashboard calls |
| **C** | `features/ledger` | Everything on XRPL: accounts, multi-sig, credentials, Batch, escrows, cancel/finish |
| **D** | `features/dashboard` | Next.js split-screen UI: chat + policy sliders (left), live tx/guardrail inspector (right) |

> Default split. Swap it once we know each person's skills (see Q1).

### Why there are no blockers

| If you need… | …build against this until the real one is ready |
|---|---|
| Merchant catalog / quotes | `contracts/fixtures/merchants.json`, `quotes.json` + merchants' `FakeMerchantDirectory` |
| Guardrail decisions | `contracts/fixtures/policy_decisions.json` + guardrail's `FakeGuardrail` (pure rules, no keys) |
| Ledger results | `contracts/fixtures/checkout_result.json` + ledger's `FakeLedger` (in-memory, fake hashes) |
| Gateway API (dashboard) | `contracts/fixtures/events.json` + mock mode `NEXT_PUBLIC_USE_MOCKS=1` |

Pick real or fake implementations per feature at runtime: `ROAM_FAKES=merchants,ledger` (comma list; empty = all real).

## 3. Architecture

```
┌──────────── features/dashboard (D) :3000 ────────────┐
│ Chat + Policy sliders        │  Tx & Guardrail Inspector│
└──────────────┬───────────────┴───────────▲────────────┘
               │ REST                       │ SSE /api/events
┌──────────────▼────────────────────────────┴───────────┐
│ features/agent (B) :8000  — gateway + orchestrator     │
│   LLM agent ──MCP──► merchants   ──HTTP──► guardrail   │
│   uses ledger as a Python library (via Ledger protocol)│
└──────┬───────────────────────┬──────────────┬─────────┘
       │ MCP + HTTP 402        │ POST /cosign │ import
┌──────▼─────────┐   ┌─────────▼────────┐  ┌──▼───────────────┐
│ merchants (A)  │   │ guardrail (A)    │  │ ledger (C)       │
│ :8001 FastAPI  │   │ :8002 FastAPI    │  │ xrpl-py library  │
│ + fastmcp      │   │ holds Key 2 only │  │ holds Key 1 path │
└────────────────┘   └──────────────────┘  └────────┬─────────┘
                                                    ▼
                                           XRPL Devnet/Testnet
```

**Key separation (the "Cryptographic Leash"):** the trip account is a 2-of-2 multi-sig (`SignerQuorum=2`, Agent key
weight 1, Guardrail key weight 1, master key disabled). The agent process never sees Key 2. The guardrail is a
separate process that runs deterministic rules (no LLM) before it adds its signature.

**Only the gateway emits `InspectorEvent`s.** Merchants and guardrail return rich responses; the ledger library takes an
`emit` callback. That keeps the event stream in one place and means no feature needs another feature's event bus.

## 4. Feature specs

### 4.1 `features/merchants` (A)

**Detailed spec (work from this):** [`features/merchants/SPEC.md`](../features/merchants/SPEC.md)

One FastAPI app on `:8001` hosting three (+1 pivot) mock Kyoto merchants, each with its own MCP mount and XRPL address.

| merchant_id | Name | Item | Direct price | Viator price | Verified credential | Notes |
|---|---|---|---|---|---|---|
| `bamboo-bikes` | Arashiyama Bamboo Bike Rentals | 2h bike rental, 2 PM | 15 | 17.65 | ✅ | Outdoor, refundable |
| `kissa-matcha` | Kissa Master Matcha Workshop | Matcha workshop, 4 PM | 30 | 35.29 | ✅ | Indoor |
| `ramen-tasting` | Gion Ramen Tasting | Ramen tasting, 2 PM | 20 | 23.53 | ✅ | Indoor; pivot target |
| `lucky-souvenir` | "Lucky Cat" Souvenir Shop (trap) | Gold maneki-neko | 500 | — | ❌ | Item description contains a prompt injection |

**MCP tools** (per merchant, mounted at `/m/{merchant_id}/mcp`):
- `search_catalog(query?, date?) -> CatalogItem[]`
- `get_quote(sku, slot_start) -> Quote` (internally calls that merchant's 402 endpoint)

**HTTP / x402** (per merchant):
- `POST /m/{merchant_id}/book {sku, slot_start}` → `402 Payment Required` with a `Quote` body (signed by the merchant's
  ed25519 key; includes `invoice_id`, exact SKU, locked price, `expires_at`).
- Retry with header `X-PAYMENT: <base64 PaymentProof>` → merchant checks on-ledger that an escrow exists to its address
  with matching `InvoiceID`/amount → `200 Booking`.
- `POST /m/{merchant_id}/cancel {invoice_id}` → frees the slot.
- `GET /m/{merchant_id}/availability` — `POST /admin/sold-out/{sku}` toggles a slot for the "sold out" demo.

**Done when:** the agent (or `curl`) can list all four merchants, get a valid 402 quote from each, and complete a booking
with a payment proof for an escrow created on the ledger.

### 4.2 `features/guardrail` (A)

**Detailed spec (work from this):** [`features/guardrail/SPEC.md`](../features/guardrail/SPEC.md)

FastAPI on `:8002`. Holds **only** Key 2. Deterministic Python, no LLM.

`POST /cosign` with a `CosignRequest` (`tx_json`, `quotes`, `policy`, `spent_today`). It:
1. Verifies every quote's merchant signature and that it hasn't expired.
2. Decodes `tx_json` and checks that each inner payment/escrow matches a quote exactly (destination, amount, currency,
   `InvoiceID`). **No transaction value may lack a quote.**
3. Applies the policy rules: `max_per_item`, `max_daily_budget` (incl. `spent_today`), `require_verified_credential`
   (on-ledger `Credential` of type `Local_Merchant_KYC` from our issuer, via read-only XRPL call), `allowed_categories`,
   `date_window`, `geofence`.
4. If all pass, multi-signs with Key 2 and returns `CosignResponse{decision.approved=true, signer_blob}`. Otherwise
   returns `approved=false` with a list of `Violation`s (rule, human-readable detail, expected vs. actual) and **no signature**.

`GET /policy`, `PUT /policy`: the current `PolicyConfig` (the dashboard sliders write here via the gateway).

**Done when:** given `fixtures/quotes.json`, it approves bike+matcha, rejects the souvenir with ≥2 violations
(`max_per_item`, `verified_credential`), and the signature it produces is accepted by XRPL for the 2-of-2 account.

### 4.3 `features/ledger` (C)

**Detailed spec (work from this):** [`features/ledger/SPEC.md`](../features/ledger/SPEC.md)

Python library (`roam_ledger`) implementing the `Ledger` protocol. Owns all `xrpl-py` code.

- `bootstrap()` (idempotent CLI `python -m roam_ledger.bootstrap`): fund accounts from the faucet, create the credential
  issuer, issue + accept `Local_Merchant_KYC` credentials for the 3 verified merchants (not the trap shop), set up the
  trip account's `SignerListSet` (2-of-2) and disable the master key, and set up RLUSD trust lines if we use RLUSD (Q2).
  It writes `.env.ledger` (addresses + seeds). The guardrail seed goes in a separate file only the guardrail reads.
- `build_checkout(quotes) -> UnsignedTx`: a `Batch` (`tfAllOrNothing`) whose inner txs are one `EscrowCreate`
  per quote (`Destination`, `Amount`, `InvoiceID` via memo or field, unique `SourceTag`, `FinishAfter`/`CancelAfter`,
  optional crypto-condition for check-in).
- `sign_as_agent(tx)`, `submit_multisigned(tx, signer_blobs) -> CheckoutResult`.
- `cancel_escrow(ref) -> TxResult`, `finish_escrow(ref, fulfillment?) -> TxResult`.
- `has_credential(address, type) -> bool`, `balances() -> dict`.
- Every step calls `emit(InspectorEvent)` with the tx hash + explorer URL.

**Hour-0 spike (blocks nothing, but decides the design):** query the `feature` RPC on Devnet and Testnet for `Batch`,
`Credentials`, `TokenEscrow` (IOU/RLUSD escrows) and `SmartEscrow` / WASM. Post the findings in the team channel. See risks R1–R3.

**Done when:** `python -m roam_ledger.demo` creates the batch from fixture quotes, gets it multi-signed (with a local
test Key 2), validates it on-ledger and prints explorer links. A cancel then recovers the bike funds.

### 4.4 `features/agent` (B)

**Detailed spec (work from this):** [`features/agent/SPEC.md`](../features/agent/SPEC.md)

FastAPI gateway on `:8000` and the orchestrator.

- **Agent:** LLM (Claude by default, Q4) with an MCP client connected to all merchant MCP mounts. Its system prompt
  says it may *only* gather quotes. It has no payment tool. The orchestrator turns its chosen quotes into a checkout.
- **Orchestrator flow:** `quotes → ledger.build_checkout → ledger.sign_as_agent → POST guardrail /cosign → ledger.submit_multisigned → merchants X-PAYMENT confirm`.
  It emits an event at every step.
- **Scenarios** (deterministic, scripted, so the demo never depends on LLM luck):
  - `happy-path`: the "plan my afternoon in Arashiyama" prompt leads to the bike + matcha quotes and then checkout.
  - `malicious-upsell`: the agent "falls for" the trap shop's injected description, so the gateway asks the guardrail to co-sign $500, the guardrail blocks it, and **no tx is submitted**.
  - `rainstorm`: a weather event at 2 PM leads to `cancel_escrow(bike)`, which refunds 15. Then a ramen quote and a guardrail co-sign lead to a new single escrow.
  - `reset`: returns the demo to its initial state.
- **Gateway API** (the contract with the dashboard, in `contracts/ts/api.ts`):

| Method | Path | Body → Response |
|---|---|---|
| GET/PUT | `/api/policy` | `PolicyConfig` |
| POST | `/api/chat` | `{message}` → `{reply, quotes: Quote[]}` |
| POST | `/api/checkout` | `{invoice_ids}` → `CheckoutResult` |
| POST | `/api/scenarios/{name}` | — → `{ok}` (results arrive as events) |
| GET | `/api/wallet` | `WalletState` |
| GET | `/api/events` | SSE stream of `InspectorEvent` |

**Done when:** all three scenarios run end-to-end with `ROAM_FAKES=merchants,guardrail,ledger`, and again with all real.

### 4.5 `features/dashboard` (D)

**Detailed spec (work from this):** [`features/dashboard/SPEC.md`](../features/dashboard/SPEC.md)

Next.js (App Router) + Tailwind. One page, split screen.

- **Left:** chat with the agent, quote cards (merchant, price, Viator price, savings, verified badge), the policy card
  (sliders for `max_daily_budget` and `max_per_item`, a toggle for `require_verified_credential`) and the "Book itinerary" button.
- **Right:** the inspector, a live timeline of `InspectorEvent`s with color by level (`blocked` = red, big). Tx hashes link
  to the XRPL explorer. It shows the 2-of-2 signer status (Agent ✅ / Guardrail ✅/❌) per transaction, plus wallet balance and total savings.
- **Demo buttons:** "Simulate Malicious Upsell", "Simulate Rainstorm at 2 PM" and "Reset".
- **Mock mode:** `NEXT_PUBLIC_USE_MOCKS=1` replays `contracts/fixtures/events.json` on a timer and serves fixture
  responses, so the UI can be finished without a backend.

**Done when:** the full demo can be clicked through in mock mode, and the same UI works against the real gateway.

## 5. Shared contracts (`contracts/`)

Source of truth: `contracts/python/roam_contracts/models.py` (Pydantic v2) and `interfaces.py` (Protocols).
`contracts/ts/api.ts` mirrors the models for the dashboard. Fixtures in `contracts/fixtures/` are valid instances.

Rules:
- Money is a **decimal string** (`"15.00"`), never a float. Currency is `"RLUSD"` or `"XRP"` (Q2).
- Event `type`s and their `data` payloads: `EVENT_TYPES` in `models.py`. On-ledger conventions (escrow invoice memo,
  credential type, per-booking `SourceTag`): `INVOICE_MEMO_TYPE`, `CREDENTIAL_TYPE`, `source_tag_for` in `models.py`.
- `invoice_id` is a 64-char uppercase hex (XRPL `Hash256`), i.e. `sha256(merchant_id|sku|slot_start|nonce)`.
- **Frozen at Hour 2.** After that, a change needs a PR touching both the Python and TS files plus the fixtures, and a
  heads-up to all owners. You may add optional fields freely. You may not remove or rename fields.

## 6. Timeline (36h)

| Hours | Milestone |
|---|---|
| 0–2 | Kickoff: answer the open questions, freeze contracts, each owner ships their fake. C runs the amendment spike. A/C agree on the merchant key/address format. |
| 2–14 | Build against fakes. Each feature reaches its "done when" in isolation. |
| 14 | **Integration #1:** real merchants + real guardrail + fake ledger. |
| 20 | **Integration #2:** all real, happy path on Devnet. |
| 20–28 | Upsell + rainstorm on-ledger, dashboard polish, sold-out batch-revert demo (stretch). |
| 28 | Feature freeze. Only bug fixes after this. |
| 28–34 | Record a backup demo video, then rehearse 3× with `reset` between runs. |
| 34–36 | Slides, buffer. |

## 7. Stretch goals (only after Hour 28 is green)

1. **Sold-out revert:** make one inner tx fail on-ledger (e.g. revoke a merchant's credential + `DepositAuth`) to show the
   whole batch reverting.
2. **Check-in escrow finish:** a crypto-condition whose fulfillment is revealed by a "tap" button, which triggers `EscrowFinish`.
3. **60-second onboarding:** paste a URL, an LLM extracts the catalog and a new merchant mount appears.

## 8. Risks

- **R1: Network features.** `Batch`, `Credentials`, IOU escrow (`TokenEscrow`) and Smart Escrows (`XLS-100`, WASM) may
  not all be enabled on the same network. Smart Escrows are likely only on a dedicated WASM devnet. *Plan:* use standard
  `EscrowCreate` (time + optional crypto-condition) on whichever network has `Batch` + `Credentials`, and describe Smart
  Escrow as the production path on the slides. Use XRP if IOU escrow isn't available.
- **R2: Escrow cancel timing.** `EscrowCancel` only succeeds after `CancelAfter`. A "refund in 3 seconds" means the bike
  escrow must be created with a short `CancelAfter` (e.g. 60–90 s) for the demo, or the rainstorm must be triggered after
  the window passes. Decide in Q3.
- **R3: Batch + multi-sig.** We need to confirm that a multi-signed outer `Batch` is accepted. C validates this in the spike before Hour 6.
- **R4: `x402-xrpl` maturity.** If the package is missing or unstable, A implements the 402 handshake by hand (it's a
  status code + JSON body + header verification). The contract stays the same.
- **R5: LLM non-determinism on stage.** Scenarios are scripted. The LLM only drives free-form chat.

## 9. Open questions

See the team discussion. Answers get recorded here.

1. Team skills / ownership: who is strongest at frontend vs. Python vs. XRPL?
2. Currency: RLUSD (needs issuer + trust lines + IOU escrow) or Testnet XRP labelled "RLUSD" in the UI?
3. Rainstorm refund: short `CancelAfter` window, or merchant-signed refund payment?
4. LLM provider + who has an API key?
5. Tooling: Python 3.12 + `uv` workspace, Node 20 + pnpm, OK?
