# Feature Spec — Guardrail / Policy Co-Signer (`features/guardrail`)

**Owner:** A · **Package:** `roam_guardrail` · **Port:** `:8002` · **Parent spec:** [`docs/SPEC.md`](../../docs/SPEC.md) §4.2

## 1. Purpose

The "Cryptographic Leash". The trip wallet is a **2-of-2 XRPL multi-sig**: Key 1 = Agent, Key 2 = Guardrail. Nothing can be
spent unless this service adds its signature, and it only does that after deterministic rules pass. It contains **no LLM**,
so a prompt injection has nothing to talk to.

## 2. Scope

**In:** policy storage, rule evaluation, tx↔quote matching, on-ledger credential check, multi-signing with Key 2,
human-readable violations, a `Guardrail` client and a fake.

**Out:** building, submitting or combining transactions (ledger), picking items (agent), UI (dashboard).

## 3. What you depend on

| Need | Source | Until it exists |
|---|---|---|
| Models | `roam_contracts.models` (`PolicyConfig`, `CosignRequest/Response`, `PolicyDecision`, `Violation`, `Quote`) | — (exists) |
| Quote signature format | `roam_contracts.signing.quote_signing_bytes` | — (exists) |
| Merchant public keys | `GET :8001/merchants` (cache) | skip signature check: `GUARDRAIL_SKIP_QUOTE_SIG=1` |
| Key 2 seed | `.env.guardrail` → `GUARDRAIL_SEED` (written by ledger bootstrap) | generate a local test wallet |
| Credential issuer | `.env.ledger` → `CREDENTIAL_ISSUER_ADDRESS` | static allowlist from `contracts/fixtures/merchants.json` (`GUARDRAIL_OFFLINE=1`) |
| XRPL node | env `XRPL_RPC_URL` | offline mode above |

You never import `roam_ledger` or `roam_merchants`. Your XRPL calls are read-only (`ledger_entry`) plus local signing.

## 4. Interfaces you provide

### 4.1 HTTP

| Method | Path | Body → Response |
|---|---|---|
| GET | `/policy` | `PolicyConfig` |
| PUT | `/policy` | `PolicyConfig` → `PolicyConfig` (validated: caps > 0, per-item ≤ daily) |
| POST | `/cosign` | `CosignRequest` → `CosignResponse` (always 200; `decision.approved` says yes/no) |
| POST | `/evaluate` | `CosignRequest` → `PolicyDecision` (dry run, never signs; used to preview in the UI) |
| POST | `/reset` | restores the default policy |

### 4.2 Python (`roam_guardrail.client`)

- `HttpGuardrail(base_url)` implements `roam_contracts.Guardrail`.
- `FakeGuardrail` runs the **same rule engine** in-process (import your own `rules.py`) and returns a dummy
  `signer_blob` when approved. **Ship this first.** B uses it until Hour 14.

### 4.3 `signer_blob` format (agreed with ledger)

```json
{"Signer": {"Account": "<guardrail r-address>", "SigningPubKey": "<hex>", "TxnSignature": "<hex>"}}
```
Produce it with `xrpl.transaction.sign(Transaction.from_xrpl(tx_json), wallet, multisign=True)` and take `Signers[0]`.

## 5. Rule engine (`rules.py`, pure functions, no I/O)

Evaluate **all** rules and return every violation, not just the first one. The demo shows a list.

| Order | Rule (`ViolationRule`) | Check | Example detail |
|---|---|---|---|
| 1 | `quote_signature` | ed25519 verify `merchant_signature` with that merchant's key | "Quote signature invalid for kissa-matcha" |
| 2 | `quote_expired` | `now < expires_at` | "Quote expired 3 min ago" |
| 3 | `tx_quote_mismatch` | every inner tx of `tx_json` maps 1:1 to a quote by memo invoice_id, and Destination/Amount/currency match **exactly**; no extra inner txs; `Account` = trip account | "Inner tx #2 pays rXYZ… but quote says rABC…" |
| 4 | `max_per_item` | each `quote.amount ≤ policy.max_per_item` | expected `<= 45`, actual `500.00` |
| 5 | `max_daily_budget` | booked or ledger spend for the day, plus the quote total, `≤ max_daily_budget`. The request's `spent_today` is ignored. | expected `<= 55.00`, actual `500.00` |
| 6 | `verified_credential` | if required: a `Credential` ledger entry exists with subject = merchant address, issuer = our issuer, type = hex(`CREDENTIAL_TYPE`), flag `lsfAccepted`, not expired | "rTrap… holds no Local_Merchant_KYC credential" |
| 7 | `category` | `quote.category in allowed_categories` | actual `shopping` |
| 8 | `date_window` | slot within window, if set | |
| 9 | `geofence` | haversine(quote.location, center) ≤ radius_km, if set | |

`approved = len(violations) == 0`. `remaining_daily_budget = max_daily_budget - spent_today` (before this purchase).

Decode inner txs: a `Batch` has `RawTransactions: [{RawTransaction: {...}}]`. Each inner `EscrowCreate` has `Destination`,
`Amount` (drops string for XRP, or an `{currency, issuer, value}` object for RLUSD), and `Memos`. Write one helper that
normalises the amount to `Decimal` in display units.

**Security notes for the pitch:** the guardrail recomputes everything from the signed quotes and the raw tx. It never
trusts the agent's summary or the request's `spent_today`. Key 2 never leaves this process. The New York activity
policy is per-item 50.00 and daily 100.00, allows activity and food, and uses the demo city's dates and center.
A flight or hotel quote is a category violation that says the activity policy excludes flights and hotels. The other
rules still run on that quote.

## 6. Tasks

**Hour 0–2 (unblocks B)**
- [ ] `rules.py` skeleton + `FakeGuardrail`, passing the two fixture decisions in `contracts/fixtures/policy_decisions.json`

**Hour 2–8** (after the merchants fake is shipped)
- [ ] All 9 rules with unit tests (table-driven; one test per rule × pass/fail)
- [ ] FastAPI endpoints, policy persistence (in-memory + optional JSON file)

**Hour 8–14**
- [ ] Real credential lookup via `ledger_entry` (coordinate the issuer address format with C via `.env.ledger`)
- [ ] Real multi-sign with Key 2. Validate it against C's 2-of-2 account by submitting one tiny tx combined with a local agent signature

## 7. Acceptance tests

1. `fixtures/quotes.json` bike + matcha, default policy → approved, `signer_blob` present.
2. Souvenir → not approved, violations ⊇ {`max_per_item`, `max_daily_budget`, `verified_credential`, `category`}, `signer_blob` null.
3. A tx whose Destination was swapped after quoting → `tx_quote_mismatch`, even if all amounts are within caps.
4. Lowering `max_per_item` to 20 via `PUT /policy` → matcha (30) gets blocked.
5. Combined with the agent signature, the guardrail's `signer_blob` gets `tesSUCCESS` on Devnet.

## 8. Config

`GUARDRAIL_PORT=8002`, `XRPL_RPC_URL`, `MERCHANTS_URL=http://localhost:8001`, `.env.guardrail`, `.env.ledger`,
`GUARDRAIL_SKIP_QUOTE_SIG`, `GUARDRAIL_OFFLINE`.
