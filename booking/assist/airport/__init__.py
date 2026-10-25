"""Hotel-to-airport departure for the Amazon Bedrock AgentCore runtime.

The master agent calls ``airport_leave`` the morning of a flight. This package
does not run that loop. See README.md.
"""

from .leave import airport_leave
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "airport_leave", "handler"]
