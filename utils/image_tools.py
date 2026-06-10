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


CONFIG_TOOLS: list[dict] = [
    {
        "name": "set_global_mode",
        "description": (
            "미피 봇 전체의 대화 스타일을 T/F 모드로 변경. "
            "'글로벌 T모드로 바꿔줘', '봇 전체 F모드', '미피 T모드 설정' 등. "
            "T=논리/직접/간결, F=공감/따뜻함(기본)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["T", "F"],
                    "description": "T=논리형, F=공감형",
                },
            },
            "required": ["mode"],
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
                    "enum": ["mbti", "saju", "saju_detail", "keyword", "advice_mode", "riot_id", "ziwei_birth"],
                    "description": (
                        "저장할 필드 종류. "
                        "saju=생년월일 등 기본 사주 텍스트. "
                        "saju_detail=년주/월주/일주/시주/오행/십신/대운 등 상세 사주 전체 블록(원문 그대로). "
                        "ziwei_birth=자미두수용 생년월일시 (음양력 포함). "
                        "advice_mode는 'T'/'F'. riot_id는 'Name#Tag' 형식."
                    ),
                },
                "value": {
                    "type": "string",
                    "description": "저장할 값. saju_detail은 사주 원문 블록 전체를 그대로 저장.",
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
    {
        "name": "delete_my_info",
        "description": (
            "내 저장 정보 중 특정 항목 삭제. "
            "'내 MBTI 지워줘', '특징 X 삭제해줘', '내 사주 없애줘', '내 정보 다 지워줘' 등. "
            "field: mbti/saju/keyword/advice_mode/all. "
            "keyword 삭제 시 value에 특정 키워드 명시하면 해당 것만, 없으면 전체 삭제."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "enum": ["mbti", "saju", "saju_detail", "keyword", "advice_mode", "riot_id", "ziwei_birth", "all"],
                    "description": "삭제할 필드. all이면 전체 삭제.",
                },
                "value": {
                    "type": "string",
                    "description": "keyword 필드 삭제 시 특정 키워드 명시 (생략 시 전체 삭제).",
                },
            },
            "required": ["field"],
        },
    },
]

GAME_TOOLS: list[dict] = [
    {
        "name": "get_game_list",
        "description": (
            "저장된 스팀 게임 위시리스트 조회. "
            "'게임 목록', '게임 리스트', '안 해본 게임', '해본 게임', '위시리스트' 등 요청 시 사용."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "enum": ["all", "unplayed", "played"],
                    "description": "all=전체, unplayed=미플레이만, played=플레이완료만. 기본 all.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "mark_game_played",
        "description": (
            "게임 플레이 여부 업데이트. "
            "'X 해봤어', 'X 했어', 'X 완료' → played=true. "
            "'X 안 해봤어로 되돌려줘' → played=false."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "game_name": {
                    "type": "string",
                    "description": "게임 이름 (부분 일치 허용) 또는 Steam appid.",
                },
                "played": {
                    "type": "boolean",
                    "description": "true=플레이완료, false=미플레이로 되돌리기. 기본 true.",
                },
            },
            "required": ["game_name"],
        },
    },
    {
        "name": "delete_game",
        "description": (
            "게임 목록에서 특정 게임 삭제. "
            "'X 지워줘', 'X 삭제해줘', 'X 목록에서 빼줘' 등 요청 시 사용."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "game_name": {
                    "type": "string",
                    "description": "삭제할 게임 이름 (부분 일치) 또는 appid.",
                },
            },
            "required": ["game_name"],
        },
    },
    {
        "name": "get_game_link",
        "description": (
            "특정 게임의 스팀 링크 반환. "
            "'X 링크', 'X 스팀 주소', 'X 어디서 사' 등 요청 시 사용."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "game_name": {
                    "type": "string",
                    "description": "게임 이름 (부분 일치 허용) 또는 Steam appid.",
                },
            },
            "required": ["game_name"],
        },
    },
]

RIOT_TOOLS: list[dict] = [
    {
        "name": "get_lol_stats",
        "description": (
            "리그 오브 레전드 전적 조회. "
            "'전적 보여줘', '롤 전적', '요즘 롤 어때', 'LoL 성적' 등 요청 시 사용. "
            "riot_id 미입력 시 사용자 본인의 저장된 ID로 조회. "
            "다른 멤버 전적: '진욱 전적 보여줘' → riot_id에 해당 멤버 ID 입력 (알면)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "riot_id": {
                    "type": "string",
                    "description": "조회할 Riot ID (Name#Tag). 비워두면 본인 저장 ID 사용.",
                },
                "count": {
                    "type": "integer",
                    "description": "조회할 최근 게임 수. 기본 5, 최대 10.",
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": [],
        },
    },
]

ALL_TOOLS: list[dict] = CONFIG_TOOLS + WEB_TOOLS + MEMBER_TOOLS + RIOT_TOOLS + GAME_TOOLS + IMAGE_TOOLS
