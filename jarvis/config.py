"""Chargement de la configuration depuis les variables d'environnement (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


def _int(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name, "").strip()
    return int(value) if value else default


def _float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    return float(value) if value else default


def _time(name: str, default: str) -> time:
    raw = os.getenv(name, default).strip()
    hours, minutes = raw.split(":")
    return time(int(hours), int(minutes))


@dataclass(frozen=True)
class Config:
    token: str
    guild_id: int | None
    owner_id: int | None
    tz: ZoneInfo
    db_path: Path

    # Briefing du matin
    brief_channel_id: int | None
    brief_time: time
    latitude: float
    longitude: float
    city_name: str

    # Alertes (prix + monitoring)
    alerts_channel_id: int | None

    # Prix
    price_check_hours: int
    price_recap_weekday: int  # 0 = lundi
    price_recap_time: time

    # Monitoring
    monitor_interval_minutes: int
    cpu_alert: float
    ram_alert: float
    disk_alert: float

    # À lire plus tard
    readlater_channel_id: int | None
    readlater_digest_weekday: int
    readlater_digest_time: time

    @classmethod
    def from_env(cls) -> Config:
        load_dotenv()
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise SystemExit("DISCORD_TOKEN manquant : copie .env.example en .env et remplis-le.")

        return cls(
            token=token,
            guild_id=_int("GUILD_ID"),
            owner_id=_int("OWNER_ID"),
            tz=ZoneInfo(os.getenv("TIMEZONE", "Europe/Paris")),
            db_path=Path(os.getenv("DB_PATH", "data/jarvis.db")),
            brief_channel_id=_int("BRIEF_CHANNEL_ID"),
            brief_time=_time("BRIEF_TIME", "07:30"),
            latitude=_float("LATITUDE", 48.8566),
            longitude=_float("LONGITUDE", 2.3522),
            city_name=os.getenv("CITY_NAME", "Paris"),
            alerts_channel_id=_int("ALERTS_CHANNEL_ID"),
            price_check_hours=_int("PRICE_CHECK_HOURS", 6),
            price_recap_weekday=_int("PRICE_RECAP_WEEKDAY", 0),
            price_recap_time=_time("PRICE_RECAP_TIME", "09:00"),
            monitor_interval_minutes=_int("MONITOR_INTERVAL_MINUTES", 5),
            cpu_alert=_float("CPU_ALERT_PERCENT", 90),
            ram_alert=_float("RAM_ALERT_PERCENT", 90),
            disk_alert=_float("DISK_ALERT_PERCENT", 90),
            readlater_channel_id=_int("READLATER_CHANNEL_ID"),
            readlater_digest_weekday=_int("READLATER_DIGEST_WEEKDAY", 5),
            readlater_digest_time=_time("READLATER_DIGEST_TIME", "10:00"),
        )
