"""Trouver le prix d'un produit dans le code HTML d'une page de boutique."""

import re

from bs4 import BeautifulSoup

from utils.money import to_cents

# Endroits où les boutiques affichent souvent le prix (Amazon en premier)
KNOWN_SELECTORS = [".a-price .a-offscreen", "#priceblock_ourprice", "[itemprop=price]", ".product-price", ".price"]


def find_price(html, selector=None):
    """Renvoie le prix en centimes, ou None s'il est introuvable."""
    page = BeautifulSoup(html, "html.parser")

    # 1. Sélecteur CSS donné par l'utilisateur
    if selector:
        element = page.select_one(selector)
        return text_to_price(element.get_text()) if element else None

    # 2. Données « JSON-LD » que la plupart des boutiques ajoutent pour Google
    for script in page.find_all("script", type="application/ld+json"):
        match = re.search(r'"(?:price|lowPrice)"\s*:\s*"?(\d+(?:\.\d+)?)', script.get_text())
        if match:
            return round(float(match[1]) * 100)

    # 3. Balises <meta> de prix
    for attributes in ({"itemprop": "price"}, {"property": "product:price:amount"}, {"property": "og:price:amount"}):
        meta = page.find("meta", attrs=attributes)
        if meta and meta.get("content"):
            return text_to_price(meta["content"])

    # 4. Emplacements classiques
    for css in KNOWN_SELECTORS:
        element = page.select_one(css)
        if element and (price := text_to_price(element.get("content") or element.get_text())):
            return price
    return None


def text_to_price(text):
    try:
        return to_cents(text)
    except ValueError:
        return None
