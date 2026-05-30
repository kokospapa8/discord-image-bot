"""Per-member persistent memory (keywords, MBTI, 사주)."""
from __future__ import annotations

import json
from pathlib import Path

_DIR = Path("/app/data/members")


def _path(member_id: int) -> Path:
    return _DIR / f"{member_id}.json"


def load(member_id: int) -> dict:
    p = _path(member_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save(member_id: int, data: dict) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    _path(member_id).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_keyword(member_id: int, display_name: str, keyword: str) -> None:
    data = load(member_id)
    data.setdefault("display_name", display_name)
    keywords = data.get("keywords", [])
    if keyword not in keywords:
        keywords.append(keyword)
    data["keywords"] = keywords[-20:]
    save(member_id, data)


def set_field(member_id: int, display_name: str, field: str, value: str) -> None:
    data = load(member_id)
    data.setdefault("display_name", display_name)
    data[field] = value
    save(member_id, data)


def context_str(member_id: int, fallback_name: str) -> str:
    """Formatted context string for Claude."""
    data = load(member_id)
    if not data:
        return ""
    parts = []
    if data.get("keywords"):
        parts.append(f"특징: {', '.join(data['keywords'][-5:])}")
    if data.get("mbti"):
        parts.append(f"MBTI: {data['mbti']}")
    if data.get("saju"):
        parts.append(f"사주: {data['saju']}")
    if data.get("advice_mode"):
        parts.append(f"고민상담 모드: {data['advice_mode']}모드")
    return "\n".join(parts)


def format_for_display(member_id: int, fallback_name: str) -> str:
    """Human-readable info for the user to see."""
    data = load(member_id)
    if not data:
        return ""
    parts = []
    if data.get("keywords"):
        parts.append(f"특징: {', '.join(data['keywords'])}")
    if data.get("mbti"):
        parts.append(f"MBTI: {data['mbti']}")
    if data.get("saju"):
        parts.append(f"사주: {data['saju']}")
    if data.get("advice_mode"):
        mode = data["advice_mode"]
        label = "논리/팩트형" if mode == "T" else "공감/감성형"
        parts.append(f"고민상담 모드: {mode}모드 ({label})")
    return "\n".join(parts)
