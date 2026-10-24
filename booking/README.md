# Trip booking orchestrator

Books a **finished** trip plan. The planner, the UI, payments, and the supplier providers are not in this folder.

The only entrypoint is one [Amazon Bedrock AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html): `BedrockAgentCoreApp` in `booking/orchestrator/main.py`. A trip plan is posted to that runtime. The runtime calls three tools it registered at startup, then returns one result per segment. Booking state goes to AgentCore Memory when a memory id is configured. With no memory id, state stays in the process.

There is no second entrypoint. A script that imports the provider packages and books on its own is not this path.

Sandbox is the default. This runtime never charges a card and never mints confirmation codes. A code is returned only when a provider produced it and it starts with `SANDBOX-`. Anything else is dropped. The runtime does not call Amadeus itself.

Nothing in this repository has been deployed to AWS.

## What it books

| Plan list | Tool registered on the runtime | Provider `book()` | Supplier API behind that provider |
| --- | --- | --- | --- |
| `flights` | `book_flight` | `booking.providers.flights` | Amadeus Flight Offers Search, then Flight Create Orders |
| `hotels` | `book_hotel` | `booking.providers.hotels` | Amadeus Hotel Search, then Hotel Booking |
| `attractions` | `book_attraction` | `booking.providers.attractions` | Amadeus Tours and Activities |

Each provider function is:

```python
def book(segment: dict, travelers: list, trip_id: str) -> dict:
    ...
```

`segment` is that segment's JSON object (`from` stays `from` on flights). `travelers` is `[{id, name}, ...]`. The return value is one booking result, below.

If the module cannot be imported, or it does not export `book`, that tool returns `failed` with `error` `provider_not_installed`. Other segments still run.

Browser, code interpreter, and payment tools are not registered.

### Amadeus credentials

The provider packages read these. This runtime does not. Sandbox is the default when they are unset: no Amadeus client id means the providers must not place a live order, and this runtime still only accepts confirmation codes that start with `SANDBOX-`.

| Variable | Value |
| --- | --- |
| `AMADEUS_CLIENT_ID` | Amadeus test application client id. Unset → sandbox. |
| `AMADEUS_CLIENT_SECRET` | Amadeus test application secret. Unset → sandbox. |
| `AMADEUS_HOSTNAME` | `test` (Amadeus test environment, `test.api.amadeus.com`). Unset → sandbox, same as `test`. |

Do not set `AMADEUS_HOSTNAME` to `production`. The tools refuse that hostname with `production_booking_refused` and do not call the provider. This path never charges a card and never books on the production Amadeus host.

## Contract

Dates are `YYYY-MM-DD`. Money amounts are decimal strings.

### Trip plan (input)

```json
{
  "tripId": "sample-kyoto",
  "travelers": [{"id": "t1", "name": "Sample Traveler"}],
  "destination": {"city": "Kyoto", "country": "JP"},
  "dates": {"start": "2026-11-02", "end": "2026-11-06"},
  "flights": [
    {
      "segmentId": "flight-1",
      "kind": "flight",
      "from": "SFO",
      "to": "KIX",
      "departDate": "2026-11-02",
      "returnDate": "2026-11-06",
      "cabin": "economy",
      "travelerIds": ["t1"]
    }
  ],
  "hotels": [
    {
      "segmentId": "hotel-1",
      "kind": "hotel",
      "city": "Kyoto",
      "checkIn": "2026-11-02",
      "checkOut": "2026-11-06",
      "rooms": 1,
      "guests": 1
    }
  ],
  "attractions": [
    {
      "segmentId": "attraction-1",
      "kind": "attraction",
      "name": "Sample temple visit",
      "city": "Kyoto",
      "date": "2026-11-03",
      "partySize": 1,
      "time": "09:00"
    }
  ]
}
```

`returnDate` and attraction `time` may be `null`.

### Booking result (one per segment)

| Field | Values |
| --- | --- |
| `segmentId` | From the plan |
| `kind` | `flight`, `hotel`, or `attraction` |
| `status` | `booked`, `failed`, or `needs_user` |
| `confirmationCode` | `null`, or a sandbox code that starts with `SANDBOX-` |
| `price` | `null`, or `{"amount": "10.00", "currency": "USD"}` |
| `error` | `null`, or a short error string |

The runtime returns:

```json
{
  "tripId": "sample-kyoto",
  "results": [],
  "error": null
}
```

`error` is `invalid_plan` when the payload is not a trip plan. `results` is then empty. A bad segment does not abort the others: each segment has its own `status`.

`needs_user` is used when the plan must be fixed before a tool is called (`unknown_traveler`, `missing_travelers`, `duplicate_segment_id`). Providers may also return `needs_user`.

Already `booked` segments are replayed from memory and are not sent to the provider again.

## Local demo (AgentCore SDK local mode, no AWS)

From the repository root:

```bash
python3 -m pip install -r booking/orchestrator/requirements.txt
PYTHONPATH=. python3 -m booking.orchestrator.demo
```

That command starts the Bedrock AgentCore app (the same server as `python3 -m booking.orchestrator.main`, SDK local mode) and posts `booking/orchestrator/fixtures/sample_plan.json` to `POST /invocations`. The entrypoint runs the three registered tools and the command prints the JSON results. It clears `AGENTCORE_MEMORY_ID` and `MEMORY_BOOKINGMEMORY_ID` for the process so the demo does not call AWS. No Amadeus credentials are required.

With no provider packages on `PYTHONPATH`, every segment is `failed` / `provider_not_installed` and `confirmationCode` is `null`. That is the expected runtime result. It is not a ticket.

`agentcore dev` is the AgentCore CLI's local server for the same entrypoint, after you have created a project with the steps below. Headless `agentcore dev` does not deploy. This repository has not run a cloud deploy.

To hold the SDK server open yourself (default port 8080):

```bash
PYTHONPATH=. python3 -m booking.orchestrator.main
```

In another shell:

```bash
curl -s http://localhost:8080/ping
curl -s -X POST http://localhost:8080/invocations \
  -H 'Content-Type: application/json' \
  --data @booking/orchestrator/fixtures/sample_plan.json
```

Tests:

```bash
PYTHONPATH=. python3 -m unittest booking.orchestrator.tests.test_orchestrator
```

## Deploy to AgentCore

These are the current documented steps. Running them needs your own AWS account. This repo does not contain credentials, account ids, or resource ARNs, and this change set does not deploy the agent.

The Python runtime SDK is `bedrock-agentcore` (`BedrockAgentCoreApp` and `@app.entrypoint` in `booking/orchestrator/main.py`). AWS now recommends the AgentCore CLI (`@aws/agentcore`) to create and deploy that runtime. The older `bedrock-agentcore-starter-toolkit` CLI is [no longer the recommended installer](https://github.com/aws/bedrock-agentcore-starter-toolkit); do not mix its `agentcore configure` flow with the CLI below.

Official references:

- [Get started with AgentCore Runtime using the AgentCore CLI](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html)
- [Direct code deployment for Python](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-code-deploy-python.html)
- [Get started with AgentCore Memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-get-started.html)

1. Install Node.js 20+ and the CLI: `npm install -g @aws/agentcore`.
2. Configure AWS credentials for the account you control (`aws configure`, or an IAM role). You also need permission to create AgentCore Runtime and Memory resources. See [AgentCore Runtime permissions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html) in the AWS docs.
3. Create a CodeZip Python project:

   ```bash
   agentcore create --name TripBooking --template agent-python-minimal
   cd TripBooking
   ```

4. Copy this repo's `booking/` directory to `app/agent/booking/` so `import booking` works from the zip root. Replace `app/agent/main.py` with:

   ```python
   from booking.orchestrator.main import app

   if __name__ == "__main__":
       app.run()
   ```

   Add `bedrock-agentcore` and `pydantic` to that project's `pyproject.toml` (same packages as `booking/orchestrator/requirements.txt`). The managed entrypoint is still `main.py`. `app` is a `BedrockAgentCoreApp`; `invoke` is registered with `@app.entrypoint`.

5. Add short-term memory for booking state. The orchestrator reads `MEMORY_BOOKINGMEMORY_ID` (set by the CLI for a memory named `BookingMemory`) or `AGENTCORE_MEMORY_ID`.

   ```bash
   agentcore add memory --name BookingMemory --expiry 30
   ```

   Booking state is stored as short-term events. In `agentcore/agentcore.json`, set that memory's `strategies` to `[]` if the command wrote long-term strategies. An example of the runtime plus memory block is `booking/orchestrator/agentcore.example.json`. Do not put an account id or a role ARN in that file. `aws-targets.json` is created by the CLI for your account; do not commit a filled-in copy.

6. Check the project, then deploy:

   ```bash
   agentcore build
   agentcore deploy
   agentcore status
   ```

   `agentcore status` is how you see whether the runtime exists. A successful `deploy` here is something you observe in your account; it is not claimed by this repository.

7. Invoke the deployed runtime with the sample plan. The minimal template names the runtime `agent`:

   ```bash
   agentcore invoke --runtime agent \
     --payload "$(cat app/agent/booking/orchestrator/fixtures/sample_plan.json)"
   ```

   Until the flight, hotel, and attraction providers are in the zip, the deployed agent returns the same `provider_not_installed` results as the local demo. Those results are not tickets.

Memory events use actor id `booking-orchestrator` and session id `tripId`. Re-invoking a trip returns segments already marked `booked` without calling the provider again. If Memory cannot be reached, the process keeps state locally and still returns per-segment results.

## What still needs keys

| To do this | You need |
| --- | --- |
| Local demo (`python3 -m booking.orchestrator.demo`) | Nothing. No AWS credentials. Leave `AMADEUS_CLIENT_ID` and `AMADEUS_CLIENT_SECRET` unset for sandbox. |
| `agentcore deploy` and AgentCore Memory in AWS | Your AWS account, credentials, and permission to create Runtime and Memory. Not done in this repo. |
| A segment to come back `booked` | The matching provider package on `PYTHONPATH`. Amadeus test calls inside that package need `AMADEUS_CLIENT_ID`, `AMADEUS_CLIENT_SECRET`, and `AMADEUS_HOSTNAME=test`. |
| A production Amadeus order or a card charge | Not supported. `AMADEUS_HOSTNAME=production` is refused. A `SANDBOX-` code is not a live ticket. |
