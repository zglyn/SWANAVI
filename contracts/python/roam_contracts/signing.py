"""Canonical bytes a merchant signs (ed25519) and the guardrail verifies. Shared so neither feature imports the other."""

import json

from .models import Quote


def quote_signing_bytes(quote: Quote) -> bytes:
    body = quote.model_dump(mode="json", exclude={"merchant_signature", "merchant_verified"})
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
