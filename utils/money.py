"""Montants : tout est stocké en centimes (1250 = 12,50 €)."""

import re


def to_cents(text):
    """« 12,50 », « 12.5 € », « 1 299,99 € », « 1,299.99 » ou « 29€99 » → centimes."""
    text = str(text).replace(" ", " ").replace(" ", " ")
    text = re.sub(r"(\d)€(\d\d)\b", r"\1,\2", text)  # « 29€99 » → « 29,99 »

    match = re.search(r"\d[\d .,]*", text)
    if not match:
        raise ValueError(f"Aucun montant trouvé dans « {text} ».")
    number = match[0].replace(" ", "").rstrip(".,")

    # Les 1 ou 2 chiffres après le dernier « , » ou « . » sont les centimes ; le reste, les euros.
    match = re.fullmatch(r"([\d.,]*?)(?:[.,](\d{1,2}))?", number)
    euros = re.sub(r"\D", "", match[1]) or "0"
    cents = (match[2] or "0").ljust(2, "0")

    total = int(euros) * 100 + int(cents)
    if total <= 0:
        raise ValueError("Le montant doit être supérieur à zéro.")
    return total


def euros(cents):
    """129999 → « 1 299,99 € »"""
    return f"{cents / 100:,.2f} €".replace(",", " ").replace(".", ",")
