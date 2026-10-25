"""Trip-plan input and per-segment booking result.

Field names are the wire contract. Do not rename them.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SegmentKind = Literal["flight", "hotel", "attraction"]
BookingStatus = Literal["booked", "failed", "needs_user"]


def _ymd(value: str) -> str:
    if not isinstance(value, str) or _DATE.fullmatch(value) is None:
        raise ValueError("date must be YYYY-MM-DD")
    date.fromisoformat(value)
    return value


class Traveler(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)


class Destination(BaseModel):
    model_config = ConfigDict(extra="ignore")

    city: str = Field(min_length=1)
    country: str = Field(min_length=1)


class DateRange(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def _dates(cls, value: str) -> str:
        return _ymd(value)


class FlightSegment(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    segmentId: str = Field(min_length=1)
    kind: Literal["flight"]
    origin: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)
    departDate: str
    returnDate: str | None = None
    cabin: str = Field(min_length=1)
    travelerIds: list[str] = Field(min_length=1)

    @field_validator("departDate")
    @classmethod
    def _depart(cls, value: str) -> str:
        return _ymd(value)

    @field_validator("returnDate")
    @classmethod
    def _return(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _ymd(value)

    @field_validator("travelerIds")
    @classmethod
    def _travelers(cls, value: list[str]) -> list[str]:
        if any(not item for item in value):
            raise ValueError("travelerIds must be non-empty strings")
        return value


class HotelSegment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    segmentId: str = Field(min_length=1)
    kind: Literal["hotel"]
    city: str = Field(min_length=1)
    checkIn: str
    checkOut: str
    rooms: int = Field(ge=1)
    guests: int = Field(ge=1)

    @field_validator("checkIn", "checkOut")
    @classmethod
    def _stay(cls, value: str) -> str:
        return _ymd(value)


class AttractionSegment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    segmentId: str = Field(min_length=1)
    kind: Literal["attraction"]
    name: str = Field(min_length=1)
    city: str = Field(min_length=1)
    date: str
    partySize: int = Field(ge=1)
    time: str | None = None

    @field_validator("date")
    @classmethod
    def _on(cls, value: str) -> str:
        return _ymd(value)


class TripPlan(BaseModel):
    """Finished plan produced by the planner. This agent only books it."""

    model_config = ConfigDict(extra="ignore")

    tripId: str = Field(min_length=1)
    travelers: list[Traveler]
    destination: Destination
    dates: DateRange
    flights: list[FlightSegment]
    hotels: list[HotelSegment]
    attractions: list[AttractionSegment]


class Price(BaseModel):
    model_config = ConfigDict(extra="ignore")

    amount: str
    currency: str = Field(min_length=1)

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, value: object) -> str:
        if isinstance(value, bool) or value is None:
            raise ValueError("amount required")
        if isinstance(value, str):
            text = value.strip()
        elif isinstance(value, (int, float, Decimal)):
            text = format(Decimal(str(value)), "f")
        else:
            raise ValueError("amount required")
        try:
            number = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError("amount must be a decimal string") from exc
        if not number.is_finite() or number < 0:
            raise ValueError("amount must be a non-negative decimal")
        return text

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("currency required")
        return text


class SegmentResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    segmentId: str
    kind: SegmentKind
    status: BookingStatus
    confirmationCode: str | None = None
    price: Price | None = None
    error: str | None = None


class TripBookingResponse(BaseModel):
    """Envelope around the per-segment booking results."""

    model_config = ConfigDict(extra="ignore")

    tripId: str | None
    results: list[SegmentResult]
    error: str | None = None
