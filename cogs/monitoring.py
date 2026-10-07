"""Monitoring : /status (état de la machine) et /site (surveiller des sites web)."""

import os
import time

import discord
import psutil
from discord import app_commands
from discord.ext import commands, tasks

import config
from database import execute, query, query_one
from utils.web import ping

CHECK_EVERY_MINUTES = 5
ALERT_THRESHOLD = 90  # % de CPU, RAM ou disque au-delà duquel on alerte
ALERT_PAUSE = 3600  # secondes minimum entre deux alertes pour la même chose


def bar(percent):
    filled = round(percent / 10)
    return "█" * filled + "░" * (10 - filled)


def duration(seconds):
    days, seconds = divmod(int(seconds), 86400)
    hours, seconds = divmod(seconds, 3600)
    return f"{days} j {hours} h {seconds // 60} min" if days else f"{hours} h {seconds // 60} min"


def machine_stats():
    return {
        "CPU": psutil.cpu_percent(interval=1),
        "RAM": psutil.virtual_memory().percent,
        "Disque": psutil.disk_usage(os.path.abspath(os.sep)).percent,
    }


def is_up(status):
    return status is not None and status < 400


class Monitoring(commands.Cog):
    site = app_commands.Group(name="site", description="Surveillance de sites web")

    def __init__(self, bot):
        self.bot = bot
        self.last_alerts = {}  # {"CPU": heure de la dernière alerte}
        self.watch.start()

    async def alert(self, title, description, color):
        channel = self.bot.get_channel(config.ALERTS_CHANNEL_ID)
        if channel:
            embed = discord.Embed(title=title, description=description, color=color)
            await channel.send(f"<@{config.OWNER_ID}>", embed=embed)

    @app_commands.command(name="status", description="État de la machine qui fait tourner le bot")
    async def status(self, interaction):
        lines = [f"**{name}** `{bar(percent)}` {percent:.0f} %" for name, percent in machine_stats().items()]
        lines.append(f"**Allumée depuis** {duration(time.time() - psutil.boot_time())}")
        lines.append(f"**Latence Discord** {self.bot.latency * 1000:.0f} ms")
        embed = discord.Embed(title="🖥️ État du serveur", description="\n".join(lines), color=discord.Color.dark_teal())
        await interaction.response.send_message(embed=embed)

    @site.command(name="ajouter", description="Surveiller un site web")
    async def add_site(self, interaction, url: str):
        if not url.startswith("http"):
            url = "https://" + url
        if query_one("SELECT id FROM sites WHERE url = ?", url):
            raise ValueError("Ce site est déjà surveillé.")
        await interaction.response.defer()
        status, ms = await ping(url)
        execute("INSERT INTO sites (url, is_up, status, ms) VALUES (?, ?, ?, ?)", url, is_up(status), status, ms)
        state = f"🟢 en ligne ({ms} ms)" if is_up(status) else f"🔴 injoignable ({status or 'pas de réponse'})"
        await interaction.followup.send(f"👁️ Je surveille {url} — {state}")

    @site.command(name="liste", description="État des sites surveillés")
    async def list_sites(self, interaction):
        lines = []
        for site in query("SELECT * FROM sites ORDER BY url"):
            if site["is_up"]:
                lines.append(f"🟢 {site['url']} · {site['ms']} ms")
            else:
                lines.append(f"🔴 {site['url']} · {site['status'] or 'pas de réponse'}")
        await interaction.response.send_message("\n".join(lines) or "Aucun site surveillé.")

    @site.command(name="supprimer", description="Ne plus surveiller un site")
    async def delete_site(self, interaction, url: str):
        if execute("DELETE FROM sites WHERE url = ?", url).rowcount == 0:
            raise ValueError("Ce site n'est pas surveillé.")
        await interaction.response.send_message("🗑️ Site retiré.", ephemeral=True)

    @delete_site.autocomplete("url")
    async def suggest_sites(self, interaction, typed: str):
        rows = query("SELECT url FROM sites WHERE url LIKE ? LIMIT 25", f"%{typed}%")
        return [app_commands.Choice(name=row["url"], value=row["url"]) for row in rows]

    @tasks.loop(minutes=CHECK_EVERY_MINUTES)
    async def watch(self):
        # 1. La machine : alerte si CPU, RAM ou disque dépasse le seuil (au plus une fois par heure)
        for name, percent in machine_stats().items():
            if percent >= ALERT_THRESHOLD and time.time() - self.last_alerts.get(name, 0) > ALERT_PAUSE:
                self.last_alerts[name] = time.time()
                await self.alert(f"🔥 {name} à {percent:.0f} %", f"Seuil d'alerte : {ALERT_THRESHOLD} %", discord.Color.red())

        # 2. Les sites : alerte quand un site tombe ou revient
        for site in query("SELECT * FROM sites"):
            status, ms = await ping(site["url"])
            up = is_up(status)
            down_since = site["down_since"]

            if site["is_up"] and not up:
                down_since = int(time.time())
                await self.alert("🔴 Site hors ligne", f"{site['url']}\nRéponse : {status or 'aucune'}", discord.Color.red())
            elif not site["is_up"] and up:
                downtime = duration(time.time() - down_since) if down_since else "?"
                down_since = None
                await self.alert("🟢 Site de retour", f"{site['url']}\nIndisponible pendant {downtime}", discord.Color.green())

            execute("UPDATE sites SET is_up = ?, status = ?, ms = ?, down_since = ? WHERE id = ?",
                    up, status, ms, down_since, site["id"])

    @watch.before_loop
    async def wait_until_ready(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Monitoring(bot))
