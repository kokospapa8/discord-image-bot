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
