"""Live attraction adapter.

Selected only when `ROAM_ATTRACTION_PROVIDER=live`. This build never calls a
ticket API and never charges a card. Production hosts are refused with no request.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

from .errors import AttractionProviderError
from .result import booking_result

SANDBOX_URL_ENV = "ROAM_ATTRACTION_SANDBOX_URL"

_BLOCKED_HOST_PARTS = (
    "amazonaws.com",
    "amadeus",
    "booking.",
    "expedia",
    "getyourguide",
    "klook",
    "ticketmaster",
    "tripadvisor",
    "viator",
)


class LiveAttractionAdapter:
    """Gated seam for a future sandbox HTTP client. Performs no I/O."""

    def book(self, segment: dict, travelers: list, trip_id: str) -> dict:
        del travelers, trip_id
        segment_id = segment.get("segmentId") if isinstance(segment, dict) else None
        url = os.environ.get(SANDBOX_URL_ENV, "").strip()
        if not url:
            return booking_result(
                segment_id,
                "needs_user",
                error=(
                    f"{SANDBOX_URL_ENV} is not set; no request was sent and no card was charged"
                ),
            )
        host = _hostname(url)
        if host is None or not _is_non_production_host(host):
            raise AttractionProviderError(
                f"refused attraction host {host!r}; no request was sent and no card was charged"
            )
        return booking_result(
            segment_id,
            "needs_user",
            error=(
                "live attraction adapter does not place orders in this build; "
                "no request was sent and no card was charged"
            ),
        )


def _hostname(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return parsed.hostname.lower().rstrip(".")


def _is_non_production_host(host: str) -> bool:
    if any(part in host for part in _BLOCKED_HOST_PARTS):
        return False
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    labels = host.split(".")
    return any(label in {"sandbox", "stub", "localhost", "local"} for label in labels)
