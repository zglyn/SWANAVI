"""Amazon Bedrock AgentCore runtime for the master booking loop.

Local: ``python -m booking.master.main`` serves ``/invocations`` and ``/ping``.
That path does not need AWS credentials or Amadeus keys.

The planner calls this entrypoint. The entrypoint calls book_flight,
book_hotel, book_attraction, the verify_*_email tools, and trip_progress.
"""

from __future__ import annotations

from bedrock_agentcore import BedrockAgentCoreApp

from booking.master.service import handle_payload
from booking.master.tools import RUNTIME_TOOLS

app = BedrockAgentCoreApp()
app.booking_tools = dict(RUNTIME_TOOLS)


@app.entrypoint
def invoke(payload: dict, context: object | None = None) -> dict:
    """Run the master control loop for one finished trip plan."""

    del context
    return handle_payload(payload)


if __name__ == "__main__":
    app.run()
