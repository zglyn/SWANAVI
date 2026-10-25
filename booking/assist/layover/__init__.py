"""Flight connection check for the Amazon Bedrock AgentCore runtime.

The master agent calls ``check_layover`` between an inbound flight and the
outbound flight. This package does not run that loop and does not change a
plan. A later integrator wires the master. See README.md.
"""

from .layover import check_layover
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "check_layover", "handler"]
