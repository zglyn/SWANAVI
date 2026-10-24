# Attraction tickets

Sandbox booking for one trip-plan segment of kind `attraction`. No AWS calls and no ticket-provider API keys.

```python
from booking.providers.attractions import book

result = book(segment, travelers, trip_id)
```

## Segment

`segmentId`, `kind` (`"attraction"`), `name`, `city`, `date` (`YYYY-MM-DD`), `partySize`, and `time` (`HH:MM` or `null`).

## Result

`segmentId`, `kind` (`"attraction"`), `status` (`booked`, `failed`, or `needs_user`), `confirmationCode` or `null`, `price` (`{"amount", "currency"}`) or `null`, and `error` or `null`.

`amount` is a decimal string such as `"36.00"`. Sandbox currency is `USD`. The same segment, travelers, and `trip_id` always return the same confirmation code and price. Sandbox codes start with `SANDBOX-`. Incomplete segments return `needs_user`. Provider errors return `failed` and are not raised.

## Providers

`ROAM_ATTRACTION_PROVIDER` defaults to `sandbox`. Set it to `live` to select the live adapter. That adapter reads `ROAM_ATTRACTION_SANDBOX_URL`, refuses production ticket hosts, and does not send a request or charge a card.

`ROAM_ATTRACTION_FORCE_ERROR=1` makes the sandbox provider fail so callers can check the `failed` result.

## Tests

From the repo root:

```bash
python3 -m unittest booking.providers.attractions.test_book
```
