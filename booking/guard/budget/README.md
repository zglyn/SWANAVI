# Trip budget

Decides whether a proposed charge fits the trip budget. The master agent calls `check_budget` before accepting a booking or a replan that adds cost. It calls this tool on the [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html) runtime. This package does not run that loop, does not book a segment, and does not replan the day.

Sandbox only. The caller supplies `tripId`, `currency`, and the three amounts. The tool does not look up the trip, open the network, or call AWS.

```python
from booking.guard.budget import AGENTCORE_TOOL, TOOL_SPEC, check_budget, handler

# TOOL_SPEC is the AgentCore tool definition (name, description, inputSchema).
# AGENTCORE_TOOL is the inline_function entry to pass on harness invoke.
# When the runtime returns a check_budget tool call, call handler(tool_input).
```

Tool name: `check_budget`.

## Input

| Field | Meaning |
| --- | --- |
| `tripId` | Trip the master is about to charge. Not looked up. |
| `currency` | Currency code from the caller, such as `USD`. Echoed on the result. |
| `budgetAmount` | Trip budget. Decimal string such as `500.00`, or a number. |
| `spentAmount` | Amount already spent. Decimal string or a number. |
| `proposedAmount` | Charge this booking or replan would add. Decimal string or a number. |

## Output

```json
{
  "allowed": true,
  "remaining": "30.00",
  "currency": "USD",
  "reason": "spentAmount + proposedAmount is within budgetAmount"
}
```

| Field | Meaning |
| --- | --- |
| `allowed` | `true` only when `spentAmount + proposedAmount <= budgetAmount`. |
| `remaining` | `budgetAmount - spentAmount - proposedAmount` as a decimal string. Negative when the charge is blocked. `null` when an amount is missing or not a number. |
| `currency` | Currency from the input. Empty when the caller did not send one. |
| `reason` | Why the charge is allowed or blocked. |

## Rules

Amounts are compared with decimal arithmetic, so one cent is exact.

- Under budget is allowed. `spentAmount` 320.00 and `proposedAmount` 150.00 against `budgetAmount` 500.00 leaves `remaining` `30.00`.
- Exactly at the budget is allowed. `remaining` is `0.00`.
- One cent over is blocked. `remaining` is `-0.01` and `allowed` is `false`.
- A missing or non-numeric `budgetAmount`, `spentAmount`, or `proposedAmount` returns `allowed` `false` and `remaining` `null`.
- A partial payload, bad JSON, and any other input return a result and do not raise.

## Tests

From the repository root:

```bash
python3 -m unittest booking.guard.budget.test_budget
```
