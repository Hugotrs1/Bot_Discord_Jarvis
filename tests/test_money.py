import pytest

from utils.money import format_euros, parse_amount


@pytest.mark.parametrize("text, cents", [
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
])
def test_parse_amount(text, cents):
    assert parse_amount(text) == cents


@pytest.mark.parametrize("text", ["", "gratuit", "0", "0,00"])
def test_parse_amount_refuse(text):
    with pytest.raises(ValueError):
        parse_amount(text)


def test_format_euros():
    assert format_euros(1250) == "12,50 €"
    assert format_euros(129999) == "1 299,99 €"
    assert format_euros(-500) == "-5,00 €"
    assert format_euros(5) == "0,05 €"
