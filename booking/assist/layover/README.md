# Flight connection

Checks that the time between an inbound flight and an outbound flight covers the connection. The master agent calls `check_layover` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime between those flights.

This package does not run that loop and does not change a plan. A later integrator wires `check_layover` into the master.

Sandbox only. The caller supplies both clocks and both airports. This package does not read the wall clock, call an airline API, open the network, or call AWS.

```python
from booking.assist.layover import AGENTCORE_TOOL, TOOL_SPEC, check_layover, handler

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a check_layover tool call, call handler(tool_input).
```

Tool name: `check_layover`.

## Input

| Field | Meaning |
| --- | --- |
| `inbound.segmentId` | `segmentId` of the arriving flight. |
| `inbound.arriveAt` | ISO-8601 arrival instant. A `Z` suffix is UTC. |
| `inbound.airport` | Arrival airport. Not looked up. |
| `outbound.segmentId` | `segmentId` of the departing flight. |
| `outbound.departAt` | ISO-8601 departure instant. A `Z` suffix is UTC. |
| `outbound.airport` | Departure airport. Not looked up. |
| `international` | `true` for an international connection. `false` for domestic. Must be a boolean. |

## Output

```json
{
  "ok": false,
  "gapMinutes": 60,
  "minimumMinutes": 90,
  "shortfallMinutes": 30,
  "action": "replan",
  "reason": "short"
}
```

| Field | Meaning |
| --- | --- |
| `ok` | `true` only when the airports match and the gap meets the minimum. |
| `gapMinutes` | `departAt` minus `arriveAt`, in whole minutes. A partial minute does not count. |
| `minimumMinutes` | `90` when `international` is true. `45` when it is false. |
| `shortfallMinutes` | `minimumMinutes - gapMinutes` when the gap is shorter than the minimum. `0` when the gap is long enough. |
| `action` | `none`, `replan`, or `needs_user`. |
| `reason` | `enough`, `short`, `inverted`, `airport_change`, or `invalid_input`. |

The input plan is not changed. Segment ids are not echoed.

## Rules

An international connection needs **90 minutes**. A domestic connection needs **45 minutes**.

`gapMinutes` is `departAt - arriveAt` in whole minutes. Comparison is on the absolute instant, so an offset and a `Z` clock for the same moment agree. `NRT` and `nrt` are the same airport.

Airports are compared first.

- Different airports: `ok` is false, `action` is `needs_user`, `reason` is `airport_change`. The gap is still reported. `shortfallMinutes` is still `max(0, minimumMinutes - gapMinutes)`.
- Same airport and `gapMinutes` greater than or equal to the minimum: `ok` is true, `action` is `none`, `shortfallMinutes` is 0, `reason` is `enough`.
- Same airport and a shorter gap that is not negative: `ok` is false, `action` is `replan`, `reason` is `short`, `shortfallMinutes` is `minimumMinutes - gapMinutes`.
- Same airport and a negative gap (`departAt` before `arriveAt`): `ok` is false, `action` is `replan`, `reason` is `inverted`. `shortfallMinutes` is `minimumMinutes - gapMinutes`.

A partial or unreadable input returns `ok` false, zeros, `action` `none`, and `reason` `invalid_input`. It does not raise. A date without a time is not an instant. `international` must be a boolean.

| Connection | Airports | Result |
| --- | --- | --- |
| 60 minutes, international | same | `ok` false, shortfall 30, `action` `replan`, `reason` `short` |
| 50 minutes, domestic | same | `ok` true, shortfall 0, `action` `none` |
| 120 minutes, domestic | `NRT` then `HND` | `ok` false, gap 120, `action` `needs_user`, `reason` `airport_change` |
| outbound leaves 60 minutes earlier | same | `ok` false, gap -60, `action` `replan`, `reason` `inverted` |

## Tests

From the repository root:

```bash
PYTHONPATH=. python3 -m unittest booking.assist.layover.test_layover
```
