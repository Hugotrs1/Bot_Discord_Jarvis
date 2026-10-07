"""Parsing de jours et de mois passés (pour le budget)."""

from __future__ import annotations

import re
from datetime import date, timedelta

from jarvis.utils.timeparse import MONTHS, normalize

MONTH_NAMES = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def parse_day(text: str | None, today: date) -> date:
    """« hier », « avant-hier », « 12/10 », « 12/10/2026 », « 2026-10-12 » → date (passée ou du jour)."""
    if not text:
        return today
    text = normalize(text)
    if text in ("aujourdhui", "auj"):
        return today
    if text == "hier":
        return today - timedelta(days=1)
    if text in ("avant-hier", "avant hier"):
        return today - timedelta(days=2)

    if m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text):
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if m := re.fullmatch(r"(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2}|\d{4}))?", text):
        day, month = int(m.group(1)), int(m.group(2))
        if m.group(3):
            year = int(m.group(3))
            return date(year + 2000 if year < 100 else year, month, day)
        candidate = date(today.year, month, day)
        # Sans année, une date dans le futur désigne l'année dernière (on note des dépenses passées).
        return candidate if candidate <= today else date(today.year - 1, month, day)
    raise ValueError(f"Je ne comprends pas la date « {text} » (ex : hier, 12/10, 2026-10-12).")


def parse_month(text: str | None, today: date) -> str:
    """« 2026-10 », « 10/2026 », « octobre », « octobre 2025 », « dernier » → « AAAA-MM »."""
    if not text:
        return today.strftime("%Y-%m")
    text = normalize(text)
    if text in ("dernier", "precedent", "mois dernier"):
        previous = today.replace(day=1) - timedelta(days=1)
        return previous.strftime("%Y-%m")

    if m := re.fullmatch(r"(\d{4})-(\d{1,2})", text):
        year, month = int(m.group(1)), int(m.group(2))
    elif m := re.fullmatch(r"(\d{1,2})[/.](\d{2}|\d{4})", text):
        month, year = int(m.group(1)), int(m.group(2))
        year = year + 2000 if year < 100 else year
    elif m := re.fullmatch(r"([a-z]+)(?:\s+(\d{4}))?", text):
        if m.group(1) not in MONTHS:
            raise ValueError(f"Mois inconnu : « {text} ».")
        month = MONTHS[m.group(1)]
        # Sans année : le mois le plus récent qui n'est pas dans le futur.
        year = int(m.group(2)) if m.group(2) else (today.year if month <= today.month else today.year - 1)
    else:
        raise ValueError(f"Je ne comprends pas le mois « {text} » (ex : octobre, 10/2026, 2026-10).")

    if not 1 <= month <= 12:
        raise ValueError(f"Mois invalide : {month}.")
    return f"{year:04d}-{month:02d}"


def month_label(month: str) -> str:
    """« 2026-10 » → « octobre 2026 »."""
    year, number = month.split("-")
    return f"{MONTH_NAMES[int(number) - 1]} {year}"
