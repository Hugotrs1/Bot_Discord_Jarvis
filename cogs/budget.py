"""Suivi du budget.

Commandes : /depense, /revenu,
            /budget resume, /budget graphique, /budget historique,
            /budget limite, /budget export, /budget supprimer
"""

import asyncio
import csv
import io

import discord
import matplotlib.pyplot as plt
from discord import app_commands
from discord.ext import commands

from database import execute, query, query_one
from utils.dates import month_label, parse_day, parse_month
from utils.discord_helpers import progress_bar
from utils.money import format_euros, parse_amount

# Dessine les graphiques en mémoire, sans ouvrir de fenêtre
plt.switch_backend("Agg")

DEFAULT_CATEGORIES = [
    "Courses", "Restaurant", "Transport", "Logement", "Factures", "Abonnements",
    "Loisirs", "Shopping", "Santé", "Cadeaux", "Voyage", "Autre",
]
INCOME_CATEGORY = "Revenu"
WARNING_RATIO = 0.8  # on prévient à 80 % du plafond


# --- Lecture des données -------------------------------------------------------------------

def month_totals(user_id: int, month: str) -> tuple[int, int]:
    """(total dépensé, total des rentrées) en centimes pour un mois « AAAA-MM »."""
    month_pattern = f"{month}-%"  # « 2026-10-% » correspond à tous les jours d'octobre 2026
    spent = query_one(
        "SELECT SUM(amount) AS total FROM transactions WHERE user_id = ? AND kind = 'depense' AND day LIKE ?",
        user_id, month_pattern,
    )["total"]
    income = query_one(
        "SELECT SUM(amount) AS total FROM transactions WHERE user_id = ? AND kind = 'revenu' AND day LIKE ?",
        user_id, month_pattern,
    )["total"]
    # SUM renvoie NULL (None) s'il n'y a aucune ligne
    return spent or 0, income or 0


def spending_by_category(user_id: int, month: str) -> dict[str, int]:
    """Dépenses du mois par catégorie, de la plus grosse à la plus petite."""
    rows = query(
        "SELECT category, SUM(amount) AS total FROM transactions "
        "WHERE user_id = ? AND kind = 'depense' AND day LIKE ? "
        "GROUP BY category ORDER BY total DESC",
        user_id, f"{month}-%",
    )
    return {row["category"]: row["total"] for row in rows}


def budget_limits(user_id: int) -> dict[str, int]:
    """Plafonds mensuels : {catégorie: montant en centimes}."""
    rows = query("SELECT category, amount FROM budget_limits WHERE user_id = ?", user_id)
    return {row["category"]: row["amount"] for row in rows}


def clean_category(text: str) -> str:
    """« courses » → « Courses » (pour éviter d'avoir deux catégories pour la même chose)."""
    return text.strip().capitalize()


# --- Graphique -----------------------------------------------------------------------------

def draw_chart(month: str, totals: dict[str, int]) -> io.BytesIO:
    """Dessine un graphique en anneau des dépenses et le renvoie sous forme d'image PNG."""
    total = sum(totals.values())

    figure, axes = plt.subplots(figsize=(8, 5), facecolor="#2b2d31")  # fond gris de Discord
    slices, _ = axes.pie(
        list(totals.values()),
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.38, "edgecolor": "#2b2d31"},  # width < 1 : un anneau plutôt qu'un camembert
    )

    # Total au centre de l'anneau, titre au-dessus
    axes.text(0, 0, format_euros(total), ha="center", va="center", fontsize=18, color="white", weight="bold")
    axes.set_title(f"Dépenses — {month_label(month)}", color="white", fontsize=14)

    # Légende à droite : « Courses · 320,50 € (57%) »
    labels = []
    for category, amount in totals.items():
        labels.append(f"{category} · {format_euros(amount)} ({amount / total:.0%})")
    legend = axes.legend(slices, labels, loc="center left", bbox_to_anchor=(1, 0.5), frameon=False)
    for text in legend.get_texts():
        text.set_color("white")

    image = io.BytesIO()
    figure.savefig(image, format="png", bbox_inches="tight", dpi=120)
    plt.close(figure)
    image.seek(0)  # revient au début du fichier pour que Discord puisse le lire
    return image


# --- Commandes ------------------------------------------------------------------------------

class Budget(commands.Cog):
    budget = app_commands.Group(name="budget", description="Suivre ton budget")

    @app_commands.command(name="depense", description="Enregistrer une dépense")
    @app_commands.describe(
        montant="Ex : 12,50",
        categorie="Courses, Restaurant…",
        description="Détail facultatif",
        date="Ex : hier, 12/10 (aujourd'hui par défaut)",
    )
    async def add_expense(
        self,
        interaction: discord.Interaction,
        montant: str,
        categorie: str,
        description: str | None = None,
        date: str | None = None,
    ):
        user_id = interaction.user.id
        amount = parse_amount(montant)
        category = clean_category(categorie)
        day = parse_day(date)

        cursor = execute(
            "INSERT INTO transactions (user_id, kind, amount, category, description, day) VALUES (?, 'depense', ?, ?, ?, ?)",
            user_id, amount, category, description, day.isoformat(),
        )

        message = f"💸 **{format_euros(amount)}** en {category}"
        if description:
            message += f" — {description}"
        message += f" (#{cursor.lastrowid}, {day:%d/%m})"
        message += self.limit_warning(user_id, category, day.strftime("%Y-%m"))
        await interaction.response.send_message(message)

    def limit_warning(self, user_id: int, category: str, month: str) -> str:
        """Texte d'alerte si la catégorie approche ou dépasse son plafond (sinon texte vide)."""
        limit = budget_limits(user_id).get(category)
        if not limit:
            return ""
        spent = spending_by_category(user_id, month).get(category, 0)
        ratio = spent / limit
        if ratio >= 1:
            return f"\n🚨 Budget **{category}** dépassé : {format_euros(spent)} / {format_euros(limit)}"
        if ratio >= WARNING_RATIO:
            return f"\n⚠️ Budget **{category}** à {ratio:.0%} : {format_euros(spent)} / {format_euros(limit)}"
        return ""

    @app_commands.command(name="revenu", description="Enregistrer une rentrée d'argent")
    @app_commands.describe(montant="Ex : 1500", description="Salaire, remboursement…", date="Ex : hier, 01/10")
    async def add_income(
        self,
        interaction: discord.Interaction,
        montant: str,
        description: str | None = None,
        date: str | None = None,
    ):
        amount = parse_amount(montant)
        day = parse_day(date)
        cursor = execute(
            "INSERT INTO transactions (user_id, kind, amount, category, description, day) VALUES (?, 'revenu', ?, ?, ?, ?)",
            interaction.user.id, amount, INCOME_CATEGORY, description, day.isoformat(),
        )

        message = f"💰 Rentrée de **{format_euros(amount)}**"
        if description:
            message += f" — {description}"
        message += f" (#{cursor.lastrowid})"
        await interaction.response.send_message(message)

    async def suggest_categories(self, interaction: discord.Interaction, typed_text: str):
        """Propose les catégories par défaut + celles que l'utilisateur a déjà utilisées."""
        rows = query(
            "SELECT DISTINCT category FROM transactions WHERE user_id = ? AND kind = 'depense'",
            interaction.user.id,
        )
        categories = list(DEFAULT_CATEGORIES)
        for row in rows:
            if row["category"] not in categories:
                categories.append(row["category"])

        matching = [category for category in categories if typed_text.lower() in category.lower()]
        return [app_commands.Choice(name=category, value=category) for category in matching[:25]]

    @budget.command(name="resume", description="Résumé du mois par catégorie")
    @app_commands.describe(mois="Ex : octobre, 09/2026, dernier (mois en cours par défaut)")
    async def summary(self, interaction: discord.Interaction, mois: str | None = None):
        user_id = interaction.user.id
        month = parse_month(mois)
        spent, income = month_totals(user_id, month)
        totals = spending_by_category(user_id, month)
        limits = budget_limits(user_id)

        lines = []
        for category, amount in totals.items():
            line = f"**{category}** — {format_euros(amount)}"
            if category in limits:
                line += "\n" + self.limit_line(amount, limits[category])
            lines.append(line)

        # Catégories avec un plafond mais aucune dépense ce mois-ci
        for category, limit in limits.items():
            if category not in totals:
                lines.append(f"**{category}** — {format_euros(0)}\n" + self.limit_line(0, limit))

        balance = income - spent
        embed = discord.Embed(
            title=f"💶 Budget — {month_label(month)}",
            description="\n".join(lines) or "Aucune dépense ce mois-ci.",
            color=discord.Color.green() if balance >= 0 else discord.Color.red(),
        )
        embed.add_field(name="Dépenses", value=format_euros(spent))
        embed.add_field(name="Rentrées", value=format_euros(income))
        embed.add_field(name="Solde", value=("🟢 " if balance >= 0 else "🔴 ") + format_euros(balance))
        await interaction.response.send_message(embed=embed)

    def limit_line(self, spent: int, limit: int) -> str:
        """« ▰▰▰▰▰▰▰▰▱▱ 82% de 150,00 € ⚠️ »"""
        ratio = spent / limit
        line = f"`{progress_bar(ratio)}` {ratio:.0%} de {format_euros(limit)}"
        if ratio >= 1:
            line += " 🚨"
        elif ratio >= WARNING_RATIO:
            line += " ⚠️"
        return line

    @budget.command(name="graphique", description="Graphique des dépenses du mois")
    @app_commands.describe(mois="Ex : octobre, 09/2026, dernier")
    async def chart(self, interaction: discord.Interaction, mois: str | None = None):
        month = parse_month(mois)
        totals = spending_by_category(interaction.user.id, month)
        if not totals:
            raise ValueError(f"Aucune dépense en {month_label(month)}.")

        await interaction.response.defer()
        # Le dessin prend un peu de temps : on le fait à côté pour ne pas bloquer le bot
        image = await asyncio.to_thread(draw_chart, month, totals)
        await interaction.followup.send(file=discord.File(image, filename=f"budget-{month}.png"))

    @budget.command(name="historique", description="Dernières opérations")
    async def history(self, interaction: discord.Interaction):
        rows = query(
            "SELECT * FROM transactions WHERE user_id = ? ORDER BY day DESC, id DESC LIMIT 20",
            interaction.user.id,
        )
        if not rows:
            raise ValueError("Aucune opération enregistrée.")

        lines = []
        for row in rows:
            year, month, day = row["day"].split("-")
            sign = "➕" if row["kind"] == "revenu" else "➖"
            line = f"`#{row['id']}` {day}/{month} · {sign} **{format_euros(row['amount'])}** {row['category']}"
            if row["description"]:
                line += f" — {row['description']}"
            lines.append(line)

        embed = discord.Embed(title="🧾 Dernières opérations", description="\n".join(lines), color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @budget.command(name="supprimer", description="Supprimer une opération (numéro visible dans /budget historique)")
    async def delete(self, interaction: discord.Interaction, operation: int):
        cursor = execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", operation, interaction.user.id)
        if cursor.rowcount == 0:
            raise ValueError(f"Opération #{operation} introuvable.")
        await interaction.response.send_message(f"🗑️ Opération #{operation} supprimée.", ephemeral=True)

    @budget.command(name="limite", description="Fixer un plafond mensuel pour une catégorie (0 pour l'enlever)")
    async def set_limit(self, interaction: discord.Interaction, categorie: str, montant: str):
        user_id = interaction.user.id
        category = clean_category(categorie)

        if montant.strip() in ("0", "0,00", "0.00"):
            execute("DELETE FROM budget_limits WHERE user_id = ? AND category = ?", user_id, category)
            await interaction.response.send_message(f"Plafond **{category}** supprimé.", ephemeral=True)
            return

        amount = parse_amount(montant)
        # INSERT OR REPLACE : crée le plafond, ou remplace l'ancien s'il existe déjà
        execute(
            "INSERT OR REPLACE INTO budget_limits (user_id, category, amount) VALUES (?, ?, ?)",
            user_id, category, amount,
        )
        await interaction.response.send_message(f"🎯 Plafond **{category}** : {format_euros(amount)} / mois.")

    @budget.command(name="export", description="Exporter les opérations d'un mois (fichier CSV pour Excel)")
    @app_commands.describe(mois="Ex : octobre, 09/2026, dernier")
    async def export(self, interaction: discord.Interaction, mois: str | None = None):
        month = parse_month(mois)
        rows = query(
            "SELECT * FROM transactions WHERE user_id = ? AND day LIKE ? ORDER BY day, id",
            interaction.user.id, f"{month}-%",
        )
        if not rows:
            raise ValueError(f"Aucune opération en {month_label(month)}.")

        text = io.StringIO()
        writer = csv.writer(text, delimiter=";")  # « ; » : Excel en français l'ouvre directement
        writer.writerow(["date", "type", "categorie", "montant", "description"])
        for row in rows:
            amount = f"{row['amount'] / 100:.2f}".replace(".", ",")  # 12.5 → « 12,50 »
            writer.writerow([row["day"], row["kind"], row["category"], amount, row["description"] or ""])

        # « utf-8-sig » ajoute une marque au début du fichier pour qu'Excel affiche bien les accents
        data = io.BytesIO(text.getvalue().encode("utf-8-sig"))
        await interaction.response.send_message(
            f"📤 {len(rows)} opération(s) en {month_label(month)}",
            file=discord.File(data, filename=f"budget-{month}.csv"),
            ephemeral=True,
        )


# Les deux commandes qui demandent une catégorie utilisent les mêmes suggestions
Budget.add_expense.autocomplete("categorie")(Budget.suggest_categories)
Budget.set_limit.autocomplete("categorie")(Budget.suggest_categories)


async def setup(bot: commands.Bot):
    await bot.add_cog(Budget())
