"""Réglages du bot, lus dans le fichier .env (voir .env.example).

Seul DISCORD_TOKEN est obligatoire : tout le reste a une valeur par défaut.
"""

import os
from datetime import time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# Charge le fichier .env dans les variables d'environnement
load_dotenv()


def read_text(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def read_int(name: str, default: int = 0) -> int:
    value = read_text(name)
    if value == "":
        return default
    return int(value)


def read_float(name: str, default: float) -> float:
    value = read_text(name)
    if value == "":
        return default
    return float(value)


def read_time(name: str, default: str) -> time:
    """Lit une heure au format « HH:MM » (ex : « 07:30 »), dans le fuseau horaire choisi."""
    hours, minutes = read_text(name, default).split(":")
    return time(int(hours), int(minutes), tzinfo=TIMEZONE)


# --- Général ---------------------------------------------------------------------------------
TOKEN = read_text("DISCORD_TOKEN")
GUILD_ID = read_int("GUILD_ID")  # ton serveur : les commandes y apparaissent tout de suite
OWNER_ID = read_int("OWNER_ID")  # ton compte : si défini, toi seul peux utiliser le bot
TIMEZONE = ZoneInfo(read_text("TIMEZONE", "Europe/Paris"))
DB_PATH = read_text("DB_PATH", "data/jarvis.db")

# --- Briefing du matin -----------------------------------------------------------------------
BRIEF_CHANNEL_ID = read_int("BRIEF_CHANNEL_ID")
BRIEF_TIME = read_time("BRIEF_TIME", "07:30")
CITY = read_text("CITY", "Paris")
LATITUDE = read_float("LATITUDE", 48.8566)
LONGITUDE = read_float("LONGITUDE", 2.3522)

# --- Alertes (prix et monitoring) --------------------------------------------------------------
ALERTS_CHANNEL_ID = read_int("ALERTS_CHANNEL_ID")

# --- Suivi des prix -----------------------------------------------------------------------------
PRICE_CHECK_HOURS = read_int("PRICE_CHECK_HOURS", 6)
PRICE_RECAP_WEEKDAY = read_int("PRICE_RECAP_WEEKDAY", 0)  # 0 = lundi … 6 = dimanche, -1 = tous les jours
PRICE_RECAP_TIME = read_time("PRICE_RECAP_TIME", "09:00")

# --- Monitoring -------------------------------------------------------------------------------------
MONITOR_INTERVAL_MINUTES = read_int("MONITOR_INTERVAL_MINUTES", 5)
CPU_ALERT_PERCENT = read_float("CPU_ALERT_PERCENT", 90)
RAM_ALERT_PERCENT = read_float("RAM_ALERT_PERCENT", 90)
DISK_ALERT_PERCENT = read_float("DISK_ALERT_PERCENT", 90)

# --- Liste de lecture (« À lire plus tard ») ------------------------------------------------------
READING_CHANNEL_ID = read_int("READING_CHANNEL_ID")
READING_DIGEST_WEEKDAY = read_int("READING_DIGEST_WEEKDAY", 5)  # 5 = samedi
READING_DIGEST_TIME = read_time("READING_DIGEST_TIME", "10:00")
