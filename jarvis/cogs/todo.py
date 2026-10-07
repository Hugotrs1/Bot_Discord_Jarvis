"""To-do list : /todo ajouter|liste|fait|supprimer."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from jarvis.utils.timeparse import parse_when

if TYPE_CHECKING:
    from jarvis.bot import Jarvis

PRIORITIES = {1: "🔴", 2: "🟡", 3: "🟢"}


def format_todo(row, now_ts: int) -> str:
    line = f"{PRIORITIES[row['priority']]} **#{row['id']}** {row['text']}"
    if row["due_at"]:
        late = " ⚠️ en retard" if row["due_at"] < now_ts else ""
        line += f" · <t:{row['due_at']}:R>{late}"
    return line


class Todo(commands.Cog):
    todo = app_commands.Group(name="todo", description="Gérer ta liste de tâches")

    def __init__(self, bot: Jarvis) -> None:
        self.bot = bot

    async def open_todos(self, user_id: int) -> list:
        return await self.bot.db.fetchall(
            "SELECT * FROM todos WHERE user_id = ? AND done_at IS NULL "
            "ORDER BY priority, due_at IS NULL, due_at, id",
            (user_id,),
        )

    @todo.command(name="ajouter", description="Ajouter une tâche")
    @app_commands.describe(tache="La tâche", priorite="Priorité (normale par défaut)", echeance="Ex : vendredi, 25/12, dans 3 jours")
    @app_commands.choices(priorite=[
        app_commands.Choice(name="🔴 Haute", value=1),
        app_commands.Choice(name="🟡 Normale", value=2),
        app_commands.Choice(name="🟢 Basse", value=3),
    ])
    async def add(
        self,
        interaction: discord.Interaction,
        tache: app_commands.Range[str, 1, 300],
        priorite: app_commands.Choice[int] | None = None,
        echeance: str | None = None,
    ) -> None:
        due = int(parse_when(echeance, self.bot.now()).timestamp()) if echeance else None
        priority = priorite.value if priorite else 2
        todo_id = await self.bot.db.execute(
            "INSERT INTO todos (user_id, text, priority, due_at, created_at) VALUES (?, ?, ?, ?, ?)",
            (interaction.user.id, tache, priority, due, int(self.bot.now().timestamp())),
        )
        when = f" pour <t:{due}:D>" if due else ""
        await interaction.response.send_message(f"📝 Tâche **#{todo_id}** ajoutée{when} : {PRIORITIES[priority]} {tache}")

    @todo.command(name="liste", description="Voir tes tâches en cours")
    async def list_(self, interaction: discord.Interaction) -> None:
        rows = await self.open_todos(interaction.user.id)
        if not rows:
            await interaction.response.send_message("Rien à faire, profite ! ☀️", ephemeral=True)
            return
        now_ts = int(self.bot.now().timestamp())
        embed = discord.Embed(
            title=f"📝 À faire ({len(rows)})",
            description="\n".join(format_todo(r, now_ts) for r in rows[:40]),
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @todo.command(name="fait", description="Marquer une tâche comme faite")
    async def done(self, interaction: discord.Interaction, tache: int) -> None:
        updated = await self.bot.db.execute_rowcount(
            "UPDATE todos SET done_at = ? WHERE id = ? AND user_id = ? AND done_at IS NULL",
            (int(self.bot.now().timestamp()), tache, interaction.user.id),
        )
        if not updated:
            raise ValueError(f"Tâche #{tache} introuvable ou déjà faite.")
        remaining = len(await self.open_todos(interaction.user.id))
        await interaction.response.send_message(f"✅ Tâche #{tache} terminée ! Plus que {remaining} tâche(s).")

    @todo.command(name="supprimer", description="Supprimer une tâche")
    async def delete(self, interaction: discord.Interaction, tache: int) -> None:
        deleted = await self.bot.db.execute_rowcount(
            "DELETE FROM todos WHERE id = ? AND user_id = ?", (tache, interaction.user.id)
        )
        if not deleted:
            raise ValueError(f"Tâche #{tache} introuvable.")
        await interaction.response.send_message(f"🗑️ Tâche #{tache} supprimée.", ephemeral=True)

    @done.autocomplete("tache")
    @delete.autocomplete("tache")
    async def todo_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
        rows = await self.bot.db.fetchall(
            "SELECT id, text, priority FROM todos WHERE user_id = ? AND done_at IS NULL AND text LIKE ? "
            "ORDER BY priority, id LIMIT 25",
            (interaction.user.id, f"%{current}%"),
        )
        return [
            app_commands.Choice(name=f"{PRIORITIES[r['priority']]} #{r['id']} — {r['text'][:80]}", value=r["id"])
            for r in rows
        ]


async def setup(bot: Jarvis) -> None:
    await bot.add_cog(Todo(bot))
