"""Conversion entre texte et montants.

Tous les montants sont stockés en centimes (nombres entiers) : 12,50 € → 1250.
Ça évite les erreurs d'arrondi des nombres à virgule (0.1 + 0.2 = 0.30000000000000004).
"""

import re

# Espaces « spéciales » que les sites utilisent souvent dans les prix (« 1 299 € »)
NON_BREAKING_SPACES = [" ", " "]


def parse_amount(text: str) -> int:
    """Trouve un montant dans un texte et le renvoie en centimes.

    Exemples :
        « 12 »                 → 1200
        « 12,50 » ou « 12.5 €» → 1250
        « 1 299,99 € »         → 129999
        « 1.299,99 » (format européen) ou « 1,299.99 » (format anglais) → 129999
        « 1.299 »              → 129900 (le point sépare ici les milliers)
        « 29€99 »              → 2999
        « Prix : 129,99 € 15 avis » → 12999 (on prend le premier nombre)

    Lève ValueError si aucun montant positif n'est trouvé.
    """
    text = str(text)
    for space in NON_BREAKING_SPACES:
        text = text.replace(space, " ")

    # Cas « 29€99 » (centimes après le symbole €) → « 29,99 ».
    # Le nombre ne doit pas suivre un chiffre, une virgule ou un point,
    # pour ne pas confondre avec « 129,99 € 15 avis ».
    euro_in_middle = re.search(r"(?<![\d,.])(\d[\d .]*)€(\d{2})\b", text)
    if euro_in_middle:
        text = euro_in_middle.group(1) + "," + euro_in_middle.group(2)

    # Le premier nombre du texte, avec ses espaces, points et virgules : « 1 299,99 »
    number_match = re.search(r"\d[\d .,]*\d|\d", text)
    if number_match is None:
        raise ValueError(f"Aucun montant trouvé dans « {text} ».")
    number = number_match.group(0).replace(" ", "")

    decimal_separator = find_decimal_separator(number)
    if decimal_separator is None:
        # Pas de centimes : on garde seulement les chiffres (« 1.299 » → « 1299 »)
        euros = re.sub(r"\D", "", number)
        cents = "00"
    else:
        euros_part, cents_part = number.rsplit(decimal_separator, 1)
        euros = re.sub(r"\D", "", euros_part)  # enlève les séparateurs de milliers
        cents = (cents_part + "0")[:2]  # « 5 » → « 50 »

    total = int(euros or "0") * 100 + int(cents)
    if total <= 0:
        raise ValueError("Le montant doit être supérieur à zéro.")
    return total


def find_decimal_separator(number: str) -> str | None:
    """Devine si les centimes sont séparés par « , » ou « . » (ou s'il n'y en a pas).

    - « 1.299,99 » : les deux sont présents → le dernier sépare les centimes (« , »)
    - « 12,5 »     : un seul séparateur suivi de 1 ou 2 chiffres → ce sont des centimes
    - « 1.299 »    : un seul séparateur suivi de 3 chiffres → séparateur de milliers
    """
    has_comma = "," in number
    has_dot = "." in number

    if has_comma and has_dot:
        if number.rfind(",") > number.rfind("."):
            return ","
        return "."

    if has_comma or has_dot:
        separator = "," if has_comma else "."
        digits_after = number.rsplit(separator, 1)[1]
        if number.count(separator) == 1 and len(digits_after) in (1, 2):
            return separator
    return None


def format_euros(cents: int) -> str:
    """129999 → « 1 299,99 € » ; -500 → « -5,00 € »"""
    sign = "-" if cents < 0 else ""
    euros, rest = divmod(abs(cents), 100)
    euros_with_spaces = f"{euros:,}".replace(",", " ")  # 1,299 → 1 299 (espace fine)
    return f"{sign}{euros_with_spaces},{rest:02d} €"
