# Hotel booking

Amazon Bedrock AgentCore tool that books one hotel segment from a finished trip plan. The only supported invoke path is the AgentCore runtime: it calls `handler`, and `handler` calls `book`.

## Tool

`TOOL_SPEC["name"]` is `book_hotel`.

Input properties:

| Field | Meaning |
|---|---|
| `segment` | `segmentId`, `kind` (`"hotel"`), `city`, `checkIn`, `checkOut` (ISO dates), `rooms`, `guests`. Optional `cityCode` (IATA) and `hotelId` for Amadeus. |
| `travelers` | People on the trip. A name, or an object with `name` and optional `email` / `phone`. |
| `trip_id` | Trip id. |

Result: `segmentId`, `kind` (`"hotel"`), `status` (`booked`, `failed`, or `needs_user`), `confirmationCode`, `price` (`{"amount", "currency"}` or null), `error`. Amounts are decimal strings.

```python
from booking.providers.hotels import TOOL_SPEC, handler

handler({"segment": segment, "travelers": travelers, "trip_id": trip_id})
```

AgentCore Gateway passes those input properties as the handler event. When the runtime sets `bedrockAgentCoreToolName`, it must be `book_hotel` (a `{target}___book_hotel` prefix is stripped).

## Sandbox

Default when `ROAM_HOTEL_PROVIDER` is unset or `sandbox`. Deterministic, no network, no AWS call, and no Amadeus keys. The same segment, travelers, and trip id always return the same confirmation code. Sandbox codes start with `SANDBOX-`.

Kyoto is 220.00 USD per room-night (3 nights, 1 room → `660.00`). Incomplete input returns `needs_user`. Provider failures return `failed` and do not raise. `sandboxFault: "error"` on a segment forces that failure. Card and payment fields return `needs_user`. Nothing is charged.

## Amadeus test

Live mode runs only when all of these are set:

- `ROAM_HOTEL_PROVIDER=live`
- `AMADEUS_CLIENT_ID`
- `AMADEUS_CLIENT_SECRET`
- `AMADEUS_HOSTNAME=test`

Any other hostname, including `production`, is refused before a request is made. The client talks only to `https://test.api.amadeus.com`. It does not follow redirects and does not follow `self` links from responses, so a payload cannot move the call onto production (`api.amadeus.com`).

Flow:

1. OAuth2 client credentials, `POST /v1/security/oauth2/token`.
2. If the segment has no `hotelId`, [Hotel List](https://developers.amadeus.com/self-service/category/hotels/api-doc/hotel-list) supplies ids: `GET /v1/reference-data/locations/hotels/by-city`.
3. [Hotel Search](https://developers.amadeus.com/self-service/category/hotels/api-doc/hotel-search): `GET /v3/shopping/hotel-offers`.
4. [Hotel Booking](https://developers.amadeus.com/self-service/category/hotels/api-doc/hotel-booking): `POST /v1/booking/hotel-bookings`.

Official walkthrough of that sequence: [Amadeus hotel APIs](https://developers.amadeus.com/self-service/apis-docs/guides/developer-guides/resources/).

Deposit and prepay offers are skipped because those policies charge at booking. The Hotel Booking body has guests and rooms only. It never includes `payments` or a card number, including cards found on the segment or travelers. Unit tests do not call this client and do not need Amadeus keys.

## Tests

From the repository root:

```bash
python3 -m unittest discover -s booking/providers/hotels/tests -v
```
