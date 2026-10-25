"""Hotel incidental authorization for the Amazon Bedrock AgentCore runtime.

The hold is not a charge. This package does not capture or charge a card
and does not open a card network. A later integrator wires the master.
See README.md.
"""

from .hold import incidental_hold
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "handler", "incidental_hold"]
