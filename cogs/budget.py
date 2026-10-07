"""Budget : /depense, /revenu, /budget resume|graphique|historique|limite|export|supprimer"""

import csv
import io

import discord
import matplotlib.pyplot as plt
from discord import app_commands
from discord.ext import commands

from database import execute, query, query_one
from utils.dates import month_name, parse_day, parse_month
from utils.money import euros, to_cents

plt.switch_backend("Agg")  # dessiner des graphiques sans fenêtre

CATEGORIES = ["Courses", "Restaurant", "Transport", "Logement", "Factures", "Abonnements",
              "Loisirs", "Shopping", "Santé", "Cadeaux", "Voyage", "Autre"]
INCOME = "Revenu"


def month_totals(month):
    """(total dépensé, total des rentrées) du mois « 2026-10 », en centimes."""
    row = query_one(
        "SELECT SUM(CASE WHEN category != ? THEN amount END) AS spent, "
        "       SUM(CASE WHEN category  = ? THEN amount END) AS income "
        "FROM transactions WHERE day LIKE ?",
        INCOME, INCOME, f"{month}-%",
    )
    return row["spent"] or 0, row["income"] or 0


def spending_by_category(month):
    """{catégorie: total} des dépenses du mois, de la plus grosse à la plus petite."""
    rows = query(
        "SELECT category, SUM(amount) AS total FROM transactions "
        "WHERE day LIKE ? AND category != ? GROUP BY category ORDER BY total DESC",
        f"{month}-%", INCOME,
    )
    return {row["category"]: row["total"] for row in rows}


def budget_limits():
    return {row["category"]: row["amount"] for row in query("SELECT * FROM budget_limits")}


def progress_bar(ratio):
    filled = min(10, round(ratio * 10))
    return "▰" * filled + "▱" * (10 - filled)


def draw_chart(month, totals):
    """Graphique en anneau des dépenses, renvoyé sous forme d'image PNG."""
    figure, ax = plt.subplots(figsize=(8, 5), facecolor="#2b2d31")
    slices, _ = ax.pie(totals.values(), startangle=90, counterclock=False,
                       wedgeprops={"width": 0.4, "edgecolor": "#2b2d31"})
    total = sum(totals.values())
    ax.text(0, 0, euros(total), ha="center", va="center", fontsize=18, color="white", weight="bold")
    ax.set_title(f"Dépenses — {month_name(month)}", color="white", fontsize=14)
    labels = [f"{category} · {euros(amount)} ({amount / total:.0%})" for category, amount in totals.items()]
    legend = ax.legend(slices, labels, loc="center left", bbox_to_anchor=(1, 0.5), frameon=False)
    for text in legend.get_texts():
        text.set_color("white")

    image = io.BytesIO()
    figure.savefig(image, format="png", bbox_inches="tight", dpi=120)
    plt.close(figure)
    image.seek(0)
    return image


class Budget(commands.Cog):
    budget = app_commands.Group(name="budget", description="Ton budget")

    @app_commands.command(name="depense", description="Noter une dépense")
    @app_commands.describe(montant="Ex : 12,50", date="Facultatif. Ex : hier, 12/10")
    async def add_expense(self, interaction, montant: str, categorie: str, description: str = None, date: str = None):
        amount = to_cents(montant)
        category = categorie.strip().capitalize()
        day = parse_day(date)
        execute("INSERT INTO transactions (amount, category, description, day) VALUES (?, ?, ?, ?)",
                amount, category, description, day.isoformat())
        message = f"💸 {euros(amount)} en {category}" + (f" — {description}" if description else "")

        # Prévenir si on approche du plafond de la catégorie
        limit = budget_limits().get(category)
        if limit:
            spent = spending_by_category(day.strftime("%Y-%m")).get(category, 0)
            if spent >= limit:
                message += f"\n🚨 Plafond {category} dépassé : {euros(spent)} / {euros(limit)}"
            elif spent >= limit * 0.8:
                message += f"\n⚠️ Plafond {category} presque atteint : {euros(spent)} / {euros(limit)}"
        await interaction.response.send_message(message)

    @app_commands.command(name="revenu", description="Noter une rentrée d'argent")
    async def add_income(self, interaction, montant: str, description: str = None, date: str = None):
        amount = to_cents(montant)
        execute("INSERT INTO transactions (amount, category, description, day) VALUES (?, ?, ?, ?)",
                amount, INCOME, description, parse_day(date).isoformat())
        await interaction.response.send_message(f"💰 Rentrée de {euros(amount)} notée.")

    @add_expense.autocomplete("categorie")
    async def suggest_categories(self, interaction, typed: str):
        return [app_commands.Choice(name=c, value=c) for c in CATEGORIES if typed.lower() in c.lower()]

    @budget.command(name="resume", description="Résumé d'un mois")
    @app_commands.describe(mois="Facultatif. Ex : octobre, 09/2026")
    async def summary(self, interaction, mois: str = None):
        month = parse_month(mois)
        spent, income = month_totals(month)
        limits = budget_limits()

        lines = []
        for category, amount in spending_by_category(month).items():
            line = f"**{category}** — {euros(amount)}"
            if category in limits:
                ratio = amount / limits[category]
                line += f"\n`{progress_bar(ratio)}` {ratio:.0%} de {euros(limits[category])}"
            lines.append(line)

        embed = discord.Embed(title=f"💶 Budget — {month_name(month)}",
                              description="\n".join(lines) or "Aucune dépense.", color=discord.Color.green())
        embed.add_field(name="Dépenses", value=euros(spent))
        embed.add_field(name="Rentrées", value=euros(income))
        embed.add_field(name="Solde", value=euros(income - spent))
        await interaction.response.send_message(embed=embed)

    @budget.command(name="graphique", description="Graphique des dépenses d'un mois")
    async def chart(self, interaction, mois: str = None):
        month = parse_month(mois)
        totals = spending_by_category(month)
        if not totals:
            raise ValueError(f"Aucune dépense en {month_name(month)}.")
        await interaction.response.send_message(file=discord.File(draw_chart(month, totals), "budget.png"))

    @budget.command(name="historique", description="Dernières opérations")
    async def history(self, interaction):
        rows = query("SELECT * FROM transactions ORDER BY day DESC, id DESC LIMIT 20")
        lines = [f"`#{r['id']}` {r['day']} · **{euros(r['amount'])}** {r['category']} {r['description'] or ''}" for r in rows]
        await interaction.response.send_message("\n".join(lines) or "Aucune opération.", ephemeral=True)

    @budget.command(name="supprimer", description="Supprimer une opération (numéro dans /budget historique)")
    async def delete(self, interaction, numero: int):
        if execute("DELETE FROM transactions WHERE id = ?", numero).rowcount == 0:
            raise ValueError(f"Opération #{numero} introuvable.")
        await interaction.response.send_message(f"🗑️ Opération #{numero} supprimée.", ephemeral=True)

    @budget.command(name="limite", description="Plafond mensuel d'une catégorie (0 pour l'enlever)")
    async def set_limit(self, interaction, categorie: str, montant: str):
        category = categorie.strip().capitalize()
        if montant.strip() == "0":
            execute("DELETE FROM budget_limits WHERE category = ?", category)
            return await interaction.response.send_message(f"Plafond {category} supprimé.")
        amount = to_cents(montant)
        execute("INSERT OR REPLACE INTO budget_limits (category, amount) VALUES (?, ?)", category, amount)
        await interaction.response.send_message(f"🎯 Plafond {category} : {euros(amount)} par mois.")

    @budget.command(name="export", description="Télécharger les opérations d'un mois (CSV pour Excel)")
    async def export(self, interaction, mois: str = None):
        month = parse_month(mois)
        rows = query("SELECT * FROM transactions WHERE day LIKE ? ORDER BY day", f"{month}-%")
        if not rows:
            raise ValueError(f"Aucune opération en {month_name(month)}.")

        text = io.StringIO()
        writer = csv.writer(text, delimiter=";")  # « ; » pour qu'Excel en français l'ouvre correctement
        writer.writerow(["date", "categorie", "montant", "description"])
        for r in rows:
            writer.writerow([r["day"], r["category"], f"{r['amount'] / 100:.2f}".replace(".", ","), r["description"] or ""])
        file = discord.File(io.BytesIO(text.getvalue().encode("utf-8-sig")), f"budget-{month}.csv")
        await interaction.response.send_message(file=file, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Budget())
