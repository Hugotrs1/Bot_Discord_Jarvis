"""Briefing du matin : météo, rappels du jour, tâches, budget du mois et lectures en attente.

Envoyé automatiquement chaque jour à BRIEF_TIME dans le salon BRIEF_CHANNEL_ID,
ou à la demande avec /brief.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from cogs.budget import month_totals
from cogs.reading_list import unread_count
from cogs.reminders import reminders_left_today
from cogs.todo import format_todo, open_todos
from utils.dates import WEEKDAY_NAMES, now
from utils.discord_helpers import find_channel, owner_mention, timestamp
from utils.money import format_euros
from utils.web import NETWORK_ERRORS, download_json

log = logging.getLogger(__name__)

WEATHER_API = "https://api.open-meteo.com/v1/forecast"

# Codes météo de l'API Open-Meteo (norme WMO) → (emoji, description)
WEATHER_CODES = {
    0: ("☀️", "Ciel dégagé"),
    1: ("🌤️", "Plutôt dégagé"),
    2: ("⛅", "Partiellement nuageux"),
    3: ("☁️", "Couvert"),
    45: ("🌫️", "Brouillard"),
    48: ("🌫️", "Brouillard givrant"),
    51: ("🌦️", "Bruine légère"),
    53: ("🌦️", "Bruine"),
    55: ("🌧️", "Bruine forte"),
    61: ("🌧️", "Pluie faible"),
    63: ("🌧️", "Pluie"),
    65: ("🌧️", "Pluie forte"),
    66: ("🌧️", "Pluie verglaçante"),
    67: ("🌧️", "Pluie verglaçante forte"),
    71: ("🌨️", "Neige faible"),
    73: ("🌨️", "Neige"),
    75: ("❄️", "Neige forte"),
    77: ("🌨️", "Grains de neige"),
    80: ("🌦️", "Averses"),
    81: ("🌧️", "Averses"),
    82: ("⛈️", "Averses violentes"),
    85: ("🌨️", "Averses de neige"),
    86: ("❄️", "Averses de neige fortes"),
    95: ("⛈️", "Orage"),
    96: ("⛈️", "Orage avec grêle"),
    99: ("⛈️", "Orage avec grêle"),
}


async def weather_summary() -> str:
    """Météo du jour en deux lignes de texte."""
    params = {
        "latitude": config.LATITUDE,
        "longitude": config.LONGITUDE,
        "current": "temperature_2m",
        "daily": "weather_code,temperature_2m_min,temperature_2m_max,precipitation_probability_max",
        "timezone": str(config.TIMEZONE),
        "forecast_days": 1,
    }
    try:
        data = await download_json(WEATHER_API, params)
    except NETWORK_ERRORS as error:
        log.warning("Météo indisponible : %s", error)
        return "Météo indisponible pour le moment."

    # L'API renvoie des listes (une valeur par jour) : on prend la première, celle d'aujourd'hui
    today = data["daily"]
    current_temperature = data["current"]["temperature_2m"]
    emoji, description = WEATHER_CODES.get(today["weather_code"][0], ("🌡️", "Météo"))
    minimum = today["temperature_2m_min"][0]
    maximum = today["temperature_2m_max"][0]
    rain_chance = today["precipitation_probability_max"][0]

    return (
        f"{emoji} **{description}** à {config.CITY}\n"
        f"Actuellement **{current_temperature:.0f}°C** · min {minimum:.0f}°C / max {maximum:.0f}°C · ☔ {rain_chance} %"
    )


async def build_briefing(user_id: int | None) -> discord.Embed:
    """Construit le message du briefing. Sans user_id, seule la météo est affichée."""
    today = now()
    embed = discord.Embed(
        title=f"☕ Bonjour ! Briefing du {WEEKDAY_NAMES[today.weekday()]} {today:%d/%m}",
        color=discord.Color.orange(),
    )
    embed.add_field(name="Météo", value=await weather_summary(), inline=False)

    if user_id is None:
        embed.set_footer(text="Définis OWNER_ID dans .env pour voir aussi tes rappels, tâches et budget.")
        return embed

    # Rappels du jour
    reminders = reminders_left_today(user_id)
    lines = [f"<t:{reminder['due_at']}:t> — {reminder['message']}" for reminder in reminders[:10]]
    embed.add_field(
        name=f"⏰ Rappels du jour ({len(reminders)})",
        value="\n".join(lines) or "Aucun rappel aujourd'hui.",
        inline=False,
    )

    # Tâches : les 5 premières, et le nombre de tâches en retard
    todos = open_todos(user_id)
    overdue = [todo for todo in todos if todo["due_at"] and todo["due_at"] < timestamp(today)]
    lines = [format_todo(todo) for todo in todos[:5]]
    if len(todos) > 5:
        lines.append(f"… et {len(todos) - 5} autre(s)")
    title = f"📝 Tâches ({len(todos)})"
    if overdue:
        title += f" · ⚠️ {len(overdue)} en retard"
    embed.add_field(name=title, value="\n".join(lines) or "Rien à faire 🎉", inline=False)

    # Budget du mois en cours
    spent, income = month_totals(user_id, today.strftime("%Y-%m"))
    embed.add_field(
        name="💶 Budget du mois",
        value=f"Dépensé : **{format_euros(spent)}** · Rentrées : {format_euros(income)}",
        inline=False,
    )

    # Articles à lire
    unread = unread_count()
    if unread:
        embed.add_field(name="📚 À lire plus tard", value=f"{unread} article(s) en attente", inline=False)

    return embed


class Briefing(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.daily_briefing.start()

    @app_commands.command(name="brief", description="Afficher le briefing du jour maintenant")
    async def brief(self, interaction: discord.Interaction):
        await interaction.response.defer()  # la météo peut prendre une seconde à arriver
        embed = await build_briefing(interaction.user.id)
        await interaction.followup.send(embed=embed)

    @tasks.loop(time=config.BRIEF_TIME)
    async def daily_briefing(self):
        channel = await find_channel(self.bot, config.BRIEF_CHANNEL_ID)
        if channel is None:
            return
        owner_id = config.OWNER_ID or None
        embed = await build_briefing(owner_id)
        await channel.send(content=owner_mention(), embed=embed)

    @daily_briefing.before_loop
    async def wait_until_ready(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Briefing(bot))
