"""Sandbox cash decision for the Amazon Bedrock AgentCore runtime.

The master agent calls ``cash_needed`` when a merchant may not take a card.
This package does not run that loop and does not contact an ATM. A later
integrator wires the tool into the master. See README.md.
"""

from .cash import cash_needed
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "cash_needed", "handler"]
