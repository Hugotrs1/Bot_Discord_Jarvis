"""Liste de lecture : l'extension navigateur poste des liens dans un salon, le bot les garde en mémoire.

- Réagir avec ✅ sous un lien le marque comme lu.
- Chaque samedi matin, le bot rappelle ce qui n'a pas été lu.
- /alire liste, /alire hasard, /alire lu
"""

import random
import re
from datetime import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from database import execute, query
from utils.dates import now

READ = "✅"
DIGEST_DAY = 5  # 5 = samedi
DIGEST_TIME = time(10, 0, tzinfo=config.TIMEZONE)


def unread_articles():
    return query("SELECT * FROM reading_list WHERE read = 0 ORDER BY added_at")


def article_line(article):
    return f"`#{article['id']}` [{article['title'][:90]}]({article['url']}) · ajouté <t:{article['added_at']}:R>"


class ReadingList(commands.Cog):
    alire = app_commands.Group(name="alire", description="Ta liste de lecture")

    def __init__(self, bot):
        self.bot = bot
        self.weekly_digest.start()

    @commands.Cog.listener()
    async def on_message(self, message):
        """Un lien arrive dans le salon de lecture (envoyé par l'extension, ou collé à la main)."""
        if message.channel.id != config.READING_CHANNEL_ID or message.author == self.bot.user:
            return

        if message.embeds and message.embeds[0].url:  # message de l'extension
            url, title = message.embeds[0].url, message.embeds[0].title or message.embeds[0].url
        elif link := re.search(r"https?://\S+", message.content):  # lien collé à la main
            url, title = link[0], link[0]
        else:
            return

        execute("INSERT INTO reading_list (url, title, message_id, added_at) VALUES (?, ?, ?, ?)",
                url, title, message.id, int(now().timestamp()))
        await message.add_reaction(READ)  # il suffit de cliquer dessus une fois l'article lu

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, reaction):
        if str(reaction.emoji) == READ and reaction.user_id != self.bot.user.id:
            execute("UPDATE reading_list SET read = 1 WHERE message_id = ?", reaction.message_id)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, reaction):
        if str(reaction.emoji) == READ:
            execute("UPDATE reading_list SET read = 0 WHERE message_id = ?", reaction.message_id)

    @alire.command(name="liste", description="Articles pas encore lus")
    async def show(self, interaction):
        articles = unread_articles()
        lines = [article_line(a) for a in articles[-20:]]
        await interaction.response.send_message("\n".join(lines) or "Ta liste de lecture est vide 🎉", ephemeral=True)

    @alire.command(name="hasard", description="Un article au hasard")
    async def random_article(self, interaction):
        articles = unread_articles()
        if not articles:
            raise ValueError("Ta liste de lecture est vide 🎉")
        article = random.choice(articles)
        await interaction.response.send_message(f"🎲 Et si tu lisais ça ?\n{article_line(article)}")

    @alire.command(name="lu", description="Marquer un article comme lu")
    async def mark_read(self, interaction, numero: int):
        if execute("UPDATE reading_list SET read = 1 WHERE id = ?", numero).rowcount == 0:
            raise ValueError(f"Article #{numero} introuvable.")
        await interaction.response.send_message(f"✅ Article #{numero} lu.", ephemeral=True)

    @tasks.loop(time=DIGEST_TIME)
    async def weekly_digest(self):
        channel = self.bot.get_channel(config.READING_CHANNEL_ID)
        articles = unread_articles()
        if channel and articles and now().weekday() == DIGEST_DAY:
            embed = discord.Embed(
                title=f"📚 À lire ce week-end ({len(articles)} en attente)",
                description="\n".join(article_line(a) for a in articles[:10]),
                color=discord.Color.purple(),
            )
            await channel.send(embed=embed)

    @weekly_digest.before_loop
    async def wait_until_ready(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(ReadingList(bot))
