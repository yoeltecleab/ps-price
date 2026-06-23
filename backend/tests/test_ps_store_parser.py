from backend.app.ps_store import parse_product_page, parse_search_page


PRODUCT_HTML = """
<html><head>
<script id="mfe-jsonld-tags" type="application/ld+json">
{"@context":"http://schema.org","@type":"Product","name":"Example Game","category":"Game","sku":"UP0000-PPSA00000_00-EXAMPLEGAME0000","image":"https://example.test/image.png","offers":{"@type":"Offer","price":59.99,"priceCurrency":"USD"}}
</script>
</head><body>
<script id="env:abc" type="application/json">
{"args":{"productId":"UP0000-PPSA00000_00-EXAMPLEGAME0000"},"cache":{"Product:UP0000-PPSA00000_00-EXAMPLEGAME0000":{"id":"UP0000-PPSA00000_00-EXAMPLEGAME0000","name":"Example Game","media":[{"type":"IMAGE","role":"MASTER","url":"https://example.test/master.png"}]},"GameCTA:ADD_TO_CART:ADD_TO_CART:UP0000-PPSA00000_00-EXAMPLEGAME0000-U001:OUTRIGHT":{"id":"cta","price":{"basePrice":"$59.99","discountedPrice":"$29.99","basePriceValue":5999,"discountedValue":2999,"currencyCode":"USD","savingTag":"Save 50%","applicability":"APPLICABLE"}}}}
</script>
</body></html>
"""


SEARCH_HTML = """
<script id="__NEXT_DATA__" type="application/json">
{"props":{"apolloState":{"Product:UP0000-PPSA00000_00-EXAMPLEGAME0000":{"id":"UP0000-PPSA00000_00-EXAMPLEGAME0000","name":"Example Game","platforms":["PS5"],"media":[{"type":"IMAGE","role":"MASTER","url":"https://example.test/master.png"}],"price":{"basePrice":"$59.99","discountedPrice":"$29.99","discountText":"-50%"}}}}}
</script>
"""


def test_parse_product_page_uses_component_price_over_jsonld():
    snapshot = parse_product_page(
        PRODUCT_HTML,
        "UP0000-PPSA00000_00-EXAMPLEGAME0000",
        "en-us",
        "https://store.playstation.com/en-us/product/UP0000-PPSA00000_00-EXAMPLEGAME0000",
    )

    assert snapshot.name == "Example Game"
    assert snapshot.current_price_cents == 2999
    assert snapshot.original_price_cents == 5999
    assert snapshot.currency == "USD"
    assert snapshot.discount_text == "Save 50%"
    assert snapshot.image_url == "https://example.test/master.png"


def test_parse_search_page_reads_next_apollo_products():
    results = parse_search_page(SEARCH_HTML, "en-us", "https://store.playstation.com")

    assert len(results) == 1
    assert results[0].product_id == "UP0000-PPSA00000_00-EXAMPLEGAME0000"
    assert results[0].current_price_cents == 2999
    assert results[0].platforms == ["PS5"]
