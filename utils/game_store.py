"""Steam game wishlist storage."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

_FILE = Path("/app/data/games.json")
_KST = timezone(timedelta(hours=9))


def _now() -> str:
    return datetime.now(_KST).isoformat()


def load() -> dict:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"games": []}
    return {"games": []}


def save(data: dict) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_game(appid: str, name: str, url: str) -> bool:
    """Returns True if newly added."""
    data = load()
    for g in data["games"]:
        if g["appid"] == appid:
            return False
    data["games"].append({
        "appid": appid,
        "name": name,
        "url": url,
        "played": False,
        "added_at": _now(),
    })
    save(data)
    return True


def mark_played(query: str, played: bool = True) -> str | None:
    """Find by name (substring, case-insensitive) or appid. Returns game name or None."""
    data = load()
    q = query.lower()
    for g in data["games"]:
        if g["appid"] == query or q in g["name"].lower():
            g["played"] = played
            save(data)
            return g["name"]
    return None


def find_game(query: str) -> dict | None:
    q = query.lower()
    for g in load()["games"]:
        if g["appid"] == query or q in g["name"].lower():
            return g
    return None


def format_list(filter_: str = "all") -> str:
    """
    filter_: 'all' | 'unplayed' | 'played'
    Returns a human-readable string for Claude to present.
    """
    games = load()["games"]
    if filter_ == "unplayed":
        games = [g for g in games if not g["played"]]
    elif filter_ == "played":
        games = [g for g in games if g["played"]]

    if not games:
        return "목록이 비어있어."

    lines = []
    for g in games:
        status = "✅" if g["played"] else "⬜"
        line = f"{status} {g['name']}"
        if not g["played"]:
            line += f"\n   {g['url']}"
        lines.append(line)
    return "\n".join(lines)
