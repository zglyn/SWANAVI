# Flight booking

Books one flight segment from a finished trip plan. The default provider is a deterministic local sandbox: confirmation codes start with `SANDBOX-`, and it does not use the network.

The only supported invoke path is the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-tools.html) runtime. Register the tool below and let the runtime call `handler`. `handler` calls `book()`.

```python
from booking.providers.flights import AGENTCORE_TOOL, TOOL_SPEC, handler

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a book_flight tool call, call handler(tool_input).
```

Tool name: `book_flight`.

Input: `segment`, `travelers`, and `trip_id`.

`segment` fields: `segmentId`, `kind` (`"flight"`), `from`, `to`, `departDate`, `returnDate` (`YYYY-MM-DD` or omit/`null` for one-way), `cabin` (`economy`, `premium_economy`, `business`, `first`), `travelerIds`.

Each traveler needs `id` and a name (`givenName` and `familyName`, or `name`).

Result: `segmentId`, `kind` (`"flight"`), `status` (`booked`, `failed`, or `needs_user`), `confirmationCode` or `null`, `price` (`{"amount", "currency"}`) or `null`, and `error` or `null`. `amount` is a decimal string such as `"248.00"`. Sandbox currency is `USD`. The same segment, travelers, and `trip_id` always return the same sandbox confirmation code and price. `book` does not raise.

`ROAM_FLIGHT_FORCE_ERROR=1` makes the sandbox provider fail so callers can check the `failed` result.

## Live Amadeus test client

Off unless all of these are set:

| Variable | Required value |
|---|---|
| `ROAM_FLIGHT_PROVIDER` | `live` |
| `AMADEUS_CLIENT_ID` | Amadeus test client id |
| `AMADEUS_CLIENT_SECRET` | Amadeus test client secret |
| `AMADEUS_HOSTNAME` | `test` |

`AMADEUS_HOSTNAME` must be exactly `test`. The client then calls only `https://test.api.amadeus.com`. Any other hostname, including production, is refused before a socket is opened. `https://api.amadeus.com` is never requested.

With those variables set, `book()` does two Amadeus Self-Service calls, in order:

1. [Flight Offers Search](https://developers.amadeus.com/self-service/category/flights/api-doc/flight-offers-search) — `POST /v2/shopping/flight-offers`
2. [Flight Create Orders](https://developers.amadeus.com/self-service/category/flights/api-doc/flight-create-orders) — `POST /v1/booking/flight-orders`

The client authenticates with the [Amadeus test OAuth2 client-credentials API](https://developers.amadeus.com/self-service/apis-docs/guides/developer-guides/API-Keys/) and keeps the token in memory for those two calls. Test versus production hosts are described in [Moving to production](https://developers.amadeus.com/self-service/apis-docs/guides/developer-guides/API-Keys/moving-to-production/).

Offers with `paymentCardRequired` are skipped. The create-order body has no `creditCard`, card number, or `formOfPayments`. Ticketing is `DELAY_TO_CANCEL` (hold the test order and cancel it if unpaid), not `CONFIRM`. A redirect off `test.api.amadeus.com` is refused. Live traveler profiles also need `dateOfBirth`, `gender`, `email`, `countryCallingCode`, and `phoneNumber`; if those are missing the result is `needs_user` and Amadeus is not called.

This live client is not used by the unit tests.

## Tests

From the repo root, with no Amadeus keys:

```bash
python3 -m unittest booking.providers.flights.test_book
```
