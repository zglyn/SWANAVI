from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, NamedTuple

from roam_contracts.models import (
    BudgetLevel,
    ChatAnswer,
    ChatRole,
    Control,
    ControlType,
    ConversationFixture,
    Pace,
    Proposal,
    StopKind,
    TimeOfDayWindow,
    TravelPackage,
    TripConversation,
    TripFacts,
    TripOrigin,
    UserProfile,
)
DESTINATIONS = ("New York", "Kyoto", "Osaka", "Tokyo")
CITY_ALIASES = {
    "sf": "san francisco",
    "bay area": "san francisco",
    "the bay area": "san francisco",
    "nyc": "new york",
    "new york city": "new york",
}
PLACE_NAMES = {
    "new york city": "New York",
    "new york": "New York",
    "nyc": "New York",
    "kyoto": "Kyoto",
    "osaka": "Osaka",
    "tokyo": "Tokyo",
}
ORIGIN_AIRPORTS = {
    "kyoto": ["KIX", "ITM"],
    "osaka": ["KIX", "ITM"],
    "tokyo": ["HND", "NRT"],
    "san francisco": ["SFO", "OAK", "SJC"],
    "new york": ["JFK", "LGA", "EWR"],
}
AIRPORT_CODES = {code for codes in ORIGIN_AIRPORTS.values() for code in codes}
ASK_TURNS = 3
PLAN_NOW = "Plan it now"
SCRIPT_KNOWS = ("destination", "origin", "start_date", "end_date")
BUDGET_WORDS = {
    BudgetLevel.BUDGET: "low",
    BudgetLevel.MID: "mid-range",
    BudgetLevel.PREMIUM: "premium",
    BudgetLevel.LUXURY: "luxury",
}
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
COUNT = r"\d{1,2}|" + "|".join(NUMBER_WORDS)
MONTH = (
    r"(january|february|march|april|may|june|july|august|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\.?"
)
DAY = r"(\d{1,2})(?:st|nd|rd|th)?(?!\d)"
UNTIL = r"\s*(?:-|–|to|until|through|thru)\s*"
ISO_RANGE = re.compile(r"(\d{4}-\d{2}-\d{2})" + UNTIL + r"(\d{4}-\d{2}-\d{2})")
DAY_RANGE = re.compile(rf"\b{MONTH}\s+{DAY}{UNTIL}(?:{MONTH}\s+)?{DAY}")
DAY_RANGE_FIRST = re.compile(rf"\b{DAY}{UNTIL}{DAY}\s+{MONTH}")
ONE_DAY = re.compile(rf"\b{MONTH}\s+{DAY}")
PERIOD = re.compile(rf"\b(early|beginning of|start of|mid|late|end of|in)[\s-]+{MONTH}")
PERIOD_DAY = {"early": 1, "beginning of": 1, "start of": 1, "mid": 11, "in": 11, "late": 21, "end of": 21}
LENGTH = re.compile(rf"\b({COUNT}|a)[\s-]+(day|night|week)s?\b")
TRAVELLERS: list[tuple[re.Pattern[str], Callable[[re.Match[str]], int]]] = [
    (re.compile(r"\b(?:just me|solo|alone|by myself|on my own)\b"), lambda _: 1),
    (re.compile(
        r"\b(?:couple|the two of us|both of us|me and my "
        r"(?:partner|wife|husband|girlfriend|boyfriend|fiancee?|friend|mom|dad|sister|brother))\b"
    ), lambda _: 2),
    (re.compile(rf"\bfamily of ({COUNT})\b"), lambda found: _count(found.group(1))),
    (re.compile(rf"\b({COUNT})\s+(?:of us|people|persons|travell?ers|adults|guests)\b"), lambda found: _count(found.group(1))),
]
BUDGET = re.compile(
    r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k)?\b"
    r"|\b(\d[\d,]*(?:\.\d+)?)\s*(k)?\s*(?:usd|dollars|bucks)\b"
    r"|\bbudget\b[^\d$]{0,12}(\d[\d,]*(?:\.\d+)?)\s*(k)?\b"
)
PACES = {
    Pace.RELAXED: re.compile(r"\b(?:relaxed|relaxing|slow|chill|laid[- ]back|leisurely)\b"),
    Pace.BALANCED: re.compile(r"\b(?:balanced|moderate)\b"),
    Pace.PACKED: re.compile(r"\b(?:packed|busy|see everything|as much as possible)\b"),
}
INTERESTS = {
    "food": re.compile(r"\b(?:food|foodie|eat|eating|restaurants?|ramen|sushi)\b"),
    "temples": re.compile(r"\b(?:temples?|shrines?)\b"),
    "museums": re.compile(r"\b(?:museums?|art|galleries)\b"),
    "nature": re.compile(r"\b(?:nature|hike|hiking|gardens?|parks?|outdoors)\b"),
    "nightlife": re.compile(r"\b(?:nightlife|bars|clubs)\b"),
}
QUESTIONS: dict[str, tuple[str, Control]] = {
    "destination": (
        "where would you like to go",
        Control(slot="destination", type=ControlType.TILES, options=list(DESTINATIONS)),
    ),
    "dates": ("when are you going and for how long", Control(slot="dates", type=ControlType.DATE_RANGE)),
    "origin": ("which airport are you leaving from", Control(slot="origin", type=ControlType.AIRPORT)),
    "travellers": (
        "how many people are going",
        Control(slot="travellers", type=ControlType.CHIPS, options=["1", "2", "3", "4+"]),
    ),
    "budget": ("what is the budget", Control(slot="budget", type=ControlType.SLIDER, min=500, max=5000, value=1500)),
}


class Reply(NamedTuple):
    facts: TripFacts
    text: str
    controls: list[Control]


def _set(facts: TripFacts, **changes: Any) -> TripFacts:
    return TripFacts.model_validate({**facts.model_dump(), **changes})


def _count(word: str) -> int:
    return NUMBER_WORDS[word] if word in NUMBER_WORDS else int(word)


def _month(name: str) -> int:
    return ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec").index(name[:3]) + 1


def _upcoming(month: int, day: int, today: date) -> date:
    found = date(today.year, month, day)
    return found if found >= today else date(today.year + 1, month, day)


def _nights(lower: str) -> int | None:
    found = list(LENGTH.finditer(lower))
    if not found:
        return None
    word, unit = found[-1].group(1), found[-1].group(2)
    amount = 1 if word == "a" else _count(word)
    return {"day": max(1, amount - 1), "night": amount, "week": 7 * amount}[unit]


def _span(start: date, end: date) -> dict[str, str]:
    return {"start_date": start.isoformat(), "end_date": end.isoformat()} if end > start else {}


def _dates(lower: str, today: date, facts: TripFacts) -> dict[str, str]:
    try:
        if found := ISO_RANGE.search(lower):
            return _span(date.fromisoformat(found.group(1)), date.fromisoformat(found.group(2)))
        if found := DAY_RANGE.search(lower):
            start = _upcoming(_month(found.group(1)), int(found.group(2)), today)
            end = date(start.year, _month(found.group(3) or found.group(1)), int(found.group(4)))
            return _span(start, end if end > start else end.replace(year=end.year + 1))
        if found := DAY_RANGE_FIRST.search(lower):
            start = _upcoming(_month(found.group(3)), int(found.group(1)), today)
            return _span(start, start.replace(day=int(found.group(2))))
        nights = _nights(lower)
        if nights is None:
            return {}
        if found := ONE_DAY.search(lower):
            start = _upcoming(_month(found.group(1)), int(found.group(2)), today)
            return _span(start, start + timedelta(days=nights))
        if found := PERIOD.search(lower):
            start = _upcoming(_month(found.group(2)), PERIOD_DAY[found.group(1)], today)
            return _span(start, start + timedelta(days=nights))
        if facts.start_date:
            start = date.fromisoformat(facts.start_date)
            return _span(start, start + timedelta(days=nights))
    except ValueError:
        return {}
    return {}


def _destination(lower: str) -> str | None:
    for found in re.finditer(r"\b(new york city|new york|nyc|kyoto|osaka|tokyo)\b", lower):
        if not re.search(r"\b(?:from|leaving|out of)\s+$", lower[:found.start()]):
            return PLACE_NAMES[found.group(1)]
    return None


def _origin(text: str) -> TripOrigin | None:
    lower = text.lower()
    city = re.search(
        r"\b(?:from|leaving|out of)\s+(san francisco|the bay area|bay area|sf|new york city|new york|nyc|kyoto|osaka|tokyo)\b",
        lower,
    )
    if city:
        name = CITY_ALIASES.get(city.group(1), city.group(1))
        return TripOrigin(from_home=False, place=name.title(), airport_codes=list(ORIGIN_AIRPORTS[name]))
    for found in re.finditer(r"\b(?:from|leaving|out of)\s+([A-Za-z]{3})\b", text, re.IGNORECASE):
        code = found.group(1)
        if code.isupper() or code.upper() in AIRPORT_CODES:
            return TripOrigin(from_home=False, airport_codes=[code.upper()])
    return None


def _travellers(lower: str) -> int | None:
    found = [(match.start(), count(match)) for pattern, count in TRAVELLERS for match in pattern.finditer(lower)]
    counts = [item for item in found if item[1] >= 1]
    return max(counts)[1] if counts else None


def _budget(lower: str) -> Decimal | None:
    found = list(BUDGET.finditer(lower))
    if not found:
        return None
    groups = found[-1].groups()
    amount, thousands = next((groups[index], groups[index + 1]) for index in (0, 2, 4) if groups[index])
    return Decimal(amount.replace(",", "")) * (1000 if thousands else 1)


def _pace(lower: str) -> Pace | None:
    found = [(match.start(), pace) for pace, pattern in PACES.items() for match in pattern.finditer(lower)]
    return max(found)[1] if found else None


def extract_facts(text: str, facts: TripFacts, today: date) -> TripFacts:
    lower = text.lower()
    found: dict[str, Any] = {
        "destination": _destination(lower),
        "origin": _origin(text),
        "travellers": _travellers(lower),
        "budget": _budget(lower),
        "pace": _pace(lower),
        **_dates(lower, today, facts),
    }
    changes = {key: value for key, value in found.items() if value is not None}
    interests = [name for name, pattern in INTERESTS.items() if pattern.search(lower)]
    if interests:
        changes["interests"] = [*facts.interests, *(name for name in interests if name not in facts.interests)]
    return _set(facts, **changes)


def _answer_dates(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        start, end = value.get("start"), value.get("end")
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        start, end = value
    else:
        start, _, end = str(value).partition("/")
    first, last = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    if last <= first:
        raise ValueError("The trip has to end after it starts")
    return _span(first, last)


def _answer_interests(value: Any) -> dict[str, list[str]]:
    items = value if isinstance(value, list) else str(value).split(",")
    return {"interests": [str(item).strip() for item in items if str(item).strip()]}


ANSWERS: dict[str, Callable[[Any], dict[str, Any]]] = {
    "destination": lambda value: {"destination": str(value).strip()},
    "dates": _answer_dates,
    "origin": lambda value: {"origin": TripOrigin(from_home=False, airport_codes=[str(value).strip().upper()])},
    "travellers": lambda value: {"travellers": int(str(value).rstrip("+"))},
    "budget": lambda value: {"budget": str(value).replace(",", "").lstrip("$")},
    "pace": lambda value: {"pace": Pace(value)},
    "interests": _answer_interests,
    "outbound_window": lambda value: {"outbound_window": TimeOfDayWindow(value)},
    "return_window": lambda value: {"return_window": TimeOfDayWindow(value)},
}


def apply_answer(facts: TripFacts, answer: ChatAnswer) -> TripFacts:
    parse = ANSWERS.get(answer.slot)
    if parse is None:
        raise ValueError(f"Swan does not ask about {answer.slot}")
    return _set(facts, **parse(answer.value))


def _day(moment: date | str) -> str:
    moment = date.fromisoformat(moment) if isinstance(moment, str) else moment
    return f"{moment:%b} {moment.day}"


def answers_text(answers: list[ChatAnswer], facts: TripFacts) -> str:
    def one(slot: str) -> str:
        if slot == "travellers":
            return "Just me" if facts.travellers == 1 else f"{facts.travellers} of us"
        if slot == "budget":
            return f"about ${facts.budget:,.0f}"
        if slot == "dates":
            return f"{_day(facts.start_date)} to {_day(facts.end_date)}"
        if slot == "origin":
            return f"From {facts.origin.airport_codes[0]}"
        if slot == "pace":
            return f"A {facts.pace.value} pace"
        if slot == "interests":
            return ", ".join(facts.interests)
        return str(next(item.value for item in answers if item.slot == slot))

    return ", ".join(one(item.slot) for item in answers)


def pin_script(facts: TripFacts, script: ConversationFixture) -> TripFacts:
    known = script.conversation.brief
    return _set(facts, **{name: getattr(known, name) for name in SCRIPT_KNOWS})


def home_origin(profile: UserProfile) -> TripOrigin:
    return TripOrigin(from_home=True, airport_codes=list(profile.home.airport_codes))


def join(items: list[str]) -> str:
    if len(items) < 3:
        return " and ".join(items)
    return ", ".join(items[:-1]) + ", and " + items[-1]


def with_defaults(facts: TripFacts, profile: UserProfile | None) -> tuple[TripFacts, list[str]]:
    said: list[str] = []
    changes: dict[str, Any] = {}
    if facts.travellers is None:
        changes["travellers"] = 1
        said.append("1 traveller")
    if facts.origin is None and profile is not None and profile.home.airport_codes:
        changes["origin"] = home_origin(profile)
        said.append(f"you leave from {profile.home.airport_codes[0]}")
    if facts.budget is None:
        level = profile.travel.budget_level if profile is not None else BudgetLevel.MID
        said.append(f"a {BUDGET_WORDS[level]} budget")
    if facts.pace is None:
        changes["pace"] = profile.travel.pace if profile is not None else Pace.BALANCED
        said.append(f"a {changes['pace'].value} pace")
    return _set(facts, **changes), said


def assume(said: list[str]) -> str:
    either = {1: "that", 2: "either"}.get(len(said), "any of them")
    return f"I'll assume {join(said)}. You can change {either} later."


def next_questions(facts: TripFacts, asked: set[str], late: bool = False) -> list[str]:
    missing = [slot for slot in facts.missing_required() if not (late and slot == "travellers")]
    slots = [slot for slot in QUESTIONS if slot in missing]
    if slots and not late and facts.budget is None and "budget" not in asked:
        slots.append("budget")
    return slots[:2]


def _question(slots: list[str]) -> str:
    phrases = [QUESTIONS[slot][0] for slot in slots]
    text = phrases[0][0].upper() + phrases[0][1:]
    return text + "".join(f", and {phrase}" for phrase in phrases[1:]) + "?"


def _core(facts: TripFacts) -> tuple:
    return facts.destination, facts.start_date, facts.end_date, facts.travellers, facts.origin


def summary(facts: TripFacts) -> str:
    text = facts.destination or "Your trip"
    if facts.start_date and facts.end_date:
        text += f" from {_day(facts.start_date)} to {_day(facts.end_date)}"
    if facts.travellers:
        text += f" for {facts.travellers} traveller" + ("s" if facts.travellers > 1 else "")
    if facts.origin is not None and (facts.origin.airport_codes or facts.origin.place):
        text += f", leaving {(facts.origin.airport_codes or [facts.origin.place])[0]}"
    return text + "."


def reply(conversation: TripConversation, before: TripFacts, profile: UserProfile | None) -> Reply:
    facts = conversation.brief
    said = [message for message in conversation.messages if message.role == ChatRole.ASSISTANT]
    parts: list[str] = []
    if conversation.messages[-1].answers is None and _core(facts) != _core(before):
        parts.append(summary(facts))
    if facts.origin is None and profile is not None and profile.home.airport_codes:
        facts = _set(facts, origin=home_origin(profile))
        parts.append(f"From {profile.home.airport_codes[0]}, right?")
    asked = {control.slot for message in said for control in message.controls}
    slots = next_questions(facts, asked, late=len(said) + 1 > ASK_TURNS)
    if slots:
        parts.append(_question(slots))
        return Reply(facts, " ".join(parts), [QUESTIONS[slot][1] for slot in slots])
    facts, assumed = with_defaults(facts, profile)
    if assumed:
        parts.append(assume(assumed))
    parts.append("Plan it whenever you are ready.")
    return Reply(facts, " ".join(parts), [])


def awaiting_answers(conversation: TripConversation) -> bool:
    last = conversation.messages[-1]
    if last.role != ChatRole.USER or last.answers is None:
        return False
    asked = next((message for message in reversed(conversation.messages) if message.role == ChatRole.ASSISTANT), None)
    if asked is None or not asked.controls:
        return False
    return not {control.slot for control in asked.controls} <= {item.slot for item in last.answers}


def still_need(missing: list[str]) -> str:
    names = {"destination": "where you are going", "dates": "your dates", "origin": "where you leave from", "travellers": "how many are going"}
    return f"I still need {join([names[slot] for slot in missing])} before I can plan."


def origin_label(origin: TripOrigin | None) -> str:
    if origin is None:
        return "home"
    return (origin.airport_codes or [origin.place or "home"])[0]


def _word(count: int) -> str:
    return {value: name for name, value in NUMBER_WORDS.items()}.get(count, str(count))


def progress(package: TravelPackage, problems: list[str]) -> list[tuple[str, str, str]]:
    flights = [
        f"{offer.carrier} {label} on {_day(offer.segments[0].depart_at.date())}"
        for label, offer in (("out", package.outbound), ("back", package.return_flight))
        if offer is not None
    ]
    visits = [stop for day in package.itinerary.days for stop in day.stops if stop.kind in {StopKind.ATTRACTION, StopKind.MERCHANT}]
    return [
        ("search_flights", "Flights: " + ", ".join(flights), "info") if flights
        else ("search_flights", "No flights match those dates", "warning"),
        ("search_hotels", "Hotel: " + ", ".join(stay.offer.name for stay in package.hotels), "info") if package.hotels
        else ("search_hotels", "No hotel found", "warning"),
        ("build_itinerary", f"{len(package.itinerary.days)} days with {len(visits)} places to visit", "info"),
        ("propose_itinerary", f"{len(problems)} to check: {problems[0]}", "warning") if problems
        else ("propose_itinerary", "Every day checks out", "info"),
    ]


def ready_text(proposal: Proposal, problems: list[str]) -> str:
    package = proposal.package
    place = proposal.package.itinerary.brief.destination.split(",")[0]
    parts: list[str] = []
    if package.outbound is not None and package.return_flight is not None:
        parts.append("flights")
    elif package.outbound is not None or package.return_flight is not None:
        parts.append("a one-way flight")
    if package.hotels:
        parts.append("a hotel" if len(package.hotels) == 1 else f"{_word(len(package.hotels))} hotels")
    days = len(package.itinerary.days)
    if days:
        parts.append(f"{_word(days)} day{'s' if days != 1 else ''} of stops")
    text = f"Your {place} trip is ready."
    if parts:
        text += f" It has {join(parts)}."
    if package.outbound is None and package.return_flight is None:
        text += " I found no flights for those dates."
    elif package.outbound is None or package.return_flight is None:
        text += f" I found no {'outbound' if package.outbound is None else 'return'} flight for those dates."
    if problems:
        count = len(problems)
        text += f" {_word(count).capitalize()} item{' needs' if count == 1 else 's need'} a second look before booking."
    return text
