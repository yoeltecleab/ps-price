"""Tests for PlayStation GraphQL product parsing."""

from backend.app.ps_graphql import parse_graphql_product

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
