# Hotel booking

Books one hotel segment from a finished trip plan. The default provider is a deterministic sandbox: no network, no AWS, and no hotel API key.

## Call

```python
from booking.providers.hotels import book

book(segment, travelers, trip_id)
```

Segment fields: `segmentId`, `kind` (`"hotel"`), `city`, `checkIn`, `checkOut` (ISO dates), `rooms`, `guests`.

Result fields: `segmentId`, `kind` (`"hotel"`), `status` (`booked`, `failed`, or `needs_user`), `confirmationCode`, `price` (`{"amount", "currency"}` or `null`), `error`. Amounts are decimal strings. Sandbox confirmation codes start with `SANDBOX-`. The same segment, travelers, and trip id always return the same code and price.

Incomplete input returns `needs_user`. Provider failures return `failed` and do not raise. On a sandbox segment, `sandboxFault: "error"` forces that failure. Kyoto is 220.00 USD per room-night (3 nights, 1 room → `660.00`).

Card and payment fields are refused with `needs_user`. Nothing is charged.

## Live adapter

Leave this unset. The sandbox is the default.

- `HOTEL_BOOKING_PROVIDER=live`
- `HOTEL_BOOKING_API_BASE` — https URL whose host is sandbox, test, or local. Production hotel hosts are refused.
- `HOTEL_BOOKING_API_KEY` — optional. Never required for the sandbox.

The live adapter is not called unless that provider is selected. It does not follow redirects and does not send card data.

## Tests

From the repository root:

```bash
python3 -m unittest discover -s booking/providers/hotels/tests -v
```
