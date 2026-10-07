"""Monitoring de la machine et de sites web.

Commandes : /status, /site ajouter, /site liste, /site supprimer

Toutes les MONITOR_INTERVAL_MINUTES minutes, le bot :
- alerte si le CPU, la RAM ou le disque dépasse son seuil (au plus une fois par heure) ;
- teste chaque site surveillé et alerte quand il tombe ou revient en ligne.
"""

import asyncio
import logging
import os
import sqlite3
import time

import discord
import psutil
from discord import app_commands
from discord.ext import commands, tasks

import config
from database import execute, query
from utils.dates import now
from utils.discord_helpers import find_channel, owner_mention, timestamp
from utils.web import check_website

log = logging.getLogger(__name__)

SECONDS_BETWEEN_ALERTS = 3600  # pas plus d'une alerte par heure pour la même ressource
SECONDS_BEFORE_CONFIRMING = 5  # un site en panne est retesté une fois avant d'alerter


# --- Mise en forme ----------------------------------------------------------------------------

def usage_bar(percent: float, width: int = 12) -> str:
    """usage_bar(50) → « ██████░░░░░░ »"""
    filled = round(percent / 100 * width)
    return "█" * filled + "░" * (width - filled)


def format_duration(seconds: float) -> str:
    """93784 → « 1 j 2 h 3 min »"""
    days, rest = divmod(int(seconds), 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    parts = []
    if days:
        parts.append(f"{days} j")
    if hours:
        parts.append(f"{hours} h")
    parts.append(f"{minutes} min")
    return " ".join(parts)


def format_size(size_in_bytes: float) -> str:
    """1536 → « 1.5 Ko »"""
    size = float(size_in_bytes)
    for unit in ["o", "Ko", "Mo", "Go", "To"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size = size / 1024
    return f"{size:.1f} Po"


# --- Mesures de la machine --------------------------------------------------------------------

def read_system_stats() -> dict:
    """Mesure l'état de la machine.

    Attention : la mesure du CPU dure 1 seconde. On appelle donc cette fonction
    avec asyncio.to_thread() pour ne pas bloquer le bot pendant ce temps.
    """
    disk_root = os.path.abspath(os.sep)  # « C:\\ » sous Windows, « / » sous Linux
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(disk_root)

    stats = {
        "cpu": psutil.cpu_percent(interval=1),
        "ram": memory.percent,
        "ram_used": memory.used,
        "ram_total": memory.total,
        "disk": disk.percent,
        "disk_free": disk.free,
        "disk_root": disk_root,
        "uptime": time.time() - psutil.boot_time(),
        "temperature": read_temperature(),
    }
    return stats


def read_temperature() -> float | None:
    """Température la plus haute des capteurs (disponible seulement sous Linux, ex : Raspberry Pi)."""
    if not hasattr(psutil, "sensors_temperatures"):
        return None
    sensors = psutil.sensors_temperatures() or {}
    readings = []
    for sensor_entries in sensors.values():
        for entry in sensor_entries:
            if entry.current:
                readings.append(entry.current)
    if not readings:
        return None
    return max(readings)


class Monitoring(commands.Cog):
    site = app_commands.Group(name="site", description="Surveiller la disponibilité de sites web")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot_started_at = time.time()
        self.last_alert_time = {}  # {"cpu": heure de la dernière alerte, ...}
        self.watch.start()

    async def send_alert(self, title: str, description: str, color: discord.Color):
        channel = await find_channel(self.bot, config.ALERTS_CHANNEL_ID)
        if channel is None:
            return
        embed = discord.Embed(title=title, description=description, color=color)
        await channel.send(content=owner_mention(), embed=embed)

    # --- /status -----------------------------------------------------------------------------

    @app_commands.command(name="status", description="État de la machine qui fait tourner le bot")
    async def status(self, interaction: discord.Interaction):
        await interaction.response.defer()
        stats = await asyncio.to_thread(read_system_stats)

        embed = discord.Embed(title="🖥️ État du serveur", color=discord.Color.dark_teal())
        embed.add_field(name="CPU", value=f"`{usage_bar(stats['cpu'])}` {stats['cpu']:.0f} %", inline=False)
        embed.add_field(
            name="RAM",
            value=(
                f"`{usage_bar(stats['ram'])}` {stats['ram']:.0f} % "
                f"({format_size(stats['ram_used'])} / {format_size(stats['ram_total'])})"
            ),
            inline=False,
        )
        embed.add_field(
            name=f"Disque ({stats['disk_root']})",
            value=f"`{usage_bar(stats['disk'])}` {stats['disk']:.0f} % · {format_size(stats['disk_free'])} libres",
            inline=False,
        )
        if stats["temperature"] is not None:
            embed.add_field(name="Température", value=f"🌡️ {stats['temperature']:.0f}°C")
        embed.add_field(name="Machine allumée depuis", value=format_duration(stats["uptime"]))
        embed.add_field(name="Bot lancé depuis", value=format_duration(time.time() - self.bot_started_at))
        embed.add_field(name="Latence Discord", value=f"{self.bot.latency * 1000:.0f} ms")
        await interaction.followup.send(embed=embed)

    async def check_system_limits(self):
        stats = await asyncio.to_thread(read_system_stats)
        limits = [
            ("cpu", "CPU", config.CPU_ALERT_PERCENT),
            ("ram", "RAM", config.RAM_ALERT_PERCENT),
            ("disk", "Disque", config.DISK_ALERT_PERCENT),
        ]
        for key, label, limit in limits:
            if stats[key] < limit:
                continue
            seconds_since_last_alert = time.time() - self.last_alert_time.get(key, 0)
            if seconds_since_last_alert < SECONDS_BETWEEN_ALERTS:
                continue
            self.last_alert_time[key] = time.time()
            await self.send_alert(f"🔥 {label} à {stats[key]:.0f} %", f"Seuil d'alerte : {limit:.0f} %", discord.Color.red())

    # --- /site ---------------------------------------------------------------------------------

    @site.command(name="ajouter", description="Surveiller un site web")
    async def add_site(self, interaction: discord.Interaction, url: str):
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        await interaction.response.defer()

        try:
            execute("INSERT INTO sites (url) VALUES (?)", url)
        except sqlite3.IntegrityError:  # la colonne url est UNIQUE
            raise ValueError("Ce site est déjà surveillé.") from None

        is_online, status, response_ms = await check_website(url)
        current = timestamp(now())
        down_since = None if is_online else current
        execute(
            "UPDATE sites SET is_up = ?, status = ?, response_ms = ?, checked_at = ?, down_since = ? WHERE url = ?",
            is_online, status, response_ms, current, down_since, url,
        )

        if is_online:
            state = f"🟢 en ligne ({status}, {response_ms} ms)"
        else:
            state = f"🔴 injoignable ({status or 'pas de réponse'})"
        await interaction.followup.send(f"👁️ Je surveille {url} — actuellement {state}.")

    @site.command(name="liste", description="État des sites surveillés")
    async def list_sites(self, interaction: discord.Interaction):
        sites = query("SELECT * FROM sites ORDER BY url")
        if not sites:
            raise ValueError("Aucun site surveillé. Ajoute-en avec /site ajouter.")

        lines = []
        for site in sites:
            if site["is_up"] is None:
                lines.append(f"⚪ {site['url']} · pas encore vérifié")
            elif site["is_up"]:
                lines.append(f"🟢 {site['url']} · {site['status']} · {site['response_ms']} ms")
            else:
                line = f"🔴 {site['url']} · {site['status'] or 'pas de réponse'}"
                if site["down_since"]:
                    line += f" depuis <t:{site['down_since']}:R>"
                lines.append(line)

        embed = discord.Embed(title="🌐 Sites surveillés", description="\n".join(lines), color=discord.Color.dark_teal())
        embed.set_footer(text=f"Vérification toutes les {config.MONITOR_INTERVAL_MINUTES} min")
        await interaction.response.send_message(embed=embed)

    @site.command(name="supprimer", description="Ne plus surveiller un site")
    async def delete_site(self, interaction: discord.Interaction, site: int):
        cursor = execute("DELETE FROM sites WHERE id = ?", site)
        if cursor.rowcount == 0:
            raise ValueError("Site introuvable.")
        await interaction.response.send_message("🗑️ Site retiré de la surveillance.", ephemeral=True)

    @delete_site.autocomplete("site")
    async def suggest_sites(self, interaction: discord.Interaction, typed_text: str):
        sites = query("SELECT id, url FROM sites WHERE url LIKE ? LIMIT 25", f"%{typed_text}%")
        return [app_commands.Choice(name=site["url"][:100], value=site["id"]) for site in sites]

    async def check_site(self, site):
        is_online, status, response_ms = await check_website(site["url"])
        if not is_online:
            # On reteste avant d'alerter, pour éviter les fausses alertes (petite coupure réseau…)
            await asyncio.sleep(SECONDS_BEFORE_CONFIRMING)
            is_online, status, response_ms = await check_website(site["url"])

        current = timestamp(now())
        was_online = site["is_up"]  # 1, 0, ou None si jamais vérifié
        down_since = site["down_since"]

        if not is_online and was_online != 0:
            # Le site vient de tomber
            down_since = current
            reason = f"HTTP {status}" if status else "Aucune réponse"
            await self.send_alert("🔴 Site hors ligne", f"{site['url']}\n{reason}", discord.Color.red())
        elif is_online and was_online == 0:
            # Le site est revenu
            if down_since:
                downtime = format_duration(current - down_since)
            else:
                downtime = "?"
            down_since = None
            await self.send_alert(
                "🟢 Site de retour en ligne", f"{site['url']}\nIndisponible pendant {downtime}", discord.Color.green()
            )

        execute(
            "UPDATE sites SET is_up = ?, status = ?, response_ms = ?, checked_at = ?, down_since = ? WHERE id = ?",
            is_online, status, response_ms, current, down_since, site["id"],
        )

    # --- Boucle automatique ----------------------------------------------------------------------

    @tasks.loop(minutes=config.MONITOR_INTERVAL_MINUTES)
    async def watch(self):
        try:
            await self.check_system_limits()
        except Exception:
            log.exception("Échec de la mesure de la machine")

        # Tous les sites sont testés en même temps (gather), plutôt que l'un après l'autre
        sites = query("SELECT * FROM sites")
        await asyncio.gather(*[self.check_site(site) for site in sites])

    @watch.before_loop
    async def wait_until_ready(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Monitoring(bot))
