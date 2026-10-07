import pytest

from utils.money import euros, to_cents
from utils.prices import find_price


@pytest.mark.parametrize("text, cents", [
    ("12", 1200),
    ("12,50", 1250),
    ("12.5 €", 1250),
    ("1 299,99 €", 129999),
    ("1 299,99 €", 129999),
    ("1,299.99", 129999),
    ("1.299,99", 129999),
    ("29€99", 2999),
    ("Prix : 129,99 € 15 avis", 12999),
])
def test_to_cents(text, cents):
    assert to_cents(text) == cents


@pytest.mark.parametrize("text", ["", "gratuit", "0"])
def test_to_cents_refuse(text):
    with pytest.raises(ValueError):
        to_cents(text)


def test_euros():
    assert euros(1250) == "12,50 €"
    assert euros(129999) == "1 299,99 €"


def test_prix_json_ld():
    html = '<script type="application/ld+json">{"@type": "Product", "offers": {"price": "89.90"}}</script>'
    assert find_price(html) == 8990


def test_prix_meta():
    assert find_price('<meta property="product:price:amount" content="1299.00">') == 129900


def test_prix_amazon():
    html = '<span class="a-price"><span class="a-offscreen">34,99 €</span></span>'
    assert find_price(html) == 3499


def test_prix_selecteur_personnalise():
    html = '<div class="prix-final">Seulement 49,90 €</div><div class="price">99 €</div>'
    assert find_price(html, ".prix-final") == 4990


def test_prix_introuvable():
    assert find_price("<p>Rupture de stock</p>") is None
