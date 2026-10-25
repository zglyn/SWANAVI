"""Schedule conflicts for the Amazon Bedrock AgentCore runtime.

The master agent calls ``check_conflicts`` after a replan. This package does
not run that loop. See README.md.
"""

from .conflicts import check_conflicts
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "check_conflicts", "handler"]
