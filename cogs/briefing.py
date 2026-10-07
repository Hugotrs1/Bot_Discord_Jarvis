"""Briefing du matin (envoyé automatiquement chaque jour, ou avec /brief)."""

from datetime import time

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from cogs.budget import month_totals
from cogs.todo import open_todos, todo_line
from database import query, query_one
from utils.dates import WEEKDAYS, now
from utils.money import euros
from utils.web import get_json

BRIEF_TIME = time(7, 30, tzinfo=config.TIMEZONE)


def weather_label(code):
    """Codes météo de l'API Open-Meteo → texte lisible."""
    if code == 0:
        return "☀️ Ensoleillé"
    if code <= 3:
        return "⛅ Nuageux"
    if code <= 48:
        return "🌫️ Brouillard"
    if code <= 67 or 80 <= code <= 82:
        return "🌧️ Pluie"
    if code <= 86:
        return "❄️ Neige"
    return "⛈️ Orage"


async def weather():
    try:
        data = await get_json("https://api.open-meteo.com/v1/forecast", {
            "latitude": config.LATITUDE,
            "longitude": config.LONGITUDE,
            "daily": "weather_code,temperature_2m_min,temperature_2m_max,precipitation_probability_max",
            "timezone": str(config.TIMEZONE),
            "forecast_days": 1,
        })
    except (aiohttp.ClientError, TimeoutError):
        return "Météo indisponible."
    day = {key: values[0] for key, values in data["daily"].items()}
    return (
        f"{weather_label(day['weather_code'])} à {config.CITY} · "
        f"{day['temperature_2m_min']:.0f}°C → {day['temperature_2m_max']:.0f}°C · "
        f"☔ {day['precipitation_probability_max']} %"
    )


async def build_briefing():
    today = now()
    embed = discord.Embed(title=f"☕ Bonjour ! On est {WEEKDAYS[today.weekday()]} {today:%d/%m}", color=discord.Color.orange())
    embed.add_field(name="Météo", value=await weather(), inline=False)

    end_of_day = today.replace(hour=23, minute=59)
    reminders = query(
        "SELECT * FROM reminders WHERE due_at BETWEEN ? AND ? ORDER BY due_at",
        int(today.timestamp()), int(end_of_day.timestamp()),
    )
    lines = [f"<t:{r['due_at']}:t> — {r['message']}" for r in reminders]
    embed.add_field(name="⏰ Rappels du jour", value="\n".join(lines) or "Aucun", inline=False)

    todos = open_todos()
    lines = [todo_line(t) for t in todos[:5]]
    if len(todos) > 5:
        lines.append(f"… et {len(todos) - 5} autre(s)")
    embed.add_field(name=f"📝 Tâches ({len(todos)})", value="\n".join(lines) or "Rien à faire 🎉", inline=False)

    spent, income = month_totals(today.strftime("%Y-%m"))
    embed.add_field(name="💶 Ce mois-ci", value=f"Dépensé : {euros(spent)} · Rentrées : {euros(income)}", inline=False)

    unread = query_one("SELECT COUNT(*) AS n FROM reading_list WHERE read = 0")["n"]
    if unread:
        embed.add_field(name="📚 À lire", value=f"{unread} article(s) en attente", inline=False)
    return embed


class Briefing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.morning_briefing.start()

    @app_commands.command(name="brief", description="Afficher le briefing du jour")
    async def brief(self, interaction):
        await interaction.response.defer()  # la météo peut prendre une seconde
        await interaction.followup.send(embed=await build_briefing())

    @tasks.loop(time=BRIEF_TIME)
    async def morning_briefing(self):
        channel = self.bot.get_channel(config.BRIEF_CHANNEL_ID)
        if channel:
            await channel.send(f"<@{config.OWNER_ID}>", embed=await build_briefing())

    @morning_briefing.before_loop
    async def wait_until_ready(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Briefing(bot))
