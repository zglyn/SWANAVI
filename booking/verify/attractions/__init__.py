"""Attraction confirmation-email check for the Amazon Bedrock AgentCore runtime.

The master agent calls ``verify_attraction_email`` on the AgentCore runtime
after ``book_attraction``. See README.md.
"""

from .email import sample_email, verify
from .tool import VERIFY_ATTRACTION_EMAIL_TOOL, verify_attraction_email

__all__ = [
    "VERIFY_ATTRACTION_EMAIL_TOOL",
    "sample_email",
    "verify",
    "verify_attraction_email",
]
