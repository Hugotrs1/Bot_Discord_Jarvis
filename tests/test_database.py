import sqlite3

import pytest

from database import execute, query


def test_supprimer_un_article_supprime_ses_boutiques_et_son_historique():
    item_id = execute("INSERT INTO price_items (user_id, name) VALUES (1, 'Clavier')").lastrowid
    offer_id = execute("INSERT INTO price_offers (item_id, url) VALUES (?, 'https://x')", item_id).lastrowid
    execute("INSERT INTO price_history (offer_id, price, checked_at) VALUES (?, 100, 0)", offer_id)

    assert execute("DELETE FROM price_items WHERE id = ?", item_id).rowcount == 1
    assert query("SELECT * FROM price_offers WHERE item_id = ?", item_id) == []
    assert query("SELECT * FROM price_history WHERE offer_id = ?", offer_id) == []


def test_type_de_transaction_controle():
    with pytest.raises(sqlite3.IntegrityError):
        execute(
            "INSERT INTO transactions (user_id, kind, amount, category, day) "
            "VALUES (1, 'autre', 100, 'X', '2026-10-07')"
        )
