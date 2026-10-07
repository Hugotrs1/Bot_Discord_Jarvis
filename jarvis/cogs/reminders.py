"""Rappels ponctuels ou récurrents : /rappel ajouter|liste|supprimer."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from jarvis.utils.timeparse import add_months, parse_when

if TYPE_CHECKING:
    from jarvis.bot import Jarvis

log = logging.getLogger(__name__)

REPEAT_LABELS = {"quotidien": "tous les jours", "hebdo": "toutes les semaines", "mensuel": "tous les mois"}


def next_occurrence(due: datetime, repeat: str, now: datetime) -> datetime:
    """Prochaine échéance strictement future d'un rappel récurrent.

    Le calcul se fait en heure locale (l'arithmétique ZoneInfo travaille en
    heure murale) pour qu'un rappel à 9h reste à 9h après un changement d'heure.
    """
    base = due.astimezone(now.tzinfo)
    result, steps = base, 0
    while result <= now:
        steps += 1
        if repeat == "quotidien":
            result = base + timedelta(days=steps)
        elif repeat == "hebdo":
            result = base + timedelta(weeks=steps)
        elif repeat == "mensuel":
            result = add_months(base, steps)
        else:
            raise ValueError(f"Récurrence inconnue : {repeat}")
    return result


class SnoozeView(discord.ui.View):
    """Boutons « reporter » sous un rappel déclenché."""

    def __init__(self, cog: Reminders, user_id: int, channel_id: int, message: str) -> None:
        super().__init__(timeout=3600)
        self.cog = cog
        self.user_id = user_id
        self.channel_id = channel_id
        self.message = message

    async def _snooze(self, interaction: discord.Interaction, due: datetime) -> None:
        await self.cog.create(self.user_id, self.channel_id, self.message, due)
        for child in self.children:
            child.disabled = True  # type: ignore[attr-defined]
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"⏰ Reporté à <t:{int(due.timestamp())}:f>.", ephemeral=True)

    @discord.ui.button(label="+10 min", emoji="💤")
    async def ten_minutes(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._snooze(interaction, self.cog.bot.now() + timedelta(minutes=10))

    @discord.ui.button(label="+1 h", emoji="🕐")
    async def one_hour(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._snooze(interaction, self.cog.bot.now() + timedelta(hours=1))

    @discord.ui.button(label="Demain 9h", emoji="🌅")
    async def tomorrow(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._snooze(interaction, parse_when("demain 9h", self.cog.bot.now()))


class Reminders(commands.Cog):
    rappel = app_commands.Group(name="rappel", description="Gérer tes rappels")

    def __init__(self, bot: Jarvis) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.dispatch_due.start()

    async def cog_unload(self) -> None:
        self.dispatch_due.cancel()

    async def create(self, user_id: int, channel_id: int, message: str, due: datetime, repeat: str | None = None) -> int:
        return await self.bot.db.execute(
            "INSERT INTO reminders (user_id, channel_id, message, due_at, repeat, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, channel_id, message, int(due.timestamp()), repeat, int(self.bot.now().timestamp())),
        )

    async def due_today(self, user_id: int) -> list:
        """Rappels restants aujourd'hui (utilisé par le briefing du matin)."""
        now = self.bot.now()
        end_of_day = now.replace(hour=23, minute=59, second=59)
        return await self.bot.db.fetchall(
            "SELECT * FROM reminders WHERE user_id = ? AND due_at BETWEEN ? AND ? ORDER BY due_at",
            (user_id, int(now.timestamp()), int(end_of_day.timestamp())),
        )

    # --- Commandes -----------------------------------------------------------------

    @rappel.command(name="ajouter", description="Créer un rappel")
    @app_commands.describe(
        quand="Ex : dans 2h, demain 9h, vendredi 18h, 25/12 10h",
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
    ) -> None:
        due = parse_when(quand, self.bot.now())
        repeat = repeter.value if repeter else None
        reminder_id = await self.create(interaction.user.id, interaction.channel_id or 0, message, due, repeat)
        suffix = f" ({REPEAT_LABELS[repeat]})" if repeat else ""
        await interaction.response.send_message(
            f"✅ Rappel **#{reminder_id}** le <t:{int(due.timestamp())}:F> (<t:{int(due.timestamp())}:R>){suffix} :\n> {message}"
        )

    @rappel.command(name="liste", description="Voir tes rappels à venir")
    async def list_(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.fetchall(
            "SELECT * FROM reminders WHERE user_id = ? ORDER BY due_at LIMIT 25", (interaction.user.id,)
        )
        if not rows:
            await interaction.response.send_message("Aucun rappel prévu. 🌴", ephemeral=True)
            return
        lines = [
            f"**#{r['id']}** · <t:{r['due_at']}:f> (<t:{r['due_at']}:R>)"
            f"{' 🔁' if r['repeat'] else ''} — {r['message']}"
            for r in rows
        ]
        embed = discord.Embed(title="⏰ Tes rappels", description="\n".join(lines), color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @rappel.command(name="supprimer", description="Supprimer un rappel")
    @app_commands.describe(rappel="Le rappel à supprimer")
    async def delete(self, interaction: discord.Interaction, rappel: int) -> None:
        deleted = await self.bot.db.execute_rowcount(
            "DELETE FROM reminders WHERE id = ? AND user_id = ?", (rappel, interaction.user.id)
        )
        if not deleted:
            raise ValueError(f"Rappel #{rappel} introuvable.")
        await interaction.response.send_message(f"🗑️ Rappel #{rappel} supprimé.", ephemeral=True)

    @delete.autocomplete("rappel")
    async def reminder_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
        rows = await self.bot.db.fetchall(
            "SELECT id, message FROM reminders WHERE user_id = ? AND message LIKE ? ORDER BY due_at LIMIT 25",
            (interaction.user.id, f"%{current}%"),
        )
        return [app_commands.Choice(name=f"#{r['id']} — {r['message'][:80]}", value=r["id"]) for r in rows]

    # --- Boucle d'envoi ----------------------------------------------------------------

    @tasks.loop(seconds=20)
    async def dispatch_due(self) -> None:
        now = self.bot.now()
        rows = await self.bot.db.fetchall("SELECT * FROM reminders WHERE due_at <= ?", (int(now.timestamp()),))
        for row in rows:
            try:
                await self._send(row)
            except discord.HTTPException:
                log.exception("Impossible d'envoyer le rappel #%s", row["id"])

            if row["repeat"]:
                due = datetime.fromtimestamp(row["due_at"], tz=self.bot.config.tz)
                following = next_occurrence(due, row["repeat"], now)
                await self.bot.db.execute(
                    "UPDATE reminders SET due_at = ? WHERE id = ?", (int(following.timestamp()), row["id"])
                )
            else:
                await self.bot.db.execute("DELETE FROM reminders WHERE id = ?", (row["id"],))

    @dispatch_due.before_loop
    async def before_dispatch(self) -> None:
        await self.bot.wait_until_ready()

    async def _send(self, row) -> None:
        channel = await self.bot.get_text_channel(row["channel_id"])
        if channel is None:
            user = await self.bot.fetch_user(row["user_id"])
            channel = await user.create_dm()
        embed = discord.Embed(description=row["message"], color=discord.Color.gold())
        embed.set_author(name="⏰ Rappel")
        if row["repeat"]:
            embed.set_footer(text=f"Récurrent : {REPEAT_LABELS[row['repeat']]}")
        view = SnoozeView(self, row["user_id"], row["channel_id"], row["message"])
        await channel.send(content=f"<@{row['user_id']}>", embed=embed, view=view)


async def setup(bot: Jarvis) -> None:
    await bot.add_cog(Reminders(bot))
