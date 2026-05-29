"""
Discord Image Bot — main entry point.

Loads all cogs and starts the bot.
"""
from __future__ import annotations

import logging
import os

import discord
from discord.ext import commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

COGS = [
    "cogs.image_search",
    "cogs.version_announce",
]

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def setup_hook() -> None:
    for cog in COGS:
        await bot.load_extension(cog)
        log.info("Loaded cog: %s", cog)


@bot.event
async def on_ready() -> None:
    log.info("Logged in as %s (id=%s)", bot.user, bot.user.id)


if __name__ == "__main__":
    token = os.environ["DISCORD_TOKEN"]
    bot.run(token)
