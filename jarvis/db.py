"""Accès SQLite asynchrone. Les dates sont stockées en timestamps Unix (UTC),
les montants en centimes pour éviter les erreurs d'arrondi."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,
    message     TEXT    NOT NULL,
    due_at      INTEGER NOT NULL,
    repeat      TEXT,
    created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_at);

CREATE TABLE IF NOT EXISTS todos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    text        TEXT    NOT NULL,
    priority    INTEGER NOT NULL DEFAULT 2,
    due_at      INTEGER,
    done_at     INTEGER,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    kind        TEXT    NOT NULL CHECK (kind IN ('depense', 'revenu')),
    amount_cents INTEGER NOT NULL,
    category    TEXT    NOT NULL,
    description TEXT,
    spent_on    TEXT    NOT NULL,
    created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transactions_month ON transactions(user_id, spent_on);

CREATE TABLE IF NOT EXISTS budget_limits (
    user_id     INTEGER NOT NULL,
    category    TEXT    NOT NULL,
    limit_cents INTEGER NOT NULL,
    PRIMARY KEY (user_id, category)
);

CREATE TABLE IF NOT EXISTS price_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    name         TEXT    NOT NULL,
    target_cents INTEGER,
    created_at   INTEGER NOT NULL,
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS price_offers (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id      INTEGER NOT NULL REFERENCES price_items(id) ON DELETE CASCADE,
    url          TEXT    NOT NULL,
    selector     TEXT,
    last_cents   INTEGER,
    lowest_cents INTEGER,
    last_checked INTEGER,
    last_error   TEXT
);

CREATE TABLE IF NOT EXISTS price_history (
    offer_id   INTEGER NOT NULL REFERENCES price_offers(id) ON DELETE CASCADE,
    cents      INTEGER NOT NULL,
    checked_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sites (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url          TEXT    NOT NULL UNIQUE,
    is_up        INTEGER,
    last_status  INTEGER,
    last_ms      INTEGER,
    last_checked INTEGER,
    down_since   INTEGER
);

CREATE TABLE IF NOT EXISTS readlater (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    url        TEXT    NOT NULL,
    title      TEXT    NOT NULL,
    note       TEXT,
    message_id INTEGER UNIQUE,
    added_at   INTEGER NOT NULL,
    read_at    INTEGER
);
"""


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path) if str(path) != ":memory:" else path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if isinstance(self.path, Path):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA foreign_keys = ON")
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        """Exécute une requête d'écriture et renvoie l'id de la dernière ligne insérée."""
        assert self.conn
        cursor = await self.conn.execute(sql, params)
        await self.conn.commit()
        return cursor.lastrowid or 0

    async def execute_rowcount(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        """Exécute une requête d'écriture et renvoie le nombre de lignes touchées."""
        assert self.conn
        cursor = await self.conn.execute(sql, params)
        await self.conn.commit()
        return cursor.rowcount

    async def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        assert self.conn
        async with self.conn.execute(sql, params) as cursor:
            return await cursor.fetchone()

    async def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        assert self.conn
        async with self.conn.execute(sql, params) as cursor:
            return list(await cursor.fetchall())
