"""Trouver le prix d'un produit dans le code HTML d'une page de boutique.

On essaie plusieurs méthodes, de la plus fiable à la moins fiable :
1. le sélecteur CSS donné par l'utilisateur (s'il y en a un) ;
2. les données structurées « JSON-LD » que la plupart des boutiques ajoutent pour Google ;
3. les balises <meta> de prix ;
4. les emplacements où les sites affichent souvent le prix (Amazon, classes « price »…).
"""

import json
import re

from bs4 import BeautifulSoup

from utils.money import parse_amount

# Sélecteurs CSS testés en dernier recours, dans cet ordre
KNOWN_PRICE_SELECTORS = [
    "#corePrice_feature_div .a-offscreen",  # Amazon
    "#corePriceDisplay_desktop_feature_div .a-offscreen",  # Amazon
    ".a-price .a-offscreen",  # Amazon
    "#priceblock_ourprice",  # Amazon (ancienne présentation)
    "[itemprop=price]",
    "[data-price]",
    ".product-price",
    ".price",
]

# Types d'objets JSON-LD qui contiennent un prix
OFFER_TYPES = ["Offer", "AggregateOffer"]


class PriceNotFound(Exception):
    """Le prix n'a pas pu être trouvé sur la page."""


def steam_app_id(url: str) -> int | None:
    """Numéro du jeu dans une URL Steam (store.steampowered.com/app/1145360/…), sinon None."""
    match = re.search(r"store\.steampowered\.com/app/(\d+)", url)
    if match:
        return int(match.group(1))
    return None


def extract_price(html: str, selector: str | None = None) -> int:
    """Renvoie le prix trouvé dans la page, en centimes. Lève PriceNotFound sinon."""
    page = BeautifulSoup(html, "html.parser")

    if selector:
        return price_from_selector(page, selector)

    price = price_from_json_ld(page)
    if price is not None:
        return price

    price = price_from_meta_tags(page)
    if price is not None:
        return price

    price = price_from_known_selectors(page)
    if price is not None:
        return price

    raise PriceNotFound("Prix introuvable : ajoute un sélecteur CSS avec l'option « selecteur ».")


# --- 1. Sélecteur choisi par l'utilisateur ---------------------------------------------------

def price_from_selector(page: BeautifulSoup, selector: str) -> int:
    element = page.select_one(selector)
    if element is None:
        raise PriceNotFound(f"Le sélecteur « {selector} » ne correspond à rien sur la page.")
    price = price_in_element(element)
    if price is None:
        raise PriceNotFound(f"Aucun prix lisible dans « {selector} ».")
    return price


# --- 2. Données structurées JSON-LD --------------------------------------------------------------

def price_from_json_ld(page: BeautifulSoup) -> int | None:
    """Les boutiques décrivent souvent leurs produits ainsi (format schema.org) :

    <script type="application/ld+json">
      {"@type": "Product", "offers": {"@type": "Offer", "price": "89.90"}}
    </script>
    """
    for script in page.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue  # bloc mal formé : on passe au suivant
        price = find_offer_price(data)
        if price is not None:
            return price
    return None


def find_offer_price(data) -> int | None:
    """Cherche un prix d'offre dans des données JSON, qui peuvent être imbriquées.

    La fonction s'appelle elle-même sur les sous-éléments (« récursion ») :
    produit → offres → offre → prix.
    """
    # Une liste : on cherche dans chaque élément
    if isinstance(data, list):
        for element in data:
            price = find_offer_price(element)
            if price is not None:
                return price
        return None

    # Ni liste ni dictionnaire (texte, nombre…) : pas de prix ici
    if not isinstance(data, dict):
        return None

    # Est-ce une offre ? (« @type » peut être un texte ou une liste de textes)
    types = data.get("@type")
    if not isinstance(types, list):
        types = [types]
    is_offer = any(offer_type in types for offer_type in OFFER_TYPES)

    if is_offer:
        # « lowPrice » est utilisé quand plusieurs vendeurs proposent le produit
        for key in ["price", "lowPrice"]:
            price = to_cents_or_none(data.get(key))
            if price is not None:
                return price
        specification = data.get("priceSpecification")
        if isinstance(specification, dict):
            price = to_cents_or_none(specification.get("price"))
            if price is not None:
                return price

    # Sinon, on descend dans les sous-parties qui contiennent habituellement les offres
    for key in ["offers", "@graph", "mainEntity", "hasVariant"]:
        if key in data:
            price = find_offer_price(data[key])
            if price is not None:
                return price
    return None


# --- 3. Balises <meta> ----------------------------------------------------------------------

def price_from_meta_tags(page: BeautifulSoup) -> int | None:
    meta_tags_to_try = [
        {"itemprop": "price"},
        {"property": "product:price:amount"},
        {"property": "og:price:amount"},
    ]
    for attributes in meta_tags_to_try:
        meta = page.find("meta", attrs=attributes)
        if meta is not None:
            price = to_cents_or_none(meta.get("content"))
            if price is not None:
                return price
    return None


# --- 4. Emplacements connus ----------------------------------------------------------------------

def price_from_known_selectors(page: BeautifulSoup) -> int | None:
    for selector in KNOWN_PRICE_SELECTORS:
        # On regarde les 3 premiers éléments trouvés (le premier est parfois vide)
        for element in page.select(selector)[:3]:
            price = price_in_element(element)
            if price is not None:
                return price
    return None


# --- Outils -------------------------------------------------------------------------------------

def price_in_element(element) -> int | None:
    """Prix contenu dans un élément HTML : d'abord dans ses attributs, puis dans son texte."""
    for attribute in ["content", "data-price", "value"]:
        value = element.get(attribute)
        if value:
            price = to_cents_or_none(value)
            if price is not None:
                return price
    return to_cents_or_none(element.get_text(" ", strip=True))


def to_cents_or_none(value) -> int | None:
    """Convertit un prix (nombre ou texte) en centimes, ou renvoie None si ce n'est pas un prix."""
    if value is None or value == "":
        return None
    # Dans le JSON, le prix peut être un vrai nombre (89.9) plutôt qu'un texte
    if isinstance(value, (int, float)):
        if value > 0:
            return round(value * 100)
        return None
    try:
        return parse_amount(str(value))
    except ValueError:
        return None
