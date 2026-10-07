from datetime import date, datetime, timedelta

import pytest

from cogs.reminders import next_date
from config import TIMEZONE
from utils.dates import add_one_month, parse_when

# Mercredi 7 octobre 2026, 14h00
NOW = datetime(2026, 10, 7, 14, 0, tzinfo=TIMEZONE)


def at(day, month, hour=9, minute=0, year=2026):
    return datetime(year, month, day, hour, minute, tzinfo=TIMEZONE)


@pytest.mark.parametrize("text, expected", [
    ("dans 10 min", NOW + timedelta(minutes=10)),
    ("dans 2h", NOW + timedelta(hours=2)),
    ("dans 3 jours", NOW + timedelta(days=3)),
    ("dans 1 semaine", NOW + timedelta(weeks=1)),
    ("18h", at(7, 10, 18)),
    ("à 18h30", at(7, 10, 18, 30)),
    ("9h", at(8, 10, 9)),  # déjà passé aujourd'hui → demain
    ("demain", at(8, 10)),
    ("demain à 7h45", at(8, 10, 7, 45)),
    ("après-demain 14h", at(9, 10, 14)),
    ("vendredi 18h", at(9, 10, 18)),
    ("mercredi", at(14, 10)),  # on est mercredi → la semaine prochaine
    ("25/12", at(25, 12)),
    ("25/12 18:00", at(25, 12, 18)),
    ("01/01", at(1, 1, year=2027)),
    ("15/03/2027 8h", at(15, 3, 8, year=2027)),
])
def test_parse_when(text, expected):
    assert parse_when(text, NOW) == expected


@pytest.mark.parametrize("text", ["", "n'importe quoi", "25h", "31/02", "01/01/2020"])
def test_parse_when_refuse(text):
    with pytest.raises(ValueError):
        parse_when(text, NOW)


def test_rappels_recurrents():
    assert next_date(at(7, 10), "jour") == at(8, 10)
    assert next_date(at(7, 10), "semaine") == at(14, 10)
    assert next_date(at(31, 1), "mois") == at(28, 2)
    assert add_one_month(at(15, 12)) == at(15, 1, year=2027)


def test_rappel_quotidien_garde_l_heure_au_changement_d_heure():
    # Passage à l'heure d'hiver le 25 octobre 2026 : le rappel doit rester à 9h
    assert next_date(at(24, 10), "jour").hour == 9
    assert next_date(at(24, 10), "jour").date() == date(2026, 10, 25)
