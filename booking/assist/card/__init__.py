"""Sandbox Mastercard choice for the Amazon Bedrock AgentCore runtime.

``pick_card`` chooses a fake fixture card for a merchant charge. This package
does not charge a card and does not run the master loop. A later integrator
wires the tool into the master. See README.md.
"""

from .pick import pick_card
from .tool import AGENTCORE_TOOL, TOOL_SPEC, handler

__all__ = ["AGENTCORE_TOOL", "TOOL_SPEC", "handler", "pick_card"]
