from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from roam_contracts.models import CosignRequest, CosignResponse, PolicyConfig, PolicyDecision
from roam_guardrail.cosigner import Cosigner, policy_file_from_env
from roam_guardrail.sources import (
    ROOT,
    MerchantKeys,
    OfflineCredentials,
    XrplCredentials,
    load_env_file,
    load_wallet,
    signer_blob,
)

load_env_file(ROOT / ".env.guardrail")
load_env_file(ROOT / ".env.ledger")

issuer = os.environ.get("CREDENTIAL_ISSUER_ADDRESS")
offline = os.environ.get("GUARDRAIL_OFFLINE") == "1" or not issuer
check_signatures = os.environ.get("GUARDRAIL_SKIP_QUOTE_SIG") != "1"
wallet, wallet_from_seed = load_wallet()

cosigner = Cosigner(
    credentials=OfflineCredentials() if offline else XrplCredentials(issuer),
    sign=lambda tx_json: signer_blob(tx_json, wallet),
    keys=MerchantKeys().for_merchants if check_signatures else None,
    trip_account=os.environ.get("TRIP_ADDRESS"),
    policy_file=policy_file_from_env(),
    xrp_as_rlusd=os.environ.get("GUARDRAIL_XRP_AS_RLUSD", "1") == "1",
)

http = FastAPI(title="Swanavi guardrail")


@http.get("/policy")
def get_policy() -> PolicyConfig:
    return cosigner.get_policy()


@http.put("/policy")
def put_policy(policy: PolicyConfig) -> PolicyConfig:
    try:
        return cosigner.set_policy(policy)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


@http.post("/cosign")
def cosign(request: CosignRequest) -> CosignResponse:
    """Always 200: decision.approved says whether the guardrail signed."""
    return cosigner.cosign(request)


@http.post("/evaluate")
def evaluate(request: CosignRequest) -> PolicyDecision:
    """Dry run for previews. Never signs and never counts the spend."""
    return cosigner.evaluate(request)


@http.post("/reset")
def reset() -> PolicyConfig:
    return cosigner.reset()


@http.get("/status")
def status():
    """How this guardrail is wired, so a misconfigured demo is obvious at a glance."""
    return {
        "guardrail_address": wallet.classic_address,
        "key_from_seed": wallet_from_seed,
        "credentials": "allowlist (offline)" if offline else f"xrpl, issuer {issuer}",
        "quote_signatures": "checked" if check_signatures else "skipped",
        "trip_account": cosigner.trip_account,
    }


def main() -> None:
    import uvicorn

    uvicorn.run(http, host="0.0.0.0", port=int(os.environ.get("GUARDRAIL_PORT", "8002")))


if __name__ == "__main__":
    main()
