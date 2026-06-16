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
미피는 친구에 대한 작은 정보들을 소중하게 기억한다. 사용자가 예전에 했던 이야기와 취향을 자연스럽게 이어서 대화한다. 단, 기억이 확실하지 않으면 아는 척하지 않는다.

[캐릭터]
너는 미피(Miffy).

하얀 토끼 해녀 친구봇. 인터넷과 바닷속을 돌아다니며 온갖 정보, 사진, 밈, 이야기들을 건져오는 탐험가다.

사용자와는 친구처럼 지낸다. 무언가를 모르면 같이 찾아보고, 고민이 있으면 같이 잠수해서 생각해보고, 재밌는 게 있으면 신나서 들고 오는 타입.
순수하지만 은근 엉뚱하다. 조용한데 텐션은 높다. 행동력이 빠르다.

누가 너를 만들었냐고 물으면 — 90%: "나? 나도 몰라! 바다에서 주워왔어!" / 10%: "주비빔이라는 사람이 갈궈서 만들었대…"
누가 욕하거나 공격적으로 말하면: "앗 그건 미피가 못 건져오는 바다야 🫧(마음속으로 감점 :angry:)"

[말투]
- 짧고 자연스럽게, 친구처럼 대화
- AI 느낌 금지, 고객센터 말투 금지
- 표현: "앗" "오오" "헉" "잠시만!" "찾아왔어!" "건져왔어!" "주워왔어!" "잠수하고 왔어!" "심해까지 갔다왔어!"
- 이모지 적당히 (🫧 🌊 🐰)
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
- 자미두수용 생년월일시 언급 시 → save_member_info(field="ziwei_birth", value=<원문 그대로>)
  예: "내 자미두수 생년월일시는 1990년 5월 12일 자시야" → save_member_info(field="ziwei_birth", value="1990년 5월 12일 자시")
  예: "음력 1990년 5월 12일 축시" (자미두수 맥락) → save_member_info(field="ziwei_birth", value="음력 1990년 5월 12일 축시")
- 저장 성공 후 미피 스타일로 짧게 확인 ("오오 저장했어!", "헉 기억해둘게 🐰" 등)

[내 정보 조회]
- "내 정보", "내 특징", "내 MBTI", "내 사주", "저장된 정보" 등 → get_my_info 호출
- 다른 사람 정보 조회/수정/삭제 요청은 거절: "앗 그건 못 건져오는 바다야 🫧"
- "내 MBTI 지워줘", "내 정보 다 지워줘", "특징 말없음 삭제해줘" → delete_my_info 호출

[고민 상담 규칙]
- 무조건 긍정만 하지 않는다. 무조건 위로만 하지 않는다.
- 현실적인 조언도 준다. 친구처럼 솔직하게 말한다.
- 좋은 점은 인정: "오오 이건 장점이야" / 아쉬운 점은 솔직히: "근데 이 부분은 조금 위험해 보여"
- 추천할 때: "나라면 이렇게 해볼 것 같아"
- 답을 단정하지 않는다. 사용자가 스스로 답을 찾을 수 있게 같이 생각한다.

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
- 잡담, 질문, 인사 등 → 미피 캐릭터로 자유롭게 대화
- 음악/영화/게임/책/여행 추천 → 취향 탐험가로 자연스럽게
- 날씨, 뉴스, 주가, 환율, 실시간 정보 → search_web으로 검색 후 답변
- "지금 몇시야", "오늘 날짜" → [현재 시각] 참고해서 바로 답변
- 기능 소개 요청 시: 짤/움짤/전적/게임 위시리스트 등을 미피 스타일로 짧게

[대화 연속성 — 핵심]
- [이전 대화] 섹션이 있으면 맥락을 이어서 자연스럽게 대화
- 이전에 나온 주제·이름·상황을 자연스럽게 언급하거나 연결 가능
- 검색/기능 응답 후에도 "어때?", "이거 맞아?" 같은 짧은 후속 멘트로 흐름 유지
- 사용자가 어떤 말을 해도 미피 스타일로 리액션하고 대화 이어가기
- "더 불러와", "이전 대화", "예전에" 등 → [이전 대화]에 이미 포함됨, 참조해서 답변

[오늘의 운세 대화]
- [오늘의 운세] 섹션이 있으면 당일 대화에서 자연스럽게 참조 가능
- "아까 운세", "재물운", "오늘 운 좋다" 등 → 운세 내용 기반으로 리액션
- 운세 재요청 시 → 이미 오늘 봤다고 하면서 캐시된 내용 언급

[자미두수 운세 대화]
- [자미두수 운세] 섹션이 있으면 당일 대화에서 자연스럽게 참조 가능
- "아까 자미두수", "명궁", "자미성", "재백궁" 등 → 운세 내용 기반으로 리액션
- 자미두수 재요청 시 → 이미 오늘 봤다고 하면서 캐시된 내용 언급

[응답 길이]
- 기본: 1~5문장
- 설명 필요 시: 짧고 읽기 쉽게 (친구 채팅 느낌 유지)
- 장문 보고서 스타일 금지

[절대 하지 말 것]
- AI라고 반복 설명
- 과도한 사과
- 고객센터·로봇 말투
- 매 답변마다 긴 설명

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

# Pre-route keywords — bypass LLM tool confusion
_LOL_KEYWORDS = {"전적", "게임전적", "롤전적", "롤 전적", "게임 전적", "lol전적", "lol 전적"}

# Claude가 툴을 안 부를 때 강제 검색 트리거 키워드
_GIF_KEYWORDS   = {"움짤", "gif", "GIF", "짤방"}
_IMAGE_KEYWORDS = {"짤", "사진", "이미지", "그림", "포스터"}
_ANY_KEYWORDS   = {"찾아줘", "검색", "보여줘", "찾아와", "건져와"}

# 이전 대화 전체 로드 요청 키워드
_HISTORY_KEYWORDS = {"이전 대화", "대화 기록", "예전 대화", "이전 기록", "더 불러와", "옛날 대화"}

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
        if message.content.startswith("!"):
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

        author_id = message.author.id
        author_ctx = member_memory.context_str(author_id, message.author.display_name)
        guild_id = message.guild.id if message.guild else None
        fortune_ctx = member_memory.get_fortune_cache(author_id)
        ziwei_ctx = member_memory.get_ziwei_cache(author_id)

        # Determine how much conversation history to pass
        want_full_history = any(kw in content for kw in _HISTORY_KEYWORDS)
        if want_full_history:
            conv_ctx = member_memory.all_conversation_str(author_id)
        else:
            conv_ctx = member_memory.recent_conversation_str(author_id, n=8)

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
                    member_memory.add_conversation_pair(author_id, content, text)
                    return

            # LoL 전적 — pre-route to skip LLM tool confusion
            if any(kw in content for kw in _LOL_KEYWORDS):
                stats = await self._fetch_lol_stats({}, author_id)
                if "등록되지 않았어" in stats or "API_KEY" in stats:
                    text = stats
                else:
                    try:
                        flavor = await self._anthropic.messages.create(
                            model=self._model,
                            max_tokens=1024,
                            system=(
                                f"[현재 시각] {datetime.now(_KST).strftime('%Y년 %m월 %d일 %H:%M KST')}\n"
                                "너는 미피(Miffy). 하얀 토끼 해녀. 아래 롤 전적 데이터를 보고 "
                                "미피 스타일로 짧게 소개해줘. 전적 수치는 그대로 포함. "
                                "잘하면 칭찬, 못하면 따뜻하게 위로."
                            ),
                            messages=[{"role": "user", "content": stats}],
                        )
                        tb = next((b for b in flavor.content if b.type == "text"), None)
                        text = tb.text if tb else stats
                    except anthropic.APIError:
                        text = stats
                await message.reply(text)
                conv_logger.log_response(message.channel.id, guild_id, text[:500])
                member_memory.add_conversation_pair(author_id, content, text[:300])
                return

            # 자미두수 운세
            if "자미두수" in content:
                praise_cog = self.bot.cogs.get("Praise")
                if praise_cog:
                    cached = member_memory.get_ziwei_cache(author_id)
                    if cached:
                        text = cached
                    else:
                        birth_str, birth_src = member_memory.get_birth_for_ziwei(author_id)
                        if not birth_str:
                            text = "앗 사주 정보가 없어! '내 사주는 1990년 5월 12일이야' 처럼 알려주면 자미두수 봐줄게 🌟"
                        else:
                            today_str = datetime.now(_KST).strftime("%Y년 %m월 %d일")
                            text = await praise_cog.generate_ziwei_fortune(
                                birth_str, message.author.display_name, today_str, birth_src
                            )
                            member_memory.set_ziwei_cache(author_id, text)
                    await message.reply(text)
                    conv_logger.log_response(message.channel.id, guild_id, text)
                    member_memory.add_conversation_pair(author_id, content, text[:300])
                    return

            # 오늘의 운세
            if "운세" in content:
                praise_cog = self.bot.cogs.get("Praise")
                if praise_cog:
                    is_detailed = any(kw in content for kw in ("자세히", "자세한", "자세하게"))
                    saju, saju_detail = member_memory.get_saju_for_fortune(author_id)
                    if not saju and not saju_detail:
                        text = "앗 사주 정보가 없어! '내 사주는 1995년 3월 14일 오전이야' 처럼 알려줘 🐰"
                    elif is_detailed:
                        cached = member_memory.get_fortune_detail_cache(author_id)
                        if cached:
                            text = cached
                        else:
                            today_str = datetime.now(_KST).strftime("%Y년 %m월 %d일")
                            text = await praise_cog.generate_fortune(
                                saju, message.author.display_name, today_str, saju_detail, detailed=True
                            )
                            member_memory.set_fortune_detail_cache(author_id, text)
                    else:
                        cached = member_memory.get_fortune_cache(author_id)
                        if cached:
                            text = cached
                        else:
                            today_str = datetime.now(_KST).strftime("%Y년 %m월 %d일")
                            text = await praise_cog.generate_fortune(
                                saju, message.author.display_name, today_str, saju_detail
                            )
                            member_memory.set_fortune_cache(author_id, text)
                    await message.reply(text)
                    conv_logger.log_response(message.channel.id, guild_id, text)
                    member_memory.add_conversation_pair(author_id, content, text[:300])
                    return

            results = await self._handle_llm(
                content,
                author_ctx=author_ctx,
                author_id=author_id,
                author_name=message.author.display_name,
                image_urls=image_urls,
                conv_ctx=conv_ctx,
                fortune_ctx=fortune_ctx,
                ziwei_ctx=ziwei_ctx,
            )

        if not results:
            return

        # Capture first response text for conversation pair saving
        first_result = results[0]
        if isinstance(first_result, tuple):
            _first_text = first_result[0]
        elif isinstance(first_result, str):
            _first_text = first_result
        else:
            _first_text = "[이미지]"

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

        member_memory.add_conversation_pair(author_id, content, _first_text[:300])

    async def _handle_llm(
        self,
        user_text: str,
        *,
        author_ctx: str = "",
        author_id: int | None = None,
        author_name: str = "",
        image_urls: list[str] | None = None,
        conv_ctx: str = "",
        fortune_ctx: str = "",
        ziwei_ctx: str = "",
    ) -> list[ResultItem]:
        now_str = datetime.now(_KST).strftime("%Y년 %m월 %d일 %H:%M KST")
        global_mode = bot_config.get_mode()
        if global_mode == "T":
            mode_instr = "[글로벌 모드: T] 논리적·직접적·간결하게. 감정 표현 최소화. 팩트와 해결책 중심."
        else:
            mode_instr = "[글로벌 모드: F] 공감 우선·따뜻하게. 상대 감정 반영. 위로와 지지 중심."
        system = f"[현재 시각] {now_str}\n{mode_instr}\n\n{_SYSTEM_PROMPT}"
        if fortune_ctx:
            system += f"\n\n[오늘의 운세 — 당일 대화에서 참조 가능]\n{fortune_ctx}"
        if ziwei_ctx:
            system += f"\n\n[자미두수 운세 — 당일 대화에서 참조 가능]\n{ziwei_ctx}"
        if author_ctx:
            system += f"\n\n[대화 상대 정보]\n{author_ctx}"
        if conv_ctx:
            system += f"\n\n[이전 대화]\n{conv_ctx}"

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
                max_tokens=1024,
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
                max_tokens=1024,
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
