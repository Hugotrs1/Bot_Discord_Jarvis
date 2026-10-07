"""Suivi de prix : une liste d'articles (avec une ou plusieurs boutiques chacun),
vérifiés régulièrement, avec alertes en cas de baisse et récapitulatif périodique.

/prix ajouter|liste|cible|verifier|supprimer
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from jarvis.utils.money import format_cents, parse_amount
from jarvis.utils.pricing import PriceNotFound, extract_price, steam_app_id

if TYPE_CHECKING:
    from jarvis.bot import Jarvis

log = logging.getLogger(__name__)

STEAM_API = "https://store.steampowered.com/api/appdetails"
DELAY_BETWEEN_REQUESTS = 2  # secondes, pour rester poli avec les boutiques


def shop_name(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.")


class Prices(commands.Cog):
    prix = app_commands.Group(name="prix", description="Suivre le prix d'articles")

    def __init__(self, bot: Jarvis) -> None:
        self.bot = bot
        self._lock = asyncio.Lock()

    async def cog_load(self) -> None:
        config = self.bot.config
        self.check_all.change_interval(hours=config.price_check_hours)
        self.recap.change_interval(time=config.price_recap_time.replace(tzinfo=config.tz))
        self.check_all.start()
        self.recap.start()

    async def cog_unload(self) -> None:
        self.check_all.cancel()
        self.recap.cancel()

    # --- Récupération des prix -------------------------------------------------------------

    async def fetch_price(self, url: str, selector: str | None) -> int:
        if app_id := steam_app_id(url):
            params = {"appids": app_id, "cc": "fr", "filters": "price_overview"}
            async with self.bot.session.get(STEAM_API, params=params) as response:
                data = await response.json(content_type=None)
            overview = (data.get(str(app_id), {}).get("data") or {}).get("price_overview")
            if not overview:
                raise PriceNotFound("Jeu gratuit ou prix indisponible sur Steam.")
            return int(overview["final"])

        async with self.bot.session.get(url) as response:
            if response.status in (403, 429, 503):
                raise PriceNotFound(f"Le site bloque les robots (HTTP {response.status}). Réessaie plus tard ou change de boutique.")
            response.raise_for_status()
            html = await response.text(errors="replace")
        return await asyncio.to_thread(extract_price, html, selector)

    async def check_offer(self, offer) -> tuple[int | None, int | None, str | None]:
        """Met à jour une offre. Renvoie (ancien prix, nouveau prix, erreur)."""
        now_ts = int(self.bot.now().timestamp())
        try:
            price = await self.fetch_price(offer["url"], offer["selector"])
        except (PriceNotFound, aiohttp.ClientError, TimeoutError, ValueError, KeyError) as exc:
            error = str(exc) or exc.__class__.__name__
            await self.bot.db.execute(
                "UPDATE price_offers SET last_checked = ?, last_error = ? WHERE id = ?", (now_ts, error, offer["id"])
            )
            return offer["last_cents"], None, error

        lowest = min(price, offer["lowest_cents"]) if offer["lowest_cents"] else price
        await self.bot.db.execute(
            "UPDATE price_offers SET last_cents = ?, lowest_cents = ?, last_checked = ?, last_error = NULL WHERE id = ?",
            (price, lowest, now_ts, offer["id"]),
        )
        if price != offer["last_cents"]:
            await self.bot.db.execute(
                "INSERT INTO price_history (offer_id, cents, checked_at) VALUES (?, ?, ?)", (offer["id"], price, now_ts)
            )
        return offer["last_cents"], price, None

    # --- Commandes -----------------------------------------------------------------------

    @prix.command(name="ajouter", description="Suivre un article (ou ajouter une boutique à un article existant)")
    @app_commands.describe(
        article="Nom de l'article (réutilise le même nom pour comparer plusieurs boutiques)",
        url="Lien de la page produit",
        prix_cible="Te prévenir quand le prix passe sous ce montant",
        selecteur="Sélecteur CSS du prix, si la détection automatique échoue",
    )
    async def add(
        self, interaction: discord.Interaction, article: str, url: str,
        prix_cible: str | None = None, selecteur: str | None = None,
    ) -> None:
        if not url.startswith(("http://", "https://")):
            raise ValueError("L'URL doit commencer par http:// ou https://")
        target = parse_amount(prix_cible) if prix_cible else None
        await interaction.response.defer()

        user_id = interaction.user.id
        item = await self.bot.db.fetchone(
            "SELECT * FROM price_items WHERE user_id = ? AND name = ? COLLATE NOCASE", (user_id, article.strip())
        )
        if item:
            item_id = item["id"]
            if target:
                await self.bot.db.execute("UPDATE price_items SET target_cents = ? WHERE id = ?", (target, item_id))
        else:
            item_id = await self.bot.db.execute(
                "INSERT INTO price_items (user_id, name, target_cents, created_at) VALUES (?, ?, ?, ?)",
                (user_id, article.strip(), target, int(self.bot.now().timestamp())),
            )

        offer_id = await self.bot.db.execute(
            "INSERT INTO price_offers (item_id, url, selector) VALUES (?, ?, ?)", (item_id, url, selecteur)
        )
        offer = await self.bot.db.fetchone("SELECT * FROM price_offers WHERE id = ?", (offer_id,))
        _, price, error = await self.check_offer(offer)

        name = article.strip()
        if error:
            message = (
                f"👀 **{name}** ajouté ({shop_name(url)}), mais je n'ai pas pu lire le prix :\n> {error}\n"
                "Je réessaierai à la prochaine vérification."
            )
        else:
            message = f"👀 Je surveille **{name}** sur {shop_name(url)} : actuellement **{format_cents(price)}**"
            if target:
                message += f" (cible : {format_cents(target)})"
        await interaction.followup.send(message)

    @prix.command(name="liste", description="Voir les prix actuels de tes articles")
    async def list_(self, interaction: discord.Interaction) -> None:
        embed = await self.build_list_embed(interaction.user.id)
        await interaction.response.send_message(embed=embed)

    async def build_list_embed(self, user_id: int) -> discord.Embed:
        items = await self.bot.db.fetchall(
            "SELECT * FROM price_items WHERE user_id = ? ORDER BY name COLLATE NOCASE", (user_id,)
        )
        embed = discord.Embed(title="🏷️ Suivi des prix", color=discord.Color.teal())
        if not items:
            embed.description = "Aucun article suivi. Ajoute-en avec `/prix ajouter`."
            return embed

        for item in items[:25]:
            offers = await self.bot.db.fetchall(
                "SELECT * FROM price_offers WHERE item_id = ? ORDER BY last_cents IS NULL, last_cents", (item["id"],)
            )
            lines = []
            for index, offer in enumerate(offers):
                if offer["last_cents"] is None:
                    lines.append(f"❔ [{shop_name(offer['url'])}]({offer['url']}) — prix inconnu")
                    continue
                medal = "🥇 " if index == 0 and len(offers) > 1 else ""
                line = f"{medal}[{shop_name(offer['url'])}]({offer['url']}) — **{format_cents(offer['last_cents'])}**"
                if offer["lowest_cents"] and offer["lowest_cents"] < offer["last_cents"]:
                    line += f" (plus bas : {format_cents(offer['lowest_cents'])})"
                if offer["last_error"]:
                    line += " ⚠️"
                lines.append(line)

            title = item["name"]
            if item["target_cents"]:
                best = offers[0]["last_cents"] if offers else None
                reached = best is not None and best <= item["target_cents"]
                title += f" · 🎯 {format_cents(item['target_cents'])}" + (" ✅" if reached else "")
            embed.add_field(name=title, value="\n".join(lines)[:1024] or "Aucune boutique", inline=False)

        embed.set_footer(text=f"Vérification toutes les {self.bot.config.price_check_hours} h · ⚠️ = dernière lecture en échec")
        return embed

    @prix.command(name="cible", description="Changer le prix cible d'un article (0 pour l'enlever)")
    async def set_target(self, interaction: discord.Interaction, article: int, montant: str) -> None:
        target = None if montant.strip() in ("0", "0,00", "0.00") else parse_amount(montant)
        updated = await self.bot.db.execute_rowcount(
            "UPDATE price_items SET target_cents = ? WHERE id = ? AND user_id = ?", (target, article, interaction.user.id)
        )
        if not updated:
            raise ValueError("Article introuvable.")
        text = f"🎯 Nouvelle cible : {format_cents(target)}" if target else "🎯 Cible supprimée."
        await interaction.response.send_message(text, ephemeral=True)

    @prix.command(name="supprimer", description="Arrêter de suivre un article")
    async def delete(self, interaction: discord.Interaction, article: int) -> None:
        deleted = await self.bot.db.execute_rowcount(
            "DELETE FROM price_items WHERE id = ? AND user_id = ?", (article, interaction.user.id)
        )
        if not deleted:
            raise ValueError("Article introuvable.")
        await interaction.response.send_message("🗑️ Article retiré du suivi.", ephemeral=True)

    @set_target.autocomplete("article")
    @delete.autocomplete("article")
    async def item_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
        rows = await self.bot.db.fetchall(
            "SELECT id, name FROM price_items WHERE user_id = ? AND name LIKE ? ORDER BY name LIMIT 25",
            (interaction.user.id, f"%{current}%"),
        )
        return [app_commands.Choice(name=r["name"][:100], value=r["id"]) for r in rows]

    @prix.command(name="verifier", description="Vérifier tous les prix maintenant")
    async def check_now(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self.run_checks()
        await interaction.followup.send(embed=await self.build_list_embed(interaction.user.id))

    # --- Vérifications périodiques -------------------------------------------------------------

    async def run_checks(self) -> None:
        async with self._lock:
            offers = await self.bot.db.fetchall(
                "SELECT o.*, i.name, i.target_cents, i.user_id FROM price_offers o "
                "JOIN price_items i ON i.id = o.item_id ORDER BY o.id"
            )
            for offer in offers:
                old, new, _ = await self.check_offer(offer)
                if new is not None and old is not None and new != old:
                    await self.notify_change(offer, old, new)
                elif new is not None and old is None and offer["target_cents"] and new <= offer["target_cents"]:
                    await self.notify_change(offer, None, new)
                await asyncio.sleep(DELAY_BETWEEN_REQUESTS)

    async def notify_change(self, offer, old: int | None, new: int) -> None:
        target = offer["target_cents"]
        target_reached = target is not None and new <= target and (old is None or old > target)
        if not target_reached and (old is None or new > old):
            return  # on ne signale que les baisses et les cibles atteintes

        channel = await self.bot.get_text_channel(self.bot.config.alerts_channel_id)
        if channel is None:
            return
        title = "🎯 Prix cible atteint !" if target_reached else "📉 Baisse de prix"
        embed = discord.Embed(title=title, url=offer["url"], color=discord.Color.green())
        embed.add_field(name="Article", value=offer["name"], inline=False)
        embed.add_field(name="Boutique", value=shop_name(offer["url"]))
        price_text = f"~~{format_cents(old)}~~ → **{format_cents(new)}**" if old else f"**{format_cents(new)}**"
        if old:
            price_text += f" ({(new - old) / old:+.0%})"
        embed.add_field(name="Prix", value=price_text)
        if target:
            embed.add_field(name="Cible", value=format_cents(target))
        await channel.send(content=f"<@{offer['user_id']}>", embed=embed)

    @tasks.loop(hours=6)  # remplacé au démarrage par PRICE_CHECK_HOURS
    async def check_all(self) -> None:
        await self.run_checks()

    @tasks.loop(hours=24)  # remplacé au démarrage par PRICE_RECAP_TIME
    async def recap(self) -> None:
        weekday = self.bot.config.price_recap_weekday
        if weekday >= 0 and self.bot.now().weekday() != weekday:
            return
        channel = await self.bot.get_text_channel(self.bot.config.alerts_channel_id)
        if channel is None:
            return
        users = await self.bot.db.fetchall("SELECT DISTINCT user_id FROM price_items")
        for row in users:
            embed = await self.build_list_embed(row["user_id"])
            embed.title = "🏷️ Récap des prix"
            await channel.send(embed=embed)

    @check_all.before_loop
    @recap.before_loop
    async def wait_ready(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: Jarvis) -> None:
    await bot.add_cog(Prices(bot))
