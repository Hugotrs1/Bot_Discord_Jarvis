from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from jarvis.utils.timeparse import TimeParseError, add_months, parse_when

TZ = ZoneInfo("Europe/Paris")
# Mercredi 7 octobre 2026, 14h00
NOW = datetime(2026, 10, 7, 14, 0, tzinfo=TZ)


def at(year, month, day, hour=9, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=TZ)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("dans 10 min", NOW + timedelta(minutes=10)),
        ("dans 2h", NOW + timedelta(hours=2)),
        ("dans 1h30", NOW + timedelta(hours=1, minutes=30)),
        ("dans 2h 30min", NOW + timedelta(hours=2, minutes=30)),
        ("dans 3 jours", NOW + timedelta(days=3)),
        ("dans 1 jour et 2 heures", NOW + timedelta(days=1, hours=2)),
        ("+2 semaines", NOW + timedelta(weeks=2)),
        ("dans 1 mois", at(2026, 11, 7, 14)),
    ],
)
def test_relative(text, expected):
    assert parse_when(text, NOW) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("18h", at(2026, 10, 7, 18)),
        ("à 18h30", at(2026, 10, 7, 18, 30)),
        ("9h", at(2026, 10, 8, 9)),  # déjà passé aujourd'hui → demain
        ("midi", at(2026, 10, 8, 12)),
        ("ce soir", at(2026, 10, 7, 20)),
        ("demain", at(2026, 10, 8, 9)),
        ("demain 7h45", at(2026, 10, 8, 7, 45)),
        ("Après-demain à 14h", at(2026, 10, 9, 14)),
        ("vendredi 18h", at(2026, 10, 9, 18)),
        ("lundi", at(2026, 10, 12, 9)),
        ("mercredi 10h", at(2026, 10, 14, 10)),  # aujourd'hui mais passé → semaine prochaine
        ("mercredi 16h", at(2026, 10, 7, 16)),  # aujourd'hui, pas encore passé
        ("25/12", at(2026, 12, 25, 9)),
        ("25/12 18h", at(2026, 12, 25, 18)),
        ("le 25/12/2027 à 8h", at(2027, 12, 25, 8)),
        ("01/01", at(2027, 1, 1, 9)),
        ("2026-12-25 18:00", at(2026, 12, 25, 18)),
        ("25 décembre 10h", at(2026, 12, 25, 10)),
        ("1er janvier", at(2027, 1, 1, 9)),
    ],
)
def test_absolute(text, expected):
    assert parse_when(text, NOW) == expected


@pytest.mark.parametrize("text", ["", "n'importe quoi", "25h", "31/02", "dans", "01/01/2020", "35 blabla"])
def test_invalid(text):
    with pytest.raises(TimeParseError):
        parse_when(text, NOW)


def test_add_months_clamps_day():
    assert add_months(at(2026, 1, 31), 1) == at(2026, 2, 28)
    assert add_months(at(2026, 12, 15), 1) == at(2027, 1, 15)
