"""Ground transfers for the Amazon Bedrock AgentCore runtime.

The master agent calls ``check_transfer`` between consecutive stops. This
package does not run that loop. See README.md.
"""

from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler
from .transfer import check_transfer

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "check_transfer", "handler"]
