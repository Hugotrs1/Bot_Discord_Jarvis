"""Jarvis, mon assistant Discord. Lancement : python bot.py"""

import logging

import discord
from discord.ext import commands

import config

# Chaque fonctionnalité est dans son propre fichier du dossier cogs/
MODULES = [
    "cogs.reminders",
    "cogs.todo",
    "cogs.briefing",
    "cogs.budget",
    "cogs.prices",
    "cogs.monitoring",
    "cogs.reading_list",
]


class Jarvis(commands.Bot):
    async def setup_hook(self):
        for module in MODULES:
            await self.load_extension(module)

        # Enregistre les commandes slash sur ton serveur (elles apparaissent tout de suite)
        server = discord.Object(id=config.GUILD_ID)
        self.tree.copy_global_to(guild=server)
        await self.tree.sync(guild=server)


intents = discord.Intents.default()
intents.message_content = True  # pour lire les liens postés par l'extension navigateur
bot = Jarvis(command_prefix="!", intents=intents)


async def only_owner(interaction):
    """Refuse les commandes de toute autre personne que toi."""
    if interaction.user.id == config.OWNER_ID:
        return True
    await interaction.response.send_message("🔒 Ce bot est privé.", ephemeral=True)
    return False


bot.tree.interaction_check = only_owner


@bot.tree.error
async def on_command_error(interaction, error):
    """Les ValueError sont des erreurs de saisie (date incomprise…) : on affiche le message tel quel."""
    error = getattr(error, "original", error)
    if isinstance(error, ValueError):
        message = f"❌ {error}"
    else:
        logging.exception("Erreur dans une commande", exc_info=error)
        message = "💥 Une erreur est survenue (voir les logs du bot)."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")


if __name__ == "__main__":
    if not config.TOKEN:
        raise SystemExit("DISCORD_TOKEN manquant : copie .env.example en .env et remplis-le.")
    bot.run(config.TOKEN)
