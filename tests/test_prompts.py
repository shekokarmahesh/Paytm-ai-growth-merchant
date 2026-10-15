"""A bare number answers the bot's most recent message — never an older question."""
import pytest

from app import db
from app.channels import twilio
from app.flows import common


@pytest.fixture
def merchant(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "path", lambda: str(tmp_path / "t.db"))
    monkeypatch.setattr(twilio, "send", lambda to, body: "SIM")
    db.init()
    db.run("INSERT INTO merchants VALUES ('k','Shop','Ji','kirana','whatsapp:+910','hi-IN','hinglish',0.2,'x@paytm')")
    return common.merchant("k")


def test_question_message_carries_its_choices(merchant):
    common.set_prompt("k", "cashback")
    common.send(merchant, "Offer… 1 haan / 2 nahi")
    assert common.last_prompt("k") == "cashback"


def test_any_later_message_resets_the_choices(merchant):
    common.set_prompt("k", "restock")
    common.send(merchant, "Draft… 1 approve / 2 reject")
    common.send(merchant, "Okay, no purchase orders sent.")
    assert common.last_prompt("k") == "none"


def test_menu_after_offer_wins(merchant):
    common.set_prompt("k", "cashback")
    common.send(merchant, "Offer…")
    common.set_prompt("k", "menu")
    common.send(merchant, "Menu…")
    assert common.last_prompt("k") == "menu"
