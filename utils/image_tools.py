WEB_TOOLS: list[dict] = [
    {
        "name": "search_web",
        "description": (
            "인터넷 웹 검색 — Brave Search 사용. "
            "최신 정보, 뉴스, 날씨, 사실 확인, 사람/장소/이벤트 정보 등 실시간 정보가 필요할 때 사용. "
            "이미지나 움짤 요청에는 사용하지 말 것. "
            "운세, 궁합, 사주 해석 등은 검색하지 말고 LLM이 직접 생성. "
            "쿼리는 핵심 키워드로 간결하게."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색어. 핵심 키워드 위주로. 예: '이재명 오늘 뉴스', '서울 날씨 오늘'.",
                },
            },
            "required": ["query"],
        },
    },
]

IMAGE_TOOLS: list[dict] = [
    {
        "name": "search_gif",
        "description": (
            "움짤(animated GIF) 검색 — Giphy 사용. "
            "'움짤', 'gif', 'GIF', '짤방', 애니메이션 요청에만 사용. "
            "'짤'만 단독으로 쓰인 경우는 search_image 사용. "
            "쿼리는 반드시 영어로 번역 (Giphy는 영어 검색 결과가 훨씬 좋음). "
            "예: '웃긴 고양이' → 'funny cat', '깜짝 반응' → 'shocked reaction'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "영어 검색어. 구체적이고 표현력 있게. 예: 'cute bunny jumping', 'excited reaction'.",
                },
                "count": {
                    "type": "integer",
                    "description": "가져올 움짤 수. 기본 1, 최대 5. '3개', '여러 개' 요청 시 반영.",
                    "minimum": 1,
                    "maximum": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_image",
        "description": (
            "짤/이미지(static image) 검색 — Naver 사용. "
            "'짤', '사진', '이미지' 요청에 사용. '움짤'이나 'gif'는 search_gif 사용. "
            "쿼리는 한국어 그대로 사용 (Naver는 한국어 검색이 최적). "
            "예: '귀여운 고양이 짤', '에펠탑 사진', '아이유 사진'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "한국어 검색어. 구체적으로. 예: '귀여운 토끼 짤', '제주도 바다 사진'.",
                },
                "count": {
                    "type": "integer",
                    "description": "가져올 이미지 수. 기본 1, 최대 5. '3장', '여러 개' 요청 시 반영.",
                    "minimum": 1,
                    "maximum": 5,
                },
            },
            "required": ["query"],
        },
    },
]


MEMBER_TOOLS: list[dict] = [
    {
        "name": "save_member_info",
        "description": (
            "사용자가 자신의 개인정보를 공유하거나 설정을 변경할 때 저장. "
            "MBTI: '나 INFP야', '내 MBTI는 ESTJ' → field=mbti. "
            "사주: '내 사주가 1995년 3월생이야' → field=saju. "
            "특징/성격: '나 원래 말 없어', '나 음식 잘 먹음' → field=keyword, 핵심 키워드 1~3단어로 추출. "
            "고민상담 모드: 'T모드로 바꿔줘', 'F모드로 해줘' → field=advice_mode, value='T' or 'F'. "
            "저장 후 미피 캐릭터로 짧게 확인 응답."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "enum": ["mbti", "saju", "keyword", "advice_mode"],
                    "description": "저장할 필드 종류. advice_mode는 'T' 또는 'F'.",
                },
                "value": {
                    "type": "string",
                    "description": "저장할 값. keyword는 핵심 단어로 압축. advice_mode는 'T' 또는 'F'.",
                },
            },
            "required": ["field", "value"],
        },
    },
    {
        "name": "get_my_info",
        "description": (
            "사용자가 자신의 저장된 정보를 물을 때 조회. "
            "예: '내 정보 알려줘', '내 특징 뭐야', '내 MBTI 뭐라고 저장돼있어'. "
            "본인 정보만 조회 가능. 다른 사람 정보 조회 요청은 거절."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

ALL_TOOLS: list[dict] = WEB_TOOLS + MEMBER_TOOLS + IMAGE_TOOLS
