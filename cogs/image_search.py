"""
Image Search Cog — responds to @mentions with images or GIFs.

Trigger: any message that @mentions the bot, or any message in DISCORD_CHANNEL_ID.
LLM: Miffy(Claude) decides between search_gif (Giphy) and search_image (Naver).
"""
from __future__ import annotations

import logging
import os
import random
import re
from datetime import datetime, timezone, timedelta

_KST = timezone(timedelta(hours=9))

import aiohttp
import anthropic
import discord
from discord.ext import commands

from utils.image_tools import ALL_TOOLS
from utils.conversation import logger as conv_logger
from utils import member_memory, game_store, riot_api, bot_config
from cogs.praise import parse_intent

log = logging.getLogger(__name__)

_IMAGE_URL_RE = re.compile(
    r"https?://\S+\.(?:jpg|jpeg|png|gif|webp|avif)(?:[?#]\S*)?",
    re.IGNORECASE,
)

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

[글로벌 모드 변경]
- "글로벌 T모드", "봇 전체 T모드로 바꿔", "미피 F모드 설정" 등 → set_global_mode 호출
- 변경 후 미피 스타일로 짧게 확인

[멤버 정보 자동 저장/조회/삭제 — 본인만]
- 사용자가 MBTI, 사주, 성격/특징을 언급하면 반드시 save_member_info 호출
  예: "나 INFP야" → save_member_info(field="mbti", value="INFP")
  예: "내 사주 1995년 3월 14일 오전이야" → save_member_info(field="saju", value="1995년 3월 14일 오전")
  예: "나 원래 말 없어" → save_member_info(field="keyword", value="말없음")
- 고민상담 모드 변경 요청: "T모드로 바꿔줘", "F모드로 해줘" → save_member_info(field="advice_mode", value="T" or "F")
- 상세 사주 블록 (년주/월주/일주/시주/오행/십신/대운 등 여러 줄) → save_member_info(field="saju_detail", value=<원문 전체>)
- 저장 성공 후 미피 스타일로 짧게 확인 ("오오 저장했어!", "헉 기억해둘게 🐰" 등)

[내 정보 조회]
- "내 정보", "내 특징", "내 MBTI", "내 사주", "저장된 정보" 등 → get_my_info 호출
- 다른 사람 정보 조회/수정/삭제 요청은 거절: "앗 그건 못 건져오는 바다야 🫧"
- "내 MBTI 지워줘", "내 정보 다 지워줘", "특징 말없음 삭제해줘" → delete_my_info 호출

[고민상담 모드 — [대화 상대 정보]에 포함됨]
- advice_mode T모드: 논리적, 직접적, 원인/해결책 위주. 공감보다 팩트와 조언.
- advice_mode F모드(기본): 공감 먼저, "그랬구나", "힘들었겠다" 로 시작. 따뜻하게.
- 모드 미설정 시 F모드로 대응

[이미지 분석]
- 사용자가 이미지를 첨부하거나 이미지 URL을 보낸 경우 볼 수 있어
- "분석해줘", "설명해줘", "이거 뭐야", "봐줘", "어때" 등 분석 요청이 있을 때만 설명
- 분석 요청이 없으면 이미지는 무시하고 텍스트 요청대로 처리 (예: 짤 검색)
- 분석 시 미피 캐릭터로 재밌게, 2~4줄

[롤 전적 조회]
- "전적", "롤 전적", "요즘 롤", "성적" 등 → get_lol_stats 호출
- riot_id 미등록 시: "앗 라이엇 ID가 없어! '내 라이엇 ID는 Name#Tag야' 라고 알려줘 🐰"
- 조회 결과를 미피 스타일로 짧게 코멘트 (잘하면 칭찬, 못하면 위로)
- "내 라이엇 ID는 Hide#KR1이야" → save_member_info(field="riot_id", value="Hide#KR1")

[게임 위시리스트 — 누구나 조회/수정/삭제 가능]
- "게임 목록", "위시리스트", "안 해본 게임", "해본 게임" → get_game_list 호출
- "X 해봤어", "X 완료", "X 했어" → mark_game_played(game_name=X, played=true)
- "X 링크", "X 스팀 주소" → get_game_link(game_name=X)
- "X 지워줘", "X 삭제해줘" → delete_game(game_name=X)
- 결과를 미피 스타일로 자연스럽게 안내

[일반 대화]
- 잡담, 질문, 인사 등 → 미피 캐릭터로 자유롭게 대화, 1~2줄
- 날씨, 뉴스, 주가, 환율, 실시간 정보 → search_web으로 검색 후 답변
- "지금 몇시야", "오늘 날짜" → [현재 시각] 참고해서 바로 답변
- 기능 소개 요청 시: 짤/움짤/전적/게임 위시리스트 등을 미피 스타일로 짧게

[제지 — 성인·폭력·불법 콘텐츠 요청에만 적용]
- "앗 그건 미피가 못 건져오는 바다야 🫧"
- 날씨·뉴스·일반 대화에는 절대 이 응답 쓰지 말 것
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
        self.riot_api_key = os.environ.get("RIOT_API_KEY", "")
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

        # Collect image URLs from attachments and text
        image_urls: list[str] = [
            att.url
            for att in message.attachments
            if att.content_type and att.content_type.startswith("image/")
        ]
        image_urls += _IMAGE_URL_RE.findall(content)
        image_urls = image_urls[:4]  # Claude supports up to 4 images per request

        if not content and not image_urls:
            await message.reply(random.choice(_EMPTY_REPLIES))
            return
        if not content:
            content = "이 이미지 봐줘"

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
                    saju, saju_detail = member_memory.get_saju_for_fortune(message.author.id)
                    if not saju and not saju_detail:
                        text = "앗 사주 정보가 없어! '내 사주는 1995년 3월 14일 오전이야' 처럼 알려줘 🐰"
                    else:
                        today_str = datetime.now(_KST).strftime("%Y년 %m월 %d일")
                        text = await praise_cog.generate_fortune(
                            saju, message.author.display_name, today_str, saju_detail
                        )
                    await message.reply(text)
                    conv_logger.log_response(message.channel.id, guild_id, text)
                    return

            results = await self._handle_llm(
                content,
                author_ctx=author_ctx,
                author_id=message.author.id,
                author_name=message.author.display_name,
                image_urls=image_urls,
            )

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

    async def _handle_llm(
        self,
        user_text: str,
        *,
        author_ctx: str = "",
        author_id: int | None = None,
        author_name: str = "",
        image_urls: list[str] | None = None,
    ) -> list[ResultItem]:
        now_str = datetime.now(_KST).strftime("%Y년 %m월 %d일 %H:%M KST")
        global_mode = bot_config.get_mode()
        if global_mode == "T":
            mode_instr = "[글로벌 모드: T] 논리적·직접적·간결하게. 감정 표현 최소화. 팩트와 해결책 중심."
        else:
            mode_instr = "[글로벌 모드: F] 공감 우선·따뜻하게. 상대 감정 반영. 위로와 지지 중심."
        system = f"[현재 시각] {now_str}\n{mode_instr}\n\n{_SYSTEM_PROMPT}"
        if author_ctx:
            system += f"\n\n[대화 상대 정보]\n{author_ctx}"

        if image_urls:
            user_content: list[dict] = [{"type": "text", "text": user_text}]
            for url in image_urls:
                user_content.append({
                    "type": "image",
                    "source": {"type": "url", "url": url},
                })
            messages: list[dict] = [{"role": "user", "content": user_content}]
        else:
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

        tool_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_blocks:
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

        # Media tools return images directly (no roundtrip needed)
        first = tool_blocks[0]
        if first.name in ("search_gif", "search_image"):
            count = min(int(first.input.get("count", 1)), 5)
            if first.name == "search_gif":
                return await self._search_giphy(first.input["query"], count=count)
            return await self._search_naver_image(first.input["query"], count=count)

        # Execute ALL tool_use blocks and collect results for roundtrip.
        # This handles the case where Claude calls multiple tools at once
        # (e.g. save_member_info twice for MBTI + 사주 in one message).
        tool_results = []
        for tb in tool_blocks:
            result_str = await self._execute_tool(tb, author_id, author_name)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tb.id,
                "content": result_str,
            })

        next_messages = messages + [
            {"role": "assistant", "content": response.content},
            {"role": "user", "content": tool_results},
        ]
        try:
            response2 = await self._anthropic.messages.create(
                model=self._model,
                max_tokens=512,
                system=system,
                tools=ALL_TOOLS,  # type: ignore[arg-type]
                messages=next_messages,
            )
        except anthropic.APIError as exc:
            log.exception("Anthropic API error (tool roundtrip)")
            return [f"앗 뭔가 잘못됐어… (오류: {exc})"]

        text_block = next((b for b in response2.content if b.type == "text"), None)
        return [text_block.text] if text_block else ["앗 결과를 못 가져왔어 🫧"]

    async def _execute_tool(self, tb, author_id: int | None, author_name: str) -> str:  # noqa: ANN001
        """Execute a single tool_use block and return its result as a string."""
        match tb.name:
            case "set_global_mode":
                mode = tb.input.get("mode", "F").upper()
                bot_config.set_mode(mode)
                log.info("global mode set to %s", mode)
                return f"{mode}모드로 변경됨"
            case "search_web":
                return await self._search_brave(tb.input["query"])
            case "save_member_info":
                return self._do_save_member_info(tb.input, author_id, author_name)
            case "get_my_info":
                info = member_memory.format_for_display(author_id, author_name) if author_id else ""
                return info if info else "저장된 정보가 없어."
            case "delete_my_info":
                return self._do_delete_my_info(tb.input, author_id, author_name)
            case "get_lol_stats":
                return await self._fetch_lol_stats(tb.input, author_id)
            case "get_game_list":
                return game_store.format_list(tb.input.get("filter", "all"))
            case "mark_game_played":
                found = game_store.mark_played(
                    tb.input.get("game_name", ""), bool(tb.input.get("played", True))
                )
                return f"완료: {found}" if found else f"'{tb.input.get('game_name')}' 못 찾았어."
            case "get_game_link":
                game = game_store.find_game(tb.input.get("game_name", ""))
                return f"{game['name']}: {game['url']}" if game else "못 찾았어."
            case "delete_game":
                deleted = game_store.delete_game(tb.input.get("game_name", ""))
                return f"삭제됨: {deleted}" if deleted else "못 찾았어."
            case _:
                log.warning("Unknown tool: %s", tb.name)
                return "알 수 없는 툴"

    async def _fetch_lol_stats(self, inp: dict, author_id: int | None) -> str:
        if not self.riot_api_key:
            return "앗 RIOT_API_KEY가 없어… 설정 확인해줘!"

        riot_id = (inp.get("riot_id") or "").strip()

        # Fall back to author's saved riot_id
        if not riot_id and author_id:
            mem = member_memory.load(author_id)
            riot_id = mem.get("riot_id", "")

        if not riot_id:
            return "Riot ID가 등록되지 않았어. '내 라이엇 ID는 Name#Tag야' 라고 알려줘!"

        count = min(int(inp.get("count", 5)), 10)
        log.info("lol stats: %r count=%d", riot_id, count)
        return await riot_api.format_stats(riot_id, count, self.riot_api_key)

    def _do_delete_my_info(
        self, inp: dict, author_id: int | None, author_name: str
    ) -> str:
        if author_id is None:
            return "삭제 실패: 사용자 ID 없음"
        field = inp.get("field", "")
        value = inp.get("value", "").strip()
        if field == "all":
            member_memory.save(author_id, {})
            log.info("deleted all member info: id=%s", author_id)
            return "전체 삭제됨"
        if field == "keyword" and value:
            ok = member_memory.delete_keyword(author_id, value)
            return f"키워드 '{value}' 삭제됨" if ok else f"키워드 '{value}' 를 못 찾았어."
        ok = member_memory.delete_field(author_id, field)
        log.info("deleted member field: id=%s field=%s", author_id, field)
        return f"{field} 삭제됨" if ok else f"{field} 정보가 없었어."

    def _do_save_member_info(
        self, inp: dict, author_id: int | None, author_name: str
    ) -> str:
        if author_id is None:
            return "저장 실패: 사용자 ID 없음"
        field = inp.get("field", "")
        value = inp.get("value", "").strip()
        if not value:
            return "저장 실패: 값이 비어있음"
        if field == "keyword":
            member_memory.add_keyword(author_id, author_name, value)
        else:
            member_memory.set_field(author_id, author_name, field, value)
        log.info("saved member info: id=%s field=%s value=%r", author_id, field, value)
        return "저장됨"

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
