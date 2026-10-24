"""Country tip ceiling for the Amazon Bedrock AgentCore runtime.

The master agent calls ``tip_policy`` before ``authorize_spend`` so a vendor
cannot add a tip past the country rule. This package does not run that loop
and does not charge a card. See README.md.
"""

from .policy import tip_policy
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "handler", "tip_policy"]
