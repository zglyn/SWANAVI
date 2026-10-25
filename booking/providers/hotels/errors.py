"""Errors the hotel booker turns into a result instead of raising."""


class HotelProviderError(Exception):
    """A hotel provider could not complete a booking.

    ``book`` catches this and returns ``status="failed"``.
    """
