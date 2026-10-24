"""Errors raised by flight providers. `book` turns them into status failed."""


class FlightProviderError(Exception):
    """A provider failed. Callers of `book` receive this as a result, not an exception."""
