"""Liste de lecture « À lire plus tard ».

L'extension navigateur poste les liens dans le salon READING_CHANNEL_ID (via un webhook).
Le bot les enregistre et ajoute ✅ sous chaque lien : cliquer dessus marque l'article comme lu.
Chaque semaine (samedi par défaut), il rappelle les articles pas encore lus.

Commandes : /alire liste, /alire hasard, /alire lu, /alire ajouter
"""

import random
import re

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from database import execute, query, query_one
from utils.dates import now
from utils.discord_helpers import find_channel, timestamp

READ_EMOJI = "✅"
URL_PATTERN = re.compile(r"https?://\S+")


def unread_count() -> int:
    return query_one("SELECT COUNT(*) AS total FROM reading_list WHERE read_at IS NULL")["total"]


def add_article(url: str, title: str, note: str | None, message_id: int | None) -> int:
    # INSERT OR IGNORE : si le message a déjà été enregistré, on ne le duplique pas
    cursor = execute(
        "INSERT OR IGNORE INTO reading_list (url, title, note, message_id, added_at) VALUES (?, ?, ?, ?, ?)",
        url, title, note, message_id, timestamp(now()),
    )
    return cursor.lastrowid


def format_article(article) -> str:
    """« #12 Titre de l'article · il y a 3 jours » (le titre est un lien cliquable)"""
    return f"`#{article['id']}` [{article['title'][:90]}]({article['url']}) · <t:{article['added_at']}:R>"


class ReadingList(commands.Cog):
    alire = app_commands.Group(name="alire", description="Ta liste de lecture")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.weekly_digest.start()

    # --- Réception des liens ---------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Appelé pour chaque message posté sur le serveur."""
        if message.channel.id != config.READING_CHANNEL_ID:
            return
        if message.author.id == self.bot.user.id:
            return  # on ignore les messages du bot lui-même
        # On accepte les messages de l'extension (webhook) et ceux du propriétaire
        sent_by_webhook = message.webhook_id is not None
        sent_by_owner = message.author.id == config.OWNER_ID
        if not (sent_by_webhook or sent_by_owner):
            return

        if message.embeds and message.embeds[0].url:
            # Message de l'extension : une carte avec le lien, le titre et la note
            embed = message.embeds[0]
            url = embed.url
            title = embed.title or embed.url
            note = embed.description
        else:
            # Lien collé à la main : « https://… titre facultatif »
            match = URL_PATTERN.search(message.content)
            if match is None:
                return
            url = match.group(0)
            title = message.content.replace(url, "").strip() or url
            note = None

        add_article(url, title, note, message.id)
        await message.add_reaction(READ_EMOJI)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, reaction: discord.RawReactionActionEvent):
        if self.is_read_reaction(reaction):
            execute("UPDATE reading_list SET read_at = ? WHERE message_id = ?", timestamp(now()), reaction.message_id)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, reaction: discord.RawReactionActionEvent):
        if self.is_read_reaction(reaction):
            execute("UPDATE reading_list SET read_at = NULL WHERE message_id = ?", reaction.message_id)

    def is_read_reaction(self, reaction: discord.RawReactionActionEvent) -> bool:
        """Vrai si c'est un ✅ ajouté (ou retiré) par quelqu'un d'autre que le bot, dans le bon salon."""
        return (
            reaction.channel_id == config.READING_CHANNEL_ID
            and str(reaction.emoji) == READ_EMOJI
            and reaction.user_id != self.bot.user.id
        )

    # --- Commandes ---------------------------------------------------------------------------------

    @alire.command(name="liste", description="Articles pas encore lus")
    async def show_list(self, interaction: discord.Interaction):
        articles = query("SELECT * FROM reading_list WHERE read_at IS NULL ORDER BY added_at DESC LIMIT 20")
        if not articles:
            raise ValueError("Ta liste de lecture est vide. 🎉")

        embed = discord.Embed(
            title=f"📚 À lire ({unread_count()})",
            description="\n".join(format_article(article) for article in articles),
            color=discord.Color.purple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @alire.command(name="hasard", description="Un article au hasard dans ta liste")
    async def random_article(self, interaction: discord.Interaction):
        articles = query("SELECT * FROM reading_list WHERE read_at IS NULL")
        if not articles:
            raise ValueError("Ta liste de lecture est vide. 🎉")

        article = random.choice(articles)
        embed = discord.Embed(
            title=article["title"][:256], url=article["url"], description=article["note"], color=discord.Color.purple()
        )
        embed.set_footer(text=f"#{article['id']} · /alire lu {article['id']} quand c'est fait")
        await interaction.response.send_message("🎲 Et si tu lisais ça ?", embed=embed)

    @alire.command(name="lu", description="Marquer un article comme lu")
    async def mark_read(self, interaction: discord.Interaction, article: int):
        cursor = execute("UPDATE reading_list SET read_at = ? WHERE id = ?", timestamp(now()), article)
        if cursor.rowcount == 0:
            raise ValueError(f"Article #{article} introuvable.")
        await interaction.response.send_message(f"✅ Article #{article} marqué comme lu.", ephemeral=True)

    @mark_read.autocomplete("article")
    async def suggest_unread(self, interaction: discord.Interaction, typed_text: str):
        articles = query(
            "SELECT id, title FROM reading_list WHERE read_at IS NULL AND title LIKE ? ORDER BY added_at DESC LIMIT 25",
            f"%{typed_text}%",
        )
        return [app_commands.Choice(name=f"#{article['id']} — {article['title'][:90]}", value=article["id"]) for article in articles]

    @alire.command(name="ajouter", description="Ajouter un lien à ta liste de lecture")
    async def add_command(self, interaction: discord.Interaction, url: str, titre: str | None = None):
        if not URL_PATTERN.fullmatch(url):
            raise ValueError("Lien invalide (il doit commencer par http:// ou https://).")
        article_id = add_article(url, titre or url, None, None)
        await interaction.response.send_message(f"📥 Ajouté à ta liste de lecture (#{article_id}).", ephemeral=True)

    # --- Rappel hebdomadaire --------------------------------------------------------------------------

    @tasks.loop(time=config.READING_DIGEST_TIME)
    async def weekly_digest(self):
        if now().weekday() != config.READING_DIGEST_WEEKDAY:
            return
        channel = await find_channel(self.bot, config.READING_CHANNEL_ID)
        oldest_articles = query("SELECT * FROM reading_list WHERE read_at IS NULL ORDER BY added_at LIMIT 10")
        if channel is None or not oldest_articles:
            return

        embed = discord.Embed(
            title=f"📚 Ta liste de lecture du week-end ({unread_count()} en attente)",
            description="\n".join(format_article(article) for article in oldest_articles),
            color=discord.Color.purple(),
        )
        embed.set_footer(text=f"Les plus anciens d'abord · {READ_EMOJI} sous un lien ou /alire lu pour le retirer")
        await channel.send(embed=embed)

    @weekly_digest.before_loop
    async def wait_until_ready(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(ReadingList(bot))
