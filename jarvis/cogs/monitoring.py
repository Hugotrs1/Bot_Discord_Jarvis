"""Monitoring : état de la machine (/status) et disponibilité de sites web (/site)."""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from typing import TYPE_CHECKING

import aiohttp
import discord
import psutil
from discord import app_commands
from discord.ext import commands, tasks

if TYPE_CHECKING:
    from jarvis.bot import Jarvis

log = logging.getLogger(__name__)

ALERT_COOLDOWN = 3600  # secondes entre deux alertes pour la même ressource


def bar(percent: float, width: int = 12) -> str:
    filled = round(percent / 100 * width)
    return "█" * filled + "░" * (width - filled)


def human_duration(seconds: float) -> str:
    days, rest = divmod(int(seconds), 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    parts = [f"{days} j" if days else "", f"{hours} h" if hours else "", f"{minutes} min"]
    return " ".join(p for p in parts if p)


def human_bytes(size: float) -> str:
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} Po"


def collect_system_stats() -> dict:
    """Mesures système (bloquant ~1 s à cause de la mesure CPU : à lancer dans un thread)."""
    disk_root = os.path.abspath(os.sep)
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
        "temperature": None,
    }
    if hasattr(psutil, "sensors_temperatures"):  # Linux uniquement (ex : Raspberry Pi)
        sensors = psutil.sensors_temperatures() or {}
        readings = [t.current for entries in sensors.values() for t in entries if t.current]
        stats["temperature"] = max(readings) if readings else None
    return stats


class Monitoring(commands.Cog):
    site = app_commands.Group(name="site", description="Surveiller la disponibilité de sites web")

    def __init__(self, bot: Jarvis) -> None:
        self.bot = bot
        self.started_at = time.time()
        self.last_alert: dict[str, float] = {}

    async def cog_load(self) -> None:
        self.watch.change_interval(minutes=self.bot.config.monitor_interval_minutes)
        self.watch.start()

    async def cog_unload(self) -> None:
        self.watch.cancel()

    async def alert(self, embed: discord.Embed) -> None:
        channel = await self.bot.get_text_channel(self.bot.config.alerts_channel_id)
        if channel:
            owner = self.bot.config.owner_id
            await channel.send(content=f"<@{owner}>" if owner else None, embed=embed)

    # --- Machine -----------------------------------------------------------------------

    @app_commands.command(name="status", description="État de la machine qui héberge le bot")
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        s = await asyncio.to_thread(collect_system_stats)
        embed = discord.Embed(title="🖥️ État du serveur", color=discord.Color.dark_teal())
        embed.add_field(name="CPU", value=f"`{bar(s['cpu'])}` {s['cpu']:.0f}%", inline=False)
        embed.add_field(
            name="RAM",
            value=f"`{bar(s['ram'])}` {s['ram']:.0f}% ({human_bytes(s['ram_used'])} / {human_bytes(s['ram_total'])})",
            inline=False,
        )
        embed.add_field(
            name=f"Disque ({s['disk_root']})",
            value=f"`{bar(s['disk'])}` {s['disk']:.0f}% · {human_bytes(s['disk_free'])} libres",
            inline=False,
        )
        if s["temperature"] is not None:
            embed.add_field(name="Température", value=f"🌡️ {s['temperature']:.0f}°C")
        embed.add_field(name="Machine allumée depuis", value=human_duration(s["uptime"]))
        embed.add_field(name="Bot lancé depuis", value=human_duration(time.time() - self.started_at))
        embed.add_field(name="Latence Discord", value=f"{self.bot.latency * 1000:.0f} ms")
        await interaction.followup.send(embed=embed)

    async def check_thresholds(self) -> None:
        config = self.bot.config
        s = await asyncio.to_thread(collect_system_stats)
        for key, label, limit in (
            ("cpu", "CPU", config.cpu_alert),
            ("ram", "RAM", config.ram_alert),
            ("disk", "Disque", config.disk_alert),
        ):
            if s[key] < limit or time.time() - self.last_alert.get(key, 0) < ALERT_COOLDOWN:
                continue
            self.last_alert[key] = time.time()
            await self.alert(discord.Embed(
                title=f"🔥 {label} à {s[key]:.0f}%",
                description=f"Seuil d'alerte : {limit:.0f}%",
                color=discord.Color.red(),
            ))

    # --- Sites web -------------------------------------------------------------------------

    async def probe(self, url: str) -> tuple[bool, int | None, int]:
        """Renvoie (en ligne ?, code HTTP, temps de réponse en ms)."""
        start = time.perf_counter()
        try:
            async with self.bot.session.get(url, allow_redirects=True) as response:
                await response.read()
                ok = response.status < 400
                return ok, response.status, round((time.perf_counter() - start) * 1000)
        except (aiohttp.ClientError, TimeoutError):
            return False, None, round((time.perf_counter() - start) * 1000)

    async def check_site(self, site) -> None:
        up, status, ms = await self.probe(site["url"])
        if not up:  # on confirme la panne avant d'alerter, pour éviter les fausses alertes
            await asyncio.sleep(5)
            up, status, ms = await self.probe(site["url"])

        now_ts = int(self.bot.now().timestamp())
        was_up = site["is_up"]
        down_since = site["down_since"]
        if not up and (was_up or was_up is None):
            down_since = now_ts
            await self.alert(discord.Embed(
                title="🔴 Site hors ligne",
                description=f"{site['url']}\n{'HTTP ' + str(status) if status else 'Aucune réponse'}",
                color=discord.Color.red(),
            ))
        elif up and was_up == 0:
            duration = human_duration(now_ts - down_since) if down_since else "?"
            down_since = None
            await self.alert(discord.Embed(
                title="🟢 Site de retour en ligne",
                description=f"{site['url']}\nIndisponible pendant {duration}",
                color=discord.Color.green(),
            ))

        await self.bot.db.execute(
            "UPDATE sites SET is_up = ?, last_status = ?, last_ms = ?, last_checked = ?, down_since = ? WHERE id = ?",
            (int(up), status, ms, now_ts, down_since, site["id"]),
        )

    @site.command(name="ajouter", description="Surveiller un site web")
    async def add_site(self, interaction: discord.Interaction, url: str) -> None:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        await interaction.response.defer()
        try:
            await self.bot.db.execute("INSERT INTO sites (url) VALUES (?)", (url,))
        except sqlite3.IntegrityError as exc:
            raise ValueError("Ce site est déjà surveillé.") from exc
        site = await self.bot.db.fetchone("SELECT * FROM sites WHERE url = ?", (url,))
        up, status, ms = await self.probe(url)
        await self.bot.db.execute(
            "UPDATE sites SET is_up = ?, last_status = ?, last_ms = ?, last_checked = ?, down_since = ? WHERE id = ?",
            (int(up), status, ms, int(self.bot.now().timestamp()), None if up else int(self.bot.now().timestamp()), site["id"]),
        )
        state = f"🟢 en ligne ({status}, {ms} ms)" if up else f"🔴 injoignable ({status or 'pas de réponse'})"
        await interaction.followup.send(f"👁️ Je surveille {url} — actuellement {state}.")

    @site.command(name="liste", description="État des sites surveillés")
    async def list_sites(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.fetchall("SELECT * FROM sites ORDER BY url")
        if not rows:
            raise ValueError("Aucun site surveillé. Ajoute-en avec `/site ajouter`.")
        lines = []
        for r in rows:
            if r["is_up"]:
                lines.append(f"🟢 {r['url']} · {r['last_status']} · {r['last_ms']} ms")
            elif r["is_up"] == 0:
                since = f" depuis <t:{r['down_since']}:R>" if r["down_since"] else ""
                lines.append(f"🔴 {r['url']} · {r['last_status'] or 'pas de réponse'}{since}")
            else:
                lines.append(f"⚪ {r['url']} · pas encore vérifié")
        embed = discord.Embed(title="🌐 Sites surveillés", description="\n".join(lines), color=discord.Color.dark_teal())
        embed.set_footer(text=f"Vérification toutes les {self.bot.config.monitor_interval_minutes} min")
        await interaction.response.send_message(embed=embed)

    @site.command(name="supprimer", description="Ne plus surveiller un site")
    async def delete_site(self, interaction: discord.Interaction, site: int) -> None:
        if not await self.bot.db.execute_rowcount("DELETE FROM sites WHERE id = ?", (site,)):
            raise ValueError("Site introuvable.")
        await interaction.response.send_message("🗑️ Site retiré de la surveillance.", ephemeral=True)

    @delete_site.autocomplete("site")
    async def site_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
        rows = await self.bot.db.fetchall("SELECT id, url FROM sites WHERE url LIKE ? LIMIT 25", (f"%{current}%",))
        return [app_commands.Choice(name=r["url"][:100], value=r["id"]) for r in rows]

    # --- Boucle --------------------------------------------------------------------------------

    @tasks.loop(minutes=5)  # remplacé au démarrage par MONITOR_INTERVAL_MINUTES
    async def watch(self) -> None:
        try:
            await self.check_thresholds()
        except Exception:
            log.exception("Échec de la mesure système")
        sites = await self.bot.db.fetchall("SELECT * FROM sites")
        await asyncio.gather(*(self.check_site(s) for s in sites))

    @watch.before_loop
    async def before_watch(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: Jarvis) -> None:
    await bot.add_cog(Monitoring(bot))
