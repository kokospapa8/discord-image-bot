"""
Image Search Cog — responds to @mentions with images or GIFs.

Trigger: any message that @mentions the bot.
APIs: Tenor (GIF), Google Custom Search (images) — configure via .env.

TODO: implement actual search logic here.
"""
from __future__ import annotations

import logging
import os

import discord
from discord.ext import commands

log = logging.getLogger(__name__)


class ImageSearch(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.tenor_api_key = os.getenv("TENOR_API_KEY", "")
        self.google_api_key = os.getenv("GOOGLE_API_KEY", "")
        self.google_cx = os.getenv("GOOGLE_CX", "")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not message.guild:
            return
        if self.bot.user not in message.mentions:
            return

        content = message.content
        if self.bot.user:
            content = content.replace(f"<@{self.bot.user.id}>", "").strip()
            content = content.replace(f"<@!{self.bot.user.id}>", "").strip()

        if not content:
            await message.reply("검색어를 입력해 주세요! 예: `@봇이름 귀여운 고양이`")
            return

        async with message.channel.typing():
            # TODO: implement image/GIF search and send result
            await message.reply(f"🔍 `{content}` 검색 중... (구현 예정)")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ImageSearch(bot))
