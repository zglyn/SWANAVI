"""Spend guard for the Amazon Bedrock AgentCore runtime.

The master agent calls ``authorize_spend`` before a charge. This package does
not run that loop and does not charge a card. See README.md.
"""

from .spend import authorize_spend
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "authorize_spend", "handler"]
