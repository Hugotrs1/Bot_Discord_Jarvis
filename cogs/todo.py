"""To-do list : /todo ajouter, /todo liste, /todo fait, /todo supprimer"""

from discord import app_commands
from discord.ext import commands

from database import execute, query
from utils.dates import now, parse_when

PRIORITY_ICONS = {1: "🔴", 2: "🟡", 3: "🟢"}


def open_todos():
    """Tâches pas encore faites, les plus importantes d'abord."""
    return query("SELECT * FROM todos WHERE done = 0 ORDER BY priority, due_at IS NULL, due_at")


def todo_line(todo):
    line = f"{PRIORITY_ICONS[todo['priority']]} **#{todo['id']}** {todo['text']}"
    if todo["due_at"]:
        line += f" · <t:{todo['due_at']}:R>"
        if todo["due_at"] < now().timestamp():
            line += " ⚠️ en retard"
    return line


class Todo(commands.Cog):
    todo = app_commands.Group(name="todo", description="Ta liste de tâches")

    @todo.command(name="ajouter", description="Ajouter une tâche")
    @app_commands.describe(echeance="Facultatif. Ex : vendredi, 25/12, dans 3 jours")
    @app_commands.choices(priorite=[
        app_commands.Choice(name="🔴 Haute", value=1),
        app_commands.Choice(name="🟡 Normale", value=2),
        app_commands.Choice(name="🟢 Basse", value=3),
    ])
    async def add(self, interaction, tache: str, priorite: int = 2, echeance: str = None):
        due = int(parse_when(echeance).timestamp()) if echeance else None
        todo_id = execute(
            "INSERT INTO todos (text, priority, due_at) VALUES (?, ?, ?)", tache, priorite, due
        ).lastrowid
        await interaction.response.send_message(f"📝 Tâche #{todo_id} ajoutée : {PRIORITY_ICONS[priorite]} {tache}")

    @todo.command(name="liste", description="Voir tes tâches")
    async def show(self, interaction):
        todos = open_todos()
        if not todos:
            return await interaction.response.send_message("Rien à faire, profite ! ☀️", ephemeral=True)
        await interaction.response.send_message("\n".join(todo_line(t) for t in todos), ephemeral=True)

    @todo.command(name="fait", description="Marquer une tâche comme faite")
    async def done(self, interaction, numero: int):
        if execute("UPDATE todos SET done = 1 WHERE id = ? AND done = 0", numero).rowcount == 0:
            raise ValueError(f"Tâche #{numero} introuvable.")
        await interaction.response.send_message(f"✅ Tâche #{numero} terminée ! Plus que {len(open_todos())} tâche(s).")

    @todo.command(name="supprimer", description="Supprimer une tâche")
    async def delete(self, interaction, numero: int):
        if execute("DELETE FROM todos WHERE id = ?", numero).rowcount == 0:
            raise ValueError(f"Tâche #{numero} introuvable.")
        await interaction.response.send_message(f"🗑️ Tâche #{numero} supprimée.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Todo())
