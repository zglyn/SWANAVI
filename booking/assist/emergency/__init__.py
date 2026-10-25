"""Emergency phone numbers for the Amazon Bedrock AgentCore runtime.

The master agent calls ``emergency_card`` when the traveler asks for help.
This package returns phone numbers only. It does not give medical guidance
and it does not run the master loop. See README.md.
"""

from .card import emergency_card
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "emergency_card", "handler"]
