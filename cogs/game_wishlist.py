"""
Game Wishlist Cog — watches GAME_CHANNEL_ID for Steam links and saves them.

Trigger: any message in GAME_CHANNEL_ID containing a Steam store URL.
Fetches game name from Steam API and adds to /app/data/games.json.
"""
from __future__ import annotations

import logging
import os
import re

import aiohttp
import discord
from discord.ext import commands

from utils import game_store

log = logging.getLogger(__name__)

_STEAM_RE = re.compile(r"https?://store\.steampowered\.com/app/(\d+)")


async def fetch_steam_name(appid: str) -> str:
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&l=english"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return f"App {appid}"
                data = await resp.json(content_type=None)
        app_data = data.get(str(appid), {})
        if app_data.get("success"):
            return app_data["data"].get("name", f"App {appid}")
    except Exception as exc:
        log.warning("Steam API error for appid %s: %s", appid, exc)
    return f"App {appid}"


class GameWishlist(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        raw = os.getenv("GAME_CHANNEL_ID", "").strip()
        self._game_channel_id: int | None = int(raw) if raw.isdigit() else None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if self._game_channel_id is None:
            return
        if message.channel.id != self._game_channel_id:
            return

        appids = _STEAM_RE.findall(message.content)
        if not appids:
            return

        for appid in appids:
            name = await fetch_steam_name(appid)
            canonical_url = f"https://store.steampowered.com/app/{appid}/"
            is_new = game_store.add_game(appid, name, canonical_url)
            if is_new:
                log.info("game added: %s (%s)", name, appid)
                await message.add_reaction("🎮")
                await message.channel.send(
                    f"오오 **{name}** 목록에 추가했어! 🎮\n{canonical_url}"
                )
            else:
                log.info("game already in list: %s (%s)", name, appid)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GameWishlist(bot))
