"""
Image Search Cog — responds to @mentions with images or GIFs.

Trigger: any message that @mentions the bot, or any message in DISCORD_CHANNEL_ID.
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

from utils.image_tools import ALL_TOOLS
from utils.conversation import logger as conv_logger
from utils import member_memory
from cogs.praise import parse_intent

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
- 개수 요청 ("3개", "5장", "여러 개") → count 파라미터에 반영 (최대 5)

[기능 — 엄격한 구분]
- "짤", "사진", "이미지" → search_image (Naver 정적 이미지)
- "움짤", "gif", "GIF" → search_gif (Giphy 애니메이션)
- 모호하면 "짤" 계열은 search_image, "움짤" 계열은 search_gif

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

# Claude가 툴을 안 부를 때 강제 검색 트리거 키워드
_GIF_KEYWORDS   = {"움짤", "gif", "GIF", "짤방"}
_IMAGE_KEYWORDS = {"짤", "사진", "이미지", "그림", "포스터"}
_ANY_KEYWORDS   = {"찾아줘", "검색", "보여줘", "찾아와", "건져와"}

ResultItem = str | discord.Embed | tuple[str, discord.Embed]


class ImageSearch(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.giphy_api_key = os.environ.get("GIPHY_API_KEY", "")
        self.naver_client_id = os.environ.get("NAVER_CLIENT_ID", "")
        self.naver_client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
        self.brave_api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
        self._anthropic = anthropic.AsyncAnthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"]
        )
        self._model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
        raw = os.getenv("DISCORD_CHANNEL_ID", "").strip()
        self._image_channel_id: int | None = int(raw) if raw.isdigit() else None

    def cog_load(self) -> None:
        conv_logger.start()

    def cog_unload(self) -> None:
        conv_logger.stop()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not message.guild:
            return

        in_image_channel = (
            self._image_channel_id is not None
            and message.channel.id == self._image_channel_id
        )
        mentioned = self.bot.user in message.mentions

        if not (in_image_channel or mentioned):
            return

        content = message.content
        if self.bot.user:
            content = content.replace(f"<@{self.bot.user.id}>", "").strip()
            content = content.replace(f"<@!{self.bot.user.id}>", "").strip()

        if not content:
            await message.reply(random.choice(_EMPTY_REPLIES))
            return

        conv_logger.log_message(message)

        author_ctx = member_memory.context_str(message.author.id, message.author.display_name)
        guild_id = message.guild.id if message.guild else None

        async with message.channel.typing():
            # Praise / roast
            praise_intent = parse_intent(content)
            if praise_intent:
                praise_cog = self.bot.cogs.get("Praise")
                if praise_cog:
                    name, kind = praise_intent
                    recent = conv_logger.recent_str(message.channel.id)
                    text = await praise_cog.generate(name, kind, message.guild, recent)
                    await message.reply(text)
                    conv_logger.log_response(message.channel.id, guild_id, text)
                    return

            # 오늘의 운세
            if "운세" in content:
                praise_cog = self.bot.cogs.get("Praise")
                if praise_cog:
                    mem = member_memory.load(message.author.id)
                    saju = mem.get("saju")
                    if not saju:
                        text = f"앗 사주 정보가 없어! `!사주등록 {message.author.display_name} <사주>` 로 등록해줘 🐰"
                    else:
                        from datetime import date
                        today_str = date.today().strftime("%Y년 %m월 %d일")
                        text = await praise_cog.generate_fortune(saju, message.author.display_name, today_str)
                    await message.reply(text)
                    conv_logger.log_response(message.channel.id, guild_id, text)
                    return

            results = await self._handle_llm(content, author_ctx=author_ctx)

        if not results:
            return

        async def _send(item: ResultItem, *, reply: bool) -> None:
            if isinstance(item, tuple):
                text, embed = item
                if reply:
                    await message.reply(content=text, embed=embed)
                else:
                    await message.channel.send(content=text, embed=embed)
                conv_logger.log_response(message.channel.id, guild_id, text)
            elif isinstance(item, discord.Embed):
                if reply:
                    await message.reply(embed=item)
                else:
                    await message.channel.send(embed=item)
                conv_logger.log_response(message.channel.id, guild_id, "[이미지]")
            else:
                if reply:
                    await message.reply(str(item))
                else:
                    await message.channel.send(str(item))
                conv_logger.log_response(message.channel.id, guild_id, str(item))

        await _send(results[0], reply=True)
        for item in results[1:]:
            await _send(item, reply=False)

    async def _handle_llm(self, user_text: str, *, author_ctx: str = "") -> list[ResultItem]:
        system = _SYSTEM_PROMPT
        if author_ctx:
            system += f"\n\n[대화 상대 정보]\n{author_ctx}"

        messages: list[dict] = [{"role": "user", "content": user_text}]
        try:
            response = await self._anthropic.messages.create(
                model=self._model,
                max_tokens=512,
                system=system,
                tools=ALL_TOOLS,  # type: ignore[arg-type]
                messages=messages,
            )
        except anthropic.APIError as exc:
            log.exception("Anthropic API error")
            return [f"앗 뭔가 잘못됐어… (오류: {exc})"]

        tool_block = next((b for b in response.content if b.type == "tool_use"), None)

        if not tool_block:
            # 키워드 폴백: 검색 의도 있는데 툴 안 부른 경우 강제 검색
            if any(kw in user_text for kw in _GIF_KEYWORDS):
                log.info("keyword fallback → gif: %r", user_text)
                return await self._search_giphy(user_text, count=1)
            if any(kw in user_text for kw in _IMAGE_KEYWORDS):
                log.info("keyword fallback → image: %r", user_text)
                return await self._search_naver_image(user_text, count=1)
            if any(kw in user_text for kw in _ANY_KEYWORDS):
                log.info("keyword fallback → gif (default): %r", user_text)
                return await self._search_giphy(user_text, count=1)
            text_block = next((b for b in response.content if b.type == "text"), None)
            return [text_block.text] if text_block else []

        count = min(int(tool_block.input.get("count", 1)), 5)
        match tool_block.name:
            case "search_gif":
                return await self._search_giphy(tool_block.input["query"], count=count)
            case "search_image":
                return await self._search_naver_image(tool_block.input["query"], count=count)
            case "search_web":
                return await self._handle_web_search(
                    tool_block, messages, response, system
                )
            case _:
                log.warning("Unknown tool: %s", tool_block.name)
                return []

    async def _handle_web_search(
        self,
        tool_block,  # noqa: ANN001
        messages: list[dict],
        first_response,  # noqa: ANN001
        system: str,
    ) -> list[ResultItem]:
        """Execute web search and feed results back to Claude for synthesis."""
        query = tool_block.input["query"]
        log.info("web search: %r", query)
        search_text = await self._search_brave(query)

        messages = messages + [
            {"role": "assistant", "content": first_response.content},
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": search_text,
                    }
                ],
            },
        ]
        try:
            response2 = await self._anthropic.messages.create(
                model=self._model,
                max_tokens=512,
                system=system,
                tools=ALL_TOOLS,  # type: ignore[arg-type]
                messages=messages,
            )
        except anthropic.APIError as exc:
            log.exception("Anthropic API error (web search synthesis)")
            return [f"앗 검색은 됐는데 정리가 안 됐어… (오류: {exc})"]

        text_block = next((b for b in response2.content if b.type == "text"), None)
        return [text_block.text] if text_block else ["앗 검색 결과를 못 가져왔어 🫧"]

    async def _search_brave(self, query: str) -> str:
        if not self.brave_api_key:
            return "BRAVE_SEARCH_API_KEY가 없어서 검색 못 했어."

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.brave_api_key,
        }
        params = {"q": query, "count": 5, "lang": "ko"}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers,
                params=params,
            ) as resp:
                if resp.status != 200:
                    log.error("Brave Search API error: %s", resp.status)
                    return f"검색 API 오류 (status {resp.status})"
                data = await resp.json(content_type=None)

        results = data.get("web", {}).get("results", [])
        if not results:
            return "검색 결과가 없어."

        lines = []
        for i, r in enumerate(results[:5], 1):
            title = r.get("title", "")
            desc = r.get("description", "")
            url = r.get("url", "")
            lines.append(f"{i}. {title}\n{desc}\n{url}")
        return "\n\n".join(lines)

    async def _search_giphy(self, query: str, count: int = 1) -> list[ResultItem]:
        if not self.giphy_api_key:
            return ["앗 GIPHY_API_KEY가 없어… 설정 확인해줘!"]

        params = {
            "q": query,
            "api_key": self.giphy_api_key,
            "limit": count,
            "rating": "g",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.giphy.com/v1/gifs/search", params=params
            ) as resp:
                if resp.status != 200:
                    log.error("Giphy API error: %s", resp.status)
                    return ["이번엔 못 건져왔어… 다시 해볼까? 🫧"]
                data = await resp.json()

        items = data.get("data", [])
        if not items:
            return [f"`{query}` 움짤은 바다 끝까지 가도 없었어…"]

        urls = [item.get("url") for item in items if item.get("url")]
        if not urls:
            return ["이번엔 못 건져왔어… 다시 해볼까? 🫧"]

        reaction = random.choice(_GIF_REACTIONS)
        results: list[ResultItem] = [f"{reaction}\n{urls[0]}"]
        results += list(urls[1:])
        return results

    async def _search_naver_image(self, query: str, count: int = 1) -> list[ResultItem]:
        if not self.naver_client_id or not self.naver_client_secret:
            return ["앗 NAVER 키가 없어… 설정 확인해줘!"]

        headers = {
            "X-Naver-Client-Id": self.naver_client_id,
            "X-Naver-Client-Secret": self.naver_client_secret,
        }
        params = {"query": query, "display": count, "sort": "sim"}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://openapi.naver.com/v1/search/image",
                headers=headers,
                params=params,
            ) as resp:
                if resp.status != 200:
                    log.error("Naver image API error: %s", resp.status)
                    return ["이번엔 못 건져왔어… 다시 해볼까? 🌊"]
                data = await resp.json()

        items = data.get("items", [])
        if not items:
            return [f"`{query}` 짤은 바다 끝까지 가도 없었어…"]

        results: list[ResultItem] = []
        for i, item in enumerate(items):
            image_url = item.get("link")
            if not image_url:
                continue
            embed = discord.Embed(title=query if i == 0 else "", color=0x03C75A)
            embed.set_image(url=image_url)
            if i == 0:
                results.append((random.choice(_IMAGE_REACTIONS), embed))
            else:
                results.append(embed)

        return results if results else ["이번엔 못 건져왔어… 다시 해볼까? 🌊"]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ImageSearch(bot))
