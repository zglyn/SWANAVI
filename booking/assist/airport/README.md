# Airport departure

Says when to leave a hotel for a flight. The master agent calls `airport_leave` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime the morning of a flight. This package does not run that loop, does not book the flight, and does not check the traveler in.

Sandbox only. The tool subtracts a fixed buffer from `departAt`. It does not call an airline API, open the network, or call AWS.

```python
from booking.assist.airport import AGENTCORE_TOOL, TOOL_SPEC, airport_leave, handler

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns an airport_leave tool call, call handler(tool_input).
```

Tool name: `airport_leave`.

## Input

| Field | Meaning |
| --- | --- |
| `flightSegmentId` | Flight the traveler is leaving for. |
| `departAt` | ISO-8601 departure time supplied by the caller. |
| `international` | `true` for an international flight. `false` for domestic. |
| `hotelCheckoutAt` | ISO-8601 hotel checkout, or `null` when there is no checkout to compare. |

## Output

```json
{
  "flightSegmentId": "flight-1",
  "leaveBy": "2026-11-06T11:00:00Z",
  "ok": true,
  "reason": "leave 3 hours before an international departure"
}
```

| Field | Meaning |
| --- | --- |
| `flightSegmentId` | Echoed from the input. Empty when it is not a string. |
| `leaveBy` | ISO-8601 time to leave, in UTC. Empty when `departAt` cannot be read. |
| `ok` | `false` when `departAt` is missing or hotel checkout is after `leaveBy`. |
| `reason` | Why the result is ok, or why it is not. |

## Rules

An international flight uses a 3 hour buffer. A domestic flight uses a 2 hour buffer. `leaveBy` is `departAt` minus that buffer.

`ok` is false when `hotelCheckoutAt` is after `leaveBy`: the traveler would still be at the hotel when they need to be gone. Checkout at exactly `leaveBy` is ok. A null or omitted checkout does not fail the result.

A missing `departAt` returns `ok` false and does not raise. An unreadable timestamp, a non-boolean `international`, and any other partial input also return a result and do not raise.

Clocks are UTC. A `Z` suffix and a numeric offset are the same instant. A timestamp with no offset is read as UTC. `leaveBy` is written as `YYYY-MM-DDTHH:MM:SSZ`.

## Tests

From the repository root:

```bash
python3 -m unittest booking.assist.airport.test_leave
```
