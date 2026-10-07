from datetime import date

import pytest

from jarvis.utils.periods import month_label, parse_day, parse_month

TODAY = date(2026, 10, 7)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, TODAY),
        ("hier", date(2026, 10, 6)),
        ("avant-hier", date(2026, 10, 5)),
        ("01/10", date(2026, 10, 1)),
        ("25/12", date(2025, 12, 25)),  # sans année et dans le futur → l'an dernier
        ("2026-09-30", date(2026, 9, 30)),
        ("15/08/25", date(2025, 8, 15)),
    ],
)
def test_parse_day(text, expected):
    assert parse_day(text, TODAY) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, "2026-10"),
        ("octobre", "2026-10"),
        ("décembre", "2025-12"),
        ("septembre 2024", "2024-09"),
        ("dernier", "2026-09"),
        ("2026-03", "2026-03"),
        ("3/2026", "2026-03"),
        ("03/26", "2026-03"),
    ],
)
def test_parse_month(text, expected):
    assert parse_month(text, TODAY) == expected


@pytest.mark.parametrize("text", ["blabla", "13/2026", "brumaire"])
def test_parse_month_invalid(text):
    with pytest.raises(ValueError):
        parse_month(text, TODAY)


def test_month_label():
    assert month_label("2026-08") == "août 2026"
