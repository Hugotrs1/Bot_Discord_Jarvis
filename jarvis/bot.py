"""Classe principale du bot : connexion, base de données, chargement des modules."""

from __future__ import annotations

import logging
from datetime import datetime

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from jarvis.config import Config
from jarvis.db import Database

log = logging.getLogger(__name__)

EXTENSIONS = [
    "jarvis.cogs.reminders",
    "jarvis.cogs.todo",
    "jarvis.cogs.briefing",
    "jarvis.cogs.budget",
    "jarvis.cogs.prices",
    "jarvis.cogs.monitoring",
    "jarvis.cogs.readlater",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


class OwnerOnlyTree(app_commands.CommandTree):
    """Arbre de commandes qui refuse les commandes aux autres membres si OWNER_ID est défini."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        owner_id = interaction.client.config.owner_id  # type: ignore[attr-defined]
        if owner_id is None or interaction.user.id == owner_id:
            return True
        await interaction.response.send_message("🔒 Ce bot est réservé à son propriétaire.", ephemeral=True)
        return False

    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        """Les ValueError levées par les commandes sont des erreurs de saisie : on les affiche telles quelles."""
        original = getattr(error, "original", error)
        if isinstance(original, ValueError):
            message = f"❌ {original}"
        else:
            log.exception("Erreur dans /%s", interaction.command and interaction.command.qualified_name, exc_info=original)
            message = "💥 Oups, une erreur interne est survenue (détails dans les logs)."

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


class Jarvis(commands.Bot):
    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # nécessaire pour lire les liens envoyés par l'extension
        super().__init__(command_prefix=commands.when_mentioned, intents=intents, tree_cls=OwnerOnlyTree)
        self.config = config
        self.db = Database(config.db_path)
        self.http_session: aiohttp.ClientSession | None = None

    @property
    def session(self) -> aiohttp.ClientSession:
        assert self.http_session, "Session HTTP non initialisée"
        return self.http_session

    def now(self) -> datetime:
        return datetime.now(self.config.tz)

    async def get_text_channel(self, channel_id: int | None) -> discord.abc.Messageable | None:
        if channel_id is None:
            return None
        channel = self.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(channel_id)
            except discord.HTTPException:
                log.warning("Salon %s introuvable", channel_id)
                return None
        return channel if isinstance(channel, discord.abc.Messageable) else None

    async def setup_hook(self) -> None:
        await self.db.connect()
        self.http_session = aiohttp.ClientSession(
            headers={"User-Agent": USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"},
            timeout=aiohttp.ClientTimeout(total=20),
        )
        for extension in EXTENSIONS:
            await self.load_extension(extension)
            log.info("Module chargé : %s", extension)

        if self.config.guild_id:
            guild = discord.Object(id=self.config.guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
        else:
            synced = await self.tree.sync()
        log.info("%d commandes slash synchronisées", len(synced))

    async def on_ready(self) -> None:
        log.info("Connecté en tant que %s (%s)", self.user, getattr(self.user, "id", "?"))

    async def close(self) -> None:
        await super().close()
        if self.http_session:
            await self.http_session.close()
        await self.db.close()
