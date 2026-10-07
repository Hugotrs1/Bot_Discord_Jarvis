import pytest

from jarvis.utils.money import format_cents, parse_amount


@pytest.mark.parametrize(
    ("text", "cents"),
    [
        ("12", 1200),
        ("12,50", 1250),
        ("12.5", 1250),
        ("12.5€", 1250),
        ("1 299,99 €", 129999),
        ("1 299,99 €", 129999),
        ("€1,299.99", 129999),
        ("1.299,99", 129999),
        ("1.299", 129900),
        ("29€99", 2999),
        ("Prix : 129,99 € 15 avis", 12999),
        ("0,99", 99),
    ],
)
def test_parse_amount(text, cents):
    assert parse_amount(text) == cents


@pytest.mark.parametrize("text", ["", "gratuit", "0", "0,00"])
def test_parse_amount_invalid(text):
    with pytest.raises(ValueError):
        parse_amount(text)


def test_format_cents():
    assert format_cents(1250) == "12,50 €"
    assert format_cents(129999) == "1 299,99 €"
    assert format_cents(-500) == "-5,00 €"
    assert format_cents(5) == "0,05 €"
