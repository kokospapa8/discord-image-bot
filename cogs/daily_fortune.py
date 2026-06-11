"""
Daily Fortune Cog — scheduled reminders and fortune notifications.

Tasks (all KST):
  08:00  사주 등록 멤버에게 오늘의 운세
  23:00  듀오링고 리마인더
  23:30  양치 리마인더
"""
from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime, time, timezone, timedelta
from pathlib import Path

import discord
from discord.ext import commands, tasks

from utils import member_memory

log = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))
_MEMBER_DIR = Path("/app/data/members")

_MORNING_TIME   = time(hour=8,  minute=0,  tzinfo=_KST)
_DUOLINGO_TIME  = time(hour=23, minute=0,  tzinfo=_KST)
_BRUSH_TIME     = time(hour=23, minute=30, tzinfo=_KST)

_NO_SAJU_PROMPT = (
    "사주 없는 분들도 미피 멘션하고 '내 사주는 [생년월일]이야' 라고 알려주면 "
    "내일부터 같이 알려줄게 🐰"
)

_DUOLINGO_MSGS = [
    "오늘 듀오링고 했어? 🦉 초록 부엉이 기다리고 있어",
    "앗 듀오링고! 아직 안 했으면 지금이라도 🫧",
    "오오 스트릭 지켰어? 부엉이 화나기 전에 얼른 🦉",
    "듀오링고 잊지 않았지? 잠수하기 전에 꼭 해 🌊",
]

_BRUSH_MSGS = [
    "양치했어? 🦷 안 하면 잠수 못 해",
    "이 닦고 자야지! 얼른 🦷🫧",
    "앗 양치! 잊기 전에 지금 해 🐰",
    "오늘 양치 완료? 심해에서도 치카치카 🦷",
]


class DailyFortune(commands.Cog):
    def __init__(self, bot: commands.Bot, channel_id: int) -> None:
        self.bot = bot
        self._channel_id = channel_id
        self.daily_task.start()
        self.duolingo_reminder.start()
        self.brush_reminder.start()

    def cog_unload(self) -> None:
        self.daily_task.cancel()
        self.duolingo_reminder.cancel()
        self.brush_reminder.cancel()

    # ── 08:00 운세 ────────────────────────────────────────────────────────────

    @tasks.loop(time=_MORNING_TIME)
    async def daily_task(self) -> None:
        channel = self.bot.get_channel(self._channel_id)
        if not isinstance(channel, discord.TextChannel):
            log.warning("daily_fortune: channel %s not found or not text", self._channel_id)
            return

        praise_cog = self.bot.cogs.get("Praise")
        if not praise_cog:
            log.warning("daily_fortune: Praise cog not loaded")
            return

        today_str = datetime.now(_KST).strftime("%Y년 %m월 %d일")
        sent = 0

        if not _MEMBER_DIR.exists():
            log.warning("daily_fortune: member dir not found: %s", _MEMBER_DIR)
            return

        for path in sorted(_MEMBER_DIR.glob("*.json")):
            if "_conv" in path.stem:
                continue
            try:
                member_id = int(path.stem)
            except ValueError:
                continue

            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                log.exception("daily_fortune: failed to read %s", path)
                continue

            saju = data.get("saju", "")
            saju_detail = data.get("saju_detail", "")
            if not saju and not saju_detail:
                continue

            member = channel.guild.get_member(member_id)
            if not member:
                continue

            cached = member_memory.get_fortune_cache(member_id)
            if cached:
                fortune = cached
            else:
                try:
                    fortune = await praise_cog.generate_fortune(
                        saju, member.display_name, today_str, saju_detail
                    )
                    member_memory.set_fortune_cache(member_id, fortune)
                except Exception:
                    log.exception("daily_fortune: fortune generation failed for %s", member_id)
                    continue

            await channel.send(f"{member.mention}\n{fortune}")
            sent += 1

        if sent == 0:
            await channel.send(
                f"🌅 {today_str} 운세 시간!\n"
                "아직 사주 정보 등록한 분이 없어. 미피 멘션하고 '내 사주는 [생년월일]이야' 라고 알려줘 🐰"
            )
        else:
            await channel.send(_NO_SAJU_PROMPT)

    @daily_task.before_loop
    async def before_daily_task(self) -> None:
        await self.bot.wait_until_ready()

    # ── 23:00 듀오링고 ────────────────────────────────────────────────────────

    @tasks.loop(time=_DUOLINGO_TIME)
    async def duolingo_reminder(self) -> None:
        channel = self.bot.get_channel(self._channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        await channel.send(random.choice(_DUOLINGO_MSGS))

    @duolingo_reminder.before_loop
    async def before_duolingo(self) -> None:
        await self.bot.wait_until_ready()

    # ── 23:30 양치 ────────────────────────────────────────────────────────────

    @tasks.loop(time=_BRUSH_TIME)
    async def brush_reminder(self) -> None:
        channel = self.bot.get_channel(self._channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        await channel.send(random.choice(_BRUSH_MSGS))

    @brush_reminder.before_loop
    async def before_brush(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    raw = os.getenv("DISCORD_CHANNEL_ID", "").strip()
    if not raw.isdigit():
        log.warning("daily_fortune: DISCORD_CHANNEL_ID not set, cog disabled")
        return
    await bot.add_cog(DailyFortune(bot, int(raw)))
