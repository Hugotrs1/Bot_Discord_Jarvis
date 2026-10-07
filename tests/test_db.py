import pytest

from jarvis.db import Database


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


async def test_schema_and_cascade(db):
    item_id = await db.execute(
        "INSERT INTO price_items (user_id, name, created_at) VALUES (1, 'Clavier', 0)"
    )
    offer_id = await db.execute("INSERT INTO price_offers (item_id, url) VALUES (?, 'https://x')", (item_id,))
    await db.execute("INSERT INTO price_history (offer_id, cents, checked_at) VALUES (?, 100, 0)", (offer_id,))

    assert await db.execute_rowcount("DELETE FROM price_items WHERE id = ?", (item_id,)) == 1
    assert await db.fetchall("SELECT * FROM price_offers") == []
    assert await db.fetchall("SELECT * FROM price_history") == []


async def test_transactions_kind_constraint(db):
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        await db.execute(
            "INSERT INTO transactions (user_id, kind, amount_cents, category, spent_on, created_at) "
            "VALUES (1, 'autre', 100, 'X', '2026-10-07', 0)"
        )
