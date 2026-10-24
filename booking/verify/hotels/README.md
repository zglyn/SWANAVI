# Hotel confirmation email

Sandbox check that the email a traveler would get after a hotel books matches the hotel segment. The master agent calls this tool on the Amazon Bedrock AgentCore runtime after `book_hotel`.

No network, no real inbox, and no AWS. `sample_email` builds the message in memory. `verify` only reads that message. Nothing is sent or fetched.

## Tool

`verify_hotel_email` (`TOOL_SPEC["name"]`) is the AgentCore tool. The runtime calls `handler`, which calls `verify` unless `operation` is `sample_email`.

```python
from booking.verify.hotels import handler, sample_email, verify

email = sample_email(segment, confirmation_code, travelers, trip_id)
verify(email, segment, confirmation_code, travelers)

handler({
    "email": email,
    "segment": segment,
    "confirmation_code": confirmation_code,
    "travelers": travelers,
})
```

`confirmationCode` is accepted as an alias of `confirmation_code`, matching the `book_hotel` result. When the runtime sets `bedrockAgentCoreToolName`, it must be `verify_hotel_email` (a `{target}___verify_hotel_email` prefix is stripped).

`sample_email` returns `from`, `to`, `subject`, `body`, and `receivedAt`. The body includes the confirmation code, city, check-in, check-out, and guest names. `from` is `hotel-confirmations@sandbox.swanavi.invalid`. `receivedAt` is the fixed sandbox time `2026-01-01T12:00:00Z`.

## Fields checked

`verified` is true only when every field below appears in the subject or the body:

| Field | Where it comes from |
|---|---|
| Confirmation code | `confirmation_code` argument, exact match |
| City | `segment["city"]` |
| Check-in | `segment["checkIn"]` as `YYYY-MM-DD` |
| Check-out | `segment["checkOut"]` as `YYYY-MM-DD` |
| Guest names | Each traveler, a name or an object with `name` |

A wrong confirmation code or wrong check-in or check-out sets `verified` to false. `from`, `to`, and `receivedAt` are not checked. A missing or malformed email returns `verified: false` and does not raise.

The result is `segmentId`, `kind` (`"hotel"`), `verified`, and `reason`.

## Tests

From the repository root:

```bash
python3 -m unittest discover -s booking/verify/hotels/tests -v
```
