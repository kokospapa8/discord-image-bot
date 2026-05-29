"""
Announces new bot version to the configured channel on startup.

Flow:
  1. Bot starts → on_ready fires → reads /app/VERSION
  2. Compares with /app/data/last_version.txt
  3. If different → sends embed to DISCORD_CHANNEL_ID
  4. Saves current version to last_version.txt

VERSION format: YYYYMMDD_NN  (e.g. 20260529_01)
ANNOUNCE.md   : changelog text shown inside the embed (markdown)
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import discord
from discord.ext import commands

log = logging.getLogger(__name__)

_VERSION_FILE  = Path(os.getenv("VERSION_FILE",       "/app/VERSION"))
_STATE_FILE    = Path(os.getenv("VERSION_STATE_PATH", "/app/data/last_version.txt"))
_ANNOUNCE_FILE = Path(os.getenv("ANNOUNCE_FILE",      "/app/ANNOUNCE.md"))


class VersionAnnounce(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await asyncio.sleep(3)
        await self._maybe_announce()

    async def _maybe_announce(self) -> None:
        channel_id = os.getenv("DISCORD_CHANNEL_ID", "").strip()
        if not channel_id or not channel_id.isdigit():
            log.debug("version_announce: DISCORD_CHANNEL_ID not set")
            return

        current = self._read_file(_VERSION_FILE)
        if not current:
            log.debug("version_announce: no VERSION file found")
            return

        last = self._read_file(_STATE_FILE)
        if current == last:
            log.debug("version_announce: already announced %s", current)
            return

        changelog = self._read_file(_ANNOUNCE_FILE) or "새 버전이 배포되었습니다."
        embed = discord.Embed(
            title=f"🫧 미피 업데이트  `{current}`",
            description=changelog,
            color=0x7DD3FC,
        )
        embed.set_footer(text="잠수하고 돌아왔어! 🐰")

        ch = self.bot.get_channel(int(channel_id))
        if ch:
            try:
                await ch.send(embed=embed)
                log.info("version_announce: announced %s to channel %s", current, channel_id)
            except Exception as exc:
                log.warning("version_announce: send failed: %s", exc)

        self._write_file(_STATE_FILE, current)

    @staticmethod
    def _read_file(path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8").strip() or None
        except Exception:
            return None

    @staticmethod
    def _write_file(path: Path, content: str) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except Exception as exc:
            log.error("version_announce: write failed (%s): %s", path, exc)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VersionAnnounce(bot))
