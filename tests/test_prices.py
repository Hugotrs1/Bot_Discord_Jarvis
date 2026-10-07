import pytest

from cogs.prices import Prices
from utils.prices import PriceNotFound, extract_price, steam_app_id

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


def test_json_ld_prioritaire():
    assert extract_price(JSON_LD) == 8990


def test_json_ld_graph_et_aggregate_offer():
    assert extract_price(JSON_LD_GRAPH) == 24900


def test_balises_meta():
    assert extract_price(META) == 129900


def test_amazon():
    assert extract_price(AMAZON) == 3499


def test_selecteur_personnalise():
    assert extract_price(CUSTOM, selector=".montant") == 104995


def test_selecteur_introuvable():
    with pytest.raises(PriceNotFound):
        extract_price(CUSTOM, selector=".introuvable")


def test_pas_de_prix():
    with pytest.raises(PriceNotFound):
        extract_price("<html><body><p>Rupture de stock</p></body></html>")


def test_steam_app_id():
    assert steam_app_id("https://store.steampowered.com/app/1145360/Hades/") == 1145360
    assert steam_app_id("https://www.amazon.fr/dp/B0") is None


@pytest.mark.parametrize("old, new, target, expected", [
    (5000, 4500, None, True),   # baisse
    (5000, 5500, None, False),  # hausse
    (5000, 5000, None, False),  # pas de changement
    (None, 4000, 4500, True),   # première lecture déjà sous la cible
    (None, 5000, 4500, False),
    (4000, 4000, 4500, False),  # cible déjà atteinte avant : pas de nouvelle alerte
])
def test_quand_alerter(old, new, target, expected):
    assert Prices.should_alert(old, new, target) is expected
