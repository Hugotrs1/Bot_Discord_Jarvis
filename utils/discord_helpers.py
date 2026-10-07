"""Petites aides pour Discord, partagées par plusieurs modules."""

import discord

import config


async def find_channel(bot: discord.Client, channel_id: int):
    """Retrouve un salon à partir de son identifiant.

    Renvoie None si l'identifiant n'est pas configuré (0) ou si le salon n'existe pas.
    """
    if not channel_id:
        return None

    # D'abord dans le cache du bot (instantané), sinon on le demande à Discord
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except discord.HTTPException:
            return None
    return channel


def owner_mention() -> str | None:
    """« @toi » pour notifier le propriétaire du bot, ou None si OWNER_ID n'est pas défini."""
    if config.OWNER_ID:
        return f"<@{config.OWNER_ID}>"
    return None


def progress_bar(ratio: float, width: int = 10) -> str:
    """Barre de progression en texte : progress_bar(0.4) → « ▰▰▰▰▱▱▱▱▱▱ »"""
    filled = min(width, round(ratio * width))
    return "▰" * filled + "▱" * (width - filled)


def timestamp(moment) -> int:
    """Convertit une date en timestamp Unix (nombre entier de secondes)."""
    return int(moment.timestamp())
