"""Turning a free-text Telegram post into a structured game.

This is the least reliable component in the system and it is supposed to be. The
input is whatever a stranger typed on a phone, and no amount of engineering
makes that fully deterministic. So the design goal is not perfect extraction, it
is **honest** extraction: get what is confidently there, leave the rest null, and
report how much was understood so the rest of the app can decide what to trust.

Two rules that follow from that, and that you should not quietly break:

1. Never invent a field to make a record look complete. A missing price is
   `None`, not zero. A missing date is `None`, not today.
2. Every heuristic here is a guess with a stated reason. If you add one, say
   what real posting habit it encodes, or it will be impossible to tell later
   whether a wrong answer is a bug or a deliberate trade.

Bump `PARSER_VERSION` whenever behaviour changes, so `scripts/reparse.py` can
tell which stored games predate the improvement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.ingest import venue_catalogue as catalogue
from app.models import ParseConfidence, SkillLevel

PARSER_VERSION = 2

SGT = ZoneInfo("Asia/Singapore")

# A bare "8-10" almost always means the evening in these groups. Morning
# sessions are nearly always written with an explicit "am" because the poster
# knows it is the unusual case.
ASSUME_PM_WHEN_AMBIGUOUS = True

# Used when a post gives a start but no end.
DEFAULT_SESSION_MINUTES = 120

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

WEEKDAYS = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "weds": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}

# Posts that are answering or closing an offer rather than making one.
FILLED_MARKERS = re.compile(
    r"\b(filled|full|closed|found|taken|no longer|cancelled|canceled|slots? gone)\b",
    re.IGNORECASE,
)

SKILL_MARKERS: list[tuple[re.Pattern[str], SkillLevel]] = [
    (re.compile(r"\b(beginner|newbie|new to|casual|social|fun game|chill)\b", re.I), SkillLevel.BEGINNER),
    (re.compile(r"\b(intermediate|inter|int lvl|int level|average)\b", re.I), SkillLevel.INTERMEDIATE),
    (re.compile(r"\b(advanced|competitive|comp lvl|strong|high level|adv)\b", re.I), SkillLevel.ADVANCED),
]


@dataclass
class ParsedGame:
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    venue_slug: str | None = None
    raw_venue: str | None = None
    price_cents: int | None = None
    spots_wanted: int | None = None
    skill: SkillLevel | None = None
    is_filled: bool = False
    confidence: ParseConfidence = ParseConfidence.LOW

    @property
    def is_usable(self) -> bool:
        return self.confidence is not ParseConfidence.LOW


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------


def _resolve_weekday(target: int, today: date, *, force_next_week: bool) -> date:
    delta = (target - today.weekday()) % 7
    if force_next_week:
        delta = delta or 7
        return today + timedelta(days=delta + 7)
    return today + timedelta(days=delta)


def parse_date(text: str, today: date) -> date | None:
    lowered = text.lower()

    if re.search(r"\b(today|tonite|tonight)\b", lowered):
        return today
    if re.search(r"\b(tmr|tmrw|tomor+ow|2mr|tomo)\b", lowered):
        return today + timedelta(days=1)

    # "25 Jul", "25th July"
    day_month = re.search(
        r"\b(\d{1,2})\s*(?:st|nd|rd|th)?\s*[-/ ]?\s*"
        r"(jan|feb|mar|apr|may|jun|jul|aug|sept|sep|oct|nov|dec)[a-z]*\b",
        lowered,
    )
    # "Jul 25"
    month_day = re.search(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sept|sep|oct|nov|dec)[a-z]*\s+"
        r"(\d{1,2})\s*(?:st|nd|rd|th)?\b",
        lowered,
    )
    if day_month:
        day, month = int(day_month.group(1)), MONTHS[day_month.group(2)]
    elif month_day:
        month, day = MONTHS[month_day.group(1)], int(month_day.group(2))
    else:
        day = month = None

    if day and month:
        return _year_corrected(day, month, today)

    # "25/7", "25-07-2026"
    numeric = re.search(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b", lowered)
    if numeric:
        day, month = int(numeric.group(1)), int(numeric.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            year_part = numeric.group(3)
            if year_part:
                year = int(year_part)
                year += 2000 if year < 100 else 0
                try:
                    return date(year, month, day)
                except ValueError:
                    return None
            return _year_corrected(day, month, today)

    # Bare weekday, optionally prefixed with "next".
    weekday_match = re.search(
        r"\b(next|nxt|this|coming)?\s*"
        r"(mon|monday|tues|tue|tuesday|weds|wed|wednesday|thurs|thur|thu|thursday|"
        r"fri|friday|sat|saturday|sun|sunday)\b",
        lowered,
    )
    if weekday_match:
        qualifier = weekday_match.group(1)
        target = WEEKDAYS[weekday_match.group(2)]
        return _resolve_weekday(
            target, today, force_next_week=qualifier in {"next", "nxt"}
        )

    return None


def _year_corrected(day: int, month: int, today: date) -> date | None:
    """Pick the year a poster meant.

    Groups post about the near future, so a date more than a month behind us is
    almost certainly next year's — someone writing "2 Jan" in December.
    """
    try:
        candidate = date(today.year, month, day)
    except ValueError:
        return None
    if (today - candidate).days > 31:
        try:
            return date(today.year + 1, month, day)
        except ValueError:
            return None
    return candidate


# ---------------------------------------------------------------------------
# Times
# ---------------------------------------------------------------------------


def _to_minutes(hour: int, minute: int, meridiem: str | None) -> int:
    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    return hour * 60 + minute


def parse_time_range(text: str) -> tuple[int | None, int | None]:
    """Return (start_minutes, end_minutes) past midnight."""
    lowered = text.lower()

    # 24-hour ranges written without separators: "2000-2200".
    military = re.search(
        r"\b([01]\d|2[0-3])([0-5]\d)\s*(?:-|–|—|to|till|until|~)\s*([01]\d|2[0-3])([0-5]\d)\b",
        lowered,
    )
    if military:
        start = int(military.group(1)) * 60 + int(military.group(2))
        end = int(military.group(3)) * 60 + int(military.group(4))
        return start, end

    match = re.search(
        r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\s*"
        r"(?:-|–|—|to|till|untill?|~)\s*"
        r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?",
        lowered,
    )
    if match:
        s_hour, s_min, s_mer = int(match.group(1)), int(match.group(2) or 0), match.group(3)
        e_hour, e_min, e_mer = int(match.group(4)), int(match.group(5) or 0), match.group(6)

        if s_hour > 23 or e_hour > 23:
            return None, None

        # Plain 24-hour clock, e.g. "19:00-21:00".
        if not s_mer and not e_mer and (s_hour > 12 or e_hour > 12):
            return s_hour * 60 + s_min, e_hour * 60 + e_min

        s_mer, e_mer = _resolve_meridiems(s_hour, s_mer, e_hour, e_mer)

        start = _to_minutes(s_hour, s_min, s_mer)
        end = _to_minutes(e_hour, e_min, e_mer)
        if end <= start:
            end += 12 * 60
        return start, (end if end <= 24 * 60 else None)

    # A single stated time: assume a standard session length after it.
    single = re.search(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)\b", lowered)
    if single:
        start = _to_minutes(int(single.group(1)), int(single.group(2) or 0), single.group(3))
        return start, min(start + DEFAULT_SESSION_MINUTES, 24 * 60 - 1)

    return None, None


def _resolve_meridiems(
    s_hour: int, s_mer: str | None, e_hour: int, e_mer: str | None
) -> tuple[str | None, str | None]:
    """Work out am/pm for both ends of a range when the poster only wrote one.

    The 12 o'clock cases are the fiddly ones. "12-3pm" means noon to 3pm, but
    "12-1am" means midnight to 1am, so a blanket "12 means noon" rule is wrong.
    An explicit marker on the other end always wins over the noon assumption.
    """
    if s_mer and not e_mer:
        if e_hour == 12:
            return s_mer, "pm"
        inferred = s_mer
        if e_hour < s_hour:  # crosses the meridiem, e.g. 11am-1pm
            inferred = "pm" if s_mer == "am" else "am"
        return s_mer, inferred

    if e_mer and not s_mer:
        if s_hour == 12 and e_hour != 12:
            return e_mer, e_mer  # "12-1am" is midnight, not noon
        if s_hour == 12:
            return "pm", e_mer
        inferred = e_mer
        if s_hour > e_hour:
            inferred = "am" if e_mer == "pm" else "pm"
        return inferred, e_mer

    if not s_mer and not e_mer:
        default = "pm" if ASSUME_PM_WHEN_AMBIGUOUS else "am"
        return ("pm" if s_hour == 12 else default), ("pm" if e_hour == 12 else default)

    return s_mer, e_mer


# ---------------------------------------------------------------------------
# Venue, price, spots, skill
# ---------------------------------------------------------------------------


def parse_venue(text: str) -> tuple[str | None, str | None]:
    """Return (known_venue_slug, unmatched_venue_text)."""
    lowered = text.lower()
    for alias, slug in catalogue.ALIAS_INDEX:
        if re.search(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])", lowered):
            return slug, None

    # Nothing canonical matched. Keep whatever looks like a place name so the
    # post stays searchable and so gaps in the catalogue are visible.
    for pattern in (
        r"(?:📍|🏟|🏸)\s*([^\n]{3,60})",
        r"\bvenue\s*[:\-]\s*([^\n]{3,60})",
        r"\blocation\s*[:\-]\s*([^\n]{3,60})",
        r"\b(?:at|@)\s+([A-Z][A-Za-z' ]{3,40}(?:hall|centre|center|cc|court|gym|academy|complex))",
    ):
        found = re.search(pattern, text, re.IGNORECASE)
        if found:
            return None, found.group(1).strip(" .,-|")
    return None, None


def parse_price_cents(text: str) -> int | None:
    match = re.search(r"(?:\$|sgd\s*)(\d{1,3}(?:\.\d{1,2})?)", text, re.IGNORECASE)
    if not match:
        match = re.search(
            r"\b(\d{1,3}(?:\.\d{1,2})?)\s*(?:/|per\s*)?(?:pax|person|head)\b", text, re.I
        )
    if not match:
        return None
    return int(round(float(match.group(1)) * 100))


def parse_spots(text: str) -> int | None:
    for pattern in (
        r"\b(?:need|looking for|want|short of|require|wtb)\s*(\d{1,2})\b",
        r"\b(\d{1,2})\s*(?:more\s*)?(?:pax|players?|slots?|spaces?)\b",
        r"\b(\d{1,2})\s*more\b",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            if 1 <= value <= 30:
                return value
    return None


def parse_skill(text: str) -> SkillLevel | None:
    """Last marker wins, since posts tend to end with the qualifier that matters
    ("casual game, intermediate and above")."""
    found: SkillLevel | None = None
    best_position = -1
    for pattern, level in SKILL_MARKERS:
        match = pattern.search(text)
        if match and match.start() > best_position:
            best_position = match.start()
            found = level
    return found


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse(text: str, *, posted_at: datetime | None = None) -> ParsedGame:
    """Parse a post.

    `posted_at` anchors relative dates. Using the post's own timestamp rather
    than the clock means a backfill of six months of history resolves "tomorrow"
    against the day it was written, not the day we happened to run the importer.
    """
    text = text or ""
    anchor = (posted_at or datetime.now(SGT)).astimezone(SGT)
    today = anchor.date()

    game_date = parse_date(text, today)
    start_min, end_min = parse_time_range(text)
    venue_slug, raw_venue = parse_venue(text)

    starts_at = ends_at = None
    if game_date is not None and start_min is not None:
        starts_at = _combine(game_date, start_min)
        if end_min is not None:
            ends_at = _combine(game_date, end_min)
            if ends_at <= starts_at:  # session ran past midnight
                ends_at += timedelta(days=1)

    parsed = ParsedGame(
        starts_at=starts_at,
        ends_at=ends_at,
        venue_slug=venue_slug,
        raw_venue=raw_venue,
        price_cents=parse_price_cents(text),
        spots_wanted=parse_spots(text),
        skill=parse_skill(text),
        is_filled=bool(FILLED_MARKERS.search(text)),
    )
    parsed.confidence = _grade(parsed, has_time=start_min is not None, has_date=game_date is not None)
    return parsed


def _combine(day: date, minutes: int) -> datetime:
    hour, minute = divmod(minutes, 60)
    if hour >= 24:
        day = day + timedelta(days=1)
        hour -= 24
    return datetime.combine(day, time(hour, minute), tzinfo=SGT)


def _grade(parsed: ParsedGame, *, has_time: bool, has_date: bool) -> ParseConfidence:
    """Decide how much of the post we actually understood.

    A time is non-negotiable: a game without one cannot be filtered, which is
    the entire point of the product. Beyond that, knowing both where and when
    makes a clean card; knowing one of the two still beats leaving the post
    buried in a chat log.
    """
    if not has_time:
        return ParseConfidence.LOW

    has_venue = parsed.venue_slug is not None
    if has_date and has_venue:
        return ParseConfidence.HIGH
    if has_date or has_venue or parsed.raw_venue:
        return ParseConfidence.PARTIAL
    return ParseConfidence.LOW
