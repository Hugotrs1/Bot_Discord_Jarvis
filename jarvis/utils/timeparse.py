"""Parseur de dates en français pour les rappels et les échéances.

Formats acceptés (exemples) :
    dans 10 min · dans 2h · dans 1h30 · dans 3 jours · +2 semaines
    18h · à 18h30 · midi · ce soir
    demain · demain 9h · après-demain à 14h
    lundi · vendredi 18h
    25/12 · 25/12/2026 18h · 2026-12-25 18:00 · 25 décembre 9h
"""

from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date, datetime, time, timedelta

DEFAULT_TIME = time(9, 0)
EVENING_TIME = time(20, 0)

WEEKDAYS = {
    "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3,
    "vendredi": 4, "samedi": 5, "dimanche": 6,
}
MONTHS = {
    "janvier": 1, "janv": 1, "fevrier": 2, "fevr": 2, "fev": 2, "mars": 3,
    "avril": 4, "avr": 4, "mai": 5, "juin": 6, "juillet": 7, "juil": 7,
    "aout": 8, "septembre": 9, "sept": 9, "octobre": 10, "oct": 10,
    "novembre": 11, "nov": 11, "decembre": 12, "dec": 12,
}

DURATION_TOKEN = re.compile(
    r"(\d+)\s*(mois|semaines?|sem|jours?|j|heures?|h|minutes?|mins?|mn|m|secondes?|secs?|s)\b"
)
TIME_AT_END = re.compile(r"(?:^|\s)(?:a\s+)?(\d{1,2})\s*(?:h|:)\s*(\d{2})?$")
DATE_DMY = re.compile(r"^(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2}|\d{4}))?$")
DATE_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
DATE_DAY_MONTH = re.compile(r"^(\d{1,2})(?:er)?\s+([a-z]+)\.?(?:\s+(\d{4}))?$")


class TimeParseError(ValueError):
    pass


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("'", "").replace("’", "")
    return re.sub(r"\s+", " ", text).strip()


def add_months(dt: datetime, months: int) -> datetime:
    """Ajoute des mois en ramenant le jour au dernier jour du mois si besoin (31/01 + 1 mois = 28/02)."""
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def parse_duration(text: str) -> tuple[timedelta, int]:
    """Renvoie (durée, nombre de mois) pour un texte comme '1h30' ou '2 jours et 3h'."""
    text = re.sub(r"\bet\b|,", " ", text)
    # « 1h30 » : les minutes n'ont pas d'unité explicite
    text = re.sub(r"(\d+)\s*h\s*(\d+)\b(?!\s*[a-z])", r"\1h \2min", text)

    delta = timedelta()
    months = 0
    consumed = DURATION_TOKEN.sub("", text).strip(" ,")
    if consumed:
        raise TimeParseError(f"Je ne comprends pas la durée « {text} ».")

    matches = list(DURATION_TOKEN.finditer(text))
    if not matches:
        raise TimeParseError(f"Je ne comprends pas la durée « {text} ».")

    for match in matches:
        amount, unit = int(match.group(1)), match.group(2)
        if unit == "mois":
            months += amount
        elif unit.startswith("sem"):
            delta += timedelta(weeks=amount)
        elif unit.startswith("j"):
            delta += timedelta(days=amount)
        elif unit.startswith("h"):
            delta += timedelta(hours=amount)
        elif unit.startswith("m"):
            delta += timedelta(minutes=amount)
        else:
            delta += timedelta(seconds=amount)
    return delta, months


def _parse_date(text: str, today: date) -> date | None:
    """Renvoie la date décrite par `text` (sans heure), ou None si le texte est vide."""
    text = re.sub(r"^le\s+", "", text).strip()
    if not text:
        return None
    if text in ("aujourdhui", "auj"):
        return today
    if text == "demain":
        return today + timedelta(days=1)
    if text in ("apres-demain", "apres demain", "apresdemain"):
        return today + timedelta(days=2)

    weekday_name = text.removesuffix(" prochain").strip()
    if weekday_name in WEEKDAYS:
        days_ahead = (WEEKDAYS[weekday_name] - today.weekday()) % 7
        return today + timedelta(days=days_ahead)

    if m := DATE_ISO.match(text):
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    if m := DATE_DMY.match(text):
        day, month = int(m.group(1)), int(m.group(2))
        if m.group(3):
            year = int(m.group(3))
            year = year + 2000 if year < 100 else year
            return _safe_date(year, month, day)
        return _next_occurrence(day, month, today)

    if m := DATE_DAY_MONTH.match(text):
        day, month_name = int(m.group(1)), m.group(2)
        if month_name not in MONTHS:
            raise TimeParseError(f"Mois inconnu : « {month_name} ».")
        if m.group(3):
            return _safe_date(int(m.group(3)), MONTHS[month_name], day)
        return _next_occurrence(day, MONTHS[month_name], today)

    raise TimeParseError(f"Je ne comprends pas la date « {text} ».")


def _safe_date(year: int, month: int, day: int) -> date:
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise TimeParseError(f"Date invalide : {day:02d}/{month:02d}/{year}.") from exc


def _next_occurrence(day: int, month: int, today: date) -> date:
    candidate = _safe_date(today.year, month, day)
    return candidate if candidate >= today else _safe_date(today.year + 1, month, day)


def parse_when(text: str, now: datetime) -> datetime:
    """Convertit une expression française en datetime (dans le fuseau de `now`).

    `now` doit être un datetime avec fuseau horaire. Lève TimeParseError si le
    texte est incompréhensible ou désigne un moment passé.
    """
    raw = text
    text = normalize(text)
    if not text:
        raise TimeParseError("Il me faut une date ou une durée.")

    # Durée relative : « dans 2h », « +3 jours »
    if text.startswith("dans ") or text.startswith("+"):
        delta, months = parse_duration(text.removeprefix("dans ").lstrip("+ "))
        result = add_months(now, months) + delta
        if result <= now:
            raise TimeParseError("La durée doit être positive.")
        return result.replace(microsecond=0)

    default_time = DEFAULT_TIME
    if "ce soir" in text:
        text = text.replace("ce soir", "aujourdhui").strip()
        default_time = EVENING_TIME
    text = re.sub(r"\bmidi\b", "12h", text)

    # Heure en fin de texte : « 18h », « à 9h30 », « 18:00 »
    clock: time | None = None
    if m := TIME_AT_END.search(text):
        hours, minutes = int(m.group(1)), int(m.group(2) or 0)
        if hours > 23 or minutes > 59:
            raise TimeParseError(f"Heure invalide : {hours}h{minutes:02d}.")
        clock = time(hours, minutes)
        text = text[: m.start()].strip()

    text = re.sub(r"\s+a$", "", text).strip()
    day = _parse_date(text, now.date())

    if day is None:
        if clock is None:
            raise TimeParseError(f"Je ne comprends pas « {raw} ».")
        result = datetime.combine(now.date(), clock, tzinfo=now.tzinfo)
        if result <= now:
            result += timedelta(days=1)
        return result

    result = datetime.combine(day, clock or default_time, tzinfo=now.tzinfo)
    if result <= now:
        # « lundi » dit un lundi après l'heure : on vise la semaine suivante.
        if text.removesuffix(" prochain").strip() in WEEKDAYS:
            return result + timedelta(days=7)
        raise TimeParseError(f"« {raw} » est déjà passé.")
    return result
