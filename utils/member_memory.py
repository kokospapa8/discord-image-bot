"""Per-member persistent memory (keywords, MBTI, 사주, conversation)."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

_DIR = Path("/app/data/members")
_KST = timezone(timedelta(hours=9))
_MAX_CONV = 30


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


def delete_field(member_id: int, field: str) -> bool:
    """Delete a specific field. For 'keyword', clears all. Returns True if something was deleted."""
    data = load(member_id)
    if not data:
        return False
    if field == "keyword":
        if "keywords" not in data:
            return False
        data.pop("keywords")
    elif field in data:
        data.pop(field)
    else:
        return False
    save(member_id, data)
    return True


def delete_keyword(member_id: int, keyword: str) -> bool:
    """Delete a specific keyword entry."""
    data = load(member_id)
    keywords = data.get("keywords", [])
    kl = keyword.lower()
    new_kw = [k for k in keywords if k.lower() != kl]
    if len(new_kw) == len(keywords):
        return False
    data["keywords"] = new_kw
    save(member_id, data)
    return True


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
    """Formatted context string for Claude (conversation context, brief)."""
    data = load(member_id)
    if not data:
        return ""
    parts = []
    if data.get("keywords"):
        parts.append(f"특징: {', '.join(data['keywords'][-5:])}")
    if data.get("mbti"):
        parts.append(f"MBTI: {data['mbti']}")
    if data.get("saju_detail"):
        parts.append(f"[상세 사주 있음]")
    elif data.get("saju"):
        parts.append(f"사주: {data['saju']}")
    if data.get("advice_mode"):
        parts.append(f"고민상담 모드: {data['advice_mode']}모드")
    return "\n".join(parts)


def get_saju_for_fortune(member_id: int) -> tuple[str, str]:
    """Returns (saju_basic, saju_detail). Either may be empty."""
    data = load(member_id)
    return data.get("saju", ""), data.get("saju_detail", "")


def get_ziwei_birth(member_id: int) -> str:
    """Returns stored 자미두수 birth datetime string, or empty string."""
    return load(member_id).get("ziwei_birth", "")


# ── conversation pair memory ──────────────────────────────────────────────────

def add_conversation_pair(member_id: int, user_text: str, miffy_text: str) -> None:
    """Append a user↔miffy exchange. Compacts oldest entries when over _MAX_CONV."""
    data = load(member_id)
    pairs: list[dict] = data.get("conversation", [])
    pairs.append({
        "ts": datetime.now(_KST).isoformat(),
        "user": user_text[:300],
        "miffy": miffy_text[:300],
    })
    if len(pairs) > _MAX_CONV:
        _archive_pairs(member_id, pairs[:-_MAX_CONV])
        pairs = pairs[-_MAX_CONV:]
    data["conversation"] = pairs
    save(member_id, data)


def _archive_pairs(member_id: int, pairs: list[dict]) -> None:
    archive = _DIR / f"{member_id}_conv_archive.jsonl"
    _DIR.mkdir(parents=True, exist_ok=True)
    with archive.open("a", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")


def recent_conversation_str(member_id: int, n: int = 8) -> str:
    """Last N pairs formatted for Claude context."""
    data = load(member_id)
    pairs: list[dict] = data.get("conversation", [])[-n:]
    if not pairs:
        return ""
    lines: list[str] = []
    for p in pairs:
        lines.append(f"사용자: {p['user']}")
        lines.append(f"미피: {p['miffy']}")
    return "\n".join(lines)


def all_conversation_str(member_id: int) -> str:
    """All stored pairs (up to _MAX_CONV) — used when user explicitly requests full history."""
    data = load(member_id)
    pairs: list[dict] = data.get("conversation", [])
    if not pairs:
        return ""
    lines: list[str] = []
    for p in pairs:
        lines.append(f"사용자: {p['user']}")
        lines.append(f"미피: {p['miffy']}")
    return "\n".join(lines)


# ── daily ziwei (자미두수) cache ──────────────────────────────────────────────

def get_ziwei_cache(member_id: int) -> str:
    """Returns today's cached 자미두수 fortune, or empty string."""
    cache = load(member_id).get("ziwei_cache", {})
    today = datetime.now(_KST).strftime("%Y-%m-%d")
    return cache.get("fortune", "") if cache.get("date") == today else ""


def set_ziwei_cache(member_id: int, fortune: str) -> None:
    data = load(member_id)
    today = datetime.now(_KST).strftime("%Y-%m-%d")
    data["ziwei_cache"] = {"date": today, "fortune": fortune[:1500]}
    save(member_id, data)


# ── daily fortune cache ───────────────────────────────────────────────────────

def get_fortune_cache(member_id: int) -> str:
    """Returns today's cached fortune text, or empty string if not generated yet."""
    data = load(member_id)
    cache: dict = data.get("fortune_cache", {})
    today = datetime.now(_KST).strftime("%Y-%m-%d")
    if cache.get("date") == today:
        return cache.get("fortune", "")
    return ""


def set_fortune_cache(member_id: int, fortune: str) -> None:
    data = load(member_id)
    today = datetime.now(_KST).strftime("%Y-%m-%d")
    data["fortune_cache"] = {"date": today, "fortune": fortune[:1000]}
    save(member_id, data)


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
    if data.get("saju_detail"):
        parts.append("상세 사주: 등록됨 (년주/월주/일주/시주/오행/십신/대운 포함)")
    if data.get("ziwei_birth"):
        parts.append(f"자미두수 생년월일시: {data['ziwei_birth']}")
    if data.get("advice_mode"):
        mode = data["advice_mode"]
        label = "논리/팩트형" if mode == "T" else "공감/감성형"
        parts.append(f"고민상담 모드: {mode}모드 ({label})")
    if data.get("riot_id"):
        parts.append(f"Riot ID: {data['riot_id']}")
    return "\n".join(parts)
