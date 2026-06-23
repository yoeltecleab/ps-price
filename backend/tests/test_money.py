from backend.app.money import money_to_cents


def test_money_to_cents_handles_common_store_values():
    assert money_to_cents("$69.99") == 6999
    assert money_to_cents("Free") == 0
    assert money_to_cents(12.34) == 1234
    assert money_to_cents("EUR 9,99") == 999
