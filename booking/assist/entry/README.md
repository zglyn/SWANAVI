# Entry requirements

Checks the passport and the visa before the trip starts. The master agent calls `check_entry` before the trip starts. It calls this tool on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime. This package does not run that loop.

Sandbox only. The caller supplies `destinationCountry`, `passportExpiry`, `tripEnd`, and `visaOnFile`. The tool does not look up visa rules, open the network, or call AWS.

```python
from booking.assist.entry import AGENTCORE_TOOL, TOOL_SPEC, check_entry, handler

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a check_entry tool call, call handler(tool_input).
```

Tool name: `check_entry`.

## Input

| Field | Meaning |
| --- | --- |
| `destinationCountry` | Destination country from the caller. Not looked up. |
| `passportExpiry` | Passport expiry date, `YYYY-MM-DD`. |
| `tripEnd` | Trip end date, `YYYY-MM-DD`. |
| `visaOnFile` | `true` only when the visa is already on file. |

## Output

```json
{
  "ok": true,
  "issues": []
}
```

| Field | Meaning |
| --- | --- |
| `ok` | `false` when `passportExpiry` is missing, when `passportExpiry` is less than 180 days after `tripEnd`, or when `visaOnFile` is false. `true` otherwise. |
| `issues` | Why entry is not ok. Empty when `ok` is true. |

## Rules

Dates are calendar dates. The passport clears the window when `passportExpiry` is at least 180 days after `tripEnd`. A passport that expires on `tripEnd` plus 180 days is ok. One day earlier is not.

- A valid passport and `visaOnFile` true returns `ok` true and an empty `issues` list.
- A missing `passportExpiry` returns `ok` false.
- A `passportExpiry` less than 180 days after `tripEnd` returns `ok` false.
- A missing or unparseable `tripEnd` returns `ok` false, because the 180-day window cannot be checked.
- `visaOnFile` false returns `ok` false.
- A partial payload, bad JSON, and any other input return a result and do not raise.

## Tests

From the repository root:

```bash
python3 -m unittest booking.assist.entry.test_entry
```
