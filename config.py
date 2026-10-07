"""Réglages du bot, lus dans le fichier .env."""

import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def env_int(name, default=0):
    value = os.getenv(name)
    return int(value) if value else default


TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = env_int("GUILD_ID")  # ton serveur Discord
OWNER_ID = env_int("OWNER_ID")  # ton compte : seul toi peux utiliser le bot

# Salons où le bot écrit tout seul
BRIEF_CHANNEL_ID = env_int("BRIEF_CHANNEL_ID")  # briefing du matin
ALERTS_CHANNEL_ID = env_int("ALERTS_CHANNEL_ID")  # baisses de prix, sites en panne…
READING_CHANNEL_ID = env_int("READING_CHANNEL_ID")  # liens envoyés par l'extension

# Ville pour la météo du briefing
CITY = os.getenv("CITY", "Paris")
LATITUDE = float(os.getenv("LATITUDE", "48.8566"))
LONGITUDE = float(os.getenv("LONGITUDE", "2.3522"))

TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Europe/Paris"))
DB_PATH = os.getenv("DB_PATH", "data/jarvis.db")
