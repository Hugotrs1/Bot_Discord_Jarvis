"""To-do list.

Commandes : /todo ajouter, /todo liste, /todo fait, /todo supprimer
"""

import discord
from discord import app_commands
from discord.ext import commands

from database import execute, query
from utils.dates import now, parse_when
from utils.discord_helpers import timestamp

PRIORITY_ICONS = {1: "🔴", 2: "🟡", 3: "🟢"}


def open_todos(user_id: int) -> list:
    """Tâches pas encore faites : les plus prioritaires d'abord, puis par échéance."""
    return query(
        "SELECT * FROM todos WHERE user_id = ? AND done_at IS NULL "
        "ORDER BY priority, due_at IS NULL, due_at, id",
        user_id,
    )


def format_todo(todo) -> str:
    """Une ligne lisible pour une tâche : « 🔴 #3 Finir le rapport · dans 2 jours »"""
    line = f"{PRIORITY_ICONS[todo['priority']]} **#{todo['id']}** {todo['text']}"
    if todo["due_at"]:
        line += f" · <t:{todo['due_at']}:R>"
        if todo["due_at"] < timestamp(now()):
            line += " ⚠️ en retard"
    return line


class Todo(commands.Cog):
    todo = app_commands.Group(name="todo", description="Gérer ta liste de tâches")

    @todo.command(name="ajouter", description="Ajouter une tâche")
    @app_commands.describe(
        tache="La tâche",
        priorite="Priorité (normale par défaut)",
        echeance="Ex : vendredi, 25/12, dans 3 jours",
    )
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
    ):
        priority = priorite.value if priorite else 2
        due = None
        if echeance:
            due = timestamp(parse_when(echeance))

        cursor = execute(
            "INSERT INTO todos (user_id, text, priority, due_at) VALUES (?, ?, ?, ?)",
            interaction.user.id, tache, priority, due,
        )

        text = f"📝 Tâche **#{cursor.lastrowid}** ajoutée"
        if due:
            text += f" pour <t:{due}:D>"
        text += f" : {PRIORITY_ICONS[priority]} {tache}"
        await interaction.response.send_message(text)

    @todo.command(name="liste", description="Voir tes tâches en cours")
    async def show_list(self, interaction: discord.Interaction):
        todos = open_todos(interaction.user.id)
        if not todos:
            await interaction.response.send_message("Rien à faire, profite ! ☀️", ephemeral=True)
            return

        lines = [format_todo(todo) for todo in todos[:40]]
        embed = discord.Embed(title=f"📝 À faire ({len(todos)})", description="\n".join(lines), color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @todo.command(name="fait", description="Marquer une tâche comme faite")
    async def mark_done(self, interaction: discord.Interaction, tache: int):
        cursor = execute(
            "UPDATE todos SET done_at = ? WHERE id = ? AND user_id = ? AND done_at IS NULL",
            timestamp(now()), tache, interaction.user.id,
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Tâche #{tache} introuvable ou déjà faite.")

        remaining = len(open_todos(interaction.user.id))
        await interaction.response.send_message(f"✅ Tâche #{tache} terminée ! Plus que {remaining} tâche(s).")

    @todo.command(name="supprimer", description="Supprimer une tâche")
    async def delete(self, interaction: discord.Interaction, tache: int):
        cursor = execute("DELETE FROM todos WHERE id = ? AND user_id = ?", tache, interaction.user.id)
        if cursor.rowcount == 0:
            raise ValueError(f"Tâche #{tache} introuvable.")
        await interaction.response.send_message(f"🗑️ Tâche #{tache} supprimée.", ephemeral=True)

    @mark_done.autocomplete("tache")
    @delete.autocomplete("tache")
    async def suggest_todos(self, interaction: discord.Interaction, typed_text: str):
        """Propose les tâches en cours pendant que l'utilisateur tape."""
        todos = query(
            "SELECT id, text, priority FROM todos "
            "WHERE user_id = ? AND done_at IS NULL AND text LIKE ? ORDER BY priority, id LIMIT 25",
            interaction.user.id, f"%{typed_text}%",
        )
        return [
            app_commands.Choice(name=f"{PRIORITY_ICONS[todo['priority']]} #{todo['id']} — {todo['text'][:80]}", value=todo["id"])
            for todo in todos
        ]


async def setup(bot: commands.Bot):
    await bot.add_cog(Todo())
