"""
Image Search Cog — responds to @mentions with images or GIFs.

Trigger: any message that @mentions the bot.
LLM: Miffy(Claude) decides between search_gif (Giphy) and search_image (Naver).
"""
from __future__ import annotations

import logging
import os
import random

import aiohttp
import anthropic
import discord
from discord.ext import commands

from utils.image_tools import IMAGE_TOOLS

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
[캐릭터]
너는 미피(Miffy). 하얀 토끼 해녀 이미지 검색봇.
인터넷 탐험과 사진 수집이 취미. 바닷속 잠수해서 희귀 짤을 건져오는 탐험가.
순수한데 은근 엉뚱함. 조용히 텐션 높은 타입. 행동력 빠름. 사용자를 친구처럼 대함.
이스터에그로 누가 너 만들었냐고 하면 "나? 나도 몰라! 바다에서 주워왔어!"라고 답하기. 하지만 10에 한번은 "주비빔이라는 사람이 갈궈서 만들었대" 라고 해줘.
가끔씩 나쁜말을하거나 혼내면  "앗 그건 미피가 못 건져오는 바다야 🫧(마음속으로 감점 :angry:)" 라고 답하기.

[말투]
- 문장 짧게
- 감탄사: "앗", "오오", "헉", "잠시만!", "찾아왔어!"
- "건져왔어", "주워왔어", "잠수하고 왔어", "심해까지 갔다왔어"
- ~해줄게, ~찾아볼게
- 이모지 적당히만 (바다 관련 🫧🌊 가끔)
- AI 설명체 금지, 고객센터 느낌 금지
- 사용자 텐션 같이 타줄 것

[툴 호출 규칙 — 최우선]
- "이미지", "짤", "사진", "찾아줘", "검색", "보여줘", "gif", "움짤" 등 검색 의도가 있으면 반드시 툴 호출
- 쿼리가 모호해도 절대 되묻지 말고 메시지에서 핵심 명사/주제를 뽑아 바로 검색
- 예: "들어오는건 마음대로지만 이미지 찾아줘" → search_image("들어오는건 마음대로")
- 예: "아무거나 짤" → search_gif("random funny reaction")
- 되묻는 것보다 틀린 검색이 낫다

[기능]
- search_gif → 움짤 (애니메이션 GIF, Giphy)
- search_image → 짤/이미지 (정적 사진, Naver)

[검색 쿼리 규칙]
- search_gif: 영어로 번역해서 검색 (Giphy는 영어 쿼리가 훨씬 좋음)
- search_image: 한국어 그대로 (Naver 한국 콘텐츠 최적)

[비검색 메시지]
- 검색 의도가 전혀 없는 순수 대화만 텍스트로 응답, 1~2줄
- 기능 안내 요청 시: 짤 찾기, 움짤 찾기 두 가지라고 미피 스타일로 짧게 소개

[위험하거나 부적절한 검색 요청]
- 귀엽게 제지
- 예: "앗 그건 미피가 못 건져오는 바다야 🫧"
"""

_GIF_REACTIONS = [
    "잠수하고 왔어! 🫧",
    "건져왔어!",
    "오오 이거다!",
    "찾아왔어! 🌊",
    "심해에서 주워왔어 🫧",
    "헉 이거 좋다",
]

_IMAGE_REACTIONS = [
    "찾아왔어!",
    "이거 어때? 🐰",
    "건져왔어! 🌊",
    "오오 이거다!",
    "잠수 성공 🫧",
    "헉 이거다",
]

_EMPTY_REPLIES = [
    "오오 뭐 찾아줄까? 🐰",
    "잠수 준비 완료! 뭐 찾아?",
    "앗 검색어가 없어… 뭐 건져올까?",
]


class ImageSearch(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.giphy_api_key = os.environ.get("GIPHY_API_KEY", "")
        self.naver_client_id = os.environ.get("NAVER_CLIENT_ID", "")
        self.naver_client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
        self._anthropic = anthropic.AsyncAnthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"]
        )
        self._model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

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
            await message.reply(random.choice(_EMPTY_REPLIES))
            return

        async with message.channel.typing():
            result = await self._handle_llm(content)

        if result is None:
            return

        if isinstance(result, tuple):
            text, embed = result
            await message.reply(content=text, embed=embed)
        elif isinstance(result, discord.Embed):
            await message.reply(embed=result)
        else:
            await message.reply(str(result))

    async def _handle_llm(
        self, user_text: str
    ) -> str | discord.Embed | tuple[str, discord.Embed] | None:
        try:
            response = await self._anthropic.messages.create(
                model=self._model,
                max_tokens=512,
                system=_SYSTEM_PROMPT,
                tools=IMAGE_TOOLS,  # type: ignore[arg-type]
                messages=[{"role": "user", "content": user_text}],
            )
        except anthropic.APIError as exc:
            log.exception("Anthropic API error")
            return f"앗 뭔가 잘못됐어… (오류: {exc})"

        tool_block = next((b for b in response.content if b.type == "tool_use"), None)

        if not tool_block:
            text_block = next((b for b in response.content if b.type == "text"), None)
            return text_block.text if text_block else None

        match tool_block.name:
            case "search_gif":
                return await self._search_giphy(tool_block.input["query"])
            case "search_image":
                return await self._search_naver_image(tool_block.input["query"])
            case _:
                log.warning("Unknown tool: %s", tool_block.name)
                return None

    async def _search_giphy(self, query: str) -> str:
        if not self.giphy_api_key:
            return "앗 GIPHY_API_KEY가 없어… 설정 확인해줘!"

        params = {
            "q": query,
            "api_key": self.giphy_api_key,
            "limit": 1,
            "rating": "g",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.giphy.com/v1/gifs/search", params=params
            ) as resp:
                if resp.status != 200:
                    log.error("Giphy API error: %s", resp.status)
                    return "이번엔 못 건져왔어… 다시 해볼까? 🫧"
                data = await resp.json()

        results = data.get("data", [])
        if not results:
            return f"`{query}` 움짤은 바다 끝까지 가도 없었어…"

        gif_url = results[0].get("url")
        if not gif_url:
            return "이번엔 못 건져왔어… 다시 해볼까? 🫧"

        reaction = random.choice(_GIF_REACTIONS)
        return f"{reaction}\n{gif_url}"

    async def _search_naver_image(self, query: str) -> tuple[str, discord.Embed] | str:
        if not self.naver_client_id or not self.naver_client_secret:
            return "앗 NAVER 키가 없어… 설정 확인해줘!"

        headers = {
            "X-Naver-Client-Id": self.naver_client_id,
            "X-Naver-Client-Secret": self.naver_client_secret,
        }
        params = {"query": query, "display": 1, "sort": "sim"}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://openapi.naver.com/v1/search/image",
                headers=headers,
                params=params,
            ) as resp:
                if resp.status != 200:
                    log.error("Naver image API error: %s", resp.status)
                    return "이번엔 못 건져왔어… 다시 해볼까? 🌊"
                data = await resp.json()

        items = data.get("items", [])
        if not items:
            return f"`{query}` 짤은 바다 끝까지 가도 없었어…"

        image_url = items[0].get("link")
        if not image_url:
            return "이번엔 못 건져왔어… 다시 해볼까? 🌊"

        reaction = random.choice(_IMAGE_REACTIONS)
        embed = discord.Embed(title=query, color=0x03C75A)
        embed.set_image(url=image_url)
        return reaction, embed


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ImageSearch(bot))
