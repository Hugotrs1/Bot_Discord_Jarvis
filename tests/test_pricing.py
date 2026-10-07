import pytest

from jarvis.utils.pricing import PriceNotFound, extract_price, steam_app_id

JSON_LD = """
<html><head>
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "Product", "name": "Clavier",
 "offers": {"@type": "Offer", "price": "89.90", "priceCurrency": "EUR"}}
</script>
</head><body><span class="price">99,99 €</span></body></html>
"""

JSON_LD_GRAPH = """
<script type="application/ld+json">
{"@graph": [{"@type": "WebPage"}, {"@type": "Product",
  "offers": [{"@type": "AggregateOffer", "lowPrice": 249, "highPrice": 299}]}]}
</script>
"""

META = '<meta property="product:price:amount" content="1299.00"><meta property="og:title" content="TV">'

AMAZON = """
<div id="corePrice_feature_div"><span class="a-price"><span class="a-offscreen">34,99 €</span></span></div>
"""

CUSTOM = '<div class="produit"><b class="montant">1 049<sup>€95</sup></b></div>'


def test_json_ld_has_priority():
    assert extract_price(JSON_LD) == 8990


def test_json_ld_graph_and_aggregate_offer():
    assert extract_price(JSON_LD_GRAPH) == 24900


def test_meta_tags():
    assert extract_price(META) == 129900


def test_amazon_selector():
    assert extract_price(AMAZON) == 3499


def test_custom_selector():
    assert extract_price(CUSTOM, selector=".montant") == 104995


def test_custom_selector_missing():
    with pytest.raises(PriceNotFound):
        extract_price(CUSTOM, selector=".introuvable")


def test_no_price():
    with pytest.raises(PriceNotFound):
        extract_price("<html><body><p>Rupture de stock</p></body></html>")


def test_steam_app_id():
    assert steam_app_id("https://store.steampowered.com/app/1145360/Hades/") == 1145360
    assert steam_app_id("https://www.amazon.fr/dp/B0") is None
