"""Same-day rebook of one cancelled segment for the Amazon Bedrock AgentCore runtime.

The master agent calls ``rebook_segment`` after a cancellation. This package
does not run that loop and does not call the planner. See README.md.
"""

from .rebook import rebook_segment
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "handler", "rebook_segment"]
