"""Extraction du prix d'une page produit, sans dépendre d'un site en particulier.

Stratégie, de la plus fiable à la moins fiable :
1. sélecteur CSS fourni par l'utilisateur ;
2. données structurées JSON-LD (schema.org Product/Offer), présentes sur la plupart des boutiques ;
3. balises meta (itemprop="price", product:price:amount, og:price:amount) ;
4. sélecteurs connus (Amazon, etc.).
"""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from jarvis.utils.money import parse_amount

STEAM_APP = re.compile(r"store\.steampowered\.com/app/(\d+)")

FALLBACK_SELECTORS = [
    "#corePrice_feature_div .a-offscreen",
    "#corePriceDisplay_desktop_feature_div .a-offscreen",
    ".a-price .a-offscreen",
    "#priceblock_ourprice",
    "[itemprop=price]",
    "[data-price]",
    ".product-price",
    ".price",
]

OFFER_TYPES = {"Offer", "AggregateOffer"}


class PriceNotFound(Exception):
    pass


def steam_app_id(url: str) -> int | None:
    m = STEAM_APP.search(url)
    return int(m.group(1)) if m else None


def _to_cents(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return round(float(value) * 100) if value > 0 else None
    try:
        return parse_amount(str(value))
    except ValueError:
        return None


def _find_offer_price(node: Any) -> int | None:
    """Parcourt récursivement un bloc JSON-LD à la recherche d'un prix d'offre."""
    if isinstance(node, list):
        for child in node:
            if (price := _find_offer_price(child)) is not None:
                return price
        return None
    if not isinstance(node, dict):
        return None

    types = node.get("@type")
    types = set(types) if isinstance(types, list) else {types}
    if types & OFFER_TYPES:
        for key in ("price", "lowPrice"):
            if (price := _to_cents(node.get(key))) is not None:
                return price
        spec = node.get("priceSpecification")
        if spec and (price := _find_offer_price({"@type": "Offer", **spec} if isinstance(spec, dict) else spec)):
            return price

    for key in ("offers", "@graph", "mainEntity", "hasVariant"):
        if key in node and (price := _find_offer_price(node[key])) is not None:
            return price
    return None


def extract_price(html: str, selector: str | None = None) -> int:
    """Renvoie le prix trouvé dans la page, en centimes. Lève PriceNotFound sinon."""
    soup = BeautifulSoup(html, "html.parser")

    if selector:
        element = soup.select_one(selector)
        if element is None:
            raise PriceNotFound(f"Le sélecteur « {selector} » ne correspond à rien sur la page.")
        if (price := _element_price(element)) is not None:
            return price
        raise PriceNotFound(f"Aucun prix lisible dans « {selector} ».")

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if (price := _find_offer_price(data)) is not None:
            return price

    for attrs in (
        {"itemprop": "price"},
        {"property": "product:price:amount"},
        {"property": "og:price:amount"},
    ):
        meta = soup.find("meta", attrs=attrs)
        if meta and (price := _to_cents(meta.get("content"))) is not None:
            return price

    for css in FALLBACK_SELECTORS:
        for element in soup.select(css)[:3]:
            if (price := _element_price(element)) is not None:
                return price

    raise PriceNotFound("Prix introuvable : ajoute un sélecteur CSS avec l'option `selecteur`.")


def _element_price(element: Any) -> int | None:
    for attr in ("content", "data-price", "value"):
        if element.get(attr) and (price := _to_cents(element[attr])) is not None:
            return price
    return _to_cents(element.get_text(" ", strip=True))
