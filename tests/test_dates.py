from datetime import date, datetime, timedelta

import pytest

import utils.dates
from cogs.reminders import next_occurrence
from config import TIMEZONE
from utils.dates import add_months, month_label, parse_day, parse_month, parse_when

# Pour tous les tests, « maintenant » = mercredi 7 octobre 2026, 14h00
NOW = datetime(2026, 10, 7, 14, 0, tzinfo=TIMEZONE)


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch):
    monkeypatch.setattr(utils.dates, "now", lambda: NOW)


def at(year, month, day, hour=9, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=TIMEZONE)


# --- parse_when : durées -----------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("dans 10 min", NOW + timedelta(minutes=10)),
    ("dans 2h", NOW + timedelta(hours=2)),
    ("dans 1h30", NOW + timedelta(hours=1, minutes=30)),
    ("dans 2h 30min", NOW + timedelta(hours=2, minutes=30)),
    ("dans 3 jours", NOW + timedelta(days=3)),
    ("dans 1 jour et 2 heures", NOW + timedelta(days=1, hours=2)),
    ("+2 semaines", NOW + timedelta(weeks=2)),
    ("dans 1 mois", at(2026, 11, 7, 14)),
])
def test_durees(text, expected):
    assert parse_when(text) == expected


# --- parse_when : jours et heures ----------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("18h", at(2026, 10, 7, 18)),
    ("à 18h30", at(2026, 10, 7, 18, 30)),
    ("9h", at(2026, 10, 8, 9)),  # déjà passé aujourd'hui → demain
    ("midi", at(2026, 10, 8, 12)),
    ("ce soir", at(2026, 10, 7, 20)),
    ("demain", at(2026, 10, 8, 9)),
    ("demain 7h45", at(2026, 10, 8, 7, 45)),
    ("Après-demain à 14h", at(2026, 10, 9, 14)),
    ("vendredi 18h", at(2026, 10, 9, 18)),
    ("vendredi prochain", at(2026, 10, 9, 9)),
    ("lundi", at(2026, 10, 12, 9)),
    ("mercredi 10h", at(2026, 10, 14, 10)),  # aujourd'hui mais passé → semaine prochaine
    ("mercredi 16h", at(2026, 10, 7, 16)),  # aujourd'hui, pas encore passé
    ("25/12", at(2026, 12, 25, 9)),
    ("25/12 18h", at(2026, 12, 25, 18)),
    ("le 25/12/2027 à 8h", at(2027, 12, 25, 8)),
    ("25/12/27", at(2027, 12, 25, 9)),
    ("01/01", at(2027, 1, 1, 9)),
    ("2026-12-25 18:00", at(2026, 12, 25, 18)),
    ("25 décembre 10h", at(2026, 12, 25, 10)),
    ("1er janvier", at(2027, 1, 1, 9)),
    ("14 juillet 2027", at(2027, 7, 14, 9)),
])
def test_dates_et_heures(text, expected):
    assert parse_when(text) == expected


@pytest.mark.parametrize("text", ["", "n'importe quoi", "25h", "31/02", "dans", "01/01/2020", "35 blabla", "dans 3 lunes"])
def test_textes_refuses(text):
    with pytest.raises(ValueError):
        parse_when(text)


def test_add_months_reste_dans_le_mois():
    assert add_months(at(2026, 1, 31), 1) == at(2026, 2, 28)
    assert add_months(at(2026, 12, 15), 1) == at(2027, 1, 15)


# --- Rappels récurrents --------------------------------------------------------------------

def test_rappel_quotidien_saute_les_jours_manques():
    assert next_occurrence(at(2026, 10, 1), "quotidien", NOW) == at(2026, 10, 8)


def test_rappel_quotidien_garde_l_heure_au_changement_d_heure():
    # Passage à l'heure d'hiver le 25 octobre 2026
    due = at(2026, 10, 24)
    result = next_occurrence(due, "quotidien", due + timedelta(seconds=1))
    assert (result.day, result.hour) == (25, 9)
    assert result.utcoffset() != due.utcoffset()


def test_rappel_hebdomadaire():
    due = at(2026, 10, 7, 18)
    assert next_occurrence(due, "hebdo", due) == at(2026, 10, 14, 18)


def test_rappel_mensuel_fin_de_mois():
    due = at(2026, 1, 31)
    assert next_occurrence(due, "mensuel", due) == at(2026, 2, 28)
    assert next_occurrence(due, "mensuel", at(2026, 2, 28)) == at(2026, 3, 31)  # revient au 31


# --- Budget : jours et mois ------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    (None, date(2026, 10, 7)),
    ("hier", date(2026, 10, 6)),
    ("avant-hier", date(2026, 10, 5)),
    ("01/10", date(2026, 10, 1)),
    ("25/12", date(2025, 12, 25)),  # sans année et dans le futur → l'an dernier
    ("2026-09-30", date(2026, 9, 30)),
    ("15/08/25", date(2025, 8, 15)),
])
def test_parse_day(text, expected):
    assert parse_day(text) == expected


@pytest.mark.parametrize("text, expected", [
    (None, "2026-10"),
    ("octobre", "2026-10"),
    ("décembre", "2025-12"),
    ("septembre 2024", "2024-09"),
    ("dernier", "2026-09"),
    ("2026-03", "2026-03"),
    ("3/2026", "2026-03"),
    ("03/26", "2026-03"),
])
def test_parse_month(text, expected):
    assert parse_month(text) == expected


@pytest.mark.parametrize("text", ["blabla", "13/2026", "brumaire"])
def test_parse_month_refuse(text):
    with pytest.raises(ValueError):
        parse_month(text)


def test_month_label():
    assert month_label("2026-08") == "août 2026"
