"""Sandbox flight confirmation checks. Invoke `verify_flight_email` on AgentCore.

See README.md. `sample_email` builds the message a traveler would receive.
`verify` checks that message. Neither one uses the network.
"""

from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler
from .verify import sample_email, verify

__all__ = [
    "AGENTCORE_TOOL",
    "TOOL_SPEC",
    "handler",
    "sample_email",
    "verify",
]
