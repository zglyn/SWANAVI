"""The co-signer: holds the policy and Key 2, gathers facts, runs the rules, and signs only when nothing is violated."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from roam_contracts.models import CosignRequest, CosignResponse, PolicyConfig, PolicyDecision, Violation, ViolationRule
from roam_guardrail.rules import Facts, evaluate
from roam_guardrail.sources import Credentials, utc_now

Keys = Callable[[list[str]], dict[str, str]]
Signer = Callable[[dict[str, Any]], dict[str, Any]]


class Cosigner:
    """The request's own policy and spent_today are hints from the agent, not authority: the stored policy always wins,
    and spending counts at least what this guardrail has already co-signed today."""

    def __init__(
        self,
        credentials: Credentials,
        sign: Signer,
        keys: Keys | None = None,
        trip_account: str | None = None,
        policy_file: Path | None = None,
        xrp_as_rlusd: bool = True,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.credentials = credentials
        self.sign = sign
        self.keys = keys
        self.trip_account = trip_account
        self.policy_file = policy_file
        self.xrp_as_rlusd = xrp_as_rlusd
        self.clock = clock
        self.spent: dict[date, Decimal] = {}
        self.policy = self._load_policy()

    def get_policy(self) -> PolicyConfig:
        return self.policy

    def set_policy(self, policy: PolicyConfig) -> PolicyConfig:
        if policy.max_per_item <= 0 or policy.max_daily_budget <= 0:
            raise ValueError("caps must be greater than 0")
        if policy.max_per_item > policy.max_daily_budget:
            raise ValueError("max_per_item can't be more than max_daily_budget")
        self.policy = policy
        if self.policy_file:
            self.policy_file.write_text(policy.model_dump_json(indent=2))
        return policy

    def reset(self) -> PolicyConfig:
        self.spent.clear()
        return self.set_policy(PolicyConfig())

    def evaluate(self, request: CosignRequest) -> PolicyDecision:
        """Dry run: the same decision cosign would make, without signing or counting the spend."""
        now = self.clock()
        quotes = request.quotes
        if not quotes:
            return PolicyDecision(approved=False, total=Decimal("0"), remaining_daily_budget=self._remaining(request, now),
                                  violations=[Violation(rule=ViolationRule.TX_QUOTE_MISMATCH, detail="No quotes to pay for")])
        facts = Facts(
            now=now,
            merchant_keys=self.keys([q.merchant_id for q in quotes]) if self.keys else None,
            verified=self.credentials.verified([q.merchant_address for q in quotes], now),
            trip_account=self.trip_account,
            xrp_as_rlusd=self.xrp_as_rlusd,
        )
        return evaluate(quotes, request.tx.tx_json, self.policy, self._spent(request, now), facts)

    def cosign(self, request: CosignRequest) -> CosignResponse:
        decision = self.evaluate(request)
        if not decision.approved:
            return CosignResponse(decision=decision)
        try:
            blob = self.sign(request.tx.tx_json)
        except Exception as error:  # a tx xrpl-py can't even parse is not one we'll put our key on
            decision = decision.model_copy(update={
                "approved": False,
                "remaining_daily_budget": decision.remaining_daily_budget + decision.total,
                "violations": [Violation(rule=ViolationRule.TX_QUOTE_MISMATCH, detail=f"Transaction can't be signed: {error}")],
            })
            return CosignResponse(decision=decision)
        today = self.clock().date()
        self.spent[today] = self.spent.get(today, Decimal("0")) + decision.total
        return CosignResponse(decision=decision, signer_blob=blob)

    def _spent(self, request: CosignRequest, now: datetime) -> Decimal:
        return max(request.spent_today, self.spent.get(now.date(), Decimal("0")))

    def _remaining(self, request: CosignRequest, now: datetime) -> Decimal:
        return self.policy.max_daily_budget - self._spent(request, now)

    def _load_policy(self) -> PolicyConfig:
        if self.policy_file and self.policy_file.exists():
            return PolicyConfig.model_validate(json.loads(self.policy_file.read_text()))
        return PolicyConfig()


def policy_file_from_env() -> Path | None:
    path = os.environ.get("GUARDRAIL_POLICY_FILE")
    return Path(path) if path else None
