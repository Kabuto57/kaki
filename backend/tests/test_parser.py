"""Parser tests.

These are written against the shapes real posts take, not against the parser's
internals, so they stay meaningful when the implementation is rewritten. Every
case here came from a habit people actually have: abbreviating venues, dropping
the am/pm, writing "tmr", saying "12-3pm" and meaning noon.

Run: pytest tests/test_parser.py -v
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.ingest.parser import SGT, parse
from app.models import ParseConfidence, SkillLevel

# A Tuesday, so weekday resolution has somewhere to go in both directions.
ANCHOR = datetime(2026, 7, 28, 10, 0, tzinfo=ZoneInfo("Asia/Singapore"))


def p(text: str):
    return parse(text, posted_at=ANCHOR)


class TestStructuredPosts:
    def test_emoji_block_format(self):
        game = p("📍 Choa Chu Kang Sports Hall\n📅 30 Jul (Thu)\n⏰ 8pm-10pm\n$8/pax, need 2 more")
        assert game.venue_slug == "choa_chu_kang"
        assert game.starts_at == datetime(2026, 7, 30, 20, 0, tzinfo=SGT)
        assert game.ends_at == datetime(2026, 7, 30, 22, 0, tzinfo=SGT)
        assert game.price_cents == 800
        assert game.spots_wanted == 2
        assert game.confidence is ParseConfidence.HIGH

    def test_labelled_format(self):
        game = p("Venue: Bishan Sports Hall\nDate: 1 Aug\nTime: 7-9pm\nPrice: $6")
        assert game.venue_slug == "bishan"
        assert game.starts_at == datetime(2026, 8, 1, 19, 0, tzinfo=SGT)
        assert game.price_cents == 600


class TestFreeformPosts:
    def test_conversational(self):
        game = p("anyone free for badminton at Bishan tmr 7-9pm? need 3 players")
        assert game.venue_slug == "bishan"
        assert game.starts_at == datetime(2026, 7, 29, 19, 0, tzinfo=SGT)
        assert game.spots_wanted == 3

    def test_abbreviated_venue(self):
        game = p("CCK 8-10pm wed, 2 slots")
        assert game.venue_slug == "choa_chu_kang"

    def test_longest_alias_wins(self):
        assert p("Jurong West Sports Hall 8-10pm Thu").venue_slug == "jurong_west"
        assert p("Jurong East SH 8-10pm Thu").venue_slug == "jurong_east"


class TestTimeParsing:
    def test_military_range(self):
        game = p("Jurong East 2000-2200 tonight")
        assert game.starts_at.hour == 20
        assert game.ends_at.hour == 22

    def test_half_hours(self):
        game = p("Tampines 8.30-10.30pm Fri")
        assert (game.starts_at.hour, game.starts_at.minute) == (20, 30)
        assert (game.ends_at.hour, game.ends_at.minute) == (22, 30)

    def test_explicit_morning(self):
        game = p("Sat 9-11am at Woodlands Sports Hall")
        assert game.starts_at.hour == 9
        assert game.ends_at.hour == 11

    def test_crosses_noon(self):
        game = p("Sunday 11am-1pm Kallang")
        assert game.starts_at.hour == 11
        assert game.ends_at.hour == 13

    def test_bare_range_assumes_evening(self):
        # Groups overwhelmingly post evening games; "8-10" is 8pm.
        assert p("CCK 8-10 wed").starts_at.hour == 20

    def test_noon_start_without_meridiem(self):
        # "12-3pm" is noon to 3pm, not midnight.
        game = p("Court 12-3pm at Bishan tmr")
        assert game.starts_at.hour == 12
        assert game.ends_at.hour == 15

    def test_midnight_beats_noon_when_am_is_explicit(self):
        # "12-1am" is genuinely midnight; the explicit marker must win.
        game = p("Kallang 12-1am tonight")
        assert game.starts_at.hour == 0
        assert game.ends_at.hour == 1

    def test_single_time_gets_default_length(self):
        game = p("badminton at Yishun tonight 8pm")
        assert game.starts_at.hour == 20
        assert game.ends_at.hour == 22


class TestDateParsing:
    def test_today_and_tomorrow(self):
        assert p("Bishan 8-10pm today").starts_at.date() == ANCHOR.date()
        assert p("Bishan 8-10pm tmr").starts_at.day == 29

    def test_bare_weekday_resolves_forward(self):
        # Anchor is Tuesday 28 Jul; "Fri" is the 31st.
        assert p("Bukit Gombak 8-10pm Fri").starts_at.day == 31

    def test_next_weekday_skips_a_week(self):
        assert p("Bukit Gombak 8-10pm next Fri").starts_at.day == 7

    def test_numeric_date(self):
        assert p("Hougang 7.30pm-9.30pm on 5/8").starts_at.date().isoformat() == "2026-08-05"

    def test_rolls_into_next_year(self):
        # Posted in July, "2 Jan" means the coming January.
        assert p("Clementi 8-10pm on 2 Jan").starts_at.year == 2027

    def test_relative_date_anchors_to_post_time_not_now(self):
        earlier = datetime(2026, 3, 10, 9, 0, tzinfo=SGT)
        game = parse("Bishan 8-10pm tmr", posted_at=earlier)
        assert game.starts_at.date().isoformat() == "2026-03-11"


class TestSignals:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Bishan 8-10pm tmr, casual game welcome", SkillLevel.BEGINNER),
            ("Bishan 8-10pm tmr, intermediate level", SkillLevel.INTERMEDIATE),
            ("Bishan 8-10pm tmr, advanced players only", SkillLevel.ADVANCED),
            ("Bishan 8-10pm tmr", None),
        ],
    )
    def test_skill_detection(self, text, expected):
        assert p(text).skill is expected

    def test_filled_posts_are_flagged(self):
        assert p("Bishan 8-10pm tmr — FILLED thanks all").is_filled is True
        assert p("Bishan 8-10pm tmr, 2 slots left").is_filled is False

    def test_price_formats(self):
        assert p("Bishan 8-10pm tmr $7.50").price_cents == 750
        assert p("Bishan 8-10pm tmr, 8/pax").price_cents == 800
        assert p("Bishan 8-10pm tmr").price_cents is None


class TestConfidence:
    def test_date_time_and_venue_is_high(self):
        assert p("Bishan 30 Jul 8-10pm").confidence is ParseConfidence.HIGH

    def test_missing_date_is_partial(self):
        assert p("Bishan 8-10pm").confidence is ParseConfidence.PARTIAL

    def test_unknown_venue_still_partial(self):
        game = p("📍 Some New Sports Centre\n8-10pm tmr")
        assert game.venue_slug is None
        assert "Sports Centre" in game.raw_venue
        assert game.confidence is ParseConfidence.PARTIAL

    @pytest.mark.parametrize(
        "noise",
        [
            "anyone knows where to restring rackets?",
            "thanks bro",
            "Yonex Astrox 88D for sale $150",
            "good game today everyone",
        ],
    )
    def test_chatter_is_not_usable(self, noise):
        assert p(noise).is_usable is False

    def test_no_invented_values(self):
        """The parser must never fill a gap with a plausible default."""
        game = p("Bishan 8-10pm")
        assert game.starts_at is None  # no date given, so no timestamp
        assert game.price_cents is None
        assert game.spots_wanted is None
