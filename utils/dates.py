"""Comprendre les dates écrites en français : « dans 2h », « demain 9h », « vendredi 18h », « 25/12 »…"""

import calendar
import re
from datetime import date, datetime, time, timedelta

from config import TIMEZONE

WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin",
          "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

EXAMPLES = "Exemples : dans 10 min, dans 2h, demain 9h, vendredi 18h, 25/12 14h30"


def now():
    return datetime.now(TIMEZONE)


def parse_when(text, current=None):
    """Transforme un texte en date future. Lève ValueError si le texte n'est pas compris."""
    current = current or now()
    text = text.lower().strip()

    # 1. Durée : « dans 10 min », « dans 2h », « dans 3 jours », « dans 1 semaine »
    match = re.fullmatch(r"dans (\d+) ?(min|minutes?|h|heures?|j|jours?|semaines?)", text)
    if match:
        number, unit = int(match[1]), match[2]
        if unit.startswith("min"):
            return current + timedelta(minutes=number)
        if unit.startswith("h"):
            return current + timedelta(hours=number)
        if unit.startswith("j"):
            return current + timedelta(days=number)
        return current + timedelta(weeks=number)

    # 2. Heure à la fin : « 18h », « 18h30 », « 18:30 » (9h par défaut)
    hour, minute = 9, 0
    has_time = False
    match = re.search(r"(\d{1,2}) ?[h:] ?(\d{2})?$", text)
    if match:
        hour, minute = int(match[1]), int(match[2] or 0)
        has_time = True
        text = text[:match.start()].strip()
    text = text.removesuffix("à").strip()  # « demain à 9h »

    # 3. Jour : aujourd'hui, demain, un jour de la semaine ou une date « 25/12 »
    today = current.date()
    if text in ("", "aujourd'hui"):
        if not has_time:
            raise ValueError(f"Je ne comprends pas cette date. {EXAMPLES}")
        day = today
    elif text == "demain":
        day = today + timedelta(days=1)
    elif text in ("après-demain", "apres-demain"):
        day = today + timedelta(days=2)
    elif text in WEEKDAYS:
        days_ahead = (WEEKDAYS.index(text) - today.weekday()) % 7 or 7  # toujours dans le futur
        day = today + timedelta(days=days_ahead)
    elif match := re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?", text):
        day = make_date(int(match[3] or today.year), int(match[2]), int(match[1]))
        if day < today and not match[3]:  # « 01/01 » en octobre = l'année prochaine
            day = day.replace(year=today.year + 1)
    else:
        raise ValueError(f"Je ne comprends pas cette date. {EXAMPLES}")

    if hour > 23 or minute > 59:
        raise ValueError(f"Heure invalide : {hour}h{minute:02d}.")
    result = datetime.combine(day, time(hour, minute), tzinfo=TIMEZONE)

    if result <= current:
        if text in ("", "aujourd'hui"):  # « 9h » alors qu'il est 14h → demain 9h
            return result + timedelta(days=1)
        raise ValueError("Cette date est déjà passée.")
    return result


def make_date(year, month, day):
    try:
        return date(year, month, day)
    except ValueError:
        raise ValueError(f"La date {day:02d}/{month:02d}/{year} n'existe pas.") from None


def add_one_month(moment):
    """31 janvier + 1 mois = 28 février (on s'arrête au dernier jour du mois)."""
    year, month = (moment.year + 1, 1) if moment.month == 12 else (moment.year, moment.month + 1)
    last_day = calendar.monthrange(year, month)[1]
    return moment.replace(year=year, month=month, day=min(moment.day, last_day))


def parse_day(text):
    """Jour d'une dépense : vide = aujourd'hui, « hier », « avant-hier » ou « 12/10 »."""
    today = now().date()
    text = (text or "").lower().strip()
    if text in ("", "aujourd'hui"):
        return today
    if text == "hier":
        return today - timedelta(days=1)
    if text in ("avant-hier", "avant hier"):
        return today - timedelta(days=2)
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?", text)
    if not match:
        raise ValueError("Date non comprise. Exemples : hier, 12/10, 12/10/2026")
    return make_date(int(match[3] or today.year), int(match[2]), int(match[1]))


def parse_month(text):
    """Mois au format « 2026-10 » : vide = mois en cours, « octobre » ou « 10/2026 »."""
    today = now().date()
    text = (text or "").lower().strip()
    if text == "":
        return today.strftime("%Y-%m")
    if text in MONTHS:
        month = MONTHS.index(text) + 1
        year = today.year if month <= today.month else today.year - 1  # le dernier mois écoulé
        return f"{year}-{month:02d}"
    match = re.fullmatch(r"(\d{1,2})/(\d{4})", text)
    if match and 1 <= int(match[1]) <= 12:
        return f"{match[2]}-{int(match[1]):02d}"
    raise ValueError("Mois non compris. Exemples : octobre, 10/2026")


def month_name(month):
    """« 2026-10 » → « octobre 2026 »"""
    year, number = month.split("-")
    return f"{MONTHS[int(number) - 1]} {year}"
