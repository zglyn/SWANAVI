# Ride to the next stop

Requests a car from the attraction that is ending to the next stop. The master calls `request_ride` on [Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) when an attraction is about to end so the car is there for the next stop. This package does not run that loop.

Sandbox is the default. No Uber token is read and no network call is made. A sandbox ride code starts with `SANDBOX-RIDE-`.

```python
from booking.assist.ride import AGENTCORE_TOOL, TOOL_SPEC, handler, request_ride

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a request_ride tool call, call handler(tool_input).
```

Tool name: `request_ride`.

## Input

| Field | Meaning |
| --- | --- |
| `fromSegmentId` | Attraction that is about to end. |
| `toSegmentId` | Next stop. |
| `pickupAt` | ISO-8601 time when the attraction ends. The car is requested for this time. |
| `pickupName` | Pickup place name. |
| `dropoffName` | Dropoff place name, the next stop. |
| `partySize` | People in the car. |

## Output

```json
{
  "status": "requested",
  "rideCode": "SANDBOX-RIDE-0123456789AB",
  "pickupAt": "2026-11-03T11:00:00+09:00",
  "dropoffName": "Nishiki Market",
  "partySize": 2,
  "reason": null
}
```

| Field | Meaning |
| --- | --- |
| `status` | `requested` or `failed` |
| `rideCode` | Starts with `SANDBOX-RIDE-` in the sandbox. `null` when failed. |
| `pickupAt` | Echoed from the input when it can be read. |
| `dropoffName` | Echoed from the input when it can be read. |
| `partySize` | Echoed when it is a positive integer, otherwise `null`. |
| `reason` | Why the ride was not requested. `null` when status is `requested`. |

A missing `pickupAt` or `dropoffName` returns `status` `failed`, `rideCode` `null`, and a `reason`. It does not raise. The same complete input returns the same sandbox ride code.

## Live Uber Rides API

Off unless both of these are set:

| Variable | Required value |
| --- | --- |
| `ROAM_RIDE_PROVIDER` | `live` |
| `UBER_ACCESS_TOKEN` | OAuth access token for the [Uber Rides API](https://developer.uber.com/docs/riders/references/api) (`request` scope) |

Any other `ROAM_RIDE_PROVIDER`, or a missing `UBER_ACCESS_TOKEN`, keeps the local sandbox. The client then calls only `https://sandbox-api.uber.com`. `https://api.uber.com` is never requested. A redirect off the sandbox host is refused. Unit tests do not call this client and do not hit production.

With both variables set, `request_ride` does two Uber Rides API calls, in order:

1. [Request estimate](https://developer.uber.com/docs/riders/ride-requests/tutorials/api/curl) — `POST /v1.2/requests/estimate`, from `pickupName` to `dropoffName` (`start_address` / `start_nickname` and `end_address` / `end_nickname`).
2. [Create a ride request](https://developer.uber.com/docs/riders/references/api/v1.2/requests-post) — `POST /v1.2/requests`, the same places, the `fare_id` from the estimate, and `scheduling.pickup_time` set to `pickupAt` so the car is there when the attraction ends.

The sandbox host is the one in the [Uber API sandbox](https://developer.uber.com/docs/riders/guides/sandbox) guide. The sandbox `POST /requests` call does not create a real-world trip. No card is sent.

## Tests

From the repository root:

```bash
python3 -m unittest booking.assist.ride.test_ride
```
