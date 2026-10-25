# Attraction confirmation email

`verify_attraction_email` is an Amazon Bedrock AgentCore tool. The master agent calls this tool on the AgentCore runtime after `book_attraction`.

```python
from booking.verify.attractions import (
    VERIFY_ATTRACTION_EMAIL_TOOL,
    sample_email,
    verify,
    verify_attraction_email,
)

email = sample_email(segment, confirmation_code, travelers, trip_id)
verify(email, segment, confirmation_code, travelers)
```

`VERIFY_ATTRACTION_EMAIL_TOOL` is the tool spec (`name` is `verify_attraction_email`). The runtime handler is `verify_attraction_email`. `action` `sample_email` calls `sample_email`. `action` `verify` calls `verify`. This package does not call AWS itself. AgentCore is the caller.

## Sandbox

Messages are built in memory. There is no network call, no real inbox, and no AWS client. The sender is `tickets@sandbox.roam402.invalid`. `receivedAt` is the visit date at 18:00:00Z when that date is a real `YYYY-MM-DD`, otherwise `1970-01-01T00:00:00Z`.

## sample_email

`sample_email(segment, confirmation_code, travelers, trip_id)` returns `from`, `to`, `subject`, `body`, and `receivedAt`.

The body includes the confirmation code, attraction name, city, date, and party size. `to` is taken from traveler `email` when present, otherwise the traveler name at `traveler@sandbox.roam402.invalid`.

## Fields that are checked

`verify(email, segment, confirmation_code, travelers)` returns `segmentId`, `kind` (`"attraction"`), `verified`, and `reason`.

`verified` is true only when all of these appear in the subject or the body:

| Field | Where it comes from | How it matches |
| --- | --- | --- |
| Confirmation code | `confirmation_code` | Exact text |
| Attraction name | `segment["name"]` | Exact text |
| Date | `segment["date"]` | Exact `YYYY-MM-DD` |
| Party size | `segment["partySize"]` | Whole number |

Each field can be in the subject, the body, or split across them. `from`, `to`, and `receivedAt` are not checked. The city is written in the sample body and is not a checked field. Traveler names are not a checked field.

Party size is matched as its own number after the confirmation code and the visit date are removed from the text, so a digit inside the code or the date does not count.

A wrong confirmation code or a wrong date leaves `verified` false. A missing name or party size does too. `reason` lists the missing fields, or says that the confirmation code, attraction name, date, and party size match.

A malformed email, a non-object payload, or any other bad input returns `verified` false. `verify` does not raise.

## Tests

From the repo root:

```bash
python3 -m unittest booking.verify.attractions.test_verify
```
