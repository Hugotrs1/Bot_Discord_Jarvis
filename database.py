"""Base de données SQLite : un simple fichier (data/jarvis.db), créé au premier lancement.

Conventions :
- les dates sont des « timestamps » Unix (nombre de secondes depuis 1970) ;
- les montants sont en centimes (1250 = 12,50 €) ;
- user_id est l'identifiant Discord de la personne à qui appartient la donnée.
"""

import os
import sqlite3

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,     -- salon où envoyer le rappel
    message     TEXT    NOT NULL,
    due_at      INTEGER NOT NULL,     -- quand l'envoyer
    repeat      TEXT                  -- NULL, 'quotidien', 'hebdo' ou 'mensuel'
);

CREATE TABLE IF NOT EXISTS todos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    text        TEXT    NOT NULL,
    priority    INTEGER NOT NULL DEFAULT 2,   -- 1 = haute, 2 = normale, 3 = basse
    due_at      INTEGER,                      -- échéance facultative
    done_at     INTEGER                       -- NULL tant que la tâche n'est pas faite
);

CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    kind        TEXT    NOT NULL CHECK (kind IN ('depense', 'revenu')),
    amount      INTEGER NOT NULL,     -- en centimes, toujours positif
    category    TEXT    NOT NULL,
    description TEXT,
    day         TEXT    NOT NULL      -- '2026-10-07'
);

CREATE TABLE IF NOT EXISTS budget_limits (
    user_id     INTEGER NOT NULL,
    category    TEXT    NOT NULL,
    amount      INTEGER NOT NULL,     -- plafond mensuel en centimes
    PRIMARY KEY (user_id, category)
);

CREATE TABLE IF NOT EXISTS price_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    name        TEXT    NOT NULL,
    target      INTEGER,              -- prix cible facultatif, en centimes
    UNIQUE (user_id, name)
);

-- Un article peut être suivi dans plusieurs boutiques : une ligne par boutique.
-- ON DELETE CASCADE : supprimer un article supprime aussi ses boutiques.
CREATE TABLE IF NOT EXISTS price_offers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     INTEGER NOT NULL REFERENCES price_items(id) ON DELETE CASCADE,
    url         TEXT    NOT NULL,
    selector    TEXT,                 -- sélecteur CSS du prix, si la détection automatique échoue
    price       INTEGER,              -- dernier prix lu
    lowest      INTEGER,              -- prix le plus bas jamais vu
    checked_at  INTEGER,
    error       TEXT                  -- dernière erreur de lecture, sinon NULL
);

-- Chaque changement de prix, pour garder un historique
CREATE TABLE IF NOT EXISTS price_history (
    offer_id    INTEGER NOT NULL REFERENCES price_offers(id) ON DELETE CASCADE,
    price       INTEGER NOT NULL,
    checked_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url         TEXT    NOT NULL UNIQUE,
    is_up       INTEGER,              -- 1 = en ligne, 0 = hors ligne, NULL = pas encore vérifié
    status      INTEGER,              -- dernier code HTTP
    response_ms INTEGER,
    checked_at  INTEGER,
    down_since  INTEGER
);

CREATE TABLE IF NOT EXISTS reading_list (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url         TEXT    NOT NULL,
    title       TEXT    NOT NULL,
    note        TEXT,
    message_id  INTEGER UNIQUE,       -- message Discord correspondant (pour la réaction ✅)
    added_at    INTEGER NOT NULL,
    read_at     INTEGER               -- NULL tant que l'article n'est pas lu
);
"""

# Crée le dossier « data » si besoin (sauf pour la base en mémoire des tests)
if DB_PATH != ":memory:":
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

connection = sqlite3.connect(DB_PATH)
connection.row_factory = sqlite3.Row  # permet d'écrire row["title"] au lieu de row[2]
connection.execute("PRAGMA foreign_keys = ON")  # active les ON DELETE CASCADE
connection.executescript(SCHEMA)


def query(sql: str, *params) -> list[sqlite3.Row]:
    """Exécute un SELECT et renvoie toutes les lignes."""
    return connection.execute(sql, params).fetchall()


def query_one(sql: str, *params) -> sqlite3.Row | None:
    """Exécute un SELECT et renvoie la première ligne (ou None s'il n'y en a pas)."""
    return connection.execute(sql, params).fetchone()


def execute(sql: str, *params) -> sqlite3.Cursor:
    """Exécute un INSERT, UPDATE ou DELETE et enregistre le changement.

    Le résultat donne notamment :
    - .lastrowid : l'id de la ligne qui vient d'être ajoutée ;
    - .rowcount  : le nombre de lignes modifiées ou supprimées.
    """
    cursor = connection.execute(sql, params)
    connection.commit()
    return cursor
