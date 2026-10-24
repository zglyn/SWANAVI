"""Amazon Bedrock AgentCore Runtime entrypoint for trip booking.

Local: ``python -m booking.orchestrator.main`` serves ``/invocations`` and
``/ping`` on port 8080. That path does not need AWS credentials unless
``AGENTCORE_MEMORY_ID`` or ``MEMORY_BOOKINGMEMORY_ID`` is set.

Deploy steps are in ``booking/README.md``. This module does not create AWS
resources.
"""

from __future__ import annotations

from bedrock_agentcore import BedrockAgentCoreApp

from booking.orchestrator.memory import memory_from_env
from booking.orchestrator.service import handle_payload

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict, context: object | None = None) -> dict:
    """Book the finished plan in ``payload`` and return per-segment results.

    ``context`` is the AgentCore request context (session id and headers).
    Booking state is keyed by ``tripId``, not by the runtime session.
    """

    del context  # trip state is keyed by tripId inside the plan
    return handle_payload(payload, memory_from_env())


if __name__ == "__main__":
    app.run()
