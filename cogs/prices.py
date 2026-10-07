"""Suivi de prix.

Commandes : /prix ajouter, /prix liste, /prix cible, /prix verifier, /prix supprimer

- Un article peut être suivi dans plusieurs boutiques : ajoute-le plusieurs fois avec le même nom.
- Les prix sont vérifiés toutes les PRICE_CHECK_HOURS heures.
- Une alerte part dans le salon d'alertes quand un prix baisse ou passe sous ta cible.
- Un récapitulatif est envoyé chaque semaine (ou chaque jour, voir PRICE_RECAP_WEEKDAY).
"""

import asyncio
import logging
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from database import execute, query, query_one
from utils.dates import now
from utils.discord_helpers import find_channel, timestamp
from utils.money import format_euros, parse_amount
from utils.prices import PriceNotFound, extract_price, steam_app_id
from utils.web import NETWORK_ERRORS, download_json, download_page

log = logging.getLogger(__name__)

STEAM_API = "https://store.steampowered.com/api/appdetails"
SECONDS_BETWEEN_REQUESTS = 2  # pour ne pas bombarder les boutiques de requêtes
BLOCKED_STATUSES = [403, 429, 503]  # codes HTTP renvoyés quand un site bloque les robots


def shop_name(url: str) -> str:
    """« https://www.amazon.fr/dp/123 » → « amazon.fr »"""
    return urlparse(url).netloc.removeprefix("www.")


def parse_optional_amount(text: str) -> int | None:
    """« 0 » ou « 0,00 » veut dire « pas de montant » (pour enlever une cible)."""
    if text.strip() in ("0", "0,00", "0.00"):
        return None
    return parse_amount(text)


# --- Lecture des prix ----------------------------------------------------------------------------

async def fetch_price(url: str, selector: str | None) -> int:
    """Prix actuel d'une page, en centimes. Lève PriceNotFound (avec une explication) si impossible."""
    # Steam a une API officielle, plus fiable que la lecture de la page
    app_id = steam_app_id(url)
    if app_id is not None:
        return await fetch_steam_price(app_id)

    status, html = await download_page(url)
    if status in BLOCKED_STATUSES:
        raise PriceNotFound(f"Le site bloque les robots (HTTP {status}). Réessaie plus tard ou change de boutique.")
    if status >= 400:
        raise PriceNotFound(f"La page ne répond pas correctement (HTTP {status}).")

    # L'analyse du HTML peut prendre un moment : on la fait à côté pour ne pas bloquer le bot
    return await asyncio.to_thread(extract_price, html, selector)


async def fetch_steam_price(app_id: int) -> int:
    params = {"appids": app_id, "cc": "fr", "filters": "price_overview"}
    data = await download_json(STEAM_API, params)
    game = data.get(str(app_id), {}).get("data") or {}
    price_overview = game.get("price_overview")
    if not price_overview:
        raise PriceNotFound("Jeu gratuit ou prix indisponible sur Steam.")
    return int(price_overview["final"])  # Steam donne déjà le prix en centimes


async def update_offer(offer) -> tuple[int | None, int | None, str | None]:
    """Relit le prix d'une boutique et l'enregistre.

    Renvoie (ancien prix, nouveau prix, erreur). En cas d'échec, nouveau prix = None.
    """
    old_price = offer["price"]
    checked_at = timestamp(now())

    try:
        new_price = await fetch_price(offer["url"], offer["selector"])
    except (PriceNotFound, ValueError, KeyError, *NETWORK_ERRORS) as error:
        error_text = str(error) or error.__class__.__name__
        execute("UPDATE price_offers SET checked_at = ?, error = ? WHERE id = ?", checked_at, error_text, offer["id"])
        return old_price, None, error_text

    lowest = new_price
    if offer["lowest"] is not None and offer["lowest"] < new_price:
        lowest = offer["lowest"]

    execute(
        "UPDATE price_offers SET price = ?, lowest = ?, checked_at = ?, error = NULL WHERE id = ?",
        new_price, lowest, checked_at, offer["id"],
    )
    if new_price != old_price:
        execute(
            "INSERT INTO price_history (offer_id, price, checked_at) VALUES (?, ?, ?)",
            offer["id"], new_price, checked_at,
        )
    return old_price, new_price, None


# --- Affichage -------------------------------------------------------------------------------------

def format_offer(offer, is_cheapest: bool) -> str:
    """Une ligne par boutique : « 🥇 amazon.fr — 34,99 € (plus bas : 29,99 €) »"""
    link = f"[{shop_name(offer['url'])}]({offer['url']})"
    if offer["price"] is None:
        return f"❔ {link} — prix inconnu"

    line = f"{link} — **{format_euros(offer['price'])}**"
    if is_cheapest:
        line = "🥇 " + line
    if offer["lowest"] is not None and offer["lowest"] < offer["price"]:
        line += f" (plus bas : {format_euros(offer['lowest'])})"
    if offer["error"]:
        line += " ⚠️"
    return line


def build_price_list(user_id: int) -> discord.Embed:
    """Message listant tous les articles suivis, avec le prix dans chaque boutique."""
    embed = discord.Embed(title="🏷️ Suivi des prix", color=discord.Color.teal())
    items = query("SELECT * FROM price_items WHERE user_id = ? ORDER BY name COLLATE NOCASE", user_id)
    if not items:
        embed.description = "Aucun article suivi. Ajoute-en avec /prix ajouter."
        return embed

    for item in items[:25]:  # Discord limite un message à 25 sections
        # Les boutiques les moins chères d'abord, celles sans prix à la fin
        offers = query(
            "SELECT * FROM price_offers WHERE item_id = ? ORDER BY price IS NULL, price", item["id"]
        )
        lines = []
        for position, offer in enumerate(offers):
            is_cheapest = position == 0 and len(offers) > 1
            lines.append(format_offer(offer, is_cheapest))

        title = item["name"]
        if item["target"]:
            title += f" · 🎯 {format_euros(item['target'])}"
            best_price = offers[0]["price"] if offers else None
            if best_price is not None and best_price <= item["target"]:
                title += " ✅"
        embed.add_field(name=title, value="\n".join(lines)[:1024] or "Aucune boutique", inline=False)

    embed.set_footer(text=f"Vérification toutes les {config.PRICE_CHECK_HOURS} h · ⚠️ = dernière lecture en échec")
    return embed


# --- Commandes --------------------------------------------------------------------------------------

class Prices(commands.Cog):
    prix = app_commands.Group(name="prix", description="Suivre le prix d'articles")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Empêche deux vérifications de tourner en même temps (boucle automatique + /prix verifier)
        self.check_lock = asyncio.Lock()
        self.check_all_prices.start()
        self.price_recap.start()

    @prix.command(name="ajouter", description="Suivre un article (ou ajouter une boutique à un article existant)")
    @app_commands.describe(
        article="Nom de l'article (réutilise le même nom pour comparer plusieurs boutiques)",
        url="Lien de la page produit",
        prix_cible="Te prévenir quand le prix passe sous ce montant",
        selecteur="Sélecteur CSS du prix, si la détection automatique échoue",
    )
    async def add(
        self,
        interaction: discord.Interaction,
        article: str,
        url: str,
        prix_cible: str | None = None,
        selecteur: str | None = None,
    ):
        if not url.startswith(("http://", "https://")):
            raise ValueError("L'URL doit commencer par http:// ou https://")
        user_id = interaction.user.id
        name = article.strip()
        target = parse_amount(prix_cible) if prix_cible else None

        # Lire le prix peut prendre quelques secondes : on prévient Discord qu'on répondra plus tard
        await interaction.response.defer()

        # Article existant (même nom) ? Sinon on le crée.
        item = query_one(
            "SELECT * FROM price_items WHERE user_id = ? AND name = ? COLLATE NOCASE", user_id, name
        )
        if item is None:
            item_id = execute(
                "INSERT INTO price_items (user_id, name, target) VALUES (?, ?, ?)", user_id, name, target
            ).lastrowid
        else:
            item_id = item["id"]
            if target:
                execute("UPDATE price_items SET target = ? WHERE id = ?", target, item_id)

        offer_id = execute(
            "INSERT INTO price_offers (item_id, url, selector) VALUES (?, ?, ?)", item_id, url, selecteur
        ).lastrowid
        offer = query_one("SELECT * FROM price_offers WHERE id = ?", offer_id)
        _, price, error = await update_offer(offer)

        if error:
            message = (
                f"👀 **{name}** ajouté ({shop_name(url)}), mais je n'ai pas pu lire le prix :\n> {error}\n"
                "Je réessaierai à la prochaine vérification."
            )
        else:
            message = f"👀 Je surveille **{name}** sur {shop_name(url)} : actuellement **{format_euros(price)}**"
            if target:
                message += f" (cible : {format_euros(target)})"
        await interaction.followup.send(message)

    @prix.command(name="liste", description="Voir les prix actuels de tes articles")
    async def show_list(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=build_price_list(interaction.user.id))

    @prix.command(name="cible", description="Changer le prix cible d'un article (0 pour l'enlever)")
    async def set_target(self, interaction: discord.Interaction, article: int, montant: str):
        target = parse_optional_amount(montant)
        cursor = execute(
            "UPDATE price_items SET target = ? WHERE id = ? AND user_id = ?", target, article, interaction.user.id
        )
        if cursor.rowcount == 0:
            raise ValueError("Article introuvable.")
        if target:
            await interaction.response.send_message(f"🎯 Nouvelle cible : {format_euros(target)}", ephemeral=True)
        else:
            await interaction.response.send_message("🎯 Cible supprimée.", ephemeral=True)

    @prix.command(name="supprimer", description="Arrêter de suivre un article")
    async def delete(self, interaction: discord.Interaction, article: int):
        cursor = execute("DELETE FROM price_items WHERE id = ? AND user_id = ?", article, interaction.user.id)
        if cursor.rowcount == 0:
            raise ValueError("Article introuvable.")
        await interaction.response.send_message("🗑️ Article retiré du suivi.", ephemeral=True)

    @set_target.autocomplete("article")
    @delete.autocomplete("article")
    async def suggest_items(self, interaction: discord.Interaction, typed_text: str):
        items = query(
            "SELECT id, name FROM price_items WHERE user_id = ? AND name LIKE ? ORDER BY name LIMIT 25",
            interaction.user.id, f"%{typed_text}%",
        )
        return [app_commands.Choice(name=item["name"][:100], value=item["id"]) for item in items]

    @prix.command(name="verifier", description="Vérifier tous les prix maintenant")
    async def check_now(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.check_every_offer()
        await interaction.followup.send(embed=build_price_list(interaction.user.id))

    # --- Vérifications automatiques -------------------------------------------------------------

    async def check_every_offer(self):
        async with self.check_lock:
            offers = query(
                "SELECT price_offers.*, price_items.name, price_items.target, price_items.user_id "
                "FROM price_offers JOIN price_items ON price_items.id = price_offers.item_id "
                "ORDER BY price_offers.id"
            )
            for offer in offers:
                old_price, new_price, _ = await update_offer(offer)
                if new_price is not None and self.should_alert(old_price, new_price, offer["target"]):
                    await self.send_price_alert(offer, old_price, new_price)
                await asyncio.sleep(SECONDS_BETWEEN_REQUESTS)

    @staticmethod
    def should_alert(old_price: int | None, new_price: int, target: int | None) -> bool:
        """On prévient quand le prix baisse, ou quand il passe sous la cible pour la première fois."""
        price_dropped = old_price is not None and new_price < old_price
        target_just_reached = target is not None and new_price <= target and (old_price is None or old_price > target)
        return price_dropped or target_just_reached

    async def send_price_alert(self, offer, old_price: int | None, new_price: int):
        channel = await find_channel(self.bot, config.ALERTS_CHANNEL_ID)
        if channel is None:
            return

        target = offer["target"]
        if target is not None and new_price <= target:
            title = "🎯 Prix cible atteint !"
        else:
            title = "📉 Baisse de prix"

        if old_price:
            change = (new_price - old_price) / old_price
            price_text = f"~~{format_euros(old_price)}~~ → **{format_euros(new_price)}** ({change:+.0%})"
        else:
            price_text = f"**{format_euros(new_price)}**"

        embed = discord.Embed(title=title, url=offer["url"], color=discord.Color.green())
        embed.add_field(name="Article", value=offer["name"], inline=False)
        embed.add_field(name="Boutique", value=shop_name(offer["url"]))
        embed.add_field(name="Prix", value=price_text)
        if target:
            embed.add_field(name="Cible", value=format_euros(target))
        await channel.send(content=f"<@{offer['user_id']}>", embed=embed)

    @tasks.loop(hours=config.PRICE_CHECK_HOURS)
    async def check_all_prices(self):
        await self.check_every_offer()

    @tasks.loop(time=config.PRICE_RECAP_TIME)
    async def price_recap(self):
        # PRICE_RECAP_WEEKDAY = -1 : tous les jours ; sinon seulement le jour choisi
        if config.PRICE_RECAP_WEEKDAY >= 0 and now().weekday() != config.PRICE_RECAP_WEEKDAY:
            return
        channel = await find_channel(self.bot, config.ALERTS_CHANNEL_ID)
        if channel is None:
            return
        for row in query("SELECT DISTINCT user_id FROM price_items"):
            embed = build_price_list(row["user_id"])
            embed.title = "🏷️ Récap des prix"
            await channel.send(embed=embed)

    @check_all_prices.before_loop
    @price_recap.before_loop
    async def wait_until_ready(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Prices(bot))
