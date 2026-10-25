"""Dynamic currency conversion refusal for the Amazon Bedrock AgentCore runtime.

Tourist rule: pay the merchant's currency. A later integrator wires
``refuse_dcc`` into the master. This package does not run that loop, does not
call a payment terminal, and does not charge a card. See README.md.
"""

from .dcc import refuse_dcc
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "handler", "refuse_dcc"]
