"""Base de données SQLite (un simple fichier, créé automatiquement au premier lancement)."""

import os
import sqlite3

from config import DB_PATH

os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row  # permet d'écrire row["titre"] au lieu de row[2]
db.execute("PRAGMA foreign_keys = ON")

# Dates : timestamps Unix. Montants : en centimes (évite les erreurs d'arrondi).
db.executescript("""
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    message TEXT,
    due_at INTEGER,
    repeat TEXT              -- NULL, 'jour', 'semaine' ou 'mois'
);
CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY,
    text TEXT,
    priority INTEGER,        -- 1 = haute, 2 = normale, 3 = basse
    due_at INTEGER,
    done INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    amount INTEGER,
    category TEXT,           -- 'Revenu' pour une rentrée d'argent
    description TEXT,
    day TEXT                 -- '2026-10-07'
);
CREATE TABLE IF NOT EXISTS budget_limits (
    category TEXT PRIMARY KEY,
    amount INTEGER
);
CREATE TABLE IF NOT EXISTS price_items (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE,
    target INTEGER
);
CREATE TABLE IF NOT EXISTS price_offers (
    id INTEGER PRIMARY KEY,
    item_id INTEGER REFERENCES price_items(id) ON DELETE CASCADE,
    url TEXT,
    selector TEXT,
    price INTEGER,
    lowest INTEGER,
    error TEXT
);
CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY,
    url TEXT UNIQUE,
    is_up INTEGER,
    status INTEGER,
    ms INTEGER,
    down_since INTEGER
);
CREATE TABLE IF NOT EXISTS reading_list (
    id INTEGER PRIMARY KEY,
    url TEXT,
    title TEXT,
    message_id INTEGER,
    added_at INTEGER,
    read INTEGER DEFAULT 0
);
""")


def query(sql, *params):
    """Renvoie toutes les lignes d'un SELECT."""
    return db.execute(sql, params).fetchall()


def query_one(sql, *params):
    """Renvoie la première ligne d'un SELECT (ou None)."""
    return db.execute(sql, params).fetchone()


def execute(sql, *params):
    """Exécute un INSERT / UPDATE / DELETE et l'enregistre."""
    cursor = db.execute(sql, params)
    db.commit()
    return cursor
