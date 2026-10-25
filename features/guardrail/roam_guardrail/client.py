"""The two Guardrail implementations the orchestrator can use: the real service over HTTP, and an in-process fake
that runs the same rules but never holds a real key."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import httpx

from roam_contracts.models import CosignRequest, CosignResponse, PolicyConfig, PolicyDecision
from roam_guardrail.cosigner import Cosigner, Keys
from roam_guardrail.sources import OfflineCredentials, utc_now

FAKE_SIGNER = {"Signer": {"Account": "rGuardrailFAKE", "SigningPubKey": "00", "TxnSignature": "00"}}


class HttpGuardrail:
    def __init__(self, base_url: str = "http://localhost:8002", client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=15)

    def get_policy(self) -> PolicyConfig:
        return PolicyConfig.model_validate(self._call("GET", "/policy"))

    def set_policy(self, policy: PolicyConfig) -> PolicyConfig:
        return PolicyConfig.model_validate(self._call("PUT", "/policy", policy.model_dump(mode="json")))

    def cosign(self, request: CosignRequest) -> CosignResponse:
        return CosignResponse.model_validate(self._call("POST", "/cosign", request.model_dump(mode="json")))

    def evaluate(self, request: CosignRequest) -> PolicyDecision:
        return PolicyDecision.model_validate(self._call("POST", "/evaluate", request.model_dump(mode="json")))

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        response = self.client.request(method, self.base_url + path, json=body)
        response.raise_for_status()
        return response.json()


class FakeGuardrail(Cosigner):
    """Same rule engine, offline credential allowlist, and a dummy signer blob when approved.
    Pass merchant keys to also check quote signatures; by default that rule is skipped."""

    def __init__(self, keys: Keys | None = None, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(credentials=OfflineCredentials(), sign=lambda tx: dict(FAKE_SIGNER), keys=keys, clock=clock)
