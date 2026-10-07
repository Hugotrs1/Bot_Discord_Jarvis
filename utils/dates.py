"""Comprendre les dates écrites en français.

Formats acceptés par parse_when() (pour les rappels et les échéances) :

    Durées        dans 10 min · dans 2h · dans 1h30 · dans 2h 30min · dans 3 jours
                  dans 1 jour et 2 heures · +2 semaines · dans 1 mois
    Heures        18h · à 18h30 · 18:00 · midi · ce soir
    Jours         aujourd'hui · demain · après-demain · lundi · vendredi prochain
    Dates         25/12 · 25/12/2026 · 25/12/26 · 2026-12-25 · 25 décembre · 1er janvier 2027
    Combinaisons  demain 9h · vendredi à 18h · le 25/12 à 14h30 · 2026-12-25 18:00

Les fonctions parse_day() et parse_month() servent au budget (dates passées).
"""

import calendar
import re
import unicodedata
from datetime import date, datetime, time, timedelta

from config import TIMEZONE

# Heure choisie quand on donne seulement un jour (« demain » = demain 9h)
DEFAULT_TIME = time(9, 0)
# Heure choisie pour « ce soir »
EVENING_TIME = time(20, 0)

# Les textes sont comparés sans accents (voir normalize), d'où « fevrier », « aout »…
WEEKDAYS = {
    "lundi": 0,
    "mardi": 1,
    "mercredi": 2,
    "jeudi": 3,
    "vendredi": 4,
    "samedi": 5,
    "dimanche": 6,
}
WEEKDAY_NAMES = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

MONTHS = {
    "janvier": 1, "janv": 1,
    "fevrier": 2, "fevr": 2, "fev": 2,
    "mars": 3,
    "avril": 4, "avr": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7, "juil": 7,
    "aout": 8,
    "septembre": 9, "sept": 9,
    "octobre": 10, "oct": 10,
    "novembre": 11, "nov": 11,
    "decembre": 12, "dec": 12,
}
MONTH_NAMES = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]

# Unités de durée acceptées → nom utilisé par timedelta (ou "months", traité à part)
DURATION_UNITS = {
    "s": "seconds", "sec": "seconds", "secs": "seconds", "seconde": "seconds", "secondes": "seconds",
    "m": "minutes", "mn": "minutes", "min": "minutes", "mins": "minutes", "minute": "minutes", "minutes": "minutes",
    "h": "hours", "heure": "hours", "heures": "hours",
    "j": "days", "jour": "days", "jours": "days",
    "sem": "weeks", "semaine": "weeks", "semaines": "weeks",
    "mois": "months",
}

EXAMPLES = "Exemples : dans 2h, demain 9h, vendredi 18h, 25/12 14h30, 25 décembre."


def now() -> datetime:
    """Date et heure actuelles, dans le fuseau horaire configuré."""
    return datetime.now(TIMEZONE)


def normalize(text: str) -> str:
    """Prépare un texte pour l'analyse : minuscules, sans accents, sans apostrophes.

    Exemple : « Après-demain à 9h » → « apres-demain a 9h »
    """
    text = text.lower().strip()
    # Sépare chaque lettre de son accent (« é » devient « e » + « ´ »), puis supprime les accents
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    without_apostrophes = without_accents.replace("'", "").replace("’", "")
    # Remplace les espaces multiples par un seul
    return re.sub(r"\s+", " ", without_apostrophes)


def add_months(moment: datetime, months: int) -> datetime:
    """Ajoute des mois à une date.

    Si le jour n'existe pas dans le mois d'arrivée, on prend le dernier jour du mois :
    31 janvier + 1 mois = 28 février.
    """
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    last_day_of_month = calendar.monthrange(year, month)[1]
    day = min(moment.day, last_day_of_month)
    return moment.replace(year=year, month=month, day=day)


def make_date(year: int, month: int, day: int) -> date:
    """Comme date(), mais avec un message d'erreur en français."""
    try:
        return date(year, month, day)
    except ValueError:
        raise ValueError(f"La date {day:02d}/{month:02d}/{year} n'existe pas.") from None


def full_year(year: int) -> int:
    """Une année écrite sur 2 chiffres (« 26 ») devient « 2026 »."""
    if year < 100:
        return year + 2000
    return year


# --- Durées : « dans 2h 30min » ---------------------------------------------------------------

def parse_duration(text: str) -> tuple[timedelta, int]:
    """Analyse une durée. Renvoie (durée, nombre de mois).

    Les mois sont renvoyés à part car ils n'ont pas tous la même longueur.
    Exemples : « 2h 30min » → (2h30, 0) ; « 1 mois et 2 jours » → (2 jours, 1)
    """
    # « 1 jour et 2 heures », « 1 jour, 2 heures » → « 1 jour  2 heures »
    text = re.sub(r"\bet\b|,", " ", text)

    # « 1h30 » : les minutes n'ont pas d'unité, on l'ajoute → « 1h 30min ».
    # (On ne le fait pas si une unité suit déjà le nombre, comme dans « 2h 30min ».)
    text = re.sub(r"(\d+)\s*h\s*(\d+)\b(?!\s*[a-z])", r"\1h \2min", text)

    # On découpe en morceaux « nombre + unité » : « 2h 30min » → [("2", "h"), ("30", "min")]
    pieces = re.findall(r"(\d+)\s*([a-z]+)", text)
    leftover = re.sub(r"(\d+)\s*([a-z]+)", "", text).strip()
    if not pieces or leftover:
        raise ValueError(f"Je ne comprends pas la durée « {text.strip()} ». {EXAMPLES}")

    duration = timedelta()
    months = 0
    for number, unit_text in pieces:
        unit = DURATION_UNITS.get(unit_text)
        if unit is None:
            raise ValueError(f"Unité de durée inconnue : « {unit_text} ».")
        if unit == "months":
            months += int(number)
        else:
            # timedelta(hours=2), timedelta(days=3)…
            duration += timedelta(**{unit: int(number)})
    return duration, months


# --- Heure : « 18h », « à 18h30 », « 18:00 » --------------------------------------------------

def extract_time(text: str) -> tuple[time | None, str]:
    """Cherche une heure à la fin du texte.

    Renvoie (heure trouvée ou None, reste du texte).
    Exemple : « demain a 18h30 » → (18:30, « demain »)
    """
    # (début ou espace) + « a » facultatif + heures + « h » ou « : » + minutes facultatives, en fin de texte
    match = re.search(r"(?:^|\s)(?:a\s+)?(\d{1,2})\s*(?:h|:)\s*(\d{2})?$", text)
    if match is None:
        return None, text

    hours = int(match.group(1))
    minutes = int(match.group(2) or 0)
    if hours > 23 or minutes > 59:
        raise ValueError(f"Heure invalide : {hours}h{minutes:02d}.")

    remaining_text = text[: match.start()].strip()
    return time(hours, minutes), remaining_text


# --- Jour : « demain », « vendredi », « 25/12 », « 25 décembre »… -----------------------------

def parse_day_words(text: str, today: date) -> date | None:
    """Transforme la partie « jour » du texte en date.

    Renvoie None si le texte est vide (seule une heure a été donnée).
    """
    text = text.removeprefix("le ").strip()

    if text == "":
        return None
    if text in ("aujourdhui", "auj"):
        return today
    if text == "demain":
        return today + timedelta(days=1)
    if text in ("apres-demain", "apres demain", "apresdemain"):
        return today + timedelta(days=2)

    # « vendredi » ou « vendredi prochain » : le prochain vendredi (aujourd'hui compris)
    weekday_name = text.removesuffix(" prochain")
    if weekday_name in WEEKDAYS:
        days_until = (WEEKDAYS[weekday_name] - today.weekday()) % 7
        return today + timedelta(days=days_until)

    # « 2026-12-25 » (format ISO)
    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match:
        return make_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))

    # « 25/12 », « 25/12/2026 », « 25/12/26 » (ou avec des points : « 25.12 »)
    match = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2}|\d{4}))?", text)
    if match:
        day, month, year_text = int(match.group(1)), int(match.group(2)), match.group(3)
        if year_text:
            return make_date(full_year(int(year_text)), month, day)
        return next_date_with(day, month, today)

    # « 25 decembre », « 1er janvier », « 14 juillet 2027 »
    match = re.fullmatch(r"(\d{1,2})(?:er)?\s+([a-z]+)\.?(?:\s+(\d{4}))?", text)
    if match:
        day, month_name, year_text = int(match.group(1)), match.group(2), match.group(3)
        if month_name not in MONTHS:
            raise ValueError(f"Mois inconnu : « {month_name} ».")
        if year_text:
            return make_date(int(year_text), MONTHS[month_name], day)
        return next_date_with(day, MONTHS[month_name], today)

    raise ValueError(f"Je ne comprends pas la date « {text} ». {EXAMPLES}")


def next_date_with(day: int, month: int, today: date) -> date:
    """Prochaine date future avec ce jour et ce mois : « 01/01 » en octobre = 1er janvier de l'an prochain."""
    this_year = make_date(today.year, month, day)
    if this_year >= today:
        return this_year
    return make_date(today.year + 1, month, day)


# --- Fonction principale --------------------------------------------------------------------

def parse_when(text: str, current: datetime | None = None) -> datetime:
    """Transforme une expression en français en date et heure futures.

    `current` est le moment présent (utile pour les tests) ; par défaut, maintenant.
    Lève ValueError avec un message clair si le texte n'est pas compris ou est déjà passé.
    """
    if current is None:
        current = now()
    original_text = text
    text = normalize(text)
    if text == "":
        raise ValueError(f"Il me faut une date ou une durée. {EXAMPLES}")

    # 1. Durée relative : « dans 2h », « +3 jours »
    if text.startswith("dans ") or text.startswith("+"):
        duration_text = text.removeprefix("dans ").removeprefix("+").strip()
        duration, months = parse_duration(duration_text)
        result = add_months(current, months) + duration
        if result <= current:
            raise ValueError("La durée doit être positive.")
        return result.replace(microsecond=0)

    # 2. Mots spéciaux
    default_time = DEFAULT_TIME
    if "ce soir" in text:
        text = text.replace("ce soir", "aujourdhui")
        default_time = EVENING_TIME
    text = re.sub(r"\bmidi\b", "12h", text)

    # 3. On sépare l'heure (à la fin) du jour (au début)
    time_of_day, day_text = extract_time(text)
    day_text = day_text.removesuffix(" a").strip()  # « demain a » (le « à » de « demain à 9h »)
    day = parse_day_words(day_text, current.date())

    # 4a. Seulement une heure (« 18h ») : aujourd'hui, ou demain si l'heure est passée
    if day is None:
        if time_of_day is None:
            raise ValueError(f"Je ne comprends pas « {original_text} ». {EXAMPLES}")
        result = datetime.combine(current.date(), time_of_day, tzinfo=TIMEZONE)
        if result <= current:
            result = result + timedelta(days=1)
        return result

    # 4b. Un jour, avec ou sans heure
    result = datetime.combine(day, time_of_day or default_time, tzinfo=TIMEZONE)
    if result <= current:
        # « mercredi 10h » dit un mercredi à 14h : on parle de mercredi prochain
        if day_text.removesuffix(" prochain") in WEEKDAYS:
            return result + timedelta(days=7)
        raise ValueError(f"« {original_text} » est déjà passé.")
    return result


# --- Pour le budget : jours et mois passés ------------------------------------------------------

def parse_day(text: str | None) -> date:
    """Jour d'une dépense. Vide = aujourd'hui.

    Accepte : « hier », « avant-hier », « 12/10 », « 12/10/2026 », « 12/10/26 », « 2026-10-12 ».
    Sans année, une date future désigne l'année dernière (on note des dépenses déjà faites).
    """
    today = now().date()
    if not text:
        return today
    text = normalize(text)

    if text in ("aujourdhui", "auj"):
        return today
    if text == "hier":
        return today - timedelta(days=1)
    if text in ("avant-hier", "avant hier"):
        return today - timedelta(days=2)

    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match:
        return make_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))

    match = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2}|\d{4}))?", text)
    if match:
        day, month, year_text = int(match.group(1)), int(match.group(2)), match.group(3)
        if year_text:
            return make_date(full_year(int(year_text)), month, day)
        this_year = make_date(today.year, month, day)
        if this_year <= today:
            return this_year
        return make_date(today.year - 1, month, day)

    raise ValueError(f"Je ne comprends pas la date « {text} ». Exemples : hier, 12/10, 2026-10-12.")


def parse_month(text: str | None) -> str:
    """Mois au format « AAAA-MM ». Vide = mois en cours.

    Accepte : « octobre », « octobre 2025 », « 10/2026 », « 10/26 », « 2026-10 », « dernier ».
    Un nom de mois sans année désigne le plus récent qui n'est pas dans le futur.
    """
    today = now().date()
    if not text:
        return today.strftime("%Y-%m")
    text = normalize(text)

    if text in ("dernier", "precedent", "mois dernier"):
        last_day_of_previous_month = today.replace(day=1) - timedelta(days=1)
        return last_day_of_previous_month.strftime("%Y-%m")

    match_iso = re.fullmatch(r"(\d{4})-(\d{1,2})", text)
    match_slash = re.fullmatch(r"(\d{1,2})[/.](\d{2}|\d{4})", text)
    match_name = re.fullmatch(r"([a-z]+)(?:\s+(\d{4}))?", text)

    if match_iso:
        year, month = int(match_iso.group(1)), int(match_iso.group(2))
    elif match_slash:
        month, year = int(match_slash.group(1)), full_year(int(match_slash.group(2)))
    elif match_name:
        month_name, year_text = match_name.group(1), match_name.group(2)
        if month_name not in MONTHS:
            raise ValueError(f"Mois inconnu : « {text} ».")
        month = MONTHS[month_name]
        if year_text:
            year = int(year_text)
        elif month <= today.month:
            year = today.year
        else:
            year = today.year - 1
    else:
        raise ValueError(f"Je ne comprends pas le mois « {text} ». Exemples : octobre, 10/2026, dernier.")

    if not 1 <= month <= 12:
        raise ValueError(f"Mois invalide : {month}.")
    return f"{year:04d}-{month:02d}"


def month_label(month: str) -> str:
    """« 2026-10 » → « octobre 2026 »"""
    year, month_number = month.split("-")
    return f"{MONTH_NAMES[int(month_number) - 1]} {year}"
