# features/ledger — Owner C

> **Full spec: [`SPEC.md`](SPEC.md)** — everything you need to build this feature without waiting on anyone.

All XRPL code (`xrpl-py`): bootstrap, multi-sig, credentials, `Batch` (all-or-nothing) of `EscrowCreate`s, cancel/finish. Spec: `docs/SPEC.md` §4.3.

- Python library `roam_ledger` implementing `Ledger` + `FakeLedger` (in-memory, fake hashes, returns `contracts/fixtures/checkout_result.json`-shaped data).
- `python -m roam_ledger.bootstrap` — idempotent; writes `.env.ledger` and `.env.guardrail` (both git-ignored).
- `python -m roam_ledger.demo` — end-to-end on-ledger smoke test using a local test Key 2.

## Hour-0 spike
Check `feature` RPC on Devnet/Testnet for `Batch`, `Credentials`, `TokenEscrow`, Smart Escrow; confirm a multi-signed outer `Batch` is accepted. Post results to the team (risks R1–R3 in the spec).
