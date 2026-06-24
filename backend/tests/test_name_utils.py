"""Tests for PlayStation Store display name helpers."""

from backend.app.name_utils import clean_game_name, infer_edition_name


def test_clean_game_name_strips_code_suffix():
    assert clean_game_name("007 First Light (007FIRSTLIGHT000)") == "007 First Light"


def test_infer_edition_name_deluxe():
    assert (
        infer_edition_name("007 First Light", "EP3969-PPSA11386_00-007FLDELUXE00000")
        == "007 First Light - Deluxe Edition"
    )


def test_infer_edition_name_upgrade():
    assert (
        infer_edition_name("007 First Light", "EP3969-PPSA11386_00-007FLDELUXEUPG00")
        == "007 First Light - Deluxe Edition Upgrade"
    )
