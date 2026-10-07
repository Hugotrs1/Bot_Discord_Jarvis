"""« À lire plus tard » : l'extension navigateur poste les liens dans un salon via un
webhook, le bot les enregistre, ✅ en réaction les marque comme lus, et un digest
hebdomadaire ressort ce qui n'a pas été lu.

/alire liste|hasard|lu|ajouter
"""

from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

if TYPE_CHECKING:
    from jarvis.bot import Jarvis

URL_RE = re.compile(r"https?://\S+")
READ_EMOJI = "✅"


def format_item(row) -> str:
    return f"`#{row['id']}` [{row['title'][:90]}]({row['url']}) · <t:{row['added_at']}:R>"


class ReadLater(commands.Cog):
    alire = app_commands.Group(name="alire", description="Ta liste de lecture")

    def __init__(self, bot: Jarvis) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        config = self.bot.config
        self.digest.change_interval(time=config.readlater_digest_time.replace(tzinfo=config.tz))
        self.digest.start()

    async def cog_unload(self) -> None:
        self.digest.cancel()

    async def unread_count(self) -> int:
        row = await self.bot.db.fetchone("SELECT COUNT(*) AS n FROM readlater WHERE read_at IS NULL")
        return row["n"] if row else 0

    async def add(self, url: str, title: str, note: str | None, message_id: int | None) -> int:
        return await self.bot.db.execute(
            "INSERT OR IGNORE INTO readlater (url, title, note, message_id, added_at) VALUES (?, ?, ?, ?, ?)",
            (url, title, note, message_id, int(self.bot.now().timestamp())),
        )

    async def set_read(self, *, item_id: int | None = None, message_id: int | None = None, read: bool = True) -> int:
        column, value = ("id", item_id) if item_id is not None else ("message_id", message_id)
        read_at = int(self.bot.now().timestamp()) if read else None
        return await self.bot.db.execute_rowcount(f"UPDATE readlater SET read_at = ? WHERE {column} = ?", (read_at, value))

    # --- Réception des liens ---------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.channel.id != self.bot.config.readlater_channel_id:
            return
        is_owner = message.author.id == self.bot.config.owner_id
        if not (message.webhook_id or is_owner) or message.author.id == getattr(self.bot.user, "id", None):
            return

        embed = message.embeds[0] if message.embeds else None
        if embed and embed.url:
            url, title, note = embed.url, embed.title or embed.url, embed.description
        elif match := URL_RE.search(message.content):
            url = match.group(0)
            title = message.content.replace(url, "").strip() or url
            note = None
        else:
            return

        await self.add(url, title, note, message.id)
        await message.add_reaction(READ_EMOJI)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if self._is_read_toggle(payload):
            await self.set_read(message_id=payload.message_id, read=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if self._is_read_toggle(payload):
            await self.set_read(message_id=payload.message_id, read=False)

    def _is_read_toggle(self, payload: discord.RawReactionActionEvent) -> bool:
        return (
            payload.channel_id == self.bot.config.readlater_channel_id
            and str(payload.emoji) == READ_EMOJI
            and payload.user_id != getattr(self.bot.user, "id", None)
        )

    # --- Commandes -----------------------------------------------------------------------

    @alire.command(name="liste", description="Articles pas encore lus")
    async def list_(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.fetchall("SELECT * FROM readlater WHERE read_at IS NULL ORDER BY added_at DESC LIMIT 20")
        if not rows:
            raise ValueError("Ta liste de lecture est vide. 🎉")
        total = await self.unread_count()
        embed = discord.Embed(
            title=f"📚 À lire ({total})",
            description="\n".join(format_item(r) for r in rows),
            color=discord.Color.purple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @alire.command(name="hasard", description="Un article au hasard dans ta liste")
    async def random_item(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.fetchall("SELECT * FROM readlater WHERE read_at IS NULL")
        if not rows:
            raise ValueError("Ta liste de lecture est vide. 🎉")
        row = random.choice(rows)
        embed = discord.Embed(title=row["title"][:256], url=row["url"], description=row["note"], color=discord.Color.purple())
        embed.set_footer(text=f"#{row['id']} · /alire lu {row['id']} quand c'est fait")
        await interaction.response.send_message("🎲 Et si tu lisais ça ?", embed=embed)

    @alire.command(name="lu", description="Marquer un article comme lu")
    async def mark_read(self, interaction: discord.Interaction, article: int) -> None:
        if not await self.set_read(item_id=article):
            raise ValueError(f"Article #{article} introuvable.")
        await interaction.response.send_message(f"✅ Article #{article} marqué comme lu.", ephemeral=True)

    @mark_read.autocomplete("article")
    async def unread_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
        rows = await self.bot.db.fetchall(
            "SELECT id, title FROM readlater WHERE read_at IS NULL AND title LIKE ? ORDER BY added_at DESC LIMIT 25",
            (f"%{current}%",),
        )
        return [app_commands.Choice(name=f"#{r['id']} — {r['title'][:90]}", value=r["id"]) for r in rows]

    @alire.command(name="ajouter", description="Ajouter un lien à ta liste de lecture")
    async def add_command(self, interaction: discord.Interaction, url: str, titre: str | None = None) -> None:
        if not URL_RE.fullmatch(url):
            raise ValueError("Lien invalide.")
        item_id = await self.add(url, titre or url, None, None)
        await interaction.response.send_message(f"📥 Ajouté à ta liste de lecture (#{item_id}).", ephemeral=True)

    # --- Digest hebdomadaire ---------------------------------------------------------------------

    @tasks.loop(hours=24)  # remplacé au démarrage par READLATER_DIGEST_TIME
    async def digest(self) -> None:
        if self.bot.now().weekday() != self.bot.config.readlater_digest_weekday:
            return
        channel = await self.bot.get_text_channel(self.bot.config.readlater_channel_id)
        rows = await self.bot.db.fetchall("SELECT * FROM readlater WHERE read_at IS NULL ORDER BY added_at LIMIT 10")
        if channel is None or not rows:
            return
        total = await self.unread_count()
        embed = discord.Embed(
            title=f"📚 Ta liste de lecture du week-end ({total} en attente)",
            description="\n".join(format_item(r) for r in rows),
            color=discord.Color.purple(),
        )
        embed.set_footer(text="Les plus anciens d'abord · ✅ sous un lien ou /alire lu pour le retirer")
        await channel.send(embed=embed)

    @digest.before_loop
    async def before_digest(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: Jarvis) -> None:
    await bot.add_cog(ReadLater(bot))
