"""Rappels ponctuels ou récurrents.

Commandes : /rappel ajouter, /rappel liste, /rappel supprimer
Toutes les 20 secondes, le bot envoie les rappels arrivés à échéance.
"""

import logging
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from database import execute, query
from utils.dates import add_months, now, parse_when
from utils.discord_helpers import find_channel, timestamp

log = logging.getLogger(__name__)

# Valeur enregistrée en base → texte affiché
REPEAT_LABELS = {
    "quotidien": "tous les jours",
    "hebdo": "toutes les semaines",
    "mensuel": "tous les mois",
}


def next_occurrence(due: datetime, repeat: str, current: datetime) -> datetime:
    """Prochaine date (strictement dans le futur) d'un rappel récurrent.

    Si le bot était éteint plusieurs jours, on saute les dates manquées
    au lieu d'envoyer le rappel plusieurs fois d'affilée.

    On repart toujours de la date d'origine (`due`) : ainsi un rappel mensuel
    du 31 reste au 31 quand c'est possible (31/01 → 28/02 → 31/03).
    L'heure ne bouge pas lors des changements d'heure été/hiver.
    """
    due = due.astimezone(current.tzinfo)
    steps = 0
    next_due = due
    while next_due <= current:
        steps += 1
        if repeat == "quotidien":
            next_due = due + timedelta(days=steps)
        elif repeat == "hebdo":
            next_due = due + timedelta(weeks=steps)
        elif repeat == "mensuel":
            next_due = add_months(due, steps)
        else:
            raise ValueError(f"Récurrence inconnue : {repeat}")
    return next_due


def create_reminder(user_id: int, channel_id: int, message: str, due: datetime, repeat: str | None = None) -> int:
    """Enregistre un rappel et renvoie son numéro."""
    cursor = execute(
        "INSERT INTO reminders (user_id, channel_id, message, due_at, repeat) VALUES (?, ?, ?, ?, ?)",
        user_id, channel_id, message, timestamp(due), repeat,
    )
    return cursor.lastrowid


def reminders_left_today(user_id: int) -> list:
    """Rappels qui restent à venir aujourd'hui (utilisé par le briefing du matin)."""
    start = now()
    end_of_day = start.replace(hour=23, minute=59, second=59)
    return query(
        "SELECT * FROM reminders WHERE user_id = ? AND due_at BETWEEN ? AND ? ORDER BY due_at",
        user_id, timestamp(start), timestamp(end_of_day),
    )


class SnoozeButtons(discord.ui.View):
    """Boutons affichés sous un rappel pour le reporter. Ils restent actifs une heure."""

    def __init__(self, user_id: int, channel_id: int, message: str):
        super().__init__(timeout=3600)
        self.user_id = user_id
        self.channel_id = channel_id
        self.message = message

    async def snooze(self, interaction: discord.Interaction, new_due: datetime):
        create_reminder(self.user_id, self.channel_id, self.message, new_due)

        # Grise les boutons pour qu'on ne reporte pas deux fois
        for button in self.children:
            button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"⏰ Reporté à <t:{timestamp(new_due)}:f>.", ephemeral=True)

    @discord.ui.button(label="+10 min", emoji="💤")
    async def in_ten_minutes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.snooze(interaction, now() + timedelta(minutes=10))

    @discord.ui.button(label="+1 h", emoji="🕐")
    async def in_one_hour(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.snooze(interaction, now() + timedelta(hours=1))

    @discord.ui.button(label="Demain 9h", emoji="🌅")
    async def tomorrow_morning(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.snooze(interaction, parse_when("demain 9h"))


class Reminders(commands.Cog):
    rappel = app_commands.Group(name="rappel", description="Gérer tes rappels")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.send_due_reminders.start()

    # --- Commandes ---------------------------------------------------------------------

    @rappel.command(name="ajouter", description="Créer un rappel")
    @app_commands.describe(
        quand="Ex : dans 2h, demain 9h, vendredi 18h, 25/12 10h, 1er janvier",
        message="Ce qu'il faut te rappeler",
        repeter="Répéter le rappel",
    )
    @app_commands.choices(repeter=[
        app_commands.Choice(name="Tous les jours", value="quotidien"),
        app_commands.Choice(name="Toutes les semaines", value="hebdo"),
        app_commands.Choice(name="Tous les mois", value="mensuel"),
    ])
    async def add(
        self,
        interaction: discord.Interaction,
        quand: str,
        message: app_commands.Range[str, 1, 500],
        repeter: app_commands.Choice[str] | None = None,
    ):
        due = parse_when(quand)
        repeat = repeter.value if repeter else None
        reminder_id = create_reminder(interaction.user.id, interaction.channel_id, message, due, repeat)

        text = f"✅ Rappel **#{reminder_id}** le <t:{timestamp(due)}:F> (<t:{timestamp(due)}:R>)"
        if repeat:
            text += f" ({REPEAT_LABELS[repeat]})"
        text += f" :\n> {message}"
        await interaction.response.send_message(text)

    @rappel.command(name="liste", description="Voir tes rappels à venir")
    async def show_list(self, interaction: discord.Interaction):
        reminders = query(
            "SELECT * FROM reminders WHERE user_id = ? ORDER BY due_at LIMIT 25", interaction.user.id
        )
        if not reminders:
            await interaction.response.send_message("Aucun rappel prévu. 🌴", ephemeral=True)
            return

        lines = []
        for reminder in reminders:
            line = f"**#{reminder['id']}** · <t:{reminder['due_at']}:f> (<t:{reminder['due_at']}:R>)"
            if reminder["repeat"]:
                line += " 🔁"
            line += f" — {reminder['message']}"
            lines.append(line)

        embed = discord.Embed(title="⏰ Tes rappels", description="\n".join(lines), color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @rappel.command(name="supprimer", description="Supprimer un rappel")
    @app_commands.describe(rappel="Le rappel à supprimer")
    async def delete(self, interaction: discord.Interaction, rappel: int):
        cursor = execute("DELETE FROM reminders WHERE id = ? AND user_id = ?", rappel, interaction.user.id)
        if cursor.rowcount == 0:
            raise ValueError(f"Rappel #{rappel} introuvable.")
        await interaction.response.send_message(f"🗑️ Rappel #{rappel} supprimé.", ephemeral=True)

    @delete.autocomplete("rappel")
    async def suggest_reminders(self, interaction: discord.Interaction, typed_text: str):
        """Propose les rappels pendant que l'utilisateur tape."""
        reminders = query(
            "SELECT id, message FROM reminders WHERE user_id = ? AND message LIKE ? ORDER BY due_at LIMIT 25",
            interaction.user.id, f"%{typed_text}%",
        )
        return [
            app_commands.Choice(name=f"#{reminder['id']} — {reminder['message'][:80]}", value=reminder["id"])
            for reminder in reminders
        ]

    # --- Envoi automatique -----------------------------------------------------------------

    @tasks.loop(seconds=20)
    async def send_due_reminders(self):
        current = now()
        due_reminders = query("SELECT * FROM reminders WHERE due_at <= ?", timestamp(current))

        for reminder in due_reminders:
            try:
                await self.send_reminder(reminder)
            except discord.HTTPException:
                log.exception("Impossible d'envoyer le rappel #%s", reminder["id"])

            if reminder["repeat"]:
                # Rappel récurrent : on le décale à sa prochaine date
                due = datetime.fromtimestamp(reminder["due_at"], config.TIMEZONE)
                next_due = next_occurrence(due, reminder["repeat"], current)
                execute("UPDATE reminders SET due_at = ? WHERE id = ?", timestamp(next_due), reminder["id"])
            else:
                execute("DELETE FROM reminders WHERE id = ?", reminder["id"])

    @send_due_reminders.before_loop
    async def wait_until_ready(self):
        await self.bot.wait_until_ready()

    async def send_reminder(self, reminder):
        # Dans le salon d'origine ; s'il n'existe plus, en message privé
        channel = await find_channel(self.bot, reminder["channel_id"])
        if channel is None:
            user = await self.bot.fetch_user(reminder["user_id"])
            channel = await user.create_dm()

        embed = discord.Embed(description=reminder["message"], color=discord.Color.gold())
        embed.set_author(name="⏰ Rappel")
        if reminder["repeat"]:
            embed.set_footer(text=f"Récurrent : {REPEAT_LABELS[reminder['repeat']]}")

        buttons = SnoozeButtons(reminder["user_id"], reminder["channel_id"], reminder["message"])
        await channel.send(content=f"<@{reminder['user_id']}>", embed=embed, view=buttons)


async def setup(bot: commands.Bot):
    await bot.add_cog(Reminders(bot))
