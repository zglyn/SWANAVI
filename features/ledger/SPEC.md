# Feature Spec — Ledger (`features/ledger`)

**Owner:** C · **Package:** `roam_ledger` (Python library + CLIs) · **Parent spec:** [`docs/SPEC.md`](../../docs/SPEC.md) §4.3

## 1. Purpose

All transaction-building and submitting XRPL code lives here: bootstrapping demo accounts, the 2-of-2 multi-sig trip
wallet, merchant credentials, the all-or-nothing `Batch` of escrows, and escrow cancel/finish. Every step emits an
`InspectorEvent` so the dashboard can show the ledger live.

## 2. Scope

**In:** `bootstrap`, `Ledger` protocol implementation, `FakeLedger`, `demo` smoke-test CLI, explorer links, wallet state.

**Out:** policy rules (guardrail), HTTP servers (agent), quote creation (merchants). You don't run a server. B imports your library.

## 3. What you depend on

| Need | Source | Until it exists |
|---|---|---|
| Models + protocol | `roam_contracts` (`Quote`, `UnsignedTx`, `CheckoutResult`, `EscrowRef`, `TxResult`, `WalletState`, `Ledger`) | — (exists) |
| Conventions | `INVOICE_MEMO_TYPE`, `CREDENTIAL_TYPE`, `source_tag_for` | — (exists) |
| Quotes to escrow | callers pass `Quote`s | `contracts/fixtures/quotes.json` (swap placeholder addresses for bootstrap ones) |
| Guardrail signature | `signer_blob` passed in by caller | sign locally with the guardrail seed from bootstrap (test-only helper) |

You never import `roam_guardrail`, `roam_merchants` or `roam_agent`.

## 4. Hour-0 spike (decides the design; post results in the team chat)

1. For Devnet and Testnet, run `feature` RPC and record whether `Batch`, `Credentials`, `TokenEscrow`, `MultiSignReserve` and any Smart Escrow / WASM amendment is enabled.
2. Submit a 2-inner-tx `Batch` (`tfAllOrNothing`) from a **multi-signed** account. Confirm the signing payload and fee calculation.
3. Pick the network and currency. Default if unsure: the network with `Batch` + `Credentials`, **XRP shown as RLUSD** (1:1), standard escrows.

Write results to `features/ledger/SPIKE.md`. Then set `XRPL_RPC_URL`, `XRPL_NETWORK`, `ROAM_LEDGER_CURRENCY` defaults accordingly.

## 5. Interfaces you provide

### 5.1 `python -m roam_ledger.bootstrap` (idempotent)

Creates and funds (faucet):
- `TRIP` account: `SignerListSet` quorum 2 with `AGENT` (weight 1) + `GUARDRAIL` (weight 1), then `AccountSet asfDisableMaster`.
- `AGENT`, `GUARDRAIL` signer wallets (they need no funds beyond reserve; they're signers only).
- `ISSUER` credential issuer.
- 4 merchants. `CredentialCreate` (type hex(`Local_Merchant_KYC`)) from ISSUER for bamboo-bikes, kissa-matcha and ramen-tasting, then `CredentialAccept` by each. **Not** for lucky-souvenir.
- If RLUSD: an issuer + trust lines + funding. Otherwise skip.

Writes (both git-ignored):
- `.env.ledger`: `XRPL_RPC_URL`, `TRIP_ADDRESS`, `AGENT_SEED`, `AGENT_ADDRESS`, `GUARDRAIL_ADDRESS`,
  `CREDENTIAL_ISSUER_ADDRESS`, `MERCHANT_<ID>_ADDRESS` for each merchant (ID upper-snake, e.g. `MERCHANT_BAMBOO_BIKES_ADDRESS`), `MERCHANT_<ID>_SEED`.
- `.env.guardrail`: `GUARDRAIL_SEED` only.

Commit a `.env.example` showing the keys with no values.

### 5.2 Python API (`roam_ledger.XrplLedger` implements `roam_contracts.Ledger`)

| Method | Behaviour |
|---|---|
| `build_checkout(quotes)` | Autofilled `Batch` from TRIP, flag `tfAllOrNothing`. One inner `EscrowCreate` per quote: `Destination=merchant_address`, `Amount`, `SourceTag=source_tag_for(invoice_id)`, `Memos=[{MemoType: hex(INVOICE_MEMO_TYPE), MemoData: invoice_id}]`, `CancelAfter` (see §6), `FinishAfter = now + 5s` (or a condition, stretch). The fee must account for 2 signers + inner txs. Returns `UnsignedTx(tx_json, invoice_ids)`. |
| `sign_as_agent(tx)` | Multi-sign with `AGENT_SEED`; returns a `signer_blob` (same format as guardrail: `{"Signer": {...}}`). |
| `submit_multisigned(tx, signer_blobs, quotes, emit)` | Combine signers (sorted by account, as XRPL requires), submit, wait for validation. Emits `batch.submitted` then `batch.validated` / `batch.failed`. Returns `CheckoutResult` with `EscrowRef`s (owner + sequence from metadata), totals, `viator_total`, `savings`. |
| `cancel_escrow(ref, emit)` | `EscrowCancel` (multi-signed by agent + guardrail key from `.env.guardrail`, or by any account since EscrowCancel is permissionless after `CancelAfter`). Emits `escrow.cancelled`. |
| `finish_escrow(ref, emit, fulfillment)` | `EscrowFinish`. Emits `escrow.finished`. |
| `has_credential(address)` | `ledger_entry` credential lookup (same logic the guardrail uses). |
| `wallet_state()` | Balance, sum locked in TRIP's escrows, signer list + quorum. Emit `wallet.updated` after every tx. |

Emitted events use `source="ledger"` and set `tx_hash` + `explorer_url` (`https://devnet.xrpl.org/transactions/<hash>` or the testnet equivalent).

### 5.3 `FakeLedger`

Same API, in memory: fake hashes (`sha256` of inputs), immediate "validation", balances that go down on checkout and up
on cancel. **Ship it in the first 2 hours.** B depends on it until Hour 20.

### 5.4 `python -m roam_ledger.demo`

Full on-ledger smoke test with no other feature running: load fixture quotes, then rewrite addresses with bootstrap
merchants, then `build_checkout`, then `sign_as_agent`, then sign as guardrail (local test helper), then `submit`, then print
explorer links, then `cancel_escrow` on the first escrow once `CancelAfter` passes.

## 6. Decisions to confirm (blocked on team questions, defaults given)

- **Currency (Q2):** default XRP, `ROAM_LEDGER_CURRENCY=XRP`, amounts 1:1 with the display value.
- **Cancel timing (Q3):** XRPL only allows `EscrowCancel` after `CancelAfter`. Default: `CancelAfter = now + ROAM_DEMO_CANCEL_SECONDS` (default 45) so the rainstorm refund works live. The quote's `cancel_after` stays the "real" policy shown in the UI.
- **Smart Escrow (XLS-100):** out of scope unless the spike finds it alongside `Batch`. Present it as the production path.

## 7. Tasks

**Hour 0–2:** spike (§4) + `FakeLedger` pushed.
**Hour 2–8:** `bootstrap` (accounts, multi-sig, credentials), `.env` outputs, `wallet_state`, `has_credential`.
**Hour 8–14:** `build_checkout`, `sign_as_agent`, `submit_multisigned`, `demo` CLI green on-ledger.
**Hour 14–20:** `cancel_escrow`, `finish_escrow`, events with explorer links, hand real `.env.*` files to A and B.
**Stretch:** sold-out revert (make one inner tx fail on-ledger, e.g. revoke a credential + `DepositAuth`); check-in via crypto-condition.

## 8. Acceptance tests

1. `bootstrap` run twice → second run is a no-op. `.env.ledger` is complete.
2. TRIP account: master disabled, signer list quorum 2. A tx signed by the agent alone → rejected (show in demo).
3. `demo` → one validated `Batch`, 2 escrows visible in the explorer with memos and distinct SourceTags.
4. Cancel after the window → TRIP balance back up by the escrow amount (minus fees).
5. `FakeLedger` and `XrplLedger` return structurally identical `CheckoutResult`s for the same input.

## 9. Config

`XRPL_RPC_URL`, `XRPL_NETWORK` (`devnet`|`testnet`), `ROAM_LEDGER_CURRENCY`, `ROAM_DEMO_CANCEL_SECONDS`, `.env.ledger`, `.env.guardrail`.
