"""Briefing du matin : météo, rappels du jour, tâches, budget, lectures en attente."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from jarvis.cogs.todo import format_todo
from jarvis.utils.money import format_cents

if TYPE_CHECKING:
    from jarvis.bot import Jarvis

log = logging.getLogger(__name__)

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# Codes météo WMO utilisés par Open-Meteo
WEATHER_CODES = {
    0: ("☀️", "Ciel dégagé"), 1: ("🌤️", "Plutôt dégagé"), 2: ("⛅", "Partiellement nuageux"),
    3: ("☁️", "Couvert"), 45: ("🌫️", "Brouillard"), 48: ("🌫️", "Brouillard givrant"),
    51: ("🌦️", "Bruine légère"), 53: ("🌦️", "Bruine"), 55: ("🌧️", "Bruine forte"),
    61: ("🌧️", "Pluie faible"), 63: ("🌧️", "Pluie"), 65: ("🌧️", "Pluie forte"),
    66: ("🌧️", "Pluie verglaçante"), 67: ("🌧️", "Pluie verglaçante forte"),
    71: ("🌨️", "Neige faible"), 73: ("🌨️", "Neige"), 75: ("❄️", "Neige forte"), 77: ("🌨️", "Grains de neige"),
    80: ("🌦️", "Averses"), 81: ("🌧️", "Averses"), 82: ("⛈️", "Averses violentes"),
    85: ("🌨️", "Averses de neige"), 86: ("❄️", "Averses de neige fortes"),
    95: ("⛈️", "Orage"), 96: ("⛈️", "Orage avec grêle"), 99: ("⛈️", "Orage avec grêle"),
}

GREETINGS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


class Briefing(commands.Cog):
    def __init__(self, bot: Jarvis) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        config = self.bot.config
        self.daily_brief.change_interval(time=config.brief_time.replace(tzinfo=config.tz))
        self.daily_brief.start()

    async def cog_unload(self) -> None:
        self.daily_brief.cancel()

    async def fetch_weather(self) -> str:
        config = self.bot.config
        params = {
            "latitude": config.latitude,
            "longitude": config.longitude,
            "current": "temperature_2m,weather_code",
            "daily": "temperature_2m_min,temperature_2m_max,precipitation_probability_max,weather_code",
            "timezone": str(config.tz),
            "forecast_days": 1,
        }
        try:
            async with self.bot.session.get(WEATHER_URL, params=params) as response:
                response.raise_for_status()
                data = await response.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            log.warning("Météo indisponible : %s", exc)
            return "Météo indisponible pour le moment."

        current, daily = data["current"], data["daily"]
        emoji, label = WEATHER_CODES.get(daily["weather_code"][0], ("🌡️", "Météo"))
        return (
            f"{emoji} **{label}** à {config.city_name}\n"
            f"Actuellement **{current['temperature_2m']:.0f}°C** · "
            f"min {daily['temperature_2m_min'][0]:.0f}°C / max {daily['temperature_2m_max'][0]:.0f}°C · "
            f"☔ {daily['precipitation_probability_max'][0]}%"
        )

    async def build_embed(self, user_id: int | None) -> discord.Embed:
        now = self.bot.now()
        embed = discord.Embed(
            title=f"☕ Bonjour ! Briefing du {GREETINGS[now.weekday()]} {now:%d/%m}",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Météo", value=await self.fetch_weather(), inline=False)

        if user_id is None:
            embed.set_footer(text="Définis OWNER_ID dans .env pour voir tes rappels, tâches et budget ici.")
            return embed

        if reminders_cog := self.bot.get_cog("Reminders"):
            reminders = await reminders_cog.due_today(user_id)  # type: ignore[attr-defined]
            value = "\n".join(f"<t:{r['due_at']}:t> — {r['message']}" for r in reminders[:10]) or "Aucun rappel aujourd'hui."
            embed.add_field(name=f"⏰ Rappels du jour ({len(reminders)})", value=value, inline=False)

        if todo_cog := self.bot.get_cog("Todo"):
            todos = await todo_cog.open_todos(user_id)  # type: ignore[attr-defined]
            now_ts = int(now.timestamp())
            overdue = sum(1 for t in todos if t["due_at"] and t["due_at"] < now_ts)
            value = "\n".join(format_todo(t, now_ts) for t in todos[:5]) or "Rien à faire 🎉"
            if len(todos) > 5:
                value += f"\n… et {len(todos) - 5} autre(s)"
            title = f"📝 Tâches ({len(todos)})" + (f" · ⚠️ {overdue} en retard" if overdue else "")
            embed.add_field(name=title, value=value, inline=False)

        if budget_cog := self.bot.get_cog("Budget"):
            spent, income = await budget_cog.month_totals(user_id, now.strftime("%Y-%m"))  # type: ignore[attr-defined]
            embed.add_field(
                name="💶 Budget du mois",
                value=f"Dépensé : **{format_cents(spent)}** · Rentrées : {format_cents(income)}",
                inline=False,
            )

        if readlater_cog := self.bot.get_cog("ReadLater"):
            unread = await readlater_cog.unread_count()  # type: ignore[attr-defined]
            if unread:
                embed.add_field(name="📚 À lire plus tard", value=f"{unread} article(s) en attente", inline=False)

        return embed

    @app_commands.command(name="brief", description="Afficher le briefing du jour maintenant")
    async def brief(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await interaction.followup.send(embed=await self.build_embed(interaction.user.id))

    @tasks.loop(hours=24)  # remplacé au démarrage par l'heure BRIEF_TIME
    async def daily_brief(self) -> None:
        channel = await self.bot.get_text_channel(self.bot.config.brief_channel_id)
        if channel is None:
            return
        owner = self.bot.config.owner_id
        await channel.send(content=f"<@{owner}>" if owner else None, embed=await self.build_embed(owner))

    @daily_brief.before_loop
    async def before_brief(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: Jarvis) -> None:
    await bot.add_cog(Briefing(bot))
