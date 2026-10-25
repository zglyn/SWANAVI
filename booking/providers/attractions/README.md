# Attraction tickets

`book_attraction` is an Amazon Bedrock AgentCore tool. The only supported invoke path is the AgentCore runtime. The runtime passes the attraction segment, travelers, and `trip_id`. The handler calls `book()`.

```python
from booking.providers.attractions import BOOK_ATTRACTION_TOOL, book_attraction

book_attraction(segment, travelers, trip_id)
```

`BOOK_ATTRACTION_TOOL` is the tool spec (`name` is `book_attraction`). This package does not call AWS itself. AgentCore is the caller.

## Segment

`segmentId`, `kind` (`"attraction"`), `name`, `city`, `date` (`YYYY-MM-DD`), `partySize`, and `time` (`HH:MM` or `null`).

## Result

`segmentId`, `kind` (`"attraction"`), `status` (`booked`, `failed`, or `needs_user`), `confirmationCode` or `null`, `price` (`{"amount", "currency"}`) or `null`, and `error` or `null`.

`amount` is a decimal string such as `"36.00"`. Sandbox currency is `USD`. The same segment, travelers, and `trip_id` always return the same confirmation code and price. Sandbox codes start with `SANDBOX-`. Incomplete segments return `needs_user`. Provider errors return `failed` and are not raised.

## Sandbox

`ROAM_ATTRACTION_PROVIDER` defaults to `sandbox`. No Amadeus keys are read and no network call is made.

`ROAM_ATTRACTION_FORCE_ERROR=1` makes the sandbox provider fail so callers can check the `failed` result.

## Live API

Amadeus Tours and Activities (search, then book) on the Amadeus test host `https://test.api.amadeus.com`.

Docs:

- [Tours and Activities](https://developers.amadeus.com/self-service/category/destination-experiences/api-doc/tours-and-activities)
- [API reference](https://developers.amadeus.com/self-service/category/destination-experiences/api-doc/tours-and-activities/api-reference)
- [Destination experiences guide](https://amadeus4dev.github.io/developer-guides/resources/destination-experiences/)
- [Authorization](https://developers.amadeus.com/self-service/apis-docs/guides/developer-guides/API-Keys/authorization/)

Set all of these. Any other `AMADEUS_HOSTNAME` is refused before a request.

- `ROAM_ATTRACTION_PROVIDER=live`
- `AMADEUS_CLIENT_ID`
- `AMADEUS_CLIENT_SECRET`
- `AMADEUS_HOSTNAME=test`

The client gets a test-host token, resolves the city on the test host, searches `GET /v1/shopping/activities`, then retrieves `GET /v1/shopping/activities/{id}`. The provider `bookingLink` is not opened. Card fields are refused. Nothing is charged. That stop returns `needs_user`. Unit tests do not select this client and do not need keys.

## Tests

From the repo root:

```bash
python3 -m unittest booking.providers.attractions.test_book
```
