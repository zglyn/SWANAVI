# Landing data

Labels a sandbox eSIM so the phone has data before a ride is requested. The master agent calls `landing_data` on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime before a ride is requested. This package does not run that loop.

A later integrator wires the master. This package does not edit `booking/master` and does not register the tool on the master loop.

Sandbox only. The plan code is a label. There is no real eSIM seller. The tool does not buy a plan, call a carrier API, open the network, or call AWS.

```python
from booking.assist.connectivity import AGENTCORE_TOOL, TOOL_SPEC, handler, landing_data

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a landing_data tool call, call handler(tool_input).
```

Tool name: `landing_data`.

## Input

| Field | Meaning |
| --- | --- |
| `country` | Destination country supplied by the caller. Not looked up. |
| `arriveAt` | ISO-8601 arrival time. A `Z` suffix is UTC. |
| `now` | ISO-8601 time the caller is asking. This tool does not read the wall clock. |
| `hasData` | `true` when the phone already has data for this arrival. |

## Output

```json
{
  "country": "JP",
  "status": "install",
  "action": "install_esim",
  "planCode": "SANDBOX-ESIM-0123456789AB",
  "remindAt": null
}
```

| Field | Meaning |
| --- | --- |
| `country` | Country from the input, with surrounding space removed. Empty when it was not a string. |
| `status` | `ready`, `remind`, `install`, or `needs_user`. |
| `action` | `none`, `remind`, or `install_esim`. |
| `planCode` | Sandbox label starting with `SANDBOX-ESIM-` when `status` is `install`. `null` otherwise. |
| `remindAt` | ISO-8601 UTC time, `arriveAt` minus 2 hours, when `status` is `remind`. `null` otherwise. |

## Rules

An empty country, a blank country, or an unknown country (`unknown`, `n/a`, or a value with fewer than two letters) returns `status` `needs_user`, `action` `none`, and `planCode` null. That check comes first, including when `hasData` is true.

`hasData` true returns `status` `ready`, `action` `none`, and `planCode` null. No plan is labeled.

`hasData` false uses a 2-hour rule. `remindAt` is `arriveAt` minus 2 hours.

- When `now` is earlier than that instant, `status` is `remind`, `action` is `remind`, and `planCode` is null.
- When `now` is inside that 2-hour window, exactly on `remindAt`, or after arrival, `status` is `install` and `action` is `install_esim`.

`install_esim` does not install a profile and does not buy a plan. `planCode` starts with `SANDBOX-ESIM-`. The same country and `arriveAt` always get the same label. `now` does not change the label. The code is not an order id from a seller.

A missing or unreadable `hasData`, `arriveAt`, or `now` returns `needs_user` when a plan would otherwise be labeled. The tool returns a result and does not raise.

Clocks are UTC. A `Z` suffix and a numeric offset are the same instant. A timestamp with no offset is read as UTC. `remindAt` is written as `YYYY-MM-DDTHH:MM:SSZ`.

## Tests

From the repository root:

```bash
PYTHONPATH=. python3 -m unittest booking.assist.connectivity.test_connectivity
```

The tests cover `hasData`, a time that is too early to install, a time inside the 2-hour window, and a missing country. They stay in-process. They do not call a carrier or buy a plan.
