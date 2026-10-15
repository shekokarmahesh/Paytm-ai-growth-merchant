from datetime import date, datetime

import pytest

from app.agent import guard, lang
from app.analytics import discount, restock
from app.analytics.footfall import Forecast, find_slump
from app.config import settings, whatsapp_address


# --- numbers guardrail ---------------------------------------------------------------------------

def test_inr_uses_indian_grouping():
    assert guard.inr(1234567) == "₹12,34,567"
    assert guard.inr(18998) == "₹18,998"
    assert guard.inr(999) == "₹999"


@pytest.mark.parametrize("draft,reason", [
    ("Kal {sales} ki bikri", None),
    ("Kal 14200 ki bikri", "contains a number the model wrote itself"),
    ("Kal १४ ki bikri", "contains a number the model wrote itself"),
    ("Kal {profit} ki bikri", "unknown placeholders ['profit']"),
    ("Kal {sales ki bikri", "malformed braces"),
])
def test_validate(draft, reason):
    assert guard.validate(draft, {"sales"}) == reason


def test_render_falls_back_when_llm_invents_a_number():
    text, used_llm = guard.render("Sales 99999!", "Sales {sales}", {"sales": "₹18,998"})
    assert (text, used_llm) == ("Sales ₹18,998", False)


# --- margin-safe cashback ------------------------------------------------------------------------

def test_optimiser_never_exceeds_half_the_margin():
    plan = discount.optimise(targets=100, avg_ticket=120, margin=0.12)
    assert plan is None or plan.discount_pct <= 6


def test_optimiser_picks_a_profitable_offer():
    plan = discount.optimise(targets=86, avg_ticket=123, margin=0.20, hours=3, p0=0.02)
    assert plan and 5 <= plan.discount_pct <= 10 and plan.expected_profit > 0


def test_optimiser_skips_when_nothing_is_profitable():
    assert discount.optimise(targets=100, avg_ticket=120, margin=0.10, p0=0.9) is None
    assert discount.optimise(targets=0, avg_ticket=120, margin=0.20) is None


@pytest.mark.parametrize("pct,hours,reason", [(12, 3, "above_cap"), (3, 3, "below_min"), (8, 12, "bad_duration")])
def test_modified_offer_is_rechecked(pct, hours, reason):
    plan, why = discount.check(pct, hours, targets=86, avg_ticket=123, margin=0.20)
    assert plan is None and why == reason


def test_safe_modification_is_accepted():
    plan, why = discount.check(8, 2, targets=86, avg_ticket=123, margin=0.20)
    assert why is None and plan.discount_pct == 8 and plan.duration_hours == 2


# --- restock -------------------------------------------------------------------------------------

def test_reorder_covers_lead_time_plus_cover():
    assert restock.reorder_qty(rate=2.0, lead=6, stock=10) == 2 * (6 + restock.COVER_DAYS) - 10
    assert restock.reorder_qty(rate=0.1, lead=3, stock=50) == 0


def test_festive_acceleration_lifts_run_rate_only_in_season():
    in_season, off_season = date(2026, 10, 6), date(2026, 6, 1)
    base = 0.6 * 14 / 7 + 0.4 * 28 / 28
    assert restock.run_rate(14, 28, off_season) == pytest.approx(base)
    assert restock.run_rate(14, 28, in_season) == pytest.approx(base * 1.5)


# --- slump detection -----------------------------------------------------------------------------

def _fc(hourly):
    return Forecast(date(2026, 10, 6), hourly, 0.1)


def test_finds_the_afternoon_trough():
    hourly = {h: 12.0 for h in range(7, 23)} | {14: 3.0, 15: 2.5, 16: 3.0}
    s = find_slump(_fc(hourly), after=datetime(2026, 10, 6, 13, 45, tzinfo=settings.tz))
    assert (s.start_hour, s.end_hour) == (14, 17) and s.drop_pct > 60


def test_ignores_slumps_already_past():
    hourly = {h: 12.0 for h in range(7, 23)} | {9: 2.0, 10: 2.0}
    assert find_slump(_fc(hourly), after=datetime(2026, 10, 6, 13, 0, tzinfo=settings.tz)) is None


# --- language + addressing -----------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("haan bilkul shuru kar do", "hinglish"),
    ("हाँ शुरू कर दो", "hi"),
    ("please launch the offer now", "en"),
    ("ok", "hinglish"),  # too short to tell -> keep the merchant's default
])
def test_language_detection(text, expected):
    assert lang.detect(text, default="hinglish") == expected


def test_whatsapp_address_normalises_spaces_and_prefix():
    assert whatsapp_address("+91 00000 00001") == "whatsapp:+910000000001"
    assert whatsapp_address("whatsapp:+1 555 010 0200") == "whatsapp:+15550100200"


# --- tap buttons ---------------------------------------------------------------------------------

def _utf16(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def test_choice_titles_fit_twilio_limits():
    from app.flows import choices
    for opts in choices.QUICK.values():
        for buttons in opts.values():
            assert len(buttons) <= 3
            assert all(_utf16(t) <= 20 for _, t in buttons), buttons
    for button, items in choices.LIST.values():
        assert _utf16(button) <= 20 and len(items) <= 10
        assert all(_utf16(i) <= 24 and len(d) <= 72 for _, i, d in items), items


def test_tapped_titles_map_to_commands():
    from app.flows import choices
    assert choices.tapped("✅ Haan, shuru karo") == "haan"
    assert choices.tapped("📦 Restock check") == "stock"
    assert choices.tapped("📱 Electronics store") == "switch electronics"
    assert choices.tapped("kal kitni bikri hui") is None
