"""Rappels : /rappel ajouter, /rappel liste, /rappel supprimer"""

from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from database import execute, query
from utils.dates import add_one_month, now, parse_when

REPEAT_LABELS = {"jour": "tous les jours", "semaine": "toutes les semaines", "mois": "tous les mois"}


def next_date(due, repeat):
    """Prochaine date d'un rappel qui se répète."""
    if repeat == "jour":
        return due + timedelta(days=1)
    if repeat == "semaine":
        return due + timedelta(weeks=1)
    return add_one_month(due)


def add_reminder(channel_id, message, due, repeat=None):
    return execute(
        "INSERT INTO reminders (channel_id, message, due_at, repeat) VALUES (?, ?, ?, ?)",
        channel_id, message, int(due.timestamp()), repeat,
    ).lastrowid


class SnoozeButtons(discord.ui.View):
    """Boutons sous un rappel pour le reporter."""

    def __init__(self, channel_id, message):
        super().__init__(timeout=3600)
        self.channel_id = channel_id
        self.message = message

    async def snooze(self, interaction, due):
        add_reminder(self.channel_id, self.message, due)
        await interaction.response.edit_message(view=None)  # retire les boutons
        await interaction.followup.send(f"💤 Reporté à <t:{int(due.timestamp())}:t>.", ephemeral=True)

    @discord.ui.button(label="+10 min")
    async def ten_minutes(self, interaction, button):
        await self.snooze(interaction, now() + timedelta(minutes=10))

    @discord.ui.button(label="+1 h")
    async def one_hour(self, interaction, button):
        await self.snooze(interaction, now() + timedelta(hours=1))

    @discord.ui.button(label="Demain 9h")
    async def tomorrow(self, interaction, button):
        await self.snooze(interaction, parse_when("demain 9h"))


class Reminders(commands.Cog):
    rappel = app_commands.Group(name="rappel", description="Tes rappels")

    def __init__(self, bot):
        self.bot = bot
        self.send_due_reminders.start()

    @rappel.command(name="ajouter", description="Créer un rappel")
    @app_commands.describe(quand="Ex : dans 2h, demain 9h, vendredi 18h, 25/12", message="De quoi te rappeler")
    @app_commands.choices(repeter=[
        app_commands.Choice(name="Tous les jours", value="jour"),
        app_commands.Choice(name="Toutes les semaines", value="semaine"),
        app_commands.Choice(name="Tous les mois", value="mois"),
    ])
    async def add(self, interaction, quand: str, message: str, repeter: str = None):
        due = parse_when(quand)
        reminder_id = add_reminder(interaction.channel_id, message, due, repeter)
        repeat_text = f" ({REPEAT_LABELS[repeter]})" if repeter else ""
        await interaction.response.send_message(
            f"✅ Rappel #{reminder_id} le <t:{int(due.timestamp())}:F>{repeat_text} :\n> {message}"
        )

    @rappel.command(name="liste", description="Voir tes rappels")
    async def show(self, interaction):
        rows = query("SELECT * FROM reminders ORDER BY due_at LIMIT 25")
        if not rows:
            return await interaction.response.send_message("Aucun rappel prévu. 🌴", ephemeral=True)
        lines = [f"**#{r['id']}** · <t:{r['due_at']}:f> {'🔁' if r['repeat'] else ''} — {r['message']}" for r in rows]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @rappel.command(name="supprimer", description="Supprimer un rappel")
    async def delete(self, interaction, numero: int):
        if execute("DELETE FROM reminders WHERE id = ?", numero).rowcount == 0:
            raise ValueError(f"Rappel #{numero} introuvable.")
        await interaction.response.send_message(f"🗑️ Rappel #{numero} supprimé.", ephemeral=True)

    @tasks.loop(seconds=20)
    async def send_due_reminders(self):
        """Toutes les 20 secondes : envoie les rappels arrivés à échéance."""
        for reminder in query("SELECT * FROM reminders WHERE due_at <= ?", int(now().timestamp())):
            channel = self.bot.get_channel(reminder["channel_id"])
            if channel:
                embed = discord.Embed(title="⏰ Rappel", description=reminder["message"], color=discord.Color.gold())
                buttons = SnoozeButtons(reminder["channel_id"], reminder["message"])
                await channel.send(f"<@{config.OWNER_ID}>", embed=embed, view=buttons)

            if reminder["repeat"]:
                # Rappel récurrent : on le décale à sa prochaine date (sans en envoyer plusieurs si le bot était éteint)
                due = datetime.fromtimestamp(reminder["due_at"], config.TIMEZONE)
                while due <= now():
                    due = next_date(due, reminder["repeat"])
                execute("UPDATE reminders SET due_at = ? WHERE id = ?", int(due.timestamp()), reminder["id"])
            else:
                execute("DELETE FROM reminders WHERE id = ?", reminder["id"])

    @send_due_reminders.before_loop
    async def wait_until_ready(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Reminders(bot))
