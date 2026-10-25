# Flight status

Reports whether one flight is on time, delayed, or cancelled. The master agent calls `flight_status` for each flight segment on a tick, before it replans. Pass the tick clock as `now`. Pass the sandbox feed when one arrived for that segment. `action` `replan` means the master should hand that flight to the replan path: a delay carries `delayMinutes`, and a cancellation carries `delayMinutes` 0. A later integrator wires that call into the master loop. This package does not run the loop, does not change the plan, and does not call the replan agents.

Sandbox only. No network, no AWS, no Amadeus, and no Uber. The caller supplies `now` and the optional `feed`. The tool does not read the wall clock. A missing field returns a result and does not raise.

```python
from booking.assist.flightstatus import AGENTCORE_TOOL, TOOL_SPEC, flight_status, handler

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a flight_status tool call, call handler(tool_input).
```

Tool name: `flight_status`.

## Input

| Field | Meaning |
| --- | --- |
| `tripId` | Trip the segment belongs to. |
| `now` | ISO-8601 timestamp supplied by the caller. A `Z` suffix is UTC. |
| `segment` | One segment: `segmentId`, `kind`, `from`, `to`, `departAt` or `departDate`, and `confirmationCode` or null. |
| `feed` | Optional `{event, delayMinutes}`. `event` is `on_time`, `delayed`, or `cancelled`. |

Omit `feed` when the caller has no status. That is `on_time` and `delayMinutes` 0.

## Output

```json
{
  "segmentId": "flight-1",
  "event": "delayed",
  "delayMinutes": 40,
  "action": "replan",
  "departAt": "2026-11-02T16:00:00Z"
}
```

| Field | Meaning |
| --- | --- |
| `segmentId` | Segment from the input. Empty when it was missing. |
| `event` | `on_time`, `delayed`, `cancelled`, or `not_a_flight`. |
| `delayMinutes` | Minutes late. `0` when the feed is omitted, the flight is on time, or it is cancelled. |
| `action` | `replan` or `none`. |
| `departAt` | Scheduled departure from the segment. A date-only `departDate` is returned as that date. |

`departAt` is not moved by `delayMinutes`. The segment in the input is not changed.

A missing field returns `action` `none` and does not raise:

```json
{
  "segmentId": "",
  "event": "",
  "delayMinutes": 0,
  "action": "none",
  "departAt": "",
  "error": "invalid_segment"
}
```

## Rules

- An omitted feed, or `event` `on_time`, sets `action` to `none` and `delayMinutes` to 0.
- `delayed` with `delayMinutes` greater than 0 sets `action` to `replan` and keeps that delay.
- `delayed` with `delayMinutes` of 0 or less is reported as `event` `on_time` and `action` `none`. A missing or unreadable delay is the same result.
- `cancelled` sets `action` to `replan` and `delayMinutes` to 0, including when the feed carried a positive delay.
- `kind` other than `flight` sets `event` to `not_a_flight` and `action` to `none`. The feed is ignored.
- A flight is missing a field when `tripId`, `now`, `segmentId`, `kind`, `from`, or `to` is blank, when neither `departAt` nor `departDate` can be read, or when `confirmationCode` is present and is not a string or null. `error` is `invalid_segment` and `action` is `none`.

## Tests

From the repository root:

```bash
PYTHONPATH=. python3 -m unittest booking.assist.flightstatus.test_status
```
