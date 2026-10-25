"""Trip budget check for the Amazon Bedrock AgentCore runtime.

The master agent calls ``check_budget`` before accepting a booking or a replan
that adds cost. This package does not run that loop. See README.md.
"""

from .budget import check_budget
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "check_budget", "handler"]
