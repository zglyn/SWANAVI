"""The co-signer: holds the policy and Key 2, gathers facts, runs the rules, and signs only when nothing is violated."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, TypeVar

from roam_contracts.models import CosignRequest, CosignResponse, PolicyConfig, PolicyDecision, Violation, ViolationRule
from roam_guardrail.rules import Facts, evaluate
from roam_guardrail.sources import Credentials, utc_now

Keys = Callable[[list[str]], dict[str, str]]
Signer = Callable[[dict[str, Any]], dict[str, Any]]
T = TypeVar("T")


class SpendBook:
    """Activity spend posted from a booking, a ledger row, or a co-sign. One day has one total, so the decision and the write share a lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: list[tuple[date, Decimal]] = []

    def spent_on(self, day: date) -> Decimal:
        with self._lock:
            return self._sum(day)

    def record(self, day: date, amount: Decimal) -> None:
        with self._lock:
            self._rows.append((day, amount))

    def clear(self) -> None:
        with self._lock:
            self._rows.clear()

    def commit(self, day: date, proposal: Callable[[Decimal], tuple[Decimal | None, T]]) -> T:
        with self._lock:
            extra, value = proposal(self._sum(day))
            if extra is not None:
                self._rows.append((day, extra))
            return value

    def _sum(self, day: date) -> Decimal:
        return sum((amount for row_day, amount in self._rows if row_day == day), Decimal("0"))


class Cosigner:
    """Stored policy wins over the request. Daily spend is the spend book. request.spent_today is not read."""

    def __init__(
        self,
        credentials: Credentials,
        sign: Signer,
        keys: Keys | None = None,
        trip_account: str | None = None,
        policy_file: Path | None = None,
        xrp_as_rlusd: bool = True,
        clock: Callable[[], datetime] = utc_now,
        baseline: PolicyConfig | None = None,
    ) -> None:
        self.credentials = credentials
        self.sign = sign
        self.keys = keys
        self.trip_account = trip_account
        self.policy_file = policy_file
        self.xrp_as_rlusd = xrp_as_rlusd
        self.clock = clock
        self.baseline = baseline or PolicyConfig()
        self.book = SpendBook()
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
        self.book.clear()
        return self.set_policy(self.baseline)

    def record_spend(self, amount: Decimal, on: date | None = None) -> None:
        self.book.record(on or self.clock().date(), amount)

    def evaluate(self, request: CosignRequest) -> PolicyDecision:
        """Dry run: the same decision cosign would make, without signing or counting the spend."""
        now = self.clock()
        return self._evaluate(request, self.book.spent_on(now.date()), now)

    def cosign(self, request: CosignRequest) -> CosignResponse:
        now = self.clock()

        def proposal(spent: Decimal) -> tuple[Decimal | None, CosignResponse]:
            decision = self._evaluate(request, spent, now)
            if not decision.approved:
                return None, CosignResponse(decision=decision)
            try:
                blob = self.sign(request.tx.tx_json)
            except Exception as error:  # a tx xrpl-py can't even parse is not one we'll put our key on
                decision = decision.model_copy(update={
                    "approved": False,
                    "remaining_daily_budget": decision.remaining_daily_budget + decision.total,
                    "violations": [Violation(rule=ViolationRule.TX_QUOTE_MISMATCH, detail=f"Transaction can't be signed: {error}")],
                })
                return None, CosignResponse(decision=decision)
            return decision.total, CosignResponse(decision=decision, signer_blob=blob)

        return self.book.commit(now.date(), proposal)

    def _evaluate(self, request: CosignRequest, spent: Decimal, now: datetime) -> PolicyDecision:
        quotes = request.quotes
        if not quotes:
            return PolicyDecision(
                approved=False, total=Decimal("0"), remaining_daily_budget=self.policy.max_daily_budget - spent,
                violations=[Violation(rule=ViolationRule.TX_QUOTE_MISMATCH, detail="No quotes to pay for")],
            )
        facts = Facts(
            now=now,
            merchant_keys=self.keys([q.merchant_id for q in quotes]) if self.keys else None,
            verified=self.credentials.verified([q.merchant_address for q in quotes], now),
            trip_account=self.trip_account,
            xrp_as_rlusd=self.xrp_as_rlusd,
        )
        return evaluate(quotes, request.tx.tx_json, self.policy, spent, facts)

    def _load_policy(self) -> PolicyConfig:
        if self.policy_file and self.policy_file.exists():
            return PolicyConfig.model_validate(json.loads(self.policy_file.read_text()))
        return self.baseline


def policy_file_from_env() -> Path | None:
    path = os.environ.get("GUARDRAIL_POLICY_FILE")
    return Path(path) if path else None
