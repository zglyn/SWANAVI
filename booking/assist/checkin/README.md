# Flight check-in

Checks in one flight inside the 24 hour window before departure. The master agent calls `check_in_flight` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime. This package does not run that loop. A later integrator wires the master loop. This package does not book the flight.

Sandbox only. The tool does not call an airline API, open the network, or call AWS. The boarding pass is a sandbox code, not a real barcode.

```python
from booking.assist.checkin import AGENTCORE_TOOL, TOOL_SPEC, check_in_flight, handler

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a check_in_flight tool call, call handler(tool_input).
```

Tool name: `check_in_flight`.

## Input

| Field | Meaning |
| --- | --- |
| `now` | ISO-8601 timestamp from the caller. This tool does not read the wall clock. |
| `segment` | One segment: `segmentId`, `kind`, `departAt` or `departDate`, and `confirmationCode` or `null`. |
| `travelers` | List of `{id, name}`. An empty list is allowed. |

`departAt` is an ISO-8601 departure. When `departAt` is absent, `departDate` is used. A date-only `departDate` (`YYYY-MM-DD`) is that date at `T09:00:00Z`.

## Output

```json
{
  "segmentId": "flight-1",
  "status": "checked_in",
  "boardingPass": "SANDBOX-BP-0123456789AB",
  "opensAt": "2026-11-01T09:00:00Z",
  "error": null
}
```

| Field | Meaning |
| --- | --- |
| `segmentId` | From the segment. Empty when the input has no id. |
| `status` | `waiting`, `checked_in`, `missed`, `needs_user`, or `not_a_flight`. Null when `error` is `invalid_segment`. |
| `boardingPass` | Sandbox code starting with `SANDBOX-BP-` when `status` is `checked_in`. Null otherwise. Not a barcode. |
| `opensAt` | When the window opens: departure minus 24 hours, written as UTC. Null when departure cannot be read. |
| `error` | `invalid_segment` when the input cannot be read. Null otherwise. |

## Rules

The window opens 24 hours before departure. Clocks are UTC. A `Z` suffix and a numeric offset are the same instant. A timestamp with no offset is read as UTC. `opensAt` is written as `YYYY-MM-DDTHH:MM:SSZ`.

| Condition | Result |
| --- | --- |
| `kind` is not `flight` | `status` `not_a_flight`. `boardingPass` and `opensAt` are null. |
| No confirmation code | `status` `needs_user`. `boardingPass` is null. |
| `now` is before departure minus 24 hours | `status` `waiting`. `opensAt` is departure minus 24 hours. `boardingPass` is null. |
| `now` is at or after departure | `status` `missed`. `boardingPass` is null. |
| Inside the window, with a confirmation code | `status` `checked_in`. `boardingPass` starts with `SANDBOX-BP-`. |

The same segment, confirmation code, and travelers always return the same boarding pass. That code is a sandbox token. It is not a barcode and it is not an airline document.

A missing segment, a missing `now` on a flight, a departure that cannot be read, or any other partial input returns `error` `invalid_segment` and does not raise.

## Tests

From the repository root:

```bash
PYTHONPATH=. python3 -m unittest booking.assist.checkin.test_checkin
```
