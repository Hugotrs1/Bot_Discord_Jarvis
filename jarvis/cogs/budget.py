"""Suivi du budget : /depense, /revenu, /budget resume|graphique|historique|limite|export|supprimer."""

from __future__ import annotations

import asyncio
import csv
import io
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from jarvis.utils.money import format_cents, parse_amount
from jarvis.utils.periods import month_label, parse_day, parse_month

if TYPE_CHECKING:
    from jarvis.bot import Jarvis

DEFAULT_CATEGORIES = [
    "Courses", "Restaurant", "Transport", "Logement", "Factures", "Abonnements",
    "Loisirs", "Shopping", "Santé", "Cadeaux", "Voyage", "Autre",
]
INCOME_CATEGORY = "Revenu"


def progress_bar(ratio: float, width: int = 10) -> str:
    filled = min(width, round(ratio * width))
    return "▰" * filled + "▱" * (width - filled)


def render_chart(month: str, totals: list[tuple[str, int]]) -> io.BytesIO:
    """Génère un graphique en anneau des dépenses par catégorie (PNG)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    total = sum(cents for _, cents in totals)

    fig, ax = plt.subplots(figsize=(8, 5), facecolor="#2b2d31")
    wedges, _ = ax.pie(
        [cents for _, cents in totals], startangle=90, counterclock=False,
        wedgeprops={"width": 0.38, "edgecolor": "#2b2d31"},
    )
    ax.text(0, 0, format_cents(total), ha="center", va="center", fontsize=18, color="white", weight="bold")
    ax.set_title(f"Dépenses — {month_label(month)}", color="white", fontsize=14)
    legend = ax.legend(
        wedges,
        [f"{category} · {format_cents(cents)} ({cents / total:.0%})" for category, cents in totals],
        loc="center left", bbox_to_anchor=(1, 0.5), frameon=False,
    )
    for text in legend.get_texts():
        text.set_color("white")

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", dpi=120)
    plt.close(fig)
    buffer.seek(0)
    return buffer


class Budget(commands.Cog):
    budget = app_commands.Group(name="budget", description="Suivre ton budget")

    def __init__(self, bot: Jarvis) -> None:
        self.bot = bot

    # --- Requêtes ----------------------------------------------------------------------

    async def month_totals(self, user_id: int, month: str) -> tuple[int, int]:
        """(total dépensé, total des rentrées) en centimes pour le mois « AAAA-MM »."""
        row = await self.bot.db.fetchone(
            "SELECT "
            "  COALESCE(SUM(CASE WHEN kind = 'depense' THEN amount_cents END), 0) AS spent, "
            "  COALESCE(SUM(CASE WHEN kind = 'revenu'  THEN amount_cents END), 0) AS income "
            "FROM transactions WHERE user_id = ? AND spent_on LIKE ?",
            (user_id, f"{month}-%"),
        )
        return (row["spent"], row["income"]) if row else (0, 0)

    async def category_totals(self, user_id: int, month: str) -> list[tuple[str, int]]:
        rows = await self.bot.db.fetchall(
            "SELECT category, SUM(amount_cents) AS total FROM transactions "
            "WHERE user_id = ? AND kind = 'depense' AND spent_on LIKE ? "
            "GROUP BY category ORDER BY total DESC",
            (user_id, f"{month}-%"),
        )
        return [(r["category"], r["total"]) for r in rows]

    async def limits(self, user_id: int) -> dict[str, int]:
        rows = await self.bot.db.fetchall(
            "SELECT category, limit_cents FROM budget_limits WHERE user_id = ?", (user_id,)
        )
        return {r["category"]: r["limit_cents"] for r in rows}

    async def _insert(self, user_id: int, kind: str, cents: int, category: str, description: str | None, day: str) -> int:
        return await self.bot.db.execute(
            "INSERT INTO transactions (user_id, kind, amount_cents, category, description, spent_on, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, kind, cents, category, description, day, int(self.bot.now().timestamp())),
        )

    # --- Saisie -------------------------------------------------------------------------

    @app_commands.command(name="depense", description="Enregistrer une dépense")
    @app_commands.describe(
        montant="Ex : 12,50", categorie="Catégorie (Courses, Restaurant…)",
        description="Détail facultatif", date="Ex : hier, 12/10 (aujourd'hui par défaut)",
    )
    async def add_expense(
        self, interaction: discord.Interaction, montant: str, categorie: str,
        description: str | None = None, date: str | None = None,
    ) -> None:
        cents = parse_amount(montant)
        category = categorie.strip().capitalize()
        day = parse_day(date, self.bot.now().date())
        tx_id = await self._insert(interaction.user.id, "depense", cents, category, description, day.isoformat())

        message = f"💸 **{format_cents(cents)}** en {category}" + (f" — {description}" if description else "")
        message += f" (#{tx_id}, {day:%d/%m})"

        month = day.strftime("%Y-%m")
        limit = (await self.limits(interaction.user.id)).get(category)
        if limit:
            spent = dict(await self.category_totals(interaction.user.id, month)).get(category, 0)
            ratio = spent / limit
            if ratio >= 1:
                message += f"\n🚨 Budget **{category}** dépassé : {format_cents(spent)} / {format_cents(limit)}"
            elif ratio >= 0.8:
                message += f"\n⚠️ Budget **{category}** à {ratio:.0%} : {format_cents(spent)} / {format_cents(limit)}"
        await interaction.response.send_message(message)

    @app_commands.command(name="revenu", description="Enregistrer une rentrée d'argent")
    @app_commands.describe(montant="Ex : 1500", description="Salaire, remboursement…", date="Ex : hier, 01/10")
    async def add_income(
        self, interaction: discord.Interaction, montant: str,
        description: str | None = None, date: str | None = None,
    ) -> None:
        cents = parse_amount(montant)
        day = parse_day(date, self.bot.now().date())
        tx_id = await self._insert(interaction.user.id, "revenu", cents, INCOME_CATEGORY, description, day.isoformat())
        await interaction.response.send_message(
            f"💰 Rentrée de **{format_cents(cents)}**" + (f" — {description}" if description else "") + f" (#{tx_id})"
        )

    @add_expense.autocomplete("categorie")
    async def category_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        rows = await self.bot.db.fetchall(
            "SELECT DISTINCT category FROM transactions WHERE user_id = ? AND kind = 'depense'", (interaction.user.id,)
        )
        categories = list(dict.fromkeys(DEFAULT_CATEGORIES + [r["category"] for r in rows]))
        return [app_commands.Choice(name=c, value=c) for c in categories if current.lower() in c.lower()][:25]

    # --- Consultation -------------------------------------------------------------------

    @budget.command(name="resume", description="Résumé du mois par catégorie")
    @app_commands.describe(mois="Ex : octobre, 09/2026, dernier (mois en cours par défaut)")
    async def summary(self, interaction: discord.Interaction, mois: str | None = None) -> None:
        month = parse_month(mois, self.bot.now().date())
        user_id = interaction.user.id
        spent, income = await self.month_totals(user_id, month)
        totals = await self.category_totals(user_id, month)
        limits = await self.limits(user_id)

        lines = []
        for category, total in totals:
            line = f"**{category}** — {format_cents(total)}"
            if limit := limits.get(category):
                ratio = total / limit
                flag = " 🚨" if ratio >= 1 else " ⚠️" if ratio >= 0.8 else ""
                line += f"\n`{progress_bar(ratio)}` {ratio:.0%} de {format_cents(limit)}{flag}"
            lines.append(line)
        for category, limit in limits.items():
            if category not in dict(totals):
                lines.append(f"**{category}** — 0,00 €\n`{progress_bar(0)}` 0% de {format_cents(limit)}")

        balance = income - spent
        embed = discord.Embed(
            title=f"💶 Budget — {month_label(month)}",
            description="\n".join(lines) or "Aucune dépense ce mois-ci.",
            color=discord.Color.green() if balance >= 0 else discord.Color.red(),
        )
        embed.add_field(name="Dépenses", value=format_cents(spent))
        embed.add_field(name="Rentrées", value=format_cents(income))
        embed.add_field(name="Solde", value=f"{'🟢' if balance >= 0 else '🔴'} {format_cents(balance)}")
        await interaction.response.send_message(embed=embed)

    @budget.command(name="graphique", description="Graphique des dépenses du mois")
    @app_commands.describe(mois="Ex : octobre, 09/2026, dernier")
    async def chart(self, interaction: discord.Interaction, mois: str | None = None) -> None:
        month = parse_month(mois, self.bot.now().date())
        totals = await self.category_totals(interaction.user.id, month)
        if not totals:
            raise ValueError(f"Aucune dépense en {month_label(month)}.")
        await interaction.response.defer()
        image = await asyncio.to_thread(render_chart, month, totals)
        await interaction.followup.send(file=discord.File(image, filename=f"budget-{month}.png"))

    @budget.command(name="historique", description="Dernières opérations")
    async def history(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.fetchall(
            "SELECT * FROM transactions WHERE user_id = ? ORDER BY spent_on DESC, id DESC LIMIT 20",
            (interaction.user.id,),
        )
        if not rows:
            raise ValueError("Aucune opération enregistrée.")
        lines = [
            f"`#{r['id']}` {r['spent_on'][8:10]}/{r['spent_on'][5:7]} · "
            f"{'➕' if r['kind'] == 'revenu' else '➖'} **{format_cents(r['amount_cents'])}** "
            f"{r['category']}" + (f" — {r['description']}" if r["description"] else "")
            for r in rows
        ]
        embed = discord.Embed(title="🧾 Dernières opérations", description="\n".join(lines), color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @budget.command(name="supprimer", description="Supprimer une opération (voir /budget historique)")
    async def delete(self, interaction: discord.Interaction, operation: int) -> None:
        deleted = await self.bot.db.execute_rowcount(
            "DELETE FROM transactions WHERE id = ? AND user_id = ?", (operation, interaction.user.id)
        )
        if not deleted:
            raise ValueError(f"Opération #{operation} introuvable.")
        await interaction.response.send_message(f"🗑️ Opération #{operation} supprimée.", ephemeral=True)

    @budget.command(name="limite", description="Fixer un plafond mensuel pour une catégorie (0 pour l'enlever)")
    async def set_limit(self, interaction: discord.Interaction, categorie: str, montant: str) -> None:
        category = categorie.strip().capitalize()
        if montant.strip() in ("0", "0,00", "0.00"):
            await self.bot.db.execute(
                "DELETE FROM budget_limits WHERE user_id = ? AND category = ?", (interaction.user.id, category)
            )
            await interaction.response.send_message(f"Plafond **{category}** supprimé.", ephemeral=True)
            return
        cents = parse_amount(montant)
        await self.bot.db.execute(
            "INSERT INTO budget_limits (user_id, category, limit_cents) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, category) DO UPDATE SET limit_cents = excluded.limit_cents",
            (interaction.user.id, category, cents),
        )
        await interaction.response.send_message(f"🎯 Plafond **{category}** : {format_cents(cents)} / mois.")

    set_limit.autocomplete("categorie")(category_autocomplete)

    @budget.command(name="export", description="Exporter les opérations d'un mois en CSV")
    @app_commands.describe(mois="Ex : octobre, 09/2026, dernier")
    async def export(self, interaction: discord.Interaction, mois: str | None = None) -> None:
        month = parse_month(mois, self.bot.now().date())
        rows = await self.bot.db.fetchall(
            "SELECT spent_on, kind, category, amount_cents, description FROM transactions "
            "WHERE user_id = ? AND spent_on LIKE ? ORDER BY spent_on, id",
            (interaction.user.id, f"{month}-%"),
        )
        if not rows:
            raise ValueError(f"Aucune opération en {month_label(month)}.")

        text = io.StringIO()
        writer = csv.writer(text, delimiter=";")  # « ; » : ouverture directe dans Excel en français
        writer.writerow(["date", "type", "categorie", "montant", "description"])
        for r in rows:
            amount = f"{r['amount_cents'] / 100:.2f}".replace(".", ",")
            writer.writerow([r["spent_on"], r["kind"], r["category"], amount, r["description"] or ""])
        data = io.BytesIO(text.getvalue().encode("utf-8-sig"))
        await interaction.response.send_message(
            f"📤 {len(rows)} opération(s) en {month_label(month)}",
            file=discord.File(data, filename=f"budget-{month}.csv"),
            ephemeral=True,
        )


async def setup(bot: Jarvis) -> None:
    await bot.add_cog(Budget(bot))
