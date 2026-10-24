"""Entry requirements for the Amazon Bedrock AgentCore runtime.

The master agent calls ``check_entry`` before the trip starts. This package
does not run that loop. See README.md.
"""

from .entry import check_entry
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "check_entry", "handler"]
