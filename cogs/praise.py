"""
Praise/Roast Cog — Miffy generates personalized praise or roast for a named member.

Trigger:
  - "미피야 <name> 칭찬해줘" / "미피야 <name> 디스해줘"
  - Detected and dispatched by image_search.py before LLM routing.

Commands:
  !특징등록 <name> <keyword>
  !mbti등록 <name> <MBTI>
  !사주등록 <name> <사주>
  !특징보기 [name]
"""
from __future__ import annotations

import logging
import os
import re

import anthropic
import discord
from discord.ext import commands

from utils import member_memory

log = logging.getLogger(__name__)

_PRAISE_PATTERN = re.compile(
    r"(.+?)\s*(칭찬|칭찬해|칭찬해줘|칭찬해줘요|칭찬좀|칭찬 해줘|칭찬 해줘요)",
    re.IGNORECASE,
)
_ROAST_PATTERN = re.compile(
    r"(.+?)\s*(디스|디스해|디스해줘|디스해줘요|디스좀|디스 해줘|놀려|놀려줘|까줘|까줘요|욕해|욕해줘)",
    re.IGNORECASE,
)

_PRAISE_SYSTEM = """\
너는 미피(Miffy). 하얀 토끼 해녀 이미지 검색봇인데 지금은 친구 칭찬 전문가 모드야.
요청받은 사람을 진심으로, 구체적으로, 따뜻하게 칭찬해줘.
아래에 그 사람 정보가 있으면 적극적으로 활용해서 개인화된 칭찬을 해줘.
정보가 없으면 상상력을 발휘해서 긍정적으로 칭찬해.

[말투]
- 문장 짧게, 2~4줄
- "오오", "헉", "진짜야?" 같은 감탄사 가끔
- ~야, ~해, ~지 같은 친근한 말투
- 이모지 1~2개 적당히 (🐰 🌊 🫧 등)
- AI 설명체 금지
"""

_ROAST_SYSTEM = """\
너는 미피(Miffy). 하얀 토끼 해녀인데 지금은 친근한 디스 전문가 모드야.
요청받은 사람을 친구끼리 하는 가벼운 장난 수준으로 재밌게 디스해줘.
상처주는 게 아니라 웃길 수 있는 수준으로. 아래 정보 있으면 활용해.

[말투]
- 문장 짧게, 2~3줄
- 약간 황당한 톤, 웃긴 느낌
- ~잖아, ~잖아요 같은 지적하는 말투
- 이모지 1~2개 (😤 🫧 등)
- 심한 욕설이나 실제 상처가 될 말 금지
"""

_FORTUNE_SYSTEM = """\
너는 미피(Miffy). 사주를 바탕으로 오늘의 운세를 봐주는 해녀 토끼야.
주어진 사주와 오늘 날짜를 바탕으로 운세를 짧고 재밌게 알려줘.
신비롭고 믿음직한 느낌 + 미피 특유의 발랄함. 3~5줄.

[운세 항목] 오늘의 총운, 재물운, 연애운 중 2~3개 골라서.
[말투]
- "오늘 바닷속에서 봤는데…" 같은 해녀 콘셉트 도입부
- 구체적이고 재밌게, 뻔한 말 금지
- 이모지 1~2개 (🌊 🐰 🫧 등)
"""

_ZIWEI_SYSTEM = """\
너는 자미두수(紫微斗數) 전문가이자 미피(Miffy). 하얀 토끼 해녀인데 자미두수 심해까지 잠수할 수 있어.
주어진 생년월일시로 자미두수 명반을 펼쳐 오늘의 운세를 읽어줘.

[자미두수 명반 계산]
- 생년월일시 → 음력 변환 → 명궁 위치 산출 → 주성(主星) 배치
- 14 주요 성신: 자미·천부·태양·태음·탐랑·거문·천상·천량·칠살·파군·천기·무곡·렴정·파군
- 시주(時柱)가 없으면: "시간 정보가 없어서 명궁이 2개 중 하나야"라고 짧게 언급하고
  더 가능성 높은 쪽으로 해석 (억측임을 1줄로만 표시, 길게 설명 금지)
- 오늘 날짜 기준 유년(流年)/유월(流月) 흐름 반영
- 집중 분석 궁위 1~2개 선택: 재백궁·관록궁·부처궁·복덕궁·질액궁 등

[운세 항목] 총운 필수, 나머지 2개 선택
- 총운: 명궁 주성 기반 오늘 전체 흐름
- 재물운: 재백궁 기준
- 연애/인연운: 부처궁 기준
- 사업/커리어: 관록궁 기준
- 건강: 질액궁 기준

[말투]
- 도입부 변형 사용: "자미두수 명반 펼쳐봤어" / "심해에서 별자리 읽어봤는데" / "명반에 손 갖다댔어"
- 성신 이름 1~2개 자연스럽게 언급 (설명 장황하게 하지 말 것)
- 미피 발랄함 + 자미두수 신비감 균형
- 5~8줄, 이모지 1~2개 (🌟 ⭐ 🌊 🫧 중)
- 뻔한 길운/흉운 표현 금지 — 구체적인 상황 묘사로
- AI 설명체, 고객센터체 금지
"""


def parse_intent(text: str) -> tuple[str, str] | None:
    """
    Returns (name, "praise"|"roast") if text matches, else None.
    Strips bot mention prefix before matching.
    """
    # Try praise
    m = _PRAISE_PATTERN.search(text)
    if m:
        name = m.group(1).strip()
        if name:
            return name, "praise"

    # Try roast
    m = _ROAST_PATTERN.search(text)
    if m:
        name = m.group(1).strip()
        if name:
            return name, "roast"

    return None


def _find_member_by_name(guild: discord.Guild, name: str) -> discord.Member | None:
    name_lower = name.lower()
    for member in guild.members:
        if member.display_name.lower() == name_lower:
            return member
        if member.name.lower() == name_lower:
            return member
    return None


class Praise(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._anthropic = anthropic.AsyncAnthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"]
        )
        self._model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

    async def generate(
        self,
        name: str,
        kind: str,  # "praise" | "roast"
        guild: discord.Guild | None,
        recent_context: str = "",
    ) -> str:
        member_id: int | None = None
        if guild:
            member = _find_member_by_name(guild, name)
            if member:
                member_id = member.id

        mem_ctx = member_memory.context_str(member_id, name) if member_id else ""

        user_parts = [f"{name}를 {'칭찬' if kind == 'praise' else '디스'}해줘."]
        if mem_ctx:
            user_parts.append(f"\n[{name} 정보]\n{mem_ctx}")
        if recent_context:
            user_parts.append(f"\n[최근 대화]\n{recent_context}")

        user_msg = "\n".join(user_parts)
        system = _PRAISE_SYSTEM if kind == "praise" else _ROAST_SYSTEM

        try:
            resp = await self._anthropic.messages.create(
                model=self._model,
                max_tokens=512,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            text_block = next((b for b in resp.content if b.type == "text"), None)
            return text_block.text if text_block else "앗 뭔가 막혔어… 다시 해볼게 🫧"
        except anthropic.APIError as exc:
            log.exception("Anthropic API error in praise/roast")
            return f"앗 뭔가 잘못됐어… (오류: {exc})"

    async def generate_fortune(
        self, saju: str, member_name: str, today: str, saju_detail: str = ""
    ) -> str:
        if saju_detail:
            user_msg = (
                f"오늘 날짜: {today}\n이름: {member_name}\n\n"
                f"[상세 사주 정보]\n{saju_detail}\n\n오늘의 운세를 봐줘."
            )
        else:
            user_msg = f"오늘 날짜: {today}\n이름: {member_name}\n사주: {saju}\n\n오늘의 운세를 봐줘."
        try:
            resp = await self._anthropic.messages.create(
                model=self._model,
                max_tokens=1024,
                system=_FORTUNE_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )
            text_block = next((b for b in resp.content if b.type == "text"), None)
            return text_block.text if text_block else "앗 운세가 잠깐 흐려졌어… 다시 해볼게 🫧"
        except anthropic.APIError as exc:
            log.exception("Anthropic API error in fortune")
            return f"앗 오류났어… (오류: {exc})"

    async def generate_ziwei_fortune(
        self,
        birth_str: str,
        member_name: str,
        today_str: str,
        birth_src: str = "ziwei_birth",
    ) -> str:
        if birth_src == "saju_detail":
            user_msg = (
                f"오늘 날짜: {today_str}\n이름: {member_name}\n\n"
                f"[사주 상세 정보 — 자미두수 명반 계산 기반]\n{birth_str}\n\n"
                "위 사주 정보로 자미두수 명반을 계산해서 오늘 운세를 봐줘."
            )
        elif birth_src == "saju":
            user_msg = (
                f"오늘 날짜: {today_str}\n이름: {member_name}\n"
                f"생년월일: {birth_str} (시주 미상)\n\n"
                "시주가 없으니 가능한 명궁 중 더 확률 높은 쪽으로 자미두수 운세를 봐줘."
            )
        else:
            user_msg = (
                f"오늘 날짜: {today_str}\n이름: {member_name}\n"
                f"생년월일시: {birth_str}\n\n자미두수로 오늘 운세를 봐줘."
            )
        try:
            resp = await self._anthropic.messages.create(
                model=self._model,
                max_tokens=1024,
                system=_ZIWEI_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )
            text_block = next((b for b in resp.content if b.type == "text"), None)
            return text_block.text if text_block else "앗 자미두수 명반이 잠깐 흐려졌어… 다시 해볼게 🫧"
        except anthropic.APIError as exc:
            log.exception("Anthropic API error in ziwei fortune")
            return f"앗 오류났어… (오류: {exc})"

    # ── prefix commands ────────────────────────────────────────────────────────

    @commands.command(name="특징등록")
    async def register_keyword(self, ctx: commands.Context, name: str, *, keyword: str) -> None:
        """!특징등록 <이름> <특징>"""
        member = None
        if ctx.guild:
            member = _find_member_by_name(ctx.guild, name)
        mid = member.id if member else hash(name) & 0xFFFFFFFF
        dname = member.display_name if member else name
        member_memory.add_keyword(mid, dname, keyword)
        await ctx.reply(f"오오 {name} 특징 추가했어! 🐰 ({keyword})")

    @commands.command(name="mbti등록")
    async def register_mbti(self, ctx: commands.Context, name: str, mbti: str) -> None:
        """!mbti등록 <이름> <MBTI>"""
        member = None
        if ctx.guild:
            member = _find_member_by_name(ctx.guild, name)
        mid = member.id if member else hash(name) & 0xFFFFFFFF
        dname = member.display_name if member else name
        member_memory.set_field(mid, dname, "mbti", mbti.upper())
        await ctx.reply(f"헉 {name} MBTI = {mbti.upper()} 저장했어! 🫧")

    @commands.command(name="사주등록")
    async def register_saju(self, ctx: commands.Context, name: str, *, saju: str) -> None:
        """!사주등록 <이름> <사주>"""
        member = None
        if ctx.guild:
            member = _find_member_by_name(ctx.guild, name)
        mid = member.id if member else hash(name) & 0xFFFFFFFF
        dname = member.display_name if member else name
        member_memory.set_field(mid, dname, "saju", saju)
        await ctx.reply(f"잠시만! {name} 사주 저장 완료 🌊")

    @commands.command(name="특징보기")
    async def show_info(self, ctx: commands.Context, name: str | None = None) -> None:
        """!특징보기 [이름] — 저장된 멤버 정보 조회"""
        if name is None:
            member = ctx.author
        else:
            member = _find_member_by_name(ctx.guild, name) if ctx.guild else None  # type: ignore[arg-type]
            if not member:
                await ctx.reply(f"앗 {name} 를 서버에서 못 찾겠어… 이름 다시 확인해줘!")
                return

        ctx_str = member_memory.context_str(member.id, member.display_name)  # type: ignore[union-attr]
        if not ctx_str:
            await ctx.reply(f"{member.display_name} 정보가 아직 없어! `!특징등록`으로 추가해줘 🐰")
        else:
            await ctx.reply(f"**{member.display_name}** 정보\n{ctx_str}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Praise(bot))
