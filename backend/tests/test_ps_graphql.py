"""Tests for PlayStation GraphQL product parsing."""

from backend.app.ps_graphql import parse_graphql_concept, parse_graphql_product

SAMPLE_PRODUCT = {
    "id": "UP0001-CUSA12345_00-EXAMPLEGAME",
    "name": "Example Game Deluxe",
    "platforms": ["PS5", "PS4"],
    "media": [
        {"role": "GAMEHUB_COVER_ART", "url": "https://image.api.playstation.com/cover.jpg"}
    ],
    "price": {
        "basePrice": "$59.99",
        "discountedPrice": "$29.99",
        "discountText": "-50%",
    },
}


def test_parse_graphql_product_extracts_fields():
    result = parse_graphql_product(
        SAMPLE_PRODUCT, "en-us", "https://store.playstation.com"
    )
    assert result is not None
    assert result.product_id == "UP0001-CUSA12345_00-EXAMPLEGAME"
    assert result.name == "Example Game Deluxe"
    assert result.current_price_formatted == "$29.99"
    assert result.original_price_formatted == "$59.99"
    assert result.discount_text == "-50%"
    assert result.platforms == ["PS5", "PS4"]
    assert "store.playstation.com" in result.store_url


def test_parse_graphql_product_skips_invalid():
    assert parse_graphql_product({}, "en-us", "https://store.playstation.com") is None
    assert (
        parse_graphql_product({"id": "X", "name": ""}, "en-us", "https://store.playstation.com")
        is None
    )


def test_parse_graphql_concept_uses_nested_product():
    result = parse_graphql_concept(
        {
            "name": "007 First Light",
            "media": [{"role": "GAMEHUB_COVER_ART", "url": "https://example.test/007.jpg"}],
            "price": {"basePrice": "$69.99", "discountedPrice": "$69.99"},
            "products": [{"id": "EP3969-PPSA11386_00-007FIRSTLIGHT000", "platforms": ["PS5"]}],
        },
        "en-us",
        "https://store.playstation.com",
    )
    assert result is not None
    assert result.name == "007 First Light"
    assert result.product_id == "EP3969-PPSA11386_00-007FIRSTLIGHT000"
    assert result.current_price_formatted == "$69.99"
