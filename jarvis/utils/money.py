"""Conversion entre texte et montants en centimes."""

from __future__ import annotations

import re

_SPACES = re.compile(r"[\s  ]")
_NUMBER = re.compile(r"\d[\d\s  .,]*\d|\d")
_EURO_CENTS = re.compile(r"(?<![\d,.])(\d[\d\s  .]*)€(\d{2})\b")  # « 29€99 »


def parse_amount(text: str) -> int:
    """Convertit « 12,50 », « 12.5€ », « 1 299,99 € » ou « 29€99 » en centimes.

    Lève ValueError si aucun montant positif n'est trouvé.
    """
    text = str(text).strip()
    if m := _EURO_CENTS.search(text):
        text = f"{m.group(1)},{m.group(2)}"

    match = _NUMBER.search(text)
    if not match:
        raise ValueError(f"Aucun montant dans « {text} ».")
    number = _SPACES.sub("", match.group(0))

    if "," in number and "." in number:
        decimal = "," if number.rfind(",") > number.rfind(".") else "."
    elif "," in number or "." in number:
        sep = "," if "," in number else "."
        integer_part, _, fraction = number.rpartition(sep)
        # Un seul séparateur suivi de 1 ou 2 chiffres = décimales, sinon séparateur de milliers
        decimal = sep if number.count(sep) == 1 and len(fraction) in (1, 2) else None
    else:
        decimal = None

    if decimal:
        thousands = "." if decimal == "," else ","
        integer_part, _, fraction = number.replace(thousands, "").partition(decimal)
    else:
        integer_part, fraction = number.replace(",", "").replace(".", ""), ""

    cents = int(integer_part or 0) * 100 + int((fraction + "00")[:2])
    if cents <= 0:
        raise ValueError("Le montant doit être positif.")
    return cents


def format_cents(cents: int, currency: str = "€") -> str:
    """1234567 -> « 12 345,67 € » (espace insécable fine comme séparateur de milliers)."""
    sign = "-" if cents < 0 else ""
    euros, rest = divmod(abs(cents), 100)
    grouped = f"{euros:,}".replace(",", " ")
    return f"{sign}{grouped},{rest:02d} {currency}"
