"""Jarvis, mon assistant Discord.

Lancement : python bot.py

Chaque fonctionnalité est dans son propre fichier du dossier cogs/ (un « cog » est un
module de discord.py qui regroupe des commandes et des tâches automatiques).
"""

import logging

import discord
from discord.ext import commands

import config

MODULES = [
    "cogs.reminders",      # /rappel
    "cogs.todo",           # /todo
    "cogs.briefing",       # /brief + briefing automatique du matin
    "cogs.budget",         # /depense, /revenu, /budget
    "cogs.prices",         # /prix
    "cogs.monitoring",     # /status, /site
    "cogs.reading_list",   # /alire + liens envoyés par l'extension navigateur
]

log = logging.getLogger("jarvis")


class Jarvis(commands.Bot):
    async def setup_hook(self):
        """Appelé une fois au démarrage, avant la connexion à Discord."""
        for module in MODULES:
            await self.load_extension(module)
            log.info("Module chargé : %s", module)

        if config.GUILD_ID:
            # Commandes enregistrées sur ton serveur uniquement : elles apparaissent immédiatement
            server = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=server)
            synced = await self.tree.sync(guild=server)
        else:
            # Commandes globales : peuvent mettre jusqu'à une heure à apparaître
            synced = await self.tree.sync()
        log.info("%d commandes slash enregistrées", len(synced))


intents = discord.Intents.default()
intents.message_content = True  # nécessaire pour lire les liens postés par l'extension navigateur
bot = Jarvis(command_prefix="!", intents=intents)


async def only_owner(interaction: discord.Interaction) -> bool:
    """Vérification faite avant chaque commande.

    Si OWNER_ID est défini dans .env, seul le propriétaire peut utiliser le bot.
    """
    if not config.OWNER_ID or interaction.user.id == config.OWNER_ID:
        return True
    await interaction.response.send_message("🔒 Ce bot est réservé à son propriétaire.", ephemeral=True)
    return False


bot.tree.interaction_check = only_owner


@bot.tree.error
async def on_command_error(interaction: discord.Interaction, error: Exception):
    """Appelé quand une commande plante.

    Dans tout le bot, une ValueError signifie « erreur de saisie » (date incomprise,
    montant invalide…) : on affiche son message à l'utilisateur. Les autres erreurs
    sont des bugs : on les note dans les logs.
    """
    # discord.py emballe l'erreur d'origine dans une autre : on la récupère
    original_error = getattr(error, "original", error)

    if isinstance(original_error, ValueError):
        message = f"❌ {original_error}"
    else:
        log.exception("Erreur dans une commande", exc_info=original_error)
        message = "💥 Oups, une erreur interne est survenue (détails dans les logs du bot)."

    # Si la commande a déjà répondu (ou demandé un délai), on doit envoyer un « followup »
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


@bot.event
async def on_ready():
    log.info("✅ Connecté en tant que %s", bot.user)


if __name__ == "__main__":
    if not config.TOKEN:
        raise SystemExit("DISCORD_TOKEN manquant : copie .env.example en .env et remplis-le.")
    discord.utils.setup_logging(level=logging.INFO)  # affiche les messages dans le terminal
    bot.run(config.TOKEN, log_handler=None)
