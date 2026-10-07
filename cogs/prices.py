"""Suivi de prix : /prix ajouter|liste|cible|verifier|supprimer

Chaque article peut avoir plusieurs boutiques (ajoute le même nom avec une autre URL).
Les prix sont vérifiés régulièrement ; une alerte part si un prix baisse ou passe sous ta cible.
"""

import asyncio
import re
from datetime import time
from urllib.parse import urlparse

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from database import execute, query, query_one
from utils.dates import now
from utils.money import euros, to_cents
from utils.prices import find_price
from utils.web import get_json, get_page

CHECK_EVERY_HOURS = 6
WEEKLY_RECAP_DAY = 0  # 0 = lundi
WEEKLY_RECAP_TIME = time(9, 0, tzinfo=config.TIMEZONE)


async def fetch_price(url, selector=None):
    """Prix actuel en centimes. Lève ValueError (avec une explication) si on n'y arrive pas."""
    steam = re.search(r"store\.steampowered\.com/app/(\d+)", url)
    if steam:  # Steam a une API officielle, plus fiable que la page
        app_id = steam[1]
        data = await get_json("https://store.steampowered.com/api/appdetails",
                              {"appids": app_id, "cc": "fr", "filters": "price_overview"})
        price = (data[app_id].get("data") or {}).get("price_overview")
        if not price:
            raise ValueError("Pas de prix sur Steam (jeu gratuit ?).")
        return price["final"]

    status, html = await get_page(url)
    if status != 200:
        raise ValueError(f"Le site a répondu « {status} » (il bloque peut-être les robots).")
    price = find_price(html, selector)
    if price is None:
        raise ValueError("Prix introuvable sur la page : réessaie avec l'option « selecteur ».")
    return price


async def check_offer(offer):
    """Met à jour le prix d'une boutique. Renvoie le nouveau prix, ou None en cas d'échec."""
    try:
        price = await fetch_price(offer["url"], offer["selector"])
    except (ValueError, aiohttp.ClientError, TimeoutError) as error:
        execute("UPDATE price_offers SET error = ? WHERE id = ?", str(error) or "Erreur réseau", offer["id"])
        return None
    lowest = min(price, offer["lowest"] or price)
    execute("UPDATE price_offers SET price = ?, lowest = ?, error = NULL WHERE id = ?", price, lowest, offer["id"])
    return price


def shop_name(url):
    return urlparse(url).netloc.removeprefix("www.")


def prices_embed():
    embed = discord.Embed(title="🏷️ Suivi des prix", color=discord.Color.teal())
    for item in query("SELECT * FROM price_items ORDER BY name"):
        offers = query("SELECT * FROM price_offers WHERE item_id = ? ORDER BY price IS NULL, price", item["id"])
        lines = []
        for offer in offers:
            shop = f"[{shop_name(offer['url'])}]({offer['url']})"
            if offer["price"] is None:
                lines.append(f"❔ {shop} — {offer['error'] or 'pas encore vérifié'}")
                continue
            line = f"{shop} — **{euros(offer['price'])}**"
            if offer["lowest"] < offer["price"]:
                line += f" (plus bas vu : {euros(offer['lowest'])})"
            if offer["error"]:
                line += " ⚠️"
            lines.append(line)

        title = item["name"] + (f" · 🎯 {euros(item['target'])}" if item["target"] else "")
        embed.add_field(name=title, value="\n".join(lines)[:1024] or "Aucune boutique", inline=False)

    if not embed.fields:
        embed.description = "Aucun article suivi. Ajoute-en avec /prix ajouter."
    embed.set_footer(text="Boutique la moins chère en premier · ⚠️ = dernière vérification ratée")
    return embed


class Prices(commands.Cog):
    prix = app_commands.Group(name="prix", description="Suivi de prix")

    def __init__(self, bot):
        self.bot = bot
        self.check_all_prices.start()
        self.weekly_recap.start()

    @prix.command(name="ajouter", description="Suivre un article (même nom = boutique supplémentaire)")
    @app_commands.describe(
        url="Lien de la page produit",
        prix_cible="Facultatif : te prévenir sous ce prix",
        selecteur="Facultatif : sélecteur CSS du prix si la détection automatique échoue",
    )
    async def add(self, interaction, article: str, url: str, prix_cible: str = None, selecteur: str = None):
        if not url.startswith("http"):
            raise ValueError("Le lien doit commencer par http:// ou https://")
        target = to_cents(prix_cible) if prix_cible else None
        await interaction.response.defer()  # la vérification du prix peut prendre quelques secondes

        execute("INSERT OR IGNORE INTO price_items (name) VALUES (?)", article)
        item = query_one("SELECT * FROM price_items WHERE name = ?", article)
        if target:
            execute("UPDATE price_items SET target = ? WHERE id = ?", target, item["id"])
        offer_id = execute("INSERT INTO price_offers (item_id, url, selector) VALUES (?, ?, ?)",
                           item["id"], url, selecteur).lastrowid

        price = await check_offer(query_one("SELECT * FROM price_offers WHERE id = ?", offer_id))
        if price is None:
            error = query_one("SELECT error FROM price_offers WHERE id = ?", offer_id)["error"]
            await interaction.followup.send(f"👀 {article} ajouté, mais je n'arrive pas à lire le prix :\n> {error}")
        else:
            await interaction.followup.send(f"👀 Je surveille **{article}** sur {shop_name(url)} : {euros(price)}")

    @prix.command(name="liste", description="Voir les prix de tes articles")
    async def show(self, interaction):
        await interaction.response.send_message(embed=prices_embed())

    @prix.command(name="cible", description="Changer le prix cible d'un article (0 pour l'enlever)")
    async def set_target(self, interaction, article: str, montant: str):
        target = None if montant.strip() == "0" else to_cents(montant)
        if execute("UPDATE price_items SET target = ? WHERE name = ?", target, article).rowcount == 0:
            raise ValueError(f"Article « {article} » introuvable.")
        await interaction.response.send_message("🎯 Cible mise à jour.", ephemeral=True)

    @prix.command(name="supprimer", description="Arrêter de suivre un article")
    async def delete(self, interaction, article: str):
        if execute("DELETE FROM price_items WHERE name = ?", article).rowcount == 0:
            raise ValueError(f"Article « {article} » introuvable.")
        await interaction.response.send_message(f"🗑️ {article} n'est plus suivi.", ephemeral=True)

    @set_target.autocomplete("article")
    @delete.autocomplete("article")
    async def suggest_articles(self, interaction, typed: str):
        rows = query("SELECT name FROM price_items WHERE name LIKE ? LIMIT 25", f"%{typed}%")
        return [app_commands.Choice(name=row["name"], value=row["name"]) for row in rows]

    @prix.command(name="verifier", description="Vérifier tous les prix maintenant")
    async def check_now(self, interaction):
        await interaction.response.defer()
        await self.check_all_prices()
        await interaction.followup.send(embed=prices_embed())

    @tasks.loop(hours=CHECK_EVERY_HOURS)
    async def check_all_prices(self):
        offers = query("SELECT price_offers.*, name, target FROM price_offers "
                       "JOIN price_items ON price_items.id = price_offers.item_id")
        for offer in offers:
            old_price = offer["price"]
            new_price = await check_offer(offer)
            if old_price and new_price and new_price < old_price:
                await self.send_price_drop(offer, old_price, new_price)
            await asyncio.sleep(2)  # on ne bombarde pas les boutiques de requêtes

    async def send_price_drop(self, offer, old_price, new_price):
        channel = self.bot.get_channel(config.ALERTS_CHANNEL_ID)
        if not channel:
            return
        target = offer["target"]
        title = "🎯 Prix cible atteint !" if target and new_price <= target else "📉 Baisse de prix"
        embed = discord.Embed(title=title, url=offer["url"], color=discord.Color.green(),
                              description=f"**{offer['name']}** sur {shop_name(offer['url'])}\n"
                                          f"~~{euros(old_price)}~~ → **{euros(new_price)}**")
        await channel.send(f"<@{config.OWNER_ID}>", embed=embed)

    @tasks.loop(time=WEEKLY_RECAP_TIME)
    async def weekly_recap(self):
        channel = self.bot.get_channel(config.ALERTS_CHANNEL_ID)
        if channel and now().weekday() == WEEKLY_RECAP_DAY:
            await channel.send(embed=prices_embed())

    @check_all_prices.before_loop
    @weekly_recap.before_loop
    async def wait_until_ready(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Prices(bot))
