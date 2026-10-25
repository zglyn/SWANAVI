"""Hotel confirmation-email check for the Amazon Bedrock AgentCore runtime.

The master agent calls ``verify_hotel_email`` after ``book_hotel``. Sandbox
only: no network, no real inbox, and no AWS.
"""

from .email import sample_email, verify
from .tool import TOOL_SPEC, handler

verify_hotel_email = TOOL_SPEC

__all__ = [
    "TOOL_SPEC",
    "handler",
    "sample_email",
    "verify",
    "verify_hotel_email",
]
