"""Result shape for flight booking."""

from __future__ import annotations

STATUSES = ("booked", "failed", "needs_user")


def booking_result(
    segment_id: str | None,
    status: str,
    confirmation_code: str | None = None,
    price: dict | None = None,
    error: str | None = None,
) -> dict:
    if status not in STATUSES:
        raise ValueError(f"invalid flight status: {status}")
    return {
        "segmentId": segment_id,
        "kind": "flight",
        "status": status,
        "confirmationCode": confirmation_code,
        "price": price,
        "error": error,
    }
