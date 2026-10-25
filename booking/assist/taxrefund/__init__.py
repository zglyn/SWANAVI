"""Sandbox tax-refund quotes for the Amazon Bedrock AgentCore runtime.

The master agent calls ``tax_refund``. This package does not run that loop
and does not register itself on the master. See README.md.
"""

from .refund import tax_refund
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "handler", "tax_refund"]
